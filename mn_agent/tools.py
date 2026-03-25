"""
Tools module for mn_agent - Provides LangChain tools for searching industry codes.

This module contains tools that the AI agent can use to search and filter
Vietnamese industry codes (mã ngành) from the Qdrant database.
"""

import json
import logging
import math
import time
from typing import Any, Dict, List, Optional

import pandas as pd
from langchain.tools import tool

from .backend import get_backend

# Configure logging - chỉ hiển thị ERROR để giảm noise
logger = logging.getLogger(__name__)
logger.setLevel(logging.ERROR)


def clean_for_json(data: Any) -> Any:
    """
    Clean data to ensure it can be serialized to JSON.
    
    Handles NaN, Infinity, and pandas NA values by converting them to None.
    Recursively processes dictionaries and lists.
    
    Args:
        data: Data to clean (can be dict, list, or primitive type)
    
    Returns:
        Cleaned data that can be JSON serialized
    """
    if isinstance(data, dict):
        return {k: clean_for_json(v) for k, v in data.items()}
    elif isinstance(data, list):
        return [clean_for_json(item) for item in data]
    elif isinstance(data, float):
        if math.isnan(data) or math.isinf(data):
            return None
        return data
    elif pd.isna(data):
        return None
    elif data is None:
        return None
    else:
        return data


def analyze_search_term(search_term: str) -> Dict[str, Any]:
    """
    Phân tích từ khóa tìm kiếm để xác định chiến lược tìm kiếm tốt nhất.
    
    Args:
        search_term: Từ khóa cần phân tích
    
    Returns:
        Dict chứa thông tin phân tích và gợi ý chiến lược
    """
    search_term = search_term.strip().lower()
    words = search_term.split()
    
    # Các từ khóa chỉ hoạt động chung
    general_keywords = {
        'hoạt động', 'dịch vụ', 'kinh doanh', 'sản xuất', 'chế biến', 
        'trồng', 'nuôi', 'khai thác', 'xây dựng', 'vận tải', 'bán'
    }
    
    # Các từ khóa chỉ ngành cụ thể
    specific_indicators = {
        'lúa', 'gạo', 'cà phê', 'cao su', 'ô tô', 'xe máy', 'nhà hàng',
        'khách sạn', 'bệnh viện', 'trường học', 'ngân hàng', 'bảo hiểm'
    }
    
    # Các từ khóa chỉ câu hỏi về mã ngành con
    parent_code_indicators = {
        'dưới', 'con', 'thuộc', 'gồm', 'bao gồm', 'có những', 'các mã', 
        'nhóm', 'những nhóm', 'những ngành'
    }
    
    # Các từ khóa chỉ câu hỏi về hoạt động tương tự
    similar_activity_indicators = {
        'tương tự', 'giống như', 'hoạt động', 'tương đương', 'như'
    }
    
    # Kiểm tra mã ngành (chữ cái hoặc số)
    import re
    has_code_pattern = bool(re.search(r'^[A-Z0-9]+$', search_term.upper()))
    
    # Phân tích
    has_general_words = any(word in general_keywords for word in words)
    has_specific_words = any(word in specific_indicators for word in words)
    has_parent_code_words = any(word in parent_code_indicators for word in words)
    has_similar_activity_words = any(word in similar_activity_indicators for word in words)
    
    # Xác định loại tìm kiếm
    if has_code_pattern:
        search_type = "parent_code_query"
    elif has_parent_code_words:
        search_type = "parent_code_query"
    elif has_similar_activity_words:
        search_type = "similar_activity_query"
    elif has_specific_words and not has_general_words:
        search_type = "specific_name"
    elif has_general_words and not has_specific_words:
        search_type = "general_keyword"
    elif len(words) >= 3 and any(len(word) > 4 for word in words):
        search_type = "specific_name"
    else:
        search_type = "general_keyword"
    
    return {
        "search_type": search_type,
        "has_general_words": has_general_words,
        "has_specific_words": has_specific_words,
        "has_parent_code_words": has_parent_code_words,
        "has_similar_activity_words": has_similar_activity_words,
        "has_code_pattern": has_code_pattern,
        "word_count": len(words),
        "main_keywords": [word for word in words if len(word) > 2]
    }


@tool
def search_by_code_tool(ma_nganh: str) -> str:
    """
    Tìm kiếm thông tin ngành nghề theo mã ngành cụ thể.
    
    Công cụ này cho phép tìm kiếm thông tin chi tiết về một mã ngành cụ thể
    trong hệ thống phân loại ngành nghề Việt Nam (VSIC).
    
    Args:
        ma_nganh: Mã ngành cần tìm (VD: "01.11", "47.11", "0111")
    
    Returns:
        JSON string chứa thông tin ngành hoặc thông báo lỗi
    """
    return safe_tool_execution("search_by_code", _search_by_code_impl, ma_nganh)


def _search_by_code_impl(ma_nganh: str) -> str:
    """Implementation of search by code tool"""
    start_time = time.time()
    logger.info(f"search_by_code_tool called with ma_nganh='{ma_nganh}'")
    
    try:
        # Validate input
        if not ma_nganh or not ma_nganh.strip():
            result = {
                "type": "error",
                "message": "Mã ngành không được để trống."
            }
            logger.warning("Empty ma_nganh provided")
            return json.dumps(result, ensure_ascii=False)
        
        # Get backend and search
        backend = get_backend()
        data = backend.search_by_code(ma_nganh.strip())
        
        processing_time = time.time() - start_time
        
        if data:
            # Clean data and create response
            cleaned_data = clean_for_json(data)
            result = {
                "type": "single_result",
                "data": cleaned_data
            }
            logger.info(f"search_by_code_tool found result for '{ma_nganh}' in {processing_time:.3f}s")
        else:
            # Kiểm tra nếu backend có vấn đề
            if backend.client is None:
                result = {
                    "type": "error",
                    "message": f"Không thể tìm kiếm mã ngành '{ma_nganh}' do lỗi hệ thống. Vui lòng thử lại sau."
                }
            else:
                result = {
                    "type": "not_found",
                    "message": f"Không tìm thấy mã ngành '{ma_nganh}' trong hệ thống."
                }
            logger.info(f"search_by_code_tool no result for '{ma_nganh}' in {processing_time:.3f}s")
        
        return json.dumps(result, ensure_ascii=False)
        
    except Exception as e:
        processing_time = time.time() - start_time
        error_msg = f"Lỗi khi tìm kiếm mã ngành: {str(e)}"
        result = {
            "type": "error",
            "message": error_msg
        }
        logger.error(f"search_by_code_tool error for '{ma_nganh}' in {processing_time:.3f}s: {str(e)}")
        return json.dumps(result, ensure_ascii=False)


@tool
def search_by_keyword_tool(keyword: str) -> str:
    """
    Tìm kiếm ngành nghề theo từ khóa hoặc mô tả.
    
    Công cụ này sử dụng tìm kiếm ngữ nghĩa (semantic search) để tìm các ngành nghề
    liên quan đến từ khóa hoặc mô tả hoạt động kinh doanh.
    Đặc biệt hỗ trợ tìm kiếm mã ngành con theo cấu trúc phân cấp.
    
    Args:
        keyword: Từ khóa tìm kiếm (VD: "trồng lúa", "may mặc", "chế biến thực phẩm", "01", "A")
    
    Returns:
        JSON string chứa danh sách ngành liên quan hoặc thông báo lỗi
    """
    return safe_tool_execution("search_by_keyword", _search_by_keyword_impl, keyword)


def _search_by_keyword_impl(keyword: str) -> str:
    """Implementation of search by keyword tool"""
    start_time = time.time()
    logger.info(f"search_by_keyword_tool called with keyword='{keyword}'")
    
    try:
        # Validate input
        if not keyword or not keyword.strip():
            result = {
                "type": "error",
                "message": "Từ khóa tìm kiếm không được để trống."
            }
            logger.warning("Empty keyword provided")
            return json.dumps(result, ensure_ascii=False)
        
        keyword = keyword.strip()
        
        # Phát hiện nếu đây là câu hỏi về mã ngành con
        is_parent_code_query = False
        parent_code = None
        
        # Kiểm tra các pattern về mã ngành con
        import re
        parent_code_patterns = [
            r'(?:mã ngành |ngành |các |)(?:dưới|con của|thuộc) ([A-Z0-9]+)',
            r'([A-Z0-9]+)(?:\s+có những mã ngành nào|\s+gồm những ngành nào|\s+có những nhóm nào)',
            r'(?:nhóm|ngành)\s+([A-Z0-9]+)(?:\s+gồm|\s+có|\s+bao gồm)',
            r'^([A-Z0-9]+)$'  # Chỉ có mã ngành đơn thuần
        ]
        
        # Kiểm tra các pattern về hoạt động tương tự
        similar_activity_patterns = [
            r'hoạt động.*?tương tự.*?với\s+(.+?)(?:\s+thuộc|\s+là|$)',
            r'tương tự.*?với\s+(.+?)(?:\s+thuộc|\s+là|$)',
            r'giống.*?như\s+(.+?)(?:\s+thuộc|\s+là|$)'
        ]
        
        # Tìm hoạt động tương tự trước
        similar_activity = None
        for pattern in similar_activity_patterns:
            match = re.search(pattern, keyword, re.IGNORECASE)
            if match:
                similar_activity = match.group(1).strip()
                break
        
        if similar_activity:
            # Nếu tìm thấy "hoạt động tương tự với X", sử dụng search_by_name thay vì search_by_keyword
            keyword = similar_activity
            logger.info(f"Phát hiện câu hỏi về hoạt động tương tự, tìm kiếm với search_by_name: '{keyword}'")
            
            # Get backend
            backend = get_backend()
            
            # Sử dụng search_by_name cho kết quả chính xác hơn
            data_list = backend.search_by_name(keyword, limit=15)
            
            # Kiểm tra nếu backend trả về empty (do lỗi Qdrant)
            if not data_list:
                # Fallback với search_by_keyword
                data_list = backend.search_by_keyword(keyword, limit=10)
                
                if not data_list:
                    result = {
                        "type": "error",
                        "message": f"Không thể tìm kiếm hoạt động tương tự với '{keyword}' do lỗi hệ thống. Vui lòng thử lại sau."
                    }
                    return json.dumps(result, ensure_ascii=False)
        
        # Kiểm tra parent code chỉ khi không phải câu hỏi về hoạt động tương tự
        elif not similar_activity:
            for pattern in parent_code_patterns:
                match = re.search(pattern, keyword, re.IGNORECASE)
                if match:
                    parent_code = match.group(1).upper()
                    is_parent_code_query = True
                    break
        
        # Get backend and search (chỉ khi chưa có backend)
        if 'backend' not in locals():
            backend = get_backend()
        
        if similar_activity:
            # Đã xử lý ở trên, data_list đã có sẵn
            pass
        elif is_parent_code_query and parent_code:
            # Tìm kiếm mã ngành con với limit cao hơn
            data_list = backend.search_by_keyword(parent_code, limit=30)
            
            # Kiểm tra nếu backend trả về empty (do lỗi Qdrant)
            if not data_list:
                result = {
                    "type": "error",
                    "message": f"Không thể tìm kiếm mã ngành con của '{parent_code}' do lỗi hệ thống. Vui lòng thử lại sau."
                }
                return json.dumps(result, ensure_ascii=False)
            
            # Lọc kết quả để chỉ lấy mã ngành con
            filtered_results = []
            parent_len = len(parent_code)
            
            for item in data_list:
                ma_nganh = item.get('ma_nganh', '')
                # Kiểm tra nếu là mã ngành con (bắt đầu bằng parent_code và dài hơn)
                if (ma_nganh.startswith(parent_code) and 
                    len(ma_nganh) > parent_len and 
                    ma_nganh != parent_code):
                    filtered_results.append(item)
            
            # Sắp xếp theo mã ngành
            filtered_results.sort(key=lambda x: x.get('ma_nganh', ''))
            data_list = filtered_results[:20]  # Giới hạn 20 kết quả
            
        else:
            # Tìm kiếm thông thường - ưu tiên search_by_name cho kết quả chính xác hơn
            data_list = backend.search_by_name(keyword, limit=15)
            
            # Nếu search_by_name không có kết quả, fallback với search_by_keyword
            if not data_list:
                data_list = backend.search_by_keyword(keyword, limit=10)
            
            # Kiểm tra nếu backend trả về empty (do lỗi Qdrant)
            if not data_list:
                result = {
                    "type": "error", 
                    "message": f"Không thể tìm kiếm từ khóa '{keyword}' do lỗi hệ thống. Vui lòng thử lại sau."
                }
                return json.dumps(result, ensure_ascii=False)
        
        processing_time = time.time() - start_time
        
        if data_list:
            # Clean data and create response
            cleaned_data_list = clean_for_json(data_list)
            result = {
                "type": "multiple_results",
                "data_list": cleaned_data_list,
                "total_found": len(data_list),
                "displayed": len(data_list),
                "is_parent_code_query": is_parent_code_query,
                "parent_code": parent_code if is_parent_code_query else None
            }
            
            # Thêm thông báo nếu đang sử dụng mock mode
            if hasattr(backend, 'mock_mode') and backend.mock_mode:
                result["note"] = "Đang sử dụng dữ liệu mẫu do lỗi hệ thống"
                
            logger.info(f"search_by_keyword_tool found {len(data_list)} results for '{keyword}' in {processing_time:.3f}s")
        else:
            message = f"Không tìm thấy ngành nghề nào liên quan đến '{keyword}'."
            if is_parent_code_query:
                message = f"Không tìm thấy mã ngành con nào thuộc '{parent_code}'."
            
            result = {
                "type": "not_found",
                "message": message,
                "is_parent_code_query": is_parent_code_query,
                "parent_code": parent_code if is_parent_code_query else None
            }
            logger.info(f"search_by_keyword_tool no results for '{keyword}' in {processing_time:.3f}s")
        
        return json.dumps(result, ensure_ascii=False)
        
    except Exception as e:
        processing_time = time.time() - start_time
        error_msg = f"Lỗi khi tìm kiếm theo từ khóa: {str(e)}"
        result = {
            "type": "error",
            "message": error_msg
        }
        logger.error(f"search_by_keyword_tool error for '{keyword}' in {processing_time:.3f}s: {str(e)}")
        return json.dumps(result, ensure_ascii=False)


@tool
def filter_by_system_and_level_tool(
    he_thong: Optional[str] = None,
    cap_nganh: Optional[int] = None
) -> str:
    """
    Lọc danh sách mã ngành theo hệ thống phân loại và cấp ngành.
    
    Công cụ này cho phép lọc các mã ngành theo hệ thống phân loại (như VSIC 2018, VSIC 2025)
    và/hoặc theo cấp ngành (cấp 1, 2, 3, 4).
    
    Args:
        he_thong: Hệ thống phân loại (VD: "VSIC 2018", "VSIC 2025"). Tùy chọn.
        cap_nganh: Cấp ngành (1, 2, 3, hoặc 4). Tùy chọn.
    
    Returns:
        JSON string chứa danh sách ngành thỏa mãn điều kiện hoặc thông báo lỗi
    """
    return safe_tool_execution("filter_by_system_and_level", _filter_by_system_and_level_impl, he_thong, cap_nganh)


def _filter_by_system_and_level_impl(
    he_thong: Optional[str] = None,
    cap_nganh: Optional[int] = None
) -> str:
    """Implementation of filter by system and level tool"""
    start_time = time.time()
    logger.info(f"filter_by_system_and_level_tool called with he_thong='{he_thong}', cap_nganh={cap_nganh}")
    
    try:
        # Validate input - at least one parameter must be provided
        if he_thong is None and cap_nganh is None:
            result = {
                "type": "error",
                "message": "Cần cung cấp ít nhất một trong hai tham số: hệ thống ngành hoặc cấp ngành."
            }
            logger.warning("No filter parameters provided")
            return json.dumps(result, ensure_ascii=False)
        
        # Validate cap_nganh if provided
        if cap_nganh is not None and cap_nganh not in [1, 2, 3, 4]:
            result = {
                "type": "error",
                "message": "Cấp ngành phải là 1, 2, 3, hoặc 4."
            }
            logger.warning(f"Invalid cap_nganh: {cap_nganh}")
            return json.dumps(result, ensure_ascii=False)
        
        # Get backend and filter
        backend = get_backend()
        data_list = backend.filter_by_system_and_level(
            system=he_thong.strip() if he_thong else None,
            level=cap_nganh,
            limit=50
        )
        
        processing_time = time.time() - start_time
        
        if data_list:
            # Clean data and create response
            cleaned_data_list = clean_for_json(data_list)
            result = {
                "type": "multiple_results",
                "data_list": cleaned_data_list,
                "total_found": len(data_list),
                "displayed": len(data_list)
            }
            logger.info(f"filter_by_system_and_level_tool found {len(data_list)} results in {processing_time:.3f}s")
        else:
            filter_desc = []
            if he_thong:
                filter_desc.append(f"hệ thống '{he_thong}'")
            if cap_nganh:
                filter_desc.append(f"cấp {cap_nganh}")
            
            result = {
                "type": "not_found",
                "message": f"Không tìm thấy mã ngành nào với {' và '.join(filter_desc)}."
            }
            logger.info(f"filter_by_system_and_level_tool no results in {processing_time:.3f}s")
        
        return json.dumps(result, ensure_ascii=False)
        
    except Exception as e:
        processing_time = time.time() - start_time
        error_msg = f"Lỗi khi lọc mã ngành: {str(e)}"
        result = {
            "type": "error",
            "message": error_msg
        }
        logger.error(f"filter_by_system_and_level_tool error in {processing_time:.3f}s: {str(e)}")
        return json.dumps(result, ensure_ascii=False)


def safe_tool_execution(tool_name: str, func, *args, **kwargs):
    """
    Wrapper an toàn cho tất cả tool executions để tránh Pydantic validation errors
    """
    try:
        return func(*args, **kwargs)
    except Exception as e:
        error_str = str(e).lower()
        pydantic_keywords = [
            'pydantic', 'validation', 'max_optimization_threads', 
            'parsingmodel', 'inlineresponse', 'int_type', 'nonetype',
            'input should be a valid integer', 'optimizer_config',
            'model_rebuild', 'generate_schema', 'complete_model_class'
        ]
        
        if any(keyword in error_str for keyword in pydantic_keywords):
            logger.error(f"Pydantic validation error trong tool {tool_name}: {str(e)}")
            # Trả về error response thay vì crash
            result = {
                "type": "error",
                "message": f"Lỗi hệ thống khi thực hiện tìm kiếm. Vui lòng thử lại sau."
            }
            return json.dumps(result, ensure_ascii=False)
        else:
            # Re-raise non-Pydantic errors
            raise


@tool
def search_by_name_tool(ten_nganh: str) -> str:
    """
    Tìm kiếm mã ngành theo tên ngành nghề.
    
    Công cụ này cho phép tìm kiếm mã ngành dựa trên tên chính xác hoặc gần đúng
    của ngành nghề trong hệ thống VSIC.
    
    Args:
        ten_nganh: Tên ngành cần tìm (VD: "Trồng lúa", "May mặc", "Bán lẻ thực phẩm")
    
    Returns:
        JSON string chứa danh sách mã ngành có tên tương tự hoặc thông báo lỗi
    """
    return safe_tool_execution("search_by_name", _search_by_name_impl, ten_nganh)


def _search_by_name_impl(ten_nganh: str) -> str:
    """Implementation of search by name tool"""
    start_time = time.time()
    
    try:
        # Validate input
        if not ten_nganh or not ten_nganh.strip():
            result = {
                "type": "error",
                "message": "Tên ngành không được để trống."
            }
            return json.dumps(result, ensure_ascii=False)
        
        # Get backend and search by name (sử dụng method riêng cho tên ngành)
        backend = get_backend()
        
        # Phân tích từ khóa tìm kiếm
        analysis = analyze_search_term(ten_nganh)
        
        # Sử dụng method search_by_name riêng thay vì search_by_keyword
        data_list = backend.search_by_name(ten_nganh.strip(), limit=15)
        
        # Kiểm tra nếu backend trả về empty (do lỗi Qdrant)
        if not data_list:
            # Thử fallback với search_by_keyword
            logger.info(f"search_by_name trả về empty, thử fallback với search_by_keyword")
            data_list = backend.search_by_keyword(ten_nganh.strip(), limit=10)
            
            if not data_list:
                result = {
                    "type": "error",
                    "message": f"Không thể tìm kiếm tên ngành '{ten_nganh}' do lỗi hệ thống. Vui lòng thử lại sau."
                }
                return json.dumps(result, ensure_ascii=False)
        
        processing_time = time.time() - start_time
        
        if data_list:
            # Kết quả đã được sắp xếp trong backend
            # Clean data and create response
            cleaned_data_list = clean_for_json(data_list)
            
            # Đếm các loại match từ name_similarity_score
            exact_matches = len([item for item in data_list if item.get('name_similarity_score', 0) >= 100])
            high_priority_matches = len([item for item in data_list if 80 <= item.get('name_similarity_score', 0) < 100])
            
            result = {
                "type": "multiple_results",
                "data_list": cleaned_data_list,
                "total_found": len(data_list),
                "displayed": len(data_list),
                "exact_matches": exact_matches,
                "high_priority_matches": high_priority_matches,
                "search_analysis": analysis
            }
        else:
            result = {
                "type": "not_found",
                "message": f"Không tìm thấy ngành nghề nào có tên '{ten_nganh}'."
            }
        
        return json.dumps(result, ensure_ascii=False)
        
    except Exception as e:
        processing_time = time.time() - start_time
        error_msg = f"Lỗi khi tìm kiếm theo tên ngành: {str(e)}"
        result = {
            "type": "error",
            "message": error_msg
        }
        return json.dumps(result, ensure_ascii=False)