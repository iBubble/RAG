"""
Slot 缓存管理。
WHY: 预计算的 Slot 映射表缓存在磁盘上，
     当范文内容变更时需要失效对应项目的全部缓存。
"""
import logging
import shutil
from pathlib import Path

from core.config import settings

logger = logging.getLogger(__name__)

CACHE_DIR = Path(settings.DATA_DIR) / "slot_cache"


def invalidate(project_id: str) -> None:
    """清除指定项目的全部 Slot 缓存。"""
    cache_path = CACHE_DIR / project_id
    if cache_path.exists():
        shutil.rmtree(cache_path, ignore_errors=True)
        logger.info(f"Slot 缓存已清除: {project_id}")


def get_cache_dir(project_id: str) -> Path:
    """返回项目的缓存目录路径（不创建）。"""
    return CACHE_DIR / project_id
