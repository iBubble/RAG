import os
import json
from pathlib import Path
from datetime import datetime, timezone, timedelta
from threading import Lock

from core.config import settings
import logging

logger = logging.getLogger(__name__)

# WHY: 统一所有看板（管理员学习进度 + 项目知识库）的文件统计排除口径。
#      这些状态的文件不计入"有效文件总数"，避免管理员和用户看到不同的数字。
EXCLUDED_STATUSES = frozenset({
    "empty_text",          # 未提取到文本（纯图扫描件）
    "unsupported_format",  # 不支持的格式
    "too_large",           # 文件体积超过 1.5GB 限制
    "failed",              # 解析过程异常崩溃
})

# WHY: 失败原因的中文映射，供看板展示。单点维护避免多处硬编码不一致。
EXCLUDED_REASON_MAP = {
    "empty_text": "未提取到文本 (可能是纯图扫描件)",
    "unsupported_format": "不支持的格式",
    "too_large": "文件体积过大",
    "failed": "解析过程失败",
}

# 获取准确的上传目录根路径，与 api/files.py 保持一致
UPLOAD_ROOT = Path(settings.UPLOAD_DIR)
try:
    UPLOAD_ROOT.mkdir(parents=True, exist_ok=True)
except (PermissionError, OSError):
    UPLOAD_ROOT = Path("uploads")


def _get_status_file(project_id: str, file_id: str) -> Path:
    """获取该文件的状态持久化路径"""
    status_dir = UPLOAD_ROOT / project_id / ".job_states"
    status_dir.mkdir(parents=True, exist_ok=True)
    return status_dir / f"{file_id}.json"


def update_file_status(project_id: str, file_id: str, status: str, chunks: int | None = None, error_message: str = ""):
    """
    将文件的解析状态更新到本地 json 文件中。
    status 等级: 
        - "processing"
        - "vectorized"
        - "unsupported_format"
        - "empty_text"
        - "failed"
        - "too_large"
    """
    try:
        status_file = _get_status_file(project_id, file_id)
        
        existing_chunks = 0
        if status_file.exists():
            try:
                with open(status_file, "r", encoding="utf-8") as sf:
                    existing_data = json.load(sf)
                    existing_chunks = existing_data.get("chunks", 0)
            except Exception:
                pass

        final_chunks = chunks if chunks is not None else existing_chunks
        
        data = {
            "file_id": file_id,
            "status": status,
            "chunks": final_chunks,
            "error_message": error_message,
            "updated_at": datetime.now(timezone(timedelta(hours=8))).replace(tzinfo=None).isoformat()
        }
        
        # 覆写最新的状态
        with open(status_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            
    except Exception as e:
        logger.error(f"无法更新文件 {file_id} 状态: {e}")


def get_file_status(project_id: str, file_id: str) -> dict:
    """
    尝试读取本地解析状态，若无则返回空字典
    """
    try:
        status_file = _get_status_file(project_id, file_id)
        if status_file.exists():
            with open(status_file, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception as e:
        logger.warning(f"无法读取文件 {file_id} 状态: {e}")
        
    return {}
