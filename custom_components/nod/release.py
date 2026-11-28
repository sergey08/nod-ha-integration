"""Read the coordinated update published by the Nod app catalog."""
from dataclasses import dataclass
import json
import re

from aiohttp import ClientError, ClientTimeout

from .inventory import ROLES


CATALOG = "https://github.com/sergey08/homeassistant-addons"
SOURCE = f"{CATALOG}#feat/nod-home-assistant"
MANIFEST_URLS = {
    f"{CATALOG}#{branch}":
        f"https://raw.githubusercontent.com/sergey08/homeassistant-addons/{branch}/nod-upstream.json"
    for branch in ("feat/nod-home-assistant", "test/nod-0.10.3-vmware")
}
MAX_MANIFEST_BYTES = 16_384
NUMBER = r"0|[1-9][0-9]{0,7}"
APP_VERSION = re.compile(
    rf"({NUMBER})\.({NUMBER})\.({NUMBER})(?:-(dev|alpha|beta|rc)\.({NUMBER}))?"
)
RELEASE_TAG = re.compile(r"nod-v[0-9]+\.[0-9]+\.[0-9]+")
REVISION = re.compile(r"[0-9a-f]{40}")
STAGES = {"dev": 0, "alpha": 1, "beta": 2, "rc": 3, None: 4}


class UpgradeBlocked(Exception):
    """The catalog, installed apps or backup do not meet the upgrade preconditions."""


@dataclass(frozen=True)
class UpgradePlan:
    """Exact app versions and pinned upstream release reviewed during an update."""

    baseline: dict[str, str]
    target: dict[str, str]
    tag: str
    revision: str

    def record(self):
        return {
            "baseline": self.baseline,
            "target": self.target,
            "tag": self.tag,
            "revision": self.revision,
        }


# Read journals already created by v0.1.0b10. These versions cannot authorize
# a new update without also appearing in the catalog manifest.
LEGACY_PLAN = UpgradePlan(
    {"Server": "0.1.0-dev.34", "Browser": "0.1.0-dev.6", "Workspace": "0.1.0-dev.6"},
    {"Server": "0.1.0-dev.35", "Browser": "0.1.0-dev.7", "Workspace": "0.1.0-dev.7"},
    "nod-v0.10.3",
    "8494bcf12030451ad1093f0579bba57caf34c1d9",
)


def recovery_matches(pending, plan):
    """Check that the saved recovery point describes exactly this plan."""
    if not isinstance(pending, dict):
        return False
    running = pending.get("running")
    backup_id = pending.get("backup_id")
    if (
        not isinstance(running, list)
        or any(not isinstance(role, str) or role not in ROLES for role in running)
        or len(set(running)) != len(running)
        or not (backup_id is None or isinstance(backup_id, str) and backup_id)
    ):
        return False
    if "plan" in pending:
        return pending["plan"] == plan.record()
    return plan == LEGACY_PLAN and pending.get("target") == plan.target


@dataclass(frozen=True)
class Release:
    """The store's destination release and the tested ways to get there."""

    tag: str
    revision: str
    target: dict[str, str]
    supported_from: tuple[dict[str, str], ...]

    def select(self, installed, pending):
        """Select an explicitly approved transition or its exact saved recovery point."""
        if pending is None and installed == self.target:
            raise UpgradeBlocked("up_to_date")
        for baseline in self.supported_from:
            plan = UpgradePlan(baseline, self.target, self.tag, self.revision)
            if pending is None and installed == baseline:
                return plan
            if pending is not None and recovery_matches(pending, plan):
                return plan
        raise UpgradeBlocked(
            "recovery_plan_changed" if pending is not None else "unsupported_versions"
        )


def version_order(versions):
    if not isinstance(versions, dict) or set(versions) != set(ROLES):
        raise ValueError("Invalid Nod app version set")
    ordered = {}
    for role, version in versions.items():
        match = APP_VERSION.fullmatch(version) if isinstance(version, str) else None
        if match is None:
            raise ValueError("Invalid Nod app version")
        major, minor, patch, stage, number = match.groups()
        ordered[role] = (int(major), int(minor), int(patch), STAGES[stage], int(number or 0))
    return ordered


def parse_manifest(document):
    """Verify the schema and reject ambiguous, unchanged or decreasing migrations."""
    if not isinstance(document, dict) or document.get("repository") != "n8n-io/nod":
        raise ValueError("Invalid Nod upstream repository")
    tag = document.get("tag")
    revision = document.get("revision")
    if not isinstance(tag, str) or not RELEASE_TAG.fullmatch(tag):
        raise ValueError("Invalid Nod upstream tag")
    if not isinstance(revision, str) or not REVISION.fullmatch(revision):
        raise ValueError("Invalid Nod upstream revision")

    upgrade = document.get("ha_upgrade")
    if (
        not isinstance(upgrade, dict)
        or set(upgrade) != {"schema", "target", "supported_from"}
        or type(upgrade["schema"]) is not int
        or upgrade["schema"] != 1
    ):
        raise ValueError("Unknown Nod upgrade schema")
    target = upgrade["target"]
    ordered_target = version_order(target)
    sources = upgrade["supported_from"]
    if not isinstance(sources, list) or not sources:
        raise ValueError("Missing Nod upgrade origins")

    approved = []
    for baseline in sources:
        ordered_baseline = version_order(baseline)
        if (
            baseline in approved
            or ordered_baseline == ordered_target
            or any(ordered_baseline[role] > ordered_target[role] for role in ROLES)
        ):
            raise ValueError("Invalid Nod upgrade transition")
        approved.append(baseline)
    return Release(tag, revision, target, tuple(approved))


async def fetch_release(session, client, prefix):
    """Use the known manifest URL for the catalog the adopted apps belong to."""
    repository = await client.store.repository_info(prefix)
    if repository.source not in MANIFEST_URLS or repository.slug != prefix:
        raise UpgradeBlocked("untrusted_catalog")

    try:
        async with session.get(
            MANIFEST_URLS[repository.source], timeout=ClientTimeout(total=10),
            allow_redirects=False,
        ) as response:
            if response.status != 200:
                raise UpgradeBlocked("manifest_unavailable")
            document = bytearray()
            async for chunk in response.content.iter_chunked(4096):
                document.extend(chunk)
                if len(document) > MAX_MANIFEST_BYTES:
                    raise ValueError("Nod upgrade manifest too large")
        return parse_manifest(json.loads(document))
    except (ClientError, TimeoutError) as err:
        raise UpgradeBlocked("manifest_unavailable") from err
    except (ValueError, RecursionError) as err:
        raise UpgradeBlocked("invalid_manifest") from err
