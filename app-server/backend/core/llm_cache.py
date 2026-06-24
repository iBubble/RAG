"""
LLM 调用结果 Redis 缓存。

WHY: 图谱提取、社区摘要、路径精排等场景中，相同的 prompt 可能被重复调用
     （断点续传重试、相似 chunk 重复触发等），每次都消耗 GPU 推理时间。
     用 xxhash 做 key，Redis 缓存 24 小时，相同输入直接命中缓存跳过推理。
     借鉴自 RAGFlow 的 get_llm_cache / set_llm_cache 方案。

注意：仅用于非流式、收集全量输出的场景。聊天 SSE 不走此缓存。
"""
import logging

import xxhash

from core.redis_client import get_redis

logger = logging.getLogger(__name__)

# WHY: 24 小时过期。文档内容变更后 prompt 自然变化导致 key 不同，
#      不需要手动失效。24h 兼顾命中率和数据新鲜度。
LLM_CACHE_TTL = 86400


def _cache_key(model: str, prompt: str) -> str:
    """生成缓存 key：xxhash64(model:prompt) 的十六进制摘要。"""
    h = xxhash.xxh64()
    h.update(f"{model}:{prompt}".encode("utf-8"))
    return f"llm_cache:{h.hexdigest()}"


def get_llm_cache(model: str, prompt: str) -> str | None:
    """
    查询 LLM 调用缓存。
    返回缓存的 LLM 输出文本，未命中返回 None。
    """
    r = get_redis()
    if not r:
        return None
    try:
        key = _cache_key(model, prompt)
        val = r.get(key)
        if val:
            logger.debug(f"🎯 LLM 缓存命中: {key[:24]}...")
            return val
        return None
    except Exception as e:
        logger.warning(f"LLM 缓存读取失败（降级跳过）: {e}")
        return None


def set_llm_cache(model: str, prompt: str, result: str) -> None:
    """
    写入 LLM 调用缓存。
    空结果或错误标记（❌/⚠️ 开头）不缓存，避免缓存失败结果。
    """
    r = get_redis()
    if not r:
        return
    # WHY: 空结果和错误标记不缓存，防止永久阻断重试
    if not result or not result.strip():
        return
    if result.strip().startswith(("❌", "⚠️")):
        return
    try:
        key = _cache_key(model, prompt)
        r.setex(key, LLM_CACHE_TTL, result)
        logger.debug(f"💾 LLM 缓存写入: {key[:24]}...")
    except Exception as e:
        logger.warning(f"LLM 缓存写入失败（降级跳过）: {e}")
