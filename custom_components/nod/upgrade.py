"""Coordinate a verified Nod release set with Home Assistant Supervisor."""
import asyncio
from dataclasses import dataclass

from aiohasupervisor.models import PartialBackupOptions, StoreAddonUpdate

from .inventory import ROLES

BASELINE = {
    "Server": "0.1.0-dev.34",
    "Browser": "0.1.0-dev.6",
    "Workspace": "0.1.0-dev.6",
}
TARGET = {
    "Server": "0.1.0-dev.35",
    "Browser": "0.1.0-dev.7",
    "Workspace": "0.1.0-dev.7",
}
UPDATE_ORDER = ("Workspace", "Browser", "Server")


class UpgradeBlocked(Exception):
    """The catalog, installed apps or backup do not meet the upgrade preconditions."""


@dataclass(frozen=True)
class AppVersion:
    """The installed version and current offer for a single app."""

    installed: str
    offered: str
    state: str


class NodUpgrade:
    """Update an adopted set of apps and retain recovery state across HA restarts."""

    def __init__(self, client, store, prefix, *, backup_password=None):
        self.client = client
        self.store = store
        self.backup_password = backup_password
        self.slugs = {role: f"{prefix}_{name}" for role, name in ROLES.items()}
        self.stage = "preflight"
        self.backup_id = None

    async def inspect(self):
        """Read live Supervisor state, including the version the store will install."""
        async def app(slug):
            installed, offered = await asyncio.gather(
                self.client.addons.addon_info(slug),
                self.client.store.addon_info(slug),
            )
            return AppVersion(installed.version, offered.version_latest, installed.state)

        results = await asyncio.gather(*(app(slug) for slug in self.slugs.values()))
        return dict(zip(self.slugs, results, strict=True))

    @staticmethod
    def versions(apps):
        return {role: app.installed for role, app in apps.items()}

    def check(self, apps, pending):
        """Refuse arbitrary version combinations and offers below installed versions."""
        if any(app.state not in ("started", "stopped") for app in apps.values()):
            raise UpgradeBlocked("busy_or_unavailable")
        if any(app.offered != TARGET[role] for role, app in apps.items()):
            raise UpgradeBlocked("catalog_changed")
        allowed = TARGET if pending and pending.get("backup_id") else BASELINE
        if any(app.installed not in (BASELINE[role], allowed[role]) for role, app in apps.items()):
            raise UpgradeBlocked("unsupported_versions")

    async def _stop(self, apps):
        for role, app in apps.items():
            self.stage = f"stop / {role}"
            if app.state == "started":
                await self.client.addons.stop_addon(self.slugs[role])
            current = await self.client.addons.addon_info(self.slugs[role])
            if current.state != "stopped" or current.version != app.installed:
                raise UpgradeBlocked("stop_failed")

    async def _start(self, roles, expected):
        for role in UPDATE_ORDER:
            if role not in roles:
                continue
            self.stage = f"start / {role}"
            slug = self.slugs[role]
            current = await self.client.addons.addon_info(slug)
            if current.version != expected[role] or current.state not in ("started", "stopped"):
                raise UpgradeBlocked("start_failed")
            if current.state == "stopped":
                await self.client.addons.start_addon(slug)
                current = await self.client.addons.addon_info(slug)
            if current.version != expected[role] or current.state != "started":
                raise UpgradeBlocked("start_failed")

    async def _check_backup(self):
        self.stage = "verify backup"
        details = await self.client.backups.backup_info(self.backup_id)
        expected = {slug: BASELINE[role] for role, slug in self.slugs.items()}
        location = details.location_attributes.get(".local")
        if (
            details.type != "partial"
            or details.homeassistant is not None
            or details.folders
            or {app.slug: app.version for app in details.addons} != expected
            or not location
            or location.size_bytes <= 0
        ):
            raise UpgradeBlocked("backup_incomplete")
        return location

    async def run(self, reviewed_versions):
        """Apply the reviewed set, or resume a previous attempt with its original backup."""
        pending = await self.store.async_load()
        if pending:
            if pending.get("target") != TARGET:
                raise UpgradeBlocked("unsupported_versions")
            self.backup_id = pending.get("backup_id")
        apps = await self.inspect()
        self.check(apps, pending)
        if self.versions(apps) != reviewed_versions:
            raise UpgradeBlocked("versions_changed")

        for slug in self.slugs.values():
            await self.client.store.addon_availability(slug)
        if pending is None:
            pending = {
                "target": TARGET,
                "running": [role for role, app in apps.items() if app.state == "started"],
                "backup_id": None,
            }
            # Preserve intended running states even if Core restarts while apps are stopped.
            await self.store.async_save(pending)

        try:
            await self._stop(apps)
            if not self.backup_id:
                self.stage = "create backup"
                backup = await self.client.backups.partial_backup(
                    PartialBackupOptions(
                        name="Nod before upgrade to 0.10.3",
                        addons=set(self.slugs.values()),
                        location=".local",
                        password=self.backup_password,
                        background=False,
                    )
                )
                self.backup_id = backup.slug
                if not self.backup_id:
                    raise UpgradeBlocked("backup_incomplete")
                location = await self._check_backup()
                if self.backup_password and not location.protected:
                    raise UpgradeBlocked("backup_not_protected")
                await self.store.async_save({**pending, "backup_id": self.backup_id})
            else:
                await self._check_backup()
        except (Exception, asyncio.CancelledError):
            # Before any version change, recover the old services after a failed stop/backup.
            current = await self.inspect()
            if self.versions(current) == BASELINE:
                stage = self.stage
                try:
                    await self._start(pending["running"], BASELINE)
                finally:
                    self.stage = stage
            raise

        for role in UPDATE_ORDER:
            self.stage = f"update / {role}"
            apps = await self.inspect()
            self.check(apps, {"backup_id": self.backup_id})
            if any(app.state != "stopped" for app in apps.values()):
                raise UpgradeBlocked("versions_changed")
            if apps[role].installed != TARGET[role]:
                slug = self.slugs[role]
                await self.client.store.update_addon(slug, StoreAddonUpdate(backup=False, background=False))
                current = await self.client.addons.addon_info(slug)
                if current.version != TARGET[role] or current.state != "stopped":
                    raise UpgradeBlocked("update_failed")

        self.stage = "verify versions"
        apps = await self.inspect()
        if self.versions(apps) != TARGET:
            raise UpgradeBlocked("update_failed")
        await self._start(pending["running"], TARGET)
        self.stage = "verify startup"
        apps = await self.inspect()
        for role, app in apps.items():
            expected_state = "started" if role in pending["running"] else "stopped"
            if app.installed != TARGET[role] or app.state != expected_state:
                raise UpgradeBlocked("start_failed")
        await self.store.async_remove()
