import sys
import os
import hashlib
from pathlib import Path

# 添加后端目录到 Python 环境变量，以便使用系统的连接工具和配置
sys.path.append('/app/backend')

from core.config import settings
from core.database import get_db
from core.vector_store import _get_client, _collection_name
from core.graph_rag import graph_engine

def get_valid_file_ids():
    """获取 Ground Truth 的 valid file IDs"""
    valid_ids = set()
    upload_root = Path(settings.UPLOAD_DIR)
    
    # 1. 扫描本地物理文件
    print(">>> 正在扫描本地物理文件...")
    if upload_root.exists():
        for file_path in upload_root.rglob('*'):
            if file_path.is_file():
                # 排除系统保留目录
                if ".job_states" in file_path.parts:
                    continue
                # 计算相对路径，格式应为 "project_id/folder/.../file.ext"
                rel_path = str(file_path.relative_to(upload_root))
                # 提取 project_id (第一段路径)
                parts = rel_path.split("/")
                if len(parts) >= 1:
                    project_id = parts[0]
                    # 生成 file_id
                    file_id = hashlib.md5(f"{project_id}_{rel_path}".encode("utf-8")).hexdigest()
                    valid_ids.add(file_id)
    
    # 2. 扫描数据库中的 web_sources
    print(">>> 正在读取 SQLite web_sources...")
    try:
        with get_db() as conn:
            rows = conn.execute("SELECT id FROM web_sources").fetchall()
            for r in rows:
                valid_ids.add(r['id'])
    except Exception as e:
        print(f"警告：无法读取 web_sources: {e}")
        
    return valid_ids

def check_table_registry(valid_ids):
    """检查 Table Registry 中的幽灵文件"""
    print(">>> 正在检查表格注册表 (Table Registry)...")
    ghosts = set()
    table_dir = Path(settings.DATA_DIR) / "tables"
    if table_dir.exists():
        for json_file in table_dir.rglob('*.json'):
            if json_file.is_file():
                file_id = json_file.stem
                if file_id not in valid_ids:
                    ghosts.add(file_id)
    return ghosts

def check_job_states(valid_ids):
    """检查任务状态文件 (.job_states) 中的幽灵文件"""
    print(">>> 正在检查任务状态 (.job_states)...")
    ghosts = set()
    upload_root = Path(settings.UPLOAD_DIR)
    if upload_root.exists():
        for state_file in upload_root.rglob('.job_states/*.json'):
            if state_file.is_file():
                file_id = state_file.stem
                if file_id not in valid_ids:
                    ghosts.add(file_id)
    return ghosts

def check_qdrant(valid_ids):
    """检查 Qdrant 中的幽灵向量切片"""
    print(">>> 正在检查 Qdrant 向量库...")
    ghost_ids = set()
    client = _get_client()
    try:
        # 获取全部存在的 file_id（为了不影响生产环境内存，通过 scroll 分页）
        # 由于我们只关心 file_id，可以用 payload 抽取
        offset = None
        seen_file_ids_in_qdrant = set()
        
        while True:
            records, offset = client.scroll(
                collection_name=_collection_name,
                limit=1000,
                with_payload=True,
                with_vectors=False,
                offset=offset
            )
            for record in records:
                fid = record.payload.get("file_id") if record.payload else None
                if fid:
                    seen_file_ids_in_qdrant.add(fid)
            
            if offset is None:
                break
                
        for fid in seen_file_ids_in_qdrant:
            if fid not in valid_ids:
                ghost_ids.add(fid)
    except Exception as e:
        print(f"警告：无法连接 Qdrant 检查幽灵文件: {e}")
    
    return ghost_ids

def check_neo4j(valid_ids):
    """检查 Neo4j 图数据库中的幽灵节点和关系"""
    print(">>> 正在检查 Neo4j 图谱数据库...")
    ghost_ids = set()
    try:
        if graph_engine._ensure_connection():
            with graph_engine._driver.session() as session:
                # 找到具有 file_id 属性的所有独立 entity 节点
                result = session.run("MATCH (n:Entity) WHERE n.file_id IS NOT NULL RETURN DISTINCT n.file_id AS file_id")
                for record in result:
                    fid = record["file_id"]
                    if fid not in valid_ids:
                        ghost_ids.add(fid)
                
                # 找到具有 file_id 属性的关联边上的 file_id
                result = session.run("MATCH ()-[r:RELATES_TO]-() WHERE r.file_id IS NOT NULL RETURN DISTINCT r.file_id AS file_id")
                for record in result:
                    fid = record["file_id"]
                    if fid not in valid_ids:
                        ghost_ids.add(fid)
    except Exception as e:
        print(f"警告：无法查询 Neo4j 检查幽灵文件: {e}")
        
    return ghost_ids

if __name__ == "__main__":
    print("=========================================")
    print("幽灵文件 / 孤儿数据 排查工具启动")
    print("=========================================")
    
    valid_ids = get_valid_file_ids()
    print(f"[基准] 发现有效物理文件/网页抓取记录共计: {len(valid_ids)} 个\n")
    
    ghost_tables = check_table_registry(valid_ids)
    ghost_states = check_job_states(valid_ids)
    ghost_qdrant = check_qdrant(valid_ids)
    ghost_neo4j = check_neo4j(valid_ids)
    
    print("\n=========================================")
    print("排查结果汇总 (按各个子系统中游离的幽灵 file_id 统计):")
    print("=========================================")
    print(f"1. 本地表格注册表 (Table Registry): 发现 {len(ghost_tables)} 个幽灵文件")
    print(f"2. 任务执行状态 (.job_states):      发现 {len(ghost_states)} 个幽灵文件")
    print(f"3. 向量数据库切片 (Qdrant chunks):  发现 {len(ghost_qdrant)} 个幽灵文件")
    print(f"4. 图数据库三元组 (Neo4j graph):    发现 {len(ghost_neo4j)} 个幽灵文件")
    
    all_ghosts = ghost_tables | ghost_states | ghost_qdrant | ghost_neo4j
    print(f"\n总计有 {len(all_ghosts)} 个 file_id 在各系统中成为孤儿。")
    print("\n若确认数据无误，您可以允许代理执行自动清理逻辑。")
    
    if all_ghosts:
        # 可选打印示例 ID
        print(f"\n示例孤儿 ID: {list(all_ghosts)[:5]}")
