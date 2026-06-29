"""
GraphRAG 知识图谱引擎。

WHY: 纯向量检索在高度逻辑耦合的工程条文查询中存在"孤立瓶颈"——
     相关实体散落在不同 chunk 中，语义相似度无法捕捉逻辑跳跃关系。
     通过 NER 将文档中的实体和关系提取为三元组存入 Neo4j，
     查询时可通过图谱扩散找到隐藏的上下游关联。
"""
from __future__ import annotations

import json
import logging
import os
import re

from neo4j import GraphDatabase

from core.config import settings

logger = logging.getLogger(__name__)

# ── LLM 三元组抽取 Prompt ──
# WHY: 工程文档中实体关系密度高（设备→参数→工序→标准），
#      用结构化 JSON 输出确保可靠解析。
EXTRACT_PROMPT = """你是一个精准的知识图谱实体关系抽取工具。

## 任务
从下方文本中提取所有有意义的实体和它们之间的关系。

## 文本
{text}

## 输出格式（严格 JSON，不要输出任何其他内容）
```json
{{"triples": [
  {{"subject": "实体A", "relation": "关系描述", "object": "实体B", "s_type": "类型", "o_type": "类型"}}
]}}
```

## 实体类型
地名、机构、工程、设备、参数、标准、材料、工序、时间、人物、法规

## 抽取规则
1. 每个三元组必须包含 subject、relation、object
2. relation 用简短动词短语（属于、位于、要求、包含、执行、依据等）
3. 忽略过于宽泛的关系（如"相关"）
4. 最多抽取 30 个三元组
5. 仅输出 JSON，不要解释

/no_think"""


def _parse_triples(raw: str) -> list[dict]:
    """从 LLM 输出中解析三元组 JSON。"""
    # 清除 <think> 标签
    text = re.sub(r'<think>.*?</think>', '', raw, flags=re.DOTALL)

    # WHY: 抛弃低效的正则表达式，改用首尾定位器截取 JSON。
    #      大模型返回的长异常文本配上 .* 正则在匹配失败时极易引发
    #      Python 正则引擎的灾难性回溯，把 CPU 100% 跑满卡死。
    #      使用 string.find/rfind 保证 O(N) 复杂度，绝对不卡死。
    start = text.find('{')
    end = text.rfind('}')
    if start != -1 and end != -1 and end > start:
        text = text[start:end+1]
    else:
        # 支持直接返回数组的情况
        start = text.find('[')
        end = text.rfind(']')
        if start != -1 and end != -1 and end > start:
            text = f'{{"triples": {text[start:end+1]}}}'

    try:
        data = json.loads(text)
        triples = data.get("triples", [])
        valid = []
        for t in triples:
            if (isinstance(t, dict)
                    and t.get("subject", "").strip()
                    and t.get("relation", "").strip()
                    and t.get("object", "").strip()):
                valid.append({
                    "subject": t["subject"].strip(),
                    "relation": t["relation"].strip(),
                    "object": t["object"].strip(),
                    "s_type": t.get("s_type", "未知").strip(),
                    "o_type": t.get("o_type", "未知").strip(),
                })
        return valid
    except (json.JSONDecodeError, AttributeError) as e:
        logger.warning(f"三元组 JSON 解析失败: {e}")
        return []


class GraphRAGEngine:
    """
    基于 Neo4j 的图谱 RAG 引擎。
    WHY: 通过实体识别将文档中的设备、参数、施工环节提取为
         三元组存入图谱，查询时进行逻辑扩散检索。
    """

    def __init__(self):
        self._driver = None
        self._connected = False
        self._entity_cache: dict | None = None  # name → BGE-M3 embedding
        self._building_projects = set()

    def _build_entity_cache(self, project_id: str = ""):
        """
        从 Neo4j 拉取所有实体名，用 BGE-M3 编码后缓存（后台线程版本）。
        WHY: 语义实体检索需要 BGE-M3 向量做 cosine 相似度匹配。
             在后台线程构建，避免阻塞 Uvicorn 异步事件循环导致服务假死，
             未构建完成前降级使用 Lexical/Keyword 检索。
        """
        if self._entity_cache is not None:
            return
        if project_id in self._building_projects:
            return

        self._building_projects.add(project_id)

        def _bg_build():
            try:
                if not self._ensure_connection():
                    return

                import numpy as np
                from core.vector_store import _get_dense_model

                with self._driver.session() as s:
                    cypher = "MATCH (e:Entity) RETURN DISTINCT e.name AS name"
                    if project_id:
                        cypher = (
                            "MATCH (e:Entity) "
                            "WHERE e.project_id = $pid "
                            "RETURN DISTINCT e.name AS name"
                        )
                    result = s.run(cypher, pid=project_id) if project_id else s.run(cypher)
                    names = [r["name"] for r in result if r["name"]]

                if not names:
                    self._entity_cache = {}
                    return

                logger.info(f"🕸️ [GraphRAG] 开始在后台线程构建实体缓存: {len(names)} 个实体...")
                # WHY: 限制缓存容量防止内存失控（1024维 × 4字节 × 10000 ≈ 40MB）
                _MAX_ENTITY_CACHE = 10000
                if len(names) > _MAX_ENTITY_CACHE:
                    logger.warning(
                        f"实体数量 {len(names)} 超出缓存上限 {_MAX_ENTITY_CACHE}，"
                        f"按字母序截断"
                    )
                    names = sorted(names)[:_MAX_ENTITY_CACHE]
                model = _get_dense_model()
                embeddings = model.encode(
                    names, normalize_embeddings=True,
                    show_progress_bar=False, batch_size=32,
                )
                self._entity_cache = {
                    name: embeddings[i]
                    for i, name in enumerate(names)
                }
                logger.info(f"🕸️ [GraphRAG] ✅ 实体缓存后台构建完成: {len(names)} 个实体")
            except Exception as e:
                logger.error(f"🕸️ [GraphRAG] ❌ 实体缓存后台构建失败: {e}")
                self._entity_cache = {}
            finally:
                self._building_projects.discard(project_id)

        import threading
        t = threading.Thread(target=_bg_build, daemon=True)
        t.start()

    def _semantic_entity_search(
        self, query: str, top_k: int = 10
    ) -> list[str]:
        """
        用 BGE-M3 对 query 做语义编码，匹配缓存中最相似的实体名。
        WHY: 替代 CONTAINS 模糊匹配。用户问"灌溉用水标准"能命中
             实体"灌溉定额"，即使它们没有共同子串。
        返回：[entity_name, ...] 按相似度降序排列。
        """
        if not self._entity_cache:
            return []

        try:
            import numpy as np
            from core.vector_store import _get_dense_model

            model = _get_dense_model()
            query_vec = model.encode(
                [query], normalize_embeddings=True,
                show_progress_bar=False,
            )[0]

            names = list(self._entity_cache.keys())
            emb_matrix = np.stack([self._entity_cache[n] for n in names])
            sims = np.dot(emb_matrix, query_vec)

            # 取相似度 > 0.5 的 Top-K
            threshold = 0.5
            ranked = sorted(
                [(names[i], sims[i]) for i in range(len(names))
                 if sims[i] > threshold],
                key=lambda x: -x[1],
            )[:top_k]

            if ranked:
                logger.info(
                    f"🕸️ [GraphRAG] 语义匹配: "
                    f"{', '.join(n for n, _ in ranked[:5])}"
                )
            return [name for name, _ in ranked]
        except Exception as e:
            logger.warning(f"🕸️ [GraphRAG] 语义实体检索失败: {e}")
            return []

    def _ensure_connection(self):
        """惰性连接 Neo4j（首次调用时建立）。"""
        if self._connected and self._driver:
            return True
        try:
            logger.info("🕸️ [GraphRAG] 正在建立 Neo4j 连接...")
            self._driver = GraphDatabase.driver(
                settings.NEO4J_URI,
                auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD),
                connection_timeout=5,
                max_transaction_retry_time=3,
            )
            self._driver.verify_connectivity()
            self._connected = True
            logger.info(f"🕸️ [GraphRAG] ✅ Neo4j 连接成功: {settings.NEO4J_URI}")
            # 创建索引（幂等）
            self._create_indexes()
            return True
        except Exception as e:
            logger.error(f"🕸️ [GraphRAG] ❌ Neo4j 连接失败: {e}")
            self._connected = False
            return False

    def _create_indexes(self):
        """创建必要的索引以加速查询。"""
        try:
            with self._driver.session() as s:
                s.run(
                    "CREATE INDEX IF NOT EXISTS "
                    "FOR (e:Entity) ON (e.name)"
                )
                s.run(
                    "CREATE INDEX IF NOT EXISTS "
                    "FOR (e:Entity) ON (e.project_id)"
                )
            logger.info("Neo4j 索引已就绪")
        except Exception as e:
            logger.warning(f"Neo4j 索引创建失败: {e}")

    async def extract_entities_and_relationships(
        self, text_chunk: str
    ) -> list[dict]:
        """
        调用 Ollama LLM 从文本切片中抽取实体和关系三元组（异步版本）。
        WHY: 必须为 async，避免在 Celery async 上下文中嵌套创建事件循环。
        返回: [{"subject": ..., "relation": ..., "object": ...}, ...]
        """
        if len(text_chunk) < 50:
            return []

        import asyncio
        from core.llm_engine import stream_ollama
        from core.llm_cache import get_llm_cache, set_llm_cache

        model = "qwen3.6:35b-q4"
        prompt = EXTRACT_PROMPT.format(
            text=text_chunk[:2000]
        )

        # WHY: 图谱提取是非流式场景，相同 chunk 重试时命中缓存可跳过 GPU
        cached = get_llm_cache(model, prompt)
        if cached is not None:
            triples = _parse_triples(cached)
            if triples:
                logger.debug(f"🕸️ 缓存命中，抽取到 {len(triples)} 个三元组")
            return triples

        chunks: list[str] = []

        async def _collect():
            async for chunk in stream_ollama(
                prompt,
                model=model,
                temperature=0,
                num_predict=1536,
                num_ctx=16384,
            ):
                chunks.append(chunk)

        try:
            # WHY: 300 秒硬超时保护。并发场景下 GPU 信号量等待可能消耗 60-120 秒，
            #      加上 35B 模型推理 10-60 秒，120 秒远远不够。
            #      300 秒足以覆盖信号量排队 + 推理的最坏情况。
            await asyncio.wait_for(_collect(), timeout=300)
            raw = "".join(chunks)
            # WHY: 成功的 LLM 输出写入缓存，断点续传重试时直接命中
            set_llm_cache(model, prompt, raw)
            triples = _parse_triples(raw)
            if triples:
                logger.debug(
                    f"🕸️ 抽取到 {len(triples)} 个三元组"
                )
            return triples
        except asyncio.TimeoutError:
            logger.warning(
                f"三元组抽取超时 (300s)，跳过当前切片 "
                f"(text_len={len(text_chunk)})"
            )
            return []
        except Exception as e:
            logger.error(f"三元组抽取异常: {type(e).__name__}: {e}")
            return []

    def ingest_to_graph(
        self,
        triples: list[dict],
        project_id: str = "",
        file_id: str = "",
    ):
        """将提取的三元组写入 Neo4j 图数据库。"""
        if not triples:
            return
        if not self._ensure_connection():
            logger.warning(
                "Neo4j 未连接，跳过图谱入库"
            )
            return

        # WHY: 使用 MERGE 保证幂等——相同实体不会重复创建。
        #      添加 file_ids 数组追踪实体来源文件，方便清理。
        cypher = """
        UNWIND $triples AS t
        MERGE (s:Entity {name: t.subject, project_id: $pid})
        ON CREATE SET s.type = t.s_type
        MERGE (o:Entity {name: t.object, project_id: $pid})
        ON CREATE SET o.type = t.o_type
        WITH s, o, t, $fid AS fid
        SET s.file_ids = CASE WHEN NOT fid IN coalesce(s.file_ids, []) THEN coalesce(s.file_ids, []) + [fid] ELSE coalesce(s.file_ids, []) END
        SET o.file_ids = CASE WHEN NOT fid IN coalesce(o.file_ids, []) THEN coalesce(o.file_ids, []) + [fid] ELSE coalesce(o.file_ids, []) END
        MERGE (s)-[r:RELATES_TO {type: t.relation}]->(o)
        ON CREATE SET r.file_id = fid
        """
        try:
            with self._driver.session() as s:
                s.run(
                    cypher,
                    triples=triples,
                    pid=project_id,
                    fid=file_id,
                )
            logger.info(
                f"🕸️ 图谱入库完成: {len(triples)} 个三元组 "
                f"(project={project_id})"
            )
            # WHY: 新三元组入库后，旧的实体缓存不再完整，
            #      置空后下次 hybrid_search 时会自动重建。
            self._entity_cache = None
        except Exception as e:
            logger.error(f"图谱入库失败: {e}")

    def delete_by_project_id(self, project_id: str):
        """删除图谱中属于指定 project_id 的所有节点和关系"""
        if not self._ensure_connection():
            logger.warning("Neo4j 未连接，跳过图谱删除")
            return
        try:
            with self._driver.session() as s:
                res = s.run("MATCH (n {project_id: $pid}) DETACH DELETE n", pid=project_id)
                summary = res.consume()
                nodes_deleted = summary.counters.nodes_deleted
                rels_deleted = summary.counters.relationships_deleted
                logger.info(f"🗑️ 图谱清理完成: 删除 {nodes_deleted} 节点, {rels_deleted} 关系 (project={project_id})")
                self._entity_cache = None
        except Exception as e:
            logger.error(f"删除图谱 project_id={project_id} 失败: {e}")

    def delete_by_file_id(self, file_id: str, project_id: str = ""):
        """
        删除图谱中指定 file_id 来源的所有关系，并清理孤立节点。
        WHY: 支持单文件增量重建——重新处理文件时先清除旧三元组，
             避免同一文件多次入库导致数据堆积重复。
        """
        if not self._ensure_connection():
            logger.warning("Neo4j 未连接，跳过按 file_id 删除")
            return 0
        try:
            with self._driver.session() as s:
                # 第 1 步：删除该 file_id 来源的所有 RELATES_TO 关系
                res = s.run(
                    "MATCH ()-[r:RELATES_TO {file_id: $fid}]-() DELETE r",
                    fid=file_id,
                )
                rels_deleted = res.consume().counters.relationships_deleted

                # 第 2 步：删除属于该 file_id 的所有 EvidenceUnit 节点
                res2 = s.run(
                    "MATCH (eu:EvidenceUnit {file_id: $fid}) DETACH DELETE eu",
                    fid=file_id,
                )
                eu_deleted = res2.consume().counters.nodes_deleted

                # 第 3 步：如果对应的 Document 没有其他关系，删除 Document 节点
                res3 = s.run(
                    "MATCH (d:Document {id: $fid}) WHERE NOT (d)--() DELETE d",
                    fid=file_id,
                )
                doc_deleted = res3.consume().counters.nodes_deleted

                # 第 4 步：清理孤立节点（无任何关系的实体 Entity）
                nodes_deleted = 0
                if project_id:
                    res4 = s.run(
                        "MATCH (e:Entity {project_id: $pid}) "
                        "WHERE NOT (e)--() DELETE e",
                        pid=project_id,
                    )
                    nodes_deleted = res4.consume().counters.nodes_deleted

                # 第 5 步：清理孤立的 FormField 节点
                ff_deleted = 0
                if project_id:
                    res5 = s.run(
                        "MATCH (ff:FormField {project_id: $pid}) "
                        "WHERE NOT (ff)--() DELETE ff",
                        pid=project_id,
                    )
                    ff_deleted = res5.consume().counters.nodes_deleted

            logger.info(
                f"🗑️ 图谱增量清理: file_id={file_id}, "
                f"删除 {rels_deleted} RELATES_TO 关系, {eu_deleted} EvidenceUnit 节点, "
                f"{doc_deleted} Document 节点, {nodes_deleted} 孤立 Entity 节点, {ff_deleted} 孤立 FormField"
            )
            self._entity_cache = None
            return rels_deleted
        except Exception as e:
            logger.error(f"按 file_id 删除图谱失败: {e}")
            return 0

    async def _rerank_graph_paths(
        self,
        query: str,
        paths: list[str],
        top_n: int = 10,
    ) -> list[str]:
        """
        用 LLM 对图谱路径做相关性精排（异步版本，避免调用 asyncio.run 死锁/挂起）。
        WHY: 高噪声场景下原始 CONTAINS/语义匹配可能返回
             大量无关路径（设备 A→参数 B→标准 C 但与灌溉无关）。
             用 qwen3.6:35b-q4 判断每条路径与查询的相关性再排序。
        返回：按相关性降序排列的路径列表。
        """
        if not paths or len(paths) <= 1:
            return paths

        # 只对候选集做精排，控制 cost
        candidates = paths[: min(len(paths), 20)]
        if len(candidates) <= 3:
            return candidates[:top_n]

        numbered = "\n".join(
            f"[{i+1}] {p}" for i, p in enumerate(candidates)
        )

        prompt = f"""分析以下知识图谱路径与用户问题的相关性，输出按相关性从高到低排序的路径编号。

用户问题：
{query}

图谱路径：
{numbered}

只输出排序后的编号（逗号分隔），如：3,7,1,5,2,...
不在排序中的路径将被丢弃。
/no_think"""

        try:
            from core.llm_engine import stream_ollama
            from core.llm_cache import get_llm_cache, set_llm_cache

            model = "qwen3.6:35b-q4"
            # WHY: 路径精排的 prompt 包含固定候选列表，相同查询+相同路径会命中缓存
            cached = get_llm_cache(model, prompt)
            if cached is not None:
                raw = cached
            else:
                async def _collect_rerank():
                    raw = ""
                    async for chunk in stream_ollama(
                        prompt,
                        model=model,
                        temperature=0,
                        num_predict=256,
                        num_ctx=16384,
                    ):
                        raw += chunk
                    return raw

                raw = await _collect_rerank()
                set_llm_cache(model, prompt, raw)

            # 解析编号序列
            import re as _re
            nums = _re.findall(r'\d+', raw)
            order = [int(n) - 1 for n in nums
                     if 1 <= int(n) <= len(candidates)]
            # 去重保序
            seen = set()
            order = [i for i in order if not (i in seen or seen.add(i))]

            if order:
                ranked = [candidates[i] for i in order][:top_n]
                logger.info(
                    f"🕸️ [GraphRAG] ✅ 图谱路径精排完成: "
                    f"{len(ranked)} 条返回"
                )
            else:
                ranked = candidates[:top_n]
        except Exception as e:
            logger.warning(
                f"🕸️ [GraphRAG] 图谱路径精排失败(降级原始顺序): {e}"
            )
            ranked = candidates[:top_n]

        return ranked

    async def hybrid_search(
        self,
        user_query: str,
        project_id: str = "",
        max_paths: int = 10,
    ) -> dict:
        """
        混合检索（异步版本）：从 Neo4j 中查找与查询关键词相关的实体路径。
        WHY: 先从 query 中提取关键词，在图谱中模糊匹配实体，
             然后沿关系扩散 1-2 跳，返回相关的实体网络路径。
        """
        if not self._ensure_connection():
            return {"graph_context": "", "paths": []}

        # WHY: 先用 BGE-M3 语义检索匹配实体名，
        #      替代纯 CONTAINS 字符串匹配。
        #      语义匹配失败时降级为原始分词 + CONTAINS。
        #      构建缓存过程被放到了后台线程，绝对不阻塞主线程。
        self._build_entity_cache(project_id)
        semantic_entities = self._semantic_entity_search(
            user_query, top_k=10
        )

        if semantic_entities:
            # 语义检索成功：用精准实体名做节点匹配
            # WHY: 扩展到 3 跳（N-Hop），发现隐式关联。
            #      借鉴 RAGFlow search.py 的 n_hop_with_weight 路径扩展。
            cypher = """
            UNWIND $entities AS ename
            MATCH (e:Entity {name: ename})
            WHERE (e.project_id = $pid OR e.project_id IS NULL)
            OPTIONAL MATCH path = (e)-[:RELATES_TO*1..3]-(neighbor:Entity)
            WHERE neighbor.project_id = $pid OR neighbor.project_id IS NULL
            OPTIONAL MATCH (c:Community)-[:CONTAINS]->(e)
            WITH e, path, neighbor, c,
                 [r IN relationships(path) | r.type] AS rel_types,
                 [n IN nodes(path) | n.name] AS path_nodes
            RETURN e.name AS entity, e.type AS entity_type,
                   rel_types,
                   path_nodes,
                   neighbor.name AS neighbor_name,
                   neighbor.type AS neighbor_type,
                   length(path) AS distance,
                   c.summary AS community_summary,
                   coalesce(e.pagerank, 0) AS pagerank
            ORDER BY pagerank DESC, distance ASC
            LIMIT $limit
            """
            cypher_params = {
                "entities": semantic_entities,
                "pid": project_id,
                "limit": max_paths * 5,  # 3-hop 可能返回更多路径
            }
        else:
            # 降级：原始分词 + CONTAINS
            keywords = [
                w for w in re.split(r'[，,。？！\s]+', user_query)
                if len(w) >= 2
            ]
            if not keywords:
                return {"graph_context": "", "paths": []}
            cypher = """
            UNWIND $keywords AS kw
            MATCH (e:Entity)
            WHERE (e.project_id = $pid OR e.project_id IS NULL)
                  AND e.name CONTAINS kw
            OPTIONAL MATCH path = (e)-[:RELATES_TO*1..2]-(neighbor:Entity)
            WHERE neighbor.project_id = $pid OR neighbor.project_id IS NULL
            OPTIONAL MATCH (c:Community)-[:CONTAINS]->(e)
            UNWIND relationships(path) AS rel
            RETURN e.name AS entity, e.type AS entity_type,
                   type(rel) AS relation,
                   neighbor.name AS neighbor_name,
                   neighbor.type AS neighbor_type,
                   length(path) AS distance,
                   c.summary AS community_summary
            LIMIT $limit
            """
            cypher_params = {
                "keywords": keywords,
                "pid": project_id,
                "limit": max_paths,
            }

        try:
            logger.info(
                f"🕸️ [GraphRAG] hybrid_search 开始 "
                f"| mode={'semantic' if semantic_entities else 'keyword'} "
                f"| pid={project_id}"
            )
            with self._driver.session() as s:
                result = s.run(
                    cypher,
                    **cypher_params,
                )
                paths = []
                summaries = set()
                for record in result:
                    # WHY: 多跳路径格式化——展示完整的 A→B→C 路径，
                    #      而非只显示起点和终点，帮助 LLM 理解隐式关联。
                    path_nodes = record.get("path_nodes") or []
                    rel_types = record.get("rel_types") or []
                    if path_nodes and len(path_nodes) > 1 and rel_types:
                        # 组装多跳路径: 实体A（关系1）实体B（关系2）实体C
                        parts = [path_nodes[0]]
                        for j, rel_type in enumerate(rel_types):
                            if j + 1 < len(path_nodes):
                                parts.append(f"（{rel_type}）{path_nodes[j+1]}")
                        path_str = "".join(parts)
                    else:
                        path_str = record["entity"]
                        if record.get("neighbor_name"):
                            path_str += f"（关联）{record['neighbor_name']}"

                    paths.append(path_str)
                    if record.get("community_summary"):
                        summaries.add(record["community_summary"])

            # 去重
            paths = list(dict.fromkeys(paths))

            # WHY: 图谱路径 LLM 精排。高噪声场景下
            #      （如 CONTAINS 匹配了大量无关实体），
            #      用 qwen3.6:35b-q4 按与 query 相关性排序。
            if len(paths) > 3:
                paths = await self._rerank_graph_paths(
                    user_query, paths, top_n=max_paths
                )

            graph_context = ""
            if paths:
                # WHY: 添加"仅供参考"警告，防止 LLM 将图谱信息原样输出到正文
                graph_context = (
                    "【补充关联信息（仅供写作参考，严禁将本节内容原样输出到正文中）】\n"
                    + "\n".join(
                        f"- {p}" for p in paths[:max_paths]
                    )
                )
                if summaries:
                    graph_context += "\n\n【背景摘要（仅供参考，严禁原样输出）】\n" + "\n".join(f"- {s}" for s in list(summaries)[:3])
                logger.info(f"🕸️ [GraphRAG] ✅ 命中 {len(paths)} 条路径, {len(summaries)} 个社区摘要")
            else:
                logger.debug("🕸️ [GraphRAG] 未命中任何路径")

            return {
                "graph_context": graph_context,
                "paths": paths,
            }
        except Exception as e:
            logger.error(f"🕸️ [GraphRAG] ❌ 检索失败: {e}")
            return {"graph_context": "", "paths": []}

    def ingest_doco_and_form_relations(
        self,
        filename: str,
        project_id: str,
        file_id: str,
        chunks_payloads: list[dict]
    ):
        """
        增量写入 DoCO 树节点（第一层：Document -> EvidenceUnit）
        与表单字段-凭证拓扑关系（第二层：FormField -> EvidenceUnit）
        """
        if not chunks_payloads:
            return
        if not self._ensure_connection():
            logger.warning("Neo4j 未连接，跳过 DoCO 与表单字段入库")
            return

        evidence_units = []
        form_field_relations = []
        
        for payload in chunks_payloads:
            text = payload.get("document", "")
            chunk_index = payload.get("chunk_index", 0)
            page_number = payload.get("page_number", 0)
            semantic_role = payload.get("semantic_role", "text_block")
            
            chunk_id = f"{file_id}_{chunk_index}"
            
            evidence_units.append({
                "id": chunk_id,
                "text": text,
                "chunk_index": chunk_index,
                "page_number": page_number,
                "semantic_role": semantic_role
            })
            
            # 检测 FormField 关联
            fields = []
            # 信用代码
            if re.search(r'\b[0-9A-HJ-NP-RT-UW-XY]{18}\b', text) or re.search(r'信用代码|统一社会信用代码', text):
                fields.append("credit_code")
            # 企业名称
            if any(kw in text for kw in ["有限责任公司", "有限公司", "商行", "合作社", "经营部", "制品厂", "当事人", "被处罚人"]):
                fields.append("company_name")
            # 处罚类型
            if any(kw in text for kw in ["罚款", "警告", "暂扣", "吊销"]):
                fields.append("penalty_type")
            # 罚款金额
            if any(kw in text for kw in ["罚款", "元", "万元"]):
                fields.append("fine_amount_yuan")
            # 法律依据
            if any(kw in text for kw in ["依据", "根据", "违反", "触犯", "条", "款", "项", "法规"]):
                fields.append("legal_basis")
                
            for field in fields:
                form_field_relations.append({
                    "field_name": field,
                    "chunk_id": chunk_id
                })

        cypher = """
        // 1. 创建/更新 Document 节点
        MERGE (d:Document {id: $fid, project_id: $pid})
        ON CREATE SET d.name = $filename
        ON MATCH SET d.name = $filename
        
        // 2. 批量创建 EvidenceUnit 节点并建立 HAS_ELEMENT 关系
        WITH d
        UNWIND $units AS u
        MERGE (eu:EvidenceUnit {id: u.id, project_id: $pid})
        SET eu.text = u.text,
            eu.chunk_index = u.chunk_index,
            eu.page_number = u.page_number,
            eu.semantic_role = u.semantic_role,
            eu.file_id = $fid
        MERGE (d)-[:HAS_ELEMENT]->(eu)
        
        // 3. 批量建立 FormField 关系
        WITH d
        UNWIND $field_rels AS fr
        MERGE (ff:FormField {name: fr.field_name, project_id: $pid})
        WITH ff, fr
        MATCH (eu:EvidenceUnit {id: fr.chunk_id, project_id: $pid})
        MERGE (ff)-[:EVIDENCE_BY]->(eu)
        """
        
        try:
            with self._driver.session() as s:
                s.run(
                    cypher,
                    pid=project_id,
                    fid=file_id,
                    filename=filename,
                    units=evidence_units,
                    field_rels=form_field_relations
                )
            logger.info(
                f"🕸️ DoCO 与 FormField 关系入库完成: {len(evidence_units)} units, "
                f"{len(form_field_relations)} field relations (project={project_id})"
            )
        except Exception as e:
            logger.error(f"DoCO 与 FormField 关系入库失败: {e}")

    def get_stats(self, project_id: str = "") -> dict:
        """返回图谱统计信息。"""
        if not self._ensure_connection():
            return {"nodes": 0, "edges": 0, "connected": False}
        try:
            with self._driver.session() as s:
                if project_id:
                    nodes = s.run(
                        "MATCH (e:Entity {project_id: $pid}) "
                        "RETURN count(e) AS c",
                        pid=project_id,
                    ).single()["c"]
                    edges = s.run(
                        "MATCH (:Entity {project_id: $pid})"
                        "-[r:RELATES_TO]-() "
                        "RETURN count(r) AS c",
                        pid=project_id,
                    ).single()["c"]
                else:
                    nodes = s.run(
                        "MATCH (e:Entity) RETURN count(e) AS c"
                    ).single()["c"]
                    edges = s.run(
                        "MATCH ()-[r:RELATES_TO]-() "
                        "RETURN count(r) AS c"
                    ).single()["c"]
            return {
                "nodes": nodes,
                "edges": edges,
                "connected": True,
            }
        except Exception as e:
            logger.error(f"图谱统计失败: {e}")
            return {"nodes": 0, "edges": 0, "connected": False}


# 单例实例
graph_engine = GraphRAGEngine()
