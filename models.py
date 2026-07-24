from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date, datetime, timezone
import hashlib
import json
from typing import Any


def stable_item_id(*, url: str, title: str, doi: str | None = None) -> str:
    key = doi or url or title
    return hashlib.sha256(key.strip().lower().encode("utf-8")).hexdigest()[:24]


@dataclass(slots=True)
class Item:
    id: str
    title: str
    url: str
    source_type: str
    source_name: str
    tier: str
    authors: list[str]
    published_date: str | None
    fetched_date: str
    abstract: str | None = None
    doi: str | None = None
    embedding: list[float] | None = None
    relevance_score: float | None = None
    quality_score: float | None = None
    score_reason: str | None = None
    theme: str | None = None
    summary: str | None = None
    why_it_matters: str | None = None
    digest_date: str | None = None
    status: str = "candidate"
    dup_of: str | None = None

    @classmethod
    def from_source(
        cls,
        *,
        title: str,
        url: str,
        source_type: str,
        source_name: str,
        tier: str,
        authors: list[str] | None = None,
        published_date: str | None = None,
        abstract: str | None = None,
        doi: str | None = None,
    ) -> "Item":
        return cls(
            id=stable_item_id(url=url, title=title, doi=doi),
            title=title.strip(),
            url=url.strip(),
            source_type=source_type,
            source_name=source_name,
            tier=tier,
            authors=authors or [],
            published_date=published_date,
            fetched_date=datetime.now(timezone.utc).date().isoformat(),
            abstract=abstract,
            doi=doi,
        )

    def to_db_row(self) -> dict[str, Any]:
        row = asdict(self)
        row["authors"] = json.dumps(self.authors, sort_keys=True)
        row["embedding"] = json.dumps(self.embedding) if self.embedding is not None else None
        return row

    def display_date(self) -> str:
        return self.published_date or self.fetched_date or date.today().isoformat()

