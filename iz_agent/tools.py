from langchain_core.tools import tool
from .backend import IIPMapBackend
import json
import uuid
import os
import math
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# --- CẤU HÌNH ---
EXCEL_PATH = os.getenv("EXCEL_FILE_PATH", "./data/IIPMap_FULL_63_COMPLETE.xlsx")
GEOJSON_PATH = os.getenv("GEOJSON_FILE_PATH", "./map_ui/industrial_zones.geojson")
backend = IIPMapBackend(EXCEL_PATH, GEOJSON_PATH)

# ✅ KHO CHỨA ẢNH TẠM THỜI (Global Variable)
# Đây là nơi lưu ảnh thật để AI không phải "vác" theo
CHART_STORE = {}

def _clean_value_for_json(value):
    """Clean a single value for JSON serialization"""
    import math
    import pandas as pd
    
    # Xử lý NaN và Infinity
    if isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            return None
    
    # Xử lý pandas NaN
    if pd.isna(value):
        return None
        
    # Xử lý string "nan", "inf"
    if isinstance(value, str):
        if value.lower() in ['nan', 'inf', '-inf', 'infinity', '-infinity']:
            return None
    
    return value

def _clean_dict_completely(data_dict):
    """Làm sạch hoàn toàn dictionary cho JSON"""
    import math
    import pandas as pd
    
    if not isinstance(data_dict, dict):
        return _clean_value_for_json(data_dict)
    
    cleaned = {}
    for key, value in data_dict.items():
        # Bỏ qua các cột _num
        if key.endswith('_num'):
            continue
            
        if isinstance(value, dict):
            cleaned[key] = _clean_dict_completely(value)
        elif isinstance(value, list):
            cleaned[key] = [_clean_dict_completely(item) for item in value]
        else:
            cleaned[key] = _clean_value_for_json(value)
    
    return cleaned

@tool
def search_single_zone_tool(zone_name: str):
    """
    Tìm thông tin chi tiết của 1 KCN/CCN cụ thể.
    Nếu có nhiều kết quả tương tự, sẽ đưa ra danh sách lựa chọn.
    """
    result = backend.search_single_zone(zone_name)
    
    # Làm sạch toàn bộ kết quả trước khi trả về
    cleaned_result = _clean_dict_completely(result)
    
    if cleaned_result["type"] == "single_result":
        # Tìm thấy 1 kết quả duy nhất
        data = cleaned_result["data"]
        
        # Tìm tên để lấy coordinates
        zone_display_name = zone_name
        for col in data.keys():
            if any(keyword in col.lower() for keyword in ['tên', 'name']) and not col.endswith('_num'):
                zone_display_name = str(data.get(col, zone_name))
                break
        
        # Tạo thông tin chi tiết
        info = {
            "type": "single_zone_info",
            "zone_name": zone_name,
            "data": data,
            "coordinates": backend.match_coordinates(zone_display_name),
            "message": f"Thông tin chi tiết về {zone_name}:"
        }
        
        return _clean_dict_completely(info)
    
    elif cleaned_result["type"] == "multiple_choices":
        # Nhiều lựa chọn - đã được làm sạch rồi
        return cleaned_result
    
    else:
        # Không tìm thấy hoặc lỗi - đã được làm sạch rồi
        return cleaned_result

@tool
def search_flexible_tool(filter_json: str, view_option: str = "list"):
    """
    Tìm kiếm và vẽ biểu đồ. 
    Lưu ý: Ảnh Base64 sẽ được lưu vào CHART_STORE, chỉ trả về chart_id cho AI.
    """
    try:
        filters = json.loads(filter_json)
    except:
        return {"type": "error", "message": "Lỗi JSON input."}
        
    df_res = backend.query_flexible(filters)
    
    prov_str = filters.get("Tỉnh/Thành phố", "Kết quả")
    
    if df_res.empty:
        return {"type": "error", "message": "Không tìm thấy dữ liệu."}

    # 1. Lấy dữ liệu danh sách (Data List) - GIỚI HẠN ĐỂ TRÁNH RATE LIMIT
    data_list = []
    # Giới hạn số lượng để tránh vượt quá token limit của OpenAI
    max_items = min(50, len(df_res))  # Tối đa 50 items để tránh rate limit
    
    # Tìm cột tên tự động
    name_col = None
    for col in df_res.columns:
        if any(keyword in col.lower() for keyword in ['tên', 'name']) and not col.endswith('_num'):
            name_col = col
            break
    
    if not name_col:
        name_col = df_res.columns[0]  # Fallback: dùng cột đầu tiên
    
    for idx, row in df_res.head(max_items).iterrows():
        name = row.get(name_col)
        coordinates = backend.match_coordinates(str(name)) if name else None
        
        item = {
            "Tên": _clean_value_for_json(name),
            "coordinates": coordinates
        }
        
        # Thêm các cột cơ bản một cách linh hoạt
        # Tìm cột địa chỉ
        for col in row.index:
            if any(keyword in col.lower() for keyword in ['địa chỉ', 'address']) and col not in item:
                item["Địa chỉ"] = _clean_value_for_json(str(row[col]))
                break
        
        # Tìm cột giá
        for col in row.index:
            if any(keyword in col.lower() for keyword in ['giá', 'price', 'thuê']) and not col.endswith('_num') and col not in item:
                item["Giá"] = _clean_value_for_json(str(row[col]))
                break
        
        # Tìm cột diện tích
        for col in row.index:
            if any(keyword in col.lower() for keyword in ['diện tích', 'area', 'tổng']) and not col.endswith('_num') and col not in item:
                item["Diện tích"] = _clean_value_for_json(str(row[col]))
                break
        
        # Chỉ thêm một số cột quan trọng để giảm token
        important_cols = ['Tỉnh/Thành phố', 'Loại', 'Thời gian vận hành', 'Tổng diện tích', 'Giá thuê đất']
        for col in important_cols:
            if col in row.index:
                item[col] = _clean_value_for_json(str(row[col]))
        
        # Làm sạch toàn bộ item trước khi thêm vào danh sách
        data_list.append(_clean_dict_completely(item))

    # 2. XỬ LÝ BIỂU ĐỒ (HIỂN THỊ TẤT CẢ)
    chart_id = None
    chart_type = "none"
    
    if view_option != "list":
        metric = 'dual'  # Giữ dual cho tương thích ngược
        if view_option.startswith('chart_'): 
            metric = view_option.replace("chart_", "")
            chart_type = "bar"
        
        title = f"BIỂU ĐỒ {metric.upper()} - {prov_str}"
        
        # Vẽ ảnh với tất cả dữ liệu (KHÔNG GIỚI HẠN cho biểu đồ)
        base64_str = backend.generate_chart_base64(df_res, title, metric, limit=-1)  # -1 = unlimited
        
        if base64_str:
            # ✅ BƯỚC QUAN TRỌNG: 
            # - Tạo ID ngẫu nhiên
            # - Cất ảnh vào kho CHART_STORE
            chart_id = str(uuid.uuid4())
            CHART_STORE[chart_id] = base64_str

    # 3. TRẢ VỀ CHO AI (Gói tin siêu nhẹ - Không có Base64)
    total_found = len(df_res)
    displayed_count = len(data_list)
    
    result = {
        "type": "excel_visualize_with_data",
        "province": prov_str,
        "count": displayed_count,
        "total_found": total_found,  # Tổng số tìm thấy
        "data": data_list,
        "message": f"Tìm thấy {total_found} kết quả, hiển thị {displayed_count} kết quả đầu tiên.",
        
        # ✅ AI chỉ nhìn thấy ID này (nhẹ 36 bytes), không phải chuỗi ảnh (500KB)
        "chart_id": chart_id, 
        "chart_type": chart_type,
        
        # Đánh dấu null ở đây để AI không bị nhiễu
        "chart_base64": None, 
        
        "text": f"Đã tìm thấy {total_found} kết quả.{f' Hiển thị {displayed_count} kết quả đầu tiên.' if total_found > displayed_count else ''}{' Có biểu đồ đi kèm.' if chart_id else ''}"
    }
    
    # Làm sạch toàn bộ kết quả trước khi trả về
    return _clean_dict_completely(result)