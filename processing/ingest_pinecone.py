# ===================== IMPORTS =====================
import os
import time
from typing import List, Dict, Any
from pathlib import Path

from dotenv import load_dotenv
load_dotenv(override=True)

from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_openai import OpenAIEmbeddings
from langchain_pinecone import Pinecone 
from pinecone import Pinecone as PineconeClient, PodSpec
from langchain_community.document_loaders import PyMuPDFLoader

# ===================== CẤU HÌNH =====================
OPENAI_API_KEY = os.getenv("OPENAI__API_KEY")
OPENAI_EMBEDDING_MODEL = os.getenv("OPENAI__EMBEDDING_MODEL")
PINECONE_API_KEY = os.getenv("PINECONE_API_KEY")
PINECONE_ENVIRONMENT = os.getenv("PINECONE_ENVIRONMENT")
PINECONE_INDEX_NAME = os.getenv("PINECONE_INDEX_NAME")

EMBEDDING_DIM = 3072  
PDF_FOLDER = r"C:\Users\tabao\Downloads\qd36" 
BATCH_SIZE = 30  

# ===================== KHỞI TẠO =====================
print("🔧 Đang khởi tạo Pinecone Client và Embedding...")

if not all([OPENAI_API_KEY, PINECONE_API_KEY, PINECONE_ENVIRONMENT, PINECONE_INDEX_NAME]):
    print("❌ LỖI: Thiếu biến môi trường bắt buộc!")
    print(f"   OPENAI_API_KEY: {'✅' if OPENAI_API_KEY else '❌'}")
    print(f"   PINECONE_API_KEY: {'✅' if PINECONE_API_KEY else '❌'}")
    print(f"   PINECONE_ENVIRONMENT: {'✅' if PINECONE_ENVIRONMENT else '❌'}")
    print(f"   PINECONE_INDEX_NAME: {'✅' if PINECONE_INDEX_NAME else '❌'}")
    exit(1)

# Khởi tạo clients
pc = PineconeClient(api_key=PINECONE_API_KEY)
emb = OpenAIEmbeddings(api_key=OPENAI_API_KEY, model=OPENAI_EMBEDDING_MODEL)

print("✅ Đã khởi tạo thành công!\n")

# ===================== HÀM HỖ TRỢ =====================

def get_pdf_files_from_folder(folder_path: str) -> List[str]:
    """Lấy tất cả file PDF trong folder"""
    if not os.path.exists(folder_path):
        print(f"⚠️ Folder không tồn tại: {folder_path}")
        return []
    
    pdf_files = []
    for file in os.listdir(folder_path):
        if file.lower().endswith('.pdf'):
            full_path = os.path.join(folder_path, file)
            pdf_files.append(full_path)
    
    return sorted(pdf_files)


def get_existing_sources_from_index(index_name: str) -> set:
    """Lấy danh sách file đã có trong Pinecone Index"""
    try:
        if index_name not in pc.list_indexes().names():
            return set()
        
        index = pc.Index(index_name)
        stats = index.describe_index_stats()
        
        if stats['total_vector_count'] == 0:
            return set()
        
        # Query để lấy metadata
        # Tạo vector zero để query
        dummy_query = [0.0] * EMBEDDING_DIM
        results = index.query(
            vector=dummy_query, 
            top_k=10,  # Lấy nhiều để đảm bảo có tất cả sources
            include_metadata=True
        )
        
        sources = set()
        for match in results.get('matches', []):
            if 'metadata' in match and 'source' in match['metadata']:
                sources.add(match['metadata']['source'])
        
        return sources
        
    except Exception as e:
        print(f"⚠️ Lỗi khi lấy danh sách file từ Index: {e}")
        return set()


def create_or_get_index(index_name: str, force_recreate: bool = False) -> Any:
    """Tạo hoặc lấy Pinecone Index"""
    
    # Xóa index nếu force_recreate = True
    if force_recreate:
        print(f"🗑️ Đang xóa Index '{index_name}' (nếu tồn tại)...")
        if index_name in pc.list_indexes().names():
            pc.delete_index(index_name)
            print(f"✅ Đã xóa Index '{index_name}'")
            time.sleep(2)  # Đợi Pinecone xử lý
    
    # Tạo index nếu chưa tồn tại
    if index_name not in pc.list_indexes().names():
        print(f"🛠️ Đang tạo Index '{index_name}'...")
        pc.create_index(
            name=index_name,
            dimension=EMBEDDING_DIM,
            metric='cosine',
            spec=PodSpec(environment=PINECONE_ENVIRONMENT)
        )
        print(f"✅ Đã tạo Index '{index_name}'")
        time.sleep(5)  # Đợi index sẵn sàng
    
    return pc.Index(index_name)


def load_and_chunk_pdf(file_path: str) -> List:
    """Đọc và chunk một file PDF"""
    filename = os.path.basename(file_path)
    
    try:
        # Load PDF
        loader = PyMuPDFLoader(file_path)
        docs = loader.load()
        
        # Gắn metadata
        for i, doc in enumerate(docs):
            if doc.metadata is None:
                doc.metadata = {}
            doc.metadata["source"] = filename
            doc.metadata["page"] = i + 1
        
        # Chunk documents
        splitter = RecursiveCharacterTextSplitter(
            chunk_size=4000,  
            chunk_overlap=300,
            separators=["\n\n", "\n", ". ", " ", ""]
        )
        split_docs = splitter.split_documents(docs)
        
        # Gắn chunk index
        for i, doc in enumerate(split_docs):
            doc.metadata["chunk_id"] = i
        
        return split_docs
        
    except Exception as e:
        print(f"❌ Lỗi khi load file {filename}: {e}")
        return []


def ingest_documents_to_pinecone(
    pdf_paths: List[str],
    index_name: str,
    force_reload: bool = False
) -> Dict[str, Any]:
    """
    Nạp documents vào Pinecone Index
    
    Args:
        pdf_paths: Danh sách đường dẫn file PDF
        index_name: Tên Pinecone Index
        force_reload: Nếu True, xóa và nạp lại toàn bộ
    
    Returns:
        Dictionary chứa thông tin kết quả
    """
    
    print("=" * 70)
    print("🚀 BẮT ĐẦU QUÁ TRÌNH NẠP TÀI LIỆU VÀO PINECONE")
    print("=" * 70)
    print(f"📁 Folder: {PDF_FOLDER}")
    print(f"📚 Tổng số file PDF: {len(pdf_paths)}")
    print(f"☁️  Index Name: {index_name}")
    print(f"🔄 Force Reload: {force_reload}\n")
    
    # 1. Tạo hoặc lấy Index
    index = create_or_get_index(index_name, force_recreate=force_reload)
    
    # 2. Lấy danh sách file đã có
    if not force_reload:
        print("📊 Đang kiểm tra file đã có trong Index...")
        existing_sources = get_existing_sources_from_index(index_name)
        print(f"   ✓ Tìm thấy {len(existing_sources)} file đã có")
        if existing_sources:
            print(f"   └─ {', '.join(sorted(existing_sources))}\n")
    else:
        existing_sources = set()
        print("📊 Chế độ force reload - Sẽ nạp toàn bộ file\n")
    
    # 3. Xác định file cần nạp
    target_files = {os.path.basename(p): p for p in pdf_paths}
    
    if force_reload:
        files_to_load = target_files
        print(f"📥 Sẽ nạp {len(files_to_load)} file\n")
    else:
        new_files = {name: path for name, path in target_files.items() 
                    if name not in existing_sources}
        
        if not new_files:
            print(f"✅ Tất cả {len(target_files)} file đã có trong Index!")
            stats = index.describe_index_stats()
            return {
                "success": True,
                "message": "Không có file mới cần nạp",
                "total_vectors": stats['total_vector_count'],
                "files_processed": 0
            }
        
        files_to_load = new_files
        print(f"📥 Phát hiện {len(new_files)} file mới cần nạp:")
        for name in sorted(new_files.keys()):
            print(f"   + {name}")
        print()
    
    # 4. Load và chunk tất cả file
    print("📖 Đang đọc và chunk documents...")
    all_docs = []
    file_stats = {}
    
    for filename, path in files_to_load.items():
        if not os.path.exists(path):
            print(f"   ⚠️ Không tìm thấy: {path}")
            continue
        
        print(f"   📄 {filename}...", end=" ")
        chunks = load_and_chunk_pdf(path)
        
        if chunks:
            all_docs.extend(chunks)
            file_stats[filename] = len(chunks)
            print(f"✓ {len(chunks)} chunks")
        else:
            print(f"✗ Lỗi")
    
    if not all_docs:
        print("\n⚠️ Không có document nào để nạp!")
        return {
            "success": False,
            "message": "Không có document nào được load thành công",
            "files_processed": 0
        }
    
    print(f"\n📚 Tổng cộng: {len(all_docs)} chunks từ {len(file_stats)} file\n")
    
    # 5. Nạp vào Pinecone theo batch
    print("💾 Đang nạp vào Pinecone Index...")
    print(f"📦 Batch size: {BATCH_SIZE} documents/batch\n")
    
    total_batches = (len(all_docs) + BATCH_SIZE - 1) // BATCH_SIZE
    vectordb = None
    
    try:
        for i in range(0, len(all_docs), BATCH_SIZE):
            batch_num = (i // BATCH_SIZE) + 1
            batch = all_docs[i:i + BATCH_SIZE]
            
            print(f"   📦 Batch {batch_num}/{total_batches} ({len(batch)} docs)...", end=" ")
            
            if i == 0:
                # Batch đầu tiên: Tạo vectordb
                vectordb = Pinecone.from_documents(
                    batch,
                    index_name=index_name,
                    embedding=emb,
                    text_key="text"
                )
            else:
                # Các batch tiếp theo: Thêm vào vectordb
                vectordb.add_documents(batch)
            
            print("✓")
            time.sleep(1)  # Tránh rate limit
        
        print("\n✅ Đã nạp toàn bộ documents thành công!")
        
    except Exception as e:
        print(f"\n❌ Lỗi khi nạp vào Pinecone: {e}")
        return {
            "success": False,
            "message": str(e),
            "files_processed": len(file_stats)
        }
    
    # 6. Thống kê cuối cùng
    stats = index.describe_index_stats()
    
    print("\n" + "=" * 70)
    print("📊 THỐNG KÊ KẾT QUẢ")
    print("=" * 70)
    print(f"✅ Tổng vectors trong Index: {stats['total_vector_count']}")
    print(f"📁 Số file đã xử lý: {len(file_stats)}")
    print(f"📄 Chi tiết:")
    for filename, chunks in sorted(file_stats.items()):
        print(f"   • {filename}: {chunks} chunks")
    print("=" * 70 + "\n")
    
    return {
        "success": True,
        "message": "Nạp tài liệu thành công",
        "total_vectors": stats['total_vector_count'],
        "files_processed": len(file_stats),
        "file_stats": file_stats
    }


# ===================== MAIN =====================
if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Tự động nạp tài liệu PDF vào Pinecone Index"
    )
    parser.add_argument(
        "--force-reload",
        action="store_true",
        help="Xóa và nạp lại toàn bộ (mặc định: chỉ nạp file mới)"
    )
    parser.add_argument(
        "--folder",
        type=str,
        default=PDF_FOLDER,
        help=f"Đường dẫn folder chứa PDF (mặc định: {PDF_FOLDER})"
    )
    
    args = parser.parse_args()
    
    # Lấy danh sách file PDF
    pdf_files = get_pdf_files_from_folder(args.folder)
    
    if not pdf_files:
        print(f"❌ Không tìm thấy file PDF nào trong folder: {args.folder}")
        exit(1)
    
    print(f"📚 Tìm thấy {len(pdf_files)} file PDF:")
    for idx, path in enumerate(pdf_files, 1):
        status = "✅" if os.path.exists(path) else "❌"
        print(f"   {idx}. {status} {os.path.basename(path)}")
    print()
    
    # Xác nhận trước khi thực hiện
    if args.force_reload:
        confirm = input("⚠️  Bạn sắp XÓA và NẠP LẠI toàn bộ Index. Tiếp tục? (yes/no): ")
        if confirm.lower() != "yes":
            print("❌ Đã hủy")
            exit(0)
    
    # Thực hiện nạp tài liệu
    result = ingest_documents_to_pinecone(
        pdf_paths=pdf_files,
        index_name=PINECONE_INDEX_NAME,
        force_reload=args.force_reload
    )
    
    # Hiển thị kết quả
    if result["success"]:
        print("🎉 HOÀN THÀNH!")
    else:
        print("❌ CÓ LỖI XẢY RA!")
        print(f"   Lý do: {result['message']}")
        exit(1)