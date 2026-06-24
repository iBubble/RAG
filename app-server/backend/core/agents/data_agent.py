# -*- coding: utf-8 -*-
"""
Data Agent — DuckDB 精确数据分析。
WHY: 封装现有 data_analyzer 为 Tool Calling 模式，
     Agent 可自主决定查询哪些表格、构建什么 SQL。
"""
from __future__ import annotations

from core.agents.agent_base import AgentBase
from core.agents.tool_registry import Tool, ToolParameter
from core.config import settings


class DataAgent(AgentBase):
    """数据分析 Agent。"""

    name = "data_agent"
    temperature = 0.1  # 数据分析需要 high 确定性
    num_ctx = 16384
    num_predict = 4096

    system_prompt = (
        "你是一名精确数据分析专家，擅长 SQL 查询和统计分析。\n"
        "你拥有 DuckDB SQL 引擎工具，可对项目的完整 Excel 数据表执行精确查询。\n\n"
        "工作规则：\n"
        "1. 先用 list_tables 了解可用数据表\n"
        "2. 再用 run_analysis 执行精确 SQL 分析\n"
        "3. 回答必须引用精确数值，严禁近似估算\n"
        "4. 如果数据不足，如实告知而非捏造"
    )

    def register_tools(self) -> None:
        self.registry.register(Tool(
            name="list_tables",
            description="列出项目中所有可用的数据表及其列名、行数",
            parameters=[],
            handler=self._list_tables,
        ))
        self.registry.register(Tool(
            name="run_analysis",
            description="使用 DuckDB SQL 引擎对项目数据表执行精确查询分析",
            parameters=[
                ToolParameter("question", "string", "用户的数据分析问题（自然语言）"),
            ],
            handler=self._run_analysis,
        ))

    async def _list_tables(self, args: dict, ctx: dict) -> str:
        """列出项目所有表格。"""
        from core.table_registry import get_all_tables

        project_id = ctx.get("project_id", "")
        file_ids = ctx.get("file_ids")

        try:
            tables = get_all_tables(project_id, file_ids)
            if not tables:
                return "项目中未发现可分析的数据表。"

            parts = []
            for t in tables[:10]:
                title = t.get("title", "未命名")
                rows = t.get("row_count", 0)
                source = t.get("source_file", "")
                # 提取列名
                md = t.get("markdown", "")
                headers = ""
                if md:
                    lines = [l for l in md.split("\n") if l.strip().startswith("|")]
                    if lines:
                        headers = lines[0]
                parts.append(f"表格「{title}」| {rows}行 | 来源: {source}\n列: {headers}")
            return "\n\n".join(parts)
        except Exception as e:
            return f"获取表格列表失败: {str(e)}"

    async def _run_analysis(self, args: dict, ctx: dict) -> str:
        """执行 DuckDB 数据分析。"""
        from core.data_analyzer import analyze_data

        question = args.get("question", "")
        project_id = ctx.get("project_id", "")
        model = ctx.get("model", settings.DEFAULT_LLM_MODEL)

        try:
            result = await analyze_data(question, project_id, None, model)
            if result.error:
                return f"数据分析错误: {result.error}"
            if not result.result_table:
                return "查询无结果。"

            tables_desc = "\n".join(
                f"  - {t['display']}({t['rows']}行)" for t in result.tables_used
            )
            return (
                f"SQL: {result.sql}\n"
                f"使用表格:\n{tables_desc}\n"
                f"查询结果 ({result.row_count}行):\n{result.result_text}"
            )
        except Exception as e:
            return f"DuckDB 分析异常: {str(e)}"
