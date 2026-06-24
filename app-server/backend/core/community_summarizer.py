import logging
import asyncio
import re
import hashlib
from neo4j import GraphDatabase
import networkx as nx
# WHY: Leiden 算法是 Louvain 的改进版，保证每个社区内部连通，解决断裂社区问题。
#      借鉴 RAGFlow graphrag/general/leiden.py 的实现。
#      保留 Louvain 作为降级方案（graspologic 安装失败时）。
try:
    from graspologic.partition import hierarchical_leiden
    _USE_LEIDEN = True
except ImportError:
    from community import community_louvain
    _USE_LEIDEN = False

from core.config import settings
from core.llm_engine import stream_ollama

logger = logging.getLogger(__name__)

COMMUNITY_SUMMARY_PROMPT = """你是一个专业的工程领域知识总结助手。
以下是知识图谱中通过社区发现算法提取出的一组紧密相关的实体及其关系网络。

## 实体与关系
{context}

## 任务
请根据上述实体关系，总结出一段连贯、专业、信息丰富的中文摘要。
- 描述这些实体是如何相互关联的。
- 突出它们代表的核心工程环节、设备系统、或规范要求。
- 保持客观，不编造未提供的信息。
- 总结长度在 100-300 字之间。

请直接输出摘要，不要有任何客套话。
/no_think"""

class CommunitySummarizer:
    """
    基于 Louvain 算法的图谱社区发现与摘要提取。
    通过 Hash ID 实现增量计算，分页防超时。
    """
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

    async def run(self, project_id: str, skip_sync: bool = False):
        """执行增量社区计算与分页摘要提取"""
        try:
            self._connect()
            
            # === Phase 1: 社区对齐与同步 ===
            if not skip_sync:
                await self._sync_communities(project_id)
            else:
                logger.info(f"🕸️ 跳过社区对齐与同步 (skip_sync=True): project={project_id}")

            # === Phase 2: 分批执行摘要 (每次最多 30 个) ===
            await self._process_pending_summaries(project_id)
            
        except Exception as e:
            logger.error(f"社区摘要流程异常: {e}")
            from core.redis_client import get_redis
            r = get_redis()
            if r:
                r.setex(f"community_summary:status:{project_id}", 86400 * 7, "failed")
        finally:
            self._close()

    async def _sync_communities(self, project_id: str):
        """
        获取全图，运行 Leiden/Louvain 算法，计算稳定 Hash ID。
        删除已淘汰的社区，写入新社区（summary=NULL）。
        """
        edges = self._fetch_graph(project_id)
        if not edges:
            logger.info(f"项目 {project_id} 图谱为空，跳过分区同步")
            return

        G = nx.Graph()
        for s, rel, o in edges:
            G.add_edge(s, o, relation=rel)

        if len(G.nodes) < 5:
            logger.info(f"项目 {project_id} 图谱太小 ({len(G.nodes)} 节点)，跳过社区计算")
            return

        if _USE_LEIDEN:
            # WHY: Leiden 算法保证每个社区内部连通，且支持层级聚类。
            #      max_cluster_size=15 控制社区最大规模，与 Louvain 产出规模接近。
            community_mapping = hierarchical_leiden(
                G, max_cluster_size=15, random_seed=42
            )
            communities = {}
            for p in community_mapping:
                if p.level == 0:  # 使用最细粒度层级
                    communities.setdefault(p.cluster, []).append(p.node)
            algo_name = "Leiden"
        else:
            # 降级：Louvain
            partition = community_louvain.best_partition(G, random_state=42)
            communities = {}
            for node, comm_id in partition.items():
                communities.setdefault(comm_id, []).append(node)
            algo_name = "Louvain"

        logger.info(f"社区发现算法: {algo_name}, 原始社区数: {len(communities)}")

        # === PageRank 计算与写回 ===
        # WHY: PageRank 标识图谱中的重要实体（高连接度节点）。
        #      N-Hop 路径检索按 pagerank 降序排列，优先返回核心实体的关联路径。
        #      在此处计算最高效——NetworkX 图 G 已就绪，不用再读一次 Neo4j。
        try:
            pr = nx.pagerank(G, alpha=0.85)
            # 批量写回 Neo4j
            pr_data = [{"name": name, "rank": round(rank, 6)} for name, rank in pr.items()]
            with self._driver.session() as session:
                session.run("""
                    UNWIND $data AS d
                    MATCH (e:Entity {name: d.name, project_id: $pid})
                    SET e.pagerank = d.rank
                """, data=pr_data, pid=project_id)
            logger.info(f"📊 PageRank 写回完成: {len(pr_data)} 个实体 (project={project_id})")
        except Exception as e:
            logger.warning(f"PageRank 计算/写回失败(非致命): {e}")

        valid_communities = [nodes for nodes in communities.values() if len(nodes) >= 3]
        
        # 1. 计算当前最新图谱的 稳定 Hash ID 集合
        current_hashes = {}
        for nodes in valid_communities:
            sorted_nodes = sorted(nodes)
            comm_hash = hashlib.md5(",".join(sorted_nodes).encode('utf-8')).hexdigest()
            stable_id = f"{project_id}_comm_{comm_hash}"
            current_hashes[stable_id] = nodes
            
        logger.info(f"项目 {project_id} 发现 {len(current_hashes)} 个有效社区分区")

        with self._driver.session() as session:
            # 2. 查询 Neo4j 中已有的此项目的所有社区 ID
            existing_result = session.run(
                "MATCH (c:Community {project_id: $pid}) RETURN c.id AS id",
                pid=project_id
            )
            existing_ids = set(record["id"] for record in existing_result)

            # 3. 找出需要删除的淘汰社区（旧的拆分方式）
            obsolete_ids = existing_ids - set(current_hashes.keys())
            if obsolete_ids:
                session.run(
                    "MATCH (c:Community) WHERE c.id IN $obsolete_ids DETACH DELETE c",
                    obsolete_ids=list(obsolete_ids)
                )
                logger.info(f"🗑️ 淘汰了 {len(obsolete_ids)} 个旧社区分区")

            # 4. 找出需要新增的社区
            new_ids = set(current_hashes.keys()) - existing_ids
            for nid in new_ids:
                nodes = current_hashes[nid]
                session.run(
                    """
                    MERGE (c:Community {id: $cid, project_id: $pid})
                    // 默认 summary 是 null
                    WITH c
                    UNWIND $nodes AS n
                    MATCH (e:Entity {name: n, project_id: $pid})
                    MERGE (c)-[:CONTAINS]->(e)
                    """,
                    cid=nid, pid=project_id, nodes=nodes
                )
            if new_ids:
                logger.info(f"✨ 注册了 {len(new_ids)} 个新社区分区等待摘要")

    async def _process_pending_summaries(self, project_id: str):
        """查询 Neo4j 中尚未有 summary 的社区并处理，限制单批次数量"""
        MAX_BATCH_SIZE = 5
        
        with self._driver.session() as session:
            # 获取所有待处理和总数
            total_res = session.run("MATCH (c:Community {project_id: $pid}) RETURN count(c) AS cnt", pid=project_id).single()
            total_communities = total_res["cnt"] if total_res else 0
            
            # WHY: 精确获取当前真实的未处理社区数，避免粗暴估算导致的进度条虚高与卡顿
            pending_total_res = session.run(
                "MATCH (c:Community {project_id: $pid}) WHERE c.summary IS NULL RETURN count(c) AS cnt",
                pid=project_id
            ).single()
            pending_total = pending_total_res["cnt"] if pending_total_res else 0
            
            pending_res = session.run(
                """
                MATCH (c:Community {project_id: $pid}) 
                WHERE c.summary IS NULL 
                RETURN c.id AS id, [(c)-[:CONTAINS]->(e) | e.name] AS nodes
                LIMIT $limit
                """,
                pid=project_id, limit=MAX_BATCH_SIZE + 1 # +1 to check if there are more
            )
            pending_records = list(pending_res)
            
        pending_count = len(pending_records)
        if pending_count == 0:
            logger.info(f"🎉 项目 {project_id} 所有图谱社区 ({total_communities} 个) 的摘要均已就绪！")
            from core.redis_client import get_redis
            r = get_redis()
            if r:
                r.setex(f"community_summary:status:{project_id}", 86400 * 7, "completed")
                r.delete(f"community_summary:current_task:{project_id}")
                r.setex(f"community_summary:total:{project_id}", 86400 * 7, total_communities)
                r.setex(f"community_summary:completed:{project_id}", 86400 * 7, total_communities)
            return

        has_more = pending_count > MAX_BATCH_SIZE
        batch_records = pending_records[:MAX_BATCH_SIZE]
        
        logger.info(f"处理社区摘要批次: 本次提取 {len(batch_records)} 个，存在后续批次: {has_more}")
        
        # 提取边关系供摘要使用
        edges = self._fetch_graph(project_id)
        
        from core.redis_client import get_redis
        r = get_redis()
        if r:
            r.setex(f"community_summary:status:{project_id}", 86400 * 7, "processing")
            # 使用真实的未完成数计算完成度
            completed = max(0, total_communities - pending_total)
            r.setex(f"community_summary:total:{project_id}", 86400 * 7, total_communities)
            r.setex(f"community_summary:completed:{project_id}", 86400 * 7, completed)

        async def process_record(record):
            comm_id = record["id"]
            nodes = record["nodes"]
            
            # 组装关系上下文
            sub_edges = []
            for s, rel, o in edges:
                if s in nodes and o in nodes:
                    sub_edges.append(f"{s} -[{rel}]-> {o}")
            
            context = "\n".join(sub_edges[:200]) # 防超 token
            if not context.strip():
                # 标记为空摘要避免反复查
                self._update_community_summary(comm_id, "（无显著内部关联）")
                return True
                
            prompt = COMMUNITY_SUMMARY_PROMPT.format(context=context)
            # WHY: 使用统一协同模型 settings.COLLAB_LLM_MODEL，减小显存占用，并保证后台慢任务模型一致。
            model = settings.COLLAB_LLM_MODEL
            
            try:
                # WHY: 相同社区成员产生相同 prompt，重试时命中缓存跳过 GPU
                from core.llm_cache import get_llm_cache, set_llm_cache
                cached = get_llm_cache(model, prompt)
                if cached is not None:
                    summary = re.sub(r'<think>.*?</think>', '', cached, flags=re.DOTALL).strip()
                    if summary and not summary.startswith(('❌', '⚠️')):
                        self._update_community_summary(comm_id, summary)
                        logger.debug(f"🎯 社区 {comm_id} 摘要命中缓存")
                        return True

                summary_chunks = []
                # WHY: 社区摘要 prompt 仅含 ≤200 条边关系（约 4k tokens），
                #      不需要默认 16384 上下文。缩小到 4096 大幅加速 35B 推理。
                async for chunk in stream_ollama(
                    prompt,
                    model=model,
                    temperature=0.3,
                    num_ctx=4096,
                    num_predict=512
                ):
                    summary_chunks.append(chunk)
                
                raw = "".join(summary_chunks)
                summary = re.sub(r'<think>.*?</think>', '', raw, flags=re.DOTALL).strip()
                
                if summary and not summary.startswith(('❌', '⚠️')):
                    set_llm_cache(model, prompt, raw)
                    self._update_community_summary(comm_id, summary)
                    return True
            except Exception as e:
                logger.warning(f"社区 {comm_id} 摘要生成失败: {e}")
            return False

        # WHY: 串行处理避免同时占满 GPU slot 导致 Ollama 35B 过载超时。
        #      并行 5 个请求 → 4 个同时打到 Ollama → 单请求耗时从秒级暴涨到
        #      分钟级 → 最终全部 ReadTimeout。串行后单请求快速完成。
        success_count = 0
        for idx, rec in enumerate(batch_records):
            if r:
                r.setex(
                    f"community_summary:current_task:{project_id}",
                    86400,
                    f"处理社区 {idx + 1}/{len(batch_records)}"
                )
            ok = await process_record(rec)
            if ok:
                success_count += 1
                # 实时更新 Redis 进度条
                if r:
                    new_completed = max(0, total_communities - pending_total + success_count)
                    r.setex(f"community_summary:completed:{project_id}", 86400 * 7, new_completed)
                
        logger.info(f"本批次结束: 成功完成 {success_count} 个摘要")
        
        if has_more:
            from core.redis_client import get_redis
            r = get_redis()
            slow_q_len = 0
            if r:
                try:
                    slow_q_len = r.llen("slow_queue")
                except Exception:
                    pass
            
            # 检查当前项目是否已处理完毕所有文件图谱提取
            project_finished = True
            try:
                import os
                import hashlib
                from pathlib import Path
                from core.status_tracker import get_file_status
                project_dir = Path(settings.UPLOAD_DIR) / project_id
                if project_dir.exists():
                    for root, dirs, files in os.walk(str(project_dir)):
                        if ".job_states" in dirs:
                            dirs.remove(".job_states")
                        for f in files:
                            if f.startswith(".") or f.endswith(".lock"):
                                continue
                            path = Path(root) / f
                            rel_path = str(path.relative_to(Path(settings.UPLOAD_DIR)))
                            fid = hashlib.md5(f"{project_id}_{rel_path}".encode("utf-8")).hexdigest()
                            try:
                                status_data = get_file_status(project_id, fid)
                                st = status_data.get("status", "pending")
                            except Exception:
                                st = "pending"
                            
                            # 如果有任意一个文件依然处于排队或提取中，说明本项目的图谱提取还在进行
                            if st in ("graph_queued", "graph_extracting", "pending", "processing"):
                                project_finished = False
                                break
                        if not project_finished:
                            break
            except Exception as _pe:
                logger.warning(f"Failed to check project file statuses: {_pe}")
                project_finished = False

            should_yield = False
            if not project_finished and slow_q_len > 0:
                should_yield = True

            if should_yield:
                logger.info(f"⚠️ 仍有未处理社区，但本项目图谱提取仍在进行且 slow_queue 剩余 {slow_q_len}，中断摘要接力，让出算力")
                if r:
                    r.delete(f"community_summary:current_task:{project_id}")
            else:
                logger.info("⚠️ 仍有未处理社区，触发自调度接力...")
                # IMPORT DELAYED TO AVOID CIRCULAR IMPORT
                from worker import compute_community_summaries
                # 使用 summary_queue 自我接力，延迟10秒释放算力给其他任务，并传入 skip_sync=True 避免图谱重新分区
                compute_community_summaries.apply_async(
                    args=[project_id, True],
                    queue='summary_queue',
                    countdown=10
                )
        else:
            logger.info("🎉 所有社区摘要提炼完毕，更新 Redis 状态为 completed")
            from core.redis_client import get_redis
            r = get_redis()
            if r:
                r.setex(f"community_summary:status:{project_id}", 86400 * 7, "completed")
                r.setex(f"community_summary:completed:{project_id}", 86400 * 7, total_communities)
                r.delete(f"community_summary:current_task:{project_id}")

    def _fetch_graph(self, project_id: str) -> list[tuple[str, str, str]]:
        cypher = """
        MATCH (s:Entity)-[r:RELATES_TO]->(o:Entity)
        WHERE s.project_id = $pid AND o.project_id = $pid
        RETURN s.name AS subject, r.type AS relation, o.name AS object
        """
        edges = []
        with self._driver.session() as session:
            result = session.run(cypher, pid=project_id)
            for record in result:
                edges.append((record["subject"], record["relation"], record["object"]))
        return edges

    def _update_community_summary(self, comm_id: str, summary: str):
        """仅更新 summary 字段"""
        with self._driver.session() as session:
            session.run(
                "MATCH (c:Community {id: $cid}) SET c.summary = $summary",
                cid=comm_id, summary=summary
            )
