import os
import sys
import json
import shutil
import hashlib
from pathlib import Path
from datetime import datetime

sys.path.append("/app/backend")
from core.config import settings
from core.database import get_db

DEMO_CASES = [
    {
        "id": "case_guazi_2026",
        "name": "焦糖瓜子配料表争议",
        "src_dir": "/app/backend/docs/测试数据/CASE-A-2026-0001-焦糖瓜子配料表争议"
    },
    {
        "id": "case_beef_2026",
        "name": "卤香牛肉执行标准与分装资质",
        "src_dir": "/app/backend/docs/测试数据/CASE-B-2026-0002-卤香牛肉执行标准与分装资质"
    }
]

def init_demo_projects():
    upload_root = Path(settings.UPLOAD_DIR)
    data_root = Path(settings.DATA_DIR)
    
    with get_db() as conn:
        admin_row = conn.execute("SELECT id FROM users WHERE role = 'admin' LIMIT 1").fetchone()
        admin_id = admin_row["id"] if admin_row else "0b84397e-238f-401c-8311-52298a1ec5d3"

        for case in DEMO_CASES:
            p_id = case["id"]
            p_name = case["name"]
            src_dir = Path(case["src_dir"])
            
            # 1. 确保数据库中有项目
            existing = conn.execute("SELECT id FROM projects WHERE id = ? OR name = ?", (p_id, p_name)).fetchone()
            now_str = datetime.now().isoformat()
            if existing:
                real_id = existing["id"]
                conn.execute(
                    "UPDATE projects SET name = ?, owner_id = ?, visibility = 'public' WHERE id = ?",
                    (p_name, admin_id, real_id)
                )
                case["id"] = real_id
                print(f"✅ 更新已存在项目: {p_name} (ID: {real_id})")
            else:
                conn.execute(
                    """INSERT INTO projects 
                       (id, name, owner_id, visibility, project_type, metadata_json, created_at, sort_order)
                       VALUES (?, ?, ?, 'public', 'case', '{}', ?, 0)""",
                    (p_id, p_name, admin_id, now_str)
                )
                print(f"✅ 创建新项目: {p_name} (ID: {p_id})")
            conn.commit()

            # 2. 复制案卷材料文件到上传目录
            real_id = case["id"]
            dest_dir = upload_root / real_id
            if dest_dir.exists():
                shutil.rmtree(dest_dir)
            dest_dir.mkdir(parents=True, exist_ok=True)

            file_count = 0
            if src_dir.exists():
                for root, dirs, files in os.walk(src_dir):
                    dirs[:] = [d for d in dirs if not d.startswith(".")]
                    for f in files:
                        if f.startswith("."):
                            continue
                        s_path = Path(root) / f
                        rel_path = s_path.relative_to(src_dir)
                        t_path = dest_dir / rel_path
                        t_path.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(s_path, t_path)
                        file_count += 1
            print(f"📁 已同步 {file_count} 个案卷材料文件至 {dest_dir}")

            # 3. 建立 documents 持久化目录
            (data_root / "documents" / real_id).mkdir(parents=True, exist_ok=True)
            (data_root / "triage").mkdir(parents=True, exist_ok=True)
            (data_root / "judgment").mkdir(parents=True, exist_ok=True)
            (data_root / "adjudication").mkdir(parents=True, exist_ok=True)

    print("\n🎉 项目建档与材料迁移完成！")

if __name__ == "__main__":
    init_demo_projects()
