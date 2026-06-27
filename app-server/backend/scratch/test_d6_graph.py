import sys
sys.path.append("/app/backend")

import asyncio
from core.graph_rag import graph_engine
from core.vector_store import get_all_chunks_with_payload

project_id = 'a179bfa2f2ef'
file_id = '33f11d34c10b80a3eda53fc12e7b6c0c'
filename = 'test_dogo_file.pdf'

print("🚀 1. 尝试从 Qdrant 中获取分块的 payload...")
payloads = get_all_chunks_with_payload(file_id, limit=10)
if not payloads:
    print("⚠️ 未找到任何 payloads，可能该 file_id 尚未在 Qdrant 中向量化或已被删除")
    # 为了测试，我们手动生成一个 Mock payload
    payloads = [
        {
            "document": "当事人张三，统一社会信用代码为91110108MA00000000，因涉嫌虚假宣传被处以罚款120000元。本案依据《中华人民共和国行政处罚法》第57条规定...",
            "chunk_index": 0,
            "page_number": 1,
            "semantic_role": "section_header"
        },
        {
            "document": "以下是本案的罚款细节。本决定自送达之日起生效。当事人有陈述和申辩的权利。",
            "chunk_index": 1,
            "page_number": 2,
            "semantic_role": "text_block"
        }
    ]
    print("   -> 已使用 Mock 数据进行测试")

print(f"🚀 2. 尝试向 Neo4j 增量写入 DoCO 树节点及表单字段-凭证拓扑关系...")
graph_engine.ingest_doco_and_form_relations(
    filename=filename,
    project_id=project_id,
    file_id=file_id,
    chunks_payloads=payloads
)

print("🚀 3. 使用 Cypher 查询并验证 Neo4j 中的连接...")
if graph_engine._ensure_connection():
    with graph_engine._driver.session() as s:
        # 查询 Document 和 EvidenceUnit
        res_doc = s.run(
            "MATCH (d:Document {id: $fid})-[:HAS_ELEMENT]->(eu:EvidenceUnit) "
            "RETURN d.name AS doc_name, eu.id AS eu_id, eu.semantic_role AS role",
            fid=file_id
        ).data()
        print(f"   -> 发现 Document-EvidenceUnit 关系数: {len(res_doc)}")
        for r in res_doc[:3]:
            print(f"      [DoCO 第一层] {r['doc_name']} -> {r['eu_id']} ({r['role']})")
            
        # 查询 FormField 和 EvidenceUnit
        res_ff = s.run(
            "MATCH (ff:FormField)-[:EVIDENCE_BY]->(eu:EvidenceUnit {file_id: $fid}) "
            "RETURN ff.name AS field_name, eu.id AS eu_id",
            fid=file_id
        ).data()
        print(f"   -> 发现 FormField-EvidenceUnit 关系数: {len(res_ff)}")
        for r in res_ff[:5]:
            print(f"      [拓扑第二层] {r['field_name']} -> {r['eu_id']}")
            
        assert len(res_doc) > 0, "❌ 缺少 DoCO 第一层关系"
        assert len(res_ff) > 0, "❌ 缺少 FormField 第二层拓扑关系"
        print("   ✅ 第一层与第二层拓扑连接验证 100% 成功！")

        print("🚀 4. 测试增量清理 delete_by_file_id 级联删除...")
        graph_engine.delete_by_file_id(file_id, project_id)
        
        # 再次查询确认已被清理
        res_doc_cleaned = s.run(
            "MATCH (d:Document {id: $fid}) RETURN d", fid=file_id
        ).data()
        res_eu_cleaned = s.run(
            "MATCH (eu:EvidenceUnit {file_id: $fid}) RETURN eu", fid=file_id
        ).data()
        res_ff_cleaned = s.run(
            "MATCH (ff:FormField {project_id: $pid}) RETURN ff", pid=project_id
        ).data()
        
        print(f"   -> 清理后 Document 节点数: {len(res_doc_cleaned)}")
        print(f"   -> 清理后 EvidenceUnit 节点数: {len(res_eu_cleaned)}")
        print(f"   -> 清理后 FormField 节点数: {len(res_ff_cleaned)}")
        
        assert len(res_doc_cleaned) == 0, "❌ Document 节点未完全清理"
        assert len(res_eu_cleaned) == 0, "❌ EvidenceUnit 节点未完全清理"
        assert len(res_ff_cleaned) == 0, "❌ 孤立的 FormField 节点未完全清理"
        print("   ✅ 级联清理验证 100% 成功！")
else:
    print("❌ Neo4j 无法连接！")
