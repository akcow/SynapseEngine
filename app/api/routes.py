from fastapi import APIRouter, Request, HTTPException
from typing import List
import logging

from app.api.schemas import AddMessageRequest, MessageResponse, MemorySearchResponse

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Memory Interface"])

@router.post("/sessions/{session_id}/messages", response_model=MessageResponse, summary="发送对话消息")
async def add_message(session_id: str, payload: AddMessageRequest, request: Request):
    """
    接收来自任意端侧用户的消息，触发后台提取、记忆聚合等任务。
    保安大爷(Pydantic)会自动校验 payload 格式。
    """
    logger.info(f"Processing message in session: {session_id}")
    engine = request.app.state.engine
    
    # 调用引擎底层方法
    msg = await engine.add_message(
        session_id=session_id, 
        peer_id=payload.peer_id, 
        content=payload.content
    )
    return msg

@router.get("/memories", response_model=List[MemorySearchResponse], summary="检索相似记忆")
async def search_memory(observer: str, observed: str, query: str, request: Request, top_k: int = 5):
    """
    基于向量数据库或本地内存索引，快速检索相关记忆。
    """
    engine = request.app.state.engine
    results = engine.search_memory(observer=observer, observed=observed, query=query, top_k=top_k)
    
    # 组装返回结果
    response = []
    for score, obs in results:
        # 兼容 Pydantic 和 Enum 的层级读取
        level_val = obs.level.value if hasattr(obs.level, 'value') else obs.level
        response.append(MemorySearchResponse(
            score=score,
            content=obs.content,
            level=level_val
        ))
        
    return response
