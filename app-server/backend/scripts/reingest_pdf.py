"""
PDF 文件清理与重新入库脚本。
步骤:
  1. 扫描所有项目目录中的 xlsx/xls 文件
  2. 清除幽灵文件（Qdrant 中有向量但磁盘文件已不存在）
  3. 清除孤儿文件（磁盘文件存在但 Qdrant 无向量的不处理，会在重新入库时自动创建）
  4. 删除现有 xlsx/xls 的旧向量 + 旧表格注册
  5. 用新的 _extract_pdf 重新提取文本 → 切片 → 向量化入库
  6. 重新提取并注册表格

用法: cd /app/backend && python3 scripts/reingest_excel.py
"""
import hashlib
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.config import settings
from core.extractors import extract_text, extract_tables
from core.vector_store import ingest_text, delete_by_file_id, _get_client, _collection_name, ensure_collection
from core.table_registry import register_tables, delete_tables
from core.status_tracker import update_file_status
from qdrant_client import models

UPLOAD_ROOT = Path(settings.UPLOAD_DIR)
PDF_EXTS = {".pdf"}


def _compute_file_id(project_id: str, rel_path: str) -> str:
    return hashlib.md5(f"{project_id}_{rel_path}".encode("utf-8")).hexdigest()


def main():
    if not UPLOAD_ROOT.exists():
        print(f"❌ 上传目录不存在: {UPLOAD_ROOT}")
        return

    t_start = time.time()

    # ══════════════════════════════════════════
    # Phase 1: 扫描磁盘，建立 file_id → 文件路径 映射
    # ══════════════════════════════════════════
    print("=" * 60)
    print("Phase 1: 扫描磁盘 PDF 文件")
    print("=" * 60)

    disk_files = {}  # {file_id: (file_path, filename, project_id, rel_path)}

    for project_dir in sorted(UPLOAD_ROOT.iterdir()):
        if not project_dir.is_dir() or project_dir.name.startswith("."):
            continue

        project_id = project_dir.name

        for file_path in project_dir.rglob("*"):
            if not file_path.is_file():
                continue
            if file_path.suffix.lower() not in PDF_EXTS:
                continue
            # 跳过隐藏目录中的文件
            if any(p.name.startswith(".") for p in file_path.relative_to(UPLOAD_ROOT).parents):
                continue

            rel_path = str(file_path.relative_to(UPLOAD_ROOT))
            file_id = _compute_file_id(project_id, rel_path)
            disk_files[file_id] = (str(file_path), file_path.name, project_id, rel_path)

    print(f"  磁盘上找到 {len(disk_files)} 个 PDF 文件")
    for fid, (fp, fn, pid, rp) in disk_files.items():
        print(f"  📄 [{pid[:8]}] {fn} (id={fid[:8]})")

    # ══════════════════════════════════════════
    # Phase 2: 扫描 Qdrant，找出 PDF 相关的幽灵向量
    # ══════════════════════════════════════════
    print(f"\n{'=' * 60}")
    print("Phase 2: 扫描 Qdrant 幽灵向量")
    print("=" * 60)

    client = _get_client()
    ensure_collection()

    # 查找所有 filename 包含 .xlsx 或 .xls 的向量
    ghost_file_ids = set()
    valid_qdrant_ids = set()

    for ext in [".pdf"]:
        try:
            scroll_result, _ = client.scroll(
                collection_name=_collection_name,
                scroll_filter=models.Filter(
                    must=[
                        models.FieldCondition(
                            key="filename",
                            match=models.MatchText(text=ext),
                        ),
                    ]
                ),
                limit=1000,
                with_payload=["file_id", "filename", "project_id"],
                with_vectors=False,
            )

            for point in scroll_result:
                payload = point.payload or {}
                fid = payload.get("file_id", "")
                if fid in disk_files:
                    valid_qdrant_ids.add(fid)
                elif fid:
                    ghost_file_ids.add(fid)
                    fname = payload.get("filename", "?")
                    pid = payload.get("project_id", "?")
                    print(f"  👻 幽灵: {fname} (id={fid[:8]}, project={pid[:8]})")
        except Exception as e:
            print(f"  ⚠️ Qdrant 扫描异常: {e}")

    print(f"  有效向量组: {len(valid_qdrant_ids)}, 幽灵向量组: {len(ghost_file_ids)}")

    # ══════════════════════════════════════════
    # Phase 3: 清除幽灵向量 + 幽灵表格注册
    # ══════════════════════════════════════════
    if ghost_file_ids:
        print(f"\n{'=' * 60}")
        print(f"Phase 3: 清除 {len(ghost_file_ids)} 组幽灵向量")
        print("=" * 60)

        for fid in ghost_file_ids:
            v_count = delete_by_file_id(fid)
            # 尝试从所有项目目录清除表格注册
            for project_dir in UPLOAD_ROOT.iterdir():
                if project_dir.is_dir() and not project_dir.name.startswith("."):
                    delete_tables(fid, project_dir.name)
            print(f"  🗑️ 已清除幽灵 id={fid[:8]}, 向量={v_count}")
    else:
        print("\n  ✅ 无幽灵向量")

    # ══════════════════════════════════════════
    # Phase 4: 重新入库所有 PDF 文件
    # ══════════════════════════════════════════
    print(f"\n{'=' * 60}")
    print(f"Phase 4: 重新入库 {len(disk_files)} 个 PDF 文件")
    print("=" * 60)

    # 先将所有待处理文件状态重置为 pending，让前端进度条归零
    for fid, (_, _, pid, _) in disk_files.items():
        update_file_status(pid, fid, "pending")

    total_chunks = 0
    total_tables = 0
    errors = []

    for i, (file_id, (file_path, filename, project_id, rel_path)) in enumerate(disk_files.items(), 1):
        print(f"\n  [{i}/{len(disk_files)}] {filename}", flush=True)
        update_file_status(project_id, file_id, "processing")

        # 4a. 删除旧向量和旧表格注册
        old_chunks = delete_by_file_id(file_id)
        delete_tables(file_id, project_id)
        if old_chunks > 0:
            print(f"    🗑️ 清除旧向量: {old_chunks} chunks", flush=True)

        # 4b. 重新提取文本（现在走 _extract_pdf）
        try:
            text = extract_text(file_path)
            if not text or not text.strip():
                print(f"    ⚠️ 提取文本为空，跳过", flush=True)
                continue

            print(f"    📝 提取文本: {len(text)} 字符", flush=True)

            # 4c. 切片+向量化入库
            chunks = ingest_text(text, file_id, filename, project_id)
            total_chunks += chunks
            print(f"    ✅ 向量入库: {chunks} chunks", flush=True)

            # 4d. 提取并注册表格
            tables = extract_tables(file_path)
            if tables:
                registered = register_tables(tables, file_id, filename, project_id)
                total_tables += registered
                print(f"    📊 表格注册: {registered} 张", flush=True)
            else:
                print(f"    📊 无表格", flush=True)
            
            # 标记为 graph_queued 并推入 Celery 执行图谱提取
            update_file_status(project_id, file_id, "graph_queued", chunks=chunks)
            from worker import process_graph_extraction
            process_graph_extraction.apply_async(
                args=[file_id, filename, project_id],
                queue='slow_queue'
            )
            print(f"    🕸️ 图谱提取已推入 Celery 队列", flush=True)

        except Exception as e:
            print(f"    ❌ 失败: {e}", flush=True)
            update_file_status(project_id, file_id, "failed", error_message=str(e))
            errors.append((filename, str(e)))

    # ══════════════════════════════════════════
    # 汇总
    # ══════════════════════════════════════════
    elapsed = time.time() - t_start
    print(f"\n{'=' * 60}")
    print(f"✅ PDF 重新入库完成")
    print(f"   磁盘文件: {len(disk_files)} 个")
    print(f"   幽灵清除: {len(ghost_file_ids)} 组")
    print(f"   向量入库: {total_chunks} chunks")
    print(f"   表格注册: {total_tables} 张")
    print(f"   失败文件: {len(errors)} 个")
    print(f"   总耗时: {elapsed:.1f}s")
    if errors:
        print(f"\n   ❌ 失败详情:")
        for fn, err in errors:
            print(f"      {fn}: {err}")
    print("=" * 60)


if __name__ == "__main__":
    main()
