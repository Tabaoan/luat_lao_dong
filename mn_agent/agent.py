"""
Agent module for mn_agent - LangChain Agent for processing natural language queries about industry codes.

This module implements the main AI agent that uses LangChain with OpenAI to process
Vietnamese natural language queries about industry codes (mã ngành) and intelligently
choose between available tools to provide structured JSON responses.
"""

import json
import logging
import os
from typing import Any, Dict, List, Tuple

from langchain_classic.agents import AgentExecutor, create_openai_functions_agent
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_openai import ChatOpenAI

from .tools import (
    filter_by_system_and_level_tool,
    search_by_code_tool,
    search_by_keyword_tool,
    search_by_name_tool,
)

# Configure logging - chỉ hiển thị ERROR để giảm noise
logger = logging.getLogger(__name__)
logger.setLevel(logging.ERROR)

# Global variables for agent components
llm = None
agent_executor = None
chat_history = []


def validate_agent_environment_variables() -> Dict[str, Any]:
    """
    Validate environment variables specifically needed for the Agent.
    
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
    
    # Required variables for Agent
    required_vars = {
        "OPENAI__API_KEY": {
            "value": os.getenv("OPENAI__API_KEY"),
            "validator": lambda x: x and x.startswith('sk-')
        }
    }
    
    # Optional variables with defaults
    optional_vars = {
        "OPENAI__MODEL_NAME": {
            "value": os.getenv("OPENAI__MODEL_NAME", "gpt-4o-mini"),
            "default": "gpt-4o-mini",
            "validator": lambda x: x in ["gpt-4o-mini", "gpt-4o", "gpt-4", "gpt-3.5-turbo"]
        },
        "OPENAI__TEMPERATURE": {
            "value": os.getenv("OPENAI__TEMPERATURE", "0"),
            "default": "0",
            "validator": lambda x: 0 <= float(x) <= 2
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
            error_msg = f"Biến môi trường '{var_name}' có giá trị không hợp lệ"
            validation_results["errors"].append(error_msg)
            logger.error(error_msg)
        else:
            validation_results["required_vars"][var_name] = value
            logger.info(f"✓ {var_name}: OK")
    
    # Validate optional variables
    for var_name, config in optional_vars.items():
        value = config["value"]
        default = config["default"]
        validator = config.get("validator")
        
        if not value:
            value = default
            warning_msg = f"Biến môi trường '{var_name}' không được thiết lập, sử dụng giá trị mặc định: '{default}'"
            validation_results["warnings"].append(warning_msg)
            logger.warning(warning_msg)
        elif validator and not validator(value):
            warning_msg = f"Biến môi trường '{var_name}' có giá trị không khuyến nghị: '{value}', sử dụng giá trị mặc định: '{default}'"
            validation_results["warnings"].append(warning_msg)
            logger.warning(warning_msg)
            value = default
        
        validation_results["optional_vars"][var_name] = value
        logger.info(f"✓ {var_name}: {value}")
    
    # Raise exception if there are errors
    if validation_results["errors"]:
        error_summary = f"Phát hiện {len(validation_results['errors'])} lỗi biến môi trường Agent: " + "; ".join(validation_results["errors"])
        raise ValueError(error_summary)
    
    logger.info(f"Agent validation hoàn tất: {len(validation_results['required_vars'])} biến bắt buộc OK, {len(validation_results['warnings'])} cảnh báo")
    return validation_results


def get_openai_config() -> Dict[str, Any]:
    """
    Get OpenAI configuration from environment variables with comprehensive validation.
    
    Returns:
        Dict containing OpenAI configuration
    
    Raises:
        ValueError: If required environment variables are missing or invalid
    """
    # Validate environment variables
    try:
        validation_results = validate_agent_environment_variables()
        logger.info("Agent environment variables validated successfully")
    except ValueError as e:
        logger.error(f"Agent environment validation failed: {str(e)}")
        raise
    
    # Extract configuration from validation results
    api_key = validation_results["required_vars"]["OPENAI__API_KEY"]
    model_name = validation_results["optional_vars"]["OPENAI__MODEL_NAME"]
    
    # Always use temperature=0 for consistency as per requirements
    temperature = 0
    
    logger.info(f"OpenAI config: model={model_name}, temperature={temperature}")
    
    return {
        "openai_api_key": api_key,
        "model": model_name,
        "temperature": temperature
    }


def create_system_prompt() -> ChatPromptTemplate:
    """
    Create the system prompt for the Agent with Vietnamese instructions.

    Returns:
        ChatPromptTemplate configured for industry code queries
    """
    system_message = """Bạn là chuyên gia tư vấn về mã ngành nghề kinh doanh Việt Nam (VSIC).

**NGUYÊN TẮC QUAN TRỌNG NHẤT: SAU KHI GỌI 1 CÔNG CỤ VÀ CÓ KẾT QUẢ → TRẢ LỜI NGAY. KHÔNG GỌI THÊM CÔNG CỤ KHÁC.**

Bạn có 4 công cụ:

1. **search_by_code_tool**: Tìm theo mã ngành cụ thể (VD: "01.11", "1130")
2. **search_by_name_tool**: Tìm theo tên ngành cụ thể (VD: "Trồng lúa", "May mặc")  
3. **search_by_keyword_tool**: Tìm theo từ khóa chung hoặc mã ngành con (VD: "nông nghiệp", "các mã dưới 01")
4. **filter_by_system_and_level_tool**: Lọc theo cấp ngành (VD: "cấp 1", "cấp 2")

**QUY TẮC CHỌN CÔNG CỤ:**
- Có mã ngành cụ thể (01.11, 1130) → dùng search_by_code_tool
- Có tên ngành cụ thể hoặc mô tả hoạt động cụ thể → dùng search_by_name_tool  
- Hỏi "mã ngành dưới/con của X", "nhóm nào", "gồm những gì" → dùng search_by_keyword_tool
- Hỏi "cấp 1/2/3/4" → dùng filter_by_system_and_level_tool

**QUAN TRỌNG**: Ưu tiên search_by_name_tool cho tất cả câu hỏi về tên hoạt động cụ thể

**VÍ DỤ CÂU HỎI VỀ MÃ NGÀNH CON:**
- "Ngành A có những nhóm nào?" → dùng search_by_keyword_tool với "A"
- "Mã ngành dưới 01" → dùng search_by_keyword_tool với "01"  
- "Nhóm A gồm những ngành nào?" → dùng search_by_keyword_tool với "A"
- "01 có những mã ngành con nào?" → dùng search_by_keyword_tool với "01"

**VÍ DỤ CÂU HỎI VỀ TÊN NGÀNH/HOẠT ĐỘNG:**
- "Hoạt động ấp trứng và sản xuất giống gia cầm" → dùng search_by_name_tool
- "Trồng lúa có mã ngành gì?" → dùng search_by_name_tool với "Trồng lúa"
- "May mặc thuộc mã ngành nào?" → dùng search_by_name_tool với "May mặc"

**VÍ DỤ CÂU HỎI PHỨC TẠP:**
- "Hoạt động tương tự với xuất khẩu gỗ" → dùng search_by_name_tool với "xuất khẩu gỗ"
- "Ngành nào liên quan đến chế biến thực phẩm" → dùng search_by_name_tool với "chế biến thực phẩm"
- "Các hoạt động về nông nghiệp" → dùng search_by_name_tool với "nông nghiệp"

**CÁCH HOẠT ĐỘNG:**
1. Đọc câu hỏi và phân tích loại câu hỏi
2. Nếu có "hoạt động tương tự với X" → tìm kiếm với từ khóa X
3. Nếu có mã ngành cụ thể → dùng search_by_code_tool
4. Nếu có tên ngành cụ thể → dùng search_by_name_tool
5. Nếu hỏi về mã ngành con → dùng search_by_keyword_tool với mã cha
6. Các trường hợp khác → dùng search_by_keyword_tool
7. TRẢ LỜI NGAY với kết quả

**Cấu trúc mã ngành:**
- Cấp 1: A, B, C... (nhóm lớn) - VD: A = "NÔNG NGHIỆP, LÂM NGHIỆP VÀ THUỶ SẢN"
- Cấp 2: 01, 02, 03... (ngành) - VD: 01 = "Nông nghiệp và hoạt động dịch vụ có liên quan"
- Cấp 3: 011, 012... (phân ngành) - VD: 011 = "Trồng cây hàng năm"
- Cấp 4: 0111, 01110... (hoạt động cụ thể) - VD: 01110 = "Trồng lúa"

**QUAN TRỌNG**: Khi hỏi về "nhóm A có những gì", "ngành A gồm gì" → tìm các mã cấp 2 thuộc A (01, 02, 03...)

Trả lời bằng tiếng Việt, ngắn gọn và rõ ràng."""

    prompt = ChatPromptTemplate.from_messages([
        ("system", system_message),
        MessagesPlaceholder(variable_name="chat_history"),
        ("human", "{input}"),
        MessagesPlaceholder(variable_name="agent_scratchpad"),
    ])

    return prompt



def initialize_agent() -> AgentExecutor:
    """
    Initialize the LangChain Agent with OpenAI and tools.
    
    Returns:
        Configured AgentExecutor ready for processing queries
    
    Raises:
        ValueError: If OpenAI configuration is invalid
        Exception: If agent initialization fails
    """
    global llm, agent_executor
    
    try:
        # Get OpenAI configuration
        config = get_openai_config()
        logger.info(f"Initializing agent with model: {config['model']}")
        
        # Initialize ChatOpenAI
        llm = ChatOpenAI(**config)
        
        # Create system prompt
        prompt = create_system_prompt()
        
        # Import and setup tools
        tools = [
            search_by_code_tool,
            search_by_name_tool,
            search_by_keyword_tool,
            filter_by_system_and_level_tool
        ]
        
        # Create agent
        agent = create_openai_functions_agent(llm, tools, prompt)
        
        # Create agent executor với cấu hình tối ưu
        agent_executor = AgentExecutor(
            agent=agent,
            tools=tools,
            verbose=False,  # Tắt verbose để giảm log
            handle_parsing_errors=True,
            max_iterations=4,  # Giảm xuống 4 để buộc agent trả lời nhanh
            max_execution_time=60  # Giảm xuống 60 giây
        )
        
        logger.info("Agent initialized successfully")
        return agent_executor
        
    except Exception as e:
        logger.error(f"Failed to initialize agent: {str(e)}")
        raise


def format_chat_history(messages: List[Tuple[str, str]]) -> List:
    """
    Format chat history for LangChain agent.
    
    Args:
        messages: List of (role, content) tuples
    
    Returns:
        List of LangChain message objects
    """
    formatted_messages = []
    
    for role, content in messages:
        if role == "human":
            formatted_messages.append(HumanMessage(content=content))
        elif role == "ai":
            formatted_messages.append(AIMessage(content=content))
    
    return formatted_messages


def process_query(user_input: str, history: List[Tuple[str, str]] = None) -> str:
    """
    Process user query with chat history context.
    
    Args:
        user_input: User's question in Vietnamese
        history: Optional chat history as list of (role, content) tuples
    
    Returns:
        Agent's response as string
    
    Raises:
        Exception: If query processing fails
    """
    global agent_executor, chat_history
    
    try:
        # Initialize agent if not already done
        if agent_executor is None:
            initialize_agent()
        
        # Use provided history or global chat_history
        current_history = history if history is not None else chat_history
        
        # Format chat history for LangChain
        formatted_history = format_chat_history(current_history)
        
        logger.info(f"Processing query: '{user_input}' with {len(current_history)} history messages")
        
        # Invoke agent với timeout handling
        try:
            result = agent_executor.invoke({
                "input": user_input,
                "chat_history": formatted_history
            })
        except Exception as agent_error:
            # Xử lý các lỗi cụ thể từ agent
            error_str = str(agent_error).lower()
            if "iteration limit" in error_str or "time limit" in error_str:
                logger.warning(f"Agent stopped due to limits: {str(agent_error)}")
                return "Xin lỗi, câu hỏi này phức tạp quá và tôi cần nhiều thời gian để xử lý. Bạn có thể thử đặt câu hỏi ngắn gọn hơn không?"
            else:
                raise agent_error
        
        # Extract output
        output = result.get("output", "Xin lỗi, tôi không thể xử lý câu hỏi này.")
        
        # Update global chat history if using it
        if history is None:
            chat_history.append(("human", user_input))
            chat_history.append(("ai", output))
            
            # Limit chat history to last 10 messages (5 exchanges)
            if len(chat_history) > 10:
                chat_history = chat_history[-10:]
        
        logger.info(f"Query processed successfully, response length: {len(output)}")
        return output
        
    except Exception as e:
        error_msg = f"Lỗi khi xử lý câu hỏi: {str(e)}"
        logger.error(f"Error processing query '{user_input}': {str(e)}")
        
        # Return error in JSON format
        error_response = {
            "type": "error",
            "message": "Xin lỗi, đã xảy ra lỗi khi xử lý câu hỏi của bạn. Vui lòng thử lại."
        }
        return json.dumps(error_response, ensure_ascii=False)


def parse_agent_output(output: str) -> Dict[str, Any]:
    """
    Parse and validate agent output to ensure it's valid JSON.
    
    Args:
        output: Raw output from agent
    
    Returns:
        Parsed JSON dict or error dict if parsing fails
    """
    try:
        # Try to parse as JSON first
        if output.strip().startswith('{') and output.strip().endswith('}'):
            return json.loads(output)
        
        # If not JSON, wrap in a response format
        return {
            "type": "text_response",
            "message": output
        }
        
    except json.JSONDecodeError as e:
        logger.warning(f"Failed to parse agent output as JSON: {str(e)}")
        return {
            "type": "text_response", 
            "message": output
        }
    except Exception as e:
        logger.error(f"Error parsing agent output: {str(e)}")
        return {
            "type": "error",
            "message": "Lỗi khi xử lý phản hồi từ hệ thống."
        }


def get_agent_info() -> Dict[str, Any]:
    """
    Get information about the current agent configuration.
    
    Returns:
        Dict containing agent configuration info
    """
    global llm, agent_executor
    
    return {
        "agent_initialized": agent_executor is not None,
        "llm_initialized": llm is not None,
        "model_name": os.getenv("OPENAI__MODEL_NAME", "gpt-4o-mini"),
        "chat_history_length": len(chat_history),
        "available_tools": [
            "search_by_code_tool",
            "search_by_name_tool",
            "search_by_keyword_tool", 
            "filter_by_system_and_level_tool"
        ]
    }


def clear_chat_history():
    """
    Clear the global chat history.
    """
    global chat_history
    chat_history = []
    logger.info("Chat history cleared")


# Initialize agent on module import
try:
    initialize_agent()
    logger.info("mn_agent module loaded successfully")
except Exception as e:
    logger.error(f"Failed to initialize mn_agent on import: {str(e)}")
    # Don't raise here to allow module to load, agent will be initialized on first use