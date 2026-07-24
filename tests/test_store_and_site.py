import tempfile
from pathlib import Path
import importlib.util
import unittest

from models import Item
from store.db import (
    connect,
    included_items,
    included_items_between,
    init_db,
    latest_weekly_summary,
    log_run,
    upsert_items,
    upsert_weekly_summary,
    weekly_summaries,
)


SITE_BUILD_PATH = Path(__file__).resolve().parents[1] / "site" / "build.py"
SPEC = importlib.util.spec_from_file_location("hst_site_build", SITE_BUILD_PATH)
site_build = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(site_build)


class StoreTests(unittest.TestCase):
    def test_init_upsert_and_query_included_items(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "tracker.db"
            item = Item.from_source(
                title="Gel fraction control in crosslinked polyolefin tubing",
                url="https://example.test/paper",
                source_type="test",
                source_name="Example",
                tier="A",
            )
            item.status = "included"
            item.summary = "A useful test item."
            item.why_it_matters = "It proves the store path works."

            with connect(db_path) as db:
                init_db(db)
                upsert_items(db, [item])
                log_run(db, counts={"fetched": 1, "included": 1})
                rows = included_items(db)

            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["title"], "Gel fraction control in crosslinked polyolefin tubing")

    def test_static_render_includes_item_and_rss_metadata(self):
        config = {
            "site": {
                "name": "HST Intelligence",
                "description": "Weekly feed plus synthesis.",
                "url": "https://example.github.io/",
            }
        }
        item = {
            "id": "abc123",
            "title": "Dual-wall heat shrink tubing for EV busbars",
            "url": "https://example.test/paper",
            "source_name": "Example",
            "published_date": "2026-06-29",
            "fetched_date": "2026-06-29",
            "theme": "products_and_launches",
            "summary": "A useful test item.",
            "abstract": None,
            "why_it_matters": "It proves rendering works.",
        }

        html = site_build.render_index(config, [item])

        self.assertIn("Dual-wall heat shrink tubing for EV busbars", html)
        self.assertIn("Products &amp; Launches", html)
        # RSS was removed entirely — no feed, no nav/footer link, and no <link rel="alternate">
        # discovery tag (that tag is what makes browsers show an RSS affordance on a page with
        # no visible link).
        self.assertNotIn("application/rss+xml", html)
        self.assertNotIn("feed.xml", html)
        self.assertFalse(hasattr(site_build, "render_rss"))

    def test_archive_render_includes_filters_and_items(self):
        config = {
            "site": {
                "name": "HST Intelligence",
                "description": "Weekly feed plus synthesis.",
                "url": "https://example.github.io/",
            }
        }
        items = [
            {
                "id": "abc123",
                "title": "Gel fraction control in crosslinked polyolefin tubing",
                "url": "https://example.test/paper",
                "source_name": "Example",
                "published_date": "2026-06-29",
                "fetched_date": "2026-06-29",
                "theme": "manufacturing & processing",
                "summary": "A useful test item.",
                "abstract": None,
                "why_it_matters": "It proves rendering works.",
            }
        ]

        html = site_build.render_archive(config, items)

        self.assertIn('id="search"', html)
        self.assertIn('value="Example"', html)
        self.assertIn('value="Manufacturing &amp; Processing"', html)
        self.assertIn("Gel fraction control in crosslinked polyolefin tubing", html)

    def test_index_ranks_industry_items_above_academic(self):
        config = {
            "site": {"name": "HST Intelligence", "description": "d", "url": "https://example.github.io/"},
            "targeting": {"technical_boost_terms": ["gel fraction"]},
        }

        def row(title, source_type, relevance):
            return {
                "id": title, "title": title, "url": f"https://x/{title}", "source_name": "E",
                "source_type": source_type, "published_date": "2026-06-29", "fetched_date": "2026-06-29",
                "theme": "Products & Launches", "summary": None, "abstract": None,
                "why_it_matters": None, "relevance_score": relevance, "quality_score": relevance,
            }

        # Equal scores, and the academic item carries a technical boost term — industry still
        # leads. (Scores themselves outrank this: render_index splits the "High signal" section
        # by score first, so a genuinely higher-scored paper does sort above a weak launch. That
        # is the rubric's job, and prompts/relevance.md is what weights industry there.)
        items = [row("Gel fraction paper", "crossref", 88), row("Tubing launched", "company_news", 88)]
        html = site_build.render_index(config, items)

        self.assertLess(html.index("Tubing launched"), html.index("Gel fraction paper"))

    def test_archive_json_escapes_script_closing_sequences(self):
        rendered = site_build.json_for_script([{"title": "</script><p>bad</p>"}])

        self.assertIn("<\\/script>", rendered)
        self.assertNotIn("</script>", rendered)

    def test_markdown_heading_formats_theme_identifiers(self):
        html = site_build.markdown_to_html("### materials_informatics_property_prediction")

        self.assertIn("materials informatics property prediction", html)

    def test_feed_days_per_source_override_puts_vendor_posts_on_the_front_page(self):
        """Manufacturer newsrooms post a few times a year; under the global 30-day window a
        vendor's only heat shrink post of the quarter never reaches the front page."""
        config = {
            "site": {"feed_days": 30},
            "sources": {"company_news": {"feed_days": 180}},
        }
        vendor = {"source_type": "company_news"}
        trade = {"source_type": "web_news"}

        self.assertEqual(site_build.feed_days_for(vendor, config), 180)
        self.assertEqual(site_build.feed_days_for(trade, config), 30)
        self.assertEqual(site_build.feed_days_for({"source_type": "crossref"}, config), 30)

    def test_build_site_shows_an_old_vendor_post_on_the_front_page(self):
        from datetime import date, timedelta

        old = (date.today() - timedelta(days=120)).isoformat()
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "tracker.db"
            config_path = Path(tmpdir) / "targeting.yaml"
            output_dir = Path(tmpdir) / "public"
            config_path.write_text(
                "\n".join(
                    [
                        "site: {name: HST Intelligence, description: d, url: https://x/, feed_days: 30}",
                        "sources:",
                        "  company_news: {feed_days: 180}",
                        "targeting: {technical_boost_terms: []}",
                    ]
                ),
                encoding="utf-8",
            )
            vendor = Item.from_source(
                title="Zeus expands PFX Flex heat shrink line", url="https://x/zeus",
                source_type="company_news", source_name="Zeus", tier="A", published_date=old,
            )
            vendor.status = "included"
            stale_paper = Item.from_source(
                title="An old polymer paper", url="https://x/old",
                source_type="crossref", source_name="Crossref", tier="B", published_date=old,
            )
            stale_paper.status = "included"

            with connect(db_path) as db:
                init_db(db)
                upsert_items(db, [vendor, stale_paper])

            site_build.build_site(config_path=str(config_path), db_path=str(db_path), output_dir=str(output_dir))
            index = (output_dir / "index.html").read_text()
            archive = (output_dir / "archive.html").read_text()

        self.assertIn("Zeus expands PFX Flex heat shrink line", index)
        # the equally-old academic item is still held to the 30-day window
        self.assertNotIn("An old polymer paper", index)
        self.assertIn("An old polymer paper", archive)

    def test_within_days_windows_by_effective_date(self):
        from datetime import date, timedelta

        recent = {"published_date": (date.today() - timedelta(days=10)).isoformat(), "fetched_date": None}
        old = {"published_date": (date.today() - timedelta(days=200)).isoformat(), "fetched_date": None}
        undated = {"published_date": None, "fetched_date": None}

        self.assertTrue(site_build.within_days(recent, 30))
        self.assertFalse(site_build.within_days(old, 30))
        self.assertTrue(site_build.within_days(undated, 30))   # undated treated as current
        self.assertTrue(site_build.within_days(old, 0))        # window disabled

    def test_build_site_writes_archive_page(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "tracker.db"
            config_path = Path(tmpdir) / "targeting.yaml"
            output_dir = Path(tmpdir) / "public"
            config_path.write_text(
                "\n".join(
                    [
                        "site:",
                        "  name: HST Intelligence",
                        "  description: Weekly feed plus synthesis.",
                        "  url: https://example.github.io/",
                    ]
                ),
                encoding="utf-8",
            )
            item = Item.from_source(
                title="Gel fraction control in crosslinked polyolefin tubing",
                url="https://example.test/paper",
                source_type="test",
                source_name="Example",
                tier="A",
            )
            item.status = "included"

            with connect(db_path) as db:
                init_db(db)
                upsert_items(db, [item])

            site_build.build_site(config_path=str(config_path), db_path=str(db_path), output_dir=str(output_dir))

            self.assertTrue((output_dir / "archive.html").exists())
            self.assertTrue((output_dir / "index.json").exists())

    def test_weekly_summary_store_and_render(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "tracker.db"
            item = Item.from_source(
                title="Gel fraction control in crosslinked polyolefin tubing",
                url="https://example.test/paper",
                source_type="test",
                source_name="Example",
                tier="A",
                published_date="2026-06-29",
            )
            item.status = "included"

            with connect(db_path) as db:
                init_db(db)
                upsert_items(db, [item])
                rows = included_items_between(db, start_date="2026-06-29", end_date="2026-07-05")
                upsert_weekly_summary(
                    db,
                    week_start="2026-06-29",
                    week_end="2026-07-05",
                    synthesis_md="## Weekly Synthesis\n\nA useful trend.",
                    item_ids=[row["id"] for row in rows],
                )
                latest = latest_weekly_summary(db)
                summaries = weekly_summaries(db)

        config = {
            "site": {
                "name": "HST Intelligence",
                "description": "Weekly feed plus synthesis.",
                "url": "https://example.github.io/",
            }
        }

        self.assertEqual(len(rows), 1)
        self.assertEqual(latest["week_start"], "2026-06-29")
        self.assertIn("Weekly Synthesis", site_build.render_weekly(config, summaries))


if __name__ == "__main__":
    unittest.main()
