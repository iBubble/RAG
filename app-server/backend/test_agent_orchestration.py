# -*- coding: utf-8 -*-
import dotenv
dotenv.load_dotenv()
import asyncio
import sys
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s - %(message)s",
    stream=sys.stdout
)

async def main():
    from core.agents.orchestrator import run_orchestration
    from core.database import get_db
    
    print("开始多 Agent 真实案件协同测试...", flush=True)
    project_id = "fc6a91f57b0a"
    question = "目前最有利的方法是？"
    
    # 模拟前端全选项目文档
    file_ids = [
        "8201a34b946607b4c703a4efa12f534d",
        "4b18b0c45f4f10e9dd34d8d952accd60",
        "b6a023a7050ea850ffb188a57ff05dc9",
        "b3e77b3b55a2b2a971b99e79d36a4e3a",
        "d782131bbda3fe4e5955ca3ef35e2aa3",
        "b39f40152b37c81397c14aeba1662c2d",
        "8563148c390ef23ec0b8dbd0d7204d86",
        "e538ff88f983ee9c39f57c4326ba5498"
    ]
        
    print(f"获取到项目 {project_id} 关联的文件数: {len(file_ids)}", flush=True)
    
    # 模拟运行
    result = await run_orchestration(
        user_message=question,
        project_id=project_id,
        file_ids=file_ids,
        enable_critique=True
    )
    
    print("\n--- 执行结果 ---", flush=True)
    print(f"Success: {result.error is None}", flush=True)
    print(f"Error: {result.error}", flush=True)
    print(f"Agent Chain: {' -> '.join(result.agent_chain)}", flush=True)
    print(f"Final Answer:\n{result.final_answer}", flush=True)
    print(f"Critique:\n{result.critique}", flush=True)
    print(f"Worker Answer:\n{result.worker_answer}", flush=True)
    print(f"Elapsed: {result.elapsed_seconds:.2f}s", flush=True)

if __name__ == "__main__":
    asyncio.run(main())
