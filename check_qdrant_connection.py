#!/usr/bin/env python3
"""
Simple diagnostic script to check Qdrant connection and collection status
Run: python check_qdrant_connection.py
"""

import os
import sys
from dotenv import load_dotenv

load_dotenv(override=True)

QDRANT_URL = os.getenv("QDRANT_URL")
QDRANT_COLLECTION_NAME = os.getenv("QDRANT_COLLECTION_NAME", "legal_documents")

print("=" * 80)
print("🔍 QDRANT CONNECTION DIAGNOSTIC")
print("=" * 80)

# 1. Check environment variables
print("\n1️⃣ ENVIRONMENT VARIABLES:")
print(f"   QDRANT_URL = {QDRANT_URL or '❌ NOT SET'}")
print(f"   QDRANT_COLLECTION_NAME = {QDRANT_COLLECTION_NAME}")

if not QDRANT_URL:
    print("\n❌ ERROR: QDRANT_URL is not set!")
    print("   Please set it in your .env file")
    sys.exit(1)

# 2. Try to connect to Qdrant
print("\n2️⃣ TESTING QDRANT CONNECTION:")
try:
    from qdrant_client import QdrantClient
    
    print(f"   Connecting to {QDRANT_URL}...")
    client = QdrantClient(
        url=QDRANT_URL,
        api_key=None,
        timeout=10,
        prefer_grpc=False,
        check_compatibility=False
    )
    print("   ✅ Connected successfully!")
except Exception as e:
    print(f"   ❌ Connection failed: {e}")
    print("\n   💡 SOLUTIONS:")
    print("      1. Check if Qdrant is running:")
    print("         docker ps | grep qdrant")
    print("      2. Start Qdrant with Docker:")
    print("         docker run -p 6333:6333 -p 6334:6334 qdrant/qdrant")
    print("      3. Check QDRANT_URL is correct (e.g., http://localhost:6333)")
    sys.exit(1)

# 3. Check collections
print("\n3️⃣ CHECKING COLLECTIONS:")
try:
    collections = client.get_collections()
    print(f"   Total collections: {len(collections.collections) if collections.collections else 0}")
    
    if collections.collections:
        print("   Available collections:")
        for col in collections.collections:
            info = client.get_collection(col.name)
            print(f"      • {col.name}")
            print(f"        - Points: {info.points_count}")
            print(f"        - Dimension: {info.config.params.vectors.size if hasattr(info.config.params.vectors, 'size') else 'N/A'}")
    else:
        print("   ⚠️ No collections found")
except Exception as e:
    print(f"   ❌ Error listing collections: {e}")
    sys.exit(1)

# 4. Check our target collection
print(f"\n4️⃣ CHECKING TARGET COLLECTION: '{QDRANT_COLLECTION_NAME}'")
try:
    exists = client.collection_exists(QDRANT_COLLECTION_NAME)
    if exists:
        info = client.get_collection(QDRANT_COLLECTION_NAME)
        print(f"   ✅ Collection EXISTS")
        print(f"      - Points: {info.points_count}")
        print(f"      - Dimension: {info.config.params.vectors.size if hasattr(info.config.params.vectors, 'size') else 'N/A'}")
        
        if info.points_count == 0:
            print("\n   ⚠️ WARNING: Collection is empty (no documents)")
            print("      You need to ingest data into this collection")
    else:
        print(f"   ❌ Collection '{QDRANT_COLLECTION_NAME}' NOT FOUND")
        print("\n   💡 SOLUTIONS:")
        print("      1. Check the collection name is correct")
        print("      2. Create and populate the collection using:")
        print("         python processing/ingest_pinecone_json.py")
        print("      3. Or verify the collection name with:")
        print("         python check_qdrant_connection.py")
except Exception as e:
    print(f"   ❌ Error: {e}")
    sys.exit(1)

print("\n" + "=" * 80)
print("✅ DIAGNOSTIC COMPLETE")
print("=" * 80)
