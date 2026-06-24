"""
文件上传与持久化存储路由。
WHY: 用户上传的工程文件需要以原始目录层级结构保存在服务器上，
     便于后续 LlamaIndex 管道按文件 ID 精确定位和索引。
"""
from __future__ import annotations
import os
import hashlib
import uuid
from datetime import datetime
from pathlib import Path

from typing import List

from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Query, BackgroundTasks, Depends
from fastapi.responses import JSONResponse, FileResponse, StreamingResponse
from pydantic import BaseModel
import zipfile
import io

from core.config import settings
from core.extractors import extract_text, extract_tables
from core.vector_store import ingest_text, get_chunk_count
from core.table_registry import register_tables
from core.auth_deps import get_current_user
from core.project_access import require_project_access
from core.status_tracker import get_file_status

import logging
logger = logging.getLogger(__name__)

def bg_process_document(file_path: str, file_id: str, filename: str, project_id: str):
    """
    后台文本提取与向量化任务。
    WHY: 解析复杂 GIS 文件或执行 OCR 耗时较长（10s-120s），必须异步执行以防前端超时。
    """
    try:
        import time
        start_time = time.time()
        
        path = Path(file_path)
        if not path.exists():
            logger.error(f"后台解析失败: 文件不存在 - {file_path}")
            return

        logger.info(f"正在后台解析文件: {filename} ({path.stat().st_size / 1024 / 1024:.2f} MB)")
        
        text = extract_text(file_path)
        if not text or not text.strip():
            logger.warning(f"后台解析完成但未提取到有效文本，写入占位文本: {filename}")
            text = "（此文件暂无可用文本或完全由图片构成，不支持深度提取）"
        
        chunks = ingest_text(text, file_id, filename, project_id)

        # WHY: 同步提取完整表格并注册到表格注册表，
        #      使报告生成时可以按标题语义匹配后直接原样注入。
        try:
            tables = extract_tables(file_path)
            if tables:
                registered = register_tables(tables, file_id, filename, project_id)
                logger.info(f"表格注册完成: {filename}, {registered} 张表格")
        except Exception as te:
            logger.warning(f"表格提取/注册失败(非致命): {filename}, {te}")

        duration = time.time() - start_time
        logger.info(f"后台入库成功: {filename}, {chunks} 块, 耗时 {duration:.2f}s")
    except Exception as e:
        logger.error(f"后台入库异常: {filename}, 错误类型: {type(e).__name__}, 详细信息: {str(e)}")

router = APIRouter(prefix="/api/files", tags=["文件管理"])

# WHY: 确保上传根目录存在。如果 RAID 卷不可用（未挂载/无权限），降级到本地 uploads/ 目录
UPLOAD_ROOT = Path(settings.UPLOAD_DIR)
try:
    UPLOAD_ROOT.mkdir(parents=True, exist_ok=True)
except (PermissionError, OSError) as exc:
    logger.warning(f"RAID 上传目录不可用（{exc}），降级到本地 uploads/ 目录")
    UPLOAD_ROOT = Path("uploads")
    UPLOAD_ROOT.mkdir(parents=True, exist_ok=True)


def _safe_resolve(base: Path, user_path: str) -> Path:
    """
    校验用户输入路径不会穿越到基准目录之外。
    WHY: 防止攻击者通过 ../../etc/passwd 等相对路径读取或删除系统文件。
         使用 resolve() 将符号链接和 .. 展开为绝对路径后，与基准目录比较。
    """
    resolved = (base / user_path).resolve()
    if not str(resolved).startswith(str(base.resolve())):
        raise HTTPException(status_code=403, detail="非法路径：禁止访问基准目录之外的文件")
    return resolved


@router.post("/upload")
async def upload_files(
    background_tasks: BackgroundTasks,
    files: List[UploadFile] = File(...),
    project_id: str = Form(default="default"),
    relative_path: str = Form(default=""),
    user: dict = Depends(get_current_user),
):
    """
    接收前端上传的多个文件，按 project_id/relative_path 目录层级持久化保存。
    保存后自动触发文本提取与向量化入库。
    WHY: 上传是写操作，仅 Owner/Admin 可执行。
    """
    require_project_access(project_id, user, write=True)
    saved = []

    for file in files:
        # 🔗 增强版文件名清洗：保留中文字符、字母、数字、点、横杠和下划线，剔除括号和空格等可能导致路径问题的特殊符号
        import re
        # 原名: (510921)蓬溪县分布图.jpg -> 510921蓬溪县分布图.jpg
        # 这里为了兼容性，将非中英文数字字符替换为下划线
        raw_filename = file.filename.replace("\\", "/").split("/")[-1]
        safe_filename = re.sub(r'[^\w\u4e00-\u9fa5.-]', '_', raw_filename)
        # 避免连续下划线
        safe_filename = re.sub(r'_{2,}', '_', safe_filename)

        # 构建持久化目标路径：uploads/{project_id}/{relative_path}/{filename}
        target_dir = UPLOAD_ROOT / project_id / relative_path
        target_dir.mkdir(parents=True, exist_ok=True)

        target_path = target_dir / safe_filename
        
        # 同名文件自动追加时间戳避免覆盖
        if target_path.exists():
            stem = target_path.stem
            suffix = target_path.suffix
            from datetime import timezone, timedelta
            timestamp = datetime.now(timezone(timedelta(hours=8))).strftime("%Y%m%d%H%M%S")
            target_path = target_dir / f"{stem}_{timestamp}{suffix}"

        # WHY: 流式分块写入磁盘，避免大文件（如 250MB+ 的 .shp/.dbf）一次性撑爆内存
        CHUNK_SIZE = 8 * 1024 * 1024  # 8MB 分块
        file_size = 0
        try:
            with open(target_path, "wb") as f:
                while True:
                    chunk = await file.read(CHUNK_SIZE)
                    if not chunk:
                        break
                    f.write(chunk)
                    file_size += len(chunk)
        except Exception as e:
            # 写入失败时清理残留文件
            if target_path.exists():
                target_path.unlink()
            raise HTTPException(status_code=500, detail=f"文件保存失败: {str(e)}")

        rel_path = str(target_path.relative_to(UPLOAD_ROOT))
        # WHY: 将文件 ID 从随机 UUID 改为由项目前缀+相对路径决定的强散列（MD5）。
        # 这使得无论后台怎么重启，只要源文件在这个位置，它的 ID 就是幂等且唯一的。
        file_id = hashlib.md5(f"{project_id}_{rel_path}".encode("utf-8")).hexdigest()

        SUPPORTED_EXTS = {
            ".txt", ".md", ".csv", ".log", ".json", ".xml", ".html", ".htm",
            ".pdf", ".doc", ".docx", ".xlsx", ".xls", ".pptx", ".caj",
            ".dwg", ".dxf", ".shp", ".dbf", ".gdb", ".mdb",
            ".jpg", ".jpeg", ".png", ".bmp", ".tiff", ".tif", ".webp",
            ".mp3", ".wav", ".mp4", ".mov"
        }

        # 防御机制：PyMuPDF 底层 C 引擎对大文件免疫 OOM，阈值放宽至 1.5GB
        MAX_INGEST_SIZE = int(1.5 * 1024 * 1024 * 1024)  # 1.5GB
        if file_size > MAX_INGEST_SIZE:
            cur_ingest_status = "too_large"
        elif target_path.suffix.lower() not in SUPPORTED_EXTS:
            cur_ingest_status = "unsupported_format"
        else:
            cur_ingest_status = "pending"
            # WHY: 将重负载的（加载 BGE 模型，推理几千 chunks）操作彻底移交给外置的 Celery 进程
            # 避免它在 uvicorn 进程的背景线程中执行时，挤死主线程导致 HTTP 超时。
            from worker import process_document
            # WHY: 对于大概率超过 chunks 阈值的大文件（>2MB 或 >1MB 的 Excel），
            #      直接路由到 slow_queue，避免在 fast worker 上浪费一次预估+重路由。
            if file_size > 2 * 1024 * 1024:
                process_document.apply_async(
                    args=[str(target_path), file_id, safe_filename, project_id],
                    queue='slow_queue'
                )
            elif file_size > 1 * 1024 * 1024 and target_path.suffix.lower() in ('.xlsx', '.xls'):
                process_document.apply_async(
                    args=[str(target_path), file_id, safe_filename, project_id],
                    queue='slow_queue'
                )
            else:
                process_document.delay(str(target_path), file_id, safe_filename, project_id)

        # WHY: 保证上传即刻响应，后台挂载解析。
        saved.append({
            "id": file_id,
            "filename": safe_filename,
            "size": file_size,
            "path": rel_path,
            "content_type": file.content_type,
            "ingest_status": cur_ingest_status,  # 告知前端已在后台排队，或因过大而跳过
            "chunks": 0,
        })

    # WHY: 入库文件变更后，预计算缓存可能已过期，自动清除
    from core.precompute import invalidate_draft_cache
    invalidate_draft_cache(project_id)
    # WHY: 文档变更后 Chat 缓存可能基于旧的检索结果，必须清除
    from core.chat_cache import invalidate_chat_cache
    invalidate_chat_cache(project_id)

    # WHY: 记录文件上传操作到审计日志，供管理员追踪用户行为
    from core.audit_log import log_operation
    filenames = ', '.join(f['filename'] for f in saved[:3])
    suffix = f' 等{len(saved)}个文件' if len(saved) > 3 else ''
    log_operation(user["id"], "file_upload", f"上传文件：{filenames}{suffix}（项目={project_id[:8]}）")

    return JSONResponse(content={
        "message": f"成功持久化 {len(saved)} 个文件",
        "files": saved,
    })


@router.get("/list")
async def list_files(project_id: str = "default", user: dict = Depends(get_current_user)):
    """
    递归遍历指定项目下的所有文件。
    特殊处理：将 .gdb 文件夹视为单个"文件"实体，隐藏其内部的二进制琐碎文件。
    WHY: 读操作，公开项目允许所有登录用户查看。
    WHY: os.walk / stat 是同步阻塞 I/O，在 NFS 挂载场景下可能因中文目录名或网络波动
         导致无限阻塞，卡死 uvicorn 事件循环。通过 asyncio.to_thread + wait_for 超时保护。
    """
    import asyncio

    require_project_access(project_id, user, write=False)
    project_dir = UPLOAD_ROOT / project_id
    if not project_dir.exists():
        return {"project_id": project_id, "files": []}

    def _scan_project_dir() -> list[dict]:
        """同步文件扫描逻辑，在线程池中执行以避免阻塞事件循环"""
        result = []
        import os
        for root, dirs, files in os.walk(str(project_dir)):
            dirs[:] = [d for d in dirs if not d.startswith('.')]
            root_path = Path(root)

            if ".gdb" in root_path.suffixes or any(p.suffix.lower() == ".gdb" for p in root_path.parents):
                continue

            for d in dirs:
                if d.lower().endswith(".gdb"):
                    gdb_path = root_path / d
                    rel_path = str(gdb_path.relative_to(UPLOAD_ROOT))
                    file_id = hashlib.md5(f"{project_id}_{rel_path}".encode("utf-8")).hexdigest()
                    try:
                        total_size = sum(f.stat().st_size for f in gdb_path.rglob("*") if f.is_file())
                        status_data = get_file_status(project_id, file_id)
                        ingest_status = status_data.get("status")
                        if not ingest_status:
                            ingest_status = "vectorized" if get_chunk_count(file_id) > 0 else "pending"
                        result.append({
                            "id": file_id, "filename": d, "path": rel_path,
                            "size": total_size, "is_folder": False,
                            "modified": datetime.fromtimestamp(gdb_path.stat().st_mtime).isoformat(),
                            "ingest_status": ingest_status,
                        })
                    except OSError:
                        pass

            SHP_COMPANION_EXTS = {'.shx', '.dbf', '.prj', '.sbn', '.sbx', '.cpg', '.qix', '.fix', '.atx', '.mta'}
            shp_basenames = set()
            for f in files:
                if f.lower().endswith('.shp') and not f.lower().endswith('.shp.xml'):
                    shp_basenames.add(Path(f).stem)

            shp_entries: dict[str, dict] = {}

            for f in files:
                if f.startswith(".") or f.endswith(".lock"):
                    continue

                path = root_path / f
                f_lower = f.lower()
                f_stem = Path(f).stem
                f_ext = Path(f).suffix.lower()

                is_shp_companion = False
                if f_stem in shp_basenames:
                    if f_ext in SHP_COMPANION_EXTS:
                        is_shp_companion = True
                    elif f_lower.endswith('.shp.xml'):
                        is_shp_companion = True

                if is_shp_companion:
                    if f_stem not in shp_entries:
                        shp_entries[f_stem] = {"extra_size": 0}
                    try:
                        shp_entries[f_stem]["extra_size"] += path.stat().st_size
                    except OSError:
                        pass
                    continue

                if f_ext == '.shp' and not f_lower.endswith('.shp.xml') and f_stem in shp_basenames:
                    rel_path = str(path.relative_to(UPLOAD_ROOT))
                    file_id = hashlib.md5(f"{project_id}_{rel_path}".encode("utf-8")).hexdigest()
                    try:
                        status_data = get_file_status(project_id, file_id)
                        ingest_status = status_data.get("status")
                        if not ingest_status:
                            ingest_status = "vectorized" if get_chunk_count(file_id) > 0 else "pending"
                        entry = {
                            "id": file_id, "filename": f, "path": rel_path,
                            "size": path.stat().st_size,
                            "modified": datetime.fromtimestamp(path.stat().st_mtime).isoformat(),
                            "is_shapefile_group": True,
                            "ingest_status": ingest_status,
                        }
                        if f_stem not in shp_entries:
                            shp_entries[f_stem] = {"extra_size": 0}
                        shp_entries[f_stem]["entry"] = entry
                    except OSError:
                        pass
                    continue

                rel_path = str(path.relative_to(UPLOAD_ROOT))
                file_id = hashlib.md5(f"{project_id}_{rel_path}".encode("utf-8")).hexdigest()
                try:
                    status_data = get_file_status(project_id, file_id)
                    ingest_status = status_data.get("status")
                    if not ingest_status:
                        ingest_status = "vectorized" if get_chunk_count(file_id) > 0 else "pending"
                    result.append({
                        "id": file_id, "filename": f, "path": rel_path,
                        "size": path.stat().st_size,
                        "modified": datetime.fromtimestamp(path.stat().st_mtime).isoformat(),
                        "ingest_status": ingest_status,
                    })
                except OSError:
                    pass

            for basename, info in shp_entries.items():
                if "entry" in info:
                    info["entry"]["size"] += info["extra_size"]
                    result.append(info["entry"])

        result.sort(key=lambda x: x["path"])
        return result

    # WHY: 15 秒超时保护——NFS 卡死不会拖垮整个 uvicorn 进程
    LIST_TIMEOUT = 15
    try:
        file_list = await asyncio.wait_for(
            asyncio.to_thread(_scan_project_dir),
            timeout=LIST_TIMEOUT,
        )
    except asyncio.TimeoutError:
        logger.warning(f"文件列表扫描超时 ({LIST_TIMEOUT}s)，项目={project_id}，可能 NFS 卡顿")
        file_list = []

    # WHY: 追加网络/粘贴来源，使其与本地文件统一出现在文件树中
    from api.web_ingest import _read_web_sources
    web_sources = _read_web_sources(project_id)
    for ws in web_sources:
        file_list.append({
            "id": ws["id"],
            "filename": ws.get("title", "未命名网络资料"),
            "path": f"__web__/{ws['id']}",
            "size": ws.get("text_length", 0),
            "source_type": ws.get("source_type", "web"),  # web / text
            "source_url": ws.get("url", ""),
            "chunks": ws.get("chunks", 0),
        })

    return {"project_id": project_id, "files": file_list}


@router.delete("/delete")
async def delete_file(file_path: str, project_id: str = "default", user: dict = Depends(get_current_user)):
    """
    删除某个已持久化的文件（或 .gdb 文件夹），并同步清理 ChromaDB 中的向量索引。
    WHY: 删除是写操作，仅 Owner/Admin 可执行。
    """
    require_project_access(project_id, user, write=True)
    import shutil

    target = _safe_resolve(UPLOAD_ROOT, file_path)
    is_gdb_folder = target.is_dir() and target.suffix.lower() == ".gdb"

    if not target.exists() or (not target.is_file() and not is_gdb_folder):
        raise HTTPException(status_code=404, detail="文件不存在")

    from core.vector_store import delete_by_file_id
    from core.table_registry import delete_tables

    if is_gdb_folder:
        # GDB 文件夹：递归清理所有内部文件的向量 + 删除目录
        file_id = hashlib.md5(f"{project_id}_{file_path}".encode("utf-8")).hexdigest()
        removed_chunks = delete_by_file_id(file_id)
        delete_tables(file_id, project_id)
        shutil.rmtree(str(target))
    else:
        # 普通文件
        file_id = hashlib.md5(f"{project_id}_{file_path}".encode("utf-8")).hexdigest()
        target.unlink()
        removed_chunks = delete_by_file_id(file_id)
        delete_tables(file_id, project_id)

    logger.info(f"已删除: {file_path}，清理 {removed_chunks} 个向量切片")

    # WHY: 文件删除后预计算缓存失效
    from core.precompute import invalidate_draft_cache
    invalidate_draft_cache(project_id)
    from core.chat_cache import invalidate_chat_cache
    invalidate_chat_cache(project_id)

    # 记录操作日志
    from core.audit_log import log_operation
    log_operation(user["id"], "file_delete", f"删除文件：{file_path}")

    return {
        "message": f"已删除: {file_path}",
        "file_id": file_id,
        "removed_chunks": removed_chunks,
    }


@router.delete("/delete-folder")
async def delete_folder(folder_path: str, project_id: str = "default", user: dict = Depends(get_current_user)):
    """
    递归删除整个文件夹及其下所有文件，并同步清理 ChromaDB 向量索引。
    WHY: 删除是写操作，仅 Owner/Admin 可执行。
    """
    require_project_access(project_id, user, write=True)
    import shutil

    target = _safe_resolve(UPLOAD_ROOT, folder_path)
    if not target.exists() or not target.is_dir():
        raise HTTPException(status_code=404, detail="文件夹不存在")

    from core.vector_store import delete_by_file_id
    from core.table_registry import delete_tables

    # 1. 遍历文件夹下所有文件，逐个清理向量索引
    removed_files = 0
    removed_chunks = 0
    for file in target.rglob("*"):
        if file.is_file():
            rel_path = str(file.relative_to(UPLOAD_ROOT))
            file_id = hashlib.md5(f"{project_id}_{rel_path}".encode("utf-8")).hexdigest()
            removed_chunks += delete_by_file_id(file_id)
            delete_tables(file_id, project_id)
            removed_files += 1

    # 2. 递归删除整个文件夹
    shutil.rmtree(str(target))

    logger.info(f"已删除文件夹: {folder_path}，共 {removed_files} 个文件，清理 {removed_chunks} 个向量切片")

    # WHY: 文件夹删除后预计算缓存失效
    from core.precompute import invalidate_draft_cache
    invalidate_draft_cache(project_id)
    from core.chat_cache import invalidate_chat_cache
    invalidate_chat_cache(project_id)

    # 记录操作日志
    from core.audit_log import log_operation
    log_operation(user["id"], "folder_delete", f"删除文件夹：{folder_path}（{removed_files} 个文件）")

    return {
        "message": f"已删除文件夹: {folder_path}",
        "removed_files": removed_files,
        "removed_chunks": removed_chunks,
    }


@router.get("/download")
async def download_file(
    file_path: str = Query(..., description="相对于 uploads 根目录的文件路径"),
    as_pdf: bool = Query(False, description="是否将 CAJ 文件转换为 PDF 返回以供预览"),
    user: dict = Depends(get_current_user)
):
    """
    返回指定文件的原始二进制流，供前端 iframe 预览或浏览器下载。
    WHY: 读操作，从 file_path 提取 project_id 进行权限校验。
    """
    # WHY: file_path 格式为 "{project_id}/..."，提取第一段作为 project_id
    path_project_id = file_path.split("/")[0] if "/" in file_path else "default"
    require_project_access(path_project_id, user, write=False)
    target = _safe_resolve(UPLOAD_ROOT, file_path)
    if not target.exists() or not target.is_file():
        raise HTTPException(status_code=404, detail="文件不存在")

    # 如果是 CAJ 格式且请求转换为 PDF 以供预览
    if target.suffix.lower() == ".caj" and as_pdf:
        try:
            # 使用本地磁盘快照缓存，避免重复执行大开销的解壳命令
            cache_dir = target.parent / ".cache"
            cache_dir.mkdir(exist_ok=True)
            cache_pdf = cache_dir / f"{target.stem}.pdf"

            if not cache_pdf.exists() or cache_pdf.stat().st_mtime < target.stat().st_mtime:
                import subprocess
                from pathlib import Path
                # 动态定位 caj2pdf 转换器
                caj2pdf_script = Path(__file__).parents[2] / "caj2pdf" / "caj2pdf"
                if not caj2pdf_script.exists():
                    caj2pdf_script = Path("/app/caj2pdf/caj2pdf")
                
                cmd = ["python3", str(caj2pdf_script), "convert", str(target), "-o", str(cache_pdf)]
                result = subprocess.run(cmd, capture_output=True, text=True, timeout=45)
                if result.returncode != 0 or not cache_pdf.exists() or cache_pdf.stat().st_size == 0:
                    raise RuntimeError(f"caj2pdf 转换失败 (Exit code {result.returncode}). stderr: {result.stderr}")
            
            return FileResponse(
                path=str(cache_pdf),
                filename=f"{target.stem}.pdf",
                media_type="application/pdf"
            )
        except Exception as e:
            logger.error(f"CAJ 实时转换为 PDF 预览失败: {e}，将回退原件流输出")
            pass

    return FileResponse(
        path=str(target),
        filename=target.name,
        media_type=None,  # 让 FastAPI 自动根据扩展名推断 Content-Type
    )

class BatchDownloadRequest(BaseModel):
    project_id: str
    paths: List[str]

@router.post("/download-batch")
async def download_batch(req: BatchDownloadRequest, user: dict = Depends(get_current_user)):
    """
    批量下载多个文件或整个文件夹，将其打包为 ZIP 供前端下载。
    """
    require_project_access(req.project_id, user, write=False)

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for p in req.paths:
            # 确保传递的路径是受限且解析到 uploads 根目录下的
            target = _safe_resolve(UPLOAD_ROOT, p)
            if target.exists():
                if target.is_file():
                    zf.write(target, arcname=target.name)
                elif target.is_dir():
                    # 递归遍历文件夹并保持其内部的目录结构
                    for root, _, files in os.walk(target):
                        for f in files:
                            f_path = Path(root) / f
                            # 在 ZIP 中以所选文件夹为顶层目录，保持相对层级
                            arcname = f_path.relative_to(target.parent)
                            zf.write(f_path, arcname=str(arcname))

    buf.seek(0)
    
    # 获取下载时的默认文件名
    download_filename = "batch_download.zip"
    if len(req.paths) == 1:
        first_target = _safe_resolve(UPLOAD_ROOT, req.paths[0])
        if first_target.is_dir():
            download_filename = f"{first_target.name}.zip"

    # URL编码防止中文乱码
    from urllib.parse import quote
    encoded_filename = quote(download_filename)

    return StreamingResponse(
        buf,
        media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename*=utf-8''{encoded_filename}"}
    )


@router.get("/preview")
async def preview_file_text(file_path: str = Query(..., description="相对于 uploads 根目录的文件路径"), user: dict = Depends(get_current_user)):
    """
    统一文件预览接口：复用 extractors.extract_text() 提取纯文本。
    WHY: 读操作，从 file_path 提取 project_id 进行权限校验。
    """
    path_project_id = file_path.split("/")[0] if "/" in file_path else "default"
    require_project_access(path_project_id, user, write=False)
    target = _safe_resolve(UPLOAD_ROOT, file_path)
    is_gdb_folder = target.is_dir() and target.suffix.lower() == ".gdb"

    if not target.exists() or (not target.is_file() and not is_gdb_folder):
        raise HTTPException(status_code=404, detail="文件不存在")

    ext = target.suffix.lower()

    # 图片类：浏览器 iframe 原生渲染，不走文本提取
    if ext in ('.png', '.jpg', '.jpeg', '.gif', '.webp', '.svg', '.bmp'):
        return {"type": "image", "filename": target.name, "message": "请使用 iframe 预览"}

    # 调用统一提取器
    try:
        text = extract_text(str(target))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"解析失败: {str(e)}")

    if text is None or not text.strip():
        return {"type": "unsupported", "filename": target.name, "message": f"{ext} 格式暂不支持文本预览或文件内容为空"}

    return {"type": "text", "filename": target.name, "content": text}


@router.get("/ingest-status")
async def get_ingest_status(
    file_id: str = Query(..., description="文件 ID（MD5 哈希）"),
    project_id: str = Query(default="default"),
    user: dict = Depends(get_current_user),
):
    """
    轻量级入库状态查询接口。
    WHY: 前端上传完成后需要轮询后台解析进度，
         通过查阅本地记录优先判断空跳过与失败，最后回退检测向量切片。
    """
    require_project_access(project_id, user, write=False)
    
    from core.status_tracker import get_file_status
    local_status = get_file_status(project_id, file_id)
    
    if local_status and local_status.get("status") in ("empty_text", "unsupported_format", "failed", "too_large", "vectorized", "processing"):
        # processing 将被转为 pending 对齐前端，但其他终态会被传递给前端从而打破死等
        status_value = local_status["status"] if local_status["status"] != "processing" else "pending"
        return {
            "file_id": file_id,
            "status": status_value,
            "chunks": local_status.get("chunks", 0),
            "error_message": local_status.get("error_message", "")
        }

    chunks = get_chunk_count(file_id)
    return {
        "file_id": file_id,
        "status": "vectorized" if chunks > 0 else "pending",
        "chunks": chunks,
    }


# ═══════════════════════════════════════════════════════════════
# P1: Shapefile → GeoJSON 预览接口
# WHY: 前端 Leaflet 地图组件需要 GeoJSON 格式才能渲染空间数据。
#      后端用 geopandas 读取 Shapefile 并简化几何体后返回 GeoJSON。
# ═══════════════════════════════════════════════════════════════

@router.get("/preview-geo")
async def preview_geo(
    file_path: str = Query(..., description="Shapefile 相对路径"),
    user: dict = Depends(get_current_user),
):
    """
    将 Shapefile 转为 GeoJSON 返回，供前端 Leaflet 渲染。
    包含几何体简化和缓存机制，避免重复计算。
    """
    import json as json_mod

    path_project_id = file_path.split("/")[0] if "/" in file_path else "default"
    require_project_access(path_project_id, user, write=False)

    target = _safe_resolve(UPLOAD_ROOT, file_path)
    if not target.exists():
        raise HTTPException(status_code=404, detail="文件不存在")

    # WHY: 缓存 GeoJSON 到 .cache 目录，避免每次预览都重新解析
    cache_dir = target.parent / ".cache"
    cache_dir.mkdir(exist_ok=True)
    cache_file = cache_dir / f"{target.stem}.geojson"

    if cache_file.exists() and cache_file.stat().st_mtime > target.stat().st_mtime:
        return JSONResponse(
            content=json_mod.loads(cache_file.read_text(encoding="utf-8")),
            media_type="application/json",
        )

    try:
        import geopandas as gpd

        gdf = gpd.read_file(str(target))

        # WHY: 确保坐标系为 WGS84 (EPSG:4326)，Leaflet 默认使用此坐标系
        if gdf.crs and gdf.crs.to_epsg() != 4326:
            gdf = gdf.to_crs(epsg=4326)

        # WHY: 简化几何体，减少传输的 JSON 体积（tolerance 约为 ~1 米精度）
        gdf["geometry"] = gdf["geometry"].simplify(tolerance=0.00001, preserve_topology=True)

        # 限制最多返回 5000 个要素，防止浏览器卡死
        if len(gdf) > 5000:
            gdf = gdf.head(5000)

        geojson_str = gdf.to_json(ensure_ascii=False)
        # 缓存到磁盘
        cache_file.write_text(geojson_str, encoding="utf-8")

        return JSONResponse(
            content=json_mod.loads(geojson_str),
            media_type="application/json",
        )
    except ImportError:
        raise HTTPException(status_code=500, detail="后端缺少 geopandas 依赖，请安装: pip install geopandas")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Shapefile 解析失败: {str(e)}")


# ═══════════════════════════════════════════════════════════════
# P1: DXF/DWG → SVG 预览接口
# WHY: 前端需要矢量图形来展示 CAD 图纸，SVG 是浏览器原生支持的矢量格式。
#      后端用 ezdxf.addons.drawing 将 DXF 渲染为 SVG 字符串。
# ═══════════════════════════════════════════════════════════════

@router.get("/preview-cad")
async def preview_cad(
    file_path: str = Query(..., description="DXF/DWG 文件相对路径"),
    user: dict = Depends(get_current_user),
):
    """
    将 DXF/DWG 文件渲染为 SVG 字符串返回，供前端 CadViewer 展示。
    包含磁盘缓存，避免重复渲染。
    """
    from fastapi.responses import Response

    path_project_id = file_path.split("/")[0] if "/" in file_path else "default"
    require_project_access(path_project_id, user, write=False)

    target = _safe_resolve(UPLOAD_ROOT, file_path)
    if not target.exists():
        raise HTTPException(status_code=404, detail="文件不存在")

    # 缓存：支持 SVG 和 PNG 两种格式
    cache_dir = target.parent / ".cache"
    cache_dir.mkdir(exist_ok=True)
    cache_file = cache_dir / f"{target.stem}.svg"
    cache_png = cache_dir / f"{target.stem}.png"

    # 优先检查 PNG 缓存（大图纸）
    if cache_png.exists() and cache_png.stat().st_mtime > target.stat().st_mtime:
        return Response(
            content=cache_png.read_bytes(),
            media_type="image/png",
        )
    # 再检查 SVG 缓存（小图纸）
    if cache_file.exists() and cache_file.stat().st_mtime > target.stat().st_mtime:
        return Response(
            content=cache_file.read_text(encoding="utf-8"),
            media_type="image/svg+xml",
        )

    try:
        import ezdxf
        from ezdxf.addons.drawing import Frontend, RenderContext
        import subprocess

        # 处理 DWG 到 DXF 的转换
        process_target = target
        temp_dxf = None
        
        if target.suffix.lower() == ".dwg":
            tool_path = Path(__file__).parent.parent / "tools" / "dwg2dxf"
            if not tool_path.exists():
                raise HTTPException(
                    status_code=500,
                    detail="后端缺少 dwg2dxf 转换工具，请联系管理员配置 libredwg。"
                )
                
            temp_dxf = cache_dir / f"{target.stem}_temp.dxf"
            cmd = [str(tool_path), "-o", str(temp_dxf), str(target)]
            env = os.environ.copy()
            env["DYLD_LIBRARY_PATH"] = str(tool_path.parent)
            
            result = subprocess.run(cmd, capture_output=True, text=True, env=env)
            
            # WHY: dwg2dxf 对于部分复杂的 DWG 经常会因 Warning（如 HATCH 丢失）返回非零退出码，但 DXF 依然成功生成。
            # 改进：我们只检查目标 DXF 是否生成且大小大于 0 来判断成功与否。
            if not temp_dxf.exists() or temp_dxf.stat().st_size == 0:
                raise HTTPException(
                    status_code=500,
                    detail=f"DWG 转换失败，无输出。日志: {result.stderr.strip()[:1000]}"
                )
            process_target = temp_dxf

        try:
            doc = ezdxf.readfile(str(process_target))
        except Exception:
            try:
                doc, _auditor = ezdxf.recover.readfile(str(process_target))
            except Exception as recover_err:
                raise recover_err

        # WHY: dwg2dxf 转换后几乎所有图层都处于关闭/冻结状态，必须强制全部开启
        for layer in doc.layers:
            layer.on()
            layer.thaw()

        msp = doc.modelspace()

        # WHY: 对于复杂 CAD 图纸（数万实体），SVG 可达 60MB+ 浏览器无法承受
        #       策略：先用 SVGBackend 快速渲染，若 SVG > 5MB 则回退 Matplotlib 生成 PNG
        from ezdxf.addons.drawing.svg import SVGBackend
        from ezdxf.addons.drawing import layout as ezdxf_layout
        
        ctx = RenderContext(doc)
        out = SVGBackend()
        Frontend(ctx, out).draw_layout(msp)

        page = ezdxf_layout.Page(0, 0)
        svg_content = out.get_string(page)

        SVG_SIZE_THRESHOLD = 5 * 1024 * 1024  # 5MB

        if len(svg_content) <= SVG_SIZE_THRESHOLD:
            # 小图纸：直接返回 SVG（矢量无损缩放）
            cache_file.write_text(svg_content, encoding="utf-8")
            if temp_dxf and temp_dxf.exists():
                temp_dxf.unlink()
            return Response(content=svg_content, media_type="image/svg+xml")
        else:
            # 大图纸：回退到 Matplotlib 渲染高分辨率 PNG
            import matplotlib
            matplotlib.use("Agg")
            import matplotlib.pyplot as plt
            from ezdxf.addons.drawing.matplotlib import MatplotlibBackend
            import io

            fig = plt.figure(dpi=72)
            ax = fig.add_axes([0, 0, 1, 1])
            ctx2 = RenderContext(doc)
            out2 = MatplotlibBackend(ax)
            Frontend(ctx2, out2).draw_layout(msp)
            out2.finalize()
            ax.autoscale(True)
            ax.set_aspect('equal')
            ax.set_axis_off()

            buf = io.BytesIO()
            fig.savefig(buf, format='png', dpi=200, bbox_inches='tight',
                        pad_inches=0.1, facecolor='white')
            plt.close(fig)
            png_bytes = buf.getvalue()

            # 缓存为 PNG
            cache_png = cache_dir / f"{target.stem}.png"
            cache_png.write_bytes(png_bytes)
            # 删除可能存在的旧 SVG 缓存
            if cache_file.exists():
                cache_file.unlink()

            if temp_dxf and temp_dxf.exists():
                temp_dxf.unlink()
            return Response(content=png_bytes, media_type="image/png")

    except ImportError as ie:
        raise HTTPException(status_code=500, detail=f"后端缺少依赖: {str(ie)}")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"CAD 文件渲染失败: {str(e)}")


# ═══════════════════════════════════════════════════════════════
# MDB/GDB 地理数据库图层浏览接口
# WHY: 用户需要像 ArcGIS Catalog 一样查看数据库内的所有图层和属性表，
#      而不是只看到一个"黑盒"文件。
# 策略: MDB → mdb-tools CLI，GDB → pyogrio/geopandas
# ═══════════════════════════════════════════════════════════════

# 将 extractors.py 中的字段翻译映射复用过来
from core.extractors import _GIS_FIELD_MAP, _GIS_LAYER_MAP

# MDB 系统表黑名单（不显示给用户）
_MDB_SYSTEM_TABLES = {
    "GDB_SpatialRefs", "GDB_GeomColumns", "GDB_Items", "GDB_ColumnInfo",
    "GDB_ItemTypes", "GDB_ItemRelationships", "GDB_ItemRelationshipTypes",
    "GDB_ReplicaLog", "GDB_DatabaseLocks", "Selections", "SelectedObjects",
}


def _translate_field_name(name: str) -> str:
    """将 GIS 拼音缩写字段翻译为中文（用于前端表头显示）。"""
    upper = name.upper().strip()
    if upper in _GIS_FIELD_MAP:
        return f"{name}({_GIS_FIELD_MAP[upper]})"
    return name


def _translate_layer_name(name: str) -> str:
    """将图层名翻译为中文。"""
    upper = name.upper().strip()
    if upper in _GIS_LAYER_MAP:
        return _GIS_LAYER_MAP[upper]
    return ""


def _decode_mdb_bytes(raw: bytes) -> str:
    """智能解码 MDB 导出数据：UTF-8 优先，GBK 兜底。"""
    # WHY: mdb-tools 在 macOS 上输出 UTF-8，但某些旧 MDB 可能包含 GBK 数据
    # 策略：严格尝试 UTF-8 → GBK → 替换模式兜底
    try:
        return raw.decode('utf-8')
    except UnicodeDecodeError:
        pass
    for enc in ('gbk', 'gb18030', 'gb2312'):
        try:
            return raw.decode(enc)
        except (UnicodeDecodeError, LookupError):
            continue
    return raw.decode('utf-8', errors='replace')


def _list_mdb_layers(mdb_path: str) -> list:
    """用 mdb-tools 列出 MDB 内的用户表/图层。"""
    import subprocess

    # 获取全部表名
    result = subprocess.run(
        ["mdb-tables", "-1", mdb_path],
        capture_output=True, text=True, timeout=10,
    )
    if result.returncode != 0:
        raise RuntimeError(f"mdb-tables 失败: {result.stderr}")

    all_tables = [t.strip() for t in result.stdout.strip().split("\n") if t.strip()]

    # 过滤系统表和 Shape_Index 索引表
    user_tables = [
        t for t in all_tables
        if t not in _MDB_SYSTEM_TABLES
        and not t.endswith("_Shape_Index")
    ]

    layers = []
    for table_name in user_tables:
        try:
            # WHY: mdb-export 导出 CSV，取表头得字段名、数行数
            export_result = subprocess.run(
                ["mdb-export", mdb_path, table_name],
                capture_output=True, timeout=15,
            )
            # WHY: 中文 MDB 使用 GBK 编码，优先用 GBK 解码
            csv_text = _decode_mdb_bytes(export_result.stdout)
            lines = csv_text.strip().split("\n")
            header_line = lines[0] if lines else ""
            fields = [f.strip().strip('"') for f in header_line.split(",")][:10]
            row_count = max(0, len(lines) - 1)

            # 判断是否有几何体（检查 GDB_GeomColumns）
            has_geometry = any(
                f.upper() in ("SHAPE", "GEOMETRY", "GEOM") for f in fields
            )

            translated_name = _translate_layer_name(table_name)

            layers.append({
                "name": table_name,
                "display_name": f"{table_name}({translated_name})" if translated_name else table_name,
                "row_count": row_count,
                "has_geometry": has_geometry,
                "fields": [_translate_field_name(f) for f in fields if f],
            })
        except Exception as e:
            layers.append({
                "name": table_name,
                "display_name": table_name,
                "row_count": -1,
                "has_geometry": False,
                "fields": [],
                "error": str(e),
            })

    return layers


def _list_gdb_layers(gdb_path: str) -> list:
    """用 pyogrio 列出 GDB (FileGDB) 内的图层。"""
    import pyogrio

    raw_layers = pyogrio.list_layers(gdb_path)
    layers = []
    for name, geom_type in raw_layers:
        try:
            info = pyogrio.read_info(gdb_path, layer=name)
            fields = list(info.get("fields", []))[:10]
            row_count = info.get("features", 0)
            has_geometry = geom_type is not None and str(geom_type) != "None"
            translated_name = _translate_layer_name(name)
            layers.append({
                "name": name,
                "display_name": f"{name}({translated_name})" if translated_name else name,
                "row_count": row_count,
                "has_geometry": has_geometry,
                "geometry_type": str(geom_type) if has_geometry else None,
                "fields": [_translate_field_name(f) for f in fields if f],
            })
        except Exception as e:
            layers.append({
                "name": name,
                "display_name": name,
                "row_count": -1,
                "has_geometry": False,
                "fields": [],
                "error": str(e),
            })
    return layers


@router.get("/preview-db-layers")
async def preview_db_layers(
    file_path: str = Query(..., description="MDB/GDB 文件相对路径"),
    user: dict = Depends(get_current_user),
):
    """列出 MDB/GDB 数据库内的所有用户表/图层。"""
    path_project_id = file_path.split("/")[0] if "/" in file_path else "default"
    require_project_access(path_project_id, user, write=False)

    target = UPLOAD_ROOT / file_path
    if not target.exists():
        raise HTTPException(status_code=404, detail="文件不存在")

    ext = target.suffix.lower()
    try:
        if ext == ".mdb":
            layers = _list_mdb_layers(str(target))
            db_type = "mdb"
        elif ext == ".gdb":
            layers = _list_gdb_layers(str(target))
            db_type = "gdb"
        else:
            raise HTTPException(status_code=400, detail=f"不支持的数据库格式: {ext}")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"数据库读取失败: {str(e)}")

    import json as json_mod
    from starlette.responses import Response as RawResponse
    result = {
        "db_type": db_type,
        "filename": target.name,
        "layer_count": len(layers),
        "layers": layers,
    }
    json_bytes = json_mod.dumps(result, ensure_ascii=False, default=str).encode("utf-8")
    return RawResponse(content=json_bytes, media_type="application/json; charset=utf-8")


@router.get("/preview-db-table")
async def preview_db_table(
    file_path: str = Query(..., description="MDB/GDB 文件相对路径"),
    layer: str = Query(..., description="图层/表名称"),
    limit: int = Query(default=500, le=2000, description="最大返回行数"),
    user: dict = Depends(get_current_user),
):
    """读取 MDB/GDB 中某个图层的属性表数据，空间图层额外返回 GeoJSON。"""
    import json as json_mod

    path_project_id = file_path.split("/")[0] if "/" in file_path else "default"
    require_project_access(path_project_id, user, write=False)

    target = UPLOAD_ROOT / file_path
    if not target.exists():
        raise HTTPException(status_code=404, detail="文件不存在")

    ext = target.suffix.lower()

    try:
        if ext == ".mdb":
            data = _read_mdb_table(str(target), layer, limit)
        elif ext == ".gdb":
            data = _read_gdb_table(str(target), layer, limit)
        else:
            raise HTTPException(status_code=400, detail=f"不支持的数据库格式: {ext}")

        # WHY: 必须用 ensure_ascii=False 直接输出中文原文，
        # 避免 \uXXXX 转义在 FRP/Nginx 代理链路中被二次编码导致乱码
        from starlette.responses import Response as RawResponse
        json_bytes = json_mod.dumps(data, ensure_ascii=False, default=str).encode("utf-8")
        return RawResponse(
            content=json_bytes,
            media_type="application/json; charset=utf-8",
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"图层读取失败: {str(e)}")


def _read_mdb_table(mdb_path: str, layer: str, limit: int) -> dict:
    """用 mdb-export 读取 MDB 表的属性数据。"""
    import subprocess
    import csv
    import io

    result = subprocess.run(
        ["mdb-export", mdb_path, layer],
        capture_output=True, timeout=30,
    )
    if result.returncode != 0:
        raise RuntimeError(f"mdb-export 失败: {result.stderr.decode('utf-8', errors='replace')}")

    # WHY: MDB 可能包含二进制几何数据或 Null 字节，导致 csv.reader 崩溃。
    # 先移除 Null 字节，再用 GBK 优先解码（中文 Windows MDB 标配）。
    raw_data = result.stdout.replace(b'\x00', b'')
    csv_text = _decode_mdb_bytes(raw_data)
    
    reader = csv.reader(io.StringIO(csv_text))
    rows_raw = []
    try:
        rows_raw = list(reader)
    except Exception as e:
        # 如果还是解析失败，回退到简单的行切割
        rows_raw = [line.split(',') for line in csv_text.strip().split('\n')]

    if not rows_raw:
        return {"layer": layer, "columns": [], "rows": [], "total_rows": 0, "has_geometry": False}

    raw_columns = rows_raw[0]
    # 过滤 SHAPE 列（二进制几何体在 CSV 里是乱码）
    valid_cols = [(i, c) for i, c in enumerate(raw_columns) if c.upper() not in ("SHAPE", "GEOMETRY", "GEOM")]
    columns = [_translate_field_name(c) for _, c in valid_cols]

    data_rows = []
    for row in rows_raw[1:limit + 1]:
        data_rows.append([row[i] if i < len(row) else "" for i, _ in valid_cols])

    return {
        "layer": layer,
        "display_name": _translate_layer_name(layer) or layer,
        "columns": columns,
        "rows": data_rows,
        "total_rows": len(rows_raw) - 1,
        "has_geometry": False,  # MDB 空间数据通过 mdb-export 无法提取几何体
        "geojson": None,
    }


def _read_gdb_table(gdb_path: str, layer: str, limit: int) -> dict:
    """用 geopandas 读取 GDB 图层数据，空间图层返回 GeoJSON。"""
    import geopandas as gpd
    import json as json_mod

    gdf = gpd.read_file(gdb_path, layer=layer, rows=limit)
    has_geometry = "geometry" in gdf.columns and not gdf.geometry.isna().all()

    # 属性表列（排除 geometry）
    attr_cols = [c for c in gdf.columns if c != "geometry"]
    columns = [_translate_field_name(c) for c in attr_cols]

    # 转为字符串行
    data_rows = []
    for _, row in gdf.head(limit).iterrows():
        data_rows.append([str(row[c]) if row[c] is not None else "" for c in attr_cols])

    geojson = None
    if has_geometry:
        # 转 WGS84 + 简化
        if gdf.crs and gdf.crs.to_epsg() != 4326:
            gdf = gdf.to_crs(epsg=4326)
        gdf["geometry"] = gdf["geometry"].simplify(tolerance=0.00001, preserve_topology=True)
        # 限制 GeoJSON 要素数
        geo_gdf = gdf.head(min(limit, 5000))
        geojson = json_mod.loads(geo_gdf.to_json(ensure_ascii=False))

    return {
        "layer": layer,
        "display_name": _translate_layer_name(layer) or layer,
        "columns": columns,
        "rows": data_rows,
        "total_rows": len(gdf),
        "has_geometry": has_geometry,
        "geojson": geojson,
    }


