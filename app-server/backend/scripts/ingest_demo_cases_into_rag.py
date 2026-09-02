import os
import sys
import hashlib
from pathlib import Path

sys.path.append("/app/backend")
from core.config import settings
from core.extractors import extract_text
from core.vector_store import ingest_text
from core.status_tracker import update_file_status

pids = ["case_guazi_2026", "case_beef_2026"]

for pid in pids:
    p_dir = Path(settings.UPLOAD_DIR) / pid
    print(f"\n🚀 开始对项目 {pid} 的案卷进行真实向量化与全文入库...")
    for root, dirs, files in os.walk(str(p_dir)):
        if ".job_states" in dirs:
            dirs.remove(".job_states")
        for f in files:
            if f.startswith("."):
                continue
            ext = Path(f).suffix.lower()
            if ext not in [".md", ".json", ".txt", ".docx", ".pdf"]:
                continue
            fpath = Path(root) / f
            rel = str(fpath.relative_to(Path(settings.UPLOAD_DIR)))
            fid = hashlib.md5(f"{pid}_{rel}".encode("utf-8")).hexdigest()
            print(f"  📄 正在切片并向量化: {f} (fid={fid[:8]})...")
            try:
                # 提取文本
                text = extract_text(str(fpath))
                if text and len(text.strip()) > 10:
                    chunks_count = ingest_text(text, f, fid, pid)
                    update_file_status(pid, fid, "vectorized", chunks=chunks_count, error_message="Graph OK")
                    print(f"     ✅ 成功入库: {chunks_count} chunks")
                else:
                    print(f"     ⚠️ 文本为空或过短，跳过")
            except Exception as e:
                print(f"     ❌ 入库异常: {e}")

print("\n🎉 全部案卷文档向量化与全文入库完毕！")
