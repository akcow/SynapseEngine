import os
import json
from dataclasses import dataclass
from typing import Any
from app.services.llm import get_llm_client

@dataclass
class RuleBasedSummarizer:
    def summarize(self, messages: list[Any]) -> dict[str, str]:
        if not messages: return {"content": "", "sentiment": "Unknown"}
        count = len(messages)
        start_id = messages[0].id
        end_id = messages[-1].id
        return {"content": f"此阶段会话包含 {count} 条消息 (ID: {start_id} 至 {end_id})。", "sentiment": "中性"}

@dataclass
class LLMBasedSummarizer:
    fallback: RuleBasedSummarizer
    def summarize(self, messages: list[Any]) -> dict[str, str]:
        if not messages: return {"content": "", "sentiment": "Unknown"}
        dialogue = "\n".join([f"{m.peer_id}: {m.content}" for m in messages])
        model = os.getenv("EXTRACTOR_MODEL", "gpt-4o-mini")
        allowed_sentiments = ["积极", "消极", "中性", "好奇", "挫败"]
        prompt = (
            "You are a conversation summarizer and sentiment analyst.\n"
            "Analyze the following dialogue and provide a summary and the overall sentiment.\n"
            "Return ONLY a valid JSON object in this format:\n"
            "{\"content\": \"(Summary in Chinese, max 100 chars)\", \"sentiment\": \"(One tag from the list)\"}\n"
            f"Allowed sentiment tags: {json.dumps(allowed_sentiments, ensure_ascii=False)}\n\n"
            f"Dialogue:\n{dialogue}"
        )
        try:
            client = get_llm_client()
            resp = client.chat.completions.create(model=model, messages=[{"role": "user", "content": prompt}], temperature=0.3)
            raw_text = (resp.choices[0].message.content or "").strip()
            if "```json" in raw_text: raw_text = raw_text.split("```json")[1].split("```")[0].strip()
            parsed = json.loads(raw_text)
            content = str(parsed.get("content", "")).strip()
            sentiment = str(parsed.get("sentiment", "中性")).strip()
            if sentiment not in allowed_sentiments: sentiment = "中性"
            return {"content": content, "sentiment": sentiment}
        except Exception: return self.fallback.summarize(messages)

def generate_summary(messages: list[Any]) -> dict[str, str]:
    mode = os.getenv("EXTRACTOR_MODE", "rule").strip().lower()
    rule_sum = RuleBasedSummarizer()
    if mode == "llm":
        return LLMBasedSummarizer(fallback=rule_sum).summarize(messages)
    return rule_sum.summarize(messages)
