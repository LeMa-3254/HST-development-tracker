from __future__ import annotations

import time
from typing import Any
from urllib.parse import urlencode
import xml.etree.ElementTree as ET

from models import Item
from .base import SourceAdapter, SourceResult, clean_text, fetch_url, normalize_date, vocabulary_match


ATOM = {"atom": "http://www.w3.org/2005/Atom", "arxiv": "http://arxiv.org/schemas/atom"}


class ArxivAdapter(SourceAdapter):
    source_type = "arxiv"

    def fetch(self) -> SourceResult:
        items: list[Item] = []
        errors: list[str] = []
        for category in self.source_config.get("categories", []):
            query = f"cat:{category}"
            params = urlencode(
                {
                    "search_query": query,
                    "sortBy": "submittedDate",
                    "sortOrder": "descending",
                    "max_results": "50",
                }
            )
            url = f"{self.source_config['api_base']}?{params}"
            try:
                parsed = parse_arxiv_feed(fetch_url(url), tier=self.tier)
            except Exception as exc:  # Source isolation belongs at adapter boundary.
                errors.append(f"arxiv:{category}: {exc}")
                continue
            items.extend(
                item
                for item in parsed
                if not self.source_config.get("filter_with_vocabulary") or vocabulary_match(item, self.config)
            )
            time.sleep(3)
        return SourceResult(items=items, errors=errors)


def parse_arxiv_feed(payload: bytes, *, tier: str) -> list[Item]:
    root = ET.fromstring(payload)
    items: list[Item] = []
    for entry in root.findall("atom:entry", ATOM):
        title = clean_text(entry.findtext("atom:title", namespaces=ATOM))
        url = entry.findtext("atom:id", default="", namespaces=ATOM)
        abstract = clean_text(entry.findtext("atom:summary", namespaces=ATOM))
        published = normalize_date(entry.findtext("atom:published", namespaces=ATOM))
        authors = [
            clean_text(author.findtext("atom:name", namespaces=ATOM))
            for author in entry.findall("atom:author", ATOM)
        ]
        doi = entry.findtext("arxiv:doi", namespaces=ATOM)
        if title and url:
            items.append(
                Item.from_source(
                    title=title,
                    url=url,
                    source_type="arxiv",
                    source_name="arXiv",
                    tier=tier,
                    authors=[author for author in authors if author],
                    published_date=published,
                    abstract=abstract,
                    doi=doi,
                )
            )
    return items

