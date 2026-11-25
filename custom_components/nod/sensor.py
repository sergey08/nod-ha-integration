"""Installed component versions from Supervisor's local inventory."""
from homeassistant.components.hassio.coordinator import get_addons_list
from homeassistant.components.sensor import SensorEntity
from homeassistant.helpers.device_registry import DeviceInfo
from .inventory import ROLES, inventory

async def async_setup_entry(hass, entry, async_add_entities):
    async_add_entities([NodVersion(entry.data["prefix"], role) for role in ROLES], True)

class NodVersion(SensorEntity):
    _attr_has_entity_name = True

    def __init__(self, prefix, role):
        self.prefix = prefix
        self.role = role
        self._attr_name = role
        self._attr_unique_id = f"{prefix}_{ROLES[role]}_version"
        self._attr_device_info = DeviceInfo(identifiers={("nod", prefix)}, name="Nod", configuration_url=f"homeassistant://{prefix}_nod_native_preflight")

    async def async_update(self):
        app = inventory(get_addons_list(self.hass), self.prefix)[self.role]
        self._attr_available = app is not None
        self._attr_native_value = app.get("version") if app else None
