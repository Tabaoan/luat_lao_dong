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
except ImportError:
    iz_executor = None
    CHART_STORE = {}
    IZ_AGENT_AVAILABLE = False

# ===============================
# Import Chatbot từ app.py
# ===============================
try:
    import app  # app.py: LangChain chatbot + vectordb + llm + emb + sheet funcs
    CHATBOT_AVAILABLE = True
    print("✅ Đã import thành công module 'app'")
except ImportError as e:
    app = None
    CHATBOT_AVAILABLE = False
    print(f"⚠️ Could not import 'app' module. Error: {e}")


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
    return any(k in msg for k in keywords)


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
        "message": "✅ Chatbot API đang hoạt động (v2 - IZ Agent Integrated).",
        "iz_agent_status": "Available" if IZ_AGENT_AVAILABLE else "Not Available",
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
        return {"answer": "Câu hỏi bị rỗng.", "error": True}

    try:

        # ===============================
        # 0️⃣ LAW COUNT – SQL FIRST
        # ===============================
        payload = handle_law_count_query(question)
        if isinstance(payload, dict) and payload.get("intent") == "law_count":
            if not CHATBOT_AVAILABLE:
                return {"answer": "Backend chưa sẵn sàng.", "error": True}

            response = await run_in_threadpool(
                app.chatbot.invoke,
                {"message": question, "law_count": payload["total_laws"]}
            )
            
            return {"answer": response}

        # ===============================
        # 1️⃣ MST INTENT (Tra cứu Mã số thuế)
        # ===============================
        if is_mst_query(question):
            if not CHATBOT_AVAILABLE:
                return {"answer": "Backend chưa sẵn sàng.", "error": True}

            mst_answer = await run_in_threadpool(
                handle_mst_query,
                message=question,
                llm=app.llm,
                embedding=app.emb
            )
            return {"answer": mst_answer}
        # ===============================
        # 2️⃣ IZ AGENT (XỬ LÝ ẢNH THÔNG MINH)
        # ===============================
        if IZ_AGENT_AVAILABLE and is_iz_agent_query(question):
            try:
                # GỌI AGENT (không cần lịch sử chat)
                iz_result = await run_in_threadpool(
                    iz_executor.invoke,
                    {"input": question, "chat_history": []}
                )

                final_output = iz_result.get("output", "")
                
                # Duyệt qua các bước chạy của Tool
                for action, output in iz_result.get("intermediate_steps", []):
                    if isinstance(output, dict):
                        output_type = output.get("type")
                        
                        # Xử lý flexible search tool (có biểu đồ)
                        if output_type == "excel_visualize_with_data":
                            chart_id = output.get("chart_id")
                            
                            if chart_id and chart_id in CHART_STORE:
                                real_base64 = CHART_STORE[chart_id]
                                output["chart_base64"] = real_base64
                            
                            # Trả về answer + chart base64 + data
                            return {
                                "answer": final_output,
                                "chart_base64": output.get("chart_base64"),
                                "data": output.get("data", []),
                                "province": output.get("province"),
                                "count": output.get("count"),
                                "total_found": output.get("total_found")
                            }
                        
                        # Xử lý single zone tool (có coordinates)
                        elif output_type == "single_zone_info":
                            return {
                                "answer": final_output,
                                "zone_data": output.get("data", {}),
                                "coordinates": output.get("coordinates")
                            }
                        
                        # Xử lý multiple choices
                        elif output_type == "multiple_choices":
                            return {
                                "answer": output.get("message", final_output),
                                "choices": output.get("choices", []),
                                "total_found": output.get("total_found")
                            }
                        
                        # Xử lý error
                        elif output_type == "error":
                            return {
                                "answer": output.get("message", "Đã xảy ra lỗi"),
                                "error": True
                            }
                
                # Không có tool payload - trả về text thuần
                return {"answer": final_output}

            except Exception as e:
                print(f"❌ IZ Agent Error: {e}")
                return {
                    "answer": "Đã xảy ra lỗi khi xử lý câu hỏi. Vui lòng thử lại.",
                    "error": True
                }

        # ===============================
        # 3️⃣ FALLBACK: CHATBOT THƯỜNG (RAG PDF)
        # ===============================
        if CHATBOT_AVAILABLE and hasattr(app, "chatbot"):
            try:
                # Kiểm tra điều luật cụ thể trước
                from law_db_query.handler import handle_law_article_query
                law_article_response = handle_law_article_query(question)
                if law_article_response:
                    return {"answer": law_article_response}
                
                if inspect.iscoroutinefunction(app.chatbot.invoke):
                    response = await app.chatbot.invoke({"message": question})
                else:
                    response = await run_in_threadpool(
                        app.chatbot.invoke,
                        {"message": question}
                    )

                # Xử lý kết quả trả về
                if isinstance(response, dict) and "output" in response:
                    answer = response["output"]
                elif isinstance(response, str):
                    answer = response
                else:
                    answer = str(response)

                # Kiểm tra nếu cần liên hệ
                requires_contact = False
                if answer and answer.strip() == CONTACT_TRIGGER_RESPONSE.strip():
                    requires_contact = True
                
                return {
                    "answer": answer,
                    "requires_contact": requires_contact
                }

            except Exception as e:
                print(f"❌ Chatbot Invoke Error: {e}")
                return {
                    "answer": "Xin lỗi, hệ thống đang gặp sự cố gián đoạn.",
                    "error": True
                }
        else:
            return {
                "answer": "Hệ thống đang bảo trì (Backend unavailable).",
                "error": True
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