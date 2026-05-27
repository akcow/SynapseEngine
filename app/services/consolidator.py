import os
import json
from dataclasses import dataclass
from typing import Any
from app.services.llm import get_llm_client, normalize_observations

@dataclass
class RuleConsolidator:
    def consolidate(self, facts: list[tuple[int, str]]) -> list[dict[str, Any]]:
        results = []
        python_ids = [f[0] for f in facts if "Python" in f[1]]
        ai_ids = [f[0] for f in facts if "AI" in f[1] or "学习" in f[1]]
        if python_ids and ai_ids:
            results.append({"level": "deductive", "content": "用户专注于 Python 在 AI 领域的 application 实现", "source_ids": sorted(list(set(python_ids + ai_ids)))})
        name_ids = [f[0] for f in facts if "名字" in f[1]]
        loc_ids = [f[0] for f in facts if "居住地" in f[1]]
        if name_ids and loc_ids:
            results.append({"level": "deductive", "content": "用户已完成基础个人身份画像（姓名+地点）", "source_ids": sorted(list(set(name_ids + loc_ids)))})
        return results

@dataclass
class LLMConsolidator:
    fallback: RuleConsolidator
    def consolidate(self, facts: list[tuple[int, str]]) -> list[dict[str, Any]]:
        facts_text = "\n".join([f"Fact [ID: {f[0]}]: {f[1]}" for f in facts])
        model = os.getenv("EXTRACTOR_MODEL", "gpt-4o-mini")
        prompt = (
            "You are a knowledge consolidation engine.\n"
            "Given the following atomic observations (with IDs), synthesize 1-2 higher-level insights.\n"
            "Return ONLY a valid JSON array.\n"
            "Format: [{\"level\": \"deductive|inductive|insight\", \"content\": \"...\", \"source_ids\": [ID1, ID2]}]\n"
            f"Observations:\n{facts_text}"
        )
        try:
            client = get_llm_client()
            resp = client.chat.completions.create(model=model, messages=[{"role": "user", "content": prompt}], temperature=0)
            raw_text = resp.choices[0].message.content or ""
            parsed = json.loads(raw_text)
            return normalize_observations(parsed)
        except Exception:
            return self.fallback.consolidate(facts)

def deduce_observations(facts: list[tuple[int, str]]) -> list[dict[str, Any]]:
    mode = os.getenv("EXTRACTOR_MODE", "rule").strip().lower()
    rule_cons = RuleConsolidator()
    if mode == "llm":
        return LLMConsolidator(fallback=rule_cons).consolidate(facts)
    return rule_cons.consolidate(facts)

@dataclass
class RuleBasedDreamSpecialist:
    def dream(self, observations: list[str]) -> str:
        unique_obs = []
        for o in observations:
            if o not in unique_obs: unique_obs.append(o)
        return "；".join(unique_obs)

@dataclass
class LLMBasedDreamSpecialist:
    fallback: RuleBasedDreamSpecialist
    def dream(self, observations: list[str]) -> str:
        if not observations: return ""
        if len(observations) == 1: return observations[0]
        obs_text = "\n".join([f"- {o}" for o in observations])
        model = os.getenv("EXTRACTOR_MODEL", "gpt-4o-mini")
        prompt = (
            "你是一个记忆整合与智慧提炼专家。请将以下观察结果合并为一条连贯、高维度的陈述。\n"
            "这些结果可能包括原始碎片（explicit）和之前的推论（deductive）。\n"
            "要求：\n"
            "1. 演化逻辑：如果输入包含多个具体事实，请尝试提炼背后的通用模式、用户性格画像或长期偏好（智慧层级）。\n"
            "2. 细节保留：必须保留所有独特的细节（如具体的名称、日期、偏好程度），不得为了抽象而丢失关键信息。\n"
            "3. 消除冗余：合并相似表述，使逻辑严密。\n"
            "4. 仅返回合并后的中文文本。\n\n"
            f"待处理观察结果：\n{obs_text}"
        )
        try:
            client = get_llm_client()
            resp = client.chat.completions.create(model=model, messages=[{"role": "user", "content": prompt}], temperature=0.3)
            return (resp.choices[0].message.content or "").strip()
        except Exception:
            return self.fallback.dream(observations)

def consolidate_clusters(observations: list[str]) -> str:
    mode = os.getenv("EXTRACTOR_MODE", "rule").strip().lower()
    rule_spec = RuleBasedDreamSpecialist()
    if mode == "llm":
        return LLMBasedDreamSpecialist(fallback=rule_spec).dream(observations)
    return rule_spec.dream(observations)
