"""
RAPTOR 多层摘要模块。

WHY: 纯向量检索在面对宏观问题（"这个项目整体情况怎样？"）时表现差，
     因为答案散布在多个 chunk 中。RAPTOR 通过递归聚类+摘要，
     生成多层级摘要 chunk，检索时同时命中细粒度原文和粗粒度摘要。
     借鉴 RAGFlow raptor.py 的实现，简化为 GMM 聚类+LLM 摘要的轻量版本。

架构：
     Layer 0: 原始 chunks (文本 + embedding)
     Layer 1: 聚类摘要 (GMM 聚类后 LLM 汇总)
     Layer 2: 更高层摘要 (如果 Layer 1 chunk 数量仍多)
     ...递归直到只剩 1 个聚类
"""
from __future__ import annotations

import logging
import re

import numpy as np
from sklearn.mixture import GaussianMixture

from core.llm_cache import get_llm_cache, set_llm_cache

logger = logging.getLogger(__name__)

# WHY: 控制摘要长度。工程文档的摘要不需要太长，300 token 足够。
MAX_SUMMARY_TOKENS = 512

RAPTOR_SUMMARY_PROMPT = """你是一个专业的文档摘要助手。
请将以下多段文本内容合并为一段简洁、连贯的中文摘要。

## 要求
- 保留关键事实、数据和实体名称
- 字数控制在 100-300 字
- 语言专业、客观
- 不编造未提供的信息

## 文本内容
{cluster_content}

请直接输出摘要，不要有任何客套话。
/no_think"""


class RaptorSummarizer:
    """
    RAPTOR 多层摘要：递归聚类 + LLM 摘要。

    输入：[(text, embedding), ...]
    输出：原始 chunks + 各层摘要 chunks + 层级边界列表
    """

    def __init__(
        self,
        max_cluster: int = 10,
        threshold: float = 0.1,
        max_layers: int = 3,
    ):
        self._max_cluster = max_cluster
        self._threshold = threshold
        self._max_layers = max_layers
        self._error_count = 0
        self._max_errors = 5

    def _get_optimal_clusters(
        self, embeddings: np.ndarray, random_state: int = 42
    ) -> int:
        """用 BIC 选择最优 GMM 聚类数。"""
        max_clusters = min(self._max_cluster, len(embeddings))
        if max_clusters <= 1:
            return 1

        n_clusters_range = np.arange(1, max_clusters)
        bics = []
        for n in n_clusters_range:
            gm = GaussianMixture(
                n_components=n, random_state=random_state
            )
            gm.fit(embeddings)
            bics.append(gm.bic(embeddings))
        return int(n_clusters_range[np.argmin(bics)])

    async def _summarize_cluster(
        self, texts: list[str], embed_fn
    ) -> tuple[str, list[float]] | None:
        """
        对一组文本调用 LLM 生成摘要，并计算摘要的 embedding。
        WHY: embed_fn 由调用方注入，保持模块解耦。
        """
        if not texts:
            return None

        # WHY: 截断过长的集群内容，防止超 token
        max_chars_per_chunk = 1000
        cluster_content = "\n---\n".join(
            t[:max_chars_per_chunk] for t in texts
        )

        prompt = RAPTOR_SUMMARY_PROMPT.format(
            cluster_content=cluster_content
        )
        model = "qwen3.6:35b-q4"

        try:
            # 先查 LLM 缓存
            cached = get_llm_cache(model, prompt)
            if cached is not None:
                summary = re.sub(
                    r'<think>.*?</think>', '', cached, flags=re.DOTALL
                ).strip()
            else:
                from core.llm_engine import stream_ollama
                import asyncio

                chunks = []
                async def _collect():
                    async for chunk in stream_ollama(
                        prompt, model=model,
                        temperature=0.3,
                        num_predict=MAX_SUMMARY_TOKENS,
                        num_ctx=8192,
                    ):
                        chunks.append(chunk)

                await asyncio.wait_for(_collect(), timeout=90)
                raw = "".join(chunks)
                set_llm_cache(model, prompt, raw)
                summary = re.sub(
                    r'<think>.*?</think>', '', raw, flags=re.DOTALL
                ).strip()

            if not summary or summary.startswith(("❌", "⚠️")):
                return None

            # 计算摘要的 embedding
            emb = await embed_fn(summary)
            if emb is None:
                return None

            return summary, emb

        except Exception as e:
            self._error_count += 1
            logger.warning(
                f"[RAPTOR] 聚类摘要失败 ({len(texts)} chunks): {e}"
            )
            if self._error_count >= self._max_errors:
                raise RuntimeError(
                    f"RAPTOR 连续 {self._error_count} 次错误，中止"
                ) from e
            return None

    async def build_layers(
        self,
        chunks: list[tuple[str, list[float]]],
        embed_fn,
        callback=None,
    ) -> tuple[list[tuple[str, list[float]]], list[tuple[int, int]]]:
        """
        构建 RAPTOR 多层摘要。

        Args:
            chunks: [(text, embedding), ...] 原始 chunk 列表
            embed_fn: async (text: str) -> list[float] 嵌入函数
            callback: 进度回调 (msg: str) -> None

        Returns:
            (extended_chunks, layers) 其中 layers = [(start, end), ...]
        """
        if len(chunks) <= 1:
            return chunks, [(0, len(chunks))]

        # WHY: 过滤掉空 embedding 的 chunk
        chunks = [
            (s, a) for s, a in chunks
            if s and a is not None and len(a) > 0
        ]
        if len(chunks) <= 1:
            return chunks, [(0, len(chunks))]

        layers = [(0, len(chunks))]
        start, end = 0, len(chunks)

        for layer_idx in range(self._max_layers):
            if end - start <= 1:
                break

            embeddings = np.array(
                [emb for _, emb in chunks[start:end]]
            )

            if len(embeddings) == 2:
                # 只有 2 个 chunk，直接合并摘要
                texts = [chunks[start][0], chunks[start + 1][0]]
                result = await self._summarize_cluster(texts, embed_fn)
                if result:
                    chunks.append(result)
                    layers.append((end, len(chunks)))
                    if callback:
                        callback(
                            msg=f"RAPTOR Layer {layer_idx+1}: "
                                f"2 chunks → 1 摘要"
                        )
                break

            # GMM 聚类
            n_clusters = self._get_optimal_clusters(embeddings)
            if n_clusters <= 1:
                # 所有 chunk 归为一类，生成一个顶层摘要
                texts = [chunks[i][0] for i in range(start, end)]
                result = await self._summarize_cluster(texts, embed_fn)
                if result:
                    chunks.append(result)
                    layers.append((end, len(chunks)))
                break

            gm = GaussianMixture(
                n_components=n_clusters, random_state=42
            )
            gm.fit(embeddings)
            probs = gm.predict_proba(embeddings)
            labels = [
                np.where(prob > self._threshold)[0]
                for prob in probs
            ]
            labels = [
                int(lbl[0]) if isinstance(lbl, np.ndarray) else int(lbl)
                for lbl in labels
            ]

            # 为每个聚类生成摘要
            produced = 0
            for c in range(n_clusters):
                cluster_indices = [
                    i + start
                    for i in range(len(labels))
                    if labels[i] == c
                ]
                if not cluster_indices:
                    continue

                texts = [chunks[i][0] for i in cluster_indices]
                result = await self._summarize_cluster(texts, embed_fn)
                if result:
                    chunks.append(result)
                    produced += 1

            if produced == 0:
                logger.warning(
                    f"[RAPTOR] Layer {layer_idx+1} 未产出摘要，终止"
                )
                break

            layers.append((end, len(chunks)))
            if callback:
                callback(
                    msg=f"RAPTOR Layer {layer_idx+1}: "
                        f"{end - start} chunks → {produced} 摘要"
                )

            logger.info(
                f"[RAPTOR] Layer {layer_idx+1} 完成: "
                f"{end - start} → {produced}"
            )
            start = end
            end = len(chunks)

        return chunks, layers
