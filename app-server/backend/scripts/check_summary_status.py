import sys
import os

# 确保 backend 路径在 sys.path 中
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from neo4j import GraphDatabase
from core.config import settings
from core.redis_client import get_redis

def main():
    driver = GraphDatabase.driver(settings.NEO4J_URI, auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD))
    r = get_redis()
    
    with driver.session() as s:
        # 获取所有唯一的 project_id
        res = s.run("MATCH (c:Community) RETURN DISTINCT c.project_id AS pid")
        pids = [rec["pid"] for rec in res if rec["pid"]]
        
        print("=== Community Summary Status ===")
        for pid in sorted(pids):
            total = s.run(
                "MATCH (c:Community {project_id: $pid}) RETURN count(c) AS cnt", 
                pid=pid
            ).single()["cnt"]
            
            pending = s.run(
                "MATCH (c:Community {project_id: $pid}) WHERE c.summary IS NULL RETURN count(c) AS cnt", 
                pid=pid
            ).single()["cnt"]
            
            redis_status = r.get(f"community_summary:status:{pid}") if r else None
            redis_completed = r.get(f"community_summary:completed:{pid}") if r else None
            redis_total = r.get(f"community_summary:total:{pid}") if r else None
            
            print(f"Project: {pid:16s} | Total: {total:3d} | Pending: {pending:3d} | Redis Status: {redis_status} | Redis Completed: {redis_completed}/{redis_total}")
            
    driver.close()

if __name__ == "__main__":
    main()
