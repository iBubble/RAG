# -*- coding: utf-8 -*-
"""
顶层编排器 (Orchestrator)。
WHY: 串联完整的多 Agent 协作链路：
     Supervisor 路由 → Worker 执行 → 小杠质疑 → 大BOSS 仲裁。
     这是对外暴露的唯一入口，API 层只需调用 orchestrator.run()。

协作链路：
  简单问题: Supervisor → direct_answer → 用户
  普通问题: Supervisor → Worker → 大BOSS 润色 → 用户
  复杂问题: Supervisor → Worker(s) → 小杠质疑 → 大BOSS 仲裁 → 用户
"""
from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from typing import Any, AsyncGenerator, Optional

from core.agents.blackboard import Blackboard, AgentEvent
from core.config import settings

logger = logging.getLogger(__name__)

# 简单回答长度阈值：低于此长度的回答跳过小杠/大BOSS
_SIMPLE_ANSWER_THRESHOLD = 100


@dataclass
class OrchestrationResult:
    """编排执行结果。"""
    final_answer: str = ""
    worker_answer: str = ""
    critique: str = ""
    agent_chain: list[str] = field(default_factory=list)
    events: list[dict] = field(default_factory=list)
    elapsed_seconds: float = 0.0
    error: Optional[str] = None


async def _enrich_message_with_context(user_message: str, project_id: str, file_ids: list[str]) -> str:
    """拼装项目名和文档列表背景，使 Supervisor 能做出正确的 RAG 路由选择。"""
    project_context = ""
    if project_id:
        try:
            from core.project_access import _read_projects
            for p in _read_projects():
                if p["id"] == project_id:
                    project_context += f"当前项目/案卷名称：{p['name']}\n"
                    break
        except Exception:
            pass

    if file_ids:
        try:
            from core.vector_store import get_file_metadata_multi_level
            meta_map = get_file_metadata_multi_level(file_ids, project_id)
            file_names = []
            for fid in file_ids:
                meta = meta_map.get(fid)
                if meta and meta.get("filename"):
                    file_names.append(meta["filename"])
            
            if file_names:
                unique_names = list(dict.fromkeys(file_names))
                project_context += "当前已勾选关联以下文档作为知识库参考，如果问题与这些文档、案情、或专业主题相关，请调用 ask_rag_agent 以检索文档内容：\n"
                for fn in unique_names:
                    project_context += f"- {fn}\n"
        except Exception as e:
            logger.warning(f"拼装文档背景失败: {e}")

    if project_context:
        return f"【系统背景】\n{project_context}\n【用户问题】\n{user_message}"
    return user_message


async def run_orchestration(
    user_message: str,
    project_id: str = "",
    file_ids: Optional[list[str]] = None,
    model: str = settings.DEFAULT_LLM_MODEL,
    enable_critique: bool = True,
    blackboard: Optional[Blackboard] = None,
) -> OrchestrationResult:
    """
    执行完整的多 Agent 协作链。

    Args:
        user_message: 用户原始消息
        project_id: 项目 ID
        file_ids: 文件 ID 列表
        model: Worker Agent 使用的模型
        enable_critique: 是否启用小杠质疑环节
        blackboard: 共享记忆黑板（可选）

    Returns:
        OrchestrationResult 包含最终回答和协作过程信息
    """
    from api.admin import _read_system_settings
    sys_settings = _read_system_settings()
    name_supervisor = sys_settings.get("collab_supervisor_name", "【协同】文档秘书")
    name_legal = sys_settings.get("collab_legal_name", "【协同】法律分析专家")
    name_contrarian = sys_settings.get("collab_contrarian_name", "【协同】审查员")
    name_arbiter = sys_settings.get("collab_arbiter_name", "【协同】仲裁官")

    t0 = time.time()
    bb = blackboard or Blackboard()
    ctx = {
        "project_id": project_id,
        "file_ids": file_ids or [],
        "model": model,
    }

    result = OrchestrationResult()

    # ── Step 1: Supervisor 路由决策 ──
    await bb.log_event(AgentEvent(
        "supervisor", "routing", f"🧠 {name_supervisor} 正在分析任务类型..."
    ))

    enriched_msg = await _enrich_message_with_context(user_message, project_id, file_ids or [])

    from core.agents.supervisor import SupervisorAgent
    supervisor = SupervisorAgent()
    sup_result = await supervisor.run(enriched_msg, context=ctx)

    result.agent_chain.append("supervisor")
    result.worker_answer = sup_result.content or ""

    if sup_result.error:
        result.error = f"Supervisor 错误: {sup_result.error}"
        result.final_answer = "⚠️ 系统编排出现异常，请稍后重试。"
        result.elapsed_seconds = time.time() - t0
        return result

    # 记录 Supervisor 调用了哪些 Worker
    for tc in sup_result.tool_calls_log:
        tool_name = tc.get("tool", "")
        await bb.log_event(AgentEvent(
            tool_name.replace("ask_", ""),
            "executing",
            f"📋 正在执行: {tool_name}",
        ))
        result.agent_chain.append(tool_name)

    worker_answer = sup_result.content
    await bb.write("supervisor", "worker_answer", worker_answer[:5000])

    # ── 判断是否需要小杠 + 大BOSS ──
    has_expert_tool = any(tc.get("tool", "") != "direct_answer" for tc in sup_result.tool_calls_log)
    is_simple = (
        not enable_critique
        or len(worker_answer) < _SIMPLE_ANSWER_THRESHOLD
        or not has_expert_tool
    )

    if is_simple:
        # 简单回答，直接返回
        result.final_answer = worker_answer
        result.elapsed_seconds = time.time() - t0
        result.events = await bb.get_events()
        return result

    # ── Step 2: 小杠质疑 ──
    await bb.log_event(AgentEvent(
        "contrarian", "critiquing", f"🤨 {name_contrarian} 正在审查回答..."
    ))

    from core.agents.contrarian_agent import ContrarianAgent
    contrarian = ContrarianAgent()
    critique = await contrarian.critique(user_message, worker_answer, context=ctx)

    result.critique = critique
    result.agent_chain.append("contrarian")
    await bb.write("contrarian", "critique", critique[:3000])

    await bb.log_event(AgentEvent(
        "contrarian", "done",
        "✅ 审查完成" if "审查通过" in critique else "⚠️ 发现问题",
    ))

    # ── Step 3: 大BOSS 仲裁 ──
    await bb.log_event(AgentEvent(
        "arbiter", "deciding", f"👑 {name_arbiter} 正在做最终决策..."
    ))

    from core.agents.arbiter_agent import ArbiterAgent
    arbiter = ArbiterAgent()

    # 确定执行的 Worker 名称
    worker_name = "知识检索专家"
    for tc in sup_result.tool_calls_log:
        tn = tc.get("tool", "")
        if "rag" in tn:
            worker_name = "知识检索专家"
        elif "legal" in tn:
            worker_name = name_legal
        elif "service" in tn:
            worker_name = "企业法律顾问"
        elif "data" in tn:
            worker_name = "数据分析专家"

    final_answer = await arbiter.arbitrate(
        user_message, worker_answer, critique, worker_name
    )

    result.final_answer = final_answer
    result.agent_chain.append("arbiter")
    result.elapsed_seconds = time.time() - t0

    await bb.log_event(AgentEvent(
        "arbiter", "done", f"👑 {name_arbiter} 最终决策完成"
    ))

    result.events = await bb.get_events()

    logger.info(
        f"[Orchestrator] 协作链完成 | "
        f"chain={' → '.join(result.agent_chain)} | "
        f"耗时={result.elapsed_seconds:.1f}s"
    )

    return result


async def run_orchestration_stream(
    user_message: str,
    project_id: str = "",
    file_ids: Optional[list[str]] = None,
    model: str = settings.DEFAULT_LLM_MODEL,
    enable_critique: bool = True,
) -> AsyncGenerator[str, None]:
    """
    流式版编排器 — 用于 SSE 推送。
    WHY: 前端需要实时展示 Agent 协作过程和最终回答。
    推送格式: data: {"type": "event|token|done", ...}
    """
    from api.admin import _read_system_settings
    sys_settings = _read_system_settings()
    name_supervisor = sys_settings.get("collab_supervisor_name", "【协同】文档秘书")
    name_legal = sys_settings.get("collab_legal_name", "【协同】法律分析专家")
    name_contrarian = sys_settings.get("collab_contrarian_name", "【协同】审查员")
    name_arbiter = sys_settings.get("collab_arbiter_name", "【协同】仲裁官")

    bb = Blackboard()
    ctx = {"project_id": project_id, "file_ids": file_ids or [], "model": model}

    # 推送协作事件的辅助函数
    def _event_sse(agent: str, status: str, msg: str) -> str:
        return f"data: {json.dumps({'type': 'agent_event', 'agent': agent, 'status': status, 'message': msg}, ensure_ascii=False)}\n\n"

    yield _event_sse("supervisor", "routing", f"🧠 {name_supervisor} 正在分析任务...")

    # Step 1: Supervisor
    enriched_msg = await _enrich_message_with_context(user_message, project_id, file_ids or [])

    from core.agents.supervisor import SupervisorAgent
    supervisor = SupervisorAgent()
    sup_result = await supervisor.run(enriched_msg, context=ctx)

    if sup_result.error:
        yield f"data: {json.dumps({'type': 'token', 'content': '⚠️ 系统编排异常'}, ensure_ascii=False)}\n\n"
        yield f"data: {json.dumps({'type': 'done'})}\n\n"
        return

    tool_name_map = {
        "rag_agent": "【协同】知识检索助手",
        "direct_answer": "【协同】直答助手"
    }
    for tc in sup_result.tool_calls_log:
        tn = tc.get("tool", "").replace("ask_", "")
        display_name = tool_name_map.get(tn, tn)
        yield _event_sse(tn, "executing", f"📋 {display_name} 正在执行...")

    worker_answer = sup_result.content or ""

    # 简单回答直接推送
    has_expert_tool = any(tc.get("tool", "") != "direct_answer" for tc in sup_result.tool_calls_log)
    is_simple = (
        not enable_critique
        or len(worker_answer) < _SIMPLE_ANSWER_THRESHOLD
        or not has_expert_tool
    )

    if is_simple:
        yield f"data: {json.dumps({'type': 'token', 'content': worker_answer}, ensure_ascii=False)}\n\n"
        yield f"data: {json.dumps({'type': 'done'})}\n\n"
        return

    # Step 2: 小杠
    yield _event_sse("contrarian", "critiquing", f"🤨 {name_contrarian} 正在审查...")

    from core.agents.contrarian_agent import ContrarianAgent
    contrarian = ContrarianAgent()
    critique = await contrarian.critique(user_message, worker_answer, context=ctx)

    critique_status = "✅ 通过" if "审查通过" in critique else "⚠️ 有质疑"
    yield _event_sse("contrarian", "done", critique_status)

    # Step 3: 大BOSS 流式仲裁
    yield _event_sse("arbiter", "deciding", f"👑 {name_arbiter} 正在做最终决策...")

    from core.agents.arbiter_agent import ArbiterAgent
    arbiter = ArbiterAgent()

    async for token in arbiter.arbitrate_stream(
        user_message, worker_answer, critique, name_legal
    ):
        yield f"data: {json.dumps({'type': 'token', 'content': token}, ensure_ascii=False)}\n\n"

    yield _event_sse("arbiter", "done", "👑 决策完成")
    yield f"data: {json.dumps({'type': 'done'})}\n\n"
