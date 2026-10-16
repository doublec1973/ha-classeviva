"""Calendario agenda ClasseViva."""
from __future__ import annotations

from datetime import datetime

from homeassistant.util import dt as dt_util

from homeassistant.components.calendar import CalendarEntity, CalendarEvent
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import ClasseVivaConfigEntry
from .api import ClasseVivaError
from .coordinator import ClasseVivaCoordinator, to_calendar_event
from .entity import ClasseVivaEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ClasseVivaConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    async_add_entities([ClasseVivaCalendar(entry.runtime_data)])


class ClasseVivaCalendar(ClasseVivaEntity, CalendarEntity):
    _attr_translation_key = "agenda"
    _attr_icon = "mdi:calendar-school"

    def __init__(self, coordinator: ClasseVivaCoordinator) -> None:
        super().__init__(coordinator)
        self._attr_unique_id = f"{self._ident}_agenda"

    @property
    def event(self) -> CalendarEvent | None:
        """Evento in corso o prossimo (salta quelli già terminati)."""
        now = dt_util.now()
        for item in self.coordinator.data["agenda"]:
            ev = to_calendar_event(item)
            if ev is None:
                continue
            if isinstance(ev.end, datetime):
                if ev.end > now:
                    return ev
            elif ev.end > now.date():
                return ev
        return None

    async def async_get_events(
        self, hass: HomeAssistant, start_date: datetime, end_date: datetime
    ) -> list[CalendarEvent]:
        try:
            raw = await self.coordinator.client.agenda(
                start_date.date(), end_date.date()
            )
        except ClasseVivaError:
            return []
        events = (to_calendar_event(i) for i in raw)
        return [e for e in events if e is not None]
