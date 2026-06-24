# -*- coding: utf-8 -*-
"""
Supervisor Agent — 任务编排与路由决策。
WHY: 系统的"大脑"，接收用户请求后通过 Tool Calling
     自主决定委派给哪个 Worker Agent。
     使用轻量级 qwen3:8b 实现快速路由（~1-3s）。
"""
from __future__ import annotations

from core.agents.agent_base import AgentBase
from core.agents.tool_registry import Tool, ToolParameter


class SupervisorAgent(AgentBase):
    """Supervisor 编排者 Agent。"""

    name = "supervisor"
    model = "qwen3:8b"  # 轻量模型，快速路由
    temperature = 0.1   # 路由决策需要高确定性
    num_ctx = 4096
    num_predict = 2048

    system_prompt = (
        "你是一名任务编排专家（Supervisor），负责分析用户请求并分配给最合适的专家。\n"
        "你不直接回答用户的问题，而是通过调用工具将任务委派给专业 Agent。\n\n"
        "可用的专家 Agent：\n"
        "- ask_rag_agent: 知识检索专家，擅长从文档库中检索事实信息\n"
        "- ask_legal_agent: 法律分析专家，擅长法规检索、案例分析、文书起草\n"
        "- ask_service_agent: 企业法律顾问，擅长合同审查、合规检查\n"
        "- ask_data_agent: 数据分析专家，擅长 SQL 统计、表格聚合计算\n"
        "- direct_answer: 简单问题直接回答（问候、闲聊、常识）\n\n"
        "路由与工作流规则：\n"
        "1. 问文档/资料内容 → ask_rag_agent\n"
        "2. 问法律法规/案例/诉讼/文书 → ask_legal_agent\n"
        "3. 问合同审查/企业合规 → ask_service_agent\n"
        "4. 问数据统计/多少/合计/占比 → ask_data_agent\n"
        "5. 简单问候/闲聊 → direct_answer\n"
        "6. 复杂跨领域问题 → 可以依次调用多个 Agent\n"
        "7. 关键终止规则：当专家 Agent（如 ask_rag_agent）工作结束并返回了针对用户问题的最终回答时，你必须调用 `direct_answer` 工具，并将专家的回答作为 `answer` 参数传入，以正常结束当前的协同编排。绝对不能重复、循环地调用已经给出回答的专家工具。\n\n"
        "你的回答应该只包含工具调用，不要自己回答专业问题。\n"
        "只返回 JSON 格式的工具调用。"
    )

    def register_tools(self) -> None:
        self.registry.register(Tool(
            name="ask_rag_agent",
            description="委派给知识检索专家：从项目文档中检索事实信息并回答",
            parameters=[
                ToolParameter("question", "string", "转发给 RAG 专家的问题"),
            ],
            handler=self._ask_rag,
        ))
        self.registry.register(Tool(
            name="ask_legal_agent",
            description="委派给法律分析专家：法规检索、案例分析、风险评估、文书起草",
            parameters=[
                ToolParameter("question", "string", "转发给法律专家的问题"),
            ],
            handler=self._ask_legal,
        ))
        self.registry.register(Tool(
            name="ask_service_agent",
            description="委派给企业法律顾问：合同审查、合规检查、常法服务",
            parameters=[
                ToolParameter("question", "string", "转发给法律顾问的问题"),
            ],
            handler=self._ask_service,
        ))
        self.registry.register(Tool(
            name="ask_data_agent",
            description="委派给数据分析专家：SQL 统计查询、表格聚合、数值计算",
            parameters=[
                ToolParameter("question", "string", "转发给数据分析专家的问题"),
            ],
            handler=self._ask_data,
        ))
        self.registry.register(Tool(
            name="direct_answer",
            description="简单问题直接回答，无需委派（如问候、闲聊、常识问题）",
            parameters=[
                ToolParameter("answer", "string", "直接回答的内容"),
            ],
            handler=self._direct_answer,
        ))

    def _enrich_question(self, question: str, ctx: dict) -> str:
        project_id = ctx.get("project_id", "")
        if not project_id:
            return question
        try:
            from core.project_access import _read_projects
            project_name = ""
            for p in _read_projects():
                if p["id"] == project_id:
                    project_name = p["name"]
                    break
            if project_name and project_name not in question:
                return f"{project_name}：{question}"
        except Exception:
            pass
        return question

    async def _ask_rag(self, args: dict, ctx: dict) -> str:
        from core.agents.rag_agent import RAGAgent
        agent = RAGAgent()
        question = self._enrich_question(args.get("question", ""), ctx)
        result = await agent.run(question, context=ctx)
        return result.content or result.error or "RAG Agent 未返回结果。"

    async def _ask_legal(self, args: dict, ctx: dict) -> str:
        from core.agents.legal_agent import LegalAgent
        agent = LegalAgent()
        question = self._enrich_question(args.get("question", ""), ctx)
        result = await agent.run(question, context=ctx)
        return result.content or result.error or "Legal Agent 未返回结果。"

    async def _ask_service(self, args: dict, ctx: dict) -> str:
        from core.agents.service_agent import ServiceAgent
        agent = ServiceAgent()
        question = self._enrich_question(args.get("question", ""), ctx)
        result = await agent.run(question, context=ctx)
        return result.content or result.error or "Service Agent 未返回结果。"

    async def _ask_data(self, args: dict, ctx: dict) -> str:
        from core.agents.data_agent import DataAgent
        agent = DataAgent()
        question = self._enrich_question(args.get("question", ""), ctx)
        result = await agent.run(question, context=ctx)
        return result.content or result.error or "Data Agent 未返回结果。"

    async def _direct_answer(self, args: dict, ctx: dict) -> str:
        return args.get("answer", "你好！有什么可以帮你的吗？")
