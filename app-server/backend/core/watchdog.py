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

def _watchdog_worker():
    global SYSTEM_READ_ONLY
    logger.info(f"💾 开始监听外部存储阵列心跳: {TARGET_RAID_PATH}")
    
    while True:
        try:
            # WHY: 测试宿主机的挂载盘是否可写或者至少存在
            if not os.path.exists(TARGET_RAID_PATH):
                if not SYSTEM_READ_ONLY:
                    logger.critical(f"🤬 🚨 紧急！检测到外部存储 {TARGET_RAID_PATH} 脱机，系统立刻进入安全只读保护模式 (Read-Only)！")
                    SYSTEM_READ_ONLY = True
            else:
                # WHY: 改用 os.access 检查写权限，避免频繁在磁盘上创建文件
                if os.access(TARGET_RAID_PATH, os.W_OK):
                    if SYSTEM_READ_ONLY:
                        logger.info("🟩 外部存储已恢复上线，系统退出保护模式，恢复正常读写！")
                        SYSTEM_READ_ONLY = False
                else:
                    if not SYSTEM_READ_ONLY:
                        logger.critical(f"🤬 🚨 紧急！外部存储 {TARGET_RAID_PATH} 失去写权限，可能被强退或休眠！进入只读保护模式！")
                        SYSTEM_READ_ONLY = True
                        
        except Exception as e:
            logger.error(f"Watchdog 异常: {e}")
            
        time.sleep(30) # 每 30 秒心跳一次

def start_watchdog():
    t = threading.Thread(target=_watchdog_worker, daemon=True)
    t.start()

class ReadOnlyMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        global SYSTEM_READ_ONLY
        
        # 如果系统是只读模式，拦截所有非 GET 的修改型请求
        if SYSTEM_READ_ONLY:
            if request.method in ["POST", "PUT", "DELETE", "PATCH"]:
                return JSONResponse(
                    status_code=503,
                    content={"detail": "🚨 [系统防灾熔断警告] 外部 NAS 存储阵列离线，为防止造成数据幽灵覆盖及损坏，系统已强制进入只读(Read-Only)保护模式，暂时无法处理新建/修改/生成指派。"},
                )
        
        response = await call_next(request)
        return response
