from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
import gzip
from html import unescape
import re
import ssl
from typing import Any
from urllib.error import URLError
from urllib.request import Request, urlopen

from models import Item


class SourceError(RuntimeError):
    pass


@dataclass(slots=True)
class SourceResult:
    items: list[Item]
    errors: list[str]


class SourceAdapter:
    source_type = "unknown"

    def __init__(self, config: dict[str, Any], source_config: dict[str, Any]) -> None:
        self.config = config
        self.source_config = source_config
        self.tier = source_config.get("tier", "C")

    def fetch(self) -> SourceResult:
        raise NotImplementedError


def fetch_url(url: str, *, headers: dict[str, str] | None = None, timeout: int = 30) -> bytes:
    request = Request(url, headers=headers or {"User-Agent": "HSTIntelligence/0.1"})
    try:
        with urlopen(request, timeout=timeout, context=certificate_context()) as response:
            return decompress_if_gzip(response.read())
    except URLError as exc:
        raise SourceError(str(exc)) from exc


def decompress_if_gzip(payload: bytes) -> bytes:
    """Some feeds (mattr.com/feed/ among them) return gzip-encoded bytes even when no
    Accept-Encoding request header was sent, which urllib does not unwrap. Sniff the gzip
    magic bytes rather than trusting Content-Encoding, and fall through untouched on anything
    that fails to inflate."""
    if not payload.startswith(b"\x1f\x8b"):
        return payload
    try:
        return gzip.decompress(payload)
    except OSError:
        return payload


def certificate_context() -> ssl.SSLContext | None:
    try:
        import certifi
    except ImportError:
        return None
    return ssl.create_default_context(cafile=certifi.where())


def clean_text(value: str | None) -> str:
    if not value:
        return ""
    without_tags = re.sub(r"<[^>]+>", " ", value)
    return re.sub(r"\s+", " ", unescape(without_tags)).strip()


def normalize_date(value: str | None) -> str | None:
    if not value:
        return None
    value = value.strip()
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00")).date()
        return parsed.isoformat() if parsed <= datetime.now(timezone.utc).date() else None
    except ValueError:
        pass
    try:
        parsed = parsedate_to_datetime(value).date()
        return parsed.isoformat() if parsed <= datetime.now(timezone.utc).date() else None
    except (TypeError, ValueError, IndexError):
        return None


def first_real_date(*values: str | None) -> str | None:
    for value in values:
        parsed = normalize_date(value)
        if parsed:
            return parsed
    return None


def vocabulary_match(item: Item, config: dict[str, Any]) -> bool:
    """Two-axis heat shrink tubing gate:

        hst_core_terms  OR  (adjacent_terms AND context_terms)

    A single-axis gate on "heat shrink" would be far narrower than SoftRobotics' "robot"
    anchor — most weeks would surface two or three items, and relevant work (FEP extrusion,
    e-beam crosslinking, PFAS restrictions) frequently never uses the phrase. Gating on the
    broad polymer vocabulary alone would drown the feed instead. So a core term qualifies an
    item outright, and otherwise it must pair polymer/process vocabulary with an HST context
    (wire, cable, catheter, busbar, ...). Excludes hard-drop obvious off-topic matches first."""
    targeting = config.get("targeting", {})
    text = f"{item.title} {item.abstract or ''}".lower()

    def hits(key: str) -> bool:
        return any(str(term).lower() in text for term in targeting.get(key, []))

    if hits("exclude_terms"):
        return False
    if hits("hst_core_terms"):
        return True
    return hits("adjacent_terms") and hits("context_terms")


def utc_today() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def lookback_date(config: dict[str, Any]) -> str:
    hours = int(config.get("meta", {}).get("lookback_hours", 48))
    return (datetime.now(timezone.utc) - timedelta(hours=hours)).date().isoformat()


def resolve_filter_placeholders(filters: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
    resolved: dict[str, Any] = {}
    replacements = {"{lookback_date}": lookback_date(config)}
    for key, value in filters.items():
        if isinstance(value, str):
            for placeholder, replacement in replacements.items():
                value = value.replace(placeholder, replacement)
        resolved[key] = value
    return resolved
