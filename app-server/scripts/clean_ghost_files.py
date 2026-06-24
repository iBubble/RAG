import sys
import os
import shutil
from pathlib import Path

# 添加后端目录
sys.path.append('/app/backend')
from core.config import settings
from core.graph_rag import graph_engine

# 复用检查脚本的逻辑来获取幽灵列表
from check_ghost_files import get_valid_file_ids, check_table_registry, check_job_states, check_qdrant, check_neo4j

def clean_all_ghosts():
    valid_ids = get_valid_file_ids()
    print(f"[清理基准] 有效物理文件/网页抓取记录共计: {len(valid_ids)} 个\n")
    
    ghost_tables = check_table_registry(valid_ids)
    ghost_states = check_job_states(valid_ids)
    ghost_qdrant = check_qdrant(valid_ids)
    ghost_neo4j = check_neo4j(valid_ids)
    
    all_ghosts = ghost_tables | ghost_states | ghost_qdrant | ghost_neo4j
    if not all_ghosts:
        print("系统干净，无需清理。")
        return
    
    print(f"\n=========================================")
    print(f"开始深度清理 {len(all_ghosts)} 个幽灵文件...")
    print(f"=========================================\n")
    
    # 1. Table Registry 清理
    table_dir = Path(settings.DATA_DIR) / "tables"
    for fid in ghost_tables:
        for json_file in table_dir.rglob(f"{fid}.json"):
            try:
                json_file.unlink()
                print(f"  ✅ [Table Registry] 已删除物理表结构残留 {json_file}")
            except Exception as e:
                print(f"  ❌ [Table Registry] 删除失败 {json_file}: {e}")
                
        # 顺便尝试从 Qdrant 删除 table_index (以防之前漏查)
        try:
            from core.vector_store import _get_client, _collection_name
            from qdrant_client.models import Filter, FieldCondition, MatchValue, FilterSelector
            client = _get_client()
            client.delete(
                collection_name=_collection_name,
                points_selector=FilterSelector(
                    filter=Filter(
                        must=[FieldCondition(key="file_id", match=MatchValue(value=fid))]
                    )
                ),
            )
            print(f"  ✅ [Qdrant Table Index] 清理了关联索引 (若存在): {fid}")
        except Exception as e:
            print(f"  ❌ [Qdrant] 无法清理表索引: {e}")
            
    # 2. Neo4j 清理
    for fid in ghost_neo4j:
        try:
            # Graph_engine 方法自带确保连接，并执行删除关系和游离节点
            rels_deleted = graph_engine.delete_by_file_id(fid)
            print(f"  ✅ [Neo4j] file_id={fid} 清理完成，删除了 {rels_deleted} 个失效图谱关系及游离节点。")
        except Exception as e:
            print(f"  ❌ [Neo4j] file_id={fid} 清理失败: {e}")
            
    # 3. .job_states 清理
    upload_root = Path(settings.UPLOAD_DIR)
    for fid in ghost_states:
        for state_file in upload_root.rglob(f".job_states/{fid}.json"):
            try:
                state_file.unlink()
                print(f"  ✅ [.job_states] 已删除状态残留 {state_file}")
            except Exception as e:
                print(f"  ❌ [.job_states] 删除失败 {state_file}: {e}")
                
    # 4. Qdrant Chunks 清理
    for fid in ghost_qdrant:
        try:
            from core.vector_store import delete_by_file_id
            deleted_chunks = delete_by_file_id(fid)
            print(f"  ✅ [Qdrant Chunks] file_id={fid} 清理完成，删除了 {deleted_chunks} 个切片向量。")
        except Exception as e:
            print(f"  ❌ [Qdrant Chunks] file_id={fid} 清理失败: {e}")
            
    # 5. 连带清理空文件夹
    print("\n--- 执行末端清理 ---")
    cleared_dirs = 0
    # topdown=False 表示从最内层子目录向外层删，这样嵌套的空目录能一起被删
    for dirpath, dirnames, filenames in os.walk(str(upload_root), topdown=False):
        try:
            dp = Path(dirpath)
            # 不删根目录
            if dp == upload_root:
                continue
            
            # 如果只剩下空的 .job_states 文件夹，也可以将其删除
            if dp.name == ".job_states" and not any(dp.iterdir()):
                dp.rmdir()
                cleared_dirs += 1
                continue
                
            # 看看是否空目录
            if not any(dp.iterdir()):
                dp.rmdir()
                cleared_dirs += 1
                print(f"  ✅ [Folder Cleanup] 删除了空文件夹: {dp}")
        except Exception:
            pass
            
    print(f"\n清理完成。连带删除了 {cleared_dirs} 个空目录。")

if __name__ == "__main__":
    clean_all_ghosts()
