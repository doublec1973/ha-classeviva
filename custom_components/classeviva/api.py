"""Client asincrono per le API REST di ClasseViva (Spaggiari)."""
from __future__ import annotations

import re
from datetime import date
from typing import Any

import aiohttp

from .const import API_BASE, API_HEADERS

TIMEOUT = aiohttp.ClientTimeout(total=30)


class ClasseVivaError(Exception):
    """Errore generico."""


class ClasseVivaAuthError(ClasseVivaError):
    """Credenziali non valide."""


class ClasseVivaConnectionError(ClasseVivaError):
    """Problema di connessione."""


class ClasseVivaBlockedError(ClasseVivaConnectionError):
    """Richiesta bloccata dal WAF di Spaggiari (HTTP 403 con pagina HTML)."""


class ClasseVivaClient:
    """Client API."""

    def __init__(
        self, session: aiohttp.ClientSession, username: str, password: str
    ) -> None:
        self._session = session
        self._username = username
        self._password = password
        self.token: str | None = None
        self.ident: str | None = None
        self.student_id: str | None = None
        self.full_name: str | None = None

    async def login(self) -> None:
        payload = {"ident": None, "pass": self._password, "uid": self._username}
        try:
            async with self._session.post(
                f"{API_BASE}/auth/login",
                json=payload,
                headers=API_HEADERS,
                timeout=TIMEOUT,
            ) as resp:
                if resp.status == 403:
                    raise ClasseVivaBlockedError(
                        "Accesso bloccato da ClasseViva (HTTP 403, Access Denied)"
                    )
                if resp.status in (401, 422):
                    raise ClasseVivaAuthError("Credenziali non valide")
                if resp.status >= 400:
                    raise ClasseVivaError(f"Login HTTP {resp.status}")
                data = await resp.json(content_type=None)
        except (aiohttp.ClientError, TimeoutError) as err:
            raise ClasseVivaConnectionError(str(err)) from err

        self.token = data["token"]
        self.ident = data["ident"]
        # "S1234567X" / "G1234567X" -> "1234567"
        self.student_id = re.sub(r"\D", "", self.ident)
        first = (data.get("firstName") or "").title()
        last = (data.get("lastName") or "").title()
        self.full_name = f"{first} {last}".strip() or self.ident

    async def _get(self, path: str, _retry: bool = True) -> dict[str, Any]:
        if not self.token:
            await self.login()
        headers = {**API_HEADERS, "Z-Auth-Token": self.token}
        try:
            async with self._session.get(
                f"{API_BASE}{path}", headers=headers, timeout=TIMEOUT
            ) as resp:
                if resp.status == 401 and _retry:
                    self.token = None
                    await self.login()
                    return await self._get(path, _retry=False)
                if resp.status == 403:
                    raise ClasseVivaBlockedError(f"Accesso bloccato (403): {path}")
                if resp.status == 401:
                    raise ClasseVivaAuthError(f"Non autorizzato: {path}")
                if resp.status >= 400:
                    raise ClasseVivaError(f"HTTP {resp.status} su {path}")
                return await resp.json(content_type=None)
        except (aiohttp.ClientError, TimeoutError) as err:
            raise ClasseVivaConnectionError(str(err)) from err

    async def grades(self) -> list[dict]:
        data = await self._get(f"/students/{self.student_id}/grades")
        return data.get("grades", [])

    async def agenda(self, begin: date, end: date) -> list[dict]:
        data = await self._get(
            f"/students/{self.student_id}/agenda/all/"
            f"{begin:%Y%m%d}/{end:%Y%m%d}"
        )
        return data.get("agenda", [])

    async def absences(self) -> list[dict]:
        data = await self._get(f"/students/{self.student_id}/absences/details")
        return data.get("events", [])

    async def noticeboard(self) -> list[dict]:
        data = await self._get(f"/students/{self.student_id}/noticeboard")
        return data.get("items", [])

    async def notes(self) -> dict[str, list]:
        return await self._get(f"/students/{self.student_id}/notes/all")

    async def school_calendar(self, begin: date, end: date) -> list[dict]:
        data = await self._get(
            f"/students/{self.student_id}/calendar/all/{begin:%Y%m%d}/{end:%Y%m%d}"
        )
        return data.get("calendar", [])
