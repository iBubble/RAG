"""
图谱提取与学习任务进度自动监控和重试脚本。
WHY: 监听全局 8 个项目的向量化、知识图谱提取、社区摘要及智能学习预计算进度。
     在检测到 Ghost Task (幽灵任务) 或 Stale Processing (卡死任务) 时自动触发重试。
"""
import sys
import os
import time
import asyncio

# 1. 动态加载 .env
def load_env():
    env_path = '/app/backend/.env'
    if os.path.exists(env_path):
        with open(env_path) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#'):
                    parts = line.split('=', 1)
                    if len(parts) == 2:
                        k = parts[0].strip()
                        v = parts[1].strip()
                        if (v.startswith('"') and v.endswith('"')) or (v.startswith("'") and v.endswith("'")):
                            v = v[1:-1]
                        os.environ[k] = v

load_env()
sys.path.append('/app/backend')

from api.admin import get_learning_progress, get_failed_files, retry_failed_file, RetryFileRequest

async def auto_retry_failures(project_id: str):
    """自动获取失败的文件并加入对应的重试队列。"""
    try:
        failed_list = await get_failed_files(project_id, admin={})
        for f in failed_list:
            filename = f.get("filename")
            stage = f.get("stage")
            err = f.get("error", "")
            print(f"⚠️ 发现失败文件: 项目={project_id}, 文件={filename}, 阶段={stage}, 错误={err}。正在自动重试...")
            req = RetryFileRequest(filename=filename, stage=stage)
            await retry_failed_file(project_id, req, admin={})
    except Exception as e:
        print(f"❌ 自动重试异常: {e}")

async def main():
    print("🚀 启动图谱提取与预计算任务进度自动监控...")
    while True:
        try:
            res = await get_learning_progress(admin={})
            
            tot_vec, comp_vec = 0, 0
            tot_graph, comp_graph = 0, 0
            tot_comm, comp_comm = 0, 0
            tot_pre, comp_pre = 0, 0
            
            for p in res:
                pid = p["id"]
                
                # 1. 向量化
                v = p.get("vectorization", {})
                tot_vec += v.get("total", 0)
                comp_vec += v.get("completed", 0)
                
                # 2. 图谱
                g = p.get("graph_rag", {})
                tot_graph += g.get("total", 0)
                comp_graph += g.get("completed", 0)
                
                # 3. 社区摘要
                c = p.get("community_summary", {})
                tot_comm += c.get("total", 0)
                comp_comm += c.get("completed", 0)
                
                # 4. 预计算
                pre = p.get("precompute", {})
                for mode in ("generate", "replace", "clone"):
                    mdata = pre.get(mode, {})
                    tot_pre += mdata.get("total", 0)
                    comp_pre += mdata.get("completed", 0)
                
                # 触发此项目的错误/卡死自动重试
                await auto_retry_failures(pid)
            
            # 计算百分比
            p_vec = int(comp_vec / tot_vec * 100) if tot_vec > 0 else 100
            p_graph = int(comp_graph / tot_graph * 100) if tot_graph > 0 else 100
            p_comm = int(comp_comm / tot_comm * 100) if tot_comm > 0 else 100
            p_pre = int(comp_pre / tot_pre * 100) if tot_pre > 0 else 100
            
            overall = int((p_vec + p_graph + p_comm + p_pre) / 4)
            
            print(f"📊 [{time.strftime('%Y-%m-%d %H:%M:%S')}] 总体学习完成率: {overall}% | "
                  f"1. 向量化入库: {comp_vec}/{tot_vec} ({p_vec}%) | "
                  f"2. 知识图谱提取: {comp_graph}/{tot_graph} ({p_graph}%) | "
                  f"3. 图谱社区摘要: {comp_comm}/{tot_comm} ({p_comm}%) | "
                  f"4. 智能学习预计算: {comp_pre}/{tot_pre} ({p_pre}%)")
            
            # 达成 100% 判定
            import redis
            r = redis.Redis.from_url(os.getenv('REDIS_URL', 'redis://:Sy2026@sy@rag-redis:6379/0'))
            fast_q = r.llen('celery')
            slow_q = r.llen('slow_queue')
            
            if (comp_vec >= tot_vec and comp_graph >= tot_graph and 
                comp_comm >= tot_comm and comp_pre >= tot_pre and 
                fast_q == 0 and slow_q == 0):
                print("🎉 [SUCCESS] 所有项目学习任务已 100% 成功完成，积压队列已清空！监控退出。")
                break
                
        except Exception as e:
            print(f"❌ 监控轮询发生异常: {e}")
            
        await asyncio.sleep(60)

if __name__ == "__main__":
    asyncio.run(main())
