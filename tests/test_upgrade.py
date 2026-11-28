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
    with patch.dict(sys.modules, {"test_nod": package}):
        return importlib.import_module("test_nod.upgrade"), importlib.import_module("test_nod.release")


upgrade, release = load_upgrade()
PLAN = release.LEGACY_PLAN
BASELINE = PLAN.baseline
TARGET = PLAN.target


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
        self.installed = BASELINE.copy()
        self.offers = TARGET.copy()
        self.states = {role: "started" for role in self.installed}
        self.events = []
        self.fail = None
        self.incomplete_backup = False
        self.local_backup = True
        self.protected_backup = None
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
        if self.protected_backup is None:
            self.protected_backup = bool(options.password)
        self.backup_apps = [
            SimpleNamespace(slug=slug, version=self.installed[role])
            for slug, role in self.slugs.items()
            if not (self.incomplete_backup and role == "Workspace")
        ]
        return SimpleNamespace(slug="backup1")

    async def backup_info(self, slug):
        assert slug == "backup1"
        return SimpleNamespace(
            addons=self.backup_apps,
            type="partial",
            location_attributes={
                ".local": SimpleNamespace(size_bytes=4096, protected=self.protected_backup)
            } if self.local_backup else {},
            homeassistant=None,
            folders=[],
        )

    async def update_addon(self, slug, options):
        role = self.slugs[slug]
        assert not options.backup and not options.background
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
        await self.job.run(BASELINE, PLAN)
        self.assertEqual(self.supervisor.installed, TARGET)
        self.assertEqual(self.supervisor.events, [
            ("stop", "Server"), ("stop", "Workspace"), ("backup", None),
            ("update", "Workspace"), ("update", "Browser"), ("update", "Server"),
            ("start", "Workspace"), ("start", "Server"),
        ])
        self.assertIsNone(self.store.data)

    async def test_does_not_run_against_a_partial_catalog(self):
        self.supervisor.offers["Browser"] = BASELINE["Browser"]
        with self.assertRaisesRegex(upgrade.UpgradeBlocked, "catalog_changed"):
            await self.job.run(BASELINE, PLAN)
        self.assertEqual(self.supervisor.events, [])
        self.assertIsNone(self.store.data)

    async def test_incomplete_backup_blocks_changes_and_restarts_old_apps(self):
        self.supervisor.incomplete_backup = True
        with self.assertRaisesRegex(upgrade.UpgradeBlocked, "backup_incomplete"):
            await self.job.run(BASELINE, PLAN)
        self.assertEqual(self.supervisor.installed, BASELINE)
        self.assertEqual(set(self.supervisor.states.values()), {"started"})
        self.assertIsNone(self.store.data["backup_id"])

    async def test_copy_missing_from_local_storage_blocks_updates(self):
        self.supervisor.local_backup = False
        with self.assertRaisesRegex(upgrade.UpgradeBlocked, "backup_incomplete"):
            await self.job.run(BASELINE, PLAN)
        self.assertEqual(self.supervisor.installed, BASELINE)
        self.assertEqual(set(self.supervisor.states.values()), {"started"})
        self.assertIsNone(self.store.data["backup_id"])

    async def test_refuses_unprotected_backup_when_a_password_was_supplied(self):
        self.supervisor.protected_backup = False
        job = upgrade.NodUpgrade(self.supervisor, self.store, "test", backup_password="synthetic")
        with self.assertRaisesRegex(upgrade.UpgradeBlocked, "backup_not_protected"):
            await job.run(BASELINE, PLAN)
        self.assertEqual(self.supervisor.installed, BASELINE)
        self.assertEqual(set(self.supervisor.states.values()), {"started"})
        self.assertIsNone(self.store.data["backup_id"])

    async def test_resume_uses_the_original_backup_after_partial_update(self):
        self.supervisor.fail = "Browser"
        with self.assertRaises(RuntimeError):
            await self.job.run(BASELINE, PLAN)
        self.assertEqual(self.supervisor.installed["Workspace"], TARGET["Workspace"])
        self.assertEqual(self.store.data["backup_id"], "backup1")
        self.assertEqual(set(self.supervisor.states.values()), {"stopped"})

        self.supervisor.fail = None
        resumed = upgrade.NodUpgrade(self.supervisor, self.store, "test")
        await resumed.run(self.supervisor.installed.copy(), PLAN)
        self.assertEqual(self.supervisor.events.count(("backup", None)), 1)
        self.assertEqual(self.supervisor.events.count(("update", "Workspace")), 1)
        self.assertEqual(self.supervisor.installed, TARGET)
        self.assertIsNone(self.store.data)

    async def test_never_adopts_an_untracked_partial_upgrade(self):
        self.supervisor.installed["Browser"] = TARGET["Browser"]
        with self.assertRaisesRegex(upgrade.UpgradeBlocked, "unsupported_versions"):
            await self.job.run(self.supervisor.installed.copy(), PLAN)
        self.assertEqual(self.supervisor.events, [])

    async def test_rejects_an_installed_version_that_changed_after_review(self):
        with self.assertRaisesRegex(upgrade.UpgradeBlocked, "versions_changed"):
            await self.job.run(TARGET, PLAN)
        self.assertEqual(self.supervisor.events, [])

    async def test_rechecks_catalog_after_each_component_update(self):
        update_addon = self.supervisor.update_addon

        async def change_offer_after_update(slug, options):
            await update_addon(slug, options)
            self.supervisor.offers["Browser"] = BASELINE["Browser"]

        self.supervisor.update_addon = change_offer_after_update
        with self.assertRaisesRegex(upgrade.UpgradeBlocked, "catalog_changed"):
            await self.job.run(BASELINE, PLAN)
        updates = [role for event, role in self.supervisor.events if event == "update"]
        self.assertEqual(updates, ["Workspace"])
        self.assertEqual(self.store.data["backup_id"], "backup1")

    async def test_applies_a_future_manifest_plan_with_an_unchanged_worker(self):
        self.supervisor.installed = TARGET.copy()
        self.supervisor.offers = {
            "Server": "0.1.0-dev.36", "Browser": "0.1.0-dev.7", "Workspace": "0.1.0-dev.8",
        }
        manifest = release.parse_manifest({
            "repository": "n8n-io/nod", "tag": "nod-v0.11.0", "revision": "1" * 40,
            "ha_upgrade": {
                "schema": 1, "target": self.supervisor.offers, "supported_from": [TARGET],
            },
        })
        plan = manifest.select(self.supervisor.installed, None)
        await self.job.run(TARGET, plan)
        self.assertEqual(self.supervisor.installed, plan.target)
        self.assertEqual([role for event, role in self.supervisor.events if event == "update"],
                         ["Workspace", "Server"])
        self.assertEqual({app.version for app in self.supervisor.backup_apps}, set(TARGET.values()))
        self.assertIsNone(self.store.data)

    async def test_resumes_a_legacy_journal_with_the_same_approved_plan(self):
        self.supervisor.fail = "Browser"
        with self.assertRaises(RuntimeError):
            await self.job.run(BASELINE, PLAN)
        self.store.data["target"] = self.store.data.pop("plan")["target"]
        self.supervisor.fail = None
        resumed = upgrade.NodUpgrade(self.supervisor, self.store, "test")
        await resumed.run(self.supervisor.installed.copy(), PLAN)
        self.assertEqual(self.supervisor.events.count(("backup", None)), 1)
        self.assertEqual(self.supervisor.installed, TARGET)

    async def test_refuses_a_recovery_plan_that_changed_after_review(self):
        self.store.data = {
            "plan": {**PLAN.record(), "revision": "1" * 40},
            "running": ["Server", "Browser", "Workspace"],
            "backup_id": "backup1",
        }
        with self.assertRaisesRegex(upgrade.UpgradeBlocked, "recovery_plan_changed"):
            await self.job.run(BASELINE, PLAN)
        self.assertEqual(self.supervisor.events, [])
        self.assertEqual(self.store.data["backup_id"], "backup1")
