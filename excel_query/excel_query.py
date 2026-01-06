"""
Module xử lý truy vấn trực tiếp file Excel về KCN/CCN
Tích hợp vào chatbot để trả về dữ liệu dạng JSON khi người dùng hỏi
về số lượng hoặc danh sách khu/cụm công nghiệp.

✅ BỔ SUNG:
- Load industrial_zones.geojson (tuỳ chọn) để gắn tọa độ cho từng KCN/CCN
- Trả JSON có thêm:
    - data[i]["coordinates"] = [lng, lat] (nếu match được)
    - not_found_coordinates: danh sách tên không match được tọa độ
"""

import pandas as pd
import re
import json
from typing import Dict, List, Optional, Tuple, Any
from pathlib import Path

# RapidFuzz (khuyến nghị). Nếu không có sẽ dùng fallback match cơ bản.
try:
    from rapidfuzz import fuzz, process
except Exception:
    fuzz = None
    process = None


class ExcelQueryHandler:
    def __init__(
        self,
        excel_path: str,
        geojson_path: Optional[str] = None,
        match_threshold: int = 82
    ):
        """
        Khởi tạo handler với đường dẫn file Excel

        Args:
            excel_path: Đường dẫn đến file Excel chứa thông tin KCN/CCN
            geojson_path: (tuỳ chọn) Đường dẫn industrial_zones.geojson để gắn tọa độ
            match_threshold: ngưỡng match tên (RapidFuzz) để chấp nhận tọa độ
        """
        self.excel_path = excel_path
        self.df: Optional[pd.DataFrame] = None

        self.match_threshold = match_threshold
        self.geojson_path = geojson_path

        # Lưu index map toạ độ: name_norm -> [lng, lat]
        self._iz_name_to_coord: Dict[str, List[float]] = {}
        self._iz_names_original: List[str] = []
        self._iz_names_norm: List[str] = []

        # Khai báo các cột cần thiết
        self.columns_map = {
            "province": None,
            "type": None,  # Cột Loại (KCN/CCN)
            "name": None,
            "address": None,
            "operation_time": None,
            "area": None,
            "rental_price": None,
            "industry": None
        }

        self._load_excel()
        self._load_geojson_if_provided()

    # ==========================================================
    # 🧩 LOAD FILE EXCEL & NHẬN DIỆN CỘT
    # ==========================================================
    def _load_excel(self):
        """Load file Excel và tự động phát hiện các cột quan trọng"""
        try:
            self.df = pd.read_excel(self.excel_path)
            self.df.columns = self.df.columns.str.strip()

            for col in self.df.columns:
                col_lower = col.lower()
                if any(k in col_lower for k in ["tỉnh", "thành phố", "province"]):
                    self.columns_map["province"] = col
                elif any(k in col_lower for k in ["loại", "loai", "type"]):
                    self.columns_map["type"] = col
                elif any(k in col_lower for k in ["tên", "ten", "kcn", "ccn"]) and "loại" not in col_lower:
                    self.columns_map["name"] = col
                elif any(k in col_lower for k in ["địa chỉ", "dia chi", "address"]):
                    self.columns_map["address"] = col
                elif any(k in col_lower for k in ["thời gian", "vận hành", "operation"]):
                    self.columns_map["operation_time"] = col
                elif any(k in col_lower for k in ["diện tích", "dien tich", "area"]):
                    self.columns_map["area"] = col
                elif any(k in col_lower for k in ["giá thuê", "gia thue", "rent", "rental"]):
                    self.columns_map["rental_price"] = col
                elif any(k in col_lower for k in ["ngành nghề", "nganh nghe", "industry"]):
                    self.columns_map["industry"] = col

            print(f"✅ Đã load Excel: {len(self.df)} bản ghi")
            print("🧭 Cấu trúc cột nhận diện được:")
            for key, val in self.columns_map.items():
                print(f"   - {key}: {val}")

        except Exception as e:
            print(f"❌ Lỗi khi load Excel: {e}")
            self.df = None

    # ==========================================================
    # 🗺️ LOAD GEOJSON (industrial_zones.geojson) để gắn tọa độ
    # ==========================================================
    def _load_geojson_if_provided(self):
        """
        Load GeoJSON nếu có path.
        Kết quả: map name_norm -> [lng, lat]
        """
        if not self.geojson_path:
            return

        p = Path(self.geojson_path)
        if not p.exists():
            print(f"⚠️ GeoJSON không tồn tại: {self.geojson_path} (bỏ qua gắn tọa độ)")
            return

        try:
            with open(p, "r", encoding="utf-8") as f:
                gj = json.load(f)

            features = gj.get("features", []) or []
            name_to_coord: Dict[str, List[float]] = {}

            iz_names_original: List[str] = []
            iz_names_norm: List[str] = []

            for fe in features:
                props = fe.get("properties", {}) or {}
                geom = fe.get("geometry", {}) or {}
                coords = geom.get("coordinates")

                name = str(props.get("name", "")).strip()
                if not name:
                    continue

                # Chỉ hỗ trợ Point [lng, lat] như file của bạn đang dùng
                if isinstance(coords, list) and len(coords) == 2 and all(isinstance(x, (int, float)) for x in coords):
                    n = self._normalize_text(name)
                    name_to_coord[n] = [float(coords[0]), float(coords[1])]
                    iz_names_original.append(name)
                    iz_names_norm.append(n)

            self._iz_name_to_coord = name_to_coord
            self._iz_names_original = iz_names_original
            self._iz_names_norm = iz_names_norm

            print(f"✅ Đã load GeoJSON IZ: {len(self._iz_name_to_coord)} điểm có tọa độ")

        except Exception as e:
            print(f"⚠️ Lỗi load GeoJSON: {e}. (bỏ qua gắn tọa độ)")

    # ==========================================================
    # 🧠 NHẬN DIỆN CÂU HỎI NGƯỜI DÙNG
    # ==========================================================
    def is_count_query(self, question: str) -> bool:
        """
        Nhận diện câu hỏi về tra cứu KCN/CCN (đếm, liệt kê, danh sách...).

        NOTE: bản cũ kiểm tra count_keywords nhưng cuối cùng vẫn return has_industrial.
        Ở đây giữ “thoáng” nhưng hợp lý hơn: cần có industrial keyword.
        """
        question_norm = self._normalize_text(question.lower())

        industrial_keywords = [
            "kcn", "ccn", "khu cong nghiep", "cum cong nghiep",
            "khu cn", "cum cn", "khu nghiep", "cum nghiep"
        ]

        has_industrial = any(k in question_norm for k in industrial_keywords)
        return has_industrial

    # ==========================================================
    # 🧭 XÁC ĐỊNH LOẠI TRUY VẤN (KHU / CỤM)
    # ==========================================================
    def detect_type(self, question: str) -> Optional[str]:
        """
        Xác định người dùng hỏi khu hay cụm công nghiệp.
        Ưu tiên từ khóa cụm trước.
        """
        q = self._normalize_text(question)

        if any(k in q for k in ["cum cong nghiep", "ccn", "cum cn", "cum nghiep"]):
            return "CCN"

        if any(k in q for k in ["khu cong nghiep", "kcn", "khu cn", "khu nghiep"]):
            return "KCN"

        if "cong nghiep" in q:
            return None

        return None

    # ==========================================================
    # 🧩 TRÍCH XUẤT TỈNH/THÀNH PHỐ
    # ==========================================================
    def extract_province(self, question: str) -> Optional[str]:
        """Trích xuất tên tỉnh/thành phố từ câu hỏi"""
        if self.df is None or self.columns_map["province"] is None:
            return None

        question_norm = self._normalize_text(question.lower())
        unique_provinces = self.df[self.columns_map["province"]].dropna().unique()

        # match exact substring theo normalized
        for prov in unique_provinces:
            prov_str = str(prov).strip()
            if not prov_str:
                continue
            prov_norm = self._normalize_text(prov_str)
            if prov_norm and prov_norm in question_norm:
                return prov_str

        if any(k in question_norm for k in ["toan quoc", "ca nuoc", "viet nam", "vn"]):
            return "TOÀN QUỐC"

        return None

    # ==========================================================
    # 🔡 CHUẨN HÓA TEXT (BỎ DẤU)
    # ==========================================================
    def _normalize_text(self, text: str) -> str:
        intab = "àáảãạăắằẳẵặâấầẩẫậèéẻẽẹêếềểễệìíỉĩịòóỏõọôốồổỗộơớờởỡợùúủũụưứừửữựỳýỷỹỵđ"
        outtab = "aaaaaaaaaaaaaaaaaeeeeeeeeeeeiiiiiooooooooooooooooouuuuuuuuuuuyyyyyd"
        intab_upper = "ÀÁẢÃẠĂẮẰẲẴẶÂẤẦẨẪẬÈÉẺẼẸÊẾỀỂỄỆÌÍỈĨỊÒÓỎÕỌÔỐỒỔỖỘƠỚỜỞỠỢÙÚỦŨỤƯỨỪỬỮỰỲÝỶỸỴĐ"
        outtab_upper = "AAAAAAAAAAAAAAAAAEEEEEEEEEEEIIIIIOOOOOOOOOOOOOOOOOUUUUUUUUUUUYYYYYD"
        transtab = str.maketrans(intab + intab_upper, outtab + outtab_upper)
        return str(text).translate(transtab).lower().strip()

    # ==========================================================
    # 🔍 TRUY VẤN DỮ LIỆU
    # ==========================================================
    def query_by_province(self, province_name: str, query_type: Optional[str]) -> Optional[pd.DataFrame]:
        """
        Lọc dữ liệu theo tỉnh/thành phố và loại (KCN/CCN).
        Sử dụng cột "Loại" có sẵn trong Excel để lọc chính xác.
        """
        if self.df is None or self.columns_map["province"] is None:
            return None

        # Lọc theo tỉnh/thành phố
        if province_name == "TOÀN QUỐC":
            df_filtered = self.df.copy()
        else:
            df_filtered = self.df[
                self.df[self.columns_map["province"]].astype(str).str.lower().str.contains(
                    str(province_name).lower(), na=False
                )
            ].copy()

        # Lọc theo loại KCN/CCN dựa vào cột "Loại"
        if query_type and self.columns_map["type"] is not None:
            df_filtered = df_filtered[
                df_filtered[self.columns_map["type"]].astype(str).str.strip().str.upper() == query_type
            ]

        return df_filtered

    # ==========================================================
    # 🧭 MATCH TỌA ĐỘ THEO TÊN KCN/CCN
    # ==========================================================
    def _match_coordinates(self, zone_name: str) -> Optional[List[float]]:
        """
        Trả về [lng, lat] nếu match được tên zone trong GeoJSON.
        """
        if not zone_name:
            return None
        if not self._iz_name_to_coord:
            return None

        z_norm = self._normalize_text(zone_name)

        # 1) exact match normalized
        if z_norm in self._iz_name_to_coord:
            return self._iz_name_to_coord[z_norm]

        # 2) fuzzy match nếu có rapidfuzz
        if process is not None and fuzz is not None and self._iz_names_original:
            result = process.extractOne(zone_name, self._iz_names_original, scorer=fuzz.WRatio)
            if result and result[1] >= self.match_threshold:
                best_name = result[0]
                best_norm = self._normalize_text(best_name)
                return self._iz_name_to_coord.get(best_norm)

        # 3) fallback: contains match normalized (thô)
        for n, coord in self._iz_name_to_coord.items():
            if n and (n in z_norm or z_norm in n):
                return coord

        return None

    # ==========================================================
    # 🧾 TRẢ KẾT QUẢ DẠNG JSON (dict hoặc string)
    # ==========================================================
    def format_json_response(
        self,
        df: pd.DataFrame,
        province_name: str,
        query_type: Optional[str],
        as_string: bool = True
    ) -> Any:
        """
        Trả kết quả truy vấn dạng JSON.
        - as_string=True: trả về chuỗi JSON
        - as_string=False: trả về dict (khuyến nghị khi dùng trong Flask)
        """
        label = "khu" if query_type == "KCN" else "cụm" if query_type == "CCN" else "khu/cụm"

        if df is None or df.empty:
            obj = {
                "province": province_name,
                "type": query_type,
                "count": 0,
                "message": f"Không tìm thấy {label} công nghiệp tại {province_name}.",
                "data": [],
                "not_found_coordinates": []
            }
            return json.dumps(obj, ensure_ascii=False, indent=2) if as_string else obj

        cols = self.columns_map
        records = []
        not_found = []

        for _, row in df.iterrows():
            name_val = str(row.get(cols["name"], "")).strip()

            coord = self._match_coordinates(name_val)

            item = {
                "Tỉnh/Thành phố": str(row.get(cols["province"], "")),
                "Loại": str(row.get(cols["type"], "")),
                "Tên": name_val,
                "Địa chỉ": str(row.get(cols["address"], "")),
                "Thời gian vận hành": str(row.get(cols["operation_time"], "")),
                "Tổng diện tích": str(row.get(cols["area"], "")),
                "Giá thuê đất": str(row.get(cols["rental_price"], "")),
                "Ngành nghề": str(row.get(cols["industry"], "")),
                # ✅ BỔ SUNG TỌA ĐỘ
                "coordinates": coord
            }

            if coord is None and name_val:
                not_found.append(name_val)

            records.append(item)

        obj = {
            "province": province_name,
            "type": query_type,
            "count": len(records),
            "message": f"{province_name} có {len(records)} {label} công nghiệp.",
            "data": records,
            "not_found_coordinates": not_found
        }

        return json.dumps(obj, ensure_ascii=False, indent=2) if as_string else obj

    # ==========================================================
    # ⚙️ XỬ LÝ TRUY VẤN NGƯỜI DÙNG
    # ==========================================================
    def process_query(self, question: str, return_json: bool = True) -> Tuple[bool, Optional[Any]]:
        """
        Xử lý truy vấn và trả kết quả.
        - return_json=True: trả JSON (mặc định)
            + trả về STRING JSON (để backward compatible)
        - return_json=False: trả text bảng (như cũ)

        Return:
            (handled: bool, response: Optional[str|dict])
        """
        if not self.is_count_query(question):
            return False, None

        province = self.extract_province(question)
        if province is None:
            # Ở đây để "handled=True" hay "False" tuỳ bạn.
            # Mình để True để phía server/frontend biết đây là nhánh Excel nhưng thiếu tỉnh.
            err = {"error": "❓ Bạn vui lòng nêu rõ tỉnh/thành phố cần tra cứu."}
            return True, json.dumps(err, ensure_ascii=False) if return_json else err["error"]

        query_type = self.detect_type(question)
        if query_type is None:
            err = {"error": "❓ Bạn muốn tra cứu KHU công nghiệp hay CỤM công nghiệp? Vui lòng nêu rõ."}
            return True, json.dumps(err, ensure_ascii=False) if return_json else err["error"]

        df_result = self.query_by_province(province, query_type)

        if return_json:
            # ✅ trả string JSON để giữ tương thích code cũ
            return True, self.format_json_response(df_result, province, query_type, as_string=True)
        else:
            return True, self.format_table_response(df_result, province, query_type)

    # ==========================================================
    # 🧩 GIỮ LẠI HÀM CŨ (BẢNG TEXT)
    # ==========================================================
    def format_table_response(self, df: pd.DataFrame, province_name: str, query_type: Optional[str]) -> str:
        """(Tuỳ chọn) Hiển thị kết quả dạng bảng text"""
        label = "khu" if query_type == "KCN" else "cụm" if query_type == "CCN" else "khu/cụm"

        if df is None or df.empty:
            return f"Không tìm thấy {label} công nghiệp tại {province_name}."

        cols = self.columns_map
        response = f"📊 {province_name} có {len(df)} {label} công nghiệp.\n\n"
        for _, row in df.iterrows():
            response += f"- {row.get(cols['name'], 'Không rõ')} ({row.get(cols['address'], '')})\n"
        return response


# ==========================================================
# 🔌 TÍCH HỢP VÀO CHATBOT
# ==========================================================
def integrate_excel_to_chatbot(excel_path: str, geojson_path: Optional[str] = None):
    """Tích hợp module Excel vào chatbot"""
    if not Path(excel_path).exists():
        print(f"❌ Không tìm thấy file Excel: {excel_path}")
        return None
    handler = ExcelQueryHandler(excel_path, geojson_path=geojson_path)
    print("✅ Đã tích hợp module truy vấn Excel.")
    return handler


# ==========================================================
# 🧪 TEST MODULE
# ==========================================================
if __name__ == "__main__":
    EXCEL_FILE = r"./data/IIPMap_FULL_63_COMPLETE.xlsx"
    GEOJSON_FILE = r"./map_ui/industrial_zones.geojson"  

    handler = ExcelQueryHandler(EXCEL_FILE, geojson_path=GEOJSON_FILE)

    test_queries = [
        "Danh sách cụm công nghiệp ở Bắc Ninh",
        "Danh sách khu công nghiệp ở Bắc Ninh"
    ]

    print("\n" + "=" * 80)
    print("TEST MODULE TRẢ KẾT QUẢ DẠNG JSON (CÓ TỌA ĐỘ)")
    print("=" * 80)

    for query in test_queries:
        print(f"\n❓ {query}")
        handled, response = handler.process_query(query, return_json=True)
        if handled:
            print(response)
        else:
            print("⏭️ Bỏ qua - Không phải câu hỏi liệt kê KCN/CCN hoặc thiếu thông tin")
        print("-" * 80)
