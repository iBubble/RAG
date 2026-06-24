"""
验证 Table Registry 注册完整性。
检查: 本地 JSON 文件数量 / Qdrant table_index 向量 / Excel 文件覆盖率。
"""
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from pathlib import Path
from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parents[1] / ".env")

from core.config import settings
from core.database import get_db

TABLE_DIR = Path(settings.DATA_DIR) / "tables"
PROJECT_ID = "5f2ba65331ed"  # 泸县项目

def main():
    print(f"=== Table Registry 验证 ===")
    print(f"DATA_DIR: {settings.DATA_DIR}")
    print(f"TABLE_DIR: {TABLE_DIR}")
    print()

    # 1. 本地 JSON 文件统计
    project_table_dir = TABLE_DIR / PROJECT_ID
    if not project_table_dir.exists():
        print(f"❌ 项目表格目录不存在: {project_table_dir}")
        return

    json_files = list(project_table_dir.glob("*.json"))
    print(f"📁 本地 JSON 文件数: {len(json_files)}")

    total_tables = 0
    file_table_map = {}
    for jf in json_files:
        try:
            data = json.loads(jf.read_text(encoding="utf-8"))
            file_id = data.get("file_id", jf.stem)
            filename = data.get("filename", "?")
            tables = data.get("tables", [])
            total_tables += len(tables)
            file_table_map[file_id] = {
                "filename": filename,
                "table_count": len(tables),
                "table_titles": [t.get("title", "?") for t in tables],
            }
        except Exception as e:
            print(f"  ⚠️ 解析失败 {jf.name}: {e}")

    print(f"📊 本地注册表格总数: {total_tables}")
    print()

    # 2. 数据库中的 Excel 文件列表
    db = get_db()
    cursor = db.execute(
        "SELECT file_id, filename, status FROM files WHERE project_id = ? AND "
        "(LOWER(filename) LIKE '%.xlsx' OR LOWER(filename) LIKE '%.xls')",
        (PROJECT_ID,),
    )
    excel_files = cursor.fetchall()
    print(f"📂 数据库中 Excel 文件数: {len(excel_files)}")
    print()

    # 3. 逐文件对比
    print("=== Excel 文件 → 表格注册对照 ===")
    registered_count = 0
    missing_count = 0
    for row in excel_files:
        fid = row[0]
        fname = row[1]
        status = row[2]
        info = file_table_map.get(fid)
        if info:
            registered_count += 1
            print(f"  ✅ {fname} | status={status} | {info['table_count']} 张表格")
            for title in info["table_titles"][:3]:
                print(f"      → {title}")
            if info["table_count"] > 3:
                print(f"      → ... (共 {info['table_count']} 张)")
        else:
            missing_count += 1
            print(f"  ❌ {fname} | status={status} | 未注册表格")

    print()
    print(f"📈 覆盖率: {registered_count}/{len(excel_files)} ({registered_count*100//max(len(excel_files),1)}%)")
    print(f"   已注册: {registered_count}, 未注册: {missing_count}")
    print()

    # 4. Qdrant table_index 向量检查
    try:
        from qdrant_client import QdrantClient, models
        client = QdrantClient(url=settings.QDRANT_URL, timeout=5)
        from core.vector_store import _collection_name
        count_result = client.count(
            collection_name=_collection_name,
            count_filter=models.Filter(
                must=[
                    models.FieldCondition(
                        key="chunk_type",
                        match=models.MatchValue(value="table_index"),
                    ),
                    models.FieldCondition(
                        key="project_id",
                        match=models.MatchValue(value=PROJECT_ID),
                    ),
                ]
            ),
        )
        print(f"🔍 Qdrant table_index 向量数: {count_result.count}")
    except Exception as e:
        print(f"⚠️ Qdrant 查询失败: {e}")

    # 5. 抽样查看一个表格 JSON 内容
    if json_files:
        sample = json_files[0]
        data = json.loads(sample.read_text(encoding="utf-8"))
        tables = data.get("tables", [])
        if tables:
            t = tables[0]
            print(f"\n=== 抽样表格 ===")
            print(f"文件: {data.get('filename')}")
            print(f"表格标题: {t.get('title')}")
            print(f"工作表: {t.get('sheet_name')}")
            print(f"行数: {t.get('row_count')}")
            print(f"字符数: {t.get('char_count')}")
            print(f"Markdown 前 500 字符:")
            print(t.get("markdown", "")[:500])

if __name__ == "__main__":
    main()
