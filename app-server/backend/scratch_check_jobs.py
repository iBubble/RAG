import sys
import os
import json
import hashlib
from pathlib import Path

sys.path.append("/app/backend")

from core.config import settings
from core.status_tracker import get_file_status

target_pids = ["3351edac695f", "2c81146fbda1"]

for pid in target_pids:
    project_dir = Path(settings.UPLOAD_DIR) / pid
    print(f"\n================ Project: {pid} ================")
    if not project_dir.exists():
        print("Project directory does not exist.")
        continue
    
    # 扫描 UPLOAD_DIR 下的所有文件
    files_found = []
    for root, dirs, files in os.walk(str(project_dir)):
        if ".job_states" in dirs:
            dirs.remove(".job_states")
        for f in files:
            if f.startswith(".") or f.endswith(".lock"):
                continue
            path = Path(root) / f
            rel_path = str(path.relative_to(Path(settings.UPLOAD_DIR)))
            file_id = hashlib.md5(f"{pid}_{rel_path}".encode("utf-8")).hexdigest()
            files_found.append({
                "filename": f,
                "rel_path": rel_path,
                "file_id": file_id,
                "size": os.path.getsize(path)
            })
            
    print(f"Total files in disk: {len(files_found)}")
    for item in files_found:
        fid = item["file_id"]
        status_data = get_file_status(pid, fid)
        status = status_data.get("status", "none (no job state file)")
        updated = status_data.get("updated_at", "")
        err = status_data.get("error_message", "")
        print(f"File: {item['rel_path']} | Size: {item['size']} B | ID: {fid} | Status: {status} | Updated: {updated} | Err: {err}")
