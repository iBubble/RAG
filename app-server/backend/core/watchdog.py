import os
import time
import logging
import threading
from fastapi import Request, HTTPException
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger(__name__)

from core.config import settings, STORAGE_ROOT

# 全局状态：指示系统是否处于只读模式（即检测到磁盘离线）
SYSTEM_READ_ONLY = False
TARGET_RAID_PATH = STORAGE_ROOT

def test_storage_accessible() -> bool:
    """测试外部存储阵列是否可正常访问并具备写入权限"""
    try:
        return os.path.exists(TARGET_RAID_PATH) and os.access(TARGET_RAID_PATH, os.W_OK)
    except Exception:
        return False

def _watchdog_worker():
    global SYSTEM_READ_ONLY
    logger.info(f"💾 开始监听外部存储阵列心跳: {TARGET_RAID_PATH}")
    
    consecutive_failures = 0
    MAX_RETRY_COUNT = 3  # 连续失败 3 次（每次间隔 2 秒，共约 6 秒防抖）才确认脱机

    while True:
        try:
            is_ok = test_storage_accessible()

            if is_ok:
                consecutive_failures = 0
                if SYSTEM_READ_ONLY:
                    logger.info("🟩 外部存储已成功恢复上线，系统退出保护模式，恢复正常读写！")
                    SYSTEM_READ_ONLY = False
                sleep_duration = 15  # 正常在线状态每 15 秒轻量巡检一次
            else:
                consecutive_failures += 1
                if not SYSTEM_READ_ONLY:
                    if consecutive_failures < MAX_RETRY_COUNT:
                        logger.warning(
                            f"⚠️ 检测到外部存储瞬态抖动/未就绪 (第 {consecutive_failures}/{MAX_RETRY_COUNT} 次)，"
                            f"启动自动防抖重试中..."
                        )
                        time.sleep(2)  # 快速重试间隔
                        continue
                    else:
                        logger.critical(
                            f"🤬 🚨 紧急！外部存储 {TARGET_RAID_PATH} 连续 {MAX_RETRY_COUNT} 次校验失败，"
                            f"确认脱机！系统立刻进入安全只读保护模式 (Read-Only)！"
                        )
                        SYSTEM_READ_ONLY = True

                sleep_duration = 3  # 处于脱机保护模式时，每 3 秒快速探活以便秒级自愈

        except Exception as e:
            logger.error(f"Watchdog 异常: {e}")
            sleep_duration = 10
            
        time.sleep(sleep_duration)

def start_watchdog():
    t = threading.Thread(target=_watchdog_worker, daemon=True)
    t.start()

class ReadOnlyMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # WHY: 根据最新方案，不再限制非文档类的其它写操作，外置硬盘不在线只在文件上传时熔断。
        response = await call_next(request)
        return response

