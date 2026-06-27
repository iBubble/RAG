"""
Redis 语义缓存通用模块。
封装利用 BGE-M3 提问向量的余弦相似度匹配逻辑，以解耦并复用。
"""
import base64
import logging
import numpy as np
from typing import Optional

from core.redis_client import get_redis
from core.vector_store import _get_dense_model

logger = logging.getLogger(__name__)

def _get_semantic_key(project_id: str, chat_mode: str, file_ids: list[str]) -> str:
    """生成语义缓存的 Redis Hash Key"""
    sorted_fids = ",".join(sorted(file_ids)) if file_ids else ""
    return f"semantic_cache:{project_id}:{chat_mode}:{sorted_fids}"

def get_semantic_cache(
    project_id: str,
    message: str,
    chat_mode: str,
    file_ids: list[str],
) -> Optional[str]:
    """
    通过 BGE-M3 向量匹配语义缓存。
    相似度阈值固定为 0.96，命中则返回对应的精确缓存 key，否则返回 None。
    """
    r = get_redis()
    if not r:
        return None
    
    try:
        semantic_key = _get_semantic_key(project_id, chat_mode, file_ids)
        cached_vectors = r.hgetall(semantic_key)
        if not cached_vectors:
            return None
        
        logger.info(f"🔍 尝试语义缓存匹配 (样本数: {len(cached_vectors)})")
        
        # 生成当前查询的向量并归一化
        model = _get_dense_model()
        query_vec = model.encode(message)
        query_vec = query_vec / np.linalg.norm(query_vec)
        
        best_sim = -1.0
        best_exact_key = None
        
        for ans_key_b, vec_b64_b in cached_vectors.items():
            ans_key = ans_key_b.decode("utf-8") if isinstance(ans_key_b, bytes) else ans_key_b
            vec_b64 = vec_b64_b.decode("utf-8") if isinstance(vec_b64_b, bytes) else vec_b64_b
            
            vec_bytes = base64.b64decode(vec_b64)
            vec = np.frombuffer(vec_bytes, dtype=np.float32)
            
            # 余弦相似度
            sim = np.dot(query_vec, vec)
            if sim > best_sim:
                best_sim = sim
                best_exact_key = ans_key
        
        if best_sim >= 0.96 and best_exact_key:
            logger.info(f"🎯 语义缓存命中 (相似度: {best_sim:.4f})")
            # 确认精确 key 是否确实存在
            if r.exists(best_exact_key):
                return best_exact_key
            else:
                # 引用失效，清理之
                r.hdel(semantic_key, best_exact_key)
        return None
    except Exception as e:
        logger.warning(f"获取语义缓存失败: {e}")
        return None

def set_semantic_cache(
    project_id: str,
    message: str,
    chat_mode: str,
    file_ids: list[str],
    exact_key: str,
    ttl: int = 3600,
) -> None:
    """
    写入语义缓存对应的向量映射。
    """
    r = get_redis()
    if not r:
        return
    
    try:
        # 生成当前查询的向量并归一化
        model = _get_dense_model()
        query_vec = model.encode(message)
        query_vec = query_vec / np.linalg.norm(query_vec)
        vec_b64 = base64.b64encode(query_vec.astype(np.float32).tobytes()).decode("utf-8")
        
        semantic_key = _get_semantic_key(project_id, chat_mode, file_ids)
        r.hset(semantic_key, exact_key, vec_b64)
        r.expire(semantic_key, ttl)
        
        # 关联到 project 的失效集合
        project_pattern = f"chat_keys:{project_id}"
        r.sadd(project_pattern, semantic_key)
        logger.debug(f"💾 语义缓存映射写入成功: {exact_key[:30]}...")
    except Exception as e:
        logger.warning(f"写入语义缓存失败: {e}")
