# File: excel_visualize/data_adapter.py
import pandas as pd
from typing import Optional

# ==================================================
# 1. Các hàm Parse (Chuyển text sang số)
# ==================================================
def _parse_price_to_float(value) -> Optional[float]:
    """
    Chuyển đổi giá thuê đất sang số float.
    VD: "120 USD/m2/năm" -> 120.0
        "80 - 100 USD" -> 90.0
    """
    if pd.isna(value):
        return None

    s = str(value).lower().strip()

    # Loại bỏ các đơn vị thường gặp
    stop_words = ["usd/m²/năm", "usd/m2/năm", "usd", "/m2", "/năm", "m2"]
    for word in stop_words:
        s = s.replace(word, "")
    s = s.strip()

    # Xử lý trường hợp khoảng giá (VD: "80-100") -> Lấy trung bình
    if "-" in s:
        try:
            parts = s.split("-")
            return (float(parts[0]) + float(parts[1])) / 2
        except:
            return None

    # Xử lý số thông thường
    try:
        return float(s)
    except:
        return None

def _parse_area_to_float(value) -> Optional[float]:
    """
    Chuyển đổi diện tích sang số float.
    VD: "500 ha" -> 500.0
    """
    if pd.isna(value):
        return None

    s = str(value).lower().strip()
    
    # Loại bỏ đơn vị, thay dấu phẩy thành chấm
    s = s.replace("ha", "").replace("hecta", "").replace(",", ".").strip()
    
    try:
        return float(s)
    except:
        return None

# ==================================================
# 2. Hàm Main: Làm sạch DataFrame
# ==================================================
def clean_numeric_data(df: pd.DataFrame, is_price_metric: bool = True) -> pd.DataFrame:
    """
    Nhận vào DataFrame đã lọc, thực hiện tạo cột số liệu chuẩn để vẽ.
    - is_price_metric=True: Xử lý cột 'Giá thuê đất'
    - is_price_metric=False: Xử lý cột 'Tổng diện tích'
    """
    df_out = df.copy()
    
    if is_price_metric:
        # Tạo cột 'Giá số'
        if "Giá thuê đất" not in df_out.columns:
            return pd.DataFrame() # Trả về rỗng nếu không có cột
        
        df_out["Giá số"] = df_out["Giá thuê đất"].apply(_parse_price_to_float)
        # Chỉ giữ lại dòng có giá trị số hợp lệ
        df_out = df_out.dropna(subset=["Giá số"])
        # Loại bỏ giá trị 0 hoặc âm nếu có
        df_out = df_out[df_out["Giá số"] > 0]
        
    else:
        # Tạo cột 'Diện tích số'
        if "Tổng diện tích" not in df_out.columns:
            return pd.DataFrame()
            
        df_out["Diện tích số"] = df_out["Tổng diện tích"].apply(_parse_area_to_float)
        df_out = df_out.dropna(subset=["Diện tích số"])
        df_out = df_out[df_out["Diện tích số"] > 0]

    return df_out