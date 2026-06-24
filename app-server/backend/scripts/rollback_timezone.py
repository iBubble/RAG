"""
数据库历史时间记录时区回滚修复脚本。
WHY: 之前 migrate_timezone.py 错误地将已经是本地北京时间的 naive 时间数据
     再次前移了 8 小时，导致出现未来的时间点。此脚本将其识别并回滚减去 8 小时。
"""
from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta

def rollback_db():
    db_path = "/Volumes/macData/RAG_Files/shengyao.db"
    print(f"正在打开数据库进行时区回滚: {db_path}")
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # 阈值：当前时间 2026-06-05 16:55:19
    limit_time = "2026-06-05T16:55:19"
    
    # 1. 修复 operation_logs 表
    cursor.execute("SELECT id, timestamp FROM operation_logs WHERE timestamp > ?", (limit_time,))
    logs = cursor.fetchall()
    print(f"operation_logs 待回滚数据条数: {len(logs)}")
    for lid, ts in logs:
        dt = datetime.fromisoformat(ts.replace(" ", "T"))
        new_dt = dt - timedelta(hours=8)
        new_ts = new_dt.isoformat(timespec="seconds")
        cursor.execute("UPDATE operation_logs SET timestamp = ? WHERE id = ?", (new_ts, lid))
        print(f"  - Log {lid}: {ts} -> {new_ts}")
        
    # 2. 修复 metrics_history 表
    cursor.execute("SELECT id, recorded_at FROM metrics_history WHERE recorded_at > ?", (limit_time,))
    metrics = cursor.fetchall()
    print(f"metrics_history 待回滚数据条数: {len(metrics)}")
    for mid, rat in metrics:
        dt = datetime.fromisoformat(rat.replace(" ", "T"))
        new_dt = dt - timedelta(hours=8)
        new_rat = new_dt.isoformat(timespec="seconds")
        cursor.execute("UPDATE metrics_history SET recorded_at = ? WHERE id = ?", (new_rat, mid))
        print(f"  - Metrics {mid}: {rat} -> {new_rat}")
        
    conn.commit()
    conn.close()
    print("🎉 历史未来时间戳回滚对齐完成！")

if __name__ == "__main__":
    rollback_db()
