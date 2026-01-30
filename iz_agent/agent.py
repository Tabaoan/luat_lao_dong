import os
import sys
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain.agents.factory import create_agent

# Xử lý Import linh hoạt (để chạy được cả khi đứng từ root hoặc trong folder con)
try:
    from .backend import IIPMapBackend
    from .tools import search_flexible_tool, EXCEL_PATH, GEOJSON_PATH
except ImportError:
    # Fallback nếu chạy trực tiếp file này để test
    from backend import IIPMapBackend
    from tools import search_flexible_tool, EXCEL_PATH, GEOJSON_PATH

load_dotenv()
MY_API_KEY = os.getenv("OPENAI__API_KEY")

if not MY_API_KEY:
    print("❌ LỖI: Chưa cấu hình OPENAI_API_KEY trong file .env")
    # Không dùng sys.exit(1) ở đây để tránh làm sập cả app chính nếu thiếu key
    # Thay vào đó, agent_executor sẽ là None
    agent_executor = None
else:
    # 1. Load danh sách cột (Dùng để nhắc Agent biết dữ liệu có gì)
    try:
        temp_backend = IIPMapBackend(EXCEL_PATH, GEOJSON_PATH)
        full_cols = temp_backend.get_all_columns()
        # Lấy 50 cột đầu để tránh quá tải token, ưu tiên các cột quan trọng
        ALL_COLUMNS = ", ".join(full_cols[:50]) 
        if len(full_cols) > 50:
            ALL_COLUMNS += "..."
    except Exception as e:
        print(f"⚠️ Cảnh báo: Không đọc được file Excel để lấy cột ({e}). Dùng cột mặc định.")
        ALL_COLUMNS = "Tên, Tỉnh/Thành phố, Giá thuê đất, Tổng diện tích, Mật độ xây dựng..."

    # 2. Định nghĩa Tools
    tools = [search_flexible_tool]

    # 3. System Prompt (Đã tối ưu cho Context)
    system_message = f"""Bạn là chuyên gia tư vấn Bất động sản Công nghiệp (IIPMap).
    Dữ liệu Excel có các cột: [{ALL_COLUMNS}]

    QUY TẮC QUAN TRỌNG NHẤT - XỬ LÝ NGỮ CẢNH (CHAT HISTORY):
    1. Luôn xem lại `chat_history` trước khi gọi tool.
    2. Nếu câu hỏi nối tiếp (Ví dụ: "Còn ở Hưng Yên?", "Thế Bắc Ninh giá bao nhiêu?"):
       - GIỮ LẠI các bộ lọc (numeric_filters, zone_type) của câu trước.
       - CHỈ THAY ĐỔI địa điểm hoặc thuộc tính mới được nhắc đến.
       
       VÍ DỤ:
       - User trước: "Tìm KCN ở Ninh Bình dưới 100ha" -> Tool: {{ "Tỉnh/Thành phố": "Ninh Bình", "numeric_filters": [{{"col": "area", "op": "<", "val": 100}}] }}
       - User hiện tại: "Còn Hưng Yên thì sao?"
       - ACTION: {{ "Tỉnh/Thành phố": "Hưng Yên", "numeric_filters": [{{"col": "area", "op": "<", "val": 100}}] }} (Giữ nguyên filter diện tích)

    QUY TẮC DÙNG TOOL `search_flexible_tool`:
    - `filter_json`: Map câu hỏi thành JSON string.
       + Tìm văn bản: {{ "Tỉnh/Thành phố": "Bắc Ninh", "Chủ đầu tư": "..." }}
       + LỌC SỐ: Dùng "numeric_filters". Format: {{ "col": "price"/"area", "op": "<"/">", "val": 80 }}
    - `view_option`: "list" (mặc định), "full", "chart_price", "chart_area".

    Hãy trả lời ngắn gọn, tập trung vào số liệu tìm được.
    """

    # 4. Khởi tạo LLM
    llm = ChatOpenAI(
        model="gpt-4o-mini", 
        temperature=0, 
        openai_api_key=MY_API_KEY,
        max_retries=3, 
        request_timeout=30 
    )

    # 5. Tạo Agent (langchain v0.3.x API)
    agent_executor = create_agent(
        model=llm,
        tools=tools,
        system_prompt=system_message
    )

# --- Phần này chỉ chạy khi bạn test riêng file này, không ảnh hưởng khi import vào app.py ---
if __name__ == "__main__":
    if agent_executor is None:
        print("Không thể chạy Agent vì thiếu API Key.")
    else:
        print("🚀 IIP AGENT CLI MODE (Test riêng biệt)")
        messages = []
        while True:
            try:
                from langchain_core.messages import HumanMessage
                u_input = input("\nBạn: ")
                if u_input.lower() in ["quit", "exit"]: break
                
                # Sử dụng API mới langchain v0.3.x
                messages.append(HumanMessage(content=u_input))
                result = agent_executor.invoke({"messages": messages})
                
                # result['messages'] chứa tất cả messages kể từ cuối
                print(f"Agent: {result['messages'][-1].content}")
                messages = result['messages']
                
            except Exception as e:
                print(f"Lỗi: {e}")
                import traceback
                traceback.print_exc()