import re

def is_law_article_query(message: str) -> bool:
    """
    Trả True nếu câu hỏi dạng:
    - Điều 30 luật lao động
    - điều 31 luật dân sự
    """
    pattern = r"điều\s+\d+.*luật\s+.+"
    return re.search(pattern, message.lower()) is not None


def is_law_count_query(message: str) -> bool:
    """
    Nhận diện câu hỏi về số lượng văn bản luật
    """
    message = message.lower()

    keywords = [
        "bao nhiêu luật",
        "số lượng luật",
        "bao nhiêu văn bản luật",
        "số lượng văn bản luật",
        "bao nhiêu văn bản pháp luật",
        "trong hệ thống có bao nhiêu luật",
        "trong database có bao nhiêu luật"
    ]

    return any(k in message for k in keywords)
