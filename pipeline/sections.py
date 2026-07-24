from __future__ import annotations

from datetime import date
from typing import Any

from pipeline.model_clients import add_token_usage, build_anthropic_client, read_prompt


def generate_material_requirements(
    config: dict[str, Any],
    *,
    model_client: Any | None = None,
    token_usage: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Materials section: map tubing family / end use -> base polymer + crosslinking route ->
    numeric property targets -> open challenge, via the web_search tool. Returns None when
    disabled or no API key is available (offline dry-runs skip the section rather than failing
    the run)."""
    return _generate_section(
        config,
        section_key="material_requirements",
        usage_name="anthropic_material_requirements",
        model_client=model_client,
        token_usage=token_usage,
    )


def generate_notable_products(
    config: dict[str, Any],
    *,
    model_client: Any | None = None,
    token_usage: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Notable Products section: real heat shrink tubing launches from the vendor landscape,
    via the web_search tool. Returns None when disabled or no API key is available."""
    return _generate_section(
        config,
        section_key="notable_products",
        usage_name="anthropic_notable_products",
        model_client=model_client,
        token_usage=token_usage,
    )


def generate_regulatory_watch(
    config: dict[str, Any],
    *,
    model_client: Any | None = None,
    token_usage: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Regulatory Watch section: standards and regulatory movement (UL, MIL, IEC, SAE, ISO,
    EPA/ECHA PFAS, RoHS, FDA) and what each changes for a tubing manufacturer, via the
    web_search tool. These bodies publish no reliable RSS, so this section is the only path by
    which their activity reaches the site. Returns None when disabled or no API key."""
    return _generate_section(
        config,
        section_key="regulatory_watch",
        usage_name="anthropic_regulatory_watch",
        model_client=model_client,
        token_usage=token_usage,
    )


def _generate_section(
    config: dict[str, Any],
    *,
    section_key: str,
    usage_name: str,
    model_client: Any | None,
    token_usage: dict[str, Any] | None,
) -> dict[str, Any] | None:
    section = config.get("sections", {}).get(section_key, {})
    if not section.get("enabled"):
        return None

    client = model_client if model_client is not None else build_anthropic_client()
    if client is None:
        return None  # no API key / SDK — skip the section offline, don't crash the run

    prompt = read_prompt(section["prompt"])
    try:
        result, usage = client.search_json(
            model=section["model"],
            system_prompt=prompt,
            user_prompt=_user_prompt(config),
            max_searches=int(section.get("max_searches", 6)),
        )
    except Exception:
        return None  # a section outage must never break the weekly run
    add_token_usage(token_usage, usage_name, usage)
    return result


def _user_prompt(config: dict[str, Any]) -> str:
    site = config.get("site", {})
    return (
        f"Today is {date.today().isoformat()}. Audience: {site.get('tagline', 'materials scientists and engineers')}. "
        "Use web search to gather current information, then return the JSON object described in the system prompt. "
        "Return JSON only — no preamble, no markdown."
    )
