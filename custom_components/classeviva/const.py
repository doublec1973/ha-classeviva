"""Costanti per l'integrazione ClasseViva."""
from __future__ import annotations

DOMAIN = "classeviva"

API_BASE = "https://web.spaggiari.eu/rest/v1"
API_HEADERS = {
    "User-Agent": "CVVS/std/4.2.3 Android/12",
    "Z-Dev-Apikey": "Tg1NWEwNGIgIC0K",
    "Content-Type": "application/json",
}

CONF_SCAN_INTERVAL = "scan_interval"
DEFAULT_SCAN_INTERVAL = 30  # minuti
MIN_SCAN_INTERVAL = 10
AGENDA_DAYS_AHEAD = 30

# Codici eventi assenze
ABSENCE_CODE = "ABA0"
DELAY_CODES = ("ABR0", "ABR1")
EXIT_CODE = "ABU0"

CONF_SATURDAY = "saturday"
CONF_KEYWORDS = "keywords"
DEFAULT_KEYWORDS = "compiti,studiare,esercizio,esercizi,ripassare,da svolgere,da fare,consegna"
AGENDA_DAYS_BACK = 3
CALENDAR_DAYS_AHEAD = 60
CONF_CLOSURES = "closures"
