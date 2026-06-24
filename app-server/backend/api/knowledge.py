"""
知识库数据看板 API — 向量化统计与可视化数据接口。
WHY: 用户上传的文件经过切片+嵌入后存入 Qdrant，但缺乏直观展示。
     本模块从 Qdrant 聚合统计数据，供前端可视化面板消费。
"""
from __future__ import annotations

import logging
from pathlib import Path
from collections import defaultdict

from fastapi import APIRouter, Depends, Query

from core.config import settings
from core.vector_store import _get_client, _collection_name
from core.project_access import require_project_access
from api.auth import get_current_user
from qdrant_client import models

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/knowledge", tags=["knowledge"])

# 表格注册表的本地存储目录
_TABLE_DIR = Path(settings.DATA_DIR) / "tables"


def _count_tables(project_id: str) -> int:
    """统计项目下已注册的表格数量。"""
    table_dir = _TABLE_DIR / project_id
    if not table_dir.exists():
        return 0
    import json
    total = 0
    for f in table_dir.glob("*.json"):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            total += len(data.get("tables", []))
        except Exception:
            pass
    return total


@router.get("/stats")
async def knowledge_stats(
    project_id: str = Query("default"),
    user: dict = Depends(get_current_user),
):
    """
    返回项目级知识库统计数据：
    - 各文件的切片数量
    - 切片长度分布
    - 已注册表格数量
    """
    require_project_access(project_id, user, write=False)

    client = _get_client()

    # WHY: 用 scroll 遍历该项目所有 point 的 payload，
    #      一次性拉取所有需要的元数据，避免 N+1 查询。
    scroll_filter = models.Filter(
        must=[
            models.FieldCondition(
                key="project_id",
                match=models.MatchValue(value=project_id),
            )
        ]
    )

    # 聚合容器
    file_chunks: dict[str, dict] = defaultdict(
        lambda: {"filename": "", "chunk_count": 0, "total_chars": 0}
    )
    length_buckets = {
        "0-128": 0,
        "128-256": 0,
        "256-512": 0,
        "512-1024": 0,
        "1024+": 0,
    }
    total_chunks = 0
    total_chars = 0

    # WHY: scroll 分页遍历，每次最多取 100 条防止内存爆炸
    offset = None
    while True:
        results, next_offset = client.scroll(
            collection_name=_collection_name,
            scroll_filter=scroll_filter,
            limit=100,
            offset=offset,
            with_payload=True,
            with_vectors=False,  # 不需要向量数据，节省带宽
        )

        for point in results:
            payload = point.payload or {}
            # WHY: 跳过表格索引向量（chunk_type=table_index），
            #      它们是表格标题的语义索引，不是正文切片。
            if payload.get("chunk_type") == "table_index":
                continue

            file_id = payload.get("file_id", "unknown")
            filename = payload.get("filename", "未知文件")
            doc = payload.get("document", "")
            doc_len = len(doc)

            file_chunks[file_id]["filename"] = filename
            file_chunks[file_id]["chunk_count"] += 1
            file_chunks[file_id]["total_chars"] += doc_len

            total_chunks += 1
            total_chars += doc_len

            # 切片长度分桶
            if doc_len < 128:
                length_buckets["0-128"] += 1
            elif doc_len < 256:
                length_buckets["128-256"] += 1
            elif doc_len < 512:
                length_buckets["256-512"] += 1
            elif doc_len < 1024:
                length_buckets["512-1024"] += 1
            else:
                length_buckets["1024+"] += 1

        if next_offset is None:
            break
        offset = next_offset

    file_stats = sorted(
        [
            {
                "file_id": fid,
                "filename": info["filename"],
                "chunk_count": info["chunk_count"],
                "avg_length": round(info["total_chars"] / info["chunk_count"])
                if info["chunk_count"] > 0
                else 0,
                "file_type": _guess_file_type(info["filename"]),
            }
            for fid, info in file_chunks.items()
        ],
        key=lambda x: x["chunk_count"],
        reverse=True,
    )

    table_count = _count_tables(project_id)

    return {
        "total_files": len(file_stats),
        "total_chunks": total_chunks,
        "total_tables": table_count,
        "avg_chunk_length": round(total_chars / total_chunks)
        if total_chunks > 0
        else 0,
        "file_stats": file_stats,
        "chunk_length_distribution": [
            {"range": k, "count": v} for k, v in length_buckets.items()
        ],
    }


@router.get("/vectors")
async def knowledge_vectors(
    project_id: str = Query("default"),
    user: dict = Depends(get_current_user),
):
    """
    返回 t-SNE 降维后的 2D 向量坐标，供前端绘制'知识星云图'。
    WHY: 高维向量(1024d)人类无法直觉理解，降维到 2D 后可以直观
         看到哪些文档的切片在语义空间中靠近（聚集）或分散。
    """
    import json
    import time
    import hashlib
    import numpy as np

    require_project_access(project_id, user, write=False)

    # ── 缓存检查（避免每次都重新跑 t-SNE）──
    cache_dir = Path(settings.DATA_DIR) / "cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_key = hashlib.md5(f"vectors_{project_id}".encode()).hexdigest()
    cache_file = cache_dir / f"{cache_key}.json"

    CACHE_TTL_SECONDS = 600  # 10 分钟
    if cache_file.exists():
        age = time.time() - cache_file.stat().st_mtime
        if age < CACHE_TTL_SECONDS:
            try:
                cached = json.loads(cache_file.read_text(encoding="utf-8"))
                logger.info(f"[Knowledge] 命中向量缓存 (age={int(age)}s)")
                return cached
            except Exception:
                pass

    client = _get_client()
    from core.vector_store import _DENSE_VECTOR_NAME

    scroll_filter = models.Filter(
        must=[
            models.FieldCondition(
                key="project_id",
                match=models.MatchValue(value=project_id),
            )
        ]
    )

    # ── 1. 从 Qdrant 拉取所有向量 + payload ──
    all_vectors = []
    all_meta = []
    offset = None

    while True:
        results, next_offset = client.scroll(
            collection_name=_collection_name,
            scroll_filter=scroll_filter,
            limit=100,
            offset=offset,
            with_payload=True,
            with_vectors=[_DENSE_VECTOR_NAME],
        )

        for point in results:
            payload = point.payload or {}
            if payload.get("chunk_type") == "table_index":
                continue

            vec = point.vector
            # WHY: scroll 返回的 vector 结构可能是 dict（命名向量）或 list
            if isinstance(vec, dict):
                vec = vec.get(_DENSE_VECTOR_NAME)
            if vec is None:
                continue

            doc = payload.get("document", "")
            all_vectors.append(vec)
            all_meta.append({
                "filename": payload.get("filename", "未知"),
                "preview": doc[:80] if doc else "",
                "file_type": _guess_file_type(payload.get("filename", "")),
            })

        if next_offset is None:
            break
        offset = next_offset

    n = len(all_vectors)
    if n < 3:
        return {"points": [], "message": "切片数量不足（至少需要 3 个）"}

    # ── 2. 随机采样（大项目防止 t-SNE 计算超时）──
    MAX_POINTS = 500
    if n > MAX_POINTS:
        indices = np.random.choice(n, MAX_POINTS, replace=False)
        all_vectors = [all_vectors[i] for i in indices]
        all_meta = [all_meta[i] for i in indices]
        n = MAX_POINTS
        logger.info(f"[Knowledge] 采样 {MAX_POINTS}/{n} 个点")

    # ── 3. t-SNE 降维（CPU 密集型，放到线程池防止阻塞事件循环）──
    import asyncio
    from concurrent.futures import ThreadPoolExecutor
    from sklearn.manifold import TSNE

    X = np.array(all_vectors, dtype=np.float32)
    perp = min(30, max(5, n // 3))

    def _run_tsne():
        tsne = TSNE(
            n_components=2,
            perplexity=perp,
            random_state=42,
            max_iter=800,
            learning_rate="auto",
            init="pca",
        )
        return tsne.fit_transform(X)

    loop = asyncio.get_event_loop()
    coords = await loop.run_in_executor(None, _run_tsne)

    # WHY: 释放大矩阵，降低内存驻留
    del X, all_vectors

    # ── 4. 组装结果 ──
    points = []
    for i in range(n):
        points.append({
            "x": round(float(coords[i, 0]), 2),
            "y": round(float(coords[i, 1]), 2),
            **all_meta[i],
        })

    result = {"points": points, "total_sampled": n}

    # ── 5. 写入缓存 ──
    try:
        cache_file.write_text(
            json.dumps(result, ensure_ascii=False), encoding="utf-8"
        )
    except Exception as e:
        logger.warning(f"[Knowledge] 缓存写入失败: {e}")

    return result


def _guess_file_type(name: str) -> str:
    """推断文件类型。"""
    name_lower = name.lower()
    if name_lower.endswith(".pdf"):
        return "pdf"
    if name_lower.endswith((".doc", ".docx")):
        return "docx"
    if name_lower.endswith((".xls", ".xlsx")):
        return "xlsx"
    if name_lower.endswith((".ppt", ".pptx")):
        return "pptx"
    if name_lower.startswith("web_"):
        return "web"
    return "other"
