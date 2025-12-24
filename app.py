# ===================== IMPORTS =====================
import os
import sys
from typing import Dict
from pathlib import Path

from dotenv import load_dotenv
load_dotenv(override=True)

# LangChain
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langchain_core.runnables import RunnableLambda
from langchain_core.runnables.history import RunnableWithMessageHistory
from langchain_community.chat_message_histories import ChatMessageHistory

# Pinecone
from pinecone import Pinecone as PineconeClient
from langchain_pinecone import Pinecone

# Internal modules
from excel_query import ExcelQueryHandler
from data_processing.pipeline import process_pdf_question
from law_db_query.handler import (
    handle_law_article_query,
    handle_law_count_query
)
from law_db_query.router import route_message
from mst.router import is_mst_query
from mst.handler import handle_mst_query
from msn_2018.retriever import load_vsic_2018_retriever

# ===================== ENV =====================
OPENAI__API_KEY = os.getenv("OPENAI__API_KEY")
OPENAI__EMBEDDING_MODEL = os.getenv("OPENAI__EMBEDDING_MODEL")
OPENAI__MODEL_NAME = os.getenv("OPENAI__MODEL_NAME")
OPENAI__TEMPERATURE = os.getenv("OPENAI__TEMPERATURE", "0")
LANG_MODEL_API_KEY = os.getenv("LANG_MODEL_API_KEY")
PINECONE_API_KEY = os.getenv("PINECONE_API_KEY")
PINECONE_INDEX_NAME = os.getenv("PINECONE_INDEX_NAME")
EXCEL_FILE_PATH = os.getenv("EXCEL_FILE_PATH")
RUNNING_IN_API = os.getenv("RUNNING_IN_API", "false").lower() == "true"

EMBEDDING_DIM = 3072

# ===================== INIT LLM =====================
llm = ChatOpenAI(
    api_key=OPENAI__API_KEY,
    model_name=OPENAI__MODEL_NAME,
    temperature=float(OPENAI__TEMPERATURE)
)

lang_llm = ChatOpenAI(
    api_key=LANG_MODEL_API_KEY,
    model_name="gpt-4o-mini",
    temperature=0
)

# ===================== INIT EMBEDDING =====================
emb = OpenAIEmbeddings(
    api_key=OPENAI__API_KEY,
    model=OPENAI__EMBEDDING_MODEL
)

# ===================== INIT PINECONE =====================
if not PINECONE_API_KEY:
    raise RuntimeError("❌ Thiếu PINECONE_API_KEY")

pc = PineconeClient(api_key=PINECONE_API_KEY)

vectordb = None
retriever = None
retriever_vsic_2018 = None


# ===================== LOAD VECTOR DB =====================
def load_vectordb():
    global vectordb, retriever, retriever_vsic_2018

    if vectordb is not None:
        return vectordb  # tránh init lại

    if PINECONE_INDEX_NAME not in pc.list_indexes().names():
        raise RuntimeError(f"Pinecone index '{PINECONE_INDEX_NAME}' không tồn tại")

    index = pc.Index(PINECONE_INDEX_NAME)
    stats = index.describe_index_stats()

    if stats["total_vector_count"] == 0:
        raise RuntimeError("Pinecone index rỗng")

    vectordb = Pinecone(index=index, embedding=emb, text_key="text")
    retriever = vectordb.as_retriever(search_kwargs={"k": 15})

    try:
        retriever_vsic_2018 = load_vsic_2018_retriever(emb)
    except Exception:
        retriever_vsic_2018 = None

    return vectordb


def get_vectordb_stats() -> Dict:
    try:
        index = pc.Index(PINECONE_INDEX_NAME)
        stats = index.describe_index_stats()
        return {
            "exists": stats["total_vector_count"] > 0,
            "total_documents": stats["total_vector_count"],
            "dimension": stats.get("dimension", EMBEDDING_DIM)
        }
    except Exception as e:
        return {"exists": False, "error": str(e)}


# ===================== INIT EXCEL =====================
excel_handler = None
if EXCEL_FILE_PATH and Path(EXCEL_FILE_PATH).exists():
    try:
        excel_handler = ExcelQueryHandler(EXCEL_FILE_PATH)
    except Exception:
        excel_handler = None


# ===================== PIPELINE WRAPPER =====================
pdf_chain = RunnableLambda(
    lambda i: route_message(
        i,
        llm=llm,
        lang_llm=lang_llm,
        retriever=retriever,
        retriever_vsic_2018=retriever_vsic_2018,
        excel_handler=excel_handler
    )
)

store: Dict[str, ChatMessageHistory] = {}


def get_history(session_id: str):
    if session_id not in store:
        store[session_id] = ChatMessageHistory()
    return store[session_id]


chatbot = RunnableWithMessageHistory(
    pdf_chain,
    get_history,
    input_messages_key="message",
    history_messages_key="history"
)

# ===================== AUTO INIT (API MODE) =====================
if RUNNING_IN_API:
    try:
        print("🔄 [API MODE] Initializing VectorDB...")
        load_vectordb()
        print("✅ [API MODE] VectorDB ready")
    except Exception as e:
        print(f"❌ [API MODE] Init failed: {e}")


# ===================== CLI MODE =====================
def run_cli():
    session = "cli_session"

    print("\n" + "=" * 80)
    print(" CHATBOT PHÁP LÝ & KCN/CCN")
    print("=" * 80)

    load_vectordb()
    stats = get_vectordb_stats()
    print(f"VectorDB sẵn sàng ({stats['total_documents']} documents)\n")

    while True:
        try:
            message = input("👤 Bạn: ").strip()
            if not message:
                continue

            # MST
            if is_mst_query(message):
                print(handle_mst_query(message, llm=llm, embedding=emb))
                continue

            # Law count
            payload = handle_law_count_query(message)
            if isinstance(payload, dict):
                response = chatbot.invoke(
                    {
                        "message": message,
                        "law_count": payload["total_laws"]
                    },
                    config={"configurable": {"session_id": session}}
                )
                print(response)
                continue

            # Law article
            article = handle_law_article_query(message)
            if article:
                print(article)
                continue

            # Fallback
            response = chatbot.invoke(
                {"message": message},
                config={"configurable": {"session_id": session}}
            )
            print(response)

        except KeyboardInterrupt:
            print("\n👋 Tạm biệt!")
            break


# ===================== ENTRY POINT =====================
if __name__ == "__main__":
    run_cli()
