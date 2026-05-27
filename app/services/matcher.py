import os
import json
from typing import Any
from dataclasses import dataclass
from app.services.llm import get_llm_client

@dataclass
class RuleMatcher:
    def is_contradictory(self, a: str, b: str) -> bool:
        negations = ["不", "没", "非", "无", "未", "别"]
        has_a = any(n in a for n in negations)
        has_b = any(n in b for n in negations)
        return has_a != has_b

@dataclass
class LLMMatcher:
    fallback: RuleMatcher
    def is_contradictory(self, a: str, b: str) -> bool:
        model = os.getenv("EXTRACTOR_MODEL", "gpt-4o-mini")
        prompt = (
            "Determine if these two user-related observations are logically contradictory.\n"
            "Return ONLY a valid JSON object: {\"contradictory\": true|false}\n"
            f"Observation A: {a}\n"
            f"Observation B: {b}"
        )
        try:
            client = get_llm_client()
            resp = client.chat.completions.create(model=model, messages=[{"role": "user", "content": prompt}], temperature=0)
            raw_text = resp.choices[0].message.content or ""
            parsed = json.loads(raw_text)
            return bool(parsed.get("contradictory", False))
        except Exception:
            return self.fallback.is_contradictory(a, b)

@dataclass
class MatchingSpecialist:
    def find_match(self, content: str, embedding: list[float], candidates: list[Any], threshold: float = 0.7) -> dict[str, Any]:
        from app.utils.vectorizer import HashVectorizer
        mode = os.getenv("EXTRACTOR_MODE", "rule").strip().lower()
        rule_matcher = RuleMatcher()
        matcher = LLMMatcher(fallback=rule_matcher) if mode == "llm" else rule_matcher
        for o in candidates:
            if o.content == content: return {"type": "match", "id": o.id}
            if o.embedding and embedding:
                sim = HashVectorizer.cosine(o.embedding, embedding)
                if sim >= threshold:
                    if matcher.is_contradictory(o.content, content): return {"type": "contradiction", "id": o.id}
                    return {"type": "match", "id": o.id}
        return {"type": "new", "id": None}
