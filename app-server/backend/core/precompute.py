"""
三模式全文预计算引擎：generate / replace / clone。

WHY: 旧版预计算仅做 Slot 抽取（结果全为空，形同虚设）。
     新版在后台完整执行 RAG 检索 → Prompt 构建 → LLM 推理，
     将生成的 Markdown 全文缓存到磁盘。
     用户后续点击生成按钮时，前端直接从缓存读取并渲染，秒级完成。
"""
from __future__ import annotations

import json
import logging
import time
import re
import shutil
from pathlib import Path
from typing import List, Optional

from core.config import settings
from core.redis_client import get_redis

logger = logging.getLogger(__name__)

EXEMPLARS_DIR = Path(settings.DATA_DIR) / "exemplars"
DRAFT_CACHE_DIR = Path(settings.DATA_DIR) / "draft_cache"

VALID_MODES = ("generate", "replace", "clone")

# WHY: 低优先级延迟——每生成一个章节后等待 1 秒，
#      让前端的实时请求有机会优先获得 GPU 推理槽位。
_INTER_SECTION_DELAY = 1.0


# ═══════════════════════════════════════════════════
# 缓存读写
# ═══════════════════════════════════════════════════

def _get_cache_dir(project_id: str, mode: str) -> Path:
    return DRAFT_CACHE_DIR / project_id / mode


def get_draft_cache(
    project_id: str, section_id: str, mode: str
) -> Optional[dict]:
    """读取单章节缓存。返回 None 表示无缓存。"""
    fp = _get_cache_dir(project_id, mode) / f"{section_id}.json"
    if not fp.exists():
        return None
    try:
        return json.loads(fp.read_text(encoding="utf-8"))
    except Exception:
        return None


def get_all_draft_caches(project_id: str, mode: str) -> List[dict]:
    """读取指定模式下所有已缓存的章节。按 section_index 排序。"""
    cache_dir = _get_cache_dir(project_id, mode)
    if not cache_dir.exists():
        return []
    results = []
    for fp in cache_dir.glob("*.json"):
        try:
            data = json.loads(fp.read_text(encoding="utf-8"))
            if data.get("status") in ("ok", "skipped"):
                results.append(data)
        except Exception:
            continue
    results.sort(key=lambda x: x.get("section_index", 9999))
    return results


def invalidate_draft_cache(project_id: str, mode: Optional[str] = None):
    """
    清除预计算缓存。mode=None 时清除该项目全部模式的缓存。
    WHY: 入库文件变更或范文重传时自动调用，防止使用过期数据。
    """
    if mode:
        cache_dir = _get_cache_dir(project_id, mode)
        if cache_dir.exists():
            shutil.rmtree(cache_dir, ignore_errors=True)
            logger.info(f"草稿缓存已清除: {project_id}/{mode}")
    else:
        project_cache = DRAFT_CACHE_DIR / project_id
        if project_cache.exists():
            shutil.rmtree(project_cache, ignore_errors=True)
            logger.info(f"草稿缓存已全部清除: {project_id}")


# ═══════════════════════════════════════════════════
# 进度统计
# ═══════════════════════════════════════════════════

def get_project_precompute_stats(project_id: str) -> dict:
    """
    返回项目三个模式各自的预计算进度。
    WHY: 前端需实时展示每个模式的进度条。
    """
    # 读取范文章节数量
    exemplar_path = EXEMPLARS_DIR / f"{project_id}.json"
    exemplar_total = 0
    if exemplar_path.exists():
        try:
            data = json.loads(exemplar_path.read_text(encoding="utf-8"))
            exemplar_total = len(data.get("sections", []))
        except Exception:
            pass

    # 读取模板章节数量（generate 模式用模板，不用范文）
    template_path = Path(settings.DATA_DIR) / "templates" / f"{project_id}.json"
    template_total = 0
    if template_path.exists():
        try:
            data = json.loads(template_path.read_text(encoding="utf-8"))
            template_total = len(data.get("sections", []))
        except Exception:
            pass

    r = get_redis()

    result = {}
    for mode in VALID_MODES:
        # generate 用模板章节数，replace/clone 用范文章节数
        total = template_total if mode == "generate" else exemplar_total

        # 统计已缓存文件数
        cache_dir = _get_cache_dir(project_id, mode)
        completed = 0
        if cache_dir.exists():
            completed = len(list(cache_dir.glob("*.json")))

        percent = round(completed / total * 100, 2) if total > 0 else 0.0

        # 运行状态
        status = "idle"
        current_section = None
        if r:
            rkey = f"precompute:running:{project_id}:{mode}"
            if r.get(rkey):
                status = "running"
                sec_bytes = r.get(
                    f"precompute:current_section:{project_id}:{mode}"
                )
                if sec_bytes:
                    current_section = (
                        sec_bytes.decode("utf-8")
                        if isinstance(sec_bytes, bytes)
                        else str(sec_bytes)
                    )
            elif r.get(f"precompute:queued:{project_id}:{mode}"):
                status = "queued"
            elif completed > 0 and completed >= total:
                status = "completed"

        result[mode] = {
            "total": total,
            "completed": completed,
            "percent": percent,
            "status": status,
            "current_task": (
                {"section_title": current_section}
                if current_section
                else None
            ),
        }

    return result


# ═══════════════════════════════════════════════════
# 调度：投递到 Celery
# ═══════════════════════════════════════════════════

def schedule_precompute(
    project_id: str, mode: str = "replace", is_user_action: bool = False
):
    """
    将预计算任务投递到 Celery slow_queue。
    WHY: countdown=10 实现防抖（连续点击只执行最后一次）。
    """
    if mode not in VALID_MODES:
        logger.warning(f"无效的预计算模式: {mode}")
        return

    from core.celery_app import celery_app

    try:
        r = get_redis()
        queue_key = f"precompute:queued:{project_id}:{mode}"

        if r:
            # 非用户操作 + 已排队 → 跳过
            if not is_user_action and r.get(queue_key):
                return

            # 撤销旧任务（防抖）
            task_key = f"precompute:task_id:{project_id}:{mode}"
            old_task_id = r.get(task_key)
            if old_task_id:
                celery_app.control.revoke(old_task_id)

        result = celery_app.send_task(
            "worker.precompute_project",
            args=[project_id, mode],
            queue="slow_queue",
            countdown=10,
        )

        if r:
            r.setex(
                f"precompute:task_id:{project_id}:{mode}",
                600,
                result.id,
            )
            r.setex(queue_key, 86400, "1")

        logger.info(
            f"📤 Precompute dispatched: {project_id} mode={mode} "
            f"(task_id={result.id})"
        )
    except Exception as e:
        logger.error(f"Failed to dispatch precompute: {e}")


# ═══════════════════════════════════════════════════
# 核心：全文预计算执行
# ═══════════════════════════════════════════════════

async def _generate_single_section(
    title: str,
    mode: str,
    project_id: str,
    project_name: str,
    model: str,
    exemplar_id: str,
    section_index: int,
    section_level: int,
    prior_context: str = "",
    exemplar_content_override: str = "",
) -> dict:
    """
    为单个章节生成完整文本。复用 generate.py 的 Prompt 构建逻辑。
    返回 {"markdown", "sources", "verify_warnings", "status"}
    """
    import asyncio
    from starlette.concurrency import run_in_threadpool
    from core.llm_engine import (
        stream_ollama, PARAGRAPH_PROMPT,
        REPLACE_PROMPT, CLONE_PROMPT, DUAL_TRACK_PROMPT,
    )
    from core.vector_store import query_by_file_ids
    from core.graph_rag import graph_engine

    # 延迟导入 generate.py 中的辅助函数，避免循环依赖
    from api.generate import (
        _match_exemplar_section,
        _extract_replace_keywords,
        _get_global_project_context,
        _get_section_image_hint,
        _extract_place_names,
        _is_structural_heading,
    )

    # ── 结构性标题跳过 ──
    if mode not in ("replace", "clone") and exemplar_id and section_index >= 0:
        is_structural = _is_structural_heading(
            exemplar_id, title, section_index
        )
        is_protected = "前言" in title or "概述" in title
        if is_structural and not is_protected and section_level <= 1:
            return {"markdown": "", "sources": [], "status": "skipped"}

    # ── 读取项目人设 ──
    custom_persona = ""
    from core.project_access import _read_projects
    for p in _read_projects():
        if p["id"] == project_id:
            project_name = project_name or p.get("name", "")
            custom_persona = (
                p.get("metadata", {}).get("aiPersona", "").strip()
            )
            break

    # ── 范文匹配 ──
    # WHY: replace/clone 模式预计算时，sections 就来自范文本身，
    #      直接使用 exemplar_content_override 可避免 _match_exemplar_section
    #      的模糊匹配失败或匹配到错误章节。
    exemplar_content = ""
    if exemplar_content_override:
        exemplar_content = exemplar_content_override
    elif exemplar_id:
        exemplar_content = _match_exemplar_section(
            exemplar_id, title, section_index, section_level, model=model
        )

    # ── RAG 检索 ──
    context = ""
    source_files = []
    # WHY: 预计算使用全项目文件（file_ids=[]），
    #      由 query_by_file_ids 的 hierarchical prefilter 自动筛选
    if mode in ("replace", "clone") and exemplar_content:
        exemplar_keywords = _extract_replace_keywords(exemplar_content)
        rag_query = f"{project_name} {title} {exemplar_keywords}".strip()
    else:
        rag_query = (
            f"{project_name} {title}" if project_name else title
        )

    # WHY: Replace/Clone 只需精准替换数据，不需要海量参考资料（与 generate.py 一致）
    _rag_top_k = 4 if mode in ("replace", "clone") else 8
    docs = await run_in_threadpool(
        query_by_file_ids, rag_query, [], project_id, _rag_top_k
    )

    # WHY: 与 generate.py 一致 — replace/clone 模式过滤纯图纸元数据 chunk
    if mode in ("replace", "clone") and docs:
        _KEEP_KEYWORDS = {'建设地点', '行政村', '建设规模', '工程概况', '编制说明',
                          '项目概况', '设计依据', '建设范围', '项目名称'}
        filtered_docs = []
        for d in docs:
            content = d.get("content", "")
            if content.lstrip().startswith("[图件解析]"):
                if any(kw in content for kw in _KEEP_KEYWORDS):
                    filtered_docs.append(d)
            else:
                filtered_docs.append(d)
        docs = filtered_docs

    if docs:
        seen = set()
        for d in docs:
            fname = d["metadata"].get("filename", "未知")
            if fname not in seen:
                source_files.append(fname)
                seen.add(fname)
        context_parts = []
        for d in docs:
            fname = d["metadata"].get("filename", "未知")
            confidence = d["metadata"].get("confidence", 1.0)
            warning = (
                " (⚠️注：低可信度 OCR)"
                if confidence < 0.4 else ""
            )
            context_parts.append(
                f"[来源: {fname}]{warning}\n{d['content']}"
            )
        context = "\n\n".join(context_parts)

    # ── [A1] 全局项目指标（与 generate.py L1052 一致：replace/clone 跳过）──
    # WHY: Replace/Clone 以范文为蓝图，全局指标检索价值低且占用大量 token。
    _ENG_KW = {'水利', '水保', '水土', '地价', '区片', '测绘', '工程', '规划'}
    if any(kw in (project_name or '') for kw in _ENG_KW) and mode not in ("replace", "clone"):
        global_ctx = await _get_global_project_context(
            project_name, [], project_id
        )
        if global_ctx:
            context = (
                f"## 项目核心指标（全局）\n{global_ctx}\n\n"
                f"## 章节相关资料\n{context}"
                if context else global_ctx
            )

    # ── [A3] 图谱注入（与 generate.py L1065 一致：replace/clone 限 4 路径）──
    try:
        graph_query = (
            f"{project_name} {title}" if project_name else title
        )
        _graph_max = 4 if mode in ("replace", "clone") else 8
        graph_result = await graph_engine.hybrid_search(
            graph_query, project_id=project_id, max_paths=_graph_max
        )
        if graph_result.get("graph_context"):
            context = f"{graph_result['graph_context']}\n\n{context}"
    except Exception as e:
        logger.warning(f"图谱检索降级: {e}")

    # ── Replace/Clone 模式：注入完整表格（与 generate.py 对齐）──
    # WHY: Clone 模式：通过表名匹配直接替换范文中的表格体（绕过 LLM）。
    #      Replace 模式：通过语义检索注入完整表格到 context。
    if mode == "clone" and project_id and exemplar_content:
        # ── Clone 专用：表名匹配 → 直接替换范文表格体 ──
        try:
            from core.table_registry import match_tables_by_name
            from api.generate import _extract_exemplar_tables, _replace_exemplar_tables
            ex_tables = _extract_exemplar_tables(exemplar_content)
            if ex_tables:
                ex_names = [t['name'] for t in ex_tables]
                matches = match_tables_by_name(
                    ex_names, project_id, None,
                )
                if matches:
                    exemplar_content, replaced = _replace_exemplar_tables(
                        exemplar_content, ex_tables, matches,
                    )
                    logger.info(
                        f"✅ [clone] 表格直接替换 | "
                        f"{replaced}/{len(ex_tables)} 张表 | "
                        f"标题={list(matches.keys())}"
                    )
                # 未匹配的表格回退到语义检索
                unmatched_names = [t['name'] for t in ex_tables if t['name'] not in matches]
                if unmatched_names:
                    from core.table_registry import query_tables
                    for uname in unmatched_names[:3]:
                        _fb_results = query_tables(
                            f"{project_name} {uname}", project_id,
                            None, max_tables=1,
                        )
                        if _fb_results:
                            t = _fb_results[0]
                            md = t.get('markdown', '')
                            if len(md) > 4000:
                                md = md[:4000] + "\n...[表格过长，已截断]"
                            context = (
                                f"【完整表格: {t['title']}】"
                                f"(来源: {t['source_file']})\n{md}"
                                f"\n\n{context}"
                            )
        except Exception as e:
            logger.warning(f"Clone 表名匹配降级: {e}")

    elif mode == "replace" and project_id and exemplar_content:
        # ── Replace 模式：保持原有语义检索注入逻辑 ──
        try:
            from core.table_registry import query_tables
            _table_query = f"{project_name} {title}"
            _exemplar_bold_titles = re.findall(
                r'\*\*(.+?)\*\*', exemplar_content
            )
            _exemplar_table_refs = re.findall(
                r'(表\d[\d\-]*\s*[^\n|]{2,30})', exemplar_content
            )
            _tbl_hints = _exemplar_bold_titles + _exemplar_table_refs
            if _tbl_hints:
                _table_query = f"{project_name} {_tbl_hints[0].strip()}"

            matched_tables = query_tables(
                _table_query, project_id,
                None,  # 预计算使用全项目文件
                max_tables=2,
            )
            if matched_tables:
                table_parts = []
                for t in matched_tables:
                    md = t.get('markdown', '')
                    if len(md) > 4000:
                        md = md[:4000] + "\n...[表格过长，已截断]"
                    table_parts.append(
                        f"【完整表格: {t['title']}】"
                        f"(来源: {t['source_file']})\n{md}"
                    )
                table_injection = "\n\n".join(table_parts)
                context = (
                    f"## 📊 精确匹配的完整表格（优先使用此数据替换范文）\n"
                    f"⚠️ 以下表格包含新项目「{project_name}」的精确数据，"
                    f"表格中的每个单元格都可直接用于替换范文。\n"
                    f"⚠️ **严禁忽视此表格**：范文中引用的统计表、汇总表的数据"
                    f"必须从以下表格中逐行提取，不得填写[待补充]。\n"
                    f"⚠️ **逐行对应**：表格每一行对应一个村/一个条目，"
                    f"请按行读取并填入范文的对应位置。\n\n"
                    f"{table_injection}\n\n{context}"
                )
                logger.info(
                    f"🗃️ [replace] 表格注入 | "
                    f"{len(matched_tables)} 张表 | "
                    f"标题={[t['title'] for t in matched_tables]}"
                )
        except Exception as e:
            logger.warning(f"Replace 表格注入降级: {e}")

    # ── [A2] 前文注入（与 generate.py 一致：replace/clone 跳过）──
    # WHY: replace/clone 以范文为唯一结构蓝图，prior_context 会污染 project_facts。
    if prior_context and mode not in ("replace", "clone"):
        context = f"{context}\n\n## 前文结构参考\n{prior_context[-2000:]}"
    if not context:
        context = "（暂无参考资料，请基于专业知识撰写）"

    # ── [A4] replace/clone 模式 context 最终截断兜底（与 generate.py 对齐）──
    # WHY: 从 6000 提升到 8000，为完整表格注入预留空间。
    if mode in ("replace", "clone") and exemplar_content and context:
        from api.generate import _is_list_section
        if _is_list_section(exemplar_content):
            _max_facts = 500
        else:
            _max_facts = 8000
        if len(context) > _max_facts:
            context = context[:_max_facts]

    # ── 地名正字 ──
    place_names = _extract_place_names(context)
    place_name_hint = ""
    if place_names:
        place_name_hint = (
            f"\n\n【⚠️ 强制地名正字约束】\n"
            f"请必须逐字核对以下地名，严禁同音字替代：\n"
            f"{', '.join(place_names)}\n"
            f"（此约束仅供内部检查，严禁输出到正文中）"
        )

    # ── 图件指令 ──
    image_hint = ""
    if exemplar_id and section_index >= 0:
        image_hint = _get_section_image_hint(
            exemplar_id, section_index, title,
            project_name or "未知项目"
        )

    # ── Prompt 路由 ──
    # 注意：此处为 fallback/普通生成准备 prompt，超长文下面会覆盖
    if mode == "clone" and exemplar_content:
        prompt = CLONE_PROMPT.format(
            exemplar_content=exemplar_content,
            project_facts=context,
            project_name=project_name or "未知项目",
        )
    elif mode in ("replace", "clone"):
        if not exemplar_content:
            # Graceful Fallback
            prompt = PARAGRAPH_PROMPT.format(
                title=title, context=context,
                project_name=project_name or "未知项目",
            )
        else:
            # WHY: 与 generate.py 保持一致的三场景 table_rule 分级
            _table_lines = re.findall(r'^\|.+\|', exemplar_content, re.MULTILINE)
            _total_lines = [l for l in exemplar_content.split('\n') if l.strip()]
            _table_ratio = len(_table_lines) / max(len(_total_lines), 1)

            if not _table_lines:
                # 场景 A：纯文本
                # WHY: 检查范文是否引用了表名（如"表2-1项目区耕地现状统计表"），
                #      若引用了表名且参考资料有完整表格，则不应禁止创建表格。
                _has_table_ref = bool(re.search(r'表\d[\d\-]*\s*\S{2,}', exemplar_content))
                if _has_table_ref:
                    table_rule = (
                        '7. **表格引用处理**：范文底稿是叙述性文本，但引用了数据表格名称。'
                        '若参考资料中包含📊标记的完整表格且与范文引用的表名对应，'
                        '你必须在引用位置之后输出完整的 Markdown 表格，数据从参考资料逐行复制。'
                        '除此之外，叙述性段落严禁转换为表格结构'
                    )
                else:
                    table_rule = '7. **⚠️ 严禁创建表格**：范文底稿中没有任何表格，严禁创建任何表格结构'
            elif _table_ratio < 0.6:
                # 场景 B：混合内容
                table_rule = (
                    '7. **混合内容处理（文本+表格）**：范文底稿中同时包含叙述性段落和数据表格。你必须严格区分两者：\n'
                    '   - **叙述性段落**：必须以自然段落形式输出，**严禁用管道符 `|` 包裹文字**\n'
                    '   - **数据表格**：严格保持范文表格的行列结构和表头文字不变，用新项目数据逐单元格替换\n'
                    '   - 若范文表格包含合计/小计/占比等汇总行，需根据新数据重新计算后填写\n'
                    '   - ⚠️ 表格和段落中的项目特定数据均遵循规则4的[待补充]约束'
                )
            else:
                # 场景 C：表格为主
                table_rule = (
                    '7. **表格处理**：范文中已有表格。你必须：\n'
                    '（a）严格保持范文表格的行列结构和表头文字不变；\n'
                    '（b）用新项目的数据逐单元格替换；\n'
                    '（c）若范文表格包含合计/小计/占比等汇总行，需根据新数据重新计算后填写；\n'
                    '（d）⚠️ 项目特定数据遵循规则4的[待补充]约束，严禁照搬范文中旧项目数据；\n'
                    '（e）⚠️ **合并单元格识别**：若范文表格中存在连续多列内容完全相同的行（如同一数据重复4列），'
                    '这是合并单元格的解析痕迹。输出时应将这些重复列合并为一列，仅保留一份数据，不要复制重复列'
                )

            # WHY: 与 generate.py 保持一致的三级 knowledge_rule
            from api.generate import _is_policy_section, _is_list_section
            _is_list = _is_list_section(exemplar_content)
            if _is_list:
                knowledge_rule = (
                    '5. **⚠️ 列表型章节（严禁扩写）**：范文底稿是一份引用清单（法规/标准/文件列表）。'
                    '你只能做以下操作：（a）保持清单的条目数量和格式完全一致；'
                    '（b）如有更新的法规/标准版本号可替换旧版本号；'
                    '（c）**严禁增加新条目、严禁插入解释性文字、严禁利用参考资料中的项目数据扩写内容**。'
                    '输出必须是与范文格式完全一致的引用清单，不多不少'
                )
            elif _is_policy_section(title):
                knowledge_rule = (
                    '5. **知识补充权限（宽松级）**：本章节属于概念性/政策性内容。'
                    '当参考资料缺乏行业背景、政策依据或技术标准解读时，'
                    '可调用专业知识库对**政策叙述、行业背景、技术原理**等通用性内容适当补充，'
                    '但段落数量仍须与范文保持一致。'
                    '⚠️ **但项目特定数据（地名、面积、金额、村名、行政区划、建设规模等）'
                    '仍必须严格遵循规则4的[待补充]约束，不得用知识库编造**'
                )
            else:
                knowledge_rule = '5. **知识补充权限（严格级）**：仅限对句子中的局部词汇进行完善，严禁生成新句子或段落，核心项目数据必须来自参考资料'

            prompt = REPLACE_PROMPT.format(
                exemplar_content=exemplar_content,
                project_facts=context,
                project_name=project_name or "未知项目",
                table_constraint=table_rule,
                knowledge_rule=knowledge_rule,
            )

            # WHY: 超长范文分段生成（与 generate.py 一致）
            #      水源工程等超长章节（29736字）无法一次性放入 Prompt，
            #      需要拆分后逐段走 REPLACE/CLONE 流程再拼接。
            from api.generate import _split_long_exemplar
            _max_exemplar = 3000
            _MAX_SEGMENTS = 10
            if len(exemplar_content) > _max_exemplar:
                segments = _split_long_exemplar(exemplar_content, max_chars=_max_exemplar)
                if len(segments) > _MAX_SEGMENTS:
                    # 尾部合并
                    merged_tail = '\n'.join(segments[_MAX_SEGMENTS - 1:])
                    segments = segments[:_MAX_SEGMENTS - 1] + [merged_tail[:_max_exemplar]]
                logger.info(
                    f"📐 超长范文分段 | {title[:20]} | {len(exemplar_content)}字 → {len(segments)}段"
                )
                all_parts = []
                for seg_idx, seg in enumerate(segments):
                    seg_table_lines = re.findall(r'^\|.+\|', seg, re.MULTILINE)
                    seg_total_lines = [l for l in seg.split('\n') if l.strip()]
                    seg_table_ratio = len(seg_table_lines) / max(len(seg_total_lines), 1)
                    if not seg_table_lines:
                        seg_table_rule = '7. **⚠️ 严禁创建表格**：本段范文中没有任何表格，严禁创建任何表格结构'
                    elif seg_table_ratio < 0.6:
                        seg_table_rule = table_rule  # 继承父级混合规则
                    else:
                        seg_table_rule = table_rule  # 继承父级表格规则

                    if mode == "clone":
                        seg_prompt = CLONE_PROMPT.format(
                            exemplar_content=seg,
                            project_facts=context,
                            project_name=project_name or "未知项目",
                        )
                    else:
                        seg_prompt = REPLACE_PROMPT.format(
                            exemplar_content=seg,
                            project_facts=context,
                            project_name=project_name or "未知项目",
                            table_constraint=seg_table_rule,
                            knowledge_rule=knowledge_rule,
                        )
                    if image_hint and seg_idx == len(segments) - 1:
                        seg_prompt += image_hint
                    if place_name_hint:
                        seg_prompt += place_name_hint
                    if custom_persona:
                        seg_prompt = (
                            f"【专属角色注入】\n{custom_persona}\n\n==========\n\n"
                            + seg_prompt
                        )
                    seg_prompt += "\n\n/no_think"

                    seg_tokens = []
                    try:
                        async for chunk in stream_ollama(
                            seg_prompt, model=model, num_ctx=8192, num_predict=8192
                        ):
                            seg_tokens.append(chunk)
                    except Exception as e:
                        logger.error(f"分段 {seg_idx+1}/{len(segments)} 生成失败: {e}")
                        continue

                    seg_text = "".join(seg_tokens)
                    seg_text = re.sub(r'<think>.*?</think>', '', seg_text, flags=re.DOTALL).strip()
                    if seg_text:
                        all_parts.append(seg_text)

                raw_text = "\n\n".join(all_parts)

                # 去除开头可能重复的标题
                core_title = re.sub(
                    r'^[一二三四五六七八九十\d\.（()）)、\s]+', '', title
                ).strip()
                if core_title and raw_text.startswith(core_title):
                    raw_text = raw_text[len(core_title):].lstrip('\n')

                return {
                    "markdown": raw_text,
                    "sources": source_files,
                    "status": "ok" if raw_text.strip() else "skipped",
                }

    elif exemplar_content:
        prompt = DUAL_TRACK_PROMPT.format(
            title=title, project_facts=context,
            exemplar_content=exemplar_content,
            project_name=project_name or "未知项目",
        )
    else:
        prompt = PARAGRAPH_PROMPT.format(
            title=title, context=context,
            project_name=project_name or "未知项目",
        )

    # ── 后处理注入 ──
    if image_hint:
        prompt += image_hint
    if place_name_hint:
        prompt += place_name_hint
    if custom_persona:
        prompt = (
            f"【专属角色注入】\n{custom_persona}\n\n==========\n\n"
            + prompt
        )
    prompt += "\n\n/no_think"

    ctx_size = 16384

    # ── 调用 LLM 并收集全部 token ──
    full_tokens: list[str] = []
    try:
        async for chunk in stream_ollama(
            prompt, model=model, num_ctx=ctx_size
        ):
            full_tokens.append(chunk)
    except Exception as e:
        logger.error(f"LLM 生成失败: {title[:30]} | {e}")
        return {
            "markdown": "",
            "sources": source_files,
            "status": "error",
            "error": str(e),
        }

    raw_text = "".join(full_tokens)

    # ── 清理 think 标签残留 ──
    raw_text = re.sub(
        r'<think>.*?</think>', '', raw_text, flags=re.DOTALL
    ).strip()

    # ── 去除开头可能重复的标题 ──
    core_title = re.sub(
        r'^[一二三四五六七八九十\d\.（()）)、\s]+', '', title
    ).strip()
    if core_title and raw_text.startswith(core_title):
        raw_text = raw_text[len(core_title):].lstrip('\n')

    return {
        "markdown": raw_text,
        "sources": source_files,
        "status": "ok" if raw_text.strip() else "skipped",
    }


async def do_precompute_v2(project_id: str, mode: str):
    """
    全量预计算入口：遍历章节，逐个调用 LLM 生成并缓存结果。
    WHY: 在 Celery Worker 中通过 asyncio.run() 调用。
         每完成一个章节立即持久化到磁盘，支持断点续传。
    """
    import asyncio

    if mode not in VALID_MODES:
        logger.error(f"无效模式: {mode}")
        return

    r = get_redis()
    run_key = f"precompute:running:{project_id}:{mode}"
    if r:
        r.setex(run_key, 7200, "1")
        r.delete(f"precompute:queued:{project_id}:{mode}")

    try:
        from core.project_access import _read_projects

        # ── 读取章节列表 ──
        if mode == "generate":
            # generate 模式使用模板大纲（template），不依赖范文
            template_path = (
                Path(settings.DATA_DIR)
                / "templates"
                / f"{project_id}.json"
            )
            if not template_path.exists():
                logger.warning(
                    f"项目 {project_id} 无模板，跳过 generate 预计算"
                )
                return
            tpl = json.loads(template_path.read_text(encoding="utf-8"))
            sections = tpl.get("sections", [])
            exemplar_id = project_id  # 仍可选性使用范文做 dual-track
        else:
            # replace/clone 模式使用范文（exemplar）
            exemplar_path = EXEMPLARS_DIR / f"{project_id}.json"
            if not exemplar_path.exists():
                logger.warning(
                    f"项目 {project_id} 无范文，跳过 {mode} 预计算"
                )
                return
            exemplar = json.loads(
                exemplar_path.read_text(encoding="utf-8")
            )
            sections = exemplar.get("sections", [])
            exemplar_id = project_id

        if not sections:
            logger.warning(f"项目 {project_id} 章节为空")
            return

        # ── 读取项目名称 ──
        project_name = project_id
        for p in _read_projects():
            if p.get("id") == project_id:
                project_name = p.get("name", project_id)
                break

        # ── 准备缓存目录 ──
        cache_dir = _get_cache_dir(project_id, mode)
        cache_dir.mkdir(parents=True, exist_ok=True)

        model = "qwen3.6:35b-q4"
        total = len(sections)
        prior_context = ""

        for i, section in enumerate(sections):
            sid = section.get("id", f"idx-{i}")
            title = section.get("title", "")

            # ── 断点续传：已缓存则跳过 ──
            cache_file = cache_dir / f"{sid}.json"
            if cache_file.exists():
                # 读取已缓存的 markdown 作为后续章节的前文参考
                try:
                    cached = json.loads(
                        cache_file.read_text(encoding="utf-8")
                    )
                    if cached.get("markdown"):
                        prior_context = cached["markdown"]
                except Exception:
                    pass
                continue

            # ── 更新 Redis 进度 ──
            if r:
                r.setex(
                    f"precompute:current_section:{project_id}:{mode}",
                    3600, title
                )
                # WHY: 随着预计算任务持续运行（可能长达数小时），延长运行状态 key 的 TTL 防止其过期导致前端显示“待触发”
                r.setex(run_key, 7200, "1")

            logger.info(
                f"⏳ Precompute [{mode}] {project_id} - "
                f"Section {i+1}/{total}: {title[:30]}..."
            )

            # ── 调用生成 ──
            # WHY: replace/clone 模式的 sections 就来自范文本身，
            #      直接传入 section.content 作为范文底稿，
            #      避免 _match_exemplar_section 的模糊匹配失败。
            _exemplar_override = (
                section.get("content", "")
                if mode in ("replace", "clone") else ""
            )

            # WHY: replace/clone 模式下，范文无正文的章节必须保持为空，严禁降级为自由生成。
            if mode in ("replace", "clone") and not _exemplar_override.strip():
                cache_data = {
                    "section_id": sid, "section_index": i, "title": title,
                    "mode": mode, "markdown": "", "sources": [],
                    "status": "skipped", "timestamp": time.time(),
                }
                cache_file.write_text(
                    json.dumps(cache_data, ensure_ascii=False, indent=2),
                    encoding="utf-8",
                )
                logger.info(f"⏭️ [{mode}] 空章节跳过: {title[:30]}")
                continue

            result = await _generate_single_section(
                title=title,
                mode=mode,
                project_id=project_id,
                project_name=project_name,
                model=model,
                exemplar_id=exemplar_id if mode != "generate" else "",
                section_index=i,
                section_level=section.get("level", 1),
                prior_context=prior_context[-2000:],
                exemplar_content_override=_exemplar_override,
            )

            # ── 持久化 ──
            cache_data = {
                "section_id": sid,
                "section_index": i,
                "title": title,
                "mode": mode,
                "markdown": result.get("markdown", ""),
                "sources": result.get("sources", []),
                "status": result.get("status", "error"),
                "error": result.get("error"),
                "timestamp": time.time(),
            }
            cache_file.write_text(
                json.dumps(cache_data, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

            # 更新前文参考
            if result.get("markdown"):
                prior_context = result["markdown"]

            logger.info(
                f"{'✅' if result['status'] == 'ok' else '⏭️'} "
                f"[{mode}] {title[:30]} | "
                f"{len(result.get('markdown', ''))} chars | "
                f"({i+1}/{total})"
            )

            # ── 低优先级延迟，让前端请求优先获得 GPU ──
            await asyncio.sleep(_INTER_SECTION_DELAY)

        logger.info(
            f"🎉 项目 {project_id} [{mode}] 全量预计算完成"
        )

    except Exception as e:
        logger.error(f"预计算异常: {e}", exc_info=True)
        raise
    finally:
        if r:
            r.delete(run_key)
            r.delete(f"precompute:task_id:{project_id}:{mode}")
            r.delete(
                f"precompute:current_section:{project_id}:{mode}"
            )
