# ===============================
# main.py – FastAPI entrypoint (Production ready)
# ===============================

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
import os
import uvicorn

from starlette.concurrency import run_in_threadpool

from mst.router import is_mst_query
from mst.handler import handle_mst_query

# ===============================
# Import chatbot core (app.py)
# ===============================
try:
    import app
    CHATBOT_AVAILABLE = True
    print("✅ app.py imported successfully")
except Exception as e:
    app = None
    CHATBOT_AVAILABLE = False
    print(f"❌ Failed to import app.py: {e}")

# ===============================
# FastAPI init
# ===============================
app_fastapi = FastAPI(
    title="Chatbot Pháp lý API",
    description="API Chatbot pháp lý – Production",
    version="1.0.0"
)

# ===============================
# CORS
# ===============================
app_fastapi.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ===============================
# Request models
# ===============================
class Question(BaseModel):
    question: str

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
                f"Ready ({stats['total_documents']} docs)"
                if stats.get("exists")
                else "Not ready"
            )
        except Exception as e:
            vectordb_status = f"Error: {e}"

    return {
        "status": "ok",
        "chatbot": "available" if CHATBOT_AVAILABLE else "not available",
        "vectordb": vectordb_status,
    }

# ===============================
# Chat endpoint
# ===============================
@app_fastapi.post("/chat")
async def chat(data: Question):
    if not CHATBOT_AVAILABLE:
        raise HTTPException(status_code=503, detail="Chatbot backend not available")

    question = data.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="Question is empty")

    try:
        # 1️⃣ MST – ưu tiên cao nhất
        if is_mst_query(question):
            answer = await run_in_threadpool(
                handle_mst_query,
                message=question,
                llm=app.llm,
                embedding=app.emb
            )
            return {"answer": answer}

        # 2️⃣ Chatbot chính (SYNC → threadpool)
        response = await run_in_threadpool(
            app.chatbot.invoke,
            {"message": question},
            config={"configurable": {"session_id": "api_session"}}
        )

        if isinstance(response, str):
            return {"answer": response}

        return {"answer": str(response)}

    except Exception as e:
        print(f"❌ Chat error: {e}")
        raise HTTPException(status_code=500, detail="Internal chatbot error")

# ===============================
# Status endpoint
# ===============================
@app_fastapi.get("/status")
async def status():
    if not CHATBOT_AVAILABLE:
        return {"chatbot": "not available"}

    try:
        stats = app.get_vectordb_stats()
        return {
            "chatbot": "available",
            "vectordb": stats
        }
    except Exception as e:
        return {
            "chatbot": "error",
            "error": str(e)
        }

# ===============================
# Uvicorn entry
# ===============================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    uvicorn.run(
        "main:app_fastapi",
        host="0.0.0.0",
        port=port,
        log_level="info"
    )
