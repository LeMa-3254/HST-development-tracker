from __future__ import annotations

import math
from typing import Any, Iterable

from models import Item


def cosine_similarity(left: Iterable[float], right: Iterable[float]) -> float:
    left_values = list(left)
    right_values = list(right)
    if len(left_values) != len(right_values) or not left_values:
        return 0.0
    dot = sum(a * b for a, b in zip(left_values, right_values))
    left_norm = math.sqrt(sum(a * a for a in left_values))
    right_norm = math.sqrt(sum(b * b for b in right_values))
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return dot / (left_norm * right_norm)


def deduplicate_items(
    items: list[Item],
    memory: list[dict[str, Any]],
    config: dict[str, Any],
) -> list[Item]:
    dedup_config = config.get("dedup", {})
    threshold = float(dedup_config.get("similarity_threshold", 0.85))
    on_duplicate = dedup_config.get("on_duplicate", "drop")
    seen = [
        {"id": row["id"], "embedding": row["embedding"]}
        for row in memory
        if row.get("id") and row.get("embedding")
    ]

    for item in items:
        if item.status != "included" or not item.embedding:
            continue

        # Never let an item collide with its OWN prior embedding: the same story is re-fetched
        # every run while it's inside the lookback window, and its id is still in the 30-day memory.
        # Comparing it to itself (cosine ~1.0) would demote an already-included item to a duplicate.
        candidates = [row for row in seen if row["id"] != item.id]
        duplicate_id = find_duplicate_id(item.embedding, candidates, threshold)
        if duplicate_id:
            item.dup_of = duplicate_id
            if on_duplicate == "tag_as_update":
                item.status = "included"
            else:
                item.status = "dropped_dup"
            continue

        seen.append({"id": item.id, "embedding": item.embedding})

    return items


def find_duplicate_id(
    embedding: Iterable[float],
    memory: list[dict[str, Any]],
    threshold: float,
) -> str | None:
    best_id: str | None = None
    best_score = threshold
    for row in memory:
        score = cosine_similarity(embedding, row["embedding"])
        if score >= best_score:
            best_id = row["id"]
            best_score = score
    return best_id
