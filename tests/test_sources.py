import unittest

from models import Item
import sources.google_news as google_news
from sources.base import (
    decompress_if_gzip,
    normalize_date,
    resolve_filter_placeholders,
    vocabulary_match,
)
from sources.crossref import crossref_source_date, date_parts
from sources.google_news import GoogleNewsAdapter
from sources.journal_rss import parse_rss_or_atom
from sources.openalex import openalex_source_date, reconstruct_abstract
from sources.rss_feeds import CompanyNewsAdapter, UniversityNewsAdapter


CONFIG = {
    "targeting": {
        "hst_core_terms": ["heat shrink", "shrink tubing", "cross-linked polyolefin"],
        "adjacent_terms": ["fluoropolymer", "ptfe", "fep", "extrusion", "crosslinking"],
        "context_terms": ["wire", "cable", "catheter", "busbar"],
        "exclude_terms": ["shrinkflation"],
    }
}


def _item(title: str, url: str = "https://example.test/item") -> Item:
    return Item.from_source(
        title=title,
        url=url,
        source_type="test",
        source_name="Test",
        tier="A",
    )


class GateTests(unittest.TestCase):
    """The two-axis gate: core OR (adjacent AND context). This is the one place the design
    departs from SoftRobotics Intelligence's single-axis gate, so each branch is pinned."""

    def test_core_term_alone_passes(self):
        # No polymer or context vocabulary anywhere — the core anchor carries it on its own.
        self.assertTrue(vocabulary_match(_item("Supplier expands heat shrink capacity"), CONFIG))

    def test_adjacent_without_context_fails(self):
        # Polymer vocabulary with no HST context is exactly the noise the second axis exists to stop.
        self.assertFalse(vocabulary_match(_item("New PTFE membrane for water filtration"), CONFIG))

    def test_context_without_adjacent_fails(self):
        self.assertFalse(vocabulary_match(_item("Utility replaces overhead cable spans"), CONFIG))

    def test_adjacent_plus_context_passes(self):
        self.assertTrue(vocabulary_match(_item("FEP extrusion advances for catheter shaft liners"), CONFIG))

    def test_adjacent_and_context_may_be_split_across_title_and_abstract(self):
        item = _item("Crosslinking dose study")
        item.abstract = "Applied to wire insulation samples."
        self.assertTrue(vocabulary_match(item, CONFIG))

    def test_excludes_hard_drop_even_with_a_core_term(self):
        self.assertFalse(vocabulary_match(_item("Heat shrink prices and shrinkflation"), CONFIG))


class SourceTests(unittest.TestCase):

    def test_parse_rss_feed(self):
        payload = b"""<?xml version="1.0"?>
        <rss version="2.0"><channel><item>
          <title>Machine learning polymer discovery</title>
          <link>https://example.test/rss-item</link>
          <description>New materials informatics result.</description>
          <pubDate>Mon, 29 Jun 2026 12:00:00 GMT</pubDate>
        </item></channel></rss>"""

        items = parse_rss_or_atom(payload, source_name="Example Journal", tier="A")

        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].source_name, "Example Journal")
        self.assertEqual(items[0].published_date, "2026-06-29")

    def test_parse_rss_tags_caller_source_type(self):
        payload = b"""<?xml version="1.0"?>
        <rss version="2.0"><channel><item>
          <title>Machine learning polymer discovery</title>
          <link>https://example.test/uni-item</link>
          <description>University press release.</description>
        </item></channel></rss>"""

        items = parse_rss_or_atom(
            payload, source_name="MIT News", tier="C", source_type="university_news"
        )

        self.assertEqual(items[0].source_type, "university_news")

    def test_feed_list_adapter_gates_by_vocabulary(self):
        on_topic = b"""<?xml version="1.0"?>
        <rss version="2.0"><channel><item>
          <title>Dual-wall heat shrink tubing for harness sealing</title>
          <link>https://example.test/on</link>
          <description>Adhesive-lined tubing study.</description>
        </item></channel></rss>"""
        off_topic = b"""<?xml version="1.0"?>
        <rss version="2.0"><channel><item>
          <title>Campus wins football championship</title>
          <link>https://example.test/off</link>
          <description>Sports news.</description>
        </item></channel></rss>"""
        fetched: list[str] = []

        def fake_fetch(url, **kwargs):
            fetched.append(url)
            return on_topic if url.endswith("/on.rss") else off_topic

        adapter = UniversityNewsAdapter(
            CONFIG,
            {
                "tier": "C",
                "feeds": [
                    {"name": "On", "url": "https://example.test/on.rss"},
                    {"name": "Off", "url": "https://example.test/off.rss"},
                ],
            },
        )
        import sources.rss_feeds as rss_feeds

        original = rss_feeds.fetch_url
        rss_feeds.fetch_url = fake_fetch
        try:
            result = adapter.fetch()
        finally:
            rss_feeds.fetch_url = original

        self.assertEqual(len(fetched), 2)
        self.assertEqual([item.title for item in result.items], ["Dual-wall heat shrink tubing for harness sealing"])
        self.assertEqual(result.items[0].source_type, "university_news")

    def test_company_news_adapter_tags_its_own_source_type(self):
        payload = b"""<?xml version="1.0"?>
        <rss version="2.0"><channel><item>
          <title>Zeus launches PFAS-free heat shrink tubing</title>
          <link>https://example.test/press</link>
          <description>Manufacturer press release.</description>
        </item></channel></rss>"""

        adapter = CompanyNewsAdapter(
            CONFIG,
            {"tier": "B", "feeds": [{"name": "Zeus Company", "url": "https://example.test/feed"}]},
        )
        import sources.rss_feeds as rss_feeds

        original = rss_feeds.fetch_url
        rss_feeds.fetch_url = lambda url, **kwargs: payload
        try:
            result = adapter.fetch()
        finally:
            rss_feeds.fetch_url = original

        self.assertEqual(len(result.items), 1)
        self.assertEqual(result.items[0].source_type, "company_news")
        self.assertEqual(result.items[0].tier, "B")

    def test_google_news_encodes_queries_and_gates(self):
        payload = b"""<?xml version="1.0"?>
        <rss version="2.0"><channel><item>
          <title>New heat shrink tubing series unveiled by supplier</title>
          <link>https://news.google.test/article</link>
          <description>Coverage of a tubing launch.</description>
        </item></channel></rss>"""
        urls: list[str] = []

        def fake_fetch(url, **kwargs):
            urls.append(url)
            return payload

        adapter = GoogleNewsAdapter(
            CONFIG,
            {"tier": "C", "queries": ["heat shrink tubing new product launch"]},
        )
        original = google_news.fetch_url
        google_news.fetch_url = fake_fetch
        try:
            result = adapter.fetch()
        finally:
            google_news.fetch_url = original

        self.assertEqual(len(urls), 1)
        self.assertIn("q=heat+shrink+tubing+new+product+launch", urls[0])
        self.assertEqual(result.items[0].source_type, "google_news")
        self.assertEqual(result.items[0].source_name, "Google News")

    def test_reconstruct_openalex_abstract(self):
        self.assertEqual(
            reconstruct_abstract({"polymer": [1], "AI": [0], "design": [2]}),
            "AI polymer design",
        )

    def test_resolve_lookback_date_placeholder(self):
        resolved = resolve_filter_placeholders(
            {"from_publication_date": "{lookback_date}"},
            {"meta": {"lookback_hours": 48}},
        )

        self.assertRegex(resolved["from_publication_date"], r"^\d{4}-\d{2}-\d{2}$")

    def test_gzip_payloads_are_transparently_decompressed(self):
        # mattr.com/feed/ returns gzip bytes with no Accept-Encoding request header, which
        # urllib does not unwrap; without this the feed dies at the XML parser.
        import gzip as gzip_mod

        raw = b"<?xml version='1.0'?><rss version='2.0'><channel></channel></rss>"
        self.assertEqual(decompress_if_gzip(gzip_mod.compress(raw)), raw)

    def test_non_gzip_payloads_pass_through_untouched(self):
        raw = b"<?xml version='1.0'?><rss/>"
        self.assertEqual(decompress_if_gzip(raw), raw)

    def test_normalize_date_rejects_future_dates(self):
        self.assertIsNone(normalize_date("2035-09-05"))

    def test_crossref_date_parts_rejects_future_dates(self):
        self.assertIsNone(date_parts({"date-parts": [[2035, 9, 5]]}))

    def test_openalex_source_date_uses_record_date_when_publication_is_future(self):
        self.assertEqual(
            openalex_source_date(
                {
                    "publication_date": "2035-09-05",
                    "created_date": "2026-06-20",
                    "updated_date": "2026-06-21",
                }
            ),
            "2026-06-20",
        )

    def test_crossref_source_date_uses_created_date_when_publication_is_future(self):
        self.assertEqual(
            crossref_source_date(
                {
                    "published-print": {"date-parts": [[2035, 9, 5]]},
                    "published-online": {"date-parts": [[2026, 12, 31]]},
                    "created": {"date-parts": [[2026, 6, 20]]},
                }
            ),
            "2026-06-20",
        )


if __name__ == "__main__":
    unittest.main()
