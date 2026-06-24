"""
Redis 客户端单例工厂。
WHY: 多模块需要 Redis 做任务锁、防抖标志、状态缓存，
     统一入口避免每处重复创建连接。
"""
import logging
import os
import time
import redis

logger = logging.getLogger(__name__)

_redis_instance: redis.Redis | None = None
_last_fail_time: float = 0
# WHY: 连接失败后 60 秒内不重试，避免频繁重连风暴
_RETRY_INTERVAL = 60


def get_redis() -> redis.Redis | None:
    """
    返回 Redis 连接实例；连接失败时返回 None（允许降级运行）。
    WHY: 失败后每 60 秒自动重试一次，支持 Redis 服务恢复后自动重连。
    """
    global _redis_instance, _last_fail_time
    if _redis_instance is not None:
        return _redis_instance
    # WHY: 冷却期内不重试，避免频繁连接失败的日志刷屏
    if _last_fail_time and (time.time() - _last_fail_time) < _RETRY_INTERVAL:
        return None
    try:
        url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
        if url.count("@") > 1:
            parts = url.rsplit("@", 1)
            url = parts[0].replace("@", "%40") + "@" + parts[1]
            
        _redis_instance = redis.Redis.from_url(
            url, decode_responses=True, socket_connect_timeout=3
        )
        _redis_instance.ping()
        _last_fail_time = 0
        logger.info("Redis 连接成功")
        return _redis_instance
    except Exception as e:
        logger.warning(f"Redis 连接失败，降级运行（{_RETRY_INTERVAL}s 后重试）: {e}")
        _last_fail_time = time.time()
        _redis_instance = None
        return None


def set_agent_active(agent_key: str, task_desc: str, project_name: str | None = None, duration: int = 90):
    """
    将 Agent 的实时活跃工作状态写入 Redis。
    """
    import json
    try:
        r = get_redis()
        if r:
            data = {"task": task_desc, "project": project_name or "系统项目"}
            r.setex(f"linvis:active:{agent_key}", duration, json.dumps(data, ensure_ascii=False))
    except Exception as e:
        logger.warning(f"写入 Agent 活跃状态到 Redis 失败: {e}")


def get_agent_active(agent_key: str) -> dict | None:
    """
    从 Redis 获取 Agent 的实时工作状态。
    """
    import json
    try:
        r = get_redis()
        if r:
            val = r.get(f"linvis:active:{agent_key}")
            if val:
                return json.loads(val)
    except Exception:
        pass
    return None

