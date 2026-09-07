"""
后台学习流程全自动定时排查与自愈守护进程 (Daemon Watchdog)。
每 60 秒对全系统项目进行故障扫描与原子自愈，由 PM2 常驻托管运行。
"""
import os
import sys
import time
import logging

sys.path.append("/app/backend")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [WatchdogDaemon] %(message)s"
)
logger = logging.getLogger("WatchdogDaemon")

from core.watchdog_engine import run_full_inspection_and_repair

def main():
    logger.info("🚀 启动后台学习流程自愈守护引擎 (PM2 常驻模式，周期: 60s)...")
    while True:
        try:
            res = run_full_inspection_and_repair()
            if res.get("vectors_repaired", 0) > 0 or res.get("graphs_repaired", 0) > 0 or res.get("summaries_triggered", 0) > 0:
                logger.warning(f"⚡ [WatchdogDaemon] 自愈触发动作: {res}")
        except Exception as e:
            logger.error(f"❌ [WatchdogDaemon] 巡检异常(下周期自动接续): {e}")
        time.sleep(60)

if __name__ == "__main__":
    main()
