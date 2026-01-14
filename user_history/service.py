# user_history/service.py
from typing import List

from langchain_core.messages import (
    HumanMessage,
    AIMessage,
    SystemMessage,
    BaseMessage,
)

from user_history.models import ChatMessage
from user_history.repository import (
    insert_message,
    fetch_recent_messages,
)

def load_history_as_messages(
    session_id: str,
    limit: int = 20
) -> List[BaseMessage]:
    """
    Trả về history dạng LangChain messages
    để đưa thẳng vào prompt.
    """
    records = fetch_recent_messages(session_id, limit)

    messages: List[BaseMessage] = []
    for r in records:
        if r.role == "human":
            messages.append(HumanMessage(content=r.content))
        elif r.role == "ai":
            messages.append(AIMessage(content=r.content))
        elif r.role == "system":
            messages.append(SystemMessage(content=r.content))

    return messages


def save_user_message(session_id: str, content: str) -> None:
    insert_message(ChatMessage(
        session_id=session_id,
        role="human",
        content=content,
    ))


def save_ai_message(session_id: str, content: str) -> None:
    insert_message(ChatMessage(
        session_id=session_id,
        role="ai",
        content=content,
    ))
