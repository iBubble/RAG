from __future__ import annotations

import os
os.environ["HF_HUB_OFFLINE"] = os.getenv("HF_HUB_OFFLINE", "0")

# ── onnxruntime 阻断器（必须在所有其他 import 之前执行） ──
import core.onnx_blocker  # noqa: F401

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response


class Utf8CharsetMiddleware(BaseHTTPMiddleware):
    """强制所有 JSON 响应声明 charset=utf-8。

    WHY: FRP 代理 + 服务端 Nginx 转发时，如果 Content-Type 缺少 charset，
    中间环节可能按系统默认编码（如 latin-1）重解释字节流，导致中文乱码。
    """

    async def dispatch(self, request: Request, call_next) -> Response:
        response = await call_next(request)
        ct = response.headers.get("content-type", "")
        if "application/json" in ct and "charset" not in ct:
            response.headers["content-type"] = "application/json; charset=utf-8"
        return response
from core.config import settings
from core.watchdog import ReadOnlyMiddleware, start_watchdog
from api.files import router as files_router
from api.ingest import router as ingest_router
from api.generate import router as generate_router
from api.export import router as export_router
from api.template import router as template_router
from api.exemplar import router as exemplar_router
from api.projects import router as projects_router
from api.auth import router as auth_router
from api.admin import router as admin_router
from api.web_ingest import router as web_ingest_router
from api.knowledge import router as knowledge_router
from api.legal import router as legal_router

import asyncio
from contextlib import asynccontextmanager


@asynccontextmanager
async def lifespan(application: FastAPI):
    """
    FastAPI Lifespan 管理器。
    WHY: 替代已废弃的 @app.on_event("startup")，兼容 FastAPI 0.100+。
    """
    # ── Startup ──
    start_watchdog()

    # ── 数据库设置热修复 ──
    try:
        from core.database import get_db
        with get_db() as conn:
            conn.execute(
                "UPDATE system_settings SET value = ? WHERE key = 'collab_arbiter_model'",
                (settings.COLLAB_LLM_MODEL,)
            )
            conn.commit()
    except Exception as e:
        import logging
        logging.getLogger("startup").warning(f"数据库热修复 collab_arbiter_model 失败: {e}")

    from core.llm_engine import warmup_model, start_model_heartbeat

    async def _warmup_and_heartbeat():
        await warmup_model()
        await start_model_heartbeat()

    asyncio.create_task(_warmup_and_heartbeat())

    async def _preload_embedding():
        import logging
        _logger = logging.getLogger("startup")
        try:
            from core.vector_store import (
                _get_dense_model, _get_sparse_model, ensure_collection
            )
            _logger.info("🧠 BGE-M3 Embedding 预加载启动...")
            ensure_collection()
            _get_dense_model()
            _get_sparse_model()
            _logger.info("🧠 BGE-M3 Embedding 预加载完成 (Dense 1024d + Sparse)")
        except Exception as e:
            _logger.error(f"BGE-M3 预加载失败: {e}")
        _logger.info("🔄 Reranker: 已切换为 LLM Reranker（按需调用 Ollama，无需预加载）")

    asyncio.create_task(_preload_embedding())

    from core.ssl_checker import check_and_renew_ssl
    asyncio.create_task(check_and_renew_ssl())

    # ── 定时指标采集（每 10 分钟自动写入 metrics_history） ──
    async def _metrics_collector():
        """
        WHY: 后台独立定时采集，不依赖前端是否打开「系统状态」页面。
             确保 7×24 小时持续积累趋势数据，使曲线图有意义。
        """
        import logging
        _log = logging.getLogger("metrics_collector")
        # 启动后等 60 秒再开始，避免与 warmup 阶段竞争资源
        await asyncio.sleep(60)
        _log.info("📊 指标定时采集器已启动（间隔 10 分钟）")
        while True:
            try:
                from api.admin import _collect_and_save_snapshot
                _collect_and_save_snapshot()
            except Exception as e:
                _log.warning(f"指标采集异常: {e}")
            await asyncio.sleep(600)  # 10 分钟

    asyncio.create_task(_metrics_collector())

    yield
    # ── Shutdown ── (如有清理逻辑可在此添加)


app = FastAPI(
    title="ShengyaoRAG Backend",
    version="1.0.0",
    lifespan=lifespan,
)

# 配置 CORS 允许跨域
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOW_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# WHY: FRP 公网代理转发 JSON 时，缺少 charset=utf-8 导致中文乱码
app.add_middleware(Utf8CharsetMiddleware)

# 加入外部挂载盘守护熔断器
app.add_middleware(ReadOnlyMiddleware)

# 挂载路由
app.include_router(auth_router)
app.include_router(admin_router)
app.include_router(files_router)
app.include_router(ingest_router)
app.include_router(generate_router)
app.include_router(export_router)
app.include_router(template_router)
app.include_router(exemplar_router)
app.include_router(projects_router)
app.include_router(web_ingest_router)
app.include_router(knowledge_router)
app.include_router(legal_router)


@app.get("/health")
async def health_check():
    # WHY: 追加 Celery Worker 队列状态，方便运维监控
    #       fast/slow 两个独立 Worker 的活跃/保留任务数
    celery_status = {"fast_tasks": None, "slow_tasks": None}
    try:
        from core.celery_app import celery_app
        inspect = celery_app.control.inspect(timeout=2.0)
        active = inspect.active() or {}
        reserved = inspect.reserved() or {}
        celery_status = {
            "active_tasks": sum(len(v) for v in active.values()),
            "reserved_tasks": sum(len(v) for v in reserved.values()),
            "worker_hosts": list(active.keys()),
        }
    except Exception:
        pass  # Celery 未完全启动时静默

    return {
        "status": "ok",
        "version": app.version,
        "celery": celery_status,
    }