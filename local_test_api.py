from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import os
import uvicorn
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
    print("✅ [LOCAL] Import thành công module app.py")
except ImportError as e:
    app = None
    CHATBOT_AVAILABLE = False
    print(f"❌ [LOCAL] Không import được app.py: {e}")

# ===============================
# Load CONTACT_TRIGGER_RESPONSE
# ===============================
if CHATBOT_AVAILABLE and hasattr(app, "CONTACT_TRIGGER_RESPONSE"):
    CONTACT_TRIGGER_RESPONSE = app.CONTACT_TRIGGER_RESPONSE
else:
    CONTACT_TRIGGER_RESPONSE = (
        "Anh/chị vui lòng để lại tên và số điện thoại, "
        "chuyên gia của IIP sẽ liên hệ và giải đáp các yêu cầu của anh/chị ạ."
    )

# ===============================
# Google Sheet availability
# ===============================
SHEET_AVAILABLE = (
    CHATBOT_AVAILABLE
    and hasattr(app, "save_contact_info")
    and hasattr(app, "is_valid_phone")
)

# ===============================
# Pydantic Models
# ===============================
class Question(BaseModel):
    question: str
    phone: Optional[str] = None
    name: Optional[str] = None
    url: Optional[str] = None


class ContactInfo(BaseModel):
    original_question: str
    phone: str
    name: Optional[str] = None


# ===============================
# FastAPI App
# ===============================
app_fastapi = FastAPI(
    title="Chatbot Luật Lao động API (LOCAL)",
    description="API test local – logic giống app.py",
    version="1.0.0-local"
)

# ===============================
# CORS (LOCAL: mở toàn bộ)
# ===============================
app_fastapi.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ===============================
# Health check
# ===============================
@app_fastapi.get("/")
async def home():
    vectordb_status = "Unknown"

    if CHATBOT_AVAILABLE:
        try:
            stats = app.get_vectordb_stats()
            vectordb_status = (
                f"Ready ({stats.get('total_documents', 0)} docs)"
                if stats.get("exists")
                else "Empty / Not Found"
            )
        except Exception as e:
            vectordb_status = f"Error: {e}"

    return {
        "message": "✅ Chatbot API LOCAL đang chạy",
        "chatbot": CHATBOT_AVAILABLE,
        "vectordb": vectordb_status,
        "google_sheet": SHEET_AVAILABLE,
        "trigger_response": CONTACT_TRIGGER_RESPONSE,
    }

# ===============================
# CHAT ROUTE
# ===============================
@app_fastapi.post("/chat")
async def chat(data: Question):
    question = data.question.strip()
    if not question:
        raise HTTPException(400, "Thiếu nội dung câu hỏi")

    try:
        # 1️⃣ LAW COUNT
        payload = handle_law_count_query(question)
        if isinstance(payload, dict) and payload.get("intent") == "law_count":
            response = await run_in_threadpool(
                app.chatbot.invoke,
                {"message": question, "law_count": payload["total_laws"]},
                config={"configurable": {"session_id": "local_session"}},
            )
            return {"answer": response, "requires_contact": False}

        # 2️⃣ MST
        if is_mst_query(question):
            answer = await run_in_threadpool(
                handle_mst_query,
                message=question,
                llm=app.llm,
                embedding=app.emb,
            )
            return {"answer": answer, "requires_contact": False}

        # 3️⃣ EXCEL VISUALIZE
        if is_excel_visualize_price_intent(question):
            result = await run_in_threadpool(
                handle_excel_price_visualize,
                message=question,
                excel_handler=app.excel_handler,
            )
            return {
                "type": "excel_visualize",
                "payload": result,
                "requires_contact": False,
            }

        # 4️⃣ CHATBOT
        requires_contact = False
        answer = None

        if CHATBOT_AVAILABLE and hasattr(app, "chatbot"):
            response = await run_in_threadpool(
                app.chatbot.invoke,
                {"message": question},
                config={"configurable": {"session_id": "local_session"}},
            )

            if isinstance(response, dict) and "output" in response:
                answer = response["output"]
            else:
                answer = str(response)

            if answer.strip() == CONTACT_TRIGGER_RESPONSE.strip():
                requires_contact = True
        else:
            answer = "[LOCAL] Chatbot chưa sẵn sàng"

        # Save phone sớm nếu có
        if data.phone and SHEET_AVAILABLE:
            await run_in_threadpool(
                app.save_contact_info,
                question,
                data.phone,
                data.name or "",
            )

        return {
            "answer": answer,
            "requires_contact": requires_contact,
        }

    except Exception as e:
        raise HTTPException(500, f"Lỗi xử lý chatbot: {e}")

# ===============================
# SUBMIT CONTACT
# ===============================
@app_fastapi.post("/submit-contact")
async def submit_contact(data: ContactInfo):
    if not SHEET_AVAILABLE:
        raise HTTPException(503, "Google Sheet không khả dụng")

    if not app.is_valid_phone(data.phone):
        raise HTTPException(400, "Số điện thoại không hợp lệ")

    await run_in_threadpool(
        app.save_contact_info,
        data.original_question,
        data.phone,
        data.name or "",
    )

    return {
        "success": True,
        "message": "Cảm ơn anh/chị! IIP sẽ liên hệ sớm.",
    }

# ===============================
# STATUS
# ===============================
@app_fastapi.get("/status")
async def status():
    if not CHATBOT_AVAILABLE:
        return {"chatbot": "Not available"}

    stats = app.get_vectordb_stats()
    return {
        "chatbot": "Available",
        "vectordb": stats,
        "google_sheet": SHEET_AVAILABLE,
    }

# ===============================
# RUN LOCAL
# ===============================
if __name__ == "__main__":
    uvicorn.run(
        "local_test_api:app_fastapi",
        host="127.0.0.1",
        port=10000,
        reload=True,
        log_level="info",
    )
