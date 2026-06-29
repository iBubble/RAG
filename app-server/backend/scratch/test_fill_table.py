import sys
import os
import logging

# Configure logging first
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s")
logging.getLogger("api.generate").setLevel(logging.INFO)
logging.getLogger("core.llm_engine").setLevel(logging.INFO)

# Load env variables from .env
env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")
if os.path.exists(env_path):
    with open(env_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, val = line.split("=", 1)
                os.environ[key.strip()] = val.strip().strip('"').strip("'")

# Set essential defaults if still missing
os.environ.setdefault("PYTHONPATH", ".")
os.environ.setdefault("QDRANT_URL", "http://genrag-database:6333")
os.environ.setdefault("REDIS_URL", "redis://:Sy2026@sy@genrag-redis:6379/0")

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi.testclient import TestClient
from main import app
from api.generate import get_current_user

# Mock authentication
app.dependency_overrides[get_current_user] = lambda: {"username": "admin"}

client = TestClient(app)

# Scan actual upload directory to generate file IDs
import hashlib
from pathlib import Path
from core.config import settings

project_id = "15e2a7f1208b"
upload_root = Path(settings.UPLOAD_DIR)
project_dir = upload_root / project_id
file_ids = []
files_found = []

if project_dir.exists():
    for root, dirs, files in os.walk(str(project_dir)):
        dirs[:] = [d for d in dirs if not d.startswith('.')]
        for f in files:
            if f.startswith('.'):
                continue
            fpath = Path(root) / f
            rel_path = str(fpath.relative_to(upload_root))
            fid = hashlib.md5(f"{project_id}_{rel_path}".encode("utf-8")).hexdigest()
            file_ids.append(fid)
            files_found.append((fid, f))

print("Files found by disk scan:", files_found)

payload = {
    "project_id": project_id,
    "template_html": """
    <p>投诉人姓名：______</p>
    <p>被投诉主体：______</p>
    <p>投诉时间：______</p>
    <p>投诉事实详情：______</p>
    """,
    "file_ids": file_ids,
    "ref_ids": [],
    "ref_global_lib": False,
    "model": "qwen3.6:35b-q4"
}

print("Sending fill-table request...")
try:
    resp = client.post("/api/generate/fill-table", json=payload, timeout=600)
    print("Status Code:", resp.status_code)
    try:
        print("Response JSON:", resp.json())
    except Exception:
        print("Raw Response:", resp.text)
except Exception as e:
    print("Request failed:", e)
