import os
from pathlib import Path
from urllib.parse import quote
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse, PlainTextResponse, JSONResponse

router = APIRouter(prefix="/api/viewer", tags=["文档浏览"])

# 支持容器内路径与宿主机路径
POSSIBLE_ROOTS = [
    Path("/Volumes/macData/RAG_Files/法规原文"),
    Path("/root/www/sc/docs/法规原文"),
    Path("/app/backend/data/法规原文"),
]

DOCS_ROOT = None
for r in POSSIBLE_ROOTS:
    if r.exists() and r.is_dir():
        DOCS_ROOT = r
        break

if DOCS_ROOT is None:
    DOCS_ROOT = Path("/Volumes/macData/RAG_Files/法规原文")

_CATALOG_CACHE = None


def _get_catalog_data():
    global _CATALOG_CACHE
    if _CATALOG_CACHE is not None:
        return _CATALOG_CACHE

    if not DOCS_ROOT.exists():
        return {"total_files": 0, "categories": []}

    categories = []
    total_files = 0

    order = ["规章制度", "市监法规", "食品安全国家标准"]

    for cat_name in order:
        cat_path = DOCS_ROOT / cat_name
        if not cat_path.exists():
            continue

        cat_files = []
        subdirs_map = {}

        for root, dirs, files in os.walk(str(cat_path)):
            dirs[:] = [d for d in dirs if not d.startswith(".")]
            for f in sorted(files):
                if f.startswith("."):
                    continue

                full_path = Path(root) / f
                rel_cat = str(full_path.relative_to(cat_path)).replace("\\", "/")
                rel_all = f"{cat_name}/{rel_cat}"

                parts = rel_cat.split("/")
                subdir = parts[0] if len(parts) > 1 else "根目录"
                if len(parts) > 2 and parts[0] == "规章":
                    subdir = f"规章/{parts[1]}"

                f_size = full_path.stat().st_size
                ext = full_path.suffix.lower().lstrip(".")
                
                item = {
                    "name": f,
                    "title": full_path.stem,
                    "path": rel_all,
                    "rel_path": rel_cat,
                    "subdir": subdir,
                    "size": f_size,
                    "type": ext,
                    "category": cat_name,
                }

                if subdir not in subdirs_map:
                    subdirs_map[subdir] = []
                subdirs_map[subdir].append(item)
                cat_files.append(item)
                total_files += 1

        subdirs_list = []
        for sname, sfiles in sorted(subdirs_map.items()):
            subdirs_list.append({
                "name": sname,
                "count": len(sfiles),
                "files": sfiles,
            })

        categories.append({
            "name": cat_name,
            "count": len(cat_files),
            "doc_type": "pdf" if cat_name == "食品安全国家标准" else "md",
            "subdirs": subdirs_list,
        })

    _CATALOG_CACHE = {
        "total_files": total_files,
        "categories": categories,
    }
    return _CATALOG_CACHE


@router.get("/catalog")
async def get_catalog():
    """获取法规原文所有分类及文件树形目录"""
    return JSONResponse(content=_get_catalog_data())


@router.get("/doc")
async def get_document(path: str = Query(..., description="文档相对路径")):
    """在线读取或预览指定文档"""
    # 安全校验：防止跨目录遍历
    clean_path = path.strip("/\\")
    if ".." in clean_path:
        raise HTTPException(status_code=400, detail="非法文件路径")

    target_file = (DOCS_ROOT / clean_path).resolve()

    # 验证是否在 DOCS_ROOT 或 uploads 真实目录下
    try:
        real_target = target_file.resolve()
    except Exception:
        raise HTTPException(status_code=404, detail="文件不存在")

    if not real_target.exists() or not real_target.is_file():
        raise HTTPException(status_code=404, detail="文档未找到")

    ext = real_target.suffix.lower()
    if ext == ".md":
        try:
            with open(real_target, "r", encoding="utf-8") as f:
                content = f.read()
            return PlainTextResponse(content=content, media_type="text/plain; charset=utf-8")
        except UnicodeDecodeError:
            with open(real_target, "r", encoding="gb18030", errors="ignore") as f:
                content = f.read()
            return PlainTextResponse(content=content, media_type="text/plain; charset=utf-8")

    elif ext == ".pdf":
        encoded_name = quote(real_target.name)
        headers = {
            "Content-Disposition": f"inline; filename*=UTF-8''{encoded_name}",
            "Accept-Ranges": "bytes",
        }
        return FileResponse(
            path=str(real_target),
            media_type="application/pdf",
            headers=headers
        )
    else:
        return FileResponse(path=str(real_target))


@router.get("/download")
async def download_single_document(path: str = Query(..., description="文档相对路径")):
    """下载指定单份文档"""
    clean_path = path.strip("/\\")
    if ".." in clean_path:
        raise HTTPException(status_code=400, detail="非法文件路径")

    target_file = (DOCS_ROOT / clean_path).resolve()
    if not target_file.exists() or not target_file.is_file():
        raise HTTPException(status_code=404, detail="文档未找到")

    encoded_name = quote(target_file.name)
    headers = {
        "Content-Disposition": f"attachment; filename*=UTF-8''{encoded_name}",
        "Accept-Ranges": "bytes",
    }
    return FileResponse(
        path=str(target_file),
        filename=target_file.name,
        headers=headers
    )
