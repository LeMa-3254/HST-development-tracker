from __future__ import annotations

import json
from typing import Any
from urllib.parse import urlencode

from models import Item
from .base import SourceAdapter, SourceResult, clean_text, fetch_url, first_real_date, resolve_filter_placeholders


class OpenAlexAdapter(SourceAdapter):
    source_type = "openalex"

    def fetch(self) -> SourceResult:
        meta = self.config.get("meta", {})
        filters = ",".join(
            f"{key}:{value}"
            for key, value in resolve_filter_placeholders(self.source_config.get("filters", {}), self.config).items()
        )
        params = {
            "search": self.source_config.get("search", ""),
            "filter": filters,
            "per-page": str(self.source_config.get("per_page", 200)),
        }
        if self.source_config.get("mailto_from_meta") and meta.get("contact_email"):
            params["mailto"] = meta["contact_email"]
        url = f"{self.source_config['api_base']}?{urlencode(params)}"
        try:
            return SourceResult(items=parse_openalex(json.loads(fetch_url(url)), tier=self.tier), errors=[])
        except Exception as exc:
            return SourceResult(items=[], errors=[f"openalex: {exc}"])


def parse_openalex(payload: dict[str, Any], *, tier: str) -> list[Item]:
    items: list[Item] = []
    for work in payload.get("results", []):
        title = clean_text(work.get("title"))
        url = work.get("doi") or work.get("id") or work.get("primary_location", {}).get("landing_page_url", "")
        authorships = work.get("authorships", [])
        authors = [
            authorship.get("author", {}).get("display_name", "")
            for authorship in authorships
            if authorship.get("author")
        ]
        abstract = clean_text(work.get("abstract") or reconstruct_abstract(work.get("abstract_inverted_index")))
        if title and url:
            items.append(
                Item.from_source(
                    title=title,
                    url=url,
                    source_type="openalex",
                    source_name="OpenAlex",
                    tier=tier,
                    authors=[author for author in authors if author],
                    published_date=openalex_source_date(work),
                    abstract=abstract,
                    doi=work.get("doi"),
                )
            )
    return items


def reconstruct_abstract(index: dict[str, list[int]] | None) -> str | None:
    if not index:
        return None
    words: list[tuple[int, str]] = []
    for word, positions in index.items():
        words.extend((position, word) for position in positions)
    return " ".join(word for _, word in sorted(words))


def openalex_source_date(work: dict[str, Any]) -> str | None:
    return first_real_date(
        work.get("publication_date"),
        work.get("created_date"),
        work.get("updated_date"),
    )
