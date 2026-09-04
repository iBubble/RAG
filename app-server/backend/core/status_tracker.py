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


def update_file_status(project_id: str, file_id: str, status: str, chunks: int | None = None, error_message: str = "", filename: str = ""):
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
        existing_filename = ""
        if status_file.exists():
            try:
                with open(status_file, "r", encoding="utf-8") as sf:
                    existing_data = json.load(sf)
                    existing_chunks = existing_data.get("chunks", 0)
                    existing_filename = existing_data.get("filename", "")
            except Exception:
                pass

        final_chunks = chunks if chunks is not None else existing_chunks
        final_filename = filename or existing_filename
        
        data = {
            "file_id": file_id,
            "filename": final_filename,
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


def check_readiness_for_chat(project_id: str, file_ids: list[str] | None = None) -> dict:
    """
    检查指定项目及文件的就绪状态（用于 /api/chat 前置就绪度守卫与算力熔断）。
    返回结构：
    {
        "should_block": bool,
        "reason": "all_processing" | "all_failed" | "ready" | "partial_ready" | "no_files",
        "wait_message": str,
        "partial_notice": str,
        "processing_files": list,
        "ready_files": list
    }
    """
    if not project_id:
        return {"should_block": False, "reason": "no_project", "wait_message": "", "partial_notice": ""}

    project_dir = UPLOAD_ROOT / project_id
    import hashlib
    file_map = {}

    if project_dir.exists():
        for root, dirs, files in os.walk(str(project_dir)):
            dirs[:] = [d for d in dirs if not d.startswith('.')]
            for fname in files:
                if fname.startswith('.') or fname.endswith('.lock'):
                    continue
                fpath = Path(root) / fname
                try:
                    rel_path = str(fpath.relative_to(UPLOAD_ROOT))
                except Exception:
                    rel_path = f"{project_id}/{fname}"
                fid = hashlib.md5(f"{project_id}_{rel_path}".encode("utf-8")).hexdigest()
                st_data = get_file_status(project_id, fid)
                st = st_data.get("status", "pending")
                chunks = st_data.get("chunks", 0)
                file_map[fid] = {"file_id": fid, "filename": fname, "status": st, "chunks": chunks}

    # 兜底：如果传入了 file_ids 但未在物理扫描中匹配到，尝试直接读取 status_tracker
    if file_ids:
        for fid in file_ids:
            if fid not in file_map:
                st_data = get_file_status(project_id, fid)
                if st_data:
                    file_map[fid] = {
                        "file_id": fid,
                        "filename": st_data.get("filename", f"材料_{fid[:6]}"),
                        "status": st_data.get("status", "pending"),
                        "chunks": st_data.get("chunks", 0)
                    }

    if not file_map:
        return {"should_block": False, "reason": "no_files", "wait_message": "", "partial_notice": ""}

    target_fids = [fid for fid in file_ids if fid in file_map] if file_ids else list(file_map.keys())
    if not target_fids:
        return {"should_block": False, "reason": "external_files", "wait_message": "", "partial_notice": ""}

    processing_files = []
    ready_files = []
    failed_files = []

    for fid in target_fids:
        info = file_map[fid]
        st = info["status"]
        chunks = info.get("chunks", 0)
        if st in ("processing", "pending"):
            processing_files.append(info)
        elif st in ("vectorized", "graph_queued", "graph_extracting") or chunks > 0:
            ready_files.append(info)
        elif st in EXCLUDED_STATUSES:
            failed_files.append(info)
        else:
            processing_files.append(info)

    # 1. 目标文件全部在处理中（单选未完成或全案卷均未完成）
    if processing_files and not ready_files:
        fnames = "、".join([f"《{f['filename']}》" for f in processing_files[:3]])
        if len(processing_files) > 3:
            fnames += f" 等 {len(processing_files)} 份材料"
        wait_msg = (
            f"⏳ 案卷材料 {fnames} 正在进行多模态文字提取与切片索引中，知识库尚未就绪。\n\n"
            f"为避免生成不准确内容并为您节省计算算力，请等待材料解析完成（通常仅需 10~30 秒）后再发起提问。"
        )
        return {
            "should_block": True,
            "reason": "all_processing",
            "wait_message": wait_msg,
            "partial_notice": "",
            "processing_files": processing_files
        }

    # 2. 目标文件全部解析失败或空文本（且无就绪切片）
    if failed_files and not ready_files and not processing_files:
        fnames = "、".join([f"《{f['filename']}》" for f in failed_files[:3]])
        fail_msg = (
            f"⚠️ 案卷材料 {fnames} 解析未提取到有效文本（可能是纯图片扫描件、文件损坏或不支持的格式）。\n\n"
            f"当前知识库中无可用文本切片，无法进行事实研判。请在案卷管理中检查文件状态或重新上传。"
        )
        return {
            "should_block": True,
            "reason": "all_failed",
            "wait_message": fail_msg,
            "partial_notice": "",
            "failed_files": failed_files
        }

    # 3. 部分文件就绪，部分文件处理中
    partial_notice = ""
    if processing_files and ready_files:
        fnames = "、".join([f"《{f['filename']}》" for f in processing_files[:2]])
        partial_notice = f"ℹ️ 提示：案卷中还有 {fnames} 等正在切片中，本次回答仅基于已完成索引的 {len(ready_files)} 份材料。\n\n"

    return {
        "should_block": False,
        "reason": "ready" if not processing_files else "partial_ready",
        "wait_message": "",
        "partial_notice": partial_notice,
        "processing_files": processing_files,
        "ready_files": ready_files
    }

