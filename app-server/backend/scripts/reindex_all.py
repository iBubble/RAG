"""
全量重建向量索引 — Contextual Chunking 升级后一次性执行。

WHY: _inject_chunk_context 改变了向量编码方式，旧的 chunk 向量
     不携带文档上下文前缀，需要重新编码才能享受精度提升。

用法:
  # 在容器内执行（建议在 Celery 空闲时段运行）
  cd /app/backend && python3 scripts/reindex_all.py

  # 或通过 Celery 任务投递
  python3 -c "from worker import celery_app; celery_app.send_task('worker.reindex_all', queue='slow_queue')"
"""
from __future__ import annotations

import os
import sys
import time
import logging

# WHY: 确保 backend/ 在 import 路径中
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from core.config import settings, STORAGE_ROOT
from core.vector_store import (
    delete_by_file_id, ingest_text, get_chunk_count,
)

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

UPLOAD_DIR = settings.UPLOAD_DIR


def _scan_project_files(project_id: str) -> list[dict]:
    """
    扫描项目上传目录，返回所有可入库的文件信息。
    WHY: 重建索引需要从磁盘重新读取原始文本。
    """
    import hashlib
    project_dir = os.path.join(UPLOAD_DIR, project_id)
    if not os.path.isdir(project_dir):
        return []

    files = []
    for root, dirs, filenames in os.walk(project_dir):
        # WHY: 跳过 .job_states 等以点开头的隐藏目录，
        #      这些目录存放的是系统状态元数据，不是知识文件。
        dirs[:] = [d for d in dirs if not d.startswith('.')]
        for fname in filenames:
            # WHY: 跳过隐藏文件（如 .DS_Store）和 Office 临时文件（~$xxx）
            if fname.startswith('.') or fname.startswith('~$'):
                continue
            fpath = os.path.join(root, fname)
            rel_path = os.path.relpath(fpath, UPLOAD_DIR)
            # WHY: file_id 必须与 files.py L152 完全一致：MD5("project_id_rel_path")
            #      分隔符是下划线(_)，使用完整 32 字符 hex，不截断。
            file_id = hashlib.md5(
                f"{project_id}_{rel_path}".encode("utf-8")
            ).hexdigest()
            files.append({
                "file_id": file_id,
                "filename": fname,
                "path": fpath,
            })
    return files


def _read_file_text(path: str) -> str:
    """读取文件原始文本，支持常见格式。"""
    ext = os.path.splitext(path)[1].lower()

    # 纯文本格式直接读取
    if ext in ('.txt', '.md', '.csv', '.json', '.xml', '.html'):
        try:
            with open(path, 'r', encoding='utf-8', errors='ignore') as f:
                return f.read()
        except Exception:
            return ""

    # PDF
    if ext == '.pdf':
        try:
            import fitz
            doc = fitz.open(path)
            return "\n\n".join(page.get_text() for page in doc)
        except Exception:
            return ""

    # DOCX
    if ext == '.docx':
        try:
            from docx import Document
            doc = Document(path)
            return "\n\n".join(p.text for p in doc.paragraphs if p.text.strip())
        except Exception:
            return ""

    return ""


def reindex_all():
    """全量重建所有项目的向量索引。"""
    from core.database import get_db

    # 读取所有项目
    with get_db() as conn:
        rows = conn.execute("SELECT id, name FROM projects").fetchall()
    projects = [(r["id"], r["name"]) for r in rows]

    if not projects:
        logger.warning("数据库中无项目，跳过重建")
        return

    logger.info(f"📦 开始全量重建索引，共 {len(projects)} 个项目")
    t_start = time.time()
    total_files = 0
    total_chunks = 0

    for pid, pname in projects:
        files = _scan_project_files(pid)
        if not files:
            logger.info(f"  ⏭️ 项目 {pname} ({pid}) 无文件，跳过")
            continue

        logger.info(f"  📂 项目 {pname} ({pid}): {len(files)} 个文件")

        for i, f in enumerate(files):
            fid = f["file_id"]
            fname = f["filename"]

            # Step 1: 读取原始文本
            text = _read_file_text(f["path"])
            if not text or len(text.strip()) < 50:
                logger.debug(f"    ⏭️ {fname}: 文本过短或不可读，跳过")
                continue

            # Step 2: 清除旧的切片
            old_count = delete_by_file_id(fid)

            # Step 3: 重新入库（带 Contextual Chunking）
            new_count = ingest_text(text, fid, fname, pid)

            total_files += 1
            total_chunks += new_count
            logger.info(
                f"    ✅ [{i+1}/{len(files)}] {fname}: "
                f"{old_count} 旧切片 → {new_count} 新切片"
            )

    elapsed = time.time() - t_start
    logger.info(
        f"🎉 全量重建完成: {total_files} 个文件, "
        f"{total_chunks} 个切片, 耗时 {elapsed:.1f}s"
    )


if __name__ == "__main__":
    reindex_all()
