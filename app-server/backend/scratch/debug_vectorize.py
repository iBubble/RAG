import os
os.environ["OMP_NUM_THREADS"] = "1"
os.environ["OPENBLAS_NUM_THREADS"] = "1"
os.environ["MKL_NUM_THREADS"] = "1"

import sys
import time

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

print("[DEBUG] 脚本已启动...", flush=True)

print("[DEBUG] 1. 正在导入 extract_text...", flush=True)
from core.extractors import extract_text
print("[DEBUG] extract_text 导入成功！", flush=True)

print("[DEBUG] 2. 正在导入 ingest_text...", flush=True)
from core.vector_store import ingest_text
print("[DEBUG] ingest_text 导入成功！", flush=True)

file_path = "/Volumes/macData/RAG_Files/uploads/fc28c7fff7bb/中华人民共和国刑事诉讼法.md"
file_id = "b2d6aec4d82b55ccca393476a9130b9c"
filename = "中华人民共和国刑事诉讼法.md"
project_id = "fc28c7fff7bb"

print("[DEBUG] 3. 开始提取文本...", flush=True)
t0 = time.time()
text = extract_text(file_path, is_slow_queue=False)
print(f"[DEBUG] 文本提取成功, 长度: {len(text) if text else 0}, 耗时: {time.time()-t0:.2f}s", flush=True)

if not text:
    print("[DEBUG] 提取文本为空，退出")
    sys.exit(0)

print("[DEBUG] 4. 开始执行 ingest_text 向量化并写入...", flush=True)
t1 = time.time()
try:
    chunks = ingest_text(
        text=text,
        file_id=file_id,
        filename=filename,
        project_id=project_id,
    )
    print(f"[DEBUG] ingest_text 成功, chunks数: {chunks}, 耗时: {time.time()-t1:.2f}s", flush=True)
except Exception as e:
    print(f"[DEBUG] ingest_text 发生异常: {e}", flush=True)
    import traceback
    traceback.print_exc()

print("[DEBUG] 调试执行完毕！", flush=True)
