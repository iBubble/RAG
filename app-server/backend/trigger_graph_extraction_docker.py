import os
import json
import hashlib
from pathlib import Path

import sys
sys.path.append("/app/backend")

from worker import process_graph_extraction
from core.status_tracker import update_file_status
from core.config import settings

project_id = "cd2974761e91"
uploads_dir = Path(settings.UPLOAD_DIR) / project_id
states_dir = uploads_dir / ".job_states"

triggered_count = 0

for state_file in states_dir.glob("*.json"):
    data = json.loads(state_file.read_text())
    
    # Check if status is "graph_queued" (since we already modified them on host)
    if data.get("status") == "graph_queued":
        file_id = data.get("file_id")
        
        basename = "unknown.pdf"
        for root, dirs, files in os.walk(uploads_dir):
            if ".job_states" in dirs: dirs.remove(".job_states")
            for f in files:
                rel_path = str(Path(root, f).relative_to(uploads_dir.parent))
                if hashlib.md5(f"{project_id}_{rel_path}".encode()).hexdigest() == file_id:
                    basename = f
                    break
        
        print(f"Triggering graph extraction for {basename} ({file_id})")
        # Ensure it stays graph_queued
        update_file_status(project_id, file_id, "graph_queued")
        process_graph_extraction.apply_async(args=[file_id, basename, project_id], queue='slow_queue')
        triggered_count += 1

print(f"Triggered {triggered_count} graph extractions.")
