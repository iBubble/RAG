"""
查询预处理服务：LLM 查询改写 + 指代消解 + 简单问题判断。

WHY: 用户自然语言问题包含大量虚词和疑问句结构，直接做向量检索效果差。
     LLM 改写提取核心关键词后可显著提升召回率。
     同时整合指代消解和简单问题判断，统一管理查询预处理逻辑。

设计：主路径用 Ollama LLM 改写，失败时降级到正则规则。
      借鉴 DeepParseX query_rewrite_service.py 架构。
"""
from __future__ import annotations

import json
import logging
import re
import time
from typing import Optional

logger = logging.getLogger(__name__)

# WHY: 查询改写仅输出 2-8 个关键词（~20 tokens），8B 小模型完全胜任，
#      推理速度比 35B 快 10x（5-15s → 1-3s）。
_REWRITE_MODEL = "qwen3:8b"

# ── LLM 改写 Prompt ──────────────────────────────────────

_REWRITE_SYSTEM_PROMPT = (
    "你是一个搜索查询优化器。将用户的自然语言问题改写为适合"
    "全文检索和语义检索的简短查询词。\n\n"
    "改写规则：\n"
    "1. 提取核心实体、关键词，去掉疑问词"
    "（\"是什么\"\"怎么\"\"为什么\"\"多少\"\"有没有\"等）"
    "和时间修饰词（\"最近\"\"目前\"等）\n"
    "2. 保留专业术语、地名、编号（如 开发复垦001#、K0+300、"
    "GB50201）\n"
    "3. 保留数值+单位组合（如 10min、24h、0.5m）\n"
    "4. 输出 2~8 个核心词，用空格分隔\n"
    "5. 只返回改写后的查询词，不要有任何解释\n\n"
    "示例：\n"
    "用户: \"这个项目的防洪标准是怎么确定的？\" → 防洪标准 确定依据\n"
    "用户: \"整治地块开发复垦001#预计新增耕地面积是多少？\""
    " → 开发复垦001# 预计新增耕地面积\n"
    "用户: \"项目区涉及的行政村有哪些？\" → 项目区 行政村\n"
    "用户: \"土方工程量的计算方法是什么？\" → 土方工程量 计算方法\n"
)

# ── 正则兜底：去除常见疑问/修饰结构 ─────────────────────

_FILLER_RE = re.compile(
    r'(请问|请|帮我|帮忙|你知道|我想知道|能告诉我|查一下|找一下|搜一下'
    r'|是什么|是啥|有哪些|有什么|怎么样|怎样|如何|为什么|为何'
    r'|最近|近期|近来|当前|目前|现在|这个|这些|那个|那些'
    r'|吗|呢|啊|哦|嗯|\?|？|。|，|,|\.)+',
    re.IGNORECASE,
)

# ── 缓存：相同问题 5 分钟内直接返回 ─────────────────────

_rewrite_cache: dict[str, tuple[str, float]] = {}
_CACHE_TTL = 300  # 秒


def _cache_get(key: str) -> Optional[str]:
    """查询缓存，过期自动清理。"""
    entry = _rewrite_cache.get(key)
    if entry and time.time() - entry[1] < _CACHE_TTL:
        return entry[0]
    if entry:
        del _rewrite_cache[key]
    return None


def _cache_set(key: str, value: str) -> None:
    """写入缓存，超过 200 条时清理最早的一半。"""
    if len(_rewrite_cache) > 200:
        sorted_keys = sorted(
            _rewrite_cache, key=lambda k: _rewrite_cache[k][1]
        )
        for k in sorted_keys[:100]:
            del _rewrite_cache[k]
    _rewrite_cache[key] = (value, time.time())


# ── 简单问题判断 ─────────────────────────────────────────

_EXACT_TRIGGERS = {
    "你好", "嗨", "在吗", "你是谁", "我是谁", "你好啊", "你好呀",
    "谢谢", "感谢", "好的", "收到", "明白", "ok", "hi", "hello",
    "hey", "thanks", "help",
}

_CONTAINS_TRIGGERS = [
    "你是谁", "自我介绍", "你的角色", "你的功能", "你能做什么",
    "干什么的", "干嘛的", "什么助手", "who are you", "who am i",
    "what can you do",
]


def is_simple_query(text: str) -> bool:
    """
    判断是否为简单指令或身份询问，以此决定是否跳过 RAG。
    WHY: 简单问题触发快车道后，可稳定控制延迟。
    """
    text = text.strip().lower()
    if len(text) > 40:
        return False
    clean = re.sub(r'[^\w\u4e00-\u9fa5]', '', text)
    if clean in _EXACT_TRIGGERS:
        return True
    return any(t in text for t in _CONTAINS_TRIGGERS)


# ── 指代消解 ─────────────────────────────────────────────

_COREFERENCE_TRIGGERS = [
    "上面", "之前", "那个", "这个", "刚才", "前面",
    "它的", "这些", "那些", "上述",
]

_GENERIC_WORDS = {
    '根据', '参考', '资料', '显示', '可以', '其中', '以下',
    '如下', '来源', '项目', '数据', '信息', '内容', '文件',
    '建议', '分析', '总结', '相关', '关于', '目前', '具体',
}


def resolve_coreference(message: str, history: list) -> str:
    """
    1 轮历史指代消解：从最近 AI 回复中提取实体，补全指代词。

    WHY: 用户多轮对话中常用指代词代替具体内容，
         导致向量检索 query 语义模糊、命中率低。
    """
    if not any(t in message for t in _COREFERENCE_TRIGGERS):
        return message

    last_assistant_msg = ""
    for msg in reversed(history):
        role = msg.role if hasattr(msg, 'role') else msg.get('role', '')
        content = (
            msg.content if hasattr(msg, 'content') else msg.get('content', '')
        )
        if role in ("agent", "assistant"):
            last_assistant_msg = content
            break

    if not last_assistant_msg:
        return message

    # WHY: 提取中文名词短语 + 数值短语
    entities = re.findall(r'[\u4e00-\u9fa5]{2,8}', last_assistant_msg[:500])
    entities = [e for e in entities if e not in _GENERIC_WORDS][:5]

    numbers = re.findall(
        r'[\d\.]+\s*(?:万元|亿元|元|米|m|km|公里|亩|公顷|ha|%'
        r'|min|h|d|cm|mm|kg|吨|MPa)',
        last_assistant_msg[:500],
    )[:3]

    supplements = entities + numbers
    if supplements:
        resolved = f"{message} {' '.join(supplements)}"
        print(
            f"🔗 [指代消解] '{message[:30]}' -> 补充: {supplements}",
            flush=True,
        )
        return resolved

    return message


# ── 正则改写（降级路径）────────────────────────────────────

def _rewrite_by_regex(message: str, project_name: str = "") -> str:
    """
    正则改写：提取核心实体并拼接项目名。
    WHY: 当 LLM 不可用时作为降级路径。
    """
    # 提取中文短语
    zh_entities = re.findall(r'[\u4e00-\u9fa5]{3,8}', message)

    # 数值+单位混合术语
    mixed_entities = re.findall(
        r'\d+\s*(?:min|h|d|s|ms|km|m|mm|cm|ha|亩|吨|kg|MPa)',
        message, re.IGNORECASE
    )

    # 工程编号/桩号
    code_pattern = (
        r'[a-zA-Z]?\d+\+\d+(?:\.\d+)?'
        r'|(?:(?=[a-zA-Z0-9_-]*[a-zA-Z])'
        r'(?=[a-zA-Z0-9_-]*\d)[a-zA-Z0-9_-]+)'
    )
    code_entities = re.findall(code_pattern, message)

    # 过滤停用词
    STOP = {
        '什么是', '怎么样', '有没有', '是不是', '能不能', '请问下',
        '帮我看', '请问你', '帮我查', '告诉我', '介绍一', '解释下',
        '说说看', '分析一', '主要有', '包括哪', '是否有', '有哪些',
    }
    zh_entities = [e for e in zh_entities if e not in STOP][:5]

    # 去重组合
    seen = set()
    unique_entities = []

    for c in code_entities:
        key = c.replace(' ', '').lower()
        if key not in seen:
            seen.add(key)
            unique_entities.append(c)

    for m in mixed_entities[:3]:
        key = m.replace(' ', '').lower()
        if key not in seen:
            seen.add(key)
            unique_entities.append(m)

    for e in zh_entities:
        key = e.replace(' ', '').lower()
        if key not in seen:
            seen.add(key)
            unique_entities.append(e)

    if unique_entities:
        return f"{project_name} {' '.join(unique_entities)}".strip()
    return f"{project_name} {message}".strip()


# ── LLM 改写（主路径）──────────────────────────────────────

async def _rewrite_by_llm(
    question: str,
    model: str = _REWRITE_MODEL,
) -> Optional[str]:
    """
    调用 Ollama LLM 提取核心检索关键词。

    WHY: LLM 能理解语义，比纯正则更精准地去除虚词、
         保留专业术语和工程编号。
    Returns:
        改写后的查询字符串，失败返回 None（触发降级）。
    """
    from core.llm_engine import get_client, _gpu_semaphore
    from core.config import settings

    url = f"{settings.OLLAMA_BASE_URL}/api/generate"

    # WHY: 使用 ChatML raw 模式 + /no_think 跳过推演链，
    #      最大限度压缩延迟。
    raw_prompt = (
        f"<|im_start|>system\n{_REWRITE_SYSTEM_PROMPT}<|im_end|>\n"
        f"<|im_start|>user\n{question}<|im_end|>\n"
        f"<|im_start|>assistant\n<think>\n</think>\n"
    )

    payload = {
        "model": model,
        "prompt": raw_prompt,
        "raw": True,
        "stream": False,
        "think": False,
        "keep_alive": -1,
        "options": {
            "temperature": 0,
            "num_predict": 60,
            "num_ctx": 2048,
            "repeat_penalty": 1.0,
        },
    }

    try:
        async with _gpu_semaphore:
            client = get_client()
            resp = await client.post(url, json=payload, timeout=15.0)
            resp.raise_for_status()
            data = resp.json()
            raw_text = data.get("response", "").strip()

        if not raw_text:
            return None

        # 清理：取第一行，去掉可能的 markdown 包裹
        rewritten = raw_text.strip().splitlines()[0].strip()
        rewritten = rewritten.strip('`"\'')

        # WHY: 过滤 <think> 残留
        rewritten = re.sub(
            r'<think>.*?(</think>|$)', '', rewritten, flags=re.DOTALL
        ).strip()

        # 合理性校验：长度在 2~100 字符之间
        if rewritten and 2 <= len(rewritten) <= 100:
            return rewritten

        return None

    except Exception as e:
        logger.warning(f"[query_rewrite] LLM 改写失败，降级到规则: {repr(e)}")
        return None


# ── 公开入口 ─────────────────────────────────────────────

async def rewrite_query(
    question: str,
    project_name: str = "",
    model: str = _REWRITE_MODEL,
) -> str:
    """
    查询改写主入口：LLM 改写 → 规则兜底。

    Args:
        question: 用户原始问题
        project_name: 项目名称（拼接到改写结果前）
        model: Ollama 模型名

    Returns:
        改写后的检索 query
    """
    # 短问题不改写
    if len(question.strip()) <= 10:
        return f"{project_name} {question}".strip()

    # 缓存命中
    cache_key = f"{project_name}|{question}"
    cached = _cache_get(cache_key)
    if cached:
        print(
            f"🔍 [QueryRewrite] 缓存命中: '{question[:30]}' -> '{cached[:50]}'",
            flush=True,
        )
        return cached

    # 主路径：LLM 改写
    rewritten = await _rewrite_by_llm(question, model)

    if rewritten:
        result = f"{project_name} {rewritten}".strip()
        print(
            f"🔍 [QueryRewrite/LLM] '{question[:30]}...' -> '{result[:50]}'",
            flush=True,
        )
    else:
        # 降级：正则改写
        result = _rewrite_by_regex(question, project_name)
        print(
            f"🔍 [QueryRewrite/Regex] '{question[:30]}...' -> '{result[:50]}'",
            flush=True,
        )

    _cache_set(cache_key, result)
    return result
