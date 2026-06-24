# -*- coding: utf-8 -*-
"""
Service Agent — 合同审查与企业常法服务。
WHY: 封装合同审查、合规检查等企业法律服务能力为 Tool Calling 模式。
"""
from __future__ import annotations

from core.agents.agent_base import AgentBase
from core.agents.tool_registry import Tool, ToolParameter


class ServiceAgent(AgentBase):
    """法律顾问服务 Agent。"""

    name = "service_agent"
    temperature = 0.2
    num_ctx = 16384
    num_predict = 8192

    system_prompt = (
        "你是一名企业法律顾问，专注合同审查和企业合规服务。\n"
        "你拥有合同条款审查和合规风险检查等专业工具。\n\n"
        "工作规则：\n"
        "1. 合同审查需逐条分析风险等级（高/中/低）\n"
        "2. 必须指出具体风险条款的原文位置\n"
        "3. 给出修改建议时，需提供替代条款文本\n"
        "4. 合规检查需引用具体法规依据"
    )

    def register_tools(self) -> None:
        self.registry.register(Tool(
            name="review_contract_clause",
            description="审查合同中的指定条款，识别法律风险并提出修改建议",
            parameters=[
                ToolParameter("clause_text", "string", "待审查的合同条款文本"),
                ToolParameter("contract_type", "string", "合同类型", required=False),
            ],
            handler=self._review_clause,
        ))
        self.registry.register(Tool(
            name="compliance_check",
            description="对企业行为或文件进行合规性检查",
            parameters=[
                ToolParameter("subject", "string", "待检查的事项描述"),
            ],
            handler=self._compliance_check,
        ))

    async def _review_clause(self, args: dict, ctx: dict) -> str:
        """合同条款审查。"""
        clause = args.get("clause_text", "")
        contract_type = args.get("contract_type", "通用合同")
        return (
            f"已收到合同条款审查请求：\n"
            f"合同类型: {contract_type}\n"
            f"条款内容: {clause[:2000]}\n"
            f"请对该条款进行风险分析并提供修改建议。"
        )

    async def _compliance_check(self, args: dict, ctx: dict) -> str:
        """合规性检查。"""
        subject = args.get("subject", "")
        return (
            f"已收到合规检查请求：\n"
            f"事项: {subject[:1000]}\n"
            f"请对照相关法规进行合规性分析。"
        )
