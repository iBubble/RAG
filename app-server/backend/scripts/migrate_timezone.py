"""
数据库历史时间记录时区迁移脚本。
WHY: 将已有的 naive UTC 及 Z-suffix UTC 格式的时间数据统一前移 8 小时，
     以 naive 本地北京时间格式回写，保证前后端口径完全一致。
"""
from __future__ import annotations

import sys
from pathlib import Path

# 将项目根目录和 backend 目录加入 sys.path 以正常导入 core.database
backend_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(backend_dir))

from datetime import datetime, timezone, timedelta
from core.database import get_db

def to_beijing_iso(time_str: str | None) -> str | None:
    if not time_str:
        return time_str
    try:
        # 兼容处理空格分隔的非标准 ISO 格式
        normalized_str = time_str.replace(" ", "T")
        # 兼容旧版本 Python 不支持 Z 后缀的问题
        if normalized_str.endswith("Z"):
            normalized_str = normalized_str[:-1] + "+00:00"
        dt = datetime.fromisoformat(normalized_str)
        tz_bj = timezone(timedelta(hours=8))
        if dt.tzinfo is not None:
            # timezone-aware 时间转为北京本地时间，并去除时区信息
            dt_bj = dt.astimezone(tz_bj).replace(tzinfo=None)
        else:
            # naive 时间，原先默认是 UTC，声明为 UTC 后转为北京本地时间
            dt_bj = dt.replace(tzinfo=timezone.utc).astimezone(tz_bj).replace(tzinfo=None)
        return dt_bj.isoformat(timespec="seconds")
    except Exception as e:
        print(f"[Warning] 无法解析时间格式 '{time_str}': {e}")
        return time_str

def run_migration():
    print("🚀 开始执行 SQLite 历史时间戳时区纠偏...")
    
    with get_db() as conn:
        # 1. 迁移 users 表
        print(" -> 迁移 users.created_at...")
        users = conn.execute("SELECT id, created_at FROM users").fetchall()
        for u in users:
            uid, cat = u["id"], u["created_at"]
            new_cat = to_beijing_iso(cat)
            if new_cat != cat:
                conn.execute("UPDATE users SET created_at = ? WHERE id = ?", (new_cat, uid))
                
        # 2. 迁移 projects 表
        print(" -> 迁移 projects.created_at...")
        projects = conn.execute("SELECT id, created_at FROM projects").fetchall()
        for p in projects:
            pid, cat = p["id"], p["created_at"]
            new_cat = to_beijing_iso(cat)
            if new_cat != cat:
                conn.execute("UPDATE projects SET created_at = ? WHERE id = ?", (new_cat, pid))
                
        # 3. 迁移 operation_logs 表
        print(" -> 迁移 operation_logs.timestamp...")
        logs = conn.execute("SELECT id, timestamp FROM operation_logs").fetchall()
        print(f"    (共 {len(logs)} 条日志记录，正在处理...)")
        for log in logs:
            lid, ts = log["id"], log["timestamp"]
            new_ts = to_beijing_iso(ts)
            if new_ts != ts:
                conn.execute("UPDATE operation_logs SET timestamp = ? WHERE id = ?", (new_ts, lid))
                
        # 4. 迁移 metrics_history 表
        print(" -> 迁移 metrics_history.recorded_at...")
        metrics = conn.execute("SELECT id, recorded_at FROM metrics_history").fetchall()
        for m in metrics:
            mid, rat = m["id"], m["recorded_at"]
            new_rat = to_beijing_iso(rat)
            if new_rat != rat:
                conn.execute("UPDATE metrics_history SET recorded_at = ? WHERE id = ?", (new_rat, mid))

    print("🎉 历史数据迁移与时区对齐完成！")

if __name__ == "__main__":
    run_migration()
