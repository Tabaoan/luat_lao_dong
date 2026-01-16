# main_local.py

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import os
import uvicorn
from typing import Optional, Any, Dict
from starlette.concurrency import run_in_threadpool

from mst.router import is_mst_query
from mst.handler import handle_mst_query
from law_db_query.handler import handle_law_count_query
from excel_visualize import (
    is_excel_visualize_intent,
    handle_excel_visualize
)

import json
from pathlib import Path
import inspect

from excel_query.excel_query import ExcelQueryHandler
from fastapi import Request
import uuid

# ===============================
# Helper: parse JSON string (flowchart/excel json từ pipeline)
# ===============================
def try_parse_json_string(s: Any):
    """
    Nếu s là JSON string thì parse ra dict/list; không thì trả None.
    """
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
# Import Chatbot từ app.py
# ===============================
try:
    import app
    CHATBOT_AVAILABLE = True
    print("✅ [LOCAL] Đã import thành công module 'app'")
except ImportError as e:
    app = None
    CHATBOT_AVAILABLE = False
    print(f"⚠️ [LOCAL] Could not import 'app' module. Error: {e}")


# ===============================
# Lấy các hằng số từ app.py
# ===============================
CONTACT_TRIGGER_RESPONSE = None
if CHATBOT_AVAILABLE and hasattr(app, "CONTACT_TRIGGER_RESPONSE"):
    CONTACT_TRIGGER_RESPONSE = app.CONTACT_TRIGGER_RESPONSE
    print("✅ [LOCAL] Đã load CONTACT_TRIGGER_RESPONSE từ app.py")
else:
    CONTACT_TRIGGER_RESPONSE = (
        "Anh/chị vui lòng để lại tên và số điện thoại, chuyên gia của IIP sẽ liên hệ "
        "và giải đáp các yêu cầu của anh/chị ạ."
    )
    print("⚠️ [LOCAL] Sử dụng CONTACT_TRIGGER_RESPONSE mặc định")


# ===============================
# Kiểm tra Google Sheet availability
# ===============================
SHEET_AVAILABLE = False
try:
    if CHATBOT_AVAILABLE and hasattr(app, "save_contact_info") and hasattr(app, "is_valid_phone"):
        SHEET_AVAILABLE = True
        print("✅ [LOCAL] Google Sheet functions đã sẵn sàng từ app.py")
    else:
        print("⚠️ [LOCAL] Google Sheet functions not found in app.py")
except Exception as e:
    print(f"⚠️ [LOCAL] Error checking Google Sheet availability: {e}")


# --- Khai báo Model cho dữ liệu đầu vào ---
class Question(BaseModel):
    question: str
    phone: Optional[str] = None
    session_id: Optional[str] = None
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
    title="Chatbot Luật Lao động API (LOCAL TEST)",
    description="API cho mô hình chatbot - bản local test Postman",
    version="1.0.0-local"
)

origins = ["*"]

app_fastapi.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------
# 2️⃣ Init ExcelQueryHandler (KCN/CCN)
# ---------------------------------------
BASE_DIR = Path(__file__).resolve().parent

EXCEL_FILE_PATH = str(BASE_DIR / "data" / "IIPMap_FULL_63_COMPLETE.xlsx")
GEOJSON_IZ_PATH = str(BASE_DIR / "map_ui" / "industrial_zones.geojson")

#  Check tồn tại để test local dễ debug
if not Path(EXCEL_FILE_PATH).exists():
    print(f" [LOCAL] Không tìm thấy EXCEL_FILE_PATH: {EXCEL_FILE_PATH}")
else:
    print(f" [LOCAL] EXCEL_FILE_PATH: {EXCEL_FILE_PATH}")

if not Path(GEOJSON_IZ_PATH).exists():
    print(f" [LOCAL] Không tìm thấy GEOJSON_IZ_PATH: {GEOJSON_IZ_PATH}")
else:
    print(f" [LOCAL] GEOJSON_IZ_PATH: {GEOJSON_IZ_PATH}")

excel_kcn_handler = ExcelQueryHandler(
    excel_path=EXCEL_FILE_PATH,
    geojson_path=GEOJSON_IZ_PATH
)

print(" [LOCAL] Endpoints test nhanh:")
print("   - GET  http://127.0.0.1:10000/")
print("   - POST http://127.0.0.1:10000/chat  body: {\"question\":\"Danh sách khu công nghiệp ở Bắc Ninh\"}")
print("   - POST http://127.0.0.1:10000/chat  body: {\"question\":\"Vẽ flowchart luồng web nông dân\"}")


# ---------------------------------------
# 3️⃣ Route kiểm tra hoạt động (GET /)
# ---------------------------------------
@app_fastapi.get("/", summary="Kiểm tra trạng thái API")
async def home():
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
        "message": "✅ Chatbot Luật Lao động API (LOCAL) đang hoạt động.",
        "usage": "Gửi POST tới /chat với JSON { 'question': 'Câu hỏi của bạn' }",
        "chatbot_status": "Available" if CHATBOT_AVAILABLE else "Not Available",
        "vectordb_status": vectordb_status,
        "sheet_status": "Available" if SHEET_AVAILABLE else "Not Available",
        "contact_trigger": CONTACT_TRIGGER_RESPONSE,
        "excel_file_exists": Path(EXCEL_FILE_PATH).exists(),
        "geojson_file_exists": Path(GEOJSON_IZ_PATH).exists(),
    }


# ---------------------------------------
# 4️⃣ Route chính: /chat (POST)
# ---------------------------------------
@app_fastapi.post("/chat", summary="Dự đoán/Trả lời câu hỏi từ Chatbot")
async def predict(data: Question, request: Request):
    question = (data.question or "").strip()
    if not question:
        raise HTTPException(status_code=400, detail="Thiếu trường 'question' hoặc câu hỏi bị rỗng.")
    session = (
        (data.session_id or "").strip()
        or (request.headers.get("X-Session-Id") or "").strip()
    )
    if not session:
        session = f"anon-{uuid.uuid4()}"
    try:
        answer: Optional[str] = None
        requires_contact = False

        # ===============================
        # 0️⃣ LAW COUNT – SQL FIRST
        # ===============================
        payload = handle_law_count_query(question)
        if isinstance(payload, dict) and payload.get("intent") == "law_count":
            if not CHATBOT_AVAILABLE or not hasattr(app, "chatbot"):
                return {"answer": "Backend chưa sẵn sàng (không import được app.py/chatbot).", "requires_contact": False}

            response = await run_in_threadpool(
                app.chatbot.invoke,
                {"message": question, "law_count": payload["total_laws"]},
                config={"configurable": {"session_id": session}}
            )

            # ✅ NEW: parse flowchart json nếu có
            parsed = try_parse_json_string(response)
            if isinstance(parsed, dict) and parsed.get("type") == "flowchart":
                return {
                    "answer": "Đây là flowchart do ChatIIP tạo cho bạn:",
                    "type": "flowchart",
                    "payload": {
                        "format": parsed.get("format", "mermaid"),
                        "code": parsed.get("code", ""),
                        "explanation": parsed.get("explanation", "")
                    },
                    "requires_contact": False
                }

            return {"answer": response, "requires_contact": False}

        # ===============================
        # MST INTENT (ƯU TIÊN CAO NHẤT)
        # ===============================
        if is_mst_query(question):
            if not CHATBOT_AVAILABLE:
                return {"answer": "Backend chưa sẵn sàng (không import được app.py).", "requires_contact": False}

            mst_answer = await run_in_threadpool(
                handle_mst_query,
                message=question,
                llm=app.llm,
                embedding=app.emb
            )
            return {"answer": mst_answer, "requires_contact": False}

        # ===============================
        # EXCEL VISUALIZE
        # ===============================
        if is_excel_visualize_intent(question):
            if not CHATBOT_AVAILABLE:
                return {
                    "answer": "Backend chưa sẵn sàng ",
                    "requires_contact": False,
                    "session_id": session
                }

            excel_result = await run_in_threadpool(
                handle_excel_visualize,
                message=question,
                #excel_handler=app.excel_handler
            )
            return {
                "answer": "Đây là biểu đồ do Chatiip tạo cho bạn: ",
                "type": "excel_visualize",
                "payload": excel_result,
                "requires_contact": False,
                "session_id": session
            }

        # ===============================
        # 1️⃣ EXCEL KCN/CCN (BẢNG + TỌA ĐỘ) - ƯU TIÊN TRƯỚC LLM
        # ===============================
        handled, excel_payload = await run_in_threadpool(
            excel_kcn_handler.process_query,
            question,
            True
        )

        if handled and excel_payload:
            try:
                excel_obj = json.loads(excel_payload) if isinstance(excel_payload, str) else excel_payload
            except Exception:
                excel_obj = {"error": "ExcelQuery trả về dữ liệu không hợp lệ."}

            # Nếu có lỗi yêu cầu làm rõ (thiếu tỉnh/thiếu loại)
            if isinstance(excel_obj, dict) and excel_obj.get("error"):
                return {
                    "answer": excel_obj,
                    "type": "excel_query",
                    "map_intent": None,
                    "requires_contact": False
                }

            # Build iz_list từ data[] (data đã có coordinates)
            iz_list = []
            if isinstance(excel_obj, dict):
                for r in excel_obj.get("data", []) or []:
                    coords = r.get("coordinates")
                    if isinstance(coords, list) and len(coords) == 2:
                        iz_list.append({
                            "name": r.get("Tên", ""),
                            "kind": r.get("Loại", excel_obj.get("type")),
                            "address": r.get("Địa chỉ", ""),
                            "coordinates": coords
                        })

            province = excel_obj.get("province") if isinstance(excel_obj, dict) else None

            if province and province != "TOÀN QUỐC":
                map_intent = {
                    "type": "province",
                    "province": province,
                    "iz_list": iz_list,
                    "kind": excel_obj.get("type")
                }
            else:
                map_intent = {
                    "type": "points",
                    "iz_list": iz_list,
                    "kind": excel_obj.get("type") if isinstance(excel_obj, dict) else None
                }

            return {
                "answer": excel_obj,
                "type": "excel_query",
                "map_intent": map_intent,
                "requires_contact": False
            }

        # ===============================
        # 2️⃣ FALLBACK: gọi chatbot thật
        # ===============================
        if CHATBOT_AVAILABLE and hasattr(app, "chatbot") and hasattr(app.chatbot, "invoke"):
            try:
                # invoke async hay sync?
                if inspect.iscoroutinefunction(app.chatbot.invoke):
                    response = await app.chatbot.invoke(
                        {"message": question},
                        config={"configurable": {"session_id": session}}
                    )
                else:
                    response = await run_in_threadpool(
                        app.chatbot.invoke,
                        {"message": question},
                        config={"configurable": {"session_id": session}}
                    )

                # Chuẩn hóa sang string
                if isinstance(response, dict) and "output" in response:
                    answer = response["output"]
                elif isinstance(response, str):
                    answer = response
                else:
                    answer = f"Lỗi: Chatbot trả về định dạng không mong muốn: {repr(response)}"

                #  NEW: parse JSON string từ pipeline (FLOWCHART)
                parsed = try_parse_json_string(answer)
                if isinstance(parsed, dict) and parsed.get("type") == "flowchart":
                    return {
                        "answer": "Đây là flowchart do ChatIIP tạo cho bạn:",
                        "type": "flowchart",
                        "payload": {
                            "format": parsed.get("format", "mermaid"),
                            "code": parsed.get("code", ""),
                            "explanation": parsed.get("explanation", "")
                        },
                        "requires_contact": False
                    }

                # Trigger contact
                if answer and answer.strip() == CONTACT_TRIGGER_RESPONSE.strip():
                    requires_contact = True

            except Exception as invoke_error:
                print(f" [LOCAL] Lỗi khi gọi chatbot.invoke: {invoke_error}")
                answer = "Xin lỗi, đã xảy ra lỗi khi xử lý câu hỏi của bạn."
        else:
            answer = f"(Chatbot mô phỏng - LỖI BACKEND: Không tìm thấy đối tượng app.chatbot) Bạn hỏi: '{question}'"

        # Nếu gửi phone sớm
        if data.phone and SHEET_AVAILABLE and CHATBOT_AVAILABLE:
            try:
                await run_in_threadpool(
                    app.save_contact_info,
                    question,
                    data.phone,
                    data.name or ""
                )
            except Exception as sheet_error:
                print(f" [LOCAL] Lỗi ghi Google Sheet: {sheet_error}")

        return {
            "answer": answer,
            "requires_contact": requires_contact,
            "session_id": session
        }

    except HTTPException:
        raise
    except Exception as e:
        print(f" [LOCAL] LỖI CHATBOT: {e}")
        raise HTTPException(status_code=500, detail=f"Lỗi xử lý Chatbot: {str(e)}")


# ---------------------------------------
# 5️⃣ Route: /submit-contact (POST)
# ---------------------------------------
@app_fastapi.post("/submit-contact", summary="Gửi thông tin liên hệ sau khi chatbot yêu cầu")
async def submit_contact(data: ContactInfo):
    if not SHEET_AVAILABLE or not CHATBOT_AVAILABLE:
        raise HTTPException(status_code=503, detail="Google Sheet không khả dụng.")

    phone = (data.phone or "").strip()
    if not app.is_valid_phone(phone):
        raise HTTPException(status_code=400, detail="Số điện thoại không hợp lệ.")

    try:
        await run_in_threadpool(
            app.save_contact_info,
            data.original_question,
            phone,
            data.name or ""
        )

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
        print(f"❌ [LOCAL] Lỗi khi lưu thông tin liên hệ: {e}")
        raise HTTPException(status_code=500, detail=f"Không thể lưu thông tin liên hệ. Lỗi: {str(e)}")


# ---------------------------------------
# 6️⃣ Route: /status (GET)
# ---------------------------------------
@app_fastapi.get("/status", summary="Kiểm tra trạng thái chi tiết của hệ thống")
async def get_status():
    if not CHATBOT_AVAILABLE:
        return {
            "chatbot": "Not Available",
            "vectordb": "Unknown",
            "google_sheet": "Unknown",
            "error": "Module app.py không được import thành công"
        }

    vectordb_info: Dict[str, Any] = {}
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
        vectordb_info = {"status": "Error", "error": str(e)}

    sheet_info = {
        "status": "Available" if SHEET_AVAILABLE else "Not Available",
        "sheet_id": os.getenv("GOOGLE_SHEET_ID", "Not configured")
    }

    return {
        "chatbot": "Available",
        "vectordb": vectordb_info,
        "google_sheet": sheet_info,
        "trigger_response": CONTACT_TRIGGER_RESPONSE,
        "excel_file": EXCEL_FILE_PATH,
        "geojson_file": GEOJSON_IZ_PATH
    }


# ---------------------------------------
# 7️⃣ Run local server
# ---------------------------------------
if __name__ == "__main__":
    # ✅ Local test: bind 127.0.0.1 để Postman dùng localhost/127.0.0.1
    port = int(os.environ.get("PORT", 10000))
    uvicorn.run("main_local:app_fastapi", host="127.0.0.1", port=port, log_level="info", reload=True)
