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
# ⬅️ THÊM IMPORT MODULE EXCEL
from excel_query import ExcelQueryHandler
from langdetect import detect


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
EXCEL_FILE_PATH = os.getenv("EXCEL_FILE_PATH")

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
    "   Ví dụ:\n"
    "   'Tỉnh Bình Dương có 29 khu công nghiệp. Bao gồm:\n"
    "   - Khu công nghiệp Sóng Thần 1\n"
    "   - Khu công nghiệp VSIP 1\n"
    "   - Khu công nghiệp Mỹ Phước 3\n"
    "   ...'\n\n"
    
    "2) Nếu người dùng hỏi chi tiết về một khu/cụm công nghiệp cụ thể, hãy trình bày đầy đủ thông tin (nếu có trong tài liệu), gồm:\n"
    "   - Tên khu công nghiệp (kcn) / cụm công nghiệp (cnn)\n"
    "   - Địa điểm (tỉnh/thành phố, huyện/thị xã)\n"
    "   - Diện tích (ha hoặc m²)\n"
    "   - Cơ quan quản lý / chủ đầu tư\n"
    "   - Quyết định thành lập hoặc phê duyệt quy hoạch\n"
    "   - Ngành nghề hoạt động chính\n"
    "   - Tình trạng hoạt động (đang hoạt động / đang quy hoạch / đang xây dựng)\n"
    "   - Các thông tin khác liên quan (nếu có)\n\n"
    

    "🌐 QUY TẮC NGÔN NGỮ:\n"
    "- Luôn trả lời đúng theo NGÔN NGỮ của câu hỏi cuối cùng.\n"
    "- Nếu tài liệu là tiếng Việt nhưng người dùng hỏi bằng ngôn ngữ khác (Anh, Hàn, Nhật, Trung...), "
    "hãy DỊCH phần thông tin trích xuất từ tài liệu sang ngôn ngữ của người dùng rồi trình bày.\n"
    "- Không được trả lời bằng tiếng Việt nếu người dùng không dùng tiếng Việt.\n"
    "- Không thay đổi chủ đề hoặc thêm thông tin ngoài tài liệu.\n"
    "- Bạn luôn sử dụng đúng ngôn ngữ được cung cấp trong metadata 'user_lang' của tin nhắn người dùng.\n\n"
    
    "🏢 QUY ĐỊNH RIÊNG ĐỐI VỚI CÁC YÊU CẦU LIÊN QUAN ĐẾN THUÊ ĐẤT / TÌM ĐẤT TRONG KCN – CCN:\n"
    "1) Nếu người dùng hỏi về việc thuê đất, giá thuê, thủ tục thuê, điều kiện thuê, hồ sơ thuê đất, "
    "hoặc quy trình thuê đất trong khu công nghiệp/cụm công nghiệp, bạn phải:\n"
    "   - Trả lời ĐÚNG và CHI TIẾT theo nội dung có trong tài liệu (Luật, Nghị định, Quy hoạch, Quyết định…).\n"
    "   - Nêu rõ căn cứ pháp lý (Ví dụ: Theo Điều X của Luật Đất đai 2013…, Theo Khoản Y Điều Z của Nghị định…).\n"
    "   - Tuyệt đối KHÔNG suy đoán nếu tài liệu không đề cập.\n\n"

    "2) Nếu người dùng hỏi về QUỸ ĐẤT TRỐNG trong KCN/CCN, diện tích còn cho thuê, hoặc tình trạng sẵn sàng cho thuê, "
    "bạn chỉ được trả lời nếu thông tin đó CÓ TRONG TÀI LIỆU đã cung cấp.\n"
    "   - Nếu tài liệu có thông tin → Trình bày đầy đủ.\n"
    "   - Nếu tài liệu KHÔNG có → Trả lời lịch sự rằng tài liệu không có dữ liệu và khuyến nghị người dùng cung cấp thêm thông tin (nhưng không đưa thông tin ngoài tài liệu).\n\n"

    "3) Nếu người dùng hỏi 'cụm công nghiệp/khu công nghiệp nào có thể thuê đất', "
    "bạn phải:\n"
    "   - Xác định trong tài liệu nơi nào có mô tả về tình trạng hoạt động hoặc quỹ đất.\n"
    "   - Trả lời đúng theo thông tin đã ghi (ví dụ: đang hoạt động, đang quy hoạch, đã lấp đầy…).\n"
    "   - Nếu tài liệu không nói rõ về khả năng cho thuê → chỉ trả lời theo tình trạng được nêu trong tài liệu, không suy diễn.\n\n"

    "4) Nếu người dùng hỏi về quy trình thuê đất, phải mô tả theo luật:\n"
    "   - Điều kiện được thuê đất.\n"
    "   - Hồ sơ cần chuẩn bị.\n"
    "   - Thẩm quyền phê duyệt.\n"
    "   - Trình tự thực hiện (theo Luật Đất đai, Nghị định và văn bản liên quan… nếu đã nằm trong cơ sở dữ liệu).\n\n"

    "5) Nếu người dùng hỏi về MỨC GIÁ thuê đất hoặc chi phí thuê đất:\n"
    "   - Chỉ trả lời nếu nội dung này xuất hiện trong các tài liệu đã được index.\n"
    "   - Nếu tài liệu không chứa thông tin → chỉ thông báo 'tài liệu không đề cập đến đơn giá hoặc giá thuê đất'.\n\n"
    "6) Nếu người dùng hỏi về giới thiệu khu công nghiệp còn đất trống mà không nói rõ của tỉnh thành nào, thì hãy dựa vào câu hỏi trước khách hỏi tỉnh thành nào để trả lời.\n\n"
    "Nếu câu trước không nhắc tỉnh thành nào thì lấy ngẫu nhiên một tỉnh thành để trả lơi.\n\n"
    "🎯 TÓM TẮT:\n"
    "- Câu hỏi chung chung/ngoài tài liệu → trả lời NGẮN GỌN.\n"
    "- Câu hỏi pháp luật/KCN/CCN → trả lời ĐẦY ĐỦ dựa trên tài liệu.\n"
    "- Luôn dịch câu trả lời sang ngôn ngữ của người dùng nếu họ không dùng tiếng Việt.\n"

)


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
            print(f"   Index: {current_dim} | Model: {EMBEDDING_DIM}")
            print(f"   Điều này có thể gây lỗi khi query.")
            
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


def convert_language(text: str, target_lang: str) -> str:
    """
    Dịch câu trả lời sang đúng ngôn ngữ người dùng.
    Cải thiện: Thêm mapping ngôn ngữ rõ ràng hơn
    """
    # Mapping code ngôn ngữ sang tên đầy đủ
    lang_mapping = {
        "vi": "Tiếng Việt",
        "en": "English",
        "ko": "한국어 (Korean)",
        "ja": "日本語 (Japanese)",
        "zh-cn": "简体中文 (Simplified Chinese)",
        "zh-tw": "繁體中文 (Traditional Chinese)",
        "fr": "Français",
        "de": "Deutsch",
        "es": "Español",
        "th": "ภาษาไทย (Thai)"
    }
    
    target_lang_name = lang_mapping.get(target_lang, target_lang)
    
    try:
        translated = llm.invoke([
            SystemMessage(content="Bạn là một phiên dịch chuyên nghiệp. Hãy dịch chính xác nội dung sang ngôn ngữ được yêu cầu."),
            HumanMessage(
                content=f"Dịch đoạn văn sau sang {target_lang_name} ({target_lang}). CHỈ trả về bản dịch, KHÔNG thêm giải thích:\n\n{text}"
            )
        ]).content
        return translated.strip()
    except Exception as e:
        print(f"⚠️ Lỗi dịch ngôn ngữ: {e}")
        return text


def process_pdf_question(i: Dict[str, Any]) -> str:
    """Xử lý câu hỏi từ người dùng (ƯU TIÊN EXCEL → VECTORDB → LLM)"""
    global retriever
    
    message = i["message"]
    history: List[BaseMessage] = i.get("history", [])

    clean_question = clean_question_remove_uris(message)
    
    # 1️⃣ PHÁT HIỆN NGÔN NGỮ
    try:
        user_lang = detect(message)
    except:
        user_lang = "vi"
    
    # 2️⃣ ƯU TIÊN XỬ LÝ BỞI EXCEL QUERY — ƯU TIÊN CAO NHẤT
    if excel_handler is not None:
        try:
            handled, excel_response = excel_handler.process_query(clean_question)
            if handled and excel_response:
                # Dịch nếu cần
                if user_lang != "vi":
                    excel_response = convert_language(excel_response, user_lang)
                return excel_response
        except Exception as e:
            print(f"⚠️ Lỗi Excel Query: {e}")

    # 3️⃣ KIỂM TRA VECTORDB
    if retriever is None:
        error_msg = "❌ VectorDB chưa được load hoặc không có dữ liệu."
        return convert_language(error_msg, user_lang) if user_lang != "vi" else error_msg
    
    try:
        # 4️⃣ TÌM KIẾM TRONG VECTORDB
        hits = retriever.invoke(clean_question)
        
        if not hits:
            msg = "Xin lỗi, tôi không tìm thấy thông tin liên quan trong dữ liệu hiện có."
            return convert_language(msg, user_lang) if user_lang != "vi" else msg

        # 5️⃣ TẠO CONTEXT
        context = build_context_from_hits(hits, max_chars=6000)
        
        # SYSTEM PROMPT (kèm yêu cầu ngôn ngữ)
        system_prompt_with_lang = PDF_READER_SYS + f"\n\n🌍 Người dùng đang sử dụng ngôn ngữ '{user_lang}'. Hãy trả lời bằng ngôn ngữ này."
        
        messages = [SystemMessage(content=system_prompt_with_lang)]
        
        # Lịch sử 10 đoạn gần nhất
        if history:
            messages.extend(history[-10:])

        # USER MESSAGE KÈM CONTEXT
        user_message = f"""Câu hỏi: {clean_question}

Nội dung liên quan từ tài liệu:
{context}

Hãy trả lời dựa trên nội dung trên bằng ngôn ngữ '{user_lang}'."""
        
        messages.append(HumanMessage(content=user_message))

        # 6️⃣ GỌI LLM
        response = llm.invoke(messages).content

        # 7️⃣ ĐẢM BẢO TRẢ LỜI ĐÚNG NGÔN NGỮ
        try:
            if detect(response) != user_lang:
                response = convert_language(response, user_lang)
        except:
            response = convert_language(response, user_lang)

        return response

    except Exception as e:
        msg = f"Xin lỗi, tôi gặp lỗi: {str(e)}"
        return convert_language(msg, user_lang) if user_lang != "vi" else msg


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
    print(" - exit / quit  : Thoát chương trình")
    print(" - clear        : Xóa lịch sử hội thoại")
    print(" - status       : Kiểm tra trạng thái Pinecone Index")
    print(" - help         : Hiển thị hướng dẫn này")
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
        print("📊 TRẠNG THÁI PINECONE INDEX")
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
    
    elif cmd == "help":
        print_help()
        return True
    
    else:
        return True


# ===================== AUTO LOAD WHEN IMPORTED =====================
if __name__ != "__main__":
    print("📦 Tự động load Pinecone khi import app.py...")
    load_vectordb()


# ===================== CLI =====================
if __name__ == "__main__":
    session = "pdf_reader_session"

    # Kiểm tra môi trường
    if not all([OPENAI__API_KEY, PINECONE_API_KEY, PINECONE_INDEX_NAME]):
        print("❌ LỖI CẤU HÌNH: Thiếu các biến môi trường cần thiết.")
        print("Hãy kiểm tra: OPENAI_API_KEY, PINECONE_API_KEY, PINECONE_INDEX_NAME.")
        exit(1)

    print("\n" + "="*80)
    print("🤖 CHATBOT PHÁP LÝ & KCN/CCN")
    print("="*80)
    print(f"☁️ Pinecone Index: {PINECONE_INDEX_NAME}")
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
            message = input("👤 Bạn: ").strip()
            
            if not message:
                continue
            
            # Xử lý lệnh
            if not handle_command(message, session):
                break
            
            # Bỏ qua
                        # Bỏ qua nếu là lệnh
            if message.lower() in ["clear", "status", "help"]:
                continue
            
            # Xử lý câu hỏi thường
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