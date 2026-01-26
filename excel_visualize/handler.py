import pandas as pd
from .rag_core import rag_agent
from .data_adapter import clean_numeric_data, _parse_price_to_float, _parse_area_to_float
from .chart import (
    plot_price_bar_chart_base64, 
    plot_area_bar_chart_base64, 
    plot_dual_bar_chart_base64,
    plot_horizontal_bar_chart, 
    plot_pie_chart,            
    plot_line_chart            
)

# 🗺️ IMPORT EXCEL_QUERY HANDLER ĐỂ SỬ DỤNG COORDINATES MATCHING
from excel_query.excel_query import ExcelQueryHandler
from pathlib import Path
import os

# 🎯 IMPORT PROVINCE ZOOM HANDLER từ main hoặc main_local
try:
    from kcn_detail_query import process_kcn_detail_query
    KCN_DETAIL_AVAILABLE = True
    print("✅ KCN Detail Query module loaded")
except ImportError as e:
    KCN_DETAIL_AVAILABLE = False
    print(f"⚠️ KCN Detail Query not available: {e}")
    def process_kcn_detail_query(*args, **kwargs):
        return None
def get_province_zoom_info(province_name: str):
    """Import province zoom handler từ main.py (unified server)"""
    try:
        from main import get_province_zoom_info as _get_zoom
        return _get_zoom(province_name)
    except ImportError as e:
        print(f"⚠️ Province zoom không khả dụng cho {province_name}: {e}")
        return None

# Load paths
BASE_DIR = Path(__file__).resolve().parent.parent
EXCEL_FILE_PATH = str(BASE_DIR / "data" / "IIPMap_FULL_63_COMPLETE.xlsx")
GEOJSON_IZ_PATH = str(BASE_DIR / "map_ui" / "industrial_zones.geojson")

# 🎯 GLOBAL EXCEL HANDLER FOR COORDINATES MATCHING
_excel_handler_for_coords = None

def _get_excel_handler():
    """Lazy load excel handler for coordinates matching"""
    global _excel_handler_for_coords
    if _excel_handler_for_coords is None:
        _excel_handler_for_coords = ExcelQueryHandler(
            excel_path=EXCEL_FILE_PATH,
            geojson_path=GEOJSON_IZ_PATH
        )
    return _excel_handler_for_coords

def _add_coordinates_to_data(data_list: list) -> list:
    """
    Thêm tọa độ vào dữ liệu từ GeoJSON
    """
    try:
        excel_handler = _get_excel_handler()
        
        for item in data_list:
            kcn_name = item.get('Tên', '')
            if kcn_name:
                # Tìm coordinates từ GeoJSON using the correct method
                coordinates = excel_handler._match_coordinates(kcn_name)
                if coordinates and len(coordinates) == 2:
                    item['coordinates'] = coordinates
                else:
                    item['coordinates'] = None
            else:
                item['coordinates'] = None
                
        return data_list
        
    except Exception as e:
        print(f"⚠️ Error adding coordinates: {e}")
        # Trả về data gốc nếu có lỗi
        for item in data_list:
            item['coordinates'] = None
        return data_list

def _get_province_zoom_for_data(data_list: list) -> dict:
    """
    Lấy thông tin province zoom từ dữ liệu
    """
    try:
        # Lấy tỉnh đầu tiên từ data
        if not data_list:
            return None
            
        first_province = None
        for item in data_list:
            province = item.get('Tỉnh/Thành phố', '')
            if province:
                first_province = province
                break
        
        if not first_province:
            return None
            
        # Lấy province zoom info
        zoom_info = get_province_zoom_info(first_province)
        if zoom_info:
            print(f"✅ Đã lấy province zoom cho {first_province}: zoom level {zoom_info['zoom_level']}")
            return zoom_info
        else:
            print(f"⚠️ Không tìm thấy province zoom cho {first_province}")
            return None
            
    except Exception as e:
        print(f"⚠️ Error getting province zoom: {e}")
        return None

def handle_excel_visualize(message: str) -> dict:
    query_result = rag_agent.retrieve_filters(message)
    if query_result.get("filter_type") == "error":
        return _error_response(query_result.get("message", "Lỗi xử lý câu hỏi."))

    df_filtered = query_result.get("data")
    industrial_type = query_result.get("industrial_type", "Khu công nghiệp")
    
    viz_metric = query_result.get("visualization_metric", "dual") 
    chart_type = query_result.get("chart_type", "bar")            

    if df_filtered is None or df_filtered.empty:
        return _error_response(f"Không tìm thấy {industrial_type} nào phù hợp.")

    found_provinces = df_filtered["Tỉnh/Thành phố"].unique().tolist()
    province_str = ", ".join(found_provinces) if found_provinces else "Khu vực tìm kiếm"

    # --- FIX LỖI BIỂU ĐỒ TRÒN ---
    if chart_type == "pie" and viz_metric in ["dual", "price"]:
        viz_metric = "area"

    # Tạo data list cho bản đồ và bảng (giống excel_query) với coordinates matching
    excel_handler = _get_excel_handler()
    data_list = []
    for _, row in df_filtered.iterrows():
        zone_name = row.get("Tên", "")
        # 🎯 MATCH COORDINATES USING EXCEL_QUERY LOGIC
        coordinates = excel_handler._match_coordinates(zone_name) if zone_name else None
        
        data_list.append({
            "Tên": zone_name,
            "Địa chỉ": row.get("Địa chỉ", ""),
            "Tổng diện tích": row.get("Tổng diện tích", ""),
            "Giá thuê đất": row.get("Giá thuê đất", ""),
            "Ngành nghề": row.get("Ngành nghề", ""),
            "Loại": row.get("Loại", industrial_type),
            "Tỉnh/Thành phố": row.get("Tỉnh/Thành phố", ""),
            "coordinates": coordinates  # Sử dụng coordinates từ matching
        })

    # 1. BIỂU ĐỒ ĐÔI (DUAL)
    if viz_metric == "dual":
        df_dual = df_filtered.copy()
        df_dual["Giá số"] = df_dual["Giá thuê đất"].apply(_parse_price_to_float)
        df_dual["Diện tích số"] = df_dual["Tổng diện tích"].apply(_parse_area_to_float)
        df_dual = df_dual.dropna(subset=["Giá số", "Diện tích số"], how="all")
        
        if df_dual.empty: return _error_response("Không có đủ dữ liệu để vẽ.")

        # Sắp xếp để đánh số thứ tự chuẩn (Ưu tiên Giá -> Diện tích)
        df_sorted = df_dual.sort_values(by=["Giá số", "Diện tích số"], ascending=[False, False])

        # Vẽ biểu đồ (đã sort)
        chart_base64 = plot_dual_bar_chart_base64(df_sorted, province_str, industrial_type)
        
        # Tạo JSON Items (đã sort)
        items = []
        for idx, row in enumerate(df_sorted.iterrows()):
            _, r = row
            items.append({
                "index": idx + 1,
                "name": r.get("Tên", ""),
                "price": r.get("Giá thuê đất", "N/A"),
                "area": r.get("Tổng diện tích", "N/A")
            })

        # 🗺️ THÊM COORDINATES VÀO DATA
        data_list = _add_coordinates_to_data(data_list)
        
        # 🎯 LẤY PROVINCE ZOOM INFO
        province_zoom = _get_province_zoom_for_data(data_list)

        return {
            "type": "excel_visualize_with_data",
            "province": province_str,
            "industrial_type": industrial_type,
            "metric": "dual",
            "count": len(data_list),
            "message": f"Đã tạo biểu đồ và danh sách {len(data_list)} {industrial_type.lower()} tại {province_str}",
            "data": data_list,
            "items": items,
            "chart_base64": chart_base64,
            "base64": chart_base64,  # 🎯 THÊM TRƯỜNG BASE64 CHO XUẤT DỮ LIỆU
            "text": f"Đã vẽ biểu đồ tổng quan (Giá & Diện tích) tại {province_str}.",
            "has_coordinates": True,
            "exportable": True,  # Đánh dấu có thể xuất JSON
            "province_zoom": province_zoom  # 🎯 THÊM PROVINCE ZOOM INFO
        }

    # 2. BIỂU ĐỒ ĐƠN (GIÁ hoặc DIỆN TÍCH)
    else:
        is_price = (viz_metric == "price")
        df_plot = clean_numeric_data(df_filtered, is_price_metric=is_price)
        if df_plot.empty: return _error_response(f"Thiếu dữ liệu về {'Giá' if is_price else 'Diện tích'}.")
        
        col_name = "Giá số" if is_price else "Diện tích số"
        unit = "USD/m²/năm" if is_price else "ha"
        color = "#1f77b4" if is_price else "#2ca02c"
        metric_vn = "GIÁ THUÊ" if is_price else "DIỆN TÍCH"
        full_title = f"{metric_vn} {industrial_type.upper()}\nTẠI {province_str.upper()}"

        # Sắp xếp giảm dần
        df_sorted = df_plot.sort_values(by=col_name, ascending=False)

        # Chọn hàm vẽ
        if chart_type == "pie":
            chart_base64 = plot_pie_chart(df_sorted, full_title, col_name, unit)
        elif chart_type == "line":
            chart_base64 = plot_line_chart(df_sorted, full_title, col_name, color, unit)
        elif chart_type == "barh":
            chart_base64 = plot_horizontal_bar_chart(df_sorted, full_title, col_name, color, unit)
        else:
            if is_price:
                chart_base64 = plot_price_bar_chart_base64(df_sorted, province_str, industrial_type)
            else:
                chart_base64 = plot_area_bar_chart_base64(df_sorted, province_str, industrial_type)

        items = []
        for idx, row in enumerate(df_sorted.iterrows()):
            _, r = row
            val = r.get("Giá thuê đất", "N/A") if is_price else r.get("Tổng diện tích", "N/A")
            items.append({
                "index": idx + 1,
                "name": r.get("Tên", ""),
                viz_metric: val
            })

        # 🗺️ THÊM COORDINATES VÀO DATA CHO SINGLE CHART
        data_list = _add_coordinates_to_data(data_list)
        
        # 🎯 LẤY PROVINCE ZOOM INFO
        province_zoom = _get_province_zoom_for_data(data_list)

        return {
            "type": "excel_visualize_with_data",
            "province": province_str,
            "industrial_type": industrial_type,
            "metric": viz_metric,
            "chart_type": chart_type,
            "count": len(data_list),
            "message": f"Đã tạo biểu đồ và danh sách {len(data_list)} {industrial_type.lower()} tại {province_str}",
            "data": data_list,
            "items": items,
            "chart_base64": chart_base64,
            "base64": chart_base64,  # 🎯 THÊM TRƯỜNG BASE64 CHO XUẤT DỮ LIỆU
            "text": f"Đã vẽ {chart_type.replace('pie','biểu đồ tròn').replace('line','biểu đồ đường').replace('barh','biểu đồ ngang').replace('bar','biểu đồ cột')} về {metric_vn.lower()} tại {province_str}.",
            "has_coordinates": True,
            "exportable": True,  # Đánh dấu có thể xuất JSON
            "province_zoom": province_zoom  # 🎯 THÊM PROVINCE ZOOM INFO
        }

def _error_response(msg):
    return {"type": "error", "message": msg}