import os
from qdrant_client import QdrantClient
from langchain_qdrant import QdrantVectorStore

def get_mst_retriever(embedding):
    """
    Khởi tạo Retriever cho dữ liệu MST bằng Qdrant
    """
    # 1. Lấy cấu hình từ biến môi trường
    QDRANT_URL = os.getenv("QDRANT_URL")
    #QDRANT_API_KEY = os.getenv("QDRANT_API_KEY")
    
    # Tên collection riêng cho MST (Bạn nên thêm dòng này vào file .env)
    # Ví dụ: QDRANT_COLLECTION_NAME_MST=mst_data
    COLLECTION_NAME = os.getenv("QDRANT_COLLECTION_NAME_MST", "mst_data")

    if not QDRANT_URL:
        print("⚠️ Thiếu QDRANT_URL trong biến môi trường")
        return None

    # 2. Khởi tạo Qdrant Client
    try:
        client = QdrantClient(
            url=QDRANT_URL,
            api_key=None,
            timeout=60
        )
    except Exception as e:
        print(f"❌ Lỗi kết nối Qdrant MST: {e}")
        return None

    # 3. Kiểm tra xem Collection có tồn tại không
    if not client.collection_exists(COLLECTION_NAME):
        print(f"⚠️ Collection MST '{COLLECTION_NAME}' chưa tồn tại trên Qdrant.")
        return None

    # 4. Khởi tạo VectorStore
    # Lưu ý: QdrantVectorStore mặc định dùng 'page_content' làm key nội dung.
    # Nếu dữ liệu cũ của bạn dùng key khác, hãy thêm tham số content_payload_key="..."
    vectordb = QdrantVectorStore(
        client=client,
        collection_name=COLLECTION_NAME,
        embedding=embedding,
    )

    # 5. Trả về Retriever
    return vectordb.as_retriever(search_kwargs={"k": 5})