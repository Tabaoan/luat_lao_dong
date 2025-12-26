# data_processing/pipeline.py

from typing import Dict, Any, List
from langchain_core.messages import SystemMessage, HumanMessage, BaseMessage

from data_processing.cleaning import clean_question_remove_uris
from data_processing.language import detect_language_openai, convert_language
from data_processing.context_builder import build_context_from_hits
from system_prompts.pdf_reader_system import PDF_READER_SYS
from data_processing.intent import is_vsic_code_query

def is_labor_related_question(question: str) -> bool:
    keywords = [
        # Lao động – việc làm
        "lao động", "việc làm", "người lao động", "người sử dụng lao động",
        "hợp đồng lao động", "thử việc", "thời gian thử việc",

        # Lương – thu nhập
        "tiền lương", "lương", "tiền công", "trả lương",

        # Bảo hiểm
        "bảo hiểm xã hội", "bhxh", "bảo hiểm y tế", "bhyt",
        "bảo hiểm thất nghiệp", "bhtn",

        # Doanh nghiệp
        "doanh nghiệp", "công ty", "người sử dụng lao động"
    ]

    q = question.lower()
    return any(k in q for k in keywords)

    
def process_pdf_question(
    i: Dict[str, Any],
    *,
    llm,
    lang_llm,
    retriever,
    retriever_vsic_2018=None,
    excel_handler=None
) -> str:
    """
    PIPELINE TRUNG TÂM:
    - Điều phối mọi câu hỏi
    - Backend cung cấp dữ liệu (SQL / Excel / Vector)
    - LLM chỉ DIỄN ĐẠT theo system prompt
    """

    # ============================
    # 0️⃣ INPUT & CONTEXT
    # ============================
    message = i["message"]
    history: List[BaseMessage] = i.get("history", [])

    #  DỮ LIỆU HỆ THỐNG TRUYỀN TỪ BACKEND (NẾU CÓ)
    law_count = i.get("law_count")  # int | None

    clean_question = clean_question_remove_uris(message)
    user_lang = detect_language_openai(message, lang_llm)

    # ============================
    # 1️⃣ ƯU TIÊN EXCEL
    # ============================
    if excel_handler:
        handled, excel_response = excel_handler.process_query(clean_question)
        if handled and excel_response:
            return (
                convert_language(excel_response, user_lang, lang_llm)
                if user_lang != "vi"
                else excel_response
            )

    # ============================
    # 2️⃣ NHÁNH RIÊNG: ĐẾM SỐ LƯỢNG LUẬT (SQL → LLM)
    # ============================
    if law_count is not None:
        system_prompt = (
            PDF_READER_SYS
            + f"\n\n Người dùng đang dùng ngôn ngữ: '{user_lang}'."
            + "\n\n DỮ LIỆU HỆ THỐNG (BẮT BUỘC SỬ DỤNG):"
              f"\n- TOTAL_LAWS = {law_count}"
        )

        messages = [SystemMessage(content=system_prompt)]
        if history:
            messages.extend(history[-10:])

        messages.append(
            HumanMessage(
                content=f"""
Câu hỏi: {clean_question}

Dữ liệu thống kê về số lượng văn bản luật đã được hệ thống cung cấp.
Hãy trả lời ĐÚNG theo quy định đối với CÂU HỎI VỀ SỐ LƯỢNG VĂN BẢN PHÁP LUẬT.
Hãy trả lời bằng ngôn ngữ: {user_lang}.
"""
            )
        )

        response = llm.invoke(messages).content
        detected = detect_language_openai(response, lang_llm)
        if detected != user_lang:
            response = convert_language(response, user_lang, lang_llm)

        return response

    # ============================
    # 3️⃣ XÁC ĐỊNH CÓ PHẢI MÃ NGÀNH KHÔNG
    # ============================
    is_vsic_query = is_vsic_code_query(clean_question)

    # ============================
    # 4️⃣ RAG BÌNH THƯỜNG (KHÔNG PHẢI MÃ NGÀNH)
    # ============================
    if not is_vsic_query:
        if retriever is None:
            msg = "VectorDB chưa sẵn sàng."
            return convert_language(msg, user_lang, lang_llm)

        hits = retriever.invoke(clean_question)
        if not hits:
            msg = "Không tìm thấy thông tin liên quan."
            return convert_language(msg, user_lang, lang_llm)

        context = build_context_from_hits(hits)

        system_prompt = (
            PDF_READER_SYS
            + f"\n\n Người dùng đang dùng ngôn ngữ: '{user_lang}'."
        )

        messages = [SystemMessage(content=system_prompt)]
        if history:
            messages.extend(history[-10:])

#         messages.append(
#             HumanMessage(
#                 content=f"""
# Câu hỏi: {clean_question}

# Nội dung liên quan:
# {context}

# Hãy trả lời bằng ngôn ngữ: {user_lang}.
# """
#             )
#         )
        labor_related = is_labor_related_question(clean_question)

        if labor_related:
            human_instruction = f"""
        Câu hỏi: {clean_question}

        Nội dung liên quan:
        {context}

        YÊU CẦU BẮT BUỘC KHI TRẢ LỜI:
        - Trả lời đầy đủ, đúng nội dung pháp luật theo tài liệu đã cung cấp.
        - Sau khi trả lời nội dung chính, PHẢI bổ sung các mục sau,
        trình bày thành các đoạn RIÊNG BIỆT:

        1) Rủi ro pháp lý có thể phát sinh
        2) Người hỏi cần thực hiện những bước tiếp theo nào
        3) Giấy tờ, hồ sơ, chứng cứ cần chuẩn bị (nếu có)
        4) Hậu quả pháp lý nếu thực hiện sai hoặc không tuân thủ quy định

        - Nội dung bổ sung phải PHÙ HỢP TRỰC TIẾP với câu hỏi,
        không nêu chung chung, không suy đoán ngoài tài liệu.

        Hãy trả lời bằng ngôn ngữ: {user_lang}.
        """
        else:
            human_instruction = f"""
        Câu hỏi: {clean_question}

        Nội dung liên quan:
        {context}

        Hãy trả lời đầy đủ, chính xác theo nội dung tài liệu đã cung cấp.
        Hãy trả lời bằng ngôn ngữ: {user_lang}.
        """

        messages.append(HumanMessage(content=human_instruction))

        response = llm.invoke(messages).content
        detected = detect_language_openai(response, lang_llm)
        if detected != user_lang:
            response = convert_language(response, user_lang, lang_llm)

        return response

    # ============================
    # 5️⃣ NHÁNH RIÊNG: MÃ NGÀNH (VSIC 2025 ↔ 2018)
    # ============================
    if retriever is None:
        msg = "VectorDB chưa sẵn sàng."
        return convert_language(msg, user_lang, lang_llm)

    # --- VSIC 2025 ---
    hits_2025 = retriever.invoke(clean_question)
    context_2025 = build_context_from_hits(hits_2025) if hits_2025 else (
        " Mã ngành này không được quy định trong Hệ thống ngành kinh tế Việt Nam "
        "ban hành theo Quyết định số 36/2025/QĐ-TTg."
    )

    # --- VSIC 2018 (đối chứng) ---
    context_2018 = ""
    if retriever_vsic_2018:
        hits_2018 = retriever_vsic_2018.invoke(clean_question)
        context_2018 = build_context_from_hits(hits_2018) if hits_2018 else (
            " Mã ngành này không được quy định trong Hệ thống ngành kinh tế Việt Nam "
            "ban hành theo Quyết định số 27/2018/QĐ-TTg."
        )

    system_prompt = (
        PDF_READER_SYS
        + f"\n\n Người dùng đang dùng ngôn ngữ: '{user_lang}'."
        + "\n\n QUY ĐỊNH BẮT BUỘC:"
          "\n- Đây là câu hỏi về MÃ NGÀNH KINH TẾ."
          "\n- PHẢI trình bày RIÊNG từng hệ thống:"
          "\n  (1) VSIC 2025 – hiện hành"
          "\n  (2) VSIC 2018 – đối chứng"
          "\n- PHẢI nêu rõ: giữ nguyên / thay đổi / không tồn tại."
    )

    messages = [SystemMessage(content=system_prompt)]
    if history:
        messages.extend(history[-10:])

    messages.append(
        HumanMessage(
            content=f"""
Câu hỏi: {clean_question}

Theo Quyết định số 36/2025/QĐ-TTg:
{context_2025}

Theo Quyết định số 27/2018/QĐ-TTg (đối chứng):
{context_2018}

Hãy trả lời đầy đủ, có cấu trúc so sánh rõ ràng.
Hãy trả lời bằng ngôn ngữ: {user_lang}.
"""
        )
    )

    response = llm.invoke(messages).content
    detected = detect_language_openai(response, lang_llm)
    if detected != user_lang:
        response = convert_language(response, user_lang, lang_llm)

    return response
