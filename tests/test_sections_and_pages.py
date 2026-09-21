import importlib.util
from pathlib import Path
import tempfile
import unittest

from pipeline.sections import (
    generate_material_requirements,
    generate_notable_products,
    generate_regulatory_watch,
)
from store.db import (
    all_material_requirements,
    all_notable_products,
    all_regulatory_watch,
    connect,
    init_db,
    latest_material_requirements,
    latest_notable_products,
    latest_regulatory_watch,
    upsert_material_requirements,
    upsert_notable_products,
    upsert_regulatory_watch,
)


SITE_BUILD_PATH = Path(__file__).resolve().parents[1] / "site" / "build.py"
SPEC = importlib.util.spec_from_file_location("hst_site_build", SITE_BUILD_PATH)
site_build = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(site_build)


SITE_CONFIG = {"site": {"name": "HST Intelligence", "tagline": "t", "description": "d", "url": "https://x/"}}


class FakeSearchClient:
    def __init__(self, payload):
        self.payload = payload
        self.calls = []

    def search_json(self, **kwargs):
        self.calls.append(kwargs)
        return self.payload, {"input_tokens": 7}


class SectionsTests(unittest.TestCase):
    def _config(self, enabled=True):
        return {
            "site": {"tagline": "polymer engineers"},
            "sections": {
                "material_requirements": {
                    "enabled": enabled,
                    "model": "test-model",
                    "prompt": "prompts/material_requirements.md",
                    "max_searches": 3,
                },
                "notable_products": {
                    "enabled": enabled,
                    "model": "test-model",
                    "prompt": "prompts/notable_products.md",
                    "max_searches": 3,
                },
                "regulatory_watch": {
                    "enabled": enabled,
                    "model": "test-model",
                    "prompt": "prompts/regulatory_watch.md",
                    "max_searches": 3,
                },
            },
        }

    def test_disabled_sections_return_none(self):
        config = self._config(enabled=False)
        self.assertIsNone(generate_material_requirements(config))
        self.assertIsNone(generate_notable_products(config))
        self.assertIsNone(generate_regulatory_watch(config))

    def test_no_client_returns_none(self):
        # model_client=None and no API key => build returns None => section skipped
        self.assertIsNone(generate_notable_products(self._config(), model_client=None))
        # (build_anthropic_client returns None without a key; this stays None offline)

    def test_material_requirements_uses_injected_client_and_tracks_usage(self):
        payload = {"materials": [{"application": "Dual-wall harness seal", "material_class": "e-beam irradiated polyolefin",
                                  "key_properties": "3:1 shrink, 125 C", "open_challenge": "PFAS-free liner",
                                  "source_url": "https://x/1"}]}
        client = FakeSearchClient(payload)
        token_usage = {}
        result = generate_material_requirements(self._config(), model_client=client, token_usage=token_usage)
        self.assertEqual(result, payload)
        self.assertEqual(client.calls[0]["model"], "test-model")
        self.assertEqual(client.calls[0]["max_searches"], 3)
        self.assertEqual(token_usage["anthropic_material_requirements"]["input_tokens"], 7)

    def test_notable_products_tracks_its_own_usage_key(self):
        client = FakeSearchClient({"products": []})
        token_usage = {}
        generate_notable_products(self._config(), model_client=client, token_usage=token_usage)
        self.assertIn("anthropic_notable_products", token_usage)

    def test_regulatory_watch_tracks_its_own_usage_key(self):
        client = FakeSearchClient({"regulations": []})
        token_usage = {}
        generate_regulatory_watch(self._config(), model_client=client, token_usage=token_usage)
        self.assertIn("anthropic_regulatory_watch", token_usage)

    def test_sections_swallow_client_errors(self):
        """Failure isolation: one section's outage must never break the weekly run."""

        class Boom:
            def search_json(self, **kwargs):
                raise RuntimeError("search down")

        self.assertIsNone(generate_material_requirements(self._config(), model_client=Boom()))
        self.assertIsNone(generate_notable_products(self._config(), model_client=Boom()))
        self.assertIsNone(generate_regulatory_watch(self._config(), model_client=Boom()))


class SectionStoreTests(unittest.TestCase):
    def test_upsert_and_latest_round_trip_for_all_three_sections(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "tracker.db"
            with connect(db_path) as db:
                init_db(db)
                upsert_material_requirements(db, week_start="2026-06-22", week_end="2026-06-28",
                                             payload={"materials": [{"application": "PTFE catheter liner"}]})
                upsert_notable_products(db, week_start="2026-06-22", week_end="2026-06-28",
                                        payload={"products": [{"product": "Raychem ATUM"}]})
                upsert_regulatory_watch(db, week_start="2026-06-22", week_end="2026-06-28",
                                        payload={"regulations": [{"regulation": "UL 224"}]})
                mats = latest_material_requirements(db)
                products = latest_notable_products(db)
                regulations = latest_regulatory_watch(db)

        self.assertEqual(mats["week_start"], "2026-06-22")
        self.assertEqual(mats["payload"]["materials"][0]["application"], "PTFE catheter liner")
        self.assertEqual(products["payload"]["products"][0]["product"], "Raychem ATUM")
        self.assertEqual(regulations["payload"]["regulations"][0]["regulation"], "UL 224")

    def test_upsert_replaces_the_same_week(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "tracker.db"
            with connect(db_path) as db:
                init_db(db)
                upsert_notable_products(db, week_start="2026-06-22", week_end="2026-06-28",
                                        payload={"products": [{"product": "first"}]})
                upsert_notable_products(db, week_start="2026-06-22", week_end="2026-06-28",
                                        payload={"products": [{"product": "second"}]})
                products = latest_notable_products(db)
                rows = db.execute("SELECT COUNT(*) FROM notable_products").fetchone()[0]

        self.assertEqual(rows, 1)
        self.assertEqual(products["payload"]["products"][0]["product"], "second")

    def test_all_sections_return_every_week_newest_first(self):
        """The section pages are cumulative, so the store must hand back the whole history."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "tracker.db"
            with connect(db_path) as db:
                init_db(db)
                for week_start, week_end in (("2026-06-22", "2026-06-28"), ("2026-06-29", "2026-07-05")):
                    upsert_material_requirements(db, week_start=week_start, week_end=week_end,
                                                 payload={"materials": [{"application": week_start}]})
                    upsert_notable_products(db, week_start=week_start, week_end=week_end,
                                            payload={"products": [{"product": week_start}]})
                    upsert_regulatory_watch(db, week_start=week_start, week_end=week_end,
                                            payload={"regulations": [{"regulation": week_start}]})
                mats = all_material_requirements(db)
                products = all_notable_products(db)
                regulations = all_regulatory_watch(db)

        for sections in (mats, products, regulations):
            self.assertEqual([s["week_start"] for s in sections], ["2026-06-29", "2026-06-22"])
        self.assertEqual(mats[1]["payload"]["materials"][0]["application"], "2026-06-22")

    def test_all_sections_are_empty_before_any_run(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "tracker.db"
            with connect(db_path) as db:
                init_db(db)
                self.assertEqual(all_material_requirements(db), [])


class SectionPageRenderTests(unittest.TestCase):
    def test_render_materials_table(self):
        section = {"week_start": "2026-06-22", "week_end": "2026-06-28",
                   "payload": {"materials": [{"application": "Dual-wall harness seal",
                                              "material_class": "e-beam irradiated polyolefin",
                                              "key_properties": "3:1 shrink, 125 C continuous",
                                              "open_challenge": "PFAS-free adhesive liner",
                                              "source_url": "https://x/1"}]}}
        html = site_build.render_materials(SITE_CONFIG, section)
        self.assertIn("Materials", html)
        self.assertIn("Dual-wall harness seal", html)
        self.assertIn("PFAS-free adhesive liner", html)
        self.assertIn("https://x/1", html)
        self.assertIn("2026-06-22", html)

    def test_render_products_table(self):
        section = {"week_start": "2026-06-22", "week_end": "2026-06-28",
                   "payload": {"products": [{"product": "ATUM-X", "manufacturer": "TE Connectivity",
                                             "material_construction": "dual-wall polyolefin, 4:1",
                                             "application": "EV busbar insulation",
                                             "announced": "2026-06-24", "source_url": "https://x/2"}]}}
        html = site_build.render_products(SITE_CONFIG, section)
        self.assertIn("Notable Products", html)
        self.assertIn("ATUM-X", html)
        self.assertIn("TE Connectivity", html)
        self.assertIn("EV busbar insulation", html)
        self.assertIn("https://x/2", html)

    def test_render_regulatory_table(self):
        section = {"week_start": "2026-06-22", "week_end": "2026-06-28",
                   "payload": {"regulations": [{"regulation": "UL 224 Ed. 6", "body": "UL",
                                                "change": "New flame test method",
                                                "status_effective_date": "Effective 2027-01-01",
                                                "hst_impact": "Requalification of all listed tubing",
                                                "source_url": "https://x/3"}]}}
        html = site_build.render_regulatory(SITE_CONFIG, section)
        self.assertIn("Regulatory Watch", html)
        self.assertIn("UL 224 Ed. 6", html)
        self.assertIn("Requalification of all listed tubing", html)
        self.assertIn("https://x/3", html)

    def test_all_three_pages_render_an_empty_state(self):
        for render in (site_build.render_materials, site_build.render_products, site_build.render_regulatory):
            with self.subTest(render=render.__name__):
                html = render(SITE_CONFIG, None)
                self.assertIn("compiled yet", html)

    def test_pages_render_every_week_of_history(self):
        sections = [
            {"week_start": "2026-06-29", "week_end": "2026-07-05",
             "payload": {"products": [{"product": "ATUM-X", "manufacturer": "TE Connectivity"}]}},
            {"week_start": "2026-06-22", "week_end": "2026-06-28",
             "payload": {"products": [{"product": "Versafit V4", "manufacturer": "TE Connectivity"}]}},
        ]
        html = site_build.render_products(SITE_CONFIG, sections)
        self.assertIn("ATUM-X", html)
        self.assertIn("Versafit V4", html)  # last week's row is still on the page
        self.assertIn('data-weeks="2026-06-22"', html)
        self.assertIn("2 weekly compilations", html)

    def test_a_subject_repeated_across_weeks_is_kept_once_at_its_newest_week(self):
        sections = [
            {"week_start": "2026-06-29", "week_end": "2026-07-05",
             "payload": {"regulations": [{"regulation": "UL 224", "change": "new wording"}]}},
            {"week_start": "2026-06-22", "week_end": "2026-06-28",
             "payload": {"regulations": [{"regulation": "UL 224", "change": "old wording"}]}},
        ]
        html = site_build.render_regulatory(SITE_CONFIG, sections)
        self.assertEqual(html.count("UL 224"), 1)
        self.assertIn("new wording", html)
        self.assertNotIn("old wording", html)
        # one row spanning both weeks, not one row per week
        self.assertIn('data-weeks="2026-06-22 2026-06-29"', html)

    def test_a_reworded_subject_still_collapses_to_one_row(self):
        """The model rewords the same subject every week; matching text would miss it."""
        sections = [
            {"week_start": "2026-06-29", "week_end": "2026-07-05",
             "payload": {"regulations": [{"regulation": "IEC 60684-2:2025 (4th edition)",
                                          "body": "IEC", "change": "NEWEST-WORDING"}]}},
            {"week_start": "2026-06-22", "week_end": "2026-06-28",
             "payload": {"regulations": [{"regulation": "IEC 60684-2 Ed. 4",
                                          "body": "IEC", "change": "PRIOR-WORDING"}]}},
        ]
        html = site_build.render_regulatory(SITE_CONFIG, sections)
        self.assertIn("NEWEST-WORDING", html)
        self.assertNotIn("PRIOR-WORDING", html)

    def test_distinct_subjects_sharing_a_prefix_are_not_merged(self):
        """AS23053C and AS23053/12B are different specs and must stay separate."""
        sections = [{"week_start": "2026-06-22", "week_end": "2026-06-28",
                     "payload": {"regulations": [
                         {"regulation": "SAE AS23053C", "body": "SAE", "change": "one"},
                         {"regulation": "SAE AS23053/12B", "body": "SAE", "change": "two"},
                     ]}}]
        html = site_build.render_regulatory(SITE_CONFIG, sections)
        self.assertIn("one", html)
        self.assertIn("two", html)

    def test_a_product_keeps_its_identity_when_the_manufacturer_drifts(self):
        """HS-101 is filed under "Insultab (Pexco)" one week and "Pexco" the next."""
        sections = [
            {"week_start": "2026-06-29", "week_end": "2026-07-05",
             "payload": {"products": [{"product": "HS-101 Polyolefin Heat Shrink Tubing",
                                       "manufacturer": "Insultab (Pexco)", "announced": "NEWEST-WORDING"}]}},
            {"week_start": "2026-06-22", "week_end": "2026-06-28",
             "payload": {"products": [{"product": "HS-101 Polyolefin Heat Shrink Tubing",
                                       "manufacturer": "Pexco", "announced": "PRIOR-WORDING"}]}},
        ]
        html = site_build.render_products(SITE_CONFIG, sections)
        self.assertIn("NEWEST-WORDING", html)
        self.assertNotIn("PRIOR-WORDING", html)

    def test_different_polymers_are_never_merged(self):
        """Similarity scoring collapses PVDF into PTFE; identity keys must not."""
        sections = [{"week_start": "2026-06-22", "week_end": "2026-06-28",
                     "payload": {"materials": [
                         {"application": "PVDF high-temperature aerospace sleeve",
                          "material_class": "irradiated PVDF", "open_challenge": "pvdf-row"},
                         {"application": "PTFE high-temperature chemical-resistant sleeve",
                          "material_class": "expanded PTFE", "open_challenge": "ptfe-row"},
                     ]}}]
        html = site_build.render_materials(SITE_CONFIG, sections)
        self.assertIn("pvdf-row", html)
        self.assertIn("ptfe-row", html)

    def test_a_single_section_still_renders(self):
        """build_site passes a list; the renderers also accept one section (or None)."""
        section = {"week_start": "2026-06-22", "week_end": "2026-06-28",
                   "payload": {"materials": [{"application": "PTFE catheter liner"}]}}
        html = site_build.render_materials(SITE_CONFIG, section)
        self.assertIn("PTFE catheter liner", html)
        self.assertIn("1 weekly compilation", html)

    def test_nav_carries_all_three_section_pages(self):
        hrefs = [href for href, _ in site_build.NAV]
        self.assertIn("materials.html", hrefs)
        self.assertIn("products.html", hrefs)
        self.assertIn("regulatory.html", hrefs)


if __name__ == "__main__":
    unittest.main()
