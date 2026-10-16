"""Sensori ClasseViva."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import ClasseVivaConfigEntry
from .coordinator import ClasseVivaCoordinator
from .entity import ClasseVivaEntity


@dataclass(frozen=True, kw_only=True)
class CVSensorDescription(SensorEntityDescription):
    value_fn: Callable[[dict], Any]
    attrs_fn: Callable[[dict], dict] | None = None


def _day_count(d: dict, i: int):
    days = d["homework_days"]
    return len(days[i]["compiti"]) if i < len(days) else None


def _day_attrs(d: dict, i: int) -> dict:
    days = d["homework_days"]
    return days[i] if i < len(days) else {}


SENSORS: tuple[CVSensorDescription, ...] = (
    CVSensorDescription(
        key="average",
        translation_key="average",
        icon="mdi:school",
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=2,
        value_fn=lambda d: d["average"],
        attrs_fn=lambda d: {
            "medie_materie": {v["name"]: v["average"] for v in d["subjects"].values()},
            "ultimi_voti": d["recent_grades"],
        },
    ),
    CVSensorDescription(
        key="last_grade",
        translation_key="last_grade",
        icon="mdi:numeric",
        value_fn=lambda d: (d["last_grade"] or {}).get("voto"),
        attrs_fn=lambda d: d["last_grade"] or {},
    ),
    CVSensorDescription(
        key="homework",
        translation_key="homework",
        icon="mdi:book-edit",
        native_unit_of_measurement="compiti",
        value_fn=lambda d: len(d["homework"]),
        attrs_fn=lambda d: {"compiti": d["homework"]},
    ),
    CVSensorDescription(
        key="homework_tomorrow",  # = 1° giorno utile (chiave mantenuta per compatibilità)
        translation_key="homework_tomorrow",
        icon="mdi:book-clock",
        native_unit_of_measurement="compiti",
        value_fn=lambda d: _day_count(d, 0),
        attrs_fn=lambda d: _day_attrs(d, 0),
    ),
    CVSensorDescription(
        key="homework_day_2",
        translation_key="homework_day_2",
        icon="mdi:book-clock-outline",
        native_unit_of_measurement="compiti",
        value_fn=lambda d: _day_count(d, 1),
        attrs_fn=lambda d: _day_attrs(d, 1),
    ),
    CVSensorDescription(
        key="homework_day_3",
        translation_key="homework_day_3",
        icon="mdi:book-clock-outline",
        native_unit_of_measurement="compiti",
        value_fn=lambda d: _day_count(d, 2),
        attrs_fn=lambda d: _day_attrs(d, 2),
    ),
    CVSensorDescription(
        key="homework_recent",
        translation_key="homework_recent",
        icon="mdi:book-edit-outline",
        native_unit_of_measurement="annotazioni",
        value_fn=lambda d: len(d["homework_recent"]),
        attrs_fn=lambda d: {"compiti": d["homework_recent"]},
    ),
    CVSensorDescription(
        key="tests",
        translation_key="tests",
        icon="mdi:clipboard-text-clock",
        native_unit_of_measurement="verifiche",
        value_fn=lambda d: len(d["tests"]),
        attrs_fn=lambda d: {"verifiche": d["tests"]},
    ),
    CVSensorDescription(
        key="absences",
        translation_key="absences",
        icon="mdi:calendar-remove",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement="assenze",
        value_fn=lambda d: d["absences"]["absences"],
        attrs_fn=lambda d: {
            "da_giustificare": d["absences"]["absences_open"],
            "elenco_da_giustificare": d["absences"]["open_list"],
        },
    ),
    CVSensorDescription(
        key="delays",
        translation_key="delays",
        icon="mdi:clock-alert",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement="ritardi",
        value_fn=lambda d: d["absences"]["delays"],
        attrs_fn=lambda d: {"da_giustificare": d["absences"]["delays_open"]},
    ),
    CVSensorDescription(
        key="exits",
        translation_key="exits",
        icon="mdi:exit-run",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement="uscite",
        value_fn=lambda d: d["absences"]["exits"],
        attrs_fn=lambda d: {"da_giustificare": d["absences"]["exits_open"]},
    ),
    CVSensorDescription(
        key="unjustified",
        translation_key="unjustified",
        icon="mdi:alert-circle",
        native_unit_of_measurement="eventi",
        value_fn=lambda d: d["absences"]["absences_open"]
        + d["absences"]["delays_open"]
        + d["absences"]["exits_open"],
        attrs_fn=lambda d: {"elenco": d["absences"]["open_list"]},
    ),
    CVSensorDescription(
        key="notices",
        translation_key="notices",
        icon="mdi:bulletin-board",
        native_unit_of_measurement="comunicazioni",
        value_fn=lambda d: len(d["notices_unread"]),
        attrs_fn=lambda d: {"comunicazioni": d["notices_unread"]},
    ),
    CVSensorDescription(
        key="notes",
        translation_key="notes",
        icon="mdi:note-alert",
        native_unit_of_measurement="note",
        value_fn=lambda d: d["notes_count"],
        attrs_fn=lambda d: {"note": d["notes"]},
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ClasseVivaConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    async_add_entities(ClasseVivaSensor(coordinator, desc) for desc in SENSORS)

    known: set[int] = set()

    @callback
    def _add_subject_sensors() -> None:
        new = [
            SubjectAverageSensor(coordinator, sid)
            for sid in coordinator.data["subjects"]
            if sid not in known
        ]
        known.update(s.subject_id for s in new)
        if new:
            async_add_entities(new)

    _add_subject_sensors()
    entry.async_on_unload(coordinator.async_add_listener(_add_subject_sensors))


class ClasseVivaSensor(ClasseVivaEntity, SensorEntity):
    entity_description: CVSensorDescription

    def __init__(
        self, coordinator: ClasseVivaCoordinator, description: CVSensorDescription
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{self._ident}_{description.key}"

    @property
    def native_value(self):
        return self.entity_description.value_fn(self.coordinator.data)

    @property
    def extra_state_attributes(self):
        fn = self.entity_description.attrs_fn
        return fn(self.coordinator.data) if fn else None


class SubjectAverageSensor(ClasseVivaEntity, SensorEntity):
    """Media per singola materia."""

    _attr_icon = "mdi:book-open-variant"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 2

    def __init__(self, coordinator: ClasseVivaCoordinator, subject_id: int) -> None:
        super().__init__(coordinator)
        self.subject_id = subject_id
        self._attr_unique_id = f"{self._ident}_avg_{subject_id}"
        self._attr_name = f"Media {coordinator.data['subjects'][subject_id]['name']}"

    @property
    def native_value(self):
        return self.coordinator.data["subjects"].get(self.subject_id, {}).get("average")

    @property
    def extra_state_attributes(self):
        s = self.coordinator.data["subjects"].get(self.subject_id, {})
        return {"numero_voti": s.get("count")}
