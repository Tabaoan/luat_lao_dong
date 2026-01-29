# ===================== IMPORTS =====================
import os
import sys
import json
from typing import Dict
from pathlib import Path
from dotenv import load_dotenv
load_dotenv(override=True)
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langchain_core.runnables import RunnableLambda
from langchain_core.runnables.history import RunnableWithMessageHistory
from user_history.langchain_history import SupabaseChatMessageHistory
from pinecone import Pinecone as PineconeClient
from langchain_pinecone import Pinecone
from data_processing.pipeline import process_pdf_question
from law_db_query.handler import handle_law_article_query, handle_law_count_query
from law_db_query.router import route_message
from mst.router import is_mst_query
from mst.handler import handle_mst_query
from iz_agent.agent import agent_executor as iz_executor
from msn_2018.retriever import load_vsic_2018_retriever

# ===================== ENV =====================
OPENAI__API_KEY = os.getenv("OPENAI__API_KEY")
OPENAI__EMBEDDING_MODEL = os.getenv("OPENAI__EMBEDDING_MODEL")
OPENAI__MODEL_NAME = os.getenv("OPENAI__MODEL_NAME")
OPENAI__TEMPERATURE = os.getenv("OPENAI__TEMPERATURE")
LANG_MODEL_API_KEY = os.getenv("LANG_MODEL_API_KEY")
PINECONE_API_KEY = os.getenv("PINECONE_API_KEY")
PINECONE_INDEX_NAME = os.getenv("PINECONE_INDEX_NAME")

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

# ===================== ROUTER CHO IZ_AGENT =====================
def is_iz_agent_query(message: str) -> bool:
    """
    Router nhận diện câu hỏi liên quan đến BĐS Công Nghiệp (KCN/CCN)
    để chuyển hướng sang iz_agent xử lý.
    """
    keywords = [
        "kcn", "ccn", "khu công nghiệp", "cụm công nghiệp",
        "giá thuê", "giá đất", "diện tích", "biểu đồ", "so sánh", 
        "mật độ", "tỷ lệ lấp đầy", "chủ đầu tư", "vẽ biểu đồ",
        "danh sách", "liệt kê", "bao nhiêu", "ở đâu"
    ]
    # Kiểm tra xem câu hỏi có chứa keyword VÀ có ngữ cảnh công nghiệp không
    msg = message.lower()
    
    # Nếu câu hỏi chứa từ khóa cốt lõi thì bắt luôn
    core_hits = any(k in msg for k in keywords)
    
    # Nếu chỉ hỏi chung chung "vẽ biểu đồ" mà không nói gì thêm thì có thể để Agent xử lý
    # hoặc thêm logic chặt chẽ hơn nếu cần.
    return core_hits


# ===================== PIPELINE WRAPPER =====================
# (Đã xóa logic excel_handler cũ)
def pdf_dispatch(i: Dict):
    """
    Dispatcher cho các câu hỏi KHÔNG phải KCN/CCN (đã được lọc ở main loop).
    Chủ yếu xử lý Luật, PDF, RAG văn bản.
    """
    global retriever, retriever_vsic_2018

    if retriever is None:
        load_vectordb()

    # 1️⃣ Thử route_message (Luật/VSIC)
    result = route_message(
        i,
        llm=llm,
        lang_llm=lang_llm,
        retriever=retriever,
        retriever_vsic_2018=retriever_vsic_2018,
        excel_handler=None # Đã xóa handler cũ, truyền None
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
        excel_handler=None
    )


pdf_chain = RunnableLambda(pdf_dispatch)

def get_history(session_id: str):
    return SupabaseChatMessageHistory(session_id=session_id, limit=40)

chatbot = RunnableWithMessageHistory(
    pdf_chain,
    get_history,
    input_messages_key="message",
    history_messages_key="history"
)


# ===================== CLI HELPERS =====================
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


# ===================== MAIN APP =====================
if __name__ == "__main__":
    session = "user_session_v1"

    # Kiểm tra biến môi trường cơ bản (bỏ qua check excel path ở đây vì iz_agent tự lo)
    if not all([OPENAI__API_KEY, PINECONE_API_KEY, PINECONE_INDEX_NAME]):
        print(" Thiếu biến môi trường bắt buộc (OpenAI/Pinecone)")
        sys.exit(1)

    print("\n" + "=" * 80)
    print(" HỆ THỐNG TRỢ LÝ ẢO TỔNG HỢP")
    print(" (Hỗ trợ: KCN/CCN, Luật, PDF, Mã số thuế)")
    print("=" * 80)
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

            print(" Đang xử lý...")

            # ==================================================================
            # 1. KIỂM TRA MÃ SỐ THUẾ (MST)
            # ==================================================================
            if is_mst_query(message):
                mst_response = handle_mst_query(
                    message=message,
                    llm=llm,
                    embedding=emb
                )
                if mst_response:
                    print(f"\n Bot (MST):\n{mst_response}\n")
                    print("-" * 80)
                    continue

            # ==================================================================
            # 2. KIỂM TRA IZ_AGENT (KCN/CCN) - ĐÃ SỬA LỖI NHỚ CONTEXT
            # ==================================================================
            if iz_executor and is_iz_agent_query(message):
                try:
                    # [FIX 1] Lấy quản lý lịch sử cho session hiện tại
                    history_manager = get_history(session)
                    
                    # [FIX 2] Lấy danh sách tin nhắn cũ để truyền vào Agent
                    # (Lấy 10 tin gần nhất để tiết kiệm token nhưng vẫn đủ nhớ)
                    current_messages = history_manager.messages[-10:] if history_manager.messages else []

                    # [FIX 3] Truyền lịch sử vào Agent
                    iz_result = iz_executor.invoke({
                        "input": message,
                        "chat_history": current_messages 
                    })
                    
                    output_text = iz_result.get("output", "Không có phản hồi.")
                    
                    print(f"\n Bot (IIP Agent):\n{output_text}\n")
                    
                    # [FIX 4] QUAN TRỌNG: Lưu hội thoại này vào lịch sử
                    # Vì ta gọi Agent thủ công nên phải tự lưu, nếu không câu sau sẽ quên câu này.
                    history_manager.add_user_message(message)
                    history_manager.add_ai_message(output_text)
                    
                except Exception as e:
                    print(f"⚠️ Lỗi IIP Agent: {e}")
                
                print("-" * 80)
                continue

            # ==================================================================
            # 3. KIỂM TRA LUẬT (Count Query)
            # ==================================================================
            payload = handle_law_count_query(message)
            if isinstance(payload, dict):
                response = chatbot.invoke(
                    {
                        "message": message,
                        "law_count": payload["total_laws"]
                    },
                    config={"configurable": {"session_id": session}}
                )
                print(f"\n Bot (Law):\n{response}\n")
                print("-" * 80)
                continue

            # ==================================================================
            # 4. KIỂM TRA ĐIỀU LUẬT CỤ THỂ
            # ==================================================================
            law_article_response = handle_law_article_query(message)
            if law_article_response:
                print(f"\n Bot (Article):\n{law_article_response}\n")
                print("-" * 80)
                continue

            # ==================================================================
            # 5. FALLBACK (PDF RAG / CHAT CHUNG)
            # ==================================================================
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
            print(f"\nLỗi hệ thống: {e}\n")