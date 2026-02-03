import os
import sys
import time
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain.agents import AgentExecutor, create_openai_functions_agent
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

# Import module
try:
    from .backend import IIPMapBackend
    from .tools import search_flexible_tool, search_single_zone_tool, EXCEL_PATH, GEOJSON_PATH
except ImportError:
    from backend import IIPMapBackend
    from tools import search_flexible_tool, search_single_zone_tool, EXCEL_PATH, GEOJSON_PATH

load_dotenv()
MY_API_KEY = os.getenv("OPENAI__API_KEY")

if not MY_API_KEY:
    print("❌ LỖI: Chưa cấu hình OPENAI_API_KEY")
    sys.exit(1)

# Load danh sách cột (Cắt bớt nếu quá dài để tiết kiệm Token)
try:
    temp_backend = IIPMapBackend(EXCEL_PATH, GEOJSON_PATH)
    full_cols = temp_backend.get_all_columns()
    # Chỉ lấy 20 cột đầu tiên để tránh tràn Token và rate limit
    ALL_COLUMNS = ", ".join(full_cols[:20]) 
    if len(full_cols) > 20:
        ALL_COLUMNS += "..."
except Exception as e:
    ALL_COLUMNS = "Tên, Tỉnh/Thành phố, Giá thuê đất, Tổng diện tích..."

tools = [search_flexible_tool, search_single_zone_tool]

# Prompt - Completely rewritten with proper escaping
system_message = f"""Bạn là chuyên gia tư vấn IIPMap.
Dữ liệu Excel có các cột: [{ALL_COLUMNS}]

TOOLS:
1. search_flexible_tool(filter_json, view_option) - Tìm kiếm và vẽ biểu đồ nhiều KCN/CCN
2. search_single_zone_tool(zone_name) - Tìm thông tin chi tiết 1 KCN/CCN cụ thể

QUY TẮC QUAN TRỌNG NHẤT - XỬ LÝ NGỮ CẢNH (CHAT HISTORY):
1. Trước khi gọi tool, HÃY XEM LẠI chat_history (lịch sử chat).
2. Nếu câu hỏi hiện tại là câu hỏi nối tiếp:
   - BẮT BUỘC PHẢI GIỮ LẠI các điều kiện lọc (numeric_filters, zone_type) của câu trước đó.
   - CHỈ THAY ĐỔI địa điểm nếu người dùng nhắc đến địa điểm mới.

QUY TẮC NHẬN DIỆN LOẠI TỰ ĐỘNG - CỰC KỲ QUAN TRỌNG:
1. KHU CÔNG NGHIỆP (KCN):
   - "khu công nghiệp", "KCN", "khu CN", "industrial park", "IP"
   - → zone_type: "KCN"

2. CỤM CÔNG NGHIỆP (CCN):
   - "cụm công nghiệp", "CCN", "cụm CN", "industrial cluster", "cluster"
   - → zone_type: "CCN"

3. CẢ HAI (ALL):
   - "khu công nghiệp và cụm công nghiệp", "KCN và CCN", "tất cả"
   - Không nhắc cụ thể loại nào
   - → zone_type: "ALL"

CÁCH CHỌN TOOL:
- "thông tin về KCN X" → search_single_zone_tool("X")
- "danh sách KCN/CCN" → search_flexible_tool
- "so sánh KCN/CCN" → search_flexible_tool
- "vẽ biểu đồ" → search_flexible_tool

PARAMETERS:
search_flexible_tool:
1. filter_json: Map câu hỏi thành JSON string với zone_type tự động
2. view_option: "list" (mặc định), "chart_price", "chart_area"

Hãy trả lời ngắn gọn, súc tích.
"""

prompt = ChatPromptTemplate.from_messages([
    ("system", system_message),
    MessagesPlaceholder(variable_name="chat_history"), # <-- Dòng này bắt buộc phải có
    ("human", "{input}"),
    MessagesPlaceholder(variable_name="agent_scratchpad"),
])

# === THAY ĐỔI Ở ĐÂY: DÙNG GPT-4o-mini HOẶC THÊM MAX RETRIES ===
llm = ChatOpenAI(
    model="gpt-4o-mini", 
    temperature=0, 
    openai_api_key=MY_API_KEY,
    max_retries=3, # Tăng từ 2 lên 3
    request_timeout=60 # Tăng từ 15 lên 60 giây
)

agent = create_openai_functions_agent(llm, tools, prompt)
agent_executor = AgentExecutor(
    agent=agent, 
    tools=tools, 
    verbose=True,
    max_execution_time=120,  # Tăng từ 20 lên 120 giây (2 phút)
    max_iterations=5,        # Tăng từ 3 lên 5 lần thử
    early_stopping_method="generate"
)

def run():
    print(f"🤖 IIP AGENT (Auto Retry Mode) ĐANG CHẠY...")
    chat_history = []
    
    while True:
        try:
            user_input = input("\nBạn: ")
            if user_input.lower() in ["exit", "quit"]: break
            
            # GIỚI HẠN LỊCH SỬ CHAT: Chỉ giữ 4 câu gần nhất để tiết kiệm Token
            if len(chat_history) > 4:
                chat_history = chat_history[-4:]

            # CƠ CHẾ THỬ LẠI THỦ CÔNG (BACKOFF)
            max_retries = 3
            for attempt in range(max_retries):
                try:
                    result = agent_executor.invoke({
                        "input": user_input,
                        "chat_history": chat_history
                    })
                    print(f"Agent: {result['output']}")
                    chat_history.append(("human", user_input))
                    chat_history.append(("ai", result['output']))
                    break # Thành công thì thoát vòng lặp
                except Exception as e:
                    if "429" in str(e) or "Rate limit" in str(e):
                        wait_time = (attempt + 1) * 2 # Chờ 2s, 4s, 6s...
                        print(f"⚠️ Quá tải (Rate Limit). Đang chờ {wait_time}s để thử lại...")
                        time.sleep(wait_time)
                    else:
                        raise e # Lỗi khác thì báo luôn

        except Exception as e:
            print(f"❌ Lỗi không thể xử lý: {e}")

if __name__ == "__main__":
    run()