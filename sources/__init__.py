from .arxiv import ArxivAdapter
from .crossref import CrossrefAdapter
from .google_news import GoogleNewsAdapter
from .journal_rss import JournalRssAdapter
from .openalex import OpenAlexAdapter
from .rss_feeds import CompanyNewsAdapter, OrgBlogsAdapter, UniversityNewsAdapter, WebNewsAdapter

__all__ = [
    "ArxivAdapter",
    "CompanyNewsAdapter",
    "CrossrefAdapter",
    "GoogleNewsAdapter",
    "JournalRssAdapter",
    "OpenAlexAdapter",
    "OrgBlogsAdapter",
    "UniversityNewsAdapter",
    "WebNewsAdapter",
]
