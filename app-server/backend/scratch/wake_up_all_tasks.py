import os
import sys
import json
import hashlib
from pathlib import Path

# 将后端目录加入路径
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from core.config import settings
from core.database import get_db
from worker import process_document, process_graph_extraction
from core.status_tracker import update_file_status, get_file_status

print("🚀 开始扫描并恢复所有项目中悬空的学习进度...")

UPLOAD_DIR = settings.UPLOAD_DIR
print(f"上传根目录: {UPLOAD_DIR}")

# 1. 从数据库读取所有项目
with get_db() as conn:
    projects = conn.execute("SELECT id, name FROM projects").fetchall()

print(f"找到数据库中的项目数: {len(projects)}")

for p in projects:
    pid = p["id"]
    pname = p["name"]
    proj_dir = Path(UPLOAD_DIR) / pid
    if not proj_dir.is_dir():
        continue
    
    print(f"\n检查项目: {pname} ({pid})")
    
    pending_count = 0
    extracting_count = 0
    queued_count = 0
    
    for root, dirs, files in os.walk(proj_dir):
        if ".job_states" in dirs:
            dirs.remove(".job_states")
        for f in files:
            if f.startswith(".") or f.endswith(".lock"):
                continue
            path = Path(root) / f
            try:
                rel_path = str(path.relative_to(Path(UPLOAD_DIR)))
            except Exception:
                continue
            
            # 计算 file_id
            file_id = hashlib.md5(f"{pid}_{rel_path}".encode("utf-8")).hexdigest()
            status_data = get_file_status(pid, file_id)
            status = status_data.get("status", "pending")
            
            # 1. 恢复向量化任务
            if status == "pending":
                update_file_status(pid, file_id, "pending", error_message="手动唤醒重投")
                process_document.delay(str(path), file_id, f, pid)
                pending_count += 1
                
            # 2. 恢复已经卡死的 graph_extracting
            elif status == "graph_extracting":
                update_file_status(pid, file_id, "graph_queued", error_message="手动唤醒重投")
                process_graph_extraction.apply_async(
                    args=[file_id, f, pid],
                    queue="slow_queue"
                )
                extracting_count += 1
                
            # 3. 补投丢掉的 graph_queued 图谱任务
            elif status == "graph_queued":
                update_file_status(pid, file_id, "graph_queued", error_message="手动唤醒重投")
                process_graph_extraction.apply_async(
                    args=[file_id, f, pid],
                    queue="slow_queue"
                )
                queued_count += 1

    if pending_count > 0 or extracting_count > 0 or queued_count > 0:
        print(f"-> 项目 {pname} 恢复动作已触发: 补投向量化={pending_count}, 重置并提取图谱={extracting_count}, 补投图谱={queued_count}")
    else:
        print(f"-> 项目 {pname} 状态正常，无悬空任务。")

print("\n🎉 所有项目的悬空任务唤醒指令发送完毕！")
