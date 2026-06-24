import json
import logging
import os
from pathlib import Path
from neo4j import GraphDatabase
import redis
from core.config import settings
from worker import process_graph_extraction

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

project_id = "5f2ba65331ed"

# 1. Neo4j Cleanup
logger.info("🧹 开始清理 Neo4j 图谱和社区...")
try:
    driver = GraphDatabase.driver(settings.NEO4J_URI, auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD))
    with driver.session() as session:
        result = session.run("MATCH (n) WHERE n.project_id = $pid DETACH DELETE n", pid=project_id)
        summary = result.consume()
        logger.info(f"✅ Neo4j 清理完成: 删除了 {summary.counters.nodes_deleted} 个节点, {summary.counters.relationships_deleted} 个关系。")
    driver.close()
except Exception as e:
    logger.error(f"❌ Neo4j 清理失败: {e}")

# 2. Redis Cleanup
logger.info("🧹 开始清理 Redis 进度缓存...")
try:
    r = redis.Redis(host="rag-redis", port=6379, db=0, password="Sy2026@sy", decode_responses=True)
    keys = r.keys(f"community_summary:*{project_id}*")
    if keys:
        r.delete(*keys)
        logger.info(f"✅ 删除了 {len(keys)} 个 Redis 进度缓存键。")
    else:
        logger.info("✅ Redis 缓存无内容。")
except Exception as e:
    logger.error(f"❌ Redis 清理失败: {e}")

# 3. Update job_states and Enqueue
logger.info("🚀 开始重置文件状态并重新排队...")
status_dir = Path(settings.UPLOAD_DIR) / project_id / ".job_states"
source_dir = Path(settings.UPLOAD_DIR) / project_id
enqueued = 0

if not status_dir.exists():
    logger.error(f"找不到状态目录: {status_dir}")
else:
    for json_file in status_dir.glob("*.json"):
        file_id = json_file.stem
        try:
            with open(json_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            
            if data.get("status") in ["vectorized", "graph_queued", "graph_extracting"]:
                filename = data.get("filename", f"{file_id}.pdf")
                
                matched_files = list(source_dir.glob(f"{file_id}.*"))
                if matched_files:
                    filename = matched_files[0].name
                
                data["status"] = "graph_queued"
                data["error_message"] = "Re-queued for 120s graph extraction"
                with open(json_file, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)
                
                process_graph_extraction.apply_async(
                    args=[file_id, filename, project_id],
                    queue='slow_queue'
                )
                enqueued += 1
        except Exception as e:
            logger.error(f"处理文件 {json_file.name} 失败: {e}")

logger.info(f"🎉 全部完成！成功将 {enqueued} 个文件打入 slow_queue 开始重新提取图谱。")
