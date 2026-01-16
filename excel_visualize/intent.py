# File: excel_visualize/intent.py

def is_excel_visualize_intent(message: str) -> bool:
    """Kiểm tra user có muốn xem biểu đồ/dữ liệu Excel không"""
    keywords = [
        "biểu đồ", "so sánh", "visualize", "trực quan", "chart", 
        "giá đất", "diện tích", "quy mô"
    ]
    msg = message.lower()
    return any(k in msg for k in keywords)

def detect_excel_metric(message: str) -> str | None:
    """
    Xác định user muốn xem 'Giá thuê đất' hay 'Tổng diện tích'.
    Mặc định trả về None (để bên ngoài xử lý fallback).
    """
    msg = message.lower()
    
    # Nhóm từ khóa Diện tích
    area_keywords = ["diện tích", "quy mô", "rộng", "lớn", "ha", "hecta"]
    if any(k in msg for k in area_keywords):
        return "Tổng diện tích"
    
    # Nhóm từ khóa Giá
    price_keywords = ["giá", "tiền", "thuê", "chi phí", "usd"]
    if any(k in msg for k in price_keywords):
        return "Giá thuê đất"
    
    return None

def detect_industrial_type(message: str) -> str | None:
    """(Optional) Gợi ý loại hình Khu hay Cụm dựa trên từ khóa"""
    msg = message.lower()
    if "cụm" in msg or "ccn" in msg:
        return "Cụm công nghiệp"
    return "Khu công nghiệp"