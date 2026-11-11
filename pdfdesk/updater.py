"""Verifica degli aggiornamenti di PDFDesk (autore: Guido Cauli).

Interroga l'API pubblica di GitHub (ultima release) e confronta il numero di versione.
Non viene inviato alcun dato personale; la verifica parte solo quando l'utente la richiede.
"""
from __future__ import annotations

import json
import re
import urllib.request

from . import __version__

REPO = "guidocauli/pdfdesk"
API_URL = f"https://api.github.com/repos/{REPO}/releases/latest"
RELEASES_URL = f"https://github.com/{REPO}/releases/latest"


def parse_version(s: str) -> tuple[int, ...]:
    """'v0.7.3' -> (0, 7, 3); le parti non numeriche finali sono ignorate."""
    m = re.match(r"\s*v?(\d+(?:\.\d+)*)", s or "")
    return tuple(int(x) for x in m.group(1).split(".")) if m else ()


def is_newer(latest: str, current: str = __version__) -> bool:
    a, b = parse_version(latest), parse_version(current)
    n = max(len(a), len(b))
    return bool(a) and a + (0,) * (n - len(a)) > b + (0,) * (n - len(b))


def fetch_latest(timeout: float = 8.0, url: str = API_URL) -> dict:
    """Restituisce {'version', 'url', 'notes'} dell'ultima release; solleva eccezioni di rete."""
    req = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json",
                                               "User-Agent": "PDFDesk-update-check"})
    with urllib.request.urlopen(req, timeout=timeout) as r:  # noqa: S310 (URL https fisso)
        data = json.loads(r.read().decode("utf-8"))
    tag = str(data.get("tag_name") or data.get("name") or "")
    return {"version": tag.lstrip("vV"), "url": data.get("html_url") or RELEASES_URL,
            "notes": str(data.get("body") or "")[:1500]}
