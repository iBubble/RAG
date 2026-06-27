import os
import sys
import json
import hashlib
from pathlib import Path

# 将后端目录加入路径
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from worker import process_document, process_graph_extraction
from core.status_tracker import update_file_status

UPLOAD_DIR = "/Volumes/SYRAID/RAG_Files/uploads"
target_pids = {"fc28c7fff7bb": "国家市场监督法律法规", "1c34280f1f56": "规章制度"}

print("🚀 开始恢复悬空的学习进度...")

for pid, pname in target_pids.items():
    proj_dir = os.path.join(UPLOAD_DIR, pid)
    if not os.path.isdir(proj_dir):
        print(f"项目目录不存在: {proj_dir}")
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
            file_id = hashlib.md5(f"{pid}_{rel_path}".encode("utf-8")).hexdigest()
            
            status_file = Path(UPLOAD_DIR) / pid / ".job_states" / f"{file_id}.json"
            status = "pending"
            if status_file.exists():
                try:
                    with open(status_file, "r") as sf:
                        data = json.load(sf)
                        status = data.get("status", "pending")
                except Exception:
                    pass
            
            # 1. 恢复向量化任务
            if status == "pending":
                update_file_status(pid, file_id, "pending")
                process_document.delay(str(path), file_id, f, pid)
                pending_count += 1
                
            # 2. 恢复已经卡死的 graph_extracting
            elif status == "graph_extracting":
                update_file_status(pid, file_id, "graph_queued")
                process_graph_extraction.apply_async(
                    args=[file_id, f, pid],
                    queue="slow_queue"
                )
                extracting_count += 1
                
            # 3. 补投因为服务热重启丢失的 graph_queued 图谱任务
            elif status == "graph_queued":
                process_graph_extraction.apply_async(
                    args=[file_id, f, pid],
                    queue="slow_queue"
                )
                queued_count += 1

    print(f"项目 {pname} 恢复完成: 补投向量化={pending_count}, 重置提取={extracting_count}, 补投图谱={queued_count}")

print("\n🎉 所有任务补投指令已发送完毕！")
