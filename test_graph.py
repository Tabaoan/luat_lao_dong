# ===================== IMPORTS =====================
import os
import sys
import json
import base64
from typing import Dict
from pathlib import Path
from dotenv import load_dotenv
load_dotenv(override=True)

# LangChain
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langchain_core.runnables import RunnableLambda
from langchain_core.runnables.history import RunnableWithMessageHistory
from langchain_community.chat_message_histories import ChatMessageHistory

# Pinecone
from pinecone import Pinecone as PineconeClient
from langchain_pinecone import Pinecone

# Internal modules
from excel_query.excel_query import ExcelQueryHandler
from data_processing.pipeline import process_pdf_question
from law_db_query.handler import handle_law_article_query
from law_db_query.router import route_message
from mst.router import is_mst_query
from mst.handler import handle_mst_query

# ===================== EXCEL VISUALIZE =====================
from excel_visualize import (
    is_excel_visualize_price_intent,
    handle_excel_price_visualize
)

# ===================== law count response =====================
from law_db_query.handler import handle_law_count_query

# ===================== COMPARE 2018 =====================
from msn_2018.retriever import load_vsic_2018_retriever

# ===================== ENV =====================
OPENAI__API_KEY = os.getenv("OPENAI__API_KEY")
OPENAI__EMBEDDING_MODEL = os.getenv("OPENAI__EMBEDDING_MODEL")
OPENAI__MODEL_NAME = os.getenv("OPENAI__MODEL_NAME")
OPENAI__TEMPERATURE = os.getenv("OPENAI__TEMPERATURE")
LANG_MODEL_API_KEY = os.getenv("LANG_MODEL_API_KEY")
PINECONE_API_KEY = os.getenv("PINECONE_API_KEY")
PINECONE_INDEX_NAME = os.getenv("PINECONE_INDEX_NAME")
EXCEL_FILE_PATH = os.getenv("EXCEL_FILE_PATH")
EMBEDDING_DIM = 3072

# ===================== INIT LLM =====================
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

# ===================== INIT EMBEDDING =====================
emb = OpenAIEmbeddings(
    api_key=OPENAI__API_KEY,
    model=OPENAI__EMBEDDING_MODEL
)

# ===================== INIT PINECONE =====================
pc = PineconeClient(api_key=PINECONE_API_KEY)
vectordb = None
retriever = None
retriever_vsic_2018 = None


def load_vectordb():
    global vectordb, retriever, retriever_vsic_2018

    index = pc.Index(PINECONE_INDEX_NAME)
    vectordb = Pinecone(index=index, embedding=emb, text_key="text")
    retriever = vectordb.as_retriever(search_kwargs={"k": 4})

    try:
        retriever_vsic_2018 = load_vsic_2018_retriever(emb)
    except Exception:
        retriever_vsic_2018 = None


# ===================== INIT EXCEL =====================
excel_handler = None
if EXCEL_FILE_PATH and Path(EXCEL_FILE_PATH).exists():
    excel_handler = ExcelQueryHandler(EXCEL_FILE_PATH)

# ===================== PIPELINE =====================
def pdf_dispatch(i: Dict):
    if retriever is None:
        load_vectordb()

    result = route_message(
        i,
        llm=llm,
        lang_llm=lang_llm,
        retriever=retriever,
        retriever_vsic_2018=retriever_vsic_2018,
        excel_handler=excel_handler
    )

    if isinstance(result, str) and result.strip():
        return result

    return process_pdf_question(
        i,
        llm=llm,
        lang_llm=lang_llm,
        retriever=retriever,
        retriever_vsic_2018=retriever_vsic_2018,
        excel_handler=excel_handler
    )


pdf_chain = RunnableLambda(pdf_dispatch)
store: Dict[str, ChatMessageHistory] = {}


def get_history(session_id: str):
    if session_id not in store:
        store[session_id] = ChatMessageHistory()
    return store[session_id]


chatbot = RunnableWithMessageHistory(
    pdf_chain,
    get_history,
    input_messages_key="message",
    history_messages_key="history"
)

# ===================== CLI MAIN =====================
if __name__ == "__main__":
    session = "excel_visualize_dump"

    print("\n=== CHATBOT (EXCEL VISUALIZE DUMP MODE) ===\n")

    while True:
        try:
            message = input("Bạn: ").strip()
            if not message:
                continue
            if message.lower() in {"exit", "quit"}:
                break

            # ===== MST =====
            if is_mst_query(message):
                print(handle_mst_query(message, llm=llm, embedding=emb))
                continue

            # ===== EXCEL VISUALIZE =====
            if is_excel_visualize_price_intent(message):
                result = handle_excel_price_visualize(
                    message=message,
                    excel_handler=excel_handler
                )

                # ===== LƯU RESPONSE =====
                out_dir = Path("temp_data")
                out_dir.mkdir(exist_ok=True)

                json_path = out_dir / "excel_visualize_response.json"
                with open(json_path, "w", encoding="utf-8") as f:
                    json.dump(result, f, ensure_ascii=False, indent=2)

                print(f"\n✔ Đã lưu JSON: {json_path}")

                # ===== GIẢI MÃ BASE64 =====
                if "chart_base64" in result:
                    img_path = out_dir / "excel_visualize_chart.png"
                    with open(img_path, "wb") as f:
                        f.write(base64.b64decode(result["chart_base64"]))
                    print(f"✔ Đã lưu PNG: {img_path}")

                print("\n📄 RESPONSE PREVIEW:")
                print(json.dumps(
                    {k: v for k, v in result.items() if k != "chart_base64"},
                    ensure_ascii=False,
                    indent=2
                ))
                print("-" * 80)
                continue

            # ===== FALLBACK CHATBOT =====
            response = chatbot.invoke(
                {"message": message},
                config={"configurable": {"session_id": session}}
            )
            print(response)

        except Exception as e:
            print(f"Lỗi: {e}")
