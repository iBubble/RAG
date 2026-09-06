"""
食品标准与市监规程极速批量文本提取与向量化入库脚本。
针对标准类文档优化：原生 PDF 采用 PyMuPDF 高性能直接提取文本层，
Markdown 直接读取完整条款，跳过高延迟的外部 Vision 503 阻塞，
确保秒级分块与向量化入库。
"""
import os
import sys
import time
import hashlib
import logging
from pathlib import Path

sys.path.append("/app/backend")

from core.config import settings
from core.vector_store import ingest_text, get_chunk_count
from core.status_tracker import update_file_status
from core.database import get_db

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger("FastBatchIngest")

PROJECT_ID = "fe2982b3820e"

def extract_content_fast(file_path: str) -> str:
    path = Path(file_path)
    suffix = path.suffix.lower()

    if suffix in (".md", ".txt"):
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            return f.read()

    if suffix == ".pdf":
        import fitz  # PyMuPDF
        doc = fitz.open(file_path)
        texts = []
        for page_idx, page in enumerate(doc):
            tabs = page.find_tables()
            images = page.get_images()
            tab_bboxes = [t.bbox for t in tabs.tables] if tabs.tables else []
            blocks = page.get_text("blocks")
            items = []

            for b in blocks:
                if b[6] == 0:  # 纯文本块
                    is_in_tab = False
                    for tbox in tab_bboxes:
                        if fitz.Rect(b[:4]).intersects(fitz.Rect(tbox)):
                            is_in_tab = True
                            break
                    if not is_in_tab and b[4].strip():
                        items.append((b[1], "text", b[4].strip()))

            if tabs.tables:
                for tab in tabs.tables:
                    try:
                        md_table = tab.to_markdown()
                        if md_table and md_table.strip():
                            items.append((tab.bbox[1], "table", md_table.strip()))
                    except Exception:
                        pass

            items.sort(key=lambda x: x[0])
            page_elements = [it[2] for it in items]

            if images and len(tabs.tables) == 0:
                page_elements.append(f"（本页包含 {len(images)} 幅标准图示/谱图/流程图）")

            p_text = "\n\n".join(page_elements).strip()
            if p_text:
                texts.append(f"--- 第 {page_idx + 1} 页 ---\n{p_text}")

        doc.close()
        combined = "\n\n".join(texts)
        if combined.strip():
            return combined
        return f"（标准文件 {path.name} 为扫描版图像，无直接内嵌文本层）"

    return ""

def batch_ingest_fast(project_id: str = PROJECT_ID):
    upload_root = Path(settings.UPLOAD_DIR)
    project_dir = upload_root / project_id
    if not project_dir.exists():
        logger.error("项目目录不存在: %s", project_dir)
        return

    logger.info("🚀 启动快速入库管道: %s", project_dir)
    file_list = []
    for root, dirs, files in os.walk(str(project_dir)):
        dirs[:] = [d for d in dirs if not d.startswith('.')]
        for f in files:
            if f.startswith('.'):
                continue
            full_path = Path(root) / f
            rel_path = str(full_path.relative_to(upload_root))
            file_id = hashlib.md5(f"{project_id}_{rel_path}".encode("utf-8")).hexdigest()
            file_list.append((file_id, str(full_path), f, rel_path))

    logger.info("共发现 %d 个待入库标准文件", len(file_list))
    success_count = 0
    total_chunks = 0

    for idx, (file_id, full_path, filename, rel_path) in enumerate(file_list, 1):
        try:
            # 检查已入库情况
            existing_chunks = get_chunk_count(file_id)
            if existing_chunks > 0:
                logger.info("[%d/%d] 已入库 (%d chunks)，跳过: %s", idx, len(file_list), existing_chunks, filename)
                update_file_status(project_id, file_id, "vectorized", chunks=existing_chunks, filename=filename)
                success_count += 1
                total_chunks += existing_chunks
                continue

            logger.info("[%d/%d] 正在提取与向量化: %s", idx, len(file_list), filename)
            start_t = time.time()
            text = extract_content_fast(full_path)
            if not text.strip():
                text = f"（文件 {filename} 内容为空）"

            chunks = ingest_text(text, file_id, filename, project_id)
            update_file_status(project_id, file_id, "vectorized", chunks=chunks, filename=filename)
            dur = time.time() - start_t
            logger.info("✅ 成功入库: %s (%d chunks, 耗时 %.2fs)", filename, chunks, dur)
            success_count += 1
            total_chunks += chunks
        except Exception as e:
            logger.error("❌ 入库异常 [%s]: %s", filename, e)
            update_file_status(project_id, file_id, "failed", error_message=str(e), filename=filename)

    with get_db() as conn:
        conn.execute(
            "UPDATE projects SET source_count = ? WHERE id = ?",
            (success_count, project_id)
        )
    logger.info("🎉 快速入库达成: 成功 %d/%d 个文件，生成向量切片 %d 块！", success_count, len(file_list), total_chunks)

if __name__ == "__main__":
    target_proj = sys.argv[1] if len(sys.argv) > 1 else PROJECT_ID
    batch_ingest_fast(target_proj)

