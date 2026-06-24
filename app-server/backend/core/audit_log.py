"""
统一操作审计日志模块。
WHY: _log_operation 原先定义在 api/auth.py 中，被 api/files.py 等多个模块
     跨层导入（from api.auth import _log_operation），形成 api → api 的
     耦合依赖。提取到 core 层消除循环导入风险，各 API 模块统一调用。
"""
from __future__ import annotations

import uuid
import logging
from datetime import datetime

from core.database import get_db

logger = logging.getLogger(__name__)


def log_operation(user_id: str | None, action: str, detail: str):
    """
    记录关键操作日志到 SQLite。
    WHY: 日志写入失败绝不阻断核心业务流程。
         滚动清理改为按时间戳删除 30 天前的记录，
         避免每次写入都触发全表扫描排序。
    """
    from datetime import timezone, timedelta
    tz_bj = timezone(timedelta(hours=8))
    try:
        with get_db() as conn:
            conn.execute(
                """INSERT INTO operation_logs (id, user_id, action, detail, timestamp)
                   VALUES (?, ?, ?, ?, ?)""",
                (
                    str(uuid.uuid4()), user_id, action, detail,
                    datetime.now(tz_bj).replace(tzinfo=None).isoformat(timespec="seconds"),
                ),
            )
            # WHY: 按时间清理替代 NOT IN 子查询，性能从 O(n·log n) 降至 O(1)
            #      idx_logs_time 索引保证删除操作快速定位
            conn.execute(
                """DELETE FROM operation_logs
                   WHERE datetime(timestamp) < datetime('now', '+8 hours', '-30 days')""",
            )
    except Exception as exc:
        # WHY: 日志写入绝不能阻断登录/注册等核心流程
        logger.warning(f"操作日志写入失败（已静默跳过）: {exc}")
