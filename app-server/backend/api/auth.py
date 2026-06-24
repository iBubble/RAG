"""
用户认证路由：注册、登录、个人信息管理。
WHY: 用户数据已从 users.json 迁移至 SQLite，
     消除并发 read-modify-write 竞态条件。
"""
from __future__ import annotations

import json
import uuid
import os
import re
from datetime import datetime, timezone, timedelta
from pathlib import Path

import bcrypt
from fastapi import APIRouter, HTTPException, Depends, UploadFile, File
from pydantic import BaseModel

from core.auth_deps import create_token, get_current_user
from core.config import settings
from core.database import get_db, dict_from_row

router = APIRouter(prefix="/api/auth", tags=["认证"])

# WHY: 头像文件仍存文件系统（二进制文件不适合入库）
AVATARS_DIR = Path("data/avatars")
AVATAR_MAX_SIZE = 10 * 1024 * 1024  # 10MB 限制

# 初始化
AVATARS_DIR.mkdir(parents=True, exist_ok=True)


def _read_users() -> list[dict]:
    """读取全部用户（兼容旧调用方式）。"""
    with get_db() as conn:
        rows = conn.execute("SELECT * FROM users").fetchall()
        return [dict(r) for r in rows]


def _get_user_by_id(user_id: str) -> dict | None:
    """按 ID 精确查找用户。"""
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM users WHERE id = ?", (user_id,)
        ).fetchone()
        return dict_from_row(row)


def _get_user_by_login(login_name: str) -> dict | None:
    """按登录名精确查找用户。"""
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM users WHERE login_name = ?", (login_name,)
        ).fetchone()
        return dict_from_row(row)


def _write_users(users: list[dict]):
    """
    兼容层：全量写入用户列表（仅供 admin.py 批量操作调用）。
    WHY: admin.py 中 approve/disable/delete 等操作仍使用
         _read_users() → 修改列表 → _write_users() 的旧模式，
         此函数将列表差异同步到 SQLite。
    """
    with get_db() as conn:
        # WHY: 先获取现有 ID 集合，与新列表对比
        existing_ids = {
            r["id"] for r in conn.execute("SELECT id FROM users").fetchall()
        }
        new_ids = {u["id"] for u in users}

        # 删除不再存在的用户
        removed = existing_ids - new_ids
        for uid in removed:
            conn.execute("DELETE FROM users WHERE id = ?", (uid,))

        # Upsert 所有用户
        for u in users:
            conn.execute(
                """INSERT OR REPLACE INTO users
                   (id, username, login_name, email, password_hash,
                    company, department, role, status, avatar, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    u["id"], u.get("username", ""),
                    u.get("login_name", ""), u.get("email", ""),
                    u.get("password_hash", ""),
                    u.get("company", ""), u.get("department", ""),
                    u.get("role", "user"), u.get("status", "pending"),
                    u.get("avatar", ""), u.get("created_at", ""),
                ),
            )


def _hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def _verify_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))


def _init_admin():
    """首次启动时自动创建预设管理员账号。"""
    with get_db() as conn:
        row = conn.execute(
            "SELECT id FROM users WHERE role = 'admin' LIMIT 1"
        ).fetchone()
        if row:
            return  # 已有管理员，不重复创建

        admin_id = str(uuid.uuid4())
        conn.execute(
            """INSERT INTO users
               (id, username, login_name, email, password_hash,
                company, department, role, status, avatar, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                admin_id, "系统管理员", "admin", "admin@syhsgis.com",
                _hash_password(os.environ.get("ADMIN_INIT_PASSWORD", settings.ADMIN_INIT_PASSWORD)),
                "云南力诺科技有限公司", "",
                "admin", "active", "",
                datetime.now(timezone(timedelta(hours=8))).replace(tzinfo=None).isoformat(),
            ),
        )


# 启动时初始化管理员
_init_admin()


def _safe_user(user: dict) -> dict:
    """返回用户信息时剔除密码哈希等敏感字段。"""
    return {k: v for k, v in user.items() if k != "password_hash"}


# ===================== 数据模型 =====================

class RegisterRequest(BaseModel):
    username: str
    login_name: str
    email: str
    password: str
    confirm_password: str
    company: str = ""
    department: str = ""


class LoginRequest(BaseModel):
    login_name: str
    password: str


class UpdateProfileRequest(BaseModel):
    username: str | None = None
    email: str | None = None
    company: str | None = None
    department: str | None = None


class ChangePasswordRequest(BaseModel):
    old_password: str
    new_password: str
    confirm_password: str


# ===================== 路由 =====================

@router.post("/register")
async def register(req: RegisterRequest):
    """用户注册。状态默认为 pending，需管理员审批后才能登录。"""
    if req.password != req.confirm_password:
        raise HTTPException(status_code=400, detail="两次输入的密码不一致")
    if len(req.password) < 6:
        raise HTTPException(status_code=400, detail="密码长度不能少于 6 位")
    if not req.username.strip():
        raise HTTPException(status_code=400, detail="用户名不能为空")
    if not req.login_name.strip():
        raise HTTPException(status_code=400, detail="登录名不能为空")
    if not re.match(r'^[a-zA-Z0-9_]+$', req.login_name):
        raise HTTPException(status_code=400, detail="登录名只能包含字母、数字和下划线")

    with get_db() as conn:
        # 检查登录名唯一性
        if conn.execute(
            "SELECT 1 FROM users WHERE login_name = ?", (req.login_name,)
        ).fetchone():
            raise HTTPException(status_code=400, detail="该登录名已被使用")
        # 检查邮箱唯一性
        if conn.execute(
            "SELECT 1 FROM users WHERE email = ?", (req.email,)
        ).fetchone():
            raise HTTPException(status_code=400, detail="该邮箱已被注册")

        new_id = str(uuid.uuid4())
        conn.execute(
            """INSERT INTO users
               (id, username, login_name, email, password_hash,
                company, department, role, status, avatar, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                new_id, req.username.strip(), req.login_name.strip(),
                req.email.strip(), _hash_password(req.password),
                req.company.strip(), req.department.strip(),
                "user", "pending", "",
                datetime.now(timezone(timedelta(hours=8))).replace(tzinfo=None).isoformat(),
            ),
        )

    # 记录日志
    _log_operation(None, "user_register", f"新用户注册：{req.username}（{req.login_name}）")

    return {"message": "注册成功！请等待管理员审批后即可登录。"}


@router.post("/login")
async def login(req: LoginRequest):
    """用户登录。验证密码后返回 JWT Token + 用户信息。"""
    user = _get_user_by_login(req.login_name)

    if not user:
        raise HTTPException(status_code=401, detail="登录名或密码错误")
    if not _verify_password(req.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="登录名或密码错误")
    if user["status"] == "pending":
        raise HTTPException(status_code=403, detail="账号正在等待管理员审批，请稍后再试")
    if user["status"] == "disabled":
        raise HTTPException(status_code=403, detail="账号已被禁用，请联系管理员")

    token = create_token(user["id"], user["role"])

    # 记录日志
    _log_operation(user["id"], "user_login", f"用户登录：{user['username']}")

    return {
        "token": token,
        "user": _safe_user(user),
    }


@router.get("/me")
async def get_me(user: dict = Depends(get_current_user)):
    """获取当前登录用户信息。"""
    return _safe_user(user)


@router.put("/me")
async def update_me(req: UpdateProfileRequest, user: dict = Depends(get_current_user)):
    """修改个人信息。"""
    with get_db() as conn:
        # 检查邮箱唯一性
        if req.email is not None:
            dup = conn.execute(
                "SELECT 1 FROM users WHERE email = ? AND id != ?",
                (req.email, user["id"]),
            ).fetchone()
            if dup:
                raise HTTPException(status_code=400, detail="该邮箱已被其他用户使用")

        updates = []
        params = []
        if req.username is not None:
            updates.append("username = ?")
            params.append(req.username.strip())
        if req.email is not None:
            updates.append("email = ?")
            params.append(req.email.strip())
        if req.company is not None:
            updates.append("company = ?")
            params.append(req.company.strip())
        if req.department is not None:
            updates.append("department = ?")
            params.append(req.department.strip())

        if updates:
            params.append(user["id"])
            conn.execute(
                f"UPDATE users SET {', '.join(updates)} WHERE id = ?",
                params,
            )

    updated = _get_user_by_id(user["id"])
    _log_operation(user["id"], "user_update_profile", f"修改个人信息：{user['username']}")
    return _safe_user(updated)


@router.put("/me/password")
async def change_password(req: ChangePasswordRequest, user: dict = Depends(get_current_user)):
    """修改密码。"""
    if req.new_password != req.confirm_password:
        raise HTTPException(status_code=400, detail="两次输入的新密码不一致")
    if len(req.new_password) < 6:
        raise HTTPException(status_code=400, detail="新密码长度不能少于 6 位")

    current = _get_user_by_id(user["id"])
    if not current:
        raise HTTPException(status_code=404, detail="用户未找到")
    if not _verify_password(req.old_password, current["password_hash"]):
        raise HTTPException(status_code=400, detail="原密码错误")

    with get_db() as conn:
        conn.execute(
            "UPDATE users SET password_hash = ? WHERE id = ?",
            (_hash_password(req.new_password), user["id"]),
        )

    _log_operation(user["id"], "user_change_password", f"修改密码：{user['username']}")
    return {"message": "密码修改成功"}


@router.post("/me/avatar")
async def upload_avatar(file: UploadFile = File(...), user: dict = Depends(get_current_user)):
    """上传头像。限制 10MB，仅支持图片格式。"""
    if file.content_type and not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="仅支持图片格式（jpg/png/gif/webp）")

    content = await file.read()
    if len(content) > AVATAR_MAX_SIZE:
        raise HTTPException(status_code=400, detail="头像文件大小不能超过 10MB")

    # WHY: 扩展名白名单校验，防止恶意构造的文件名（如 ../../evil.sh）
    ALLOWED_AVATAR_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".webp"}
    raw_ext = Path(file.filename or "avatar.png").suffix.lower()
    ext = raw_ext if raw_ext in ALLOWED_AVATAR_EXTS else ".png"
    avatar_filename = f"{user['id']}{ext}"
    avatar_path = (AVATARS_DIR / avatar_filename).resolve()
    # WHY: 防止路径穿越——确保解析后的路径仍在 AVATARS_DIR 内
    if not str(avatar_path).startswith(str(AVATARS_DIR.resolve())):
        raise HTTPException(status_code=403, detail="非法文件名")
    avatar_path.write_bytes(content)

    # 更新用户记录
    avatar_url = f"/api/auth/avatar/{avatar_filename}"
    with get_db() as conn:
        conn.execute(
            "UPDATE users SET avatar = ? WHERE id = ?",
            (avatar_url, user["id"]),
        )

    return {"avatar": avatar_url}


@router.get("/avatar/{filename}")
async def get_avatar(filename: str):
    """获取头像文件。"""
    from fastapi.responses import FileResponse
    avatar_path = AVATARS_DIR / filename
    if not avatar_path.exists():
        raise HTTPException(status_code=404, detail="头像不存在")
    return FileResponse(str(avatar_path))


# ===================== 操作日志 =====================

def _log_operation(user_id: str | None, action: str, detail: str):
    """
    兼容性代理——已迁移到 core.audit_log.log_operation。
    WHY: auth.py 内部仍有多处调用，保留此别名避免大规模改动。
    """
    from core.audit_log import log_operation
    log_operation(user_id, action, detail)
