"""
网络材料入库 API：抓取网页正文或接收手动粘贴文本 → 向量化 → 写入 Qdrant。
WHY: 补充本地文件之外的网络资料来源，提升 RAG 知识上下文的覆盖面。
     网络来源元数据已迁移至 SQLite，消除按项目 JSON 文件的竞态问题。
"""
from __future__ import annotations

import hashlib
import logging
import uuid
from pathlib import Path

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel

from core.config import settings
from core.vector_store import ingest_text, delete_by_file_id
from core.auth_deps import get_current_user
from core.project_access import require_project_access
from core.database import get_db

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/web-ingest", tags=["网络材料入库"])


def _read_web_sources(project_id: str) -> list[dict]:
    """从 SQLite 读取指定项目的网络来源。"""
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM web_sources WHERE project_id = ?",
            (project_id,),
        ).fetchall()
    return [dict(r) for r in rows]


# ─── 方案 A：URL 自动抓取 ───

class UrlIngestRequest(BaseModel):
    url: str
    title: str = ""  # 可选自定义标题，否则从网页提取
    project_id: str = "default"


@router.post("/from-url")
async def ingest_from_url(req: UrlIngestRequest, user: dict = Depends(get_current_user)):
    """
    抓取网页正文 → 切片 → 入库 Qdrant。
    WHY: 写入向量库是修改操作，仅 Owner/Admin 可执行。
    """
    require_project_access(req.project_id, user, write=True)

    url = req.url.strip()
    if not url.startswith(("http://", "https://")):
        raise HTTPException(status_code=400, detail="URL 必须以 http:// 或 https:// 开头")

    # 1. 抓取网页并提取正文
    # WHY: trafilatura.fetch_url 的默认 User-Agent 会被百度等站点 403 拦截，
    #      改为用 httpx 自行携带浏览器级请求头抓取 HTML，再交给 trafilatura 提取正文。
    try:
        import httpx as _httpx
        import trafilatura

        _BROWSER_HEADERS = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                          "AppleWebKit/537.36 (KHTML, like Gecko) "
                          "Chrome/124.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Accept-Encoding": "gzip, deflate, br",
        }

        # WHY: 百度等站点要求先拿 cookie 再访问子页面，否则 403。
        #      用 httpx.Client session 模拟浏览器先访问根域，再访问目标 URL。
        from urllib.parse import urlparse
        parsed = urlparse(url)
        root_url = f"{parsed.scheme}://{parsed.netloc}/"

        client = _httpx.Client(follow_redirects=True, timeout=15, headers=_BROWSER_HEADERS)
        try:
            client.get(root_url)  # 预取 cookie
            resp = client.get(url)
        finally:
            client.close()
        if resp.status_code >= 400:
            raise HTTPException(status_code=400, detail=f"无法访问网页（HTTP {resp.status_code}）: {url}")

        downloaded = resp.text
        if not downloaded:
            raise HTTPException(status_code=400, detail=f"无法访问该网页: {url}")

        text = trafilatura.extract(downloaded, include_tables=True, include_comments=False)
        if not text or not text.strip():
            raise HTTPException(status_code=400, detail="网页正文提取为空，可能是动态渲染页面或需要登录")

        # 提取标题
        title = req.title.strip()
        if not title:
            metadata = trafilatura.extract(downloaded, output_format="json")
            if metadata:
                import json as _json
                meta = _json.loads(metadata)
                title = meta.get("title", "") or url
            if not title:
                title = url

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"网页抓取失败: {str(e)}")

    # 2. 生成唯一 file_id（基于项目+URL 哈希，幂等）
    file_id = hashlib.md5(f"{req.project_id}_web_{url}".encode("utf-8")).hexdigest()

    # 3. 入库向量
    chunk_count = ingest_text(
        text=text,
        file_id=file_id,
        filename=title,
        project_id=req.project_id,
    )

    # 4. 记录到 SQLite（INSERT OR REPLACE 保证幂等）
    with get_db() as conn:
        conn.execute(
            """INSERT OR REPLACE INTO web_sources
               (id, project_id, title, url, source_type, text_length, chunks)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (file_id, req.project_id, title, url, "web", len(text), chunk_count),
        )

    logger.info(f"网页入库成功: {title} ({url}), {chunk_count} chunks")

    return {
        "message": f"网页「{title}」已入库",
        "id": file_id,
        "title": title,
        "url": url,
        "chunks": chunk_count,
        "text_length": len(text),
    }


# ─── 方案 B：手动粘贴文本 ───

class TextIngestRequest(BaseModel):
    title: str
    content: str
    project_id: str = "default"


@router.post("/from-text")
async def ingest_from_text(req: TextIngestRequest, user: dict = Depends(get_current_user)):
    """
    接收用户手动粘贴的文本 → 切片 → 入库 Qdrant。
    WHY: 补充无法通过 URL 抓取的内容（如需登录的页面、PDF 复制内容）。
    """
    require_project_access(req.project_id, user, write=True)

    title = req.title.strip()
    content = req.content.strip()

    if not title:
        raise HTTPException(status_code=400, detail="标题不能为空")
    if not content or len(content) < 10:
        raise HTTPException(status_code=400, detail="粘贴内容过短（至少 10 字）")

    # 生成唯一 file_id（基于项目+标题哈希）
    file_id = hashlib.md5(f"{req.project_id}_text_{title}".encode("utf-8")).hexdigest()

    # 入库向量
    chunk_count = ingest_text(
        text=content,
        file_id=file_id,
        filename=title,
        project_id=req.project_id,
    )

    # 记录到 SQLite
    with get_db() as conn:
        conn.execute(
            """INSERT OR REPLACE INTO web_sources
               (id, project_id, title, url, source_type, text_length, chunks)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (file_id, req.project_id, title, "", "text", len(content), chunk_count),
        )

    logger.info(f"粘贴文本入库成功: {title}, {chunk_count} chunks")

    return {
        "message": f"文本「{title}」已入库",
        "id": file_id,
        "title": title,
        "chunks": chunk_count,
        "text_length": len(content),
    }


# ─── 列表 + 删除 ───

@router.get("/list")
async def list_web_sources(project_id: str = "default", user: dict = Depends(get_current_user)):
    """列出该项目的所有网络/粘贴来源。"""
    require_project_access(project_id, user, write=False)
    return _read_web_sources(project_id)


@router.delete("/{source_id}")
async def delete_web_source(source_id: str, project_id: str = "default", user: dict = Depends(get_current_user)):
    """删除一条网络/粘贴来源及其向量索引。"""
    require_project_access(project_id, user, write=True)

    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM web_sources WHERE id = ?", (source_id,)
        ).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="来源记录不存在")
        target = dict(row)

        # 清理 Qdrant 向量
        removed = delete_by_file_id(source_id)
        conn.execute("DELETE FROM web_sources WHERE id = ?", (source_id,))

    logger.info(f"已删除网络来源: {target.get('title', source_id)}, 清理 {removed} 个向量")

    return {
        "message": f"已删除「{target.get('title', '')}」",
        "removed_chunks": removed,
    }


@router.get("/preview/{source_id}")
async def preview_web_source(
    source_id: str,
    project_id: str = "default",
    user: dict = Depends(get_current_user),
):
    """
    预览网络/粘贴来源的全文内容。
    WHY: web/text 来源没有磁盘文件，需要从 Qdrant 向量库反查全部 chunks 拼接还原。
    """
    require_project_access(project_id, user, write=False)

    # 1. 验证来源是否存在
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM web_sources WHERE id = ?", (source_id,)
        ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="来源记录不存在")
    target = dict(row)

    # 2. 从 Qdrant 拉取全部 chunks
    from core.vector_store import get_all_chunks
    chunks = get_all_chunks(source_id)

    if not chunks:
        return {
            "type": "text",
            "filename": target.get("title", "未命名"),
            "content": "（该资料的向量索引为空，可能尚未入库或已被清理）",
            "source_url": target.get("url", ""),
            "source_type": target.get("source_type", "web"),
        }

    # 3. 拼接全文返回
    full_text = "\n".join(chunks)

    return {
        "type": "text",
        "filename": target.get("title", "未命名"),
        "content": full_text,
        "source_url": target.get("url", ""),
        "source_type": target.get("source_type", "web"),
        "chunks": len(chunks),
    }
