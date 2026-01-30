# ===================== IMPORTS =====================
import os
import sys
from typing import Dict
from dotenv import load_dotenv
load_dotenv(override=True)

from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langchain_core.runnables import RunnableLambda
from langchain_core.runnables.history import RunnableWithMessageHistory
from user_history.langchain_history import SupabaseChatMessageHistory

# --- SỬ DỤNG THƯ VIỆN COMMUNITY (ỔN ĐỊNH NHẤT) ---
from qdrant_client import QdrantClient
from langchain_community.vectorstores import Qdrant
# -------------------------------------------------

from data_processing.pipeline import process_pdf_question
from iz_agent.agent import agent_executor as iz_executor

# ===================== ENV =====================
OPENAI__API_KEY = os.getenv("OPENAI__API_KEY")
OPENAI__EMBEDDING_MODEL = os.getenv("OPENAI__EMBEDDING_MODEL")
OPENAI__MODEL_NAME = os.getenv("OPENAI__MODEL_NAME")
OPENAI__TEMPERATURE = os.getenv("OPENAI__TEMPERATURE")
LANG_MODEL_API_KEY = os.getenv("LANG_MODEL_API_KEY")

QDRANT_URL = os.getenv("QDRANT_URL") 
QDRANT_COLLECTION_NAME = os.getenv("QDRANT_COLLECTION_NAME") 

# ===================== INIT CLIENTS =====================
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

emb = OpenAIEmbeddings(
    api_key=OPENAI__API_KEY,
    model=OPENAI__EMBEDDING_MODEL
)

if not QDRANT_URL:
    print("Thiếu QDRANT_URL")
    sys.exit(1)

# Khởi tạo Client (Đã xóa các tham số gây lỗi compatibility)
try:
    qdrant_client = QdrantClient(
        url=QDRANT_URL,
        api_key=None,
        timeout=60
    )
except Exception as e:
    print(f"❌ Lỗi khởi tạo Client: {e}")
    sys.exit(1)

vectordb = None
retriever = None

def load_vectordb():
    global vectordb, retriever

    try:
        # 1. Kiểm tra Qdrant
        if not qdrant_client.collection_exists(QDRANT_COLLECTION_NAME):
            print(f"❌ Collection '{QDRANT_COLLECTION_NAME}' không tồn tại!")
            return None

        # 2. Tạo Retriever
        # [QUAN TRỌNG] Đây là đoạn sửa lỗi "validation error"
        vectordb = Qdrant(
            client=qdrant_client,
            collection_name=QDRANT_COLLECTION_NAME,
            embeddings=emb,           # Lưu ý: Class cũ dùng 'embeddings' (số nhiều)
            content_payload_key="Content"  # <--- FIX LỖI: Chỉ định đúng tên trường dữ liệu
        )
        
        retriever = vectordb.as_retriever(search_kwargs={"k": 4})
        return vectordb
    except Exception as e:
        print(f"❌ Lỗi load VectorDB: {e}")
        return None

def get_vectordb_stats() -> Dict:
    try:
        if qdrant_client.collection_exists(QDRANT_COLLECTION_NAME):
            info = qdrant_client.get_collection(QDRANT_COLLECTION_NAME)
            return {
                "exists": True,
                "total_documents": info.points_count,
            }
        else:
            return {"exists": False, "total_documents": 0}
    except Exception as e:
        return {"exists": False, "error": str(e)}

# ===================== ROUTER =====================
def is_iz_agent_query(message: str) -> bool:
    """Router nhận diện câu hỏi BĐS Công nghiệp"""
    keywords = [
        "kcn", "ccn", "khu công nghiệp", "cụm công nghiệp",
        "giá thuê", "giá đất", "diện tích", "biểu đồ", "so sánh", 
        "mật độ", "tỷ lệ lấp đầy", "chủ đầu tư", "vẽ biểu đồ",
        "danh sách", "liệt kê", "bao nhiêu", "ở đâu"
    ]
    msg = message.lower()
    return any(k in msg for k in keywords)

# ===================== PIPELINE =====================
def pdf_dispatch(i: Dict):
    global retriever

    if retriever is None:
        load_vectordb()

    return process_pdf_question(
        i,
        llm=llm,
        lang_llm=lang_llm,
        retriever=retriever,
        retriever_vsic_2018=None, 
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

# ===================== HELPERS =====================
def print_help():
    print("\n" + "=" * 40)
    print(" LỆNH: exit, clear, status, help")
    print("=" * 40 + "\n")

def handle_command(command: str, session: str) -> bool:
    cmd = command.lower().strip()
    if cmd in {"exit", "quit"}: return False
    if cmd == "clear":
        get_history(session).clear()
        print("Đã xóa lịch sử.")
        return True
    if cmd == "status":
        stats = get_vectordb_stats()
        print(f"Qdrant Docs: {stats.get('total_documents', 'N/A')}")
        return True
    if cmd == "help": print_help(); return True
    return True

# ===================== MAIN =====================
if __name__ == "__main__":
    session = "user_session_v1"

    if not all([OPENAI__API_KEY, QDRANT_URL, QDRANT_COLLECTION_NAME]):
        print("Thiếu biến môi trường!")
        sys.exit(1)

    print("\n=== HỆ THỐNG TRỢ LÝ ẢO (AGENT & QDRANT) ===")
    print("Đang kết nối Qdrant...")
    
    if load_vectordb() is None:
        print("⚠️ Không thể tải Collection Qdrant.")
    else:
        print(f"✅ Sẵn sàng! Collection: {QDRANT_COLLECTION_NAME}\n")

    while True:
        try:
            message = input("Bạn: ").strip()
            if not message: continue
            if not handle_command(message, session): break

            print("Đang xử lý...")

            # 1. NHÁNH AGENT (KCN/CCN)
            if iz_executor and is_iz_agent_query(message):
                try:
                    hist = get_history(session)
                    msgs = hist.messages[-10:] if hist.messages else []
                    
                    res = iz_executor.invoke({
                        "input": message,
                        "chat_history": msgs
                    })
                    output = res.get("output", "Lỗi phản hồi Agent")
                    
                    print(f"\nBot (Agent): {output}\n")
                    print("-" * 50)
                    
                    hist.add_user_message(message)
                    hist.add_ai_message(output)
                    continue
                except Exception as e:
                    print(f"Lỗi Agent: {e}")

            # 2. NHÁNH QDRANT (HỎI ĐÁP RAG)
            response = chatbot.invoke(
                {"message": message},
                config={"configurable": {"session_id": session}}
            )
            print(f"\nBot: {response}\n")
            print("-" * 50)

        except KeyboardInterrupt:
            break
        except Exception as e:
            print(f"Lỗi hệ thống: {e}")