"""
KCN Detail Query Module - Tra cứu thông tin chi tiết KCN/CCN cụ thể
Sử dụng RAG để trả lời thông minh về một KCN/CCN được chỉ định
Kết hợp structured data (Excel/GeoJSON) với RAG system để trả lời đầy đủ
"""

import pandas as pd
import json
import re
from typing import Dict, List, Optional, Tuple, Any
from pathlib import Path

# RapidFuzz (khuyến nghị). Nếu không có sẽ dùng fallback match cơ bản.
try:
    from rapidfuzz import fuzz, process
    HAS_RAPIDFUZZ = True
except ImportError:
    HAS_RAPIDFUZZ = False
    fuzz = None
    process = None

class KCNDetailQueryHandler:
    def __init__(self, excel_path: str, geojson_path: str, match_threshold: int = 60, llm=None, embedding=None):
        """
        Khởi tạo handler tra cứu chi tiết KCN/CCN với RAG
        
        Args:
            excel_path: Đường dẫn file Excel chứa thông tin KCN/CCN
            geojson_path: Đường dẫn file GeoJSON chứa tọa độ
            match_threshold: Ngưỡng matching tên (default 60%)
            llm: Language model cho RAG
            embedding: Embedding model cho RAG
        """
        self.excel_path = excel_path
        self.geojson_path = geojson_path
        self.match_threshold = match_threshold
        self.llm = llm
        self.embedding = embedding
        
        # Load data
        self.df = self._load_excel()
        self.geojson_data = self._load_geojson()
        
        # Tạo index cho tìm kiếm nhanh
        self._create_search_index()
    
    def _load_excel(self) -> pd.DataFrame:
        """Load Excel data"""
        try:
            df = pd.read_excel(self.excel_path)
            print(f"✅ Loaded Excel: {len(df)} records")
            return df
        except Exception as e:
            print(f"❌ Error loading Excel: {e}")
            return pd.DataFrame()
    
    def _load_geojson(self) -> Dict:
        """Load GeoJSON data"""
        try:
            with open(self.geojson_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            print(f"✅ Loaded GeoJSON: {len(data['features'])} features")
            return data
        except Exception as e:
            print(f"❌ Error loading GeoJSON: {e}")
            return {"type": "FeatureCollection", "features": []}
    
    def _create_search_index(self):
        """Tạo index để tìm kiếm nhanh"""
        # Index cho Excel
        self.excel_names = []
        self.excel_index = {}
        
        if not self.df.empty and 'Tên' in self.df.columns:
            for idx, row in self.df.iterrows():
                name = str(row['Tên']).strip()
                if name and name != 'nan':
                    self.excel_names.append(name)
                    self.excel_index[name] = idx
        
        # Index cho GeoJSON
        self.geojson_names = []
        self.geojson_index = {}
        
        for idx, feature in enumerate(self.geojson_data.get('features', [])):
            name = feature.get('properties', {}).get('name', '').strip()
            if name:
                self.geojson_names.append(name)
                self.geojson_index[name] = idx
        
        print(f"🔍 Search index created: {len(self.excel_names)} Excel names, {len(self.geojson_names)} GeoJSON names")
    
    def _normalize_name(self, name: str) -> str:
        """Chuẩn hóa tên để so sánh"""
        if not name:
            return ""
        
        # Loại bỏ dấu, chuyển thường, loại bỏ ký tự đặc biệt
        import unicodedata
        normalized = unicodedata.normalize('NFD', str(name))
        no_accents = ''.join(c for c in normalized if unicodedata.category(c) != 'Mn')
        
        # Chỉ giữ chữ cái, số và khoảng trắng
        clean = re.sub(r'[^a-zA-Z0-9\s]', ' ', no_accents)
        clean = re.sub(r'\s+', ' ', clean).strip().lower()
        
        return clean
    
    def find_kcn_by_name(self, query_name: str) -> Optional[Dict]:
        """
        Tìm KCN/CCN theo tên với fuzzy matching
        
        Returns:
            {
                "excel_data": {...},  # Thông tin từ Excel
                "coordinates": [lng, lat],  # Tọa độ từ GeoJSON
                "match_score": 85,  # Điểm matching
                "matched_name": "Tên chính xác"
            }
        """
        if not query_name or not query_name.strip():
            return None
        
        query_normalized = self._normalize_name(query_name)
        
        # 1. Tìm trong Excel trước
        excel_match = self._find_best_match(query_name, self.excel_names)
        
        if not excel_match or excel_match['score'] < self.match_threshold:
            return None
        
        # 2. Lấy thông tin từ Excel
        excel_name = excel_match['match']
        excel_idx = self.excel_index[excel_name]
        excel_row = self.df.iloc[excel_idx]
        
        excel_data = {
            "Tên": excel_row.get('Tên', ''),
            "Địa chỉ": excel_row.get('Địa chỉ', ''),
            "Tỉnh/Thành phố": excel_row.get('Tỉnh/Thành phố', ''),
            "Loại": excel_row.get('Loại', ''),
            "Tổng diện tích": excel_row.get('Tổng diện tích', ''),
            "Giá thuê đất": excel_row.get('Giá thuê đất', ''),
            "Thời gian vận hành": excel_row.get('Thời gian vận hành', ''),
            "Ngành nghề": excel_row.get('Ngành nghề', ''),
            "Hệ thống cấp điện": excel_row.get('Hệ thống cấp điện', ''),
            "Hệ thống cấp nước": excel_row.get('Hệ thống cấp nước', ''),
            "Hệ thống xử lý nước thải": excel_row.get('Hệ thống xử lý nước thải', ''),
            "Ưu đãi": excel_row.get('Ưu đãi', ''),
            "Liên hệ": excel_row.get('Liên hệ', ''),
            "URL": excel_row.get('URL', '')
        }
        
        # 3. Tìm tọa độ trong GeoJSON
        coordinates = self._find_coordinates_for_name(excel_name)
        
        return {
            "excel_data": excel_data,
            "coordinates": coordinates,
            "match_score": excel_match['score'],
            "matched_name": excel_name,
            "query_name": query_name
        }
    
    def _find_best_match(self, query: str, name_list: List[str]) -> Optional[Dict]:
        """Tìm match tốt nhất sử dụng fuzzy matching"""
        if not name_list:
            return None
        
        if HAS_RAPIDFUZZ:
            # Sử dụng rapidfuzz để tìm match tốt nhất
            result = process.extractOne(
                query, 
                name_list, 
                scorer=fuzz.WRatio,
                score_cutoff=self.match_threshold
            )
            
            if result:
                return {
                    "match": result[0],
                    "score": result[1]
                }
        else:
            # Fallback: improved string matching
            query_lower = query.lower()
            query_normalized = self._normalize_name(query)
            best_match = None
            best_score = 0
            
            for name in name_list:
                name_lower = name.lower()
                name_normalized = self._normalize_name(name)
                
                # Exact match
                if query_normalized == name_normalized:
                    return {"match": name, "score": 100}
                
                # Contains match
                if query_normalized in name_normalized or name_normalized in query_normalized:
                    score = 90
                    if score > best_score and score >= self.match_threshold:
                        best_match = name
                        best_score = score
                
                # Word match - improved logic
                query_words = set(query_normalized.split())
                name_words = set(name_normalized.split())
                common_words = query_words.intersection(name_words)
                
                if common_words:
                    # Tính điểm dựa trên số từ chung và độ dài
                    word_score = (len(common_words) / max(len(query_words), len(name_words))) * 100
                    
                    # Bonus nếu có từ khóa quan trọng
                    important_words = {'vsip', 'becamex', 'long', 'thanh', 'phu', 'binh', 'cao', 'nghiep'}
                    important_matches = common_words.intersection(important_words)
                    if important_matches:
                        word_score += len(important_matches) * 10
                    
                    # Giới hạn điểm tối đa
                    word_score = min(word_score, 95)
                    
                    if word_score > best_score and word_score >= self.match_threshold:
                        best_match = name
                        best_score = word_score
                
                # Partial substring match cho các tên dài
                if len(query_normalized) >= 4:
                    for word in query_words:
                        if len(word) >= 4 and word in name_normalized:
                            score = 70 + (len(word) * 2)  # Từ dài hơn = điểm cao hơn
                            if score > best_score and score >= self.match_threshold:
                                best_match = name
                                best_score = score
            
            if best_match:
                return {"match": best_match, "score": int(best_score)}
        
        return None
    
    def _find_coordinates_for_name(self, name: str) -> Optional[List[float]]:
        """Tìm tọa độ cho tên KCN/CCN"""
        # Thử exact match trước
        if name in self.geojson_index:
            feature = self.geojson_data['features'][self.geojson_index[name]]
            coords = feature.get('geometry', {}).get('coordinates', [])
            if len(coords) == 2:
                return coords
        
        # Thử fuzzy match
        geojson_match = self._find_best_match(name, self.geojson_names)
        if geojson_match and geojson_match['score'] >= self.match_threshold:
            matched_name = geojson_match['match']
            feature = self.geojson_data['features'][self.geojson_index[matched_name]]
            coords = feature.get('geometry', {}).get('coordinates', [])
            if len(coords) == 2:
                return coords
        
        return None
    
    def is_kcn_detail_query(self, question: str) -> bool:
        """
        Kiểm tra xem câu hỏi có phải là tra cứu chi tiết KCN/CCN không
        
        Patterns:
        - "thông tin về KHU CÔNG NGHIỆP ABC" (có tên cụ thể)
        - "cho tôi biết về CCN XYZ" (có tên cụ thể)
        - "KCN ABC ở đâu" (có tên cụ thể)
        - "tìm hiểu KCN ABC" (có tên cụ thể)
        
        KHÔNG PHẢI:
        - "cho tôi các khu công nghiệp ở Thanh Hóa" (query tổng quát theo tỉnh)
        - "danh sách KCN ở Bắc Ninh" (query danh sách)
        """
        question_lower = question.lower()
        
        # Loại trừ các query tổng quát trước
        general_keywords = [
            'các khu công nghiệp', 'danh sách', 'tất cả', 'những khu công nghiệp',
            'khu công nghiệp nào', 'có bao nhiêu', 'số lượng', 'liệt kê'
        ]
        
        # Nếu có từ khóa tổng quát, không phải detail query
        if any(keyword in question_lower for keyword in general_keywords):
            return False
        
        # Keywords chỉ tra cứu chi tiết
        detail_keywords = [
            'thông tin về', 'cho tôi biết về', 'tìm hiểu về', 'giới thiệu về',
            'chi tiết về', 'mô tả về', 'ở đâu', 'nằm ở đâu', 'vị trí',
            'địa chỉ của', 'liên hệ', 'contact'
        ]
        
        # Keywords KCN/CCN
        kcn_keywords = [
            'khu công nghiệp', 'kcn', 'cụm công nghiệp', 'ccn',
            'khu cn', 'cụm cn', 'industrial zone', 'industrial park'
        ]
        
        # Kiểm tra có keyword detail và KCN
        has_detail_keyword = any(keyword in question_lower for keyword in detail_keywords)
        has_kcn_keyword = any(keyword in question_lower for keyword in kcn_keywords)
        
        # Kiểm tra có tên KCN cụ thể (không chỉ là từ khóa chung)
        # Pattern: "KHU CÔNG NGHIỆP" + tên cụ thể (không phải chỉ tỉnh)
        specific_kcn_patterns = [
            r'khu công nghiệp\s+[a-zA-ZÀ-ỹ]+(?:\s+[a-zA-ZÀ-ỹ\-]+)*(?:\s*-\s*[a-zA-ZÀ-ỹ\s]+)?',
            r'kcn\s+[a-zA-ZÀ-ỹ]+(?:\s+[a-zA-ZÀ-ỹ\-]+)*',
            r'ccn\s+[a-zA-ZÀ-ỹ]+(?:\s+[a-zA-ZÀ-ỹ\-]+)*'
        ]
        
        has_specific_name = False
        for pattern in specific_kcn_patterns:
            matches = re.findall(pattern, question_lower)
            if matches:
                # Kiểm tra xem có phải chỉ là tên tỉnh không
                for match in matches:
                    # Loại trừ nếu chỉ là "khu công nghiệp ở [tỉnh]"
                    if not re.search(r'\s+ở\s+', match) and len(match.split()) >= 3:
                        has_specific_name = True
                        break
        
        # Trường hợp đặc biệt: "KCN ABC ở đâu" - có tên cụ thể + "ở đâu"
        location_question_pattern = r'(khu công nghiệp|kcn|ccn)\s+[a-zA-ZÀ-ỹ]+(?:\s+[a-zA-ZÀ-ỹ\-]+)*\s+ở\s+đâu'
        if re.search(location_question_pattern, question_lower):
            has_specific_name = True
            has_detail_keyword = True
        
        return (has_detail_keyword and has_kcn_keyword and has_specific_name) or \
               (has_specific_name and not any(keyword in question_lower for keyword in general_keywords))
    
    def extract_kcn_name_from_query(self, question: str) -> Optional[str]:
        """
        Trích xuất tên KCN/CCN từ câu hỏi
        
        Examples:
        - "thông tin về KHU CÔNG NGHIỆP PHÚ LONG - NINH BÌNH" -> "KHU CÔNG NGHIỆP PHÚ LONG - NINH BÌNH"
        - "cho tôi biết về CCN TÂN THÀNH" -> "CCN TÂN THÀNH"
        """
        # Pattern 1: "về [tên KCN]"
        match = re.search(r'về\s+(.+?)(?:\s*$|\s*\?)', question, re.IGNORECASE)
        if match:
            return match.group(1).strip()
        
        # Pattern 2: Tìm tên có chứa KCN/CCN keywords
        kcn_patterns = [
            r'(khu công nghiệp[\w\s\-]+?)(?:\s*$|\s*\?|ở|tại)',
            r'(kcn[\w\s\-]+?)(?:\s*$|\s*\?|ở|tại)',
            r'(cụm công nghiệp[\w\s\-]+?)(?:\s*$|\s*\?|ở|tại)',
            r'(ccn[\w\s\-]+?)(?:\s*$|\s*\?|ở|tại)'
        ]
        
        for pattern in kcn_patterns:
            match = re.search(pattern, question, re.IGNORECASE)
            if match:
                return match.group(1).strip()
        
        return None
    
    def _enhance_with_rag(self, kcn_info: Dict, question: str) -> str:
        """
        Sử dụng RAG để bổ sung thông tin chi tiết về KCN
        
        Args:
            kcn_info: Thông tin structured từ Excel
            question: Câu hỏi gốc của user
            
        Returns:
            Enhanced description từ RAG system
        """
        if not self.llm:
            return ""
        
        try:
            # Tạo context từ structured data
            kcn_name = kcn_info.get('Tên', 'N/A')
            kcn_address = kcn_info.get('Địa chỉ', 'N/A')
            kcn_province = kcn_info.get('Tỉnh/Thành phố', 'N/A')
            kcn_area = kcn_info.get('Tổng diện tích', 'N/A')
            kcn_industries = kcn_info.get('Ngành nghề', 'N/A')
            
            # Tạo enhanced query cho RAG
            rag_query = f"""
            Hãy cung cấp thông tin chi tiết và phân tích về {kcn_name} tại {kcn_province}.
            
            Thông tin cơ bản đã có:
            - Tên: {kcn_name}
            - Địa chỉ: {kcn_address}
            - Tỉnh/Thành phố: {kcn_province}
            - Diện tích: {kcn_area}
            - Ngành nghề: {kcn_industries[:200]}...
            
            Câu hỏi gốc: {question}
            
            Hãy bổ sung thêm:
            1. Phân tích vị trí địa lý và lợi thế
            2. Đánh giá tiềm năng phát triển
            3. So sánh với các KCN khác trong khu vực
            4. Thông tin về hạ tầng và dịch vụ
            5. Các chính sách ưu đãi đặc biệt
            
            Trả lời một cách chi tiết và chuyên nghiệp.
            """
            
            # Gọi RAG system (giả sử có method invoke)
            if hasattr(self.llm, 'invoke'):
                rag_response = self.llm.invoke(rag_query)
                if isinstance(rag_response, str):
                    return rag_response
                elif hasattr(rag_response, 'content'):
                    return rag_response.content
                else:
                    return str(rag_response)
            
            return ""
            
        except Exception as e:
            print(f"⚠️ RAG enhancement error: {e}")
            return ""
    
    def process_kcn_detail_query(self, question: str) -> Optional[Dict]:
        """
        Xử lý câu hỏi tra cứu chi tiết KCN/CCN với RAG enhancement
        
        Returns:
            {
                "type": "kcn_detail",
                "kcn_info": {...},
                "coordinates": [lng, lat],
                "zoom_level": 16,
                "rag_analysis": "Enhanced analysis from RAG",
                "message": "Thông tin chi tiết về KCN ABC"
            }
        """
        if not self.is_kcn_detail_query(question):
            return None
        
        # Trích xuất tên KCN
        kcn_name = self.extract_kcn_name_from_query(question)
        if not kcn_name:
            return None
        
        # Tìm thông tin KCN từ structured data
        kcn_result = self.find_kcn_by_name(kcn_name)
        if not kcn_result:
            return {
                "type": "kcn_detail_not_found",
                "message": f"Không tìm thấy thông tin về '{kcn_name}'. Vui lòng kiểm tra lại tên hoặc thử tìm kiếm với từ khóa khác.",
                "query_name": kcn_name
            }
        
        # Enhance với RAG
        rag_analysis = self._enhance_with_rag(kcn_result["excel_data"], question)
        
        result = {
            "type": "kcn_detail",
            "kcn_info": kcn_result["excel_data"],
            "coordinates": kcn_result["coordinates"],
            "zoom_level": 16,  # Zoom rất gần để thấy chi tiết vị trí
            "match_score": kcn_result["match_score"],
            "matched_name": kcn_result["matched_name"],
            "query_name": kcn_name,
            "message": f"Thông tin chi tiết về {kcn_result['matched_name']}"
        }
        
        # Thêm RAG analysis nếu có
        if rag_analysis:
            result["rag_analysis"] = rag_analysis
            result["has_rag"] = True
        else:
            result["has_rag"] = False
        
        return result

# Global instance
kcn_detail_handler = None

def get_kcn_detail_handler(llm=None, embedding=None):
    """Lazy load KCN detail handler với RAG support"""
    global kcn_detail_handler
    if kcn_detail_handler is None:
        from pathlib import Path
        BASE_DIR = Path(__file__).resolve().parent
        EXCEL_FILE_PATH = str(BASE_DIR / "data" / "IIPMap_FULL_63_COMPLETE.xlsx")
        GEOJSON_IZ_PATH = str(BASE_DIR / "map_ui" / "industrial_zones.geojson")
        
        kcn_detail_handler = KCNDetailQueryHandler(
            excel_path=EXCEL_FILE_PATH,
            geojson_path=GEOJSON_IZ_PATH,
            llm=llm,
            embedding=embedding
        )
    return kcn_detail_handler

def process_kcn_detail_query(question: str, llm=None, embedding=None) -> Optional[Dict]:
    """Hàm tiện ích để xử lý câu hỏi tra cứu KCN chi tiết với RAG"""
    handler = get_kcn_detail_handler(llm=llm, embedding=embedding)
    return handler.process_kcn_detail_query(question)

if __name__ == "__main__":
    # Test
    handler = get_kcn_detail_handler()
    
    test_queries = [
        "thông tin về KHU CÔNG NGHIỆP PHÚ LONG - NINH BÌNH",
        "cho tôi biết về KCN CÁI LÂN",
        "CCN TÂN THÀNH ở đâu",
        "tìm hiểu KCN BECAMEX VSIP BÌNH ĐỊNH"
    ]
    
    for query in test_queries:
        print(f"\n🔍 Query: {query}")
        result = handler.process_kcn_detail_query(query)
        if result:
            print(f"✅ Type: {result['type']}")
            if result['type'] == 'kcn_detail':
                print(f"📍 Coordinates: {result['coordinates']}")
                print(f"🎯 Zoom: {result['zoom_level']}")
                print(f"📊 Match score: {result['match_score']}")
        else:
            print("❌ No match")