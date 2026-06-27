from __future__ import annotations
import os
import logging
from typing import List
from pydantic_settings import BaseSettings, SettingsConfigDict

# WHY: 强制清除所有被 Docker Desktop 意外注入的代理变量
for _k in list(os.environ.keys()):
    if "proxy" in _k.lower() and _k.lower() not in ("no_proxy",):
        del os.environ[_k]
        
_LOCAL_ROOT = "/Volumes/macData/RAG_Files"
os.makedirs(_LOCAL_ROOT, exist_ok=True)
STORAGE_ROOT = _LOCAL_ROOT
IS_RAID_ACTIVE = False

class Settings(BaseSettings):
    # Pydantic v2 config
    model_config = SettingsConfigDict(
        env_file=os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env"), 
        extra="ignore", 
        case_sensitive=False
    )

    APP_NAME: str = "LiukunRAG Backend"
    FRONTEND_URL: str = "http://localhost:8008"
    ALLOW_ORIGINS: list[str] = ["http://localhost:8008", "https://rag.syhsgis.com"]
    
    OLLAMA_BASE_URL: str = "http://host.docker.internal:11434"
    DEFAULT_LLM_MODEL: str = "qwen3.6:35b-q4"
    COLLAB_LLM_MODEL: str = "qwen3:8b"
    CHROMA_DB_PATH: str = "/app/vector_db"
    QDRANT_URL: str = "http://localhost:6333"
    REDIS_URL: str = "redis://localhost:6379/0"

    REDIS_CACHE_DB: int = 1
    SLOT_CACHE_TTL: int = 604800
    DRAFT_CACHE_TTL: int = 259200

    # ── Chat 对话缓存配置 ──
    # WHY: L1 缓存检索结果（节省 5-15s），L2 缓存完整回答（< 100ms 返回）
    CHAT_CACHE_ENABLED: bool = True
    CHAT_RAG_CACHE_TTL: int = 1800      # L1 检索缓存 TTL（秒），30分钟
    CHAT_ANSWER_CACHE_TTL: int = 3600   # L2 回答缓存 TTL（秒），1小时



    SLOT_FILLING_V2: bool = False
    SLOT_PRECOMPUTE: bool = True
    SLOT_PRECOMPUTE_DEBOUNCE: int = 30
    DRAFT_PRECOMPUTE: bool = True

    UPLOAD_DIR: str = f"{STORAGE_ROOT}/uploads"
    # WHY: 核心元数据（生成的文档、模板等）优先存放在 RAID 卷的 data/ 目录下以保证持久性。
    DATA_DIR: str = os.path.join(STORAGE_ROOT, "data") if IS_RAID_ACTIVE else f"{_LOCAL_ROOT}/data"

    JWT_SECRET: str = "FALLBACK_INSECURE_KEY_CHECK_ENV"
    ADMIN_INIT_PASSWORD: str = "changeme"
    NEO4J_URI: str = "bolt://genrag-graphdb:7687"
    NEO4J_USER: str = "neo4j"
    NEO4J_PASSWORD: str = "syrag_secure_pwd"

settings = Settings()
