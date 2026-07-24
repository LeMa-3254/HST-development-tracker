from __future__ import annotations

import json
from typing import Any

from models import Item
from pipeline.model_clients import add_token_usage, build_anthropic_client, read_prompt
from sources.base import vocabulary_match


def score_item(
    item: Item,
    config: dict[str, Any],
    *,
    model_client: Any | None = None,
    token_usage: dict[str, Any] | None = None,
) -> Item:
    client = model_client if model_client is not None else build_anthropic_client()
    if client is not None:
        try:
            return score_item_with_model(item, config, client=client, token_usage=token_usage)
        except Exception as exc:
            bootstrap_score_item(item, config)
            item.score_reason = f"Model scoring failed; bootstrap fallback used: {exc}"
            return item
    return bootstrap_score_item(item, config)


def score_item_with_model(
    item: Item,
    config: dict[str, Any],
    *,
    client: Any,
    token_usage: dict[str, Any] | None = None,
) -> Item:
    scoring = config.get("scoring", {})
    prompt = read_prompt(scoring.get("rubric_prompt", "prompts/relevance.md"))
    result, usage = client.complete_json(
        model=scoring["model"],
        system_prompt=prompt,
        user_prompt=json.dumps(item_payload(item), indent=2, sort_keys=True),
        max_tokens=512,
    )
    add_token_usage(token_usage, "anthropic_scoring", usage)
    apply_score_result(item, config, result)
    return item


TIER_POINTS = {"A": 15, "B": 8, "C": 0, "D": -15}

# Industry sources that are *curated* feeds — manufacturer newsrooms and named trade titles.
# Deliberately excludes google_news: it is an industry source too, but an unvetted firehose
# whose market-forecast listicles would ride this bonus straight past min_score.
CURATED_INDUSTRY_SOURCE_TYPES = frozenset({"company_news", "web_news", "org_blogs"})
INDUSTRY_POINTS = 10


def bootstrap_score_item(item: Item, config: dict[str, Any]) -> Item:
    """Keyword/tier heuristic on the 0–100 scale, used only when no model is available.

    Carries the same industry-over-academia weighting as prompts/relevance.md, so an offline
    dry-run ranks the way a keyed run will. Without it the characterization boost terms (DSC,
    dielectric, tensile…) hand journal abstracts a permanent edge, since that is the vocabulary
    papers are written in."""
    scoring = config.get("scoring", {})
    text = f"{item.title} {item.abstract or ''}".lower()
    boost_terms = [term.lower() for term in config.get("targeting", {}).get("technical_boost_terms", [])]
    base = 60 if vocabulary_match(item, config) else 25
    boost = 15 if any(term in text for term in boost_terms) else 0
    tier = TIER_POINTS.get(item.tier, 0)
    industry = INDUSTRY_POINTS if item.source_type in CURATED_INDUSTRY_SOURCE_TYPES else 0

    item.relevance_score = float(max(0, min(100, base + boost + tier + industry)))
    item.quality_score = float(max(0, min(100, 55 + tier)))
    item.score_reason = "Keyword/tier bootstrap score (0–100); replace with configured model scoring."
    item.theme = infer_theme(item)
    item.status = "included" if item.relevance_score >= scoring.get("min_score", 70) else "dropped_lowscore"
    return item


def apply_score_result(item: Item, config: dict[str, Any], result: dict[str, Any]) -> None:
    # Trust the model's rubric judgment directly (0–100); no tier/polymer priors are added here,
    # so a "not really polymer" verdict cannot be inflated past the threshold.
    scoring = config.get("scoring", {})
    item.relevance_score = clamp_score(result.get("relevance"))
    item.quality_score = clamp_score(result.get("quality"))
    item.score_reason = str(result.get("reason") or "Model scored relevance and quality.")
    item.theme = str(result.get("theme") or infer_theme(item))
    item.status = "included" if item.relevance_score >= scoring.get("min_score", 70) else "dropped_lowscore"


def clamp_score(value: Any) -> float:
    try:
        score = float(value)
    except (TypeError, ValueError):
        score = 0.0
    return max(0.0, min(100.0, score))


def item_payload(item: Item) -> dict[str, Any]:
    return {
        "title": item.title,
        "url": item.url,
        "source_type": item.source_type,
        "source_name": item.source_name,
        "tier": item.tier,
        "authors": item.authors,
        "published_date": item.published_date,
        "abstract": item.abstract,
        "doi": item.doi,
    }


ACADEMIC_SOURCE_TYPES = ("arxiv", "openalex", "crossref", "journal_rss")


def infer_theme(item: Item) -> str:
    """Map to the fixed theme taxonomy (mirrors targeting.themes / the relevance rubric).

    Bootstrap fallback only — used when no API key is available, so the model's own `theme`
    never reaches this. Ordered most-specific-first: a regulatory or characterization signal is
    more informative than the generic polymer vocabulary that co-occurs with it."""
    text = f"{item.title} {item.abstract or ''}".lower()
    if any(term in text for term in ("ul 224", "mil-i-23053", "mil-dtl-23053", "iec 60684", "sae as23053",
                                     "iso 6722", "astm d2671", "reach", "rohs", "weee", "echa", "epa ",
                                     "fda ", "restriction", "compliance", "standard revision", "regulation")):
        return "Standards & Regulatory"
    if any(term in text for term in ("dsc", "tga", "ftir", "dynamic mechanical", "differential scanning",
                                     "thermogravimetric", "gel fraction", "gel content", "accelerated aging",
                                     "thermal aging", "dielectric strength", "tensile test", "elongation at break",
                                     "hot set", "failure analysis", "sem", "characteriz")):
        return "Characterization & Testing"
    if any(term in text for term in ("extrusion", "extruded", "crosslink", "cross-link", "e-beam", "electron beam",
                                     "irradiation", "gamma dose", "expansion ratio", "compounding", "line speed",
                                     "manufactur", "processing")):
        return "Manufacturing & Processing"
    if any(term in text for term in ("launch", "unveil", "introduce", "new product", "product line", "now available",
                                     "expands its range", "releases")):
        return "Products & Launches"
    if any(term in text for term in ("pfas", "fluoropolymer", "ptfe", "fep", "pfa", "pvdf", "etfe", "peek",
                                     "polyolefin", "formulation", "flame retardant", "halogen-free", "shape memory",
                                     "adhesive-lined", "additive package", "resin")):
        return "Materials & Formulations"
    if any(term in text for term in ("catheter", "implantable", "aerospace", "defense", "busbar", "bus bar",
                                     "battery pack", "automotive", "electric vehicle", "medical device",
                                     "wire harness", "downhole", "solar", "telecom")):
        return "Applications"
    if any(term in text for term in ("acquisition", "acquires", "merger", "market size", "capacity expansion",
                                     "new plant", "supply chain", "pricing", "distribution agreement",
                                     "investment", "forecast")):
        return "Market & Supply Chain"
    if item.source_type in ACADEMIC_SOURCE_TYPES:
        return "Academic R&D"
    return "Other"
