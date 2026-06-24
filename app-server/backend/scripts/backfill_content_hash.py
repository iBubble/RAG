"""
为历史 Qdrant 数据补写 content_hash 字段。
WHY: 向量化去重优化依赖 content_hash 字段，但历史数据没有此字段，
     需要回溯原始文件重新计算并批量更新 payload。
"""
import os
import sys
import hashlib

sys.path.insert(0, "/app/backend")

from core.config import settings
from core.extractors import extract_text
from qdrant_client import QdrantClient, models

COLLECTION = "syrag_documents"
QDRANT_URL = "http://host.docker.internal:6333"
UPLOAD_DIR = settings.UPLOAD_DIR


def main():
    client = QdrantClient(url=QDRANT_URL, timeout=30)

    # 1. 扫描所有 project 上传目录，建立 file_id → 文件路径映射
    file_map = {}  # file_id -> file_path
    for project_id in os.listdir(UPLOAD_DIR):
        proj_dir = os.path.join(UPLOAD_DIR, project_id)
        if not os.path.isdir(proj_dir):
            continue
        for root, dirs, files in os.walk(proj_dir):
            for fname in files:
                if fname.startswith("."):
                    continue
                fpath = os.path.join(root, fname)
                rel = os.path.relpath(fpath, proj_dir)
                fid = hashlib.md5(f"{project_id}_{rel}".encode("utf-8")).hexdigest()
                file_map[fid] = fpath

    print(f"📁 扫描到 {len(file_map)} 个文件")

    # 2. 逐文件提取文本、计算哈希、更新 Qdrant payload
    updated_files = 0
    updated_points = 0
    skipped = 0

    for fid, fpath in file_map.items():
        # 检查此 file_id 的 points 是否已有 content_hash
        sample, _ = client.scroll(
            collection_name=COLLECTION,
            scroll_filter=models.Filter(
                must=[
                    models.FieldCondition(
                        key="file_id",
                        match=models.MatchValue(value=fid),
                    )
                ]
            ),
            limit=1,
            with_payload=True,
            with_vectors=False,
        )
        if not sample:
            continue
        if sample[0].payload.get("content_hash"):
            skipped += 1
            continue

        # 提取文本并计算哈希
        try:
            text = extract_text(fpath)
        except Exception as e:
            print(f"  ⚠️ 提取失败: {fpath}: {e}")
            continue

        if not text or not text.strip():
            print(f"  ⚠️ 文本为空: {fpath}")
            continue

        content_hash = hashlib.md5(text.encode("utf-8")).hexdigest()

        # 收集此 file_id 的所有 point IDs
        point_ids = []
        offset = None
        while True:
            batch, next_offset = client.scroll(
                collection_name=COLLECTION,
                scroll_filter=models.Filter(
                    must=[
                        models.FieldCondition(
                            key="file_id",
                            match=models.MatchValue(value=fid),
                        )
                    ]
                ),
                limit=100,
                offset=offset,
                with_payload=False,
                with_vectors=False,
            )
            point_ids.extend([p.id for p in batch])
            if next_offset is None:
                break
            offset = next_offset

        if not point_ids:
            continue

        # 批量更新 payload
        client.set_payload(
            collection_name=COLLECTION,
            payload={"content_hash": content_hash},
            points=point_ids,
        )

        updated_files += 1
        updated_points += len(point_ids)
        fname = os.path.basename(fpath)
        print(
            f"  ✅ {fname}: hash={content_hash[:8]}... "
            f"({len(point_ids)} points)"
        )

    print(f"\n📊 汇总: 更新 {updated_files} 个文件 / "
          f"{updated_points} 个 points, 跳过 {skipped} 个已有 hash 的文件")


if __name__ == "__main__":
    main()
