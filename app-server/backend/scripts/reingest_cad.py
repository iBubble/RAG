#!/usr/bin/env python3
"""
CAD 图纸批量重新入库脚本。

WHY: CAD PDF 通过 PyMuPDF 提取的文本是乱码碎片，
     需要用 qwen2.5vl:7b Vision 模型重新 OCR 提取。

用法: docker exec -it RAG-Server python3 /app/backend/scripts/reingest_cad.py
"""
import os
import sys

# WHY: Pydantic Settings reads .env from CWD. 确保 CWD 是 backend 目录。
_backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(_backend_dir)
sys.path.insert(0, _backend_dir)

import time
import logging
import hashlib

os.environ["HF_HUB_OFFLINE"] = os.getenv("HF_HUB_OFFLINE", "0")

from pathlib import Path
from core.config import settings
from core.extractors.pdf import _is_garbled_cad_text
from core.extractors.vision_extractor import (
    _render_pdf_pages, _call_vision_llm, _unload_vision_model,
    _VISION_PROMPT,
)
from core.vector_store import ingest_text, delete_by_file_id

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
logger = logging.getLogger("reingest_cad")

PROJECT_ID = "cd2974761e91"
CAD_DIR = Path("/Volumes/SYRAID/RAG_Files/uploads") / PROJECT_ID
CAD_DIR = CAD_DIR / "泸县毗卢测试" / "工程图纸"
VISION_MODEL = settings.VISION_MODEL or "qwen2.5vl:7b"
OLLAMA_URL = settings.OLLAMA_BASE_URL
VISION_LOCK = "/tmp/.vision_processing_lock"


def _acquire_vision_lock():
    """创建文件锁，通知心跳协程暂停。"""
    import httpx
    # 1. 创建锁文件
    Path(VISION_LOCK).touch()
    logger.info("🔒 Vision 锁已创建，心跳暂停")
    # 2. 卸载 qwen3.6
    try:
        httpx.post(
            f"{OLLAMA_URL}/api/generate",
            json={"model": "qwen3.6:35b-q4", "keep_alive": 0},
            timeout=30.0,
        )
        logger.info("🔻 qwen3.6 已卸载")
    except Exception:
        pass
    time.sleep(2)
    # 3. 加载 Vision 模型
    try:
        httpx.post(
            f"{OLLAMA_URL}/api/generate",
            json={"model": VISION_MODEL, "prompt": "",
                  "keep_alive": -1, "options": {"num_predict": 1}},
            timeout=120.0,
        )
        logger.info(f"✅ Vision 模型已加载: {VISION_MODEL}")
    except Exception as e:
        logger.error(f"❌ Vision 模型加载失败: {e}")
        _release_vision_lock()
        sys.exit(1)


def _release_vision_lock():
    """释放文件锁，恢复心跳。"""
    try:
        os.remove(VISION_LOCK)
    except FileNotFoundError:
        pass
    logger.info("🔓 Vision 锁已释放")


def _get_file_id(filename: str, project_id: str) -> str:
    """从 Qdrant 查找 file_id，找不到则生成确定性 ID。"""
    from qdrant_client import QdrantClient
    from qdrant_client.models import Filter, FieldCondition, MatchValue
    try:
        client = QdrantClient(url=settings.QDRANT_URL, timeout=10)
        result = client.scroll(
            collection_name=settings.COLLECTION_NAME,
            scroll_filter=Filter(must=[
                FieldCondition(key="project_id",
                               match=MatchValue(value=project_id)),
                FieldCondition(key="filename",
                               match=MatchValue(value=filename)),
            ]),
            limit=1,
        )
        if result[0]:
            return result[0][0].payload.get("file_id", "")
    except Exception:
        pass
    return hashlib.md5(
        f"{project_id}/{filename}".encode()
    ).hexdigest()[:12]


def process_one(pdf_path: Path, project_id: str) -> dict:
    """处理单个 CAD PDF：Vision OCR → 向量入库。"""
    import fitz
    fn = pdf_path.name

    # Step 1: PyMuPDF 文本 + 乱码检测
    try:
        doc = fitz.open(str(pdf_path))
        parts = [p.get_text("text").strip() for p in doc
                 if p.get_text("text").strip()]
        doc.close()
        raw = "\n\n".join(parts)
    except Exception as e:
        return {"file": fn, "status": "error", "reason": str(e)}

    if raw and not _is_garbled_cad_text(raw):
        return {"file": fn, "status": "skip", "reason": "text_ok"}

    # Step 2: Vision OCR
    try:
        pages = _render_pdf_pages(str(pdf_path), dpi=300, max_pages=5)
    except Exception as e:
        return {"file": fn, "status": "error", "reason": str(e)}

    texts = []
    for _, png in pages:
        t = _call_vision_llm(
            image_bytes=png, prompt=_VISION_PROMPT,
            model=VISION_MODEL, ollama_url=OLLAMA_URL, timeout=120,
        )
        if t:
            texts.append(t)

    if not texts:
        return {"file": fn, "status": "empty", "reason": "vision_empty"}

    vision_text = "\n\n".join(texts)

    # Step 3: 清理旧向量 + 重新入库
    fid = _get_file_id(fn, project_id)
    deleted = delete_by_file_id(fid)
    if deleted:
        logger.info(f"  🗑️ 清理旧向量: {deleted} chunks")

    chunks = ingest_text(
        text=vision_text, file_id=fid,
        filename=fn, project_id=project_id,
    )
    return {"file": fn, "status": "ok",
            "chunks": chunks, "chars": len(vision_text)}


def main():
    if not CAD_DIR.exists():
        logger.error(f"目录不存在: {CAD_DIR}")
        sys.exit(1)

    pdfs = sorted(CAD_DIR.rglob("*.pdf"))
    logger.info(f"📁 找到 {len(pdfs)} 个 CAD PDF")

    _acquire_vision_lock()
    t0 = time.time()
    stats = {"ok": 0, "skip": 0, "empty": 0, "error": 0}
    total_chunks = 0

    try:
        for i, p in enumerate(pdfs, 1):
            logger.info(f"[{i}/{len(pdfs)}] {p.name}")
            t1 = time.time()
            r = process_one(p, PROJECT_ID)
            s = r["status"]
            stats[s] = stats.get(s, 0) + 1
            if s == "ok":
                total_chunks += r.get("chunks", 0)
                logger.info(
                    f"  ✅ {r['chars']}字 {r['chunks']}chunks "
                    f"{time.time()-t1:.1f}s"
                )
            elif s == "skip":
                logger.info("  ⏭️ 跳过")
            else:
                logger.warning(f"  ⚠️ {s}: {r.get('reason','')}")
    finally:
        _unload_vision_model(VISION_MODEL, OLLAMA_URL)
        _release_vision_lock()

    elapsed = time.time() - t0
    logger.info(
        f"\n{'='*50}\n"
        f"📊 完成: 总={len(pdfs)} ok={stats['ok']} "
        f"skip={stats['skip']} empty={stats['empty']} "
        f"err={stats['error']}\n"
        f"chunks={total_chunks} 耗时={elapsed/60:.1f}min\n"
        f"{'='*50}"
    )


if __name__ == "__main__":
    main()
