"""Entità base."""
from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import ClasseVivaCoordinator


class ClasseVivaEntity(CoordinatorEntity[ClasseVivaCoordinator]):
    _attr_has_entity_name = True

    def __init__(self, coordinator: ClasseVivaCoordinator) -> None:
        super().__init__(coordinator)
        ident = coordinator.client.ident
        self._ident = ident
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, ident)},
            name=f"ClasseViva {coordinator.client.full_name}",
            manufacturer="Spaggiari",
            model="ClasseViva",
            entry_type=DeviceEntryType.SERVICE,
        )
