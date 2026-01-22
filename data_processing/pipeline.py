# data_processing/pipeline.py

from typing import Dict, Any, List
from langchain_core.messages import SystemMessage, HumanMessage, BaseMessage
import json
from data_processing.cleaning import clean_question_remove_uris
from data_processing.language import detect_language_openai, convert_language
from data_processing.context_builder import build_context_from_hits
from system_prompts.pdf_reader_system import PDF_READER_SYS
from data_processing.intent import is_vsic_code_query, is_flowchart_intent, is_greeting_question


# ======================================================
# NHẬN DIỆN CHÀO HỎI / CÂU HỎI CHUNG CHUNG
# ======================================================

GREETING_VI = (
    "Xin chào Quý khách! ChatIIP là sản phẩm trong hệ sinh thái của CTCP IIP, "
    "được đào tạo chuyên sâu nhằm cung cấp thông tin chính xác và đáng tin cậy "
    "trong các lĩnh vực: pháp luật (luật, nghị định, thông tư, quyết định), "
    "ngành nghề kinh doanh, mã số thuế và thông tin doanh nghiệp, kế toán - thuế, "
    "lao động - việc làm, cũng như bất động sản công nghiệp "
    "(khu công nghiệp, cụm công nghiệp, nhà xưởng cho thuê/bán và "
    "các thủ tục pháp lý liên quan). "
    "Quý khách vui lòng nhập câu hỏi hoặc mô tả nhu cầu cụ thể để ChatIIP hỗ trợ."
)


# ======================================================
# NHẬN DIỆN LAO ĐỘNG / VIỆC LÀM / BHXH / DN
# ======================================================
def is_labor_related_question(question: str) -> bool:
    keywords = [
        "lao động", "việc làm", "người lao động", "người sử dụng lao động",
        "hợp đồng lao động", "thử việc", "thời gian thử việc",
        "tiền lương", "lương", "tiền công", "trả lương",
        "bảo hiểm xã hội", "bhxh", "bảo hiểm y tế", "bhyt",
        "bảo hiểm thất nghiệp", "bhtn",
        "doanh nghiệp", "công ty"
    ]
    q = question.lower()
    return any(k in q for k in keywords)

# NHẬN DIỆN INTENT VẼ FLOWCHART / SƠ ĐỒ LUỒNG / QUY TRÌNH


FLOWCHART_SYS = (
    "Bạn là trợ lý chuyên vẽ FLOWCHART bằng Mermaid.\n"
    "QUY TẮC BẮT BUỘC:\n"
    "- Chỉ trả về DUY NHẤT code Mermaid, không giải thích, không markdown fence.\n"
    "- Bắt đầu bằng: flowchart TD hoặc flowchart LR.\n"
    "- Node chi tiết, rõ ràng; dùng A[...], B{...}, C(...).\n"
    "- BẮT BUỘC phải có node điều kiện dạng { ... }.\n"
    "- Nếu thiếu thông tin, tự giả định hợp lý để hoàn chỉnh sơ đồ.\n"
)

FLOWCHART_EXPLAIN_SYS = (
    "Bạn là trợ lý giải thích flowchart.\n"
    "Đầu vào gồm: (1) Mermaid code, (2) mô tả yêu cầu người dùng.\n"
    "NHIỆM VỤ:\n"
    "- Giải thích từng phần mục của flowchart một cách rõ ràng, dễ hiểu.\n"
    "- Bắt buộc bám sát Mermaid code đã cho (không tự ý thêm bước không có).\n"
    "- Trình bày theo dạng gạch đầu dòng.\n"
    "- Nếu có nhánh điều kiện (node dạng {..}), giải thích rõ từng nhánh.\n"
    "- Dùng đúng ngôn ngữ của người dùng.\n"
)

FOLLOWUP_ANCHOR_SYS = (
    "Bạn đang trả lời trong một hội thoại nhiều lượt.\n"
    "QUY TẮC BẮT BUỘC:\n"
    "- Nếu câu hỏi hiện tại có tham chiếu như 'điều luật trên', 'nội dung trên', 'vừa nêu', 'ở trên'...\n"
    "  thì phải hiểu là đang hỏi tiếp nội dung trong lịch sử hội thoại.\n"
    "- TUYỆT ĐỐI không được tự chuyển sang văn bản/tài liệu khác.\n"
    "- Nếu lịch sử hội thoại không đủ để xác định điều/văn bản, hãy hỏi lại 1 câu làm rõ.\n"
)


# Phân loại lịch sử hội thoại: 
def llm_is_followup(
    clean_question: str,
    history: List[BaseMessage],
    lang_llm
) -> bool:
    """
    Trả về:
    - True  → câu hỏi hiện tại là follow-up của hội thoại trước
    - False → câu hỏi mới / đổi chủ đề
    """

    if not history:
        return False

    # chỉ lấy vài lượt gần nhất để tiết kiệm token
    recent = history[-6:]

    history_text = "\n".join(
        f"{m.type.upper()}: {m.content}"
        for m in recent
        if getattr(m, "content", None)
    )

    prompt = f"""
Bạn là bộ phân loại ngữ cảnh hội thoại.

NHIỆM VỤ:
- Xác định câu hỏi hiện tại có đang hỏi tiếp nội dung trong hội thoại trước hay không.

HỘI THOẠI TRƯỚC:
{history_text}

CÂU HỎI HIỆN TẠI:
{clean_question}

QUY TẮC:
- Trả về FOLLOW_UP nếu câu hỏi đang tiếp tục, làm rõ, mở rộng nội dung trước đó.
- Trả về NEW_TOPIC nếu câu hỏi chuyển sang chủ đề hoặc văn bản pháp luật khác.

CHỈ TRẢ VỀ MỘT TỪ DUY NHẤT:
FOLLOW_UP hoặc NEW_TOPIC
""".strip()

    try:
        result = lang_llm.invoke(
            [HumanMessage(content=prompt)]
        ).content.strip().upper()
        return result == "FOLLOW_UP"
    except Exception:
        return True
# ======================================================
# PIPELINE TRUNG TÂM
# ======================================================
def process_pdf_question(
    i: Dict[str, Any],
    *,
    llm,
    lang_llm,
    retriever,
    retriever_vsic_2018=None,
    excel_handler=None
) -> str:

    # ============================
    # 0️⃣ INPUT
    # ============================
    message = i["message"]
    history: List[BaseMessage] = i.get("history", [])
    law_count = i.get("law_count")

    clean_question = clean_question_remove_uris(message)
    user_lang = detect_language_openai(clean_question, lang_llm)

    # ============================
    # 0️⃣.1 CHÀO HỎI
    # ============================
    if is_greeting_question(clean_question):
        if user_lang == "vi":
            return GREETING_VI
        return convert_language(GREETING_VI, user_lang, lang_llm)

    # ============================
    # 0️⃣.2 FLOWCHART (MERMAID + GIẢI THÍCH)
    # ============================
    if is_flowchart_intent(clean_question):
        # 1) Sinh Mermaid code
        system_prompt = FLOWCHART_SYS + f"\nNgười dùng đang dùng ngôn ngữ: '{user_lang}'."
        messages = [SystemMessage(content=system_prompt)]
        if history:
            messages.extend(history[-10:])

        messages.append(HumanMessage(
            content=f"""
Yêu cầu: {clean_question}

Hãy xuất Mermaid flowchart theo đúng ngôn ngữ: {user_lang}.
"""
        ))

        mermaid_code = llm.invoke(messages).content.strip()

        # Fallback nếu model trả sai format
        if not mermaid_code.lower().startswith("flowchart"):
            mermaid_code = (
                "flowchart TD\n"
                "A[Không tạo được flowchart] --> B[Hãy mô tả rõ hơn yêu cầu]"
            )

        # 2) Giải thích từng phần mục của flowchart (bám sát Mermaid code)
        explain_messages = [
            SystemMessage(
                content=FLOWCHART_EXPLAIN_SYS + f"\nNgười dùng đang dùng ngôn ngữ: '{user_lang}'."
            )
        ]

        explain_messages.append(HumanMessage(
            content=f"""
MÔ TẢ NGƯỜI DÙNG:
{clean_question}

MERMAID CODE:
{mermaid_code}

Hãy giải thích "từng phần mục" của flowchart:
- Giải thích từng node theo thứ tự luồng đi.
- Nếu có nhánh điều kiện, giải thích từng nhánh.
- Kết thúc bằng 1-2 câu tóm tắt flow tổng thể.
"""
        ))

        explanation = llm.invoke(explain_messages).content.strip()

        # 3) Trả về JSON string
        return json.dumps(
            {
                "type": "flowchart",
                "format": "mermaid",
                "code": mermaid_code,
                "explanation": explanation
            },
            ensure_ascii=False
        )
    # ============================
    # 1️⃣ ƯU TIÊN EXCEL
    # ============================
    if excel_handler:
        handled, excel_response = excel_handler.process_query(clean_question)
        if handled and excel_response:
            return (
                excel_response
                if user_lang == "vi"
                else convert_language(excel_response, user_lang, lang_llm)
            )

    # ============================
    # 2️⃣ ĐẾM SỐ LƯỢNG LUẬT
    # ============================
    if law_count is not None:
        system_prompt = (
            PDF_READER_SYS
            + f"\n\nNgười dùng đang dùng ngôn ngữ: '{user_lang}'."
            + f"\n\nDỮ LIỆU HỆ THỐNG:\n- TOTAL_LAWS = {law_count}"
        )

        messages = [SystemMessage(content=system_prompt)]
        if history:
            messages.extend(history[-10:])

        messages.append(HumanMessage(
            content=f"""
Câu hỏi: {clean_question}

Hãy trả lời đúng quy định đối với CÂU HỎI VỀ SỐ LƯỢNG VĂN BẢN PHÁP LUẬT.
Trả lời bằng ngôn ngữ: {user_lang}.
"""
        ))

        response = llm.invoke(messages).content
        return response if user_lang == "vi" else convert_language(response, user_lang, lang_llm)

    # ============================
    # 3️⃣ NHẬN DIỆN VSIC
    # ============================
    is_vsic_query = is_vsic_code_query(clean_question)

    # ============================
# 4️⃣ RAG THƯỜNG (LLM quyết định dùng history hay không)
# ============================
    if not is_vsic_query:

        # ---- BƯỚC 1: DÙNG LLM PHÂN LOẠI NGỮ CẢNH ----
        use_history = llm_is_followup(clean_question, history, lang_llm)

        # ==================================================
        # CASE A: FOLLOW-UP → TRẢ LỜI THEO HISTORY
        # ==================================================
        if use_history:
            system_prompt = PDF_READER_SYS + f"\n\nNgười dùng đang dùng ngôn ngữ: '{user_lang}'."
            messages = [SystemMessage(content=system_prompt)]

            # nạp history
            messages.extend(history[-10:])

            messages.append(
                HumanMessage(
                    content=f"""
    Câu hỏi hiện tại (nối tiếp hội thoại trước đó):
    {clean_question}

    YÊU CẦU BẮT BUỘC:
    - Đây là câu hỏi FOLLOW-UP.
    - PHẢI trả lời dựa trên văn bản/vấn đề pháp lý đã được xác định trong lịch sử hội thoại.
    - TUYỆT ĐỐI không chuyển sang văn bản pháp luật khác nếu người dùng không nêu rõ.
    - Nếu lịch sử chưa đủ để xác định điều/khoản cụ thể, hãy hỏi lại 1 câu làm rõ.

    Trả lời bằng ngôn ngữ: {user_lang}.
    """
                )
            )

            response = llm.invoke(messages).content
            return response if user_lang == "vi" else convert_language(response, user_lang, lang_llm)

        # ==================================================
        # CASE B: NEW_TOPIC → COI NHƯ CÂU HỎI MỚI, CHẠY RAG
        # ==================================================
        hits = retriever.invoke(clean_question) if retriever else []
        has_context = bool(hits)
        context = build_context_from_hits(hits) if has_context else ""

        system_prompt = PDF_READER_SYS + f"\n\nNgười dùng đang dùng ngôn ngữ: '{user_lang}'."
        messages = [SystemMessage(content=system_prompt)]

        if has_context:
            human = f"""
    Câu hỏi: {clean_question}

    Nội dung liên quan:
    {context}

    Hãy trả lời đầy đủ, chính xác theo tài liệu.
    Trả lời bằng ngôn ngữ: {user_lang}.
    """
            messages.append(HumanMessage(content=human))
            response = llm.invoke(messages).content
            return response if user_lang == "vi" else convert_language(response, user_lang, lang_llm)

        # ==================================================
        # CASE C: KHÔNG CÓ CONTEXT → OUT OF SCOPE
        # ==================================================
        out_of_scope_vi = (
            "Tôi là chatbot chuyên tư vấn và tra cứu thông tin trong các lĩnh vực: "
            "pháp luật (luật, nghị định, thông tư, quyết định), "
            "ngành nghề kinh doanh, mã số thuế và thông tin doanh nghiệp, "
            "kế toán – thuế, lao động – việc làm, "
            "cũng như bất động sản công nghiệp "
            "(khu công nghiệp, cụm công nghiệp, nhà xưởng cho thuê/bán "
            "và các thủ tục pháp lý liên quan). "
            "Tôi chỉ hỗ trợ các câu hỏi thuộc những lĩnh vực nêu trên; "
            "bạn vui lòng đặt câu hỏi phù hợp để tôi có thể hỗ trợ chính xác."
        )

        return out_of_scope_vi if user_lang == "vi" else convert_language(out_of_scope_vi, user_lang, lang_llm)


    # ============================
    # 5️⃣ VSIC 2025 ↔ 2018
    # ============================
    hits_2025 = retriever.invoke(clean_question) if retriever else []
    context_2025 = build_context_from_hits(hits_2025) if hits_2025 else (
        "Mã ngành này không được quy định theo Quyết định số 36/2025/QĐ-TTg."
    )

    context_2018 = ""
    if retriever_vsic_2018:
        hits_2018 = retriever_vsic_2018.invoke(clean_question)
        context_2018 = build_context_from_hits(hits_2018) if hits_2018 else (
            "Mã ngành này không được quy định theo Quyết định số 27/2018/QĐ-TTg."
        )

    system_prompt = PDF_READER_SYS + f"\n\nNgười dùng đang dùng ngôn ngữ: '{user_lang}'."
    messages = [SystemMessage(content=system_prompt)]
    if history:
        messages.extend(history[-10:])

    messages.append(HumanMessage(
        content=f"""
Câu hỏi: {clean_question}

Theo Quyết định số 36/2025/QĐ-TTg:
{context_2025}

Theo Quyết định số 27/2018/QĐ-TTg:
{context_2018}

Hãy trả lời có cấu trúc so sánh rõ ràng.
Trả lời bằng ngôn ngữ: {user_lang}.
"""
    ))

    response = llm.invoke(messages).content
    return response if user_lang == "vi" else convert_language(response, user_lang, lang_llm)
