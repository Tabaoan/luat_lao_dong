# user_history/langchain_history.py
import os
from typing import List

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from langchain_core.chat_history import BaseChatMessageHistory
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, SystemMessage


def _role_from_message(m: BaseMessage) -> str:
    # LangChain message types -> role string
    if isinstance(m, HumanMessage):
        return "human"
    if isinstance(m, AIMessage):
        return "ai"
    if isinstance(m, SystemMessage):
        return "system"
    # fallback: treat as human
    return "human"


def _message_from_role(role: str, content: str) -> BaseMessage:
    role = (role or "").lower()
    if role == "human":
        return HumanMessage(content=content)
    if role == "ai":
        return AIMessage(content=content)
    if role == "system":
        return SystemMessage(content=content)
    return HumanMessage(content=content)


class SupabaseChatMessageHistory(BaseChatMessageHistory):
    """
    Lưu lịch sử hội thoại vào Supabase/Postgres (bảng chat_messages).

    Required ENV:
      - DATABASE_URL (SQLAlchemy URL), ví dụ:
        postgresql+psycopg2://USER:PASSWORD@HOST:PORT/postgres
    """

    def __init__(self, session_id: str, limit: int = 40):
        self.session_id = session_id
        self.limit = limit

        db_url = os.getenv("DATABASE_URL")
        if not db_url:
            raise RuntimeError("DATABASE_URL is not set")

        self._engine: Engine = create_engine(
            db_url,
            pool_pre_ping=True,
            pool_size=5,
            max_overflow=10,
        )

    @property
    def messages(self) -> List[BaseMessage]:
        # Lấy N messages gần nhất, trả về đúng thứ tự thời gian tăng dần
        sql = text("""
            select role, content
            from chat_messages
            where session_id = :session_id
            order by created_at desc
            limit :limit
        """)
        with self._engine.begin() as conn:
            rows = conn.execute(
                sql,
                {"session_id": self.session_id, "limit": self.limit},
            ).fetchall()

        rows = list(reversed(rows))
        return [_message_from_role(r[0], r[1]) for r in rows]

    def add_message(self, message: BaseMessage) -> None:
        role = _role_from_message(message)
        content = getattr(message, "content", "") or ""

        sql = text("""
            insert into chat_messages (session_id, role, content)
            values (:session_id, :role, :content)
        """)
        with self._engine.begin() as conn:
            conn.execute(
                sql,
                {"session_id": self.session_id, "role": role, "content": content},
            )

    def clear(self) -> None:
        sql = text("""
            delete from chat_messages
            where session_id = :session_id
        """)
        with self._engine.begin() as conn:
            conn.execute(sql, {"session_id": self.session_id})
