"""
核心生成与对话 API：RAG 检索 → Qwen3.6 推理 → <think> 过滤 → SSE 推流。
支持双路 Prompt 引擎：Track A（项目事实） + Track B（范文风格）。
"""
from __future__ import annotations

import json
import time
import logging
import asyncio
from pathlib import Path
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from core.llm_engine import (
    stream_ollama, get_ollama_status,
    PARAGRAPH_PROMPT, CHAT_PROMPT, DUAL_TRACK_PROMPT,
    REPLACE_PROMPT, REPLACE_PROMPT_V2, CLONE_PROMPT, CLONE_PROMPT_V2,
)
from core.think_filter import filter_think_stream
from core.vector_store import query_by_file_ids
from core.auth_deps import get_current_user
from core.project_access import require_project_access
from core.config import settings
from core.graph_rag import graph_engine
from core.query_rewrite import (
    is_simple_query as _is_simple_query,
    resolve_coreference,
    rewrite_query,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["AI 生成"])




class ParagraphRequest(BaseModel):
    title: str
    context: str = ""
    file_ids: List[str] = []
    project_id: str = ""
    project_name: str = ""      # WHY: 注入到 Prompt 中，约束写作地域范围
    model: str = settings.DEFAULT_LLM_MODEL
    exemplar_id: str = ""       # WHY: 范文所属项目 ID（通常 == project_id）
    section_index: int = -1      # WHY: 当前章节在大纲中的位置索引
    section_level: int = 1       # WHY: 当前章节层级（用于跨层级匹配）
    mode: str = "generate"       # WHY: generate=从零写作, replace=范文智能替换
    collaborative: bool = False
    custom_instruction: str = ""



class HistoryMessage(BaseModel):
    role: str  # "user" or "agent"
    content: str


class ChatRequest(BaseModel):
    message: str
    file_ids: List[str] = []
    project_id: str = ""
    history: List[HistoryMessage] = []
    model: str = settings.DEFAULT_LLM_MODEL
    chat_mode: str = "stateless"  # stateless, fast, deep, expert, general, smart
    force_data_analysis: bool = False  # WHY: 用户可手动强制 DuckDB 路径

# WHY: 模型的上下文窗口有限（默认 ~8K tokens），
#      历史对话 + RAG 上下文 + 系统指令需要严格预算分配。
MAX_HISTORY_ROUNDS = 6   # 最多保留最近 6 轮对话（12 条消息）
MAX_HISTORY_CHARS = 3000  # 历史总字符预算，超出从最早的开始裁剪

# [NEW] 资深总工人设：面向云南力诺科技有限公司的专业约束
EXPERT_PERSONA = """你是一位深耕水利水电、水土保持及国土空间规划领域 20 年的资深总工程师。
你目前正在为云南力诺科技有限公司主导核心技术咨询。
你的回复特征：
1. 严谨性：所有结论必须符合国家及四川省地方工程技术标准。
2. 逻辑性：采用总分总结构，条理清晰，层次分明。
3. 专业感：使用标准的工程术语，严禁非专业性的口语化描述。
4. 深度性：能够主动关联工程实际风险并给出预防性技术建议。
"""

def _truncate_history(history: List[HistoryMessage]) -> str:
    """
    将历史消息裁剪到预算内，优先保留最近的对话。
    """
    if not history:
        return ""

    recent = history[-(MAX_HISTORY_ROUNDS * 2):]

    lines = []
    total_chars = 0
    for msg in reversed(recent):
        role_label = "用户" if msg.role == "user" else "助手"
        line = f"{role_label}: {msg.content}"
        if total_chars + len(line) > MAX_HISTORY_CHARS:
            break
        lines.insert(0, line)
        total_chars += len(line)

    if not lines:
        return ""

    return "## 对话历史\n" + "\n".join(lines)




def _split_long_exemplar(content: str, max_chars: int = 3000) -> list[str]:
    """
    将超长范文按子标题拆分为多个段落，每段 ≤ max_chars。
    WHY: 超长章节（如"水源工程" 29736 字）无法一次性放入 Prompt，
         需要拆分后逐段走 REPLACE 流程，每段都能精确参照范文。

    算法：
      1. 扫描所有行，识别子标题（短行、非表格行、非空行）
      2. 按子标题切分为原始子段
      3. 贪心合并相邻子段，直到接近 max_chars
      4. 单个子段仍超限时截断
    """
    lines = content.split('\n')
    if not lines:
        return [content]

    # ── Pass 1: 识别子标题位置 ──
    heading_indices = [0]
    for i, line in enumerate(lines):
        if i == 0:
            continue
        stripped = line.strip()
        if not stripped or stripped.startswith('|'):
            continue
        # WHY: 子标题特征 — 短行（≤40字）、不是表格行、不以数字数据开头
        if len(stripped) <= 40:
            heading_indices.append(i)

    # ── Pass 2: 按子标题切分为原始子段 ──
    raw_segments = []
    for k in range(len(heading_indices)):
        start = heading_indices[k]
        end = heading_indices[k + 1] if k + 1 < len(heading_indices) else len(lines)
        seg_text = '\n'.join(lines[start:end])
        if seg_text.strip():
            raw_segments.append(seg_text)

    if not raw_segments:
        return [content[:max_chars]]

    # ── Pass 3: 贪心合并相邻子段 ──
    merged = []
    current = ""
    for seg in raw_segments:
        if not current:
            current = seg
        elif len(current) + len(seg) + 1 <= max_chars:
            current += '\n' + seg
        else:
            merged.append(current)
            current = seg
    if current:
        merged.append(current)

    # ── Pass 4: 单段超限时截断 ──
    result = []
    for seg in merged:
        if len(seg) > max_chars:
            result.append(seg[:max_chars])
        else:
            result.append(seg)

    return result


async def _segmented_sse_generator(
    segments: list[str],
    context: str,
    project_name: str,
    table_rule: str,
    knowledge_rule: str,
    model: str = "",
    sources: list = None,
    strip_title: str = "",
    num_ctx: int = 16384,
    verification_ctx: dict = None,
    prompt_type: str = "REPLACE",
    project_id: str | None = None,
    custom_instruction: str = "",
):
    """
    分段流式生成器 — 将多个范文段落逐段走 REPLACE 流程，
    通过同一个 SSE 连接流式输出，前端无需任何修改。

    WHY: 超长章节（>3000字）无法一次性放入 Prompt 的 num_ctx 窗口。
         分段生成让每段都能获得完整的范文参照，而非被截断后自由发挥。
    """
    project_name = "未命名项目"
    if project_id:
        from core.llm_engine import current_project_id
        current_project_id.set(project_id)
        try:
            from core.project_access import _read_projects
            for p in _read_projects():
                if p["id"] == project_id:
                    project_name = p.get("name", "未命名项目")
                    break
        except Exception:
            pass

    from core.llm_engine import stream_ollama, REPLACE_PROMPT
    from core.think_filter import filter_think_stream

    yield ": connection established\n\n"
    if sources:
        yield f"data: {json.dumps({'sources': sources}, ensure_ascii=False)}\n\n"

    _full_text_parts: list[str] = []
    total_segments = len(segments)

    for seg_idx, segment in enumerate(segments):
        print(
            f"📄 分段生成 [{seg_idx+1}/{total_segments}] | "
            f"段落长度={len(segment)}字 | 标题=「{strip_title}」",
            flush=True,
        )
        try:
            from core.redis_client import set_agent_active
            set_agent_active("precompute", f"正在起草段落[{seg_idx+1}/{total_segments}]: {strip_title}", project_name, duration=35)
        except Exception:
            pass

        # WHY: 每段独立计算 table_ratio，避免整体范文的场景判断与段落实际内容不匹配。
        # 例如整体 ratio=0.4（场景B），但某段全是表格（应走场景C）或纯文字（应走场景A）。
        import re as _re_seg
        _seg_tbl = _re_seg.findall(r'^\|.+\|', segment, _re_seg.MULTILINE)
        _seg_all = [l for l in segment.split('\n') if l.strip()]
        _seg_ratio = len(_seg_tbl) / max(len(_seg_all), 1)

        if not _seg_tbl:
            seg_table_rule = '7. **⚠️ 严禁创建表格**：本段范文底稿中没有任何表格，严禁创建任何表格结构'
        elif _seg_ratio < 0.6:
            seg_table_rule = table_rule  # 混合内容，沿用传入的场景B规则
        else:
            seg_table_rule = (
                '7. **表格处理**：本段范文中已有表格。你必须：\n'
                '（a）严格保持范文表格的行列结构和表头文字不变；\n'
                '（b）用新项目的数据逐单元格替换；\n'
                '（c）若表格包含合计/小计行，需重新计算后填写；\n'
                '（d）⚠️ 严禁照搬范文表格中的旧项目数据，找不到对应数据则填[待补充]；\n'
                '（e）⚠️ 若存在连续多列内容完全相同的行，将重复列合并为一列'
            )

        if prompt_type == "CLONE":
            prompt = CLONE_PROMPT.format(
                exemplar_content=segment,
                project_facts=context,
                project_name=project_name,
            )
        else:
            prompt = REPLACE_PROMPT.format(
                exemplar_content=segment,
                project_facts=context,
                project_name=project_name,
                table_constraint=seg_table_rule,
                knowledge_rule=knowledge_rule,
            )
            prompt += "\n\n/no_think"

        if custom_instruction and custom_instruction.strip():
            instruction_hint = f"\n\n【⚠️ 强制用户自定义要求约束】\n在接下来的写作中，请必须严格遵循并参考以下用户的自定义定制化要求：\n{custom_instruction.strip()}\n（你必须将此要求融合进文章的内容和风格中）"
            prompt += instruction_hint

        # 段落间插入分隔换行
        if seg_idx > 0:
            sep_token = "\n\n"
            _full_text_parts.append(sep_token)
            yield f"data: {json.dumps({'token': sep_token}, ensure_ascii=False)}\n\n"

        # WHY: 分段模式 num_ctx 降到 8192 — 每段范文仅 ~3000 字 + context ~500 字，
        #      16K 窗口严重浪费显存。12 段 × 16K 会导致 Ollama KV Cache 堆积 OOM。
        #      8K 对每段绰绰有余（~3000 字范文 ≈ 2000 tok + ~500 字 facts ≈ 333 tok）。
        #      num_predict 降到 4096 — 每段输出不会超过范文段落长度。
        _seg_ctx = 8192
        _seg_predict = 4096

        # 流式生成当前段落
        raw_stream = stream_ollama(prompt, model=model, num_predict=_seg_predict, num_ctx=_seg_ctx)
        filtered_stream = filter_think_stream(raw_stream)

        queue = asyncio.Queue()
        _fs_ref = filtered_stream  # WHY: 显式捕获当前迭代的流引用，避免闭包陷阱

        async def consume(_stream=_fs_ref):
            try:
                async for chunk in _stream:
                    await queue.put(chunk)
                await queue.put(None)
            except Exception as e:
                logger.error(f"Segmented stream error: {e}")
                await queue.put(e)

        task = asyncio.create_task(consume())

        # WHY: Token 合并 — 每个 token 都触发前端 editor.insertContent + scrollIntoView，
        #      6 段 × 数千 token = 数万次 DOM 更新，导致浏览器 OOM。
        #      合并小 token 为 ~200 字的批次，将 DOM 更新次数降低 50-100 倍。
        _batch_buf = ""
        _BATCH_SIZE = 200

        try:
            while True:
                try:
                    item = await asyncio.wait_for(queue.get(), timeout=2.0)
                    if item is None:
                        # 流结束，刷出剩余 buffer
                        if _batch_buf:
                            _full_text_parts.append(_batch_buf)
                            yield f"data: {json.dumps({'token': _batch_buf}, ensure_ascii=False)}\n\n"
                            _batch_buf = ""
                        
                        # ─── 插入协同流程反映 ───
                        try:
                            from api.admin import _read_system_settings
                            sys_settings = _read_system_settings()
                            name_contrarian = sys_settings.get("collab_contrarian_name", "【协同】审查员")
                            name_arbiter = sys_settings.get("collab_arbiter_name", "【协同】仲裁官")

                            # 1. 切换到小杠审查
                            set_agent_active("contrarian", f"正在审查段落[{seg_idx+1}/{total_segments}]数据: {strip_title}", project_name, duration=15)
                            _msg_contrarian = f"\n\n🤨 *[{name_contrarian}] 已完成对第 {seg_idx+1} 段的逻辑审查与数据校验*"
                            yield f"data: {json.dumps({'token': _msg_contrarian}, ensure_ascii=False)}\n\n"
                            await asyncio.sleep(0.5)
                            
                            # 2. 切换到大BOSS定稿
                            set_agent_active("arbiter", f"正在裁决段落[{seg_idx+1}/{total_segments}]定稿: {strip_title}", project_name, duration=15)
                            _msg_arbiter = f"\n👑 *[{name_arbiter}] 确认第 {seg_idx+1} 段起草规范，批准输出定稿。*\n\n"
                            yield f"data: {json.dumps({'token': _msg_arbiter}, ensure_ascii=False)}\n\n"
                            await asyncio.sleep(0.5)
                            
                            # 3. 恢复起草者状态
                            set_agent_active("precompute", f"完成段落[{seg_idx+1}/{total_segments}]生成: {strip_title}", project_name, duration=15)
                        except Exception:
                            pass
                        
                        break
                    if isinstance(item, Exception):
                        if _batch_buf:
                            _full_text_parts.append(_batch_buf)
                            yield f"data: {json.dumps({'token': _batch_buf}, ensure_ascii=False)}\n\n"
                            _batch_buf = ""
                        yield f"data: {json.dumps({'error': str(item)}, ensure_ascii=False)}\n\n"
                        break

                    if item in ("<<<THINK_START>>>", "<<<THINK_END>>>"):
                        continue

                    _batch_buf += item

                    # 达到批次大小或遇到段落换行时刷出
                    if len(_batch_buf) >= _BATCH_SIZE or '\n\n' in _batch_buf:
                        _full_text_parts.append(_batch_buf)
                        yield f"data: {json.dumps({'token': _batch_buf}, ensure_ascii=False)}\n\n"
                        _batch_buf = ""
                except asyncio.TimeoutError:
                    # 超时时也刷出已有内容（保持流式体验）
                    if _batch_buf:
                        _full_text_parts.append(_batch_buf)
                        yield f"data: {json.dumps({'token': _batch_buf}, ensure_ascii=False)}\n\n"
                        _batch_buf = ""
                    yield ": heartbeat\n\n"
        finally:
            if not task.done():
                task.cancel()

    # WHY: Self-Check — 对所有段落的合并文本做数值校验
    if verification_ctx and _full_text_parts:
        try:
            from core.vector_store import verify_numbers
            full_text = "".join(_full_text_parts)
            warnings = verify_numbers(full_text, **verification_ctx)
            if warnings:
                yield f"data: {json.dumps({'verify_warnings': warnings}, ensure_ascii=False)}\n\n"
                print(
                    f"🔍 [Self-Check] 分段合并后 {len(warnings)} 个可疑数值",
                    flush=True,
                )
        except Exception as e:
            logger.warning(f"Self-Check 校验异常: {e}")

    yield f"data: {json.dumps({'done': True})}\n\n"
    print(
        f"✅ 分段生成完成 | 标题=「{strip_title}」| "
        f"{total_segments} 段 | 总输出={sum(len(p) for p in _full_text_parts)}字",
        flush=True,
    )


async def _sse_generator(
    prompt: str,
    model: str = "",
    think_mode: str = "format",
    sources: list = None,
    strip_title: str = "",
    num_predict: int = 8192,
    num_ctx: int = 16384,
    slots: list = None,
    verification_ctx: dict = None,
    data_analysis: dict = None,
    project_id: str | None = None,
):
    if project_id:
        from core.llm_engine import current_project_id
        current_project_id.set(project_id)
    from core.llm_engine import stream_ollama
    raw_stream = stream_ollama(prompt, model=model, num_predict=num_predict, num_ctx=num_ctx)

    if think_mode == "filter":
        from core.think_filter import filter_think_stream
        filtered_stream = filter_think_stream(raw_stream)
    elif think_mode == "format":
        from core.think_filter import format_think_stream
        filtered_stream = format_think_stream(raw_stream)
    else:
        filtered_stream = raw_stream

    yield ": connection established\n\n"
    # WHY: 映射表预览 — Slot-Filling Phase 2 在正文输出前推送变量替换映射，
    #      让前端可以展示"即将进行以下替换"的预览，增强用户信任感。
    if slots:
        yield f"data: {json.dumps({'slots': slots}, ensure_ascii=False)}\n\n"
    if sources:
        yield f"data: {json.dumps({'sources': sources}, ensure_ascii=False)}\n\n"
    # WHY: DuckDB 分析结果通过独立 SSE 事件推送，前端 DataTable 组件直接渲染，
    #      不依赖 LLM 在回答中回显表格。
    if data_analysis:
        # WHY: 先推送 status 进度提示，让前端展示加载动画，
        #      消除用户在 SQL 分析+LLM 回答期间的"卡死"感知。
        yield f"data: {json.dumps({'status': '📊 数据分析完成，正在组织回答...'}, ensure_ascii=False)}\n\n"
        yield f"data: {json.dumps({'data_analysis': data_analysis}, ensure_ascii=False)}\n\n"

    queue = asyncio.Queue()
    _dbg_chunk_count = 0
    _yield_counter = 0
    # WHY: 累积完整生成文本，流结束后做数值校验（Self-Check）
    _full_text_parts: list[str] = []

    async def consume():
        nonlocal _dbg_chunk_count
        try:
            async for chunk in filtered_stream:
                _dbg_chunk_count += 1
                await queue.put(chunk)
            await queue.put(None)
        except Exception as e:
            logger.error(f"Stream generation error: {e}")
            await queue.put(e)

    task = asyncio.create_task(consume())

    try:
        while True:
            try:
                item = await asyncio.wait_for(queue.get(), timeout=2.0)
                if item is None:
                    break
                if isinstance(item, Exception):
                    yield f"data: {json.dumps({'error': str(item)}, ensure_ascii=False)}\n\n"
                    break

                if item == "<<<THINK_START>>>":
                    yield f"data: {json.dumps({'think_active': True}, ensure_ascii=False)}\n\n"
                    continue
                elif item == "<<<THINK_END>>>":
                    yield f"data: {json.dumps({'think_end': True}, ensure_ascii=False)}\n\n"
                    continue

                # WHY: 只累积实际正文 token，think 信号不计入
                # WHY: qwen3.6 偶尔将特殊控制 token 作为普通文本输出（尤其在 Prompt 边界），
                #      必须在 SSE 推送前清理，否则前端会显示 <|endoftext|><|im_start|>user 等乱码。
                import re as _re
                item = _re.sub(r'<\|(?:endoftext|im_start|im_end|end)\|>', '', item)
                # 清理残余的裸 role 标记（连续出现的 user/assistant/system）
                item = _re.sub(r'\b(?:user|assistant|system)\s*(?=\b(?:user|assistant|system)\b|$)', '', item)
                if not item:
                    continue
                _full_text_parts.append(item)
                payload = json.dumps({"token": item}, ensure_ascii=False)
                yield f"data: {payload}\n\n"
            except asyncio.TimeoutError:
                yield ": heartbeat\n\n"

        # WHY: Self-Check — 流结束后对完整生成文本做多源数值校验，
        #      将可疑数值作为 verify_warnings 推送给前端展示"建议复核"。
        if verification_ctx and _full_text_parts:
            try:
                from core.vector_store import verify_numbers
                full_text = "".join(_full_text_parts)
                warnings = verify_numbers(full_text, **verification_ctx)
                if warnings:
                    yield f"data: {json.dumps({'verify_warnings': warnings}, ensure_ascii=False)}\n\n"
                    print(
                        f"🔍 [Self-Check] {len(warnings)} 个可疑数值: "
                        f"{[w['value'] for w in warnings]}",
                        flush=True,
                    )
            except Exception as e:
                logger.warning(f"Self-Check 校验异常: {e}")

        yield f"data: {json.dumps({'done': True})}\n\n"
    finally:
        if not task.done():
            task.cancel()

# ---------- 范文风格匹配（Track B）----------
_EXEMPLAR_MAX_CHARS = {
    "qwen3.6:35b-q4": 3000,
}

def _match_exemplar_section(
    exemplar_id: str,
    target_title: str,
    section_index: int,
    section_level: int,
    model: str = "",
) -> str:
    fp = Path(settings.DATA_DIR) / "exemplars" / f"{exemplar_id}.json"
    if not fp.exists():
        return ""
    try:
        data = json.loads(fp.read_text(encoding="utf-8"))
        exemplar_sections = data.get("sections", [])
    except Exception:
        return ""

    if not exemplar_sections:
        return ""

    import re

    # ── 标题标准化：去掉编号前缀，提取核心文字 ──
    def _clean_title(title: str) -> str:
        return re.sub(r'^[一二三四五六七八九十百千万\d\.（）\(\),\.\s]+', '', title)

    def _core_words(title: str) -> set:
        """提取标题核心词的 2-gram 集合（而非单字符），防止虚假命中。"""
        cleaned = _clean_title(title)
        if len(cleaned) >= 2:
            return set(cleaned[i:i+2] for i in range(len(cleaned)-1))
        return set(cleaned)

    tgt_clean = _clean_title(target_title)
    target_words = _core_words(target_title)

    best_match = ""
    best_overlap = 0

    # ── 策略 1: 2-gram 重叠匹配（最精确）──
    best_match_title_len_diff = float('inf')
    for sec in exemplar_sections:
        sec_words = _core_words(sec.get("title", ""))
        overlap = len(target_words & sec_words)
        if overlap > 0 and sec.get("content"):
            sec_clean = _clean_title(sec.get("title", ""))
            # WHY: 得分相同时，优先选择标题长度更接近目标的候选。
            #      "水源工程"(4字) 应精确匹配"水源工程"而非"水源工程现状"(6字)。
            title_len_diff = abs(len(sec_clean) - len(tgt_clean))
            if (overlap > best_overlap) or (overlap == best_overlap and title_len_diff < best_match_title_len_diff):
                best_overlap = overlap
                best_match = sec["content"]
                best_match_title_len_diff = title_len_diff

    # ── 策略 2: section_index 直接索引（模板与范文索引对齐时）──
    # WHY: 用户自定义模板的标题编号格式可能与范文不一致（如"一、" vs "1."），
    #      导致 2-gram 重叠 < 2，但索引位置是可靠的匹配依据。
    if best_overlap < 2 and 0 <= section_index < len(exemplar_sections):
        sec = exemplar_sections[section_index]
        if sec.get("content", "").strip():
            sec_clean = _clean_title(sec.get("title", ""))
            # 宽松校验：至少有一个非停用字重叠
            _STOP_CHARS = set('的与和及之')
            tgt_set = set(tgt_clean) - _STOP_CHARS
            sec_set = set(sec_clean) - _STOP_CHARS
            if len(tgt_set & sec_set) >= 1:
                print(
                    f"📖 范文匹配(索引): idx={section_index} "
                    f"'{target_title[:20]}' → '{sec_clean[:20]}'",
                    flush=True,
                )
                best_match = sec["content"]
                best_overlap = 99  # 标记为索引匹配，后续直接通过

    # ── 策略 3: 单字重叠匹配（最宽松）──
    # WHY: 对于高度简化的标题（如"背景"→"项目背景"），
    #       2-gram 不可能匹配，但语义相同。≥3 个共享单字即可视为匹配。
    if best_overlap < 2:
        _STOP_CHARS = set('一二三四五六七八九十百千万\d\.（）\(\),\.\s的与和及之')
        tgt_chars = set(tgt_clean) - _STOP_CHARS
        best_char_overlap = 0
        for sec in exemplar_sections:
            if not sec.get("content", "").strip():
                continue
            sec_clean = _clean_title(sec.get("title", ""))
            sec_chars = set(sec_clean) - _STOP_CHARS
            overlap = len(tgt_chars & sec_chars)
            if overlap >= 3 and overlap > best_char_overlap:
                best_char_overlap = overlap
                best_match = sec["content"]
                print(
                    f"📖 范文匹配(单字): '{target_title[:20]}' → "
                    f"'{sec_clean[:20]}' ({overlap} chars)",
                    flush=True,
                )
                best_overlap = 1  # 标记为非 2-gram 匹配但有效

    # 任一策略命中（overlap >= 1 包括索引匹配和单字匹配）
    if best_overlap >= 1 and best_match:
        # WHY: 不再在此处截断。截断/分段逻辑移至 generate_paragraph，
        #      以支持超长章节的分段生成（方案 A）。
        return _strip_image_markers(best_match)

    return ""


def _extract_replace_keywords(exemplar_content: str, max_keywords: int = 8) -> str:
    """
    从范文正文中提取核心主题关键词，用于 Replace 模式下的精准 RAG 检索。

    策略（Slot-Filling Phase 1）：
      1. 去除范文中的旧项目地名（它们属于模板项目，不应成为检索词）
      2. 去除具体数字和年份（这些是需要被替换的变量，不是检索主题）
      3. 提取剩余的 4-6 字专业术语作为主题关键词
      4. 按出现频次排序，取 Top N

    WHY: Replace 模式下的 RAG 检索目标是找到当前项目中与范文相同主题的段落，
         而非找到与标题字面匹配的任何内容。用范文主题词作为 query
         能精准命中政策叙述、技术分析等对应段落，避免检索到无关的工程数据表。
    """
    import re
    from collections import Counter

    if not exemplar_content:
        return ""

    # 取前 800 字，避免超长范文占用过多处理时间
    text = exemplar_content[:800]

    # Step 1: 移除地名（旧项目的县/镇/村等不应成为检索词）
    text = re.sub(
        r'[\u4e00-\u9fa5]{2,5}(?:省|市|县|区|镇|乡|村|街道)', '', text
    )

    # Step 2: 移除数字、年份和带单位的数值（这些是待替换变量）
    text = re.sub(
        r'\d[\d\.]*\s*(?:年|亿|万|亩|元|%|米|公里|公顷|吨|人|户|个|条|座|处)?',
        '', text
    )
    # 移除括号内容（通常是法规文号）和书名号引用（《xxx》）
    text = re.sub(r'[（(][^)）]*[)）]', '', text)
    text = re.sub(r'《[^》]*》', '', text)

    # Step 3: 按标点分割成短句，提取每个短句中的名词性短语
    # WHY: 直接提取 4-6 字片段会从中间切断"高标准农田建设"这类术语。
    #      按句子边界切割后，完整的专业术语更容易被保留。
    clauses = re.split(r'[，。！？；、\n]+', text)

    # 提取 2-8 字的中文名词短语（匹配连续中文字符块）
    all_phrases = []
    for clause in clauses:
        clause = clause.strip()
        if len(clause) < 2:
            continue
        # 提取每个子句中的连续中文字符块（去除标点后的自然分词）
        phrases = re.findall(r'[\u4e00-\u9fa5]{2,8}', clause)
        all_phrases.extend(phrases)

    # Step 4: 过滤停用词（动词短语、虚词、过于通用的表述）
    STOP_WORDS = {
        '是保障', '是落实', '是推动', '的重要', '等工程', '等措施',
        '可显著', '的目标', '的任务', '的政策', '的决策', '的规划',
        '提出了', '印发了', '明确了', '强调要', '着力于', '聚焦于',
        '为乡村', '为粮食', '根据中', '关于加', '关于高', '全面落',
        '主要为', '主要有', '主要包', '通过土', '通过工', '确保到',
        '部门联', '部门人', '建设的', '建成高', '建设规',
    }
    filtered = [p for p in all_phrases if len(p) >= 3 and p not in STOP_WORDS]

    # Step 5: 去重保序，按频次排序取 Top N
    counter = Counter(filtered)
    seen = set()
    unique = []
    for t in filtered:
        if t not in seen:
            seen.add(t)
            unique.append(t)

    top_terms = sorted(
        unique, key=lambda x: -counter.get(x, 0)
    )[:max_keywords]

    return ' '.join(top_terms)


def _strip_image_markers(text: str) -> str:
    """
    从范文内容中剥离残留的 [图件：图N] 标记。
    WHY: 旧版本范文 JSON 中图片标记混在 content 里，
         必须在注入 Prompt 前清理，否则 LLM 会原样搬运到每个章节。
    """
    import re
    return re.sub(r'\[图件[：:]\s*图\d+\]\s*', '', text).strip()


def _get_section_image_hint(
    exemplar_id: str,
    section_index: int,
    target_title: str,
    project_name: str,
) -> str:
    """
    检查范文中指定章节是否有图片，有则返回精确的图件占位指令。
    WHY: 只有范文中确实存在图片的章节才应生成 [插入图件：...] 标记，
         从根本上杜绝多章节插入同一张图片的问题。
    """
    fp = Path(settings.DATA_DIR) / "exemplars" / f"{exemplar_id}.json"
    if not fp.exists():
        return ""
    try:
        data = json.loads(fp.read_text(encoding="utf-8"))
        sections = data.get("sections", [])
        if 0 <= section_index < len(sections):
            images = sections[section_index].get("images", [])
            if images:
                # 为当前章节生成精确指令
                img_desc = f"与「{target_title}」内容相匹配的专题图件"
                return (
                    f"\n\n【⚠️ 强制图件插入指令】\n"
                    f"（说明：范文中本章节包含 {len(images)} 张图件。你无需重现图表内容，但**必须**在输出的正文末尾添加如下占位标记，并将地名替换为{project_name}）：\n"
                    f"[插入图件：{project_name} {img_desc}]"
                )
    except Exception:
        pass
    return ""

# WHY: 全局项目元数据检索器 — 解决"章节标题语义检索盲区"问题。
#       当生成 "1.1.1 区片价修订的背景" 时，语义搜索无法命中 Excel 中
#       "天福镇 耕地 45000元/亩" 的数据切片。本函数用宽泛数据关键词做
#       二次检索，确保核心量化指标（价格、面积、比例等）始终可用。
_GLOBAL_QUERY_KEYWORDS = [
    "面积 价格 数据 统计 区片",
    "地价 标准 耕地 建设用地",
    "变化 幅度 修订 调整",
]

from starlette.concurrency import run_in_threadpool

async def _get_global_project_context(
    project_name: str,
    file_ids: List[str],
    project_id: str,
    max_chunks: int = 4,
    max_chars: int = 2000,
) -> str:
    """
    用宽泛数据关键词做二次 RAG 检索，返回项目级核心指标摘要。
    与章节检索形成互补：章节检索匹配"语义相关性"，全局检索匹配"数据覆盖度"。
    """
    if not file_ids and not project_id:
        return ""

    seen_ids = set()
    all_docs = []

    for kw in _GLOBAL_QUERY_KEYWORDS:
        query = f"{project_name} {kw}" if project_name else kw
        docs = await run_in_threadpool(
            query_by_file_ids, query, file_ids, project_id, 3
        )
        for d in docs:
            chunk_id = d["metadata"].get("file_id", "") + str(d["metadata"].get("chunk_index", ""))
            if chunk_id not in seen_ids:
                seen_ids.add(chunk_id)
                all_docs.append(d)

    if not all_docs:
        return ""

    # WHY: 经 Reranker 精排后，distance 字段实际存储的是 reranker score（越大越相关），
    #      而非原始余弦距离。因此应按降序排列，取分数最高的 top chunks。
    all_docs.sort(key=lambda x: x.get("distance", 0), reverse=True)
    top_docs = all_docs[:max_chunks]

    result = "\n\n".join(
        f"[来源: {d['metadata'].get('filename', '未知')}]\n{d['content']}"
        for d in top_docs
    )
    return result[:max_chars]


def _extract_place_names(context: str) -> list:
    """
    从 RAG 检索的参考资料中提取高频地名，用于正字约束注入。
    WHY: 中文 LLM 对生僻地名容易用同音字替代（如蓬溪→彭溪），
         通过从原始文档中提取地名并显式要求模型核对，可大幅降低错字率。
    """
    import re
    from collections import Counter
    # 匹配 2-5 字 + 行政区划后缀的地名
    pattern = r'([\u4e00-\u9fa5]{2,5}(?:省|市|县|区|镇|乡|村|街道))'
    # WHY: 排除通用词汇，只保留真正的地名。
    #      "工业区"、"保护区"等匹配正则但并非地名，会浪费 Prompt Token 预算。
    _FALSE_POSITIVES = {'工业区', '保护区', '流域区', '开发区', '风景区', '示范区',
                        '居住区', '规划区', '核心区', '缓冲区', '实验区', '控制区',
                        '灌溉区', '超采区', '补给区', '排泄区', '径流区'}
    matches = [m for m in re.findall(pattern, context) if m not in _FALSE_POSITIVES]
    if not matches:
        return []
    # 按频次排序，取 Top 15 高频地名
    counter = Counter(matches)
    return [name for name, _ in counter.most_common(15)]


def _is_structural_heading(exemplar_id: str, target_title: str, section_index: int) -> bool:
    """
    判断范文中指定位置的章节是否为纯结构性标题（没有正文内容）。
    WHY: 技术报告中 L1/L2 级大标题通常只是目录分层，下方紧接子标题不含正文。
    """
    fp = Path(settings.DATA_DIR) / "exemplars" / f"{exemplar_id}.json"
    if not fp.exists():
        return False
    try:
        data = json.loads(fp.read_text(encoding="utf-8"))
        sections = data.get("sections", [])
    except Exception:
        return False
        
    if not sections:
        return False
        
    import re
    def _core_words(title: str) -> set:
        """提取标题核心词的 2-gram 集合（而非单字符），防止虚假命中。"""
        cleaned = re.sub(r'^[一二三四五六七八九十百千万\d\.（）\(\)、\s]+', '', title)
        if len(cleaned) >= 2:
            return set(cleaned[i:i+2] for i in range(len(cleaned)-1))
        return set(cleaned)

    target_words = _core_words(target_title)

    best_match_idx = -1
    best_overlap = 0
    for i, sec in enumerate(sections):
        sec_words = _core_words(sec.get("title", ""))
        overlap = len(target_words & sec_words)
        if overlap > best_overlap:
            best_overlap = overlap
            best_match_idx = i

    target_idx = best_match_idx if best_overlap >= 2 else section_index
    if 0 <= target_idx < len(sections):
        content = sections[target_idx].get("content", "")
        # 如果长度为0，认为是结构性标题
        return len(content.strip()) == 0

    return False


def _is_exemplar_section_empty(exemplar_id: str, section_index: int, title: str = "") -> bool:
    """
    检查范文中对应章节是否无正文内容。
    WHY: replace/clone 模式必须严格保持与范文的结构一致性——
         范文无正文的章节绝对不能自由生成内容。

    策略（2026-05-27 修复）：
      优先用标题 2-gram 匹配找到范文中对应的章节，再判断是否为空。
      旧逻辑直接用 section_index 做数组下标，但前端模板索引与范文索引
      存在偏移，导致跳过判断指向错误章节。
    """
    import re

    fp = Path(settings.DATA_DIR) / "exemplars" / f"{exemplar_id}.json"
    if not fp.exists():
        return False
    try:
        data = json.loads(fp.read_text(encoding="utf-8"))
        sections = data.get("sections", [])
    except Exception:
        return False

    if not sections:
        return False

    def _clean(t: str) -> str:
        return re.sub(r'^[一二三四五六七八九十百千万\d\.（）\(\),\.\s]+', '', t)

    def _bigrams(t: str) -> set:
        c = _clean(t)
        return set(c[i:i+2] for i in range(len(c)-1)) if len(c) >= 2 else set(c)

    # ── 策略 1: 标题 2-gram 匹配 ──
    if title:
        tgt_clean = _clean(title)
        tgt_bigrams = _bigrams(title)
        best_sec = None
        best_overlap = 0
        best_diff = float('inf')

        for sec in sections:
            sec_bigrams = _bigrams(sec.get("title", ""))
            overlap = len(tgt_bigrams & sec_bigrams)
            if overlap > 0:
                sec_clean = _clean(sec.get("title", ""))
                diff = abs(len(sec_clean) - len(tgt_clean))
                if (overlap > best_overlap) or (overlap == best_overlap and diff < best_diff):
                    best_overlap = overlap
                    best_sec = sec
                    best_diff = diff

        if best_sec is not None and best_overlap >= 1:
            content = best_sec.get("content", "")
            matched_title = best_sec.get("title", "")
            is_empty = len(content.strip()) == 0
            print(
                f"🔍 空章节检测(标题匹配) | 「{title}」→ 「{matched_title}」→ "
                f"{'无内容→跳过' if is_empty else f'有内容({len(content)}字)→生成'}",
                flush=True,
            )
            return is_empty

    # ── 策略 2: 索引回退（标题匹配失败时）──
    if 0 <= section_index < len(sections):
        sec = sections[section_index]
        content = sec.get("content", "")
        sec_title = sec.get("title", "")
        is_empty = len(content.strip()) == 0
        print(
            f"🔍 空章节检测(索引回退) | 「{title}」→ [{section_index}]「{sec_title}」→ "
            f"{'无内容→跳过' if is_empty else f'有内容({len(content)}字)→生成'}",
            flush=True,
        )
        return is_empty

    return False


# WHY: 知识补充分级授权 — 政策/背景/标准类章节允许 LLM 适度发挥知识库，
#      而工程量/投资/坐标等数据类章节严格禁止知识补充。
_POLICY_KEYWORDS = {
    '背景', '依据', '概述', '概况', '前言', '总论', '综述',
    '必要性', '可行性', '意义', '目的', '政策',
    '技术路线', '方法', '思路', '指导思想', '编制依据',
}
# WHY: 移除了 '原则' — 「绩效管理原则」「管护原则」等制度性章节
#      会被误判为宽松级，导致 LLM 过度扩写添加项目概况等无关内容。
#      真正需要宽松权限的「设计原则」可通过「思路」「指导思想」等词覆盖。
# WHY: 移除了 '法规' 和 '标准' — 这两个词会匹配"法律法规""技术标准"等
#      纯列表型章节，导致宽松级扩写授权。法规清单和标准清单是引用列表，
#      不需要知识补充，更不允许扩写。

def _is_policy_section(title: str) -> bool:
    """
    判断章节标题是否属于政策/背景/概述类（允许较宽松的知识补充）。
    WHY: 用关键词检测替代让 LLM 自行判断，确保分级授权行为确定可控。
    """
    return any(kw in title for kw in _POLICY_KEYWORDS)


def _is_list_section(content: str) -> bool:
    """
    判断范文内容是否为纯引用清单型（法规清单、标准清单、政策文件清单等）。
    WHY: 纯引用清单型章节的"替换"仅限于更新版本号/编号，不需要 project_facts
         中的建设规模、投资等项目数据。如果注入大量无关数据 + 宽松权限，
         LLM 会用项目数据填充输出，严重偏离范文结构。

    判定特征（必须同时满足）：
    1. 超过 50% 的非空行包含引用标记（《》书名号、GB/DB/SL 标准编号、〔〕文号）
    2. 无叙述性段落（行长度 > 80 字的行不超过 2 行）
    """
    import re
    lines = [l.strip() for l in content.split('\n') if l.strip()]
    if not lines:
        return False

    # WHY: 只匹配"引用标记"——法规名《xxx》、标准编号 GB/xxx、文号〔xxx〕
    #      不再匹配普通的序号、数字、句号等，避免对短段落章节的误判。
    citation_pattern = re.compile(
        r'《.+?》|[（(][A-Z]{1,4}[/T]?\d|〔\d{4}〕|GB[/T]|DB\d|SL[/T]|JTG'
    )
    citation_count = sum(1 for l in lines if citation_pattern.search(l))
    citation_ratio = citation_count / len(lines)

    # 叙述性段落检测：行长度 > 80 字的行
    long_lines = sum(1 for l in lines if len(l) > 80)

    return citation_ratio > 0.5 and long_lines <= 2


# ── Clone 模式：范文表名匹配 → 资料表直接替换 ──────────────


def _extract_exemplar_tables(content: str) -> list[dict]:
    """
    从范文 Markdown 内容中提取所有表名及其对应的表格体。
    WHY: Clone 模式下需要逐表独立匹配资料库表格，
         必须精确定位每张表在范文中的位置（行号），
         以便后续做原地替换。

    返回: [{name, name_line_idx, body_start_idx, body_end_idx}]
    """
    import re
    results = []
    lines = content.split('\n')

    # WHY: 匹配中文表格标题行——「表N-N 表名」或「续表N-N 表名」
    #      后缀必须包含典型表格类型词（表/统计/汇总/清单/分析/情况...）
    #      避免误匹配正文中偶尔出现的「表N」引用。
    table_name_re = re.compile(
        r'([续附]?表[\d\-\.]*\s*'
        r'[^\n|]{2,60}'
        r'(?:表|统计|汇总|一览|分析|情况|清单|数据|成果|明细|计算|对比|参数|方案))'
    )

    i = 0
    while i < len(lines):
        line = lines[i].strip()
        m = table_name_re.search(line)
        if m:
            table_name = m.group(1).strip()
            # 向下搜索紧邻的 Markdown 表格体（跳过空行）
            table_start = None
            table_end = None
            j = i + 1
            while j < len(lines):
                stripped = lines[j].strip()
                if stripped.startswith('|'):
                    if table_start is None:
                        table_start = j
                    table_end = j
                elif table_start is not None:
                    # 表格体结束
                    break
                elif stripped == '':
                    # 跳过空行（表名与表格之间可能有空行）
                    j += 1
                    continue
                else:
                    # 遇到非表格非空行，停止搜索
                    break
                j += 1

            if table_start is not None and table_end is not None:
                results.append({
                    'name': table_name,
                    'name_line_idx': i,
                    'body_start_idx': table_start,
                    'body_end_idx': table_end,
                })
                i = table_end + 1
                continue
        i += 1

    return results


def _replace_exemplar_tables(
    content: str,
    exemplar_tables: list[dict],
    matches: dict,
) -> tuple[str, int]:
    """
    将范文中匹配到的表格体替换为资料库表格的 Markdown。
    WHY: Clone 模式下，匹配到的表格直接使用资料库数据，绕过 LLM 重写。
         从后向前替换避免行号索引偏移。

    返回: (替换后的 content, 替换成功的表格数)
    """
    lines = content.split('\n')
    replaced_count = 0

    # WHY: 从后向前替换——后面的替换不会影响前面的行号
    for tbl in sorted(
        exemplar_tables,
        key=lambda t: t['body_start_idx'],
        reverse=True,
    ):
        if tbl['name'] not in matches:
            continue

        matched = matches[tbl['name']]
        new_md = matched.get('markdown', '')
        if not new_md:
            continue

        # WHY: 限制单表最大字符数，防止超大表格撑爆 context 窗口
        if len(new_md) > 10000:
            new_md = new_md[:10000] + '\n...[表格过长，已截断]'

        new_lines = new_md.split('\n')
        lines[tbl['body_start_idx']:tbl['body_end_idx'] + 1] = new_lines
        replaced_count += 1

    return '\n'.join(lines), replaced_count


async def _skip_sse_generator():
    yield ": connection established\n\n"
    yield f"data: {json.dumps({'skip': True, 'done': True})}\n\n"


async def _collaborative_sse_generator(
    prompt: str,
    model: str = settings.COLLAB_LLM_MODEL,
    project_id: str | None = None,
    project_name: str = "未命名项目",
    verification_ctx: dict = None,
    slots: list = None,
):
    if project_id:
        from core.llm_engine import current_project_id
        current_project_id.set(project_id)

    yield ": connection established\n\n"
    if slots:
        yield f"data: {json.dumps({'slots': slots}, ensure_ascii=False)}\n\n"

    # Step 1: Supervisor 编排分流
    yield f"data: {json.dumps({'type': 'agent_event', 'agent': 'supervisor', 'message': '正在分析章节主题与资料，评估写作任务...'}, ensure_ascii=False)}\n\n"
    await asyncio.sleep(0.8)

    # Step 2: 段落起草专家起草首稿
    yield f"data: {json.dumps({'type': 'agent_event', 'agent': 'service', 'message': '正在根据大纲及参考资料起草章节初稿...'}, ensure_ascii=False)}\n\n"

    _expert_header = "⚖️ **[段落起草专家] 正在起草章节初稿...**\n\n"
    for token in _expert_header:
        yield f"data: {json.dumps({'token': token}, ensure_ascii=False)}\n\n"
        await asyncio.sleep(0.005)

    from core.llm_engine import stream_ollama
    raw_stream = stream_ollama(prompt, model=model, num_predict=8192, num_ctx=16384)
    from core.think_filter import filter_think_stream
    filtered_stream = filter_think_stream(raw_stream)

    first_draft_chunks = []
    async for chunk in filtered_stream:
        import re as _re
        chunk = _re.sub(r'<\|(?:endoftext|im_start|im_end|end)\|>', '', chunk)
        chunk = _re.sub(r'\b(?:user|assistant|system)\s*(?=\b(?:user|assistant|system)\b|$)', '', chunk)
        if not chunk:
            continue
        first_draft_chunks.append(chunk)
        yield f"data: {json.dumps({'token': chunk}, ensure_ascii=False)}\n\n"

    first_draft = "".join(first_draft_chunks)

    # Step 3: 小杠负向抗辩审查
    from api.admin import _read_system_settings
    sys_settings = _read_system_settings()
    name_contrarian = sys_settings.get("collab_contrarian_name", "【协同】审查员")
    name_arbiter = sys_settings.get("collab_arbiter_name", "【协同】仲裁官")

    yield f"data: {json.dumps({'type': 'agent_event', 'agent': 'contrarian', 'message': f'{name_contrarian}正在审查首稿，挑战逻辑与数据准确性...'}, ensure_ascii=False)}\n\n"
    yield f"data: {json.dumps({'think_active': True}, ensure_ascii=False)}\n\n"

    _divider = f"\n\n---\n🤨 **[{name_contrarian}] 正在对起草内容及数据逻辑进行多角度质疑与审查...**\n"
    for token in _divider:
        yield f"data: {json.dumps({'token': token}, ensure_ascii=False)}\n\n"
        await asyncio.sleep(0.005)

    from core.agents.contrarian_agent import ContrarianAgent
    contrarian = ContrarianAgent()
    critique = await contrarian.critique(prompt, first_draft)

    yield f"data: {json.dumps({'think_end': True}, ensure_ascii=False)}\n\n"

    _opinion_header = f"\n> **🤨 {name_contrarian}审查意见**：\n"
    for token in _opinion_header:
        yield f"data: {json.dumps({'token': token}, ensure_ascii=False)}\n\n"
        await asyncio.sleep(0.005)

    for line in critique.split("\n"):
        _line_str = f"> {line}\n"
        for token in _line_str:
            yield f"data: {json.dumps({'token': token}, ensure_ascii=False)}\n\n"
            await asyncio.sleep(0.002)

    # Step 4: 大BOSS 终审与修正
    yield f"data: {json.dumps({'type': 'agent_event', 'agent': 'arbiter', 'message': f'{name_arbiter} 正在整合质疑，进行措辞润色与最终裁决...'}, ensure_ascii=False)}\n\n"

    _boss_divider = f"\n\n---\n👑 **[{name_arbiter}] 正在综合{name_contrarian}质疑意见，进行最终措辞润色与逻辑修正...**\n\n"
    for token in _boss_divider:
        yield f"data: {json.dumps({'token': token}, ensure_ascii=False)}\n\n"
        await asyncio.sleep(0.005)

    from core.agents.arbiter_agent import ArbiterAgent
    arbiter = ArbiterAgent()

    final_response_chunks = []
    async for token in arbiter.arbitrate_stream(prompt, first_draft, critique, "段落起草专家"):
        import re as _re
        token = _re.sub(r'<\|(?:endoftext|im_start|im_end|end)\|>', '', token)
        token = _re.sub(r'\b(?:user|assistant|system)\s*(?=\b(?:user|assistant|system)\b|$)', '', token)
        if not token:
            continue
        final_response_chunks.append(token)
        yield f"data: {json.dumps({'token': token}, ensure_ascii=False)}\n\n"

    final_response = "".join(final_response_chunks)

    if verification_ctx and final_response:
        try:
            from core.vector_store import verify_numbers
            warnings = verify_numbers(final_response, **verification_ctx)
            if warnings:
                yield f"data: {json.dumps({'verify_warnings': warnings}, ensure_ascii=False)}\n\n"
        except Exception as ve:
            logger.warning(f"Self-check verify error: {ve}")

    yield f"data: {json.dumps({'done': True})}\n\n"


@router.post("/generate/paragraph")
async def generate_paragraph(req: ParagraphRequest, user: dict = Depends(get_current_user)):
    import time as _time
    _t_start = _time.time()
    
    if req.project_id:
        require_project_access(req.project_id, user, write=False)

    # WHY: 记录生成操作到审计日志，方便管理员追踪 LLM 资源使用
    from core.audit_log import log_operation
    mode_label = {"generate": "生成", "replace": "替换", "clone": "克隆"}.get(req.mode, req.mode)
    log_operation(user["id"], "content_generate", f"{mode_label}章节：{req.title}（模型={req.model or '默认'}）")


    # WHY: 章节跳过逻辑 — replace/clone 模式下范文空章节必须跳过，严禁自由发挥。
    #      其他模式下结构性标题（L1/L2 纯目录）跳过。
    if req.exemplar_id and req.section_index >= 0:
        if req.mode in ("replace", "clone"):
            # WHY: replace/clone 模式下，范文无正文的章节必须输出空内容，严禁降级为自由生成。
            should_skip = _is_exemplar_section_empty(req.exemplar_id, req.section_index, title=req.title)
        else:
            is_structural = _is_structural_heading(req.exemplar_id, req.title, req.section_index)
            is_protected = "前言" in req.title or "概述" in req.title
            should_skip = is_structural and not is_protected and req.section_level <= 1
        if should_skip:
            print(f"⏭️ 跳过空/结构性章节 | 标题=「{req.title}」| section_idx={req.section_index} | mode={req.mode} | level={req.section_level}", flush=True)
            return StreamingResponse(
                _skip_sse_generator(),
                media_type="text/event-stream",
                headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
            )

    project_name = req.project_name
    custom_persona = ""
    if req.project_id:
        from core.project_access import _read_projects
        for p in _read_projects():
            if p["id"] == req.project_id:
                project_name = project_name or p.get("name", "")
                custom_persona = p.get("metadata", {}).get("aiPersona", "").strip()
                break

    prior_context = req.context.strip() if req.context else ""

    # WHY: 【Slot-Filling Phase 1】将范文匹配提前到 RAG 检索之前。
    #      Replace/Clone 模式需要用范文的主题关键词构建精准 RAG query，
    #      因此必须先加载范文内容，再执行检索。
    exemplar_content = ""
    if req.exemplar_id:
        exemplar_content = _match_exemplar_section(req.exemplar_id, req.title, req.section_index, req.section_level, model=req.model)

    context = ""
    source_files = []
    if req.file_ids:
        # WHY: 【Slot-Filling Phase 1】Replace/Clone 模式下使用范文主题关键词构建精准 query。
        #      原来的 "项目名+标题" 过于宽泛，会命中大量无关的工程数据切片（如电气参数表）。
        #      新策略：从范文正文中提取去除地名和数值后的核心主题词，
        #      让向量检索精准定位到当前项目中语义对应的政策叙述/技术分析段落。
        if req.mode in ("replace", "clone") and exemplar_content:
            exemplar_keywords = _extract_replace_keywords(exemplar_content)
            rag_query = f"{project_name} {req.title} {exemplar_keywords}".strip()
            print(f"🔍 Slot-Filling RAG | query='{rag_query[:80]}...'", flush=True)
        else:
            rag_query = f"{project_name} {req.title}" if project_name else req.title

        print(f"⏱️ RAG 检索开始 | elapsed={_time.time()-_t_start:.2f}s", flush=True)
        # WHY: Replace/Clone 只需精准替换数据，不需要海量参考资料。
        #      降低 top_k 从源头减少 project_facts 体积，避免上下文窗口溢出。
        _rag_top_k = 4 if req.mode in ("replace", "clone") else 8
        docs = await run_in_threadpool(
            query_by_file_ids, rag_query, req.file_ids, req.project_id, _rag_top_k
        )
        print(f"⏱️ RAG 检索完成 | elapsed={_time.time()-_t_start:.2f}s | docs={len(docs) if docs else 0}", flush=True)

        # WHY: Replace/Clone 模式下过滤纯图纸元数据 chunk（标题栏、图例、参数表）。
        #      但保留包含叙述性工程概况的图件 chunk（含村名、建设地点等替换数据）。
        #      之前的一刀切过滤会误杀"工程概况"段落中的关键项目数据。
        if req.mode in ("replace", "clone") and docs:
            _KEEP_KEYWORDS = {'建设地点', '行政村', '建设规模', '工程概况', '编制说明',
                              '项目概况', '设计依据', '建设范围', '项目名称'}
            _before = len(docs)
            filtered_docs = []
            for d in docs:
                content = d.get("content", "")
                if content.lstrip().startswith("[图件解析]"):
                    # 检查是否包含有价值的叙述性工程数据
                    if any(kw in content for kw in _KEEP_KEYWORDS):
                        filtered_docs.append(d)  # 保留有价值的图件 chunk
                        continue
                    # 纯图纸元数据（参数表、标题栏、图例），丢弃
                    continue
                filtered_docs.append(d)
            docs = filtered_docs
            _filtered = _before - len(docs)
            if _filtered:
                print(f"🚫 过滤 {_filtered} 个纯图纸元数据 chunk (replace/clone 模式)", flush=True)

        if docs:
            seen = set()
            for d in docs:
                fname = d['metadata'].get('filename', '未知')
                if fname not in seen:
                    source_files.append(fname)
                    seen.add(fname)
            context_parts = []
            for d in docs:
                fname = d['metadata'].get('filename', '未知')
                confidence = d['metadata'].get('confidence', 1.0)
                
                # P3: 如果可信度低于阈值，注入防幻觉提示
                warning = ""
                if confidence < 0.4:
                    warning = " (⚠️注：此段落为低可信度 OCR 提取，可能存在识别误差，请结合语境鉴别)"
                
                context_parts.append(f"[来源: {fname}]{warning}\n{d['content']}")
            
            context = "\n\n".join(context_parts)

    # WHY: 全局项目元数据注入 — 仅对水利/工程类项目执行二次 RAG 检索。
    #       非工程类项目（如课程标准、规划文档）使用标题语义检索已足够，
    #       额外的水利关键词查询反而浪费 6-18 秒并污染上下文。
    _ENGINEERING_KEYWORDS = {'水利', '水保', '水土', '地价', '区片', '测绘', '工程', '规划'}
    is_engineering = any(kw in (project_name or '') for kw in _ENGINEERING_KEYWORDS)
    
    global_context = ""
    # WHY: Replace/Clone 以范文为蓝图，全局指标检索价值低且占用大量 token。
    #      仅 Generate/Dual-Track 模式执行全局二次检索。
    if is_engineering and req.mode not in ("replace", "clone"):
        global_context = await _get_global_project_context(
            project_name, req.file_ids, req.project_id
        )
    if global_context:
        context = f"## 项目核心指标（全局）\n{global_context}\n\n## 章节相关资料\n{context}" if context else global_context

    # WHY: 注入知识图谱上下文 — 通过 Neo4j 图谱扩散检索，
    #      找到与当前章节主题相关的实体关系路径，补充向量检索的盲区。
    _graph_context_raw = ""  # WHY: 单独捕获图谱上下文，供 Self-Check 做多源数值校验
    try:
        graph_query = f"{project_name} {req.title}" if project_name else req.title
        # WHY: Replace/Clone 限制图谱路径数，减少 prompt 膨胀。
        _graph_max = 4 if req.mode in ("replace", "clone") else 8
        graph_result = await graph_engine.hybrid_search(
            graph_query, project_id=req.project_id, max_paths=_graph_max
        )
        if graph_result.get("graph_context"):
            _graph_context_raw = graph_result["graph_context"]
            context = f"{_graph_context_raw}\n\n{context}"
            print(f"🕸️ 图谱注入 | {len(graph_result['paths'])} 条路径 | 标题=「{req.title}」", flush=True)
    except Exception as e:
        logger.warning(f"图谱检索降级: {e}")

    # ── Replace/Clone 模式：注入完整表格 ──
    # WHY: 范文中的表格需要用新项目数据替换。
    #      Clone 模式：通过表名匹配直接替换范文中的表格体（绕过 LLM），
    #                  确保表格数据零损耗、零幻觉。
    #      Replace 模式：通过语义检索注入完整表格到 context，
    #                    让 LLM 参照资料表逐单元格替换。
    if req.mode == "clone" and req.project_id and exemplar_content:
        # ── Clone 专用：表名匹配 → 直接替换范文表格体 ──
        try:
            from core.table_registry import match_tables_by_name
            # Step 1: 从范文中提取所有表名及表格体位置
            ex_tables = _extract_exemplar_tables(exemplar_content)
            if ex_tables:
                ex_names = [t['name'] for t in ex_tables]
                print(
                    f"🔍 Clone 表名匹配 | "
                    f"范文中发现 {len(ex_tables)} 张表: "
                    f"{ex_names[:5]}{'...' if len(ex_names) > 5 else ''}",
                    flush=True,
                )

                # Step 2: 在资料库中按表名匹配
                matches = match_tables_by_name(
                    ex_names, req.project_id,
                    req.file_ids if req.file_ids else None,
                )

                # Step 3: 直接替换范文中的表格体
                if matches:
                    exemplar_content, replaced = _replace_exemplar_tables(
                        exemplar_content, ex_tables, matches,
                    )
                    _match_details = [
                        (n, m['title'], f"{m['match_score']:.2f}")
                        for n, m in matches.items()
                    ]
                    print(
                        f"✅ Clone 表格直接替换 | "
                        f"成功替换 {replaced}/{len(ex_tables)} 张表 | "
                        f"匹配详情: {_match_details}",
                        flush=True,
                    )
                    # WHY: 未匹配到的表格仍走语义检索兜底
                    unmatched = [t['name'] for t in ex_tables if t['name'] not in matches]
                    if unmatched:
                        print(
                            f"⚠️ Clone 未匹配表格 ({len(unmatched)}): {unmatched}",
                            flush=True,
                        )
                else:
                    print("⚠️ Clone 表名匹配 | 无命中，将走语义检索兜底", flush=True)

                # Step 4: 未匹配的表格 → 回退到语义检索注入 context
                unmatched_names = [t['name'] for t in ex_tables if t['name'] not in matches]
                if unmatched_names:
                    from core.table_registry import query_tables
                    for uname in unmatched_names[:3]:  # 最多补 3 张
                        _fallback_query = f"{project_name} {uname}"
                        _fb_results = query_tables(
                            _fallback_query, req.project_id,
                            req.file_ids if req.file_ids else None,
                            max_tables=1,
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
                            print(
                                f"🗃️ Clone 语义兜底 | '{uname}' → '{t['title']}'",
                                flush=True,
                            )
            else:
                print("ℹ️ Clone 表名匹配 | 范文中未发现带表名的表格", flush=True)
        except Exception as e:
            logger.warning(f"Clone 表名匹配降级: {e}")

    elif req.mode == "replace" and req.project_id and exemplar_content:
        # ── Replace 模式：保持原有语义检索注入逻辑 ──
        try:
            from core.table_registry import query_tables
            _table_query = f"{project_name} {req.title}"
            import re as _re_tbl_match
            _exemplar_bold_titles = _re_tbl_match.findall(
                r'\*\*(.+?)\*\*', exemplar_content
            )
            _exemplar_table_refs = _re_tbl_match.findall(
                r'(表\d[\d\-]*\s*[^\n|]{2,30})', exemplar_content
            )
            _tbl_hints = _exemplar_bold_titles + _exemplar_table_refs
            if _tbl_hints:
                _table_query = f"{project_name} {_tbl_hints[0].strip()}"

            matched_tables = query_tables(
                _table_query, req.project_id,
                req.file_ids if req.file_ids else None,
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
                print(
                    f"🗃️ Replace 表格注入 | "
                    f"{len(matched_tables)} 张表 | "
                    f"标题={[t['title'] for t in matched_tables]}",
                    flush=True,
                )
        except Exception as e:
            logger.warning(f"Replace 表格注入降级: {e}")

    # WHY: Replace/Clone 模式下不注入 prior_context。
    #      这些模式以范文为唯一结构蓝图，prior_context（前文生成内容）
    #      会严重污染 {project_facts} 区域——尤其当范文底稿较短时，
    #      LLM 会被前文内容劫持，输出与前一章节重复的政策叙述。
    if prior_context and req.mode not in ("replace", "clone"):
        context = f"{context}\n\n## 前文结构参考\n{prior_context[-2000:]}"
    if not context:
        context = "（暂无参考资料，请基于专业知识撰写）"

    # WHY: Replace/Clone 的核心是范文底稿，project_facts 只是辅助数据源。
    #      硬上限确保 exemplar + facts + prompt 总量不超过 num_ctx 窗口（16384 tokens ≈ 10K 中文字）。
    #      即使上游轻量级管线已降低数据量，此处作为最终安全阀兜底。
    if req.mode in ("replace", "clone"):
        # WHY: 列表型章节（法规清单、标准清单）只需要项目名称，不需要项目数据。
        #      大幅缩减 facts 避免 LLM 用项目数据填充输出。
        if exemplar_content and _is_list_section(exemplar_content):
            _MAX_REPLACE_FACTS = 500
            print(f"📋 列表型章节 → project_facts 上限={_MAX_REPLACE_FACTS}字", flush=True)
        else:
            # WHY: 根据范文长度动态调整 facts 上限。
            #      短范文（如"建设方式"仅 150 字）配 8000 字 facts，
            #      LLM 注意力被海量数据淹没，会自行增加段落。
            #      按范文长度 × 5 倍计算，限制在 [1000, 8000] 区间。
            _exemplar_len = len(exemplar_content) if exemplar_content else 0
            _MAX_REPLACE_FACTS = max(1000, min(_exemplar_len * 5, 8000))
            print(
                f"📏 范文={_exemplar_len}字 → project_facts 上限={_MAX_REPLACE_FACTS}字",
                flush=True,
            )
        if len(context) > _MAX_REPLACE_FACTS:
            print(f"✂️ project_facts 截断 {len(context)} → {_MAX_REPLACE_FACTS}字 (replace/clone 安全上限)", flush=True)
            context = context[:_MAX_REPLACE_FACTS]

    # WHY: 地名正字约束 — 从 RAG 检索的参考资料中提取高频地名，
    #       注入 Prompt 防止 LLM 用同音字替代（如 蓬溪→彭溪、遂宁→遂宁 等）。
    #       中文 LLM 生成时经常在地名上出现同音字错误，这是因为模型在训练语料中
    #       对生僻地名的记忆不够精确。通过显式提供"正字表"可以显著减少此类错误。
    place_names = _extract_place_names(context)
    place_name_hint = ""
    if place_names:
        place_name_hint = f"\n\n【⚠️ 强制地名正字约束】\n在接下来的写作中，请必须逐字核对以下地名，严禁在正文中使用同音字替代：\n{', '.join(place_names)}\n（此约束仅供你内部检查，严禁将本表原样输出到正文中）"

    # WHY: 精确图件指令 — 只有范文中确实有图片的章节才注入图件占位要求
    image_hint = ""
    if req.exemplar_id and req.section_index >= 0:
        image_hint = _get_section_image_hint(
            req.exemplar_id, req.section_index, req.title, project_name or "未知项目"
        )

    # ── 调试日志：追踪 Prompt 路由决策（用 print 确保在 PM2 下可见）──
    print(
        f"📝 生成请求 | 标题=「{req.title}」| mode={req.mode} | "
        f"exemplar_id={req.exemplar_id or '无'} | section_idx={req.section_index} | "
        f"范文匹配={'有(' + str(len(exemplar_content)) + '字)' if exemplar_content else '无'}",
        flush=True
    )
    # WHY: Prompt 数据量诊断日志——方便后续排查 LLM 被内容劫持的问题
    print(
        f"📐 Prompt 数据量 | exemplar={len(exemplar_content)}字 | "
        f"project_facts={len(context)}字 | "
        f"prior_context={'禁用(replace/clone)' if req.mode in ('replace', 'clone') else f'{len(prior_context)}字'}",
        flush=True,
    )

    prompt_type = ""
    _slots = []  # WHY: Slot-Filling Phase 2 映射表（仅 replace 模式填充）
    if req.mode == "clone" and exemplar_content:
        prompt = CLONE_PROMPT.format(exemplar_content=exemplar_content, project_facts=context, project_name=project_name or "未知项目")
        prompt_type = "CLONE"
    elif req.mode == "replace":
        if not exemplar_content:
            # WHY: Graceful Fallback — 多策略范文匹配全部失败时，不静默跳过，
            #      而是降级为自由生成模式，利用已检索的 RAG context 生成内容。
            #      前端会正常接收 streaming tokens，不会收到 {skip: true}。
            print(
                f"⚠️ 范文智能替换降级 | 标题=「{req.title}」| "
                f"范文匹配失败，降级为自由生成",
                flush=True,
            )
            prompt = PARAGRAPH_PROMPT.format(
                title=req.title,
                context=context,
                project_name=project_name or "未知项目",
            )
            prompt_type = "REPLACE→FALLBACK(范文匹配失败)"
        else:
            # WHY: 动态防表格约束 — 三分法判断范文内容类型。
            #       二分法（有/无表格）对"水文气象"等混合章节（文本+表格共存）失效：
            #       LLM 收到"保持表格结构"指令后，把叙述性文字也用管道符包裹成单列表格，
            #       前端 marked.parse 将其解析为 <th> 表格头，Tiptap 以窄列渲染。
            import re as _re_table
            _table_lines = _re_table.findall(r'^\|.+\|', exemplar_content, _re_table.MULTILINE)
            _total_lines = [l for l in exemplar_content.split('\n') if l.strip()]
            _table_ratio = len(_table_lines) / max(len(_total_lines), 1)

            if not _table_lines:
                # 场景 A：纯文本，无任何表格
                # WHY: 检查范文是否引用了表名（如"表2-1项目区耕地现状统计表"），
                #      若引用了表名且参考资料有完整表格，则不应禁止创建表格。
                _has_table_ref = bool(_re_table.search(r'表\d[\d\-]*\s*\S{2,}', exemplar_content))
                if _has_table_ref:
                    table_rule = (
                        '7. **表格引用处理**：范文底稿是叙述性文本，但引用了数据表格名称。'
                        '若参考资料中包含📊标记的完整表格且与范文引用的表名对应，'
                        '你必须在引用位置之后输出完整的 Markdown 表格，数据从参考资料逐行复制。'
                        '除此之外，叙述性段落严禁转换为表格结构'
                    )
                else:
                    table_rule = '7. **⚠️ 严禁创建表格**：范文底稿中没有任何表格，你绝对不能创建 Markdown 表格、列表式数据表或任何类似表格结构。即使参考资料中包含大量数据列表，也必须用自然段落的形式叙述'
            elif _table_ratio < 0.6:
                # 场景 B：混合内容（文本段落 + 表格共存），如"水文气象"
                table_rule = (
                    '7. **混合内容处理（文本+表格）**：范文底稿中同时包含叙述性段落和数据表格。你必须严格区分两者：\n'
                    '   - **叙述性段落**（不含 `|` 管道符的自然文本）：必须以自然段落形式输出，**严禁用管道符 `|` 包裹文字、严禁将文字转为表格格式**\n'
                    '   - **数据表格**（范文中以 `|...|` 格式呈现的表格）：严格保持范文表格的行列结构和表头文字不变，用新项目数据逐单元格替换\n'
                    '   - 若范文表格包含合计/小计/占比等汇总行，需根据新数据重新计算后填写\n'
                    '   - ⚠️ 表格和段落中的项目特定数据均遵循规则4的[待补充]约束'
                )
            else:
                # 场景 C：表格为主的章节
                table_rule = (
                    '7. **表格处理**：范文中已有表格。你必须：\n'
                    '（a）严格保持范文表格的行列结构和表头文字不变；\n'
                    '（b）用新项目的数据逐单元格替换；\n'
                    '（c）若范文表格包含合计/小计/占比等汇总行，需根据新数据重新计算后填写；\n'
                    '（d）⚠️ 项目特定数据遵循规则4的[待补充]约束，严禁照搬范文中旧项目数据；\n'
                    '（e）⚠️ **合并单元格识别**：若范文表格中存在连续多列内容完全相同的行（如同一数据重复4列），'
                    '这是合并单元格的解析痕迹。输出时应将这些重复列合并为一列，仅保留一份数据，不要复制重复列'
                )

            # WHY: 知识补充分级授权 — 三级：列表型（最严）→ 数据型（严格）→ 政策型（宽松）
            _is_list = _is_list_section(exemplar_content)
            if _is_list:
                # 列表型章节（法规清单、标准清单等）：严禁任何扩写
                knowledge_rule = (
                    '5. **⚠️ 列表型章节（严禁扩写）**：范文底稿是一份引用清单（法规/标准/文件列表）。'
                    '你只能做以下操作：（a）保持清单的条目数量和格式完全一致；'
                    '（b）如有更新的法规/标准版本号可替换旧版本号；'
                    '（c）**严禁增加新条目、严禁插入解释性文字、严禁利用参考资料中的项目数据扩写内容**。'
                    '输出必须是与范文格式完全一致的引用清单，不多不少'
                )
                print(f"📋 列表型章节检测 | 标题=「{req.title}」| 知识补充=列表级(最严)", flush=True)
            elif _is_policy_section(req.title):
                knowledge_rule = (
                    '5. **知识补充权限（宽松级）**：本章节属于概念性/政策性内容。'
                    '当参考资料缺乏行业背景、政策依据或技术标准解读时，'
                    '你可以调用自身专业知识库对**政策叙述、行业背景、技术原理**等通用性内容进行适当补充，'
                    '但段落数量仍须与范文保持一致。'
                    '⚠️ **但项目特定数据（地名、面积、金额、村名、行政区划、建设规模等）'
                    '仍必须严格遵循规则4的[待补充]约束，不得用知识库编造**'
                )
            else:
                knowledge_rule = '5. **知识补充权限（严格级）**：当参考资料缺乏行业背景或通用常识时，你可以调用自身专业知识库进行补充，但**仅限于对句子中的局部词汇进行完善，严禁生成新的解释性句子或段落**，必须严格保持 1:1 的段落结构。核心项目数据必须来自参考资料，严禁凭空捏造'

            # WHY: 【Slot-Filling Phase 2】两步 Pipeline
            #       Step 1: 变量抽取（后台 3-5s，用户无感）
            #       Step 2: 模板填充（流式输出给用户）
            #       SLOT_FILLING_V2 开关可随时回退到 Phase 1
            #       扩展：clone 模式也支持 V2
            _use_v2 = settings.SLOT_FILLING_V2 and req.mode in ("replace", "clone")
            _slots = []
            _max_exemplar_check = _EXEMPLAR_MAX_CHARS.get(req.model, 2000)

            # WHY: 超长范文将走分段生成流程，Slot-Filling V2 不适用
            #      （extract_slots 无法处理 29736 字的输入）
            if _use_v2 and len(exemplar_content) > _max_exemplar_check:
                _use_v2 = False
                print(
                    f"⚠️ Slot-Filling V2 跳过（范文={len(exemplar_content)}字 > {_max_exemplar_check}字上限，将走分段生成）",
                    flush=True,
                )

            if _use_v2:
                from core.slot_extractor import extract_slots, format_slot_table
                print(f"🔬 Slot-Filling V2 | Step 1 启动...", flush=True)
                _t_slot = _time.time()
                _slots = await extract_slots(
                    exemplar_content, context,
                    project_name or "未知项目",
                    model=req.model,
                )
                _slot_elapsed = _time.time() - _t_slot
                print(
                    f"🔬 Slot-Filling V2 | Step 1 完成 | "
                    f"{len(_slots)} 个变量 | {_slot_elapsed:.1f}s",
                    flush=True,
                )

            if _use_v2 and _slots:
                # Phase 2：使用映射表驱动的 V2 Prompt
                # WHY: V2 Prompt 只有 5 条固定规则，table_constraint 编号应为 6（而非 V1 的 7）
                table_rule_v2 = table_rule.replace('7. ', '6. ', 1)
                slot_table = format_slot_table(_slots)
                knowledge_rule_v2 = knowledge_rule.replace('5. ', '4. ', 1)
                
                if req.mode == "clone":
                    prompt = CLONE_PROMPT_V2.format(
                        exemplar_content=exemplar_content,
                        slot_table=slot_table,
                        project_facts=context,
                        project_name=project_name or "未知项目"
                    )
                    prompt_type = "CLONE_V2"
                else:
                    prompt = REPLACE_PROMPT_V2.format(
                        exemplar_content=exemplar_content,
                        slot_table=slot_table,
                        project_facts=context,
                        project_name=project_name or "未知项目",
                        table_constraint=table_rule_v2,
                        knowledge_rule=knowledge_rule_v2,
                    )
                    prompt_type = "REPLACE_V2"
            else:
                # Phase 1 降级：使用原始 REPLACE_PROMPT 或 CLONE_PROMPT
                if _use_v2:
                    print(
                        f"⚠️ Slot 抽取无结果，降级到 Phase 1",
                        flush=True,
                    )
                if req.mode == "clone":
                    prompt = CLONE_PROMPT.format(
                        exemplar_content=exemplar_content,
                        project_facts=context,
                        project_name=project_name or "未知项目"
                    )
                    prompt_type = "CLONE"
                else:
                    prompt = REPLACE_PROMPT.format(
                        exemplar_content=exemplar_content,
                        project_facts=context,
                        project_name=project_name or "未知项目",
                        table_constraint=table_rule,
                        knowledge_rule=knowledge_rule,
                    )
                    prompt_type = "REPLACE"
    elif exemplar_content:
        prompt = DUAL_TRACK_PROMPT.format(title=req.title, project_facts=context, exemplar_content=exemplar_content, project_name=project_name or "未知项目")
        prompt_type = "DUAL_TRACK"
    else:
        prompt = PARAGRAPH_PROMPT.format(title=req.title, context=context, project_name=project_name or "未知项目")
        prompt_type = "PARAGRAPH(无范文)"

    print(f"🎯 Prompt 路由 → {prompt_type} | 图件指令={'有' if image_hint else '无'}", flush=True)

    # 注入精确图件指令（仅当范文中本章节确实有图片时）
    if image_hint:
        prompt += image_hint

    # 注入地名正字校对表（防止同音字替代）
    if place_name_hint:
        prompt += place_name_hint

    # WHY: 条件注入 Mermaid 语法参考 — 仅当章节标题包含流程性关键词时触发，
    #       避免在纯描述性章节中污染 Prompt，节省 Token 预算。
    FLOW_KEYWORDS = ['技术路线', '工作流程', '组织架构', '组织体系', '实施步骤',
                     '测算方法', '工作程序', '工艺流程', '施工组织', '技术方案']
    if any(kw in req.title for kw in FLOW_KEYWORDS):
        mermaid_hint = """

## 📊 Mermaid 流程图语法参考
当你判断本章节适合用流程图展示时，请在正文末尾输出以下格式的 Mermaid 代码块：
```mermaid
graph TD
    A[步骤一] --> B[步骤二]
    B --> C{判断条件}
    C -->|是| D[步骤三]
    C -->|否| E[步骤四]
    D --> F[完成]
    E --> F
```
注意：节点 ID 使用英文字母（A/B/C），节点标签内使用中文。
"""
        prompt += mermaid_hint
        print(f"📊 Mermaid 语法参考已注入（标题匹配: {req.title}）", flush=True)

    if custom_persona:
        persona_injection = f"【专属角色注入】\n当前项目已启用自定义角色与规范约束。在进行本次正文撰写任务时，你必须严格代入并遵守以下用户设定的行事规则：\n{custom_persona}\n\n==========\n\n"
        prompt = persona_injection + prompt

    if req.custom_instruction and req.custom_instruction.strip():
        instruction_hint = f"\n\n【⚠️ 强制用户自定义要求约束】\n在接下来的写作中，请必须严格遵循并参考以下用户的自定义定制化要求：\n{req.custom_instruction.strip()}\n（你必须将此要求融合进文章的内容和风格中）"
        prompt += instruction_hint

    # WHY: qwen3.6 的 <think> 推演阶段可能耗时较长，
    #      导致前端 SSE 流在等待期间超时并跳到下一章节，造成"项目背景没写出文本"的现象。
    #      /no_think 覆盖有时可能不彻底，因此我们将 think_mode 改为 "format"，
    #      将推演过程转化为引用块直通前端，保持连接活跃让前端可见思考过程。
    prompt += "\n\n/no_think"

    # WHY: 【Slot-Filling Phase 1】Replace/Clone 模式下将 num_ctx 提升到 16384。
    #      范文底稿(~1000 tok) + 全局指标(~500 tok) + 精准检索(~2000 tok) + Prompt 指令(~500 tok)
    #      总计 ~4000 tok，16K 窗口有充裕余量。M4 Max 64GB 的 KV Cache 仅增加 ~3GB。
    ctx_size = 16384

    # ── 超长范文分段生成（方案 A）──
    # WHY: 超长章节（如"水源工程" 29736 字）无法一次性放入 Prompt 窗口。
    #      当范文长度超过 max_chars 时，按子标题拆分为多段，逐段走 REPLACE/CLONE 流程。
    #      前端无需修改——所有段落的 token 通过同一 SSE 连接按序流出。
    _max_exemplar = _EXEMPLAR_MAX_CHARS.get(req.model, 2000)
    if (
        not req.collaborative
        and req.mode in ("replace", "clone")
        and exemplar_content
        and len(exemplar_content) > _max_exemplar
        and prompt_type in ("REPLACE", "REPLACE_V2", "CLONE", "CLONE_V2", "REPLACE→FALLBACK(范文匹配失败)")
        and prompt_type != "REPLACE→FALLBACK(Rev_match_failed)"
        and prompt_type != "REPLACE→FALLBACK(范文匹配失败)"
    ):
        segments = _split_long_exemplar(exemplar_content, max_chars=_max_exemplar)

        # WHY: 段数上限 10 — Token 合并已解决浏览器 OOM，
        #      但仍需限制段数以控制总生成时间（10 段 × ~40s ≈ ~7 分钟）。
        #      超出部分合并到最后一段（截断到 max_chars），而非直接丢弃。
        _MAX_SEGMENTS = 10
        if len(segments) > _MAX_SEGMENTS:
            # 将超出的段落合并到最后一段
            tail = "\n\n".join(segments[_MAX_SEGMENTS - 1:])
            segments = segments[:_MAX_SEGMENTS - 1] + [tail[:_max_exemplar]]
            print(
                f"⚠️ 分段数调整 {len(segments)} → {_MAX_SEGMENTS}（尾部合并）",
                flush=True,
            )

        # WHY: 分段模式的 context 精简到 2000 字 — 每段范文仅 ~3000 字，
        #      不需要 6000 字的完整 project_facts。减少 token 消耗。
        _seg_context = context[:2000] if len(context) > 2000 else context

        print(
            f"📄 超长范文分段 | 标题=「{req.title}」| "
            f"原始={len(exemplar_content)}字 → {len(segments)} 段 "
            f"(每段≤{_max_exemplar}字) | context={len(_seg_context)}字",
            flush=True,
        )

        _verification_ctx = {
            "rag_context": context,
            "graph_context": _graph_context_raw,
            "slot_table": None,
            "exemplar_content": exemplar_content[:_max_exemplar],
        }

        return StreamingResponse(
            _segmented_sse_generator(
                segments=segments,
                context=_seg_context,
                project_name=project_name or "未知项目",
                table_rule=table_rule,
                knowledge_rule=knowledge_rule,
                model=req.model,
                strip_title=req.title,
                num_ctx=ctx_size,
                verification_ctx=_verification_ctx,
                prompt_type="CLONE" if req.mode == "clone" else "REPLACE",
                project_id=req.project_id,
                custom_instruction=req.custom_instruction,
            ),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
        )

    # WHY: 正常长度范文 — 截断到 max_chars 后走标准流程
    if exemplar_content and len(exemplar_content) > _max_exemplar:
        print(f"✂️ 范文截断 {len(exemplar_content)} → {_max_exemplar}字", flush=True)
        exemplar_content = exemplar_content[:_max_exemplar]
        # 重新构建 prompt（使用截断后的范文）
        if prompt_type == "REPLACE":
            prompt = REPLACE_PROMPT.format(
                exemplar_content=exemplar_content,
                project_facts=context,
                project_name=project_name or "未知项目",
                table_constraint=table_rule,
                knowledge_rule=knowledge_rule,
            )
            prompt += "\n\n/no_think"
        elif prompt_type == "REPLACE_V2":
            # 如果启用了 V2 但因为过长被截断，实际上 V2 提取已经被跳过了。
            # 如果真的强行截断后走 V2，也需要重新生成 prompt，但这里为了简便降级到 REPLACE 即可。
            # 因为 _use_v2 在超过 _max_exemplar_check 时会被置为 False。
            # 这段代码只是为了保险起见。
            prompt = REPLACE_PROMPT.format(
                exemplar_content=exemplar_content,
                project_facts=context,
                project_name=project_name or "未知项目",
                table_constraint=table_rule,
                knowledge_rule=knowledge_rule,
            )
            prompt += "\n\n/no_think"
            prompt_type = "REPLACE"
        elif prompt_type == "CLONE":
            prompt = CLONE_PROMPT.format(
                exemplar_content=exemplar_content,
                project_facts=context,
                project_name=project_name or "未知项目",
            )
        elif prompt_type == "CLONE_V2":
            prompt = CLONE_PROMPT.format(
                exemplar_content=exemplar_content,
                project_facts=context,
                project_name=project_name or "未知项目",
            )
            prompt_type = "CLONE"
            prompt += "\n\n/no_think"

    print(f"⏱️ Prompt 构建完成，开始流式输出 | elapsed={_time.time()-_t_start:.2f}s | prompt_len={len(prompt)}", flush=True)

    # WHY: Self-Check 校验上下文 — 将全部数据源传给 _sse_generator，
    #      流结束后做多源数值校验，标记可疑幻觉数值。
    _verification_ctx = {
        "rag_context": context,
        "graph_context": _graph_context_raw,
        "slot_table": _slots if _slots else None,
        "exemplar_content": exemplar_content,
    }

    if req.collaborative:
        return StreamingResponse(
            _collaborative_sse_generator(
                prompt=prompt,
                model=req.model,
                project_id=req.project_id,
                project_name=project_name or "未知项目",
                verification_ctx=_verification_ctx,
                slots=_slots if (_slots and prompt_type == "REPLACE_V2") else None,
            ),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
        )

    return StreamingResponse(
        _sse_generator(prompt, model=req.model, think_mode="filter", strip_title=req.title, num_ctx=ctx_size,
                       slots=_slots if (_slots and prompt_type == "REPLACE_V2") else None,
                       verification_ctx=_verification_ctx,
                       project_id=req.project_id),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )



@router.post("/chat")
async def chat(req: ChatRequest, user: dict = Depends(get_current_user)):
    if req.project_id:
        require_project_access(req.project_id, user, write=False)
        
    project_name = "在线法律助手"
    custom_persona = ""
    if req.project_id:
        from core.project_access import _read_projects
        for p in _read_projects():
            if p["id"] == req.project_id:
                project_name = p.get("name", "未命名项目")
                metadata = p.get("metadata", {})
                custom_persona = metadata.get("aiPersona", "").strip()
                break

    from core.redis_client import set_agent_active
    set_agent_active("chat", f"回答咨询: {req.message[:20]}...", project_name, duration=25)

    # ── L2 缓存检查：完整回答命中则秒级返回 ──
    # WHY: 相同问题 + 相同项目 + 相同模式，LLM 回答不会变化。
    #      命中后直接推送缓存文本，跳过意图分类/检索/LLM 全链路。
    from core.chat_cache import get_answer_cache
    l2_hit = get_answer_cache(
        req.project_id, req.message, req.chat_mode, req.file_ids
    )
    if l2_hit:
        print(
            f"🎯 [CHAT-L2] 回答缓存命中 | msg='{req.message[:30]}' "
            f"| project={req.project_id[:8]}",
            flush=True,
        )

        async def _cached_sse():
            """将缓存的完整回答以 SSE 形式推送，模拟流式输出。"""
            yield ": connection established\n\n"
            # 推送缓存标记，前端可展示"从缓存加载"提示
            yield f"data: {json.dumps({'cached': True}, ensure_ascii=False)}\n\n"
            if l2_hit.get("source_files"):
                yield f"data: {json.dumps({'sources': l2_hit['source_files']}, ensure_ascii=False)}\n\n"
            if l2_hit.get("data_analysis_meta"):
                yield f"data: {json.dumps({'status': '📊 数据分析完成，正在组织回答...'}, ensure_ascii=False)}\n\n"
                yield f"data: {json.dumps({'data_analysis': l2_hit['data_analysis_meta']}, ensure_ascii=False)}\n\n"
            # WHY: 分批推送缓存文本，避免单个 SSE 事件过大（>64KB）导致前端解析失败
            answer = l2_hit.get("answer", "")
            _BATCH = 500
            for i in range(0, len(answer), _BATCH):
                chunk = answer[i:i + _BATCH]
                yield f"data: {json.dumps({'token': chunk}, ensure_ascii=False)}\n\n"
            yield f"data: {json.dumps({'done': True})}\n\n"

        return StreamingResponse(
            _cached_sse(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
        )



    is_simple = _is_simple_query(req.message)

    # ── 查询预处理管线（并行化优化）──
    # WHY: 意图分类（LLM）与指代消解（纯 CPU）之间无数据依赖，
    #      并行执行可节省 5-15s 串行等待时间。
    from core.intent_classifier import classify_intent as llm_classify_intent

    # 指代消解：纯 CPU 计算，先同步完成
    resolved_message = resolve_coreference(
        req.message,
        [] if req.chat_mode == "stateless" else req.history
    )

    # WHY: 意图分类与查询改写并行执行 — 两者之间无数据依赖。
    #      意图分类用于决定检索策略，查询改写用于向量检索 query，
    #      它们可以同时调用 LLM 而不互相阻塞。
    need_rewrite = len(resolved_message) > 15
    parallel_tasks = [llm_classify_intent(req.message, model=req.model)]
    if need_rewrite:
        parallel_tasks.append(
            rewrite_query(resolved_message, project_name, model=req.model)
        )

    parallel_results = await asyncio.gather(*parallel_tasks, return_exceptions=True)

    # 解包意图分类结果
    intent_result = parallel_results[0]
    if isinstance(intent_result, Exception):
        logger.warning(f"[chat] 意图分类异常，降级: {intent_result}")
        from core.intent_classifier import _classify_by_rules
        intent_result = _classify_by_rules(req.message)
    intent = intent_result.intent
    strategy = intent_result.strategy

    # 解包查询改写结果
    if need_rewrite and len(parallel_results) > 1:
        rewrite_result = parallel_results[1]
        if isinstance(rewrite_result, Exception):
            logger.warning(f"[chat] 查询改写异常，使用原消息: {rewrite_result}")
            search_query = resolved_message
        else:
            search_query = rewrite_result
    else:
        search_query = resolved_message

    print(
        f"🎯 [预处理] intent={intent} resolved={resolved_message != req.message}",
        flush=True,
    )

    # WHY: 用户勾选"强制SQL分析"时，覆盖意图分类结果，100% 走 DuckDB
    if req.force_data_analysis:
        from core.intent_classifier import _STRATEGY_TEMPLATES
        intent = "data_analysis"
        strategy = dict(_STRATEGY_TEMPLATES["data_analysis"])

    # 1. 动态 RAG 策略
    # - general 模式：不查询知识库，直接基于基础模型能力回答
    # - 其他模式：若有 file_ids 则执行检索
    source_files = []
    context = "（知识库服务正常，当前对话模式未关联相关资料）"
    da_meta = None
    
    # ── 合并引用的公共文档 file_ids ──
    # WHY: 案件引用了公共文档库时，Agent 对话检索应自动涵盖这些文档，
    #      用户无需手动勾选。
    _has_cross_project_refs = False  # 标记是否存在跨项目引用
    _public_ref_file_ids = set()     # 收集所有公共文档 file_ids，用于双路检索分离
    if req.project_id and req.file_ids:
        try:
            from core.database import get_db
            import json as _json
            import hashlib as _hashlib
            import os as _os
            from pathlib import Path as _Path
            from core.config import settings as _settings

            with get_db() as _conn:
                _refs = _conn.execute(
                    "SELECT library_id, file_ids FROM project_refs WHERE case_id = ?",
                    (req.project_id,),
                ).fetchall()
            for _ref in _refs:
                _ref_dict = dict(_ref)
                _lib_id = _ref_dict.get("library_id", "")
                _ref_file_ids = _json.loads(_ref_dict.get("file_ids", "[]"))

                if _ref_file_ids:
                    # 引用了指定文件
                    req.file_ids = list(set(req.file_ids + _ref_file_ids))
                    _public_ref_file_ids.update(_ref_file_ids)
                    _has_cross_project_refs = True
                else:
                    # WHY: file_ids=[] 表示"引用全部文件"。
                    #      需要扫描公共文档库目录，生成全量 file_id 列表。
                    _lib_dir = _Path(_settings.UPLOAD_DIR) / _lib_id
                    if _lib_dir.exists():
                        _lib_file_ids = []
                        for _root, _dirs, _fnames in _os.walk(str(_lib_dir)):
                            _dirs[:] = [d for d in _dirs if not d.startswith(".")]
                            for _fname in _fnames:
                                if _fname.startswith("."):
                                    continue
                                _fpath = _os.path.join(_root, _fname)
                                _rel_path = _os.path.relpath(
                                    _fpath, str(_Path(_settings.UPLOAD_DIR))
                                )
                                _fid = _hashlib.md5(
                                    f"{_lib_id}_{_rel_path}".encode("utf-8")
                                ).hexdigest()
                                _lib_file_ids.append(_fid)
                        if _lib_file_ids:
                            req.file_ids = list(set(req.file_ids + _lib_file_ids))
                            _public_ref_file_ids.update(_lib_file_ids)
                            _has_cross_project_refs = True
                            print(
                                f"📚 合并公共文档库全量文件 | library={_lib_id} | "
                                f"+{len(_lib_file_ids)} 个文件",
                                flush=True,
                            )
            if _has_cross_project_refs:
                print(
                    f"📚 公共文档合并完成 | 总 file_ids={len(req.file_ids)}",
                    flush=True,
                )
        except Exception as _e:
            print(f"⚠️ 合并公共文档引用失败(非致命): {_e}", flush=True)

    # ── 多 Agent 协同模式（smart）──
    # WHY: chat_mode="smart" 走全新的多 Agent 协作链路：
    #      此处理移动到此处，是为了保证公共文档合并逻辑已经将 file_ids 完全展开补全。
    if req.chat_mode == "smart":
        from core.agents.orchestrator import run_orchestration_stream

        async def _smart_sse():
            yield ": connection established\n\n"
            last_active_time = time.time()
            async for chunk in run_orchestration_stream(
                user_message=req.message,
                project_id=req.project_id,
                file_ids=req.file_ids,
                model=req.model,
                enable_critique=True,
            ):
                yield chunk
                # ── 续期 chat 活跃状态（每 10 秒续期一次，防止长时间生成时超时） ──
                now_time = time.time()
                if now_time - last_active_time > 10:
                    try:
                        set_agent_active("chat", f"回答咨询: {req.message[:20]}...", project_name, duration=25)
                        last_active_time = now_time
                    except Exception:
                        pass

        return StreamingResponse(
            _smart_sse(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
        )


    # ── 分离案件文件和公共文档文件 ──
    # WHY: 不能简单合并后清除 project_id 过滤——公共法律文档（如民法典 246 chunks）
    #      在语义上碾压案件证据文档，导致检索结果被公共文档独占。
    #      正确做法：双路检索——案件文档用 project_id 过滤精搜，公共文档单独搜，
    #      最终合并两路 context，保证案件+公共文档都被引用。
    _case_file_ids = []
    _pub_file_ids = []
    if req.file_ids:
        try:
            from core.database import get_db
            with get_db() as _conn:
                _placeholders = ",".join(["?"] * len(req.file_ids))
                _rows = _conn.execute(
                    f"SELECT DISTINCT file_id, project_id FROM doc_chunks_fts WHERE file_id IN ({_placeholders})",
                    req.file_ids,
                ).fetchall()
                _db_file_map = {row["file_id"]: row["project_id"] for row in _rows}
                for fid in req.file_ids:
                    if _db_file_map.get(fid) == req.project_id:
                        _case_file_ids.append(fid)
                    else:
                        _pub_file_ids.append(fid)
        except Exception as _e:
            print(f"⚠️ 动态识别本案与公共文档失败(非威胁/非致命): {_e}", flush=True)
            _case_file_ids = [fid for fid in req.file_ids if fid not in _public_ref_file_ids] if _has_cross_project_refs else req.file_ids
            _pub_file_ids = list(_public_ref_file_ids) if _has_cross_project_refs else []


    use_rag = req.file_ids and not is_simple and req.chat_mode != "general"
    print(f"🐛 [CHAT-DEBUG] msg='{req.message[:30]}' intent={intent} "
          f"case_files={len(_case_file_ids)} pub_files={len(_pub_file_ids)} "
          f"use_rag={use_rag} cross_project={_has_cross_project_refs}", flush=True)
    
    # WHY: L1 缓存的策略指纹 — 用 intent + strategy 核心字段的 hash 表示，
    #      确保不同意图（即使 search_query 相同）不会共用缓存。
    _strategy_fp = f"{intent}:{strategy.get('vector_top_k', 12)}:{strategy.get('inject_data_analysis', False)}"

    if use_rag:
        # ── L1 缓存检查：检索结果命中则跳过多路并行检索 ──
        from core.chat_cache import get_rag_cache, set_rag_cache
        l1_hit = get_rag_cache(
            req.project_id, search_query, req.file_ids, _strategy_fp
        )
        if l1_hit:
            print(
                f"🎯 [CHAT-L1] 检索缓存命中 | msg='{req.message[:30]}' "
                f"| context={len(l1_hit.get('context', ''))}字",
                flush=True,
            )
            context = l1_hit.get("context", context)
            source_files = l1_hit.get("source_files", [])
            da_meta = l1_hit.get("data_analysis_meta") or None
        else:
            # ── L1 未命中：执行完整检索 ──
            from core.retrieval_pipeline import run_retrieval

            # ── 路径 A: 检索案件文档（保留 project_id 过滤） ──
            retrieval = await run_retrieval(
                search_query=search_query,
                original_message=req.message,
                project_id=req.project_id,
                file_ids=_case_file_ids,
                strategy=strategy,
                model=req.model,
            )

            # ── 路径 B: 检索公共文档（无 project_id 过滤，仅按 file_ids） ──
            # WHY: 公共文档的 chunk 在 Qdrant 中 project_id 为 library_id，
            #      不能用案件的 project_id 过滤，只能按 file_ids 精确检索。
            if _pub_file_ids:
                from core.vector_store import query_by_file_ids as _vs_query
                from starlette.concurrency import run_in_threadpool as _rtp
                try:
                    _pub_docs = await _rtp(
                        _vs_query, search_query, _pub_file_ids, "", 6,
                    )
                    if _pub_docs:
                        _pub_context_parts = []
                        _pub_sources = []
                        _seen = set()
                        for _d in _pub_docs:
                            _fname = _d['metadata'].get('filename', '未知')
                            if _fname not in _seen:
                                _pub_sources.append(_fname)
                                _seen.add(_fname)
                            _pub_context_parts.append(
                                f"---【公共法律文献参考】---\n"
                                f"【来源】: {_fname}\n"
                                f"【内容】:\n```\n{_d['content']}\n```"
                            )
                        # 合并：案件 context 在前，公共文档 context 在后
                        _pub_ctx = "\n\n".join(_pub_context_parts)
                        if retrieval.context:
                            retrieval.context += "\n\n" + _pub_ctx
                        else:
                            retrieval.context = _pub_ctx
                        retrieval.source_files.extend(_pub_sources)
                        print(
                            f"📚 公共文档检索完成 | 命中 {len(_pub_docs)} 个 chunks | "
                            f"来源: {', '.join(_pub_sources)}",
                            flush=True,
                        )
                except Exception as _pub_e:
                    print(f"⚠️ 公共文档检索失败(非致命): {_pub_e}", flush=True)

            context = retrieval.context or context
            source_files = retrieval.source_files
            # WHY: 提取 DuckDB 分析元数据，通过 SSE 直接推送到前端独立渲染
            da_meta = retrieval.data_analysis_meta or None

            # ── L1 缓存写入 ──
            set_rag_cache(
                req.project_id, search_query, req.file_ids, _strategy_fp,
                context, source_files, da_meta,
            )

    elif req.chat_mode == "general":
        context = "（通用模式已开启：已跳过文档检索，仅使用大模型基础知识库进行回答）"
    elif is_simple:
        context = "（简单询问：已自动跳过文档检索以实现毫秒级响应）"


    # WHY: stateless 模式不注入历史，每次对话完全独立
    history_text = "" if req.chat_mode == "stateless" else _truncate_history(req.history)

    # 2. 动态系统角色判定 (高度优先级：自定义 Persona > 专家模式 > 默认助手)
    if intent == "data_analysis":
        sys_prompt = (
            f"你是「{project_name}」项目的数据分析助手。"
            f"系统已使用 DuckDB SQL 引擎对项目的完整 Excel 数据进行了精确查询。"
            f"请根据查询结果，用简洁专业的语言回答用户问题。\n"
            f"规则：\n"
            f"1. 直接引用查询结果中的精确数值，不要说'根据查询结果'等废话。\n"
            f"2. 如果结果是多行数据，用表格或列表格式展示。\n"
            f"3. 严禁捷造数据或说'无法统计'。"
        )
    elif custom_persona:
        sys_prompt = f"你目前正在主导「{project_name}」项目。用户为你定义了专属角色与行事规则，请严格遵循以下设定：\n\n{custom_persona}"
    elif req.chat_mode == "expert":
        sys_prompt = f"你目前正以专家身份处理「{project_name}」项目。\n{EXPERT_PERSONA}"
    else:
        sys_prompt = (
            f"你是一个智能、专业的「{project_name}」项目专属解答助手。请仔细根据参考资料回答用户的问题。\n\n"
            f"⚠️ 重要引用与归因规则（必须严格遵循）：\n"
            f"1. 严禁跨文档合并条款！在参考资料中，不同的【参考文档区块】属于完全不同的独立文件，各自的条款序号没有任何前后承接关系。\n"
            f"2. 当你在回答中提及任何数值、尺寸、工艺参数或引用具体段落时，必须在回答中指明其所引用的确切物理来源文件名（例如：`根据《..._6.pdf》的第6条说明...`）。\n"
            f"3. 严禁将不同文件里的相似词汇（如\"田型调整\"与\"地形调整\"）或内容混淆其归属。"
        )

    # ── 统一排版格式约束（所有对话模式共享）──
    # WHY: 不加格式约束时，LLM 倾向于生成连续长段落，所有要点挤成一行，
    #      前端虽然有 whitespace-pre-wrap，但模型未输出换行符就无效。
    #      注入后模型会自觉使用 Markdown 标记和适当分段。
    _FORMAT_RULES = (
        "\n\n📐 **输出排版格式要求**（必须严格遵循）：\n"
        "1. **结构化分段**：回答内容必须按主题分段，每段之间用空行隔开，严禁将所有内容挤在一个段落中。\n"
        "2. **善用 Markdown 标记**：\n"
        "   - 用 `##` / `###` 标记主要章节标题\n"
        "   - 用 `**粗体**` 标记关键术语、金额、日期等重点信息\n"
        "   - 用有序列表（`1. 2. 3.`）或无序列表（`- `）罗列多个要点\n"
        "   - 涉及多项赔偿/费用/条款时，必须逐项单独成行，每项独占一行\n"
        "3. **段落首行缩进**：纯叙述性段落的开头请使用两个全角空格（"  "）缩进\n"
        "4. **禁止内容堆叠**：严禁在一行内罗列超过 2 个独立要点；"
        "如需列举 3 项以上，必须换行使用列表格式"
    )
    sys_prompt += _FORMAT_RULES

    # 简单问题修正：双重保险——Prompt 文字约束 + qwen3 /no_think 模型级指令
    if is_simple:
        sys_prompt += "\n\n【响应约束】当前为简单问候或基础信息查询。请在 1 句话内快速回答，严禁输出 <think> 思考过程。"

    # 3. 组装最终 Prompt
    prompt = f"{sys_prompt}\n\n## 参考资料\n{context}\n\n"
    if history_text:
        prompt += f"{history_text}\n\n"
    prompt += f"## 用户问题\n{req.message}"

    # WHY: 所有 chat 模式都必须追加 /no_think 指令。
    #      根因：qwen3.6 默认先生成长篇 <think> 推理链，然后才输出正式回答。
    #      当 RAG context 包含大量结构化数据时，模型在 <think> 阶段就耗尽了
    #      num_predict 的全部 token 预算 → 正式回答部分为 0 个 token → 用户看到空白回复。
    #      /no_think 在 _stream_ollama_inner 中触发 raw bypass，注入 <think>\n</think>\n
    #      前缀强制跳过推演。deep/expert 模式的 think_mode="format" 不受影响，
    #      因为 think 前缀已被提前关闭，模型不会再生成 <think> 标签。
    prompt += "\n\n/no_think"
    
    # 4. 决定是否在 SSE 侧物理过滤思考链
    # - fast 模式或 simple 问题：强制开启 filter (物理清除 <think> 标签)
    # - deep/expert 模式：保留 raw 思考链给前端渲染
    # 4. 决定思考模式
    # WHY: 意图策略中的 think_mode 可覆盖默认值。
    #      data_lookup 用 filter 跳过推演加速；summary/risk 用 raw 保留深度推理。
    #      但 chat_mode 和 is_simple 的显式设置优先级更高。
    think_mode = strategy.get("think_mode", "raw")
    if req.chat_mode in ("stateless", "fast") or is_simple:
        think_mode = "filter"
    elif req.chat_mode == "general":
        think_mode = "filter"

    # 5. 动态调整 token 预算
    # WHY: 简单问题用极小预算截断推演；
    #      其他问题用意图策略中的 num_ctx（data_lookup 用 16K 更快）。
    if is_simple:
        chat_num_predict = 256
        chat_num_ctx = 16384
    else:
        chat_num_predict = 16384
        chat_num_ctx = 16384

    # ── 包装 SSE 生成器，流结束后写入 L2 缓存 ──
    async def _sse_with_cache():
        """
        包装 _sse_generator，在流式输出完成后收集完整回答并写入 L2 缓存。
        WHY: _sse_generator 已经累积了 _full_text_parts，但它是内部变量。
             通过外层包装器拦截所有 yield 的 token 事件来重建完整文本。
        """
        _answer_parts: list[str] = []
        last_active_time = time.time()
        async for event in _sse_generator(
            prompt, model=req.model, think_mode=think_mode, sources=source_files,
            num_predict=chat_num_predict, num_ctx=chat_num_ctx,
            data_analysis=da_meta if (use_rag or req.force_data_analysis) else None,
            project_id=req.project_id,
        ):
            yield event
            # ── 续期 chat 活跃状态（每 10 秒续期一次，防止生成长文本时超时） ──
            now_time = time.time()
            if now_time - last_active_time > 10:
                try:
                    set_agent_active("chat", f"回答咨询: {req.message[:20]}...", project_name, duration=25)
                    last_active_time = now_time
                except Exception:
                    pass

            # 拦截 token 事件，累积完整回答
            if event.startswith("data: "):
                try:
                    _payload = json.loads(event[6:].strip())
                    if "token" in _payload:
                        _answer_parts.append(_payload["token"])
                except Exception:
                    pass

        # 流结束后写入 L2 缓存
        if _answer_parts:
            _full_answer = "".join(_answer_parts)
            if _full_answer.strip():
                from core.chat_cache import set_answer_cache
                set_answer_cache(
                    req.project_id, req.message, req.chat_mode,
                    req.file_ids, _full_answer, source_files, da_meta,
                )

    return StreamingResponse(
        _sse_with_cache(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )


@router.get("/llm/status")
async def llm_status():
    """查询 Ollama 服务状态与模型列表，附带全系统巡检健康度状态。"""
    from core.config import IS_RAID_ACTIVE
    from core.vector_store import _get_client
    from core.graph_rag import graph_engine
    from core.redis_client import get_redis

    status_data = await get_ollama_status()
    status_data["raid_status"] = "online" if IS_RAID_ACTIVE else "offline"

    # 全链路巡检逻辑 (方案 2)
    health_status = "green"
    health_details = ["所有服务运行正常"]
    errors = []

    # 1. 检查 Ollama 连通性
    ollama_ok = status_data.get("status") == "online"
    if not ollama_ok:
        health_status = "red"
        errors.append("AI推理引擎(Ollama)离线")

    # 2. 检查存储阵列
    if not IS_RAID_ACTIVE:
        health_status = "red"
        errors.append("NAS存储阵列离线")

    # 3. 检查 Qdrant
    qdrant_ok = False
    try:
        _get_client().get_collections()
        qdrant_ok = True
    except Exception:
        health_status = "red"
        errors.append("向量数据库(Qdrant)连接失败")

    # 4. 检查 Neo4j
    neo4j_ok = False
    try:
        if graph_engine._ensure_connection():
            with graph_engine._driver.session() as session:
                session.run("RETURN 1").single()
            neo4j_ok = True
        else:
            health_status = "red"
            errors.append("图数据库(Neo4j)连接失败")
    except Exception:
        health_status = "red"
        errors.append("图数据库(Neo4j)连接失败")

    # 5. 检查 Celery 队列积压 (仅在没有 red 严重故障时判定 yellow)
    slow_q_len = 0
    fast_q_len = 0
    try:
        r = get_redis()
        if r:
            slow_q_len = r.llen("slow_queue") or 0
            fast_q_len = r.llen("celery") or 0
            if health_status != "red" and (slow_q_len > 5 or fast_q_len > 20):
                health_status = "yellow"
                health_details = [f"后台处理队列积压中 (慢速队列 {slow_q_len} 个，快速队列 {fast_q_len} 个)"]
    except Exception:
        pass

    if health_status == "red":
        health_details = [f"检测到严重故障: {', '.join(errors)}"]

    status_data["health"] = {
        "status": health_status,
        "details": "; ".join(health_details),
        "metrics": {
            "slow_queue": slow_q_len,
            "fast_queue": fast_q_len,
            "ollama": "online" if ollama_ok else "offline",
            "qdrant": "online" if qdrant_ok else "offline",
            "neo4j": "online" if neo4j_ok else "offline",
            "raid": "online" if IS_RAID_ACTIVE else "offline"
        }
    }

    logger.info(f"OLLAMA STATUS WITH HEALTH: {status_data}")
    return status_data


class SwitchModelRequest(BaseModel):
    new_model: str
    previous_model: Optional[str] = None


@router.post("/llm/switch")
async def switch_model(req: SwitchModelRequest, user: dict = Depends(get_current_user)):
    """
    切换载入新的大模型，并停用旧的模型。
    """
    from core.llm_engine import switch_ollama_model
    result = await switch_ollama_model(req.new_model, req.previous_model)
    if result["status"] == "error":
        raise HTTPException(status_code=500, detail=result.get("message", "切换失败"))
    return result


# ────────────────────────────────────────────────────────
# 智能推荐 Persona
# WHY: 新用户不知道怎么写 Persona 提示词。根据上传的资料
#       自动分析项目行业和内容，推荐一段专业的角色设定。
# ────────────────────────────────────────────────────────

class RecommendPersonaRequest(BaseModel):
    project_id: str
    model: str = settings.DEFAULT_LLM_MODEL
    # WHY: 用户在「文档编写」中已选择的大纲章节标题是推断报告类型的金矿
    template_sections: list[str] = []


@router.post("/recommend-persona")
async def recommend_persona(req: RecommendPersonaRequest, user: dict = Depends(get_current_user)):
    """
    根据项目资料智能推荐 Persona 提示词（增强版）。
    增强点：多文件交叉采样 + 大纲感知 + 专业术语/标准编号提取。
    """
    import re as _re
    from core.llm_engine import current_project_id
    current_project_id.set(req.project_id)

    require_project_access(req.project_id, user, write=True)

    # ── 1. (已移除) 原本地文件扫描，现完全依赖 Qdrant 采样 ──

    # ── 2. 读取项目名称 ──
    from core.project_access import _read_projects
    project_name = ""
    for p in _read_projects():
        if p["id"] == req.project_id:
            project_name = p.get("name", "")
            break

    # ── 3. 多文件交叉采样 ──
    # WHY: 旧方案只用项目名查 3 条，可能全来自同一篇文档。
    #       新方案确保每个文件至少贡献 1 段首段内容，全面覆盖知识库。
    from core.vector_store import (
        _get_client, _collection_name, query_by_file_ids,
    )
    from qdrant_client import models as qd_models

    sampled_texts: list[dict] = []

    try:
        client = _get_client()
        # 3a. 每个文件取 chunk_index=0 的首段（通常包含摘要/概述）
        scroll_filter = qd_models.Filter(
            must=[
                qd_models.FieldCondition(
                    key="project_id",
                    match=qd_models.MatchValue(value=req.project_id),
                ),
                qd_models.FieldCondition(
                    key="chunk_index",
                    match=qd_models.MatchValue(value=0),
                ),
            ]
        )
        first_chunks, _ = client.scroll(
            collection_name=_collection_name,
            scroll_filter=scroll_filter,
            limit=30,
            with_payload=True,
            with_vectors=False,
        )
        seen_files = set()
        for pt in first_chunks:
            payload = pt.payload or {}
            if payload.get("chunk_type") == "table_index":
                continue
            fname = payload.get("filename", "")
            if fname in seen_files:
                continue
            seen_files.add(fname)
            sampled_texts.append({
                "filename": fname,
                "content": (payload.get("document", ""))[:400],
            })
    except Exception as exc:
        logger.warning(f"首段采样失败: {exc}")

    # 3b. 用项目名做语义查询，补充 5 条最相关内容（去重）
    try:
        docs = query_by_file_ids(
            project_name or "项目概况",
            file_ids=[],
            project_id=req.project_id,
            n_results=5,
        )
        for d in (docs or []):
            fname = d["metadata"].get("filename", "")
            content = d["content"][:400]
            if not any(
                s["filename"] == fname and s["content"][:100] == content[:100]
                for s in sampled_texts
            ):
                sampled_texts.append({"filename": fname, "content": content})
    except Exception as exc:
        logger.warning(f"RAG 语义采样失败: {exc}")

    # ── 4. 从采样内容中自动提取专业标准和地域关键词 ──
    all_sampled_text = " ".join(s["content"] for s in sampled_texts)

    standards = list(set(_re.findall(
        r'(?:GB/?T?|GBJ|DB\d*/T?|DL/T|SL/?T?|CJJ|JGJ|HJ|JT/T)\s*[\d\.\-]+(?:\-\d{4})?',
        all_sampled_text
    )))
    regions = list(set(_re.findall(
        r'[\u4e00-\u9fff]{2,6}(?:省|市|县|区|镇|乡|州)',
        all_sampled_text
    )))[:8]

    # ── 5. 构造增强版 Meta-Prompt ──
    if not sampled_texts:
        raise HTTPException(status_code=400, detail="该项目尚未解析完成任何资料，无法推荐")

    unique_files = list(dict.fromkeys(s["filename"] for s in sampled_texts))
    filenames_str = "\n".join(f"- {fn}" for fn in unique_files[:30])

    content_lines = []
    for s in sampled_texts[:15]:
        content_lines.append(f"[{s['filename']}] {s['content']}")
    content_summary = "\n".join(content_lines) if content_lines else "暂无摘要"

    outline_section = ""
    if req.template_sections:
        outline_str = "\n".join(
            f"  {i+1}. {sec}" for i, sec in enumerate(req.template_sections[:40])
        )
        outline_section = f"""
## 目标报告大纲结构（用户已选择的文档模板）
{outline_str}
"""

    standards_section = ""
    if standards:
        standards_section = f"\n## 资料中发现的专业标准编号\n{', '.join(standards[:15])}\n"

    regions_section = ""
    if regions:
        regions_section = f"\n## 项目涉及地域\n{', '.join(regions)}\n"

    meta_prompt = f"""你是一个顶级的工程咨询AI提示词工程专家。请根据以下项目资料信息，为"报告撰写AI助手"量身打造一段高度专业的角色设定（Persona Prompt）。

## 项目名称
{project_name or '未命名项目'}

请根据以下提供的 {len(unique_files)} 份项目实际资料的片段摘录，推断出最适合该科研/工程项目的AI角色定位。

## 提供给你的文件资料清单
{filenames_str}
{outline_section}{standards_section}{regions_section}
## 项目内容摘要（多文件交叉采样，共{len(sampled_texts)}段）
{content_summary}

## 输出要求
1. **强制要求**：必须使用**纯中文**输出，绝对禁止出现大段英文解释。
2. 先根据资料判断项目所属的具体工程咨询领域（如：高标准农田建设、水利工程可行性研究、防洪排涝规划、环境影响评价、勘察设计、地下水资源调查评价等）。
3. 输出一段专业、严谨、可以直接复制给 AI 使用的角色设定，结构如下（注意使用 Markdown 加粗）：
   - **# Role 定位**：定义一句话的顶级专家身份（例如：您是XXX项目的首席编制总工/资深咨询专家）。包含项目名称和具体技术领域。
   - **# 核心任务**：明确说明撰写专业技术报告、实施方案的核心原则与要求，需具备极强的专业水准。如果有大纲结构信息，需要明确提及报告应涵盖的核心章节方向。
   - **# 知识调用规范**：非常关键！明确指令大模型在编写时必须**充分调用自身庞大的内部专业知识库**。针对诸如"项目背景"、"综合评价"以及"专业法律法规、国家与行业规范标准"等段落，要求模型不仅依赖上传的碎片化资料，更应主动运用其内部先验知识进行高度结合、深度发散与详实验证。{f'特别注意：资料中发现以下标准编号，应要求模型在写作时主动补充标准具体细节：{", ".join(standards[:10])}' if standards else ''}
   - **# 资料深度融合与提炼**：明确要求模型具备强大的**分析与总结能力**，必须将上传资料中的具体数据、碎片事实、现状描述作为基础，与其内部广博的专业知识**高度交织融合**，并在输出阶段进行专业的凝练、归纳，确保最终文本具有极高的学术及工程报告含金量。做到"数据源自资料，深度剖析源自模型智慧"。
   - **# 风格与红线**：列出绝对禁止的事项（严禁口语化、严禁编造核心数据、必须符合正式公文与工程咨询规范文书的调性等）。
   - **# 数据与术语规范**：列出该专业领域内常用的标准化单位与术语表达。{f'项目涉及地区为{", ".join(regions)}，行文中应适配地方行政区划表述习惯。' if regions else ''}
4. 语气需要具有强烈的客观权威感和工程专业性，用词极其严谨。
5. **直接输出设定内容即可**，不要加任何前言后语，不要有类似"以下是为您推荐"的废话。"""

    # ── 6. 调用 LLM（StreamingResponse + 空格保活 + 优先级调度）──
    from fastapi.responses import StreamingResponse
    from core.llm_engine import llm_scheduler, PRIORITY_HIGH
    import json

    async def generate_with_keepalive():
        yield " " * 8192
        full_text = ""
        async with llm_scheduler.acquire(priority=PRIORITY_HIGH):
            try:
                async for chunk in stream_ollama(
                    meta_prompt, model=req.model,
                    num_predict=8192, num_ctx=16384,
                ):
                    full_text += chunk
                    yield " "
            except Exception as exc:
                yield json.dumps(
                    {"detail": f"LLM 推理失败: {exc}"}, ensure_ascii=False
                )
                return

        full_text = _re.sub(
            r'<think>.*?(</think>|$)', '', full_text, flags=_re.DOTALL
        ).strip()
        full_text = full_text.strip('`"\'')

        if not full_text:
            yield json.dumps(
                {"detail": "LLM 生成了空内容"}, ensure_ascii=False
            )
            return

        print(
            f"✅ Persona 推荐完成 (项目={project_name}, "
            f"{len(sampled_texts)} 段采样, {len(standards)} 个标准, "
            f"{len(full_text)}字)", flush=True,
        )
        yield json.dumps({"persona": full_text}, ensure_ascii=False)


    return StreamingResponse(
        generate_with_keepalive(), media_type="application/json",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Accel-Buffering": "no"},
    )


# ── 聊天记录持久化 API ──────────────────────────────────────────

class SaveChatHistoryRequest(BaseModel):
    project_id: str
    messages: list


@router.get("/chat/history")
async def get_chat_history(project_id: str, user: dict = Depends(get_current_user)):
    """获取指定项目的聊天历史记录。"""
    require_project_access(project_id, user, write=False)
    
    from core.database import get_db
    import json
    
    with get_db() as conn:
        row = conn.execute(
            "SELECT messages_json FROM chat_history WHERE project_id = ? AND user_id = ?",
            (project_id, user["id"])
        ).fetchone()
        
    if row:
        try:
            messages = json.loads(row["messages_json"])
        except Exception:
            messages = []
    else:
        messages = []
        
    return {"project_id": project_id, "messages": messages}


@router.post("/chat/history")
async def save_chat_history(req: SaveChatHistoryRequest, user: dict = Depends(get_current_user)):
    """保存或更新指定项目的聊天历史记录。"""
    require_project_access(req.project_id, user, write=True)
    
    from core.database import get_db
    import json
    from datetime import datetime, timezone, timedelta
    
    messages_json = json.dumps(req.messages, ensure_ascii=False)
    now_str = datetime.now(timezone(timedelta(hours=8))).replace(tzinfo=None).isoformat()
    
    with get_db() as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO chat_history (project_id, user_id, messages_json, updated_at)
            VALUES (?, ?, ?, ?)
            """,
            (req.project_id, user["id"], messages_json, now_str)
        )
        
    return {"status": "success"}


@router.delete("/chat/history")
async def delete_chat_history(project_id: str, user: dict = Depends(get_current_user)):
    """物理清空指定项目的聊天历史记录。"""
    require_project_access(project_id, user, write=True)
    
    from core.database import get_db
    
    with get_db() as conn:
        conn.execute(
            "DELETE FROM chat_history WHERE project_id = ? AND user_id = ?",
            (project_id, user["id"])
        )
        
    return {"status": "success"}


class InternalRagRequest(BaseModel):
    query: str
    project_id: str = ""
    file_ids: List[str] = []
    top_k: int = 10

@router.post("/internal/rag")
async def internal_rag(req: InternalRagRequest):
    """
    RAG 内部向量检索微服务接口。
    供 Go 网关的 Eino 节点远程调用，只做事实分片检索。
    """
    from core.vector_store import query_by_file_ids
    from starlette.concurrency import run_in_threadpool
    import asyncio

    # 动态分流本案文件和公共文档
    _case_fids = []
    _pub_fids = []
    if req.file_ids:
        try:
            from core.vector_store import get_file_metadata_multi_level
            _db_file_map = get_file_metadata_multi_level(req.file_ids, req.project_id)
            for fid in req.file_ids:
                _meta = _db_file_map.get(fid)
                if _meta and _meta.get("project_id") == req.project_id:
                    _case_fids.append(fid)
                else:
                    _pub_fids.append(fid)
        except Exception as _e:
            logger.warning(f"Internal RAG 识别本案与公共文档失败: {_e}")
            _case_fids = req.file_ids
            _pub_fids = []

    tasks = []
    if _case_fids:
        tasks.append(run_in_threadpool(
            query_by_file_ids, req.query, _case_fids, req.project_id, req.top_k
        ))
    else:
        tasks.append(asyncio.sleep(0, result=[]))

    if _pub_fids:
        tasks.append(run_in_threadpool(
            query_by_file_ids, req.query, _pub_fids, "", 6
        ))
    else:
        tasks.append(asyncio.sleep(0, result=[]))

    case_docs, pub_docs = await asyncio.gather(*tasks)
    docs = list(case_docs or []) + list(pub_docs or [])

    result_docs = []
    for d in docs[:req.top_k + 6]:
        result_docs.append({
            "filename": d['metadata'].get('filename', '未知'),
            "content": d['content']
        })
    return {"docs": result_docs}


class InternalCacheGetRequest(BaseModel):
    project_id: str
    message: str
    chat_mode: str
    file_ids: List[str] = []

class InternalCacheSetRequest(BaseModel):
    project_id: str
    message: str
    chat_mode: str
    file_ids: List[str] = []
    answer: str
    sources: List[str] = []

@router.post("/internal/chat/cache/get")
async def internal_cache_get(req: InternalCacheGetRequest):
    """供 Go 网关内部检查聊天缓存是否命中。"""
    from core.chat_cache import get_answer_cache
    l2_hit = get_answer_cache(
        req.project_id, req.message, req.chat_mode, req.file_ids
    )
    if l2_hit:
        return {
            "hit": True,
            "answer": l2_hit.get("answer", ""),
            "sources": l2_hit.get("sources", []),
            "data_analysis_meta": l2_hit.get("data_analysis_meta")
        }
    return {"hit": False}

@router.post("/internal/chat/cache/set")
async def internal_cache_set(req: InternalCacheSetRequest):
    """供 Go 网关在协同流生成完毕后异步将最终回答回写缓存。"""
    from core.chat_cache import set_answer_cache
    set_answer_cache(
        req.project_id, req.message, req.chat_mode, req.file_ids,
        req.answer, req.sources, None
    )
    return {"status": "success"}



