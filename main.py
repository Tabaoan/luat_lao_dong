from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import os
import uvicorn
# import uuid
# session = f"api_{uuid.uuid4()}"
from typing import Optional, Any
from datetime import datetime
from starlette.concurrency import run_in_threadpool 
from mst.router import is_mst_query
from mst.handler import handle_mst_query
from law_db_query.handler import handle_law_count_query
from excel_visualize import (
    is_excel_visualize_price_intent,
    handle_excel_price_visualize
)
# ===============================
# Import Chatbot từ app.py
# ===============================
try:
    import app
    CHATBOT_AVAILABLE = True
    print("✅ Đã import thành công module 'app'")
except ImportError as e:
    app = None
    CHATBOT_AVAILABLE = False
    print(f"WARNING: Could not import 'app' module. Error: {e}")

# ===============================
# Lấy các hằng số từ app.py
# ===============================
CONTACT_TRIGGER_RESPONSE = None
if CHATBOT_AVAILABLE and hasattr(app, 'CONTACT_TRIGGER_RESPONSE'):
    CONTACT_TRIGGER_RESPONSE = app.CONTACT_TRIGGER_RESPONSE
    print(f"✅ Đã load CONTACT_TRIGGER_RESPONSE từ app.py")
else:
    # Fallback nếu không tìm thấy
    CONTACT_TRIGGER_RESPONSE = 'Anh/chị vui lòng để lại tên và số điện thoại, chuyên gia của IIP sẽ liên hệ và giải đáp các yêu cầu của anh/chị ạ.'
    print("⚠️ Sử dụng CONTACT_TRIGGER_RESPONSE mặc định")

# ===============================
# Kiểm tra Google Sheet availability
# ===============================
SHEET_AVAILABLE = False
try:
    if CHATBOT_AVAILABLE and hasattr(app, 'save_contact_info') and hasattr(app, 'is_valid_phone'):
        SHEET_AVAILABLE = True
        print("✅ Google Sheet functions đã sẵn sàng từ app.py")
    else:
        print("WARNING: Google Sheet functions not found in app.py")
except Exception as e:
    print(f"WARNING: Error checking Google Sheet availability: {e}")

# --- Khai báo Model cho dữ liệu đầu vào ---
# FastAPI sử dụng Pydantic để định nghĩa cấu trúc dữ liệu
class Question(BaseModel):
    """Định nghĩa cấu trúc dữ liệu JSON đầu vào."""
    question: str
    phone: Optional[str] = None
    name: Optional[str] = None
    url: Optional[str] = None

class ContactInfo(BaseModel):
    """Định nghĩa cấu trúc dữ liệu cho thông tin liên hệ."""
    original_question: str
    phone: str
    name: Optional[str] = None

# ---------------------------------------
# 1️⃣ Khởi tạo FastAPI App + bật CORS
# ---------------------------------------
# Khởi tạo ứng dụng FastAPI
app_fastapi = FastAPI(
    title="Chatbot Luật Lao động API",
    description="API cho mô hình chatbot",
    version="1.0.0"
)

# 🔹 Cấu hình CORS Middleware
# Cho phép tất cả các domain (origins=["*"]) hoặc domain cụ thể.
origins = [
    "*",
]

app_fastapi.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------
# 2️⃣ Route kiểm tra hoạt động (GET /)
# ---------------------------------------
@app_fastapi.get("/", summary="Kiểm tra trạng thái API")
async def home():
    """Route kiểm tra xem API có hoạt động không."""
    
    # Kiểm tra trạng thái VectorDB
    vectordb_status = "Unknown"
    if CHATBOT_AVAILABLE:
        try:
            stats = app.get_vectordb_stats()
            if stats.get("exists", False):
                vectordb_status = f"Ready ({stats.get('total_documents', 0)} docs)"
            else:
                vectordb_status = "Empty or Not Found"
        except Exception as e:
            vectordb_status = f"Error: {str(e)}"
    
    return {
        "message": "✅ Chatbot Luật Lao động API đang hoạt động.",
        "usage": "Gửi POST tới /chat với JSON { 'question': 'Câu hỏi của bạn' }",
        "chatbot_status": "Available" if CHATBOT_AVAILABLE else "Not Available",
        "vectordb_status": vectordb_status,
        "sheet_status": "Available" if SHEET_AVAILABLE else "Not Available",
        "contact_trigger": CONTACT_TRIGGER_RESPONSE
    }

# ---------------------------------------
# 3️⃣ Route chính: /chat (POST)
# ---------------------------------------
@app_fastapi.post("/chat", summary="Dự đoán/Trả lời câu hỏi từ Chatbot")
async def predict(data: Question):
    """
    Nhận câu hỏi và trả về câu trả lời từ mô hình chatbot.
    
    Logic hoạt động (GIỐNG FILE APP.PY):
    1. Gọi chatbot để trả lời câu hỏi
    2. Kiểm tra xem response có phải là CONTACT_TRIGGER_RESPONSE không
    3. Nếu là trigger response:
       - Trả về response với flag requires_contact = true
       - Client sẽ hiển thị form nhập phone/name
       - Client gọi POST /submit-contact để lưu thông tin
    4. Nếu user đã gửi phone ngay từ đầu (optional):
       - Lưu luôn vào Google Sheet
    """
    question = data.question.strip()

    if not question:
        raise HTTPException(status_code=400, detail="Thiếu trường 'question' trong JSON hoặc câu hỏi bị rỗng.")

    try:
        answer = None
        requires_contact = False
        # ===============================
        # 0️⃣ LAW COUNT – SQL FIRST
        # ===============================
        payload = handle_law_count_query(question)

        if isinstance(payload, dict) and payload.get("intent") == "law_count":
            response = await run_in_threadpool(
                app.chatbot.invoke,
                {
                    "message": question,
                    "law_count": payload["total_laws"]  
                },
                config={"configurable": {"session_id": "api_session"}}
            )

            return {
                "answer": response,
                "requires_contact": False
            }

        # ====== CHECK MST INTENT (ƯU TIÊN CAO NHẤT) ======
        if is_mst_query(question):
            mst_answer = await run_in_threadpool(
                handle_mst_query,
                message=question,
                llm=app.llm,
                embedding=app.emb
            )
            return {
                "answer": mst_answer,
                "requires_contact": False
            }

        if is_excel_visualize_price_intent(question):
            excel_result = await run_in_threadpool(
                handle_excel_price_visualize,
                message=question,
                excel_handler=app.excel_handler
            )

            # Excel visualize trả JSON (KHÔNG phải text)
            return {
                "answer": " Đã tạo biểu đồ so sánh giá theo yêu cầu.",
                "type": "excel_visualize",
                "payload": excel_result,
                "requires_contact": False
            }
        #  Gọi chatbot thực tế nếu có (Giả định app.py có chứa đối tượng chatbot)
        if CHATBOT_AVAILABLE and hasattr(app, "chatbot"):
            session = "api_session" 
            
            # Kiểm tra xem app.chatbot.invoke có phải là hàm bất đồng bộ (coroutine) không
            if hasattr(app.chatbot, 'invoke'):
                try:
                    # Kiểm tra xem invoke có phải async không
                    import inspect
                    if inspect.iscoroutinefunction(app.chatbot.invoke):
                        # Nếu là async (bất đồng bộ), dùng await trực tiếp
                        response = await app.chatbot.invoke(
                            {"message": question},
                            config={"configurable": {"session_id": session}}
                        )
                    else:
                        # Nếu là sync (đồng bộ), chạy nó trong thread pool để không chặn server chính
                        response = await run_in_threadpool(
                            app.chatbot.invoke,
                            {"message": question},
                            config={"configurable": {"session_id": session}}
                        )
                    
                    # Xử lý kết quả trả về
                    if isinstance(response, dict) and 'output' in response:
                        answer = response['output']
                    elif isinstance(response, str):
                        answer = response
                    else:
                        answer = f"Lỗi: Chatbot trả về định dạng không mong muốn: {repr(response)}"
                    
                    # ✅ KIỂM TRA TRIGGER (GIỐNG APP.PY)
                    # Nếu response chính xác là CONTACT_TRIGGER_RESPONSE
                    if answer and answer.strip() == CONTACT_TRIGGER_RESPONSE.strip():
                        requires_contact = True
                        print(f"🔔 TRIGGER PHÁT HIỆN: Câu hỏi '{question}' cần thu thập thông tin liên hệ")
                        
                except Exception as invoke_error:
                    print(f"❌ Lỗi khi gọi chatbot.invoke: {invoke_error}")
                    answer = f"Xin lỗi, đã xảy ra lỗi khi xử lý câu hỏi của bạn."
            else:
                answer = "Lỗi: Chatbot không có phương thức invoke"

        else:
            # Nếu chưa có chatbot thật hoặc import thất bại, trả về thông báo
            answer = f"(Chatbot mô phỏng - LỖI BACKEND: Không tìm thấy đối tượng app.chatbot) Bạn hỏi: '{question}'"

        # ✅ Nếu người dùng đã gửi phone ngay từ đầu (tùy chọn - không phổ biến)
        if data.phone and SHEET_AVAILABLE:
            try:
                # Gọi hàm save_contact_info từ app.py
                await run_in_threadpool(
                    app.save_contact_info,
                    question,
                    data.phone,
                    data.name or ""
                )
                print(f"✅ Đã ghi thông tin liên hệ sớm: {data.phone}")
            except Exception as sheet_error:
                print(f"⚠️ Lỗi ghi Google Sheet: {sheet_error}")

        # ✅ RESPONSE (GIỐNG LOGIC APP.PY)
        return {
            "answer": answer,
            "requires_contact": requires_contact  
        }

    except Exception as e:
        # Trả về lỗi server 500 nếu có lỗi xảy ra trong quá trình gọi chatbot
        print(f"LỖI CHATBOT: {e}")
        raise HTTPException(status_code=500, detail=f"Lỗi xử lý Chatbot: {str(e)}. Vui lòng kiểm tra log backend của bạn.")


# ---------------------------------------
# 4️⃣ Route mới: /submit-contact (POST)
# ---------------------------------------
@app_fastapi.post("/submit-contact", summary="Gửi thông tin liên hệ sau khi chatbot yêu cầu")
async def submit_contact(data: ContactInfo):
    """
    Route để client gửi thông tin liên hệ sau khi nhận được requires_contact=true.
    
    LOGIC (GIỐNG APP.PY - BƯỚC 2):
    1. Nhận original_question, phone, name từ client
    2. Validate số điện thoại
    3. Lưu vào Google Sheet
    4. Trả về confirmation
    
    Flow hoàn chỉnh:
    User: "Tôi muốn tư vấn về đầu tư"
    → POST /chat → Bot trả về trigger response + requires_contact=true
    → Client hiển thị form nhập phone/name
    → User nhập phone + name
    → Client POST /submit-contact với {original_question, phone, name}
    → Server lưu vào Google Sheet
    → Trả về success message
    """
    
    if not SHEET_AVAILABLE:
        raise HTTPException(
            status_code=503, 
            detail="Google Sheet không khả dụng. Vui lòng kiểm tra cấu hình server."
        )
    
    # Validate phone number
    phone = data.phone.strip()
    if not app.is_valid_phone(phone):
        raise HTTPException(
            status_code=400,
            detail="Số điện thoại không hợp lệ. Vui lòng nhập số điện thoại hợp lệ (tối thiểu 7 ký tự, chỉ chứa số, khoảng trắng hoặc dấu gạch ngang)."
        )
    
    try:
        # Lưu thông tin vào Google Sheet (Giống app.py)
        await run_in_threadpool(
            app.save_contact_info,
            data.original_question,
            phone,
            data.name or ""
        )
        
        print(f"✅ Đã lưu thông tin liên hệ:")
        print(f"   - Câu hỏi: {data.original_question}")
        print(f"   - Phone: {phone}")
        print(f"   - Name: {data.name or 'Không cung cấp'}")
        
        return {
            "success": True,
            "message": "Cảm ơn anh/chị! Chuyên gia của IIP sẽ liên hệ với anh/chị trong thời gian sớm nhất.",
            "contact_saved": {
                "question": data.original_question,
                "phone": phone,
                "name": data.name or ""
            }
        }
        
    except Exception as e:
        print(f"❌ Lỗi khi lưu thông tin liên hệ: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Không thể lưu thông tin liên hệ. Lỗi: {str(e)}"
        )


# ---------------------------------------
# 5️⃣ Route kiểm tra trạng thái VectorDB
# ---------------------------------------
@app_fastapi.get("/status", summary="Kiểm tra trạng thái chi tiết của hệ thống")
async def get_status():
    """
    Route để kiểm tra trạng thái chi tiết của các thành phần hệ thống.
    Tương tự lệnh 'status' trong CLI của app.py
    """
    
    if not CHATBOT_AVAILABLE:
        return {
            "chatbot": "Not Available",
            "vectordb": "Unknown",
            "google_sheet": "Unknown",
            "error": "Module app.py không được import thành công"
        }
    
    # Lấy thông tin VectorDB
    vectordb_info = {}
    try:
        stats = app.get_vectordb_stats()
        vectordb_info = {
            "status": "Ready" if stats.get("exists", False) else "Not Ready",
            "index_name": stats.get("name", "Unknown"),
            "total_documents": stats.get("total_documents", 0),
            "dimension": stats.get("dimension", 0),
            "exists": stats.get("exists", False)
        }
    except Exception as e:
        vectordb_info = {
            "status": "Error",
            "error": str(e)
        }
    
    # Kiểm tra Google Sheet
    sheet_info = {
        "status": "Available" if SHEET_AVAILABLE else "Not Available",
        "sheet_id": os.getenv("GOOGLE_SHEET_ID", "Not configured")
    }
    
    return {
        "chatbot": "Available",
        "vectordb": vectordb_info,
        "google_sheet": sheet_info,
        "trigger_response": CONTACT_TRIGGER_RESPONSE
    }


# ---------------------------------------
# 6️⃣ Khởi động server Uvicorn (FastAPI)
# ---------------------------------------

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))

    uvicorn.run("main:app_fastapi", host="0.0.0.0", port=port, log_level="info", reload=True)
