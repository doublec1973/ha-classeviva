"""Coordinator: scarica e rielabora i dati di ClasseViva."""
from __future__ import annotations

import asyncio
import logging
import re
from collections import defaultdict
from datetime import date, datetime, timedelta
from typing import Any

from homeassistant.components.calendar import CalendarEvent
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .api import (
    ClasseVivaAuthError,
    ClasseVivaClient,
    ClasseVivaConnectionError,
    ClasseVivaError,
)
from .const import (
    ABSENCE_CODE,
    AGENDA_DAYS_AHEAD,
    AGENDA_DAYS_BACK,
    CALENDAR_DAYS_AHEAD,
    CONF_CLOSURES,
    CONF_KEYWORDS,
    CONF_SATURDAY,
    CONF_SCAN_INTERVAL,
    DEFAULT_KEYWORDS,
    DEFAULT_SCAN_INTERVAL,
    DELAY_CODES,
    DOMAIN,
    EXIT_CODE,
)
from .schooldays import (
    WEEKDAYS_IT,
    next_school_days,
    parse_closures,
    parse_school_calendar,
)

try:  # festività nazionali (libreria inclusa in Home Assistant)
    import holidays as _holidays_lib
except ImportError:  # pragma: no cover
    _holidays_lib = None

_LOGGER = logging.getLogger(__name__)

TEST_REGEX = re.compile(
    r"verifica|compito in classe|interrogazion|test\b|prova scritta|esame",
    re.IGNORECASE,
)


def to_calendar_event(item: dict) -> CalendarEvent | None:
    """Converte un evento agenda ClasseViva in CalendarEvent."""
    begin = dt_util.parse_datetime(item.get("evtDatetimeBegin") or "")
    end = dt_util.parse_datetime(item.get("evtDatetimeEnd") or "")
    if begin is None:
        return None

    subject = (item.get("subjectDesc") or "").title()
    notes = (item.get("notes") or "").strip()
    author = (item.get("authorName") or "").strip().title()
    description = notes + (f"\n\nDocente: {author}" if author else "")
    kind = "Compiti" if item.get("evtCode") == "AGHW" else "Agenda"
    summary = f"{kind} - {subject}" if subject else f"{kind}: {notes[:50]}"

    if item.get("isFullDay") or end is None or end <= begin:
        if item.get("isFullDay"):
            start_d = begin.date()
            return CalendarEvent(
                start=start_d,
                end=start_d + timedelta(days=1),
                summary=summary,
                description=description,
                uid=str(item.get("evtId")),
            )
        end = begin + timedelta(hours=1)

    return CalendarEvent(
        start=begin,
        end=end,
        summary=summary,
        description=description,
        uid=str(item.get("evtId")),
    )


class ClasseVivaCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Gestisce l'aggiornamento periodico."""

    def __init__(
        self, hass: HomeAssistant, entry: ConfigEntry, client: ClasseVivaClient
    ) -> None:
        minutes = entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=DOMAIN,
            update_interval=timedelta(minutes=minutes),
        )
        self.client = client
        self._saturday = bool(entry.options.get(CONF_SATURDAY, False))
        kw = entry.options.get(CONF_KEYWORDS, DEFAULT_KEYWORDS) or ""
        self._keywords = [k.strip().lower() for k in kw.split(",") if k.strip()]
        self._closures, _ = parse_closures(entry.options.get(CONF_CLOSURES))
        self._holidays = None
        if _holidays_lib is not None:
            try:
                y = dt_util.now().year
                self._holidays = _holidays_lib.country_holidays(
                    "IT", years=range(y, y + 2)
                )
            except Exception:  # noqa: BLE001
                self._holidays = None

    async def _safe(self, coro, default):
        """Un endpoint non disponibile (es. bacheca disattivata) non blocca tutto."""
        try:
            return await coro
        except ClasseVivaAuthError:
            raise
        except ClasseVivaError as err:
            _LOGGER.debug("Endpoint non disponibile: %s", err)
            return default

    async def _async_update_data(self) -> dict[str, Any]:
        today = dt_util.now().date()
        try:
            if not self.client.token:
                await self.client.login()
            grades, agenda, absences, notices, notes, school_cal = await asyncio.gather(
                self._safe(self.client.grades(), []),
                self._safe(
                    self.client.agenda(
                        today - timedelta(days=AGENDA_DAYS_BACK),
                        today + timedelta(days=AGENDA_DAYS_AHEAD),
                    ),
                    [],
                ),
                self._safe(self.client.absences(), []),
                self._safe(self.client.noticeboard(), []),
                self._safe(self.client.notes(), {}),
                self._safe(
                    self.client.school_calendar(
                        today, today + timedelta(days=CALENDAR_DAYS_AHEAD)
                    ),
                    [],
                ),
            )
        except ClasseVivaAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except ClasseVivaConnectionError as err:
            raise UpdateFailed(f"Errore di connessione: {err}") from err
        except ClasseVivaError as err:
            raise UpdateFailed(str(err)) from err

        return self._process(
            today, grades, agenda, absences, notices, notes, school_cal
        )

    # ------------------------------------------------------------------
    def _process(
        self, today: date, grades, agenda, absences, notices, notes, school_cal=None
    ):
        # --- Voti -------------------------------------------------------
        valid = [
            g
            for g in grades
            if not g.get("canceled")
            and not g.get("noAverage")
            and g.get("decimalValue") is not None
        ]
        by_subject: dict[int, dict] = defaultdict(
            lambda: {"name": "", "values": [], "grades": []}
        )
        for g in valid:
            s = by_subject[g["subjectId"]]
            s["name"] = (g.get("subjectDesc") or "").title()
            s["values"].append(float(g["decimalValue"]))
            s["grades"].append(g)

        subjects = {
            sid: {
                "name": s["name"],
                "average": round(sum(s["values"]) / len(s["values"]), 2),
                "count": len(s["values"]),
            }
            for sid, s in by_subject.items()
        }
        overall = (
            round(sum(v["average"] for v in subjects.values()) / len(subjects), 2)
            if subjects
            else None
        )

        def fmt_grade(g: dict) -> dict:
            return {
                "materia": (g.get("subjectDesc") or "").title(),
                "voto": g.get("displayValue"),
                "valore": g.get("decimalValue"),
                "data": g.get("evtDate"),
                "tipo": g.get("componentDesc"),
                "periodo": g.get("periodDesc"),
                "note": g.get("notesForFamily"),
            }

        all_sorted = sorted(
            (g for g in grades if not g.get("canceled")),
            key=lambda g: (g.get("evtDate", ""), g.get("evtId", 0)),
            reverse=True,
        )

        # --- Agenda: compiti e verifiche -------------------------------
        def ev_date(e: dict) -> date | None:
            d = dt_util.parse_datetime(e.get("evtDatetimeBegin") or "")
            return d.date() if d else None

        def fmt_event(e: dict) -> dict:
            d = ev_date(e)
            return {
                "materia": (e.get("subjectDesc") or "").title(),
                "data": d.isoformat() if d else None,
                "descrizione": (e.get("notes") or "").strip(),
                "docente": e.get("authorName"),
            }

        all_events = sorted(agenda, key=lambda e: e.get("evtDatetimeBegin", ""))
        upcoming = [e for e in all_events if (ev_date(e) or today) >= today]

        def is_hw_text(e: dict) -> bool:
            notes_l = (e.get("notes") or "").lower()
            return bool(self._keywords) and any(k in notes_l for k in self._keywords)

        # Compiti "veri" (AGHW): la data è il giorno di consegna.
        # Annotazioni con parole chiave: se datate nel futuro valgono come
        # compiti per quel giorno; se di oggi o recenti vanno in "assegnati di recente".
        def is_due(e: dict) -> bool:
            d = ev_date(e) or today
            if e.get("evtCode") == "AGHW":
                return d >= today
            return d > today and is_hw_text(e)

        homework = [e for e in all_events if is_due(e)]
        recent_hw = [
            e
            for e in all_events
            if e.get("evtCode") != "AGHW"
            and is_hw_text(e)
            and today - timedelta(days=AGENDA_DAYS_BACK)
            <= (ev_date(e) or today)
            <= today
        ]
        tests = [
            e
            for e in upcoming
            if e.get("evtCode") != "AGHW"
            and TEST_REGEX.search(e.get("notes") or "")
        ]

        # Primi 3 giorni scolastici utili da domani in poi
        cal, reliable = parse_school_calendar(school_cal or [])
        days = next_school_days(
            today + timedelta(days=1),
            3,
            cal,
            reliable,
            self._saturday,
            self._holidays,
            self._closures,
        )
        homework_days = []
        for d in days:
            items = [fmt_event(e) for e in homework if ev_date(e) == d]
            homework_days.append(
                {
                    "data": d.isoformat(),
                    "giorno": WEEKDAYS_IT[d.weekday()],
                    "compiti": items,
                    "testo": "\n".join(
                        f"{i['materia'] or 'Agenda'}: {i['descrizione']}"
                        for i in items
                    ),
                }
            )

        # --- Assenze ---------------------------------------------------
        def is_open(e: dict) -> bool:
            return not e.get("isJustified")

        abs_list = [e for e in absences if e.get("evtCode") == ABSENCE_CODE]
        delays = [e for e in absences if e.get("evtCode") in DELAY_CODES]
        exits = [e for e in absences if e.get("evtCode") == EXIT_CODE]

        def fmt_abs(e: dict) -> dict:
            return {
                "data": e.get("evtDate"),
                "ora": e.get("evtHPos"),
                "giustificata": bool(e.get("isJustified")),
                "motivo": e.get("justifReasonDesc"),
            }

        # --- Bacheca ---------------------------------------------------
        unread = [n for n in notices if not n.get("readStatus")]

        # --- Note disciplinari ----------------------------------------
        all_notes = [
            n for key in ("NTTE", "NTCL", "NTWN", "NTST") for n in notes.get(key, [])
        ]

        return {
            "average": overall,
            "subjects": subjects,
            "last_grade": fmt_grade(all_sorted[0]) if all_sorted else None,
            "recent_grades": [fmt_grade(g) for g in all_sorted[:15]],
            "homework": [fmt_event(e) for e in homework[:20]],
            "homework_days": homework_days,
            "homework_recent": [fmt_event(e) for e in recent_hw[-10:]],
            "tests": [fmt_event(e) for e in tests[:20]],
            "agenda": upcoming,
            "absences": {
                "absences": len(abs_list),
                "absences_open": len([e for e in abs_list if is_open(e)]),
                "delays": len(delays),
                "delays_open": len([e for e in delays if is_open(e)]),
                "exits": len(exits),
                "exits_open": len([e for e in exits if is_open(e)]),
                "open_list": [
                    fmt_abs(e)
                    for e in absences
                    if is_open(e) and e.get("evtCode") in (ABSENCE_CODE, EXIT_CODE, *DELAY_CODES)
                ][:20],
            },
            "notices_unread": [
                {
                    "titolo": n.get("cntTitle"),
                    "categoria": n.get("cntCategory"),
                    "data": n.get("pubDT"),
                    "allegato": n.get("cntHasAttach"),
                }
                for n in unread[:20]
            ],
            "notes_count": len(all_notes),
            "notes": [
                {
                    "data": n.get("evtDate"),
                    "autore": n.get("authorName"),
                    "testo": (n.get("evtText") or "")[:300],
                }
                for n in all_notes[-10:]
            ],
            "updated": datetime.now().isoformat(timespec="seconds"),
        }
