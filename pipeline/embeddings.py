from __future__ import annotations

from typing import Any

from models import Item
from pipeline.model_clients import add_token_usage, build_embedding_client


def embed_items(
    items: list[Item],
    config: dict[str, Any],
    *,
    embedding_client: Any | None = None,
    token_usage: dict[str, Any] | None = None,
    batch_size: int = 128,
) -> list[Item]:
    pending = [item for item in items if item.status == "included" and item.embedding is None]
    if not pending:
        return items

    client = embedding_client if embedding_client is not None else build_embedding_client(config)
    if client is None:
        return items

    model = config.get("dedup", {}).get("embedding_model", "voyage-3")
    for start in range(0, len(pending), batch_size):
        batch = pending[start:start + batch_size]
        texts = [embedding_text(item) for item in batch]
        try:
            embeddings, usage = client.embed(texts, model=model, input_type="document")
        except Exception:
            continue
        add_token_usage(token_usage, "voyage_embeddings", usage)
        for item, embedding in zip(batch, embeddings):
            item.embedding = embedding
    return items


def embedding_text(item: Item) -> str:
    parts = [
        item.title,
        item.abstract or "",
        item.summary or "",
        item.why_it_matters or "",
    ]
    return "\n".join(part for part in parts if part).strip()
