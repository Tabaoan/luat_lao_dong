# user_history/models.py
from dataclasses import dataclass
from typing import Literal
from datetime import datetime

Role = Literal["system", "human", "ai"]

@dataclass
class ChatMessage:
    session_id: str
    role: Role
    content: str
    created_at: datetime | None = None
