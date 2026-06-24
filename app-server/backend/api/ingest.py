"""
文档入库 API：将已上传的文件提取文本 → 向量化 → 写入 ChromaDB。
支持 PDF/Word/Excel/PPT 等多模态格式的自动识别与提取。
"""
from __future__ import annotations

import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel

from core.config import settings
from core.vector_store import ingest_text, get_collection_stats
from core.extractors import extract_text
from core.auth_deps import get_current_user
from core.project_access import require_project_access

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/ingest", tags=["文档入库"])


class IngestRequest(BaseModel):
    file_path: str       # 相对于 uploads 根目录的路径
    file_id: str         # 前端分配的文件唯一 ID
    project_id: str = "default"


class IngestResponse(BaseModel):
    message: str
    chunks: int
    file_id: str


@router.post("", response_model=IngestResponse)
async def ingest_file(req: IngestRequest, user: dict = Depends(get_current_user)):
    """
    读取已持久化的文件内容，自动选择提取器提取文本，
    切片后写入 ChromaDB 向量库。
    WHY: 写入向量库是修改操作，仅 Owner/Admin 可执行。
    """
    require_project_access(req.project_id, user, write=True)
    upload_root = Path(settings.UPLOAD_DIR)
    file_path = upload_root / req.file_path

    if not file_path.exists():
        raise HTTPException(status_code=404, detail=f"文件不存在: {req.file_path}")

    # 使用多模态提取器自动识别格式并提取文本
    text = extract_text(str(file_path))

    if text is None:
        raise HTTPException(
            status_code=400,
            detail=f"不支持的文件格式: {file_path.suffix}（当前支持 txt/md/pdf/docx/xlsx/pptx/caj）"
        )

    if not text.strip():
        raise HTTPException(status_code=400, detail="文件内容为空，无法入库")

    chunk_count = ingest_text(
        text=text,
        file_id=req.file_id,
        filename=file_path.name,
        project_id=req.project_id,
    )

    return IngestResponse(
        message=f"成功将 {file_path.name} 切分为 {chunk_count} 个向量入库",
        chunks=chunk_count,
        file_id=req.file_id,
    )


@router.get("/stats")
async def ingest_stats():
    """获取向量库统计信息。"""
    return get_collection_stats()
