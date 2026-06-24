"""
Celery Worker 守护进程。
WHY: 运行后台耗时任务，包括各类文件的解析抽取和向量化切片。
     避免大规模并发阻塞 Web 进程。
"""
from __future__ import annotations

import os
os.environ["HF_HUB_OFFLINE"] = os.getenv("HF_HUB_OFFLINE", "0")

# ── onnxruntime 阻断器（必须在所有其他 import 之前执行） ──
import core.onnx_blocker  # noqa: F401

import logging
from celery.utils.log import get_task_logger
from celery.signals import worker_process_init

from core.celery_app import celery_app
from core.extractors import extract_text
from core.vector_store import ingest_text, estimate_chunk_count
from core.status_tracker import update_file_status

logger = get_task_logger(__name__)

# WHY: chunks 超过此阈值时，BGE-M3 编码在 ARM 上大概率超过 480s 软超时。
#      自动将任务从 fast queue 重路由到 slow_queue（3000s 超时）。
_CHUNK_THRESHOLD_SLOW_QUEUE = 200


@worker_process_init.connect
def on_worker_process_init(**kwargs):
    """
    WHY: 每个 ForkPoolWorker 子进程 fork 后立即初始化。
    原计划预热 BGE-M3 模型，但在 ARM 模拟环境下模型加载需要 5~10s，
    这会触发 Celery billiard 线程池的 3s 启动检测超时而被 SIGKILL 强杀。
    因此改为延迟到首个任务执行时懒加载，以实现零阻塞秒级启动。
    """
    logger.info("Worker 进程初始化完成 (已禁用同步预热以防 billiard 启动超时)")


def should_pause_project_task(project_id: str, task_type: str = "all") -> bool:
    """
    按任务类型判断当前低优先级任务是否应退避于高优先级任务。
    WHY: 每种进程类型（向量化、图谱、摘要）应独立调度，互不阻断。
         1级项目正在向量化时，图谱队列应继续处理其他案件的图谱任务，
         而非全系统空闲等待。

    task_type 取值：
      - "vectorize": 仅在 1 级项目有向量化任务时退避
      - "graph":     仅在 1 级项目有图谱提取任务时退避
      - "summary":   仅在 1 级项目有社区摘要任务时退避
      - "all":       任一进程类型有高优任务即退避（预计算等全局任务用）
    """
    try:
        from core.database import get_db
        # 1. 检查自己项目的优先级与暂停状态
        with get_db() as conn:
            row = conn.execute("SELECT priority, is_paused FROM projects WHERE id = ?", (project_id,)).fetchone()
        
        if row:
            priority = row[0]
            is_paused = row[1]
            if is_paused == 1:
                return True
            if priority == 1:
                return False

        # 2. 查询系统中未暂停的 1 级项目
        with get_db() as conn:
            high_priority_projects = conn.execute("SELECT id FROM projects WHERE priority = 1 AND is_paused = 0").fetchall()
        
        if not high_priority_projects:
            return False

        from pathlib import Path
        import json
        from core.config import settings
        from core.redis_client import get_redis

        r = get_redis()

        # 3. 按 task_type 分别判断 1 级项目是否在对应进程类型中有活跃任务
        for p in high_priority_projects:
            pid = p["id"]
            
            # ── 向量化阶段检测 ──
            if task_type in ("vectorize", "all"):
                project_dir = Path(settings.UPLOAD_DIR) / pid
                job_states_dir = project_dir / ".job_states"
                if job_states_dir.exists():
                    for f in job_states_dir.glob("*.json"):
                        try:
                            with open(f, "r", encoding="utf-8") as sf:
                                data = json.load(sf)
                                st = data.get("status", "pending")
                                if st in ("pending", "processing"):
                                    return True
                        except Exception:
                            pass

            # ── 图谱提取阶段检测 ──
            if task_type in ("graph", "all"):
                project_dir = Path(settings.UPLOAD_DIR) / pid
                job_states_dir = project_dir / ".job_states"
                if job_states_dir.exists():
                    for f in job_states_dir.glob("*.json"):
                        try:
                            with open(f, "r", encoding="utf-8") as sf:
                                data = json.load(sf)
                                st = data.get("status", "pending")
                                if st in ("graph_queued", "graph_extracting"):
                                    return True
                        except Exception:
                            pass

            # ── 社区摘要阶段检测 ──
            if task_type in ("summary", "all"):
                if r:
                    comm_status_key = f"community_summary:status:{pid}"
                    comm_lock_key = f"community_summary_lock:{pid}"
                    try:
                        status_val = r.get(comm_status_key)
                        if status_val:
                            comm_status = status_val.decode("utf-8") if isinstance(status_val, bytes) else str(status_val)
                            if comm_status in ("running", "pending"):
                                return True
                        if r.get(comm_lock_key):
                            return True
                    except Exception:
                        pass

    except Exception as e:
        logger.warning(f"Check priority learning task pause failed: {e}")
    
    return False

@celery_app.task(
    bind=True,
    name="worker.process_document",
    autoretry_for=(Exception,),
    retry_backoff=True,
    max_retries=3,
)
def process_document(self, file_path: str, file_id: str, filename: str, project_id: str):
    """
    异步任务：抽取文档文本并切片向量化入库。
    """
    from core.llm_engine import current_project_id
    current_project_id.set(project_id)
    if should_pause_project_task(project_id, "vectorize"):
        logger.info(f"⏳ 检测到高优先级案件正在学习，退避 process_document 任务: project={project_id}, file={filename}")
        process_document.apply_async(
            args=[file_path, file_id, filename, project_id],
            queue=self.request.delivery_info.get('routing_key', 'celery') if self.request.delivery_info else 'celery',
            countdown=30
        )
        return {"status": "paused_due_to_high_priority"}
    logger.info(f"开始处理文档: {filename} ({file_id})")
    update_file_status(project_id, file_id, "processing")
    try:
        # WHY: 幂等入库保护。如果该 file_id 已经存在（例如同名覆盖上传），
        # 强制在前置阶段清空其所有遗留的向量切片，避免数据堆积重复。
        from core.vector_store import delete_by_file_id
        from core.graph_rag import graph_engine

        v_count = delete_by_file_id(file_id)
        if v_count > 0:
            logger.info(f"历史数据清理完成: 向量={v_count}")

        text = extract_text(file_path)
        if text and text.strip():
            # ── 自动队列路由：预估 chunks 数量，超阈值时重路由到 slow_queue ──
            estimated = estimate_chunk_count(text, filename)
            current_queue = self.request.delivery_info.get('routing_key', '') if self.request.delivery_info else ''

            if estimated > _CHUNK_THRESHOLD_SLOW_QUEUE and current_queue != 'slow_queue':
                logger.info(
                    f"预估 chunks={estimated} > 阈值={_CHUNK_THRESHOLD_SLOW_QUEUE}，"
                    f"从队列 '{current_queue}' 重路由到 slow_queue: {filename}"
                )
                # WHY: 重新提交到 slow_queue，当前任务直接返回（不执行向量化）
                process_document.apply_async(
                    args=[file_path, file_id, filename, project_id],
                    queue='slow_queue'
                )
                update_file_status(project_id, file_id, "pending")
                return {"status": "rerouted_to_slow_queue", "estimated_chunks": estimated}

            if estimated > _CHUNK_THRESHOLD_SLOW_QUEUE:
                logger.info(
                    f"已在 slow_queue 中处理大文件: {filename} "
                    f"(预估 chunks={estimated})"
                )

            chunks = ingest_text(
                text=text,
                file_id=file_id,
                filename=filename,
                project_id=project_id,
            )
            logger.info(f"文档处理完成: {filename}, 入库 {chunks} 个 chunk")

            # WHY: 同步提取完整表格并注册到表格注册表，
            #      使聊天和文档生成时可按标题语义匹配后直接注入完整 Markdown 表格。
            try:
                from core.extractors import extract_tables
                from core.table_registry import register_tables
                tables = extract_tables(file_path)
                if tables:
                    registered = register_tables(tables, file_id, filename, project_id)
                    logger.info(f"表格注册完成: {filename}, {registered} 张表格")
            except Exception as te:
                logger.warning(f"表格提取/注册失败(非致命): {filename}, {te}")
            # WHY: 向量化完成后标记为 graph_queued，等待图谱提取
            update_file_status(project_id, file_id, "graph_queued", chunks=chunks)

            # === RAPTOR 多层摘要 ===
            # WHY: 对 chunk 数 ≥ 5 的文件构建多层摘要，增强宏观问题回答能力。
            #      在基础入库完成后立即执行，因为 RAPTOR 需要读取已入库的 chunk。
            #      失败不影响后续图谱提取流程。
            if chunks >= 5:
                try:
                    from core.vector_store import ingest_raptor_layers
                    raptor_count = ingest_raptor_layers(file_id, filename, project_id)
                    if raptor_count > 0:
                        logger.info(f"🌲 RAPTOR 摘要完成: {filename}, {raptor_count} 个摘要 chunk")
                except Exception as re:
                    logger.warning(f"🌲 RAPTOR 摘要失败(非致命): {filename}, {re}")

            # 触发后台全量 GraphRAG 提炼 (极度消耗 LLM，放入 slow_queue)
            process_graph_extraction.apply_async(
                args=[file_id, filename, project_id],
                queue='slow_queue'
            )



            return {"status": "graph_queued", "chunks": chunks}
        elif text is None:
            logger.warning(f"跳过处理，格式不支持: {filename}")
            update_file_status(project_id, file_id, "unsupported_format", chunks=0)
            return {"status": "unsupported_format", "chunks": 0}
        else:
            logger.warning(f"跳过处理，提取文本为空: {filename}")
            update_file_status(project_id, file_id, "empty_text", chunks=0)
            return {"status": "empty_text", "chunks": 0}

    except Exception as e:
        logger.error(f"处理文档失败: {filename}, 错误: {str(e)}")
        # 持久化记载奔溃记录，阻断前端的无止尽死等轮询
        update_file_status(project_id, file_id, "failed", chunks=0, error_message=str(e))
        raise e


@celery_app.task(
    bind=True,
    name="worker.process_graph_extraction",
    # WHY: max_retries 从 3 降到 1。Ollama 卡死时，重试只会重复浪费时间。
    #      用户可通过前端"重试"按钮手动触发。
    max_retries=1,
    # WHY: 禁用自动重试。SoftTimeLimitExceeded 不再自动 retry，
    #      改由熔断机制提前终止，避免无效重试占满队列。
    autoretry_for=(),
    retry_backoff=True,
)
def process_graph_extraction(self, file_id: str, filename: str, project_id: str):
    """
    后台任务：全量扫描 Qdrant 中的文档切片，利用大模型抽取三元组入库 Neo4j。
    """
    from core.llm_engine import current_project_id
    current_project_id.set(project_id)
    if should_pause_project_task(project_id, "graph"):
        logger.info(f"⏳ 检测到高优先级案件图谱任务，退避 process_graph_extraction: project={project_id}, file={filename}")
        process_graph_extraction.apply_async(
            args=[file_id, filename, project_id],
            queue=self.request.delivery_info.get('routing_key', 'slow_queue') if self.request.delivery_info else 'slow_queue',
            countdown=30
        )
        update_file_status(project_id, file_id, "graph_queued")
        return {"status": "paused_due_to_high_priority"}
    logger.info(f"🕸️ 开始后台图谱抽取: {filename} ({file_id})")
    update_file_status(project_id, file_id, "graph_extracting")

    from core.vector_store import get_all_chunks
    from core.graph_rag import graph_engine
    import asyncio

    chunks = get_all_chunks(file_id, limit=500)
    if not chunks:
        logger.warning(f"文件 {filename} 无有效向量切片，跳过图谱提炼")
        update_file_status(
            project_id, file_id, "vectorized",
            error_message="Graph OK: 0 triples (no chunks)"
        )
        return {"status": "empty", "triples": 0}

    # WHY: 增量重建——先清除该文件的旧三元组，避免重复处理时数据堆积。
    old_rels = graph_engine.delete_by_file_id(file_id, project_id)
    if old_rels > 0:
        logger.info(f"🕸️ 图谱增量清理完成: {filename}, 删除 {old_rels} 条旧关系")

    total_triples = 0

    async def extract_all():
        nonlocal total_triples
        triples_batch = []
        # WHY: 连续失败熔断计数器。如果连续 3 个 chunk 的 LLM 调用
        #      全部超时/返回空，说明 Ollama 服务不可用，
        #      立即跳过该文件，释放 Worker 处理队列中的下一个。
        consecutive_failures = 0
        MAX_CONSECUTIVE_FAILURES = 3

        for i, chunk in enumerate(chunks):
            # 避免对非常短的废话进行抽取
            if len(chunk) < 50:
                continue

            # 抽取三元组（异步，直接 await）
            t = await graph_engine.extract_entities_and_relationships(chunk)
            if t:
                consecutive_failures = 0  # 成功则重置
                triples_batch.extend(t)
            else:
                consecutive_failures += 1
                logger.warning(
                    f"🕸️ chunk {i+1}/{len(chunks)} LLM 无结果 "
                    f"(连续失败 {consecutive_failures}/{MAX_CONSECUTIVE_FAILURES})"
                )
                if consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
                    logger.warning(
                        f"🕸️ 连续 {MAX_CONSECUTIVE_FAILURES} 个 chunk 失败，"
                        f"熔断退出: {filename}"
                    )
                    break

            # WHY: 每个 chunk 处理后都发心跳，更新 job_states 的 updated_at。
            #      避免长时间运行被前端面板误判为 Ghost Task。
            update_file_status(project_id, file_id, "graph_extracting")

            # 每积累 20 个三元组或处理完毕，进行一次入库
            if len(triples_batch) >= 20 or i == len(chunks) - 1:
                if triples_batch:
                    graph_engine.ingest_to_graph(
                        triples_batch,
                        project_id=project_id,
                        file_id=file_id,
                    )
                    total_triples += len(triples_batch)
                    triples_batch.clear()

    # WHY: Celery ForkPoolWorker 内部已有事件循环，
    #      asyncio.run() 无法嵌套调用，必须显式创建新 loop。
    loop = asyncio.new_event_loop()
    try:
        loop.run_until_complete(extract_all())
    finally:
        loop.close()

    # 图谱抽取完成，最终状态落地为 vectorized
    update_file_status(
        project_id, file_id, "vectorized",
        error_message=f"Graph OK: {total_triples} triples"
    )
    logger.info(f"🕸️ 图谱提炼完成: {filename}, 入库 {total_triples} 个三元组")

    # WHY: 图谱提取完成后触发实体消歧和社区发现与摘要生成，
    #      确保项目具备全局性知识视角，无需手动触发。
    #      使用 countdown=120 延迟 2 分钟触发，让同项目其他文件的
    #      图谱提取先完成，避免 GPU 争抢导致 503。
    #      Celery slow_queue concurrency=1 天然串行，不冲突。
    #      社区摘要使用 MERGE 幂等写入，重复触发不产生脏数据。
    # WHY: 不再局限于单文件 total_triples > 0，而是当本项目所有文件的图谱提取都已结束时，
    #      统一评估并触发后续的消歧与社区发现，以彻底避免因最后一个文件提取出 0 三元组而丢失触发的 Bug。
    project_finished = True
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
                
                # 如果有任意一个文件依然处于排队或提取中，说明本项目的图谱学习还在进行
                if st in ("graph_queued", "graph_extracting", "pending", "processing"):
                    project_finished = False
                    break
            if not project_finished:
                break

    if project_finished:
        logger.info(f"🕸️ 项目 {project_id} 所有文件图谱提取完毕，开始评估消歧和社区摘要。")
        # 统计图谱中当前的真实节点数
        total_entities = 0
        try:
            graph_stats = graph_engine.get_stats(project_id)
            total_entities = graph_stats.get("nodes", 0)
        except Exception as _ge_e:
            logger.warning(f"Failed to check graph stats for triggering summary: {_ge_e}")

        from core.redis_client import get_redis
        r = get_redis()

        if total_entities > 0:
            # === Phase 1: 实体消歧 ===
            try:
                from core.entity_resolution import EntityResolver
                resolver = EntityResolver()
                er_loop = asyncio.new_event_loop()
                try:
                    er_result = er_loop.run_until_complete(resolver.resolve(project_id))
                    logger.info(f"🔗 实体消歧完成: {er_result}")
                finally:
                    er_loop.close()
            except Exception as e:
                logger.warning(f"🔗 实体消歧失败（不影响后续流程）: {e}")

            # === Phase 2: 社区摘要 ===
            lock_key = f"community_summary_lock:{project_id}"
            should_trigger = True
            if r:
                should_trigger = r.set(lock_key, "1", nx=True, ex=600)

            if should_trigger:
                compute_community_summaries.apply_async(
                    args=[project_id],
                    queue='summary_queue',
                    countdown=10, # 极短延迟
                )
                logger.info(f"🕸️ 触发社区摘要计算: project={project_id}")
            else:
                logger.info(f"🕸️ 社区摘要已在调度中，跳过重复触发: project={project_id}")
        else:
            logger.info(f"🕸️ 项目 {project_id} 图谱内无实体，直接将社区摘要状态设为 completed。")
            if r:
                try:
                    r.setex(f"community_summary:status:{project_id}", 86400 * 7, "completed")
                    r.set(f"community_summary:total:{project_id}", "0")
                    r.set(f"community_summary:completed:{project_id}", "0")
                except Exception as _re:
                    logger.warning(f"Failed to set community summary to completed in redis: {_re}")

    return {"status": "success", "triples": total_triples}


@celery_app.task(bind=True, name="worker.precompute_project", time_limit=18000, soft_time_limit=14400)
def precompute_project(self, project_id: str, mode: str = "replace"):
    """
    Celery 任务：为指定项目执行全量预计算（三模式全文生成）。

    WHY: 将 GPU 密集计算从 FastAPI 主进程剥离到独立 Worker 进程。
         slow_queue 的 concurrency=1 天然保证 GPU 串行化。
    """
    from core.llm_engine import current_project_id
    current_project_id.set(project_id)
    if should_pause_project_task(project_id, "all"):
        logger.info(f"⏳ 检测到高优先级案件正在学习，退避 precompute_project 任务: project={project_id}")
        precompute_project.apply_async(
            args=[project_id, mode],
            queue=self.request.delivery_info.get('routing_key', 'slow_queue') if self.request.delivery_info else 'slow_queue',
            countdown=30
        )
        return {"status": "paused_due_to_high_priority"}
    import asyncio
    logger.info(f"🚀 Celery precompute task started: {project_id} mode={mode}")

    async def _run():
        from core.precompute import do_precompute_v2
        await do_precompute_v2(project_id, mode)

    asyncio.run(_run())
    logger.info(f"✅ Celery precompute task finished: {project_id} mode={mode}")



@celery_app.task(bind=True, name="worker.compute_community_summaries", queue="summary_queue")
def compute_community_summaries(self, project_id: str, skip_sync: bool = False):
    """
    Celery 任务：为图谱执行 Louvain 社区发现，并生成社区摘要。
    WHY: 提取项目全局性知识，支持更高层级的知识问答。
    """
    from core.llm_engine import current_project_id
    current_project_id.set(project_id)
    if should_pause_project_task(project_id, "summary"):
        logger.info(f"⏳ 检测到高优先级案件摘要任务，退避 compute_community_summaries: project={project_id}")
        from core.redis_client import get_redis
        r = get_redis()
        if r:
            r.delete(f"community_summary_lock:{project_id}")
        compute_community_summaries.apply_async(
            args=[project_id, skip_sync],
            queue=self.request.delivery_info.get('routing_key', 'summary_queue') if self.request.delivery_info else 'summary_queue',
            countdown=30
        )
        return {"status": "paused_due_to_high_priority"}
    import asyncio
    logger.info(f"🕸️ 开始计算社区摘要: {project_id} (skip_sync={skip_sync})")
    
    async def _run():
        from core.community_summarizer import CommunitySummarizer
        summarizer = CommunitySummarizer()
        await summarizer.run(project_id, skip_sync=skip_sync)
        
    asyncio.run(_run())
    logger.info(f"✅ 社区摘要计算完成: {project_id}")


import subprocess
import os
import re

@celery_app.task(bind=True, name="worker.generate_docx_bg")
def generate_docx_bg(self, run_id: str, json_path: str, tmp_path: str):
    logger.info(f"开启异步 Docx 生成引擎: {run_id}")
    self.update_state(state='PROGRESS', meta={'message': '初始化文档生成', 'percent': 5})

    cmd = [
        "dotnet", "run", "--project", "/app/backend/docx_builder/KimiDocx.csproj",
        json_path, tmp_path, "/app/backend/docx_builder/assets"
    ]

    try:
        import os
        custom_env = os.environ.copy()

        # PM2 injects various variables like 'version', 'VERSION', 'npm_package_version' with 'N/A'
        # .NET MSBuild will crash if it sees 'N/A' in ANY version-related environment variable.
        keys_to_delete = [k for k, v in custom_env.items() if v == "N/A" or k.lower() == "version"]
        for k in keys_to_delete:
            if k in custom_env:
                del custom_env[k]

        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, env=custom_env)
        # Regex to parse progress lines: [PROGRESS] 50 Render xyz...
        prog_re = re.compile(r'\[PROGRESS\] (\d+) (.+)')

        while True:
            line = process.stdout.readline()
            if not line:
                break
            line = line.strip()

            match = prog_re.search(line)
            if match:
                percent = int(match.group(1))
                msg = match.group(2)
                self.update_state(state='PROGRESS', meta={'message': msg, 'percent': percent})
                logger.info(f"Docx Tiến độ: {percent}% - {msg}")
            elif line:
                logger.info(f"C#: {line}")

        process.wait()

        if process.returncode != 0:
            raise Exception(f"C# SDK Error: code {process.returncode}")

        self.update_state(state='PROGRESS', meta={'message': '调用 AI 进行后处理审阅...', 'percent': 90})
        # AI review injection
        from core.docx_comments import inject_ai_comments
        inject_ai_comments(tmp_path)

        # Validation
        from core.docx_validator import validate_exported_docx
        validate_exported_docx(tmp_path)

        self.update_state(state='PROGRESS', meta={'message': '生成完成', 'percent': 100})
        return {"status": "success", "file_path": tmp_path}

    except Exception as e:
        logger.error(f"Generate docx 遇到致命异常: {e}")
        raise e
    finally:
        if os.path.exists(json_path):
            os.remove(json_path)
