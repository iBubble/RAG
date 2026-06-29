import time
import torch
print("Loading torch & dependencies...")
t0 = time.time()
from core.vector_store import _get_dense_model, _compute_sparse_vectors
print(f"Import done, took {time.time() - t0:.2f}s")

print("Initializing models...")
t1 = time.time()
dense_model = _get_dense_model()
print(f"Models loaded, took {time.time() - t1:.2f}s")

chunks = ["这是一段用来测试 BGE-M3 模型在当前 Docker 虚拟容器 CPU 下执行向量编码计算速度的测试文本。我们将通过它来精准核算每 10 个切片的实际耗时，绝不掺杂任何估计。" * 5] * 10

print("Benchmarking Dense encoding (10 chunks)...")
t2 = time.time()
dense_vecs = dense_model.encode(chunks, show_progress_bar=False, normalize_embeddings=True)
print(f"Dense done, took {time.time() - t2:.2f}s")

print("Benchmarking Sparse encoding (10 chunks)...")
t3 = time.time()
sparse_vecs = _compute_sparse_vectors(chunks)
print(f"Sparse done, took {time.time() - t3:.2f}s")
