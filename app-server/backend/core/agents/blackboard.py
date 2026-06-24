# -*- coding: utf-8 -*-
"""
共享记忆黑板 (Blackboard)。
WHY: 实现 Agent 间的上下文共享 — 多 Agent 协同的核心通信机制。
     Agent A 将中间结果写入黑板 → Agent B 可读取并引用，
     实现真正的跨 Agent 信息传递（而非硬编码的参数传递）。

设计：
- 基于 Redis Hash，按会话 ID (session_id) 隔离
- TTL 自动清理，防止内存膨胀
- 支持协作链日志（记录 Agent 交互过程，供前端可视化）
"""
from __future__ import annotations

import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Optional

logger = logging.getLogger(__name__)


@dataclass
class AgentEvent:
    """Agent 协作事件（用于前端可视化）。"""
    agent_name: str
    status: str  # "routing", "thinking", "executing", "critiquing", "deciding"
    message: str
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return {
            "agent": self.agent_name,
            "status": self.status,
            "message": self.message,
            "timestamp": self.timestamp,
        }


class Blackboard:
    """
    Agent 间共享的上下文状态空间。

    数据结构（Redis Hash）：
      Key: "agent:blackboard:{session_id}"
      Fields: 由各 Agent 自由写入的 key-value 对

    协作链日志（Redis List）：
      Key: "agent:events:{session_id}"
      Values: AgentEvent 的 JSON 序列化
    """

    def __init__(self, session_id: Optional[str] = None, ttl: int = 600) -> None:
        self.session_id = session_id or str(uuid.uuid4())[:12]
        self.ttl = ttl
        self._bb_key = f"agent:blackboard:{self.session_id}"
        self._ev_key = f"agent:events:{self.session_id}"
        # 内存回退（Redis 不可用时）
        self._fallback: dict[str, str] = {}
        self._events: list[AgentEvent] = []

    def _get_redis(self):
        """获取 Redis 连接（容错）。"""
        try:
            from core.redis_client import get_redis
            return get_redis()
        except Exception:
            return None

    async def write(self, agent_name: str, key: str, value: Any) -> None:
        """
        Agent 写入共享数据。
        WHY: Agent A 的中间结果可以被 Agent B 读取引用。
        """
        val_str = json.dumps(value, ensure_ascii=False) if not isinstance(value, str) else value
        r = self._get_redis()
        if r:
            try:
                r.hset(self._bb_key, key, val_str)
                r.expire(self._bb_key, self.ttl)
                return
            except Exception as e:
                logger.warning(f"[Blackboard] Redis 写入失败: {e}")
        self._fallback[key] = val_str

    async def read(self, key: str) -> Optional[str]:
        """读取共享数据。"""
        r = self._get_redis()
        if r:
            try:
                val = r.hget(self._bb_key, key)
                if val:
                    return val.decode("utf-8") if isinstance(val, bytes) else str(val)
            except Exception as e:
                logger.warning(f"[Blackboard] Redis 读取失败: {e}")
        return self._fallback.get(key)

    async def read_json(self, key: str) -> Any:
        """读取并反序列化 JSON 数据。"""
        val = await self.read(key)
        if val:
            try:
                return json.loads(val)
            except json.JSONDecodeError:
                return val
        return None

    async def get_all(self) -> dict[str, str]:
        """获取当前会话的所有共享数据。"""
        r = self._get_redis()
        if r:
            try:
                data = r.hgetall(self._bb_key)
                return {
                    (k.decode() if isinstance(k, bytes) else str(k)):
                    (v.decode() if isinstance(v, bytes) else str(v))
                    for k, v in data.items()
                }
            except Exception:
                pass
        return dict(self._fallback)

    async def log_event(self, event: AgentEvent) -> None:
        """
        记录协作事件（供前端 SSE 推送和可视化）。
        WHY: 前端需要实时展示「Agent 协作流程面板」。
        """
        self._events.append(event)
        r = self._get_redis()
        if r:
            try:
                r.rpush(self._ev_key, json.dumps(event.to_dict(), ensure_ascii=False))
                r.expire(self._ev_key, self.ttl)
            except Exception:
                pass

    async def get_events(self) -> list[dict]:
        """获取当前会话的所有协作事件。"""
        r = self._get_redis()
        if r:
            try:
                items = r.lrange(self._ev_key, 0, -1)
                return [
                    json.loads(i.decode() if isinstance(i, bytes) else str(i))
                    for i in items
                ]
            except Exception:
                pass
        return [e.to_dict() for e in self._events]
