from __future__ import annotations

from urllib.parse import quote_plus

from models import Item
from .base import SourceAdapter, SourceResult, fetch_url, vocabulary_match
from .rss_feeds import FEED_HEADERS, parse_rss_or_atom


class GoogleNewsAdapter(SourceAdapter):
    """Query-mode open-web news via the Google News RSS search endpoint.

    Noisy by design: each configured query becomes one RSS search URL, results are parsed
    like any other feed, then the targeting vocabulary gate drops everything that is not a
    polymer + AI hit. The LLM rubric is the fine filter downstream.
    """

    source_type = "google_news"

    def fetch(self) -> SourceResult:
        template = self.source_config.get(
            "rss_template",
            "https://news.google.com/rss/search?q={query}&hl=en-US&gl=US&ceid=US:en",
        )
        items: list[Item] = []
        errors: list[str] = []
        for query in self.source_config.get("queries", []):
            url = template.replace("{query}", quote_plus(query))
            try:
                parsed = parse_rss_or_atom(
                    fetch_url(url, headers=FEED_HEADERS),
                    source_name="Google News",
                    tier=self.tier,
                    source_type="google_news",
                )
            except Exception as exc:  # Source isolation belongs at the adapter boundary.
                errors.append(f"google_news:{query}: {exc}")
                continue
            items.extend(item for item in parsed if vocabulary_match(item, self.config))
        return SourceResult(items=items, errors=errors)
