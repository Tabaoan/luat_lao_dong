# ===================== IMPORTS =====================
import os
import sys
import json
from typing import Dict
from pathlib import Path

from dotenv import load_dotenv
load_dotenv(override=True)

# LangChain
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langchain_core.runnables import RunnableLambda
from langchain_core.runnables.history import RunnableWithMessageHistory
# from langchain_community.chat_message_histories import ChatMessageHistory
from user_history.langchain_history import SupabaseChatMessageHistory
# Pinecone
from pinecone import Pinecone as PineconeClient
from langchain_pinecone import Pinecone

# Internal modules
from excel_query.excel_query import ExcelQueryHandler
from data_processing.pipeline import process_pdf_question
from law_db_query.handler import handle_law_article_query
from law_db_query.router import route_message
from mst.router import is_mst_query
from mst.handler import handle_mst_query

# ===================== EXCEL VISUALIZE =====================
from excel_visualize import (
    is_excel_visualize_intent,
    handle_excel_visualize
)

# ===================== law count response=====================
from law_db_query.handler import (
    handle_law_article_query,
    handle_law_count_query
)

# ===================== COMPARE 2018 =====================
from msn_2018.retriever import load_vsic_2018_retriever

# ===================== ENV =====================
OPENAI__API_KEY = os.getenv("OPENAI__API_KEY")
OPENAI__EMBEDDING_MODEL = os.getenv("OPENAI__EMBEDDING_MODEL")
OPENAI__MODEL_NAME = os.getenv("OPENAI__MODEL_NAME")
OPENAI__TEMPERATURE = os.getenv("OPENAI__TEMPERATURE")
LANG_MODEL_API_KEY = os.getenv("LANG_MODEL_API_KEY")
PINECONE_API_KEY = os.getenv("PINECONE_API_KEY")
PINECONE_INDEX_NAME = os.getenv("PINECONE_INDEX_NAME")

EXCEL_FILE_PATH = os.getenv("EXCEL_FILE_PATH")
#  Thêm biến GEOJSON để lấy tọa độ/geometry phục vụ map
GEOJSON_IZ_PATH = os.getenv("GEOJSON_FILE_PATH")

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
    temperature=0,
    max_tokens=4000,  # Tăng token limit
    streaming=False   # Tắt streaming
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
retriever_vsic_2018 = None


def load_vectordb():
    global vectordb, retriever, retriever_vsic_2018

    # ===== VSIC 2025 (hiện hành) =====
    if PINECONE_INDEX_NAME not in pc.list_indexes().names():
        print(f" Pinecone index '{PINECONE_INDEX_NAME}' không tồn tại")
        return None

    index = pc.Index(PINECONE_INDEX_NAME)
    stats = index.describe_index_stats()

    if stats["total_vector_count"] == 0:
        print(" Pinecone index rỗng")
        return None

    vectordb = Pinecone(index=index, embedding=emb, text_key="text")
    retriever = vectordb.as_retriever(search_kwargs={"k": 4})

    # ===== VSIC 2018 (đối chứng) =====
    try:
        retriever_vsic_2018 = load_vsic_2018_retriever(emb)
        print(" VSIC 2018 retriever sẵn sàng")
    except Exception as e:
        retriever_vsic_2018 = None
        print(f" Không load được VSIC 2018: {e}")

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


# ===================== INIT EXCEL (KCN/CCN + TỌA ĐỘ) =====================
excel_handler = None
if EXCEL_FILE_PATH and Path(EXCEL_FILE_PATH).exists():
    try:
        # ✅ Ưu tiên load có geojson để trả về "coordinates"
        if GEOJSON_IZ_PATH and Path(GEOJSON_IZ_PATH).exists():
            excel_handler = ExcelQueryHandler(
                excel_path=EXCEL_FILE_PATH,
                geojson_path=GEOJSON_IZ_PATH
            )
            print(f"✅ Excel + GeoJSON loaded:\n   - Excel: {EXCEL_FILE_PATH}\n   - GeoJSON: {GEOJSON_IZ_PATH}")
        else:
            # Fallback: chỉ Excel (có thể không có coordinates)
            excel_handler = ExcelQueryHandler(excel_path=EXCEL_FILE_PATH)
            print(f"⚠️ Excel loaded (NO GEOJSON): {EXCEL_FILE_PATH}")
            if not GEOJSON_IZ_PATH:
                print("⚠️ GEOJSON_IZ_PATH chưa set (không có toạ độ).")
            else:
                print(f"⚠️ GEOJSON_IZ_PATH không tồn tại: {GEOJSON_IZ_PATH}")
    except Exception as e:
        print(f"❌ Không thể load Excel: {e}")
else:
    if EXCEL_FILE_PATH:
        print(f"⚠️ EXCEL_FILE_PATH không tồn tại: {EXCEL_FILE_PATH}")
    else:
        print("⚠️ EXCEL_FILE_PATH chưa set.")


# ===================== PIPELINE WRAPPER =====================
from data_processing.pipeline import process_pdf_question

def pdf_dispatch(i: Dict):
    """
    Dispatcher cho chatbot:
    - Đảm bảo VectorDB đã load
    - Ưu tiên EXCEL KCN/CCN (trả JSON) trước LLM
    - Ưu tiên route_message
    - Fallback bắt buộc sang process_pdf_question
    """

    global retriever, retriever_vsic_2018

    if retriever is None:
        load_vectordb()

    # ===============================
    # ✅ EXCEL KCN/CCN (BẢNG + TỌA ĐỘ) - ƯU TIÊN TRƯỚC LLM
    # ===============================
    try:
        if excel_handler is not None:
            msg = i.get("message", "")
            handled, excel_payload = excel_handler.process_query(msg, return_json=True)
            # excel_payload là JSON string (đã gồm data[].coordinates + not_found_coordinates)
            if handled and excel_payload:
                return excel_payload
    except Exception as e:
        # Không làm chết pipeline nếu excel_query lỗi
        print(f"⚠️ ExcelQuery error (ignored): {e}")

    # 1️⃣ Thử route_message trước
    result = route_message(
        i,
        llm=llm,
        lang_llm=lang_llm,
        retriever=retriever,
        retriever_vsic_2018=retriever_vsic_2018,
        excel_handler=excel_handler
    )

    if isinstance(result, str) and result.strip():
        return result

    # 2️⃣ Fallback sang PDF pipeline
    return process_pdf_question(
        i,
        llm=llm,
        lang_llm=lang_llm,
        retriever=retriever,
        retriever_vsic_2018=retriever_vsic_2018,
        excel_handler=excel_handler
    )


pdf_chain = RunnableLambda(pdf_dispatch)

def get_history(session_id: str):
    # limit = số messages gần nhất (human+ai+system)
    return SupabaseChatMessageHistory(session_id=session_id, limit=40)


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
        get_history(session).clear()
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
            message = input(" Bạn: ").strip()
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
                    print(f"\n Bot:\n{mst_response}\n")
                    print("-" * 80)
                    continue

            # ================= EXCEL VISUALIZE INTENT =================
            if is_excel_visualize_intent(message):
                # Code mới (RAG tự quản lý data, không cần truyền handler vào):
                excel_response = handle_excel_visualize(message=message)
                # -----------------------

                if excel_response:
                    import json
                    try:
                        print(f"\n Bot (Visualize JSON):\n{json.dumps(excel_response, ensure_ascii=False, indent=2)}\n")
                    except:
                        print(f"\n Bot:\n{excel_response}\n")
                    
                    print("-" * 80)
                    continue

            # ================= EXCEL KCN/CCN (BẢNG + TỌA ĐỘ) =================
            if excel_handler is not None:
                handled, excel_payload = excel_handler.process_query(message, return_json=True)
                if handled and excel_payload:
                    # CLI in ra JSON (có coordinates)
                    try:
                        obj = json.loads(excel_payload) if isinstance(excel_payload, str) else excel_payload
                        print("\n Bot (excel_query JSON):\n" + json.dumps(obj, ensure_ascii=False, indent=2) + "\n")
                    except Exception:
                        print(f"\n Bot (excel_query JSON raw):\n{excel_payload}\n")
                    print("-" * 80)
                    continue

            # ====== CHECK LAW COUNT INTENT (SQL → LLM) ======
            payload = handle_law_count_query(message)
            if isinstance(payload, dict):
                response = chatbot.invoke(
                    {
                        "message": message,
                        "law_count": payload["total_laws"]
                    },
                    config={"configurable": {"session_id": session}}
                )
                print(f"\n Bot:\n{response}\n")
                print("-" * 80)
                continue

            # ====== CHECK LAW ARTICLE INTENT  ======
            law_article_response = handle_law_article_query(message)
            if law_article_response:
                print(f"\n Bot:\n{law_article_response}\n")
                print("-" * 80)
                continue

            # ====== FALLBACK TO NORMAL CHATBOT ======
            response = chatbot.invoke(
                {"message": message},
                config={"configurable": {"session_id": session}}
            )

            print(f"\n Bot: {response}\n")
            print("-" * 80)

        except KeyboardInterrupt:
            print("\n Tạm biệt!")
            break

        except Exception as e:
            print(f"\nLỗi: {e}\n")
