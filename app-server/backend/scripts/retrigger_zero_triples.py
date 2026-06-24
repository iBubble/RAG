"""
扫描所有项目的 .job_states/，找出 Ollama 卡死期间
标记为 "Graph OK: 0 triples" 的文件，重置状态并重新入队 slow_queue。
"""
import os
import sys
import json
import redis
from pathlib import Path
from datetime import datetime

# WHY: 与 ecosystem.config.js 保持一致的 Redis 连接字符串
REDIS_URL = "redis://:Sy2026@sy@rag-redis:6379/0"
UPLOAD_ROOT = Path("/Volumes/SYRAID/RAG_Files/uploads")

def scan_zero_triple_files():
    """扫描所有项目，找出 0 三元组的已完成文件"""
    zero_files = []
    
    for project_dir in UPLOAD_ROOT.iterdir():
        if not project_dir.is_dir():
            continue
        
        job_states_dir = project_dir / ".job_states"
        if not job_states_dir.exists():
            continue
        
        project_id = project_dir.name
        
        for state_file in job_states_dir.glob("*.json"):
            try:
                with open(state_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                
                status = data.get("status", "")
                error_msg = data.get("error_message", "")
                file_id = data.get("file_id", state_file.stem)
                
                # 匹配条件：状态为 vectorized + 错误信息含 "0 triples"
                if status == "vectorized" and "0 triples" in error_msg:
                    # 找到对应的原始文件名
                    filename = _find_filename(project_dir, file_id)
                    zero_files.append({
                        "project_id": project_id,
                        "file_id": file_id,
                        "filename": filename or file_id,
                        "error_message": error_msg,
                        "state_file": str(state_file),
                    })
            except Exception as e:
                print(f"  ⚠️ 读取 {state_file} 失败: {e}")
    
    return zero_files


def _find_filename(project_dir: Path, file_id: str) -> str:
    """在项目目录中查找与 file_id 匹配的文件名"""
    for f in project_dir.iterdir():
        if f.is_file() and not f.name.startswith("."):
            # file_id 通常是文件的 MD5 hash，文件名在 Celery 任务参数中
            # 此处简单匹配 file_id 前缀
            if f.stem == file_id or file_id in f.stem:
                return f.name
    # 回退：直接用 file_id 加常见扩展名
    for ext in [".pdf", ".docx", ".xlsx", ".doc", ".xls", ".pptx"]:
        candidate = project_dir / f"{file_id}{ext}"
        if candidate.exists():
            return candidate.name
    return ""


def requeue_files(zero_files: list):
    """重置状态并重新入队 slow_queue"""
    from celery import Celery
    
    celery_app = Celery(
        "syrag_worker",
        broker=REDIS_URL,
        backend=REDIS_URL,
    )
    
    requeued = 0
    for item in zero_files:
        project_id = item["project_id"]
        file_id = item["file_id"]
        filename = item["filename"]
        state_file = item["state_file"]
        
        # 步骤 1: 重置 job_state 为 graph_queued
        try:
            data = {
                "file_id": file_id,
                "status": "graph_queued",
                "chunks": 0,
                "error_message": "",
                "updated_at": datetime.now().isoformat(),
            }
            with open(state_file, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"  ❌ 重置状态失败 {file_id}: {e}")
            continue
        
        # 步骤 2: 发送 Celery 任务
        try:
            celery_app.send_task(
                "worker.process_graph_extraction",
                args=[file_id, filename or f"{file_id}.pdf", project_id],
                queue="slow_queue",
            )
            requeued += 1
            print(f"  ✅ 已入队: {filename or file_id} ({project_id[:8]}...)")
        except Exception as e:
            print(f"  ❌ 入队失败 {file_id}: {e}")
    
    return requeued


def main():
    print("=" * 60)
    print("🔍 扫描 Ollama 卡死期间的 0 三元组文件...")
    print("=" * 60)
    
    zero_files = scan_zero_triple_files()
    
    if not zero_files:
        print("\n✅ 未发现 0 三元组文件，全部正常！")
        return
    
    print(f"\n📋 发现 {len(zero_files)} 个 0 三元组文件:")
    for i, item in enumerate(zero_files, 1):
        print(f"  {i}. {item['filename'] or item['file_id']} "
              f"(project={item['project_id'][:8]}...)")
    
    if "--dry-run" in sys.argv:
        print("\n⏸️  Dry run 模式，不执行重新入队。")
        return
    
    print(f"\n🚀 开始重新入队 {len(zero_files)} 个文件...")
    requeued = requeue_files(zero_files)
    
    print(f"\n{'=' * 60}")
    print(f"✅ 完成！已重新入队 {requeued}/{len(zero_files)} 个文件")
    print(f"   队列: slow_queue")
    print(f"   监控: pm2 logs shengyao-celery-slow --lines 50")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
