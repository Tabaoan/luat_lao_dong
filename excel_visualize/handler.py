from .data_adapter import (
    extract_price_data,
    extract_area_data
)
from .chart import (
    plot_price_bar_chart_base64,
    plot_area_bar_chart_base64,
    plot_price_bar_chart_two_provinces_base64,
    plot_area_bar_chart_two_provinces_base64
)
from .intent import (
    detect_industrial_type,
    detect_excel_metric,
    parse_excel_numeric_filter
)

from typing import Dict, Any, List


def extract_province_from_excel(message: str, excel_handler) -> str | None:
    msg = message.lower()

    provinces = (
        excel_handler.df["Tỉnh/Thành phố"]
        .dropna()
        .astype(str)
        .unique()
    )

    # Ưu tiên tỉnh có tên dài hơn (VD: Bà Rịa - Vũng Tàu)
    for province in sorted(provinces, key=len, reverse=True):
        if province.lower() in msg:
            return province

    return None


# =========================
# ✅ NEW: Extract 2 provinces (nếu có)
# =========================
def extract_provinces_from_excel(message: str, excel_handler, max_provinces: int = 2) -> List[str]:
    msg = message.lower()

    provinces = (
        excel_handler.df["Tỉnh/Thành phố"]
        .dropna()
        .astype(str)
        .unique()
    )

    found: List[str] = []
    for province in sorted(provinces, key=len, reverse=True):
        if province.lower() in msg:
            found.append(province)

    # loại trùng nhưng giữ thứ tự
    unique_found = list(dict.fromkeys(found))
    return unique_found[:max_provinces]


# =========================
# ✅ NEW: Nhận diện so sánh giữa 2 tỉnh
# =========================
def _is_cross_province_compare(message: str) -> bool:
    msg = message.lower()
    keywords = ["giữa", "so với", "vs", "và", "hai tỉnh", "2 tỉnh"]
    return any(k in msg for k in keywords)


# =========================
# Format mô tả điều kiện để báo lỗi
# =========================
def _format_filter_rule(rule: Dict[str, Any], unit: str) -> str:
    if not rule:
        return ""

    t = rule.get("type")
    if t == "between":
        return f"từ {rule.get('min')} đến {rule.get('max')} {unit}".strip()
    if t == "gte":
        return f"lớn hơn hoặc bằng {rule.get('value')} {unit}".strip()
    if t == "lte":
        return f"nhỏ hơn hoặc bằng {rule.get('value')} {unit}".strip()
    if t == "gt":
        return f"lớn hơn {rule.get('value')} {unit}".strip()
    if t == "lt":
        return f"nhỏ hơn {rule.get('value')} {unit}".strip()
    return ""


# =========================
# Áp điều kiện lọc lên df (đã có cột số từ data_adapter)
# =========================
def _apply_numeric_filter(df, metric: str, rule: Dict[str, Any]):
    if df is None or df.empty or not rule:
        return df

    df = df.copy()

    # ✅ đồng bộ cột số
    if metric == "price":
        num_col = "Giá số"
    else:
        # area: "Tổng diện tích" đã là float từ data_adapter
        num_col = "Tổng diện tích"

    if num_col not in df.columns:
        return df

    t = rule.get("type")

    if t == "between":
        lo = rule.get("min")
        hi = rule.get("max")
        return df[(df[num_col] >= lo) & (df[num_col] <= hi)]

    if t == "gte":
        v = rule.get("value")
        return df[df[num_col] >= v]

    if t == "lte":
        v = rule.get("value")
        return df[df[num_col] <= v]

    if t == "gt":
        v = rule.get("value")
        return df[df[num_col] > v]

    if t == "lt":
        v = rule.get("value")
        return df[df[num_col] < v]

    return df


def handle_excel_visualize(message: str, excel_handler):
    # =========================
    # 0️⃣ Validate handler
    # =========================
    if excel_handler is None:
        return {
            "type": "error",
            "message": "Chưa cấu hình dữ liệu Excel."
        }

    # =========================
    # 1️⃣ Provinces (ưu tiên bắt 2 tỉnh nếu có)
    # =========================
    provinces = extract_provinces_from_excel(message, excel_handler, max_provinces=2)

    # Nếu không bắt được tỉnh nào → lỗi như cũ
    if not provinces:
        return {
            "type": "error",
            "message": "Vui lòng nêu rõ tỉnh/thành phố."
        }

    # =========================
    # 2️⃣ Industrial type
    # =========================
    industrial_type = detect_industrial_type(message)
    if not industrial_type:
        return {
            "type": "error",
            "message": (
                "Vui lòng cho biết bạn muốn xem "
                "**khu công nghiệp** hay **cụm công nghiệp**."
            )
        }

    # =========================
    # 3️⃣ Metric (price / area)
    # =========================
    metric = detect_excel_metric(message)
    if not metric:
        return {
            "type": "error",
            "message": (
                "Vui lòng cho biết bạn muốn so sánh "
                "**giá thuê đất** hay **tổng diện tích**."
            )
        }

    # ✅ Parse điều kiện lọc (nếu người dùng có nói)
    filter_rule = parse_excel_numeric_filter(message)

    # =========================================================
    # ✅ NEW: 2 TỈNH + PRICE → VẼ 2 BIỂU ĐỒ (TRÊN/DƯỚI)
    # =========================================================
    if metric == "price" and len(provinces) >= 2 and _is_cross_province_compare(message):
        p1, p2 = provinces[0], provinces[1]

        df1 = extract_price_data(
            excel_handler=excel_handler,
            province=p1,
            industrial_type=industrial_type
        )
        df2 = extract_price_data(
            excel_handler=excel_handler,
            province=p2,
            industrial_type=industrial_type
        )

        if df1.empty:
            return {
                "type": "error",
                "message": f"Không có dữ liệu {industrial_type.lower()} tại {p1}."
            }
        if df2.empty:
            return {
                "type": "error",
                "message": f"Không có dữ liệu {industrial_type.lower()} tại {p2}."
            }

        df1_filtered = _apply_numeric_filter(df1, metric="price", rule=filter_rule)
        df2_filtered = _apply_numeric_filter(df2, metric="price", rule=filter_rule)

        if df1_filtered.empty or df2_filtered.empty:
            cond_text = _format_filter_rule(filter_rule, unit="USD/m²/năm")
            return {
                "type": "error",
                "message": (
                    f"Một trong hai tỉnh không có dữ liệu thỏa điều kiện {cond_text}."
                    if cond_text else
                    "Một trong hai tỉnh không có dữ liệu thỏa điều kiện yêu cầu."
                )
            }

        chart_base64 = plot_price_bar_chart_two_provinces_base64(
            df1_filtered, p1,
            df2_filtered, p2,
            industrial_type
        )

        # ✅ NEW TYPE (riêng cho 2 tỉnh)
        return {
            "type": "excel_visualize_price_compare_province",
            "provinces": [p1, p2],
            "industrial_type": industrial_type,
            "metric": "price",
            "items": {
                p1: [
                    {"name": row["Tên"], "price": row["Giá thuê đất"]}
                    for _, row in df1_filtered.iterrows()
                ],
                p2: [
                    {"name": row["Tên"], "price": row["Giá thuê đất"]}
                    for _, row in df2_filtered.iterrows()
                ],
            },
            "chart_base64": chart_base64
        }
    
    # =========================================================
    # ✅ NEW: 2 TỈNH + AREA → VẼ 2 BIỂU ĐỒ (TRÊN/DƯỚI)
    # =========================================================
    if metric == "area" and len(provinces) >= 2 and _is_cross_province_compare(message):
        p1, p2 = provinces[0], provinces[1]

        df1 = extract_area_data(
            excel_handler=excel_handler,
            province=p1,
            industrial_type=industrial_type
        )
        df2 = extract_area_data(
            excel_handler=excel_handler,
            province=p2,
            industrial_type=industrial_type
        )

        if df1.empty:
            return {"type": "error", "message": f"Không có dữ liệu {industrial_type.lower()} tại {p1}."}
        if df2.empty:
            return {"type": "error", "message": f"Không có dữ liệu {industrial_type.lower()} tại {p2}."}

        df1_filtered = _apply_numeric_filter(df1, metric="area", rule=filter_rule)
        df2_filtered = _apply_numeric_filter(df2, metric="area", rule=filter_rule)

        if df1_filtered.empty or df2_filtered.empty:
            cond_text = _format_filter_rule(filter_rule, unit="ha")
            return {
                "type": "error",
                "message": (
                    f"Một trong hai tỉnh không có dữ liệu thỏa điều kiện {cond_text}."
                    if cond_text else
                    "Một trong hai tỉnh không có dữ liệu thỏa điều kiện yêu cầu."
                )
            }

        chart_base64 = plot_area_bar_chart_two_provinces_base64(
            df1_filtered, p1,
            df2_filtered, p2,
            industrial_type
        )

        return {
            "type": "excel_visualize_area_compare_province",
            "provinces": [p1, p2],
            "industrial_type": industrial_type,
            "metric": "area",
            "items": {
                p1: [{"name": row["Tên"], "area": row["Tổng diện tích"]} for _, row in df1_filtered.iterrows()],
                p2: [{"name": row["Tên"], "area": row["Tổng diện tích"]} for _, row in df2_filtered.iterrows()],
            },
            "chart_base64": chart_base64
        }


    # =========================
    # 4️⃣ Province (fallback về 1 tỉnh như cũ)
    # =========================
    province = provinces[0]

    # =========================
    # 4️⃣ PRICE CHART (1 tỉnh)
    # =========================
    if metric == "price":
        df = extract_price_data(
            excel_handler=excel_handler,
            province=province,
            industrial_type=industrial_type
        )

        if df.empty:
            return {
                "type": "error",
                "message": (
                    f"Không có dữ liệu {industrial_type.lower()} "
                    f"tại {province}."
                )
            }

        df_filtered = _apply_numeric_filter(df, metric="price", rule=filter_rule)

        if df_filtered.empty:
            cond_text = _format_filter_rule(filter_rule, unit="USD/m²/năm")
            return {
                "type": "error",
                "message": (
                    f"Không có dữ liệu {industrial_type.lower()} tại {province} "
                    f"thỏa điều kiện {cond_text}."
                    if cond_text else
                    f"Không có dữ liệu {industrial_type.lower()} tại {province} thỏa điều kiện yêu cầu."
                )
            }

        chart_base64 = plot_price_bar_chart_base64(
            df_filtered,
            province,
            industrial_type
        )

        # ✅ JSON GIỮ NGUYÊN CẤU TRÚC (không thêm key mới)
        return {
            "type": "excel_visualize_price",
            "province": province,
            "industrial_type": industrial_type,
            "metric": "price",
            "items": [
                {
                    "name": row["Tên"],
                    "price": row["Giá thuê đất"]
                }
                for _, row in df_filtered.iterrows()
            ],
            "chart_base64": chart_base64
        }

    # =========================
    # 5️⃣ AREA CHART (1 tỉnh)
    # =========================
    if metric == "area":
        df = extract_area_data(
            excel_handler=excel_handler,
            province=province,
            industrial_type=industrial_type
        )

        if df.empty:
            return {
                "type": "error",
                "message": (
                    f"Không có dữ liệu {industrial_type.lower()} "
                    f"tại {province}."
                )
            }

        df_filtered = _apply_numeric_filter(df, metric="area", rule=filter_rule)

        if df_filtered.empty:
            cond_text = _format_filter_rule(filter_rule, unit="ha")
            return {
                "type": "error",
                "message": (
                    f"Không có dữ liệu {industrial_type.lower()} tại {province} "
                    f"thỏa điều kiện {cond_text}."
                    if cond_text else
                    f"Không có dữ liệu {industrial_type.lower()} tại {province} thỏa điều kiện yêu cầu."
                )
            }

        chart_base64 = plot_area_bar_chart_base64(
            df_filtered,
            province,
            industrial_type
        )

        # ✅ JSON GIỮ NGUYÊN CẤU TRÚC (không thêm key mới)
        return {
            "type": "excel_visualize_area",
            "province": province,
            "industrial_type": industrial_type,
            "metric": "area",
            "items": [
                {
                    "name": row["Tên"],
                    "area": row["Tổng diện tích"]
                }
                for _, row in df_filtered.iterrows()
            ],
            "chart_base64": chart_base64
        }

    # =========================
    # 6️⃣ Fallback 
    # =========================
    return {
        "type": "error",
        "message": "Không xác định được loại biểu đồ cần hiển thị."
    }
