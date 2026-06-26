"""
多路径并行检索管线。

WHY: 原 generate.py chat() 中向量/图谱/表格/社区摘要串行执行，
     总延迟 = T1+T2+T3+T4。改为 asyncio.gather 并行后，
     总延迟 = max(T1,T2,T3,T4)。

设计：
- 各检索路径独立封装，任一路径失败不影响其他路径
- 融合策略：图谱精确 > 表格统计 > 向量上下文 > 社区摘要
- 借鉴 DeepParseX unified_search_service.py 架构
"""
from __future__ import annotations

import asyncio
import logging
import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Optional

from starlette.concurrency import run_in_threadpool

logger = logging.getLogger(__name__)

# ── 检索结果容器 ─────────────────────────────────────────


@dataclass
class RetrievalResult:
    """多路径检索结果。"""
    context: str = ""
    source_files: list = field(default_factory=list)
    graph_qa_context: str = ""
    graph_paths_context: str = ""
    table_stats_context: str = ""
    community_context: str = ""
    vector_context: str = ""
    entity_detail: str = ""
    data_analysis_context: str = ""
    # WHY: DuckDB 分析的结构化元数据，通过 SSE 直接推送到前端独立渲染
    data_analysis_meta: dict = field(default_factory=dict)


# ── 路径 1: 向量检索 ─────────────────────────────────────


async def _retrieve_vectors(
    search_query: str,
    file_ids: list[str],
    project_id: str,
    top_k: int = 12,
) -> tuple[str, list[str]]:
    """
    双路混合检索：Qdrant 向量检索 + SQLite FTS5 全文检索。
    使用 RRF (Reciprocal Rank Fusion) 倒数排名融合算法。
    """
    from core.vector_store import query_by_file_ids
    from core.database import search_fts

    candidate_limit = max(24, top_k * 2)

    # 1. 向量检索路
    try:
        vector_docs = await run_in_threadpool(
            query_by_file_ids, search_query, file_ids,
            project_id, candidate_limit,
        )
    except Exception as e:
        logger.warning(f"[pipeline] 向量检索失败: {e}")
        vector_docs = []

    # 2. 全文检索路
    try:
        fts_rows = await run_in_threadpool(
            search_fts, search_query, project_id, file_ids, candidate_limit
        )
        fts_docs = []
        for r in fts_rows:
            fts_docs.append({
                "content": r["document"],
                "metadata": {
                    "file_id": r["file_id"],
                    "project_id": r["project_id"],
                    "filename": r["filename"],
                    "chunk_index": r["chunk_index"],
                }
            })
    except Exception as e:
        logger.warning(f"[pipeline] SQLite 全文检索失败: {e}")
        fts_docs = []

    # 3. RRF 倒数排名融合
    k_constant = 60
    scores = {}
    docs_map = {}

    for rank, doc in enumerate(vector_docs):
        meta = doc.get("metadata", {})
        fid = meta.get("file_id")
        cidx = meta.get("chunk_index")
        if fid is None or cidx is None:
            continue
        key = (fid, cidx)
        scores[key] = scores.get(key, 0.0) + (1.0 / (k_constant + rank + 1))
        if key not in docs_map:
            docs_map[key] = doc

    for rank, doc in enumerate(fts_docs):
        meta = doc.get("metadata", {})
        fid = meta.get("file_id")
        cidx = meta.get("chunk_index")
        if fid is None or cidx is None:
            continue
        key = (fid, cidx)
        scores[key] = scores.get(key, 0.0) + (1.0 / (k_constant + rank + 1))
        if key not in docs_map:
            docs_map[key] = doc

    if not scores:
        return "", []

    sorted_keys = sorted(scores.keys(), key=lambda x: scores[x], reverse=True)
    merged_docs = [docs_map[key] for key in sorted_keys[:top_k]]

    source_files = []
    seen = set()
    for d in merged_docs:
        fname = d['metadata'].get('filename', '未知')
        if fname not in seen:
            source_files.append(fname)
            seen.add(fname)

    context_parts = []
    for idx, d in enumerate(merged_docs):
        fname = d['metadata'].get('filename', '未知')
        context_parts.append(
            f"---【参考文档区块 #{idx+1}】---\n"
            f"【物理来源文件名】: {fname}\n"
            f"【内容详情】:\n```\n{d['content']}\n```"
        )

    return "\n\n".join(context_parts), source_files


# ── 路径 2: 图谱路径检索 ─────────────────────────────────


async def _retrieve_graph_paths(
    query: str,
    project_id: str,
    max_paths: int = 8,
) -> str:
    """
    graph_rag.hybrid_search 路径检索。
    Returns: graph_context text
    """
    from core.graph_rag import graph_engine

    try:
        result = await graph_engine.hybrid_search(
            query, project_id=project_id, max_paths=max_paths,
        )
        return result.get("graph_context", "")
    except Exception as e:
        logger.warning(f"[pipeline] 图谱路径检索降级: {e}")
        return ""


# ── 路径 3: 图谱直接问答 ─────────────────────────────────


async def _retrieve_graph_qa(
    query: str,
    project_id: str,
) -> str:
    """
    graph_qa 结构化子图检索。
    Returns: structured graph context
    """
    from core.graph_qa import graph_qa

    try:
        result = await graph_qa(query, project_id)
        return result.context
    except Exception as e:
        logger.warning(f"[pipeline] 图谱直接问答降级: {e}")
        return ""


# ── 路径 4: 表格匹配检索 ─────────────────────────────────


async def _retrieve_tables(
    message: str,
    project_id: str,
    file_ids: list[str],
    max_tables: int = 2,
    inject_stats: bool = False,
) -> tuple[str, str]:
    """
    表格注册表检索 + 可选的统计分析。
    Returns: (table_context, stats_context)
    """
    from core.table_registry import query_tables

    try:
        matched = query_tables(
            message, project_id, file_ids, max_tables=max_tables,
        )
    except Exception as e:
        logger.warning(f"[pipeline] 表格检索失败: {e}")
        return "", ""

    if not matched:
        return "", ""

    # 构建表格 context
    table_parts = []
    for t in matched:
        md = t.get('markdown', '')
        md_limit = 2000 if inject_stats else 6000
        if len(md) > md_limit:
            md = md[:md_limit] + "\n...[表格过长，已截断]"
        table_parts.append(
            f"【完整表格: {t['title']}】(来源: {t['source_file']})\n{md}"
        )

    table_context = (
        "## 精确匹配的完整表格\n"
        "⚠️ 重要：以下表格包含精确数据，回答时必须直接引用表中的具体数值，"
        "严禁用近似范围（如\"约300-400\"）代替精确值（如\"320\"）。\n\n"
        + "\n\n".join(table_parts)
    )

    return table_context, ""


# ── 路径 5: 统计分析 ─────────────────────────────────────


async def _retrieve_stats(
    message: str,
    project_id: str,
    file_ids: list[str],
) -> tuple[str, str]:
    """
    全量表格统计分析 + 交叉过滤。
    Returns: (stats_context, entity_detail)
    """
    from core.table_registry import get_all_tables

    try:
        all_tables = await run_in_threadpool(
            get_all_tables, project_id,
            file_ids if file_ids else None,
        )
    except Exception as e:
        logger.warning(f"[pipeline] 全量表格获取失败: {e}")
        return "", ""

    if not all_tables:
        return "", ""

    stats_parts = []
    stats_tables = all_tables[:5]

    for t in stats_tables:
        md = t.get("markdown", "")
        title = t.get("title", "未知表")
        row_count = t.get("row_count", 0)
        source = t.get("source_file", "")

        if not md or row_count == 0:
            continue

        lines = [l for l in md.split("\n") if l.strip().startswith("|")]
        if len(lines) < 2:
            continue

        raw_header = lines[0].split("|")
        headers = [c.strip() for c in raw_header[1:-1]]

        data_lines = []
        summary_row = None
        for l in lines[1:]:
            raw = [c.strip() for c in l.split("|")[1:-1]]
            non_empty = [c for c in raw if c]
            if not non_empty:
                continue
            if all(
                c.replace("-", "").replace(":", "") == ""
                for c in non_empty
            ):
                continue
            if all(
                re.match(r'^[（\(]\d+[）\)]$', c) for c in non_empty
            ):
                continue
            first_val = non_empty[0] if non_empty else ""
            if first_val.startswith("说明") or first_val.startswith(
                "注："
            ) or first_val.startswith("注:"):
                continue
            if first_val in ("合计", "总计", "小计"):
                summary_row = raw
                continue
            data_lines.append(l)

        stat_block = (
            f"### 📊 表格「{title}」精确统计（来源: {source}）\n"
            f"- **总数据行数**: {len(data_lines)} 行\n"
            f"- **列数**: {len(headers)} 列\n"
        )

        col_stats = []
        for col_idx, header in enumerate(headers):
            col_values = []
            for dl in data_lines:
                raw_cells = dl.split("|")
                cells = [c.strip() for c in raw_cells[1:-1]]
                val = cells[col_idx] if col_idx < len(cells) else ""
                if val and val not in ("-", "—", "/"):
                    col_values.append(val)

            if not col_values:
                continue

            unique_vals = set(col_values)
            unique_count = len(unique_vals)

            numeric_vals = []
            for v in col_values:
                try:
                    numeric_vals.append(float(v))
                except (ValueError, TypeError):
                    pass

            if numeric_vals and len(numeric_vals) > len(col_values) * 0.5:
                summary_val = None
                if summary_row and col_idx < len(summary_row):
                    sv = summary_row[col_idx]
                    if sv and sv not in ("-", "—", "/", ""):
                        try:
                            summary_val = float(sv)
                        except (ValueError, TypeError):
                            pass

                if summary_val is not None:
                    col_stats.append(
                        f"  - **{header}**: "
                        f"⭐表格合计行={summary_val:.4f}, "
                        f"唯一值={unique_count}个, "
                        f"有效值={len(numeric_vals)}个, "
                        f"最小={min(numeric_vals):.4f}, "
                        f"最大={max(numeric_vals):.4f}"
                    )
                else:
                    col_stats.append(
                        f"  - **{header}**: "
                        f"唯一值={unique_count}个, "
                        f"有效值={len(numeric_vals)}个, "
                        f"合计={sum(numeric_vals):.4f}, "
                        f"平均={sum(numeric_vals)/len(numeric_vals):.4f}, "
                        f"最小={min(numeric_vals):.4f}, "
                        f"最大={max(numeric_vals):.4f}"
                    )
            else:
                counts = Counter(col_values)
                top_items = counts.most_common(10)
                items_str = ", ".join(
                    f"{val}({cnt}次)" for val, cnt in top_items
                )
                extra = ""
                if unique_count > 10:
                    extra = f" ...等共{unique_count}种"
                col_stats.append(
                    f"  - **{header}**: "
                    f"⭐唯一值={unique_count}个, "
                    f"有效值={len(col_values)}个 "
                    f"— 前10高频: {items_str}{extra}"
                )

        if col_stats:
            stat_block += (
                "- **各列精确统计**:\n"
                + "\n".join(col_stats) + "\n"
            )

        if summary_row:
            summary_items = []
            for si, (h, v) in enumerate(zip(headers, summary_row)):
                if v and v not in ("-", "—", "/", "", "合计", "总计", "小计"):
                    summary_items.append(f"  - **{h}** = {v}")
            if summary_items:
                stat_block += (
                    "- **📋 表格原始合计行**"
                    "（Excel 中的合计/总计行，权威数据）:\n"
                    + "\n".join(summary_items) + "\n"
                )

        stats_parts.append(stat_block)

    stats_context = "\n\n".join(stats_parts) if stats_parts else ""

    # ── 交叉过滤 ──
    entity_detail = _cross_filter(message, all_tables)

    return stats_context, entity_detail


def _cross_filter(message: str, all_tables: list) -> str:
    """
    交叉过滤：按用户提到的实体/关键词筛选并聚合。
    WHY: 全局统计无法回答"002#有多少土埂"这类交叉过滤问题。
    """
    entity_matches = list(re.finditer(
        r'(开发复垦|整治地块|地块)\s*(\d+)#?', message,
    ))
    keyword_filters = []
    kw_candidates = [
        "果园", "旱地", "水田", "林地", "草地",
        "土埂", "石埂", "土坎", "石坎",
    ]
    for kw in kw_candidates:
        if kw in message:
            keyword_filters.append(kw)

    if not entity_matches and not keyword_filters:
        return ""

    for t in all_tables:
        md_text = t.get("markdown", "")
        if not md_text:
            continue
        t_lines = [
            l for l in md_text.split("\n") if l.strip().startswith("|")
        ]
        if len(t_lines) < 3:
            continue
        t_headers = [c.strip() for c in t_lines[0].split("|")[1:-1]]

        parsed_rows = []
        for dl in t_lines[2:]:
            raw = [c.strip() for c in dl.split("|")[1:-1]]
            non_empty = [c for c in raw if c]
            if not non_empty:
                continue
            fv = non_empty[0]
            if fv in ("合计", "总计", "小计"):
                continue
            fv_clean = fv.strip()
            if fv_clean.startswith("说明") or fv_clean.startswith("注：") or fv_clean.startswith("注:"):
                continue
            if all(
                re.match(r'^[（\(]\d+[）\)]$', c) for c in non_empty
            ):
                continue
            if all(
                c.replace("-", "").replace(":", "") == ""
                for c in non_empty
            ):
                continue
            parsed_rows.append(raw)

        if not parsed_rows:
            continue

        filtered = parsed_rows
        filter_desc_parts = []

        if entity_matches:
            all_variants = set()
            display_names = []
            for m in entity_matches:
                num = m.group(2)
                eid = f"开发复垦{num}#"
                if eid not in display_names:
                    display_names.append(eid)
                all_variants.update([
                    eid,
                    f"开发复垦{num.lstrip('0')}#",
                    f"开发复垦{num.zfill(3)}#",
                ])
            block_ci = None
            for ci, h in enumerate(t_headers):
                if "整治地块编号" in h:
                    block_ci = ci
                    break
            if block_ci is not None:
                filtered = [
                    r for r in filtered
                    if block_ci < len(r)
                    and any(ev in r[block_ci] for ev in all_variants)
                ]
                filter_desc_parts.append(f"地块={','.join(display_names)}")

        if keyword_filters and filtered:
            kw_filtered = []
            for r in filtered:
                row_text = "|".join(r)
                if any(kw in row_text for kw in keyword_filters):
                    kw_filtered.append(r)
            if kw_filtered:
                filtered = kw_filtered
                filter_desc_parts.append(
                    f"关键词={'、'.join(keyword_filters)}"
                )

        if not filtered:
            continue

        filter_desc = " + ".join(filter_desc_parts)

        agg_lines = [
            f"## 🔍 交叉筛选精确结果（{filter_desc}）\n"
            f"筛选后共 **{len(filtered)}** 行数据。\n"
        ]

        for ci, h in enumerate(t_headers):
            # 收集该列的所有非空、非符号值，以及它们的 float 转换和地块分组
            col_vals = []
            row_num_pairs = []  # list of (block_id, float_val)
            for r in filtered:
                if ci < len(r):
                    v = r[ci]
                    if v and v not in ("-", "—", "/"):
                        col_vals.append(v)
                        try:
                            f_val = float(v)
                            b_id = r[block_ci] if (block_ci is not None and block_ci < len(r)) else None
                            row_num_pairs.append((b_id, f_val))
                        except (ValueError, TypeError):
                            pass

            if not col_vals:
                continue

            nums = [p[1] for p in row_num_pairs]

            if nums and len(nums) > len(col_vals) * 0.5:
                # ── 分组去重或全局去重 ──
                if block_ci is not None:
                    # 按地块 ID 分组
                    block_groups = {}
                    for b_id, val in row_num_pairs:
                        block_groups.setdefault(b_id, []).append(val)
                    
                    final_sum = 0.0
                    has_any_merged = False
                    for b_id, b_nums in block_groups.items():
                        is_b_merged = len(set(b_nums)) == 1
                        if is_b_merged:
                            final_sum += b_nums[0]
                            has_any_merged = True
                        else:
                            final_sum += sum(b_nums)
                else:
                    is_merged = len(set(nums)) == 1
                    final_sum = nums[0] if is_merged else sum(nums)
                    has_any_merged = is_merged

                agg_lines.append(
                    f"- **{h}**: "
                    f"合计={final_sum:.4f}"
                    f"{'（唯一值，已避免合并单元格重复累加）' if has_any_merged else ''}, "
                    f"个数={len(nums)}, "
                    f"最小={min(nums):.4f}, "
                    f"最大={max(nums):.4f}"
                )
            else:
                cnt = Counter(col_vals)
                items = ", ".join(
                    f"{val}({c}个)" for val, c in cnt.most_common(10)
                )
                agg_lines.append(f"- **{h}**: {items}")

        logger.info(
            f"🔍 [FILTER] {filter_desc}: {len(filtered)} 行"
        )
        return "\n".join(agg_lines)

    return ""


# ── 路径 5b: DuckDB 全量数据分析 ───────────────────


async def _retrieve_data_analysis(
    message: str,
    project_id: str,
    file_ids: list[str],
    model: str,
) -> tuple[str, dict]:
    """
    DuckDB 全量数据分析路径。

    WHY: RAG context 窗口无法容纳 1000+ 行的完整表格，
         而全表聚合统计需要遍历每一行。
         DuckDB SQL 引擎可以在内存中精确执行，
         LLM 只需看列名+5行样本就能生成正确 SQL。

    Returns:
        (context_str, meta_dict) 元组。
        context_str 注入 LLM 的 prompt 中；
        meta_dict 通过 SSE 直接推送到前端独立渲染。
    """
    from core.data_analyzer import analyze_data

    try:
        result = await analyze_data(
            message, project_id, file_ids, model,
        )
    except Exception as e:
        logger.warning(f"[pipeline] DuckDB 数据分析失败: {e}")
        return "", {}

    if result.error:
        logger.warning(
            f"[pipeline] DuckDB 分析错误: {result.error}"
        )
        return "", {}

    if not result.result_table:
        return "", {}

    # 构建数据表清单
    tables_desc = "\n".join(
        f"  - {t['display']}({t['name']}, {t['rows']}行)"
        for t in result.tables_used
    )

    # WHY: context 注入 LLM prompt，让 LLM 看到精确数值来组织回答
    context = (
        f"## 📊 数据精确分析结果（DuckDB SQL 引擎计算）\n"
        f"⚠️ **最高优先级指令**：以下是程序化精确计算结果。\n"
        f"回答时**必须直接引用下方精确数字**，"
        f'严禁说"无法统计""数据不足"。\n\n'
        f"查询结果（{result.row_count} 行）：\n"
        f"{result.result_text}"
    )

    # WHY: meta 通过 SSE 推送到前端，由 DataTable 组件独立渲染
    meta = {
        "sql": result.sql,
        "result_markdown": result.result_table,
        "row_count": result.row_count,
        "tables_used": result.tables_used,
    }

    return context, meta


# ── 路径 6: 社区摘要 ─────────────────────────────────────


async def _retrieve_community(
    project_id: str,
    top_n: int = 3,
) -> str:
    """从 Neo4j 查询社区摘要。"""
    from core.graph_rag import graph_engine

    if not project_id:
        return ""
    try:
        if not graph_engine._ensure_connection():
            return ""
        with graph_engine._driver.session() as session:
            result = session.run(
                "MATCH (c:Community {project_id: $pid}) "
                "WHERE c.summary IS NOT NULL "
                "RETURN c.summary AS summary "
                "LIMIT $limit",
                pid=project_id,
                limit=top_n,
            )
            summaries = [r["summary"] for r in result if r["summary"]]

        if not summaries:
            return ""
        parts = ["## 项目知识图谱社区摘要（宏观背景）"]
        for i, s in enumerate(summaries, 1):
            parts.append(f"{i}. {s[:500]}")
        return "\n".join(parts)
    except Exception as e:
        logger.warning(f"[pipeline] 社区摘要检索失败: {e}")
        return ""


# ── 主入口：并行检索管线 ─────────────────────────────────


async def run_retrieval(
    search_query: str,
    original_message: str,
    project_id: str,
    file_ids: list[str],
    strategy: dict,
    model: str = "qwen3.6:35b-q4",
) -> RetrievalResult:
    """
    并行执行多条检索路径，融合为统一 context。

    Args:
        search_query: 改写后的检索 query
        original_message: 用户原始消息（用于表格匹配和交叉过滤）
        project_id: 项目 ID
        file_ids: 文件 ID 列表
        strategy: 意图策略参数
        model: LLM 模型名

    Returns:
        RetrievalResult 包含融合后的 context 和各路径结果
    """
    result = RetrievalResult()

    vector_top_k = strategy.get("vector_top_k", 8)
    graph_max_paths = strategy.get("graph_max_paths", 8)
    table_max = strategy.get("table_max", 2)
    inject_stats = strategy.get("inject_table_stats", False)
    inject_community = strategy.get("inject_community", False)
    inject_data_analysis = strategy.get("inject_data_analysis", False)

    # ── 构建并行任务列表 ──
    tasks = {}

    # 向量检索（始终执行）
    tasks["vector"] = _retrieve_vectors(
        search_query, file_ids, project_id, vector_top_k,
    )

    # 图谱路径检索
    tasks["graph_paths"] = _retrieve_graph_paths(
        search_query, project_id, graph_max_paths,
    )

    # 图谱直接问答
    tasks["graph_qa"] = _retrieve_graph_qa(
        search_query, project_id,
    )

    # 表格匹配
    tasks["tables"] = _retrieve_tables(
        original_message, project_id, file_ids,
        table_max, inject_stats,
    )

    # 统计分析（仅 inject_table_stats 意图启用）
    if inject_stats:
        tasks["stats"] = _retrieve_stats(
            original_message, project_id, file_ids,
        )

    # DuckDB 全量数据分析（仅 inject_data_analysis 意图启用）
    # WHY: 不传 file_ids，分析项目下所有表格。
    #      file_ids 与 table_registry JSON 中的 file_id 使用不同 ID 系统，
    #      过滤会导致匹配不到数据。
    if inject_data_analysis:
        tasks["data_analysis"] = _retrieve_data_analysis(
            original_message, project_id, None, model,
        )

    # 社区摘要（仅特定意图启用）
    if inject_community:
        tasks["community"] = _retrieve_community(project_id)

    # ── 并行执行 ──
    task_names = list(tasks.keys())
    task_coros = list(tasks.values())

    results = await asyncio.gather(*task_coros, return_exceptions=True)

    # ── 解析各路径结果 ──
    for name, res in zip(task_names, results):
        if isinstance(res, Exception):
            logger.warning(f"[pipeline] {name} 路径异常: {res}")
            continue

        if name == "vector":
            result.vector_context, result.source_files = res
        elif name == "graph_paths":
            result.graph_paths_context = res
        elif name == "graph_qa":
            result.graph_qa_context = res
        elif name == "tables":
            table_ctx, _ = res
            result.table_stats_context = table_ctx
        elif name == "stats":
            stats_ctx, entity_detail = res
            if entity_detail:
                result.entity_detail = entity_detail
            if not result.entity_detail and stats_ctx:
                result.table_stats_context = (
                    result.table_stats_context + "\n\n" + stats_ctx
                    if result.table_stats_context else stats_ctx
                )
        elif name == "data_analysis":
            da_ctx, da_meta = res
            result.data_analysis_context = da_ctx
            result.data_analysis_meta = da_meta
        elif name == "community":
            result.community_context = res

    # ── 融合 context ──
    # WHY: 优先级 = DuckDB分析 > 交叉筛选精确 > 图谱QA > 表格统计 > 图谱路径 > 社区摘要 > 向量检索
    context_parts = []

    # DuckDB 全量数据分析结果（最高优先级）
    if result.data_analysis_context:
        context_parts.append(result.data_analysis_context)

    if result.entity_detail:
        # 有精确交叉筛选结果时，优先级最高
        context_parts.append(
            "## 📊 统计分析结果\n"
            "⚠️ **最高优先级指令**：以下是程序化精确计算结果。"
            "回答时**必须直接引用下方精确数字**。\n\n"
            + result.entity_detail
        )
    elif inject_stats and result.table_stats_context:
        context_parts.append(
            "## 📊 全量数据统计分析结果（程序化精确计算）\n"
            "⚠️ **最高优先级指令**：以下是程序化精确计算结果。\n"
            "回答时**必须直接引用下方精确数字**，"
            '严禁说"无法统计""数据不足"。\n'
            '- 问"总共/一共有多少"→ 用 **⭐唯一值** 数量\n'
            '- 问"合计/总计"→ 用 **⭐表格合计行** 的值\n\n'
            + result.table_stats_context
        )

    if result.graph_qa_context:
        context_parts.append(result.graph_qa_context)

    # WHY: 当 DuckDB 已返回精确分析结果时，跳过所有可能干扰的 context。
    #      实测发现：即使只保留向量检索（2154字），LLM 仍会被文档片段中
    #      的部分信息干扰（如只提到"灌木林地"），从而否认 DuckDB 的精确结果。
    #      DuckDB SQL 引擎已对完整数据做了精确计算，不需要其他辅助信息。
    has_precise_da = bool(result.data_analysis_context)

    if result.table_stats_context and not inject_stats and not has_precise_da:
        context_parts.append(result.table_stats_context)

    if result.graph_paths_context and not has_precise_da:
        context_parts.append(result.graph_paths_context)

    if result.community_context and not has_precise_da:
        context_parts.append(result.community_context)

    if result.vector_context and not has_precise_da:
        context_parts.append(result.vector_context)

    result.context = "\n\n".join(context_parts)

    # 智能截断
    if len(result.context) > 25000:
        parts = result.context.split('\n\n')
        truncated = []
        current_len = 0
        for p in parts:
            if current_len + len(p) + 2 > 25000:
                break
            truncated.append(p)
            current_len += len(p) + 2
        result.context = (
            "\n\n".join(truncated)
            + "\n\n...[参考资料过长，已被按区块智能截断]"
        )

    logger.info(
        f"📡 [Pipeline] 并行检索完成 | "
        f"vector={len(result.vector_context)}字 | "
        f"graph_qa={len(result.graph_qa_context)}字 | "
        f"graph_paths={len(result.graph_paths_context)}字 | "
        f"tables={len(result.table_stats_context)}字 | "
        f"data_analysis={len(result.data_analysis_context)}字 | "
        f"community={len(result.community_context)}字 | "
        f"entity_detail={len(result.entity_detail)}字 | "
        f"total={len(result.context)}字"
    )

    return result
