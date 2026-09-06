"""
彻底销毁指定项目的全链路数据脚本。
包括：数据库记录、物理上传文件、文档归档、模板、向量切片(Qdrant)、知识图谱(Neo4j)、Redis缓存等。
"""
import os
import sys
import shutil
import logging
from pathlib import Path

sys.path.append("/app/backend")

from core.config import settings
from core.database import get_db, DB_PATH
from core.vector_store import delete_by_project_id
from core.precompute import invalidate_draft_cache
from core.chat_cache import invalidate_chat_cache

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("DestroyProject")

def destroy_project(project_id: str, project_name: str = ""):
    logger.info("🚨 开始彻底销毁项目: %s (%s)", project_id, project_name)

    # 1. 清理 SQLite 数据库各表
    with get_db() as conn:
        tables = [
            ("projects", "id"),
            ("web_sources", "project_id"),
            ("chat_history", "project_id"),
            ("project_members", "project_id"),
            ("project_traces", "project_id"),
        ]
        for tbl, col in tables:
            try:
                cur = conn.execute(f"DELETE FROM {tbl} WHERE {col} = ?", (project_id,))
                logger.info("SQLite 表 %s 删除 %d 条记录", tbl, cur.rowcount)
            except Exception as e:
                logger.warning("清理表 %s 异常: %s", tbl, e)

    # 2. 清理 Qdrant 向量库及全文检索
    try:
        deleted_points = delete_by_project_id(project_id)
        logger.info("Qdrant 向量库删除 %d 个向量点", deleted_points)
    except Exception as e:
        logger.warning("清理 Qdrant 异常: %s", e)

    # 3. 清理 Neo4j 知识图谱实体与关系
    try:
        from core.graph_rag import graph_engine
        with graph_engine.driver.session() as session:
            res = session.run("MATCH (n {project_id: $pid}) DETACH DELETE n RETURN count(n) as cnt", pid=project_id)
            cnt = res.single()["cnt"]
            logger.info("Neo4j 图谱删除 %d 个节点及关联关系", cnt)
    except Exception as e:
        logger.warning("清理 Neo4j 图谱异常: %s", e)

    # 4. 清理 Redis 缓存与内存预计算缓存
    try:
        invalidate_draft_cache(project_id)
        invalidate_chat_cache(project_id)
        from core.redis_client import get_redis
        r = get_redis()
        if r:
            keys = r.keys(f"*{project_id}*")
            if keys:
                r.delete(*keys)
                logger.info("Redis 清理关联 Key 共 %d 个", len(keys))
    except Exception as e:
        logger.warning("清理 Redis 缓存异常: %s", e)

    # 5. 清理磁盘物理文件
    paths_to_remove = [
        Path(settings.UPLOAD_DIR) / project_id,
        Path("/Volumes/macData/RAG_Files/uploads") / project_id,
        Path("/Volumes/macData/GenRAG_Files/uploads") / project_id,
        Path(settings.DATA_DIR) / "documents" / project_id,
        Path(settings.DATA_DIR) / "templates" / f"{project_id}.json",
        Path(settings.DATA_DIR) / "exemplars" / f"{project_id}.json",
        Path(settings.DATA_DIR) / "knowledge" / project_id,
    ]
    for p in paths_to_remove:
        try:
            if p.is_file():
                p.unlink()
                logger.info("删除物理文件: %s", p)
            elif p.is_dir():
                shutil.rmtree(p, ignore_errors=True)
                logger.info("删除物理目录: %s", p)
        except Exception as e:
            logger.warning("删除路径 %s 异常: %s", p, e)

    logger.info("✅ 项目 %s 全链路数据已彻底销毁清除完毕！", project_id)

if __name__ == "__main__":
    target_id = sys.argv[1] if len(sys.argv) > 1 else "fc28c7fff7bb"
    destroy_project(target_id, "国家市场监督法律法规")
