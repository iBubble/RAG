"""
Slot-Filling Phase 2 — 变量抽取模块。

WHY: Replace 模式下，LLM 在单次调用中同时执行"变量识别+正文生成"，
     注意力分散导致地名遗漏、数据错配。将变量抽取独立为 Step 1，
     让 LLM 先专注输出 JSON 映射表，Step 2 再按表填充，
     任务从"阅读理解+写作"降维为"查表+填充"。

架构: 范文 + RAG → SLOT_EXTRACT_PROMPT → LLM(temperature=0) → JSON映射表
"""
from __future__ import annotations

import json
import logging
import re
import time
from core.config import settings

logger = logging.getLogger(__name__)

# WHY: 专门的抽取 Prompt——纯结构化输出任务，不需要创造力。
#      temperature=0 + /no_think 确保输出稳定可解析。
SLOT_EXTRACT_PROMPT = """你是一个精确的文本变量抽取工具。

## 任务
分析下方【范文】中所有需要替换的变量实体，并从【新项目资料】中查找对应的新值。

## 范文
{exemplar_content}

## 新项目资料
{rag_context}

## 新项目名称：{project_name}

## 输出格式（严格 JSON，不要输出任何其他内容）
```json
{{"slots": [
  {{"old": "旧值原文", "new": "新值或[待补充]", "type": "地名|数据|时间|地理|机构"}}
]}}
```

## 抽取规则
1. **地名类**：所有行政区划（省/市/县/区/镇/乡/村/街道）
2. **数据类**：所有数值+单位组合（面积/人口/金额/数量/百分比/坡度/座/个/条等）
3. **时间类**：年份、日期范围、时间跨度
4. **地理类**：河流名、山脉名、盆地名、地形描述
5. **机构类**：政府部门、企业、项目组名称
6. **不抽取**：政策术语（藏粮于地、乡村振兴等）、法规名称、技术标准编号
7. **new字段**：从新项目资料中精确匹配；确实找不到用"[待补充]"
8. 每个 old 值必须是范文中的**原文片段**，确保可以精确定位

仅输出 JSON 代码块，不要任何解释文字。
/no_think"""


def _parse_slots_json(raw_text: str) -> list[dict]:
    """
    从 LLM 输出中解析 slots JSON，支持容错。

    WHY: LLM 的 JSON 输出可能被 <think> 标签包裹、
         带 markdown 代码块标记、或含尾部解释文字。
         需要多层清洗才能可靠解析。
    """
    # 清除 <think>...</think> 标签
    text = re.sub(
        r'<think>.*?</think>', '', raw_text, flags=re.DOTALL
    )

    # 尝试提取 ```json ... ``` 代码块
    json_match = re.search(
        r'```(?:json)?\s*(\{.*?\})\s*```', text, re.DOTALL
    )
    if json_match:
        text = json_match.group(1)
    else:
        # 尝试提取裸 JSON 对象
        json_match = re.search(r'\{.*\}', text, re.DOTALL)
        if json_match:
            text = json_match.group(0)

    try:
        data = json.loads(text)
        slots = data.get("slots", [])
        # 校验每个 slot 的格式
        valid = []
        for s in slots:
            if (
                isinstance(s, dict)
                and "old" in s
                and "new" in s
                and s["old"].strip()
            ):
                valid.append({
                    "old": s["old"].strip(),
                    "new": s.get("new", "[待补充]").strip(),
                    "type": s.get("type", "未知"),
                })
        return valid
    except (json.JSONDecodeError, AttributeError) as e:
        logger.warning(f"Slot JSON 解析失败: {e}")
        logger.debug(f"原始文本: {text[:500]}")
        return []


async def extract_slots(
    exemplar_content: str,
    rag_context: str,
    project_name: str,
    model: str = settings.DEFAULT_LLM_MODEL,
    timeout: float = 20.0,
) -> list[dict]:
    """
    Step 1：从范文中抽取需替换的变量，从 RAG 上下文匹配新值。

    返回: [{"old": "船山区", "new": "蓬溪县", "type": "地名"}, ...]
    如果抽取失败或超时，返回空列表（调用方应降级到 Phase 1）。
    """
    import asyncio
    from core.llm_engine import stream_ollama

    prompt = SLOT_EXTRACT_PROMPT.format(
        exemplar_content=exemplar_content[:3000],
        rag_context=rag_context[:3000],
        project_name=project_name,
    )

    t_start = time.time()
    logger.info(
        f"🔍 Slot 抽取启动 | project={project_name} | "
        f"exemplar={len(exemplar_content)}字"
    )

    try:
        # WHY: 收集完整输出（非流式），因为需要完整 JSON 才能解析。
        #      使用 asyncio.wait_for 做硬超时保护。
        chunks: list[str] = []

        async def _collect():
            async for chunk in stream_ollama(
                prompt,
                model=model,
                temperature=0,
                num_predict=2048,
                num_ctx=16384,
            ):
                chunks.append(chunk)

        task = asyncio.create_task(_collect())
        done, pending = await asyncio.wait([task], timeout=timeout)

        if pending:
            # WHY: 不要取消 task，让它在后台继续跑完。
            #      如果在生成阶段强行 cancel，会强制关闭 HTTP 连接，
            #      Ollama 存在 bug，可能导致 GPU 锁死无法释放，造成所有后续请求阻塞。
            elapsed = time.time() - t_start
            logger.warning(
                f"⏱️ Slot 抽取超时 ({elapsed:.1f}s > {timeout}s)，"
                f"已将其置于后台继续运行以防死锁，降级到 Phase 1"
            )
            return []
        
        if task.exception():
            raise task.exception()

        raw = "".join(chunks)

    except Exception as e:
        logger.error(f"Slot 抽取异常: {e}")
        return []

    elapsed = time.time() - t_start
    slots = _parse_slots_json(raw)

    if slots:
        logger.info(
            f"✅ Slot 抽取完成 | {len(slots)} 个变量 | "
            f"{elapsed:.1f}s"
        )
        # 打印映射表摘要（限前 8 条，防日志过长）
        for s in slots[:8]:
            logger.info(
                f"  📌 {s['type']}: "
                f"「{s['old']}」→「{s['new']}」"
            )
        if len(slots) > 8:
            logger.info(f"  ... 共 {len(slots)} 条")
    else:
        logger.warning(
            f"⚠️ Slot 抽取无结果 ({elapsed:.1f}s)，"
            f"降级到 Phase 1"
        )

    return slots


def format_slot_table(slots: list[dict]) -> str:
    """将映射表格式化为 Prompt 注入文本。"""
    if not slots:
        return "（无预配对映射，请自行从参考资料中匹配）"

    lines = []
    for s in slots:
        marker = "✅" if s["new"] != "[待补充]" else "❓"
        lines.append(
            f"- {marker} {s['old']} → {s['new']}  "
            f"({s['type']})"
        )
    return "\n".join(lines)
