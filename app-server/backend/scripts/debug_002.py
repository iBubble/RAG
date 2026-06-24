import asyncio
import os
import sys

# 将 backend 路径加入 sys.path
backend_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if backend_path not in sys.path:
    sys.path.append(backend_path)

from core.retrieval_pipeline import run_retrieval
from core.intent_classifier import classify_intent

async def main():
    message = "整治地块编号开发复垦001#和开发复垦002#预计新增耕地面积一共是多少？"
    project_id = "7e80966d0bf2"
    file_ids = ["b5ec2ed0598af9fb2ef3b840d071ff75"]
    
    # 1. 意图分类
    intent_result = await classify_intent(message)
    print("=== 1. 意图分类 ===")
    print("意图分类:", intent_result.intent)
    print("策略参数:", intent_result.strategy)
    
    # 2. 调用检索管线
    print("\n=== 2. 执行检索管线 ===")
    retrieval = await run_retrieval(
        search_query=message,
        original_message=message,
        project_id=project_id,
        file_ids=file_ids,
        strategy=intent_result.strategy
    )
    
    print("\n=== 3. 检索结果分析 ===")
    print("检索到的 Context 大小:", len(retrieval.context))
    print("entity_detail 长度:", len(retrieval.entity_detail))
    print("entity_detail 内容:")
    print(retrieval.entity_detail)
    print("\ntable_stats_context 长度:", len(retrieval.table_stats_context))
    if retrieval.table_stats_context:
        print("table_stats_context 前500字:")
        print(retrieval.table_stats_context[:500])
    
    print("\nvector_context 长度:", len(retrieval.vector_context))

if __name__ == "__main__":
    asyncio.run(main())
