from collections import defaultdict
from typing import List, Callable, Any

from app.models.db_models import is_postgres
from app.models.base import LEVEL_HIERARCHY
from app.services.extractor import extract_observations
from app.services.consolidator import deduce_observations, consolidate_clusters
from app.services.summarizer import generate_summary
from app.core.telemetry import track_latency

class TaskProcessor:
    def __init__(self, db, vectorizer, matcher, index_adder: Callable[[str, str, int, Any], None] = None):
        self.db = db
        self.vectorizer = vectorizer
        self.matcher = matcher
        self.index_adder = index_adder

    @track_latency("TaskProcessor.process_representation_batch")
    async def process_representation_batch(self, tasks) -> None:
        grouped = defaultdict(list)
        for t in tasks: 
            grouped[(t.observer, t.observed)].append(t)
            
        for (observer, observed), group_tasks in grouped.items():
            msg_ids = [t.message_id for t in group_tasks]
            msgs = [m for m in self.db.messages if m.id in msg_ids]
            msgs.sort(key=lambda x: x.id)
            new_obs_ids = []
            
            for msg in msgs:
                extracted = extract_observations(msg.content)
                for obs in extracted:
                    content = obs["content"]
                    emb = self.vectorizer.embed(content)
                    candidates = [o for o in self.db.get_collection(observer, observed) if o.is_active]
                    match_res = self.matcher.find_match(content, emb, candidates)
                    
                    if match_res["type"] == "match":
                        saved_obs = self.db.merge_observation(
                            obs_id=match_res["id"], message_ids=[msg.id], 
                            content=content, embedding=emb
                        )
                    elif match_res["type"] == "contradiction":
                        saved_obs = self.db.add_observation(
                            observer=observer, observed=observed, content=content, 
                            level="contradiction", message_ids=[msg.id], embedding=emb
                        )
                    else:
                        saved_obs = self.db.add_observation(
                            observer=observer, observed=observed, content=content, 
                            level=obs["level"], message_ids=[msg.id], embedding=emb
                        )
                        if not is_postgres and self.index_adder:
                            self.index_adder(observer, observed, saved_obs.id, emb)
                    
                    new_obs_ids.append(saved_obs.id)
            
            if new_obs_ids:
                await self.run_deduction_cycle(observer, observed, new_obs_ids)

    async def run_deduction_cycle(self, observer: str, observed: str, new_obs_ids: list[int]) -> None:
        facts = []
        source_obs_map = {}
        for o_id in new_obs_ids:
            obs = next((o for o in self.db.observations if o.id == o_id), None)
            if obs:
                facts.append((obs.id, obs.content))
                source_obs_map[obs.id] = obs
                
        deductions = deduce_observations(facts)
        for d in deductions:
            content = d["content"]
            emb = self.vectorizer.embed(content)
            merged_msg_ids = set()
            for s_id in d.get("source_ids", []):
                if s_id in source_obs_map:
                    merged_msg_ids.update(source_obs_map[s_id].message_ids)
                    
            candidates = [o for o in self.db.get_collection(observer, observed) if o.is_active]
            match_res = self.matcher.find_match(content, emb, candidates)
            
            if match_res["type"] == "match":
                self.db.merge_observation(
                    obs_id=match_res["id"], message_ids=list(merged_msg_ids), 
                    source_ids=d.get("source_ids", []), content=content, embedding=emb
                )
            elif match_res["type"] == "contradiction":
                self.db.add_observation(
                    observer=observer, observed=observed, content=content, 
                    level="contradiction", message_ids=list(merged_msg_ids), 
                    embedding=emb, source_ids=d.get("source_ids", [])
                )
            else:
                saved_obs = self.db.add_observation(
                    observer=observer, observed=observed, content=content, 
                    level=d["level"], message_ids=list(merged_msg_ids), 
                    embedding=emb, source_ids=d.get("source_ids", [])
                )
                if not is_postgres and self.index_adder:
                    self.index_adder(observer, observed, saved_obs.id, emb)

    async def process_summary_tasks(self, tasks) -> None:
        sessions = {t.session_id for t in tasks}
        for session_id in sessions:
            session_summaries = [s for s in self.db.summaries if s.session_id == session_id]
            last_id = max(s.last_message_id for s in session_summaries) if session_summaries else 0
            all_msgs = self.db.get_session_messages(session_id)
            new_msgs = [m for m in all_msgs if m.id > last_id]
            
            if len(new_msgs) >= 1:
                summary_data = generate_summary(new_msgs)
                self.db.add_summary(
                    session_id=session_id, content=summary_data["content"], 
                    sentiment=summary_data["sentiment"], last_message_id=new_msgs[-1].id
                )

    async def process_dream_tasks(self, tasks) -> None:
        targets = {(t.observer, t.observed) for t in tasks}
        for observer, observed in targets:
            active_obs = [o for o in self.db.get_collection(observer, observed) if o.is_active]
            if len(active_obs) < 2: 
                continue
                
            clusters = []
            remaining = list(active_obs)
            while remaining:
                seed = remaining.pop(0)
                cluster = [seed]
                peers = [o for o in remaining if self.vectorizer.cosine(seed.embedding, o.embedding) > 0.6]
                for p in peers:
                    cluster.append(p)
                    remaining.remove(p)
                if len(cluster) > 1: 
                    clusters.append(cluster)
                    
            for cluster in clusters:
                merged_content = consolidate_clusters([c.content for c in cluster])
                merged_msg_ids = set()
                merged_src_ids = set()
                max_level_idx = 0
                
                for c in cluster:
                    merged_msg_ids.update(c.message_ids)
                    merged_src_ids.add(c.id)
                    try:
                        idx = LEVEL_HIERARCHY.index(c.level)
                        if idx > max_level_idx: 
                            max_level_idx = idx
                    except ValueError: 
                        pass
                        
                new_level = LEVEL_HIERARCHY[min(max_level_idx + 1, len(LEVEL_HIERARCHY) - 1)]
                emb = self.vectorizer.embed(merged_content)
                saved_obs = self.db.add_observation(
                    observer=observer, observed=observed, content=merged_content, 
                    level=new_level, message_ids=list(merged_msg_ids), 
                    embedding=emb, source_ids=list(merged_src_ids)
                )
                
                if not is_postgres and self.index_adder:
                    self.index_adder(observer, observed, saved_obs.id, emb)
                    
                for c in cluster: 
                    self.db.deactivate_observation(c.id)
