"""
图谱直接问答服务。

WHY: 本项目 Neo4j 已有 7208 个实体节点 + 247 个社区 + PageRank，
     但检索端只用了 hybrid_search 输出路径文本拼入 context，
     没有独立的图谱 QA 路径。
     此模块实现：实体识别 → Cypher 子图查询 → 结构化 context → 答案生成。
     借鉴 DeepParseX graph_qa_service.py 架构。
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

# ── 子图检索限制 ─────────────────────────────────────────

_MAX_SEED_ENTITIES = 5
_MAX_RELATIONS = 30
_PROFILE_PREVIEW = 400
_MAX_HOPS = 2


@dataclass
class GraphQAResult:
    """图谱问答结果。"""
    context: str = ""
    entities: list = field(default_factory=list)
    relations: list = field(default_factory=list)
    seed_names: list = field(default_factory=list)


def _extract_entity_names_by_regex(question: str) -> list[str]:
    """
    用正则从问题中提取候选实体名（降级路径）。
    WHY: 当 BGE-M3 语义匹配不可用时，用基础正则兜底。
    """
    # 提取 3~10 字的中文短语
    candidates = re.findall(r'[\u4e00-\u9fa5]{3,10}', question)

    # 过滤疑问/虚词
    STOP = {
        '什么是', '怎么样', '有没有', '是不是', '能不能', '请问下',
        '帮我看', '请问你', '帮我查', '告诉我', '有哪些', '是什么',
        '怎么做', '为什么', '可以吗', '是否有', '多少个', '主要有',
    }
    candidates = [c for c in candidates if c not in STOP]

    # 提取工程编号
    codes = re.findall(
        r'(?:开发复垦|整治地块)\s*\d+#?', question
    )

    return (codes + candidates)[:8]


async def graph_qa(
    question: str,
    project_id: str,
    max_hops: int = _MAX_HOPS,
) -> GraphQAResult:
    """
    图谱直接问答主入口。

    流程：
    1. 用 BGE-M3 语义匹配从 Neo4j 缓存中找种子实体
    2. 降级：正则提取实体名 → Neo4j CONTAINS 模糊查询
    3. Cypher 查 1~2 跳子图
    4. 序列化子图为结构化 context
    5. 返回 context + 实体 + 关系数据

    WHY: 不在此处调 LLM 生成答案——由 chat() 统一融合所有
         检索路径的 context 后一次性调 LLM，避免 GPU 重复占用。
    """
    from core.graph_rag import graph_engine

    result = GraphQAResult()

    # 确保 Neo4j 连接
    if not graph_engine._ensure_connection():
        logger.warning("[graph_qa] Neo4j 不可用")
        return result

    # ── 1. 种子实体识别（BGE-M3 语义 → 正则降级）──
    graph_engine._build_entity_cache(project_id)

    seed_names = graph_engine._semantic_entity_search(
        question, top_k=_MAX_SEED_ENTITIES
    )

    if not seed_names:
        # 降级：正则提取 → Neo4j CONTAINS 模糊查询
        candidates = _extract_entity_names_by_regex(question)
        if not candidates:
            return result

        try:
            with graph_engine._driver.session() as s:
                cypher = (
                    "UNWIND $candidates AS kw "
                    "MATCH (e:Entity) "
                    "WHERE (e.project_id = $pid OR e.project_id IS NULL) "
                    "  AND e.name CONTAINS kw "
                    "RETURN DISTINCT e.name AS name, "
                    "  coalesce(e.pagerank, 0) AS pr "
                    "ORDER BY pr DESC "
                    "LIMIT $limit"
                )
                records = s.run(
                    cypher, candidates=candidates,
                    pid=project_id, limit=_MAX_SEED_ENTITIES,
                )
                seed_names = [r["name"] for r in records]
        except Exception as e:
            logger.warning(f"[graph_qa] 模糊实体查询失败: {e}")
            return result

    if not seed_names:
        return result

    result.seed_names = seed_names
    print(
        f"🕸️ [GraphQA] 种子实体: {seed_names}",
        flush=True,
    )

    # ── 2. Cypher 查 1~N 跳子图 ──
    try:
        with graph_engine._driver.session() as s:
            cypher = (
                "UNWIND $seeds AS sname "
                "MATCH (e:Entity {name: sname}) "
                "WHERE e.project_id = $pid OR e.project_id IS NULL "
                # 查 N 跳子图中的关系
                "OPTIONAL MATCH (e)-[r:RELATES_TO*1.."
                + str(max_hops) + "]->(neighbor:Entity) "
                "WHERE neighbor.project_id = $pid "
                "   OR neighbor.project_id IS NULL "
                # 查种子实体所属社区
                "OPTIONAL MATCH (c:Community)-[:CONTAINS]->(e) "
                "WHERE c.project_id = $pid "
                "RETURN e.name AS seed_name, "
                "  e.type AS seed_type, "
                "  coalesce(e.pagerank, 0) AS seed_pr, "
                "  [rel IN relationships(CASE WHEN neighbor IS NOT NULL "
                "    THEN shortestPath((e)-[:RELATES_TO*1.."
                + str(max_hops) + "]->(neighbor)) END) "
                "    | {src: startNode(rel).name, "
                "       rel_type: rel.type, "
                "       tgt: endNode(rel).name}] AS path_rels, "
                "  neighbor.name AS nbr_name, "
                "  neighbor.type AS nbr_type, "
                "  c.summary AS community_summary "
                "ORDER BY seed_pr DESC "
                "LIMIT $limit"
            )

            # WHY: shortestPath 在 Cypher 中有限制。
            #      改用简化版直接查多跳路径。
            cypher_simple = (
                "UNWIND $seeds AS sname "
                "MATCH (e:Entity {name: sname}) "
                "WHERE e.project_id = $pid OR e.project_id IS NULL "
                "OPTIONAL MATCH path = (e)-[:RELATES_TO*1.."
                + str(max_hops) + "]-(neighbor:Entity) "
                "WHERE neighbor.project_id = $pid "
                "   OR neighbor.project_id IS NULL "
                "OPTIONAL MATCH (c:Community)-[:CONTAINS]->(e) "
                "WHERE c.project_id = $pid "
                "WITH e, neighbor, c, path, "
                "  [rel IN relationships(path) | "
                "    {src: startNode(rel).name, "
                "     rel_type: coalesce(rel.type, type(rel)), "
                "     tgt: endNode(rel).name}] AS rels "
                "RETURN e.name AS seed_name, "
                "  e.type AS seed_type, "
                "  coalesce(e.pagerank, 0) AS seed_pr, "
                "  rels AS path_rels, "
                "  neighbor.name AS nbr_name, "
                "  neighbor.type AS nbr_type, "
                "  c.summary AS community_summary "
                "ORDER BY seed_pr DESC "
                "LIMIT $limit"
            )

            records = list(s.run(
                cypher_simple,
                seeds=seed_names,
                pid=project_id,
                limit=_MAX_RELATIONS,
            ))

    except Exception as e:
        logger.error(f"[graph_qa] Cypher 子图查询失败: {e}")
        return result

    # ── 3. 解析结果 ──
    entities_seen = {}
    relations_seen = set()
    community_summaries = set()

    for record in records:
        seed_name = record.get("seed_name", "")
        seed_type = record.get("seed_type", "")
        seed_pr = record.get("seed_pr", 0)

        if seed_name and seed_name not in entities_seen:
            entities_seen[seed_name] = {
                "name": seed_name,
                "type": seed_type or "未知",
                "pagerank": float(seed_pr),
                "is_seed": True,
            }

        # 邻居实体
        nbr_name = record.get("nbr_name", "")
        nbr_type = record.get("nbr_type", "")
        if nbr_name and nbr_name not in entities_seen:
            entities_seen[nbr_name] = {
                "name": nbr_name,
                "type": nbr_type or "未知",
                "pagerank": 0,
                "is_seed": False,
            }

        # 路径关系
        path_rels = record.get("path_rels") or []
        for rel in path_rels:
            if isinstance(rel, dict):
                src = rel.get("src", "")
                tgt = rel.get("tgt", "")
                rel_type = rel.get("rel_type", "关联")
                key = (src, rel_type, tgt)
                if key not in relations_seen:
                    relations_seen.add(key)

        # 社区摘要
        cs = record.get("community_summary")
        if cs:
            community_summaries.add(cs)

    result.entities = list(entities_seen.values())
    result.relations = [
        {"source": s, "relation": r, "target": t}
        for s, r, t in relations_seen
    ]

    # ── 4. 序列化为结构化 context ──
    parts = []

    # 实体部分
    if result.entities:
        parts.append("## 知识图谱 — 相关实体")
        for e in sorted(
            result.entities,
            key=lambda x: (-x["pagerank"], x["name"]),
        ):
            marker = "🎯" if e["is_seed"] else "  "
            parts.append(
                f"{marker} **{e['name']}**（{e['type']}）"
                f"{'  PR=%.3f' % e['pagerank'] if e['pagerank'] else ''}"
            )

    # 关系部分
    if result.relations:
        parts.append("\n## 知识图谱 — 实体关系")
        for rel in result.relations[:_MAX_RELATIONS]:
            parts.append(
                f"- {rel['source']} —[{rel['relation']}]→ {rel['target']}"
            )

    # 社区摘要
    if community_summaries:
        parts.append("\n## 知识图谱 — 社区背景摘要")
        for i, cs in enumerate(list(community_summaries)[:3], 1):
            # 截取前 400 字
            truncated = cs[:_PROFILE_PREVIEW]
            if len(cs) > _PROFILE_PREVIEW:
                truncated += "..."
            parts.append(f"{i}. {truncated}")

    result.context = "\n".join(parts) if parts else ""

    print(
        f"🕸️ [GraphQA] ✅ 找到 {len(result.entities)} 个实体, "
        f"{len(result.relations)} 条关系, "
        f"{len(community_summaries)} 个社区摘要",
        flush=True,
    )

    return result
