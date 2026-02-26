import os
# PINECONE (COMMENTED - Chuyển sang Qdrant)
# from pinecone import Pinecone as PineconeClient
# from langchain_pinecone import Pinecone

# QDRANT (MỚI)
from qdrant_client import QdrantClient
from langchain_qdrant import QdrantVectorStore
from langchain_openai import OpenAIEmbeddings


def load_vsic_2018_retriever(embedding: OpenAIEmbeddings):
    """
    Load Qdrant retriever cho VSIC 2018 (Mã ngành 2018)
    """
    # ===== QDRANT (MỚI) =====
    qdrant_url = os.getenv("QDRANT_URL")
    index_name = os.getenv("QDRANT_COLLECTION_NAME_MSN_2018", "masonganh")

    if not qdrant_url:
        raise RuntimeError("Thiếu cấu hình QDRANT_URL cho VSIC 2018")

    try:
        client = QdrantClient(
            url=qdrant_url,
            api_key=None,
            timeout=60
        )
    except Exception as e:
        raise RuntimeError(f"Lỗi kết nối Qdrant VSIC 2018: {e}")

    if not client.collection_exists(index_name):
        raise RuntimeError(f"Qdrant collection VSIC 2018 '{index_name}' không tồn tại")

    collection_info = client.get_collection(index_name)
    
    if collection_info.points_count == 0:
        print(f"⚠️ Qdrant collection VSIC 2018 '{index_name}' đang rỗng (0 documents)")
        # Vẫn trả về retriever để có thể test
    else:
        print(f"✅ Qdrant collection VSIC 2018 '{index_name}' có {collection_info.points_count} documents")

    vectordb = QdrantVectorStore(
        client=client,
        collection_name=index_name,
        embedding=embedding,
    )

    retriever = vectordb.as_retriever(search_kwargs={"k": 10})
    return retriever

    # ===== PINECONE (COMMENTED) =====
    # pinecone_api_key = os.getenv("PINECONE_API_KEY")
    # index_name = os.getenv("PINECONE_INDEX_NAME_MSN_2018")
    # 
    # if not pinecone_api_key or not index_name:
    #     raise RuntimeError("Thiếu cấu hình Pinecone cho VSIC 2018")
    # 
    # pc = PineconeClient(api_key=pinecone_api_key)
    # 
    # if index_name not in pc.list_indexes().names():
    #     raise RuntimeError(f"Pinecone index VSIC 2018 '{index_name}' không tồn tại")
    # 
    # index = pc.Index(index_name)
    # stats = index.describe_index_stats()
    # 
    # if stats["total_vector_count"] == 0:
    #     raise RuntimeError("Pinecone index VSIC 2018 rỗng")
    # 
    # vectordb = Pinecone(
    #     index=index,
    #     embedding=embedding,
    #     text_key="text"
    # )
    # 
    # retriever = vectordb.as_retriever(search_kwargs={"k": 10})
    # return retriever
