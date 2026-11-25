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
            return self.async_abort(reason="no_server")
        if user_input is None or user_input.get("server") not in servers:
            return self.async_show_form(step_id="user", data_schema=vol.Schema({vol.Required("server", default=servers[0]): vol.In(servers)}))
        slug = user_input["server"]
        await self.async_set_unique_id(slug)
        self._abort_if_unique_id_configured()
        return self.async_create_entry(title="Nod", data={"prefix": slug.removesuffix(suffix)})

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
                       if (await manager.async_get_addon_info()).state is AddonState.NOT_INSTALLED]
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
                    return self.async_create_entry(title="", data={})
                except AddonError:
                    errors["base"] = "install_failed"
        return self.async_show_form(step_id="init", errors=errors, data_schema=vol.Schema({
            vol.Required("component", default=missing[0]): vol.In(missing),
        }))
