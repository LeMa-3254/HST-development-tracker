from pathlib import Path
import tempfile
import unittest

from models import Item
import pipeline.run as pipeline_run
from store.db import connect


class PipelineRunTests(unittest.TestCase):
    def test_pipeline_dry_run_writes_items_run_log_and_weekly_summary(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            config_path = root / "targeting.yaml"
            db_path = root / "tracker.db"
            week_start, _week_end = pipeline_run.last_complete_week_bounds()
            config_path.write_text(
                "\n".join(
                    [
                        "site:",
                        "  name: HST Intelligence",
                        "  description: Weekly feed plus synthesis.",
                        "  url: https://example.github.io/",
                        "targeting:",
                        "  hst_core_terms: [heat shrink, shrink tubing]",
                        "  adjacent_terms: [fluoropolymer, crosslinking]",
                        "  context_terms: [wire, cable]",
                        "  exclude_terms: []",
                        "  technical_boost_terms: [gel fraction]",
                        "sources: {}",
                        "scoring:",
                        "  min_score: 70",
                        "dedup:",
                        "  window_days: 30",
                        "  similarity_threshold: 0.92",
                        "  on_duplicate: drop",
                        "enrich:",
                        "  max_items_per_run: 5",
                        "synth: {}",
                    ]
                ),
                encoding="utf-8",
            )

            def fake_ingest(_config):
                item = Item.from_source(
                    title="Dual-wall heat shrink tubing with adhesive liner",
                    url="https://example.test/paper",
                    source_type="test",
                    source_name="Example",
                    tier="A",
                    published_date=week_start,
                    abstract="Irradiated polyolefin tubing characterized by gel fraction.",
                )
                return [item], []

            original_ingest = pipeline_run.ingest_enabled_sources
            pipeline_run.ingest_enabled_sources = fake_ingest
            try:
                exit_code = pipeline_run.run_pipeline(
                    config_path=str(config_path),
                    db_path=str(db_path),
                    weekly_synthesis=True,
                )
            finally:
                pipeline_run.ingest_enabled_sources = original_ingest

            self.assertEqual(exit_code, 0)
            with connect(db_path) as db:
                item_count = db.execute("SELECT COUNT(*) FROM items WHERE status = 'included'").fetchone()[0]
                run_count = db.execute("SELECT COUNT(*) FROM runs").fetchone()[0]
                weekly_count = db.execute("SELECT COUNT(*) FROM weekly_summaries").fetchone()[0]

        self.assertEqual(item_count, 1)
        self.assertEqual(run_count, 1)
        self.assertEqual(weekly_count, 1)

    def test_per_source_max_age_overrides_the_global_ceiling(self):
        """Manufacturer newsrooms post every few months; the global 30-day ceiling dropped every
        gated company_news item on the first verification run."""
        from datetime import date, timedelta

        config = {
            "meta": {"max_age_days": 30},
            "sources": {"company_news": {"max_age_days": 120}},
        }

        def make(source_type, age_days):
            return Item.from_source(
                title="t", url=f"https://x/{source_type}{age_days}", source_type=source_type,
                source_name="E", tier="A",
                published_date=(date.today() - timedelta(days=age_days)).isoformat(),
            )

        self.assertTrue(pipeline_run.is_fresh(make("company_news", 90), config))
        self.assertFalse(pipeline_run.is_fresh(make("company_news", 150), config))
        # a source without an override still uses meta.max_age_days
        self.assertFalse(pipeline_run.is_fresh(make("web_news", 90), config))
        self.assertTrue(pipeline_run.is_fresh(make("web_news", 10), config))

    def test_prefilter_ranks_industry_sources_ahead_of_academic(self):
        """HST advances in industry first, so when max_candidates bites it must drop academic
        long-tail rather than product news."""
        config = {
            "targeting": {
                "hst_core_terms": ["heat shrink"],
                "adjacent_terms": [],
                "context_terms": [],
                "exclude_terms": [],
                "technical_boost_terms": ["gel fraction"],
            },
            "meta": {"max_age_days": 0},
            "scoring": {"max_candidates": 0},
        }

        def make(title, source_type, published):
            return Item.from_source(
                title=title, url=f"https://x/{title}", source_type=source_type,
                source_name="E", tier="A", published_date=published,
            )

        # The academic item is both newer AND carries a boost term — industry must still win.
        academic = make("Heat shrink gel fraction study", "crossref", "2026-07-20")
        vendor = make("Heat shrink tubing launched", "company_news", "2026-07-01")
        trade = make("Heat shrink line commissioned", "web_news", "2026-07-02")

        ordered = pipeline_run.prefilter_candidates([academic, vendor, trade], config)

        self.assertEqual([i.source_type for i in ordered], ["web_news", "company_news", "crossref"])

    def test_prefilter_keeps_technical_then_recency_within_a_group(self):
        config = {
            "targeting": {
                "hst_core_terms": ["heat shrink"],
                "adjacent_terms": [],
                "context_terms": [],
                "exclude_terms": [],
                "technical_boost_terms": ["gel fraction"],
            },
            "meta": {"max_age_days": 0},
            "scoring": {"max_candidates": 0},
        }

        def make(title, published):
            return Item.from_source(
                title=title, url=f"https://x/{title}", source_type="web_news",
                source_name="E", tier="A", published_date=published,
            )

        older_technical = make("Heat shrink gel fraction result", "2026-07-01")
        newer_thin = make("Heat shrink roundup", "2026-07-20")
        newest_technical = make("Heat shrink gel fraction follow-up", "2026-07-22")

        ordered = pipeline_run.prefilter_candidates([older_technical, newer_thin, newest_technical], config)

        self.assertEqual(
            [i.title for i in ordered],
            ["Heat shrink gel fraction follow-up", "Heat shrink gel fraction result", "Heat shrink roundup"],
        )

    def test_is_fresh_drops_old_keeps_recent_and_undated(self):
        from datetime import date, timedelta

        config = {"meta": {"max_age_days": 30}}
        recent = Item.from_source(
            title="t", url="https://x/r", source_type="t", source_name="E", tier="A",
            published_date=(date.today() - timedelta(days=5)).isoformat(),
        )
        old = Item.from_source(
            title="t", url="https://x/o", source_type="t", source_name="E", tier="A",
            published_date=(date.today() - timedelta(days=400)).isoformat(),
        )
        undated = Item.from_source(
            title="t", url="https://x/u", source_type="t", source_name="E", tier="A",
        )

        self.assertTrue(pipeline_run.is_fresh(recent, config))
        self.assertFalse(pipeline_run.is_fresh(old, config))
        self.assertTrue(pipeline_run.is_fresh(undated, config))
        # window disabled when max_age_days is unset/zero
        self.assertTrue(pipeline_run.is_fresh(old, {"meta": {}}))

    def test_rescore_archive_drops_items_failing_current_gate(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            config_path = root / "targeting.yaml"
            db_path = root / "tracker.db"
            config_path.write_text(
                "\n".join(
                    [
                        "site: {name: HST Intelligence, description: d, url: https://x/}",
                        "targeting:",
                        "  hst_core_terms: [heat shrink, shrink tubing]",
                        "  adjacent_terms: [fluoropolymer, crosslinking]",
                        "  context_terms: [wire, cable]",
                        "  exclude_terms: []",
                        "  technical_boost_terms: [gel fraction]",
                        "scoring: {min_score: 70}",
                        "synth: {}",
                    ]
                ),
                encoding="utf-8",
            )
            from store.db import init_db, upsert_items

            on_topic = Item.from_source(
                title="Heat shrink tubing gel fraction study", url="https://x/p", source_type="t",
                source_name="E", tier="A", abstract="shrink tubing crosslinking on wire samples",
            )
            on_topic.status = "included"
            offtopic = Item.from_source(
                title="Machine learning for steel welding", url="https://x/s", source_type="t",
                source_name="E", tier="A", abstract="stainless steel weld optimization",
            )
            offtopic.status = "included"
            with connect(db_path) as db:
                init_db(db)
                upsert_items(db, [on_topic, offtopic])

            pipeline_run.rescore_archive(config_path=str(config_path), db_path=str(db_path), weekly_synthesis=False)

            with connect(db_path) as db:
                statuses = dict(db.execute("SELECT title, status FROM items"))
            self.assertEqual(statuses["Heat shrink tubing gel fraction study"], "included")
            self.assertEqual(statuses["Machine learning for steel welding"], "dropped_lowscore")


if __name__ == "__main__":
    unittest.main()
