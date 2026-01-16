# File: excel_visualize/rag_core.py
import os
import pandas as pd
from typing import Dict, Any, List
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
        
        # --- GIA CỐ PHẦN KHỞI TẠO CỘT ---
        # Đảm bảo các cột chuẩn hóa luôn tồn tại để tránh KeyError sau này
        if not self.df.empty:
            # 1. Chuẩn hóa cột Loại (Nếu không có thì tạo mặc định là rỗng)
            if "Loại" in self.df.columns:
                self.df["Loại_norm"] = self.df["Loại"].astype(str).str.lower().str.strip()
            else:
                print(" Cảnh báo: File Excel thiếu cột 'Loại'. Mặc định coi tất cả là Khu công nghiệp.")
                self.df["Loại_norm"] = "khu công nghiệp" # Giá trị fallback

            # 2. Chuẩn hóa cột Tên (Nếu không có cột Tên thì lỗi luôn vì đây là cột bắt buộc)
            if "Tên" in self.df.columns:
                self.df["Tên_norm"] = self.df["Tên"].astype(str).str.lower().str.strip()
            else:
                self.df["Tên_norm"] = ""
            
        self.llm = ChatOpenAI(
            model="gpt-3.5-turbo", 
            temperature=0, 
            api_key=OPENAI_API_KEY
        )
        
        # Safely get provinces list
        if not self.df.empty and "Tỉnh/Thành phố" in self.df.columns:
            self.provinces_list = self.df["Tỉnh/Thành phố"].dropna().unique().tolist()
        else:
            self.provinces_list = []

    def _load_data(self) -> pd.DataFrame:
        """Đọc dữ liệu an toàn"""
        if not self.excel_path or not os.path.exists(self.excel_path):
            # Fallback logic
            if self.excel_path:
                alt_path = self.excel_path.replace(".xlsx", ".csv")
                if os.path.exists(alt_path): return pd.read_csv(alt_path)
            
            backup = "data/IIPMap_FULL_63_COMPLETE.xlsx - Sheet1.csv"
            if os.path.exists(backup): return pd.read_csv(backup)
            
            print(f"❌ Lỗi: Không tìm thấy file dữ liệu tại {self.excel_path}")
            return pd.DataFrame() # Trả về DF rỗng thay vì crash

        try: 
            return pd.read_excel(self.excel_path, sheet_name=0)
        except: 
            return pd.read_csv(self.excel_path.replace(".xlsx", ".csv"))

    def retrieve_filters(self, user_query: str) -> Dict[str, Any]:
        """
        Phân tích câu hỏi để lấy filters
        """
        if self.df.empty:
             return {"filter_type": "error", "message": "Chưa load được dữ liệu Excel."}

        parser = JsonOutputParser()
        provinces_str = ", ".join([str(p) for p in self.provinces_list])
        
        prompt_template = """
        Bạn là trợ lý dữ liệu.
        
        DANH SÁCH TỈNH: [{provinces_list}]
        
        CÂU HỎI: "{query}"
        
        NHIỆM VỤ:
        Phân tích câu hỏi và trả về JSON để lọc dữ liệu Excel.
        
        Quy tắc xác định "target_type" (Loại hình):
        - Nếu user nhắc đến "Cụm", "CCN", "Cụm công nghiệp" -> "Cụm công nghiệp"
        - Nếu user nhắc đến "Khu", "KCN", "Khu công nghiệp" hoặc KHÔNG nói gì cụ thể -> "Khu công nghiệp" (Mặc định).
        
        Quy tắc xác định "filter_type" (Phạm vi):
        1. Type "province": User hỏi về Tỉnh (VD: "Giá đất tại Hà Nam", "Các cụm ở Bắc Ninh").
           -> "keywords": ["Tên tỉnh chuẩn xác"].
        2. Type "specific_zones": User nhắc tên riêng (VD: "KCN Vsip", "So sánh Đồng Văn và Hòa Mạc").
           -> "keywords": ["Tên riêng 1", "Tên riêng 2"]. (Lưu ý: Chỉ lấy tên riêng, bỏ chữ 'Khu công nghiệp', bỏ tên tỉnh phía sau. VD: "KCN Vsip Bắc Ninh" -> chỉ lấy "Vsip").
           
        OUTPUT JSON:
        {{
            "target_type": "Khu công nghiệp" hoặc "Cụm công nghiệp",
            "filter_type": "province" hoặc "specific_zones",
            "search_keywords": ["Keyword1", "Keyword2"]
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
            filter_type = llm_result.get("filter_type", "error")
            keywords = llm_result.get("search_keywords", [])
            
            # --- LOGIC LỌC PYTHON ---
            
            # 1. Lọc theo Loại hình
            # Sử dụng cột Loại_norm đã được đảm bảo tồn tại ở __init__
            if "cụm" in target_type.lower():
                type_mask = self.df["Loại_norm"].str.contains("cụm|ccn", na=False)
            else:
                type_mask = self.df["Loại_norm"].str.contains("khu|kcn", na=False)
            
            df_by_type = self.df[type_mask].copy()

            final_result = {
                "industrial_type": target_type,
                "filter_type": filter_type,
                "data": pd.DataFrame()
            }

            # 2. Lọc chi tiết
            if filter_type == "province":
                # Lọc theo danh sách tỉnh
                mask = df_by_type["Tỉnh/Thành phố"].astype(str).isin(keywords)
                final_result["data"] = df_by_type[mask]
                
            elif filter_type == "specific_zones":
                # Lọc theo tên chứa từ khóa
                masks = []
                for kw in keywords:
                    # GIA CỐ: Thêm regex=False để tránh lỗi nếu tên có dấu ngoặc ()
                    m = df_by_type["Tên_norm"].str.contains(kw.lower(), regex=False, na=False)
                    masks.append(m)
                
                if masks:
                    final_mask = pd.concat(masks, axis=1).any(axis=1)
                    final_result["data"] = df_by_type[final_mask]
            
            return final_result

        except Exception as e:
            print(f"❌ Query Error: {e}")
            return {"filter_type": "error", "message": str(e)}

# Export
rag_agent = ExcelQueryAgent()