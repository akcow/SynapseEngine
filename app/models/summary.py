from pydantic import BaseModel, ConfigDict
from datetime import datetime

class Summary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    session_id: str
    content: str
    sentiment: str
    last_message_id: int
    created_at: datetime
