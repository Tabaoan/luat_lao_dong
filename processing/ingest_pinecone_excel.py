# ===================== IMPORTS =====================
import os
import time
import pandas as pd
from typing import List, Dict, Any
from dotenv import load_dotenv

from langchain.schema import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_openai import OpenAIEmbeddings
from langchain_pinecone import Pinecone
from pinecone import Pinecone as PineconeClient, PodSpec

# ===================== CẤU HÌNH =====================
load_dotenv(override=True)

OPENAI_API_KEY = os.getenv("OPENAI__API_KEY")
OPENAI_EMBEDDING_MODEL = os.getenv("OPENAI__EMBEDDING_MODEL")
PINECONE_API_KEY = os.getenv("PINECONE_API_KEY")
PINECONE_ENVIRONMENT = os.getenv("PINECONE_ENVIRONMENT")
PINECONE_INDEX_NAME = os.getenv("PINECONE_INDEX_NAME_MST", "excel-index") 

EXCEL_FOLDER = r"C:\Users\tabao\OneDrive\Desktop\cong_viec_lam\masothue"  
EMBEDDING_DIM = 3072
BATCH_SIZE = 50

# ===================== KHỞI TẠO =====================
print("🔧 Đang khởi tạo Pinecone và Embeddings...")

if not all([OPENAI_API_KEY, PINECONE_API_KEY, PINECONE_ENVIRONMENT, PINECONE_INDEX_NAME]):
    print("❌ Lỗi: Thiếu biến môi trường (API key hoặc tên index)!")
    exit(1)

pc = PineconeClient(api_key=PINECONE_API_KEY)
emb = OpenAIEmbeddings(api_key=OPENAI_API_KEY, model=OPENAI_EMBEDDING_MODEL)

print("✅ Đã khởi tạo thành công!\n")

# ===================== HÀM HỖ TRỢ =====================
def get_excel_files(folder_path: str) -> List[str]:
    """Lấy danh sách file Excel/CSV"""
    if not os.path.exists(folder_path):
        print(f"⚠️ Thư mục không tồn tại: {folder_path}")
        return []

    files = []
    for f in os.listdir(folder_path):
        if f.lower().endswith((".xlsx", ".xls", ".csv")):
            files.append(os.path.join(folder_path, f))
    return files


def create_or_get_index(index_name: str) -> Any:
    """Tạo hoặc lấy Pinecone index"""
    if index_name not in pc.list_indexes().names():
        print(f"🛠️ Tạo mới Pinecone Index: {index_name}")
        pc.create_index(
            name=index_name,
            dimension=EMBEDDING_DIM,
            metric="cosine",
            spec=PodSpec(environment=PINECONE_ENVIRONMENT),
        )
        time.sleep(5)
    return pc.Index(index_name)


def load_and_chunk_excel(file_path: str) -> List[Document]:
    """Đọc file Excel và chia nhỏ nội dung"""
    filename = os.path.basename(file_path)
    print(f"📂 Đang đọc: {filename}")

    docs = []
    try:
        if file_path.lower().endswith(".csv"):
            df = pd.read_csv(file_path)
        else:
            df = pd.read_excel(file_path)

        # Chuyển mỗi dòng thành Document
        for i, row in df.iterrows():
            text = "\n".join([f"{col}: {val}" for col, val in row.items() if pd.notna(val)])
            if text.strip():
                docs.append(Document(
                    page_content=text,
                    metadata={"source": filename, "row": i + 1}
                ))

        # Chunk nội dung
        splitter = RecursiveCharacterTextSplitter(
            chunk_size= 3000,
            chunk_overlap= 300,
            separators=["\n\n", "\n", ". ", " ", ""],
        )
        chunks = splitter.split_documents(docs)

        for i, d in enumerate(chunks):
            d.metadata["chunk_id"] = i

        print(f"✅ {filename}: {len(chunks)} chunks từ {len(df)} hàng.")
        return chunks

    except Exception as e:
        print(f"❌ Lỗi đọc {filename}: {e}")
        return []


def upload_to_pinecone(all_docs: List[Document], index_name: str):
    """Đẩy dữ liệu lên Pinecone"""
    if not all_docs:
        print("⚠️ Không có dữ liệu để nạp.")
        return

    print(f"🚀 Đang nạp {len(all_docs)} documents vào Pinecone Index: {index_name}")
    index = create_or_get_index(index_name)

    total_batches = (len(all_docs) + BATCH_SIZE - 1) // BATCH_SIZE
    vectordb = None

    for i in range(0, len(all_docs), BATCH_SIZE):
        batch = all_docs[i : i + BATCH_SIZE]
        batch_num = i // BATCH_SIZE + 1
        print(f"   📦 Batch {batch_num}/{total_batches} ({len(batch)} docs)...", end=" ")

        if i == 0:
            vectordb = Pinecone.from_documents(batch, index_name=index_name, embedding=emb)
        else:
            vectordb.add_documents(batch)

        print("✓")
        time.sleep(1)

    print("✅ Hoàn tất đẩy dữ liệu lên Pinecone!")


# ===================== MAIN =====================
if __name__ == "__main__":
    excel_files = get_excel_files(EXCEL_FOLDER)
    if not excel_files:
        print(f"❌ Không tìm thấy file Excel nào trong thư mục: {EXCEL_FOLDER}")
        exit(1)

    print(f"📊 Tìm thấy {len(excel_files)} file Excel:")
    for f in excel_files:
        print(f"   - {os.path.basename(f)}")
    print()

    all_docs = []
    for f in excel_files:
        chunks = load_and_chunk_excel(f)
        all_docs.extend(chunks)

    upload_to_pinecone(all_docs, PINECONE_INDEX_NAME)

    print("\n🎉 Hoàn thành nạp dữ liệu Excel vào Pinecone!")
