import os
import sys
import uuid
import hashlib
from pathlib import Path

sys.path.append("/app/backend")
from core.config import settings
from core.database import insert_fts_chunks, delete_fts_by_project_id
from core.extractors import extract_text

pids = ["case_guazi_2026", "case_beef_2026"]

for pid in pids:
    delete_fts_by_project_id(pid)
    p_dir = Path(settings.UPLOAD_DIR) / pid
    print(f"📦 正在构建项目 {pid} 的 FTS 全文索引...")
    fts_chunks = []
    chunk_idx = 0
    
    for root, dirs, files in os.walk(str(p_dir)):
        if ".job_states" in dirs:
            dirs.remove(".job_states")
        for f in files:
            if f.startswith("."):
                continue
            ext = Path(f).suffix.lower()
            if ext not in [".md", ".json", ".txt"]:
                continue
            fpath = Path(root) / f
            rel = str(fpath.relative_to(Path(settings.UPLOAD_DIR)))
            fid = hashlib.md5(f"{pid}_{rel}".encode("utf-8")).hexdigest()
            
            try:
                content = extract_text(str(fpath))
                if not content or len(content.strip()) < 5:
                    continue
                
                # 简单按段落或每 500 字切片
                lines = content.split("\n\n")
                current_chunk = ""
                for line in lines:
                    if len(current_chunk) + len(line) < 600:
                        current_chunk += "\n\n" + line if current_chunk else line
                    else:
                        if current_chunk.strip():
                            fts_chunks.append({
                                "id": uuid.uuid4().hex,
                                "file_id": fid,
                                "project_id": pid,
                                "filename": f,
                                "chunk_index": chunk_idx,
                                "document": current_chunk.strip()
                            })
                            chunk_idx += 1
                        current_chunk = line
                if current_chunk.strip():
                    fts_chunks.append({
                        "id": uuid.uuid4().hex,
                        "file_id": fid,
                        "project_id": pid,
                        "filename": f,
                        "chunk_index": chunk_idx,
                        "document": current_chunk.strip()
                    })
                    chunk_idx += 1
            except Exception as e:
                print(f"  ❌ 处理 {f} 出错: {e}")

    if fts_chunks:
        insert_fts_chunks(fts_chunks)
        print(f"✅ 项目 {pid} 成功写入 {len(fts_chunks)} 个全文索引切片！")

print("\n🎉 全部案卷全文索引入库完毕！")
