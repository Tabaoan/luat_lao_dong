from langchain_core.messages import SystemMessage, HumanMessage
from mst.retriever import get_mst_retriever
from system_prompts.mst_system import MST_SYSTEM_PROMPT  

def handle_mst_query(message: str, llm, embedding):
    retriever = get_mst_retriever(embedding)
    if retriever is None:
        return None

    docs = retriever.get_relevant_documents(message)
    if not docs:
        return "Hệ thống hiện không có thông tin mã số thuế phù hợp với yêu cầu."

    context = "\n\n".join(d.page_content for d in docs)

    messages = [
        SystemMessage(content=MST_SYSTEM_PROMPT),
        HumanMessage(
            content=f"Dữ liệu:\n{context}\n\nCâu hỏi: {message}"
        )
    ]

    return llm.invoke(messages).content
