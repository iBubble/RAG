import os
import json
import hashlib
from pathlib import Path
import sys

# Add backend root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.config import settings
from core.vector_store import get_chunk_count

def main():
    upload_root = Path(settings.UPLOAD_DIR)
    if not upload_root.exists():
        print(f"❌ 上传目录不存在: {upload_root}")
        return

    print(f"🔍 开始扫描并修复零切片记录，上传目录: {upload_root}")
    repaired_count = 0

    for project_dir in sorted(upload_root.iterdir()):
        if not project_dir.is_dir():
            continue
        
        project_id = project_dir.name
        job_states_dir = project_dir / ".job_states"
        if not job_states_dir.exists():
            continue

        print(f"\n📂 项目: {project_id}")
        for state_file in sorted(job_states_dir.glob("*.json")):
            try:
                with open(state_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                
                status = data.get("status")
                chunks = data.get("chunks", 0)
                file_id = data.get("file_id")

                if status == "vectorized" and chunks == 0:
                    # 查询 Qdrant 真实切片数
                    real_chunks = get_chunk_count(file_id)
                    if real_chunks > 0:
                        data["chunks"] = real_chunks
                        # 写回文件
                        with open(state_file, "w", encoding="utf-8") as f:
                            json.dump(data, f, ensure_ascii=False, indent=2)
                        print(f"  ✅ 修复文件 {file_id}: status={status}, chunks: 0 -> {real_chunks}")
                        repaired_count += 1
                    else:
                        print(f"  ⚠️ 文件 {file_id}: status={status}, Qdrant中无对应切片")
                elif status == "vectorized":
                    print(f"  🟢 文件 {file_id}: status={status}, chunks={chunks} (无需修复)")

            except Exception as e:
                print(f"  ❌ 读取/更新 {state_file.name} 失败: {e}")

    print(f"\n🎉 修复完成！共修复了 {repaired_count} 个文件记录。")

if __name__ == "__main__":
    main()
