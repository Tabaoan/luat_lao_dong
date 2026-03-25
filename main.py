# main.py
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import os
import uvicorn
from typing import Optional, Any, Dict, List
from pathlib import Path
import json
import inspect

from starlette.concurrency import run_in_threadpool

# --- IMPORT MODULES CŨ ---
from mst.router import is_mst_query
from mst.handler import handle_mst_query
from law_db_query.handler import handle_law_count_query

try:
    # ⚠️ Import cả biến CHART_STORE từ file tools
    from iz_agent.agent import agent_executor as iz_executor
    from iz_agent.tools import CHART_STORE 
    
    iz_executor.return_intermediate_steps = True 
    IZ_AGENT_AVAILABLE = True
except ImportError as e:
    print(f"⚠️ Warning: IZ Agent không khả dụng: {e}")
    iz_executor = None
    CHART_STORE = {}
    IZ_AGENT_AVAILABLE = False

try:
    # Import mn_agent
    from mn_agent.agent import agent_executor as mn_executor
    MN_AGENT_AVAILABLE = True
except ImportError as e:
    print(f"⚠️ Warning: MN Agent không khả dụng: {e}")
    mn_executor = None
    MN_AGENT_AVAILABLE = False

# ===============================
# Import Chatbot từ app.py
# ===============================
import app  # app.py: LangChain chatbot + vectordb + llm + emb + sheet funcs
CHATBOT_AVAILABLE = True


# ===============================
# Helper: Router nhận diện câu hỏi KCN
# ===============================
def is_iz_agent_query(message: str) -> bool:
    """Kiểm tra xem câu hỏi có liên quan đến BĐS Công Nghiệp (KCN/CCN) không"""
    keywords = [
        "kcn", "ccn", "khu công nghiệp", "cụm công nghiệp",
        "giá thuê", "giá đất", "diện tích", "biểu đồ", "so sánh", 
        "mật độ", "tỷ lệ lấp đầy", "chủ đầu tư", "vẽ biểu đồ",
        "danh sách", "liệt kê", "bao nhiêu", "ở đâu"
    ]
    msg = message.lower()
    
    # LOẠI TRỪ câu hỏi về mã ngành trước (ưu tiên MN Agent)
    mn_keywords = [
        "mã ngành", "ma nganh", "ngành nghề", "nganh nghe", 
        "vsic", "mã số ngành", "ma so nganh", "cấp 1", "cấp 2", "cấp 3", "cấp 4"
    ]
    
    # Nếu có từ khóa mã ngành, không route sang IZ Agent
    if any(kw in msg for kw in mn_keywords):
        return False
    
    # Nếu có "ngành" mà không có KCN/CCN context, không route sang IZ Agent  
    if "ngành" in msg or "nganh" in msg:
        if not any(kw in msg for kw in ["kcn", "ccn", "khu công nghiệp", "cụm công nghiệp"]):
            return False
    
    # Nếu chỉ hỏi chung chung "liệt kê" mà không có context KCN/CCN, không route sang IZ Agent
    if any(kw in msg for kw in ["liệt kê", "liet ke", "danh sách", "danh sach"]):
        if not any(kw in msg for kw in ["kcn", "ccn", "khu công nghiệp", "cụm công nghiệp", "nhà xưởng", "kho xưởng"]):
            return False
    
    return any(k in msg for k in keywords)


# ===============================
# Helper: Router nhận diện câu hỏi về mã ngành
# ===============================
def is_mn_agent_query(message: str) -> bool:
    """
    Kiểm tra xem câu hỏi có liên quan đến mã ngành nghề không
    
    Args:
        message: Câu hỏi từ người dùng
    
    Returns:
        True nếu là câu hỏi về mã ngành, False nếu không
    
    Requirements: 8.2, 8.3, 9.1, 9.2, 9.3, 9.4, 9.6
    """
    import re
    
    msg = message.lower()
    
    # Từ khóa chính về mã ngành (mở rộng)
    keywords = [
        "mã ngành", "ma nganh",
        "ngành nghề", "nganh nghe", 
        "vsic", "mã số ngành", "ma so nganh",
        "phân loại ngành", "phan loai nganh",
        "mã nghề", "ma nghe",
        "ngành kinh doanh", "nganh kinh doanh",
        "hoạt động kinh doanh", "hoat dong kinh doanh",
        "lĩnh vực kinh doanh", "linh vuc kinh doanh"
    ]
    
    # Kiểm tra từ khóa
    if any(kw in msg for kw in keywords):
        return True
    
    # Kiểm tra pattern mã ngành (VD: "01.11", "47.11.0", "12.34", "1130")
    if re.search(r'\d{2,4}\.?\d{0,2}\.?\d{0,2}', msg):
        # Kiểm tra xem có phải là mã ngành không (không phải số điện thoại, năm, etc.)
        if re.search(r'\b\d{2,4}\.?\d{0,2}\.?\d{0,2}\b', msg):
            return True
    
    # Từ khóa hoạt động kinh doanh phổ biến
    business_activities = [
        "trồng", "trong", "chăn nuôi", "chan nuoi", "nuôi", "nuoi",
        "sản xuất", "san xuat", "chế biến", "che bien", "gia công", "gia cong",
        "may mặc", "may mac", "dệt", "det", "may", 
        "bán lẻ", "ban le", "bán buôn", "ban buon", "kinh doanh", 
        "vận tải", "van tai", "logistics", "kho bãi", "kho bai",
        "xây dựng", "xay dung", "thi công", "thi cong",
        "du lịch", "khách sạn", "khach san", "nhà hàng", "nha hang",
        "giáo dục", "giao duc", "đào tạo", "dao tao",
        "y tế", "y te", "chăm sóc sức khỏe", "cham soc suc khoe",
        "công nghệ thông tin", "cong nghe thong tin", "phần mềm", "phan mem",
        "tài chính", "tai chinh", "ngân hàng", "ngan hang", "bảo hiểm", "bao hiem"
    ]
    
    # Kiểm tra hoạt động kinh doanh
    if any(activity in msg for activity in business_activities):
        return True
    
    # Từ khóa về cấp ngành (mở rộng)
    level_keywords = [
        "cấp 1", "cap 1", "cấp 2", "cap 2", "cấp 3", "cap 3", "cấp 4", "cap 4",
        "cấp một", "cấp hai", "cấp ba", "cấp bốn",
        "liệt kê", "liet ke", "danh sách", "danh sach", 
        "xem", "hiển thị", "hien thi", "cho tôi xem", "cho toi xem",
        "tất cả", "tat ca", "các ngành", "cac nganh"
    ]
    
    # Kiểm tra từ khóa cấp ngành kết hợp với ngành
    level_patterns = [
        "liệt kê.*ngành", "liet ke.*nganh",
        "danh sách.*ngành", "danh sach.*nganh", 
        "xem.*ngành", "xem.*nganh",
        "các ngành.*cấp", "cac nganh.*cap",
        "ngành.*cấp", "nganh.*cap"
    ]
    
    # Kiểm tra pattern kết hợp
    import re
    if any(re.search(pattern, msg) for pattern in level_patterns):
        return True
    
    # Kiểm tra từ khóa cấp ngành
    if any(kw in msg for kw in level_keywords):
        # Đảm bảo có từ "ngành" trong câu
        if "ngành" in msg or "nganh" in msg:
            return True
    
    # Từ khóa về tên ngành cụ thể (để nhận diện câu hỏi tìm ngược)
    name_query_patterns = [
        "có mã ngành", "co ma nganh", "thuộc mã ngành", "thuoc ma nganh",
        "là mã ngành", "la ma nganh", "mã ngành của", "ma nganh cua",
        "mã ngành cho", "ma nganh cho", "tìm mã ngành cho", "tim ma nganh cho",
        "ngành.*có mã", "nganh.*co ma", "ngành.*thuộc mã", "nganh.*thuoc ma"
    ]
    
    # Kiểm tra pattern tìm ngược (tên ngành → mã ngành)
    import re
    if any(re.search(pattern, msg) for pattern in name_query_patterns):
        return True
    
    # Loại trừ câu hỏi về KCN/CCN (tránh conflict với iz_agent)
    exclude_kcn = ["kcn", "ccn", "khu công nghiệp", "cụm công nghiệp", "nhà xưởng", "kho xưởng"]
    if any(kw in msg for kw in exclude_kcn):
        return False
    
    # Loại trừ câu hỏi về mã số thuế (tránh conflict với mst module)
    exclude_mst = ["mã số thuế", "ma so thue", "mst", "thuế", "thue"]
    if any(kw in msg for kw in exclude_mst):
        return False
    
    return False


# ===============================
# Helper: parse JSON string từ pipeline
# ===============================
def try_parse_json_string(s: Any):
    if not isinstance(s, str):
        return None
    t = s.strip()
    if not t:
        return None
    if (t.startswith("{") and t.endswith("}")) or (t.startswith("[") and t.endswith("]")):
        try:
            return json.loads(t)
        except Exception:
            return None
    return None


# ===============================
# Lấy các hằng số từ app.py
# ===============================
CONTACT_TRIGGER_RESPONSE = None
if CHATBOT_AVAILABLE and hasattr(app, "CONTACT_TRIGGER_RESPONSE"):
    CONTACT_TRIGGER_RESPONSE = app.CONTACT_TRIGGER_RESPONSE
else:
    CONTACT_TRIGGER_RESPONSE = (
        "Anh/chị vui lòng để lại tên và số điện thoại, chuyên gia của IIP sẽ liên hệ "
        "và giải đáp các yêu cầu của anh/chị ạ."
    )

# ===============================
# Kiểm tra Google Sheet availability
# ===============================
SHEET_AVAILABLE = False
try:
    if CHATBOT_AVAILABLE and hasattr(app, "save_contact_info") and hasattr(app, "is_valid_phone"):
        SHEET_AVAILABLE = True
except Exception:
    pass


# --- Khai báo Model cho dữ liệu đầu vào ---
class Question(BaseModel):
    question: str
    phone: Optional[str] = None
    name: Optional[str] = None
    url: Optional[str] = None


class ContactInfo(BaseModel):
    original_question: str
    phone: str
    name: Optional[str] = None


# ---------------------------------------
# 1️⃣ Khởi tạo FastAPI App + bật CORS
# ---------------------------------------
app_fastapi = FastAPI(
    title="Chatbot Luật Lao động API",
    description="API cho mô hình chatbot",
    version="2.0.0"
)

app_fastapi.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------
# 2️⃣ Route kiểm tra hoạt động (GET /)
# ---------------------------------------
@app_fastapi.get("/", summary="Kiểm tra trạng thái API")
async def home():
    vectordb_status = "Unknown"
    if CHATBOT_AVAILABLE:
        try:
            stats = app.get_vectordb_stats()
            vectordb_status = f"Ready ({stats.get('total_documents', 0)} docs)" if stats.get("exists") else "Empty"
        except Exception as e:
            vectordb_status = f"Error: {str(e)}"

    return {
        "message": "✅ Chatbot API đang hoạt động (v2 - IZ Agent + MN Agent Integrated).",
        "iz_agent_status": "Available" if IZ_AGENT_AVAILABLE else "Not Available",
        "mn_agent_status": "Available" if MN_AGENT_AVAILABLE else "Not Available",
        "chatbot_status": "Available" if CHATBOT_AVAILABLE else "Not Available",
        "vectordb_status": vectordb_status,
    }


# ---------------------------------------
# 3️⃣ Route chính: /chat (POST)
# ---------------------------------------
@app_fastapi.post("/chat", summary="Trả lời câu hỏi từ Chatbot")
async def predict(data: Question, request: Request):
    question = (data.question or "").strip()
    if not question:
        raise HTTPException(status_code=400, detail="Câu hỏi bị rỗng.")

    try:
        answer: Optional[str] = None
        requires_contact = False

        # ===============================
        # 0️⃣ LAW COUNT – SQL FIRST
        # ===============================
        payload = handle_law_count_query(question)
        if isinstance(payload, dict) and payload.get("intent") == "law_count":
            if not CHATBOT_AVAILABLE:
                return {"answer": "Backend chưa sẵn sàng."}

            response = await run_in_threadpool(
                app.chatbot.invoke,
                {"message": question, "law_count": payload["total_laws"]},
                {"configurable": {"session_id": "default_session"}}
            )
            return {"answer": response, "requires_contact": False}

        # ===============================
        # 1️⃣ MST INTENT (Tra cứu Mã số thuế)
        # ===============================
        if is_mst_query(question):
            if not CHATBOT_AVAILABLE:
                return {"answer": "Backend chưa sẵn sàng."}

            mst_answer = await run_in_threadpool(
                handle_mst_query,
                message=question,
                llm=app.llm,
                embedding=app.emb
            )
            return {"answer": mst_answer, "requires_contact": False}
# ===============================
        # 2️⃣ IZ AGENT (XỬ LÝ ẢNH THÔNG MINH)
        # ===============================
        if IZ_AGENT_AVAILABLE and is_iz_agent_query(question):
            try:
                # GỌI AGENT (không cần lịch sử chat)
                import asyncio
                iz_result = await run_in_threadpool(
                    iz_executor.invoke,
                    {"input": question, "chat_history": []}
                )

                final_output = iz_result.get("output", "")
                
                # --- [QUAN TRỌNG] TÌM VÉ (ID) VÀ ĐỔI LẤY ẢNH THẬT ---
                tool_payload = None
                
                # Duyệt qua các bước chạy của Tool
                for action, output in iz_result.get("intermediate_steps", []):
                    if isinstance(output, dict):
                        output_type = output.get("type")
                        
                        # Xử lý flexible search tool (có biểu đồ)
                        if output_type == "excel_visualize_with_data":
                            tool_payload = output
                            tool_payload["text"] = final_output
                            
                            # ✅ CHECK: Có vé (chart_id) không?
                            chart_id = tool_payload.get("chart_id")
                            
                            if chart_id and chart_id in CHART_STORE:
                                # ✅ LẤY ẢNH THẬT TỪ KHO RA
                                print(f"📸 Đang lấy ảnh từ kho (ID: {chart_id})...")
                                real_base64 = CHART_STORE[chart_id]
                                
                                # Gán vào payload để trả về cho Frontend/Postman
                                tool_payload["chart_base64"] = real_base64
                                
                                # (Tùy chọn) Xóa khỏi kho để giải phóng RAM sau khi dùng xong
                                # del CHART_STORE[chart_id]
                            break
                        
                        # Xử lý single zone tool (có coordinates)
                        elif output_type in ["single_zone_info", "multiple_choices", "error"]:
                            tool_payload = output
                            tool_payload["text"] = final_output
                            break
                
                # Không cần lưu lịch sử chat nữa

                # TRẢ VỀ CHO POSTMAN
                if tool_payload:
                    payload_type = tool_payload.get("type")
                    
                    # Làm sạch payload trước khi trả về
                    import json
                    import math
                    import pandas as pd
                    
                    def clean_for_json(obj):
                        if isinstance(obj, dict):
                            return {k: clean_for_json(v) for k, v in obj.items()}
                        elif isinstance(obj, list):
                            return [clean_for_json(item) for item in obj]
                        elif isinstance(obj, float):
                            if math.isnan(obj) or math.isinf(obj):
                                return None
                        elif pd.isna(obj):
                            return None
                        elif isinstance(obj, str) and obj.lower() in ['nan', 'inf', '-inf']:
                            return None
                        return obj
                    
                    clean_payload = clean_for_json(tool_payload)
                    
                    # Cắt log để server không lag khi print
                    debug_payload = clean_payload.copy()
                    if "chart_base64" in debug_payload and debug_payload["chart_base64"]:
                        debug_payload["chart_base64"] = "✅ [IMAGE DATA EXISTS - HIDDEN FROM LOG]"
                    
                    print(f"🚀 Response sent to Client: {json.dumps(debug_payload, ensure_ascii=False)}")

                    # Trả về response phù hợp với từng loại tool
                    if payload_type == "excel_visualize_with_data":
                        return {
                            "answer": final_output,
                            "type": "excel_visualize_with_data",
                            "payload": clean_payload
                        }
                    elif payload_type in ["single_zone_info", "multiple_choices"]:
                        return {
                            "answer": final_output,
                            "type": payload_type,
                            "payload": clean_payload
                        }
                    elif payload_type == "error":
                        return {
                            "answer": final_output,
                            "type": "text"
                        }
                    else:
                        return {
                            "answer": final_output,
                            "type": "excel_visualize_with_data",
                            "payload": clean_payload
                        }
                
                return {"answer": final_output, "type": "text"}

            except Exception as e:
                print(f"❌ IZ Agent Error: {e}")
                return {
                    "answer": "Đã xảy ra lỗi khi xử lý câu hỏi. Vui lòng thử lại.",
                    "type": "text"
                }

        # ===============================
        # 2.5️⃣ MN AGENT (XỬ LÝ MÃ NGÀNH)
        # ===============================
        if MN_AGENT_AVAILABLE and is_mn_agent_query(question):
            try:
                # Lấy chat history từ app.py (tương tự iz_agent)
                if CHATBOT_AVAILABLE and hasattr(app, "get_history"):
                    try:
                        history_manager = app.get_history("default_session")
                        # Lấy 10 tin nhắn gần nhất để tiết kiệm token
                        current_messages = history_manager.messages[-10:] if history_manager.messages else []
                        
                        # Chuyển đổi format cho mn_agent (từ LangChain messages sang tuples)
                        chat_history = []
                        for msg in current_messages:
                            if hasattr(msg, 'type'):
                                if msg.type == 'human':
                                    chat_history.append(("human", msg.content))
                                elif msg.type == 'ai':
                                    chat_history.append(("ai", msg.content))
                        
                    except Exception as e:
                        print(f"⚠️ Warning: Không thể lấy chat history: {e}")
                        chat_history = []
                else:
                    chat_history = []
                
                # Gọi mn_agent executor với input và chat_history
                mn_result = await run_in_threadpool(
                    mn_executor.invoke,
                    {"input": question, "chat_history": chat_history}
                )
                
                # Lấy output từ mn_agent
                output_text = mn_result.get("output", "Không có phản hồi từ hệ thống mã ngành.")
                
                # Lưu user message và AI response vào history_manager
                if CHATBOT_AVAILABLE and hasattr(app, "get_history"):
                    try:
                        history_manager = app.get_history("default_session")
                        history_manager.add_user_message(question)
                        history_manager.add_ai_message(output_text)
                    except Exception as e:
                        print(f"⚠️ Warning: Không thể lưu chat history: {e}")
                
                # Trả về kết quả với prefix đặc biệt
                return {
                    "answer": f"🤖 Bot (Mã Ngành Agent):\n{output_text}",
                    "type": "text",
                    "requires_contact": False
                }
                
            except Exception as e:
                print(f"❌ MN Agent Error: {e}")
                return {
                    "answer": "Đã xảy ra lỗi khi xử lý câu hỏi về mã ngành. Vui lòng thử lại.",
                    "type": "text",
                    "requires_contact": False
                }

        # ===============================
        # 3️⃣ FALLBACK: CHATBOT THƯỜNG (RAG PDF)
        # ===============================
        if CHATBOT_AVAILABLE and hasattr(app, "chatbot"):
            try:
                if inspect.iscoroutinefunction(app.chatbot.invoke):
                    response = await app.chatbot.invoke(
                        {"message": question},
                        {"configurable": {"session_id": "default_session"}}
                    )
                else:
                    response = await run_in_threadpool(
                        app.chatbot.invoke,
                        {"message": question},
                        {"configurable": {"session_id": "default_session"}}
                    )

                # Xử lý kết quả trả về
                if isinstance(response, dict) and "output" in response:
                    answer = response["output"]
                elif isinstance(response, str):
                    answer = response
                else:
                    answer = str(response)

                if answer and answer.strip() == CONTACT_TRIGGER_RESPONSE.strip():
                    requires_contact = True

            except Exception as e:
                print(f"❌ Chatbot Invoke Error: {e}")
                answer = "Xin lỗi, hệ thống đang gặp sự cố gián đoạn."
        else:
            answer = "Hệ thống đang bảo trì (Backend unavailable)."

        # Ghi log liên hệ nếu có sđt
        if data.phone and SHEET_AVAILABLE:
            try:
                await run_in_threadpool(app.save_contact_info, question, data.phone, data.name or "")
            except Exception:
                pass

        return {
            "answer": answer,
            "requires_contact": requires_contact
        }

    except Exception as e:
        print(f"❌ Lỗi API: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------
# 4️⃣ Route: /submit-contact
# ---------------------------------------
@app_fastapi.post("/submit-contact")
async def submit_contact(data: ContactInfo):
    if not SHEET_AVAILABLE:
        raise HTTPException(status_code=503, detail="Service unavailable.")

    try:
        await run_in_threadpool(
            app.save_contact_info,
            data.original_question,
            data.phone,
            data.name or ""
        )
        return {"success": True, "message": "Đã lưu thông tin liên hệ."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ---------------------------------------
# Run server
# ---------------------------------------
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run("main:app_fastapi", host="0.0.0.0", port=port, log_level="info", reload=True)