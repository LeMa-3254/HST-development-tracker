from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
import json
from typing import Any

from pipeline.model_clients import add_token_usage, build_anthropic_client, read_prompt


def last_complete_week_bounds(today: date | None = None) -> tuple[str, str]:
    """The most recent finished Monday–Sunday week. A weekly run on Monday summarizes
    the week that just ended, not the one that is only starting."""
    today = today or date.today()
    this_monday = today - timedelta(days=today.weekday())
    start = this_monday - timedelta(days=7)
    end = this_monday - timedelta(days=1)
    return start.isoformat(), end.isoformat()


def synthesis_bounds(config: dict[str, Any], today: date | None = None) -> tuple[str, str]:
    """The range the weekly synthesis actually covers.

    Defaults to the last complete week. `synth.lookback_days` widens the *start* while keeping
    the same end, because heat shrink tubing is low-volume: a strict 7-day window turned up zero
    included items on the first live run (the two that qualified were dated 2026-07-06 and
    2026-03-04, either side of a 2026-07-13..19 window), which would leave the Weekly page empty
    most weeks. The returned start is also the weekly_summaries primary key, so it still advances
    once per run and the label on the page matches what was actually summarized."""
    week_start, week_end = last_complete_week_bounds(today)
    lookback = int(config.get("synth", {}).get("lookback_days", 0) or 0)
    if lookback <= 0:
        return week_start, week_end
    start = date.fromisoformat(week_end) - timedelta(days=lookback - 1)
    return start.isoformat(), week_end


def synthesize_week(
    items: list[Any],
    config: dict[str, Any],
    *,
    model_client: Any | None = None,
    token_usage: dict[str, Any] | None = None,
) -> str:
    if not items:
        return "No included items for this week yet."

    client = model_client if model_client is not None else build_anthropic_client()
    if client is None:
        return fallback_synthesis(items)

    synth = config.get("synth", {})
    prompt = read_prompt(synth.get("prompt", "prompts/synth.md"))
    try:
        result, usage = client.complete_json(
            model=synth["model"],
            system_prompt=prompt,
            user_prompt=json.dumps([item_payload(item) for item in items], indent=2, sort_keys=True),
            max_tokens=1600,
        )
    except Exception:
        return fallback_synthesis(items)
    add_token_usage(token_usage, "anthropic_synthesis", usage)
    return str(result.get("synthesis_md") or result.get("synthesis") or fallback_synthesis(items))


def fallback_synthesis(items: list[Any]) -> str:
    ranked = sorted(items, key=_rank_key)

    lines: list[str] = ["## This week in brief", ""]
    for item in ranked[:5]:
        detail = str(item_value(item, "why_it_matters") or item_value(item, "summary") or "").strip()
        detail = detail.split("\n")[0]
        lines.append(f"- **{_link(item)}** — {detail}" if detail else f"- **{_link(item)}**")
    lines.append("")

    grouped: dict[str, list[Any]] = defaultdict(list)
    for item in ranked:
        grouped[str(item_value(item, "theme") or "Materials AI")].append(item)

    lines.append("## Trends by theme")
    lines.append("")
    for theme, group in sorted(grouped.items()):
        lines.append(f"### {theme}")
        for item in group[:4]:
            lines.append(f"- {_link(item)}")
        lines.append("")
    return "\n".join(lines).strip()


def _rank_key(item: Any) -> tuple[float, float]:
    return (-_num(item_value(item, "relevance_score")), -_num(item_value(item, "quality_score")))


def _num(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _link(item: Any) -> str:
    title = str(item_value(item, "title") or "Untitled").replace("[", "(").replace("]", ")")
    url = str(item_value(item, "url") or "")
    return f"[{title}]({url})" if url.startswith("http") else title


def item_payload(item: Any) -> dict[str, Any]:
    return {
        "id": item_value(item, "id"),
        "title": item_value(item, "title"),
        "url": item_value(item, "url"),
        "source_name": item_value(item, "source_name"),
        "published_date": item_value(item, "published_date"),
        "theme": item_value(item, "theme"),
        "summary": item_value(item, "summary"),
        "why_it_matters": item_value(item, "why_it_matters"),
    }


def item_value(item: Any, key: str) -> Any:
    if isinstance(item, dict):
        return item.get(key)
    try:
        return item[key]
    except (KeyError, TypeError, IndexError):
        return getattr(item, key, None)
