# -*- coding: utf-8 -*-
"""
Legal Agent — 法律分析与文书起草。
WHY: 将现有 legal_assistant.py 的能力封装为 Tool Calling 模式，
     Agent 可自主决定调用法规检索、案例搜索、风险评估等工具。
"""
from __future__ import annotations

from core.agents.agent_base import AgentBase
from core.agents.tool_registry import Tool, ToolParameter


class LegalAgent(AgentBase):
    """法律助理 Agent。"""

    name = "legal_agent"
    temperature = 0.2  # 法律任务低温，减少幻觉
    num_ctx = 16384
    num_predict = 8192

    system_prompt = (
        "你是一名资深法律分析师，精通中国民商事法律实务。\n"
        "你拥有法规检索、案例搜索、风险评估和文书起草等专业工具。\n\n"
        "工作规则：\n"
        "1. 所有法律分析必须引用具体法条或司法解释\n"
        "2. 涉及案例时，必须标注案号和审理法院\n"
        "3. 风险评估采用四级分层：高/中/低/无\n"
        "4. 文书起草严格遵循法律文书格式规范\n"
        "5. 严禁编造不存在的法条或案例"
    )

    def register_tools(self) -> None:
        self.registry.register(Tool(
            name="search_statutes",
            description="检索与问题相关的法律法规条文（如民法典、合同法、劳动法等）",
            parameters=[
                ToolParameter("query", "string", "法规检索关键词"),
            ],
            handler=self._search_statutes,
        ))
        self.registry.register(Tool(
            name="search_cases",
            description="检索与案件相关的裁判案例和指导性案例",
            parameters=[
                ToolParameter("query", "string", "案例检索描述文本"),
            ],
            handler=self._search_cases,
        ))
        self.registry.register(Tool(
            name="assess_risk",
            description="对法律事项进行风险等级评估（高/中/低/无）",
            parameters=[
                ToolParameter("subject", "string", "待评估的法律事项描述"),
                ToolParameter("context", "string", "相关背景信息"),
            ],
            handler=self._assess_risk,
        ))

    async def _search_statutes(self, args: dict, ctx: dict) -> str:
        """法规检索：复用 RAG 向量检索，聚焦法律法规文档。"""
        from starlette.concurrency import run_in_threadpool
        from core.vector_store import query_by_file_ids

        query = f"法律法规 {args.get('query', '')}"
        project_id = ctx.get("project_id", "")
        file_ids = ctx.get("file_ids", [])

        docs = await run_in_threadpool(
            query_by_file_ids, query, file_ids, project_id, 8
        )
        if not docs:
            return "未检索到相关法律法规条文。"

        parts = []
        for i, d in enumerate(docs[:6]):
            fname = d['metadata'].get('filename', '未知')
            parts.append(f"【法规 #{i+1}】来源: {fname}\n{d['content'][:2000]}")
        return "\n\n".join(parts)

    async def _search_cases(self, args: dict, ctx: dict) -> str:
        """案例检索：调用北大法宝 API 或内置案例库。"""
        from core.legal_assistant import search_pkulaw_cases, MOCK_CASES
        import os

        query = args.get("query", "")
        token = os.environ.get("PKULAW_TOKEN")

        if token:
            cases = await search_pkulaw_cases(query, token)
            if cases:
                parts = []
                for c in cases[:3]:
                    parts.append(
                        f"案例: {c['title']}\n"
                        f"法院: {c['court_name']} | 案号: {c['case_number']}\n"
                        f"裁判观点: {c['content'][:500]}"
                    )
                return "\n\n".join(parts)

        # 降级到内置案例
        parts = []
        for c in MOCK_CASES[:2]:
            parts.append(
                f"案例: {c['title']}\n"
                f"法院: {c['court_name']} | 案号: {c['case_number']}\n"
                f"裁判观点: {c['content'][:500]}"
            )
        return "\n\n".join(parts) if parts else "未找到相关案例。"

    async def _assess_risk(self, args: dict, ctx: dict) -> str:
        """风险评估：基于 LLM 推理的法律风险分析（作为工具返回）。"""
        subject = args.get("subject", "")
        context = args.get("context", "")
        return (
            f"已收到风险评估请求：\n"
            f"事项：{subject}\n"
            f"背景：{context[:500]}\n"
            f"请基于以上信息进行四级风险分层分析。"
        )
