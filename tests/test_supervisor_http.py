"""Exercise Nod's upgrade against the Supervisor client used by Home Assistant."""
import unittest

from aiohasupervisor import SupervisorClient
from aiohttp import web
from aiohttp.test_utils import TestServer

from test_upgrade import MemoryStore, Supervisor, upgrade


class SupervisorHTTPTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.supervisor = Supervisor()
        self.store = MemoryStore()
        api = web.Application()
        api.add_routes([
            web.get("/addons/{slug}/info", self.installed_info),
            web.post("/addons/{slug}/stop", self.stop),
            web.post("/addons/{slug}/start", self.start),
            web.get("/store/addons/{slug}", self.store_info),
            web.get("/store/addons/{slug}/availability", self.availability),
            web.post("/store/addons/{slug}/update", self.update),
            web.post("/backups/new/partial", self.backup),
            web.get("/backups/{slug}/info", self.backup_info),
        ])
        server = TestServer(api)
        await server.start_server()
        self.addAsyncCleanup(server.close)
        self.url = str(server.make_url("/"))

    def respond(self, request, data=None):
        self.assertEqual(request.headers.get("Authorization"), "Bearer synthetic-token")
        return web.json_response({"result": "ok", "data": data or {}})

    def app_data(self, slug):
        role = self.supervisor.slugs[slug]
        installed = self.supervisor.installed[role]
        offered = self.supervisor.offers[role]
        return {
            "slug": slug, "name": role, "description": "Synthetic Nod app",
            "stage": "experimental", "repository": "test", "url": None,
            "version": installed, "version_latest": offered,
            "update_available": installed != offered,
            "advanced": False, "available": True, "build": False, "homeassistant": None,
            "icon": False, "logo": False, "arch": ["amd64"], "documentation": False,
            "apparmor": "default", "auth_api": False, "docker_api": False,
            "full_access": False, "homeassistant_api": False, "host_network": False,
            "host_pid": False, "ingress": role == "Server", "long_description": None,
            "rating": 7, "signed": False, "hassio_api": False, "hassio_role": "default",
            "detached": False,
        }

    async def installed_info(self, request):
        slug = request.match_info["slug"]
        role = self.supervisor.slugs[slug]
        data = {
            **self.app_data(slug),
            "hostname": slug.replace("_", "-"), "dns": [], "state": self.supervisor.states[role],
            "protected": True, "boot": "auto", "boot_config": "auto", "options": {},
            "schema": None, "machine": [], "network": None, "network_description": None,
            "host_ipc": False, "host_uts": False, "host_dbus": False, "privileged": [],
            "changelog": False, "stdin": False, "gpio": False, "usb": False, "uart": False,
            "kernel_modules": False, "devicetree": False, "udev": False, "video": False,
            "audio": False, "startup": "application", "services": [], "discovery": [],
            "translations": {}, "webui": None, "ingress_entry": None, "ingress_url": None,
            "ingress_port": None, "ingress_panel": None, "audio_input": None,
            "audio_output": None, "auto_update": False, "ip_address": "0.0.0.0",
            "watchdog": False, "devices": [], "system_managed": False,
            "system_managed_config_entry": None,
        }
        return self.respond(request, data)

    async def store_info(self, request):
        return self.respond(request, {**self.app_data(request.match_info["slug"]), "installed": True})

    async def availability(self, request):
        await self.supervisor.addon_availability(request.match_info["slug"])
        return self.respond(request)

    async def start(self, request):
        await self.supervisor.start_addon(request.match_info["slug"])
        return self.respond(request)

    async def stop(self, request):
        await self.supervisor.stop_addon(request.match_info["slug"])
        return self.respond(request)

    async def update(self, request):
        body = await request.json()
        self.assertEqual(body, {"backup": False, "background": False})
        slug = request.match_info["slug"]
        await self.supervisor.update_addon(slug, upgrade.StoreAddonUpdate(**body))
        return self.respond(request)

    async def backup(self, request):
        body = await request.json()
        self.assertEqual(set(body.pop("addons")), set(self.supervisor.slugs))
        self.assertEqual(body, {
            "name": "Nod before upgrade to 0.10.3",
            "location": ".local",
            "password": "synthetic-backup-password",
            "background": False,
        })
        options = upgrade.PartialBackupOptions(addons=set(self.supervisor.slugs), **body)
        await self.supervisor.partial_backup(options)
        return self.respond(request, {"slug": "backup1", "job_id": "c5293cd9-2e2d-42c5-b181-0ebccb10cc9d"})

    async def backup_info(self, request):
        result = await self.supervisor.backup_info(request.match_info["slug"])
        return self.respond(request, {
            "slug": "backup1", "type": "partial", "name": "Nod test",
            "date": "2026-11-28T08:00:00+00:00", "compressed": True,
            "location_attributes": {".local": {"size_bytes": 4096, "protected": True}},
            "supervisor_version": "2026.09.2", "homeassistant": None,
            "addons": [
                {"slug": app.slug, "version": app.version, "name": app.slug, "size": 1}
                for app in result.addons
            ],
            "repositories": [], "folders": [], "homeassistant_exclude_database": None, "extra": None,
        })

    async def test_coordinated_update_through_the_real_client(self):
        async with SupervisorClient(self.url, "synthetic-token") as client:
            job = upgrade.NodUpgrade(client, self.store, "test", backup_password="synthetic-backup-password")
            await job.run(upgrade.BASELINE)

        self.assertEqual(self.supervisor.installed, upgrade.TARGET)
        self.assertEqual(self.supervisor.events, [
            ("stop", "Server"), ("stop", "Browser"), ("stop", "Workspace"),
            ("backup", None),
            ("update", "Workspace"), ("update", "Browser"), ("update", "Server"),
            ("start", "Workspace"), ("start", "Browser"), ("start", "Server"),
        ])
        self.assertEqual(set(self.supervisor.states.values()), {"started"})
        self.assertEqual(job.backup_id, "backup1")
        self.assertIsNone(self.store.data)
