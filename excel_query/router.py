def is_kcn_price_compare_query(message: str) -> bool:
    keywords = [
        "so sánh giá",
        "giá thuê đất",
        "giá khu công nghiệp",
        "biểu đồ giá",
        "so sánh khu công nghiệp"
    ]

    msg = message.lower()
    return any(k in msg for k in keywords)
