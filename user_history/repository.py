# user_history/repository.py
import os
from typing import List

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine

from user_history.models import ChatMessage

SUPABASE_DB_URL = os.getenv("DATABASE_URL")
if not SUPABASE_DB_URL:
    raise RuntimeError("DATABASE_URL is not set")

_engine: Engine | None = None


def get_engine() -> Engine:
    global _engine
    if _engine is None:
        _engine = create_engine(
            SUPABASE_DB_URL,
            pool_pre_ping=True,
            pool_size=5,
            max_overflow=10,
        )
    return _engine


def insert_message(msg: ChatMessage) -> None:
    sql = text("""
        insert into chat_messages (session_id, role, content)
        values (:session_id, :role, :content)
    """)
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(sql, {
            "session_id": msg.session_id,
            "role": msg.role,
            "content": msg.content,
        })


def fetch_recent_messages(
    session_id: str,
    limit: int = 20
) -> List[ChatMessage]:
    sql = text("""
        select session_id, role, content, created_at
        from chat_messages
        where session_id = :session_id
        order by created_at desc
        limit :limit
    """)
    engine = get_engine()
    with engine.begin() as conn:
        rows = conn.execute(sql, {
            "session_id": session_id,
            "limit": limit
        }).fetchall()

    # đảo ngược để đúng thứ tự hội thoại
    rows = list(reversed(rows))

    return [
        ChatMessage(
            session_id=r[0],
            role=r[1],
            content=r[2],
            created_at=r[3],
        )
        for r in rows
    ]


def delete_session(session_id: str) -> None:
    sql = text("""
        delete from chat_messages
        where session_id = :session_id
    """)
    engine = get_engine()
    with engine.begin() as conn:
        conn.execute(sql, {"session_id": session_id})
