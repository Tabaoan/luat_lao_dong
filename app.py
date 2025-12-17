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
from law_db_query.handler import handle_law_article_query
from law_db_query.router import route_message
from mst.router import is_mst_query
from mst.handler import handle_mst_query

# ===================== ENV =====================
OPENAI__API_KEY = os.getenv("OPENAI__API_KEY")
OPENAI__EMBEDDING_MODEL = os.getenv("OPENAI__EMBEDDING_MODEL")
OPENAI__MODEL_NAME = os.getenv("OPENAI__MODEL_NAME")
OPENAI__TEMPERATURE = os.getenv("OPENAI__TEMPERATURE")
LANG_MODEL_API_KEY = os.getenv("LANG_MODEL_API_KEY")
PINECONE_API_KEY = os.getenv("PINECONE_API_KEY")
PINECONE_INDEX_NAME = os.getenv("PINECONE_INDEX_NAME")
EXCEL_FILE_PATH = os.getenv("EXCEL_FILE_PATH")
EMBEDDING_DIM = 3072


# ===================== INIT LLM =====================
llm = ChatOpenAI(
    api_key=OPENAI__API_KEY,
    model_name=OPENAI__MODEL_NAME,
    temperature=float(OPENAI__TEMPERATURE) if OPENAI__TEMPERATURE else 0
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
    print("Thiếu PINECONE_API_KEY")
    sys.exit(1)

pc = PineconeClient(api_key=PINECONE_API_KEY)

vectordb = None
retriever = None


def load_vectordb():
    global vectordb, retriever

    if PINECONE_INDEX_NAME not in pc.list_indexes().names():
        print(f" Pinecone index '{PINECONE_INDEX_NAME}' không tồn tại")
        return None

    index = pc.Index(PINECONE_INDEX_NAME)
    stats = index.describe_index_stats()

    if stats["total_vector_count"] == 0:
        print(" Pinecone index rỗng")
        return None

    vectordb = Pinecone(index=index, embedding=emb, text_key="text")
    retriever = vectordb.as_retriever(search_kwargs={"k": 15})
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
        print(f" Excel loaded: {EXCEL_FILE_PATH}")
    except Exception as e:
        print(f" Không thể load Excel: {e}")


# ===================== PIPELINE WRAPPER =====================
pdf_chain = RunnableLambda(
    lambda i: route_message(
        i,   # ⚠️ truyền CẢ dict, KHÔNG phải i["message"]
        llm=llm,
        lang_llm=lang_llm,
        retriever=retriever,
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


# ===================== CLI HELP =====================
def print_help():
    print("\n" + "=" * 60)
    print(" CÁC LỆNH CÓ SẴN")
    print("=" * 60)
    print(" - exit / quit  : Thoát")
    print(" - clear        : Xóa lịch sử hội thoại")
    print(" - status       : Trạng thái Pinecone")
    print(" - help         : Hướng dẫn")
    print("=" * 60 + "\n")


def handle_command(command: str, session: str) -> bool:
    cmd = command.lower().strip()

    if cmd in {"exit", "quit"}:
        print("\n Tạm biệt!")
        return False

    if cmd == "clear":
        store.get(session, ChatMessageHistory()).clear()
        print(" Đã xóa lịch sử\n")
        return True

    if cmd == "status":
        stats = get_vectordb_stats()
        print("\n" + "=" * 60)
        if stats.get("exists"):
            print(" Pinecone sẵn sàng")
            print(f" Documents: {stats['total_documents']}")
            print(f" Dimension: {stats['dimension']}")
        else:
            print(" Pinecone chưa sẵn sàng")
            if "error" in stats:
                print(f" {stats['error']}")
        print("=" * 60 + "\n")
        return True

    if cmd == "help":
        print_help()
        return True

    return True


# ===================== AUTO LOAD =====================
if __name__ != "__main__":
    load_vectordb()


# ===================== CLI MAIN =====================
if __name__ == "__main__":
    session = "pdf_reader_session"

    if not all([OPENAI__API_KEY, PINECONE_API_KEY, PINECONE_INDEX_NAME]):
        print(" Thiếu biến môi trường bắt buộc")
        sys.exit(1)

    print("\n" + "=" * 80)
    print(" CHATBOT PHÁP LÝ & KCN/CCN")
    print("=" * 80)
    print(f"Pinecone Index: {PINECONE_INDEX_NAME}\n")
    print_help()

    print(" Đang kết nối Pinecone...")
    if load_vectordb() is None:
        sys.exit(1)

    stats = get_vectordb_stats()
    print(f"VectorDB sẵn sàng ({stats['total_documents']} documents)\n")

    while True:
        try:
            message = input("👤 Bạn: ").strip()
            if not message:
                continue

            if not handle_command(message, session):
                break

            if message.lower() in {"clear", "status", "help"}:
                continue

            print(" Đang truy vấn...")
            # ====== CHECK MST INTENT ======
            if is_mst_query(message):
                mst_response = handle_mst_query(
                    message=message,
                    llm=llm,
                    embedding=emb
                )
                if mst_response:
                    print(f"\n🤖 Bot:\n{mst_response}\n")
                    print("-" * 80)
                    continue
            # ====== CHECK LAW ARTICLE INTENT ======
            law_response = handle_law_article_query(message)

            if law_response:
                print(f"\n🤖 Bot:\n{law_response}\n")
                print("-" * 80)
                continue

            # ====== FALLBACK TO NORMAL CHATBOT ======
            print(" Đang truy vấn...")
            response = chatbot.invoke(
                {"message": message},
                config={"configurable": {"session_id": session}}
            )

            print(f"\n🤖 Bot: {response}\n")
            print("-" * 80)

        except KeyboardInterrupt:
            print("\n Tạm biệt!")
            break

        except Exception as e:
            print(f"\nLỗi: {e}\n")
