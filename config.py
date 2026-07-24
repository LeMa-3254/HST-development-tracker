from __future__ import annotations

from pathlib import Path
from typing import Any


def load_config(path: str | Path = "targeting.yaml") -> dict[str, Any]:
    try:
        import yaml
    except ModuleNotFoundError as exc:
        raise RuntimeError(
            "PyYAML is required to load targeting.yaml. Install dependencies with "
            "`python3 -m pip install -r requirements.txt`."
        ) from exc

    with Path(path).open("r", encoding="utf-8") as handle:
        data = yaml.safe_load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"{path} must contain a YAML mapping at the top level")
    return data


def enabled_sources(config: dict[str, Any]) -> list[str]:
    sources = config.get("sources", {})
    return [
        name
        for name, source_config in sources.items()
        if isinstance(source_config, dict) and source_config.get("enabled") is True
    ]

