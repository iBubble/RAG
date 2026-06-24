"""
项目级访问控制模块。
WHY: 统一管理"当前用户是否有权操作指定项目"的校验逻辑，
     避免在每个 API 路由中重复编写权限判断代码。

权限模型：
  - Owner / Admin → 完整读写
  - 其他登录用户  → 对 public 项目有只读权限
  - 其他登录用户  → 对 private 项目完全不可见
"""
from __future__ import annotations

import json
from fastapi import HTTPException

from core.database import get_db, dict_from_row


def _read_projects() -> list[dict]:
    """读取全部项目列表。"""
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM projects ORDER BY sort_order ASC, created_at DESC"
        ).fetchall()
        result = []
        for r in rows:
            p = dict(r)
            # WHY: 将 metadata_json 字段还原为嵌套 dict，保持 API 响应兼容
            try:
                p["metadata"] = json.loads(p.pop("metadata_json", "{}"))
            except (json.JSONDecodeError, TypeError):
                p["metadata"] = {}
            # WHY: 数据库字段名是 snake_case，但前端期望 camelCase
            p["createdAt"] = p.pop("created_at", "")
            p["sourceCount"] = p.pop("source_count", 0)
            result.append(p)
        return result


def get_project_or_404(project_id: str) -> dict:
    """
    按 ID 查找项目，不存在则抛出 404。
    WHY: 从全表扫描优化为主键精确查询。
    """
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM projects WHERE id = ?", (project_id,)
        ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="项目未找到")
    p = dict(row)
    try:
        p["metadata"] = json.loads(p.pop("metadata_json", "{}"))
    except (json.JSONDecodeError, TypeError):
        p["metadata"] = {}
    p["createdAt"] = p.pop("created_at", "")
    p["sourceCount"] = p.pop("source_count", 0)
    return p


def require_project_access(project_id: str, user: dict, write: bool = False) -> dict:
    """
    校验当前用户是否有权访问指定项目，并返回该项目数据。

    参数:
        project_id: 项目 ID
        user: 当前登录用户（来自 get_current_user）
        write: 是否需要写权限（上传/删除/保存等修改操作）

    返回:
        项目 dict

    异常:
        404 — 项目不存在
        403 — 无访问权限

    权限矩阵:
    ┌────────────┬────────────┬────────────┐
    │            │  read      │  write     │
    ├────────────┼────────────┼────────────┤
    │  Owner     │  ✅        │  ✅        │
    │  Admin     │  ✅        │  ✅        │
    │  他人+公开  │  ✅        │  ❌ 403    │
    │  他人+私有  │  ❌ 403    │  ❌ 403    │
    └────────────┴────────────┴────────────┘
    """
    project = get_project_or_404(project_id)

    owner_id = project.get("owner_id", "")
    visibility = project.get("visibility", "public")
    is_owner = owner_id == user["id"]
    is_admin = user.get("role") == "admin"

    # Owner 和 Admin 拥有完整读写权限
    if is_owner or is_admin:
        return project

    # 私有项目：非 Owner/Admin 完全不可访问
    if visibility == "private":
        raise HTTPException(
            status_code=403,
            detail="该项目为私有项目，仅项目所有者或管理员可访问"
        )

    # 公开项目 + 写操作：非 Owner/Admin 不允许
    if write:
        raise HTTPException(
            status_code=403,
            detail="您不是该项目的所有者，无权执行此操作。公开项目仅支持只读浏览。"
        )

    # 公开项目 + 读操作：允许
    return project
