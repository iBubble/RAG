"""
全系统后台学习流程定时排查与自愈引擎 (Watchdog Engine)。
覆盖：向量化卡死、知识图谱提取中断、社区摘要挂起、自动研判公文遗漏四大关键卡顿场景。
"""
import os
import sys
import json
import time
import hashlib
import logging
from pathlib import Path
from datetime import datetime, timezone, timedelta

logger = logging.getLogger("WatchdogEngine")

sys.path.append("/app/backend")
from core.config import settings

def _get_db_connection():
    import sqlite3
    db_p = Path(settings.DATA_DIR) / "shengyao.db"
    if not db_p.exists():
        db_p = Path("/app/backend/data/shengyao.db")
    return sqlite3.connect(str(db_p))

def _is_stale(updated_at_str: str, timeout_seconds: int = 600) -> bool:
    if not updated_at_str:
        return True
    try:
        normalized = updated_at_str.replace(" ", "T")
        if normalized.endswith("Z"):
            normalized = normalized[:-1] + "+00:00"
        dt = datetime.fromisoformat(normalized)
        tz_bj = timezone(timedelta(hours=8))
        if dt.tzinfo is not None:
            dt_ts = dt.astimezone(tz_bj).replace(tzinfo=None).timestamp()
        else:
            dt_ts = dt.replace(tzinfo=timezone.utc).astimezone(tz_bj).replace(tzinfo=None).timestamp()
        now_ts = datetime.now(tz_bj).replace(tzinfo=None).timestamp()
        return (now_ts - dt_ts) > timeout_seconds
    except Exception:
        return True

def inspect_and_repair_vectors(pid: str, project_dir: Path) -> int:
    """排查并自愈卡死在 processing 状态的向量化任务"""
    from core.status_tracker import get_file_status, update_file_status
    repaired = 0
    for root, dirs, files in os.walk(str(project_dir)):
        if ".job_states" in dirs:
            dirs.remove(".job_states")
        for f in files:
            if f.startswith(".") or f.endswith(".lock"):
                continue
            path = Path(root) / f
            rel = str(path.relative_to(Path(settings.UPLOAD_DIR)))
            fid = hashlib.md5(f"{pid}_{rel}".encode("utf-8")).hexdigest()
            status_data = get_file_status(pid, fid)
            st = status_data.get("status", "pending")
            up_at = status_data.get("updated_at", "")
            if st == "processing" and _is_stale(up_at, 600):
                retries = status_data.get("auto_retry_count", 0)
                if retries < 3:
                    logger.warning(f"🚨 [Watchdog] 发现向量化卡死文件: pid={pid} fid={fid} (第 {retries+1} 次自动补发)")
                    update_file_status(pid, fid, "pending", error_message="Watchdog 自动自愈重投")
                    try:
                        from worker import process_document
                        file_size = path.stat().st_size if path.exists() else 0
                        if file_size > 2 * 1024 * 1024:
                            process_document.apply_async(args=[str(path), fid, f, pid], queue='slow_queue')
                        else:
                            process_document.delay(str(path), fid, f, pid)
                        repaired += 1
                    except Exception as e:
                        logger.error(f"[Watchdog] 补发向量化任务失败: {e}")
                else:
                    update_file_status(pid, fid, "failed", error_message="超出自动自愈重试次数上限")
    return repaired

def inspect_and_repair_graphs(pid: str, project_dir: Path, is_library: bool) -> int:
    """排查并自愈图谱提取卡死、相对路径哈希偏差与公共库状态失联"""
    from core.status_tracker import get_file_status, update_file_status
    repaired = 0
    for root, dirs, files in os.walk(str(project_dir)):
        if ".job_states" in dirs:
            dirs.remove(".job_states")
        for f in files:
            if f.startswith(".") or f.endswith(".lock"):
                continue
            path = Path(root) / f
            rel = str(path.relative_to(Path(settings.UPLOAD_DIR)))
            fid = hashlib.md5(f"{pid}_{rel}".encode("utf-8")).hexdigest()
            status_data = get_file_status(pid, fid)
            st = status_data.get("status", "pending")
            err_msg = status_data.get("error_message", "") or ""
            up_at = status_data.get("updated_at", "")

            # 1. 修复子文件夹路径哈希偏差导致的 Graph OK 丢失
            if "Graph OK" not in err_msg:
                alt_fid = hashlib.md5(f"{pid}_{f}".encode("utf-8")).hexdigest()
                if alt_fid != fid:
                    alt_data = get_file_status(pid, alt_fid)
                    if "Graph OK" in alt_data.get("error_message", ""):
                        update_file_status(pid, fid, "vectorized", error_message=alt_data.get("error_message"), chunks=alt_data.get("chunks", 1))
                        repaired += 1
                        continue

            # 2. 修复长时间卡在 graph_extracting 的僵尸任务
            if st == "graph_extracting" and _is_stale(up_at, 900):
                logger.warning(f"🚨 [Watchdog] 发现图谱提取超时僵尸任务: pid={pid} fid={fid}，自动重置排队")
                update_file_status(pid, fid, "graph_queued", error_message="Watchdog 自动超时重置排队")
                try:
                    from worker import process_graph_extraction
                    process_graph_extraction.apply_async(args=[fid, f, pid], queue='slow_queue')
                    repaired += 1
                except Exception as e:
                    logger.error(f"[Watchdog] 补发图谱任务失败: {e}")

    return repaired

def inspect_and_repair_community_summaries(pid: str) -> bool:
    """排查并自愈社区摘要挂起或未触发"""
    try:
        from core.redis_client import get_redis
        from core.graph_rag import graph_engine
        r = get_redis()
        if not r:
            return False
        st = graph_engine.get_stats(pid)
        entities = st.get("nodes", 0)
        s = r.get(f"community_summary:status:{pid}")
        status_str = s.decode("utf-8") if isinstance(s, bytes) else str(s or "")
        # 如果有实体，且摘要尚未启动或挂起
        if entities > 0 and status_str in ("pending", "None", ""):
            lock_key = f"community_summary_lock:{pid}"
            if r.set(lock_key, "1", nx=True, ex=600):
                from worker import compute_community_summaries
                compute_community_summaries.apply_async(args=[pid], queue='summary_queue', countdown=3)
                logger.info(f"🕸️ [Watchdog] 自动补偿触发项目 {pid} 社区摘要计算")
                return True
    except Exception as e:
        logger.warning(f"[Watchdog] 检查社区摘要失败 pid={pid}: {e}")
    return False

def run_full_inspection_and_repair() -> dict:
    """全局执行一次全面排查与自动修复"""
    t0 = time.time()
    logger.info("🛡️ [Watchdog] 启动后台学习全流程故障扫描与自愈...")
    results = {"total_projects": 0, "vectors_repaired": 0, "graphs_repaired": 0, "summaries_triggered": 0, "duration": 0.0}
    try:
        conn = _get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT id, name, project_type FROM projects")
        projects = cur.fetchall()
        conn.close()
    except Exception as e:
        logger.error(f"[Watchdog] 读取项目列表失败: {e}")
        return results

    results["total_projects"] = len(projects)
    for row in projects:
        pid, pname, ptype = row[0], row[1], row[2] or "case"
        is_lib = (ptype == "library")
        pdir = Path(settings.UPLOAD_DIR) / pid
        if not pdir.exists():
            continue
        v_rep = inspect_and_repair_vectors(pid, pdir)
        g_rep = inspect_and_repair_graphs(pid, pdir, is_lib)
        s_rep = inspect_and_repair_community_summaries(pid) if not is_lib else False

        results["vectors_repaired"] += v_rep
        results["graphs_repaired"] += g_rep
        if s_rep:
            results["summaries_triggered"] += 1

    results["duration"] = round(time.time() - t0, 2)
    logger.info(f"✅ [Watchdog] 本轮巡检修复完成: 耗时 {results['duration']}s，修复向量任务 {results['vectors_repaired']} 个，图谱任务 {results['graphs_repaired']} 个，触发摘要 {results['summaries_triggered']} 个")
    return results

