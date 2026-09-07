"""
食品标准与市监规程极速批量文本提取与向量化入库脚本。
针对标准类文档优化：原生 PDF 采用 PyMuPDF 高性能直接提取文本层，
Markdown 直接读取完整条款，跳过高延迟的外部 Vision 503 阻塞，
确保秒级分块与向量化入库。
"""
import os
os.environ["PYTORCH_MPS_HIGH_WATERMARK_RATIO"] = "0.0"
import sys
import time
import hashlib
import logging
from pathlib import Path

_curr_dir = str(Path(__file__).resolve().parent)
if _curr_dir not in sys.path:
    sys.path.insert(0, _curr_dir)
if not os.path.exists("/app/backend"):
    # 宿主机运行环境自适应
    if "QDRANT_URL" not in os.environ:
        os.environ["QDRANT_URL"] = "http://localhost:6335"
    if "UPLOAD_DIR" not in os.environ and os.path.exists("/Volumes/macData/GenRAG_Files/uploads"):
        os.environ["UPLOAD_DIR"] = "/Volumes/macData/GenRAG_Files/uploads"

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
            p_text = page.get_text("text").strip()
            if p_text:
                texts.append(f"--- 第 {page_idx + 1} 页 ---\n{p_text}")
            else:
                images = page.get_images()
                if images:
                    texts.append(f"--- 第 {page_idx + 1} 页 ---\n（本页包含 {len(images)} 幅标准图示/谱图/图像）")

        doc.close()
        combined = "\n\n".join(texts)
        if combined.strip():
            return combined
        return f"（标准文件 {path.name} 为扫描版图像，无直接内嵌文本层）"

    return ""

def batch_ingest_fast(project_id: str = PROJECT_ID):
    upload_root = None
    for cand in [
        "/Volumes/macData/GenRAG_Files/uploads",
        getattr(settings, "UPLOAD_DIR", ""),
        "/Volumes/macData/RAG_Files/uploads",
    ]:
        if cand and (Path(cand) / project_id).exists():
            upload_root = Path(cand)
            break

    if not upload_root or not (upload_root / project_id).exists():
        logger.error("项目目录不存在: %s (已探测候选路径)", project_id)
        return

    project_dir = upload_root / project_id
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
    batch_start_t = time.time()
    processed_count = 0

    for idx, (file_id, full_path, filename, rel_path) in enumerate(file_list, 1):
        try:
            # 优先从本地 job_states 快速探测，避免每次 HTTP 请求 Qdrant
            status_file = upload_root / project_id / ".job_states" / f"{file_id}.json"
            if status_file.exists():
                try:
                    import json
                    s_data = json.loads(status_file.read_text(encoding="utf-8"))
                    if s_data.get("status") == "vectorized" and s_data.get("chunks", 0) > 0:
                        c_cnt = s_data.get("chunks", 0)
                        logger.info("[%d/%d] 本地已标记入库 (%d chunks)，跳过: %s", idx, len(file_list), c_cnt, filename)
                        success_count += 1
                        total_chunks += c_cnt
                        continue
                except Exception:
                    pass

            # 检查已入库情况 (Qdrant)
            existing_chunks = get_chunk_count(file_id)
            if existing_chunks > 0:
                logger.info("[%d/%d] 已入库 (%d chunks)，跳过: %s", idx, len(file_list), existing_chunks, filename)
                update_file_status(project_id, file_id, "vectorized", chunks=existing_chunks, filename=filename)
                success_count += 1
                total_chunks += existing_chunks
                continue

            logger.info("[%d/%d] 正在提取与向量化 (MPS加速): %s", idx, len(file_list), filename)
            start_t = time.time()
            text = extract_content_fast(full_path)
            if not text.strip():
                text = f"（文件 {filename} 内容为空）"

            chunks = ingest_text(text, file_id, filename, project_id)
            update_file_status(project_id, file_id, "vectorized", chunks=chunks, filename=filename)
            dur = time.time() - start_t
            success_count += 1
            total_chunks += chunks
            processed_count += 1

            # 动态计算速度与预估剩余时间
            avg_t = (time.time() - batch_start_t) / max(processed_count, 1)
            remaining_cnt = len(file_list) - idx
            eta_mins = (remaining_cnt * avg_t) / 60.0
            logger.info("✅ 成功入库: %s (%d chunks, 耗时 %.2fs, ETA: %.1f分, 进度: %.1f%%)",
                        filename, chunks, dur, eta_mins, (idx / len(file_list)) * 100.0)

            # 每 15 个持久化一次数据库计数并释放显存
            if success_count % 15 == 0:
                try:
                    with get_db() as conn:
                        conn.execute("UPDATE projects SET source_count = ? WHERE id = ?", (success_count, project_id))
                except Exception:
                    pass
                try:
                    import gc, torch
                    gc.collect()
                    if hasattr(torch, "mps") and hasattr(torch.mps, "empty_cache"):
                        torch.mps.empty_cache()
                except Exception:
                    pass
        except Exception as e:
            logger.error("❌ 入库异常 [%s]: %s", filename, e)
            try:
                import gc, torch
                gc.collect()
                if hasattr(torch, "mps") and hasattr(torch.mps, "empty_cache"):
                    torch.mps.empty_cache()
            except Exception:
                pass
            update_file_status(project_id, file_id, "failed", error_message=str(e), filename=filename)

    with get_db() as conn:
        conn.execute(
            "UPDATE projects SET source_count = ? WHERE id = ?",
            (success_count, project_id)
        )
    logger.info("🎉 本轮入库扫描达成: 成功 %d/%d 个文件，生成向量切片 %d 块！", success_count, len(file_list), total_chunks)
    return success_count, len(file_list)

if __name__ == "__main__":
    target_proj = sys.argv[1] if len(sys.argv) > 1 else PROJECT_ID
    while True:
        try:
            succ, total = batch_ingest_fast(target_proj)
            if succ >= total and total > 0:
                logger.info("🎉 全量 %d 个标准已全部入库完毕，守护进程圆满完成！", total)
                break
            logger.info("本轮扫描已入库 %d/%d，继续下一轮扫描自愈推进...", succ, total)
            time.sleep(2)
        except BaseException as err:
            logger.error("守护层捕获异常，3秒后自动自愈接续: %s", err)
            try:
                import gc, torch
                gc.collect()
                if hasattr(torch, "mps") and hasattr(torch.mps, "empty_cache"):
                    torch.mps.empty_cache()
            except Exception:
                pass
            time.sleep(3)

