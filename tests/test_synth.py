from datetime import date
import unittest

from pipeline.synth import (
    fallback_synthesis,
    last_complete_week_bounds,
    synthesis_bounds,
    synthesize_week,
)


class FakeModelClient:
    def complete_json(self, **kwargs):
        return {"synthesis_md": "## Model Synthesis\n\nA short weekly narrative."}, {"input_tokens": 4}


class SynthTests(unittest.TestCase):
    def test_last_complete_week_bounds_is_previous_monday_to_sunday(self):
        # 2026-06-29 is a Monday; the most recent finished week is the prior Mon–Sun.
        self.assertEqual(last_complete_week_bounds(date(2026, 6, 29)), ("2026-06-22", "2026-06-28"))

    def test_synthesis_bounds_default_to_the_strict_week(self):
        self.assertEqual(synthesis_bounds({}, date(2026, 6, 29)), ("2026-06-22", "2026-06-28"))
        self.assertEqual(
            synthesis_bounds({"synth": {"lookback_days": 0}}, date(2026, 6, 29)),
            ("2026-06-22", "2026-06-28"),
        )

    def test_synthesis_lookback_widens_the_start_and_keeps_the_week_end(self):
        """HST is too low-volume for a strict 7-day window — it renders an empty Weekly page."""
        self.assertEqual(
            synthesis_bounds({"synth": {"lookback_days": 30}}, date(2026, 6, 29)),
            ("2026-05-30", "2026-06-28"),
        )

    def test_fallback_synthesis_groups_by_theme(self):
        markdown = fallback_synthesis(
            [
                {"title": "Gel fraction vs. e-beam dose", "theme": "Manufacturing & Processing"},
                {"title": "PFAS-free FEP tubing launch", "theme": "Products & Launches"},
            ]
        )

        self.assertIn("### Products & Launches", markdown)
        self.assertIn("- Gel fraction vs. e-beam dose", markdown)

    def test_synthesize_week_uses_model_client_and_tracks_usage(self):
        token_usage = {}
        markdown = synthesize_week(
            [{"id": "1", "title": "Crosslinked polyolefin study", "theme": "Materials & Formulations"}],
            {"synth": {"model": "test-synth-model", "prompt": "prompts/synth.md"}},
            model_client=FakeModelClient(),
            token_usage=token_usage,
        )

        self.assertIn("Model Synthesis", markdown)
        self.assertEqual(token_usage["anthropic_synthesis"]["input_tokens"], 4)


if __name__ == "__main__":
    unittest.main()
