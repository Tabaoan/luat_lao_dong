def is_excel_visualize_price_intent(message: str) -> bool:
    keywords = [
        "biểu đồ",
        "so sánh giá",
        "giá thuê đất",
        "visualize",
        "trực quan hóa"
    ]
    msg = message.lower()
    return any(k in msg for k in keywords)

def detect_industrial_type(message: str) -> str | None:
    msg = message.lower()

    if "khu công nghiệp" in msg or "kcn" in msg:
        return "Khu công nghiệp"

    if "cụm công nghiệp" in msg or "ccn" in msg:
        return "Cụm công nghiệp"

    return None