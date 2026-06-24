# -*- coding: utf-8 -*-
"""
小杠 — 反驳型 Agent (Contrarian / Devil's Advocate)。
WHY: 在 Worker Agent 给出初步回答后，小杠负责挑战和质疑，
     发现逻辑漏洞、数据矛盾、遗漏风险等问题。
     这是「辩论 + 仲裁」多 Agent 协同模式的核心差异化角色。

角色特点：
- 批判性思维，专找漏洞
- 不是为了否定，而是为了提高回答质量
- 使用轻量级模型快速生成质疑意见
"""
from __future__ import annotations

from typing import Optional
from core.agents.agent_base import AgentBase


class ContrarianAgent(AgentBase):
    """小杠 — 反驳型 Agent。"""

    name = "contrarian"
    model = "qwen3:8b"  # 轻量模型，快速生成质疑
    temperature = 0.5   # 稍高温度以产生更多元的质疑角度
    num_ctx = 8192
    num_predict = 2048

    system_prompt = (
        "你是「【协同】审查员」，一名专业的批判性审查专家。\n"
        "你的职责是审查其他专家 Agent 的回答，找出潜在问题。\n\n"
        "工作规则：\n"
        "1. 当发现专家回答中引用了具体的法条（如《民法典》某条）、关键数额或争议事实时，你必须且首先通过调用 verify_law_or_fact 工具检索文档库进行比对核对，严禁完全凭空否定或依赖自身参数化记忆进行抗辩。\n"
        "2. 审查维度包括：事实准确性、逻辑严密性、完整性、法律合规及数据可信度。\n"
        "3. 输出格式：如果发现问题，逐条列出质疑意见，标注严重程度（⚠️严重/⚡一般/💡建议）。如果回答质量很好无明显问题，请回复：「✅ 审查通过，回答质量良好。」\n"
        "4. 保持简洁，每条质疑不超过 2 句话。"
    )

    def register_tools(self) -> None:
        from core.agents.tool_registry import Tool, ToolParameter
        self.registry.register(Tool(
            name="verify_law_or_fact",
            description="法条与事实核对：从知识库中检索并验证回答中所引用的特定法条、事实、判例是否准确",
            parameters=[
                ToolParameter("query", "string", "要检索核对的法条名称、案情事实或法律条款陈述"),
                ToolParameter("top_k", "number", "返回结果数量", required=False),
            ],
            handler=self._vector_search,
        ))

    async def _vector_search(self, args: dict, ctx: dict) -> str:
        """向量检索核对工具。"""
        import asyncio
        from starlette.concurrency import run_in_threadpool
        from core.vector_store import query_by_file_ids

        query = args.get("query", "")
        top_k = int(args.get("top_k", 5))
        project_id = ctx.get("project_id", "")
        file_ids = ctx.get("file_ids", [])

        if not query:
            return "检索查询文本为空。"
        if not file_ids:
            return "当前项目无关联参考文档，无法核对。"

        try:
            docs = await run_in_threadpool(
                query_by_file_ids, query, file_ids, project_id, top_k
            )
            if not docs:
                return "未在文档库中检索到相关参考资料以供核对。"

            parts = []
            for i, d in enumerate(docs[:top_k]):
                fname = d['metadata'].get('filename', '未知')
                parts.append(
                    f"【核对参考 #{i+1}】来源: {fname}\n{d['content'][:1000]}"
                )
            return "\n\n".join(parts)
        except Exception as e:
            return f"核对检索失败: {str(e)}"

    async def critique(
        self,
        original_question: str,
        agent_answer: str,
        context: Optional[dict] = None,
    ) -> str:
        """
        对 Worker Agent 的回答进行批判性审查。

        Args:
            original_question: 用户原始问题
            agent_answer: Worker Agent 的初步回答
            context: 检索上下文信息

        Returns:
            质疑意见文本
        """
        critique_prompt = (
            f"以下是用户的问题和专家 Agent 的回答。\n"
            f"请进行批判性审查。\n\n"
            f"## 用户问题\n{original_question}\n\n"
            f"## 专家回答\n{agent_answer[:6000]}\n\n"
            f"请按照你的审查维度和规则逐一检查，给出质疑意见。"
        )

        result = await self.run(critique_prompt, context=context)
        return result.content or "✅ 审查通过，回答质量良好。"
