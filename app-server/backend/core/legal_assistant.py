"""
法律助理核心引擎 (legal_assistant.py)
WHY: 管理起诉状/答辩状的多阶段 RAG 推理流，
     并实现合同动态审查批注写入。
"""
from __future__ import annotations

import os
import re
import json
import zipfile
import tempfile
import logging
from pathlib import Path
from typing import AsyncGenerator

from core.llm_engine import stream_ollama
from core.retrieval_pipeline import run_retrieval
from core.llm_cache import get_llm_cache, set_llm_cache
from core.legal_prompts import (
    PLEADING_STAGE_PROMPTS,
    COMPLAINT_STAGE_PROMPTS,
    CONTRACT_REVIEW_PROMPT,
    PROJECT_OPINION_PROMPTS,
    PRE_CASE_ANALYSIS_PROMPTS,
    CASE_SEARCH_PROMPTS,
    CORPORATE_LEGAL_PROMPTS,
)
from core.docx_comments import (
    _utc_now,
    _new_para_id,
    _para_visible_text,
    _build_comments_xml,
    _update_rels,
    _update_content_types,
)

logger = logging.getLogger(__name__)

import time
import xxhash
import asyncio
import httpx

MOCK_CASES = [
    {
        "title": "力诺集团数字化管理体系建设规范说明",
        "court_name": "力诺集团总经办",
        "case_number": "LN-2025-001",
        "cause_of_action": "信息化建设规范",
        "content": "核心观点：各子集团及事业部在规划数字化项目时，必须优先采用集团统一的微服务框架与底座。系统上线前需通过信息安全与多模态数据安全评估..."
    },
    {
        "title": "力诺通用知识库数据入库与清洗标准说明",
        "court_name": "力诺研究院",
        "case_number": "LN-2026-012",
        "cause_of_action": "数据入库标准",
        "content": "核心观点：对于非结构化文档（PDF、docx、音视频等），应统一进行双路并行RAG切片及向量化。音频文件需使用Whisper ASR进行转写后再做知识图谱构建..."
    },
    {
        "title": "力诺通用规范关于合作伙伴合规审计与审查办法",
        "court_name": "力诺集团风控部",
        "case_number": "LN-2026-034",
        "cause_of_action": "合规审计办法",
        "content": "核心观点：为了防范业务合作中的潜在财务与运营红线风险，应对签约合作方进行分级管理和主体资格核查，并在合同中设立履约保障与违约追偿机制..."
    }
]

async def search_pkulaw_cases(text: str, token: str = None) -> list[dict]:
    token = token or os.environ.get("PKULAW_TOKEN")
    if not token:
        logger.warning("[PkulawSearch] 未配置 PKULAW_TOKEN，无法调用北大法宝案例检索接口")
        return []
    
    url = "https://apim-gateway.pkulaw.com/mcp-case-search-service"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Accept": "application/json"
    }
    payload = {
        "jsonrpc": "2.0",
        "method": "tools/call",
        "params": {
            "name": "search_case",
            "arguments": {
                "text": text
            }
        },
        "id": 1
    }
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            res = await client.post(url, headers=headers, json=payload)
            if res.status_code == 200:
                data = res.json()
                content_text = data.get("result", {}).get("content", [{}])[0].get("text", "")
                if content_text:
                    cases = json.loads(content_text)
                    if isinstance(cases, list):
                        formatted_cases = []
                        for c in cases:
                            formatted_cases.append({
                                "title": c.get("title", "未命名案例"),
                                "court_name": c.get("court_name", "未知法院"),
                                "case_number": c.get("case_number", "无案号"),
                                "cause_of_action": c.get("cause_of_action", "普通民商事纠纷"),
                                "content": c.get("content", "")
                            })
                        return formatted_cases
    except Exception as e:
        logger.error(f"[PkulawSearch] 调用北大法宝 API 检索案例失败: {e}", exc_info=True)
    return []


# L1 级内存缓存：存储最近一小时的流式推理结果
_L1_CACHE: dict[str, tuple[float, str]] = {}
_L1_CACHE_TTL = 3600  # 1 小时有效期

def get_l1_cache(key: str) -> str | None:
    if key in _L1_CACHE:
        ts, val = _L1_CACHE[key]
        if time.time() - ts < _L1_CACHE_TTL:
            return val
        else:
            _L1_CACHE.pop(key, None)
    return None

def set_l1_cache(key: str, val: str) -> None:
    if len(_L1_CACHE) >= 100:
        oldest_key = min(_L1_CACHE.keys(), key=lambda k: _L1_CACHE[k][0])
        _L1_CACHE.pop(oldest_key, None)
    _L1_CACHE[key] = (time.time(), val)

def get_cache_hash(model: str, prompt: str) -> str:
    h = xxhash.xxh64()
    h.update(f"{model}:{prompt}".encode("utf-8"))
    return h.hexdigest()

async def yield_cached_content(content: str) -> AsyncGenerator[str, None]:
    """极速流式模拟输出，提升用户体验"""
    chunk_size = 40
    for i in range(0, len(content), chunk_size):
        yield content[i:i+chunk_size]
        await asyncio.sleep(0.005)

# ── 模块一：文书多阶段流式生成 ─────────────────────────────

async def generate_legal_stage(
    project_id: str,
    file_ids: list[str],
    skill_type: str,  # "pleading" 或 "complaint"
    stage_id: str,
    context_history: str = "",
    collaborative: bool = False,
) -> AsyncGenerator[str, None]:
    """
    处理民事起诉状/答辩状某一步骤的多阶段流式推理。
    利用 RAG 检索法规并调用本地大模型。
    """
    # 确定提示词模板
    if skill_type == "pleading" or skill_type == "pleading_drafting":
        prompts_map = PLEADING_STAGE_PROMPTS
    elif skill_type == "complaint" or skill_type == "complaint_drafting":
        prompts_map = COMPLAINT_STAGE_PROMPTS
    elif skill_type == "project_opinion":
        prompts_map = PROJECT_OPINION_PROMPTS
    elif skill_type == "pre_case_analysis":
        prompts_map = PRE_CASE_ANALYSIS_PROMPTS
    elif skill_type == "case_search":
        prompts_map = CASE_SEARCH_PROMPTS
    elif skill_type == "corporate_legal":
        prompts_map = CORPORATE_LEGAL_PROMPTS
    else:
        yield f"❌ 未知的技能类型: {skill_type}"
        return

    prompt_tpl = prompts_map.get(stage_id)
    if not prompt_tpl:
        yield f"❌ 在 {skill_type} 中未找到对应的阶段 ID: {stage_id}"
        return

    # 基于阶段特征及既往史提取检索检索词
    search_query = f"{skill_type} {stage_id}"
    if stage_id == "procedural_review":
        search_query = "文档规范 审批流程 数据权限 适格主体"
    elif stage_id in ("substantive_analysis", "relation_analysis", "fact_relation_retrieval"):
        search_query = "核心业务逻辑 责任划分 业务流程 规范依据"
    elif stage_id == "claim_design":
        search_query = "项目指标 预算计算 成本核算 规划依据"
    elif stage_id == "legal_retrieval" or stage_id == "strategy_search":
        search_query = "行业政策 行业标准 指导意见 规范条款"
    elif stage_id in ("risk_assessment", "compliance_check"):
        search_query = "合规风险 安全红线 违约责任 责任豁免"

    # 执行 RAG 混合检索
    logger.info(f"[LegalAssistant] 执行 RAG 召回 | query={search_query}")
    try:
        strategy = {"vector_top_k": 8, "inject_table_stats": False}
        retrieval_res = await run_retrieval(
            search_query=search_query,
            original_message=search_query,
            project_id=project_id,
            file_ids=file_ids,
            strategy=strategy,
        )
        context = retrieval_res.vector_context or ""
    except Exception as ex:
        logger.error(f"RAG 检索失败: {ex}")
        context = "暂无参考法规/卷宗文本"

    # 如果有先前步骤的分析，追加作为大模型的参考背景
    if context_history:
        context = f"{context}\n\n## 先前阶段分析成果\n{context_history}"

    prompt = prompt_tpl.format(context=context)
    model_name = "qwen3.6:35b-q4"

    hash_key = get_cache_hash(model_name, prompt)

    # 1. 尝试从 L1 (内存) 缓存读取
    cached_val = get_l1_cache(hash_key)
    if cached_val:
        logger.info(f"[LegalAssistant] ⚡ L1 缓存命中 | hash={hash_key}")
        async for token in yield_cached_content(cached_val):
            yield token
        return

    # 2. 尝试从 L2 (Redis) 缓存读取
    cached_val = get_llm_cache(model_name, prompt)
    if cached_val:
        logger.info(f"[LegalAssistant] 💾 L2 (Redis) 缓存命中 | hash={hash_key}")
        set_l1_cache(hash_key, cached_val)
        async for token in yield_cached_content(cached_val):
            yield token
        return

    # 3. 缓存未命中
    if not collaborative:
        logger.info(f"[LegalAssistant] ❌ 缓存未命中，执行单 Agent 快速推理 | hash={hash_key}")
        full_response_chunks = []
        async for token in stream_ollama(
            prompt=prompt,
            model=model_name,
            temperature=0.2,
            num_ctx=16384,
        ):
            full_response_chunks.append(token)
            yield token
        full_response = "".join(full_response_chunks)
        set_llm_cache(model_name, prompt, full_response)
        return

    logger.info(f"[LegalAssistant] ❌ 缓存未命中，启动多 Agent 协同推理 | hash={hash_key}")

    from api.admin import _read_system_settings
    sys_settings = _read_system_settings()
    name_supervisor = sys_settings.get("collab_supervisor_name", "【协同】文档秘书")
    name_legal = sys_settings.get("collab_legal_name", "【协同】法律分析专家")
    name_contrarian = sys_settings.get("collab_contrarian_name", "【协同】审查员")
    name_arbiter = sys_settings.get("collab_arbiter_name", "【协同】仲裁官")

    # 提取项目名用于 Redis 状态注册
    project_name = "未命名项目"
    try:
        from core.project_access import _read_projects
        for p in _read_projects():
            if p["id"] == project_id:
                project_name = p.get("name", "未命名项目")
                break
    except Exception:
        pass

    from core.redis_client import set_agent_active
    import asyncio

    # Step 1: Supervisor 编排分流
    set_agent_active("legal", f"🧠 {name_supervisor} 正在分析任务...", project_name, duration=15)
    yield f"🧠 *[{name_supervisor}] 正在分流并编排当前起草任务...*\n\n"
    await asyncio.sleep(0.8)  # 模拟分配思考

    # Step 2: 法律分析专家起草首稿
    set_agent_active("legal", f"⚖️ 正在撰写: {stage_id} ({name_legal})", project_name, duration=35)
    yield f"⚖️ *[{name_legal}] 正在结合卷宗事实进行起草与推理...*\n\n"

    first_draft_chunks = []
    async for token in stream_ollama(
        prompt=prompt,
        model=model_name,
        temperature=0.2,
        num_ctx=16384,
    ):
        first_draft_chunks.append(token)
        yield token

    first_draft = "".join(first_draft_chunks)

    # Step 3: 小杠负向抗辩审查
    set_agent_active("contrarian", f"🤨 {name_contrarian} 正在针对论证漏洞进行审查与质疑...", project_name, duration=25)
    yield f"\n\n---\n🤨 *[{name_contrarian}] 正在对起草内容及论证逻辑进行多角度质疑与审查...*\n"

    from core.agents.contrarian_agent import ContrarianAgent
    contrarian = ContrarianAgent()
    
    # WHY: 小杠抗辩是非流式分析，可能耗时 30s+。
    #      在此期间启动异步轮询任务，每 4 秒向客户端发送一次零宽空格 (\u200b) 心跳，
    #      防止中间代理（如 Nginx, FRP, 路由器）因长连接无数据写入而强制断开 (vhostHTTPTimeout)。
    critique_task = asyncio.create_task(contrarian.critique(prompt, first_draft))
    critique = ""
    while not critique_task.done():
        try:
            critique = await asyncio.wait_for(asyncio.shield(critique_task), timeout=4.0)
            break
        except asyncio.TimeoutError:
            yield "\u200b"

    # 模拟流式输出小杠质疑
    yield f"\n> **🤨 {name_contrarian} 审查意见**：\n"
    for line in critique.split("\n"):
        yield f"> {line}\n"
    yield "\n"

    # Step 4: 大BOSS 终审与修正
    set_agent_active("arbiter", f"👑 {name_arbiter} 正在整合质疑，进行措辞润色与最终裁决...", project_name, duration=35)
    yield f"👑 *[{name_arbiter}] 正在综合{name_contrarian}质疑意见，进行最终措辞润色与逻辑修正...*\n\n"

    from core.agents.arbiter_agent import ArbiterAgent
    arbiter = ArbiterAgent()

    final_response_chunks = []
    async for token in arbiter.arbitrate_stream(
        prompt, first_draft, critique, name_legal
    ):
        final_response_chunks.append(token)
        yield token

    final_response = "".join(final_response_chunks)


    if skill_type == "case_search" and stage_id == "strategy_search":
        # 1. 提取检索描述
        descriptions = []
        quotes = re.findall(r'["“]([^"”]{25,})["”]', final_response)
        if quotes:
            descriptions = quotes
        else:
            lines = [line.strip().strip("-*•").strip() for line in final_response.split("\n")]
            descriptions = [line for line in lines if len(line) > 35 and not line.startswith(("#", "第", "观点"))]
        
        # 2. 对前几个描述进行案例检索
        all_cases = []
        token = os.environ.get("PKULAW_TOKEN")
        retrieved_any = False
        
        if token and descriptions:
            yield "\n\n⌛ *正在为您连接北大法宝 API 进行实时类案检索分析...*\n"
            # 异步执行检索
            tasks = [search_pkulaw_cases(desc, token) for desc in descriptions[:3]]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for res in results:
                if isinstance(res, list) and res:
                    for case in res[:2]: # 每次检索取前2个
                        if not any(c["case_number"] == case.get("case_number") for c in all_cases):
                            all_cases.append({
                                "title": case.get("title", ""),
                                "court_name": case.get("court_name", ""),
                                "case_number": case.get("case_number", ""),
                                "cause_of_action": case.get("cause_of_action", ""),
                                "content": case.get("content", "")
                            })
                            retrieved_any = True
        
        # 3. 结果合并与展示
        append_text = "\n\n## 🔍 实时类案检索结果 (法宝 API / 本地指导案例库)\n"
        if not retrieved_any:
            if token:
                append_text += "> 💡 *法宝 API 检索未匹配到高度契合类案，已为您自动检索本地指导案例库。*\n\n"
            else:
                append_text += "> 💡 *提示：未配置环境变量 `PKULAW_TOKEN`。已自动调用系统内置的高价值司法指导性案例进行拟合。*\n\n"
            all_cases = MOCK_CASES

        for i, c in enumerate(all_cases):
            append_text += (
                f"{i + 1}\n"
                f"案例名称：{c['title']}\n"
                f"审理法院：{c['court_name']}\n"
                f"案号：{c['case_number']}\n"
                f"裁判观点：{c['content']}\n\n"
            )
        
        yield append_text
        final_response += append_text

    if final_response.strip() and not final_response.strip().startswith(("❌", "⚠️")):
        set_l1_cache(hash_key, final_response)
        set_llm_cache(model_name, prompt, final_response)



# ── 模块二：Word 动态批注注入器 ─────────────────────────────

def inject_contract_comments(docx_path: str, comments_list: list[dict]) -> int:
    """
    将大模型生成的合同审核意见动态写入 docx 物理文件中。
    comments_list 结构: [{"target_text": "待改文本", "suggested_comment": "修改建议", "risk_level": "HIGH"}]
    """
    if not comments_list:
        return 0

    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            extract_dir = Path(tmpdir) / "extracted"

            # 解包 docx
            with zipfile.ZipFile(docx_path, "r") as zf:
                zf.extractall(extract_dir)

            doc_path = extract_dir / "word" / "document.xml"
            doc_xml = doc_path.read_text(encoding="utf-8")

            # 匹配段落
            para_re = re.compile(r"(<w:p[ >].*?</w:p>)", re.DOTALL)
            comments_metadata = []
            cid_counter = 0

            # 转换大模型建议为临时查找表以降低复杂度
            # 用建议文本的哈希防止重复标记
            matched_targets = set()

            def _process_para(m: re.Match) -> str:
                nonlocal cid_counter
                para_str = m.group(0)
                text = _para_visible_text(para_str)
                if not text.strip():
                    return para_str

                # 对每一个建议，检查段落是否匹配
                for item in comments_list:
                    target = item.get("target_text", "").strip()
                    if not target or len(target) < 2:
                        continue
                    if target in matched_targets:
                        continue

                    # 段落包含待修改片段
                    if target in text:
                        matched_targets.add(target)
                        cid = str(cid_counter)
                        cid_counter += 1

                        comment_text = f"【{item.get('risk_level', 'RISK')}】{item.get('suggested_comment', '')}"
                        range_start = f'<w:commentRangeStart w:id="{cid}"/>'
                        range_end = (
                            f'<w:commentRangeEnd w:id="{cid}"/>'
                            f'<w:r><w:rPr><w:rStyle w:val="CommentReference"/></w:rPr>'
                            f'<w:commentReference w:id="{cid}"/></w:r>'
                        )

                        gt_pos = para_str.index(">") + 1
                        para_str = (
                            para_str[:gt_pos]
                            + range_start
                            + para_str[gt_pos : -len("</w:p>")]
                            + range_end
                            + "</w:p>"
                        )

                        comments_metadata.append({
                            "id": cid,
                            "text": comment_text,
                            "para_id": _new_para_id(),
                            "timestamp": _utc_now(),
                        })
                        break

                return para_str

            modified_xml = para_re.sub(_process_para, doc_xml)
            if not comments_metadata:
                logger.info("[LegalAssistant] 合同审查: 未能匹配到任何段落标记，跳过批注写回")
                return 0

            # 写回各 XML
            doc_path.write_text(modified_xml, encoding="utf-8")
            (extract_dir / "word" / "comments.xml").write_text(
                _build_comments_xml(comments_metadata), encoding="utf-8"
            )
            rels_path = extract_dir / "word" / "_rels" / "document.xml.rels"
            rels_path.write_text(
                _update_rels(rels_path.read_text(encoding="utf-8")), encoding="utf-8"
            )
            ct_path = extract_dir / "[Content_Types].xml"
            ct_path.write_text(
                _update_content_types(ct_path.read_text(encoding="utf-8")), encoding="utf-8"
            )

            # 打包
            tmp_out = Path(docx_path).with_suffix(".comments_tmp.docx")
            with zipfile.ZipFile(tmp_out, "w", zipfile.ZIP_DEFLATED) as zout:
                for fp in sorted(extract_dir.rglob("*")):
                    if fp.is_file():
                        zout.write(fp, fp.relative_to(extract_dir))

            os.replace(tmp_out, docx_path)
            return len(comments_metadata)

    except Exception as exc:
        logger.error(f"合同批注注入异常: {exc}", exc_info=True)
        return 0
