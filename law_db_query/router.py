from law_db_query.handler import handle_law_article_query
from data_processing.pipeline import process_pdf_question

def route_message(
    message: str,
    llm,
    lang_llm,
    retriever,
    excel_handler
):
    # 1. Check DB-law intent
    law_response = handle_law_article_query(message)
    if law_response:
        return law_response

    # 2. Fallback sang RAG / LLM
    return process_pdf_question(
        message,
        llm=llm,
        lang_llm=lang_llm,
        retriever=retriever,
        excel_handler=excel_handler
    )
