import os
from pinecone import Pinecone as PineconeClient
from langchain_pinecone import Pinecone

def get_mst_retriever(embedding):
    PINECONE_MST_INDEX = os.getenv("PINECONE_INDEX_NAME_MST")
    PINECONE_API_KEY = os.getenv("PINECONE_API_KEY")

    if not PINECONE_MST_INDEX:
        return None

    pc = PineconeClient(api_key=PINECONE_API_KEY)

    if PINECONE_MST_INDEX not in pc.list_indexes().names():
        return None

    index = pc.Index(PINECONE_MST_INDEX)
    vectordb = Pinecone(index=index, embedding=embedding, text_key="text")

    return vectordb.as_retriever(search_kwargs={"k": 5})
