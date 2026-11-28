import importlib
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import patch


def load_upgrade():
    root = Path("custom_components/nod").resolve()
    package = ModuleType("test_nod")
    package.__path__ = [str(root)]
    supervisor = ModuleType("aiohasupervisor.models")
    supervisor.PartialBackupOptions = SimpleNamespace
    supervisor.StoreAddonUpdate = SimpleNamespace
    with patch.dict(sys.modules, {"test_nod": package, "aiohasupervisor.models": supervisor}):
        return importlib.import_module("test_nod.upgrade")


upgrade = load_upgrade()


class MemoryStore:
    data = None

    async def async_load(self):
        return self.data

    async def async_save(self, data):
        self.data = data

    async def async_remove(self):
        self.data = None


class Supervisor:
    def __init__(self):
        self.addons = self.store = self.backups = self
        self.installed = upgrade.BASELINE.copy()
        self.offers = upgrade.TARGET.copy()
        self.states = {role: "started" for role in self.installed}
        self.events = []
        self.fail = None
        self.incomplete_backup = False
        self.backup_apps = []
        self.slugs = {f"test_{suffix}": role for role, suffix in upgrade.ROLES.items()}

    async def addon_info(self, slug):
        role = self.slugs[slug]
        return SimpleNamespace(
            version=self.installed[role], version_latest=self.offers[role], state=self.states[role],
        )

    async def addon_availability(self, slug):
        self.slugs[slug]

    async def stop_addon(self, slug):
        role = self.slugs[slug]
        self.states[role] = "stopped"
        self.events.append(("stop", role))

    async def start_addon(self, slug):
        role = self.slugs[slug]
        self.states[role] = "started"
        self.events.append(("start", role))

    async def partial_backup(self, options):
        assert options.addons == set(self.slugs)
        assert options.location == ".local" and not options.background
        assert set(self.states.values()) == {"stopped"}
        self.events.append(("backup", None))
        self.backup_apps = [
            SimpleNamespace(slug=slug, version=self.installed[role])
            for slug, role in self.slugs.items()
            if not (self.incomplete_backup and role == "Workspace")
        ]
        return SimpleNamespace(slug="backup1")

    async def backup_info(self, slug):
        assert slug == "backup1"
        return SimpleNamespace(addons=self.backup_apps)

    async def update_addon(self, slug, options):
        role = self.slugs[slug]
        assert not options.backup
        assert set(self.states.values()) == {"stopped"}
        if self.fail == role:
            raise RuntimeError("synthetic interrupted update")
        self.installed[role] = self.offers[role]
        self.events.append(("update", role))


class CoordinatedUpgradeTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.supervisor = Supervisor()
        self.store = MemoryStore()
        self.job = upgrade.NodUpgrade(self.supervisor, self.store, "test")

    async def test_snapshots_all_three_before_updates_and_preserves_running_states(self):
        self.supervisor.states["Browser"] = "stopped"
        await self.job.run(upgrade.BASELINE)
        self.assertEqual(self.supervisor.installed, upgrade.TARGET)
        self.assertEqual(self.supervisor.events, [
            ("stop", "Server"), ("stop", "Workspace"), ("backup", None),
            ("update", "Workspace"), ("update", "Browser"), ("update", "Server"),
            ("start", "Server"), ("start", "Workspace"),
        ])
        self.assertIsNone(self.store.data)

    async def test_does_not_run_against_a_partial_catalog(self):
        self.supervisor.offers["Browser"] = upgrade.BASELINE["Browser"]
        with self.assertRaisesRegex(upgrade.UpgradeBlocked, "catalog_changed"):
            await self.job.run(upgrade.BASELINE)
        self.assertEqual(self.supervisor.events, [])
        self.assertIsNone(self.store.data)

    async def test_incomplete_backup_blocks_changes_and_restarts_old_apps(self):
        self.supervisor.incomplete_backup = True
        with self.assertRaisesRegex(upgrade.UpgradeBlocked, "backup_incomplete"):
            await self.job.run(upgrade.BASELINE)
        self.assertEqual(self.supervisor.installed, upgrade.BASELINE)
        self.assertEqual(set(self.supervisor.states.values()), {"started"})
        self.assertIsNone(self.store.data["backup_id"])

    async def test_resume_uses_the_original_backup_after_partial_update(self):
        self.supervisor.fail = "Browser"
        with self.assertRaises(RuntimeError):
            await self.job.run(upgrade.BASELINE)
        self.assertEqual(self.supervisor.installed["Workspace"], upgrade.TARGET["Workspace"])
        self.assertEqual(self.store.data["backup_id"], "backup1")
        self.assertEqual(set(self.supervisor.states.values()), {"stopped"})

        self.supervisor.fail = None
        resumed = upgrade.NodUpgrade(self.supervisor, self.store, "test")
        await resumed.run(self.supervisor.installed.copy())
        self.assertEqual(self.supervisor.events.count(("backup", None)), 1)
        self.assertEqual(self.supervisor.events.count(("update", "Workspace")), 1)
        self.assertEqual(self.supervisor.installed, upgrade.TARGET)
        self.assertIsNone(self.store.data)

    async def test_never_adopts_an_untracked_partial_upgrade(self):
        self.supervisor.installed["Browser"] = upgrade.TARGET["Browser"]
        with self.assertRaisesRegex(upgrade.UpgradeBlocked, "unsupported_versions"):
            await self.job.run(self.supervisor.installed.copy())
        self.assertEqual(self.supervisor.events, [])

    async def test_rejects_an_installed_version_that_changed_after_review(self):
        with self.assertRaisesRegex(upgrade.UpgradeBlocked, "versions_changed"):
            await self.job.run(upgrade.TARGET)
        self.assertEqual(self.supervisor.events, [])

    async def test_rechecks_catalog_after_each_component_update(self):
        update_addon = self.supervisor.update_addon

        async def change_offer_after_update(slug, options):
            await update_addon(slug, options)
            self.supervisor.offers["Browser"] = upgrade.BASELINE["Browser"]

        self.supervisor.update_addon = change_offer_after_update
        with self.assertRaisesRegex(upgrade.UpgradeBlocked, "catalog_changed"):
            await self.job.run(upgrade.BASELINE)
        updates = [role for event, role in self.supervisor.events if event == "update"]
        self.assertEqual(updates, ["Workspace"])
        self.assertEqual(self.store.data["backup_id"], "backup1")
