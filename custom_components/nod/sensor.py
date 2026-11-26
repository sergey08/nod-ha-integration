"""Installed component versions from Supervisor's local inventory."""
import logging
from datetime import timedelta

from homeassistant.components.hassio.handler import get_supervisor_client
from homeassistant.helpers.update_coordinator import CoordinatorEntity, DataUpdateCoordinator
from homeassistant.components.sensor import SensorEntity
from homeassistant.helpers.device_registry import DeviceInfo
from .inventory import ROLES

async def async_setup_entry(hass, entry, async_add_entities):
    client = get_supervisor_client(hass)

    async def versions():
        apps = await client.addons.list()
        return {app.slug: app.version for app in apps}

    coordinator = DataUpdateCoordinator(
        hass, logging.getLogger(__name__), name="Nod versions", config_entry=entry,
        update_method=versions, update_interval=timedelta(minutes=1),
    )
    await coordinator.async_config_entry_first_refresh()
    async_add_entities(NodVersion(coordinator, entry.data["prefix"], role) for role in ROLES)

class NodVersion(CoordinatorEntity, SensorEntity):
    _attr_has_entity_name = True

    def __init__(self, coordinator, prefix, role):
        super().__init__(coordinator)
        self.slug = f"{prefix}_{ROLES[role]}"
        self.prefix = prefix
        self.role = role
        self._attr_name = role
        self._attr_unique_id = f"{prefix}_{ROLES[role]}_version"
        self._attr_device_info = DeviceInfo(identifiers={("nod", prefix)}, name="Nod", configuration_url=f"homeassistant://{prefix}_nod_native_preflight")

    @property
    def available(self):
        return super().available and self.slug in self.coordinator.data

    @property
    def native_value(self):
        return self.coordinator.data.get(self.slug)
