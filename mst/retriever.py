import os
# PINECONE (COMMENTED - Chuyển sang Qdrant)
# from pinecone import Pinecone as PineconeClient
# from langchain_pinecone import Pinecone

# QDRANT (MỚI)
from qdrant_client import QdrantClient
from langchain_qdrant import QdrantVectorStore

def get_mst_retriever(embedding):
    """
    Khởi tạo Retriever cho dữ liệu MST bằng Qdrant
    """
    # ===== QDRANT (MỚI) =====
    QDRANT_URL = os.getenv("QDRANT_URL")
    COLLECTION_NAME = os.getenv("QDRANT_COLLECTION_NAME_MST", "masothue")

    if not QDRANT_URL:
        print("⚠️ Thiếu QDRANT_URL trong biến môi trường")
        return None

    try:
        client = QdrantClient(url=QDRANT_URL)
    except Exception as e:
        print(f"❌ Lỗi kết nối Qdrant MST: {e}")
        return None

    try:
        # Thử scroll để kiểm tra collection
        result = client.scroll(
            collection_name=COLLECTION_NAME,
            limit=1,
            with_payload=False,
            with_vectors=False
        )
        # Nếu scroll thành công, collection tồn tại
    except Exception as e:
        print(f"⚠️ Collection MST '{COLLECTION_NAME}' chưa tồn tại trên Qdrant: {e}")
        return None

    # Kiểm tra số lượng points (cho phép rỗng để test)
    collection_info = client.get_collection(COLLECTION_NAME)
    if collection_info.points_count == 0:
        print(f"⚠️ Collection MST '{COLLECTION_NAME}' đang rỗng (0 documents)")
        # Vẫn trả về retriever để có thể test, nhưng sẽ không tìm thấy gì
    else:
        print(f"✅ Collection MST '{COLLECTION_NAME}' có {collection_info.points_count} documents")

    vectordb = QdrantVectorStore(
        client=client,
        collection_name=COLLECTION_NAME,
        embedding=embedding,
    )

    return vectordb.as_retriever(search_kwargs={"k": 5})

    # ===== PINECONE (COMMENTED) =====
    # QDRANT_URL = os.getenv("QDRANT_URL")
    # COLLECTION_NAME = os.getenv("QDRANT_COLLECTION_NAME_MST", "mst_data")
    # 
    # if not QDRANT_URL:
    #     print("⚠️ Thiếu QDRANT_URL trong biến môi trường")
    #     return None
    # 
    # try:
    #     client = QdrantClient(url=QDRANT_URL)
    # except Exception as e:
    #     print(f"❌ Lỗi kết nối Qdrant MST: {e}")
    #     return None
    # 
    # collections = client.get_collections()
    # collection_names = [col.name for col in collections.collections]
    # 
    # if COLLECTION_NAME not in collection_names:
    #     print(f"⚠️ Collection MST '{COLLECTION_NAME}' chưa tồn tại trên Qdrant.")
    #     return None
    # 
    # vectordb = QdrantVectorStore(
    #     client=client,
    #     collection_name=COLLECTION_NAME,
    #     embedding=embedding,
    # )
    # 
    # return vectordb.as_retriever(search_kwargs={"k": 5})