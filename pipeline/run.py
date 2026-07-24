from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from config import load_config
from models import Item
from pipeline.dedup import deduplicate_items
from pipeline.embeddings import embed_items
from pipeline.enrich import enrich_items
from pipeline.ingest import ingest_enabled_sources
from pipeline.score import score_item
from pipeline.sections import (
    generate_material_requirements,
    generate_notable_products,
    generate_regulatory_watch,
)
from pipeline.synth import last_complete_week_bounds, synthesis_bounds, synthesize_week
from sources.base import vocabulary_match
from store.db import (
    connect,
    included_items_between,
    init_db,
    log_run,
    recent_embedding_memory,
    upsert_items,
    upsert_material_requirements,
    upsert_notable_products,
    upsert_regulatory_watch,
    upsert_weekly_summary,
)


def run_pipeline(
    config_path: str = "targeting.yaml",
    db_path: str = "data/tracker.db",
    *,
    weekly_synthesis: bool = False,
) -> int:
    config = load_config(config_path)
    token_usage: dict = {}
    items, errors = ingest_enabled_sources(config)
    candidates = prefilter_candidates(items, config)
    scored = [score_item(item, config, token_usage=token_usage) for item in candidates]
    embed_items(scored, config, token_usage=token_usage)

    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    with connect(db_path) as db:
        init_db(db)
        memory = recent_embedding_memory(
            db,
            window_days=int(config.get("dedup", {}).get("window_days", 30)),
        )
        deduped = deduplicate_items(scored, memory, config)
        included = [item for item in deduped if item.status == "included"]
        enriched = enrich_items(included, config, token_usage=token_usage)
        upsert_items(db, deduped)
        if weekly_synthesis:
            week_start, week_end = last_complete_week_bounds()
            # The synthesis may cover a wider range than the section tables (synth.lookback_days),
            # because this domain is too low-volume for a strict 7-day window to be worth reading.
            synth_start, synth_end = synthesis_bounds(config)
            weekly_items = included_items_between(db, start_date=synth_start, end_date=synth_end)
            synthesis_md = synthesize_week(weekly_items, config, token_usage=token_usage)
            upsert_weekly_summary(
                db,
                week_start=synth_start,
                week_end=synth_end,
                synthesis_md=synthesis_md,
                item_ids=[item["id"] for item in weekly_items],
            )
            # Three extra sections unique to this tracker (Materials, Notable Products,
            # Regulatory Watch). These use the Anthropic web_search tool, not the RSS feed path;
            # each generator returns None on disable/no-key/exception so a section outage never
            # breaks the weekly run. All three are stored and rendered as site pages.
            materials = generate_material_requirements(config, token_usage=token_usage)
            if materials is not None:
                upsert_material_requirements(db, week_start=week_start, week_end=week_end, payload=materials)
            products = generate_notable_products(config, token_usage=token_usage)
            if products is not None:
                upsert_notable_products(db, week_start=week_start, week_end=week_end, payload=products)
            regulations = generate_regulatory_watch(config, token_usage=token_usage)
            if regulations is not None:
                upsert_regulatory_watch(db, week_start=week_start, week_end=week_end, payload=regulations)
        log_run(
            db,
            counts={
                "fetched": len(items),
                "candidates": len(candidates),
                "scored": len(scored),
                "included": len(enriched),
                "duplicates": sum(1 for item in deduped if item.status == "dropped_dup"),
                "errors": len(errors),
            },
            errors=errors,
            token_usage=token_usage,
        )
    return 0


def is_fresh(item: Item, config: dict) -> bool:
    """Hard freshness ceiling: drop items older than meta.max_age_days. RSS sources carry no
    date filter of their own, so this is what keeps stale feed entries out. Undated items pass
    (they were just fetched and have no publication date to judge).

    A source may override the ceiling with its own `max_age_days`. Manufacturer newsrooms need
    this: they post every few months, not daily, so the global 30-day window drops a genuine
    product announcement simply for being five weeks old."""
    from datetime import date, datetime, timezone

    max_age = int(max_age_days_for(item, config) or 0)
    if max_age <= 0 or not item.published_date:
        return True
    try:
        age_days = (datetime.now(timezone.utc).date() - date.fromisoformat(item.published_date)).days
    except ValueError:
        return True
    return age_days <= max_age


def max_age_days_for(item: Item, config: dict) -> int:
    """Per-source freshness ceiling, falling back to meta.max_age_days."""
    source = config.get("sources", {}).get(item.source_type)
    if isinstance(source, dict) and source.get("max_age_days") is not None:
        return int(source["max_age_days"])
    return int(config.get("meta", {}).get("max_age_days", 0) or 0)


# Heat shrink tubing advances in industry first — manufacturers and trade press carry new
# tubing families, ratings and reformulations long before journals do. When the max_candidates
# cap bites it must drop academic long-tail, not product news, so industry sources sort first.
INDUSTRY_SOURCE_TYPES = frozenset({"company_news", "web_news", "google_news", "org_blogs"})


def prefilter_candidates(items: list[Item], config: dict) -> list[Item]:
    """Drop stale and off-vocabulary items, then keep the most promising N before any LLM
    scoring — fewer model calls, faster runs, tighter scope.

    Ranked industry-first, then technically substantive, then most recent."""
    fresh = [item for item in items if is_fresh(item, config)]
    gated = [item for item in fresh if vocabulary_match(item, config)]
    boost_terms = [term.lower() for term in config.get("targeting", {}).get("technical_boost_terms", [])]

    def is_technical(item: Item) -> bool:
        text = f"{item.title} {item.abstract or ''}".lower()
        return any(term in text for term in boost_terms)

    gated.sort(
        key=lambda it: (
            0 if it.source_type in INDUSTRY_SOURCE_TYPES else 1,   # industry before academic
            0 if is_technical(it) else 1,                          # substance before thin coverage
            -_date_rank(it),                                       # then most recent
        )
    )
    cap = int(config.get("scoring", {}).get("max_candidates", 0) or 0)
    return gated[:cap] if cap else gated


def _date_rank(item: Item) -> int:
    """ISO date as a sortable int (2026-07-24 -> 20260724), 0 when absent. Negated by the
    caller so newer sorts first; undated items fall to the back of their group."""
    value = (item.published_date or item.fetched_date or "").replace("-", "")[:8]
    return int(value) if value.isdigit() else 0


def item_from_row(row) -> Item:
    return Item(
        id=row["id"],
        title=row["title"],
        url=row["url"],
        source_type=row["source_type"],
        source_name=row["source_name"],
        tier=row["tier"],
        authors=json.loads(row["authors"]) if row["authors"] else [],
        published_date=row["published_date"],
        fetched_date=row["fetched_date"],
        abstract=row["abstract"],
        doi=row["doi"],
        embedding=json.loads(row["embedding"]) if row["embedding"] else None,
        relevance_score=row["relevance_score"],
        quality_score=row["quality_score"],
        score_reason=row["score_reason"],
        theme=row["theme"],
        summary=row["summary"],
        why_it_matters=row["why_it_matters"],
        digest_date=row["digest_date"],
        status=row["status"],
        dup_of=row["dup_of"],
    )


def rescore_archive(
    config_path: str = "targeting.yaml",
    db_path: str = "data/tracker.db",
    *,
    weekly_synthesis: bool = True,
) -> int:
    """One-time maintenance: re-score every stored item against the current rubric.

    Drops items that no longer pass and reassigns the theme, so a targeting change applies
    to the whole archive (not just newly fetched items). Preserves existing summaries,
    why-it-matters text, and embeddings."""
    config = load_config(config_path)
    token_usage: dict = {}
    with connect(db_path) as db:
        init_db(db)
        rows = list(db.execute("SELECT * FROM items"))
        before = sum(1 for row in rows if row["status"] == "included")
        rescored = [score_item(item_from_row(row), config, token_usage=token_usage) for row in rows]
        upsert_items(db, rescored)
        after = sum(1 for item in rescored if item.status == "included")
        if weekly_synthesis:
            week_start, week_end = synthesis_bounds(config)
            weekly_items = included_items_between(db, start_date=week_start, end_date=week_end)
            synthesis_md = synthesize_week(weekly_items, config, token_usage=token_usage)
            upsert_weekly_summary(
                db,
                week_start=week_start,
                week_end=week_end,
                synthesis_md=synthesis_md,
                item_ids=[item["id"] for item in weekly_items],
            )
        log_run(
            db,
            counts={"rescored": len(rows), "included_before": before, "included_after": after},
            token_usage=token_usage,
        )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the HST Intelligence tracker pipeline")
    parser.add_argument("--config", default="targeting.yaml")
    parser.add_argument("--db", default="data/tracker.db")
    parser.add_argument("--weekly-synthesis", action="store_true")
    parser.add_argument("--rescore-all", action="store_true", help="Re-score the whole archive against the current rubric")
    args = parser.parse_args()
    if args.rescore_all:
        return rescore_archive(config_path=args.config, db_path=args.db)
    return run_pipeline(config_path=args.config, db_path=args.db, weekly_synthesis=args.weekly_synthesis)


if __name__ == "__main__":
    raise SystemExit(main())
