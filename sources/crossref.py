from __future__ import annotations

import json
from typing import Any
from urllib.parse import urlencode

from models import Item
from .base import SourceAdapter, SourceResult, clean_text, fetch_url, first_real_date, resolve_filter_placeholders


class CrossrefAdapter(SourceAdapter):
    source_type = "crossref"

    def fetch(self) -> SourceResult:
        filters = ",".join(
            f"{key}:{value}"
            for key, value in resolve_filter_placeholders(self.source_config.get("filters", {}), self.config).items()
        )
        params = {
            "query": self.source_config.get("query", ""),
            "filter": filters,
            "rows": str(self.source_config.get("rows", 100)),
            "mailto": self.config.get("meta", {}).get("contact_email", ""),
        }
        url = f"{self.source_config['api_base']}?{urlencode(params)}"
        try:
            return SourceResult(items=parse_crossref(json.loads(fetch_url(url)), tier=self.tier), errors=[])
        except Exception as exc:
            return SourceResult(items=[], errors=[f"crossref: {exc}"])


def parse_crossref(payload: dict[str, Any], *, tier: str) -> list[Item]:
    items: list[Item] = []
    for work in payload.get("message", {}).get("items", []):
        title = clean_text(first(work.get("title")))
        url = work.get("URL") or (f"https://doi.org/{work['DOI']}" if work.get("DOI") else "")
        authors = [
            " ".join(part for part in [author.get("given"), author.get("family")] if part)
            for author in work.get("author", [])
        ]
        published = crossref_source_date(work)
        if title and url:
            items.append(
                Item.from_source(
                    title=title,
                    url=url,
                    source_type="crossref",
                    source_name=clean_text(first(work.get("container-title"))) or "Crossref",
                    tier=tier,
                    authors=[author for author in authors if author],
                    published_date=published,
                    abstract=clean_text(work.get("abstract")),
                    doi=work.get("DOI"),
                )
            )
    return items


def first(values: list[str] | None) -> str | None:
    return values[0] if values else None


def date_parts(value: dict[str, Any] | None) -> str | None:
    parts = (value or {}).get("date-parts", [[]])[0]
    if not parts:
        return None
    year = parts[0]
    month = parts[1] if len(parts) > 1 else 1
    day = parts[2] if len(parts) > 2 else 1
    return first_real_date(f"{year:04d}-{month:02d}-{day:02d}")


def crossref_source_date(work: dict[str, Any]) -> str | None:
    return first_real_date(
        date_parts(work.get("published-print")),
        date_parts(work.get("published-online")),
        date_parts(work.get("published")),
        date_parts(work.get("posted")),
        date_parts(work.get("accepted")),
        date_parts(work.get("approved")),
        date_parts(work.get("created")),
        date_parts(work.get("deposited")),
        date_parts(work.get("indexed")),
    )
