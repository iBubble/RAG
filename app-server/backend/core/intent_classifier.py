"""
LLM 意图分类服务。

WHY: 原 classify_intent() 是纯关键词规则匹配，误分类率高：
     "果园面积多少" 匹配到 table_stats 的"多少"，
     但实际只需精确查询单个值。
     LLM 能理解语义，输出各检索路径的相关性评分，
     精确控制哪些路径启用。

设计：
- 主路径：Ollama LLM 多维度评分（0~1）
- 降级路径：关键词规则（保留原有逻辑）
- 借鉴 DeepParseX intent_service.py 架构
"""
from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)

from core.config import settings

# WHY: 统一使用 35B 大模型以独占 GPU 显存，避免混用 8B 导致显存碎片与 CPU 降级
_INTENT_MODEL = settings.DEFAULT_LLM_MODEL


# ── 意图分类结果 ─────────────────────────────────────────

@dataclass
class IntentResult:
    """意图分类结果。"""
    intent: str = "general_qa"
    scores: dict = field(default_factory=dict)
    strategy: dict = field(default_factory=dict)


# ── LLM 意图分类 Prompt ──────────────────────────────────

_INTENT_PROMPT = """你是一个智能问题分类器。分析用户的问题，判断需要使用哪些检索路径来回答。

可用的检索路径：
1. vector：语义向量检索，从文档中找语义相关的段落
2. graph：知识图谱检索，查找实体之间的关系
3. table_stats：表格数据统计，对结构化数据做精确计算（合计、平均、筛选等）
4. community：社区摘要检索，获取项目全局概况和跨文档关联
5. data_analysis：全量数据精确计算分析（全表统计、聚合计算、条件筛选、分组汇总），适用于需要遍历整张表的问题

判断规则：
- 问全量统计（总共多少、所有XX的合计、整个项目）→ data_analysis 高分
- 问条件聚合（按村分组统计、材质为XX的有多少）→ data_analysis 高分
- 问"多少根""多少个""合计长度""总面积" → data_analysis 高分
- 问具体某个数值（某地块面积、某个投资额）→ table_stats 高分
- 问实体关系（涉及哪些、关联什么）→ graph 高分
- 问内容解释（什么是、怎么做）→ vector 高分
- 问全局概况（整体情况、项目概述）→ community 高分
- 问对比分析 → vector + community 高分

只返回 JSON，格式：
{"vector": 0.8, "graph": 0.3, "table_stats": 0.9, "community": 0.1, "data_analysis": 0.7}
分数范围 0~1，只返回 JSON，不要解释。"""

# ── 缓存 ─────────────────────────────────────────────────

_intent_cache: dict[str, tuple[IntentResult, float]] = {}
_CACHE_TTL = 300


def _cache_get(key: str) -> Optional[IntentResult]:
    entry = _intent_cache.get(key)
    if entry and time.time() - entry[1] < _CACHE_TTL:
        return entry[0]
    if entry:
        del _intent_cache[key]
    return None


def _cache_set(key: str, value: IntentResult) -> None:
    if len(_intent_cache) > 200:
        sorted_keys = sorted(
            _intent_cache, key=lambda k: _intent_cache[k][1]
        )
        for k in sorted_keys[:100]:
            del _intent_cache[k]
    _intent_cache[key] = (value, time.time())


# ── 预定义策略配置 ────────────────────────────────────────

_STRATEGY_TEMPLATES = {
    "data_analysis": {
        "vector_top_k": 2,
        "graph_max_paths": 0,
        "table_max": 0,
        "num_ctx": 16384,
        "think_mode": "filter",
        "inject_community": False,
        "inject_table_stats": False,
        "inject_data_analysis": True,
    },
    "table_stats": {
        "vector_top_k": 4,
        "graph_max_paths": 2,
        "table_max": 3,
        "num_ctx": 16384,
        "think_mode": "raw",
        "inject_community": False,
        "inject_table_stats": True,
    },
    "data_lookup": {
        "vector_top_k": 6,
        "graph_max_paths": 4,
        "table_max": 3,
        "num_ctx": 16384,
        "think_mode": "filter",
        "inject_community": False,
    },
    "graph_focus": {
        "vector_top_k": 8,
        "graph_max_paths": 12,
        "table_max": 1,
        "num_ctx": 16384,
        "think_mode": "raw",
        "inject_community": True,
    },
    "summary": {
        "vector_top_k": 8,
        "graph_max_paths": 12,
        "table_max": 1,
        "num_ctx": 16384,
        "think_mode": "raw",
        "inject_community": True,
    },
    "comparison": {
        "vector_top_k": 12,
        "graph_max_paths": 8,
        "table_max": 4,
        "num_ctx": 16384,
        "think_mode": "raw",
        "inject_community": True,
    },
    "general_qa": {
        "vector_top_k": 12,
        "graph_max_paths": 8,
        "table_max": 3,
        "num_ctx": 16384,
        "think_mode": "raw",
        "inject_community": False,
    },
}


def _scores_to_intent(scores: dict) -> str:
    """根据各路径评分判断主意图。"""
    ts = scores.get("table_stats", 0)
    gr = scores.get("graph", 0)
    cm = scores.get("community", 0)
    vc = scores.get("vector", 0)
    da = scores.get("data_analysis", 0)

    # WHY: data_analysis 优先级最高——全量聚合需要 DuckDB 引擎
    if da >= 0.7:
        return "data_analysis"
    # WHY: 按最高分路径确定主意图，
    #      table_stats 和 graph 需要额外阈值避免误触发
    if ts >= 0.7:
        return "table_stats"
    if ts >= 0.5 and vc < 0.6:
        return "data_lookup"
    if gr >= 0.7:
        return "graph_focus"
    if cm >= 0.7:
        return "summary"
    if vc >= 0.5 and cm >= 0.5:
        return "comparison"
    return "general_qa"


def _build_strategy(intent: str, scores: dict) -> dict:
    """根据意图和评分构建检索策略。"""
    base = _STRATEGY_TEMPLATES.get(intent, _STRATEGY_TEMPLATES["general_qa"])
    strategy = dict(base)

    # WHY: 根据各路径评分微调参数
    if scores.get("data_analysis", 0) >= 0.5:
        strategy["inject_data_analysis"] = True
    if scores.get("table_stats", 0) >= 0.5:
        strategy["inject_table_stats"] = True
    if scores.get("community", 0) >= 0.5:
        strategy["inject_community"] = True

    return strategy


# ── 关键词规则降级 ────────────────────────────────────────

def _classify_by_rules(message: str) -> IntentResult:
    """
    纯关键词规则意图分类（降级路径）。
    WHY: LLM 不可用时保证功能不退化。
    """
    msg = message.strip()

    INTENT_RULES = [
        ("data_analysis", {
            "keywords": [
                "总共", "一共", "共有", "合计", "总计", "总数",
                "统计", "汇总", "整个", "全部", "所有",
                "总面积", "总投资", "总工程量",
                "合计长度", "合计面积", "合计数量",
                "多少根", "多少个", "多少条",
                "按照", "分组", "分类汇总",
            ],
        }),
        ("table_stats", {
            "keywords": [
                "列出所有", "全部列出", "有哪些",
                "最大", "最小", "平均", "排名", "前几", "前五", "前十",
                "分布", "占比", "比例",
                "多少",
            ],
        }),
        ("data_lookup", {
            "keywords": [
                "是几", "数据", "造价", "金额", "面积",
                "长度", "数量", "高程", "坡比", "投资", "定额",
                "指标", "参数", "单价", "工程量",
            ],
        }),
        ("comparison", {
            "keywords": [
                "对比", "比较", "区别", "哪个好", "优劣",
                "方案一", "方案二", "差异", "不同",
            ],
        }),
        ("summary", {
            "keywords": [
                "总结", "概述", "整体", "全面", "总体", "综述",
                "全貌", "概况", "简介", "介绍", "总览", "梳理",
                "主要内容", "整个项目", "项目情况",
            ],
        }),
        ("graph_focus", {
            "keywords": [
                "涉及", "关联", "关系", "哪些实体", "知识图谱",
            ],
        }),
        ("risk_analysis", {
            "keywords": [
                "风险", "问题", "隐患", "难点", "注意",
                "防范", "措施", "建议", "对策",
            ],
        }),
    ]

    for intent_name, config in INTENT_RULES:
        if any(kw in msg for kw in config["keywords"]):
            strategy = _STRATEGY_TEMPLATES.get(
                intent_name, _STRATEGY_TEMPLATES["general_qa"]
            )
            return IntentResult(
                intent=intent_name,
                scores={},
                strategy=dict(strategy),
            )

    return IntentResult(
        intent="general_qa",
        scores={},
        strategy=dict(_STRATEGY_TEMPLATES["general_qa"]),
    )


# ── LLM 意图分类 ─────────────────────────────────────────

async def _classify_by_llm(
    message: str,
    model: str = _INTENT_MODEL,
) -> Optional[IntentResult]:
    """
    调用 Ollama LLM 评估各检索路径的相关性分数。
    Returns: IntentResult 或 None（触发降级）。
    """
    from core.llm_engine import get_client, _gpu_semaphore
    from core.config import settings

    url = f"{settings.OLLAMA_BASE_URL}/api/generate"

    raw_prompt = (
        f"<|im_start|>system\n{_INTENT_PROMPT}<|im_end|>\n"
        f"<|im_start|>user\n{message}<|im_end|>\n"
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

        # 清理 <think> 残留
        raw_text = re.sub(
            r'<think>.*?(</think>|$)', '', raw_text, flags=re.DOTALL
        ).strip()

        # 解析 JSON
        m = re.search(r'\{[^}]+\}', raw_text)
        if not m:
            return None

        scores = json.loads(m.group())

        # 校验格式
        valid_keys = {"vector", "graph", "table_stats", "community", "data_analysis"}
        if not any(k in scores for k in valid_keys):
            return None

        # 归一化到 0~1
        for k in valid_keys:
            v = scores.get(k, 0)
            if isinstance(v, (int, float)):
                scores[k] = max(0.0, min(1.0, float(v)))
            else:
                scores[k] = 0.0

        intent = _scores_to_intent(scores)
        strategy = _build_strategy(intent, scores)

        return IntentResult(
            intent=intent,
            scores=scores,
            strategy=strategy,
        )

    except Exception as e:
        logger.warning(
            f"[intent_classifier] LLM 分类失败，降级到规则: {repr(e)}"
        )
        return None


# ── 公开入口 ─────────────────────────────────────────────

async def classify_intent(
    message: str,
    model: str = _INTENT_MODEL,
) -> IntentResult:
    """
    意图分类主入口：LLM 评分 → 关键词规则兜底。

    Args:
        message: 用户原始消息
        model: Ollama 模型名

    Returns:
        IntentResult 包含意图名、评分和策略参数
    """
    # 缓存命中
    cache_key = message.strip()[:100]
    cached = _cache_get(cache_key)
    if cached:
        print(
            f"🎯 [Intent/Cache] intent={cached.intent}",
            flush=True,
        )
        return cached

    # 主路径：LLM 分类
    result = await _classify_by_llm(message, model)

    if result:
        print(
            f"🎯 [Intent/LLM] intent={result.intent} "
            f"scores={result.scores}",
            flush=True,
        )
    else:
        # 降级：关键词规则
        result = _classify_by_rules(message)
        print(
            f"🎯 [Intent/Rules] intent={result.intent}",
            flush=True,
        )

    _cache_set(cache_key, result)
    return result
