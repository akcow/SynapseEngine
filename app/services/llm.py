import os
import json
from typing import Any

def get_llm_client():
    from openai import OpenAI
    api_key = os.getenv("OPENAI_API_KEY")
    base_url = os.getenv("OPENAI_BASE_URL")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is not set")
    return OpenAI(api_key=api_key, base_url=base_url) if base_url else OpenAI(api_key=api_key)

def normalize_observations(raw_items: Any) -> list[dict[str, Any]]:
    """Validate/normalize extractor output to a stable structure."""
    if not isinstance(raw_items, list):
        return []

    normalized: list[dict[str, Any]] = []
    for item in raw_items:
        if not isinstance(item, dict):
            continue
        level = str(item.get("level", "explicit")).strip().lower()
        content = str(item.get("content", "")).strip()
        source_ids = item.get("source_ids", [])
        if not content:
            continue
        if level not in {"explicit", "deductive", "inductive", "insight"}:
            level = "explicit"
        if not isinstance(source_ids, list):
            source_ids = []
            
        normalized.append({
            "level": level, 
            "content": content, 
            "source_ids": source_ids
        })
    return normalized
