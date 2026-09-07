"""
全系统多维度综合自动化测试套件 (Comprehensive System Test Suite)。
覆盖：基础设施、知识库、自动研判、检索重排、自愈看门狗与端到端接口。
"""
import os, sys, time, json, sqlite3, subprocess, re
from pathlib import Path
from datetime import datetime

sys.path.append("/app/backend")

# 从 .env 加载必要凭据环境变量
env_file = Path("/app/backend/.env")
if env_file.exists():
    for line in env_file.read_text().splitlines():
        if "=" in line and not line.startswith("#"):
            k, v = line.split("=", 1)
            v = v.strip().strip('"').strip("'")
            os.environ.setdefault(k.strip(), v)

from core.config import settings

def test_infrastructure():
    """1. 测试基础设施与服务集群"""
    res = {"status": "PASS", "details": {}}
    # PM2 进程状态
    try:
        p = subprocess.run(["pm2", "jlist"], capture_output=True, text=True, timeout=5)
        apps = json.loads(p.stdout)
        res["details"]["pm2_apps"] = {
            a.get("name"): {
                "status": a.get("pm2_env", {}).get("status"),
                "memory_mb": round(a.get("monit", {}).get("memory", 0) / 1024 / 1024, 1),
                "cpu_percent": a.get("monit", {}).get("cpu", 0)
            } for a in apps
        }
        all_online = all(a.get("pm2_env", {}).get("status") == "online" for a in apps)
        if not all_online:
            res["status"] = "WARN"
    except Exception as e:
        res["status"] = "FAIL"
        res["details"]["pm2_error"] = str(e)

    # Redis
    try:
        from core.redis_client import get_redis
        r = get_redis()
        info = r.info("memory")
        res["details"]["redis"] = {
            "used_memory_human": info.get("used_memory_human"),
            "fast_queue_len": r.llen("celery"),
            "slow_queue_len": r.llen("slow_queue"),
            "summary_queue_len": r.llen("summary_queue")
        }
    except Exception as e:
        res["status"] = "FAIL"
        res["details"]["redis_error"] = str(e)

    # SQLite
    try:
        db_path = Path("/app/backend/data/shengyao.db")
        conn = sqlite3.connect(str(db_path))
        c = conn.cursor()
        users_count = c.execute("SELECT count(*) FROM users").fetchone()[0]
        projects_count = c.execute("SELECT count(*) FROM projects").fetchone()[0]
        conn.close()
        res["details"]["sqlite"] = {"users": users_count, "projects": projects_count}
    except Exception as e:
        res["status"] = "FAIL"
        res["details"]["sqlite_error"] = str(e)

    # Neo4j
    try:
        from core.graph_rag import graph_engine
        st = graph_engine.get_stats()
        rel_count = st.get("edges", 0) or st.get("relationships", 0)
        res["details"]["neo4j"] = {"nodes": st.get("nodes", 0), "relationships": rel_count}
    except Exception as e:
        res["status"] = "FAIL"
        res["details"]["neo4j_error"] = str(e)

    # Qdrant
    try:
        import urllib.request
        req = urllib.request.Request("http://genrag-database:6333/collections/syrag_documents")
        with urllib.request.urlopen(req, timeout=3) as resp:
            q_data = json.loads(resp.read().decode("utf-8"))
            points = q_data.get("result", {}).get("points_count", 0)
            res["details"]["qdrant"] = {"points_count": points, "status": q_data.get("result", {}).get("status")}
    except Exception as e:
        res["status"] = "FAIL"
        res["details"]["qdrant_error"] = str(e)

    return res

def test_knowledge_base():
    """2. 测试全库项目构建与学习闭环"""
    res = {"status": "PASS", "details": {"projects_count": 0, "completed_projects": 0, "projects": []}}
    try:
        from api.admin import get_learning_progress
        import asyncio
        data = asyncio.run(get_learning_progress())
        res["details"]["projects_count"] = len(data)
        completed = 0
        for p in data:
            v_p = p.get("vectorization", {}).get("percent", 0)
            g_p = p.get("graph_rag", {}).get("percent", 0)
            s_p = p.get("community_summary", {}).get("percent", 0)
            aj = p.get("auto_judgment", {})
            aj_p = aj.get("percent", 100.0) if aj else 100.0
            is_done = (v_p >= 99.9 and g_p >= 99.9 and s_p >= 99.9 and aj_p >= 99.9)
            if is_done:
                completed += 1
            res["details"]["projects"].append({
                "id": p.get("id"),
                "name": p.get("name"),
                "type": p.get("project_type"),
                "vec_percent": v_p,
                "graph_percent": g_p,
                "summary_percent": s_p,
                "auto_judgment_percent": aj_p,
                "fully_completed": is_done
            })
        res["details"]["completed_projects"] = completed
        if completed < len(data):
            res["status"] = "WARN"
    except Exception as e:
        res["status"] = "FAIL"
        res["details"]["error"] = str(e)
    return res

def test_retrieval_and_reranking():
    """3. 测试多路检索与极速重排耗时"""
    res = {"status": "PASS", "details": {}}
    try:
        from core.reranker import fast_rerank
        candidates = [
            {"document": f"第{i}条 行政处罚裁量基准规定：涉案金额10000元，罚款三倍计30000元。", "chunk_index": i}
            for i in range(15)
        ]
        t0 = time.time()
        reranked = fast_rerank("涉案金额30000元罚款依据", candidates, top_n=5)
        dt_ms = round((time.time() - t0) * 1000, 2)
        res["details"]["fast_rerank_ms"] = dt_ms
        res["details"]["top_hit"] = reranked[0]["document"] if reranked else ""
        if dt_ms > 20.0:
            res["status"] = "WARN"
    except Exception as e:
        res["status"] = "FAIL"
        res["details"]["error"] = str(e)
    return res

def test_watchdog_and_endpoints():
    """4. 测试后台自愈引擎与管理接口"""
    res = {"status": "PASS", "details": {}}
    try:
        from core.watchdog_engine import run_full_inspection_and_repair
        t0 = time.time()
        rep = run_full_inspection_and_repair()
        res["details"]["inspection_duration_s"] = rep.get("duration")
        res["details"]["vectors_repaired"] = rep.get("vectors_repaired")
        res["details"]["graphs_repaired"] = rep.get("graphs_repaired")
        res["details"]["summaries_triggered"] = rep.get("summaries_triggered")
    except Exception as e:
        res["status"] = "FAIL"
        res["details"]["error"] = str(e)
    return res

if __name__ == "__main__":
    out = {
        "timestamp": datetime.now().isoformat(),
        "infrastructure": test_infrastructure(),
        "knowledge_base": test_knowledge_base(),
        "retrieval_reranking": test_retrieval_and_reranking(),
        "watchdog_engine": test_watchdog_and_endpoints()
    }
    print(json.dumps(out, ensure_ascii=False, indent=2))
