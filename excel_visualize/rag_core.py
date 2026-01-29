# File: excel_visualize/rag_core.py
import os
import pandas as pd
import re
from typing import Dict, Any, List, Optional
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain.prompts import PromptTemplate
from langchain_core.output_parsers import JsonOutputParser

# Load environment variables
load_dotenv()
EXCEL_PATH = os.getenv("EXCEL_FILE_PATH")
OPENAI_API_KEY = os.getenv("OPENAI__API_KEY") 

class ExcelQueryAgent:
    def __init__(self):
        self.excel_path = EXCEL_PATH
        self.df = self._load_data()
        
        # --- GIA CỐ & CHUẨN HÓA DỮ LIỆU ---
        if not self.df.empty:
            # 1. Chuẩn hóa cột Loại
            if "Loại" in self.df.columns:
                self.df["Loại_norm"] = self.df["Loại"].astype(str).str.lower().str.strip()
            else:
                self.df["Loại_norm"] = "khu công nghiệp"

            # 2. Chuẩn hóa cột Tên
            if "Tên" in self.df.columns:
                self.df["Tên_norm"] = self.df["Tên"].astype(str).str.lower().str.strip()
            else:
                self.df["Tên_norm"] = ""

            # 3. Tính toán cột số liệu (Giá & Diện tích)
            if "Giá thuê đất" in self.df.columns:
                self.df["Price_num"] = self.df["Giá thuê đất"].apply(self._parse_price)
            else:
                self.df["Price_num"] = None

            if "Tổng diện tích" in self.df.columns:
                self.df["Area_num"] = self.df["Tổng diện tích"].apply(self._parse_area)
            else:
                self.df["Area_num"] = None
            
        try:
            self.llm = ChatOpenAI(
                model="gpt-3.5-turbo", 
                temperature=0, 
                api_key=OPENAI_API_KEY
            )
        except Exception as e:
            print(f"⚠️ Cannot initialize LLM for excel_visualize: {e}")
            self.llm = None
        
        if not self.df.empty and "Tỉnh/Thành phố" in self.df.columns:
            self.provinces_list = self.df["Tỉnh/Thành phố"].dropna().unique().tolist()
        else:
            self.provinces_list = []

    def _load_data(self) -> pd.DataFrame:
        if not self.excel_path or not os.path.exists(self.excel_path):
            if self.excel_path:
                alt_path = self.excel_path.replace(".xlsx", ".csv")
                if os.path.exists(alt_path): return pd.read_csv(alt_path)
            backup = "data/IIPMap_FULL_63_COMPLETE.xlsx - Sheet1.csv"
            if os.path.exists(backup): return pd.read_csv(backup)
            print(f"❌ Lỗi: Không tìm thấy file dữ liệu tại {self.excel_path}")
            return pd.DataFrame()

        try: return pd.read_excel(self.excel_path, sheet_name=0)
        except: return pd.read_csv(self.excel_path.replace(".xlsx", ".csv"))

    def _parse_price(self, value) -> Optional[float]:
        if pd.isna(value): return None
        s = str(value).lower().strip()
        for kw in ["usd/m²/năm", "usd/m2/năm", "usd", "/m2", "/năm", "m2"]:
            s = s.replace(kw, "")
        s = s.strip()
        if "-" in s:
            try:
                parts = s.split("-")
                return (float(parts[0]) + float(parts[1])) / 2
            except: return None
        try: return float(s)
        except: return None

    def _parse_area(self, value) -> Optional[float]:
        if pd.isna(value): return None
        s = str(value).lower().strip()
        s = s.replace("ha", "").replace("hecta", "").replace(",", ".").strip()
        try: return float(s)
        except: return None

    def retrieve_filters(self, user_query: str) -> Dict[str, Any]:
        """
        Phân tích câu hỏi: Xác định Loại biểu đồ (Giá/Diện tích/Dual) VÀ Dạng biểu đồ (Tròn/Đường/Cột).
        """
        if self.df.empty:
             return {"filter_type": "error", "message": "Chưa load được dữ liệu Excel."}

        # Fallback khi không có LLM
        if not self.llm:
            return self._retrieve_filters_fallback(user_query)

        parser = JsonOutputParser()
        provinces_str = ", ".join([str(p) for p in self.provinces_list])
        
        prompt_template = """
        Bạn là chuyên gia dữ liệu Bất động sản công nghiệp.
        
        DANH SÁCH TỈNH: [{provinces_list}]
        CÂU HỎI: "{query}"
        
        NHIỆM VỤ: Trích xuất JSON điều kiện lọc, DỮ LIỆU CẦN VẼ và DẠNG BIỂU ĐỒ.
        
        1. "target_type": Chọn MỘT trong ba giá trị sau:
           - "Khu công nghiệp": Nếu chỉ hỏi về KCN
           - "Cụm công nghiệp": Nếu chỉ hỏi về CCN  
           - "Cả hai": Nếu hỏi về cả KCN và CCN (ví dụ: "khu và cụm công nghiệp")
        
        2. "filter_type": 
           - "province": Nếu user hỏi về Tỉnh.
           - "specific_zones": Nếu hỏi về Tên KCN hoặc lọc theo số liệu.
        
        3. "search_keywords":
           - Tên Tỉnh (nếu filter_type=province).
           - Tên KCN cụ thể hoặc Thương hiệu (VSIP, Amata...).
             + Nếu có số hiệu (VSIP I): Giữ nguyên "VSIP I".
             + Nếu tên thương hiệu chung (VSIP): Giữ nguyên "VSIP".
        
        4. "visualization_metric" (DỮ LIỆU CẦN VẼ):
           - "price": Nếu user hỏi cụ thể về GIÁ, TIỀN, USD, THUÊ.
           - "area": Nếu user hỏi cụ thể về DIỆN TÍCH, RỘNG, QUY MÔ, HA.
           - "dual": Nếu user hỏi CHUNG CHUNG (VD: "vẽ biểu đồ KCN A", "thông tin KCN B", "so sánh KCN A và B") mà KHÔNG nhắc rõ giá hay diện tích. Hoặc nhắc đến CẢ HAI.
        
        5. "chart_type" (DẠNG BIỂU ĐỒ - MỚI):
           - "bar": Mặc định (nếu không nói gì), hoặc user nói "biểu đồ cột".
           - "barh": Nếu user nói "cột ngang", "thanh ngang".
           - "pie": Nếu user nói "biểu đồ tròn", "cơ cấu", "tỷ lệ", "bánh".
           - "line": Nếu user nói "biểu đồ đường", "xu hướng", "biến thiên".
        
        6. "numeric_filters":
           - "metric": "price" hoặc "area".
           - "operator": ">", "<", "=", ">=", "<=".
           - "value": Số thực.
        
        QUAN TRỌNG: CHỈ TRẢ VỀ JSON HỢP LỆ, KHÔNG CÓ MARKDOWN, KHÔNG CÓ TEXT THÊM.
        
        OUTPUT JSON:
        {{
            "target_type": "Khu công nghiệp",
            "filter_type": "province",
            "search_keywords": ["Hải Phòng"],
            "visualization_metric": "dual",
            "chart_type": "bar",
            "numeric_filters": []
        }}
        """

        prompt = PromptTemplate(
            template=prompt_template,
            input_variables=["query", "provinces_list"],
        )

        try:
            print(f"🔍 Analyzing query: {user_query}")
            chain = prompt | self.llm | parser
            llm_result = chain.invoke({"query": user_query, "provinces_list": provinces_str})
            
            target_type = llm_result.get("target_type", "Khu công nghiệp")
            filter_type = llm_result.get("filter_type", "specific_zones")
            
            # Logic: Mặc định là 'dual' nếu chung chung
            visualization_metric = llm_result.get("visualization_metric", "dual")
            
            # Logic: Mặc định là 'bar' nếu không nói rõ dạng biểu đồ
            chart_type = llm_result.get("chart_type", "bar")
            
            keywords = llm_result.get("search_keywords", [])
            numeric_filters = llm_result.get("numeric_filters", [])
            
            # --- LOGIC LỌC PYTHON ---
            
            # 1. Lọc Loại
            if target_type == "Cả hai":
                # Lấy cả KCN và CCN
                type_mask = (
                    self.df["Loại_norm"].str.contains("khu|kcn", na=False) |
                    self.df["Loại_norm"].str.contains("cụm|ccn", na=False)
                )
            elif "cụm" in target_type.lower():
                type_mask = self.df["Loại_norm"].str.contains("cụm|ccn", na=False)
            else:
                type_mask = self.df["Loại_norm"].str.contains("khu|kcn", na=False)
            df_filtered = self.df[type_mask].copy()

            # 2. Lọc Tên/Tỉnh
            if keywords:
                if filter_type == "province":
                    mask = df_filtered["Tỉnh/Thành phố"].astype(str).isin(keywords)
                    df_filtered = df_filtered[mask]
                
                elif filter_type == "specific_zones":
                    masks = []
                    for kw in keywords:
                        try:
                            if len(kw) >= 3: 
                                pattern = r"\b" + re.escape(kw.lower())
                                m = df_filtered["Tên_norm"].str.contains(kw.lower(), regex=False, na=False)
                            else:
                                m = df_filtered["Tên_norm"].str.contains(kw.lower(), regex=False, na=False)
                        except:
                            m = df_filtered["Tên_norm"].str.contains(kw.lower(), regex=False, na=False)
                        masks.append(m)
                    
                    if masks:
                        final_mask = pd.concat(masks, axis=1).any(axis=1)
                        df_filtered = df_filtered[final_mask]

            # 3. Lọc Số
            for f in numeric_filters:
                metric = f.get("metric")
                op = f.get("operator")
                val = f.get("value")
                
                col = None
                if metric == "price" and "Price_num" in df_filtered.columns:
                    col = "Price_num"
                elif metric == "area" and "Area_num" in df_filtered.columns:
                    col = "Area_num"
                
                if col:
                    if op == ">": df_filtered = df_filtered[df_filtered[col] > val]
                    elif op == "<": df_filtered = df_filtered[df_filtered[col] < val]
                    elif op == ">=": df_filtered = df_filtered[df_filtered[col] >= val]
                    elif op == "<=": df_filtered = df_filtered[df_filtered[col] <= val]
                    elif op == "=": df_filtered = df_filtered[df_filtered[col] == val]

            final_result = {
                "industrial_type": target_type,
                "filter_type": filter_type,
                "visualization_metric": visualization_metric, # Giá/Diện tích/Dual
                "chart_type": chart_type,                     # Bar/Line/Pie/Barh
                "data": df_filtered
            }
            return final_result

        except Exception as e:
            print(f"❌ Query Error: {e}")
            return {"filter_type": "error", "message": str(e)}

    def _retrieve_filters_fallback(self, user_query: str) -> Dict[str, Any]:
        """
        Fallback method khi không có LLM - sử dụng keyword matching
        """
        query_lower = user_query.lower()
        
        # 1. Xác định target_type
        if any(word in query_lower for word in ["khu và cụm", "kcn và ccn", "khu công nghiệp và cụm công nghiệp"]):
            target_type = "Cả hai"
            type_mask = (
                self.df["Loại_norm"].str.contains("khu|kcn", na=False) |
                self.df["Loại_norm"].str.contains("cụm|ccn", na=False)
            )
        elif any(word in query_lower for word in ["cụm", "ccn"]):
            target_type = "Cụm công nghiệp"
            type_mask = self.df["Loại_norm"].str.contains("cụm|ccn", na=False)
        else:
            target_type = "Khu công nghiệp"
            type_mask = self.df["Loại_norm"].str.contains("khu|kcn", na=False)
        
        df_filtered = self.df[type_mask].copy()
        
        # 2. Xác định visualization_metric
        if any(word in query_lower for word in ["giá", "tiền", "usd", "thuê"]):
            visualization_metric = "price"
        elif any(word in query_lower for word in ["diện tích", "rộng", "quy mô", "ha"]):
            visualization_metric = "area"
        else:
            visualization_metric = "dual"
        
        # 3. Xác định chart_type
        if any(word in query_lower for word in ["tròn", "cơ cấu", "tỷ lệ", "bánh"]):
            chart_type = "pie"
        elif any(word in query_lower for word in ["đường", "xu hướng", "biến thiên"]):
            chart_type = "line"
        elif any(word in query_lower for word in ["ngang", "thanh ngang"]):
            chart_type = "barh"
        else:
            chart_type = "bar"
        
        # 4. Tìm tỉnh trong query
        found_province = None
        for province in self.provinces_list:
            if province.lower() in query_lower:
                found_province = province
                break
        
        # 5. Lọc theo tỉnh nếu tìm thấy
        if found_province:
            mask = df_filtered["Tỉnh/Thành phố"].astype(str) == found_province
            df_filtered = df_filtered[mask]
            filter_type = "province"
            search_keywords = [found_province]
        else:
            # Không tìm thấy tỉnh cụ thể, lấy tất cả
            filter_type = "specific_zones"
            search_keywords = []
        
        return {
            "industrial_type": target_type,
            "filter_type": filter_type,
            "visualization_metric": visualization_metric,
            "chart_type": chart_type,
            "data": df_filtered
        }

# Export
rag_agent = ExcelQueryAgent()