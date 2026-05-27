import os
from datetime import datetime
from typing import List, Optional
from sqlalchemy import String, Integer, DateTime, JSON, Boolean, Enum as SQLEnum, Index, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from app.models.base import MemoryLevel

class Base(DeclarativeBase):
    pass

class DBMessage(Base):
    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(String, index=True)
    peer_id: Mapped[str] = mapped_column(String)
    content: Mapped[str] = mapped_column(String)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    token_count: Mapped[int] = mapped_column(Integer)

# 动态决定 embedding 字段的类型
database_url = os.getenv("DATABASE_URL", "sqlite:///./memory_engine.db")
is_postgres = not database_url.startswith("sqlite")

if is_postgres:
    from pgvector.sqlalchemy import Vector
    embedding_type = Vector(128)
else:
    embedding_type = JSON

class DBObservation(Base):
    __tablename__ = "observations"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    observer: Mapped[str] = mapped_column(String, index=True)
    observed: Mapped[str] = mapped_column(String, index=True)
    content: Mapped[str] = mapped_column(String)
    level: Mapped[MemoryLevel] = mapped_column(SQLEnum(MemoryLevel))
    message_ids: Mapped[List[int]] = mapped_column(JSON, default=[])
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    source_ids: Mapped[List[int]] = mapped_column(JSON, default=[])
    embedding: Mapped[List[float]] = mapped_column(embedding_type, default=[])
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_vectorized: Mapped[bool] = mapped_column(Boolean, default=False)

    # 只有在 PostgreSQL 模式下才声明 HNSW 索引
    if is_postgres:
        __table_args__ = (
            Index(
                "hnsw_obs_embedding_idx",
                "embedding",
                postgresql_using="hnsw",
                postgresql_with={"m": 16, "ef_construction": 64},
                postgresql_ops={"embedding": "vector_cosine_ops"}
            ),
        )

class DBSummary(Base):
    __tablename__ = "summaries"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(String, index=True)
    content: Mapped[str] = mapped_column(String)
    sentiment: Mapped[str] = mapped_column(String)
    last_message_id: Mapped[int] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

class DBQueueTask(Base):
    __tablename__ = "queue_tasks"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    task_type: Mapped[str] = mapped_column(String, index=True)
    session_id: Mapped[str] = mapped_column(String, index=True)
    message_id: Mapped[int] = mapped_column(Integer, index=True)
    observer: Mapped[str] = mapped_column(String)
    observed: Mapped[str] = mapped_column(String)
    
    status: Mapped[str] = mapped_column(String, default="pending", index=True)
    error_msg: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint(
            'task_type', 'session_id', 'message_id', 'observer', 'observed', 
            name='uix_queue_task_idempotency'
        ),
    )
