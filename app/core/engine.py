import asyncio
import time
from collections import defaultdict
from dataclasses import dataclass

from sqlalchemy import select, case
from sqlalchemy.exc import IntegrityError
from app.core.database import SessionLocal
from app.models.db_models import DBQueueTask
from app.models.base import LEVEL_HIERARCHY
from app.models.message import Message
from app.models.observation import Observation
from app.models.db_models import is_postgres, DBObservation
from app.core.storage import InMemoryDB
from app.utils.vectorizer import HashVectorizer
from app.utils.vector_index import CollectionIndex
from app.services.matcher import MatchingSpecialist
from app.services.task_handlers import TaskProcessor
from app.core.telemetry import track_latency, pending_tasks_gauge, tasks_processed_total

@dataclass
class QueueTask:
    task_type: str
    session_id: str
    message_id: int
    observer: str
    observed: str

class MemoryEngine:
    def __init__(
        self, 
        db: InMemoryDB = None,
        vectorizer: HashVectorizer = None,
        matcher: MatchingSpecialist = None
    ) -> None:
        self.db = db or InMemoryDB()
        self.vectorizer = vectorizer or HashVectorizer()
        self.matcher = matcher or MatchingSpecialist()
        self.indices: dict[str, CollectionIndex] = {}
        self.session_last_active: dict[str, float] = {}
        self.session_idle_triggered: dict[str, bool] = {}
        self.running = False
        self.batch_token_limit = 120
        self.monitor_task: asyncio.Task = None
        self.processor = TaskProcessor(
            db=self.db,
            vectorizer=self.vectorizer,
            matcher=self.matcher,
            index_adder=lambda obs, obsd, oid, emb: self._get_index(obs, obsd).add(oid, emb)
        )

    @track_latency("MemoryEngine.add_message")
    async def add_message(self, session_id: str, peer_id: str, content: str) -> Message:
        from app.models.db_models import DBMessage
        from datetime import datetime
        
        # 预先获取当前参与者，用于生成任务
        session_msgs = self.db.get_session_messages(session_id)
        participants = {m.peer_id for m in session_msgs}
        participants.add(peer_id)
        
        with SessionLocal() as db_session:
            # 1. 存消息，不 commit，只 flush 拿到 ID
            db_msg = DBMessage(
                session_id=session_id,
                peer_id=peer_id,
                content=content,
                created_at=datetime.utcnow(),
                token_count=max(1, len(content) // 4),
            )
            db_session.add(db_msg)
            db_session.flush() # 核心：获取 db_msg.id 但不破坏事务
            
            # 2. 存任务，绑定刚才拿到的消息 ID
            # 因为 message_id 是全新生成的，任务绝对不会引发 Unique 冲突，所以直接 add 即可
            for observer_id in participants:
                db_session.add(DBQueueTask(
                    task_type="representation", session_id=session_id,
                    message_id=db_msg.id, observer=observer_id, observed=peer_id
                ))
                
            total_msgs = len(session_msgs) + 1
            if total_msgs % 5 == 0:
                db_session.add(DBQueueTask(
                    task_type="summary", session_id=session_id,
                    message_id=db_msg.id, observer=peer_id, observed=peer_id
                ))
                
            if total_msgs % 10 == 0:
                db_session.add(DBQueueTask(
                    task_type="dream", session_id=session_id,
                    message_id=db_msg.id, observer=peer_id, observed=peer_id
                ))
                
            # 3. 终极一跃：要么同生，要么共死 (Atomicity)
            db_session.commit()
            
            # 由于 commit 后 db_msg 可能会 expire，刷新一下以便转换为 Pydantic
            db_session.refresh(db_msg)
            msg = Message.model_validate(db_msg)
            
        self.session_last_active[session_id] = time.time()
        self.session_idle_triggered[session_id] = False
        return msg

    async def wait_all_tasks_done(self) -> None:
        while True:
            with SessionLocal() as db_session:
                count = db_session.query(DBQueueTask).filter(
                    DBQueueTask.status.in_(["pending", "processing"])
                ).count()
                if count == 0:
                    break
            await asyncio.sleep(0.5)

    async def worker_loop(self) -> None:
        self.running = True
        self.monitor_task = asyncio.create_task(self._idle_monitor_loop())
        while self.running:
            db_tasks = []
            process_func = None
            queue_tasks_to_process = []
            
            with SessionLocal() as db_session:
                # 监控当前队列深度 (Gauge)
                pending_count = db_session.query(DBQueueTask).filter(DBQueueTask.status == "pending").count()
                pending_tasks_gauge.set(pending_count)
                
                task = db_session.query(DBQueueTask).filter(DBQueueTask.status == "pending").order_by(DBQueueTask.created_at).first()
                if task:
                    # 抢占锁：更新状态
                    task.status = "processing"
                    db_session.commit()
                    db_tasks.append(task)
                    
                    if task.task_type == "representation":
                        token_sum = self._message_tokens(task.message_id)
                        while token_sum < self.batch_token_limit:
                            nxt = db_session.query(DBQueueTask).filter(
                                DBQueueTask.status == "pending",
                                DBQueueTask.task_type == "representation",
                                DBQueueTask.session_id == task.session_id,
                                DBQueueTask.observed == task.observed
                            ).first()
                            if not nxt: break
                            nxt.status = "processing"
                            db_session.commit()
                            db_tasks.append(nxt)
                            token_sum += self._message_tokens(nxt.message_id)
                            
                        queue_tasks_to_process = [QueueTask(t.task_type, t.session_id, t.message_id, t.observer, t.observed) for t in db_tasks]
                        process_func = self.processor.process_representation_batch
                        
                    elif task.task_type == "summary":
                        while True:
                            nxt = db_session.query(DBQueueTask).filter(
                                DBQueueTask.status == "pending",
                                DBQueueTask.task_type == "summary",
                                DBQueueTask.session_id == task.session_id
                            ).first()
                            if not nxt: break
                            nxt.status = "processing"
                            db_session.commit()
                            db_tasks.append(nxt)
                            
                        queue_tasks_to_process = [QueueTask(t.task_type, t.session_id, t.message_id, t.observer, t.observed) for t in db_tasks]
                        process_func = self.processor.process_summary_tasks
                        
                    elif task.task_type == "dream":
                        while True:
                            nxt = db_session.query(DBQueueTask).filter(
                                DBQueueTask.status == "pending",
                                DBQueueTask.task_type == "dream",
                                DBQueueTask.session_id == task.session_id
                            ).first()
                            if not nxt: break
                            nxt.status = "processing"
                            db_session.commit()
                            db_tasks.append(nxt)
                            
                        queue_tasks_to_process = [QueueTask(t.task_type, t.session_id, t.message_id, t.observer, t.observed) for t in db_tasks]
                        process_func = self.processor.process_dream_tasks

            if not db_tasks:
                await asyncio.sleep(1)
                continue
                
            try:
                if process_func:
                    await process_func(queue_tasks_to_process)
                    
                with SessionLocal() as db_session:
                    for t in db_tasks:
                        db_t = db_session.query(DBQueueTask).get(t.id)
                        if db_t: 
                            db_t.status = "completed"
                            tasks_processed_total.labels(task_type=db_t.task_type, status="success").inc()
                    db_session.commit()

            except Exception as e:
                with SessionLocal() as db_session:
                    for t in db_tasks:
                        db_t = db_session.query(DBQueueTask).get(t.id)
                        if db_t:
                            tasks_processed_total.labels(task_type=db_t.task_type, status="error").inc()
                            db_t.retry_count += 1
                            if db_t.retry_count >= 3:
                                # 重试超过3次，进入死信状态 (failed)
                                db_t.status = "failed"
                            else:
                                # 否则退回队列重试
                                db_t.status = "pending"
                            db_t.error_msg = str(e)
                    db_session.commit()

    def retry_failed_tasks(self, task_id: int = None) -> int:
        """人工/后台调用的死信队列处理：将 failed 状态的任务捞回 pending。
        如果不传 task_id，则重试所有失败的任务。"""
        from app.core.database import SessionLocal
        from app.models.db_models import DBQueueTask
        
        with SessionLocal() as db_session:
            query = db_session.query(DBQueueTask).filter(DBQueueTask.status == "failed")
            if task_id:
                query = query.filter(DBQueueTask.id == task_id)
                
            failed_tasks = query.all()
            for t in failed_tasks:
                t.status = "pending"
                t.error_msg = None
            
            count = len(failed_tasks)
            db_session.commit()
            return count

    def stop(self) -> None:
        self.running = False
        if self.monitor_task: self.monitor_task.cancel()

    def _message_tokens(self, message_id: int) -> int:
        for m in self.db.messages:
            if m.id == message_id: return m.token_count
        return 0

    def _get_index(self, observer: str, observed: str) -> CollectionIndex:
        key = f"{observer}:{observed}"
        if key not in self.indices:
            self.indices[key] = CollectionIndex(dim=self.vectorizer.dim)
            if not is_postgres:
                active_obs = self.db.get_collection(observer, observed)
                for obs in active_obs:
                    if obs.embedding:
                        self.indices[key].add(obs.id, obs.embedding)
        return self.indices[key]

    async def _idle_monitor_loop(self) -> None:
        while self.running:
            await asyncio.sleep(5)
            now = time.time()
            for session_id, last_active in list(self.session_last_active.items()):
                if now - last_active > 30 and not self.session_idle_triggered.get(session_id):
                    if time.time() - self.session_last_active[session_id] > 30:
                        session_msgs = self.db.get_session_messages(session_id)
                        participants = {m.peer_id for m in session_msgs}
                        triggered_any = False
                        for p1 in participants:
                            for p2 in participants:
                                active_obs = [o for o in self.db.get_collection(p1, p2) if o.is_active]
                                has_explicit = any(o.level == "explicit" for o in active_obs)
                                if len(active_obs) >= 2 or (len(active_obs) == 1 and has_explicit):
                                    last_msg_id = session_msgs[-1].id if session_msgs else 0
                                    with SessionLocal() as db_session:
                                        task = DBQueueTask(task_type="dream", session_id=session_id, message_id=last_msg_id, observer=p1, observed=p2, status="pending")
                                        db_session.add(task)
                                        try:
                                            db_session.commit()
                                        except IntegrityError:
                                            db_session.rollback()
                                    triggered_any = True
                        if triggered_any: self.session_idle_triggered[session_id] = True

    def search_memory(self, observer: str, observed: str, query: str, top_k: int = 5) -> list[tuple[float, object]]:
        qv = self.vectorizer.embed(query)
        
        if is_postgres:
            from app.core.database import SessionLocal
            with SessionLocal() as db_session:
                # 动态优先级策略：insight 权重为 0（优先），explicit 权重为 1
                level_weight = case(
                    (DBObservation.level == "insight", 0),
                    else_=1
                )
                
                stmt = (
                    select(DBObservation)
                    .where(
                        DBObservation.observer == observer,
                        DBObservation.observed == observed,
                        DBObservation.is_active == True
                    )
                    # 优先按层级排序，其次按余弦距离（越小越近）
                    .order_by(level_weight.asc(), DBObservation.embedding.cosine_distance(qv))
                    .limit(top_k)
                )
                results = db_session.scalars(stmt).all()
                # 两个已归一化向量的点积（sum(x*y)）就是它们的余弦相似度分数
                return [(sum(x * y for x, y in zip(obs.embedding, qv)), Observation.model_validate(obs)) for obs in results]
        else:
            index = self._get_index(observer, observed)
            # 获取更多候选，以便在排序后仍有足够的量
            raw_results = index.search(qv, top_k=top_k * 5)
            candidates = []
            seen_ids = set()
            for score, obs_id in raw_results:
                if obs_id in seen_ids: continue
                obs = next((o for o in self.db.observations if o.id == obs_id), None)
                if obs and obs.is_active:
                    candidates.append((score, obs))
                    seen_ids.add(obs_id)
            
            # 内存二次排序策略：
            # 1. 权重：insight = 0, explicit = 1 (升序)
            # 2. 分数：相关度分数取反 (降序，也就是按原本分数的升序排列)
            candidates.sort(
                key=lambda x: (
                    0 if getattr(x[1].level, 'value', x[1].level) == "insight" else 1,
                    -x[0]
                )
            )
            return candidates[:top_k]
