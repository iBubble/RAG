import os
import sys
import logging

# 将 backend 路径添加到 sys.path 以便导入 core 模块
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

from core.vector_store import ingest_text, _get_client, _collection_name, _string_to_uuid
from qdrant_client import models

def test_qdrant_d1_indexing():
    logger.info("🚀 开始 D1 任务验证：Qdrant 动态索引与 Payload 预过滤测试...")
    
    file_id = "test_d1_file_999"
    filename = "test_d1_file.pdf"
    project_id = "test_d1_project_999"
    
    # 模拟切片数据
    text = (
        "特种设备安全监督检验说明。特种设备是指涉及生命安全、危险性较大的锅炉、压力容器、压力管道、电梯、起重机械、客运索道、大型游乐设施和场内专用机动车辆。特种设备使用单位应当建立特种设备安全技术档案。安全技术档案包括：设计文件、产品质量合格证明、安装及使用维护保养说明、监督检验证明等；定期检验记录；日常使用状况记录；维护保养记录；故障和事故记录。为了确保特种设备的使用安全，各使用单位应当定期开展安全隐患排查，落实安全生产主体责任，建立健全安全管理制度，配备专职的安全管理人员。同时，特种设备在投入使用前或者投入使用后三十日内，应当向直辖市或者设区的市的特种设备安全监督管理部门办理使用登记，取得使用登记证书。登记标志应当置于该特种设备的显著位置。在使用过程中，如发现异常情况，应当立即停止使用，并由专业人员进行检修，确保安全后方可重新投入运行。"
        "\n\n"
        "食品安全抽样检验操作规范。为了规范食品安全抽样检验工作，加强食品安全监督管理，保障公众身体健康和生命安全。食品安全抽样检验应当遵循科学、客观、公正、公开的原则。市场监督管理部门应当对食品生产经营者进行监督检查，发现食品生产经营者有违法行为的，应当依法予以处理。抽样检验结果表明食品不符合食品安全标准的，应当立即停止生产经营并召回。各级市场监督管理部门应当制定食品安全年度监督管理计划，明确监督检查的重点、频次和要求。食品生产经营者应当积极配合抽样检验工作，如实提供相关证照、票据和记录。对于抽样检验中发现的不合格食品，应当及时采取下架、封存、召回等风险控制措施，并向社会公布，防止不合格食品流入市场，切实保障人民群众舌尖上的安全。"
    )
    
    page_numbers = [1, 2]
    semantic_roles = ["section_header", "text_block"]
    departments = ["特种设备科", "食品安全科"]
    case_types = ["行政处罚", "许可审批"]
    
    # 1. 写入向量库
    logger.info("1. 正在调用 ingest_text 写入测试向量...")
    inserted = ingest_text(
        text=text,
        file_id=file_id,
        filename=filename,
        project_id=project_id,
        page_numbers=page_numbers,
        semantic_roles=semantic_roles,
        departments=departments,
        case_types=case_types
    )
    logger.info(f"写入完成，成功入库了 {inserted} 个 chunks")
    assert inserted >= 2, f"预期写入至少 2 个 points，实际写入 {inserted}"

    # 2. 从 Qdrant 读取并校验 Payload
    logger.info("2. 正在直连 Qdrant 获取 Point Payload 并进行校验...")
    client = _get_client()
    
    # 获取第一个 point 的 ID
    point_id_1 = _string_to_uuid(f"{file_id}__chunk_0")
    point_id_2 = _string_to_uuid(f"{file_id}__chunk_1")
    
    res = client.retrieve(
        collection_name=_collection_name,
        ids=[point_id_1, point_id_2]
    )
    
    assert len(res) == 2, f"预期检索到 2 个 point，实际检索到 {len(res)}"
    
    p1 = [p for p in res if p.id == point_id_1][0]
    p2 = [p for p in res if p.id == point_id_2][0]
    
    logger.info(f"Point 1 Payload: {p1.payload}")
    logger.info(f"Point 2 Payload: {p2.payload}")
    
    # 验证动态属性是否被成功写入
    assert p1.payload["page_number"] == 1
    assert p1.payload["semantic_role"] == "section_header"
    assert p1.payload["department"] == "特种设备科"
    assert p1.payload["case_type"] == "行政处罚"
    
    assert p2.payload["page_number"] == 2
    assert p2.payload["semantic_role"] == "text_block"
    assert p2.payload["department"] == "食品安全科"
    assert p2.payload["case_type"] == "许可审批"
    
    logger.info("✅ 动态 Payload 属性写入校验通过！")
    
    # 3. 测试 Qdrant HNSW 预过滤检索
    logger.info("3. 正在执行 Payload 预过滤检索测试...")
    
    # 模拟以“特种设备科”过滤检索
    query_vector = [0.1] * 1024  # 模拟一个 1024 维的 Dense 向量，维度和模型匹配即可
    search_res = client.query_points(
        collection_name=_collection_name,
        query=query_vector,
        using="dense",
        query_filter=models.Filter(
            must=[
                models.FieldCondition(
                    key="department",
                    match=models.MatchValue(value="特种设备科")
                )
            ]
        ),
        limit=5
    )
    
    logger.info(f"过滤检索到 {len(search_res.points)} 条结果")
    for r in search_res.points:
        logger.info(f"检索命中 ID: {r.id}, department: {r.payload.get('department')}")
        assert r.payload.get("department") == "特种设备科", "检索到的 point 必须过滤并属于特种设备科！"
        
    logger.info("🎉 D1 Qdrant 动态索引与 HNSW 预过滤验证完全成功！")

if __name__ == "__main__":
    test_qdrant_d1_indexing()
