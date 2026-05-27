from pydantic import BaseModel, ConfigDict
from datetime import datetime

class Message(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    session_id: str
    peer_id: str
    content: str
    created_at: datetime
    token_count: int
