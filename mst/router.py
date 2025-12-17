def is_mst_query(message: str) -> bool:
    msg = message.lower()
    keywords = [
        "mã số thuế",
        "mst",
        "tra cứu mst",
        "mã số doanh nghiệp",
        "tax code"
    ]
    return any(k in msg for k in keywords)
