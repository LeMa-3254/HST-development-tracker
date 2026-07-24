from __future__ import annotations

import xml.etree.ElementTree as ET

from models import Item
from .base import SourceAdapter, SourceResult, clean_text, fetch_url, normalize_date, vocabulary_match


# Some publishers (university press rooms, ScienceDaily, news aggregators) block the
# default urllib agent or a bare agent; a browser-like UA avoids spurious 403s.
FEED_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; HSTIntelligence/0.1; +https://lema-3254.github.io/HST-development-tracker/)",
    "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml;q=0.9, */*;q=0.8",
}


class FeedListAdapter(SourceAdapter):
    """Shared base for any source that is a list of RSS/Atom feeds.

    Broad press/blog feeds are gated by the targeting vocabulary so off-topic stories
    (sports, policy, generic ML) never reach the LLM. Subclasses only set `source_type`
    and `default_source_name`; per-feed failures are isolated and reported, not fatal.
    """

    source_type = "rss"
    default_source_name = "RSS"

    def fetch(self) -> SourceResult:
        items: list[Item] = []
        errors: list[str] = []
        for feed in self.source_config.get("feeds", []):
            name = feed.get("name", self.default_source_name)
            try:
                parsed = parse_rss_or_atom(
                    fetch_url(feed["url"], headers=FEED_HEADERS),
                    source_name=name,
                    tier=self.tier,
                    source_type=self.source_type,
                )
            except Exception as exc:  # Source isolation belongs at the adapter boundary.
                errors.append(f"{self.source_type}:{name}: {exc}")
                continue
            items.extend(item for item in parsed if vocabulary_match(item, self.config))
        return SourceResult(items=items, errors=errors)


class UniversityNewsAdapter(FeedListAdapter):
    source_type = "university_news"
    default_source_name = "University news"


class WebNewsAdapter(FeedListAdapter):
    source_type = "web_news"
    default_source_name = "Web news"


class CompanyNewsAdapter(FeedListAdapter):
    """Manufacturer newsrooms. Vendors announce new tubing SKUs here days-to-weeks before the
    trade press picks them up, so this is the earliest signal for Products & Launches."""

    source_type = "company_news"
    default_source_name = "Company news"


class OrgBlogsAdapter(FeedListAdapter):
    source_type = "org_blogs"
    default_source_name = "Research org blog"


def parse_rss_or_atom(
    payload: bytes, *, source_name: str, tier: str, source_type: str = "journal_rss"
) -> list[Item]:
    root = ET.fromstring(payload)
    if root.tag.endswith("rss") or root.find("./channel") is not None:
        return parse_rss(root, source_name=source_name, tier=tier, source_type=source_type)
    return parse_atom(root, source_name=source_name, tier=tier, source_type=source_type)


def parse_rss(root: ET.Element, *, source_name: str, tier: str, source_type: str = "journal_rss") -> list[Item]:
    items: list[Item] = []
    for element in root.findall("./channel/item"):
        title = clean_text(element.findtext("title"))
        url = clean_text(element.findtext("link"))
        abstract = clean_text(element.findtext("description"))
        published = normalize_date(element.findtext("pubDate"))
        if title and url:
            items.append(
                Item.from_source(
                    title=title,
                    url=url,
                    source_type=source_type,
                    source_name=source_name,
                    tier=tier,
                    published_date=published,
                    abstract=abstract,
                )
            )
    return items


def parse_atom(root: ET.Element, *, source_name: str, tier: str, source_type: str = "journal_rss") -> list[Item]:
    ns = {"atom": "http://www.w3.org/2005/Atom"}
    entries = root.findall("atom:entry", ns) or root.findall("entry")
    items: list[Item] = []
    for entry in entries:
        title = clean_text(entry.findtext("atom:title", namespaces=ns) or entry.findtext("title"))
        url = entry.findtext("atom:id", namespaces=ns) or entry.findtext("id") or ""
        for link in entry.findall("atom:link", ns) + entry.findall("link"):
            if link.attrib.get("href"):
                url = link.attrib["href"]
                break
        abstract = clean_text(entry.findtext("atom:summary", namespaces=ns) or entry.findtext("summary"))
        published = normalize_date(entry.findtext("atom:published", namespaces=ns) or entry.findtext("published"))
        if title and url:
            items.append(
                Item.from_source(
                    title=title,
                    url=url,
                    source_type=source_type,
                    source_name=source_name,
                    tier=tier,
                    published_date=published,
                    abstract=abstract,
                )
            )
    return items
