from pydantic import BaseModel, ConfigDict, Field
from datetime import datetime
from typing import List, Optional
from app.models.base import MemoryLevel

class Observation(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    observer: str
    observed: str
    content: str
    level: MemoryLevel
    message_ids: List[int] = Field(default_factory=list)
    created_at: datetime
    source_ids: List[int] = Field(default_factory=list)
    embedding: List[float] = Field(default_factory=list)
    is_active: bool = True
    is_vectorized: bool = False
