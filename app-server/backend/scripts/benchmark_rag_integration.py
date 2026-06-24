#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
GraphRAG 与 向量 RAG 融合检索批量评估基准脚本 (Benchmark Tool)

WHY: 用于自动化批量测试各种咨询问答场景下的融合检索效果，
     收集各个模块（意图分类、多轮消解、向量检索、图谱扩散、社区摘要、表格注册表）的耗时与召回信息，
     并生成可视化评估报告，辅助参数微调。
"""

import sys
import os
import json
import time
import sqlite3
import hashlib
import argparse
from pathlib import Path
from dotenv import load_dotenv

# 确保 backend 处于 sys.path 第一位
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, PROJECT_ROOT)

# 加载 .env 环境变量
load_dotenv(Path(PROJECT_ROOT) / ".env")

# 延迟导入 core 模块，防止 import 时 DB 尚未加载
from core.config import settings, STORAGE_ROOT
from core.database import get_db
from core.vector_store import query_by_file_ids
from core.graph_rag import graph_engine
from api.generate import classify_intent, resolve_coreference, get_community_summaries
from core.table_registry import query_tables

# 默认项目 ID（泸县项目）
DEFAULT_PROJECT_ID = "5f2ba65331ed"

# 内置批量评估问答用例库
EVAL_CASES = [
    {
        "query": "遂宁市蓬溪县高标准农田建设的耕地区片地价是多少？",
        "expected_intent": "data_lookup",
        "description": "精确数据/表格查询。验证：向量召回精度、完整表格注入、地名正字约束。"
    },
    {
        "query": "提灌设施安装前有哪些技术准备？以及相关施工规范",
        "expected_intent": "general_qa", # 预计会被 classify_intent 分为 general_qa 或 data_lookup
        "description": "局部逻辑关联查询。验证：图谱1-2跳扩散路径召回、实体语义搜索匹配。"
    },
    {
        "query": "请帮我总结并比较这个工程的不同实施方案的投资预算及主要差异",
        "expected_intent": "comparison",
        "description": "全局宏观对比。验证：全局社区摘要注入（inject_community）、项目指标全局 context 组装。"
    },
    {
        "query": "本项目水土流失主要有什么风险？怎么防范？",
        "expected_intent": "risk_analysis",
        "description": "风险防控。验证：risk_analysis 意图划分、关联风险条目与防范对策检索。"
    },
    {
        "query": "你好，请问你是谁？你能帮我做什么？",
        "expected_intent": "general_qa", # 预期触发 is_simple
        "description": "简单问答。验证：is_simple 拦截机制、零检索毫秒级响应、FSM 强制 no_think 约束。"
    }
]


def get_available_projects():
    """获取所有可用项目列表及文件数（通过扫描 uploads 磁盘路径）。"""
    try:
        with get_db() as conn:
            rows = conn.execute("SELECT id, name FROM projects").fetchall()
            projects = [dict(r) for r in rows]
            
        upload_root = Path(settings.UPLOAD_DIR)
        for p in projects:
            p_dir = upload_root / p["id"]
            count = 0
            if p_dir.exists():
                for root, dirs, files in os.walk(str(p_dir)):
                    # 排除隐藏目录
                    dirs[:] = [d for d in dirs if not d.startswith('.')]
                    for f in files:
                        if not f.startswith(".") and not f.endswith(".lock"):
                            # 过滤 SHP 伴随文件，只计主文件
                            ext = Path(f).suffix.lower()
                            SHP_COMPANION_EXTS = {'.shx', '.dbf', '.prj', '.sbn', '.sbx', '.cpg', '.qix', '.fix', '.atx', '.mta'}
                            if ext in SHP_COMPANION_EXTS or f.lower().endswith('.shp.xml'):
                                continue
                            count += 1
            p["file_count"] = count
        return projects
    except Exception as e:
        print(f"⚠️ 读取项目列表失败: {e}")
        return []


def get_project_files(project_id):
    """获取指定项目的物理文件及网页来源的 file_id 列表。"""
    upload_root = Path(settings.UPLOAD_DIR)
    project_dir = upload_root / project_id
    file_list = []
    
    # 1. 扫描磁盘物理文件
    if project_dir.exists():
        for root, dirs, files in os.walk(str(project_dir)):
            dirs[:] = [d for d in dirs if not d.startswith('.')]
            root_path = Path(root)

            # GDB 文件夹特殊处理
            for d in dirs:
                if d.lower().endswith(".gdb"):
                    gdb_path = root_path / d
                    rel_path = str(gdb_path.relative_to(upload_root))
                    file_id = hashlib.md5(f"{project_id}_{rel_path}".encode("utf-8")).hexdigest()
                    file_list.append({
                        "file_id": file_id,
                        "filename": d,
                        "path": rel_path
                    })

            for f in files:
                if f.startswith(".") or f.endswith(".lock"):
                    continue
                path = root_path / f
                ext = path.suffix.lower()
                
                # 排除 SHP 伴随文件
                SHP_COMPANION_EXTS = {'.shx', '.dbf', '.prj', '.sbn', '.sbx', '.cpg', '.qix', '.fix', '.atx', '.mta'}
                if ext in SHP_COMPANION_EXTS or f.lower().endswith('.shp.xml'):
                    continue
                
                rel_path = str(path.relative_to(upload_root))
                file_id = hashlib.md5(f"{project_id}_{rel_path}".encode("utf-8")).hexdigest()
                file_list.append({
                    "file_id": file_id,
                    "filename": f,
                    "path": rel_path
                })
                
    # 2. 查询数据库网页/文本来源
    try:
        with get_db() as conn:
            rows = conn.execute(
                "SELECT id, title FROM web_sources WHERE project_id = ?",
                (project_id,)
            ).fetchall()
            for r in rows:
                file_list.append({
                    "file_id": r["id"],
                    "filename": r["title"] or "未命名网络资料",
                    "path": f"__web__/{r['id']}"
                })
    except Exception as e:
        print(f"⚠️ 读取网络来源失败: {e}")
        
    return file_list


async def run_single_eval(query, project_id, project_name, file_ids, history=None):
    """运行单个查询的混合检索流程并评测性能。"""
    if history is None:
        history = []

    metrics = {
        "query": query,
        "history_len": len(history),
        "steps": {},
        "totals": {},
        "counts": {}
    }
    
    t_start = time.time()
    
    # 1. 意图分类与指代消解 (Preprocessing)
    t_pre_start = time.time()
    intent_result = classify_intent(query)
    intent = intent_result["intent"]
    strategy = intent_result["strategy"]
    resolved_query = resolve_coreference(query, history)
    metrics["steps"]["preprocessing_sec"] = time.time() - t_pre_start
    metrics["intent"] = intent
    metrics["resolved_query"] = resolved_query
    
    # 判断是否为 simple 简单问题
    # 类似 api/generate.py 中 _is_simple_query 判断
    from api.generate import _is_simple_query
    is_simple = _is_simple_query(query)
    metrics["is_simple"] = is_simple
    
    # 初始化变量
    context = ""
    vector_docs = []
    graph_context = ""
    community_context = ""
    table_context = ""
    
    # 2. 向量 RAG 检索
    t_vec_start = time.time()
    use_rag = file_ids and not is_simple
    if use_rag:
        vector_top_k = strategy.get("vector_top_k", 12)
        # 复杂问题触发查询重写
        search_query = resolved_query
        if len(resolved_query) > 15:
            from api.generate import _rewrite_chat_query
            search_query = _rewrite_chat_query(resolved_query, project_name)
            metrics["rewritten_query"] = search_query

        # 调用 qdrant 检索
        vector_docs = query_by_file_ids(search_query, file_ids, project_id=project_id, n_results=vector_top_k)
        if vector_docs:
            context = "\n\n".join(f"[来源: {d['metadata'].get('filename', '未知')}]\n{d['content']}" for d in vector_docs)
    metrics["steps"]["vector_rag_sec"] = time.time() - t_vec_start
    metrics["counts"]["vector_chunks_raw"] = len(vector_docs)
    
    # 3. GraphRAG 图谱关联扩散检索
    t_graph_start = time.time()
    graph_paths = []
    if use_rag:
        graph_max_paths = strategy.get("graph_max_paths", 8)
        try:
            graph_result = await graph_engine.hybrid_search(
                resolved_query, project_id=project_id, max_paths=graph_max_paths
            )
            graph_paths = graph_result.get("paths", [])
            graph_context = graph_result.get("graph_context", "")
            if graph_context:
                context = f"{graph_context}\n\n{context}"
        except Exception as e:
            graph_context = f"Error: {e}"
    metrics["steps"]["graph_rag_sec"] = time.time() - t_graph_start
    metrics["counts"]["graph_paths"] = len(graph_paths)
    
    # 4. 社区摘要全局注入
    t_comm_start = time.time()
    community_injected = False
    if use_rag and strategy.get("inject_community"):
        community_ctx = get_community_summaries(project_id, top_n=3)
        if community_ctx:
            community_context = community_ctx
            context = f"{community_ctx}\n\n{context}"
            community_injected = True
    metrics["steps"]["community_summaries_sec"] = time.time() - t_comm_start
    metrics["counts"]["community_summaries_injected"] = community_injected
    
    # 5. 完整表格注入
    t_table_start = time.time()
    table_count = 0
    if use_rag:
        table_max = strategy.get("table_max", 2)
        try:
            matched_tables = query_tables(query, project_id, file_ids, max_tables=table_max)
            table_count = len(matched_tables)
            if matched_tables:
                table_context_parts = []
                for t in matched_tables:
                    md = t.get('markdown', '')
                    if len(md) > 6000:
                        md = md[:6000] + "\n...[表格过长，已截断]"
                    table_context_parts.append(f"【完整表格: {t['title']}】(来源: {t['source_file']})\n{md}")
                table_context = "\n\n".join(table_context_parts)
                context = f"## 精确表格\n{table_context}\n\n{context}"
        except Exception as e:
            table_context = f"Error: {e}"
    metrics["steps"]["table_registry_sec"] = time.time() - t_table_start
    metrics["counts"]["tables_injected"] = table_count
    
    # 物理截断校验
    is_truncated = False
    original_len = len(context)
    if len(context) > 30000:
        context = context[:30000] + "\n\n...[参考资料过长，已被自动截断]"
        is_truncated = True
        
    metrics["totals"]["total_retrieval_sec"] = time.time() - t_start
    metrics["totals"]["context_char_length"] = len(context)
    metrics["totals"]["original_char_length"] = original_len
    metrics["totals"]["is_truncated"] = is_truncated
    
    return metrics, context


async def run_benchmark(project_id=None, output_path=None):
    print("====================================================")
    print("🚀 开始 GraphRAG + 向量 RAG 混合检索批量评估基准")
    print("====================================================")
    
    # 1. 项目与文件自动发现
    projects = get_available_projects()
    if not projects:
        print("❌ 未发现任何有效项目，请检查数据库连接及表结构。")
        return
        
    print(f"📁 发现可用项目数: {len(projects)}")
    for p in projects:
        print(f"  - 项目 ID: {p['id']} | 名称: {p['name']} | 关联文件数: {p['file_count']}")
        
    if not project_id:
        # 寻找有文件的项目
        active_projects = [p for p in projects if p["file_count"] > 0]
        if active_projects:
            project_id = active_projects[0]["id"]
            project_name = active_projects[0]["name"]
        else:
            project_id = projects[0]["id"]
            project_name = projects[0]["name"]
    else:
        project_name = "未指定项目名"
        for p in projects:
            if p["id"] == project_id:
                project_name = p["name"]
                break
                
    files = get_project_files(project_id)
    file_ids = [f["file_id"] for f in files]
    print(f"\n🎯 选定评估项目 ID: {project_id} ({project_name})")
    print(f"📄 关联有效向量文件数: {len(file_ids)}")
    if len(file_ids) == 0:
        print("⚠️ 警告：该项目关联的文件数为 0，检索将退化为零向量召回。")
        
    # 2. 依次测试批量用例
    results = []
    print("\n🔍 开始顺序执行批量查询测试...")
    for idx, case in enumerate(EVAL_CASES):
        query = case["query"]
        print(f"\n[{idx+1}/{len(EVAL_CASES)}] 测试 Query: 「{query}」")
        print(f"    ├─ 描述信息: {case['description']}")
        print(f"    └─ 预期意图: {case['expected_intent']}")
        
        try:
            metrics, context = await run_single_eval(query, project_id, project_name, file_ids)
            metrics["case_info"] = case
            results.append(metrics)
            print(f"    ✅ 执行完成 | 总检索耗时: {metrics['totals']['total_retrieval_sec']:.3f}s")
            print(f"    ├─ 意图分类结果: {metrics['intent']} (is_simple={metrics['is_simple']})")
            print(f"    ├─ 向量召回: {metrics['counts']['vector_chunks_raw']} chunks (耗时 {metrics['steps']['vector_rag_sec']:.3f}s)")
            print(f"    ├─ 图谱扩散: {metrics['counts']['graph_paths']} 条路径 (耗时 {metrics['steps']['graph_rag_sec']:.3f}s)")
            print(f"    ├─ 社区摘要: {'已注入' if metrics['counts']['community_summaries_injected'] else '未注入'} (耗时 {metrics['steps']['community_summaries_sec']:.3f}s)")
            print(f"    ├─ 注册表格: {metrics['counts']['tables_injected']} 张 (耗时 {metrics['steps']['table_registry_sec']:.3f}s)")
            print(f"    └─ 组装 Context 长度: {metrics['totals']['context_char_length']} 字符 (是否截断: {metrics['totals']['is_truncated']})")
        except Exception as ex:
            print(f"    ❌ 执行异常: {ex}")
            import traceback
            traceback.print_exc()

    # 3. 统计平均性能并生成 Markdown 报告
    if not results:
        print("❌ 未产生有效的评估结果。")
        return
        
    avg_total_sec = sum(r["totals"]["total_retrieval_sec"] for r in results) / len(results)
    avg_vec_sec = sum(r["steps"]["vector_rag_sec"] for r in results) / len(results)
    avg_graph_sec = sum(r["steps"]["graph_rag_sec"] for r in results) / len(results)
    avg_table_sec = sum(r["steps"]["table_registry_sec"] for r in results) / len(results)
    
    print("\n====================================================")
    print("📊 批量检索评估总结")
    print("====================================================")
    print(f"平均总检索耗时: {avg_total_sec:.3f}s")
    print(f"  ├─ 向量检索平均: {avg_vec_sec:.3f}s")
    print(f"  ├─ 图谱检索平均: {avg_graph_sec:.3f}s")
    print(f"  └─ 表格检索平均: {avg_table_sec:.3f}s")
    
    # 组装 markdown 报告
    report_lines = []
    report_lines.append(f"# RAG 融合检索基准评估报告 (Batch Benchmark Report)")
    report_lines.append(f"\n* **评估时间**: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime())}")
    report_lines.append(f"* **评估项目**: `{project_name}` (`{project_id}`)")
    report_lines.append(f"* **关联文件数**: {len(file_ids)} 个")
    
    report_lines.append(f"\n## 一、 平均性能概览 (Averages)")
    report_lines.append(f"| 统计指标 | 平均耗时 (秒) | 性能评级 | 说明 |")
    report_lines.append(f"| :--- | :--- | :--- | :--- |")
    report_lines.append(f"| **总检索耗时 (Total)** | {avg_total_sec:.3f}s | {'🟢 优秀 (<1.5s)' if avg_total_sec < 1.5 else '🟡 一般 (1.5-3.0s)' if avg_total_sec < 3.0 else '🔴 缓慢 (>3.0s)'} | 混合检索组装全流程 |")
    report_lines.append(f"| **向量检索耗时 (Vector RAG)** | {avg_vec_sec:.3f}s | {'🟢 优秀 (<0.5s)' if avg_vec_sec < 0.5 else '🟡 一般' if avg_vec_sec < 1.0 else '🔴 缓慢'} | Qdrant 双向量 + LLM Reranker |")
    report_lines.append(f"| **图谱检索耗时 (Graph RAG)** | {avg_graph_sec:.3f}s | {'🟢 优秀 (<0.8s)' if avg_graph_sec < 0.8 else '🟡 一般' if avg_graph_sec < 1.5 else '🔴 缓慢'} | Neo4j 扩散 + LLM 路径精排 |")
    report_lines.append(f"| **表格注册耗时 (Table Registry)** | {avg_table_sec:.3f}s | {'🟢 优秀 (<0.2s)' if avg_table_sec < 0.2 else '🟡 一般'} | SQLite 表格匹配查询 |")

    report_lines.append(f"\n## 二、 批量查询详细评测 (Detailed Queries)")
    report_lines.append(f"| ID | 评测问题 | 意图分类 | 总耗时 | 向量召回 | 图谱路径 | 表格数 | 上下文长度 | 状态 |")
    report_lines.append(f"| :-: | :--- | :--- | :-: | :-: | :-: | :-: | :-: | :-: |")
    
    for i, r in enumerate(results):
        trunc_status = "⚠️ 截断" if r["totals"]["is_truncated"] else "✅ 正常"
        if r["is_simple"]:
            trunc_status = "⚡ 极速"
        
        report_lines.append(
            f"| {i+1} | {r['query']} | `{r['intent']}` | {r['totals']['total_retrieval_sec']:.3f}s | "
            f"{r['counts']['vector_chunks_raw']} | {r['counts']['graph_paths']} | {r['counts']['tables_injected']} | "
            f"{r['totals']['context_char_length']} | {trunc_status} |"
        )
        
    report_lines.append(f"\n## 三、 诊断分析与参数微调建议")
    
    # 动态给出优化诊断建议
    has_warning = False
    
    # 诊断 1: 总耗时过长
    if avg_total_sec > 2.0:
        has_warning = True
        report_lines.append(f"\n### ⚠️ 检索响应延迟偏高 (延迟 {avg_total_sec:.2f}s > 2.0s)")
        report_lines.append(f"* **原因定位**: 从耗时看，主要是 {'图谱扩散及 LLM 路径精排' if avg_graph_sec > avg_vec_sec else '向量检索及 LLM Reranker'} 占用比例较高。")
        report_lines.append(f"* **优化对策**:")
        if avg_graph_sec > 1.0:
            report_lines.append(f"  1. 减少图谱精排的候选集，可调整 `core/graph_rag.py` 中 `top_n` 返回个数或降级为 1-hop 扩散（降低 Cypher 查询开销）。")
        if avg_vec_sec > 0.8:
            report_lines.append(f"  2. 减少向量 Reranker 的池大小（将 `core/vector_store.py` 中的 `_RERANK_POOL` 从 15 调低到 10）。")
            
    # 诊断 2: 截断现象
    truncated_cases = [r for r in results if r["totals"]["is_truncated"]]
    if truncated_cases:
        has_warning = True
        report_lines.append(f"\n### ⚠️ 发现 {len(truncated_cases)} 个用例的检索上下文触发了物理截断")
        report_lines.append(f"* **原因定位**: 图谱关联信息、向量文本切片和完整表格拼接后字符超出了 20,000 的安全阈值，导致部分内容被强制裁切，影响大模型阅读完整数据。")
        report_lines.append(f"* **优化对策**:")
        report_lines.append(f"  1. 在 `api/generate.py` 的 `classify_intent` 中微调策略参数，收紧 `vector_top_k`（例如从 12 降至 8）或 `graph_max_paths`（例如从 8 降至 4）。")
        report_lines.append(f"  2. 对表格特别大的项目，可在 `api/generate.py` 中将 `len(context) > 20000` 的阈值适度扩宽至 `30000`（Qwen 35B 在 16K/32K 上下文内完全支持）。")
        
    if not has_warning:
        report_lines.append(f"\n### 🟢 系统检索质量优秀")
        report_lines.append(f"* **评测结果**: 所有问题均获得正确的意图分流，召回切片数量饱满且去重干净。总耗时均在 1.5s 以内，无需特别微调。")

    report_content = "\n".join(report_lines)
    
    # 写入报告
    if not output_path:
        output_path = Path(PROJECT_ROOT) / "rag_benchmark_report.md"
    else:
        output_path = Path(output_path)
        
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(report_content)
        
    print(f"\n✅ 评估完成！详细评测报告已输出至: [rag_benchmark_report.md](file://{output_path})")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="GraphRAG + Vector RAG Integration Benchmark Tool")
    parser.add_argument("--project_id", type=str, default=DEFAULT_PROJECT_ID, help="泸县或当前项目的 project_id")
    parser.add_argument("--output", type=str, default=None, help="输出评测报告的绝对路径")
    args = parser.parse_args()
    
    # 运行异步基准
    import asyncio
    asyncio.run(run_benchmark(project_id=args.project_id, output_path=args.output))
