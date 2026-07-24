from __future__ import annotations

from typing import Any

from models import Item
from sources import (
    ArxivAdapter,
    CompanyNewsAdapter,
    CrossrefAdapter,
    GoogleNewsAdapter,
    JournalRssAdapter,
    OpenAlexAdapter,
    OrgBlogsAdapter,
    UniversityNewsAdapter,
    WebNewsAdapter,
)


ADAPTERS = {
    "arxiv": ArxivAdapter,
    "openalex": OpenAlexAdapter,
    "crossref": CrossrefAdapter,
    "journal_rss": JournalRssAdapter,
    "university_news": UniversityNewsAdapter,
    "web_news": WebNewsAdapter,
    "company_news": CompanyNewsAdapter,
    "org_blogs": OrgBlogsAdapter,
    "google_news": GoogleNewsAdapter,
}


def ingest_enabled_sources(config: dict[str, Any]) -> tuple[list[Item], list[str]]:
    items: list[Item] = []
    errors: list[str] = []
    for name, source_config in config.get("sources", {}).items():
        if not isinstance(source_config, dict) or not source_config.get("enabled"):
            continue
        adapter_class = ADAPTERS.get(name)
        if adapter_class is None:
            errors.append(f"{name}: no adapter implemented")
            continue
        result = adapter_class(config, source_config).fetch()
        items.extend(result.items)
        errors.extend(result.errors)
    return items, errors

