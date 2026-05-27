import asyncio
import logging
from sqlalchemy import select
from app.core.database import SessionLocal
from app.models.db_models import DBObservation, is_postgres

logger = logging.getLogger(__name__)

class Reconciler:
    """
    负责保持关系型数据库与向量数据库之间最终一致性的对账进程。
    扫描未向量化 (is_vectorized=False) 的记录进行补齐。
    """
    def __init__(self, db, vectorizer, index_adder=None):
        self.db = db
        self.vectorizer = vectorizer
        self.index_adder = index_adder
        self.running = False
        self.sleep_interval = 100  # 测试期间设定短一点，如 10 秒；生产环境可设置为 60~300 秒

    async def run_loop(self):
        self.running = True
        logger.info("[Reconciler] 对账自愈后台进程已启动...")
        while self.running:
            try:
                await self.reconcile()
            except Exception as e:
                logger.error(f"[Reconciler] 对账扫描时发生错误: {e}")
            await asyncio.sleep(self.sleep_interval)

    async def reconcile(self):
        with SessionLocal() as db_session:
            # 找到所有 is_active=True 但是 is_vectorized=False 的落单记忆
            stmt = select(DBObservation).where(
                DBObservation.is_vectorized == False,
                DBObservation.is_active == True
            )
            orphans = db_session.scalars(stmt).all()

            if not orphans:
                return

            logger.info(f"[Reconciler] 扫描到 {len(orphans)} 条未向量化 (is_vectorized=False) 的记忆，开始自愈补齐...")

            for obs in orphans:
                try:
                    # 重新计算 Embedding
                    emb = self.vectorizer.embed(obs.content)
                    
                    obs.embedding = emb
                    obs.is_vectorized = True

                    # 如果我们使用的是模拟的内存向量库（CollectionIndex），还要补齐到内存中
                    if not is_postgres and self.index_adder:
                        self.index_adder(obs.observer, obs.observed, obs.id, emb)

                    db_session.commit()
                    logger.info(f"[Reconciler] 记忆 (ID:{obs.id}) 向量补齐成功！")
                except Exception as e:
                    db_session.rollback()
                    logger.error(f"[Reconciler] 修复记忆 (ID:{obs.id}) 失败: {e}")

    def stop(self):
        self.running = False
        logger.info("[Reconciler] 对账自愈进程已停止。")
