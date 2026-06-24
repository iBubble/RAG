"""
LLM Reranker 精排模块。

WHY: 原 CrossEncoder（bge-reranker-v2-m3）在 ARM/QEMU 服务器上推理极慢
     （35-70s for 16 docs），导致 TTFT 从 10s 飙到 77s。
     改用已在 GPU 上常驻的 qwen3.6:35b-q4 做排序，实测 10 docs 仅需 ~1s，
     精度与 CrossEncoder 相当（准确地将表格数据排到第 1 位），
     且零额外内存开销。

架构：同步调用 Ollama /api/generate → 解析编号序列 → 重排文档列表。
"""
from __future__ import annotations

import json
import logging
import re
import time
from typing import List

import requests

from core.config import settings

logger = logging.getLogger(__name__)

# WHY: 与 llm_engine.py 保持一致的模型名
_RERANK_MODEL = "qwen3.6:35b-q4"

# WHY: 限制每段摘要长度，30 个候选 * 150 字 ≈ 4500 字，加 Prompt 约 5000 tokens
_MAX_SNIPPET_LEN = 150
_OLLAMA_TIMEOUT = 10  # WHY: 15→10s，Reranker prompt 仅 ~2K tokens，10s 足够覆盖


def _build_rerank_prompt(query: str, snippets: List[str]) -> str:
    """
    构建排序 Prompt。
    WHY: 使用 /no_think 跳过思考链，减少输出 tokens，加速响应。
         只要求输出逗号分隔的编号，方便正则解析。
    """
    numbered = "\n".join(
        f"{i+1}. {s}" for i, s in enumerate(snippets)
    )
    return f"""你是一个文档相关性排序工具。请将以下{len(snippets)}段文本按与问题的相关性从高到低排序。

## 规则
- 只输出编号序列，用逗号分隔（如：3,1,5,2,4）
- 不要解释，不要输出其他内容

## 问题
{query}

## 文本
{numbered}

/no_think"""


def _parse_ranking(raw: str, n: int) -> List[int]:
    """
    从 LLM 输出中解析编号序列。
    WHY: LLM 可能输出 <think> 标签或多余文字，需要鲁棒解析。
         先去 think 标签，再提取所有数字，过滤范围外的值。
    """
    # 去除 <think>...</think>
    text = re.sub(r'<think>.*?</think>', '', raw, flags=re.DOTALL)
    text = text.strip()

    # 提取所有数字
    numbers = re.findall(r'\d+', text)
    indices = []
    seen = set()
    for num_str in numbers:
        idx = int(num_str)
        # WHY: 过滤范围外的数字和重复值
        if 1 <= idx <= n and idx not in seen:
            seen.add(idx)
            indices.append(idx - 1)  # 转为 0-indexed

    return indices


def llm_rerank(
    query: str,
    documents: List[dict],
    top_n: int = 5,
) -> List[dict]:
    """
    使用 Ollama LLM 对候选文档做相关性精排。

    参数：
        query: 用户查询
        documents: RRF 召回的候选列表，每个 dict 含 content/metadata/distance
        top_n: 返回精排后的前 N 个结果

    返回：
        精排后的 documents 列表（格式不变，distance 替换为排序得分）

    WHY: qwen3.6 已常驻 GPU，推理 ~1s 完成 30 docs 排序，
         比 CrossEncoder 快 50x，精度相当。失败时静默降级。
    """
    if not documents:
        return []

    if len(documents) <= 2:
        # WHY: 2 个以下无需排序
        return documents[:top_n]

    t0 = time.time()

    # ── 构建摘要片段 ──
    snippets = []
    import re
    for doc in documents:
        content = doc.get("content", "")
        if len(content) <= _MAX_SNIPPET_LEN:
            snippet = content.replace("\n", " ").strip()
        else:
            # WHY: 采用"首行+中间数据"的双端采样，防止表格列名过长导致数据被截断
            lines = content.split("\n")
            head = lines[0][:80] if lines else ""
            
            data_line = ""
            for l in lines[1:]:
                if re.search(r'\d', l):
                    data_line = l
                    break
            
            if data_line:
                snippet = f"{head} ... {data_line[:70]}".replace("\n", " ").strip()
            else:
                snippet = content[:_MAX_SNIPPET_LEN].replace("\n", " ").strip()
                
        if not snippet:
            snippet = "(空)"
        snippets.append(snippet)

    prompt = _build_rerank_prompt(query, snippets)

    # ── 调用 Ollama ──
    import threading
    
    result_box = []
    exc_box = []

    def _do_request():
        try:
            # WHY: 设置较长的底层超时（120s），防止主动断开连接导致 Ollama GPU 锁死
            resp = requests.post(
                f"{settings.OLLAMA_BASE_URL}/api/generate",
                json={
                    "model": _RERANK_MODEL,
                    "prompt": prompt,
                    "stream": False,
                    "options": {
                        "num_predict": 40,
                        "temperature": 0,
                        "num_ctx": 16384,
                    },
                },
                timeout=120,
            )
            resp.raise_for_status()
            result_box.append(resp.json())
        except Exception as e:
            exc_box.append(e)

    t = threading.Thread(target=_do_request)
    t.start()
    t.join(timeout=_OLLAMA_TIMEOUT)

    if t.is_alive():
        # WHY: 让线程在后台跑完，不要抛出异常中断它，以防 Ollama 断连死锁
        logger.warning(f"LLM Reranker 超时（{_OLLAMA_TIMEOUT}s），将请求置于后台继续运行，降级为 RRF 排序并扩展候选窗口")
        return documents[:top_n + 2]

    if exc_box:
        logger.warning(f"LLM Reranker 调用失败: {exc_box[0]}，降级为 RRF 排序并扩展候选窗口")
        return documents[:top_n + 2]

    data = result_box[0]
    raw_output = data.get("response", "")

    # ── 解析排序结果 ──
    ranking = _parse_ranking(raw_output, len(documents))

    if not ranking:
        logger.warning(f"LLM Reranker 输出解析失败: {raw_output[:200]}，降级")
        return documents[:top_n]

    # ── 按 LLM 排序重组文档列表 ──
    result = []
    n_docs = len(documents)
    for rank, idx in enumerate(ranking):
        if idx < n_docs:
            doc = documents[idx]
            result.append({
                "content": doc["content"],
                "metadata": doc["metadata"],
                # WHY: 用归一化排名分数替代原始 distance，
                #      排第 1 得 1.0，排最后得接近 0
                "distance": 1.0 - (rank / max(len(ranking), 1)),
            })

    # WHY: LLM 可能漏掉部分编号，将未排序的文档追加到末尾
    ranked_indices = set(ranking)
    for i, doc in enumerate(documents):
        if i not in ranked_indices:
            result.append({
                "content": doc["content"],
                "metadata": doc["metadata"],
                "distance": 0.0,
            })

    elapsed = time.time() - t0
    logger.info(
        f"🔀 LLM Reranker 完成: {len(documents)} → top {top_n}, "
        f"耗时 {elapsed:.2f}s"
    )

    return result[:top_n]
