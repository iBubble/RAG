from core.redis_client import get_redis
import json

pid = "053c8cdb97f1"
r = get_redis()
if r:
    running = r.get(f"precompute:running:{pid}")
    queued = r.get(f"precompute:queued:{pid}")
    current = r.get(f"precompute:current_section:{pid}")
    task_id = r.get(f"precompute:task_id:{pid}")
    
    print(json.dumps({
        "running": running.decode("utf-8") if running else None,
        "queued": queued.decode("utf-8") if queued else None,
        "current_section": current.decode("utf-8") if current else None,
        "task_id": task_id.decode("utf-8") if task_id else None
    }, indent=2))
else:
    print("Redis not available")
