"""
RAG 审计追踪写入工具 — 升级计划 D8。

WHY: 每次 RAG 查询的完整执行轨迹（检索文档、模型响应、
     Ragas 三元组评分）需持久化到 SQLite，用于合规审计
     和质量回溯。
"""
from __future__ import annotations
import logging
import uuid
from typing import Optional

from core.database import get_db

logger = logging.getLogger(__name__)


def write_audit_trace(
    user_query: str,
    llm_response: str,
    project_id: str = "",
    session_id: str = "",
    retrieved_docs: str = "",
    dag_node: str = "",
    context_relevance: Optional[float] = None,
    groundedness: Optional[float] = None,
    answer_relevance: Optional[float] = None,
    audit_status: str = "pending",
    auditor_comment: str = "",
    frozen_state: str = "",
    trace_id: Optional[str] = None,
) -> str:
    """
    写入一条审计追踪记录。

    Returns:
        生成的 trace_id
    """
    if not trace_id:
        trace_id = str(uuid.uuid4())
    try:
        with get_db() as db:
            db.execute(
                """INSERT OR REPLACE INTO audit_traces
                (trace_id, session_id, project_id,
                 user_query, retrieved_docs,
                 llm_response, dag_node,
                 context_relevance, groundedness,
                 answer_relevance, audit_status,
                 auditor_comment, frozen_state)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    trace_id,
                    session_id,
                    project_id,
                    user_query,
                    retrieved_docs,
                    llm_response,
                    dag_node,
                    context_relevance,
                    groundedness,
                    answer_relevance,
                    audit_status,
                    auditor_comment,
                    frozen_state,
                ),
            )
        logger.info(
            f"✅ 审计记录写入: {trace_id[:8]}..."
        )

        try:
            from langfuse import Langfuse
            lf = Langfuse()
            # 兼容新版 SDK 4.x (Observation-centric)
            # OTel Trace ID 规范要求为 32 位十六进制小写字符串，需移除 UUID 的连字符
            clean_trace_id = trace_id.replace("-", "") if trace_id else None
            lf.start_observation(
                trace_context={"trace_id": clean_trace_id} if clean_trace_id else None,
                name="RAG_Audit_Trace",
                as_type="span",
                input=user_query,
                output=llm_response,
                metadata={
                    "project_id": project_id,
                    "dag_node": dag_node,
                    "context_relevance": context_relevance,
                    "groundedness": groundedness,
                    "answer_relevance": answer_relevance,
                    "audit_status": audit_status,
                    "session_id": session_id or project_id,
                }
            )
            lf.flush()
        except Exception as lfe:
            logger.warning(f"⚠️ Langfuse trace fail: {lfe}")

        return trace_id
    except Exception as e:
        logger.error(f"❌ 审计记录写入失败: {e}")
        raise
