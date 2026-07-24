from __future__ import annotations

import json
import os
from pathlib import Path
import re
import time
from typing import Any


class ApiUnavailable(RuntimeError):
    pass


def read_prompt(path: str) -> str:
    return Path(path).read_text(encoding="utf-8").strip()


def add_token_usage(bucket: dict[str, Any] | None, name: str, usage: dict[str, Any]) -> None:
    if bucket is None:
        return
    target = bucket.setdefault(name, {})
    for key, value in usage.items():
        if isinstance(value, (int, float)):
            target[key] = target.get(key, 0) + value


def parse_json_object(text: str) -> dict[str, Any]:
    cleaned = strip_code_fence(text.strip())
    decoder = json.JSONDecoder()
    for match in re.finditer(r"\{", cleaned):
        try:
            value, _ = decoder.raw_decode(cleaned[match.start():])
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            return value
    raise ValueError("No JSON object found in model response")


def strip_code_fence(text: str) -> str:
    if not text.startswith("```"):
        return text
    lines = text.splitlines()
    if lines and lines[0].startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].startswith("```"):
        lines = lines[:-1]
    return "\n".join(lines).strip()


def extract_message_text(message: Any) -> str:
    parts: list[str] = []
    for block in getattr(message, "content", []):
        text = getattr(block, "text", None)
        if text is None and isinstance(block, dict):
            text = block.get("text")
        if text:
            parts.append(text)
    return "\n".join(parts).strip()


def anthropic_usage(message: Any) -> dict[str, int]:
    usage = getattr(message, "usage", None)
    if usage is None:
        return {}
    keys = [
        "input_tokens",
        "output_tokens",
        "cache_creation_input_tokens",
        "cache_read_input_tokens",
    ]
    recorded = {
        key: value
        for key in keys
        if isinstance((value := getattr(usage, key, None)), int)
    }
    # Server-side web_search is billed per request on top of tokens, and it sits in a nested
    # object the token keys above miss entirely. Without this the `runs` table under-reports the
    # cost of exactly the three most expensive stages. Note the per-request fee is the smaller
    # half of the bill: each search also feeds its results back as input tokens, which is why
    # raising notable_products to max_searches: 12 took that section from 63k to 155k input.
    searches = getattr(getattr(usage, "server_tool_use", None), "web_search_requests", None)
    if isinstance(searches, int):
        recorded["web_search_requests"] = searches
    return recorded


def retry_call(fn, *, attempts: int = 3, initial_delay: float = 1.0):
    delay = initial_delay
    for attempt in range(attempts):
        try:
            return fn()
        except Exception:
            if attempt == attempts - 1:
                raise
            time.sleep(delay)
            delay *= 2


class AnthropicModelClient:
    def __init__(self, api_key: str | None = None) -> None:
        api_key = api_key or os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            raise ApiUnavailable("ANTHROPIC_API_KEY is not set")
        try:
            from anthropic import Anthropic
        except ImportError as exc:
            raise ApiUnavailable("anthropic package is not installed") from exc
        self.client = Anthropic(api_key=api_key)

    def complete_json(
        self,
        *,
        model: str,
        system_prompt: str,
        user_prompt: str,
        max_tokens: int = 1024,
    ) -> tuple[dict[str, Any], dict[str, int]]:
        message = retry_call(
            lambda: self.client.messages.create(
                model=model,
                max_tokens=max_tokens,
                temperature=0,
                system=system_prompt,
                messages=[{"role": "user", "content": user_prompt}],
            )
        )
        return parse_json_object(extract_message_text(message)), anthropic_usage(message)

    def search_json(
        self,
        *,
        model: str,
        system_prompt: str,
        user_prompt: str,
        max_tokens: int = 4096,
        max_searches: int = 6,
    ) -> tuple[dict[str, Any], dict[str, int]]:
        """Run a server-side web-search agentic turn and parse a JSON object from the final text.

        Anthropic runs the search loop server-side (up to `max_searches` queries) and returns the
        model's synthesized answer; `extract_message_text` keeps only the text blocks, so search
        result / tool_use blocks are ignored and just the final JSON payload is parsed."""
        message = retry_call(
            lambda: self.client.messages.create(
                model=model,
                max_tokens=max_tokens,
                temperature=0,
                system=system_prompt,
                messages=[{"role": "user", "content": user_prompt}],
                tools=[{
                    "type": "web_search_20250305",
                    "name": "web_search",
                    "max_uses": max_searches,
                }],
            )
        )
        return parse_json_object(extract_message_text(message)), anthropic_usage(message)


class LocalEmbeddingClient:
    """Local fastembed (ONNX) embeddings — no API key, runs on CPU, no PyTorch. Used so the dedup
    stage works with only an Anthropic key (Voyage is optional). The loaded model is cached per
    process."""

    _cache: dict[str, Any] = {}

    def __init__(self, model_name: str) -> None:
        try:
            from fastembed import TextEmbedding
        except ImportError as exc:
            raise ApiUnavailable("fastembed is not installed") from exc
        if model_name not in self._cache:
            self._cache[model_name] = TextEmbedding(model_name=model_name)
        self.model = self._cache[model_name]

    def embed(
        self,
        texts: list[str],
        *,
        model: str,
        input_type: str = "document",
    ) -> tuple[list[list[float]], dict[str, int]]:
        # input_type is ignored locally; matches the VoyageEmbeddingClient.embed signature so the
        # two clients are interchangeable. fastembed returns already-normalized numpy vectors; no
        # token usage for a local model.
        vectors = self.model.embed(list(texts))
        return [[float(value) for value in vector] for vector in vectors], {}


class VoyageEmbeddingClient:
    def __init__(self, api_key: str | None = None) -> None:
        api_key = api_key or os.getenv("VOYAGE_API_KEY")
        if not api_key:
            raise ApiUnavailable("VOYAGE_API_KEY is not set")
        try:
            import voyageai
        except ImportError as exc:
            raise ApiUnavailable("voyageai package is not installed") from exc
        self.client = voyageai.Client(api_key=api_key)

    def embed(
        self,
        texts: list[str],
        *,
        model: str,
        input_type: str = "document",
    ) -> tuple[list[list[float]], dict[str, int]]:
        result = retry_call(lambda: self.client.embed(texts, model=model, input_type=input_type))
        usage = getattr(result, "usage", {}) or {}
        if not isinstance(usage, dict):
            usage = {}
        return result.embeddings, {
            key: value
            for key, value in usage.items()
            if isinstance(value, int)
        }


def build_anthropic_client() -> AnthropicModelClient | None:
    try:
        return AnthropicModelClient()
    except ApiUnavailable:
        return None


def build_voyage_client() -> VoyageEmbeddingClient | None:
    try:
        return VoyageEmbeddingClient()
    except ApiUnavailable:
        return None


def build_local_embedding_client(model_name: str) -> LocalEmbeddingClient | None:
    try:
        return LocalEmbeddingClient(model_name)
    except ApiUnavailable:
        return None


DEFAULT_LOCAL_EMBEDDING_MODEL = "BAAI/bge-small-en-v1.5"


def resolve_embedding_provider(config: dict[str, Any]) -> str:
    """Decide which embedding backend to use for dedup. An explicit `dedup.embedding_provider`
    (`local` | `voyage`) wins; otherwise infer from the model name — Voyage's models start with
    `voyage`, anything else (a HuggingFace repo id) is treated as a local fastembed model."""
    dedup = config.get("dedup", {})
    provider = str(dedup.get("embedding_provider", "") or "").strip().lower()
    if provider in ("local", "voyage"):
        return provider
    model = str(dedup.get("embedding_model", "") or "").strip().lower()
    return "voyage" if model.startswith("voyage") else "local"


def build_embedding_client(config: dict[str, Any]):
    """Return the configured embedding client (local by default, Voyage if requested), or None if
    its backend is unavailable — in which case dedup falls back to exact-id matching only."""
    if resolve_embedding_provider(config) == "voyage":
        return build_voyage_client()
    model = str(config.get("dedup", {}).get("embedding_model", "") or "") or DEFAULT_LOCAL_EMBEDDING_MODEL
    return build_local_embedding_client(model)
