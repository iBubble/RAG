"""
向量库全量重建脚本 (BGE-M3 迁移专用)。
WHY: 从 bge-small-en-v1.5 升级到 BGE-M3 后，需要用新模型重新编码所有已上传文件。
用法: docker exec RAG-Server python3 /app/backend/scripts/rebuild_vectors.py
"""
import sys
import os
import time
import hashlib
import json
import logging
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from core.config import settings
from core.extractors import extract_text
from core.vector_store import ingest_text, ensure_collection, get_collection_stats

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger("rebuild")

# Shapefile 伴生文件后缀（跳过，只处理 .shp 主文件）
SHP_COMPANION_EXTS = {
    ".shx", ".dbf", ".prj", ".sbn", ".sbx",
    ".cpg", ".qix", ".fix", ".atx", ".mta",
}

# 不支持的格式
SKIP_EXTS = {
    ".lock", ".xml", ".dwg", ".dxf",
    ".jpg", ".jpeg", ".png", ".gif", ".bmp", ".tif", ".tiff",
}


def generate_file_id(project_id: str, rel_path: str) -> str:
    """与 files.py 中一致的 file_id 生成方式。"""
    return hashlib.md5(f"{project_id}_{rel_path}".encode("utf-8")).hexdigest()


def rebuild_all():
    """扫描所有上传文件并用 BGE-M3 重新编码入库。"""
    upload_root = Path(settings.UPLOAD_DIR)
    if not upload_root.exists():
        logger.error(f"上传目录不存在: {upload_root}")
        return

    # 确保 collection schema 正确
    ensure_collection()

    # 收集需要处理的文件
    tasks = []
    shp_basenames_seen = set()

    for root, dirs, files in os.walk(str(upload_root)):
        root_path = Path(root)

        # 跳过 .gdb 内部
        if ".gdb" in str(root_path):
            continue

        # 找出本目录下的 shp 主文件
        local_shp_stems = set()
        for f in files:
            if f.lower().endswith(".shp") and not f.lower().endswith(".shp.xml"):
                local_shp_stems.add(Path(f).stem)

        for f in files:
            if f.startswith("."):
                continue

            fpath = root_path / f
            f_ext = fpath.suffix.lower()
            f_stem = fpath.stem

            # 跳过不支持的格式
            if f_ext in SKIP_EXTS:
                continue

            # 跳过 shapefile 伴生文件
            if f_stem in local_shp_stems and f_ext in SHP_COMPANION_EXTS:
                continue

            # 计算相对路径和 project_id
            try:
                rel = fpath.relative_to(upload_root)
                parts = rel.parts
                project_id = parts[0] if len(parts) >= 2 else "default"
                rel_path = str(rel)
            except ValueError:
                continue

            file_id = generate_file_id(project_id, rel_path)
            tasks.append((str(fpath), file_id, f, project_id))

    logger.info(f"扫描完成，共 {len(tasks)} 个文件待重建")

    # 逐个处理
    success = 0
    failed = 0
    total_chunks = 0
    t_start = time.time()

    for i, (fpath, file_id, filename, project_id) in enumerate(tasks):
        try:
            logger.info(
                f"[{i+1}/{len(tasks)}] 处理: {filename} "
                f"(project={project_id})"
            )
            t0 = time.time()

            text = extract_text(fpath)
            if not text or not text.strip():
                logger.warning(f"  跳过（无可提取文本）: {filename}")
                continue

            chunks = ingest_text(text, file_id, filename, project_id)
            dt = time.time() - t0

            logger.info(f"  ✅ 入库 {chunks} chunks，耗时 {dt:.1f}s")
            success += 1
            total_chunks += chunks

        except Exception as e:
            logger.error(f"  ❌ 失败: {filename} -> {type(e).__name__}: {e}")
            failed += 1

    elapsed = time.time() - t_start
    stats = get_collection_stats()

    logger.info("=" * 60)
    logger.info(f"重建完成！")
    logger.info(f"  成功: {success}, 失败: {failed}, 跳过: {len(tasks) - success - failed}")
    logger.info(f"  总 chunks: {total_chunks}")
    logger.info(f"  总耗时: {elapsed:.1f}s ({elapsed/60:.1f}min)")
    logger.info(f"  向量库状态: {stats}")
    logger.info("=" * 60)


if __name__ == "__main__":
    rebuild_all()
