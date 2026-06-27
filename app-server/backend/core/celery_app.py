"""
Celery 异步队列管理器。
WHY: 隔离复杂的文本提取、CAD 解析、以及耗时的 LlamaIndex / ChromaDB 向量计算，
     防止阻塞主 FastAPI 线程导致连接超时。
"""
from __future__ import annotations

import os

# WHY: 修复 macOS 上多进程 fork 调用底层 Swift/Objective-C 库时的 crash 问题
os.environ["OBJC_DISABLE_INITIALIZE_FORK_SAFETY"] = "YES"

from celery import Celery

# 依赖系统的默认 Redis 服务作为消息 broker
REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")

celery_app = Celery(
    "syrag_worker",
    broker=REDIS_URL,
    backend=REDIS_URL,
    include=["worker"]
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Asia/Shanghai",
    enable_utc=True,
    # WHY: Vision LLM 处理期间每个 Worker 子进程独占 GPU 推理，
    #       concurrency=2 会导致两个并发进程互抢 Ollama 推理槽位，
    #       引发大量 Vision 超时和 OOM。concurrency=1 确保串行处理，
    #       同时配合 max_tasks_per_child=500 减少不必要的进程轮转。
    worker_concurrency=1,
    worker_prefetch_multiplier=1,
    # WHY: 超时由 PM2 env 注入，fast=600s slow=3600s。
    #       fast Worker (celery 队列): 文本提取/向量化，最多 10 分钟。
    #       slow Worker (slow_queue): 图谱提取/社区摘要，最多 60 分钟。
    #       hard limit 强杀进程，soft limit 抛 SoftTimeLimitExceeded。
    task_time_limit=int(os.environ.get("TASK_TIME_LIMIT", "1800")),
    task_soft_time_limit=int(os.environ.get("TASK_SOFT_TIME_LIMIT", "1500")),
    # WHY: Worker 被超时杀死后，任务不应丢失。acks_late 确保任务在完成后才确认，
    #      reject_on_worker_lost 确保 Worker 异常退出时任务自动重新入队。
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_max_tasks_per_child=500,
)

from celery.schedules import crontab

celery_app.conf.beat_schedule = {
    'nightly-ragas-audit': {
        'task': 'worker.evaluate_nightly_ragas',
        'schedule': crontab(hour=3, minute=0),  # 每天凌晨 3:00 执行
    },
}
