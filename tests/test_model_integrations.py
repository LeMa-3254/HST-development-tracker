import unittest

from models import Item
from pipeline.embeddings import embed_items
from pipeline.enrich import enrich_items
from pipeline.model_clients import add_token_usage, parse_json_object, resolve_embedding_provider, strip_code_fence
from pipeline.score import score_item


CONFIG = {
    "targeting": {
        "hst_core_terms": ["heat shrink", "shrink tubing"],
        "adjacent_terms": ["fluoropolymer", "crosslinking"],
        "context_terms": ["wire", "cable"],
        "technical_boost_terms": ["gel fraction"],
    },
    "scoring": {
        "model": "test-scoring-model",
        "rubric_prompt": "prompts/relevance.md",
        "min_score": 70,
    },
    "enrich": {
        "model": "test-enrich-model",
        "prompt": "prompts/enrich.md",
        "max_items_per_run": 10,
    },
    "dedup": {
        "embedding_model": "test-embedding-model",
    },
}


class FakeModelClient:
    def __init__(self, payload):
        self.payload = payload
        self.calls = []

    def complete_json(self, **kwargs):
        self.calls.append(kwargs)
        return self.payload, {"input_tokens": 3, "output_tokens": 2}


class FakeEmbeddingClient:
    def __init__(self):
        self.calls = []

    def embed(self, texts, *, model, input_type):
        self.calls.append({"texts": texts, "model": model, "input_type": input_type})
        return [[1.0, 0.0] for _ in texts], {"total_tokens": 5}


def make_item() -> Item:
    return Item.from_source(
        title="Crosslinking dose control in heat shrink tubing",
        url="https://example.test/item",
        source_type="test",
        source_name="Example",
        tier="A",
        abstract="Gel fraction response to e-beam dose in polyolefin wire insulation.",
    )


class ModelIntegrationTests(unittest.TestCase):
    def test_parse_json_object_accepts_fenced_json(self):
        text = """```json
        {"summary": "A", "why_it_matters": "B"}
        ```"""

        self.assertEqual(
            parse_json_object(text),
            {"summary": "A", "why_it_matters": "B"},
        )
        self.assertEqual(strip_code_fence(text).splitlines()[0].strip(), '{"summary": "A", "why_it_matters": "B"}')

    def test_score_item_uses_injected_model_client_and_tracks_usage(self):
        item = make_item()
        token_usage = {}
        client = FakeModelClient(
            {
                "relevance": 88,
                "quality": 90,
                "reason": "Strong crosslinking/formulation fit.",
                "theme": "Manufacturing & Processing",
            }
        )

        score_item(item, CONFIG, model_client=client, token_usage=token_usage)

        self.assertEqual(item.status, "included")
        self.assertEqual(item.relevance_score, 88)
        self.assertEqual(item.quality_score, 90)
        self.assertEqual(item.theme, "Manufacturing & Processing")
        self.assertEqual(token_usage["anthropic_scoring"]["input_tokens"], 3)

    def test_enrich_items_uses_injected_model_client_and_tracks_usage(self):
        item = make_item()
        item.status = "included"
        item.relevance_score = 4
        token_usage = {}
        client = FakeModelClient(
            {
                "summary": "A concise model-written summary.",
                "why_it_matters": "It changes the dose window for irradiated polyolefin.",
            }
        )

        enrich_items([item], CONFIG, model_client=client, token_usage=token_usage)

        self.assertEqual(item.summary, "A concise model-written summary.")
        self.assertEqual(item.why_it_matters, "It changes the dose window for irradiated polyolefin.")
        self.assertEqual(token_usage["anthropic_enrichment"]["output_tokens"], 2)

    def test_enrich_items_bootstraps_items_beyond_model_limit(self):
        config = dict(CONFIG)
        config["enrich"] = dict(CONFIG["enrich"], max_items_per_run=1)
        first = make_item()
        first.status = "included"
        first.relevance_score = 5
        second = make_item()
        second.id = "second"
        second.url = "https://example.test/second"
        second.status = "included"
        second.relevance_score = 4
        client = FakeModelClient(
            {
                "summary": "Model summary.",
                "why_it_matters": "Model why.",
            }
        )

        enriched = enrich_items([first, second], config, model_client=client)

        self.assertEqual(len(enriched), 2)
        self.assertEqual(first.summary, "Model summary.")
        self.assertEqual(second.summary, second.abstract)
        self.assertEqual(second.why_it_matters, "Potentially relevant to heat shrink tubing materials, processing, or qualification.")

    def test_embed_items_uses_injected_embedding_client_and_tracks_usage(self):
        item = make_item()
        item.status = "included"
        token_usage = {}
        client = FakeEmbeddingClient()

        embed_items([item], CONFIG, embedding_client=client, token_usage=token_usage)

        self.assertEqual(item.embedding, [1.0, 0.0])
        self.assertEqual(client.calls[0]["model"], "test-embedding-model")
        self.assertEqual(client.calls[0]["input_type"], "document")
        self.assertEqual(token_usage["voyage_embeddings"]["total_tokens"], 5)

    def test_resolve_embedding_provider_infers_and_honors_override(self):
        # inferred from the model name
        self.assertEqual(resolve_embedding_provider({"dedup": {"embedding_model": "voyage-3"}}), "voyage")
        self.assertEqual(
            resolve_embedding_provider({"dedup": {"embedding_model": "sentence-transformers/all-MiniLM-L6-v2"}}),
            "local",
        )
        # explicit provider wins over the name
        self.assertEqual(
            resolve_embedding_provider({"dedup": {"embedding_provider": "voyage", "embedding_model": "bge-small"}}),
            "voyage",
        )
        self.assertEqual(
            resolve_embedding_provider({"dedup": {"embedding_provider": "local", "embedding_model": "voyage-3"}}),
            "local",
        )
        # default (no dedup config) is local
        self.assertEqual(resolve_embedding_provider({}), "local")

    def test_bootstrap_scores_curated_industry_above_academic(self):
        from pipeline.score import bootstrap_score_item

        def make(source_type, tier, title):
            return Item.from_source(
                title=title, url=f"https://x/{source_type}", source_type=source_type,
                source_name="E", tier=tier, abstract="heat shrink tubing on wire",
            )

        # The paper carries a technical boost term; the vendor item does not. Industry still wins.
        paper = bootstrap_score_item(make("crossref", "B", "Heat shrink gel content study"), CONFIG)
        vendor = bootstrap_score_item(make("company_news", "A", "Heat shrink tubing launched"), CONFIG)
        trade = bootstrap_score_item(make("web_news", "A", "Heat shrink line commissioned"), CONFIG)

        self.assertGreater(vendor.relevance_score, paper.relevance_score)
        self.assertGreater(trade.relevance_score, paper.relevance_score)

    def test_bootstrap_industry_bonus_excludes_the_google_news_firehose(self):
        """google_news is an industry source but unvetted; the bonus must not carry its
        market-forecast listicles past min_score."""
        from pipeline.score import bootstrap_score_item

        item = Item.from_source(
            title="Heat Shrink Tubing Market Size, Share & Forecast 2026-2034",
            url="https://x/gn", source_type="google_news", source_name="Google News", tier="C",
        )
        bootstrap_score_item(item, CONFIG)

        self.assertEqual(item.status, "dropped_lowscore")

    def test_anthropic_usage_records_web_search_requests(self):
        """web_search is billed per request on top of tokens, and lives in a nested object —
        without it the runs table under-reports the three web-search sections."""
        from pipeline.model_clients import anthropic_usage

        class Usage:
            input_tokens = 100
            output_tokens = 20

            class server_tool_use:
                web_search_requests = 7

        recorded = anthropic_usage(type("M", (), {"usage": Usage})())

        self.assertEqual(recorded["input_tokens"], 100)
        self.assertEqual(recorded["web_search_requests"], 7)

    def test_anthropic_usage_omits_web_search_when_absent(self):
        from pipeline.model_clients import anthropic_usage

        class Usage:
            input_tokens = 100
            output_tokens = 20

        recorded = anthropic_usage(type("M", (), {"usage": Usage})())

        self.assertNotIn("web_search_requests", recorded)

    def test_add_token_usage_accumulates_numeric_fields(self):
        usage = {}

        add_token_usage(usage, "anthropic_scoring", {"input_tokens": 2, "ignored": "x"})
        add_token_usage(usage, "anthropic_scoring", {"input_tokens": 3})

        self.assertEqual(usage, {"anthropic_scoring": {"input_tokens": 5}})


if __name__ == "__main__":
    unittest.main()
