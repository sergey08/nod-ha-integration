"""Adopt an installed native Nod server."""
import logging
from homeassistant.core import callback
from homeassistant.components.hassio.addon_manager import AddonError, AddonManager, AddonState
from .inventory import ROLES
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.components.hassio.coordinator import get_addons_list

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
    """Offer installation only for missing workers of the adopted server."""

    async def async_step_init(self, user_input=None):
        prefix = self.config_entry.data["prefix"]
        managers = {
            role: AddonManager(self.hass, logging.getLogger(__name__), role, f"{prefix}_{ROLES[role]}")
            for role in ("Browser", "Workspace")
        }
        try:
            missing = [role for role, manager in managers.items()
                       if (await manager.async_get_addon_info()).state in (AddonState.NOT_INSTALLED, AddonState.NOT_RUNNING)]
        except AddonError:
            return self.async_show_form(step_id="init", errors={"base": "install_failed"},
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
        return self.async_show_form(step_id="init", errors=errors, data_schema=vol.Schema({
            vol.Required("component", default=missing[0]): vol.In(missing),
        }))
