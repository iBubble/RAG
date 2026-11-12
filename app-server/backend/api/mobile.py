"""
手机端多模态资料采集与后台按项目资料库管理路由。
WHY: 提供专用于手机端按项目选择并上传图片、视频、音频、文档的 REST 接口，
     自动投递至多模态解析与 RAG 向量/图谱管线分析，并支持后台管理员按项目查看资料与分析结果。
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import re
import threading
import time
import uuid
import zipfile
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional
from urllib.parse import quote

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, Response, UploadFile
from fastapi.responses import FileResponse, JSONResponse

from core.audit_log import log_operation
from core.auth_deps import get_current_user, require_admin
from core.config import STORAGE_ROOT, settings
from core.database import (
    delete_mobile_upload,
    get_db,
    get_fts_chunks_by_file_id,
    get_fts_summary_map,
    get_mobile_upload,
    get_mobile_uploads_by_project,
    upsert_mobile_upload,
)
from core.project_access import require_project_access
from core.status_tracker import get_file_status, update_file_status
from core.vector_store import get_chunk_count

logger = logging.getLogger(__name__)

# TODO(security): 当前系统全局与 Go 网关（nexus-gateway）统一采用 JWT Bearer Token 头认证（无 Cookie 会话状态）；
# 若未来切换至 Cookie 会话机制，必须启用 __Host- 前缀 Cookie 与双提交/同步器 CSRF Token，并可按需接入 OAuth2 与 MFA。

router = APIRouter(prefix="/api/mobile", tags=["移动端资料采集与项目资料库"])

# ── 存储根目录初始化 ──────────────────────────────────────────
UPLOAD_ROOT = Path(settings.UPLOAD_DIR)
try:
    UPLOAD_ROOT.mkdir(parents=True, exist_ok=True)
except (PermissionError, OSError) as exc:
    logger.warning("RAID 上传目录不可用，降级到本地 uploads/ 目录: %s", type(exc).__name__)
    UPLOAD_ROOT = Path("uploads")
    UPLOAD_ROOT.mkdir(parents=True, exist_ok=True)

# ── 严格输入格式白名单 ────────────────────────────────────────
_PROJECT_ID_RE = re.compile(r"^[a-zA-Z0-9_-]{1,64}$")
_FILE_ID_RE = re.compile(r"^[a-f0-9]{32}$")
_SAFE_FOLDER_RE = re.compile(r"^[\w\u4e00-\u9fa5 -]{1,40}$")

# ── 允许上传的文件扩展名、媒体分类、标准 MIME 与单文件大小上限 ──
_MB = 1024 * 1024
_ALLOWED_EXT_MAP: dict[str, tuple[str, str, int]] = {
    # 图片（上限 50MB）
    ".jpg": ("image", "image/jpeg", 50 * _MB),
    ".jpeg": ("image", "image/jpeg", 50 * _MB),
    ".png": ("image", "image/png", 50 * _MB),
    ".webp": ("image", "image/webp", 50 * _MB),
    ".gif": ("image", "image/gif", 50 * _MB),
    ".bmp": ("image", "image/bmp", 50 * _MB),
    ".tiff": ("image", "image/tiff", 50 * _MB),
    ".tif": ("image", "image/tiff", 50 * _MB),
    # 视频（上限 300MB）
    ".mp4": ("video", "video/mp4", 300 * _MB),
    ".mov": ("video", "video/quicktime", 300 * _MB),
    ".webm": ("video", "video/webm", 300 * _MB),
    ".mkv": ("video", "video/x-matroska", 300 * _MB),
    # 音频（上限 150MB）
    ".mp3": ("audio", "audio/mpeg", 150 * _MB),
    ".wav": ("audio", "audio/wav", 150 * _MB),
    ".m4a": ("audio", "audio/mp4", 150 * _MB),
    ".aac": ("audio", "audio/aac", 150 * _MB),
    ".ogg": ("audio", "audio/ogg", 150 * _MB),
    ".flac": ("audio", "audio/flac", 150 * _MB),
    # 文档（上限 50MB）
    ".pdf": ("document", "application/pdf", 50 * _MB),
    ".doc": ("document", "application/msword", 50 * _MB),
    ".docx": ("document", "application/vnd.openxmlformats-officedocument.wordprocessingml.document", 50 * _MB),
    ".xls": ("document", "application/vnd.ms-excel", 50 * _MB),
    ".xlsx": ("document", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", 50 * _MB),
    ".pptx": ("document", "application/vnd.openxmlformats-officedocument.presentationml.presentation", 50 * _MB),
    ".txt": ("document", "text/plain; charset=utf-8", 20 * _MB),
    ".md": ("document", "text/plain; charset=utf-8", 20 * _MB),
    ".csv": ("document", "text/csv; charset=utf-8", 20 * _MB),
}


# ── 轻量级线程安全滑动窗口速率限制器 ──────────────────────────
class _SlidingWindowLimiter:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._hits: dict[str, deque[float]] = defaultdict(deque)

    def check(self, key: str, limit: int, window_seconds: int = 60) -> None:
        now = time.monotonic()
        cutoff = now - window_seconds
        with self._lock:
            q = self._hits[key]
            while q and q[0] < cutoff:
                q.popleft()
            if len(q) >= limit:
                raise HTTPException(status_code=429, detail="请求过于频繁，请稍后再试")
            q.append(now)


_limiter = _SlidingWindowLimiter()


def _rate_limit_read(request: Request, user: dict = Depends(get_current_user)) -> dict:
    client_ip = request.client.host if request.client else "unknown"
    _limiter.check(f"read:{user['id']}:{client_ip}", limit=120, window_seconds=60)
    return user


def _rate_limit_write(request: Request, user: dict = Depends(get_current_user)) -> dict:
    client_ip = request.client.host if request.client else "unknown"
    _limiter.check(f"write:{user['id']}:{client_ip}", limit=30, window_seconds=60)
    return user


def _apply_security_headers(response: Response) -> Response:
    """统一为响应附加严格安全响应头。"""
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "SAMEORIGIN"
    response.headers["Cache-Control"] = "no-store"
    response.headers["Permissions-Policy"] = "geolocation=()"
    response.headers["Content-Security-Policy"] = "default-src 'self'; frame-ancestors 'self'; object-src 'none'"
    return response


def _validate_project_id(project_id: str) -> str:
    pid = (project_id or "").strip()
    if not _PROJECT_ID_RE.match(pid):
        raise HTTPException(status_code=400, detail="非法的项目标识格式")
    return pid


def _validate_file_id(file_id: str) -> str:
    fid = (file_id or "").strip().lower()
    if not _FILE_ID_RE.match(fid):
        raise HTTPException(status_code=400, detail="非法的资料标识格式")
    return fid


def _safe_resolve_within(base_dir: Path, relative_subpath: str) -> Path:
    """
    严格解析路径并强制校验末尾目录分隔符边界，防止 ../ 路径穿越与同前缀目录绕过。
    """
    base_resolved = base_dir.resolve()
    candidate = (base_resolved / relative_subpath).resolve()
    base_prefix = str(base_resolved) + os.sep
    if not str(candidate).startswith(base_prefix):
        raise HTTPException(status_code=403, detail="非法文件路径访问")
    return candidate


def _compute_compat_file_id(project_id: str, rel_path: str) -> str:
    """
    生成与现有 worker.py / api/files.py 幂等兼容的资料索引键。
    注意：此处仅作非安全用途的确定性索引键（usedforsecurity=False），文件完整性校验另用 SHA-256。
    """
    raw_key = f"{project_id}_{rel_path}".encode("utf-8")
    return hashlib.md5(raw_key, usedforsecurity=False).hexdigest()


def _sanitize_display_filename(raw_name: str) -> str:
    """提取纯文件名并移除控制字符与路径分隔符。"""
    normalized = (raw_name or "未命名文件").replace("\\", "/")
    base = os.path.basename(normalized).strip()
    base = re.sub(r"[\x00-\x1f\x7f]", "", base)
    if not base or base in (".", ".."):
        base = "未命名资料"
    if len(base) > 180:
        stem, ext = os.path.splitext(base)
        base = f"{stem[:150]}{ext[:20]}"
    return base


def _verify_magic_bytes(ext: str, header: bytes) -> bool:
    """
    基于文件头部 Magic Bytes 校验真实二进制结构是否与扩展名一致，拦截伪造扩展名上传。
    """
    if not header:
        return False

    if ext in (".jpg", ".jpeg"):
        return header.startswith(b"\xff\xd8\xff")
    if ext == ".png":
        return header.startswith(b"\x89PNG\r\n\x1a\n")
    if ext == ".gif":
        return header.startswith((b"GIF87a", b"GIF89a"))
    if ext == ".webp":
        return len(header) >= 12 and header[:4] == b"RIFF" and header[8:12] == b"WEBP"
    if ext == ".bmp":
        return header.startswith(b"BM")
    if ext in (".tiff", ".tif"):
        return header.startswith((b"II*\x00", b"MM\x00*"))

    if ext in (".mp4", ".mov", ".m4a"):
        # ISO Base Media File Format / QuickTime 容器原子标记
        iso_markers = (b"ftyp", b"moov", b"mdat", b"wide", b"free", b"skip", b"pnot")
        return len(header) >= 12 and any(m in header[4:16] for m in iso_markers)
    if ext in (".webm", ".mkv"):
        return header.startswith(b"\x1a\x45\xdf\xa3")

    if ext == ".mp3":
        return header.startswith(b"ID3") or (
            len(header) >= 2 and header[0] == 0xFF and (header[1] & 0xE0) == 0xE0
        )
    if ext == ".aac":
        return (
            (len(header) >= 2 and header[0] == 0xFF and (header[1] & 0xF0) == 0xF0)
            or header.startswith(b"ADIF")
            or (len(header) >= 12 and b"ftyp" in header[4:12])
        )
    if ext == ".wav":
        return len(header) >= 12 and header[:4] == b"RIFF" and header[8:12] == b"WAVE"
    if ext == ".ogg":
        return header.startswith(b"OggS")
    if ext == ".flac":
        return header.startswith(b"fLaC")

    if ext == ".pdf":
        return b"%PDF-" in header[:16]
    if ext in (".docx", ".xlsx", ".pptx"):
        return header.startswith(b"PK\x03\x04")
    if ext in (".doc", ".xls"):
        return header.startswith(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1")
    if ext in (".txt", ".md", ".csv"):
        if b"\x00" in header and not header.startswith((b"\xff\xfe", b"\xfe\xff")):
            return False
        return True

    return False


def _verify_office_zip_safety(file_path: Path) -> None:
    """对基于 ZIP 的 Office 文档校验内部归档路径，防止 Zip Slip 目录穿越。"""
    try:
        with zipfile.ZipFile(file_path, "r") as zf:
            for member in zf.namelist():
                norm = os.path.normpath(member)
                if norm.startswith("..") or norm.startswith("/") or "\\" in member:
                    raise HTTPException(status_code=400, detail="文档内部结构包含非法归档路径")
    except zipfile.BadZipFile as exc:
        raise HTTPException(status_code=400, detail="Office 文档结构已损坏或格式伪造") from exc


def _infer_category_from_filename(filename: str) -> tuple[str, str]:
    ext = Path(filename).suffix.lower()
    if ext in _ALLOWED_EXT_MAP:
        cat, mime, _ = _ALLOWED_EXT_MAP[ext]
        return cat, mime
    return "document", "application/octet-stream"


def _status_label(status_code: str) -> str:
    mapping = {
        "pending": "排队待分析",
        "processing": "多模态解析中",
        "graph_queued": "向量已入库·图谱排队中",
        "graph_extracting": "知识图谱提炼中",
        "vectorized": "已完成入库分析",
        "empty_text": "未识别到有效文本",
        "unsupported_format": "格式暂不支持",
        "too_large": "文件超出大小限制",
        "failed": "解析失败",
    }
    return mapping.get(status_code or "pending", "排队待分析")


def _scan_project_materials_sync(
    project_id: str,
    include_preview: bool = True,
    preloaded_counts: Optional[dict[str, int]] = None,
) -> list[dict]:
    """
    同步扫描指定项目资料库目录并融合 mobile_uploads 元数据、解析状态与分析摘要。
    """
    project_dir = _safe_resolve_within(UPLOAD_ROOT, project_id)
    if not project_dir.exists() or not project_dir.is_dir():
        return []

    mu_map = get_mobile_uploads_by_project(project_id)
    if preloaded_counts is not None and not include_preview:
        fts_counts = preloaded_counts
        fts_previews: dict[str, str] = {}
    else:
        fts_counts, fts_previews = get_fts_summary_map(project_id, include_preview=include_preview)

    materials: list[dict] = []

    for root, dirs, files in os.walk(str(project_dir)):
        dirs[:] = [d for d in dirs if not d.startswith(".") and not d.lower().endswith(".gdb")]
        root_path = Path(root)
        for fname in files:
            if fname.startswith(".") or fname.endswith(".lock"):
                continue
            fpath = root_path / fname
            try:
                stat = fpath.stat()
                rel_path = str(fpath.relative_to(UPLOAD_ROOT)).replace("\\", "/")
            except OSError:
                continue

            fid = _compute_compat_file_id(project_id, rel_path)
            mu = mu_map.get(fid)
            display_name = mu["original_filename"] if (mu and mu.get("original_filename")) else fname
            media_cat, mime_type = (
                (mu["media_category"], mu["mime_type"])
                if mu
                else _infer_category_from_filename(display_name)
            )
            upload_source = mu.get("upload_source", "mobile") if mu else "web"
            remark = mu.get("remark", "") if mu else ""
            uploader_name = mu.get("uploader_name", "") if mu else ""
            created_at = (
                mu["created_at"]
                if (mu and mu.get("created_at"))
                else datetime.fromtimestamp(stat.st_mtime, tz=timezone(timedelta(hours=8)))
                .replace(tzinfo=None)
                .isoformat()
            )

            st_data = get_file_status(project_id, fid)
            status_code = st_data.get("status")
            chunks_count = st_data.get("chunks", 0) or fts_counts.get(fid, 0)
            error_msg = st_data.get("error_message", "")
            updated_at = st_data.get("updated_at", created_at)

            if not status_code:
                chunks_count = fts_counts.get(fid, 0)
                status_code = "vectorized" if chunks_count > 0 else "pending"

            # 读取单次聚合出的分析摘要供列表快速预览
            fts_preview = fts_previews.get(fid, "") if include_preview else ""

            # 智能判定是否出现乱码
            is_garbled_flag = False
            garbled_desc = ""
            if fts_preview:
                from core.extractors.ocr_cleaner import is_garbled_text
                is_garbled_flag, garbled_desc = is_garbled_text(fts_preview)

            # RAG 规范检测状态与分数
            comp_status = (mu.get("compliance_status") if mu else "") or st_data.get("compliance_status", "")
            comp_score = (mu.get("compliance_score") if mu else 0) or st_data.get("compliance_score", 0)

            sub_folder = ""
            rel_inside_proj = rel_path[len(project_id) + 1 :] if rel_path.startswith(f"{project_id}/") else rel_path
            if "/" in rel_inside_proj:
                sub_folder = rel_inside_proj.rsplit("/", 1)[0]

            materials.append({
                "file_id": fid,
                "project_id": project_id,
                "filename": display_name,
                "sub_folder": sub_folder,
                "media_category": media_cat,
                "mime_type": mime_type,
                "size": stat.st_size,
                "upload_source": upload_source,
                "remark": remark,
                "uploader_name": uploader_name,
                "created_at": created_at,
                "updated_at": updated_at,
                "ingest_status": status_code,
                "status_label": _status_label(status_code),
                "chunks": chunks_count,
                "error_message": error_msg if not error_msg.startswith("Graph OK:") else "",
                "graph_info": error_msg if error_msg.startswith("Graph OK:") else "",
                "analysis_preview": fts_preview,
                "is_garbled": is_garbled_flag,
                "garbled_reason": garbled_desc,
                "compliance_status": comp_status,
                "compliance_score": comp_score,
            })

    materials.sort(key=lambda x: x.get("created_at") or "", reverse=True)
    return materials


def _summarize_materials(materials: list[dict]) -> dict:
    summary = {
        "total": len(materials),
        "image_count": 0,
        "video_count": 0,
        "audio_count": 0,
        "document_count": 0,
        "mobile_count": 0,
        "analyzed_count": 0,
        "processing_count": 0,
        "failed_count": 0,
        "total_chunks": 0,
        "latest_upload_at": materials[0]["created_at"] if materials else "",
    }
    for m in materials:
        cat = m.get("media_category", "document")
        if cat == "image":
            summary["image_count"] += 1
        elif cat == "video":
            summary["video_count"] += 1
        elif cat == "audio":
            summary["audio_count"] += 1
        else:
            summary["document_count"] += 1

        if m.get("upload_source") == "mobile":
            summary["mobile_count"] += 1

        st = m.get("ingest_status", "pending")
        chunks = int(m.get("chunks") or 0)
        summary["total_chunks"] += chunks
        if st in ("vectorized", "graph_queued", "graph_extracting") or chunks > 0:
            summary["analyzed_count"] += 1
        elif st in ("pending", "processing"):
            summary["processing_count"] += 1
        else:
            summary["failed_count"] += 1

    return summary


# ═══════════════════════════════════════════════════════════════
# 1. 手机端可选项目列表接口
# ═══════════════════════════════════════════════════════════════

@router.get("/projects")
async def list_mobile_projects(
    response: Response,
    writable_only: bool = Query(False, description="是否仅返回当前用户有上传权限的项目"),
    user: dict = Depends(_rate_limit_read),
):
    """
    获取手机端可选择的项目/资料库列表，附带各项目的上传权限标记与资料数量统计。
    """
    _apply_security_headers(response)
    is_admin = user.get("role") == "admin"

    with get_db() as conn:
        if is_admin:
            rows = conn.execute(
                "SELECT * FROM projects ORDER BY sort_order ASC, created_at DESC"
            ).fetchall()
        else:
            rows = conn.execute(
                """SELECT * FROM projects
                   WHERE owner_id = ? OR visibility = 'public'
                   ORDER BY sort_order ASC, created_at DESC""",
                (user["id"],),
            ).fetchall()

    projects_out: list[dict] = []
    for row in rows:
        p = dict(row)
        pid = p["id"]
        can_upload = is_admin or (p.get("owner_id") == user["id"])
        if writable_only and not can_upload:
            continue

        # 轻量统计该项目文件数
        file_count = 0
        try:
            proj_dir = _safe_resolve_within(UPLOAD_ROOT, pid)
            if proj_dir.exists():
                for _, dirs, fnames in os.walk(str(proj_dir)):
                    dirs[:] = [d for d in dirs if not d.startswith(".")]
                    file_count += sum(1 for fn in fnames if not fn.startswith(".") and not fn.endswith(".lock"))
        except Exception:
            file_count = 0

        projects_out.append({
            "id": pid,
            "name": p.get("name", ""),
            "icon": p.get("icon") or ("📚" if p.get("project_type") == "library" else "⚖️"),
            "project_type": p.get("project_type", "case"),
            "visibility": p.get("visibility", "public"),
            "owner_id": p.get("owner_id", ""),
            "owner_name": p.get("owner_name", ""),
            "created_at": p.get("created_at", ""),
            "source_count": file_count,
            "can_upload": can_upload,
        })

    return {"projects": projects_out}


# ═══════════════════════════════════════════════════════════════
# 2. 手机端多模态资料上传与自动入库分析接口
# ═══════════════════════════════════════════════════════════════

@router.post("/upload")
async def mobile_upload_materials(
    files: list[UploadFile] = File(..., description="上传的图片、视频、音频或文档文件列表"),
    project_id: str = Form(..., description="目标项目/资料库 ID"),
    category_folder: str = Form(default="手机端上传", description="项目资料库内的归档子目录"),
    remark: str = Form(default="", description="现场取证/上传备注说明（参与知识库检索分析）"),
    user: dict = Depends(_rate_limit_write),
):
    """
    手机端按项目上传图片、视频等资料的核心接口：
    1. 校验用户对目标项目的写权限；
    2. 校验文件扩展名白名单、文件头 Magic Bytes 与文件大小上限；
    3. 使用不可预测随机 UUID 命名并设置 0o600 权限保存在 Web 根目录之外的对应项目资料库；
    4. 记录原始文件名与备注至 SQLite，并立即投递 Celery 多模态解析与向量/图谱入库任务。
    """
    # TODO(security): 如部署环境引入外部杀毒网关（如 ClamAV API）及文档内容清洗（CDR）服务，可在此处落盘前接入扫描。
    pid = _validate_project_id(project_id)
    project_info = require_project_access(pid, user, write=True)

    if not os.path.exists(STORAGE_ROOT):
        raise HTTPException(status_code=503, detail="存储服务当前不可用，请稍后重试")

    if not files or len(files) > 20:
        raise HTTPException(status_code=400, detail="单次上传文件数量需在 1 至 20 个之间")

    clean_folder = (category_folder or "手机端上传").strip().strip("/\\")
    if not clean_folder:
        clean_folder = "手机端上传"
    if not _SAFE_FOLDER_RE.match(clean_folder):
        raise HTTPException(status_code=400, detail="归档目录名称仅允许中文、字母、数字、空格、横杠和下划线（不超过40字符）")

    clean_remark = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", (remark or "").strip())[:500]

    project_base_dir = _safe_resolve_within(UPLOAD_ROOT, pid)
    project_base_dir.mkdir(parents=True, exist_ok=True)
    target_dir = _safe_resolve_within(project_base_dir, clean_folder)
    target_dir.mkdir(parents=True, exist_ok=True)

    uploaded_results: list[dict] = []
    now_iso = datetime.now(timezone(timedelta(hours=8))).replace(tzinfo=None).isoformat()

    for up_file in files:
        orig_filename = _sanitize_display_filename(up_file.filename or "未命名文件")
        ext = Path(orig_filename).suffix.lower()
        if ext not in _ALLOWED_EXT_MAP:
            raise HTTPException(
                status_code=400,
                detail=f"不支持的文件类型（{ext or '无扩展名'}），仅支持常见图片、视频、音频及办公文档格式",
            )

        media_category, canonical_mime, max_bytes = _ALLOWED_EXT_MAP[ext]

        # 读取首块并检验文件头 Magic Bytes
        first_chunk = await up_file.read(64 * 1024)
        if not first_chunk:
            raise HTTPException(status_code=400, detail=f"文件《{orig_filename}》内容为空")
        if not _verify_magic_bytes(ext, first_chunk[:64]):
            raise HTTPException(
                status_code=400,
                detail=f"文件《{orig_filename}》真实内容与扩展名 {ext} 不匹配，已拦截上传",
            )

        storage_uuid = uuid.uuid4().hex
        stored_filename = f"{storage_uuid}{ext}"
        final_path = _safe_resolve_within(target_dir, stored_filename)
        temp_path = _safe_resolve_within(target_dir, f".tmp_{storage_uuid}{ext}")

        sha256_hasher = hashlib.sha256()
        total_size = 0
        chunk_size = 2 * _MB

        try:
            with open(temp_path, "wb") as out_f:
                out_f.write(first_chunk)
                sha256_hasher.update(first_chunk)
                total_size += len(first_chunk)
                if total_size > max_bytes:
                    raise HTTPException(
                        status_code=413,
                        detail=f"文件《{orig_filename}》超过单文件大小上限（{max_bytes // _MB} MB）",
                    )

                while True:
                    buf = await up_file.read(chunk_size)
                    if not buf:
                        break
                    total_size += len(buf)
                    if total_size > max_bytes:
                        raise HTTPException(
                            status_code=413,
                            detail=f"文件《{orig_filename}》超过单文件大小上限（{max_bytes // _MB} MB）",
                        )
                    out_f.write(buf)
                    sha256_hasher.update(buf)

            # 对 ZIP 容器类 Office 文档执行防穿越结构校验
            if ext in (".docx", ".xlsx", ".pptx"):
                _verify_office_zip_safety(temp_path)

            # 设置为不可执行权限 0o600 并原子落盘
            os.chmod(temp_path, 0o600)
            os.replace(temp_path, final_path)
        except HTTPException:
            if temp_path.exists():
                temp_path.unlink(missing_ok=True)
            raise
        except Exception as exc:
            logger.error("保存手机端上传文件异常: %s", type(exc).__name__)
            if temp_path.exists():
                temp_path.unlink(missing_ok=True)
            raise HTTPException(status_code=500, detail="资料持久化写入失败，请稍后重试") from exc

        rel_path = str(final_path.relative_to(UPLOAD_ROOT)).replace("\\", "/")
        file_id = _compute_compat_file_id(pid, rel_path)
        sha256_hex = sha256_hasher.hexdigest()

        # 持久化上传资料元数据
        upsert_mobile_upload({
            "file_id": file_id,
            "storage_uuid": storage_uuid,
            "project_id": pid,
            "original_filename": orig_filename,
            "stored_rel_path": rel_path,
            "media_category": media_category,
            "mime_type": canonical_mime,
            "file_size": total_size,
            "sha256_hash": sha256_hex,
            "remark": clean_remark,
            "uploader_id": user["id"],
            "uploader_name": user.get("username") or user.get("login_name") or "用户",
            "upload_source": "mobile",
            "created_at": now_iso,
        })

        # 初始化任务追踪状态并投递异步多模态分析
        update_file_status(pid, file_id, "pending", chunks=0, filename=orig_filename)

        from worker import process_document
        if media_category in ("video", "audio") or total_size > 2 * _MB:
            process_document.apply_async(
                args=[str(final_path), file_id, orig_filename, pid],
                queue="slow_queue",
            )
        else:
            process_document.delay(str(final_path), file_id, orig_filename, pid)

        uploaded_results.append({
            "file_id": file_id,
            "project_id": pid,
            "project_name": project_info.get("name", ""),
            "filename": orig_filename,
            "sub_folder": clean_folder,
            "media_category": media_category,
            "mime_type": canonical_mime,
            "size": total_size,
            "sha256": sha256_hex,
            "remark": clean_remark,
            "ingest_status": "pending",
            "status_label": _status_label("pending"),
            "created_at": now_iso,
        })

    # 失效相关缓存并记录审计日志
    try:
        from core.precompute import invalidate_draft_cache
        from core.chat_cache import invalidate_chat_cache
        invalidate_draft_cache(pid)
        invalidate_chat_cache(pid)
    except Exception:
        pass

    sample_names = ", ".join(item["filename"] for item in uploaded_results[:3])
    more_tag = f" 等{len(uploaded_results)}份资料" if len(uploaded_results) > 3 else ""
    log_operation(
        user["id"],
        "mobile_upload",
        f"手机端上传资料：{sample_names}{more_tag}（项目：{project_info.get('name', pid)}）",
    )

    resp = JSONResponse(
        content={
            "message": f"已成功上传 {len(uploaded_results)} 份资料至项目「{project_info.get('name', pid)}」并启动后台智能分析",
            "project_id": pid,
            "project_name": project_info.get("name", ""),
            "files": uploaded_results,
        }
    )
    return _apply_security_headers(resp)


# ═══════════════════════════════════════════════════════════════
# 3. 按项目查询资料库列表及智能分析状态（手机端 & 后台管理通用）
# ═══════════════════════════════════════════════════════════════

@router.get("/projects/{project_id}/materials")
async def list_project_materials(
    project_id: str,
    response: Response,
    media_category: str = Query("all", description="筛选类型：all / image / video / audio / document"),
    source: str = Query("all", description="筛选来源：all / mobile / web"),
    q: str = Query("", max_length=100, description="按文件名或备注关键词检索"),
    user: dict = Depends(_rate_limit_read),
):
    """
    根据项目 ID 获取对应资料库内的全部上传资料、媒体分类及多模态入库分析进度。
    """
    _apply_security_headers(response)
    pid = _validate_project_id(project_id)
    project_info = require_project_access(pid, user, write=False)

    try:
        all_materials = await asyncio.wait_for(
            asyncio.to_thread(_scan_project_materials_sync, pid),
            timeout=15.0,
        )
    except asyncio.TimeoutError:
        logger.warning("扫描项目资料库超时: project=%s", pid)
        all_materials = []

    summary = _summarize_materials(all_materials)

    filtered = all_materials
    if media_category != "all":
        filtered = [m for m in filtered if m["media_category"] == media_category]
    if source != "all":
        filtered = [m for m in filtered if m["upload_source"] == source]
    keyword = (q or "").strip().lower()
    if keyword:
        filtered = [
            m for m in filtered
            if keyword in m["filename"].lower()
            or keyword in (m.get("remark") or "").lower()
            or keyword in (m.get("analysis_preview") or "").lower()
        ]

    can_write = user.get("role") == "admin" or project_info.get("owner_id") == user["id"]

    return {
        "project": {
            "id": pid,
            "name": project_info.get("name", ""),
            "icon": project_info.get("icon") or ("📚" if project_info.get("project_type") == "library" else "⚖️"),
            "project_type": project_info.get("project_type", "case"),
            "visibility": project_info.get("visibility", "public"),
            "owner_name": project_info.get("owner_name", ""),
            "can_write": can_write,
        },
        "summary": summary,
        "materials": filtered,
    }


# ═══════════════════════════════════════════════════════════════
# 4. 查看单份资料的完整 AI 分析提取文本与向量切片
# ═══════════════════════════════════════════════════════════════

def _locate_material_by_id(project_id: str, file_id: str) -> tuple[Path, dict]:
    """在指定项目目录内安全定位 file_id 对应的物理文件与元数据。"""
    mu = get_mobile_upload(file_id, project_id)
    project_dir = _safe_resolve_within(UPLOAD_ROOT, project_id)

    if mu and mu.get("stored_rel_path"):
        rel = mu["stored_rel_path"]
        if rel.startswith(f"{project_id}/"):
            sub_rel = rel[len(project_id) + 1 :]
            target = _safe_resolve_within(project_dir, sub_rel)
            if target.is_file():
                return target, mu

    # 兼容桌面端上传的无 mobile_uploads 记录文件：扫描当前项目目录匹配 file_id
    if project_dir.exists():
        for root, dirs, files in os.walk(str(project_dir)):
            dirs[:] = [d for d in dirs if not d.startswith(".")]
            for fname in files:
                if fname.startswith(".") or fname.endswith(".lock"):
                    continue
                candidate = (Path(root) / fname).resolve()
                if not str(candidate).startswith(str(project_dir) + os.sep):
                    continue
                rel_path = str(candidate.relative_to(UPLOAD_ROOT)).replace("\\", "/")
                if _compute_compat_file_id(project_id, rel_path) == file_id:
                    cat, mime = _infer_category_from_filename(fname)
                    return candidate, {
                        "file_id": file_id,
                        "project_id": project_id,
                        "original_filename": fname,
                        "stored_rel_path": rel_path,
                        "media_category": cat,
                        "mime_type": mime,
                        "remark": "",
                        "uploader_name": "",
                        "upload_source": "web",
                    }

    raise HTTPException(status_code=404, detail="未找到指定资料文件")


@router.get("/projects/{project_id}/materials/{file_id}/analysis")
async def get_material_analysis_detail(
    project_id: str,
    file_id: str,
    response: Response,
    user: dict = Depends(_rate_limit_read),
):
    """
    获取单份上传资料的多模态提取文本与知识库切片详情。
    """
    _apply_security_headers(response)
    pid = _validate_project_id(project_id)
    fid = _validate_file_id(file_id)
    require_project_access(pid, user, write=False)

    target_path, meta = await asyncio.to_thread(_locate_material_by_id, pid, fid)
    st_data = get_file_status(pid, fid)
    status_code = st_data.get("status")
    chunks_count = st_data.get("chunks", 0)
    if not status_code:
        chunks_count = get_chunk_count(fid)
        status_code = "vectorized" if chunks_count > 0 else "pending"

    chunks_list = get_fts_chunks_by_file_id(fid)
    extracted_text = "\n\n".join(c["document"] for c in chunks_list) if chunks_list else ""

    # 乱码智能检测
    from core.extractors.ocr_cleaner import is_garbled_text
    is_garbled_flag, garbled_desc = is_garbled_text(extracted_text)

    # 读取 RAG 规范检测结构化报告
    comp_report_raw = meta.get("compliance_report") or st_data.get("compliance_report")
    compliance_report = None
    if comp_report_raw:
        if isinstance(comp_report_raw, dict):
            compliance_report = comp_report_raw
        elif isinstance(comp_report_raw, str):
            try:
                compliance_report = json.loads(comp_report_raw)
            except Exception:
                compliance_report = None

    comp_status = meta.get("compliance_status") or st_data.get("compliance_status", "")
    comp_score = meta.get("compliance_score") if meta.get("compliance_score") is not None else st_data.get("compliance_score", 0)
    comp_checked_at = meta.get("compliance_checked_at") or st_data.get("compliance_checked_at", "")

    return {
        "file_id": fid,
        "project_id": pid,
        "filename": meta.get("original_filename") or target_path.name,
        "media_category": meta.get("media_category", "document"),
        "mime_type": meta.get("mime_type", "application/octet-stream"),
        "size": target_path.stat().st_size,
        "upload_source": meta.get("upload_source", "web"),
        "remark": meta.get("remark", ""),
        "uploader_name": meta.get("uploader_name", ""),
        "created_at": meta.get("created_at", ""),
        "ingest_status": status_code,
        "status_label": _status_label(status_code),
        "chunks_count": max(chunks_count, len(chunks_list)),
        "error_message": st_data.get("error_message", ""),
        "updated_at": st_data.get("updated_at", ""),
        "extracted_text": extracted_text,
        "is_garbled": is_garbled_flag,
        "garbled_reason": garbled_desc,
        "compliance_status": comp_status,
        "compliance_score": comp_score,
        "compliance_report": compliance_report,
        "compliance_checked_at": comp_checked_at,
        "chunks": [
            {"chunk_index": c.get("chunk_index", idx), "content": c.get("document", "")}
            for idx, c in enumerate(chunks_list)
        ],
    }


# ═══════════════════════════════════════════════════════════════
# 5. 安全受控媒体读取/下载流接口（带 nosniff 与 attachment 头）
# ═══════════════════════════════════════════════════════════════

@router.get("/projects/{project_id}/materials/{file_id}/media")
async def stream_material_media(
    project_id: str,
    file_id: str,
    user: dict = Depends(_rate_limit_read),
):
    """
    安全受控地向已授权客户端返回资料原始二进制流（支持前端受控 Blob 预览与原件下载）。
    强制携带 Content-Disposition: attachment 与 X-Content-Type-Options: nosniff 防止浏览器直接执行活跃内容。
    """
    pid = _validate_project_id(project_id)
    fid = _validate_file_id(file_id)
    require_project_access(pid, user, write=False)

    target_path, meta = await asyncio.to_thread(_locate_material_by_id, pid, fid)
    display_name = _sanitize_display_filename(meta.get("original_filename") or target_path.name)
    _, safe_mime = _infer_category_from_filename(display_name)
    encoded_name = quote(display_name)

    headers = {
        "Content-Disposition": f"attachment; filename*=UTF-8''{encoded_name}",
        "X-Content-Type-Options": "nosniff",
        "X-Frame-Options": "DENY",
        "Cache-Control": "private, no-store",
    }
    return FileResponse(
        path=str(target_path),
        media_type=safe_mime,
        headers=headers,
    )


# ═══════════════════════════════════════════════════════════════
# 6. 重新触发资料多模态分析 & 安全删除资料
# ═══════════════════════════════════════════════════════════════

@router.post("/projects/{project_id}/materials/{file_id}/reanalyze")
async def reanalyze_material(
    project_id: str,
    file_id: str,
    response: Response,
    user: dict = Depends(_rate_limit_write),
):
    """重新投递单份资料至后台多模态提取与向量入库队列。"""
    _apply_security_headers(response)
    pid = _validate_project_id(project_id)
    fid = _validate_file_id(file_id)
    require_project_access(pid, user, write=True)

    target_path, meta = await asyncio.to_thread(_locate_material_by_id, pid, fid)
    display_name = meta.get("original_filename") or target_path.name
    media_cat = meta.get("media_category", "document")
    file_size = target_path.stat().st_size

    update_file_status(pid, fid, "pending", chunks=0, filename=display_name)
    from worker import process_document
    if media_cat in ("video", "audio") or file_size > 2 * _MB:
        process_document.apply_async(
            args=[str(target_path), fid, display_name, pid],
            queue="slow_queue",
        )
    else:
        process_document.delay(str(target_path), fid, display_name, pid)

    log_operation(user["id"], "material_reanalyze", f"重新分析资料：{display_name}（项目={pid}）")
    return {
        "message": f"已重新提交《{display_name}》至智能分析队列",
        "file_id": fid,
        "ingest_status": "pending",
        "status_label": _status_label("pending"),
    }


@router.post("/projects/{project_id}/materials/{file_id}/compliance-check")
async def trigger_material_compliance_check(
    project_id: str,
    file_id: str,
    response: Response,
    user: dict = Depends(_rate_limit_write),
):
    """手动重新触发指定图片或视频的 RAG 规范合规检测。"""
    _apply_security_headers(response)
    pid = _validate_project_id(project_id)
    fid = _validate_file_id(file_id)
    require_project_access(pid, user, write=True)

    target_path, meta = await asyncio.to_thread(_locate_material_by_id, pid, fid)
    display_name = meta.get("original_filename") or target_path.name
    media_cat = meta.get("media_category", "image")

    # 获取已有的解析文本作为 RAG 审查依据
    chunks_list = get_fts_chunks_by_file_id(fid)
    extracted_text = "\n\n".join(c["document"] for c in chunks_list) if chunks_list else ""
    remark = meta.get("remark", "")

    from core.rag_compliance import run_rag_compliance_check
    report = await asyncio.to_thread(
        run_rag_compliance_check,
        str(target_path),
        fid,
        display_name,
        pid,
        media_cat,
        extracted_text,
        remark,
    )

    log_operation(user["id"], "material_compliance_check", f"RAG规范检测资料：{display_name}（项目={pid}，状态={report.get('compliance_status')}）")
    return {
        "message": f"已完成《{display_name}》的 RAG 规范检测",
        "file_id": fid,
        "compliance_status": report.get("compliance_status"),
        "compliance_label": report.get("compliance_label"),
        "compliance_score": report.get("compliance_score"),
        "report": report,
    }


@router.delete("/projects/{project_id}/materials/{file_id}")
async def delete_material(
    project_id: str,
    file_id: str,
    response: Response,
    user: dict = Depends(_rate_limit_write),
):
    """安全删除指定项目下的单份资料，并同步清理向量库、FTS 索引、表格注册及元数据。"""
    _apply_security_headers(response)
    pid = _validate_project_id(project_id)
    fid = _validate_file_id(file_id)
    require_project_access(pid, user, write=True)

    target_path, meta = await asyncio.to_thread(_locate_material_by_id, pid, fid)
    display_name = meta.get("original_filename") or target_path.name

    from core.table_registry import delete_tables
    from core.vector_store import delete_by_file_id

    target_path.unlink(missing_ok=True)
    removed_chunks = delete_by_file_id(fid)
    delete_tables(fid, pid)
    delete_mobile_upload(fid, pid)

    # 同步删除本地状态追踪文件
    try:
        status_file = _safe_resolve_within(UPLOAD_ROOT, f"{pid}/.job_states/{fid}.json")
        status_file.unlink(missing_ok=True)
    except Exception:
        pass

    try:
        from core.chat_cache import invalidate_chat_cache
        from core.precompute import invalidate_draft_cache
        invalidate_draft_cache(pid)
        invalidate_chat_cache(pid)
    except Exception:
        pass

    log_operation(user["id"], "material_delete", f"删除项目资料：{display_name}（项目={pid}）")
    return {
        "message": f"已删除资料《{display_name}》",
        "file_id": fid,
        "removed_chunks": removed_chunks,
    }


# ═══════════════════════════════════════════════════════════════
# 7. 后台管理：全项目资料库汇总看板接口（仅管理员）
# ═══════════════════════════════════════════════════════════════

@router.get("/admin/overview")
async def admin_materials_overview(
    response: Response,
    admin: dict = Depends(require_admin),
):
    """
    供后台管理「项目资料库」页面按项目总览所有项目的图片、视频、音频、文档与分析完成度。
    """
    _apply_security_headers(response)
    _limiter.check(f"admin_overview:{admin['id']}", limit=60, window_seconds=60)

    with get_db() as conn:
        rows = conn.execute(
            """SELECT p.*, COALESCE(u.username, p.owner_name, '系统') AS resolved_owner
               FROM projects p
               LEFT JOIN users u ON p.owner_id = u.id
               ORDER BY p.sort_order ASC, p.created_at DESC"""
        ).fetchall()

    def _build_overview() -> list[dict]:
        global_counts, _ = get_fts_summary_map(None, include_preview=False)
        items: list[dict] = []
        for r in rows:
            p = dict(r)
            pid = p["id"]
            if not _PROJECT_ID_RE.match(pid):
                continue
            mats = _scan_project_materials_sync(pid, include_preview=False, preloaded_counts=global_counts)
            stats = _summarize_materials(mats)
            items.append({
                "id": pid,
                "name": p.get("name", ""),
                "icon": p.get("icon") or ("📚" if p.get("project_type") == "library" else "⚖️"),
                "project_type": p.get("project_type", "case"),
                "visibility": p.get("visibility", "public"),
                "owner_name": p.get("resolved_owner", "系统"),
                "created_at": p.get("created_at", ""),
                "stats": stats,
            })
        return items

    project_items = await asyncio.to_thread(_build_overview)
    totals = {
        "project_count": len(project_items),
        "total_materials": sum(x["stats"]["total"] for x in project_items),
        "total_images": sum(x["stats"]["image_count"] for x in project_items),
        "total_videos": sum(x["stats"]["video_count"] for x in project_items),
        "total_audios": sum(x["stats"]["audio_count"] for x in project_items),
        "total_documents": sum(x["stats"]["document_count"] for x in project_items),
        "total_mobile": sum(x["stats"]["mobile_count"] for x in project_items),
        "total_analyzed": sum(x["stats"]["analyzed_count"] for x in project_items),
    }

    return {
        "totals": totals,
        "projects": project_items,
    }


# ═══════════════════════════════════════════════════════════════
# 8. 移动端 /m2 现场检查 Demo 专用轻量拍照上传与媒体获取接口
# ═══════════════════════════════════════════════════════════════

_DEMO_INSPECT_DIR = UPLOAD_ROOT / "demo_inspections"
try:
    _DEMO_INSPECT_DIR.mkdir(parents=True, exist_ok=True)
except Exception as e:
    logger.warning("创建 demo_inspections 目录失败: %s", e)

_DEMO_FILENAME_RE = re.compile(r"^[a-zA-Z0-9_-]{1,64}\.(jpg|jpeg|png|webp|heic)$", re.IGNORECASE)


@router.post("/demo-inspect-upload")
async def upload_demo_inspect_photo(
    file: UploadFile = File(..., description="现场拍摄或上传的检查照片"),
    item_no: str = Form(default="", description="检查要点编号，如 *1.1"),
    request: Request = None,
):
    """
    /m2 现场监督检查 Demo 专用拍照上传接口：
    1. 校验图片类型与文件头 Magic Bytes；
    2. 使用随机 UUID 命名并设置 0o600 权限保存在 demo_inspections 目录；
    3. 返回可供手机端预览的受控静态媒体路径。
    """
    client_ip = request.client.host if request and request.client else "demo_client"
    _limiter.check(f"demo_upload:{client_ip}", limit=120, window_seconds=60)

    orig_filename = _sanitize_display_filename(file.filename or "photo.jpg")
    ext = Path(orig_filename).suffix.lower()
    if ext not in (".jpg", ".jpeg", ".png", ".webp", ".heic"):
        raise HTTPException(status_code=400, detail="仅支持上传 JPG、PNG、WEBP 或 HEIC 格式现场照片")

    # 读取首块并校验 Magic Bytes
    first_chunk = await file.read(64 * 1024)
    if not first_chunk:
        raise HTTPException(status_code=400, detail="上传照片内容为空")
    if not _verify_magic_bytes(ext, first_chunk[:64]):
        raise HTTPException(status_code=400, detail="照片内容格式校验失败，请上传真实图片文件")

    storage_uuid = uuid.uuid4().hex
    stored_name = f"{storage_uuid}{ext}"
    target_path = _safe_resolve_within(_DEMO_INSPECT_DIR, stored_name)

    total_size = len(first_chunk)
    max_bytes = 25 * _MB
    if total_size > max_bytes:
        raise HTTPException(status_code=413, detail="现场照片超过单张 25MB 大小限制")

    temp_path = _safe_resolve_within(_DEMO_INSPECT_DIR, f".tmp_{storage_uuid}{ext}")
    try:
        with open(temp_path, "wb") as out_f:
            out_f.write(first_chunk)
            while True:
                chunk = await file.read(1024 * 1024)
                if not chunk:
                    break
                total_size += len(chunk)
                if total_size > max_bytes:
                    raise HTTPException(status_code=413, detail="现场照片超过单张 25MB 大小限制")
                out_f.write(chunk)

        os.chmod(temp_path, 0o600)
        os.replace(temp_path, target_path)
    except HTTPException:
        if temp_path.exists():
            temp_path.unlink(missing_ok=True)
        raise
    except Exception as exc:
        if temp_path.exists():
            temp_path.unlink(missing_ok=True)
        logger.error("保存 Demo 现场照片异常: %s", exc)
        raise HTTPException(status_code=500, detail="现场照片保存失败，请重试") from exc

    return JSONResponse(
        content={
            "success": True,
            "item_no": item_no,
            "filename": orig_filename,
            "stored_filename": stored_name,
            "url": f"/api/mobile/demo-inspect-media/{stored_name}",
            "size": total_size,
        },
        headers={
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "no-store",
        },
    )


@router.api_route("/demo-inspect-media/{filename}", methods=["GET", "HEAD"])
async def get_demo_inspect_media(filename: str):
    """
    受控流式读取 Demo 现场照片，附带安全标头防范 XSS 与嗅探。
    """
    if not _DEMO_FILENAME_RE.match(filename):
        raise HTTPException(status_code=400, detail="非法的照片文件名格式")

    target_path = _safe_resolve_within(_DEMO_INSPECT_DIR, filename)
    if not target_path.is_file():
        raise HTTPException(status_code=404, detail="未找到该现场照片")

    ext = target_path.suffix.lower()
    mime_type = "image/jpeg"
    if ext == ".png":
        mime_type = "image/png"
    elif ext == ".webp":
        mime_type = "image/webp"

    return FileResponse(
        path=str(target_path),
        media_type=mime_type,
        headers={
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "public, max-age=86400",
        },
    )


_DOWNLOADS_DIR = Path(__file__).resolve().parent.parent / "downloads"


@router.api_route("/download-project-archive", methods=["GET", "HEAD"])
async def download_project_archive(kind: str = Query("code", pattern="^(code|full)$")):
    """
    提供项目打包文件供下载到本地。
    kind="code": 纯源码与配置文件包 (~42MB，不含大模型与大型法规PDF库，推荐快速同步)
    kind="full": 包含全量法规库与源码打包文件 (~4.5GB)
    """
    filename = "sc_code_only.tar.gz" if kind == "code" else "sc_source_code.tar.gz"
    target_path = (_DOWNLOADS_DIR / filename).resolve()
    if not target_path.is_file() or not str(target_path).startswith(str(_DOWNLOADS_DIR.resolve())):
        raise HTTPException(status_code=404, detail="打包文件不存在")

    return FileResponse(
        path=str(target_path),
        filename=filename,
        media_type="application/gzip",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "X-Content-Type-Options": "nosniff",
        },
    )



