from pydantic import BaseModel, Field
from typing import List

# 请求模型 (Request)：规定前端发过来的数据必须长什么样
class AddMessageRequest(BaseModel):
    peer_id: str = Field(..., description="发送消息的用户ID", example="alice")
    content: str = Field(..., description="消息文本内容")

# 响应模型 (Response)：规定返回给前端的数据必须长什么样
class MessageResponse(BaseModel):
    id: int
    session_id: str
    peer_id: str
    content: str
    token_count: int

class MemorySearchResponse(BaseModel):
    score: float
    content: str
    level: str
