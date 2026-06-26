"""
FastAPI 路由 (api/legal.py)
WHY: 暴露法律助理技能与多阶段流式起草接口。
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
import re
from typing import AsyncGenerator
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from core.auth_deps import get_current_user
from core.config import settings
from core.legal_assistant import generate_legal_stage, inject_contract_comments
from core.legal_prompts import CONTRACT_REVIEW_PROMPT
from core.llm_engine import stream_ollama
from core.retrieval_pipeline import run_retrieval

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/legal", tags=["Legal Assistant"])

# ── Pydantic 请求体定义 ───────────────────────────────────

class WorkflowRequest(BaseModel):
    project_id: str
    file_ids: list[str]
    skill_type: str  # "pleading" 或 "complaint"
    stage_id: str
    context_history: str = ""
    collaborative: bool = False

class ContractReviewRequest(BaseModel):
    file_path: str  # 相对于 uploads 根目录的相对路径
    project_id: str
    collaborative: bool = False
    file_ids: list[str] = []

# ── API 路由实现 ──────────────────────────────────────────

@router.get("/skills")
async def list_legal_skills(user: dict = Depends(get_current_user)):
    """获取所有支持的 AI 法律技能及其各分析阶段。"""
    return {
        "skills": [
            {
                "id": "pleading_drafting",
                "name": "民事答辩状撰写",
                "description": "协助被告律师完成从案卷梳理到答辩状起草的全部工作。",
                "stages": [
                    {"id": "fact_sorting", "name": "事实整理与梳理"},
                    {"id": "procedural_review", "name": "程序性审查与抗辩"},
                    {"id": "substantive_analysis", "name": "实体法律分析（三段论）"},
                    {"id": "evidence_analysis", "name": "证据分析与质证准备"},
                    {"id": "strategy_formulation", "name": "答辩策略制定"},
                    {"id": "document_drafting", "name": "正式答辩状撰写"},
                ]
            },
            {
                "id": "complaint_drafting",
                "name": "民事起诉状撰写",
                "description": "协助原告律师完成起诉事实整理、诉求设计及起诉状起草。",
                "stages": [
                    {"id": "fact_sorting", "name": "事实整理与梳理"},
                    {"id": "claim_design", "name": "诉讼请求与依据设计"},
                    {"id": "procedural_review", "name": "程序与管辖权审查"},
                    {"id": "evidence_chain", "name": "证据清单与证据链构建"},
                    {"id": "document_drafting", "name": "正式起诉状撰写"},
                ]
            },
            {
                "id": "project_opinion",
                "name": "项目法律意见书",
                "description": "以战略顾问视角为项目出具法律意见书（备忘录格式）。",
                "stages": [
                    {"id": "fact_sorting", "name": "基本事实梳理"},
                    {"id": "relation_analysis", "name": "法律关系梳理"},
                    {"id": "legal_retrieval", "name": "核心法规检索"},
                    {"id": "risk_assessment", "name": "风险四级分层分析"},
                    {"id": "path_structure", "name": "论证路径与框架确认"},
                    {"id": "document_drafting", "name": "正式法律意见书起草"},
                ]
            },
            {
                "id": "pre_case_analysis",
                "name": "委托代理前案件分析",
                "description": "协助律师在正式接受委托代理前，对民商事诉讼案件进行系统性分析与胜诉判定。",
                "stages": [
                    {"id": "material_client", "name": "材料阅读与利益图谱"},
                    {"id": "fact_relation_retrieval", "name": "事实梳理与法规检索"},
                    {"id": "strategy_focus_assessment", "name": "诉讼方案与争议焦点评估"},
                    {"id": "contradiction_outcome", "name": "交叉验证与胜诉预判"},
                    {"id": "document_drafting", "name": "代理意见与报告撰写"},
                ]
            },
            {
                "id": "case_search",
                "name": "案例检索与分析",
                "description": "针对案件中需要案例支撑的法律观点，进行典型裁判类案检索，并生成结构化案例检索报告。",
                "stages": [
                    {"id": "material_point", "name": "阅读材料与梳理待证观点"},
                    {"id": "strategy_search", "name": "检索策略设计与类案搜索"},
                    {"id": "document_drafting", "name": "案例筛选排序与报告生成"},
                ]
            },
            {
                "id": "corporate_legal",
                "name": "常规企业常法服务",
                "description": "为企业客户日常咨询、常规合规、合同条款等常见常法服务提供标准化备忘录起草。",
                "stages": [
                    {"id": "client_reading", "name": "客户档案与日常问题阅读"},
                    {"id": "compliance_check", "name": "合规与合意风险审查"},
                    {"id": "document_drafting", "name": "解决方案与备忘录起草"},
                ]
            }
        ]
    }

@router.post("/workflow/stream")
async def stream_workflow(req: WorkflowRequest, user: dict = Depends(get_current_user)):
    """流式返回当前法律阶段分析的大模型推理 Token 序列。"""
    project_name = "未知项目"
    try:
        from core.project_access import _read_projects
        for p in _read_projects():
            if p["id"] == req.project_id:
                project_name = p.get("name", "未命名项目")
                break
    except Exception:
        pass

    from core.redis_client import set_agent_active
    stage_name_map = {
        "fact_sorting": "事实梳理",
        "procedural_review": "程序性审查",
        "substantive_analysis": "实体法律分析",
        "evidence_analysis": "证据质证分析",
        "strategy_formulation": "诉讼策略制定",
        "document_drafting": "文稿正式起草",
        "claim_design": "诉求依据设计",
        "evidence_chain": "证据链构建",
        "relation_analysis": "法律关系梳理",
        "legal_retrieval": "法规检索",
        "risk_assessment": "风险评估",
        "path_structure": "论证框架确认",
        "material_client": "客户材料阅读",
        "fact_relation_retrieval": "事实法规梳理",
        "strategy_focus_assessment": "诉讼方案评估",
        "contradiction_outcome": "胜诉预判",
        "material_point": "观点梳理",
        "strategy_search": "类案搜索",
        "client_reading": "日常案档阅读",
        "compliance_check": "风险审查",
    }
    stage_display = stage_name_map.get(req.stage_id, req.stage_id)
    set_agent_active("legal", f"分析阶段: {stage_display}", project_name, duration=45)

    async def event_generator() -> AsyncGenerator[str, None]:
        try:
            async for token in generate_legal_stage(
                project_id=req.project_id,
                file_ids=req.file_ids,
                skill_type=req.skill_type,
                stage_id=req.stage_id,
                context_history=req.context_history,
                collaborative=req.collaborative,
            ):
                yield token
        except Exception as e:
            logger.exception("工作流生成失败")
            yield f"\n\n❌ 法律工作流推理中途出错: {str(e)}"

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@router.post("/contract/review")
async def review_contract(req: ContractReviewRequest, user: dict = Depends(get_current_user)):
    """对指定的 Word 合同进行审查，提取风险项并动态回写 DOCX 物理批注。"""
    docx_path = Path(settings.UPLOAD_DIR) / req.file_path.lstrip("/")
    if not docx_path.exists() or not docx_path.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"找不到指定的合同文件: {req.file_path}"
        )

    project_name = "未知项目"
    try:
        from core.project_access import _read_projects
        for p in _read_projects():
            if p["id"] == req.project_id:
                project_name = p.get("name", "未命名项目")
                break
    except Exception:
        pass

    from core.redis_client import set_agent_active
    set_agent_active("service", f"正在审查文档: {docx_path.name}", project_name, duration=60)
    try:
        from docx import Document
        doc = Document(str(docx_path))
        contract_text = "\n".join([p.text for p in doc.paragraphs if p.text.strip()])
    except Exception as e:
        logger.exception("读取合同 Word 失败")
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"无法解析合同文件: {str(e)}"
        )

    if not contract_text.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="合同文本为空，无法进行审查"
        )

    # 2. 检索合同法及标准合同条文（大前提 RAG）
    try:
        retrieval_res = await run_retrieval(
            search_query="合同审核 示范文本 违约责任 责任限制 争议解决",
            original_message="合同审核",
            project_id=req.project_id,
            file_ids=req.file_ids,
            strategy={"vector_top_k": 6, "inject_table_stats": False},
        )
        context = retrieval_res.vector_context or ""
    except Exception:
        context = "参考《民法典》合同编一般规定"

    # 3. 大模型分析生成 JSON 格式修改批注
    prompt = CONTRACT_REVIEW_PROMPT.format(
        contract_text=contract_text[:8000],  # 截断防 OOM
        context=context
    )

    try:
        import asyncio
        # Step 1: 顾问起草初审意见
        set_agent_active("service", f"正在进行文档内容合规分析: {docx_path.name}", project_name, duration=25)
        
        chunks = []
        async for chunk in stream_ollama(
            prompt=prompt,
            model="qwen3.6:35b-q4",
            temperature=0.0,  # 强制使用完全一致性，排查风险不需发散思维
            num_predict=4096,
            num_ctx=16384
        ):
            chunks.append(chunk)
        raw_output = "".join(chunks).strip()

        if req.collaborative:
            # Step 2: 小杠交叉抗辩审查（状态体现）
            set_agent_active("contrarian", f"正在审查初审意见并进行合规审查: {docx_path.name}", project_name, duration=15)
            await asyncio.sleep(1.2)

            # Step 3: 大BOSS最终裁定与定稿
            set_agent_active("arbiter", f"正在进行文档合规定稿与格式化: {docx_path.name}", project_name, duration=15)
            await asyncio.sleep(1.0)

        # 清洗 <think> 标签并提取 JSON 数组
        clean_output = re.sub(r"<think>.*?</think>", "", raw_output, flags=re.DOTALL).strip()
        json_match = re.search(r"\{.*\}", clean_output, re.DOTALL)
        if not json_match:
            raise ValueError("大模型未返回 JSON")

        data = json.loads(json_match.group(0))
        comments = data.get("comments", [])
    except Exception as ex:
        logger.exception("大模型合同审查解析异常")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"大模型合同审核过程分析失败: {str(ex)}"
        )

    # 4. 动态写入 docx 物理批注
    injected_count = inject_contract_comments(str(docx_path), comments)

    return {
        "status": "success",
        "injected_count": injected_count,
        "comments": comments,
        "filename": docx_path.name
    }
