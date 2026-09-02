import time
import sys
sys.path.append("/app/backend")

from core.vector_store import _get_dense_model, _get_sparse_model, _get_client
from core.database import get_db

print("1. 测试 Qdrant 客户端...")
t0 = time.time()
client = _get_client()
print(f"   Qdrant OK, collections: {len(client.get_collections().collections)}, 耗时: {time.time()-t0:.2f}s")

print("2. 测试 SQLite doc_chunks_fts 写入...")
t0 = time.time()
with get_db() as conn:
    conn.execute(
        "INSERT INTO doc_chunks_fts (chunk_id, file_id, project_id, filename, content) VALUES (?, ?, ?, ?, ?)",
        ("test_chunk_1", "test_file_1", "test_proj", "test.md", "这是一段测试文本")
    )
    conn.commit()
    conn.execute("DELETE FROM doc_chunks_fts WHERE chunk_id = ?", ("test_chunk_1",))
    conn.commit()
print(f"   SQLite OK, 耗时: {time.time()-t0:.2f}s")

print("3. 测试 Dense 编码器...")
t0 = time.time()
dense = _get_dense_model()
print(f"   Dense 模型加载完成, 耗时: {time.time()-t0:.2f}s")

t0 = time.time()
vec = dense.encode(["测试编码文本"], normalize_embeddings=True)
print(f"   Dense encode 完成, shape={vec.shape}, 耗时: {time.time()-t0:.2f}s")

print("4. 测试 Sparse 编码器...")
t0 = time.time()
tok, sm = _get_sparse_model()
print(f"   Sparse 模型加载完成, 耗时: {time.time()-t0:.2f}s")

print("🎉 诊断完成！全部正常！")
