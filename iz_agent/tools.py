from langchain_core.tools import tool
from .backend import IIPMapBackend
import json
import uuid

# --- CẤU HÌNH ---
EXCEL_PATH = r"C:\Users\tabao\OneDrive\Desktop\Qdrant\IIPMap_FULL_63_COMPLETE.xlsx"
GEOJSON_PATH = r"./map_ui/industrial_zones.geojson"
backend = IIPMapBackend(EXCEL_PATH, GEOJSON_PATH)

# ✅ KHO CHỨA ẢNH TẠM THỜI (Global Variable)
# Đây là nơi lưu ảnh thật để AI không phải "vác" theo
CHART_STORE = {}

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

    # 1. Lấy dữ liệu danh sách (Data List) như bình thường
    data_list = []
    for idx, row in df_res.head(20).iterrows():
        name = row.get(backend.cols['name'])
        item = {
            "Tên": name,
            "Địa chỉ": row.get(backend.cols['address']),
            "Giá": row.get(backend.cols['price']),
            "Diện tích": row.get(backend.cols['area']),
            "coordinates": backend.match_coordinates(name)
        }
        # Thêm các cột động khác...
        for col in row.index:
            if col not in item and col not in ['price_num', 'area_num', 'name_norm', 'prov_norm', 'type_norm']:
                item[col] = str(row[col])
        data_list.append(item)

    # 2. XỬ LÝ BIỂU ĐỒ (TỐI ƯU HÓA)
    chart_id = None
    chart_type = "none"
    
    if view_option != "list":
        metric = 'dual'
        if view_option.startswith('chart_'): metric = view_option.replace("chart_", "")
        title = f"BIỂU ĐỒ {metric} - {prov_str}"
        
        # Vẽ ảnh (Tạo chuỗi Base64 nặng nề)
        base64_str = backend.generate_chart_base64(df_res, title, metric)
        
        if base64_str:
            chart_type = "bar"
            # ✅ BƯỚC QUAN TRỌNG: 
            # - Tạo ID ngẫu nhiên
            # - Cất ảnh vào kho CHART_STORE
            chart_id = str(uuid.uuid4())
            CHART_STORE[chart_id] = base64_str

    # 3. TRẢ VỀ CHO AI (Gói tin siêu nhẹ - Không có Base64)
    return {
        "type": "excel_visualize_with_data",
        "province": prov_str,
        "count": len(data_list),
        "data": data_list,
        "message": f"Tìm thấy {len(df_res)} kết quả.",
        
        # ✅ AI chỉ nhìn thấy ID này (nhẹ 36 bytes), không phải chuỗi ảnh (500KB)
        "chart_id": chart_id, 
        "chart_type": chart_type,
        
        # Đánh dấu null ở đây để AI không bị nhiễu
        "chart_base64": None, 
        
        "text": f"Đã tìm thấy dữ liệu.{' Có biểu đồ đi kèm.' if chart_id else ''}"
    }