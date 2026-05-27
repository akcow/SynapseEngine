import os
import json
import re
from dataclasses import dataclass
from typing import Any
from app.services.llm import get_llm_client, normalize_observations

@dataclass
class RuleBasedExtractor:
    def extract(self, content: str) -> list[dict[str, Any]]:
        results = []
        text = content.strip()
        if not text: return results
        patterns = [
            (r"我叫(.+)", "名字是{0}"),
            (r"我(?:目前|现在|已经)?住在(.+)", "居住地是{0}"),
            (r"我喜欢(.+)", "喜欢{0}"),
            (r"我不喜欢(.+)", "不喜欢{0}"),
            (r"我在学(.+)", "正在学习{0}"),
        ]
        for pattern, template in patterns:
            match = re.search(pattern, text)
            if match:
                value = match.group(1).strip("。.!?！？")
                if value:
                    results.append({"level": "explicit", "content": template.format(value), "source_ids": []})
        if not results:
            results.append({"level": "explicit", "content": text, "source_ids": []})
        return results

@dataclass
class LLMBasedExtractor:
    fallback: RuleBasedExtractor
    def extract(self, content: str) -> list[dict[str, Any]]:
        text = content.strip()
        if not text: return []
        model = os.getenv("EXTRACTOR_MODEL", "gpt-4o-mini")
        prompt = (
            "You are an information extraction engine.\n"
            "Extract user-related observations from the message.\n"
            "Return ONLY valid JSON array.\n"
            "Each item format: {\"level\":\"explicit|deductive\",\"content\":\"...\",\"source_ids\":[]}\n"
            "Prefer explicit observations and keep each content concise.\n"
            f"Message: {text}"
        )
        try:
            client = get_llm_client()
            resp = client.chat.completions.create(model=model, messages=[{"role": "user", "content": prompt}], temperature=0)
            raw_text = resp.choices[0].message.content or ""
            parsed = json.loads(raw_text)
            normalized = normalize_observations(parsed)
            if normalized: return normalized
        except Exception: pass
        return self.fallback.extract(content)

def extract_observations(content: str) -> list[dict[str, Any]]:
    mode = os.getenv("EXTRACTOR_MODE", "rule").strip().lower()
    rule_extractor = RuleBasedExtractor()
    if mode == "llm":
        return LLMBasedExtractor(fallback=rule_extractor).extract(content)
    return rule_extractor.extract(content)
