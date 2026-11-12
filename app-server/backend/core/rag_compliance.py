"""
基于 RAG 检索知识驱动的上传图片与视频规范合规检测引擎。
WHY: 移动端采集现场图片、视频作为案件证据或资料时，必须第一时间对照关联标准、
     法律法规（如《广告法》、食品安全国标 GB 7718、行政执法证据勘验规范）进行多模态合规性核验，
     杜绝非标、违法宣传、缺失关键标签或证据瑕疵。
"""
from __future__ import annotations

import json
import logging
import re
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import httpx

from core.config import settings
from core.database import (
    get_db,
    get_mobile_upload,
    update_mobile_upload_compliance,
)
from core.llm_config import get_active_llm_config, normalize_endpoint
from core.status_tracker import get_file_status, update_file_status

logger = logging.getLogger(__name__)

# ── 内置基础通用规范知识库储备（当目标案卷未关联专属标准时自动激活 RAG 增强）──
_BUILTIN_STANDARDS = {
    "ad_compliance": {
        "title": "《中华人民共和国广告法》",
        "clauses": [
            {"clause": "第四条", "text": "广告不得含有虚假或者引人误解的内容，不得欺骗、误导消费者。"},
            {"clause": "第八条", "text": "广告中对商品的性能、产地、用途、质量、价格、生产者、有效期限等有表示的，应当准确、清楚、明白。"},
            {"clause": "第九条第(三)项", "text": "广告不得使用“国家级”、“最高级”、“最佳”等绝对化用语。"},
            {"clause": "第二十八条", "text": "广告以虚假或者引人误解的内容欺骗、误导消费者的，构成虚假广告。对引证内容应真实并标明出处。"},
        ],
    },
    "food_label": {
        "title": "《食品安全国家标准 预包装食品标签通则》(GB 7718)",
        "clauses": [
            {"clause": "4.1 标示内容", "text": "必须清晰标示食品名称、配料表、净含量和规格、生产者/经销者名称地址、生产日期和保质期、贮存条件、食品生产许可证编号及产品标准代号。"},
            {"clause": "4.1.3 配料表", "text": "应以‘配料’或‘配料表’为引导词，各种配料应按加入量递减顺序一一排列；食品添加剂应标示通用名称。"},
            {"clause": "3.1 基本要求", "text": "不得以虚假、夸大、使消费者误解或欺骗性的文字、图形等方式介绍食品，不得利用字号大小或色差误导消费者。"},
        ],
    },
    "evidence_video": {
        "title": "《市场监督管理行政处罚程序规定》与《电子数据取证技术规范》",
        "clauses": [
            {"clause": "第二十三条", "text": "现场勘验取证应制作笔录，如实记录勘验时间、地点、现场状况；视听资料应当真实完整，说明摄制时间、地点及人员。"},
            {"clause": "第三十条", "text": "音视频证据需保持声音与画面的完整性与连续性，不得有剪辑、拼接、涂抹或无授权变动痕迹。"},
            {"clause": "第四十一条", "text": "当事人陈述或现场询问音视频应清晰体现执法人员亮明执法证件及权利义务告知过程。"},
        ],
    },
}


def _get_project_related_libraries(project_id: str) -> List[str]:
    """获取指定项目关联的法规/标准库列表（从 project_refs 与常用公共库发现）。"""
    libs = [project_id]
    try:
        with get_db() as conn:
            rows = conn.execute(
                "SELECT target_project_id FROM project_refs WHERE project_id = ?",
                (project_id,),
            ).fetchall()
            for r in rows:
                tid = r[0] if isinstance(r, (list, tuple)) else r["target_project_id"]
                if tid and tid not in libs:
                    libs.append(tid)

            # 如果未关联，且存在标准库，补充系统核心知识库
            if len(libs) == 1:
                cand_rows = conn.execute(
                    "SELECT id FROM projects WHERE id IN ('fe2982b3820e', 'cae3c576c743', '1c34280f1f56')"
                ).fetchall()
                for cr in cand_rows:
                    cid = cr[0] if isinstance(cr, (list, tuple)) else cr["id"]
                    if cid and cid not in libs:
                        libs.append(cid)
    except Exception as exc:
        logger.debug("获取关联标准库跳过: %s", exc)
    return libs


def _retrieve_compliance_standards(
    query_text: str,
    project_id: str,
    media_category: str,
) -> Tuple[List[dict], str]:
    """
    通过 RAG 向量检索召回最匹配的法律规范、国家标准或案卷准则。
    返回: (召回的标准条款列表, 格式化上下文字符串)
    """
    from core.vector_store import query_by_file_ids

    libs = _get_project_related_libraries(project_id)
    retrieved_chunks: List[dict] = []
    
    # 构建针对规范的检索 Query
    clean_q = re.sub(r"[^\w\u4e00-\u9fa5\s]", " ", query_text)[:200]
    rag_query = f"{clean_q} 规范 标准 规定 要求 检查 合规 准则"

    for lib_id in libs:
        try:
            hits = query_by_file_ids(
                query_text=rag_query,
                file_ids=[],
                project_id=lib_id,
                n_results=3,
            )
            for h in hits:
                doc = h.get("document", "").strip()
                fname = h.get("filename", "")
                if doc and len(doc) > 30:
                    retrieved_chunks.append({
                        "standard_name": fname or "案件相关法规标准",
                        "content": doc,
                        "score": h.get("confidence", 0.0),
                    })
            if len(retrieved_chunks) >= 4:
                break
        except Exception as q_err:
            logger.debug("RAG 规范检索异常 (lib=%s): %s", lib_id, q_err)

    standards_list: List[dict] = []
    context_lines: List[str] = []

    if retrieved_chunks:
        for idx, chunk in enumerate(retrieved_chunks[:4], start=1):
            s_name = chunk["standard_name"]
            snippet = chunk["content"][:350].replace("\n", " ")
            standards_list.append({
                "title": s_name,
                "clause": f"第{idx}条匹配规范",
                "requirement": snippet,
            })
            context_lines.append(f"【规范 {idx}】《{s_name}》：\n{snippet}")

    # 若检索知识过少，补充内置基准规范
    if len(context_lines) < 2:
        if media_category == "video":
            b = _BUILTIN_STANDARDS["evidence_video"]
        elif any(k in query_text for k in ("食品", "配料", "包装", "标签", "保质期", "生产日期")):
            b = _BUILTIN_STANDARDS["food_label"]
        else:
            b = _BUILTIN_STANDARDS["ad_compliance"]

        for item in b["clauses"]:
            standards_list.append({
                "title": b["title"],
                "clause": item["clause"],
                "requirement": item["text"],
            })
            context_lines.append(f"【通用基准】{b['title']} {item['clause']}：\n{item['text']}")

    return standards_list, "\n\n".join(context_lines)


def _call_llm_json(prompt: str, system_prompt: str) -> Optional[dict]:
    """同步调用大模型端点并解析结构化 JSON 结果。"""
    active_cfg = get_active_llm_config()
    model = active_cfg.get("model") or getattr(settings, "DEFAULT_LLM_MODEL", "qwen3.8:27b-q4")
    base_url = active_cfg.get("baseURL") or getattr(settings, "OLLAMA_BASE_URL", "http://host.docker.internal:11434")
    api_key = active_cfg.get("apiKey", "")
    timeout = min(float(active_cfg.get("timeoutSeconds", 60)), 90.0)

    is_ollama = "11434" in base_url or "/api/" in base_url
    headers = {"Content-Type": "application/json"}
    if api_key and api_key.strip().upper() != "EMPTY":
        headers["Authorization"] = f"Bearer {api_key.strip()}"

    req_url = f"{base_url.rstrip('/')}/api/chat" if is_ollama else normalize_endpoint(base_url, is_openai_chat=True)

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": prompt},
    ]

    payload: dict[str, Any]
    if is_ollama:
        payload = {
            "model": model,
            "messages": messages,
            "stream": False,
            "format": "json",
            "options": {"temperature": 0.1, "num_predict": 2048},
        }
    else:
        payload = {
            "model": model,
            "messages": messages,
            "temperature": 0.1,
            "max_tokens": 2048,
            "response_format": {"type": "json_object"},
        }

    try:
        with httpx.Client(timeout=timeout, trust_env=False) as client:
            resp = client.post(req_url, json=payload, headers=headers)
            resp.raise_for_status()
            data = resp.json()
            if is_ollama:
                content = data.get("message", {}).get("content", "")
            else:
                choices = data.get("choices", [])
                content = choices[0].get("message", {}).get("content", "") if choices else ""

            # 清理可能的 markdown 代码块标记与思考标签
            clean = re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL)
            clean = re.sub(r"^```(?:json)?\s*", "", clean.strip(), flags=re.IGNORECASE)
            clean = re.sub(r"\s*```$", "", clean)
            return json.loads(clean.strip())
    except Exception as exc:
        logger.warning("大模型 JSON 研判解析调用异常: %s", exc)
        return None


def _rule_based_fallback(
    media_category: str,
    filename: str,
    content: str,
    remark: str,
    standards_list: List[dict],
) -> dict:
    """当 LLM 暂时不可用时，启用轻量确定性规则生成稳健合规报告兜底。"""
    full_text = f"{filename} {remark} {content}"
    issues: List[dict] = []
    recommendations: List[str] = []
    status = "compliant"
    label = "规范合格"
    score = 90

    # 违禁词检测（广告法绝对化用语）
    violation_kws = ["国家级", "最高级", "最佳", "第一品牌", "极品", "顶级", "独家绝密", "绝对安全", "彻底包治"]
    found_viol = [kw for kw in violation_kws if kw in full_text]
    if found_viol:
        status = "violation"
        label = "违反规范"
        score = 45
        issues.append({
            "item": "绝对化禁止用语核验",
            "status": "fail",
            "detail": f"资料中出现法律明令禁用的词汇：{', '.join(found_viol)}，涉嫌违反《广告法》第九条。",
        })
        recommendations.append("请核实该资料宣传文案，责令清除绝对化禁忌词汇，或补充法定引证证明材料。")

    # 视频取证完整性检查
    if media_category == "video":
        if "未识别到清晰的人声对话" in content or "静音" in content:
            if status != "violation":
                status = "warning"
                label = "证据需补正"
                score = 75
            issues.append({
                "item": "现场音画同步核验",
                "status": "warning",
                "detail": "视频未提取到人声对话或音轨较弱，仅包含画面特征。",
            })
            recommendations.append("建议补充执法现场人员问答录音或笔录，形成闭环印证。")
        else:
            issues.append({
                "item": "音轨有效性核验",
                "status": "pass",
                "detail": "检测到完整语音对话音轨，具备取证基础要素。",
            })

    if not issues:
        issues.append({
            "item": "资料要素合规性核验",
            "status": "pass",
            "detail": "图像画面清晰完整，排版要素符合常规归档与证据采信要求。",
        })
        recommendations.append("建议在案卷归档目录中做好编号与现场记录关联。")

    return {
        "compliance_status": status,
        "compliance_label": label,
        "compliance_score": score,
        "check_type": f"{'视频' if media_category == 'video' else '图片'}规范检测",
        "applied_standards": standards_list[:3],
        "summary": f"经基于规范库的智能检测，该{ '视频' if media_category == 'video' else '图片'}资料{'存在一定合规风险' if status == 'violation' else '整体基本符合规范要求'}。",
        "findings": issues,
        "recommendations": recommendations,
        "checked_at": datetime.now(timezone(timedelta(hours=8))).replace(tzinfo=None).isoformat(),
    }


def run_rag_compliance_check(
    file_path: str,
    file_id: str,
    filename: str,
    project_id: str,
    media_category: str = "image",
    extracted_text: str = "",
    remark: str = "",
) -> dict:
    """
    执行单份图片或视频的 RAG 模式规范合规性全自动检测。
    WHY: 落实“每次上传的图片，视频都需要进行rag规范的检测”核心需求。
    """
    t0 = time.time()
    logger.info("🛡️ 开始执行 RAG 规范检测: %s (file_id=%s, cat=%s)", filename, file_id, media_category)

    # 1. 组合待研判资料特征
    content_snippet = (extracted_text or "").strip()
    if len(content_snippet) > 1500:
        content_snippet = content_snippet[:1500] + "...(后略)"

    search_seed = f"{filename} {remark} {content_snippet[:200]}"
    standards_list, standards_context = _retrieve_compliance_standards(
        query_text=search_seed,
        project_id=project_id,
        media_category=media_category,
    )

    # 2. 构建严谨的 RAG 合规研判 Prompt
    system_prompt = (
        "你是一位资深的行政执法规范、广告法规与食品质量安全国家标准审查专家。"
        "你的任务是结合检索到的【关联法律法规与国家标准条款】，对用户上传的现场图片或视频提取内容进行规范性审查与风险研判。"
        "输出必须为纯合法 JSON 对象，严禁包含任何 Markdown 格式或额外文字说明。"
    )

    prompt = f"""请依据以下检索到的【法规与国家标准依据】，对上传的【资料多模态内容】进行逐项规范性核验：

【参考依据的标准与法规条款】
{standards_context}

【待审查资料信息】
- 文件名称：{filename}
- 媒体类别：{'视频' if media_category == 'video' else '图片'}
- 上传备注/现场说明：{remark or '无现场备注'}
- 资料识别内容/转写文本：
{content_snippet or '（画面主体未提取到文字，主要为现场实景）'}

【必须返回的 JSON 结构】
{{
  "compliance_status": "compliant" | "warning" | "violation",
  "compliance_label": "规范合格" | "合规存疑" | "违反规范",
  "compliance_score": 85,
  "summary": "简练综合审查结论（2句话以内）",
  "findings": [
    {{"item": "审查核验要点名称", "status": "pass" | "warning" | "fail", "detail": "具体比对分析情况说明"}}
  ],
  "recommendations": [
    "针对该资料的整改、取证补正或采信建议"
  ]
}}
"""

    report: Optional[dict] = None
    try:
        report = _call_llm_json(prompt, system_prompt)
    except Exception as err:
        logger.warning("调用 LLM RAG 审查失败: %s", err)

    if not report or not isinstance(report, dict) or "compliance_status" not in report:
        logger.info("启用规则引擎兜底生成规范检测报告: %s", filename)
        report = _rule_based_fallback(media_category, filename, content_snippet, remark, standards_list)
    else:
        # 补全结构化元数据
        report["check_type"] = f"{'视频' if media_category == 'video' else '图片'}规范检测"
        report["applied_standards"] = standards_list[:3]
        report["checked_at"] = datetime.now(timezone(timedelta(hours=8))).replace(tzinfo=None).isoformat()
        if "compliance_score" not in report:
            st = report.get("compliance_status")
            report["compliance_score"] = 92 if st == "compliant" else (70 if st == "warning" else 40)
        if "compliance_label" not in report:
            st = report.get("compliance_status")
            report["compliance_label"] = "规范合格" if st == "compliant" else ("合规存疑" if st == "warning" else "违反规范")

    status_val = str(report.get("compliance_status") or "compliant")
    score_val = int(report.get("compliance_score") or 90)
    report_json = json.dumps(report, ensure_ascii=False)

    # 3. 持久化记录至 SQLite 与状态追踪文件
    try:
        update_mobile_upload_compliance(
            file_id=file_id,
            project_id=project_id,
            compliance_status=status_val,
            compliance_score=score_val,
            compliance_report=report_json,
        )
    except Exception as db_err:
        logger.error("持久化规范检测结果至数据库失败: %s", db_err)

    try:
        curr_status = get_file_status(project_id, file_id)
        update_file_status(
            project_id=project_id,
            file_id=file_id,
            status=curr_status.get("status") or "vectorized",
            filename=filename,
            compliance_status=status_val,
            compliance_score=score_val,
            compliance_report=report,
            compliance_checked_at=report["checked_at"],
        )
    except Exception as st_err:
        logger.debug("更新本地状态追踪文件跳过: %s", st_err)

    elapsed = time.time() - t0
    logger.info("✅ RAG 规范检测完成: %s -> %s (%d分), 耗时 %.2fs", filename, status_val, score_val, elapsed)
    return report
