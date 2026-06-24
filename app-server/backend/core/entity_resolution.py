"""
图谱实体消歧模块（Entity Resolution）。

WHY: 工程文档中同一实体常以多种形式出现（"幸福水库"/"幸福水库工程"/"幸福水库项目"），
     图谱提取后会生成多个独立节点，导致图谱碎片化、社区摘要质量下降。
     借鉴 RAGFlow 的实体消歧流程：
     1. 按 entity_type 分组 → 编辑距离+字符集重叠预筛候选对
     2. LLM 批量确认 → Neo4j MERGE 合并节点
"""
from __future__ import annotations

import itertools
import logging
import re

import editdistance
from neo4j import GraphDatabase

from core.config import settings
from core.llm_cache import get_llm_cache, set_llm_cache

logger = logging.getLogger(__name__)

# WHY: 每批判断 10 对，控制单次 LLM 调用的 prompt 长度
BATCH_SIZE = 10

RESOLUTION_PROMPT = """你是一个实体消歧专家。判断以下每组中的两个名称是否指代同一个实体。

## 判断规则
- 一个是另一个的简称/全称/别名 → 是同一实体
- 仅有"工程""项目""建设"等后缀差异 → 是同一实体
- 核心名词不同（如"幸福水库"vs"和平水库"） → 不是同一实体
- 包含不同数字（如"表2-1"vs"表2-2"） → 不是同一实体

## 待判断的实体对
{pairs_text}

## 输出格式（每行一个判断）
Q1: YES 或 NO
Q2: YES 或 NO
...

直接输出判断，不解释理由。
/no_think"""


def _has_digit_in_2gram_diff(a: str, b: str) -> bool:
    """
    检查两个字符串的 2-gram 差集中是否包含数字。
    WHY: 防止 "表2-1" 和 "表2-2" 被判为同一实体。
    """
    def to_2gram_set(s):
        return {s[i:i+2] for i in range(len(s) - 1)}
    diff = to_2gram_set(a) ^ to_2gram_set(b)
    return any(any(c.isdigit() for c in pair) for pair in diff)


def is_candidate_pair(a: str, b: str) -> bool:
    """
    判断两个实体名是否值得发给 LLM 做消歧确认。
    WHY: 预筛选降低 LLM 调用次数。只有编辑距离足够近或字符集高度重叠的才送审。
    借鉴 RAGFlow entity_resolution.py 的 is_similarity() 逻辑。
    """
    if a == b:
        return False
    if _has_digit_in_2gram_diff(a, b):
        return False

    # WHY: 一个实体名完全包含另一个时（如"幸福水库"⊆"幸福水库工程"），
    #      几乎必然是同一实体的不同表述，直接判为候选对。
    shorter, longer = (a, b) if len(a) <= len(b) else (b, a)
    if shorter in longer and len(shorter) >= 2:
        return True

    # WHY: 判断是否为英文（简单启发式）
    a_is_en = all(ord(c) < 256 for c in a.replace(" ", ""))
    b_is_en = all(ord(c) < 256 for c in b.replace(" ", ""))

    if a_is_en and b_is_en:
        # 英文：编辑距离 ≤ 较短者长度的一半
        return editdistance.eval(a.lower(), b.lower()) <= min(len(a), len(b)) // 2

    # 中文：字符集重叠度 ≥ 0.8
    set_a, set_b = set(a), set(b)
    max_l = max(len(set_a), len(set_b))
    if max_l < 4:
        return len(set_a & set_b) > 1
    return len(set_a & set_b) / max_l >= 0.8


class EntityResolver:
    """图谱实体消歧：合并同一实体的不同表述。"""

    def __init__(self):
        self._driver = None

    def _connect(self):
        if not self._driver:
            self._driver = GraphDatabase.driver(
                settings.NEO4J_URI,
                auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD)
            )

    def _close(self):
        if self._driver:
            self._driver.close()
            self._driver = None

    async def resolve(self, project_id: str) -> dict:
        """
        执行完整的实体消歧流程。
        返回: {"candidates": N, "confirmed": M, "merged": K}
        """
        try:
            self._connect()
            # Phase 1: 拉取实体并按类型分组
            entities_by_type = self._fetch_entities_by_type(project_id)
            total_entities = sum(len(v) for v in entities_by_type.values())
            if total_entities < 2:
                return {"candidates": 0, "confirmed": 0, "merged": 0}

            # Phase 2: 预筛选候选合并对
            candidates = self._find_all_candidates(entities_by_type)
            logger.info(
                f"🔗 实体消歧: {total_entities} 个实体, "
                f"{len(candidates)} 个候选对 (project={project_id})"
            )
            if not candidates:
                return {"candidates": 0, "confirmed": 0, "merged": 0}

            # Phase 3: LLM 批量确认
            confirmed = await self._llm_confirm_batched(candidates)
            logger.info(f"🔗 LLM 确认 {len(confirmed)} 对需要合并")

            # Phase 4: Neo4j 合并
            merged = self._merge_confirmed_pairs(project_id, confirmed)

            result = {
                "candidates": len(candidates),
                "confirmed": len(confirmed),
                "merged": merged,
            }
            logger.info(f"🔗 实体消歧完成: {result}")
            return result
        except Exception as e:
            logger.error(f"实体消歧异常: {e}")
            return {"candidates": 0, "confirmed": 0, "merged": 0, "error": str(e)}
        finally:
            self._close()

    def _fetch_entities_by_type(self, project_id: str) -> dict[str, list[str]]:
        """从 Neo4j 拉取所有实体名，按 type 分组。"""
        cypher = """
        MATCH (e:Entity {project_id: $pid})
        RETURN e.name AS name, coalesce(e.type, '未知') AS type
        """
        result: dict[str, list[str]] = {}
        with self._driver.session() as s:
            for record in s.run(cypher, pid=project_id):
                etype = record["type"]
                result.setdefault(etype, []).append(record["name"])
        return result

    def _find_all_candidates(
        self, entities_by_type: dict[str, list[str]]
    ) -> list[tuple[str, str]]:
        """对每组同类型实体，预筛选候选合并对。"""
        candidates = []
        for etype, names in entities_by_type.items():
            if len(names) < 2:
                continue
            # WHY: 只对同类型实体做比较，跨类型不消歧
            for a, b in itertools.combinations(sorted(names), 2):
                if is_candidate_pair(a, b):
                    candidates.append((a, b))
        return candidates

    async def _llm_confirm_batched(
        self, candidates: list[tuple[str, str]]
    ) -> list[tuple[str, str]]:
        """将候选对分批发给 LLM 确认，返回确认为同一实体的对。"""
        confirmed = []
        for i in range(0, len(candidates), BATCH_SIZE):
            batch = candidates[i:i + BATCH_SIZE]
            batch_confirmed = await self._llm_confirm_batch(batch)
            confirmed.extend(batch_confirmed)
        return confirmed

    async def _llm_confirm_batch(
        self, batch: list[tuple[str, str]]
    ) -> list[tuple[str, str]]:
        """单批次 LLM 确认。"""
        pairs_text = "\n".join(
            f"Q{i+1}: 「{a}」 vs 「{b}」"
            for i, (a, b) in enumerate(batch)
        )
        prompt = RESOLUTION_PROMPT.format(pairs_text=pairs_text)
        model = "qwen3.6:35b-q4"

        # WHY: 相同候选对组合会产生相同 prompt，重试时命中缓存
        cached = get_llm_cache(model, prompt)
        if cached is not None:
            return self._parse_confirmation(batch, cached)

        try:
            from core.llm_engine import stream_ollama
            import asyncio

            chunks = []
            async def _collect():
                async for chunk in stream_ollama(
                    prompt, model=model,
                    temperature=0, num_predict=256, num_ctx=8192,
                ):
                    chunks.append(chunk)

            await asyncio.wait_for(_collect(), timeout=60)
            raw = "".join(chunks)
            set_llm_cache(model, prompt, raw)
            return self._parse_confirmation(batch, raw)
        except Exception as e:
            logger.warning(f"实体消歧 LLM 确认失败: {e}")
            return []

    def _parse_confirmation(
        self, batch: list[tuple[str, str]], raw: str
    ) -> list[tuple[str, str]]:
        """解析 LLM 输出，提取确认为 YES 的对。"""
        # 清除 <think> 标签
        text = re.sub(r'<think>.*?</think>', '', raw, flags=re.DOTALL)
        confirmed = []
        for i, (a, b) in enumerate(batch):
            # 查找 Q{i+1}: YES/NO
            pattern = rf'Q{i+1}\s*[:：]\s*(YES|NO|yes|no|Yes|No)'
            m = re.search(pattern, text)
            if m and m.group(1).upper() == "YES":
                confirmed.append((a, b))
        return confirmed

    def _merge_confirmed_pairs(
        self, project_id: str, pairs: list[tuple[str, str]]
    ) -> int:
        """
        在 Neo4j 中合并确认的实体对。
        策略：保留名字较短的（通常是标准名称），合并关系到保留节点。
        """
        if not pairs:
            return 0

        merged_count = 0
        with self._driver.session() as s:
            for keep, remove in pairs:
                # WHY: 保留较短名字（通常是标准简称），较长的是带后缀的变体
                if len(keep) > len(remove):
                    keep, remove = remove, keep

                try:
                    # Step 1: 将 remove 节点的所有出边迁移到 keep
                    s.run("""
                        MATCH (remove:Entity {name: $remove, project_id: $pid})
                              -[r:RELATES_TO]->(target:Entity)
                        MATCH (keep:Entity {name: $keep, project_id: $pid})
                        WHERE NOT (keep)-[:RELATES_TO {type: r.type}]->(target)
                        CREATE (keep)-[nr:RELATES_TO]->(target)
                        SET nr = properties(r)
                    """, keep=keep, remove=remove, pid=project_id)

                    # Step 2: 将 remove 节点的所有入边迁移到 keep
                    s.run("""
                        MATCH (source:Entity)-[r:RELATES_TO]->
                              (remove:Entity {name: $remove, project_id: $pid})
                        MATCH (keep:Entity {name: $keep, project_id: $pid})
                        WHERE NOT (source)-[:RELATES_TO {type: r.type}]->(keep)
                        CREATE (source)-[nr:RELATES_TO]->(keep)
                        SET nr = properties(r)
                    """, keep=keep, remove=remove, pid=project_id)

                    # Step 3: 合并 file_ids
                    s.run("""
                        MATCH (keep:Entity {name: $keep, project_id: $pid})
                        MATCH (remove:Entity {name: $remove, project_id: $pid})
                        SET keep.file_ids = coalesce(keep.file_ids, [])
                            + coalesce(remove.file_ids, [])
                        SET keep.aliases = coalesce(keep.aliases, []) + [$remove]
                    """, keep=keep, remove=remove, pid=project_id)

                    # Step 4: 删除 remove 节点
                    s.run("""
                        MATCH (remove:Entity {name: $remove, project_id: $pid})
                        DETACH DELETE remove
                    """, remove=remove, pid=project_id)

                    merged_count += 1
                    logger.info(f"🔗 合并实体: 「{remove}」→「{keep}」")
                except Exception as e:
                    logger.warning(f"合并实体 {remove}→{keep} 失败: {e}")

        return merged_count
