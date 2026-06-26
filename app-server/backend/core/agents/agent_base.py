# -*- coding: utf-8 -*-
"""
Agent 基类 (AgentBase)。
WHY: 实现多 Agent 协同框架的核心 — Tool Calling 执行循环。
     每个 Agent 继承此类，定义自己的 system_prompt 和 tools，
     即可自主推理并调用工具完成任务。

设计要点：
- 使用 Ollama /api/chat 原生 Tool Calling（非模拟）
- 内置最大循环次数保护（防止无限递归）
- 工具执行结果通过 role:"tool" 消息回注
- 支持 Blackboard 跨 Agent 共享记忆
"""
from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Optional

from core.agents.tool_registry import ToolRegistry, Tool
from core.agents.ollama_chat import ollama_chat
from core.config import settings

logger = logging.getLogger(__name__)

# 最大工具调用循环次数（安全保护）
MAX_TOOL_CALL_ROUNDS = 6


@dataclass
class AgentResult:
    """Agent 执行结果。"""
    content: str = ""
    tool_calls_log: list[dict] = field(default_factory=list)
    agent_name: str = ""
    elapsed_seconds: float = 0.0
    error: Optional[str] = None

    @property
    def success(self) -> bool:
        return self.error is None and bool(self.content)


class AgentBase:
    """
    多 Agent 协同框架的基类。

    子类需要覆写:
        - name: Agent 标识符
        - system_prompt: 系统角色 Prompt
        - model: 使用的 Ollama 模型
        - 调用 register_tools() 注册工具
    """

    name: str = "base_agent"
    system_prompt: str = "你是一个智能助手。"
    model: str = settings.COLLAB_LLM_MODEL
    temperature: float = 0.3
    num_ctx: int = 8192
    num_predict: int = 4096

    def __init__(self) -> None:
        self.registry = ToolRegistry()
        self.register_tools()
        self._load_custom_settings()

    def _load_custom_settings(self) -> None:
        try:
            from api.admin import _read_system_settings
            settings_dict = _read_system_settings()

            # 1. 尝试覆盖 model 和 temperature
            if self.name == "contrarian":
                if "collab_contrarian_model" in settings_dict:
                    self.model = settings_dict["collab_contrarian_model"]
                if "collab_contrarian_temp" in settings_dict:
                    try:
                        self.temperature = float(settings_dict["collab_contrarian_temp"])
                    except ValueError:
                        pass
            elif self.name == "arbiter":
                if "collab_arbiter_model" in settings_dict:
                    self.model = settings_dict["collab_arbiter_model"]
                if "collab_arbiter_temp" in settings_dict:
                    try:
                        self.temperature = float(settings_dict["collab_arbiter_temp"])
                    except ValueError:
                        pass

            # 2. 角色名称替换：如果 system_prompt 包含默认名称，替换为自定义名称
            default_names = {
                "supervisor": "【协同】文档秘书",
                "contrarian": "【协同】审查员",
                "arbiter": "【协同】仲裁官",
                "legal": "【协同】法律分析专家",
            }
            if hasattr(self, "system_prompt") and self.system_prompt:
                for k_role, default_zh_name in default_names.items():
                    custom_name_key = f"collab_{k_role}_name"
                    if custom_name_key in settings_dict:
                        custom_zh_name = settings_dict[custom_name_key]
                        if custom_zh_name and custom_zh_name != default_zh_name:
                            self.system_prompt = self.system_prompt.replace(default_zh_name, custom_zh_name)

        except Exception as e:
            logger.warning(f"加载 Agent {self.name} 自定义配置失败: {e}")

    def register_tools(self) -> None:
        """
        子类覆写此方法，注册该 Agent 可用的工具。
        WHY: 每个 Agent 拥有独立的工具集，
             通过 Tool Calling 实现自主决策。
        """
        pass

    async def run(
        self,
        user_message: str,
        context: Optional[dict] = None,
        blackboard: Optional[Any] = None,
    ) -> AgentResult:
        """
        核心执行循环：
        1. 构建 messages + tools → Ollama /api/chat
        2. 如果模型返回 tool_calls → 执行工具 → 追加结果到 messages
        3. 重复直到模型返回纯文本（不再调用工具）
        4. 返回最终结果
        """
        t0 = time.time()
        ctx = context or {}

        # 构建初始消息
        messages = [
            {"role": "system", "content": self.system_prompt},
            {"role": "user", "content": user_message},
        ]

        tools_schema = self.registry.to_ollama_tools()
        tool_calls_log: list[dict] = []

        for round_idx in range(MAX_TOOL_CALL_ROUNDS):
            # 调用 Ollama /api/chat
            try:
                from core.llm_engine import _gpu_semaphore
                async with _gpu_semaphore:
                    resp = await ollama_chat(
                        messages=messages,
                        model=self.model,
                        tools=tools_schema if tools_schema else None,
                        temperature=self.temperature,
                        num_ctx=min(self.num_ctx, 8192),
                        num_predict=self.num_predict,
                    )
            except Exception as e:
                logger.error(
                    f"[{self.name}] LLM 调用失败 (round {round_idx}): {e}"
                )
                return AgentResult(
                    agent_name=self.name,
                    error=f"LLM 调用失败: {str(e)}",
                    elapsed_seconds=time.time() - t0,
                )

            msg = resp.get("message", {})
            tool_calls = msg.get("tool_calls")

            # 如果没有 tool_calls → 模型已给出最终回答
            if not tool_calls:
                content = msg.get("content", "").strip()
                return AgentResult(
                    content=content,
                    tool_calls_log=tool_calls_log,
                    agent_name=self.name,
                    elapsed_seconds=time.time() - t0,
                )

            # 有 tool_calls → 逐个执行
            # 先将 assistant 的 tool_call 消息追加到历史
            messages.append(msg)

            for tc in tool_calls:
                fn = tc.get("function", {})
                fn_name = fn.get("name", "")
                fn_args = fn.get("arguments", {})
                if isinstance(fn_args, str):
                    try:
                        fn_args = json.loads(fn_args)
                    except json.JSONDecodeError:
                        fn_args = {}

                logger.info(
                    f"[{self.name}] Tool Call: {fn_name}({fn_args})"
                )

                # 执行工具
                result = await self.registry.execute(fn_name, fn_args, ctx)

                # 将结果序列化为字符串
                if isinstance(result, dict):
                    result_str = json.dumps(result, ensure_ascii=False)
                elif isinstance(result, str):
                    result_str = result
                else:
                    result_str = str(result)

                # 截断过长的工具返回（防止上下文溢出）
                if len(result_str) > 12000:
                    result_str = result_str[:12000] + "\n...[结果过长已截断]"

                tool_calls_log.append({
                    "round": round_idx,
                    "tool": fn_name,
                    "args": fn_args,
                    "result_len": len(result_str),
                })

                # 如果是 direct_answer 工具，直接将其内容作为最终回答返回，结束推理
                if fn_name == "direct_answer":
                    return AgentResult(
                        content=result_str,
                        tool_calls_log=tool_calls_log,
                        agent_name=self.name,
                        elapsed_seconds=time.time() - t0,
                    )

                # 回注工具执行结果
                messages.append({
                    "role": "tool",
                    "content": result_str,
                })

        # 超过最大循环次数
        logger.warning(f"[{self.name}] 达到最大工具调用轮次 {MAX_TOOL_CALL_ROUNDS}")
        return AgentResult(
            content="⚠️ Agent 达到最大推理轮次限制，已强制终止。",
            tool_calls_log=tool_calls_log,
            agent_name=self.name,
            elapsed_seconds=time.time() - t0,
            error="达到最大工具调用轮次",
        )

    def __repr__(self) -> str:
        return (
            f"<{self.__class__.__name__} name='{self.name}' "
            f"model='{self.model}' tools={len(self.registry)}>"
        )
