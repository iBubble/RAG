# -*- coding: utf-8 -*-
"""
RAG Agent — 知识检索与事实问答。
WHY: 封装现有 retrieval_pipeline 为 Tool Calling 模式，
     Agent 自主决定调用哪些检索工具（替代 intent_classifier 的静态策略）。
     可以先调用 vector_search，根据结果再决定是否追加 graph_search。
"""
from __future__ import annotations

from core.agents.agent_base import AgentBase
from core.agents.tool_registry import Tool, ToolParameter


class RAGAgent(AgentBase):
    """RAG 知识检索 Agent。"""

    name = "rag_agent"
    temperature = 0.3
    num_ctx = 16384
    num_predict = 8192

    system_prompt = (
        "你是一名专业的知识检索与事实问答专家。\n"
        "你拥有多种检索工具，可以从项目文档库中获取精确信息。\n\n"
        "工作规则：\n"
        "1. 你必须且首先通过调用 vector_search、table_search 或 graph_search 等检索工具来获取事实参考资料，严禁在不调用任何工具的情况下直接凭空生成回答。\n"
        "2. 先分析用户问题，判断需要哪种检索方式\n"
        "3. 调用对应的检索工具获取参考资料\n"
        "4. 基于检索结果，给出精确、有据可查的回答\n"
        "5. 回答中必须标注信息来源文件名\n"
        "6. 如果检索结果不足以回答，如实告知\n"
        "7. 严禁编造未在检索结果中出现的数据"
    )

    def _expand_query(self, query: str, project_id: str) -> str:
        """如果检索 query 较短，且项目存在，自动将项目名称作为前缀拼接到 query 中，以补全 RAG 检索实体上下文。"""
        if not project_id:
            return query
        try:
            from core.project_access import _read_projects
            project_name = ""
            for p in _read_projects():
                if p["id"] == project_id:
                    project_name = p["name"]
                    break
            if project_name and len(query) < 15 and project_name not in query:
                return f"{project_name} {query}"
        except Exception:
            pass
        return query

    def register_tools(self) -> None:
        self.registry.register(Tool(
            name="vector_search",
            description="语义向量检索：从文档库中找到与查询语义最相关的文本片段",
            parameters=[
                ToolParameter("query", "string", "检索查询文本"),
                ToolParameter("top_k", "number", "返回结果数量", required=False),
            ],
            handler=self._vector_search,
        ))
        self.registry.register(Tool(
            name="graph_search",
            description="知识图谱检索：查找实体之间的关系和路径",
            parameters=[
                ToolParameter("query", "string", "图谱查询文本"),
            ],
            handler=self._graph_search,
        ))
        self.registry.register(Tool(
            name="table_search",
            description="表格精确匹配：从结构化表格中检索精确数据",
            parameters=[
                ToolParameter("query", "string", "表格查询文本"),
            ],
            handler=self._table_search,
        ))
        self.registry.register(Tool(
            name="community_search",
            description="社区摘要检索：获取项目全局概况和跨文档关联信息",
            parameters=[
                ToolParameter("query", "string", "概况查询文本"),
            ],
            handler=self._community_search,
        ))

    # ── 工具实现：封装现有检索管线 ──

    async def _vector_search(self, args: dict, ctx: dict) -> str:
        """向量检索工具。"""
        import asyncio
        from starlette.concurrency import run_in_threadpool
        from core.vector_store import query_by_file_ids

        query = args.get("query", "")
        top_k = int(args.get("top_k", 10))
        project_id = ctx.get("project_id", "")
        query = self._expand_query(query, project_id)
        file_ids = ctx.get("file_ids", [])

        # ── 动态分流案件文件和公共文档 ──
        _case_fids = []
        _pub_fids = []
        if file_ids:
            try:
                from core.vector_store import get_file_metadata_multi_level
                _db_file_map = get_file_metadata_multi_level(file_ids, project_id)
                for fid in file_ids:
                    _meta = _db_file_map.get(fid)
                    if _meta and _meta.get("project_id") == project_id:
                        _case_fids.append(fid)
                    else:
                        _pub_fids.append(fid)
            except Exception as _e:
                logger.warning(f"RAGAgent 识别本案与公共文档失败: {_e}")
                _case_fids = file_ids
                _pub_fids = []

        # 双路并发检索
        tasks = []
        if _case_fids:
            tasks.append(run_in_threadpool(
                query_by_file_ids, query, _case_fids, project_id, top_k
            ))
        else:
            tasks.append(asyncio.sleep(0, result=[]))

        if _pub_fids:
            tasks.append(run_in_threadpool(
                query_by_file_ids, query, _pub_fids, "", 6
            ))
        else:
            tasks.append(asyncio.sleep(0, result=[]))

        case_docs, pub_docs = await asyncio.gather(*tasks)

        docs = list(case_docs or []) + list(pub_docs or [])
        if not docs:
            return "未检索到相关文档片段。"

        parts = []
        for i, d in enumerate(docs[:top_k + 6]):
            fname = d['metadata'].get('filename', '未知')
            parts.append(
                f"【文档 #{i+1}】来源: {fname}\n{d['content'][:1500]}"
            )
        return "\n\n".join(parts)


    async def _graph_search(self, args: dict, ctx: dict) -> str:
        """图谱检索工具。"""
        from core.graph_rag import graph_engine

        query = args.get("query", "")
        project_id = ctx.get("project_id", "")
        query = self._expand_query(query, project_id)

        try:
            result = await graph_engine.hybrid_search(
                query, project_id=project_id, max_paths=8
            )
            ctx_text = result.get("graph_context", "")
            return ctx_text if ctx_text else "图谱中未找到相关实体关系。"
        except Exception as e:
            return f"图谱检索异常: {str(e)}"

    async def _table_search(self, args: dict, ctx: dict) -> str:
        """表格检索工具。"""
        from core.table_registry import query_tables

        query = args.get("query", "")
        project_id = ctx.get("project_id", "")
        query = self._expand_query(query, project_id)
        file_ids = ctx.get("file_ids", [])

        # ── 动态分流案件文件和公共文档 ──
        _case_fids = []
        _pub_fids = []
        if file_ids:
            try:
                from core.vector_store import get_file_metadata_multi_level
                _db_file_map = get_file_metadata_multi_level(file_ids, project_id)
                for fid in file_ids:
                    _meta = _db_file_map.get(fid)
                    if _meta and _meta.get("project_id") == project_id:
                        _case_fids.append(fid)
                    else:
                        _pub_fids.append(fid)
            except Exception as _e:
                logger.warning(f"RAGAgent 表格检索识别本案与公共文档失败: {_e}")
                _case_fids = file_ids
                _pub_fids = []

        try:
            matched = []
            if _case_fids:
                matched.extend(query_tables(query, project_id, _case_fids, max_tables=3))
            if _pub_fids:
                matched.extend(query_tables(query, "", _pub_fids, max_tables=3))

            if not matched:
                return "未匹配到相关表格。"
            parts = []
            for t in matched:
                md = t.get("markdown", "")[:3000]
                parts.append(f"【表格: {t['title']}】\n{md}")
            return "\n\n".join(parts)
        except Exception as e:
            return f"表格检索异常: {str(e)}"

    async def _community_search(self, args: dict, ctx: dict) -> str:
        """社区摘要检索工具。"""
        from core.graph_rag import graph_engine

        project_id = ctx.get("project_id", "")
        if not project_id:
            return "未指定项目 ID。"

        try:
            if not graph_engine._ensure_connection():
                return "图谱数据库连接失败。"
            with graph_engine._driver.session() as session:
                result = session.run(
                    "MATCH (c:Community {project_id: $pid}) "
                    "WHERE c.summary IS NOT NULL "
                    "RETURN c.summary AS summary LIMIT 3",
                    pid=project_id,
                )
                summaries = [r["summary"] for r in result if r["summary"]]
            if not summaries:
                return "暂无社区摘要数据。"
            return "\n\n".join(
                f"摘要 {i+1}: {s[:500]}" for i, s in enumerate(summaries)
            )
        except Exception as e:
            return f"社区摘要检索异常: {str(e)}"
