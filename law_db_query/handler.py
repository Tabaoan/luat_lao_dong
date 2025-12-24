from law_db_query.intent import (
    is_law_article_query,
    is_law_count_query
)
from law_db_query.parser import parse_law_query
from law_db_query.db import (
    query_article_from_db,
    count_distinct_laws_from_db
)


# ============================
# HANDLER: TRA CỨU ĐIỀU LUẬT
# ============================
def handle_law_article_query(message: str) -> str | None:
    """
    Trả về NỘI DUNG ĐIỀU LUẬT (string)
    Pipeline KHÔNG can thiệp
    """
    if not is_law_article_query(message):
        return None

    law_names, article = parse_law_query(message)
    result = query_article_from_db(law_names, article)

    if not result:
        return "Không tìm thấy điều luật bạn yêu cầu."

    ln, ly, ch, sec, art, text = result

    return (
        f"{ln} ({ly})\n"
        f"Chương: {ch} | Mục: {sec} | Điều: {art}\n\n"
        f"{text}"
    )


# ============================
# HANDLER: ĐẾM SỐ LƯỢNG LUẬT
# ============================
def handle_law_count_query(message: str) -> dict | None:
    """
    Trả về DATA cho pipeline:
    {
        "intent": "law_count",
        "total_laws": <int>
    }
    """
    if not is_law_count_query(message):
        return None

    total = count_distinct_laws_from_db()

    return {
        "intent": "law_count",
        "total_laws": total
    }
