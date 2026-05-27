from datetime import datetime
from typing import List, Optional
from sqlalchemy import select, func

from app.core.database import SessionLocal, init_db
from app.models.db_models import DBMessage, DBObservation, DBSummary
from app.models.message import Message
from app.models.observation import Observation
from app.models.summary import Summary
from app.core.cache_client import (
    safe_cache_get, 
    safe_cache_set, 
    safe_cache_delete_prefix, 
    session_msgs_cache_key, 
    session_msgs_cache_prefix
)

class SQLStorage:
    def __init__(self) -> None:
        # 在启动时初始化数据库表
        init_db()

    def add_message(self, session_id: str, peer_id: str, content: str) -> Message:
        with SessionLocal() as db:
            db_msg = DBMessage(
                session_id=session_id,
                peer_id=peer_id,
                content=content,
                created_at=datetime.utcnow(),
                token_count=max(1, len(content) // 4),
            )
            db.add(db_msg)
            db.commit()
            db.refresh(db_msg)
            
            # Cache Invalidation: 新消息产生，立刻清除该 session 相关的所有旧缓存
            safe_cache_delete_prefix(session_msgs_cache_prefix(session_id))
            
            return Message.model_validate(db_msg)

    def add_observation(
        self,
        observer: str,
        observed: str,
        content: str,
        level: str,
        message_ids: List[int],
        embedding: List[float],
        source_ids: List[int] = None,
        is_vectorized: bool = True,
    ) -> Observation:
        with SessionLocal() as db:
            db_obs = DBObservation(
                observer=observer,
                observed=observed,
                content=content,
                level=level,
                message_ids=message_ids,
                embedding=embedding,
                source_ids=source_ids or [],
                is_vectorized=is_vectorized,
                created_at=datetime.utcnow(),
            )
            db.add(db_obs)
            db.commit()
            db.refresh(db_obs)
            return Observation.model_validate(db_obs)

    def add_summary(self, session_id: str, content: str, sentiment: str, last_message_id: int) -> Summary:
        with SessionLocal() as db:
            db_summary = DBSummary(
                session_id=session_id,
                content=content,
                sentiment=sentiment,
                last_message_id=last_message_id,
                created_at=datetime.utcnow()
            )
            db.add(db_summary)
            db.commit()
            db.refresh(db_summary)
            return Summary.model_validate(db_summary)

    def get_session_messages(self, session_id: str, token_limit: Optional[int] = None) -> List[Message]:
        # 1. 查询缓存
        cache_key = session_msgs_cache_key(session_id, token_limit)
        cached_result = safe_cache_get(cache_key)
        if cached_result is not None:
            return cached_result
            
        with SessionLocal() as db:
            if token_limit is not None:
                # 借助数据库的 Window Function，从最新的消息往回累加 Token
                token_subquery = (
                    select(
                        DBMessage.id,
                        func.sum(DBMessage.token_count)
                        .over(order_by=DBMessage.id.desc())
                        .label("running_token_sum"),
                    )
                    .where(DBMessage.session_id == session_id)
                    .subquery()
                )
                
                # 在数据库层直接截断超出预算的旧消息，最终按正序返回
                stmt = (
                    select(DBMessage)
                    .join(token_subquery, DBMessage.id == token_subquery.c.id)
                    .where(token_subquery.c.running_token_sum <= token_limit)
                    .order_by(DBMessage.id.asc())
                )
            else:
                stmt = select(DBMessage).where(DBMessage.session_id == session_id).order_by(DBMessage.id.asc())
                
            results = db.scalars(stmt).all()
            final_result = [Message.model_validate(m) for m in results]
            
            # 2. 回写缓存
            safe_cache_set(cache_key, final_result)
            return final_result

    def get_collection(self, observer: str, observed: str) -> List[Observation]:
        with SessionLocal() as db:
            stmt = select(DBObservation).where(
                DBObservation.observer == observer,
                DBObservation.observed == observed,
                DBObservation.is_active == True
            )
            results = db.scalars(stmt).all()
            return [Observation.model_validate(o) for o in results]

    def merge_observation(self, obs_id: int, message_ids: List[int], source_ids: List[int] = None, content: str = None, embedding: List[float] = None, is_vectorized: bool = True) -> Observation:
        with SessionLocal() as db:
            db_obs = db.get(DBObservation, obs_id)
            if not db_obs:
                raise ValueError(f"Observation {obs_id} not found")
            
            msg_set = set(db_obs.message_ids or [])
            msg_set.update(message_ids)
            db_obs.message_ids = sorted(list(msg_set))
            
            src_set = set(db_obs.source_ids or [])
            src_set.update(source_ids or [])
            db_obs.source_ids = sorted(list(src_set))
            
            if content: db_obs.content = content
            if embedding: 
                db_obs.embedding = embedding
                db_obs.is_vectorized = is_vectorized
            
            db_obs.created_at = datetime.utcnow()
            db.commit()
            db.refresh(db_obs)
            return Observation.model_validate(db_obs)

    def deactivate_observation(self, obs_id: int) -> bool:
        with SessionLocal() as db:
            db_obs = db.get(DBObservation, obs_id)
            if db_obs:
                db_obs.is_active = False
                db.commit()
                return True
            return False

    def get_all_summaries(self) -> List[Summary]:
        with SessionLocal() as db:
            stmt = select(DBSummary)
            results = db.scalars(stmt).all()
            return [Summary.model_validate(s) for s in results]

    def get_all_observations(self) -> List[Observation]:
        with SessionLocal() as db:
            stmt = select(DBObservation)
            results = db.scalars(stmt).all()
            return [Observation.model_validate(o) for o in results]

    @property
    def messages(self) -> List[Message]:
        with SessionLocal() as db:
            stmt = select(DBMessage)
            results = db.scalars(stmt).all()
            return [Message.model_validate(m) for m in results]

    @property
    def observations(self) -> List[Observation]:
        return self.get_all_observations()

    @property
    def summaries(self) -> List[Summary]:
        return self.get_all_summaries()

# 为了兼容现有 Engine，我们将 SQLStorage 导出为 InMemoryDB
InMemoryDB = SQLStorage
