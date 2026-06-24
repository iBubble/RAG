"""
Chat 对话两级缓存管理器。

WHY: /api/chat 每次请求都要经历完整的意图分类 → 查询改写 → 六路并行检索
     → LLM 推理流程，即使用户问到相同问题也要重新执行全链路（10-30 秒）。
     L1 缓存检索结果（节省 5-15s），L2 缓存完整回答（< 100ms 返回）。

架构：
  L1 — RAG Context Cache: 缓存 run_retrieval() 的返回结果
  L2 — Answer Cache:      缓存 LLM 完整回答文本 + source_files

Key 策略：
  L1: chat_rag:{xxhash64(project_id:search_query:sorted_file_ids:strategy_fp)}
  L2: chat_ans:{xxhash64(project_id:message:chat_mode:sorted_file_ids)}

失效策略：
  - TTL 自动过期（L1=30min, L2=1h）
  - 文档入库/更新/删除时按 project_id 批量失效（Redis SCAN + DEL）
"""
from __future__ import annotations

import json
import logging
from typing import Optional

import xxhash

from core.redis_client import get_redis
from core.config import settings

logger = logging.getLogger(__name__)


# ── Key 生成 ────────────────────────────────────────────


def _l1_key(
    project_id: str,
    search_query: str,
    file_ids: list[str],
    strategy_fingerprint: str,
) -> str:
    """L1 检索缓存 Key。"""
    h = xxhash.xxh64()
    sorted_fids = ",".join(sorted(file_ids)) if file_ids else ""
    h.update(
        f"{project_id}:{search_query}:{sorted_fids}"
        f":{strategy_fingerprint}".encode("utf-8")
    )
    return f"chat_rag:{h.hexdigest()}"


def _l2_key(
    project_id: str,
    message: str,
    chat_mode: str,
    file_ids: list[str],
) -> str:
    """L2 回答缓存 Key。"""
    h = xxhash.xxh64()
    sorted_fids = ",".join(sorted(file_ids)) if file_ids else ""
    h.update(
        f"{project_id}:{message}:{chat_mode}"
        f":{sorted_fids}".encode("utf-8")
    )
    return f"chat_ans:{h.hexdigest()}"


def _project_pattern(project_id: str) -> str:
    """用于 SCAN 的模式，匹配指定项目的所有 chat 缓存。"""
    # WHY: xxhash key 中嵌入了 project_id，无法通过 key 前缀匹配。
    #      改用独立的 Set 记录每个 project 的所有 key。
    return f"chat_keys:{project_id}"


# ── L1: 检索缓存 ────────────────────────────────────────


def get_rag_cache(
    project_id: str,
    search_query: str,
    file_ids: list[str],
    strategy_fingerprint: str,
) -> Optional[dict]:
    """
    查询 L1 检索缓存。
    返回 {"context": str, "source_files": list, "data_analysis_meta": dict}
    未命中返回 None。
    """
    if not settings.CHAT_CACHE_ENABLED:
        return None
    r = get_redis()
    if not r:
        return None
    try:
        key = _l1_key(
            project_id, search_query, file_ids, strategy_fingerprint
        )
        val = r.get(key)
        if val:
            logger.info(f"🎯 Chat L1 缓存命中: {key[:30]}...")
            return json.loads(val)
        return None
    except Exception as e:
        logger.warning(f"Chat L1 缓存读取失败（降级跳过）: {e}")
        return None


def set_rag_cache(
    project_id: str,
    search_query: str,
    file_ids: list[str],
    strategy_fingerprint: str,
    context: str,
    source_files: list,
    data_analysis_meta: dict | None = None,
) -> None:
    """写入 L1 检索缓存。"""
    if not settings.CHAT_CACHE_ENABLED:
        return
    r = get_redis()
    if not r:
        return
    if not context or not context.strip():
        return
    try:
        key = _l1_key(
            project_id, search_query, file_ids, strategy_fingerprint
        )
        payload = json.dumps(
            {
                "context": context,
                "source_files": source_files,
                "data_analysis_meta": data_analysis_meta or {},
            },
            ensure_ascii=False,
        )
        r.setex(key, settings.CHAT_RAG_CACHE_TTL, payload)
        # 记录 key 到项目索引（用于批量失效）
        r.sadd(_project_pattern(project_id), key)
        logger.debug(f"💾 Chat L1 缓存写入: {key[:30]}...")
    except Exception as e:
        logger.warning(f"Chat L1 缓存写入失败（降级跳过）: {e}")


# ── L2: 回答缓存 ────────────────────────────────────────


def get_answer_cache(
    project_id: str,
    message: str,
    chat_mode: str,
    file_ids: list[str],
) -> Optional[dict]:
    """
    查询 L2 回答缓存。
    返回 {"answer": str, "source_files": list, "data_analysis_meta": dict}
    未命中返回 None。
    """
    if not settings.CHAT_CACHE_ENABLED:
        return None
    r = get_redis()
    if not r:
        return None
    try:
        key = _l2_key(project_id, message, chat_mode, file_ids)
        val = r.get(key)
        if val:
            logger.info(f"🎯 Chat L2 缓存命中: {key[:30]}...")
            return json.loads(val)
        return None
    except Exception as e:
        logger.warning(f"Chat L2 缓存读取失败（降级跳过）: {e}")
        return None


def set_answer_cache(
    project_id: str,
    message: str,
    chat_mode: str,
    file_ids: list[str],
    answer: str,
    source_files: list,
    data_analysis_meta: dict | None = None,
) -> None:
    """写入 L2 回答缓存。空回答或错误标记不缓存。"""
    if not settings.CHAT_CACHE_ENABLED:
        return
    r = get_redis()
    if not r:
        return
    if not answer or not answer.strip():
        return
    # WHY: 错误标记不缓存，防止永久阻断重试
    if answer.strip().startswith(("❌", "⚠️")):
        return
    try:
        key = _l2_key(project_id, message, chat_mode, file_ids)
        payload = json.dumps(
            {
                "answer": answer,
                "source_files": source_files,
                "data_analysis_meta": data_analysis_meta or {},
            },
            ensure_ascii=False,
        )
        r.setex(key, settings.CHAT_ANSWER_CACHE_TTL, payload)
        # 记录 key 到项目索引
        r.sadd(_project_pattern(project_id), key)
        logger.debug(f"💾 Chat L2 缓存写入: {key[:30]}...")
    except Exception as e:
        logger.warning(f"Chat L2 缓存写入失败（降级跳过）: {e}")


# ── 缓存失效 ────────────────────────────────────────────


def invalidate_chat_cache(project_id: str) -> int:
    """
    按 project_id 批量失效所有 Chat 缓存（L1 + L2）。
    WHY: 文档入库/更新/删除时调用，防止使用过期检索结果。

    返回删除的 key 数量。
    """
    r = get_redis()
    if not r:
        return 0
    try:
        idx_key = _project_pattern(project_id)
        keys = r.smembers(idx_key)
        if not keys:
            return 0
        count = 0
        # WHY: Pipeline 批量删除，减少 RTT
        pipe = r.pipeline()
        for k in keys:
            pipe.delete(k)
        pipe.delete(idx_key)
        pipe.execute()
        count = len(keys)
        logger.info(
            f"🗑️ Chat 缓存失效: project={project_id} | "
            f"清除 {count} 个 key"
        )
        return count
    except Exception as e:
        logger.warning(f"Chat 缓存失效异常（非致命）: {e}")
        return 0
