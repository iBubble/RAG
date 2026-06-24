"""
JWT 认证依赖注入模块。
WHY: 统一管理 Token 生成/验证逻辑，以 FastAPI Dependency 形式注入各路由。
"""
from __future__ import annotations

import os
import jwt
from datetime import datetime, timedelta, timezone
from fastapi import Depends, HTTPException, Query, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

# WHY: JWT 密钥必须从环境变量读取，禁止硬编码在源码中。
#      硬编码密钥意味着任何能看到源码的人都能伪造 admin Token。
JWT_SECRET = os.environ.get("JWT_SECRET")
if not JWT_SECRET:
    raise RuntimeError("JWT_SECRET environment variable is not set. Please set it before starting the application.")
JWT_ALGORITHM = "HS256"
JWT_EXPIRATION_HOURS = 168  # WHY: 改为7天，防止用户长期不关控制台导致写作中断

security = HTTPBearer(auto_error=False)

def create_token(user_id: str, role: str) -> str:
    """生成 JWT Token，有效期 7 天。"""
    payload = {
        "sub": user_id,
        "role": role,
        "exp": datetime.now(timezone.utc) + timedelta(hours=JWT_EXPIRATION_HOURS),
        "iat": datetime.now(timezone.utc),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)

def decode_token(token: str) -> dict:
    """解码并验证 JWT Token。"""
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token 已过期，请重新登录")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="无效的 Token")

import logging

async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
    token: str = Query(None, description="Support for SSE where headers cannot be set")
) -> dict:
    """
    FastAPI Dependency：从请求头解析 JWT Token，返回当前用户信息。
    WHY: 所有需要身份验证的路由都注入此依赖。
    """
    raw_token = token if token else (credentials.credentials if credentials else None)
    if not raw_token:
        raise HTTPException(status_code=401, detail="未提供认证凭据")
    
    try:
        payload = decode_token(raw_token)
    except Exception as e:
        raise
    
    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="Token 无效")
    
    # WHY: 直接从 SQLite 查询单用户，避免 core → api 的跨层导入
    from core.database import get_db, dict_from_row
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM users WHERE id = ?", (user_id,)
        ).fetchone()
    user = dict_from_row(row)
    if not user:
        raise HTTPException(status_code=401, detail="用户不存在")
    if user["status"] == "disabled":
        raise HTTPException(status_code=403, detail="账号已被禁用")
    if user["status"] == "pending":
        raise HTTPException(status_code=403, detail="账号待审批，请联系管理员")
    
    return user

async def require_admin(user: dict = Depends(get_current_user)) -> dict:
    """FastAPI Dependency：要求当前用户为管理员角色。"""
    if user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="需要管理员权限")
    return user

async def get_optional_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(security),
) -> dict | None:
    """
    FastAPI Dependency：可选认证。有 Token 返回用户，无 Token 返回 None。
    WHY: 用于既支持游客又支持登录用户的接口（如获取公开项目列表）。
    """
    if credentials is None:
        return None
    try:
        payload = decode_token(credentials.credentials)
        user_id = payload.get("sub")
        if not user_id:
            return None
        from core.database import get_db, dict_from_row
        with get_db() as conn:
            row = conn.execute(
                "SELECT * FROM users WHERE id = ?", (user_id,)
            ).fetchone()
        user = dict_from_row(row)
        if user and user["status"] == "active":
            return user
        return None
    except Exception:
        return None
