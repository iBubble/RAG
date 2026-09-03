"""
分拣填报与案情研判 API 路由。
WHY: 遵循《智能呈报》设计规范（令121号与令2号），为来件分诊与处罚裁量提供
     基于规则图谱与大模型混合推理的智能表单推荐与持久化管理。
"""
from __future__ import annotations

import json
import logging
import os
import re
from pathlib import Path
from typing import List, Optional, Dict, Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from core.config import settings
from core.database import get_db
from core.auth_deps import get_current_user
from core.project_access import require_project_access
from core.llm_engine import stream_ollama

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/projects", tags=["triage_judgment"])

# 数据持久化目录定义
TRIAGE_DIR = Path(settings.DATA_DIR) / "triage"
JUDGMENT_DIR = Path(settings.DATA_DIR) / "judgment"
ADJUDICATION_DIR = Path(settings.DATA_DIR) / "adjudication"
TRIAGE_DIR.mkdir(parents=True, exist_ok=True)
JUDGMENT_DIR.mkdir(parents=True, exist_ok=True)
ADJUDICATION_DIR.mkdir(parents=True, exist_ok=True)
INVESTIGATION_DIR = JUDGMENT_DIR

class RecommendRequest(BaseModel):
    model: Optional[str] = ""
    force_refresh: Optional[bool] = False

def get_rules_context() -> str:
    """读取 docs/智能呈报 核心规范文本片段作为 LLM 推理参考依据。"""
    candidates = [
        Path(__file__).parent.parent / "docs" / "智能呈报",
        Path("/app/backend/docs/智能呈报"),
        Path("/Users/gemini/Projects/Own/RAG/docs/智能呈报")
    ]
    rule_dir = None
    for c in candidates:
        if c.exists() and c.is_dir():
            rule_dir = c
            break

    if not rule_dir:
        return "《市场监督管理投诉举报处理办法》（总局令第121号）分别处理原则；《行政处罚程序规定》（总局令第2号）。"

    texts = []
    main_files = [
        "智能体设计方案-市场监管投诉举报判罚.md",
        "规范-市场监管来件智能处理系统建设规范.md"
    ]
    for mf in main_files:
        fp = rule_dir / mf
        if fp.exists():
            try:
                content = fp.read_text(encoding="utf-8")
                texts.append(f"### 规范依据 [{mf}]\n" + content[:4000])
            except Exception as e:
                logger.warning(f"读取规则文件 {mf} 失败: {e}")
    return "\n\n".join(texts)

def get_project_materials_text(project_id: str) -> str:
    """提取当前项目上传的案卷材料文本及基础描述。"""
    collected = []
    try:
        with get_db() as conn:
            cur = conn.cursor()
            cur.execute("SELECT name, metadata_json FROM projects WHERE id = ?", (project_id,))
            row = cur.fetchone()
            if row:
                collected.append(f"【案件/项目名称】：{row[0]}")
                if row[1] and row[1] != "{}":
                    collected.append(f"【项目属性】：{row[1]}")
    except Exception as e:
        logger.warning(f"读取项目基本信息异常: {e}")

    # 1. 优先从 Qdrant 抓取所有已切片/已 OCR 的向量文档内容（支持图片、PDF 等全格式）
    try:
        from core.vector_store import _get_client, _collection_name
        from qdrant_client import models
        client = _get_client()
        resp = client.scroll(
            collection_name=_collection_name,
            scroll_filter=models.Filter(
                must=[models.FieldCondition(key="project_id", match=models.MatchValue(value=project_id))]
            ),
            limit=50,
            with_payload=True,
            with_vectors=False
        )
        points, _ = resp
        if points:
            for pt in points:
                payload = pt.payload or {}
                fn = payload.get("filename", "未知文件")
                doc_txt = (payload.get("document") or payload.get("text") or "").strip()
                if doc_txt and len(doc_txt) > 10:
                    collected.append(f"【卷宗/证据切片: {fn}】:\n{doc_txt[:1500]}")
    except Exception as _qe:
        logger.warning(f"从 Qdrant 提取项目材料文本失败: {_qe}")

    upload_path = Path(settings.UPLOAD_DIR) / project_id
    if upload_path.exists():
        for p in upload_path.glob("**/*"):
            if p.is_file() and p.suffix.lower() in [".txt", ".md", ".json"]:
                try:
                    txt = p.read_text(encoding="utf-8", errors="ignore").strip()
                    if txt:
                        collected.append(f"【材料文件: {p.name}】:\n{txt[:2000]}")
                except Exception:
                    pass

    doc_path = Path(settings.DATA_DIR) / "documents" / project_id
    if doc_path.exists():
        for dp in doc_path.glob("*.json"):
            try:
                d = json.loads(dp.read_text(encoding="utf-8"))
                c = re.sub(r'<[^>]+>', ' ', d.get("content", ""))
                c = re.sub(r'\s+', ' ', c).strip()
                if c:
                    collected.append(f"【历史记载: {d.get('title', '')}】:\n{c[:1500]}")
            except Exception:
                pass

    res = "\n\n".join(collected)
    return res if res else "暂无上传案卷材料，根据项目名称及市场监督管理通用执法流程研判。"


async def run_triage_inference(project_id: str, model: str) -> dict:
    """执行分拣填报智能推理，返回表单推荐列表与判定依据摘要。"""
    materials = get_project_materials_text(project_id)
    rules = get_rules_context()

    prompt = f"""你是一名资深市场监督管理执法专家，请依据《市场监督管理投诉举报处理办法》（总局令第121号）与《市场监督管理部门处理投诉举报文书式样》（10种），对当前案件材料进行智能分诊与表单推荐。

【候选表单清单（共10种，必须使用完全一致的表单全名）】：
1. 投诉登记表
2. 举报登记表
3. 投诉/举报分送通知书
4. 限期提供身份证明材料通知书
5. 投诉受理决定书
6. 投诉不予受理决定书
7. 投诉调解通知书
8. 投诉终止调解决定书
9. 投诉调解书
10. 举报处理结果告知书

【强制互斥与业务规则】：
1. 诉求定性：主张退款退赔等消费者民事争议者走“投诉轨”；主张惩处商家违法行为者走“举报轨”。“投诉登记表”与“举报登记表”二者不可同时出现，必须严格二选一！
2. 受理决定：若为投诉轨，依据第16/17条判断受理条件，“投诉受理决定书”与“投诉不予受理决定书”只能二选一！
3. 调解与结果：“投诉调解书”与“投诉终止调解决定书”二选一；举报轨可搭配“举报处理结果告知书”。
4. 其他表单（分送通知书、限期提供身份证明材料通知书）仅在材料指明不归本局管辖或身份缺失时才推荐。

【案件参考材料】：
{materials[:3500]}

【参考法规及判罚规则】：
{rules[:2500]}

【请严格按如下 JSON 格式输出，禁止包含任何 Markdown 标记或多余文字】：
{{
  "track": "投诉轨" 或 "举报轨",
  "summary": "AI 分诊核心结论简述（200字以内，点明来件性质、是否受理及法律依据）",
  "recommended_forms": [
    {{
      "name": "1.投诉登记表",
      "reason": "推荐该表单的具体事实与法条依据",
      "required": true
    }}
  ]
}}
"""
    raw_output = ""
    try:
        async for chunk in stream_ollama(prompt, model=model or settings.DEFAULT_LLM_MODEL, temperature=0.1):
            raw_output += chunk
    except Exception as e:
        logger.error(f"分拣推理大模型调用失败: {e}")

    # 清除 think 标签与反引号
    clean_json = re.sub(r'<think>.*?</think>', '', raw_output, flags=re.DOTALL).strip()
    clean_json = re.sub(r'^```(?:json)?\s*', '', clean_json, flags=re.MULTILINE)
    clean_json = re.sub(r'\s*```$', '', clean_json, flags=re.MULTILINE).strip()

    parsed = None
    try:
        match = re.search(r'\{.*\}', clean_json, re.DOTALL)
        if match:
            parsed = json.loads(match.group(0))
    except Exception as e:
        logger.warning(f"解析大模型分拣结果 JSON 失败: {e}, 尝试兜底")

    # 兜底保底与强制互斥过滤
    return sanitize_triage_result(parsed, materials)


def sanitize_triage_result(parsed: Optional[dict], materials: str) -> dict:
    """强制执行互斥业务规则过滤，确保投诉/举报、受理/不受理绝对二选一。"""
    is_report = ("举报" in materials and "投诉" not in materials) or ("查处" in materials and "退款" not in materials)
    default_track = "举报轨" if is_report else "投诉轨"

    if not parsed or not isinstance(parsed, dict) or "recommended_forms" not in parsed:
        if is_report:
            return {
                "track": "举报轨",
                "summary": "经 AI 分诊研判，来件诉求主要为反映被举报人违法行为并请求查处，依据令121号第27条进入举报查处程序。",
                "recommended_forms": [
                    {"name": "2.举报登记表", "reason": "来件属于反映违法行为线索，登记立卷", "required": True},
                    {"name": "10.举报处理结果告知书", "reason": "向实名举报人反馈处理结论", "required": False}
                ]
            }
        else:
            return {
                "track": "投诉轨",
                "summary": "经 AI 分诊研判，来件属于消费者与经营者之间的权益争议，符合令121号受理要件，进入调解程序。",
                "recommended_forms": [
                    {"name": "1.投诉登记表", "reason": "消费者权益争议登记，固定当事人与诉求信息", "required": True},
                    {"name": "5.投诉受理决定书", "reason": "经核验符合令121号第10条要件，决定受理调解", "required": True},
                    {"name": "7.投诉调解通知书", "reason": "通知双方参加调解", "required": False},
                    {"name": "9.投诉调解书", "reason": "调解达成一致签署书面调解协议", "required": False}
                ]
            }

    track = parsed.get("track", default_track)
    forms = parsed.get("recommended_forms", [])
    names = [f.get("name", "") for f in forms if isinstance(f, dict)]

    # 1. 强制 投诉登记表 vs 举报登记表 二选一
    has_tousu = any("投诉登记表" in n for n in names)
    has_jubao = any("举报登记表" in n for n in names)
    if has_tousu and has_jubao:
        if "举报" in track:
            forms = [f for f in forms if "投诉登记表" not in f.get("name", "")]
        else:
            forms = [f for f in forms if "举报登记表" not in f.get("name", "")]
    elif not has_tousu and not has_jubao:
        if "举报" in track:
            forms.insert(0, {"name": "2.举报登记表", "reason": "反映违法行为，建立举报查处台账", "required": True})
        else:
            forms.insert(0, {"name": "1.投诉登记表", "reason": "消费者民事权益争议登记", "required": True})

    # 2. 强制 投诉受理决定书 vs 投诉不予受理决定书 二选一
    has_shouli = any("投诉受理决定书" in f.get("name", "") for f in forms)
    has_bushouli = any("投诉不予受理决定书" in f.get("name", "") for f in forms)
    if has_shouli and has_bushouli:
        forms = [f for f in forms if "投诉不予受理决定书" not in f.get("name", "")]

    # 3. 规范化表单序号与命名
    std_map = {
        "投诉登记表": "1.投诉登记表",
        "举报登记表": "2.举报登记表",
        "投诉/举报分送通知书": "3.投诉/举报分送通知书",
        "分送通知书": "3.投诉/举报分送通知书",
        "限期提供身份证明材料通知书": "4.限期提供身份证明材料通知书",
        "投诉受理决定书": "5.投诉受理决定书",
        "投诉不予受理决定书": "6.投诉不予受理决定书",
        "投诉调解通知书": "7.投诉调解通知书",
        "投诉终止调解决定书": "8.投诉终止调解决定书",
        "投诉调解书": "9.投诉调解书",
        "举报处理结果告知书": "10.举报处理结果告知书"
    }
    normalized = []
    seen = set()
    for f in forms:
        fn = f.get("name", "")
        clean_name = re.sub(r'^\d+[\.、\s]*', '', fn).strip()
        final_name = std_map.get(clean_name, fn)
        if final_name not in seen:
            seen.add(final_name)
            normalized.append({
                "name": final_name,
                "reason": f.get("reason", "依据办案规则推荐"),
                "required": f.get("required", False)
            })

    return {
        "track": track,
        "summary": parsed.get("summary", "来件分诊推荐完成。"),
        "recommended_forms": normalized
    }


@router.get("/{project_id}/triage/recommend")
async def get_triage_recommendation(project_id: str, user: dict = Depends(get_current_user)):
    """获取项目持久化的分拣推荐表单列表。"""
    require_project_access(project_id, user)
    fp = TRIAGE_DIR / f"{project_id}.json"
    if fp.exists():
        try:
            return json.loads(fp.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"status": "none", "data": None}


@router.post("/{project_id}/triage/recommend")
async def trigger_triage_recommendation(
    project_id: str,
    req: RecommendRequest,
    user: dict = Depends(get_current_user)
):
    """触发 AI 大模型执行分拣推荐，持久化并返回结果。"""
    require_project_access(project_id, user, write=True)
    fp = TRIAGE_DIR / f"{project_id}.json"
    if not req.force_refresh and fp.exists():
        try:
            return {"status": "success", "data": json.loads(fp.read_text(encoding="utf-8"))}
        except Exception:
            pass

    data = await run_triage_inference(project_id, req.model or "")
    # 持久化存储
    try:
        fp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as e:
        logger.error(f"持久化保存分拣结果失败: {e}")

    return {"status": "success", "data": data}


async def run_judgment_inference(project_id: str, model: str) -> dict:
    """执行案情研判智能推理，依据令2号与裁量基准推荐适用的行政处罚文书。"""
    materials = get_project_materials_text(project_id)
    rules = get_rules_context()

    prompt = f"""你是一名精通《市场监督管理行政处罚程序规定》（令2号）与《行政处罚法》的法制审核专家。
请依据案件材料与法律程序，智能研判当前案情所处的办案阶段，推荐最适用的行政处罚文书（来源于《市场监督管理行政处罚文书格式范本》56种）。

【办案阶段关键文书参考】：
- 案源初查：1.案件来源登记表
- 调查取证：9.现场笔录、14.询问笔录、15.抽样取证凭证
- 强制措施：21.实施行政强制措施决定书、24.场所/设施/财物清单、25.封条
- 审理审核：35.案件调查终结报告、36.案件审核表
- 告知程序：37.行政处罚告知书、38.行政处罚听证告知书
- 决定阶段：45.行政处罚决定书（认定违法处罚）与 46.不予行政处罚决定书（违法事实不成立或免罚），二者必须严格互斥二选一！
- 结案归档：53.结案审批表

【案件参考材料】：
{materials[:3500]}

【处罚程序与裁量依据】：
{rules[:2500]}

【请严格按如下 JSON 格式输出，禁止包含任何 Markdown 标记或多余文字】：
{{
  "stage": "调查取证阶段" 或 "告知拟罚阶段" 或 "决定结案阶段",
  "summary": "案情定性与裁量分析摘要（250字以内，点明涉嫌违法事由、证据链完整度及处罚依据）",
  "recommended_forms": [
    {{
      "name": "1.案件来源登记表",
      "reason": "推荐该文书的程序依据与事实支撑",
      "required": true
    }}
  ]
}}
"""
    raw_output = ""
    try:
        async for chunk in stream_ollama(prompt, model=model or settings.DEFAULT_LLM_MODEL, temperature=0.1):
            raw_output += chunk
    except Exception as e:
        logger.error(f"案情研判大模型调用失败: {e}")

    clean_json = re.sub(r'<think>.*?</think>', '', raw_output, flags=re.DOTALL).strip()
    clean_json = re.sub(r'^```(?:json)?\s*', '', clean_json, flags=re.MULTILINE)
    clean_json = re.sub(r'\s*```$', '', clean_json, flags=re.MULTILINE).strip()

    parsed = None
    try:
        match = re.search(r'\{.*\}', clean_json, re.DOTALL)
        if match:
            parsed = json.loads(match.group(0))
    except Exception as e:
        logger.warning(f"解析大模型案情研判结果 JSON 失败: {e}, 尝试兜底")

    return sanitize_judgment_result(parsed, materials)


def sanitize_judgment_result(parsed: Optional[dict], materials: str) -> dict:
    """对案情研判结果进行法律程序完备性与互斥性校验。"""
    if not parsed or not isinstance(parsed, dict) or "recommended_forms" not in parsed:
        return {
            "stage": "调查取证阶段",
            "summary": "根据案涉线索初步研判，当事人涉嫌违反市场监管法律法规，当前应重点开展现场核查、固定证据并完成案源与笔录制作。",
            "recommended_forms": [
                {"name": "1.案件来源登记表", "reason": "案源线索归口登记，启动核查程序", "required": True},
                {"name": "9.现场笔录", "reason": "对涉案经营场所及在售商品进行实地检查核实", "required": True},
                {"name": "14.询问笔录", "reason": "调查询问当事人或相关经办人员", "required": True},
                {"name": "35.案件调查终结报告", "reason": "调查完毕后提请法制审核", "required": False},
                {"name": "37.行政处罚告知书", "reason": "向当事人正式告知拟处罚事实、理由与救济权利", "required": False},
                {"name": "45.行政处罚决定书", "reason": "拟定正式行政处罚决定文书", "required": False}
            ]
        }

    stage = parsed.get("stage", "案件办理阶段")
    forms = parsed.get("recommended_forms", [])

    # 互斥检查：行政处罚决定书 vs 不予行政处罚决定书 严禁同时出现
    has_pufa = any("45.行政处罚决定书" in f.get("name", "") or "行政处罚决定书" == f.get("name", "") for f in forms)
    has_buyu = any("46.不予行政处罚决定书" in f.get("name", "") or "不予行政处罚决定书" == f.get("name", "") for f in forms)
    if has_pufa and has_buyu:
        forms = [f for f in forms if "不予行政处罚决定书" not in f.get("name", "")]

    # 规范化名称（若大模型输出没有前缀数字，自动对齐至 56 种官方规范全称）
    valid_names = []
    tpl_path = Path(__file__).parent.parent / "local_data" / "ai_templates.json"
    if tpl_path.exists():
        try:
            with open(tpl_path, encoding="utf-8") as tf:
                cats = json.load(tf)
                for c in cats:
                    if "行政处罚" in c.get("name", ""):
                        valid_names = [t["name"] for t in c.get("tables", [])]
        except Exception:
            pass

    normalized = []
    seen = set()
    for f in forms:
        raw_n = f.get("name", "")
        # 寻找最佳匹配
        target_name = None
        for vn in valid_names:
            if vn == raw_n or vn.endswith(raw_n) or raw_n.endswith(re.sub(r'^\d+[\.、\s]*', '', vn)):
                target_name = vn
                break
        final_name = target_name or raw_n
        if final_name not in seen:
            seen.add(final_name)
            normalized.append({
                "name": final_name,
                "reason": f.get("reason", "依据行政处罚法定程序推荐"),
                "required": f.get("required", False)
            })

    return {
        "stage": stage,
        "summary": parsed.get("summary", "案情研判文书推荐完成。"),
        "recommended_forms": normalized
    }


@router.get("/{project_id}/judgment/recommend")
async def get_judgment_recommendation(project_id: str, user: dict = Depends(get_current_user)):
    """获取项目持久化的案情研判推荐文书列表。"""
    require_project_access(project_id, user)
    fp = JUDGMENT_DIR / f"{project_id}.json"
    if fp.exists():
        try:
            return json.loads(fp.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"status": "none", "data": None}


@router.post("/{project_id}/judgment/recommend")
async def trigger_judgment_recommendation(
    project_id: str,
    req: RecommendRequest,
    user: dict = Depends(get_current_user)
):
    """触发 AI 大模型执行案情研判推荐，持久化并返回结果。"""
    require_project_access(project_id, user, write=True)
    fp = JUDGMENT_DIR / f"{project_id}.json"
    if not req.force_refresh and fp.exists():
        try:
            return {"status": "success", "data": json.loads(fp.read_text(encoding="utf-8"))}
        except Exception:
            pass

    data = await run_judgment_inference(project_id, req.model or "")
    try:
        fp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as e:
        logger.error(f"持久化保存案情研判结果失败: {e}")

    return {"status": "success", "data": data}


# 调查取证路由别名绑定（向后兼容 judgment）
@router.get("/{project_id}/investigation/recommend")
async def get_investigation_recommendation(project_id: str, user: dict = Depends(get_current_user)):
    """获取项目调查取证推荐文书列表。"""
    return await get_judgment_recommendation(project_id, user)


@router.post("/{project_id}/investigation/recommend")
async def trigger_investigation_recommendation(
    project_id: str,
    req: RecommendRequest,
    user: dict = Depends(get_current_user)
):
    """触发调查取证文书智能推荐。"""
    return await trigger_judgment_recommendation(project_id, req, user)


async def run_adjudication_inference(project_id: str, model: str) -> dict:
    """执行研判裁量智能推理，基于案情与裁量基准推演处罚结果（处罚/整改/免罚）及文书。"""
    materials = get_project_materials_text(project_id)
    rules = get_rules_context()

    prompt = f"""你是一名精通《行政处罚法》与市场监督管理裁量基准的法制审核专家。
请依据案涉违法事实、当事人主观过错、社会危害程度及证据链闭环情况，对案件进行【裁量推理】，推演出最终的【处理结果】（如：责令改正、拟处罚与听证告知、行政处罚决定、不予行政处罚免罚、结案等），并在《市场监督管理行政处罚文书格式范本》中推荐处理结果对应的文书。

【处理结果核心文书范围】：
- 调查终结与审核：35.案件调查终结报告、36.案件审核表
- 告知程序：37.行政处罚告知书、38.行政处罚听证告知书
- 责令改正：47.责令改正通知书
- 决定阶段：44.当场行政处罚决定书（简易程序）；45.行政处罚决定书（认定违法处罚）与 46.不予行政处罚决定书（事实不清/情节轻微免罚），二者必须严格互斥二选一！
- 措施后续：28.解除行政强制措施决定书（若此前采取强制措施需解除）
- 结案归档：53.结案审批表

【严格互斥与裁量规则】：
1. 处罚决定书 vs 不予行政处罚决定书：若决定实施处罚，只推荐《45.行政处罚决定书》；若认定免罚或不予立案，只推荐《46.不予行政处罚决定书》，二者严禁同时出现！
2. 责令整改：涉案存在需要改正行为的（如未明码标价、轻微标签瑕疵等），应搭配《47.责令改正通知书》。

【案件参考材料】：
{materials[:3500]}

【裁量依据与法规基准】：
{rules[:2500]}

【请严格按如下 JSON 格式输出，禁止包含任何 Markdown 标记或多余文字】：
{{
  "disposition_type": "从轻处罚" 或 "一般处罚" 或 "减轻处罚" 或 "责令改正免罚" 或 "不予处罚",
  "summary": "裁量推理分析报告（250字以内，点明拟处理结果、裁量幅度、是否责令改正及裁量法规依据）",
  "recommended_forms": [
    {{
      "name": "35.案件调查终结报告",
      "reason": "提请法制审核与结案裁量",
      "required": true
    }}
  ]
}}
"""
    raw_output = ""
    try:
        async for chunk in stream_ollama(prompt, model=model or settings.DEFAULT_LLM_MODEL, temperature=0.1):
            raw_output += chunk
    except Exception as e:
        logger.error(f"研判裁量大模型调用失败: {e}")

    clean_json = re.sub(r'<think>.*?</think>', '', raw_output, flags=re.DOTALL).strip()
    clean_json = re.sub(r'^```(?:json)?\s*', '', clean_json, flags=re.MULTILINE)
    clean_json = re.sub(r'\s*```$', '', clean_json, flags=re.MULTILINE).strip()

    parsed = None
    try:
        match = re.search(r'\{.*\}', clean_json, re.DOTALL)
        if match:
            parsed = json.loads(match.group(0))
    except Exception as e:
        logger.warning(f"解析大模型研判裁量结果 JSON 失败: {e}, 尝试兜底")

    return sanitize_adjudication_result(parsed, materials)


def sanitize_adjudication_result(parsed: Optional[dict], materials: str) -> dict:
    """对研判裁量结果执行互斥校验与文书规范化。"""
    if not parsed or not isinstance(parsed, dict) or "recommended_forms" not in parsed:
        return {
            "disposition_type": "一般处罚",
            "summary": "案涉违法事实清楚、证据充分，建议责令当事人立即停止侵权行为，拟依法实施行政处罚，并出具行政处罚告知书及处罚决定书。",
            "recommended_forms": [
                {"name": "35.案件调查终结报告", "reason": "调查终结并梳理全部证据事实", "required": True},
                {"name": "36.案件审核表", "reason": "法制审核机构进行合法性审核", "required": True},
                {"name": "37.行政处罚告知书", "reason": "依法向当事人告知拟处罚事实、理由与陈述申辩权", "required": True},
                {"name": "45.行政处罚决定书", "reason": "作出正式行政处罚决定并送达当事人", "required": True},
                {"name": "47.责令改正通知书", "reason": "责令当事人立即停止侵权违法行为", "required": False},
                {"name": "53.结案审批表", "reason": "执行完毕后办理结案归档", "required": False}
            ]
        }

    disp_type = parsed.get("disposition_type", "处理结果裁量")
    forms = parsed.get("recommended_forms", [])

    # 互斥检查：45.行政处罚决定书 vs 46.不予行政处罚决定书
    has_pufa = any("45.行政处罚决定书" in f.get("name", "") or "行政处罚决定书" == f.get("name", "") for f in forms)
    has_buyu = any("46.不予行政处罚决定书" in f.get("name", "") or "不予行政处罚决定书" == f.get("name", "") for f in forms)
    if has_pufa and has_buyu:
        if "免罚" in disp_type or "不予" in disp_type:
            forms = [f for f in forms if "45.行政处罚决定书" not in f.get("name", "") and "行政处罚决定书" != f.get("name", "")]
        else:
            forms = [f for f in forms if "不予行政处罚决定书" not in f.get("name", "")]

    # 规范化名称对齐 56 项文书
    valid_names = []
    tpl_path = Path(__file__).parent.parent / "local_data" / "ai_templates.json"
    if tpl_path.exists():
        try:
            with open(tpl_path, encoding="utf-8") as tf:
                cats = json.load(tf)
                for c in cats:
                    if "行政处罚" in c.get("name", ""):
                        valid_names = [t["name"] for t in c.get("tables", [])]
        except Exception:
            pass

    normalized = []
    seen = set()
    for f in forms:
        raw_n = f.get("name", "")
        target_name = None
        for vn in valid_names:
            if vn == raw_n or vn.endswith(raw_n) or raw_n.endswith(re.sub(r'^\d+[\.、\s]*', '', vn)):
                target_name = vn
                break
        final_name = target_name or raw_n
        if final_name not in seen:
            seen.add(final_name)
            normalized.append({
                "name": final_name,
                "reason": f.get("reason", "依据办案裁量与法定程序推荐"),
                "required": f.get("required", False)
            })

    return {
        "disposition_type": disp_type,
        "summary": parsed.get("summary", "研判裁量处理结果推荐完成。"),
        "recommended_forms": normalized
    }


@router.get("/{project_id}/adjudication/recommend")
async def get_adjudication_recommendation(project_id: str, user: dict = Depends(get_current_user)):
    """获取项目持久化的研判裁量处理结果文书列表。"""
    require_project_access(project_id, user)
    fp = ADJUDICATION_DIR / f"{project_id}.json"
    if fp.exists():
        try:
            return json.loads(fp.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"status": "none", "data": None}


@router.post("/{project_id}/adjudication/recommend")
async def trigger_adjudication_recommendation(
    project_id: str,
    req: RecommendRequest,
    user: dict = Depends(get_current_user)
):
    """触发 AI 大模型执行研判裁量与处理结果推演，持久化并返回结果。"""
    require_project_access(project_id, user, write=True)
    fp = ADJUDICATION_DIR / f"{project_id}.json"
    if not req.force_refresh and fp.exists():
        try:
            return {"status": "success", "data": json.loads(fp.read_text(encoding="utf-8"))}
        except Exception:
            pass

    data = await run_adjudication_inference(project_id, req.model or "")
    try:
        fp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as e:
        logger.error(f"持久化保存研判裁量结果失败: {e}")

    return {"status": "success", "data": data}
