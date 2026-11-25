"""Adopt an installed native Nod server."""
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.components.hassio.coordinator import get_addons_list

class NodFlow(config_entries.ConfigFlow, domain="nod"):
    VERSION = 1

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
