"""Validate catalog selection and recovery against versioned manifests."""
from copy import deepcopy
import json
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock

from test_upgrade import BASELINE, PLAN, TARGET, release


def manifest():
    return {
        "repository": "n8n-io/nod",
        "tag": PLAN.tag,
        "revision": PLAN.revision,
        "ha_upgrade": {"schema": 1, "target": TARGET.copy(), "supported_from": [BASELINE.copy()]},
    }


class ReleaseTest(unittest.TestCase):
    def test_selects_only_an_approved_complete_version_set(self):
        approved = release.parse_manifest(manifest())
        self.assertEqual(approved.select(BASELINE, None), PLAN)
        with self.assertRaisesRegex(release.UpgradeBlocked, "up_to_date"):
            approved.select(TARGET, None)
        with self.assertRaisesRegex(release.UpgradeBlocked, "unsupported_versions"):
            approved.select({**BASELINE, "Workspace": TARGET["Workspace"]}, None)

    def test_rejects_invalid_or_downgrade_manifests(self):
        original = manifest()
        variants = [
            ("ha_upgrade", None),
            ("revision", "not-a-revision"),
            ("tag", "latest"),
            ("ha_upgrade", {**original["ha_upgrade"], "schema": True}),
            ("ha_upgrade", {**original["ha_upgrade"], "target": {"Server": "0.1.0-dev.35"}}),
            ("ha_upgrade", {**original["ha_upgrade"], "supported_from": [TARGET]}),
            ("ha_upgrade", {**original["ha_upgrade"], "supported_from": [BASELINE, BASELINE]}),
            ("ha_upgrade", {**original["ha_upgrade"], "supported_from": [{**BASELINE, "Browser": "0.1.0-dev.10"}]}),
        ]
        for key, value in variants:
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                release.parse_manifest({**original, key: value})

    def test_preserves_exact_saved_plan_and_refuses_a_rewritten_revision(self):
        approved = release.parse_manifest(manifest())
        installed = {**BASELINE, "Workspace": TARGET["Workspace"]}
        pending = {"plan": PLAN.record(), "running": ["Server"], "backup_id": "backup1"}
        self.assertEqual(approved.select(installed, pending), PLAN)
        changed = release.parse_manifest({**manifest(), "revision": "2" * 40})
        with self.assertRaisesRegex(release.UpgradeBlocked, "recovery_plan_changed"):
            changed.select(installed, deepcopy(pending))
        with self.assertRaisesRegex(release.UpgradeBlocked, "recovery_plan_changed"):
            approved.select(installed, {**pending, "running": ["Server", "Other"]})


class ManifestFetchTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.session = Mock()
        self.client = SimpleNamespace(store=SimpleNamespace(repository_info=AsyncMock()))
        self.client.store.repository_info.return_value = SimpleNamespace(
            slug="test", source=release.SOURCE,
        )

    def response(self, status, payload):
        async def chunks(size):
            for offset in range(0, len(payload), size):
                yield payload[offset:offset + size]

        response = SimpleNamespace(status=status, content=SimpleNamespace(iter_chunked=chunks))
        request = AsyncMock()
        request.__aenter__.return_value = response
        self.session.get.return_value = request

    async def test_reads_the_approved_location_without_redirects(self):
        self.response(200, json.dumps(manifest()).encode())
        approved = await release.fetch_release(self.session, self.client, "test")
        self.assertEqual(approved.select(BASELINE, None), PLAN)
        self.client.store.repository_info.assert_awaited_once_with("test")
        call = self.session.get.call_args
        self.assertEqual(call.args, (release.MANIFEST_URLS[release.SOURCE],))
        self.assertFalse(call.kwargs["allow_redirects"])

    async def test_unknown_catalog_cannot_trigger_a_network_request(self):
        self.client.store.repository_info.return_value.source = "https://github.com/example/nod"
        with self.assertRaisesRegex(release.UpgradeBlocked, "untrusted_catalog"):
            await release.fetch_release(self.session, self.client, "test")
        self.session.get.assert_not_called()

    async def test_refuses_redirects_and_oversize_manifests(self):
        self.response(302, b"")
        with self.assertRaisesRegex(release.UpgradeBlocked, "manifest_unavailable"):
            await release.fetch_release(self.session, self.client, "test")
        self.response(200, b" " * (release.MAX_MANIFEST_BYTES + 1))
        with self.assertRaisesRegex(release.UpgradeBlocked, "invalid_manifest"):
            await release.fetch_release(self.session, self.client, "test")
