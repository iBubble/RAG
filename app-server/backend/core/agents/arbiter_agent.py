# -*- coding: utf-8 -*-
"""
大BOSS — 最终仲裁者 Agent (Arbiter / Final Decision Maker)。
WHY: 在 Worker Agent 回答 + 小杠质疑之后，
     大BOSS 综合所有信息做出最终裁决，产出交付给用户的最终回答。
     确保回答质量经过「执行 → 质疑 → 仲裁」三重保障。

角色特点：
- 权威性：拥有最终决策权
- 综合性：综合 Worker 回答和小杠质疑
- 公正性：客观判断质疑是否成立
"""
from __future__ import annotations

from typing import AsyncGenerator

from core.agents.agent_base import AgentBase
from core.agents.ollama_chat import ollama_chat_stream


class ArbiterAgent(AgentBase):
    """大BOSS — 最终仲裁者 Agent。"""

    name = "arbiter"
    temperature = 0.3
    num_ctx = 16384
    num_predict = 8192

    system_prompt = (
        "你是「【协同】仲裁官」，团队的最终决策者。\n"
        "你将收到：【协同】法律分析专家的初步回答 + 【协同】审查员的质疑意见。\n\n"
        "你的职责：\n"
        "1. 审阅专家回答和【协同】审查员的质疑\n"
        "2. 判断哪些质疑成立、哪些不成立\n"
        "3. 综合所有信息，生成最终的高质量回答\n\n"
        "决策规则：\n"
        "- 如果【协同】审查员指出的事实错误确实存在 → 必须修正\n"
        "- 如果【协同】审查员指出的遗漏确实重要 → 必须补充\n"
        "- 如果【协同】审查员的质疑过于苛刻或不合理 → 可以驳回\n"
        "- 如果【协同】审查员说「审查通过」→ 在原回答基础上润色即可\n\n"
        "输出要求：\n"
        "- 直接输出最终回答，不要提及内部审查过程\n"
        "- 使用 Markdown 格式，结构清晰\n"
        "- 重要数据用粗体标注\n"
        "- 如果涉及法律内容，必须标注法条来源"
    )

    def register_tools(self) -> None:
        """大BOSS 不需要工具，纯靠推理做最终仲裁。"""
        pass

    async def arbitrate(
        self,
        original_question: str,
        agent_answer: str,
        critique: str,
        agent_name: str = "专家",
    ) -> str:
        """
        综合 Worker 回答和小杠质疑，做出最终裁决。

        Args:
            original_question: 用户原始问题
            agent_answer: Worker Agent 的初步回答
            critique: 小杠的质疑意见
            agent_name: 执行回答的 Agent 名称

        Returns:
            最终决策回答
        """
        arbitration_prompt = (
            f"## 用户问题\n{original_question}\n\n"
            f"## {agent_name}的回答\n{agent_answer[:8000]}\n\n"
            f"## 小杠的质疑意见\n{critique[:3000]}\n\n"
            f"请综合以上信息，做出最终裁决并生成高质量回答。"
        )

        result = await self.run(arbitration_prompt)
        return result.content or agent_answer  # 如果仲裁失败，回退到原始回答

    async def arbitrate_stream(
        self,
        original_question: str,
        agent_answer: str,
        critique: str,
        agent_name: str = "专家",
    ) -> AsyncGenerator[str, None]:
        """
        流式仲裁 — 用于前端 SSE 实时推送最终回答。
        WHY: 大BOSS 的最终回答通常较长，流式输出体验更好。
        """
        arbitration_prompt = (
            f"## 用户问题\n{original_question}\n\n"
            f"## {agent_name}的回答\n{agent_answer[:8000]}\n\n"
            f"## 小杠的质疑意见\n{critique[:3000]}\n\n"
            f"请综合以上信息，做出最终裁决并生成高质量回答。"
        )

        messages = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": arbitration_prompt},
        ]

        from core.llm_engine import _gpu_semaphore
        async with _gpu_semaphore:
            async for token in ollama_chat_stream(
                messages=messages,
                model=self.model,
                temperature=self.temperature,
                num_ctx=min(self.num_ctx, 8192),
                num_predict=self.num_predict,
            ):
                yield token
