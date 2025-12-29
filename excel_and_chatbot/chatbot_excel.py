# ===================== IMPORTS =====================
import os, re, io
from typing import Dict, Any, List
from pathlib import Path
import sys 

# ⬅️ THÊM THƯ VIỆN GOOGLE SHEETS
try:
    import gspread
    import datetime
except ImportError:
    print("❌ Lỗi: Cần cài đặt thư viện 'gspread' (pip install gspread).")
    sys.exit(1)
# ⬅️ THÊM IMPORT MODULE EXCEL
from excel_query.excel_query import ExcelQueryHandler

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


# ===================== ENV =====================
OPENAI__API_KEY = os.getenv("OPENAI__API_KEY")
OPENAI__EMBEDDING_MODEL = os.getenv("OPENAI__EMBEDDING_MODEL")
OPENAI__MODEL_NAME = os.getenv("OPENAI__MODEL_NAME")
OPENAI__TEMPERATURE = os.getenv("OPENAI__TEMPERATURE")

# ⬅️ THÊM BIẾN MÔI TRƯỜNG PINECONE
PINECONE_API_KEY = os.getenv("PINECONE_API_KEY")
PINECONE_ENVIRONMENT = os.getenv("PINECONE_ENVIRONMENT")
PINECONE_INDEX_NAME = os.getenv("PINECONE_INDEX_NAME")
EMBEDDING_DIM = 3072 

# ⬅️ THÊM BIẾN MÔI TRƯỜNG GOOGLE SHEET
GOOGLE_SHEET_ID = os.getenv("GOOGLE_SHEET_ID")
GOOGLE_SERVICE_ACCOUNT_FILE = os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE") 

# ⬅️ THÊM BIẾN ĐƯỜNG DẪN FILE EXCEL
EXCEL_FILE_PATH = os.getenv("EXCEL_FILE_PATH", "IIPVietNam.xlsx")

llm = ChatOpenAI(
    api_key=OPENAI__API_KEY,
    model_name=OPENAI__MODEL_NAME,
    temperature=float(OPENAI__TEMPERATURE) if OPENAI__TEMPERATURE else 0
)

# Khởi tạo Pinecone Client
if PINECONE_API_KEY:
    pc = PineconeClient(api_key=PINECONE_API_KEY)
else:
    pc = None
    print("❌ Lỗi: Không tìm thấy PINECONE_API_KEY. Pinecone sẽ không hoạt động.")

emb = OpenAIEmbeddings(api_key=OPENAI__API_KEY, model=OPENAI__EMBEDDING_MODEL)

vectordb = None
retriever = None

# ===================== EXCEL HANDLER =====================
excel_handler = None
if Path(EXCEL_FILE_PATH).exists():
    try:
        excel_handler = ExcelQueryHandler(EXCEL_FILE_PATH)
        print(f"✅ Đã load Excel Handler: {EXCEL_FILE_PATH}")
    except Exception as e:
        print(f"⚠️ Không thể load Excel: {e}")
else:
    print(f"⚠️ Không tìm thấy file Excel: {EXCEL_FILE_PATH}")




# ===================== NEW CONSTANTS FOR DATA COLLECTION =====================
CONTACT_TRIGGER_RESPONSE = 'Anh/chị vui lòng để lại tên và số điện thoại, chuyên gia của IIP sẽ liên hệ và giải đáp các yêu cầu của anh/chị ạ.'
FIXED_RESPONSE_Q3 = 'Nếu bạn muốn biết thêm thông tin chi tiết về các cụm, hãy truy cập vào website https://iipmap.com/.'


# ===================== SYSTEM PROMPT (CẬP NHẬT) =====================
PDF_READER_SYS = (
    "Bạn là một trợ lý AI pháp lý thông minh, chuyên đọc hiểu và tra cứu các tài liệu được cung cấp "
    "(bao gồm: Luật, Nghị định, Quyết định, Thông tư, Văn bản hợp nhất, Quy hoạch, Danh mục khu/cụm công nghiệp, v.v.). "
    "Nhiệm vụ của bạn là trích xuất và trả lời chính xác các thông tin có trong tài liệu, "
    "đặc biệt liên quan đến Lao động, Dân sự và các Khu công nghiệp, Cụm công nghiệp tại Việt Nam.\n\n"

    "⚙️ NGUYÊN TẮC ỨNG XỬ:\n"
    "1️⃣ Nếu người dùng chào hỏi hoặc đặt câu hỏi chung chung (ví dụ: 'xin chào', 'bạn làm được gì', 'giúp tôi với'...), "
    "hãy trả lời NGUYÊN VĂN như sau:\n"
    "'Xin chào! Mình là Chatbot Cổng việc làm Việt Nam. Mình có thể giúp anh/chị tra cứu và giải thích các quy định pháp luật "
    "(luật, nghị định, thông tư...) liên quan đến lao động, việc làm, dân sự và các lĩnh vực pháp lý khác. "
    "Gõ câu hỏi cụ thể hoặc mô tả tình huống nhé — mình sẽ trả lời ngắn gọn, có dẫn nguồn.'\n\n"

    "📘 NGUYÊN TẮC CHUNG:\n"
    "2️⃣ Phân loại câu hỏi:\n"
    "   - Câu hỏi CHUNG CHUNG hoặc NGOÀI TÀI LIỆU: Trả lời ngắn gọn (1–3 câu), lịch sự, không đi sâu.\n"
    "   - Câu hỏi VỀ LUẬT/NGHỊ ĐỊNH hoặc TRONG TÀI LIỆU: Trả lời đầy đủ, chính xác theo nội dung tài liệu.\n"
    "   - Câu hỏi VỀ SỐ LƯỢNG HOẶC DANH SÁCH KHU/CỤM CÔNG NGHIỆP (ví dụ: 'Có bao nhiêu KCN ở Bắc Ninh', 'Liệt kê các CCN ở Đồng Nai') "
    "     → KHÔNG tự trả lời. Hãy trả lời ngắn gọn rằng: 'Đang truy xuất dữ liệu từ hệ thống khu/cụm công nghiệp...', "
    "     để hệ thống tự động xử lý bằng cơ chế Excel Query.\n\n"

    "3️⃣ Phạm vi: Chỉ dựa vào các tài liệu đã được cung cấp; tuyệt đối không suy diễn kiến thức ngoài.\n\n"

    "4️⃣ Khi trả lời về luật, nghị định: Ghi rõ nguồn (ví dụ: 'Theo Điều X, Nghị định số Y/NĐ-CP...'). "
    "KHÔNG được dùng dạng [1], [2], [3]... hoặc nhắc tới 'PDF', 'tài liệu PDF'.\n\n"

    "5️⃣ Văn phong: Pháp lý, trung lập, rõ ràng, hành chính. Không dùng ký tự **in đậm** hoặc __gạch chân__.\n\n"

    "6️⃣ Nếu câu hỏi mơ hồ, hãy yêu cầu người dùng làm rõ hoặc bổ sung chi tiết để trả lời chính xác hơn.\n\n"

    "🏭 QUY TẮC ĐẶC BIỆT CHO KHU/CỤM CÔNG NGHIỆP:\n"
    "1) Nếu câu hỏi chỉ hỏi SỐ LƯỢNG, DANH SÁCH, hoặc LIỆT KÊ các khu/cụm công nghiệp → KHÔNG tự trả lời. "
    "Hãy phản hồi ngắn gọn: 'Đang truy xuất dữ liệu khu/cụm công nghiệp...', hệ thống sẽ trả lời bằng bảng.\n\n"

    "2) Nếu người dùng hỏi CHI TIẾT về một khu/cụm cụ thể (ví dụ: 'Chi tiết KCN VSIP 1 ở Bình Dương'), "
    "hãy trả lời theo các thông tin có trong tài liệu, bao gồm:\n"
    "   - Tên khu/cụm\n"
    "   - Địa điểm (tỉnh/thành phố, huyện/thị xã)\n"
    "   - Diện tích (ha hoặc m²)\n"
    "   - Cơ quan quản lý / chủ đầu tư\n"
    "   - Quyết định thành lập / phê duyệt quy hoạch\n"
    "   - Ngành nghề hoạt động chính\n"
    "   - Tình trạng hoạt động (đang hoạt động / đang quy hoạch / đang xây dựng)\n\n"

    "3) Nếu người dùng hỏi lại chi tiết về các khu/cụm khác (từ lần thứ hai trở đi), "
    "hãy KHÔNG liệt kê lại mà trả lời cố định như sau:\n"
    f"'{FIXED_RESPONSE_Q3}'\n\n"

    "4) Nếu người dùng hỏi ngoài phạm vi pháp luật hoặc KCN/CCN "
    "(ví dụ: tuyển dụng, đầu tư, giá đất...), hãy trả lời nguyên văn:\n"
    f"'{CONTACT_TRIGGER_RESPONSE}'\n\n"

    "🎯 TÓM TẮT:\n"
    "- Câu hỏi chung / chào hỏi → Trả lời NGẮN GỌN, lịch sự.\n"
    "- Câu hỏi pháp luật → Trả lời ĐẦY ĐỦ, chính xác.\n"
    "- Câu hỏi về SỐ LƯỢNG hoặc DANH SÁCH KCN/CCN → KHÔNG trả lời, để hệ thống Excel Query xử lý.\n"
)


# ===================== GOOGLE SHEET UTILS (THỰC TẾ) =====================
def is_valid_phone(phone: str) -> bool:
    """Kiểm tra số điện thoại chỉ chứa chữ số, khoảng trắng hoặc dấu gạch ngang (Tối thiểu 7 ký tự)."""
    return re.match(r'^[\d\s-]{7,}$', phone.strip()) is not None

def authenticate_google_sheet():
    """Xác thực và trả về gspread client."""
    global GOOGLE_SERVICE_ACCOUNT_FILE
    if not GOOGLE_SERVICE_ACCOUNT_FILE or not Path(GOOGLE_SERVICE_ACCOUNT_FILE).exists():
        print("❌ LỖI XÁC THỰC: Không tìm thấy file Service Account. Vui lòng kiểm tra GOOGLE_SERVICE_ACCOUNT_FILE trong .env")
        return None
    try:
        # Sử dụng service_account_file để xác thực
        gc = gspread.service_account(filename=GOOGLE_SERVICE_ACCOUNT_FILE)
        return gc
    except Exception as e:
        print(f"❌ LỖI XÁC THỰC GOOGLE SHEET: {e}")
        return None

def save_contact_info(original_question: str, phone_number: str, name: str = ""):
    """
    Lưu thông tin liên hệ vào Google Sheet đã cấu hình.
    """
    global GOOGLE_SHEET_ID

    print("\n" + "=" * 80)
    #print("💾 ĐANG LƯU THÔNG TIN LIÊN HỆ VÀO GOOGLE SHEET...")
    
    gc = authenticate_google_sheet()
    if gc is None:
        print("❌ KHÔNG THỂ KẾT NỐI VỚI GOOGLE SHEET. Vui lòng kiểm tra lỗi xác thực.")
        print("=" * 80 + "\n")
        return

    if not GOOGLE_SHEET_ID:
        print("❌ LỖI CẤU HÌNH: Thiếu GOOGLE_SHEET_ID trong .env.")
        print("=" * 80 + "\n")
        return

    try:
        # 1. Mở Sheet bằng ID
        sh = gc.open_by_key(GOOGLE_SHEET_ID)
        

        worksheet = sh.sheet1 
        
        # 3. Dữ liệu cần ghi
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        row_data = [
            original_question,
            phone_number,
            name if name else "",
            timestamp 
        ]
        
        # 4. Ghi dữ liệu vào cuối sheet
        worksheet.append_row(row_data)
        
        # 5. Kiểm tra và thêm tiêu đề nếu sheet trống (Tùy chọn)
        try:
            first_row = worksheet.row_values(1)
            expected_headers = ["Câu Hỏi Khách Hàng", "Số Điện Thoại", "Tên", "Thời Gian Ghi Nhận"]
            
            # Nếu dòng 1 trống rỗng (không có giá trị nào)
            if not any(first_row): 
                 worksheet.update('A1:D1', [expected_headers])
            # Có thể thêm logic cảnh báo nếu header không khớp, nhưng hiện tại ta bỏ qua.
        except Exception as e:
            # Bỏ qua lỗi kiểm tra header
            pass
        
        #print(f"✅ Đã ghi nhận thông tin vào Google Sheet (ID: {GOOGLE_SHEET_ID}).")
        print(f"1. Câu hỏi gốc: {original_question}")
        print(f"2. Số điện thoại: {phone_number}")
        print(f"3. Tên: {name if name else 'Không cung cấp'}")
        
    except gspread.exceptions.SpreadsheetNotFound:
        print(f"❌ LỖI: Không tìm thấy Google Sheet với ID: {GOOGLE_SHEET_ID}. Vui lòng kiểm tra lại ID và quyền truy cập.")
    except Exception as e:
        print(f"❌ Lỗi khi ghi dữ liệu vào Google Sheet: {e}")
        
    print("=" * 80 + "\n")


# ===================== VECTORDB UTILS (Pinecone) =====================
def build_context_from_hits(hits, max_chars: int = 6000) -> str:
    """Xây dựng context từ kết quả tìm kiếm"""
    ctx = []
    total = 0
    for idx, h in enumerate(hits, start=1):
        source = h.metadata.get('source', 'unknown')
        seg = f"[Nguồn: {source}, Trang: {h.metadata.get('page', '?')}]\n{h.page_content.strip()}"
        if total + len(seg) > max_chars:
            break
        ctx.append(seg)
        total += len(seg)
    return "\n\n".join(ctx)

def get_existing_sources() -> set:
    """Lấy danh sách file đã có trong VectorDB (Pinecone - không hiệu quả, trả về rỗng)"""
    return set()

def check_vectordb_exists() -> bool:
    """Kiểm tra xem Pinecone Index có tồn tại và có vectors không"""
    global pc, vectordb, retriever
    
    if pc is None or not PINECONE_INDEX_NAME:
        return False

    try:
        if PINECONE_INDEX_NAME not in pc.list_indexes().names():
            return False
            
        index = pc.Index(PINECONE_INDEX_NAME)
        stats = index.describe_index_stats()
        total_vectors = stats['total_vector_count']
        
        if total_vectors > 0:
            if vectordb is None:
                vectordb = Pinecone(
                    index=index, 
                    embedding=emb, 
                    text_key="text"
                )
                retriever = vectordb.as_retriever(search_kwargs={"k": 15})
            return True
            
        return False
        
    except Exception as e:
        return False

def get_vectordb_stats() -> Dict[str, Any]:
    """Lấy thông tin thống kê về VectorDB (Pinecone)"""
    global pc
    
    if pc is None or not PINECONE_INDEX_NAME or PINECONE_INDEX_NAME not in pc.list_indexes().names():
        return {"total_documents": 0, "name": PINECONE_INDEX_NAME, "exists": False, "sources": []}
    
    try:
        index = pc.Index(PINECONE_INDEX_NAME)
        stats = index.describe_index_stats()
        
        count = stats['total_vector_count']
        sources = ["Thông tin nguồn cần được quản lý riêng"]
        
        return {
            "total_documents": count,
            "name": PINECONE_INDEX_NAME,
            "exists": count > 0,
            "sources": sources,
            "dimension": stats.get('dimension', EMBEDDING_DIM)
        }
    except Exception as e:
        return {
            "total_documents": 0,
            "name": PINECONE_INDEX_NAME,
            "exists": False,
            "error": str(e),
            "sources": []
        }

def load_vectordb():
    """Load VectorDB từ Pinecone Index (Chỉ Đọc)"""
    global vectordb, retriever, pc

    if pc is None:
        print("❌ Lỗi: Pinecone Client chưa được khởi tạo. Vui lòng kiểm tra PINECONE_API_KEY.")
        return None

    try:
        # Kiểm tra Index có tồn tại không
        if PINECONE_INDEX_NAME not in pc.list_indexes().names():
            print(f"❌ Index '{PINECONE_INDEX_NAME}' không tồn tại trên Pinecone.")
            return None
            
        # Kết nối đến Index
        index = pc.Index(PINECONE_INDEX_NAME)
        stats = index.describe_index_stats()
        
        # Kiểm tra có document không
        if stats['total_vector_count'] == 0:
            print(f"❌ Index '{PINECONE_INDEX_NAME}' không có document nào.")
            return None
        
        # Kiểm tra dimension
        current_dim = stats.get('dimension', 0)
        if current_dim != EMBEDDING_DIM:
            print(f"⚠️ CẢNH BÁO: Dimension không khớp!")
            print(f"   Index: {current_dim} | Model: {EMBEDDING_DIM}")
            print(f"   Điều này có thể gây lỗi khi query.")
            
        # Khởi tạo vectordb và retriever
        vectordb = Pinecone(
            index=index, 
            embedding=emb, 
            text_key="text"
        )
        retriever = vectordb.as_retriever(search_kwargs={"k": 15})
        
        return vectordb
        
    except Exception as e:
        print(f"❌ Lỗi khi load Pinecone Index: {e}")
        vectordb = None
        retriever = None
        return None

# ===================== CLEANING & RETRIEVAL =====================
_URL_RE = re.compile(r"https?://[^\s]+", re.IGNORECASE)

def clean_question_remove_uris(text: str) -> str:
    """Làm sạch câu hỏi, loại bỏ URL và tên file PDF"""
    txt = _URL_RE.sub(" ", text or "")
    toks = re.split(r"\s+", txt)
    toks = [t for t in toks if not t.lower().endswith(".pdf")]
    return " ".join(toks).strip()


def is_detail_query(text: str) -> bool:
    """Kiểm tra xem câu hỏi có phải là câu hỏi chi tiết về khu/cụm công nghiệp hay không"""
    text_lower = text.lower()
    keywords = ["nêu chi tiết", "chi tiết về", "thông tin chi tiết", "cụm công nghiệp", "khu công nghiệp"]
    if any(k in text_lower for k in keywords):
        if "thống kê" in text_lower:
            return False
        return True
    return False

def count_previous_detail_queries(history: List[BaseMessage]) -> int:
    """Đếm số lần hỏi chi tiết về KCN/CCN đã được trả lời trước đó"""
    count = 0
    for i in range(len(history)):
        current_message = history[i]
        if isinstance(current_message, HumanMessage):
            is_q = is_detail_query(current_message.content)
            if is_q and i + 1 < len(history) and isinstance(history[i+1], AIMessage):
                bot_response = history[i+1].content
                if FIXED_RESPONSE_Q3 not in bot_response:
                    count += 1
    return count

def classify_question_intent(question: str) -> str:
    """
    Phân loại ý định câu hỏi:
    - "count" → hỏi số lượng / liệt kê / danh sách
    - "detail" → hỏi thông tin chi tiết
    - "other" → còn lại
    """
    q = question.lower()
    q_norm = re.sub(r"[^a-z0-9\s]", "", q)

    count_keywords = [
        "bao nhieu", "so luong", "liet ke", "danh sach", "ke ten",
        "co may", "tong so", "toan bo", "bao gom", "nhung", "cac"
    ]
    industrial_keywords = [
        "kcn", "ccn", "khu cong nghiep", "cum cong nghiep",
        "khu cn", "cum cn", "cong nghiep"
    ]

    if any(k in q_norm for k in industrial_keywords) and any(k in q_norm for k in count_keywords):
        return "count"

    # 🔹 Bổ sung nhận diện implicit “các KCN ở …”
    if re.search(r"cac (khu|cum) cong nghiep", q_norm) or re.search(r"nhung (khu|cum) cong nghiep", q_norm):
        return "count"

    detail_keywords = [
        "chi tiet", "thong tin", "mo ta", "chu dau tu",
        "dien tich", "nganh nghe", "quy hoach", "trang thai"
    ]
    if any(k in q_norm for k in industrial_keywords) and any(k in q_norm for k in detail_keywords):
        return "detail"

    return "other"

def process_pdf_question(i: Dict[str, Any]) -> str:
    """
    Xử lý câu hỏi từ người dùng — ƯU TIÊN kiểm tra Excel (số lượng / liệt kê)
    trước khi gửi vào mô hình GPT (Prompt).
    """
    global retriever, excel_handler

    message = i["message"]
    history: List[BaseMessage] = i.get("history", [])
    clean_question = clean_question_remove_uris(message)

    # ================================
    # 1️⃣ KIỂM TRA CÂU HỎI LIÊN QUAN ĐẾN SỐ LƯỢNG / LIỆT KÊ TRƯỚC TIÊN
    # ================================
    if excel_handler is not None:
        try:
            # Nếu người dùng hỏi về số lượng, danh sách, liệt kê KCN/CCN
            if excel_handler.is_count_query(clean_question):
                print("📊 Phát hiện: Câu hỏi đếm / liệt kê KCN-CCN → Dùng Excel")
                handled, excel_response = excel_handler.process_query(clean_question)
                if handled and excel_response:
                    return excel_response
        except Exception as e:
            print(f"⚠️ Lỗi khi xử lý Excel Query: {e}")

    # ================================
    # 2️⃣ PHÂN LOẠI Ý ĐỊNH CÂU HỎI (phục vụ các loại khác)
    # ================================
    intent = classify_question_intent(clean_question)
    # print(f"🤖 Phân loại câu hỏi: {intent}")

    # ================================
    # 3️⃣ NẾU LÀ CÂU HỎI CHI TIẾT → ÁP DỤNG QUY TẮC 3
    # ================================
    if intent == "detail":
        count_detail_queries = count_previous_detail_queries(history)
        if count_detail_queries >= 1:
            return FIXED_RESPONSE_Q3

    # ================================
    # 4️⃣ CÒN LẠI: TRẢ LỜI BẰNG GPT / PINECONE (System Prompt)
    # ================================
    if retriever is None:
        return "❌ VectorDB chưa được load hoặc không có dữ liệu. Vui lòng kiểm tra lại Pinecone Index."
    
    try:
        hits = retriever.invoke(clean_question)

        if not hits:
            return "Xin lỗi, tôi không tìm thấy thông tin liên quan trong dữ liệu hiện có."

        # Xây dựng context cho GPT
        context = build_context_from_hits(hits, max_chars=6000)
        messages = [SystemMessage(content=PDF_READER_SYS)]

        # Giữ lại lịch sử ngắn để GPT hiểu ngữ cảnh
        if history:
            messages.extend(history[-10:])

        user_message = f"""Câu hỏi: {clean_question}

Nội dung liên quan từ tài liệu:
{context}

Hãy trả lời dựa trên nội dung trên và tuân thủ System Prompt."""
        
        messages.append(HumanMessage(content=user_message))
        response = llm.invoke(messages).content
        return response

    except Exception as e:
        print(f"❌ Lỗi: {e}")
        return f"Xin lỗi, tôi gặp lỗi khi xử lý câu hỏi: {str(e)}"



# ===================== MAIN CHATBOT =====================
pdf_chain = RunnableLambda(process_pdf_question)
store: Dict[str, ChatMessageHistory] = {}

def get_history(session_id: str):
    """Lấy hoặc tạo lịch sử chat cho session"""
    if session_id not in store:
        store[session_id] = ChatMessageHistory()
    return store[session_id]

chatbot = RunnableWithMessageHistory(
    pdf_chain,
    get_history,
    input_messages_key="message",
    history_messages_key="history"
)

def print_help():
    """In hướng dẫn sử dụng"""
    print("\n" + "="*60)
    print("📚 CÁC LỆNH CÓ SẴN:")
    print("="*60)
    print(" - exit / quit  : Thoát chương trình")
    print(" - clear        : Xóa lịch sử hội thoại")
    print(" - status       : Kiểm tra trạng thái Pinecone Index")
    print(" - help         : Hiển thị hướng dẫn này")
    print("="*60 + "\n")

def handle_command(command: str, session: str) -> bool:
    """Xử lý các lệnh đặc biệt"""
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
        print("\n" + "="*60)
        #print("📊 TRẠNG THÁI PINECONE INDEX (CHẾ ĐỘ CHỈ ĐỌC)")
        print("="*60)
        if stats["exists"]:
            print(f"✅ Trạng thái: Sẵn sàng")
            print(f"📚 Tên Index: {stats['name']}")
            print(f"📊 Tổng documents: {stats['total_documents']}")
            print(f"📏 Dimension: {stats['dimension']}")
        else:
            print("❌ Trạng thái: Chưa sẵn sàng")
            print(f"💡 Index '{PINECONE_INDEX_NAME}' không tồn tại hoặc không có documents.")
        print("="*60 + "\n")
        return True
    
    elif cmd == "excel":
        if excel_handler is not None:
            print("\n" + "="*60)
            print("📊 THÔNG TIN FILE EXCEL")
            print("="*60)
            print(f"📁 File: {EXCEL_FILE_PATH}")
            print(f"📚 Tổng bản ghi: {len(excel_handler.df)}")
            print(f"📍 Cột tỉnh: {excel_handler.province_column}")
            print(f"📝 Cột tên: {excel_handler.name_column}")
            print(f"🏠 Cột địa chỉ: {excel_handler.address_column}")
            print("="*60 + "\n")
        else:
            print("❌ Excel Handler chưa được khởi tạo.\n")
        return True
    
    elif cmd == "help":
        print_help()
        return True
    
    else:
        return True

# ===================== AUTO LOAD WHEN IMPORTED =====================
if __name__ != "__main__":
    #print("📦 Tự động load Pinecone khi import app.py...")
    load_vectordb()

# ===================== CLI =====================
if __name__ == "__main__":
    session = "pdf_reader_session"
    
    # Biến quản lý trạng thái thu thập thông tin liên hệ
    contact_collection_mode = False
    original_question = ""

    # Kiểm tra môi trường
    if not all([OPENAI__API_KEY, PINECONE_API_KEY, PINECONE_INDEX_NAME, GOOGLE_SHEET_ID, GOOGLE_SERVICE_ACCOUNT_FILE]):
        print("❌ LỖI CẤU HÌNH: Thiếu các biến môi trường cần thiết.")
        print("Hãy kiểm tra: OPENAI, PINECONE, GOOGLE_SHEET_ID, GOOGLE_SERVICE_ACCOUNT_FILE.")
        exit(1)

    print("\n" + "="*80)
    print("🤖 CHATBOT PHÁP LÝ & KCN/CCN")
    print("="*80)
    print(f"☁️ Pinecone Index: {PINECONE_INDEX_NAME}")
    print(f"📄 Google Sheet ID: {GOOGLE_SHEET_ID}")
    print("🔍 Tôi hỗ trợ: Luật Lao động & Luật Dân sự Việt Nam")
    print_help()

    # Load VectorDB từ Pinecone
    print("📥 Đang kết nối đến Pinecone Index...")
    result = load_vectordb()
    
    if result is None:
        print("❌ KHÔNG THỂ LOAD PINECONE INDEX. Vui lòng kiểm tra lại cấu hình.")
        exit(1)

    # In thống kê
    stats = get_vectordb_stats()
    print(f"✅ Pinecone Index sẵn sàng với {stats['total_documents']} documents\n")
    
    print("💬 Sẵn sàng trả lời câu hỏi! (Gõ 'help' để xem hướng dẫn)\n")

    # Main loop
    while True:
        try:
            # --- Xử lý chế độ thu thập thông tin liên hệ (Bước 2) ---
            if contact_collection_mode:
                # Bỏ qua lịch sử chat cho quá trình thu thập thông tin
                print("\n" + "-"*80)
                print("📞 BƯỚC THU THẬP THÔNG TIN LIÊN HỆ")
                print(f"❓ Câu hỏi gốc: '{original_question}'")
                
                # 1. Nhập Số điện thoại (Bắt buộc)
                while True:
                    phone_number = input("Vui lòng nhập SỐ ĐIỆN THOẠI (Bắt buộc): ").strip()
                    if is_valid_phone(phone_number):
                        break
                    print("❌ Số điện thoại không hợp lệ. Vui lòng thử lại.")
                
                # 2. Nhập Tên (Tùy chọn)
                name = input("Vui lòng nhập TÊN (Tùy chọn, Enter để bỏ qua): ").strip() or ""
                
                # 3. Thực hiện lưu trữ
                save_contact_info(original_question, phone_number, name)
                
                # 4. Reset trạng thái
                contact_collection_mode = False
                original_question = ""
                # Xóa câu hỏi gốc và phản hồi bot khỏi lịch sử để bot không bị lặp
                history = get_history(session).messages
                if len(history) >= 2:
                    history.pop() 
                    history.pop() 
                
                print("-" * 80)
                print("💬 Tiếp tục cuộc trò chuyện thường (hoặc gõ 'exit' để thoát).")
                continue 


            # --- Xử lý Chatbot thông thường (Bước 1) ---
            message = input("👤 Bạn: ").strip()
            
            if not message:
                continue
            
            # Xử lý lệnh
            if not handle_command(message, session):
                break
            
            # Bỏ qua nếu là lệnh
            if message.lower() in ["clear", "status", "help"]: 
                continue
            
            # Xử lý câu hỏi thường
            print("🔎 Đang tìm kiếm trong Pinecone Index...")
            
            # Lưu câu hỏi trước khi gọi bot
            current_query = message
            
            response = chatbot.invoke(
                {"message": current_query},
                config={"configurable": {"session_id": session}}
            )
            
            print(f"\n🤖 Bot: {response}\n")
            print("-" * 80 + "\n")
            
            # --- KIỂM TRA TRIGER THU THẬP THÔNG TIN ---
            if response.strip() == CONTACT_TRIGGER_RESPONSE.strip():
                contact_collection_mode = True
                original_question = current_query
                print("--- ĐÃ KÍCH HOẠT CHẾ ĐỘ THU THẬP THÔNG TIN ---")

        except KeyboardInterrupt:
            print("\n\n👋 Tạm biệt!")
            break
        except Exception as e:
            print(f"\n❌ Lỗi: {e}\n")