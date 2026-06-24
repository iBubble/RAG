# -*- coding: utf-8 -*-
"""
工具注册表 (Tool Registry)。
WHY: 统一管理 Agent 可调用的工具定义，序列化为 Ollama /api/chat tools 格式。
     每个工具包含 JSON Schema 参数描述和实际执行函数。
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Awaitable, Optional

logger = logging.getLogger(__name__)


@dataclass
class ToolParameter:
    """工具参数定义。"""
    name: str
    type: str  # "string", "number", "boolean", "array", "object"
    description: str
    required: bool = True
    enum: Optional[list[str]] = None


@dataclass
class Tool:
    """
    Agent 可调用的工具。
    WHY: 封装工具的元数据和执行函数，支持序列化为 Ollama tools 格式。
    """
    name: str
    description: str
    parameters: list[ToolParameter] = field(default_factory=list)
    # handler 是一个 async 函数: (args: dict, context: dict) -> Any
    handler: Optional[Callable[..., Awaitable[Any]]] = None

    def to_ollama_schema(self) -> dict:
        """
        转换为 Ollama /api/chat tools JSON Schema 格式。
        WHY: Ollama 原生 Tool Calling 要求 OpenAI 兼容的 tools 数组格式。
        """
        properties = {}
        required_fields = []

        for param in self.parameters:
            prop: dict[str, Any] = {
                "type": param.type,
                "description": param.description,
            }
            if param.enum:
                prop["enum"] = param.enum
            properties[param.name] = prop
            if param.required:
                required_fields.append(param.name)

        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": properties,
                    "required": required_fields,
                },
            },
        }


class ToolRegistry:
    """
    工具注册中心。
    WHY: 集中管理所有已注册工具，提供按名称查找和批量序列化能力。
    """

    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        """注册一个工具。"""
        if tool.name in self._tools:
            logger.warning(f"[ToolRegistry] 工具 '{tool.name}' 已存在，将被覆盖")
        self._tools[tool.name] = tool

    def get(self, name: str) -> Optional[Tool]:
        """按名称获取工具。"""
        return self._tools.get(name)

    def get_all(self) -> list[Tool]:
        """获取所有已注册工具。"""
        return list(self._tools.values())

    def to_ollama_tools(self) -> list[dict]:
        """将所有工具序列化为 Ollama tools 数组。"""
        return [t.to_ollama_schema() for t in self._tools.values()]

    async def execute(self, name: str, arguments: dict, context: dict) -> Any:
        """
        执行指定工具。
        WHY: 统一的执行入口，包含错误处理和日志记录。
        """
        tool = self._tools.get(name)
        if not tool:
            return {"error": f"未找到工具: {name}"}
        if not tool.handler:
            return {"error": f"工具 '{name}' 未绑定执行函数"}

        try:
            result = await tool.handler(arguments, context)
            logger.info(f"[ToolRegistry] 工具 '{name}' 执行成功")
            return result
        except Exception as e:
            logger.error(f"[ToolRegistry] 工具 '{name}' 执行失败: {e}")
            return {"error": f"工具执行异常: {str(e)}"}

    def __len__(self) -> int:
        return len(self._tools)

    def __repr__(self) -> str:
        names = ", ".join(self._tools.keys())
        return f"ToolRegistry([{names}])"
