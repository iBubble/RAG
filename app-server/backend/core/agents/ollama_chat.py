# -*- coding: utf-8 -*-
"""
Ollama /api/chat Tool Calling 封装。
WHY: 现有 llm_engine.py 使用 /api/generate 接口（不支持 tools 参数）。
     多 Agent 协同需要 /api/chat 的原生 Tool Calling 能力，
     模型可以自主决定调用哪些工具，实现真正的自主推理。
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any, Optional, AsyncGenerator

from core.config import settings

logger = logging.getLogger(__name__)

# 清理 ChatML 残留 token 的正则
_CTRL_RE = re.compile(
    r'<\|(?:endoftext|im_start|im_end|end)\|>'
    r'|(?:^|\n)(?:user|assistant|system)\s*$',
    re.MULTILINE,
)


async def ollama_chat(
    messages: list[dict],
    model: str = settings.COLLAB_LLM_MODEL,
    tools: Optional[list[dict]] = None,
    temperature: float = 0.3,
    num_ctx: int = 8192,
    num_predict: int = 4096,
    stream: bool = False,
) -> dict:
    """
    调用 Ollama /api/chat 接口（支持 Tool Calling）。

    WHY: /api/chat 接口原生支持 tools 参数 and 多轮对话 messages 格式，
         是 Ollama Tool Calling 的唯一正确入口。
         /api/generate 不支持 tools，无法实现 Agent 自主工具调用。

    Args:
        messages: OpenAI 格式的消息列表
        model: Ollama 模型名
        tools: Ollama tools JSON Schema 数组（可选）
        temperature: 采样温度
        num_ctx: 上下文窗口
        num_predict: 最大生成 token 数
        stream: 是否流式（当前仅支持非流式）

    Returns:
        包含 message 字段的响应 dict，message 可能含 tool_calls
    """
    import asyncio
    import httpx
    from core.llm_engine import get_client

    url = f"{settings.OLLAMA_BASE_URL}/api/chat"

    payload: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "stream": False,
        "think": False,
        "keep_alive": "5m",
        "options": {
            "temperature": temperature,
            "num_predict": num_predict,
            "num_ctx": num_ctx,
            "repeat_penalty": 1.0,
        },
    }

    if tools:
        payload["tools"] = tools

    max_retries = 3
    base_delay = 1.0

    for attempt in range(max_retries):
        try:
            client = get_client()
            resp = await client.post(url, json=payload, timeout=120.0)
            resp.raise_for_status()
            data = resp.json()

            # 清理 message.content 中的 ChatML 残留
            msg = data.get("message", {})
            content = msg.get("content", "")
            if content:
                # 清理 <think>...</think> 块
                content = re.sub(
                    r'<think>.*?</think>', '', content, flags=re.DOTALL
                ).strip()
                content = _CTRL_RE.sub('', content).strip()
                msg["content"] = content

            return data

        except (httpx.TimeoutException, httpx.HTTPStatusError, httpx.RequestError) as e:
            if attempt == max_retries - 1:
                logger.error(f"[ollama_chat] 请求失败且耗尽重试次数: {e}")
                raise
            delay = base_delay * (2 ** attempt)
            logger.warning(
                f"[ollama_chat] 请求失败: {e}，正在进行第 {attempt + 1} 次重试，等待 {delay} 秒..."
            )
            await asyncio.sleep(delay)


async def ollama_chat_stream(
    messages: list[dict],
    model: str = settings.COLLAB_LLM_MODEL,
    temperature: float = 0.5,
    num_ctx: int = 16384,
    num_predict: int = 8192,
) -> AsyncGenerator[str, None]:
    """
    流式调用 Ollama /api/chat（不带 tools，用于最终回答生成）。

    WHY: 大BOSS 仲裁和最终回答需要流式输出到前端，
         但 Tool Calling 阶段不需要流式（需要完整解析 tool_calls JSON）。
    """
    import asyncio
    import httpx
    from core.llm_engine import get_client

    url = f"{settings.OLLAMA_BASE_URL}/api/chat"
    payload = {
        "model": model,
        "messages": messages,
        "stream": True,
        "think": False,
        "keep_alive": "5m",
        "options": {
            "temperature": temperature,
            "num_predict": num_predict,
            "num_ctx": num_ctx,
        },
    }

    max_retries = 3
    base_delay = 1.0

    for attempt in range(max_retries):
        try:
            client = get_client()
            in_think = False

            async with client.stream("POST", url, json=payload, timeout=60.0) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line.strip():
                        continue
                    try:
                        data = json.loads(line)
                        msg = data.get("message", {})
                        token = msg.get("content", "")
                        if not token:
                            continue

                        # 过滤 <think> 块
                        if "<think>" in token:
                            in_think = True
                            continue
                        if "</think>" in token:
                            in_think = False
                            continue
                        if in_think:
                            continue

                        # 清理 ChatML 残留
                        token = _CTRL_RE.sub('', token)
                        if token:
                            yield token

                        if data.get("done", False):
                            break
                    except json.JSONDecodeError:
                        continue
            # 正常生成并退出
            return

        except (httpx.TimeoutException, httpx.HTTPStatusError, httpx.RequestError) as e:
            if attempt == max_retries - 1:
                logger.error(f"[ollama_chat_stream] 流式请求失败且耗尽重试次数: {e}")
                raise
            delay = base_delay * (2 ** attempt)
            logger.warning(
                f"[ollama_chat_stream] 流式建立失败: {e}，正在进行第 {attempt + 1} 次重试，等待 {delay} 秒..."
            )
            await asyncio.sleep(delay)
