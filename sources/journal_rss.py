from __future__ import annotations

from .rss_feeds import FeedListAdapter, parse_atom, parse_rss, parse_rss_or_atom

__all__ = ["JournalRssAdapter", "parse_rss_or_atom", "parse_rss", "parse_atom"]


class JournalRssAdapter(FeedListAdapter):
    source_type = "journal_rss"
    default_source_name = "journal RSS"
