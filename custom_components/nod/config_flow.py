"""Install or manage the Nod apps for Home Assistant."""
import asyncio
import logging
from homeassistant.core import callback
from homeassistant.components.hassio.addon_manager import AddonError, AddonManager, AddonState
from .inventory import ROLES
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.components.backup import async_get_manager as async_get_backup_manager
from homeassistant.components.hassio.coordinator import get_addons_list
from homeassistant.components.hassio.handler import get_supervisor_client
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.storage import Store

from .release import UpgradeBlocked, fetch_release
from .upgrade import NodUpgrade

_LOGGER = logging.getLogger(__name__)

class NodFlow(config_entries.ConfigFlow, domain="nod"):
    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return NodOptionsFlow()

    async def async_step_user(self, user_input=None):
        suffix = "_nod_native_preflight"
        servers = sorted(app["slug"] for app in get_addons_list(self.hass) if app["slug"].endswith(suffix))
        if not servers:
            return await self.async_step_install()
        if user_input is None or user_input.get("server") not in servers:
            return self.async_show_form(step_id="user", data_schema=vol.Schema({vol.Required("server", default=servers[0]): vol.In(servers)}))
        slug = user_input["server"]
        await self.async_set_unique_id(slug)
        self._abort_if_unique_id_configured()
        return self.async_create_entry(title="Nod", data={"prefix": slug.removesuffix(suffix)})

    async def async_step_install(self, user_input=None):
        progress = {'stage': 'initialization'}
        detail = ''
        errors = {}
        if user_input is not None:
            try:
                from .bootstrap import provision
                prefix = await provision(self.hass, progress)
            except Exception as err:
                detail = f"{progress['stage']} ({type(err).__name__})"
                logging.getLogger(__name__).warning('Nod setup failed at %s', detail)
                errors["base"] = "bootstrap_failed"
            else:
                await self.async_set_unique_id(f"{prefix}_nod_native_preflight")
                self._abort_if_unique_id_configured()
                return self.async_create_entry(title="Nod", data={"prefix": prefix})
        return self.async_show_form(step_id="install", errors=errors, description_placeholders={"detail": detail},
                                    data_schema=vol.Schema({}))

class NodOptionsFlow(config_entries.OptionsFlow):
    """Manage the adopted server and its paired workers."""

    async def async_step_init(self, user_input=None):
        return self.async_show_menu(step_id="init", menu_options=["upgrade", "install_component"])

    async def async_step_upgrade(self, user_input=None):
        prefix = self.config_entry.data["prefix"]
        store = Store(self.hass, 1, f"nod.{self.config_entry.entry_id}.upgrade")
        upgrade = NodUpgrade(get_supervisor_client(self.hass), store, prefix)
        try:
            apps = await upgrade.inspect()
            pending = await store.async_load()
            release = await fetch_release(async_get_clientsession(self.hass), upgrade.client, prefix)
        except UpgradeBlocked as err:
            return self.async_abort(reason=str(err))
        except Exception as err:
            _LOGGER.warning("Could not inspect Nod upgrade (%s)", type(err).__name__)
            return self.async_abort(reason="upgrade_inspection_failed")

        installed = upgrade.versions(apps)
        try:
            plan = release.select(installed, pending)
            upgrade.check(apps, plan, bool(pending and pending.get("backup_id")))
        except UpgradeBlocked as err:
            backup = pending.get("backup_id") if isinstance(pending, dict) else None
            return self.async_abort(reason=str(err), description_placeholders={"backup": backup or "—"})

        errors = {}
        if user_input and user_input.get("confirm"):
            if getattr(self, "_reviewed_upgrade", None) == (installed, plan):
                locks = self.hass.data.setdefault("nod_upgrade_locks", {})
                lock = locks.setdefault(prefix, asyncio.Lock())
                if lock.locked():
                    return self.async_abort(reason="upgrade_running")
                self._upgrade = NodUpgrade(
                    upgrade.client, store, prefix, backup_password=self._backup_password()
                )
                self._upgrade_error = None
                self._upgrade_task = self.hass.async_create_task(
                    self._run_upgrade(lock, installed, plan), "Nod coordinated upgrade"
                )
                return await self.async_step_upgrade_progress()
            errors["base"] = "versions_changed"

        self._reviewed_upgrade = (installed, plan)
        summary = ", ".join(f"{role} {version} → {plan.target[role]}" for role, version in installed.items())
        return self.async_show_form(
            step_id="upgrade",
            data_schema=vol.Schema({vol.Required("confirm", default=False): bool}),
            description_placeholders={"versions": summary, "upstream": plan.tag.removeprefix("nod-v")},
            errors=errors,
        )

    def _backup_password(self):
        """Use the configured password when the local backup location is protected."""
        try:
            config = async_get_backup_manager(self.hass).config.data
        except HomeAssistantError:
            return None

        local = config.agents.get("hassio.local")
        if local is not None and not local.protected:
            return None
        return config.create_backup.password

    async def _run_upgrade(self, lock, installed, plan):
        if lock.locked():
            self._upgrade_error = "upgrade_running"
            return
        async with lock:
            try:
                await self._upgrade.run(installed, plan)
            except UpgradeBlocked as err:
                self._upgrade_error = str(err)
            except Exception as err:
                self._upgrade_error = "operation_failed"
                _LOGGER.warning("Nod upgrade stopped at %s (%s)", self._upgrade.stage, type(err).__name__)

    async def async_step_upgrade_progress(self, user_input=None):
        if self._upgrade_task.done():
            if self._upgrade_task.cancelled():
                self._upgrade_error = "operation_failed"
            return self.async_show_progress_done(next_step_id="upgrade_result")
        return self.async_show_progress(
            step_id="upgrade_progress",
            progress_action="upgrading",
            progress_task=self._upgrade_task,
        )

    async def async_step_upgrade_result(self, user_input=None):
        if self._upgrade_error:
            return self.async_abort(
                reason="upgrade_failed",
                description_placeholders={
                    "stage": self._upgrade.stage,
                    "backup": self._upgrade.backup_id or "—",
                    "detail": self._upgrade_error,
                },
            )
        return self.async_abort(
            reason="upgrade_complete",
            description_placeholders={"backup": self._upgrade.backup_id},
        )

    async def async_step_install_component(self, user_input=None):
        prefix = self.config_entry.data["prefix"]
        managers = {
            role: AddonManager(self.hass, logging.getLogger(__name__), role, f"{prefix}_{ROLES[role]}")
            for role in ("Browser", "Workspace")
        }
        try:
            missing = [role for role, manager in managers.items()
                       if (await manager.async_get_addon_info()).state in (AddonState.NOT_INSTALLED, AddonState.NOT_RUNNING)]
        except AddonError:
            return self.async_show_form(step_id="install_component", errors={"base": "install_failed"},
                                        data_schema=vol.Schema({}))
        if not missing:
            return self.async_abort(reason="complete")
        errors = {}
        if user_input is not None:
            role = user_input.get("component")
            if role in missing:
                manager = managers[role]
                try:
                    info = await manager.async_get_addon_info()
                    if info.state is AddonState.NOT_INSTALLED and info.available:
                        await manager.async_install_addon()
                    elif info.state is AddonState.NOT_INSTALLED:
                        raise AddonError("Component unavailable")
                    info = await manager.async_get_addon_info()
                    if info.state is AddonState.NOT_RUNNING:
                        server = AddonManager(self.hass, logging.getLogger(__name__), "Server", f"{prefix}_{ROLES['Server']}")
                        parent = await server.async_get_addon_info()
                        key_name = role.lower()
                        key = parent.options.get(f"{key_name}_key")
                        if (not key or not parent.hostname or not info.hostname
                                or parent.options.get(f"{key_name}_host") != info.hostname):
                            raise AddonError("Server pairing is unavailable")
                        options = dict(info.options)
                        if options.get("remote_key") not in (None, "", key):
                            raise AddonError("Existing pairing differs")
                        options.update(remote_enabled=True, remote_key=key, server_host=parent.hostname)
                        if role == "Workspace":
                            options["command_enabled"] = bool(parent.options.get("workspace_runtime_enabled"))
                        elif not parent.options.get("browser_enabled"):
                            raise AddonError("Server browser disabled")
                        await manager.async_set_addon_options(options)
                        await manager.async_start_addon()
                    if (await manager.async_get_addon_info()).state is not AddonState.RUNNING:
                        raise AddonError("Component did not start")
                    return self.async_create_entry(title="", data={})
                except AddonError:
                    errors["base"] = "install_failed"
        return self.async_show_form(step_id="install_component", errors=errors, data_schema=vol.Schema({
            vol.Required("component", default=missing[0]): vol.In(missing),
        }))
