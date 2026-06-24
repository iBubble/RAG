import sys
import os
import asyncio
import logging
from pathlib import Path

# 确保 backend 目录在 sys.path 中，方便导入 core 模块
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.config import settings
from qdrant_client import QdrantClient
from neo4j import GraphDatabase
from core.entity_resolution import EntityResolver
from core.community_summarizer import CommunitySummarizer
from core.vector_store import ingest_raptor_layers, _collection_name

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("backfill")

def get_projects_neo4j() -> set[str]:
    """从 Neo4j 获取存在实体的所有项目 ID。"""
    try:
        driver = GraphDatabase.driver(
            settings.NEO4J_URI,
            auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD)
        )
        with driver.session() as s:
            res = s.run("MATCH (n:Entity) RETURN DISTINCT n.project_id AS project_id")
            project_ids = [record["project_id"] for record in res if record["project_id"]]
        driver.close()
        return set(project_ids)
    except Exception as e:
        logger.error(f"Failed to fetch projects from Neo4j: {e}")
        return set()

def scan_qdrant_files(client: QdrantClient) -> tuple[dict, set[str]]:
    """扫描 Qdrant，统计文件状态和项目列表。"""
    offset = None
    all_points = []
    while True:
        res, next_offset = client.scroll(
            collection_name=_collection_name,
            limit=2000,
            offset=offset,
            with_payload=True,
            with_vectors=False
        )
        all_points.extend(res)
        if not next_offset:
            break
        offset = next_offset

    file_stats = {}
    qdrant_projects = set()
    for pt in all_points:
        payload = pt.payload or {}
        fid = payload.get("file_id")
        if not fid:
            continue
        filename = payload.get("filename", "")
        pid = payload.get("project_id", "default")
        chunk_type = payload.get("chunk_type", "")
        
        qdrant_projects.add(pid)
        
        if fid not in file_stats:
            file_stats[fid] = {
                "filename": filename,
                "project_id": pid,
                "chunks": 0,
                "has_raptor": False
            }
        
        if chunk_type == "raptor_summary":
            file_stats[fid]["has_raptor"] = True
        elif chunk_type != "doc_summary":
            file_stats[fid]["chunks"] += 1

    return file_stats, qdrant_projects

def backfill_project_features(project_id: str):
    """补跑单个项目的实体消歧和社区发现（Leiden/PageRank）。"""
    logger.info(f"--- Processing Project: {project_id} ---")
    
    # 实体消歧
    logger.info(f"Running Entity Resolution for {project_id}...")
    resolver = EntityResolver()
    try:
        er_result = asyncio.run(resolver.resolve(project_id))
        logger.info(f"Entity Resolution complete for {project_id}: {er_result}")
    except Exception as e:
        logger.error(f"Entity Resolution failed for {project_id}: {e}")
        
    # 社区划分与 PageRank
    logger.info(f"Running Community Summarizer (Leiden + PageRank) for {project_id}...")
    summarizer = CommunitySummarizer()
    try:
        # WHY: 仅同步社区（Leiden）和 PageRank（NetworkX毫秒级），避免本地执行耗时且易拥堵的 LLM 摘要生成
        summarizer._connect()
        asyncio.run(summarizer._sync_communities(project_id))
        logger.info(f"Leiden partitioning and PageRank write-back complete for {project_id}")
        
        # 投递异步自调度 Celery 任务，在后台由 PM2 慢队列低并发提炼摘要，脚本不阻塞
        from worker import compute_community_summaries
        compute_community_summaries.apply_async(
            args=[project_id, True], # skip_sync=True 跳过图谱分区，只补跑摘要
            queue='summary_queue'
        )
        logger.info(f"Asynchronously triggered community summary generation via Celery for {project_id}")
    except Exception as e:
        logger.error(f"Community Summarizer failed for {project_id}: {e}")
    finally:
        summarizer._close()

def backfill_raptor_files(file_stats: dict):
    """补跑满足条件（chunks >= 5 且没有 raptor_summary）的文件的 RAPTOR 摘要。"""
    candidates = [
        (fid, info) for fid, info in file_stats.items()
        if info["chunks"] >= 5 and not info["has_raptor"]
    ]
    logger.info(f"Found {len(candidates)} files requiring RAPTOR backfill.")
    
    success = 0
    for fid, info in candidates:
        filename = info["filename"]
        pid = info["project_id"]
        chunks = info["chunks"]
        logger.info(f"Running RAPTOR for: {filename} (ID: {fid}, Project: {pid}, Chunks: {chunks})")
        try:
            num_summaries = ingest_raptor_layers(fid, filename, pid)
            logger.info(f"RAPTOR finished: {filename} -> Ingested {num_summaries} chunks.")
            success += 1
        except Exception as e:
            logger.error(f"RAPTOR failed for {filename}: {e}")
    logger.info(f"RAPTOR backfill finished: {success}/{len(candidates)} successful.")

def main():
    logger.info("Starting P0-P2 backfill process...")
    
    client = QdrantClient(url=settings.QDRANT_URL)
    try:
        file_stats, qdrant_projects = scan_qdrant_files(client)
    except Exception as e:
        logger.error(f"Failed to scan Qdrant files: {e}")
        sys.exit(1)
        
    neo4j_projects = get_projects_neo4j()
    all_projects = sorted(list(qdrant_projects | neo4j_projects))
    logger.info(f"Merged projects list: {all_projects}")
    
    logger.info("=== Phase 1: Projects Features (ER & Community Summarizer) ===")
    for pid in all_projects:
        backfill_project_features(pid)
        
    logger.info("=== Phase 2: RAPTOR Layers Ingestion ===")
    backfill_raptor_files(file_stats)
    
    logger.info("All backfill phases completed.")

if __name__ == "__main__":
    main()
