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

import base64
import json
import logging
from typing import Optional

import xxhash
import numpy as np

from core.redis_client import get_redis
from core.config import settings
from core.vector_store import _get_dense_model
from core.semantic_cache import get_semantic_cache, set_semantic_cache

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
    查询 L2 回答缓存 (含语义缓存)。
    优先精确匹配，如果未命中，则进行语义匹配 (Cosine >= 0.96)。
    """
    if not settings.CHAT_CACHE_ENABLED:
        return None
    r = get_redis()
    if not r:
        return None
    try:
        # 1. 尝试精确匹配 (速度最快)
        exact_key = _l2_key(project_id, message, chat_mode, file_ids)
        val = r.get(exact_key)
        if val:
            logger.info(f"🎯 Chat L2 缓存命中 (精确): {exact_key[:30]}...")
            return json.loads(val)
        
        # 2. 尝试语义缓存匹配 (通过通用 semantic_cache 模块)
        semantic_key_hit = get_semantic_cache(project_id, message, chat_mode, file_ids)
        if semantic_key_hit:
            val = r.get(semantic_key_hit)
            if val:
                logger.info(f"🎯 Chat L2 语义缓存命中: {semantic_key_hit[:30]}...")
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
                "message": message,
                "answer": answer,
                "source_files": source_files,
                "data_analysis_meta": data_analysis_meta or {},
            },
            ensure_ascii=False,
        )
        r.setex(key, settings.CHAT_ANSWER_CACHE_TTL, payload)
        
        # 将 key 加入 project 的集合，用于后续按项目批量失效
        r.sadd(_project_pattern(project_id), key)
        
        # ── 写入语义缓存 ──
        set_semantic_cache(
            project_id=project_id,
            message=message,
            chat_mode=chat_mode,
            file_ids=file_ids,
            exact_key=key,
            ttl=settings.CHAT_ANSWER_CACHE_TTL
        )
    except Exception as e:
        logger.warning(f"写入 Chat L2 缓存失败: {e}")


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


def delete_single_chat_cache(
    project_id: str,
    message: Optional[str] = None,
    answer: Optional[str] = None,
) -> bool:
    """
    删除指定项目下匹配提问内容（message）或回答内容（answer）的 L2 缓存和对应的语义缓存。
    只在用户主动在界面上删除单条对话记录时触发。
    """
    r = get_redis()
    if not r:
        return False
    try:
        idx_key = _project_pattern(project_id)
        keys = r.smembers(idx_key)
        if not keys:
            return False
            
        keys_to_delete = []
        msg_stripped = message.strip() if message else None
        ans_stripped = answer.strip() if answer else None
        
        if not msg_stripped and not ans_stripped:
            return False
            
        # ── [CRITICAL FIX] 收集所有候选 exact_keys ──
        # 包含：1. 直接在 project 集合中的 L2 key
        #       2. 在语义缓存哈希字段中关联的 L2 key (应对老版本或间接关联的 L2 key)
        candidate_keys = set()
        semantic_keys = []
        for k_bytes in keys:
            k = k_bytes.decode("utf-8") if isinstance(k_bytes, bytes) else k_bytes
            if k.startswith("chat_ans:"):
                candidate_keys.add(k)
            elif k.startswith("semantic_cache:"):
                semantic_keys.append(k)
                try:
                    hfields = r.hkeys(k)
                    for hf_bytes in hfields:
                        hf = hf_bytes.decode("utf-8") if isinstance(hf_bytes, bytes) else hf_bytes
                        if hf.startswith("chat_ans:"):
                            candidate_keys.add(hf)
                except Exception:
                    pass

        # 1. 扫描所有候选 exact_keys
        for k in candidate_keys:
            val = r.get(k)
            if val:
                try:
                    payload = json.loads(val)
                    cached_msg = payload.get("message", "")
                    cached_ans = payload.get("answer", "")
                    
                    match_msg = msg_stripped and cached_msg and cached_msg.strip() == msg_stripped
                    match_ans = ans_stripped and cached_ans and cached_ans.strip() == ans_stripped
                    
                    if match_msg or match_ans:
                        keys_to_delete.append(k)
                except Exception:
                    pass
                    
        if not keys_to_delete:
            return False
            
        # 2. 从 Redis 删除这些精确缓存 Key
        pipe = r.pipeline()
        for k in keys_to_delete:
            pipe.delete(k)
            pipe.srem(idx_key, k)
            
        # 3. 从对应的 semantic_cache 哈希中清理掉这几个 exact_key 映射
        for k in semantic_keys:
            for exact_key in keys_to_delete:
                pipe.hdel(k, exact_key)
                
        pipe.execute()
        logger.info(f"🗑️ 已从 Redis 中清理匹配的精确及语义缓存共 {len(keys_to_delete)} 项")
        return True
    except Exception as e:
        logger.warning(f"删除单条 Chat 缓存异常: {e}")
        return False
