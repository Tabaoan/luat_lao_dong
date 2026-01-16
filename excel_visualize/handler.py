# File: excel_visualize/handler.py
import pandas as pd
from .rag_core import rag_agent
from .data_adapter import clean_numeric_data
from .chart import plot_price_bar_chart_base64, plot_area_bar_chart_base64
from .intent import detect_excel_metric

def handle_excel_visualize(message: str) -> dict:
    """
    Xử lý yêu cầu visualize, sử dụng RAG để lọc dữ liệu 
    và trả về JSON đúng định dạng cũ (price/area).
    """
    # 1. Nhận diện Metric (Giá hay Diện tích)
    metric_intent = detect_excel_metric(message) or "Giá thuê đất"
    is_price_metric = "giá" in metric_intent.lower()

    # 2. Query RAG Agent
    # Agent này đã tự động phân loại Khu/Cụm và lọc Data theo Tỉnh hoặc Tên riêng
    query_result = rag_agent.retrieve_filters(message)
    
    # Check lỗi từ Agent
    if query_result.get("filter_type") == "error":
        return _error_response(query_result.get("message", "Lỗi xử lý câu hỏi."))

    df_filtered = query_result.get("data")
    industrial_type = query_result.get("industrial_type", "Khu công nghiệp") 

    # 3. Kiểm tra dữ liệu sau lọc
    if df_filtered is None or df_filtered.empty:
        return _error_response(f"Không tìm thấy {industrial_type} nào phù hợp.")

    # 4. Xác định tên Tỉnh/Khu vực để hiển thị (trường 'province' trong JSON)
    # Lấy danh sách các tỉnh tìm thấy trong dữ liệu
    found_provinces = df_filtered["Tỉnh/Thành phố"].unique().tolist()
    province_str = ", ".join(found_provinces) if found_provinces else "Khu vực tìm kiếm"

    # 5. Làm sạch số liệu để vẽ biểu đồ (Cần số float)
    # Lưu ý: df_plot dùng để vẽ (số), df_filtered dùng để trả về text (nguyên bản)
    df_plot = clean_numeric_data(df_filtered, is_price_metric)

    if df_plot.empty:
        return _error_response(f"Có tìm thấy địa điểm nhưng thiếu dữ liệu về {metric_intent}.")

    # 6. Vẽ biểu đồ và Đóng gói JSON
    if is_price_metric:
        # --- TRƯỜNG HỢP GIÁ ---
        chart_base64 = plot_price_bar_chart_base64(df_plot, province_str, industrial_type)
        
        # Tạo danh sách items đúng format yêu cầu
        items = []
        for _, row in df_filtered.iterrows():
            items.append({
                "name": row.get("Tên", ""),
                "price": row.get("Giá thuê đất", "N/A") # Lấy giá trị gốc (text)
            })

        return {
            "type": "excel_visualize_price",
            "province": province_str,
            "industrial_type": industrial_type,
            "metric": "price",
            "items": items,
            "chart_base64": chart_base64,
            # Thêm text để CLI in ra dễ đọc nếu cần
            "text": f"Đã vẽ biểu đồ giá thuê đất tại {province_str}."
        }
        
    else:
        # --- TRƯỜNG HỢP DIỆN TÍCH ---
        chart_base64 = plot_area_bar_chart_base64(df_plot, province_str, industrial_type)
        
        items = []
        for _, row in df_filtered.iterrows():
            items.append({
                "name": row.get("Tên", ""),
                "area": row.get("Tổng diện tích", "N/A") 
            })

        return {
            "type": "excel_visualize_area",
            "province": province_str,
            "industrial_type": industrial_type,
            "metric": "area",
            "items": items,
            "chart_base64": chart_base64,
            "text": f"Đã vẽ biểu đồ diện tích tại {province_str}."
        }

def _error_response(msg):
    return {
        "type": "error",
        "message": msg
    }