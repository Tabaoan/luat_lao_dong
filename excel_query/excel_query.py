"""
Module xử lý truy vấn trực tiếp file Excel về KCN/CCN
Tích hợp vào chatbot để trả về dữ liệu dạng JSON khi người dùng hỏi
về số lượng hoặc danh sách khu/cụm công nghiệp.
"""

import pandas as pd
import re
import json
from typing import Dict, List, Optional, Tuple, Any
from pathlib import Path


class ExcelQueryHandler:
    def __init__(self, excel_path: str):
        """
        Khởi tạo handler với đường dẫn file Excel

        Args:
            excel_path: Đường dẫn đến file Excel chứa thông tin KCN/CCN
        """
        self.excel_path = excel_path
        self.df = None

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
    # 🧠 NHẬN DIỆN CÂU HỎI NGƯỜI DÙNG
    # ==========================================================
    def is_count_query(self, question: str) -> bool:
        """
        Nhận diện câu hỏi về đếm hoặc liệt kê KCN/CCN.
        """
        question_norm = self._normalize_text(question.lower())

        # Các nhóm từ khóa
        count_keywords = [
            "bao nhieu", "so luong", "tong so", "dem", "ke ten",
            "liet ke", "cho biet", "bao gom", "ke ra",
            "danh sach", "toan bo", "danh muc", "cac", "nhung", "o", "tai"
        ]

        industrial_keywords = [
            "kcn", "ccn", "khu cong nghiep", "cum cong nghiep",
            "khu cn", "cum cn", "khu nghiep", "cum nghiep", "cong nghiep"
        ]

        # Nếu có cụm công nghiệp hoặc khu công nghiệp trong câu
        has_industrial = any(k in question_norm for k in industrial_keywords)

        # Nếu có từ khóa liệt kê
        has_count = any(k in question_norm for k in count_keywords)

        # Chấp nhận nếu có industrial keywords (vì thường khi hỏi về KCN/CCN là muốn tra cứu)
        return has_industrial

    # ==========================================================
    # 🧭 XÁC ĐỊNH LOẠI TRUY VẤN (KHU / CỤM)
    # ==========================================================
    def detect_type(self, question: str) -> Optional[str]:
        """
        Xác định người dùng hỏi khu hay cụm công nghiệp.
        Ưu tiên từ khóa cụ thể trước.
        """
        q = self._normalize_text(question)
        
        # Kiểm tra CỤM trước (vì "cụm" cụ thể hơn)
        if any(k in q for k in ["cum cong nghiep", "ccn", "cum cn", "cum nghiep"]):
            return "CCN"
        
        # Kiểm tra KHU sau
        if any(k in q for k in ["khu cong nghiep", "kcn", "khu cn", "khu nghiep"]):
            return "KCN"
        
        # Nếu chỉ có "công nghiệp" chung chung thì trả về None
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

        for prov in unique_provinces:
            prov_norm = self._normalize_text(str(prov))
            if prov_norm in question_norm:
                return prov

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
        return text.translate(transtab).lower()

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
                    province_name.lower(), na=False
                )
            ].copy()

        # Lọc theo loại KCN/CCN dựa vào cột "Loại"
        if query_type and self.columns_map["type"] is not None:
            df_filtered = df_filtered[
                df_filtered[self.columns_map["type"]].astype(str).str.strip().str.upper() == query_type
            ]

        return df_filtered

    # ==========================================================
    # 🧾 TRẢ KẾT QUẢ DẠNG JSON
    # ==========================================================
    def format_json_response(self, df: pd.DataFrame, province_name: str, query_type: Optional[str]) -> str:
        """Trả kết quả truy vấn dạng JSON"""
        if df is None or df.empty:
            label = "khu" if query_type == "KCN" else "cụm" if query_type == "CCN" else "khu/cụm"
            return json.dumps({
                "province": province_name,
                "type": query_type,
                "count": 0,
                "message": f"Không tìm thấy {label} công nghiệp tại {province_name}.",
                "data": []
            }, ensure_ascii=False, indent=2)

        cols = self.columns_map
        records = []

        for _, row in df.iterrows():
            item = {
                "Tỉnh/Thành phố": str(row.get(cols["province"], "")),
                "Loại": str(row.get(cols["type"], "")),
                "Tên": str(row.get(cols["name"], "")),
                "Địa chỉ": str(row.get(cols["address"], "")),
                "Thời gian vận hành": str(row.get(cols["operation_time"], "")),
                "Tổng diện tích": str(row.get(cols["area"], "")),
                "Giá thuê đất": str(row.get(cols["rental_price"], "")),
                "Ngành nghề": str(row.get(cols["industry"], "")),
            }
            records.append(item)

        label = "khu" if query_type == "KCN" else "cụm" if query_type == "CCN" else "khu/cụm"
        response = {
            "province": province_name,
            "type": query_type,
            "count": len(df),
            "message": f"{province_name} có {len(df)} {label} công nghiệp.",
            "data": records
        }

        return json.dumps(response, ensure_ascii=False, indent=2)

    # ==========================================================
    # ⚙️ XỬ LÝ TRUY VẤN NGƯỜI DÙNG
    # ==========================================================
    def process_query(self, question: str, return_json: bool = True) -> Tuple[bool, Optional[str]]:
        """Xử lý truy vấn và trả kết quả (JSON mặc định)"""
        if not self.is_count_query(question):
            return False, None

        province = self.extract_province(question)
        if province is None:
            return False, json.dumps({"error": "❓ Bạn vui lòng nêu rõ tỉnh/thành phố cần tra cứu."}, ensure_ascii=False)

        query_type = self.detect_type(question)
        
        # Nếu không xác định được loại, yêu cầu làm rõ
        if query_type is None:
            return False, json.dumps({
                "error": "❓ Bạn muốn tra cứu KHU công nghiệp hay CỤM công nghiệp? Vui lòng nêu rõ."
            }, ensure_ascii=False)

        df_result = self.query_by_province(province, query_type)

        if return_json:
            return True, self.format_json_response(df_result, province, query_type)
        else:
            return True, self.format_table_response(df_result, province, query_type)

    # ==========================================================
    # 🧩 GIỮ LẠI HÀM CŨ (BẢNG TEXT)
    # ==========================================================
    def format_table_response(self, df: pd.DataFrame, province_name: str, query_type: Optional[str]) -> str:
        """(Tuỳ chọn) Hiển thị kết quả dạng bảng text"""
        if df is None or df.empty:
            label = "khu" if query_type == "KCN" else "cụm" if query_type == "CCN" else "khu/cụm"
            return f"Không tìm thấy {label} công nghiệp tại {province_name}."

        cols = self.columns_map
        label = "khu" if query_type == "KCN" else "cụm" if query_type == "CCN" else "khu/cụm"
        response = f"📊 {province_name} có {len(df)} {label} công nghiệp.\n\n"
        for _, row in df.iterrows():
            response += f"- {row.get(cols['name'], 'Không rõ')} ({row.get(cols['address'], '')})\n"
        return response


# ==========================================================
# 🔌 TÍCH HỢP VÀO CHATBOT
# ==========================================================
def integrate_excel_to_chatbot(excel_path: str):
    """Tích hợp module Excel vào chatbot"""
    if not Path(excel_path).exists():
        print(f"❌ Không tìm thấy file Excel: {excel_path}")
        return None
    handler = ExcelQueryHandler(excel_path)
    print("✅ Đã tích hợp module truy vấn Excel.")
    return handler


# ==========================================================
# 🧪 TEST MODULE
# ==========================================================
if __name__ == "__main__":
    EXCEL_FILE = r"./data/IIPMap_FULL_63_COMPLETE.xlsx"
    handler = ExcelQueryHandler(EXCEL_FILE)

    test_queries = [
        "Danh sách cụm công nghiệp ở Bắc Ninh"
    ]

    print("\n" + "=" * 80)
    print("TEST MODULE TRẢ KẾT QUẢ DẠNG JSON")
    print("=" * 80)

    for query in test_queries:
        print(f"\n❓ {query}")
        handled, response = handler.process_query(query, return_json=True)
        if handled:
            print(response)
        else:
            print("⏭️ Bỏ qua - Không phải câu hỏi liệt kê KCN/CCN hoặc thiếu thông tin")
        print("-" * 80)