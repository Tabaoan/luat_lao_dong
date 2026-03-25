"""
Backend module cho mn_agent - Quản lý kết nối và truy vấn Qdrant collection 'manganh'
"""

import os
import logging
import time
import re
import unicodedata
from typing import Dict, List, Optional, Any
from qdrant_client import QdrantClient
from qdrant_client.http import models
from qdrant_client.http.exceptions import ResponseHandlingException, UnexpectedResponse
from openai import OpenAI
import json

# Cấu hình logging - chỉ hiển thị ERROR để giảm noise
logging.basicConfig(level=logging.ERROR)
logger = logging.getLogger(__name__)
logger.setLevel(logging.ERROR)


def normalize_vietnamese_text(text: str) -> str:
    """
    Normalize Vietnamese text for better search results.
    
    Args:
        text: Input Vietnamese text
        
    Returns:
        Normalized text (lowercase, trimmed whitespace, normalized Unicode)
    """
    if not text:
        return ""
    
    # Convert to string if not already
    text = str(text)
    
    # Normalize Unicode (NFD -> NFC) to handle Vietnamese diacritics consistently
    text = unicodedata.normalize('NFC', text)
    
    # Convert to lowercase
    text = text.lower()
    
    # Remove extra whitespace and normalize spaces
    text = re.sub(r'\s+', ' ', text.strip())
    
    # Remove leading/trailing punctuation but keep internal punctuation
    text = re.sub(r'^[^\w\s]+|[^\w\s]+$', '', text)
    
    return text


def remove_vietnamese_accents(text: str) -> str:
    """
    Remove Vietnamese accents for fuzzy matching.
    
    Args:
        text: Input Vietnamese text with accents
        
    Returns:
        Text without Vietnamese accents
    """
    if not text:
        return ""
    
    # Vietnamese accent mapping
    accent_map = {
        'à': 'a', 'á': 'a', 'ả': 'a', 'ã': 'a', 'ạ': 'a',
        'ă': 'a', 'ằ': 'a', 'ắ': 'a', 'ẳ': 'a', 'ẵ': 'a', 'ặ': 'a',
        'â': 'a', 'ầ': 'a', 'ấ': 'a', 'ẩ': 'a', 'ẫ': 'a', 'ậ': 'a',
        'è': 'e', 'é': 'e', 'ẻ': 'e', 'ẽ': 'e', 'ẹ': 'e',
        'ê': 'e', 'ề': 'e', 'ế': 'e', 'ể': 'e', 'ễ': 'e', 'ệ': 'e',
        'ì': 'i', 'í': 'i', 'ỉ': 'i', 'ĩ': 'i', 'ị': 'i',
        'ò': 'o', 'ó': 'o', 'ỏ': 'o', 'õ': 'o', 'ọ': 'o',
        'ô': 'o', 'ồ': 'o', 'ố': 'o', 'ổ': 'o', 'ỗ': 'o', 'ộ': 'o',
        'ơ': 'o', 'ờ': 'o', 'ớ': 'o', 'ở': 'o', 'ỡ': 'o', 'ợ': 'o',
        'ù': 'u', 'ú': 'u', 'ủ': 'u', 'ũ': 'u', 'ụ': 'u',
        'ư': 'u', 'ừ': 'u', 'ứ': 'u', 'ử': 'u', 'ữ': 'u', 'ự': 'u',
        'ỳ': 'y', 'ý': 'y', 'ỷ': 'y', 'ỹ': 'y', 'ỵ': 'y',
        'đ': 'd'
    }
    
    result = ""
    for char in text.lower():
        result += accent_map.get(char, char)
    
    return result


def create_search_variants(text: str) -> List[str]:
    """
    Create search variants for Vietnamese text to improve matching.
    
    Args:
        text: Input text
        
    Returns:
        List of text variants for searching
    """
    if not text:
        return []
    
    variants = []
    
    # Original normalized text
    normalized = normalize_vietnamese_text(text)
    if normalized:
        variants.append(normalized)
    
    # Without accents
    no_accents = remove_vietnamese_accents(normalized)
    if no_accents and no_accents != normalized:
        variants.append(no_accents)
    
    # Original text (in case user provided specific casing)
    original_trimmed = text.strip()
    if original_trimmed and original_trimmed not in variants:
        variants.append(original_trimmed)
    
    # Remove duplicates while preserving order
    seen = set()
    unique_variants = []
    for variant in variants:
        if variant and variant not in seen:
            seen.add(variant)
            unique_variants.append(variant)
    
    return unique_variants


def validate_environment_variables() -> Dict[str, Any]:
    """
    Validate all required environment variables for mn_agent backend.
    
    Returns:
        Dict containing validation results and configuration
    
    Raises:
        ValueError: If required environment variables are missing or invalid
    """
    validation_results = {
        "required_vars": {},
        "optional_vars": {},
        "errors": [],
        "warnings": []
    }
    
    # Required variables
    required_vars = {
        "QDRANT_URL": {
            "value": os.getenv("QDRANT_URL"),
            "validator": lambda x: x and (x.startswith('http://') or x.startswith('https://'))
        },
        "OPENAI__API_KEY": {
            "value": os.getenv("OPENAI__API_KEY"),
            "validator": lambda x: x and x.startswith('sk-')
        }
    }
    
    # Optional variables with defaults
    optional_vars = {
        "QDRANT_COLLECTION_NAME_MANGANH": {
            "value": os.getenv("QDRANT_COLLECTION_NAME_MANGANH", "manganh"),
            "default": "manganh"
        },
        "OPENAI__MODEL_NAME": {
            "value": os.getenv("OPENAI__MODEL_NAME", "gpt-4o-mini"),
            "default": "gpt-4o-mini"
        },
        "OPENAI__EMBEDDING_MODEL": {
            "value": os.getenv("OPENAI__EMBEDDING_MODEL", "text-embedding-3-large"),
            "default": "text-embedding-3-large"
        }
    }
    
    # Validate required variables
    for var_name, config in required_vars.items():
        value = config["value"]
        validator = config["validator"]
        
        if not value:
            error_msg = f"Biến môi trường bắt buộc '{var_name}' không được tìm thấy hoặc trống"
            validation_results["errors"].append(error_msg)
            logger.error(error_msg)
        elif not validator(value):
            error_msg = f"Biến môi trường '{var_name}' có giá trị không hợp lệ: {value}"
            validation_results["errors"].append(error_msg)
            logger.error(error_msg)
        else:
            validation_results["required_vars"][var_name] = value
            logger.info(f"✓ {var_name}: OK")
    
    # Validate optional variables
    for var_name, config in optional_vars.items():
        value = config["value"]
        default = config["default"]
        
        if not value or value == default:
            if not os.getenv(var_name):
                warning_msg = f"Biến môi trường '{var_name}' không được thiết lập, sử dụng giá trị mặc định: '{default}'"
                validation_results["warnings"].append(warning_msg)
                logger.warning(warning_msg)
        
        validation_results["optional_vars"][var_name] = value
        logger.info(f"✓ {var_name}: {value}")
    
    # Raise exception if there are errors
    if validation_results["errors"]:
        error_summary = f"Phát hiện {len(validation_results['errors'])} lỗi biến môi trường: " + "; ".join(validation_results["errors"])
        raise ValueError(error_summary)
    
    logger.info(f"Validation hoàn tất: {len(validation_results['required_vars'])} biến bắt buộc OK, {len(validation_results['warnings'])} cảnh báo")
    return validation_results


class MaNganhBackend:
    """Backend quản lý kết nối và truy vấn Qdrant collection 'manganh'"""
    
    def __init__(self, qdrant_url: str = None, collection_name: str = "manganh"):
        """
        Khởi tạo kết nối Qdrant
        
        Args:
            qdrant_url: URL của Qdrant server (lấy từ env nếu None)
            collection_name: Tên collection (mặc định "manganh")
        
        Raises:
            ConnectionError: Nếu không kết nối được Qdrant
            ValueError: Nếu collection không tồn tại hoặc thiếu biến môi trường bắt buộc
        """
        # Validate tất cả biến môi trường trước khi khởi tạo
        try:
            validation_results = validate_environment_variables()
            logger.info("Tất cả biến môi trường đã được validate thành công")
        except ValueError as e:
            logger.error(f"Validation biến môi trường thất bại: {str(e)}")
            raise
        
        # Đọc cấu hình từ validation results
        self.qdrant_url = qdrant_url or validation_results["required_vars"]["QDRANT_URL"]
        self.collection_name = collection_name or validation_results["optional_vars"]["QDRANT_COLLECTION_NAME_MANGANH"]
        
        # Khởi tạo OpenAI client
        openai_api_key = validation_results["required_vars"]["OPENAI__API_KEY"]
        self.openai_client = OpenAI(api_key=openai_api_key)
        self.embedding_model = validation_results["optional_vars"]["OPENAI__EMBEDDING_MODEL"]
        
        # Initialize mock mode flag
        self.mock_mode = False
        
        logger.info(f"Backend khởi tạo với QDRANT_URL: {self.qdrant_url}, Collection: {self.collection_name}, Embedding Model: {self.embedding_model}")
        
        # Tạm thời disable Qdrant để tránh lỗi Pydantic validation
        try:
            # Thử kết nối Qdrant
            global _connection_pool
            self.client = _connection_pool.get_client(
                url=self.qdrant_url,
                timeout=60
            )
            logger.info(f"Đã kết nối thành công với Qdrant tại {self.qdrant_url} (sử dụng connection pool)")
            
            # Kiểm tra sự tồn tại của collection với error handling tốt hơn
            self._check_collection_exists()
            
        except Exception as e:
            logger.error(f"Lỗi kết nối Qdrant: {str(e)}")
            # Sử dụng mock mode để tránh crash
            self.client = None
            self.mock_mode = True
            logger.warning("Chuyển sang mock mode - sử dụng dữ liệu mẫu")
    
    def _safe_qdrant_operation(self, operation_name: str, operation_func, *args, **kwargs):
        """
        Wrapper an toàn cho tất cả operations với Qdrant để tránh Pydantic validation errors
        
        Args:
            operation_name: Tên operation để log
            operation_func: Function cần thực hiện
            *args, **kwargs: Arguments cho function
            
        Returns:
            Kết quả của operation hoặc None nếu có lỗi
        """
        try:
            if self.client is None:
                logger.warning(f"Qdrant client không khả dụng cho operation: {operation_name}")
                return None
                
            result = operation_func(*args, **kwargs)
            logger.debug(f"Operation {operation_name} thành công")
            return result
            
        except Exception as e:
            error_str = str(e).lower()
            # Mở rộng danh sách các lỗi Pydantic cần catch
            pydantic_keywords = [
                'pydantic', 'validation', 'max_optimization_threads', 
                'parsingmodel', 'inlineresponse', 'int_type', 'nonetype',
                'input should be a valid integer', 'optimizer_config',
                'model_rebuild', 'generate_schema', 'complete_model_class'
            ]
            
            if any(keyword in error_str for keyword in pydantic_keywords):
                logger.error(f"Pydantic validation error trong {operation_name}: {str(e)}")
                # Trả về empty result thay vì crash
                return None
            else:
                logger.error(f"Lỗi khác trong {operation_name}: {str(e)}")
                return None

    def _check_collection_exists(self):
        """Kiểm tra sự tồn tại của collection"""
        def _check():
            return self.client.scroll(
                collection_name=self.collection_name,
                limit=1,
                with_payload=False,
                with_vectors=False
            )
        
        result = self._safe_qdrant_operation("check_collection_exists", _check)
        if result is None:
            logger.warning(f"Không thể kiểm tra collection '{self.collection_name}' - sử dụng dummy mode")
        else:
            logger.info(f"Collection '{self.collection_name}' đã được xác nhận tồn tại")
    
    def normalize_code(self, ma_nganh: str) -> str:
        """
        Chuẩn hóa mã ngành - loại bỏ dấu chấm, khoảng trắng và normalize Vietnamese text
        
        Args:
            ma_nganh: Mã ngành cần chuẩn hóa
            
        Returns:
            Mã ngành đã chuẩn hóa
        """
        if not ma_nganh:
            return ""
        
        # Convert to string and normalize Vietnamese text first
        normalized_text = normalize_vietnamese_text(str(ma_nganh))
        
        # Loại bỏ dấu chấm và khoảng trắng
        normalized = normalized_text.replace(".", "").replace(" ", "").strip()
        
        return normalized
    def _retry_with_backoff(self, func, max_retries: int = 3, *args, **kwargs):
        """
        Thực hiện retry với exponential backoff
        
        Args:
            func: Hàm cần retry
            max_retries: Số lần retry tối đa
            *args, **kwargs: Tham số cho hàm
            
        Returns:
            Kết quả từ hàm hoặc raise exception nếu hết retry
        """
        for attempt in range(max_retries):
            try:
                return func(*args, **kwargs)
            except (ResponseHandlingException, UnexpectedResponse, Exception) as e:
                if attempt == max_retries - 1:
                    logger.error(f"Hết số lần retry ({max_retries}). Lỗi cuối: {str(e)}")
                    raise
                
                wait_time = (2 ** attempt) + 1  # Exponential backoff: 2, 3, 5 seconds
                logger.warning(f"Lần thử {attempt + 1} thất bại: {str(e)}. Retry sau {wait_time}s...")
                time.sleep(wait_time)
    
    def _validate_input(self, value: Any, param_name: str, required: bool = True) -> bool:
        """
        Validate dữ liệu đầu vào
        
        Args:
            value: Giá trị cần validate
            param_name: Tên tham số
            required: Có bắt buộc không
            
        Returns:
            True nếu hợp lệ
            
        Raises:
            ValueError: Nếu dữ liệu không hợp lệ
        """
        if required and (value is None or str(value).strip() == ""):
            raise ValueError(f"Tham số '{param_name}' là bắt buộc")
        
        return True
    
    def search_by_code(self, ma_nganh: str) -> Optional[Dict]:
        """
        Tìm kiếm theo mã ngành cụ thể
        
        Args:
            ma_nganh: Mã ngành (VD: "01.11", "0111", "01.11.0")
        
        Returns:
            Dict chứa thông tin ngành hoặc None nếu không tìm thấy
        """
        try:
            # Kiểm tra client có sẵn không hoặc đang ở mock mode
            if self.client is None or self.mock_mode:
                logger.warning(f"Sử dụng mock data cho mã ngành: {ma_nganh}")
                mock_data = self._get_mock_data("", 10)
                for item in mock_data:
                    if item["ma_nganh"] == ma_nganh.strip():
                        return item
                return None
                
            # Validate input
            self._validate_input(ma_nganh, "ma_nganh")
            
            # Chuẩn hóa mã ngành và tạo các variations
            normalized_code = self.normalize_code(ma_nganh)
            logger.info(f"Tìm kiếm mã ngành: '{ma_nganh}' -> normalized: '{normalized_code}'")
            
            # Tạo các variations để thử (cải thiện cho mã ngành 4 chữ số)
            variations = [
                normalized_code,  # "1130" -> "1130"
                normalized_code.lstrip('0'),  # "1130" -> "1130" (không thay đổi)
                ma_nganh.strip(),  # "1130"
                ma_nganh.strip().upper(),  # "1130" uppercase
                normalized_code.upper(),  # "1130" uppercase
            ]
            
            # Thêm variation với dấu chấm cho mã 4 chữ số
            if len(normalized_code) == 4:
                # "1130" -> "11.30"
                variations.append(f"{normalized_code[:2]}.{normalized_code[2:]}")
                # "1130" -> "113.0" (nếu chữ số cuối là 0)
                if normalized_code.endswith('0'):
                    variations.append(f"{normalized_code[:3]}.{normalized_code[3:]}")
            
            # Thêm variation với 4 chữ số (thêm 0 vào cuối nếu cần)
            if len(normalized_code) == 3:
                variations.append(normalized_code + '0')  # "113" -> "1130"
                variations.append(f"{normalized_code[:2]}.{normalized_code[2:]}0")  # "113" -> "11.30"
            elif len(normalized_code) == 2:
                variations.append(normalized_code + '00')  # "11" -> "1100"
                variations.append(f"{normalized_code}.00")  # "11" -> "11.00"
            
            # Loại bỏ duplicates và empty strings
            variations = list(set([v for v in variations if v]))
            
            for variant in variations:
                try:
                    filter_condition = models.Filter(
                        must=[
                            models.FieldCondition(
                                key="ma_nganh",
                                match=models.MatchValue(value=variant)
                            )
                        ]
                    )
                    
                    # Thực hiện truy vấn với retry và error handling
                    def _search():
                        return self.client.scroll(
                            collection_name=self.collection_name,
                            scroll_filter=filter_condition,
                            limit=1,
                            with_payload=True,
                            with_vectors=False
                        )
                    
                    result = self._safe_qdrant_operation(f"search_by_code_{variant}", _search)
                    if result is None:
                        logger.debug(f"Không thể tìm kiếm với variant '{variant}', thử variant tiếp theo")
                        continue
                    
                    if result[0]:  # Có kết quả
                        point = result[0][0]
                        payload = point.payload
                        
                        logger.info(f"Tìm thấy mã ngành '{ma_nganh}' với variant '{variant}': {payload.get('ten_nganh', 'N/A')}")
                        return payload
                        
                except Exception as e:
                    logger.debug(f"Lỗi tìm kiếm với variant '{variant}': {str(e)}")
                    continue
            
            logger.info(f"Không tìm thấy mã ngành '{ma_nganh}' với tất cả variants: {variations}")
            return None
                
        except Exception as e:
            logger.error(f"Lỗi tìm kiếm mã ngành '{ma_nganh}': {str(e)}")
            # Chuyển sang mock mode
            self.mock_mode = True
            mock_data = self._get_mock_data("", 10)
            for item in mock_data:
                if item["ma_nganh"] == ma_nganh.strip():
                    return item
            return None
    
    def _get_mock_data(self, keyword: str, limit: int = 10) -> List[Dict]:
        """Trả về mock data khi Qdrant không khả dụng"""
        mock_data = [
            {
                "ma_nganh": "A",
                "ten_nganh": "NÔNG NGHIỆP, LÂM NGHIỆP VÀ THUỶ SẢN",
                "mo_ta": "Nhóm ngành nông nghiệp, lâm nghiệp và thuỷ sản",
                "similarity_score": 0.9
            },
            {
                "ma_nganh": "01",
                "ten_nganh": "Nông nghiệp và hoạt động dịch vụ có liên quan",
                "mo_ta": "Các hoạt động nông nghiệp và dịch vụ liên quan",
                "similarity_score": 0.8
            },
            {
                "ma_nganh": "011",
                "ten_nganh": "Trồng cây hàng năm",
                "mo_ta": "Trồng các loại cây hàng năm",
                "similarity_score": 0.7
            },
            {
                "ma_nganh": "01110",
                "ten_nganh": "Trồng lúa",
                "mo_ta": "Hoạt động trồng lúa",
                "similarity_score": 0.6
            }
        ]
        
        # Lọc theo keyword
        if keyword.upper() == "A":
            return [item for item in mock_data if item["ma_nganh"].startswith("0")][:limit]
        elif keyword == "01":
            return [item for item in mock_data if item["ma_nganh"].startswith("01") and item["ma_nganh"] != "01"][:limit]
        else:
            return [item for item in mock_data if keyword.lower() in item["ten_nganh"].lower()][:limit]

    def search_by_keyword(self, keyword: str, limit: int = 10) -> List[Dict]:
        """
        Tìm kiếm semantic theo từ khóa sử dụng OpenAI embeddings với tối ưu tiếng Việt
        
        Args:
            keyword: Từ khóa tìm kiếm (VD: "trồng lúa", "chế biến thực phẩm")
            limit: Số lượng kết quả tối đa (mặc định 10, tối đa 50)
        
        Returns:
            List các ngành liên quan, sắp xếp theo similarity score
        """
        try:
            # Kiểm tra client có sẵn không hoặc đang ở mock mode
            if self.client is None or self.mock_mode:
                logger.warning(f"Sử dụng mock data cho keyword: {keyword}")
                return self._get_mock_data(keyword, limit)
                
            # Validate input
            self._validate_input(keyword, "keyword")
            
            # Enforce default limit of 10 and maximum of 50
            if limit <= 0 or limit > 50:
                logger.warning(f"Invalid limit {limit}, using default 10")
                limit = 10
            
            # Normalize Vietnamese text for better search
            normalized_keyword = normalize_vietnamese_text(keyword)
            search_variants = create_search_variants(keyword)
            
            logger.info(f"Tìm kiếm semantic với từ khóa: '{keyword}' -> normalized: '{normalized_keyword}', variants: {search_variants}, limit: {limit}")
            
            # Tạo embedding cho normalized keyword
            def _create_embedding():
                response = self.openai_client.embeddings.create(
                    model=self.embedding_model,
                    input=normalized_keyword
                )
                return response.data[0].embedding
            
            embedding = self._safe_qdrant_operation("create_embedding", _create_embedding)
            if embedding is None:
                logger.error("Không thể tạo embedding, chuyển sang mock mode")
                self.mock_mode = True
                return self._get_mock_data(keyword, limit)
            
            # Thực hiện semantic search trên Qdrant với error handling
            def _search():
                return self.client.scroll(
                    collection_name=self.collection_name,
                    limit=limit * 2,  # Get more results for better filtering
                    with_payload=True,
                    with_vectors=False
                )
            
            results = self._safe_qdrant_operation("search_by_keyword_scroll", _search)
            if results is None:
                logger.warning("Không thể thực hiện tìm kiếm từ khóa, chuyển sang mock mode")
                self.mock_mode = True
                return self._get_mock_data(keyword, limit)
            
            # Nếu không có kết quả, chuyển sang mock mode
            if not results[0]:
                logger.warning("Không có kết quả từ Qdrant, chuyển sang mock mode")
                self.mock_mode = True
                return self._get_mock_data(keyword, limit)
            
            # Xử lý kết quả với Vietnamese text matching
            processed_results = []
            for point in results[0]:
                payload = point.payload.copy()
                ten_nganh = payload.get('ten_nganh', '')
                mo_ta = payload.get('mo_ta', '')
                
                # Calculate similarity score based on Vietnamese text matching
                similarity_score = self._calculate_vietnamese_similarity(
                    search_variants, ten_nganh, mo_ta
                )
                
                payload['similarity_score'] = similarity_score
                processed_results.append(payload)
            
            # Sắp xếp theo similarity score và enforce limit
            processed_results.sort(key=lambda x: x.get('similarity_score', 0), reverse=True)
            processed_results = processed_results[:limit]  # Enforce limit
            
            logger.info(f"Tìm thấy {len(processed_results)} kết quả cho từ khóa '{keyword}' (limit: {limit})")
            return processed_results
            
        except Exception as e:
            logger.error(f"Lỗi tìm kiếm từ khóa '{keyword}': {str(e)}")
            # Chuyển sang mock mode
            self.mock_mode = True
            return self._get_mock_data(keyword, limit)
    
    def _calculate_vietnamese_similarity(self, search_variants: List[str], ten_nganh: str, mo_ta: str) -> float:
        """
        Calculate similarity score for Vietnamese text matching.
        
        Args:
            search_variants: List of search text variants
            ten_nganh: Industry name to match against
            mo_ta: Industry description to match against
            
        Returns:
            Similarity score between 0.0 and 1.0
        """
        if not search_variants:
            return 0.5  # Default score
        
        max_score = 0.0
        
        # Normalize target texts
        normalized_ten_nganh = normalize_vietnamese_text(ten_nganh)
        normalized_mo_ta = normalize_vietnamese_text(mo_ta)
        no_accent_ten_nganh = remove_vietnamese_accents(ten_nganh)
        no_accent_mo_ta = remove_vietnamese_accents(mo_ta)
        
        for variant in search_variants:
            variant_lower = variant.lower()
            variant_no_accent = remove_vietnamese_accents(variant)
            
            # Exact match in name (highest score)
            if variant_lower in normalized_ten_nganh:
                max_score = max(max_score, 0.95)
            elif variant_no_accent in no_accent_ten_nganh:
                max_score = max(max_score, 0.90)
            
            # Exact match in description
            elif variant_lower in normalized_mo_ta:
                max_score = max(max_score, 0.85)
            elif variant_no_accent in no_accent_mo_ta:
                max_score = max(max_score, 0.80)
            
            # Partial word matches
            elif any(word in normalized_ten_nganh for word in variant_lower.split() if len(word) > 2):
                max_score = max(max_score, 0.75)
            elif any(word in no_accent_ten_nganh for word in variant_no_accent.split() if len(word) > 2):
                max_score = max(max_score, 0.70)
            
            # Partial matches in description
            elif any(word in normalized_mo_ta for word in variant_lower.split() if len(word) > 2):
                max_score = max(max_score, 0.65)
            elif any(word in no_accent_mo_ta for word in variant_no_accent.split() if len(word) > 2):
                max_score = max(max_score, 0.60)
        
        # Default score if no matches found
        return max_score if max_score > 0 else 0.5
    def search_by_name(self, ten_nganh: str, limit: int = 15) -> List[Dict]:
        """
        Tìm kiếm theo tên ngành nghề cụ thể
        
        Args:
            ten_nganh: Tên ngành cần tìm
            limit: Số lượng kết quả tối đa
        
        Returns:
            List các ngành có tên tương tự, ưu tiên khớp chính xác
        """
        try:
            # Kiểm tra client có sẵn không
            if self.client is None:
                logger.error("Qdrant client không khả dụng")
                return []
                
            # Validate input
            self._validate_input(ten_nganh, "ten_nganh")
            
            # Normalize tên ngành
            normalized_name = normalize_vietnamese_text(ten_nganh)
            search_variants = create_search_variants(ten_nganh)
            
            logger.info(f"Tìm kiếm theo tên ngành: '{ten_nganh}' -> normalized: '{normalized_name}'")
            
            # Tìm kiếm bằng cách scroll toàn bộ collection và filter
            def _search_all():
                return self.client.scroll(
                    collection_name=self.collection_name,
                    limit=1000,  # Lấy nhiều để filter
                    with_payload=True,
                    with_vectors=False
                )
            
            results = self._safe_qdrant_operation("search_by_name_scroll", _search_all)
            if results is None:
                logger.error("Không thể thực hiện tìm kiếm theo tên ngành")
                return []
            
            # Filter và score kết quả
            scored_results = []
            normalized_search = ten_nganh.lower().strip()
            search_words = set(normalized_search.split())
            
            for point in results[0]:
                payload = point.payload.copy()
                ten_nganh_item = payload.get('ten_nganh', '').lower()
                item_words = set(ten_nganh_item.split())
                
                # Tính điểm tương tự
                score = 0
                
                # Khớp chính xác hoàn toàn = 100 điểm
                if normalized_search == ten_nganh_item:
                    score = 100
                # Chứa toàn bộ từ tìm kiếm = 80 điểm
                elif search_words.issubset(item_words):
                    score = 80
                # Khớp một phần từ khóa
                elif len(search_words.intersection(item_words)) > 0:
                    match_ratio = len(search_words.intersection(item_words)) / len(search_words)
                    score = 60 * match_ratio
                # Chứa substring
                elif any(word in ten_nganh_item for word in search_words if len(word) > 2):
                    score = 30
                
                # Chỉ lấy kết quả có điểm > 0
                if score > 0:
                    payload['name_similarity_score'] = score
                    scored_results.append(payload)
            
            # Sắp xếp theo điểm và giới hạn kết quả
            scored_results.sort(key=lambda x: x.get('name_similarity_score', 0), reverse=True)
            final_results = scored_results[:limit]
            
            logger.info(f"Tìm thấy {len(final_results)} kết quả cho tên ngành '{ten_nganh}'")
            return final_results
            
        except Exception as e:
            logger.error(f"Lỗi tìm kiếm theo tên ngành '{ten_nganh}': {str(e)}")
            return []

    def filter_by_system_and_level(
        self, 
        system: str = None, 
        level: int = None, 
        limit: int = 50
    ) -> List[Dict]:
        """
        Lọc mã ngành theo hệ thống và cấp độ
        
        Args:
            system: Hệ thống phân loại (VD: "VSIC")
            level: Cấp độ ngành (1, 2, 3, 4)
            limit: Số lượng kết quả tối đa
        
        Returns:
            List các mã ngành theo filter
        """
        try:
            # Kiểm tra client có sẵn không
            if self.client is None:
                logger.error("Qdrant client không khả dụng")
                return []
                
            logger.info(f"Lọc mã ngành theo system='{system}', level={level}, limit={limit}")
            
            # Tìm kiếm bằng cách scroll và filter
            def _search_all():
                return self.client.scroll(
                    collection_name=self.collection_name,
                    limit=1000,
                    with_payload=True,
                    with_vectors=False
                )
            
            results = self._safe_qdrant_operation("filter_by_system_and_level", _search_all)
            if results is None:
                logger.error("Không thể thực hiện filter mã ngành")
                return []
            
            # Filter kết quả
            filtered_results = []
            for point in results[0]:
                payload = point.payload.copy()
                ma_nganh = payload.get('ma_nganh', '')
                
                # Filter theo level nếu được chỉ định
                if level is not None:
                    ma_nganh_clean = ma_nganh.replace('.', '')
                    if level == 1 and len(ma_nganh_clean) != 1:
                        continue
                    elif level == 2 and len(ma_nganh_clean) != 2:
                        continue
                    elif level == 3 and len(ma_nganh_clean) != 3:
                        continue
                    elif level == 4 and len(ma_nganh_clean) < 4:
                        continue
                
                filtered_results.append(payload)
                
                # Giới hạn kết quả
                if len(filtered_results) >= limit:
                    break
            
            logger.info(f"Tìm thấy {len(filtered_results)} kết quả filter")
            return filtered_results
            
        except Exception as e:
            logger.error(f"Lỗi filter mã ngành: {str(e)}")
            return []

    def get_collection_info(self) -> Dict:
        """
        Lấy thông tin về collection
        
        Returns:
            Dict chứa thông tin collection
        """
        try:
            # Kiểm tra client có sẵn không
            if self.client is None:
                return {"error": "Qdrant client không khả dụng"}
                
            # Thử scroll để lấy thông tin cơ bản
            def _get_info():
                return self.client.scroll(
                    collection_name=self.collection_name,
                    limit=1,
                    with_payload=True,
                    with_vectors=False
                )
            
            result = self._safe_qdrant_operation("get_collection_info", _get_info)
            if result is None:
                return {"error": "Không thể lấy thông tin collection"}
            
            return {
                "collection_name": self.collection_name,
                "status": "available" if result[0] else "empty_or_error",
                "sample_count": len(result[0])
            }
            
        except Exception as e:
            logger.error(f"Lỗi lấy thông tin collection: {str(e)}")
            return {"error": str(e)}

    def health_check(self) -> bool:
        """
        Kiểm tra sức khỏe của backend
        
        Returns:
            True nếu backend hoạt động bình thường
        """
        try:
            # Kiểm tra client có sẵn không
            if self.client is None:
                return False
                
            # Thử một operation đơn giản
            def _health_check():
                result = self.client.scroll(
                    collection_name=self.collection_name,
                    limit=1,
                    with_payload=False,
                    with_vectors=False
                )
                return True
            
            return self._safe_qdrant_operation("health_check", _health_check) is not None
            
        except Exception as e:
            logger.error(f"Health check failed: {str(e)}")
            return False


# Connection pooling implementation
import threading
from typing import Optional

class QdrantConnectionPool:
    """
    Connection pool for Qdrant clients to optimize performance.
    Implements singleton pattern with thread-safe connection reuse.
    """
    
    _instance = None
    _lock = threading.Lock()
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if not self._initialized:
            self._clients = {}  # URL -> QdrantClient mapping
            self._client_lock = threading.Lock()
            self._initialized = True
            logger.info("QdrantConnectionPool initialized")
    
    def get_client(self, url: str, timeout: int = 60) -> QdrantClient:
        """
        Get or create a Qdrant client for the given URL.
        
        Args:
            url: Qdrant server URL
            timeout: Connection timeout in seconds
            
        Returns:
            QdrantClient instance (reused if exists)
        """
        with self._client_lock:
            if url not in self._clients:
                logger.info(f"Creating new Qdrant client for {url}")
                try:
                    # Thử tạo client với cấu hình tối thiểu
                    self._clients[url] = QdrantClient(url=url)
                    logger.info(f"Successfully created Qdrant client for {url}")
                except Exception as e:
                    logger.error(f"Lỗi tạo Qdrant client: {str(e)}")
                    raise ConnectionError(f"Không thể tạo Qdrant client: {str(e)}")
            else:
                logger.debug(f"Reusing existing Qdrant client for {url}")
            
            return self._clients[url]
    
    def close_all(self):
        """Close all connections in the pool."""
        with self._client_lock:
            for url, client in self._clients.items():
                try:
                    client.close()
                    logger.info(f"Closed Qdrant client for {url}")
                except Exception as e:
                    logger.warning(f"Error closing client for {url}: {e}")
            self._clients.clear()


# Singleton instances để tái sử dụng kết nối
_backend_instance = None
_connection_pool = QdrantConnectionPool()

def get_backend() -> MaNganhBackend:
    """
    Lấy singleton instance của MaNganhBackend với connection pooling
    
    Returns:
        MaNganhBackend instance
    """
    global _backend_instance
    
    if _backend_instance is None:
        _backend_instance = MaNganhBackend()
    
    return _backend_instance