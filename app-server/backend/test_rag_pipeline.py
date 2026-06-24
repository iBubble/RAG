import os
import sys

# 确保能 import core 目录
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import asyncio
from core.vector_store import ingest_text, _get_client
from qdrant_client.models import Filter, FieldCondition, MatchValue
import httpx

async def test_pipeline():
    print("🚀 启动本地 RAG 链路验证...")
    
    # 1. 读取测试文件
    script_dir = os.path.dirname(os.path.abspath(__file__))
    doc_path = os.path.join(script_dir, "test_legal_doc.txt")
    if not os.path.exists(doc_path):
        print(f"❌ 找不到测试文档: {doc_path}")
        return
        
    with open(doc_path, "r", encoding="utf-8") as f:
        text = f.read()
        
    file_id = "test_doc_001"
    filename = "test_legal_doc.txt"
    project_id = "test_project"
    
    # 2. 向量入库验证 (BGE-M3)
    print("🧠 正在调用向量化接口 (BGE-M3) ...")
    try:
        total_chunks = ingest_text(text, file_id, filename, project_id)
        print(f"✅ 向量入库成功！入库分片数: {total_chunks}")
    except Exception as e:
        print(f"❌ 向量化入库失败: {e}")
        return

    # 3. 检查 Qdrant 写入
    print("🔎 正在从 Qdrant 中校验数据...")
    client = _get_client()
    try:
        scroll_res, _ = client.scroll(
            collection_name="syrag_documents",
            scroll_filter=Filter(must=[
                FieldCondition(key="file_id", match=MatchValue(value=file_id))
            ]),
            limit=5
        )
        print(f"✅ Qdrant 验证成功！读取到 {len(scroll_res)} 个分片点。")
        for idx, pt in enumerate(scroll_res):
            print(f"   分片 [{idx}]: {pt.payload.get('document', '')[:50]}...")
    except Exception as e:
        print(f"❌ Qdrant 读取失败: {e}")
        
    # 4. Ollama Q5 大模型推理测试
    print("🤖 正在发起本地大模型推理测试 (qwen3.6:35b-q4)...")
    # 容器内访问宿主机使用 host.docker.internal，但在宿主机直接测试时可以通过 localhost 访问
    # 因为本脚本在容器内执行，所以使用 docker-compose 中定义的环境变量 OLLAMA_BASE_URL
    ollama_url = os.getenv("OLLAMA_BASE_URL", "http://host.docker.internal:11434")
    try:
        async with httpx.AsyncClient(timeout=120.0) as http_client:
            res = await http_client.post(
                f"{ollama_url}/api/generate",
                json={
                    "model": "qwen3.6:35b-q4",
                    "prompt": "基于以下内容回答：什么是合同？\n内容：" + text,
                    "stream": False
                }
            )
            if res.status_code == 200:
                answer = res.json().get("response", "")
                print(f"✅ 大模型推理成功！")
                print(f"👉 问答结果:\n{answer}")
            else:
                print(f"❌ 大模型接口返回异常: {res.status_code}")
    except Exception as e:
        print(f"❌ 大模型推理调用失败: {e}")

if __name__ == "__main__":
    asyncio.run(test_pipeline())
