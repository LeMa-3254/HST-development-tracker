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

    def test_nav_carries_all_three_section_pages(self):
        hrefs = [href for href, _ in site_build.NAV]
        self.assertIn("materials.html", hrefs)
        self.assertIn("products.html", hrefs)
        self.assertIn("regulatory.html", hrefs)


if __name__ == "__main__":
    unittest.main()
