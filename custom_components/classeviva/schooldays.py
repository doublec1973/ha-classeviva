"""Calcolo dei giorni scolastici utili (senza dipendenze da Home Assistant)."""
from __future__ import annotations

from collections.abc import Container
from datetime import date, timedelta

WEEKDAYS_IT = [
    "lunedì", "martedì", "mercoledì", "giovedì", "venerdì", "sabato", "domenica",
]
SCHOOL_DAY_STATUS = "SD"


def parse_school_calendar(raw: list[dict]) -> tuple[dict[date, str], bool]:
    """Converte il calendario scolastico Spaggiari in {data: stato}.

    Il calendario è considerato affidabile solo se contiene almeno un giorno
    con stato "SD" (giorno di scuola); altrimenti si usa la regola di ripiego.
    """
    cal: dict[date, str] = {}
    for item in raw or []:
        try:
            d = date.fromisoformat(str(item.get("dayDate", ""))[:10])
        except ValueError:
            continue
        status = item.get("dayStatus")
        if status:
            cal[d] = status
    return cal, SCHOOL_DAY_STATUS in cal.values()


def _parse_one_date(token: str) -> date:
    token = token.strip()
    if "/" in token:  # GG/MM/AAAA
        dd, mm, yy = token.split("/")
        return date(int(yy), int(mm), int(dd))
    return date.fromisoformat(token)  # AAAA-MM-GG


def parse_closures(text: str | None) -> tuple[set[date], list[str]]:
    """Legge date o intervalli ("2026-12-07, 2026-12-23..2027-01-06").

    Separatori: virgola, punto e virgola o a capo. Intervalli con "..".
    Formati data: AAAA-MM-GG oppure GG/MM/AAAA.
    Restituisce (giorni, token non validi).
    """
    days: set[date] = set()
    invalid: list[str] = []
    if not text:
        return days, invalid
    for token in text.replace(";", ",").replace("\n", ",").split(","):
        token = token.strip()
        if not token:
            continue
        try:
            if ".." in token:
                a, b = token.split("..", 1)
                start, end = _parse_one_date(a), _parse_one_date(b)
                if end < start or (end - start).days > 400:
                    raise ValueError("intervallo non valido")
                d = start
                while d <= end:
                    days.add(d)
                    d += timedelta(days=1)
            else:
                days.add(_parse_one_date(token))
        except (ValueError, TypeError):
            invalid.append(token)
    return days, invalid


def is_school_day(
    d: date,
    cal: dict[date, str],
    reliable: bool,
    saturday: bool,
    holidays: Container | None,
    closures: Container | None = None,
) -> bool:
    if closures is not None and d in closures:
        return False
    status = cal.get(d)
    if reliable and status is not None:
        return status == SCHOOL_DAY_STATUS
    if d.weekday() == 6 or (d.weekday() == 5 and not saturday):
        return False
    if holidays is not None and d in holidays:
        return False
    return True


def next_school_days(
    start: date,
    n: int,
    cal: dict[date, str],
    reliable: bool,
    saturday: bool,
    holidays: Container | None,
    closures: Container | None = None,
    max_lookahead: int = 400,
) -> list[date]:
    """Primi n giorni scolastici a partire da `start` (incluso)."""
    out: list[date] = []
    d = start
    for _ in range(max_lookahead):
        if len(out) >= n:
            break
        if is_school_day(d, cal, reliable, saturday, holidays, closures):
            out.append(d)
        d += timedelta(days=1)
    return out
