"""
后台管理路由：用户管理、项目管理、日志查看、系统设置。
WHY: 所有路由需 require_admin 守卫，仅管理员可访问。
     全面迁移至 SQLite，消除 JSON read-modify-write 竞态问题。
"""
from __future__ import annotations

import json
import shutil
import os
from pathlib import Path
from datetime import datetime

from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel

from core.config import settings
from core.auth_deps import require_admin, get_current_user
from core.database import get_db
from api.auth import (
    _read_users, _write_users, _hash_password,
    _safe_user, _log_operation,
)

router = APIRouter(prefix="/api/admin", tags=["后台管理"])

import logging
logger = logging.getLogger(__name__)

# ===================== 用户管理 =====================

@router.get("/users")
async def list_users(status: str = None, admin: dict = Depends(require_admin)):
    """获取用户列表，可按状态筛选。"""
    with get_db() as conn:
        if status:
            rows = conn.execute(
                "SELECT * FROM users WHERE status = ?", (status,)
            ).fetchall()
        else:
            rows = conn.execute("SELECT * FROM users").fetchall()
    return [_safe_user(dict(r)) for r in rows]


@router.put("/users/{uid}/approve")
async def approve_user(uid: str, admin: dict = Depends(require_admin)):
    """审批用户注册。"""
    with get_db() as conn:
        row = conn.execute("SELECT * FROM users WHERE id = ?", (uid,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="用户未找到")
        u = dict(row)
        if u["status"] != "pending":
            raise HTTPException(status_code=400, detail="该用户不在待审批状态")
        conn.execute("UPDATE users SET status = 'active' WHERE id = ?", (uid,))

    _log_operation(admin["id"], "admin_approve_user", f"审批通过用户：{u['username']}（{u['login_name']}）")
    u["status"] = "active"
    return _safe_user(u)


@router.put("/users/{uid}/disable")
async def disable_user(uid: str, admin: dict = Depends(require_admin)):
    """禁用用户。"""
    with get_db() as conn:
        row = conn.execute("SELECT * FROM users WHERE id = ?", (uid,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="用户未找到")
        u = dict(row)
        if u["role"] == "admin":
            raise HTTPException(status_code=400, detail="不能禁用管理员账号")
        conn.execute("UPDATE users SET status = 'disabled' WHERE id = ?", (uid,))

    _log_operation(admin["id"], "admin_disable_user", f"禁用用户：{u['username']}")
    u["status"] = "disabled"
    return _safe_user(u)


@router.put("/users/{uid}/enable")
async def enable_user(uid: str, admin: dict = Depends(require_admin)):
    """启用用户。"""
    with get_db() as conn:
        row = conn.execute("SELECT * FROM users WHERE id = ?", (uid,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="用户未找到")
        u = dict(row)
        conn.execute("UPDATE users SET status = 'active' WHERE id = ?", (uid,))

    _log_operation(admin["id"], "admin_enable_user", f"启用用户：{u['username']}")
    u["status"] = "active"
    return _safe_user(u)


@router.delete("/users/{uid}")
async def delete_user(uid: str, admin: dict = Depends(require_admin)):
    """删除用户。"""
    with get_db() as conn:
        row = conn.execute("SELECT * FROM users WHERE id = ?", (uid,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="用户未找到")
        target = dict(row)
        if target["role"] == "admin":
            raise HTTPException(status_code=400, detail="不能删除管理员账号")
        conn.execute("DELETE FROM users WHERE id = ?", (uid,))

    _log_operation(admin["id"], "admin_delete_user", f"删除用户：{target['username']}（{target['login_name']}）")
    return {"message": f"用户 {target['username']} 已删除"}


class UpdateUserRequest(BaseModel):
    username: str | None = None
    email: str | None = None
    role: str | None = None
    company: str | None = None
    department: str | None = None

@router.put("/users/{uid}")
async def update_user(uid: str, req: UpdateUserRequest, admin: dict = Depends(require_admin)):
    """修改用户信息。"""
    with get_db() as conn:
        row = conn.execute("SELECT * FROM users WHERE id = ?", (uid,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="用户未找到")

        updates = []
        params = []
        if req.username is not None:
            updates.append("username = ?")
            params.append(req.username)
        if req.email is not None:
            updates.append("email = ?")
            params.append(req.email)
        if req.role is not None:
            updates.append("role = ?")
            params.append(req.role)
        if req.company is not None:
            updates.append("company = ?")
            params.append(req.company)
        if req.department is not None:
            updates.append("department = ?")
            params.append(req.department)

        if updates:
            params.append(uid)
            conn.execute(
                f"UPDATE users SET {', '.join(updates)} WHERE id = ?",
                params,
            )

        updated = conn.execute("SELECT * FROM users WHERE id = ?", (uid,)).fetchone()
    return _safe_user(dict(updated))


# ===================== 项目管理 =====================

def _row_to_project(row) -> dict:
    """将 SQLite Row 转为前端兼容的项目 dict。"""
    p = dict(row)
    try:
        p["metadata"] = json.loads(p.pop("metadata_json", "{}"))
    except (json.JSONDecodeError, TypeError):
        p["metadata"] = {}
    p["createdAt"] = p.pop("created_at", "")
    p["sourceCount"] = p.pop("source_count", 0)
    return p


@router.get("/projects")
async def list_all_projects(admin: dict = Depends(require_admin)):
    """获取所有项目列表（含 owner 信息）。"""
    with get_db() as conn:
        rows = conn.execute(
            """SELECT p.*, u.username AS real_owner_name
               FROM projects p
               LEFT JOIN users u ON p.owner_id = u.id"""
        ).fetchall()
    result = []
    for r in rows:
        p = _row_to_project(r)
        p["owner_name"] = r["real_owner_name"] or "未知"
        result.append(p)
    return result


class AdminUpdateProjectRequest(BaseModel):
    name: str | None = None
    visibility: str | None = None  # public / private
    priority: int | None = None
    is_paused: int | None = None

@router.put("/projects/{pid}")
async def admin_update_project(pid: str, req: AdminUpdateProjectRequest, admin: dict = Depends(require_admin)):
    """管理员修改项目信息/可见性。"""
    with get_db() as conn:
        row = conn.execute("SELECT * FROM projects WHERE id = ?", (pid,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="项目未找到")

        updates = []
        params = []
        if req.name is not None:
            updates.append("name = ?")
            params.append(req.name)
        if req.visibility is not None:
            updates.append("visibility = ?")
            params.append(req.visibility)
        if req.priority is not None:
            updates.append("priority = ?")
            params.append(req.priority)
        if req.is_paused is not None:
            updates.append("is_paused = ?")
            params.append(req.is_paused)

        if updates:
            params.append(pid)
            conn.execute(
                f"UPDATE projects SET {', '.join(updates)} WHERE id = ?",
                params,
            )

        updated = conn.execute("SELECT * FROM projects WHERE id = ?", (pid,)).fetchone()

    p = _row_to_project(updated)
    _log_operation(admin["id"], "admin_update_project", f"修改项目：{p['name']}（可见性={p.get('visibility', 'public')}）")
    global _LEARNING_PROGRESS_CACHE, _system_stats_cache
    _LEARNING_PROGRESS_CACHE = None
    _system_stats_cache = {"time": 0, "data": {}}
    return p


@router.delete("/projects/{pid}")
async def admin_delete_project(pid: str, admin: dict = Depends(require_admin)):
    """管理员删除项目及其所有关联数据。"""
    with get_db() as conn:
        row = conn.execute("SELECT * FROM projects WHERE id = ?", (pid,)).fetchone()
        if not row:
            raise HTTPException(status_code=404, detail="项目未找到")
        target = _row_to_project(row)
        conn.execute("DELETE FROM projects WHERE id = ?", (pid,))
        conn.execute("DELETE FROM web_sources WHERE project_id = ?", (pid,))

    # 清理关联数据
    uploads_dir = Path(settings.UPLOAD_DIR) / pid
    if uploads_dir.exists():
        shutil.rmtree(uploads_dir, ignore_errors=True)
    docs_dir = Path(settings.DATA_DIR) / "documents" / pid
    if docs_dir.exists():
        shutil.rmtree(docs_dir, ignore_errors=True)
    template_file = Path(settings.DATA_DIR) / "templates" / f"{pid}.json"
    if template_file.exists():
        template_file.unlink()

    _log_operation(admin["id"], "admin_delete_project", f"删除项目：{target['name']}")
    global _LEARNING_PROGRESS_CACHE, _system_stats_cache
    _LEARNING_PROGRESS_CACHE = None
    _system_stats_cache = {"time": 0, "data": {}}
    return {"message": f"项目 {target['name']} 已彻底删除"}


# ===================== 日志管理 =====================

@router.get("/logs")
async def get_logs(
    page: int = 1,
    page_size: int = 50,
    user_id: str = None,
    action: str = None,
    admin: dict = Depends(require_admin),
):
    """
    获取操作日志，支持按用户和操作类型筛选，分页倒序展示。
    WHY: 使用 SQL 原生 OFFSET/LIMIT 分页，比读全量再切效率高数十倍。
    """
    conditions = []
    params = []
    if user_id:
        conditions.append("l.user_id = ?")
        params.append(user_id)
    if action:
        conditions.append("l.action = ?")
        params.append(action)

    where_clause = " AND ".join(conditions) if conditions else "1=1"

    with get_db() as conn:
        # 总数
        total = conn.execute(
            f"SELECT COUNT(*) AS cnt FROM operation_logs l WHERE {where_clause}",
            params,
        ).fetchone()["cnt"]

        # 分页查询（JOIN users 补充用户名）
        offset = (page - 1) * page_size
        rows = conn.execute(
            f"""SELECT l.*, COALESCE(u.username, '系统') AS user_name
                FROM operation_logs l
                LEFT JOIN users u ON l.user_id = u.id
                WHERE {where_clause}
                ORDER BY l.timestamp DESC
                LIMIT ? OFFSET ?""",
            params + [page_size, offset],
        ).fetchall()

    return {
        "total": total,
        "logs": [dict(r) for r in rows],
        "page": page,
        "page_size": page_size,
    }


@router.get("/user-activity")
async def get_user_activity(admin: dict = Depends(require_admin)):
    """
    返回每个用户的活跃概览：最近活动时间、操作总数、各类型操作计数。
    WHY: 使用 SQL GROUP BY 在数据库层面完成聚合，避免全量日志内存遍历。
    """
    with get_db() as conn:
        # 按用户聚合总操作数和最近活跃时间
        rows = conn.execute(
            """SELECT user_id,
                      COUNT(*) AS total_ops,
                      MAX(CASE WHEN action = 'user_login' THEN timestamp END) AS last_login,
                      MAX(timestamp) AS last_active
               FROM operation_logs
               WHERE user_id IS NOT NULL
               GROUP BY user_id
               ORDER BY last_active DESC"""
        ).fetchall()

        # 获取用户信息映射
        users = {
            r["id"]: _safe_user(dict(r))
            for r in conn.execute("SELECT * FROM users").fetchall()
        }

        # 按用户获取各操作类型计数
        action_rows = conn.execute(
            """SELECT user_id, action, COUNT(*) AS cnt
               FROM operation_logs
               WHERE user_id IS NOT NULL
               GROUP BY user_id, action"""
        ).fetchall()

    # 组装 action_counts 映射
    action_counts_map: dict[str, dict[str, int]] = {}
    for ar in action_rows:
        uid = ar["user_id"]
        if uid not in action_counts_map:
            action_counts_map[uid] = {}
        action_counts_map[uid][ar["action"]] = ar["cnt"]

    result = []
    for r in rows:
        uid = r["user_id"]
        result.append({
            "user": users.get(uid, {"id": uid, "username": "已删除用户"}),
            "total_ops": r["total_ops"],
            "last_login": r["last_login"],
            "last_active": r["last_active"],
            "action_counts": action_counts_map.get(uid, {}),
        })

    return result


# ===================== 系统设置 =====================

def _read_system_settings() -> dict:
    """从 SQLite 读取系统设置 KV 表。"""
    try:
        with get_db() as conn:
            rows = conn.execute("SELECT key, value FROM system_settings").fetchall()
        default_agents_info = {
            "chat": {"name": "小智 (Agent)", "gender": "male", "avatar": "horse"},
            "service": {"name": "小管 (Manager)", "gender": "female", "avatar": "horse"},
            "legal": {"name": "行业知识专家", "gender": "male", "avatar": "horse"},
            "precompute": {"name": "小预 (Precalc)", "gender": "male", "avatar": "horse"},
            "vectorizer": {"name": "小向 (Vector)", "gender": "male", "avatar": "horse"},
            "graph": {"name": "小图 (Graphy)", "gender": "female", "avatar": "horse"},
            "summary": {"name": "小聚 (Communer)", "gender": "male", "avatar": "horse"},
            "supervisor": {"name": "【协同】文档秘书", "gender": "male", "avatar": "robot"},
            "contrarian": {"name": "【协同】审查员", "gender": "male", "avatar": "horse"},
            "arbiter": {"name": "【协同】仲裁官", "gender": "male", "avatar": "ox"},
        }
        
        # 兜底默认返回值字典
        def_val = {
            "system_name": "智能体通用知识库 V1.0.0", 
            "heartbeat_enabled": False, 
            "system_run_mode": "full", 
            "funny_level": "low",
            "active_level": "low",
            "linvis_name": "麟维斯",
            "whiteboard_items": "total_projects,completed_percent,total_chunks,total_entities,queue_tasks",
            "visible_agents": "vectorizer,graph,summary,precompute,chat,legal,service",
            "collab_pleading_enabled": "false",
            "collab_contract_enabled": "false",
            "collab_document_enabled": "false",
            "collab_chat_enabled": "false",
            "collab_contrarian_temp": "0.5",
            "collab_arbiter_temp": "0.3",
            "collab_simple_threshold": "500",
            "collab_contrarian_model": "qwen3:8b",
            "collab_arbiter_model": settings.DEFAULT_LLM_MODEL,
            "collab_supervisor_name": "【协同】文档秘书",
            "collab_legal_name": "【协同】行业分析专家",
            "collab_contrarian_name": "【协同】审查员",
            "collab_arbiter_name": "【协同】仲裁官",
        }
        for a_key, a_val in default_agents_info.items():
            for prop in ("name", "gender", "avatar"):
                def_val[f"agent_{a_key}_{prop}"] = a_val[prop]

        if not rows:
            return def_val

        res = {}
        for r in rows:
            k, v = r["key"], r["value"]
            if k == "heartbeat_enabled":
                res[k] = v not in ("false", "0", "False")
            else:
                res[k] = v

        if "heartbeat_enabled" not in res:
            res["heartbeat_enabled"] = False
        if "system_run_mode" not in res:
            res["system_run_mode"] = "full"
        if "funny_level" not in res:
            res["funny_level"] = "low"
        if "active_level" not in res:
            res["active_level"] = res.get("funny_level", "low")
        if "linvis_name" not in res:
            res["linvis_name"] = "麟维斯"
        if "whiteboard_items" not in res:
            res["whiteboard_items"] = "total_projects,completed_percent,total_chunks,total_entities,queue_tasks"
        if "visible_agents" not in res:
            res["visible_agents"] = "vectorizer,graph,summary,precompute,chat,legal,service"
            
        collab_defaults = {
            "collab_pleading_enabled": "false",
            "collab_contract_enabled": "false",
            "collab_document_enabled": "false",
            "collab_chat_enabled": "false",
            "collab_contrarian_temp": "0.5",
            "collab_arbiter_temp": "0.3",
            "collab_simple_threshold": "500",
            "collab_contrarian_model": "qwen3:8b",
            "collab_arbiter_model": settings.DEFAULT_LLM_MODEL,
            "collab_supervisor_name": "【协同】文档秘书",
            "collab_legal_name": "【协同】行业分析专家",
            "collab_contrarian_name": "【协同】审查员",
            "collab_arbiter_name": "【协同】仲裁官",
        }
        for k_col, v_col in collab_defaults.items():
            if k_col not in res:
                res[k_col] = v_col

        for a_key, a_val in default_agents_info.items():
            for prop in ("name", "gender", "avatar"):
                prop_key = f"agent_{a_key}_{prop}"
                if prop_key not in res:
                    res[prop_key] = a_val[prop]
        return res
    except Exception:
        # 兜底直接返回带有 Agent 默认属性的字典
        try:
            return def_val
        except NameError:
            return {
                "system_name": "智能体通用知识库 V1.0.0", 
                "heartbeat_enabled": False, 
                "system_run_mode": "full", 
                "funny_level": "low",
                "active_level": "low",
                "linvis_name": "麟维斯",
                "whiteboard_items": "total_projects,completed_percent,total_chunks,total_entities,queue_tasks",
                "visible_agents": "vectorizer,graph,summary,precompute,chat,legal,service",
                "collab_supervisor_name": "【协同】文档秘书",
                "collab_legal_name": "【协同】行业分析专家",
                "collab_contrarian_name": "【协同】审查员",
                "collab_arbiter_name": "【协同】仲裁官",
            }


@router.get("/settings")
async def get_system_settings(admin: dict = Depends(require_admin)):
    """获取系统设置。"""
    return _read_system_settings()


class UpdateSystemSettingsRequest(BaseModel):
    system_name: str | None = None
    admin_login_name: str | None = None
    admin_password: str | None = None
    heartbeat_enabled: bool | None = None
    system_run_mode: str | None = None
    funny_level: str | None = None
    active_level: str | None = None
    linvis_name: str | None = None
    whiteboard_items: str | None = None
    visible_agents: str | None = None
    agents_custom: dict[str, dict[str, str]] | None = None
    collab_pleading_enabled: bool | None = None
    collab_contract_enabled: bool | None = None
    collab_document_enabled: bool | None = None
    collab_chat_enabled: bool | None = None
    collab_contrarian_temp: float | None = None
    collab_arbiter_temp: float | None = None
    collab_simple_threshold: int | None = None
    collab_contrarian_model: str | None = None
    collab_arbiter_model: str | None = None
    collab_supervisor_name: str | None = None
    collab_legal_name: str | None = None
    collab_contrarian_name: str | None = None
    collab_arbiter_name: str | None = None


@router.put("/settings")
async def update_system_settings(req: UpdateSystemSettingsRequest, admin: dict = Depends(require_admin)):
    """修改系统设置（系统名称、管理员登录名/密码、大模型心跳开关、系统运行模式、搞笑程度）。"""
    logger.info(f"=== 收到更新系统设置请求 ===: {req.model_dump()}")
    if req.system_name is not None:
        with get_db() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO system_settings (key, value) VALUES (?, ?)",
                ("system_name", req.system_name),
            )

    if req.heartbeat_enabled is not None:
        with get_db() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO system_settings (key, value) VALUES (?, ?)",
                ("heartbeat_enabled", "true" if req.heartbeat_enabled else "false"),
            )
        # 如果关闭了大模型心跳，立即发出卸载模型命令，瞬间释放显存
        if not req.heartbeat_enabled:
            import asyncio
            from core.llm_engine import unload_model
            asyncio.create_task(unload_model())

    if req.system_run_mode is not None:
        with get_db() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO system_settings (key, value) VALUES (?, ?)",
                ("system_run_mode", req.system_run_mode),
            )
        
        # 控制 PM2 服务
        import subprocess
        
        def _control_pm2(service: str, action: str):
            try:
                subprocess.run(["pm2", action, service], capture_output=True, text=True, check=True)
                logger.info(f"PM2 {action} {service} 成功")
            except Exception as e:
                logger.error(f"PM2 {action} {service} 失败: {e}")
                
        if req.system_run_mode == "full":
            _control_pm2("shengyao-celery-fast", "start")
            _control_pm2("shengyao-celery-slow", "start")
        elif req.system_run_mode == "vector_only":
            _control_pm2("shengyao-celery-fast", "start")
            _control_pm2("shengyao-celery-slow", "stop")
            # 异步卸载大模型释放显存
            import asyncio
            from core.llm_engine import unload_model
            asyncio.create_task(unload_model())
        elif req.system_run_mode == "suspended":
            _control_pm2("shengyao-celery-fast", "stop")
            _control_pm2("shengyao-celery-slow", "stop")
            # 异步卸载大模型释放显存
            import asyncio
            from core.llm_engine import unload_model
            asyncio.create_task(unload_model())

    # 处理 active_level 和 funny_level，使其联动保存
    level_to_save = req.active_level or req.funny_level
    if level_to_save is not None:
        if level_to_save not in ("low", "medium", "high"):
            raise HTTPException(status_code=400, detail="活跃/搞笑程度必须为 low / medium / high 之一")
        with get_db() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO system_settings (key, value) VALUES (?, ?)",
                ("funny_level", level_to_save),
            )
            conn.execute(
                "INSERT OR REPLACE INTO system_settings (key, value) VALUES (?, ?)",
                ("active_level", level_to_save),
            )

    if req.agents_custom is not None:
        with get_db() as conn:
            for a_key, a_props in req.agents_custom.items():
                for prop in ("name", "gender", "avatar"):
                    if prop in a_props:
                        conn.execute(
                            "INSERT OR REPLACE INTO system_settings (key, value) VALUES (?, ?)",
                            (f"agent_{a_key}_{prop}", str(a_props[prop])),
                        )

    collab_fields = [
        "collab_pleading_enabled",
        "collab_contract_enabled",
        "collab_document_enabled",
        "collab_chat_enabled",
        "collab_contrarian_temp",
        "collab_arbiter_temp",
        "collab_simple_threshold",
        "collab_contrarian_model",
        "collab_arbiter_model",
        "collab_supervisor_name",
        "collab_legal_name",
        "collab_contrarian_name",
        "collab_arbiter_name"
    ]
    with get_db() as conn:
        for field in collab_fields:
            val = getattr(req, field)
            if val is not None:
                # 安全校验：协同和仲裁模型不可被误设置为大参数量模型，以防显存死锁
                if field in ("collab_contrarian_model", "collab_arbiter_model"):
                    forbidden_keywords = ["35b", "72b", "70b", "32b", "deepseek-r1"]
                    if any(kw in str(val).lower() for kw in forbidden_keywords):
                        raise HTTPException(
                            status_code=400,
                            detail=f"协同代理与仲裁模型只能配置轻量级模型（如 8b），严禁设置为大参数模型 {val}，以防显存资源竞争死锁。"
                        )
                str_val = str(val).lower() if isinstance(val, bool) else str(val)
                conn.execute(
                    "INSERT OR REPLACE INTO system_settings (key, value) VALUES (?, ?)",
                    (field, str_val),
                )

    if req.linvis_name is not None:
        with get_db() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO system_settings (key, value) VALUES (?, ?)",
                ("linvis_name", req.linvis_name),
            )

    if req.whiteboard_items is not None:
        with get_db() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO system_settings (key, value) VALUES (?, ?)",
                ("whiteboard_items", req.whiteboard_items),
            )

    if req.visible_agents is not None:
        with get_db() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO system_settings (key, value) VALUES (?, ?)",
                ("visible_agents", req.visible_agents),
            )

    # 修改管理员登录名或密码
    if req.admin_login_name or req.admin_password:
        with get_db() as conn:
            if req.admin_login_name:
                conn.execute(
                    "UPDATE users SET login_name = ? WHERE id = ?",
                    (req.admin_login_name, admin["id"]),
                )
            if req.admin_password:
                if len(req.admin_password) < 6:
                    raise HTTPException(status_code=400, detail="密码长度不能少于 6 位")
                conn.execute(
                    "UPDATE users SET password_hash = ? WHERE id = ?",
                    (_hash_password(req.admin_password), admin["id"]),
                )

    _log_operation(admin["id"], "admin_update_settings", "修改系统设置")
    return _read_system_settings()


@router.post("/llm/unload")
async def manual_unload_llm(admin: dict = Depends(require_admin)):
    """手动立即卸载大模型，释放显存资源。"""
    from core.llm_engine import unload_model
    import asyncio
    
    # 异步执行卸载，防止接口卡顿
    asyncio.create_task(unload_model())
    _log_operation(admin["id"], "admin_unload_llm", "手动卸载大模型释放显存")
    return {"success": True, "message": "大模型卸载指令已成功发送，显存正在释放中"}


@router.get("/settings/public")
async def get_public_settings():
    """公开接口：获取系统名称以及所有 Agent 配置（前台交互与登录页展示使用）。"""
    s = _read_system_settings()
    res = {
        "system_name": s.get("system_name", "智能体通用知识库 V1.0.0"),
        "linvis_name": s.get("linvis_name", "麟维斯"),
    }
    for k, v in s.items():
        if k.startswith("agent_") or k.startswith("collab_"):
            res[k] = v
    return res


def _is_stale_task(updated_at: str, threshold: int = 1800) -> bool:
    """计算状态更新时间与当前北京时间的差距是否超过阈值（秒）。"""
    if not updated_at:
        return True
    try:
        from datetime import timezone, timedelta
        normalized = updated_at.replace(" ", "T")
        if normalized.endswith("Z"):
            normalized = normalized[:-1] + "+00:00"
        dt = datetime.fromisoformat(normalized)
        tz_bj = timezone(timedelta(hours=8))
        if dt.tzinfo is not None:
            dt_bj = dt.astimezone(tz_bj).replace(tzinfo=None)
        else:
            dt_bj = dt.replace(tzinfo=timezone.utc).astimezone(tz_bj).replace(tzinfo=None)
        now_bj = datetime.now(tz_bj).replace(tzinfo=None)
        return (now_bj - dt_bj).total_seconds() > threshold
    except Exception:
        return True


_LEARNING_PROGRESS_CACHE = None
_LEARNING_PROGRESS_CACHE_TIME = 0.0
_LEARNING_PROGRESS_CACHE_TTL = 15.0  # 缓存 15 秒

@router.get("/learning-progress")
async def get_learning_progress(user: dict = Depends(get_current_user)):
    """
    获取全局项目学习进度概览（GraphRAG 队列透明度）。
    WHY: 从 .job_states 读取真实文件状态，从 precompute 模块读取预计算进度，
         替代之前的硬编码模拟值。
    """
    global _LEARNING_PROGRESS_CACHE, _LEARNING_PROGRESS_CACHE_TIME
    import time
    now = time.time()
    if _LEARNING_PROGRESS_CACHE is not None and (now - _LEARNING_PROGRESS_CACHE_TIME) <= _LEARNING_PROGRESS_CACHE_TTL:
        return _LEARNING_PROGRESS_CACHE

    with get_db() as conn:
        projects = conn.execute("SELECT id, name, priority, is_paused, created_at FROM projects").fetchall()
        
    result = []
    from pathlib import Path
    import os
    import hashlib
    from core.status_tracker import get_file_status, EXCLUDED_STATUSES, EXCLUDED_REASON_MAP
    from core.precompute import get_project_precompute_stats
    from core.vector_store import get_project_chunk_count
    from core.graph_rag import graph_engine
    
    for p in projects:
        pid = p["id"]
        pname = p["name"]
        priority = dict(p).get("priority", 2) or 2
        is_paused = dict(p).get("is_paused", 0) or 0
        
        project_dir = Path(settings.UPLOAD_DIR) / pid
        if not project_dir.exists():
            continue
            
        total = 0
        vec_completed = 0
        vec_failed = 0
        failed_details = []
        graph_completed = 0
        graph_processing = 0
        graph_failed = 0
        vec_current_task = None
        vec_pending_task = None
        graph_current_task = None
        graph_pending_task = None
        
        stuck_pending_files = []
        latest_update_time = None

        def format_size(size_bytes: int) -> str:
            if size_bytes < 1024:
                return f"{size_bytes} B"
            elif size_bytes < 1024 * 1024:
                return f"{size_bytes / 1024:.1f} KB"
            else:
                return f"{size_bytes / (1024 * 1024):.1f} MB"

        for root, dirs, files in os.walk(str(project_dir)):
            if ".job_states" in dirs:
                dirs.remove(".job_states")
            for f in files:
                if f.startswith(".") or f.endswith(".lock"):
                    continue
                
                path = Path(root) / f
                rel_path = str(path.relative_to(Path(settings.UPLOAD_DIR)))
                file_id = hashlib.md5(f"{pid}_{rel_path}".encode("utf-8")).hexdigest()
                try:
                    status_data = get_file_status(pid, file_id)
                except Exception as _st_e:
                    logger.warning(f"[get_learning_progress] 获取文件状态失败 pid={pid} fid={file_id}: {_st_e}")
                    status_data = {"status": "pending"}
                st = status_data.get("status", "pending")
                error_msg = status_data.get("error_message", "") or ""
                updated_at = status_data.get("updated_at", "")
                
                # ── 向量化与图谱提炼阶段卡死 Ghost Task 物理自愈重设为 failed ──
                if st == "processing" and _is_stale_task(updated_at, 1800):
                    try:
                        from core.status_tracker import update_file_status
                        update_file_status(pid, file_id, "failed", error_message="向量化入库执行超时或进程意外终止")
                        status_data = get_file_status(pid, file_id)
                        st = status_data.get("status", "failed")
                        error_msg = status_data.get("error_message", "") or ""
                        updated_at = status_data.get("updated_at", "")
                        logger.info(f"🕸️ [get_learning_progress] 检测到向量化卡死文件: pid={pid} fid={file_id}，已物理重设为 failed。")
                    except Exception as _uf_e:
                        logger.warning(f"Failed to auto reset vector stale task: {_uf_e}")
                elif st == "graph_extracting" and _is_stale_task(updated_at, 1800):
                    try:
                        from core.status_tracker import update_file_status
                        update_file_status(pid, file_id, "failed", error_message="知识图谱提炼执行超时或进程意外终止")
                        status_data = get_file_status(pid, file_id)
                        st = status_data.get("status", "failed")
                        error_msg = status_data.get("error_message", "") or ""
                        updated_at = status_data.get("updated_at", "")
                        logger.info(f"🕸️ [get_learning_progress] 检测到图谱提炼卡死文件: pid={pid} fid={file_id}，已物理重设为 failed。")
                    except Exception as _uf_e:
                        logger.warning(f"Failed to auto reset graph stale task: {_uf_e}")

                # 收集最新更新时间
                if updated_at:
                    try:
                        normalized = updated_at.replace(" ", "T")
                        if normalized.endswith("Z"):
                            normalized = normalized[:-1] + "+00:00"
                        from datetime import datetime, timezone, timedelta
                        dt = datetime.fromisoformat(normalized)
                        if dt.tzinfo is not None:
                            tz_bj = timezone(timedelta(hours=8))
                            dt_ts = dt.astimezone(tz_bj).replace(tzinfo=None).timestamp()
                        else:
                            dt_ts = dt.replace(tzinfo=timezone.utc).astimezone(timezone(timedelta(hours=8))).replace(tzinfo=None).timestamp()
                        if latest_update_time is None or dt_ts > latest_update_time:
                            latest_update_time = dt_ts
                    except Exception:
                        pass

                # WHY: 使用共享常量排除不可用文件，保证管理员/用户看板口径一致
                if st in EXCLUDED_STATUSES:
                    vec_failed += 1
                    reason = EXCLUDED_REASON_MAP.get(st, "未知失败")
                    
                    if error_msg and st == "failed":
                        reason += f" ({error_msg[:50]})"
                        
                    failed_details.append({
                        "filename": f,
                        "reason": reason
                    })
                    continue  # 跳过，不计入 total
                
                total += 1
                
                # 收集有效但未被执行的真实 pending 文件
                if st == "pending":
                    stuck_pending_files.append({
                        "path": path,
                        "file_id": file_id,
                        "filename": f
                    })

                # 向量化完成
                if st in ("vectorized", "graph_queued", "graph_extracting"):
                    vec_completed += 1
                
                # 图谱完成判定
                if st == "vectorized" and "Graph OK" in error_msg:
                    graph_completed += 1
                elif st == "graph_extracting":
                    # WHY: 仅对 graph_extracting（正在执行）检测 Ghost Task，
                    #      graph_queued 只是排队等待 slow_queue Worker 拾取，
                    #      不算失败，不应受 30 分钟超时约束。
                    is_ghost = _is_stale_task(updated_at, 1800)
                        
                    if is_ghost:
                        graph_failed += 1
                    else:
                        graph_processing += 1
                elif st == "graph_queued":
                    # 排队等待 slow_queue 处理，算作进行中
                    graph_processing += 1
                elif st == "vectorized" and "failed" in error_msg.lower():
                    # 预留给未来可能写入 explicit graph error 的机制
                    graph_failed += 1
                    
                if st == "processing" and not vec_current_task:
                    vec_current_task = {"filename": f, "size": format_size(os.path.getsize(path))}
                elif st == "pending" and not vec_current_task and not vec_pending_task:
                    vec_pending_task = {"filename": f, "size": format_size(os.path.getsize(path))}

                if st == "graph_extracting" and not graph_current_task:
                    graph_current_task = {"filename": f, "size": format_size(os.path.getsize(path))}
                elif st == "graph_queued" and not graph_current_task and not graph_pending_task:
                    graph_pending_task = {"filename": f, "size": format_size(os.path.getsize(path))}

        # ── 僵尸 pending 任务的防空转重投自愈 ──
        if stuck_pending_files:
            has_active_tasks = (graph_processing > 0)
            import time
            from datetime import datetime, timezone, timedelta
            now_ts = datetime.now(timezone(timedelta(hours=8))).replace(tzinfo=None).timestamp()
            is_stale_project = (latest_update_time is None) or (now_ts - latest_update_time > 120)
            
            if not has_active_tasks and is_stale_project:
                from worker import process_document
                from core.status_tracker import update_file_status
                logger.info(f"🕸️ [get_learning_progress] 项目 {pid} 检测到有 {len(stuck_pending_files)} 个僵尸 pending 任务，自动补发触发 Celery 向量化任务。")
                for item in stuck_pending_files:
                    try:
                        fpath = item["path"]
                        fid = item["file_id"]
                        fname = item["filename"]
                        file_size = fpath.stat().st_size if fpath.exists() else 0
                        
                        update_file_status(pid, fid, "pending", error_message="防空转自动补发")
                        
                        if file_size > 2 * 1024 * 1024:
                            process_document.apply_async(args=[str(fpath), fid, fname, pid], queue='slow_queue')
                        else:
                            process_document.delay(str(fpath), fid, fname, pid)
                    except Exception as _tr_e:
                        logger.warning(f"Failed to auto trigger stuck pending task {item['filename']}: {_tr_e}")
        
        if not vec_current_task and vec_pending_task:
            vec_current_task = {"filename": f"排队中: {vec_pending_task['filename']}", "size": vec_pending_task['size']}
        if not graph_current_task and graph_pending_task:
            graph_current_task = {"filename": f"排队中: {graph_pending_task['filename']}", "size": graph_pending_task['size']}
        
        if total > 0:
            vec_percent = round(vec_completed / total * 100, 2)
            
            # WHY: 图谱进度必须以全部文件为分母，不能只看已进入图谱阶段的文件。
            #      否则会出现"向量化10%但图谱100%"的悖论（已完成2/2，但分母错误）。
            graph_percent = round(graph_completed / total * 100, 2)
            
            # 图谱状态判定
            if graph_processing > 0:
                graph_status = "processing"
            elif vec_percent < 100:
                graph_status = "pending"
            elif graph_completed >= total:
                graph_status = "completed"
            else:
                graph_status = "processing"
            
            # 预计算进度：从 precompute 模块读取真实数据
            try:
                precompute = get_project_precompute_stats(pid)
            except Exception as _pc_e:
                logger.warning(f"[get_learning_progress] 获取预计算进度失败 pid={pid}: {_pc_e}")
                precompute = {}
            
            # 底层资源统计
            try:
                total_chunks = get_project_chunk_count(pid)
            except Exception as _tc_e:
                logger.warning(f"[get_learning_progress] 获取项目切片数失败 pid={pid}: {_tc_e}")
                total_chunks = 0

            try:
                graph_stats = graph_engine.get_stats(pid)
                total_entities = graph_stats.get("nodes", 0)
            except Exception as _ge_e:
                logger.warning(f"[get_learning_progress] 获取图谱状态失败 pid={pid}: {_ge_e}")
                total_entities = 0
            
            # 获取社区摘要进度
            from core.redis_client import get_redis
            comm_total = 0
            comm_completed = 0
            comm_status = "pending"
            comm_percent = 0
            comm_current_task = None
            try:
                r = get_redis()
                if r:
                    t = r.get(f"community_summary:total:{pid}")
                    c = r.get(f"community_summary:completed:{pid}")
                    s = r.get(f"community_summary:status:{pid}")
                    cur = r.get(f"community_summary:current_task:{pid}")
                    
                    if t is not None:
                        comm_total = int(t)
                    if c is not None:
                        comm_completed = int(c)
                    if s is not None:
                        comm_status = s.decode("utf-8") if isinstance(s, bytes) else str(s)
                    if cur is not None:
                        comm_current_task = {"filename": cur.decode("utf-8") if isinstance(cur, bytes) else str(cur)}
                    
                    if comm_total > 0:
                        comm_percent = round(comm_completed / comm_total * 100, 2)
                    elif comm_status == "completed":
                        comm_percent = 100.0

                    # ── 自动防呆与状态自动修正兜底 ──
                    if graph_status == "completed":
                        if total_entities == 0:
                            comm_status = "completed"
                            comm_percent = 100.0
                        elif comm_status == "pending" and comm_total == 0:
                            from worker import compute_community_summaries
                            lock_key = f"community_summary_lock:{pid}"
                            should_trigger = r.set(lock_key, "1", nx=True, ex=600)
                            if should_trigger:
                                compute_community_summaries.apply_async(args=[pid], queue='summary_queue', countdown=5)
                                logger.info(f"🕸️ [get_learning_progress] 自动防呆补偿触发：项目 {pid} 图谱提取完成但社区摘要挂起，已补发 Celery 任务。")
                                comm_status = "processing"
            except Exception as _rd_e:
                logger.warning(f"[get_learning_progress] 读取 Redis 社区摘要进度失败 pid={pid}: {_rd_e}")
            
            result.append({
                "id": pid,
                "name": pname,
                "priority": priority,
                "is_paused": is_paused,
                "createdAt": dict(p).get("created_at", ""),
                "vectorization": {
                    "total": total,
                    "completed": vec_completed,
                    "failed": vec_failed,
                    "failed_details": failed_details,
                    "percent": vec_percent,
                    "current_task": vec_current_task,
                    "total_chunks": total_chunks
                },
                "graph_rag": {
                    "total": total,
                    "completed": graph_completed,
                    "failed": graph_failed,
                    "percent": graph_percent,
                    "status": graph_status,
                    "current_task": graph_current_task,
                    "total_entities": total_entities
                },
                "community_summary": {
                    "total": comm_total,
                    "completed": comm_completed,
                    "percent": comm_percent,
                    "status": comm_status,
                    "current_task": comm_current_task
                },
                "precompute": precompute
            })
            
    _LEARNING_PROGRESS_CACHE = result
    _LEARNING_PROGRESS_CACHE_TIME = now
    return result


@router.get("/projects/{project_id}/failed-files")
async def get_failed_files(project_id: str, user: dict = Depends(get_current_user)):
    """
    获取指定项目下执行失败的文件明细，包含向量化和图谱提取阶段。
    """
    import os
    from pathlib import Path
    from core.status_tracker import get_file_status, EXCLUDED_STATUSES, EXCLUDED_REASON_MAP
    import hashlib

    project_dir = Path(settings.UPLOAD_DIR) / project_id
    
    if not project_dir.exists():
        return []

    failed_files = []
    
    for root, dirs, files in os.walk(str(project_dir)):
        if ".job_states" in dirs:
            dirs.remove(".job_states")
        for f in files:
            if f.startswith(".") or f.endswith(".lock"):
                continue
                
            path = Path(root) / f
            rel_path = str(path.relative_to(Path(settings.UPLOAD_DIR)))
            file_id = hashlib.md5(f"{project_id}_{rel_path}".encode("utf-8")).hexdigest()
            
            # 传给前端的显示名称：去掉 project_id/ 前缀，保留其在项目内的目录结构
            display_path = rel_path
            if rel_path.startswith(f"{project_id}/"):
                display_path = rel_path[len(project_id)+1:]
            
            status_data = get_file_status(project_id, file_id)
            st = status_data.get("status", "pending")
            error_msg = status_data.get("error_message", "")
            updated_at = status_data.get("updated_at", "")
            
            if st in EXCLUDED_STATUSES:
                reason = EXCLUDED_REASON_MAP.get(st, "未知失败")
                
                if error_msg and st == "failed":
                    reason += f" ({error_msg[:50]})"
                    
                failed_files.append({
                    "filename": display_path,
                    "stage": "向量化入库",
                    "error": reason
                })
            elif st == "graph_extracting":
                # WHY: 仅对 graph_extracting（正在执行）检测 Ghost Task。
                #      graph_queued 只是排队等待 slow_queue Worker 拾取，不算失败。
                is_ghost = _is_stale_task(updated_at, 1800)
                    
                if is_ghost:
                    failed_files.append({
                        "filename": display_path,
                        "stage": "知识图谱提取",
                        "error": "任务意外中断或超时 (Ghost Task)"
                    })
            elif st == "graph_queued":
                # 排队等待 slow_queue 处理，不算失败
                pass
            elif st == "processing":
                # WHY: 卡在 processing 超过 30 分钟说明向量化 Worker 已丢失该任务
                is_stale = _is_stale_task(updated_at, 1800)
                if is_stale:
                    failed_files.append({
                        "filename": display_path,
                        "stage": "向量化入库",
                        "error": "任务卡住超过 30 分钟 (Stale Processing)"
                    })
            elif st == "vectorized" and "failed" in error_msg.lower():
                failed_files.append({
                    "filename": display_path,
                    "stage": "知识图谱提取",
                    "error": error_msg
                })

    return failed_files

class RetryFileRequest(BaseModel):
    filename: str
    stage: str

@router.post("/projects/{project_id}/failed-files/retry")
async def retry_failed_file(project_id: str, req: RetryFileRequest, admin: dict = Depends(require_admin)):
    """
    重新执行失败的文件任务。
    根据失败阶段，将任务重新推入 Celery 对应的队列中。
    """
    import hashlib
    import asyncio
    from core.status_tracker import get_file_status, update_file_status, EXCLUDED_STATUSES, EXCLUDED_REASON_MAP
    from core.llm_engine import warmup_model
    
    # 手动重试时，自动触发大模型及服务的异步启动与预热，确保后台推理引擎就绪
    asyncio.create_task(warmup_model())
    
    # 还原完整的 rel_path
    rel_path = f"{project_id}/{req.filename}"
    file_id = hashlib.md5(f"{project_id}_{rel_path}".encode("utf-8")).hexdigest()
    
    # 获取原始文件名 (去除目录层级) 和真实绝对路径
    from pathlib import Path
    basename = Path(req.filename).name
    full_path = str(Path(settings.UPLOAD_DIR) / rel_path)
    
    global _LEARNING_PROGRESS_CACHE, _system_stats_cache
    _LEARNING_PROGRESS_CACHE = None
    _system_stats_cache = {"time": 0, "data": {}}
    
    # 强制将状态重置并入队
    if req.stage == "知识图谱提取":
        update_file_status(project_id, file_id, "graph_queued")
        from worker import process_graph_extraction
        process_graph_extraction.apply_async(args=[file_id, basename, project_id], queue='slow_queue')
        return {"success": True, "message": "知识图谱提取任务已重新加入队列"}
        
    elif req.stage == "向量化入库":
        update_file_status(project_id, file_id, "pending")
        from worker import process_document
        # WHY: admin 手动重试时，先快速提取文本预估 chunks，
        #      超阈值直接走 slow_queue，避免用户重试后又超时。
        import os
        file_size = os.path.getsize(full_path) if os.path.exists(full_path) else 0
        if file_size > 2 * 1024 * 1024 or (file_size > 1 * 1024 * 1024 and basename.lower().endswith(('.xlsx', '.xls'))):
            process_document.apply_async(
                args=[full_path, file_id, basename, project_id],
                queue='slow_queue'
            )
        else:
            process_document.delay(full_path, file_id, basename, project_id)
        return {"success": True, "message": "向量化入库任务已重新加入队列"}
        
    raise HTTPException(status_code=400, detail="不支持的重试阶段")

# ===================== 服务状态管控 =====================


_SERVICE_STATUS_CACHE = None
_SERVICE_STATUS_CACHE_TIME = 0.0
_SERVICE_STATUS_CACHE_TTL = 15.0  # 缓存 15 秒

@router.get("/service-status")
async def get_service_status(admin: dict = Depends(require_admin)):
    """
    查询所有核心服务的运行状态及详细运行指标。
    WHY: 每个服务附带 metrics 字典，前端可展示关键运行参数，
         方便管理员快速诊断性能和容量问题。
    """
    global _SERVICE_STATUS_CACHE, _SERVICE_STATUS_CACHE_TIME
    import time
    now = time.time()
    if _SERVICE_STATUS_CACHE is not None and (now - _SERVICE_STATUS_CACHE_TIME) <= _SERVICE_STATUS_CACHE_TTL:
        return _SERVICE_STATUS_CACHE

    import httpx
    from core.config import settings as cfg

    results = []

    # 1. Ollama 大模型推理引擎
    ollama_online = False
    ollama_detail = "无模型驻留显存"
    ollama_metrics = {}
    try:
        async with httpx.AsyncClient(timeout=3.0) as c:
            resp = await c.get(f"{cfg.OLLAMA_BASE_URL}/api/tags")
            if resp.status_code == 200:
                ollama_online = True
                all_models = resp.json().get("models", [])
                ollama_metrics["available_models"] = len(all_models)

            ps_resp = await c.get(f"{cfg.OLLAMA_BASE_URL}/api/ps")
            if ps_resp.status_code == 200:
                models = ps_resp.json().get("models", [])
                if models:
                    # 遍历并收集所有驻留的模型信息
                    loaded_list = []
                    total_vram_bytes = 0
                    for m in models:
                        mvram = m.get("size_vram", 0)
                        total_vram_bytes += mvram
                        loaded_list.append(f"{m['name']} ({round(mvram / (1024**3), 1)}GB)")
                    
                    ollama_detail = f"已加载: {', '.join(loaded_list)}"
                    
                    # 兜底以第一个模型的信息作为 metrics 字段的默认展示
                    primary_m = models[0]
                    ollama_metrics["model_name"] = primary_m["name"]
                    ollama_metrics["parameter_size"] = primary_m.get("details", {}).get("parameter_size", "未知")
                    ollama_metrics["quantization"] = primary_m.get("details", {}).get("quantization_level", "未知")
                    ollama_metrics["vram_gb"] = round(total_vram_bytes / (1024**3), 1)
                    ollama_metrics["context_length"] = primary_m.get("context_length", 0)
                    ollama_metrics["family"] = primary_m.get("details", {}).get("family", "未知")
                    ollama_metrics["loaded_models"] = [
                        {
                            "name": m["name"],
                            "vram_gb": round(m.get("size_vram", 0) / (1024**3), 1),
                            "parameter_size": m.get("details", {}).get("parameter_size", "未知")
                        }
                        for m in models
                    ]
    except Exception:
        pass
    results.append({
        "id": "ollama", "name": "大模型推理引擎 (Ollama)",
        "online": ollama_online, "detail": ollama_detail,
        "controllable": True, "metrics": ollama_metrics,
    })

    # 2. Qdrant 向量数据库
    qdrant_online = False
    qdrant_detail = ""
    qdrant_metrics = {}
    try:
        async with httpx.AsyncClient(timeout=3.0) as c:
            resp = await c.get(f"{cfg.QDRANT_URL}/collections")
            if resp.status_code == 200:
                qdrant_online = True
                cols = resp.json().get("result", {}).get("collections", [])
                qdrant_detail = f"{len(cols)} 个集合"
                qdrant_metrics["collections"] = len(cols)

                # WHY: 逐集合获取向量数/磁盘占用，展示存储压力
                total_vectors = 0
                total_disk_mb = 0
                for col in cols:
                    try:
                        cr = await c.get(f"{cfg.QDRANT_URL}/collections/{col['name']}")
                        if cr.status_code == 200:
                            info = cr.json().get("result", {})
                            total_vectors += info.get("points_count", 0)
                            # segments_count 和 disk 用于磁盘估算
                            for seg in info.get("segments", {}).values() if isinstance(info.get("segments"), dict) else []:
                                total_disk_mb += seg.get("disk_usage_bytes", 0) / (1024**2)
                    except Exception:
                        pass
                qdrant_metrics["total_vectors"] = total_vectors
                if total_disk_mb > 0:
                    qdrant_metrics["disk_mb"] = round(total_disk_mb, 1)
    except Exception:
        pass
    results.append({
        "id": "qdrant", "name": "向量数据库 (Qdrant)",
        "online": qdrant_online, "detail": qdrant_detail,
        "controllable": False, "metrics": qdrant_metrics,
    })

    # 3. Neo4j 图数据库
    neo4j_online = False
    neo4j_metrics = {}
    try:
        from core.graph_rag import graph_engine
        if graph_engine._ensure_connection():
            neo4j_online = True
            with graph_engine._driver.session() as session:
                neo4j_metrics["entities"] = session.run(
                    "MATCH (n:Entity) RETURN count(n) AS c"
                ).single()["c"]
                neo4j_metrics["relationships"] = session.run(
                    "MATCH ()-[r]->() RETURN count(r) AS c"
                ).single()["c"]
                neo4j_metrics["communities"] = session.run(
                    "MATCH (n:Community) RETURN count(n) AS c"
                ).single()["c"]
            # WHY: 从环境变量读取内存配置，展示当前分配
            import os as _os
            neo4j_metrics["heap_max"] = _os.environ.get(
                "NEO4J_server_memory_heap_max__size", "未知"
            )
            neo4j_metrics["pagecache"] = _os.environ.get(
                "NEO4J_server_memory_pagecache_size", "未知"
            )
    except Exception:
        pass
    results.append({
        "id": "neo4j", "name": "知识图谱数据库 (Neo4j)",
        "online": neo4j_online,
        "detail": f"{neo4j_metrics.get('entities', 0)} 实体 / {neo4j_metrics.get('relationships', 0)} 关系" if neo4j_online else "",
        "controllable": False, "metrics": neo4j_metrics,
    })

    # 4. Redis 缓存
    redis_online = False
    redis_metrics = {}
    try:
        from core.redis_client import get_redis
        r = get_redis()
        if r and r.ping():
            redis_online = True
            info = r.info("memory")
            redis_metrics["used_memory_mb"] = round(
                info.get("used_memory", 0) / (1024**2), 1
            )
            redis_metrics["peak_memory_mb"] = round(
                info.get("used_memory_peak", 0) / (1024**2), 1
            )
            # 队列积压
            redis_metrics["fast_queue"] = r.llen("celery")
            redis_metrics["slow_queue"] = r.llen("slow_queue")
            redis_metrics["total_keys"] = r.dbsize()
            # 连接数
            clients_info = r.info("clients")
            redis_metrics["connected_clients"] = clients_info.get(
                "connected_clients", 0
            )
    except Exception:
        pass
    results.append({
        "id": "redis", "name": "缓存服务 (Redis)",
        "online": redis_online,
        "detail": f"内存 {redis_metrics.get('used_memory_mb', 0)}MB / 峰值 {redis_metrics.get('peak_memory_mb', 0)}MB" if redis_online else "",
        "controllable": False, "metrics": redis_metrics,
    })

    # 5. Celery 异步任务队列
    celery_online = False
    celery_workers: list = []
    celery_metrics = {}
    try:
        from core.celery_app import celery_app
        inspect = celery_app.control.inspect(timeout=2.0)
        active = inspect.active() or {}
        reserved = inspect.reserved() or {}
        celery_workers = list(active.keys())
        celery_online = len(celery_workers) > 0
        celery_metrics["workers"] = [
            w.split("@")[0] for w in celery_workers
        ]
        celery_metrics["active_tasks"] = sum(
            len(v) for v in active.values()
        )
        celery_metrics["reserved_tasks"] = sum(
            len(v) for v in reserved.values()
        )
    except Exception:
        pass
    results.append({
        "id": "celery", "name": "异步任务队列 (Celery)",
        "online": celery_online,
        "detail": f"{len(celery_workers)} 个 Worker · {celery_metrics.get('active_tasks', 0)} 任务执行中" if celery_workers else "",
        "controllable": False, "metrics": celery_metrics,
    })

    # 6. 大模型心跳守护
    from core.llm_engine import is_heartbeat_enabled
    heartbeat = is_heartbeat_enabled()
    results.append({
        "id": "heartbeat", "name": "大模型心跳守护 (Heartbeat)",
        "online": heartbeat,
        "detail": "保持模型常驻显存" if heartbeat else "已关闭，模型空闲后自动卸载",
        "controllable": True, "metrics": {},
    })

    _SERVICE_STATUS_CACHE = results
    _SERVICE_STATUS_CACHE_TIME = now
    return results


class ServiceToggleRequest(BaseModel):
    action: str  # "start" 或 "stop"


@router.post("/service/{service_id}/toggle")
async def toggle_service(service_id: str, req: ServiceToggleRequest, admin: dict = Depends(require_admin)):
    """
    启动或停止指定服务。
    仅支持可控服务（ollama 模型加载/卸载、heartbeat 开关）。
    """
    import asyncio

    global _SERVICE_STATUS_CACHE, _system_stats_cache
    _SERVICE_STATUS_CACHE = None
    _system_stats_cache = {"time": 0, "data": {}}

    if service_id == "ollama":
        from core.llm_engine import warmup_model, unload_model
        if req.action == "start":
            asyncio.create_task(warmup_model())
            _log_operation(admin["id"], "service_start", "手动启动大模型推理引擎")
            return {"success": True, "message": "大模型加载指令已发送，正在预热中"}
        elif req.action == "stop":
            asyncio.create_task(unload_model())
            _log_operation(admin["id"], "service_stop", "手动停止大模型推理引擎")
            return {"success": True, "message": "大模型卸载指令已发送，显存正在释放"}

    elif service_id == "heartbeat":
        with get_db() as conn:
            value = "true" if req.action == "start" else "false"
            conn.execute(
                "INSERT OR REPLACE INTO system_settings (key, value) VALUES (?, ?)",
                ("heartbeat_enabled", value),
            )
        if req.action == "stop":
            from core.llm_engine import unload_model
            asyncio.create_task(unload_model())
        msg = "大模型心跳守护已启用" if req.action == "start" else "大模型心跳守护已关闭并卸载模型"
        _log_operation(admin["id"], f"heartbeat_{req.action}", msg)
        return {"success": True, "message": msg}

    elif service_id == "all":
        from core.llm_engine import warmup_model, unload_model
        if req.action == "start":
            with get_db() as conn:
                conn.execute(
                    "INSERT OR REPLACE INTO system_settings (key, value) VALUES (?, ?)",
                    ("heartbeat_enabled", "true"),
                )
            asyncio.create_task(warmup_model())
            _log_operation(admin["id"], "service_start_all", "一键启动所有可控服务")
            return {"success": True, "message": "所有服务启动指令已发送"}
        elif req.action == "stop":
            with get_db() as conn:
                conn.execute(
                    "INSERT OR REPLACE INTO system_settings (key, value) VALUES (?, ?)",
                    ("heartbeat_enabled", "false"),
                )
            asyncio.create_task(unload_model())
            _log_operation(admin["id"], "service_stop_all", "一键停止所有可控服务")
            return {"success": True, "message": "所有服务停止指令已发送，显存正在释放"}

    raise HTTPException(status_code=400, detail="不支持的服务或操作")


# ===================== 系统统计 =====================

import time
_system_stats_cache = {"time": 0, "data": {}}

@router.get("/system-stats")
async def get_system_stats(admin: dict = Depends(require_admin)):
    import psutil
    from core.vector_store import get_collection_stats
    from core.graph_rag import graph_engine
    from core.redis_client import get_redis

    global _system_stats_cache
    if time.time() - _system_stats_cache["time"] < 15:
        return _system_stats_cache["data"]

    # 1. Resource stats
    cpu_percent = psutil.cpu_percent(interval=None)
    mem = psutil.virtual_memory()

    # WHY: 容器内 psutil.virtual_memory().total 读取的是 OrbStack/Docker VM 的内存
    #      （约 16GB），并非宿主机 macOS 的真实统一内存（48GB）。
    #      通过环境变量 HOST_MEMORY_GB 传入宿主机真实总内存来修正。
    host_memory_gb = float(os.environ.get("HOST_MEMORY_GB", "0"))
    if host_memory_gb > 0:
        memory_total_mb = int(host_memory_gb * 1024)
    else:
        memory_total_mb = mem.total // (1024 * 1024)

    # WHY: 容器内 mem.used 只反映 VM 视角的内存使用，也不准确。
    #      改为计算容器内所有进程的 RSS（常驻内存集）总和，
    #      再加上 Ollama 模型占用的 VRAM，得到本系统实际内存占用。
    container_rss_mb = 0
    try:
        for proc in psutil.process_iter(['memory_info']):
            mi = proc.info.get('memory_info')
            if mi:
                container_rss_mb += mi.rss // (1024 * 1024)
    except Exception:
        container_rss_mb = mem.used // (1024 * 1024)

    # WHY: Apple Silicon 统一内存架构下，GPU VRAM 即主内存。
    #      通过 Ollama /api/ps 获取当前驻留显存的模型大小，
    #      加入总占用计算，才能反映真实的内存压力。
    ollama_vram_mb = 0
    try:
        import httpx as _hx
        _ollama_resp = _hx.get(
            f"{settings.OLLAMA_BASE_URL}/api/ps", timeout=2.0
        )
        if _ollama_resp.status_code == 200:
            for m in _ollama_resp.json().get("models", []):
                ollama_vram_mb += m.get("size_vram", 0) // (1024 * 1024)
    except Exception:
        pass

    memory_used_mb = container_rss_mb + ollama_vram_mb

    # 2. Redis queue stats
    # WHY: Celery 默认队列在 Redis 中的 key 名固定为 "celery"（非 "fast_queue"）。
    #      fast worker 绑定 -Q celery，slow worker 绑定 -Q slow_queue。
    #      必须分别读取正确的 Redis key 才能获得真实的队列积压数。
    fast_queue_len = 0
    slow_queue_len = 0
    try:
        r = get_redis()
        if r:
            fast_queue_len = r.llen("celery")        # 默认队列 key = "celery"
            slow_queue_len = r.llen("slow_queue")
    except Exception:
        pass

    # 3. Vector stats
    vector_stats = get_collection_stats()
    total_chunks = vector_stats.get("count", 0)

    # 4. Graph stats
    total_entities = 0
    total_relationships = 0
    try:
        # WHY: _driver 是惰性初始化的，必须先调用 _ensure_connection，
        #      否则首次请求时 _driver=None 导致返回 0。
        if graph_engine._ensure_connection():
            with graph_engine._driver.session() as session:
                total_entities = session.run("MATCH (n:Entity) RETURN count(n) AS c").single()["c"]
                total_relationships = session.run("MATCH ()-[r]->() RETURN count(r) AS c").single()["c"]
    except Exception:
        pass

    # 5. Celery worker health (active tasks, worker count)
    active_tasks = 0
    worker_hosts: list = []
    try:
        from core.celery_app import celery_app
        inspect = celery_app.control.inspect(timeout=2.0)
        active = inspect.active() or {}
        active_tasks = sum(len(v) for v in active.values())
        worker_hosts = list(active.keys())
    except Exception:
        pass

    _system_stats_cache = {
        "time": time.time(),
        "data": {
            "celery": {
                "fast_queue": fast_queue_len,
                "slow_queue": slow_queue_len,
                "active_tasks": active_tasks,
                "worker_hosts": worker_hosts,
            },
            "vector_db": {
                "total_chunks": total_chunks
            },
            "graph_db": {
                "total_entities": total_entities,
                "total_relationships": total_relationships
            },
            "system": {
                "cpu_percent": cpu_percent,
                "memory_used_mb": memory_used_mb,
                "memory_total_mb": memory_total_mb
            }
        }
    }
    return _system_stats_cache["data"]


# ===================== 指标历史采集与查询 =====================

# WHY: 前端每次拉取 service-status 时顺便触发采集，
#      但使用 10 分钟节流避免高频写入，保证数据点稀疏可控。
_last_snapshot_time: float = 0
_SNAPSHOT_INTERVAL = 600  # 10 分钟


def _collect_and_save_snapshot() -> dict:
    """
    采集当前系统核心指标并持久化到 metrics_history 表。
    WHY: 提取为独立函数，供 API 端点和后台定时器共同调用。
         内含 10 分钟节流，防止高频写入膨胀数据库。
    返回: {"success": True, "recorded_at": ...} 或 {"skipped": True}
    """
    global _last_snapshot_time
    now = time.time()
    if now - _last_snapshot_time < _SNAPSHOT_INTERVAL:
        return {"skipped": True, "message": "距上次快照不足 10 分钟"}

    vectors = 0
    entities = 0
    relations = 0
    communities = 0
    redis_mem_mb = 0.0
    redis_keys = 0

    # 向量数
    try:
        from core.vector_store import get_collection_stats
        vectors = get_collection_stats().get("count", 0)
    except Exception:
        pass

    # 图谱实体/关系/社区
    try:
        from core.graph_rag import graph_engine
        if graph_engine._ensure_connection():
            with graph_engine._driver.session() as session:
                entities = session.run(
                    "MATCH (n:Entity) RETURN count(n) AS c"
                ).single()["c"]
                relations = session.run(
                    "MATCH ()-[r]->() RETURN count(r) AS c"
                ).single()["c"]
                communities = session.run(
                    "MATCH (n:Community) RETURN count(n) AS c"
                ).single()["c"]
    except Exception:
        pass

    # Redis 内存 / 键数
    try:
        from core.redis_client import get_redis
        r = get_redis()
        if r and r.ping():
            info = r.info("memory")
            redis_mem_mb = round(
                info.get("used_memory", 0) / (1024**2), 2
            )
            redis_keys = r.dbsize()
    except Exception:
        pass

    from datetime import timezone, timedelta
    tz_bj = timezone(timedelta(hours=8))
    recorded_at = datetime.now(tz_bj).replace(tzinfo=None).isoformat(timespec="seconds")
    with get_db() as conn:
        conn.execute(
            """INSERT INTO metrics_history
               (recorded_at, vectors, entities, relations,
                communities, redis_mem_mb, redis_keys)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (recorded_at, vectors, entities, relations,
             communities, redis_mem_mb, redis_keys),
        )
        # WHY: 自动清理 30 天以前的旧数据，防止表无限膨胀
        conn.execute(
            "DELETE FROM metrics_history WHERE datetime(recorded_at) < datetime('now', '+8 hours', '-30 days')"
        )

    _last_snapshot_time = now
    return {"success": True, "recorded_at": recorded_at}


@router.post("/metrics/snapshot")
async def record_metrics_snapshot(admin: dict = Depends(require_admin)):
    """
    手动触发采集指标快照（前端调用）。
    WHY: 保留 API 端点供前端兼容调用，内部委托给 _collect_and_save_snapshot。
    """
    return _collect_and_save_snapshot()


@router.get("/metrics/history")
async def get_metrics_history(
    days: int = 7,
    admin: dict = Depends(require_admin),
):
    """
    查询最近 N 天的指标历史快照，供前端曲线图渲染。
    WHY: 默认返回 7 天数据，前端可传 days 参数调整范围。
    """
    if days < 1:
        days = 1
    if days > 90:
        days = 90

    with get_db() as conn:
        rows = conn.execute(
            """SELECT recorded_at, vectors, entities, relations,
                      communities, redis_mem_mb, redis_keys
               FROM metrics_history
               WHERE datetime(recorded_at) >= datetime('now', '+8 hours', ?)
               ORDER BY recorded_at ASC""",
            (f"-{days} days",),
        ).fetchall()

    return [dict(r) for r in rows]

