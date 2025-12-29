# ===================== IMPORTS =====================
import os, re, io
from typing import Dict, Any, List
from pathlib import Path
import sys 

# GOOGLE SHEETS
try:
    import gspread
    import datetime
except ImportError:
    print("❌ Lỗi: Cần cài đặt thư viện 'gspread' (pip install gspread).")
    sys.exit(1)

from dotenv import load_dotenv
load_dotenv(override=True)

from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langchain_core.runnables import RunnableLambda
from langchain_core.runnables.history import RunnableWithMessageHistory
from langchain_community.chat_message_histories import ChatMessageHistory
from langchain_core.documents import Document
from langchain_pinecone import Pinecone 
from pinecone import Pinecone as PineconeClient
from langchain_core.messages import SystemMessage, HumanMessage, BaseMessage, AIMessage 

# EXCEL MODULE
from excel_query.excel_query import ExcelQueryHandler

# ❌ LOẠI BỎ LANGDETECT
# from langdetect import detect


# ===================== ENV =====================
OPENAI__API_KEY = os.getenv("OPENAI__API_KEY")
OPENAI__EMBEDDING_MODEL = os.getenv("OPENAI__EMBEDDING_MODEL")
OPENAI__MODEL_NAME = os.getenv("OPENAI__MODEL_NAME")
OPENAI__TEMPERATURE = os.getenv("OPENAI__TEMPERATURE")

# API KEY RIÊNG CHO DETECT + TRANSLATE
LANG_MODEL_API_KEY = os.getenv("LANG_MODEL_API_KEY")

# PINECONE
PINECONE_API_KEY = os.getenv("PINECONE_API_KEY")
PINECONE_ENVIRONMENT = os.getenv("PINECONE_ENVIRONMENT")
PINECONE_INDEX_NAME = os.getenv("PINECONE_INDEX_NAME")
EMBEDDING_DIM = 3072 

# GOOGLE SHEET
GOOGLE_SHEET_ID = os.getenv("GOOGLE_SHEET_ID")
GOOGLE_SERVICE_ACCOUNT_FILE = os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE") 

# FILE EXCEL
EXCEL_FILE_PATH = os.getenv("EXCEL_FILE_PATH")


# ===================== KHỞI TẠO LLM =====================
# LLM chính (trả lời)
llm = ChatOpenAI(
    api_key=OPENAI__API_KEY,
    model_name=OPENAI__MODEL_NAME,
    temperature=float(OPENAI__TEMPERATURE) if OPENAI__TEMPERATURE else 0
)

# LLM detect + translate (API KEY riêng)
lang_llm = ChatOpenAI(
    api_key=LANG_MODEL_API_KEY,
    model_name="gpt-4o-mini",
    temperature=0
)


# ===================== KHỞI TẠO PINECONE =====================
if PINECONE_API_KEY:
    pc = PineconeClient(api_key=PINECONE_API_KEY)
else:
    pc = None
    print("❌ Lỗi: Không tìm thấy PINECONE_API_KEY.")

emb = OpenAIEmbeddings(api_key=OPENAI__API_KEY, model=OPENAI__EMBEDDING_MODEL)

vectordb = None
retriever = None


# ===================== EXCEL HANDLER =====================
excel_handler = None
if EXCEL_FILE_PATH and Path(EXCEL_FILE_PATH).exists():
    try:
        excel_handler = ExcelQueryHandler(EXCEL_FILE_PATH)
        print(f"✅ Đã load Excel Handler: {EXCEL_FILE_PATH}")
    except Exception as e:
        print(f"⚠️ Không thể load Excel: {e}")
else:
    print(f"⚠️ Không tìm thấy file Excel: {EXCEL_FILE_PATH}")


# ===================== SYSTEM PROMPT =====================
PDF_READER_SYS = (
    "Bạn là một trợ lý AI pháp lý chuyên đọc hiểu và tra cứu các tài liệu được cung cấp "
    "(bao gồm: Luật, Nghị định, Quyết định, Thông tư, Văn bản hợp nhất, Quy hoạch, Danh mục khu công nghiệp, v.v.). "
    "Nhiệm vụ của bạn là trích xuất và trả lời chính xác các thông tin có trong tài liệu, "
    "đặc biệt liên quan đến Lao động, Dân sự và các Khu công nghiệp, Cụm công nghiệp tại Việt Nam.\n\n"

    "⚙️ QUY TẮC ĐẶC BIỆT:\n"
    "- Nếu người dùng chỉ chào hỏi hoặc đặt câu hỏi chung chung (ví dụ: 'xin chào', 'bạn làm được gì', 'giúp tôi với'...), "
    "hãy trả lời nguyên văn như sau:\n"
    "'Xin chào! Mình là Chatbot Cổng việc làm Việt Nam. Mình có thể giúp anh/chị tra cứu và giải thích các quy định pháp luật "
    "(luật, nghị định, thông tư...) liên quan đến lao động, việc làm, dân sự và các lĩnh vực pháp lý khác. "
    "Gõ câu hỏi cụ thể hoặc mô tả tình huống nhé — mình sẽ trả lời ngắn gọn, có dẫn nguồn.'\n\n"

    "📘 NGUYÊN TẮC CHUNG KHI TRẢ LỜI:\n"
    "1) Phân loại câu hỏi:\n"
    "   - Câu hỏi CHUNG CHUNG hoặc NGOÀI TÀI LIỆU: Trả lời ngắn gọn (1-3 câu), lịch sự, không đi sâu vào chi tiết.\n"
    "   - Câu hỏi VỀ LUẬT/NGHỊ ĐỊNH hoặc TRONG TÀI LIỆU: Trả lời tất cả, đầy đủ, chi tiết, chính xác theo đúng nội dung tài liệu.\n\n"

    "2) Phạm vi: Chỉ dựa vào nội dung trong các tài liệu đã được cung cấp; tuyệt đối không sử dụng hoặc suy diễn kiến thức bên ngoài.\n\n"

    "3) Nguồn trích dẫn: \n"
    "   - Khi trả lời về luật, nghị định: Ghi rõ nguồn (ví dụ: Theo Điều X, Nghị định số Y/NĐ-CP...).\n"
    "   - TUYỆT ĐỐI KHÔNG được ghi theo dạng [1], [2], [3]...\n"
    "   - TUYỆT ĐỐI KHÔNG được sử dụng cụm từ: 'tài liệu PDF', 'trích từ tài liệu PDF', 'dưới đây là thông tin từ tài liệu PDF', hoặc các cụm tương tự.\n"
    "   - Thay vào đó, nêu trực tiếp: 'Theo Luật Việc làm quy định...', 'Nghị định số X/NĐ-CP nêu rõ...'\n\n"

    "4) Ngôn ngữ: Sử dụng văn phong pháp lý, trung lập, rõ ràng và tôn trọng ngữ điệu hành chính.\n\n"

    "5) Trình bày: \n"
    "   - Ưu tiên danh sách (số thứ tự hoặc gạch đầu dòng) để dễ theo dõi.\n"
    "   - TUYỆT ĐỐI KHÔNG sử dụng ký hiệu in đậm (** hoặc __) trong bất kỳ phần trả lời nào.\n\n"

    "6) Nếu câu hỏi mơ hồ: Yêu cầu người dùng làm rõ hoặc bổ sung chi tiết để trả lời chính xác hơn.\n\n"

    "🏭 QUY ĐỊNH RIÊNG ĐỐI VỚI CÁC KHU CÔNG NGHIỆP / CỤM CÔNG NGHIỆP:\n"
    "1) Nếu người dùng hỏi 'Tỉnh/thành phố nào có bao nhiêu khu hoặc cụm công nghiệp', "
    "hãy trả lời theo định dạng sau:\n"
    "   - Số lượng khu/cụm công nghiệp trong tỉnh hoặc thành phố đó.\n"
    "   - Danh sách tên của tất cả các khu/cụm.\n\n"

    "2) Nếu người dùng hỏi chi tiết về một khu/cụm công nghiệp cụ thể, hãy trình bày đầy đủ thông tin (nếu có trong tài liệu), gồm:\n"
    "   - Tên khu công nghiệp hoặc cụm công nghiệp\n"
    "   - Địa điểm\n"
    "   - Diện tích\n"
    "   - Cơ quan quản lý hoặc chủ đầu tư\n"
    "   - Quyết định thành lập hoặc phê duyệt quy hoạch\n"
    "   - Ngành nghề hoạt động chính\n"
    "   - Tình trạng hoạt động (đang hoạt động / đang quy hoạch / đang xây dựng)\n"
    "   - Các thông tin khác (nếu có)\n\n"

    "🌐 QUY TẮC NGÔN NGỮ:\n"
    "- Luôn trả lời đúng theo NGÔN NGỮ của câu hỏi cuối cùng.\n"
    "- Nếu tài liệu là tiếng Việt nhưng người dùng hỏi bằng ngôn ngữ khác, "
    "hãy dịch phần thông tin trích xuất sang ngôn ngữ của người dùng trước khi trình bày.\n"
    "- Không được trả lời bằng tiếng Việt nếu người dùng không dùng tiếng Việt.\n"
    "- Không thay đổi chủ đề hoặc thêm thông tin ngoài tài liệu.\n"
    "- Luôn sử dụng đúng ngôn ngữ được định nghĩa trong metadata 'user_lang'.\n\n"

    "🏢 QUY ĐỊNH VỀ THUÊ ĐẤT TRONG KCN – CCN:\n"
    "1) Trả lời chi tiết theo tài liệu khi hỏi về điều kiện, thủ tục, hồ sơ, quy trình thuê đất.\n"
    "2) Nếu hỏi về quỹ đất trống hoặc diện tích còn cho thuê:\n"
    "   - Có trong tài liệu: trả lời đầy đủ.\n"
    "   - Không có trong tài liệu: thông báo tài liệu không chứa thông tin.\n"
    "3) Nếu hỏi 'khu/cụm nào còn đất', trả lời dựa trên tình trạng ghi trong tài liệu.\n"
    "4) Không được tự suy diễn về giá thuê, tình trạng đất nếu tài liệu không có.\n"
    "5) Nếu câu hỏi trước đó không nhắc tỉnh thành nào và người dùng hỏi chung, được phép chọn ngẫu nhiên một tỉnh để trả lời.\n\n"

    "🧾 QUY ĐỊNH RIÊNG VỀ CÂU HỎI LIÊN QUAN ĐẾN MÃ SỐ THUẾ (MST):\n"
    "Khi người dùng yêu cầu tra cứu mã số thuế (ví dụ: 'Tra cứu mã số thuế công ty ABC', 'MST của công ty XYZ', 'Mã số thuế 0312345678 là của ai'), "
    "bạn phải trả lời ĐẦY ĐỦ các trường sau (nếu dữ liệu có trong hệ thống):\n"
    "   - Mã số thuế\n"
    "   - Tên công ty\n"
    "   - Địa chỉ trụ sở chính\n"
    "   - Tình trạng hoạt động\n"
    "   - Ngày hoạt động hoặc ngày cấp phép\n"
    "   - Người đại diện pháp luật\n"
    "   - Các thông tin bổ sung khác (nếu có)\n"
    "Không được trả lời thiếu bất kỳ trường nào nếu dữ liệu có tồn tại.\n\n"

    "🎯 TÓM TẮT:\n"
    "- Câu hỏi chung chung/ngoài tài liệu → trả lời ngắn gọn.\n"
    "- Câu hỏi pháp luật/KCN/CCN → trả lời đầy đủ dựa trên tài liệu.\n"
    "- Câu hỏi tra cứu mã số thuế → trả lời đủ 6 trường (MST, tên, địa chỉ, tình trạng, ngày hoạt động, người đại diện).\n"
    "- Luôn viết theo ngôn ngữ người dùng.\n"
)



# ===================== VECTORDB UTILS =====================
def build_context_from_hits(hits, max_chars: int = 6000) -> str:
    ctx = []
    total = 0
    for idx, h in enumerate(hits, start=1):
        source = h.metadata.get("source", "unknown")
        seg = f"[Nguồn: {source}, Trang: {h.metadata.get('page', '?')}]\n{h.page_content.strip()}"
        if total + len(seg) > max_chars:
            break
        ctx.append(seg)
        total += len(seg)
    return "\n\n".join(ctx)


def check_vectordb_exists() -> bool:
    global pc, vectordb, retriever
    if pc is None or not PINECONE_INDEX_NAME:
        return False
    try:
        if PINECONE_INDEX_NAME not in pc.list_indexes().names():
            return False
        index = pc.Index(PINECONE_INDEX_NAME)
        stats = index.describe_index_stats()
        if stats["total_vector_count"] > 0:
            if vectordb is None:
                vectordb = Pinecone(index=index, embedding=emb, text_key="text")
                retriever = vectordb.as_retriever(search_kwargs={"k": 15})
            return True
        return False
    except:
        return False


def get_vectordb_stats() -> Dict[str, Any]:
    global pc
    if pc is None:
        return {"total_documents": 0, "exists": False}
    try:
        index = pc.Index(PINECONE_INDEX_NAME)
        stats = index.describe_index_stats()
        return {
            "total_documents": stats["total_vector_count"],
            "exists": stats["total_vector_count"] > 0,
            "dimension": stats.get("dimension", EMBEDDING_DIM)
        }
    except Exception as e:
        return {"total_documents": 0, "exists": False, "error": str(e)}


def load_vectordb():
    global vectordb, retriever, pc
    if pc is None:
        print("❌ Pinecone Client chưa được khởi tạo.")
        return None
    try:
        if PINECONE_INDEX_NAME not in pc.list_indexes().names():
            print(f"❌ Index '{PINECONE_INDEX_NAME}' không tồn tại.")
            return None
        index = pc.Index(PINECONE_INDEX_NAME)
        stats = index.describe_index_stats()
        if stats["total_vector_count"] == 0:
            print("❌ Index rỗng.")
            return None
        vectordb = Pinecone(index=index, embedding=emb, text_key="text")
        retriever = vectordb.as_retriever(search_kwargs={"k": 15})
        return vectordb
    except Exception as e:
        print("❌ Lỗi load Pinecone:", e)
        return None


# ===================== CLEANING =====================
_URL_RE = re.compile(r"https?://[^\s]+", re.IGNORECASE)

def clean_question_remove_uris(text: str) -> str:
    """Loại bỏ URL + PDF khỏi câu hỏi."""
    txt = _URL_RE.sub(" ", text or "")
    toks = re.split(r"\s+", txt)
    toks = [t for t in toks if not t.lower().endswith(".pdf")]
    return " ".join(toks).strip()


# ===================== NGÔN NGỮ: DETECT + TRANSLATE =====================

def detect_language_openai(text: str) -> str:
    """
    Phát hiện ngôn ngữ bằng OpenAI (LANG_MODEL_API_KEY).
    Trả về mã ISO-639-1 (vi, en, ko, ja, zh, fr, es...).
    """
    try:
        res = lang_llm.invoke([
            SystemMessage(content=(
                "Bạn là module phát hiện ngôn ngữ. "
                "Chỉ trả về mã ISO-639-1: vi, en, ja, ko, zh, fr, es... "
                "KHÔNG giải thích, KHÔNG thêm chữ nào khác."
            )),
            HumanMessage(content=text)
        ]).content

        return res.strip().lower()
    except Exception as e:
        print("⚠️ Lỗi detect ngôn ngữ:", e)
        return "vi"


def convert_language(text: str, target_lang: str) -> str:
    """
    Dịch câu trả lời sang ngôn ngữ người dùng bằng LANG_MODEL_API_KEY.
    """
    lang_mapping = {
        "vi": "Tiếng Việt",
        "en": "English",
        "ko": "Korean",
        "ja": "Japanese",
        "zh": "Chinese",
        "fr": "French",
        "de": "German",
        "es": "Spanish",
        "th": "Thai"
    }

    target_lang_name = lang_mapping.get(target_lang, target_lang)

    try:
        translated = lang_llm.invoke([
            SystemMessage(content="Bạn là một phiên dịch chuyên nghiệp. Chỉ trả về bản dịch, không giải thích."),
            HumanMessage(
                content=(
                    f"Dịch nội dung sau sang {target_lang_name} ({target_lang}):\n\n"
                    f"{text}\n\n"
                    f"Chỉ trả về bản dịch."
                )
            )
        ]).content

        return translated.strip()
    except Exception as e:
        print("⚠️ Lỗi dịch ngôn ngữ:", e)
        return text


# ===================== PIPELINE CHÍNH =====================
def process_pdf_question(i: Dict[str, Any]) -> str:
    """Excel → VectorDB → LLM → Dịch nếu cần"""
    global retriever

    message = i["message"]
    history: List[BaseMessage] = i.get("history", [])

    clean_question = clean_question_remove_uris(message)

    # 1️⃣ PHÁT HIỆN NGÔN NGỮ VỚI OPENAI
    try:
        user_lang = detect_language_openai(message)
    except:
        user_lang = "vi"

    # 2️⃣ ƯU TIÊN EXCEL HANDLER
    if excel_handler is not None:
        try:
            handled, excel_response = excel_handler.process_query(clean_question)
            if handled and excel_response:
                if user_lang != "vi":
                    excel_response = convert_language(excel_response, user_lang)
                return excel_response
        except Exception as e:
            print("⚠️ Lỗi Excel Query:", e)

    # 3️⃣ KIỂM TRA VECTORDB READY CHƯA
    if retriever is None:
        msg = "❌ VectorDB chưa sẵn sàng, không thể truy vấn dữ liệu."
        return convert_language(msg, user_lang) if user_lang != "vi" else msg

    # 4️⃣ TRUY VẤN VECTORDB
    try:
        hits = retriever.invoke(clean_question)

        if not hits:
            msg = "Xin lỗi, tôi không tìm thấy thông tin liên quan trong dữ liệu."
            return convert_language(msg, user_lang) if user_lang != "vi" else msg

        context = build_context_from_hits(hits, max_chars=6000)

        # 5️⃣ PROMPT SYSTEM ĐẶC BIỆT
        system_prompt_with_lang = (
            PDF_READER_SYS +
            f"\n\n🌍 Người dùng đang dùng ngôn ngữ: '{user_lang}'. "
            f"Hãy trả lời đúng ngôn ngữ này."
        )

        messages = [SystemMessage(content=system_prompt_with_lang)]

        # Lấy lịch sử 10 tin nhắn gần nhất
        if history:
            messages.extend(history[-10:])

        # USER MESSAGE
        full_user_message = f"""
Câu hỏi: {clean_question}

Nội dung liên quan từ tài liệu:
{context}

Hãy trả lời bằng ngôn ngữ: {user_lang}.
"""
        messages.append(HumanMessage(content=full_user_message))

        # 6️⃣ TRẢ LỜI BẰNG LLM CHÍNH
        response = llm.invoke(messages).content

        # 7️⃣ NẾU NGÔN NGỮ OUTPUT KHÔNG KHỚP → DỊCH LẠI
        try:
            detected_lang = detect_language_openai(response)
            if detected_lang != user_lang:
                response = convert_language(response, user_lang)
        except:
            response = convert_language(response, user_lang)

        return response

    except Exception as e:
        msg = f"❌ Lỗi xử lý: {str(e)}"
        return convert_language(msg, user_lang) if user_lang != "vi" else msg

# ===================== MAIN CHATBOT =====================
pdf_chain = RunnableLambda(process_pdf_question)
store: Dict[str, ChatMessageHistory] = {}


def get_history(session_id: str):
    """Lấy hoặc tạo lịch sử chat cho session."""
    if session_id not in store:
        store[session_id] = ChatMessageHistory()
    return store[session_id]


chatbot = RunnableWithMessageHistory(
    pdf_chain,
    get_history,
    input_messages_key="message",
    history_messages_key="history"
)


# ===================== CLI HƯỚNG DẪN =====================
def print_help():
    """In hướng dẫn sử dụng CLI."""
    print("\n" + "=" * 60)
    print("📚 CÁC LỆNH CÓ SẴN:")
    print("=" * 60)
    print(" - exit / quit  : Thoát chương trình")
    print(" - clear        : Xóa lịch sử hội thoại")
    print(" - status       : Kiểm tra trạng thái Pinecone Index")
    print(" - help         : Hiển thị hướng dẫn này")
    print("=" * 60 + "\n")


# ===================== XỬ LÝ LỆNH CLI =====================
def handle_command(command: str, session: str) -> bool:
    """Xử lý các lệnh đặc biệt."""
    cmd = command.lower().strip()

    if cmd in {"exit", "quit"}:
        print("\n👋 Tạm biệt! Hẹn gặp lại!")
        return False

    elif cmd == "clear":
        if session in store:
            store[session].clear()
            print("🧹 Đã xóa lịch sử hội thoại.\n")
        return True

    elif cmd == "status":
        stats = get_vectordb_stats()
        print("\n" + "=" * 60)
        print("📊 TRẠNG THÁI PINECONE INDEX")
        print("=" * 60)
        if stats.get("exists", False):
            print("✅ Trạng thái: Sẵn sàng")
            print(f"📚 Tổng documents: {stats['total_documents']}")
            print(f"📏 Dimension: {stats['dimension']}")
        else:
            print("❌ Chưa sẵn sàng hoặc không có dữ liệu.")
            if "error" in stats:
                print(f"⚠️ Lỗi: {stats['error']}")
        print("=" * 60 + "\n")
        return True

    elif cmd == "help":
        print_help()
        return True

    else:
        return True


# ===================== AUTO LOAD KHI IMPORT =====================
if __name__ != "__main__":
    print("📦 Tự động load Pinecone khi import app.py...")
    load_vectordb()


# ===================== CLI =====================
if __name__ == "__main__":
    session = "pdf_reader_session"

    # Kiểm tra môi trường bắt buộc
    if not all([OPENAI__API_KEY, PINECONE_API_KEY, PINECONE_INDEX_NAME]):
        print("❌ LỖI CẤU HÌNH: Thiếu biến môi trường.")
        print("Cần có: OPENAI__API_KEY, PINECONE_API_KEY, PINECONE_INDEX_NAME.")
        sys.exit(1)

    print("\n" + "=" * 80)
    print("🤖 CHATBOT PHÁP LÝ & KCN/CCN")
    print("=" * 80)
    print(f"☁️ Pinecone Index: {PINECONE_INDEX_NAME}")
    print("🔍 Hỗ trợ: Luật Lao động, Dân sự, KCN/CCN Việt Nam\n")
    print_help()

    # Kết nối Pinecone
    print("📥 Đang kết nối đến Pinecone...")
    result = load_vectordb()

    if result is None:
        print("❌ KHÔNG THỂ LOAD PINECONE INDEX. Vui lòng kiểm tra lại cấu hình.")
        sys.exit(1)

    stats = get_vectordb_stats()
    print(f"✅ VectorDB đã sẵn sàng với {stats.get('total_documents', 0)} documents.\n")
    print("💬 Bot đã sẵn sàng! (Gõ 'help' để xem hướng dẫn)\n")

    # Vòng lặp chính CLI
    while True:
        try:
            message = input("👤 Bạn: ").strip()

            if not message:
                continue

            # Xử lý lệnh CLI
            if not handle_command(message, session):
                break

            if message.lower() in ["clear", "status", "help"]:
                continue

            print("🔎 Đang tìm kiếm trong Pinecone Index...")

            response = chatbot.invoke(
                {"message": message},
                config={"configurable": {"session_id": session}}
            )

            print(f"\n🤖 Bot: {response}\n")
            print("-" * 80 + "\n")

        except KeyboardInterrupt:
            print("\n\n👋 Tạm biệt!")
            break

        except Exception as e:
            print(f"\n❌ Lỗi: {e}\n")
