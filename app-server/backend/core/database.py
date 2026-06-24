"""
SQLite 数据访问层（DAL）。
WHY: 替代分散的 JSON 文件持久化，使用 SQLite WAL 模式消除
     read-modify-write 竞态条件，同时保持同步 API 向后兼容。
"""
from __future__ import annotations

import sqlite3
import logging
from pathlib import Path
from contextlib import contextmanager

from core.config import settings, STORAGE_ROOT

logger = logging.getLogger(__name__)

# WHY: 放在 RAID 卷根目录下，与 uploads 同级，容量充裕
DB_PATH = Path(STORAGE_ROOT) / "shengyao.db"

# ── Schema DDL ──────────────────────────────────────────────

_SCHEMA_SQL = """
-- 用户表
CREATE TABLE IF NOT EXISTS users (
    id            TEXT PRIMARY KEY,
    username      TEXT NOT NULL,
    login_name    TEXT UNIQUE NOT NULL,
    email         TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    company       TEXT DEFAULT '',
    department    TEXT DEFAULT '',
    role          TEXT DEFAULT 'user',
    status        TEXT DEFAULT 'pending',
    avatar        TEXT DEFAULT '',
    created_at    TEXT NOT NULL
);

-- 项目表
CREATE TABLE IF NOT EXISTS projects (
    id            TEXT PRIMARY KEY,
    name          TEXT NOT NULL,
    created_at    TEXT NOT NULL,
    source_count  INTEGER DEFAULT 0,
    owner_id      TEXT NOT NULL,
    owner_name    TEXT DEFAULT '',
    visibility    TEXT DEFAULT 'public',
    metadata_json TEXT DEFAULT '{}',
    project_type  TEXT DEFAULT 'case',
    icon          TEXT DEFAULT '',
    sort_order    INTEGER DEFAULT 0,
    priority      INTEGER DEFAULT 2,
    is_paused     INTEGER DEFAULT 0
);

-- 操作日志表
CREATE TABLE IF NOT EXISTS operation_logs (
    id        TEXT PRIMARY KEY,
    user_id   TEXT,
    action    TEXT NOT NULL,
    detail    TEXT DEFAULT '',
    timestamp TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_logs_user   ON operation_logs(user_id);
CREATE INDEX IF NOT EXISTS idx_logs_action ON operation_logs(action);
CREATE INDEX IF NOT EXISTS idx_logs_time   ON operation_logs(timestamp);

-- 网络来源表
CREATE TABLE IF NOT EXISTS web_sources (
    id          TEXT PRIMARY KEY,
    project_id  TEXT NOT NULL,
    title       TEXT DEFAULT '',
    url         TEXT DEFAULT '',
    source_type TEXT DEFAULT 'web',
    text_length INTEGER DEFAULT 0,
    chunks      INTEGER DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_ws_project ON web_sources(project_id);

-- 系统设置表（KV 结构）
CREATE TABLE IF NOT EXISTS system_settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

-- 公共文档引用表
-- WHY: 记录普通案件与公共文档库之间的引用关系，
--      实现跨项目文档共享（只读引用，不复制文件）。
CREATE TABLE IF NOT EXISTS project_refs (
    id          TEXT PRIMARY KEY,
    case_id     TEXT NOT NULL,      -- 引用方案件的 project_id
    library_id  TEXT NOT NULL,      -- 被引用的公共文档 project_id
    file_ids    TEXT DEFAULT '[]',  -- JSON 数组，选中的文件 ID 列表
    created_at  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_refs_case ON project_refs(case_id);
CREATE INDEX IF NOT EXISTS idx_refs_lib  ON project_refs(library_id);

-- 聊天历史记录表
CREATE TABLE IF NOT EXISTS chat_history (
    project_id    TEXT NOT NULL,
    user_id       TEXT NOT NULL,
    messages_json TEXT NOT NULL,
    updated_at    TEXT NOT NULL,
    PRIMARY KEY (project_id, user_id)
);

-- 全文检索虚拟表
CREATE VIRTUAL TABLE IF NOT EXISTS doc_chunks_fts USING fts5(
    id,
    file_id,
    project_id,
    filename,
    chunk_index,
    document,
    tokenize='unicode61'
);

-- 系统指标历史快照表
-- WHY: 定期采集核心存储指标（向量数、图谱实体/关系/社区、Redis 内存/键数），
--      前端以折线图形式展示趋势变化，帮助管理员直观感知数据增长。
CREATE TABLE IF NOT EXISTS metrics_history (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    recorded_at TEXT NOT NULL,
    vectors     INTEGER DEFAULT 0,
    entities    INTEGER DEFAULT 0,
    relations   INTEGER DEFAULT 0,
    communities INTEGER DEFAULT 0,
    redis_mem_mb REAL DEFAULT 0,
    redis_keys  INTEGER DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_mh_time ON metrics_history(recorded_at);
"""


def _init_db():
    """初始化数据库文件和表结构。"""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    # WHY: WAL 模式允许多个读连接与一个写连接并发，
    #      比默认的 DELETE journal 模式吞吐量高 5~10 倍。
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.executescript(_SCHEMA_SQL)

    # ── 增量迁移：projects 表添加 project_type 字段 ──
    # WHY: 区分普通案件(case)和公共文档库(library)，
    #      旧数据默认为 'case'，新建公共文档库时设为 'library'。
    try:
        cols = [r[1] for r in conn.execute("PRAGMA table_info(projects)").fetchall()]
        if "project_type" not in cols:
            conn.execute("ALTER TABLE projects ADD COLUMN project_type TEXT DEFAULT 'case'")
            logger.info("迁移完成: projects 表新增 project_type 字段")
    except Exception as e:
        logger.warning(f"project_type 迁移检查失败(非致命): {e}")

    # ── 增量迁移：projects 表添加 icon 字段 ──
    # WHY: 允许用户为项目选择自定义 emoji 图标。
    try:
        cols = [r[1] for r in conn.execute("PRAGMA table_info(projects)").fetchall()]
        if "icon" not in cols:
            conn.execute("ALTER TABLE projects ADD COLUMN icon TEXT DEFAULT ''")
            logger.info("迁移完成: projects 表新增 icon 字段")
    except Exception as e:
        logger.warning(f"icon 迁移检查失败(非致命): {e}")

    # ── 增量迁移：projects 表添加 sort_order 字段 ──
    # WHY: 支持项目卡片的拖拽排序。
    try:
        cols = [r[1] for r in conn.execute("PRAGMA table_info(projects)").fetchall()]
        if "sort_order" not in cols:
            conn.execute("ALTER TABLE projects ADD COLUMN sort_order INTEGER DEFAULT 0")
            logger.info("迁移完成: projects 表新增 sort_order 字段")
    except Exception as e:
        logger.warning(f"sort_order 迁移检查失败(非致命): {e}")

    # ── 增量迁移：projects 表添加 priority 字段 ──
    # WHY: 引入项目/案件的优先级，默认为 2（1最优先，2其次，3最末）。
    try:
        cols = [r[1] for r in conn.execute("PRAGMA table_info(projects)").fetchall()]
        if "priority" not in cols:
            conn.execute("ALTER TABLE projects ADD COLUMN priority INTEGER DEFAULT 2")
            logger.info("迁移完成: projects 表新增 priority 字段")
    except Exception as e:
        logger.warning(f"priority 迁移检查失败(非致命): {e}")

    # ── 增量迁移：projects 表添加 is_paused 字段 ──
    # WHY: 允许暂停项目的后台学习。
    try:
        cols = [r[1] for r in conn.execute("PRAGMA table_info(projects)").fetchall()]
        if "is_paused" not in cols:
            conn.execute("ALTER TABLE projects ADD COLUMN is_paused INTEGER DEFAULT 0")
            logger.info("迁移完成: projects 表新增 is_paused 字段")
    except Exception as e:
        logger.warning(f"is_paused 迁移检查失败(非致命): {e}")

    conn.commit()
    conn.close()
    logger.info(f"SQLite 数据库已就绪: {DB_PATH}")


# 启动时自动初始化
_init_db()


@contextmanager
def get_db():
    """
    获取一个 SQLite 连接（上下文管理器）。
    用法:
        with get_db() as conn:
            conn.execute("INSERT INTO ...")
    WHY: 自动 commit / rollback / close，
         防止连接泄漏和未提交事务。
    """
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row  # WHY: 让 fetchone/fetchall 返回类 dict 对象
    # WHY: WAL 模式已在 _init_db() 中全局设置，此处无需重复
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def dict_from_row(row: sqlite3.Row | None) -> dict | None:
    """将 sqlite3.Row 转为普通 dict。"""
    if row is None:
        return None
    return dict(row)


def insert_fts_chunks(chunks_data: list[dict]) -> None:
    """批量插入 chunks 到全文检索虚拟表中。"""
    if not chunks_data:
        return
    with get_db() as conn:
        conn.executemany(
            "INSERT INTO doc_chunks_fts (id, file_id, project_id, filename, chunk_index, document) VALUES (?, ?, ?, ?, ?, ?)",
            [
                (
                    c["id"],
                    c["file_id"],
                    c["project_id"],
                    c["filename"],
                    c["chunk_index"],
                    c["document"]
                )
                for c in chunks_data
            ]
        )


def delete_fts_by_file_id(file_id: str) -> None:
    """从全文检索表中删除指定文件的 chunks。"""
    with get_db() as conn:
        conn.execute("DELETE FROM doc_chunks_fts WHERE file_id = ?", (file_id,))


def delete_fts_by_project_id(project_id: str) -> None:
    """从全文检索表中删除指定项目的 chunks。"""
    with get_db() as conn:
        conn.execute("DELETE FROM doc_chunks_fts WHERE project_id = ?", (project_id,))


def search_fts(query: str, project_id: str, file_ids: list[str] | None = None, limit: int = 20) -> list[dict]:
    """在全文检索表中执行关键词检索。"""
    if not query.strip():
        return []
    # WHY: FTS5 MATCH 语法支持 AND/OR/NOT/NEAR 等操作符，
    #      恶意用户可注入操作符干扰搜索结果。
    #      移除所有 FTS5 特殊操作符和语法字符后再用双引号包裹为精确短语匹配。
    import re
    clean_query = query.strip()
    # 移除 FTS5 操作符关键词（大小写不敏感）
    clean_query = re.sub(r'\b(AND|OR|NOT|NEAR)\b', ' ', clean_query, flags=re.IGNORECASE)
    # 移除 FTS5 特殊语法字符：* ^ "
    clean_query = re.sub(r'[*^"\'()]', ' ', clean_query)
    clean_query = ' '.join(clean_query.split()).strip()
    # 如果是空或只有特殊字符，跳过
    if not clean_query:
        return []
    # 使用双引号包裹支持按词组或单字匹配
    fts_query = f'"{clean_query}"'
    sql = "SELECT id, file_id, project_id, filename, chunk_index, document FROM doc_chunks_fts WHERE doc_chunks_fts MATCH ? AND project_id = ?"
    params = [fts_query, project_id]
    if file_ids:
        placeholders = ",".join(["?"] * len(file_ids))
        sql += f" AND file_id IN ({placeholders})"
        params.extend(file_ids)
    sql += " LIMIT ?"
    params.append(limit)
    with get_db() as conn:
        try:
            rows = conn.execute(sql, params).fetchall()
            return [dict(r) for r in rows]
        except Exception as e:
            logger.warning(f"FTS 搜索出错: {e}，尝试退回到裸词匹配")
            # 降级到模糊匹配搜索
            sql_fallback = "SELECT id, file_id, project_id, filename, chunk_index, document FROM doc_chunks_fts WHERE document LIKE ? AND project_id = ?"
            fallback_params = [f"%{clean_query}%", project_id]
            if file_ids:
                placeholders = ",".join(["?"] * len(file_ids))
                sql_fallback += f" AND file_id IN ({placeholders})"
                fallback_params.extend(file_ids)
            sql_fallback += " LIMIT ?"
            fallback_params.append(limit)
            try:
                rows = conn.execute(sql_fallback, fallback_params).fetchall()
                return [dict(r) for r in rows]
            except Exception as e2:
                logger.error(f"FTS 降级搜索依然失败: {e2}")
                return []
