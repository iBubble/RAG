"""
Qdrant 向量存储管理器 (Phase 3 - BGE-M3 混合检索版)。
WHY: 从 FastEmbed 的 bge-small-en-v1.5（384 维英文）升级到 BGE-M3（1024 维多语言）。
     启用 Dense + Sparse 双路向量，通过 RRF 融合实现混合检索。
     Dense 覆盖语义相似度，Sparse 覆盖精确术语匹配（如行政区代码、地类编码）。
"""
from __future__ import annotations

import os
os.environ["OMP_NUM_THREADS"] = "1"
os.environ["OPENBLAS_NUM_THREADS"] = "1"
os.environ["MKL_NUM_THREADS"] = "1"

import logging
import os
import uuid
import hashlib
from typing import List, Optional, Dict, Any

import numpy as np
from qdrant_client import QdrantClient, models

from core.config import settings

logger = logging.getLogger(__name__)

# ── 全局单例 ──
_client: Optional[QdrantClient] = None
_dense_model: Optional[SentenceTransformer] = None
_sparse_tokenizer: Optional[Any] = None
_sparse_model: Optional[Any] = None
_collection_name = "syrag_documents"

# ── 模型配置 ──
_MODEL_NAME = "/app/backend/models/bge-m3"
_DENSE_DIM = 1024
_DENSE_VECTOR_NAME = "dense"
_SPARSE_VECTOR_NAME = "sparse"


def _get_client() -> QdrantClient:
    """懒初始化 Qdrant 客户端。"""
    global _client
    if _client is None:
        # WHY: 在 Mac 宿主机直接运行时，Qdrant 容器端口已映射到 localhost:6333。
        #      OrbStack DNS 桥接 rag-database 域名会偶发 502 Bad Gateway，
        #      直连 localhost 更稳定。Docker 容器内运行时由 env 覆盖即可。
        from core.config import settings
        _qdrant_url = getattr(settings, "QDRANT_URL", "http://localhost:6333")
        _client = QdrantClient(url=_qdrant_url, timeout=30.0)
        logger.info(f"QdrantDB 客户端初始化完成: {_qdrant_url}")
    return _client


def _get_dense_model() -> SentenceTransformer:
    """
    懒加载 BGE-M3 Dense 编码器（SentenceTransformer 封装）。
    WHY: SentenceTransformer 自动处理 tokenize + normalize，比手动操作更稳定。
    """
    global _dense_model
    if _dense_model is None:
        logger.info(f"正在加载 Dense 编码模型: {_MODEL_NAME} ...")
        import os
        import torch
        from sentence_transformers import SentenceTransformer
        # WHY: 限制 PyTorch 线程数为 4，配合 OMP_WAIT_POLICY=PASSIVE 环境变量，既能榨干 M4 Max 多核性能，又绝无自旋锁假死
        torch.set_num_threads(4)
        os.environ["HF_HUB_OFFLINE"] = os.getenv("HF_HUB_OFFLINE", "0")
        _dense_model = SentenceTransformer(_MODEL_NAME)
        logger.info(
            f"Dense 模型加载完成: dim={_DENSE_DIM}, "
            f"max_seq={_dense_model.max_seq_length}"
        )
    return _dense_model


def _get_sparse_model():
    """
    懒加载 Sparse 编码器，复用 Dense 模型的底层 Transformer 权重。
    WHY: 之前 Dense 和 Sparse 各自加载一份完整 BGE-M3（568M × 2 = 1.1GB × 2），
         导致内存暴涨到 10GB+。现在 Sparse 直接复用 SentenceTransformer 内部的
         model 和 tokenizer，只维护一份权重，节省 ~1.2GB 内存。
    """
    global _sparse_tokenizer, _sparse_model
    if _sparse_model is None:
        logger.info("正在初始化 Sparse 编码器（复用 Dense 模型权重）...")
        dense = _get_dense_model()
        # WHY: SentenceTransformer 内部结构为 modules[0] = Transformer(model + tokenizer)
        transformer_module = dense[0]
        _sparse_model = transformer_module.auto_model
        _sparse_tokenizer = transformer_module.tokenizer
        _sparse_model.eval()
        logger.info("Sparse 编码器初始化完成（共享权重，零额外内存）")
    return _sparse_tokenizer, _sparse_model


def warmup_models():
    """
    Worker 进程级模型预热。

    WHY: Celery ForkPoolWorker 每次重启/新建进程时，首次调用
    _get_dense_model() 和 _get_sparse_model() 需要加载 BGE-M3 权重。
    通过进程初始化时预热，避免第一个任务承担模型加载延迟。

    预热内容：
    1. Dense 模型：SentenceTransformer 加载 BAAI/bge-m3 (568M 参数)
    2. Sparse 模型：复用 Dense 权重（零额外内存）
    3. 执行一次空编码以触发 PyTorch kernel 和内存分配器初始化
    """
    logger.info("Worker 进程模型预热中...")
    # 触发 Dense 模型加载
    _get_dense_model()
    # 触发 Sparse 模型初始化（复用 Dense 权重）
    _get_sparse_model()
    # 执行一次微编码以初始化 PyTorch kernel 和内存分配器
    try:
        dense = _get_dense_model()
        _ = dense.encode(["预热"], show_progress_bar=False, batch_size=1)
        _ = _compute_sparse_vectors(["预热"])
    except Exception as e:
        logger.warning(f"模型预热试运行失败（非致命）: {e}")
    logger.info("Worker 进程模型预热完成")


def _compute_sparse_vectors(texts: List[str]) -> List[models.SparseVector]:
    """
    批量计算 BGE-M3 稀疏向量。
    WHY: 稀疏向量通过 token 级别的 lexical weight 实现精确匹配。
         算法：log(1 + relu(hidden_state))，然后按 token_id max-pool。
    """
    import torch
    tokenizer, model = _get_sparse_model()
    results = []

    # WHY: 分批处理防止 OOM（每批最多 16 条，降低峰值内存）
    batch_size = 16
    for i in range(0, len(texts), batch_size):
        batch = texts[i:i + batch_size]
        inputs = tokenizer(
            batch, padding=True, truncation=True,
            return_tensors="pt", max_length=1024
        )
        with torch.no_grad():
            out = model(**inputs, return_dict=True)
            hidden = out.last_hidden_state
            # BGE-M3 sparse weight: log(1 + relu(h)) * attention_mask
            sparse_w = (
                torch.log(1 + torch.relu(hidden))
                * inputs["attention_mask"].unsqueeze(-1)
            )
            # Max-pool over hidden dim → per-token weight
            token_weights = torch.max(sparse_w, dim=-1).values

        for j in range(len(batch)):
            token_ids = inputs["input_ids"][j]
            weights = token_weights[j]

            # 聚合相同 token_id 的权重（取 max）
            sparse_dict: Dict[int, float] = {}
            for tid, w in zip(token_ids.tolist(), weights.tolist()):
                if w > 0 and tid not in (0, 1, 2):
                    # 跳过 <s>, <pad>, </s> 特殊 token
                    sparse_dict[tid] = max(
                        sparse_dict.get(tid, 0.0), w
                    )

            if sparse_dict:
                indices = list(sparse_dict.keys())
                values = list(sparse_dict.values())
            else:
                # 防御：空文本时给一个占位
                indices = [1]
                values = [0.01]

            results.append(
                models.SparseVector(indices=indices, values=values)
            )

        # WHY: 每批处理完主动释放中间 tensor，防止在大文件入库时内存累积
        del inputs, out, hidden, sparse_w, token_weights

    return results


def _string_to_uuid(string_id: str) -> str:
    """将旧版字符串形式 ID 转为 Qdrant 支持的规范 UUID。"""
    return str(uuid.uuid5(uuid.NAMESPACE_OID, string_id))


def _simple_chunk(
    text: str, chunk_size: int = 512, overlap: int = 64
) -> List[str]:
    """简单的文本切片器（已弃用，保留作为回退）。"""
    chunks = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunks.append(text[start:end])
        start = end - overlap
    return [c.strip() for c in chunks if c.strip()]


import re

# WHY: 匹配 Markdown 表格行（以 | 开头或 | 结尾）
_TABLE_ROW_RE = re.compile(r'^\s*\|.*\|\s*$')
# WHY: 匹配章节标题（如 "1.2.3 xxx" 或 "第X章" 或 "# xxx"）
_HEADING_RE = re.compile(
    r'^(?:'
    r'\d+(?:\.\d+)*\s+'      # 1.2.3 格式编号
    r'|第[一二三四五六七八九十百千\d]+[章节条款篇]'  # 中文章节号
    r'|#{1,4}\s+'             # Markdown 标题
    r')'
)


def _semantic_chunk(
    text: str,
    target_size: int = 512,
    min_size: int = 128,
    max_size: int = 1200,
) -> List[str]:
    """
    语义感知切片器——按自然段落边界切割，保护表格完整性。

    切割策略（优先级从高到低）：
    1. 空行（\\n\\n）= 段落分隔符，最佳切割点
    2. 换行 + 标题标记 = 章节分隔
    3. 句末标点（。！？；\\n）= 句子分隔

    保护机制：
    - Markdown 表格（连续的 |...|... 行）视为不可分割的原子单元
    - 如果单个原子块 > max_size，独立成 chunk（不截断）

    WHY: 替代 _simple_chunk(512) 的暴力按字符切割。
         固定切割会把段落从中间切断、把表格切碎，
         导致 LLM 收到残缺上下文后"编造"缺失数据。
    """
    if not text or not text.strip():
        return []

    # ── Step 1: 按空行分割为"段落级原子块" ──
    raw_blocks = text.split('\n\n')
    atoms: List[str] = []

    for block in raw_blocks:
        block = block.strip()
        if not block:
            continue

        lines = block.split('\n')

        # 检测是否包含表格行
        table_lines = []
        text_lines = []
        in_table = False

        for line in lines:
            if _TABLE_ROW_RE.match(line):
                if not in_table and text_lines:
                    # 表格前的文字先作为独立原子
                    atoms.append('\n'.join(text_lines).strip())
                    text_lines = []
                in_table = True
                table_lines.append(line)
            else:
                if in_table:
                    # 表格结束，将整个表格作为一个原子
                    atoms.append('\n'.join(table_lines).strip())
                    table_lines = []
                    in_table = False
                text_lines.append(line)

        # 收尾
        if table_lines:
            atoms.append('\n'.join(table_lines).strip())
        if text_lines:
            atoms.append('\n'.join(text_lines).strip())

    if not atoms:
        return []

    # ── Step 2: 进一步拆分过大的纯文本原子（在句子边界拆分） ──
    refined: List[str] = []
    for atom in atoms:
        # 表格原子不拆分（即使超大也保持完整）
        if _TABLE_ROW_RE.match(atom.split('\n')[0]):
            refined.append(atom)
            continue

        if len(atom) <= max_size:
            refined.append(atom)
            continue

        # 超大文本块：按句子边界拆分
        # WHY: 用正则在句号/分号/换行处分割，保持句子完整性
        sentences = re.split(r'(?<=[。！？；\n])', atom)
        current = ""
        for sent in sentences:
            if not sent.strip():
                continue
            if len(current) + len(sent) > target_size and current:
                refined.append(current.strip())
                current = sent
            else:
                current += sent
        if current.strip():
            refined.append(current.strip())

    # ── Step 3: 合并过小的相邻块 ──
    chunks: List[str] = []
    buffer = ""

    for atom in refined:
        # 如果当前 buffer + 新原子仍在目标范围内，合并
        if buffer and len(buffer) + len(atom) + 2 <= target_size:
            buffer += '\n\n' + atom
        else:
            if buffer:
                chunks.append(buffer)
            buffer = atom

    if buffer:
        chunks.append(buffer)

    # ── Step 4: 过滤空白/过短的碎片 ──
    result = [c.strip() for c in chunks if c.strip() and len(c.strip()) >= 20]

    return result


def ensure_collection():
    """
    确保 Qdrant collection 存在且 schema 正确（Dense 1024 + Sparse）。
    WHY: 从旧的 FastEmbed 自动管理切换到手动管理 collection schema。
         如果 collection 不存在或维度不匹配，自动创建新的。
    """
    client = _get_client()

    try:
        info = client.get_collection(_collection_name)
        vectors_config = info.config.params.vectors

        # 检查是否已经是新版 Named Vectors 模式
        if isinstance(vectors_config, dict) and _DENSE_VECTOR_NAME in vectors_config:
            current_dim = vectors_config[_DENSE_VECTOR_NAME].size
            if current_dim == _DENSE_DIM:
                logger.info(
                    f"Collection '{_collection_name}' 已存在且 schema 正确 "
                    f"(dense={current_dim}d + sparse)"
                )
                return
        # schema 不匹配，需要重建
        logger.warning(
            f"Collection '{_collection_name}' schema 不匹配，将删除并重建"
        )
        client.delete_collection(_collection_name)
    except Exception:
        # collection 不存在
        pass

    # 创建新 collection：Named Vectors + Sparse Vectors
    client.create_collection(
        collection_name=_collection_name,
        vectors_config={
            _DENSE_VECTOR_NAME: models.VectorParams(
                size=_DENSE_DIM,
                distance=models.Distance.COSINE,
            )
        },
        sparse_vectors_config={
            _SPARSE_VECTOR_NAME: models.SparseVectorParams()
        },
    )

    # 创建常用过滤字段的索引（chunk_type 用于区分普通文本和表格索引）
    for field in ("file_id", "project_id", "filename", "chunk_type", "content_hash"):
        client.create_payload_index(
            collection_name=_collection_name,
            field_name=field,
            field_schema=models.PayloadSchemaType.KEYWORD,
        )

    # ── 升级扩展：业务字段与 EU 空间元数据索引 ──
    # WHY: 支持按科室/案件类型零衰减硬预过滤，以及按页码/语义角色精确定位
    for field in ("department", "case_type", "semantic_role"):
        client.create_payload_index(
            collection_name=_collection_name,
            field_name=field,
            field_schema=models.PayloadSchemaType.KEYWORD,
        )
    # page_number 为整数类型索引，支持范围过滤
    client.create_payload_index(
        collection_name=_collection_name,
        field_name="page_number",
        field_schema=models.PayloadSchemaType.INTEGER,
    )

    logger.info(
        f"Collection '{_collection_name}' 创建完成: "
        f"dense={_DENSE_DIM}d(cosine) + sparse + payload索引"
    )


def _inject_chunk_context(
    chunks: List[str], filename: str
) -> List[str]:
    """
    Contextual Chunking：为每个 chunk 注入文档级+相邻级上下文前缀。

    WHY: 碎片化 chunk 脱离文档上下文后，向量编码会产生语义漂移。
         例如“建设规模为 3.2 万亩”单独出现时，向量编码不知道这是哪个文件的数据。
         注入文档名 + 前文提示后，编码向量携带了文档归属信息，
         检索时更容易命中正确的文件。

    注意：前缀仅影响向量编码（提升搜索精度），
         payload 中的 document 字段应存储不含前缀的原始文本（保证 LLM 看到干净内容）。
    """
    contextualized = []
    for i, chunk in enumerate(chunks):
        prefix = f"[文档：{filename}]"
        if i > 0:
            prev_hint = chunks[i - 1][:60].replace('\n', ' ')
            prefix += f" 前文：{prev_hint}…"
        contextualized.append(f"{prefix}\n{chunk}")
    return contextualized


def _compute_chunk_confidence(chunk: str, filename: str) -> float:
    """
    计算单个 chunk 的 OCR 提取可信度分数（0.0~1.0）。
    WHY: CAD 工程图纸经 OCR 提取后质量参差不齐，
         可信度标记帮助检索阶段区分高/低质量来源，
         并在生成时提示 LLM"此来源可能含 OCR 误差"。
    评分维度:
      1. CJK 字符密度（中文越多，越像真实文档）
      2. 文本长度（过短可能是 OCR 碎片）
      3. OCR 噪声检测（连续乱码、孤立单字符）
      4. 工程术语命中（命中越多，越可信）
    """
    if not chunk or not chunk.strip():
        return 0.0

    text = chunk.strip()
    length = len(text)
    score = 0.5  # 基准分

    # ── 维度1: CJK 字符密度 ──
    # WHY: 真实中文工程文档的 CJK 比例通常 > 40%
    cjk_count = sum(1 for c in text if '\u4e00' <= c <= '\u9fff')
    cjk_ratio = cjk_count / length if length > 0 else 0

    if cjk_ratio > 0.4:
        score += 0.2
    elif cjk_ratio > 0.2:
        score += 0.1
    elif cjk_ratio < 0.05 and length > 50:
        # WHY: 长文本但几乎没有中文字符，可能是 OCR 乱码
        score -= 0.2

    # ── 维度2: 文本长度 ──
    # WHY: 短于 50 字的 chunk 信息量不足，可信度降低
    if length >= 200:
        score += 0.1
    elif length < 50:
        score -= 0.15

    # ── 维度3: OCR 噪声检测 ──
    # WHY: OCR 错误的典型特征：大量孤立单字符行、连续特殊符号
    lines = text.split('\n')
    if lines:
        # 孤立单字符行比例
        single_char_lines = sum(
            1 for ln in lines if len(ln.strip()) == 1
        )
        single_ratio = single_char_lines / len(lines)
        if single_ratio > 0.3:
            score -= 0.2

    # 特殊符号密度（排除正常标点）
    special_count = sum(
        1 for c in text
        if not c.isalnum() and c not in '，。、；：！？""''（）《》【】\n\t .-·/%+='
        and not ('\u4e00' <= c <= '\u9fff')
    )
    special_ratio = special_count / length if length > 0 else 0
    if special_ratio > 0.15:
        score -= 0.15

    # ── 维度4: 工程术语命中 ──
    # WHY: 命中越多国土/建筑关键词，越说明 OCR 提取到了有效内容
    eng_terms = (
        "保护层", "钢筋", "混凝土", "设计", "施工", "标高",
        "桩号", "地基", "基础", "挡墙", "排水", "边坡",
        "管道", "涵洞", "渠道", "断面", "土方", "填方",
        "挖方", "坡度", "坡比", "图例", "比例尺", "说明",
        "面积", "地类", "耕地", "林地", "建设用地", "规划",
        # WHY: 2026-05-22 添加水文/气象术语，确保等值线图、暴雨统计参数图册
        #      等水利专题图件的 chunk 不被置信度评分偏低惩罚。
        "等值线", "降雨量", "暴雨", "径流", "流域", "高程",
        "多年平均", "变差系数", "频率", "均值", "水文", "气象",
        "等降雨", "参数", "统计", "水系", "水库", "水位",
    )
    hits = sum(1 for t in eng_terms if t in text)
    if hits >= 5:
        score += 0.2
    elif hits >= 2:
        score += 0.1


    return round(max(0.0, min(1.0, score)), 2)


def estimate_chunk_count(text: str, filename: str = "") -> int:
    """
    快速预估语义切片后的 chunk 数量，用于队列路由决策。

    算法：基于 _semantic_chunk 的 target_size=512 和 Step3 合并逻辑，
    实际平均 chunk 大小约 500-650 字符。使用保守的分母 500 使预估
    略微偏高（宁可误判为慢队列，不可因低估导致超时）。

    文件类型修正：
    - .xlsx/.xls：Excel 提取文本含大量短表格行，chunk 密度更高，
      分母下调至 420（实测：403517 字符 → 652 chunks，403517/420≈961）
    """
    if not text or not text.strip():
        return 0
    text_len = len(text)
    # 默认分母：500（较保守，会略高估）
    divisor = 500
    # Excel 文件文本密度更高（表格行短，合并少），调低分母
    if filename.lower().endswith(('.xlsx', '.xls')):
        divisor = 420
    return max(1, text_len // divisor)


# ── 跨项目内容去重辅助函数 ──

def _find_by_content_hash(content_hash: str) -> list:
    """
    在 Qdrant 中查找已有相同 content_hash 的全部 points。
    WHY: 跨项目内容去重 — 如果同一份文档已被其他项目向量化过，
         可以直接克隆其向量，跳过昂贵的 BGE-M3 编码。
    返回 point 列表（含 id、vector、payload），无匹配返回空 list。
    """
    try:
        client = _get_client()
        results = []
        offset = None
        while True:
            batch, next_offset = client.scroll(
                collection_name=_collection_name,
                scroll_filter=models.Filter(
                    must=[
                        models.FieldCondition(
                            key="content_hash",
                            match=models.MatchValue(value=content_hash),
                        )
                    ]
                ),
                limit=100,
                offset=offset,
                with_vectors=True,
                with_payload=True,
            )
            results.extend(batch)
            if next_offset is None:
                break
            offset = next_offset
        return results
    except Exception as e:
        logger.warning(f"content_hash 查重失败(非致命): {e}")
        return []


def _clone_points(
    source_points: list,
    new_file_id: str,
    new_filename: str,
    new_project_id: str,
    content_hash: str,
) -> int:
    """
    将源 points 的向量克隆到新的 file_id/project_id 下。
    WHY: 跳过 BGE-M3 编码（最耗时步骤），仅复制向量 + 替换元数据，
         同一文档跨项目入库从 ~120s 降至 ~2s。
    """
    client = _get_client()
    ensure_collection()

    new_points = []
    for pt in source_points:
        old_payload = pt.payload or {}
        chunk_index = old_payload.get("chunk_index", 0)
        chunk_type = old_payload.get("chunk_type", "")

        # 生成新的 point ID（基于 new_file_id）
        if chunk_type == "doc_summary":
            new_id = _string_to_uuid(f"{new_file_id}__doc_summary")
        else:
            new_id = _string_to_uuid(f"{new_file_id}__chunk_{chunk_index}")

        new_payload = {
            **old_payload,
            "file_id": new_file_id,
            "filename": new_filename,
            "project_id": new_project_id,
            "content_hash": content_hash,
        }

        new_points.append(
            models.PointStruct(
                id=new_id,
                vector=pt.vector,
                payload=new_payload,
            )
        )

    if not new_points:
        return 0

    # 批量写入
    batch_size = 64
    for start in range(0, len(new_points), batch_size):
        batch = new_points[start : start + batch_size]
        client.upsert(collection_name=_collection_name, points=batch)

    logger.info(
        f"⚡ 内容去重命中！文件 {new_filename} 已从已有向量克隆 "
        f"{len(new_points)} 个 points（跳过 BGE-M3 编码）"
    )
    return len(new_points)


def ingest_text(
    text: str,
    file_id: str,
    filename: str,
    project_id: str = "default",
    # ── EU 空间与业务元数据 (D1 升级) ──
    page_numbers: list[int] | None = None,
    semantic_roles: list[str] | None = None,
    departments: list[str] | None = None,
    case_types: list[str] | None = None,
) -> int:
    """
    将纯文本切片后通过 BGE-M3 编码（Dense + Sparse）写入 Qdrant。
    返回成功入库的 chunk 数量。
    """
    client = _get_client()
    ensure_collection()

    # ── 清理可能残留的全文检索记录 ──
    from core.database import delete_fts_by_file_id
    delete_fts_by_file_id(file_id)

    # WHY: 使用语义感知切片器，按段落/句子边界切割，保护表格完整性。
    #      如果语义切片结果为空（极端情况），回退到旧的固定字符切片器。
    chunks = _semantic_chunk(text)
    if not chunks:
        chunks = _simple_chunk(text)
        logger.warning(f"文件 {filename} 语义切片为空，回退到固定切片 ({len(chunks)} chunks)")
    else:
        logger.info(f"文件 {filename} 语义切片完成: {len(chunks)} chunks")

    if not chunks:
        logger.warning(f"文件 {filename} 切片结果为空，跳过入库")
        return 0

    # ── P2: Chunk 去重 ──
    # WHY: _simple_chunk 的 overlap 或极端情况可能产生完全相同的切片，
    #      重复 chunk 浪费向量空间且导致检索结果中出现冗余条目。
    seen = set()
    deduped = []
    for c in chunks:
        # WHY: 用 strip 后的文本做去重键，忽略前后空白差异
        key = c.strip()
        if key not in seen:
            seen.add(key)
            deduped.append(c)
    if len(deduped) < len(chunks):
        logger.info(
            f"文件 {filename} 去重: {len(chunks)} → {len(deduped)} chunks "
            f"(移除 {len(chunks) - len(deduped)} 个重复)"
        )
        chunks = deduped

    # ── 跨项目内容去重 ──
    # WHY: 同一文档上传到不同项目时，BGE-M3 编码是最大瓶颈（~120s/大文件）。
    #      通过内容哈希快速判断是否已有相同内容的向量，命中则直接克隆，
    #      跳过编码步骤，将入库时间从 ~120s 降至 ~2s。
    # WHY: 使用 xxhash128 替代 MD5，性能更优且项目已引入 xxhash 依赖
    import xxhash
    content_hash = xxhash.xxh128(text.encode("utf-8")).hexdigest()
    existing_points = _find_by_content_hash(content_hash)
    if existing_points:
        logger.info(
            f"⚡ 内容去重命中: {filename} (hash={content_hash[:8]}...) "
            f"已有 {len(existing_points)} 个 points，执行克隆"
        )
        return _clone_points(existing_points, file_id, filename, project_id, content_hash)

    # WHY: Contextual Chunking — 为每个 chunk 注入文档名+前文提示前缀，
    #      仅用于 Sparse 关键词向量，增强文件名词汇匹配。
    #      Dense 语义向量使用原始文本编码，保持查询-文档编码对称性。
    chunks_for_encoding = _inject_chunk_context(chunks, filename)

    # ── Dense 编码 ──
    # WHY: Dense 用原始 chunks 编码，保证与查询端（也是原始文本）的
    #      向量空间对称，避免文件名前缀造成的语义漂移。
    dense_model = _get_dense_model()
    dense_vecs_raw = dense_model.encode(
        chunks, show_progress_bar=False, normalize_embeddings=True,
        batch_size=16,  # WHY: 控制每批大小，降低峰值内存
    )
    # WHY: 立即转为 Python list 释放 numpy 大数组
    dense_vecs = [v.tolist() for v in dense_vecs_raw]
    del dense_vecs_raw

    # ── Sparse 编码 ──
    # WHY: Sparse 用带前缀的 chunks 编码，利用文件名关键词增强
    #      BM25 词汇匹配（如文件名含"管道"可提升管道相关检索）。
    sparse_vecs = _compute_sparse_vectors(chunks_for_encoding)
    del chunks_for_encoding  # WHY: 编码完成后释放带前缀的副本

    total_chunks = len(chunks)

    # ── P3: 计算每个 chunk 的可信度分数 ──
    confidences = [_compute_chunk_confidence(c, filename) for c in chunks]

    # ── 构建 Qdrant Points ──
    points = []
    for i, (chunk, dense_vec, sparse_vec) in enumerate(
        zip(chunks, dense_vecs, sparse_vecs)
    ):
        point_id = _string_to_uuid(f"{file_id}__chunk_{i}")
        
        # 动态读取并安全防越界
        p_num = page_numbers[i] if (page_numbers and i < len(page_numbers)) else 0
        if semantic_roles and i < len(semantic_roles):
            s_role = semantic_roles[i]
        else:
            from core.extractors.pdf_parser import get_standard_semantic_role
            s_role = get_standard_semantic_role(chunk)
        dept = departments[i] if (departments and i < len(departments)) else ""
        c_type = case_types[i] if (case_types and i < len(case_types)) else ""

        points.append(
            models.PointStruct(
                id=point_id,
                vector={
                    _DENSE_VECTOR_NAME: dense_vec,
                    _SPARSE_VECTOR_NAME: sparse_vec,
                },
                payload={
                    "document": chunk,  # WHY: payload 存原始文本，不含上下文前缀
                    "file_id": file_id,
                    "filename": filename,
                    "project_id": project_id,
                    "content_hash": content_hash,
                    "chunk_index": i,
                    "total_chunks": total_chunks,
                    "confidence": confidences[i],  # P3: 可信度分数 0.0~1.0
                    # ── EU 空间元数据（动态写入）──
                    "page_number": p_num,
                    "semantic_role": s_role,
                    "department": dept,
                    "case_type": c_type,
                },
            )
        )

    # ── [NEW] 生成文档摘要 point (多级索引 Level-1) ──
    # WHY: 将文件内容浓缩为一个 doc_summary，用于多级索引的
    #       第一级检索。当项目级全局搜索时，先搜摘要确定最相关文件，
    #       再在文件内搜具体切片，防止跨文件张冠李戴。
    _is_excel = filename.lower().endswith(('.xlsx', '.xls'))
    if _is_excel and len(chunks) > 3:
        # WHY: Excel 多 sheet 策略 — 均匀采样 ~8 个位置，每片 200 字。
        #      之前只取前 3 chunk，导致 28 sheet 的 Excel 只覆盖第 1 个 sheet，
        #      预筛选搜索"耕地"时找不到匹配，整个文件被淘汰。
        _sample_indices = [0]
        _step = max(1, len(chunks) // 8)
        for _si in range(_step, len(chunks), _step):
            if len(_sample_indices) < 10:
                _sample_indices.append(_si)
        _sample_indices = sorted(set(_sample_indices))
        _sample_parts = [chunks[i][:200] for i in _sample_indices]
        summary_text = "\n\n".join(_sample_parts)[:2000]
    else:
        summary_text = "\n\n".join(chunks[:3])[:1500]
    # WHY: 如果 summary 与第一个 chunk 内容完全相同（单 chunk 文件），
    #      跳过 summary 创建，避免检索结果中出现重复条目。
    summary_is_dup = (
        len(chunks) == 1
        or summary_text.strip() == chunks[0].strip()
    )
    if summary_text.strip() and not summary_is_dup:
        summary_dense = dense_model.encode(
            [summary_text], normalize_embeddings=True, show_progress_bar=False,
        )
        summary_sparse = _compute_sparse_vectors([summary_text])
        summary_point = models.PointStruct(
            id=_string_to_uuid(f"{file_id}__doc_summary"),
            vector={
                _DENSE_VECTOR_NAME: summary_dense[0].tolist(),
                _SPARSE_VECTOR_NAME: summary_sparse[0],
            },
            payload={
                "document": summary_text,
                "file_id": file_id,
                "filename": filename,
                "project_id": project_id,
                "content_hash": content_hash,
                "chunk_type": "doc_summary",
                "chunk_index": -1,
                "total_chunks": total_chunks,
            },
        )
        points.append(summary_point)
        del summary_dense, summary_sparse

    # WHY: 编码完释放中间变量，让 GC 及时回收
    del dense_vecs, sparse_vecs, chunks

    # WHY: 分批 upsert 防止单次请求过大
    batch_size = 64
    try:
        for start in range(0, len(points), batch_size):
            batch = points[start : start + batch_size]
            client.upsert(
                collection_name=_collection_name,
                points=batch,
            )
    except Exception as e:
        logger.error(f"写入 Qdrant 失败: {e}")
        return 0

    # ── 将 chunks 同步写入 SQLite 全文检索表 ──
    from core.database import insert_fts_chunks
    fts_data = []
    for pt in points:
        payload = pt.payload
        if not payload or payload.get("chunk_type") == "doc_summary":
            continue
        fts_data.append({
            "id": pt.id,
            "file_id": payload["file_id"],
            "project_id": payload["project_id"],
            "filename": payload["filename"],
            "chunk_index": payload["chunk_index"],
            "document": payload["document"]
        })
    try:
        insert_fts_chunks(fts_data)
    except Exception as ex:
        logger.error(f"同步写入 SQLite 全文检索失败: {ex}")

    total = len(points)
    del points

    # WHY: 大文件入库后主动 GC，防止 uvicorn 进程内存持续飙升
    import gc
    gc.collect()

    logger.info(
        f"文件 {filename} 成功入库 {total} 个 chunk (含 doc_summary) "
        f"(dense={_DENSE_DIM}d + sparse) 到 Qdrant"
    )
    return total


def ingest_raptor_layers(
    file_id: str,
    filename: str,
    project_id: str = "default",
) -> int:
    """
    对已入库的文件生成 RAPTOR 多层摘要并写入 Qdrant。

    WHY: 纯向量检索面对宏观问题时表现差（"项目整体情况怎样？"），
         RAPTOR 通过递归聚类+摘要生成多层级 chunk，
         检索时同时命中细粒度原文和粗粒度摘要。

    前置条件：ingest_text() 已完成（基础 chunk 已入库）。
    独立调用：可在 worker 的 slow_queue 中异步执行，不阻塞基础入库。
    """
    import asyncio

    client = _get_client()
    ensure_collection()

    # Step 1: 从 Qdrant 拉取该文件的所有普通 chunk
    try:
        results, _ = client.scroll(
            collection_name=_collection_name,
            scroll_filter=models.Filter(
                must=[
                    models.FieldCondition(
                        key="file_id",
                        match=models.MatchValue(value=file_id),
                    ),
                ],
                must_not=[
                    models.FieldCondition(
                        key="chunk_type",
                        match=models.MatchAny(any=["doc_summary", "raptor_summary"]),
                    ),
                ],
            ),
            limit=500,
            with_payload=True,
            with_vectors={_DENSE_VECTOR_NAME},
        )
    except Exception as e:
        logger.error(f"[RAPTOR] 拉取 chunks 失败: {e}")
        return 0

    if not results or len(results) < 3:
        logger.info(f"[RAPTOR] 文件 {filename} chunks 过少 ({len(results) if results else 0})，跳过")
        return 0

    # 组装 chunks: [(text, embedding), ...]
    chunks = []
    for pt in results:
        text = (pt.payload or {}).get("document", "")
        vec = pt.vector
        if isinstance(vec, dict):
            vec = vec.get(_DENSE_VECTOR_NAME)
        if text and vec:
            chunks.append((text, list(vec) if not isinstance(vec, list) else vec))

    if len(chunks) < 3:
        return 0

    logger.info(f"[RAPTOR] 开始构建多层摘要: {filename} ({len(chunks)} chunks)")

    # Step 2: 定义 embed_fn（供 RAPTOR 回调使用）
    dense_model = _get_dense_model()

    async def embed_fn(text: str) -> list[float] | None:
        try:
            vec = dense_model.encode(
                [text], normalize_embeddings=True, show_progress_bar=False
            )[0]
            return vec.tolist()
        except Exception:
            return None

    # Step 3: 执行 RAPTOR
    from core.raptor import RaptorSummarizer
    raptor = RaptorSummarizer(max_cluster=10, max_layers=3)

    loop = asyncio.new_event_loop()
    try:
        extended_chunks, layers = loop.run_until_complete(
            raptor.build_layers(chunks, embed_fn)
        )
    except Exception as e:
        logger.error(f"[RAPTOR] 构建失败: {e}")
        return 0
    finally:
        loop.close()

    # Step 4: 将新增的摘要 chunks 写入 Qdrant
    # WHY: 只写入 layers[1:] 中的摘要 chunk（layers[0] 是原始 chunk，已入库）
    new_points = []
    for layer_idx, (start, end) in enumerate(layers):
        if layer_idx == 0:
            continue  # 跳过原始 chunk 层
        for i in range(start, end):
            text, emb = extended_chunks[i]
            sparse_vec = _compute_sparse_vectors([text])[0]
            point_id = _string_to_uuid(
                f"{file_id}__raptor_L{layer_idx}_{i-start}"
            )
            new_points.append(
                models.PointStruct(
                    id=point_id,
                    vector={
                        _DENSE_VECTOR_NAME: emb,
                        _SPARSE_VECTOR_NAME: sparse_vec,
                    },
                    payload={
                        "document": text,
                        "file_id": file_id,
                        "filename": filename,
                        "project_id": project_id,
                        "chunk_type": "raptor_summary",
                        "raptor_level": layer_idx,
                        "chunk_index": -1,
                    },
                )
            )

    if not new_points:
        logger.info(f"[RAPTOR] {filename} 无新摘要生成")
        return 0

    # 分批写入
    batch_size = 64
    try:
        for start in range(0, len(new_points), batch_size):
            batch = new_points[start : start + batch_size]
            client.upsert(
                collection_name=_collection_name,
                points=batch,
            )
    except Exception as e:
        logger.error(f"[RAPTOR] 写入 Qdrant 失败: {e}")
        return 0

    logger.info(
        f"[RAPTOR] ✅ {filename} 入库 {len(new_points)} 个摘要 chunk "
        f"({len(layers)-1} 层)"
    )
    return len(new_points)


def _hierarchical_prefilter(
    query_text: str,
    project_id: str,
    top_k: int = 5,
) -> List[str]:
    """
    多级索引第一级：搜索 doc_summary 类型的 chunk，返回最相关的文件 ID 列表。

    WHY: 当用户未指定具体文件时（项目级全局搜索），在 90+ 个文件的 chunk 海洋中
         直接搜索容易跨文件串联污染（把 A 水库的参数安到 B 水库上）。
         先搜文档级摘要确定最相关的 K 份文档，再在文档内搜具体切片，
         相当于给检索引擎装上"图书馆索引卡"。
         采用混合检索 (Dense + Sparse) 提升特定文件名、工程术语及数值指标的文档召回率。
    """
    client = _get_client()
    dense_model = _get_dense_model()

    query_dense = dense_model.encode(
        [query_text], normalize_embeddings=True
    )[0].tolist()
    query_sparse = _compute_sparse_vectors([query_text])[0]

    # WHY: 仅搜索 chunk_type="doc_summary" 的摘要 point
    summary_filter = models.Filter(
        must=[
            models.FieldCondition(
                key="project_id",
                match=models.MatchValue(value=project_id),
            ),
            models.FieldCondition(
                key="chunk_type",
                match=models.MatchValue(value="doc_summary"),
            ),
        ]
    )

    try:
        results = client.query_points(
            collection_name=_collection_name,
            prefetch=[
                models.Prefetch(
                    query=query_dense,
                    using=_DENSE_VECTOR_NAME,
                    limit=top_k,
                    filter=summary_filter,
                ),
                models.Prefetch(
                    query=query_sparse,
                    using=_SPARSE_VECTOR_NAME,
                    limit=top_k,
                    filter=summary_filter,
                ),
            ],
            query=models.FusionQuery(
                fusion=models.Fusion.RRF
            ),
            limit=top_k,
            with_payload=["file_id", "filename"],
        )
        file_ids = []
        for pt in results.points:
            fid = (pt.payload or {}).get("file_id", "")
            if fid and fid not in file_ids:
                file_ids.append(fid)

        if file_ids:
            fnames = [
                (pt.payload or {}).get("filename", "?")
                for pt in results.points
            ]
            logger.info(
                f"多级索引预筛选 (Hybrid): {len(file_ids)} 个文件命中 "
                f"({', '.join(fnames[:3])}{'...' if len(fnames) > 3 else ''})"
            )
        return file_ids
    except Exception as e:
        logger.warning(f"多级索引预筛选（混合检索）失败: {e}，降级为全局搜索")
        return []


def _expand_context(
    docs: List[dict],
    window: int = 1,
) -> List[dict]:
    """
    上下文增强：为每个命中的 chunk 拉取前后相邻的 chunk，拼接为更完整的文本块。

    WHY: 语义切片后每个 chunk 约 300-500 字。当检索命中了某个参数表格，
         该表格的前一个 chunk 通常包含"表格标题+测试条件说明"，
         后一个 chunk 可能包含"脚注+数据来源"。
         膨胀后 LLM 能看到完整的上下文边界，减少断章取义和格式幻觉。

    策略：对每个命中 chunk，向 Qdrant 查询同文件的 chunk_index +/- window。
         如果相邻 chunk 已在结果中，跳过（避免 _merge_and_dedup 阶段重复）。
    """
    if not docs or window <= 0:
        return docs

    client = _get_client()

    # WHY: 收集所有需要膨胀的 (file_id, chunk_index) 对
    existing_keys = set()
    expand_requests = []  # (file_id, target_index, parent_doc_idx)
    for i, doc in enumerate(docs):
        meta = doc.get("metadata", {})
        fid = meta.get("file_id", "")
        idx = meta.get("chunk_index", -1)
        total = meta.get("total_chunks", 9999)
        if not fid or idx < 0:
            continue
        existing_keys.add((fid, idx))

        # 向前后各扩展 window 个 chunk
        for offset in range(-window, window + 1):
            if offset == 0:
                continue
            target_idx = idx + offset
            if target_idx < 0 or target_idx >= total:
                continue
            if (fid, target_idx) in existing_keys:
                continue
            expand_requests.append((fid, target_idx, i))
            existing_keys.add((fid, target_idx))

    if not expand_requests:
        return docs

    # WHY: 按 file_id 分组批量查询，减少 Qdrant 请求次数
    from collections import defaultdict
    fid_targets: dict = defaultdict(list)
    for fid, target_idx, parent_idx in expand_requests:
        fid_targets[fid].append((target_idx, parent_idx))

    expanded_docs = list(docs)  # 浅拷贝
    for fid, targets in fid_targets.items():
        target_indices = [t[0] for t in targets]
        try:
            scroll_filter = models.Filter(
                must=[
                    models.FieldCondition(
                        key="file_id",
                        match=models.MatchValue(value=fid),
                    ),
                ],
                must_not=[
                    # WHY: 排除 doc_summary，只拉取正常 chunk
                    models.FieldCondition(
                        key="chunk_type",
                        match=models.MatchValue(value="doc_summary"),
                    ),
                ],
            )
            results, _ = client.scroll(
                collection_name=_collection_name,
                scroll_filter=scroll_filter,
                limit=500,
                with_payload=True,
                with_vectors=False,
            )

            # 建立 chunk_index -> document 映射
            idx_map = {}
            for pt in results:
                payload = pt.payload or {}
                ci = payload.get("chunk_index", -1)
                if ci in target_indices:
                    idx_map[ci] = payload

            # 将相邻 chunk 追加到结果中
            for target_idx, parent_idx in targets:
                if target_idx in idx_map:
                    payload = idx_map[target_idx]
                    expanded_docs.append({
                        "content": payload.get("document", ""),
                        "metadata": payload,
                        # WHY: 给膨胀 chunk 一个略低于父 chunk 的分数,
                        #      确保在合并排序时不会跑到父 chunk 前面。
                        "distance": docs[parent_idx]["distance"] * 0.9,
                    })
        except Exception as e:
            logger.warning(f"上下文膨胀失败 (file_id={fid}): {e}")

    if len(expanded_docs) > len(docs):
        logger.info(
            f"上下文增强: {len(docs)} -> {len(expanded_docs)} chunks "
            f"(+{len(expanded_docs) - len(docs)} 个相邻块)"
        )
    return expanded_docs


def query_by_file_ids(
    query_text: str,
    file_ids: List[str],
    project_id: str = "",
    n_results: int = 5,
) -> List[dict]:
    """
    五级检索管线：
      Stage 1: 多级索引预筛选 (确定最相关文件)
      Stage 2: Dense + Sparse -> RRF 融合 (候选召回)
      Stage 3: Reranker 交叉编码器精排 (二次打分)
      Stage 4: 上下文增强 (相邻 chunk 膨胀)
      Stage 5: 相邻合并 + 内容去重

    WHY: Dense 捕捉"语义近似" (如"耕地"="农田"),
         Sparse 捕捉"精确术语" (如行政区代码"510921"、地类编码"0102")。
         RRF 将两者的排名融合，Reranker 做深度语义精排，
         上下文膨胀补齐断章取义的边界信息。
    """
    client = _get_client()
    ensure_collection()
    import time as _t
    _t0 = _t.time()

    # ── [Stage 0] 查询预处理：拼写纠偏 ──
    # WHY: 必须在 prefilter 之前完成纠偏，否则 doc_summary 搜索
    #      会因字面不匹配导致目标文件被 prefilter 淘汰。
    _TYPO_MAP = {"地型": "地形", "田形": "田型"}
    for wrong, right in _TYPO_MAP.items():
        if wrong in query_text:
            query_text = query_text.replace(wrong, right)

    # ── [Stage 1] 多级索引预筛选 ──
    # WHY: 当未指定 file_ids 或选中文件过多时，先搜文档摘要确定最相关文件，
    #       避免在海量 chunk 中跨文件串联污染。
    #       阈值 20：少量文件直接精搜即可；超过 20 份时先缩小范围再深搜。
    _need_prefilter = (not file_ids and project_id) or (
        file_ids and len(file_ids) > 20 and project_id
    )
    if _need_prefilter:
        # WHY: 当文件数量巨大（>50）时，将预筛选目标扩大到 12，
        #      防止边缘相关文件被错误过滤掉。
        _prefilter_top_k = 12 if file_ids and len(file_ids) > 50 else 8
        prefiltered_ids = _hierarchical_prefilter(
            query_text, project_id, top_k=_prefilter_top_k
        )
        if prefiltered_ids:
            file_ids = prefiltered_ids

    # ── 编码查询 ──
    _t1 = _t.time()
    print(f"⚙️ [PERF] prefilter: {_t1-_t0:.2f}s", flush=True)
    dense_model = _get_dense_model()
    query_dense = dense_model.encode(
        [query_text], normalize_embeddings=True
    )[0].tolist()
    _t2 = _t.time()
    print(f"⚙️ [PERF] dense_encode: {_t2-_t1:.2f}s", flush=True)
    query_sparse = _compute_sparse_vectors([query_text])[0]
    _t3 = _t.time()
    print(f"⚙️ [PERF] sparse_encode: {_t3-_t2:.2f}s", flush=True)

    # ── 构建过滤器 ──
    must_conditions = []
    if project_id:
        must_conditions.append(
            models.FieldCondition(
                key="project_id",
                match=models.MatchValue(value=project_id),
            )
        )
    if file_ids:
        if len(file_ids) == 1:
            must_conditions.append(
                models.FieldCondition(
                    key="file_id",
                    match=models.MatchValue(value=file_ids[0]),
                )
            )
        else:
            must_conditions.append(
                models.FieldCondition(
                    key="file_id",
                    match=models.MatchAny(any=file_ids),
                )
            )

    # WHY: 排除 doc_summary 类型的摘要 point，只检索正常内容 chunk
    must_not_conditions = [
        models.FieldCondition(
            key="chunk_type",
            match=models.MatchValue(value="doc_summary"),
        )
    ]

    query_filter = models.Filter(
        must=must_conditions if must_conditions else None,
        must_not=must_not_conditions,
    )

    # WHY: 动态候选池——Qdrant 多返回几十条记录的开销为毫秒级（实测 0.01s），
    #      但候选池过小会导致数字密集型表格切片（如灌溉用水定额表）
    #      因 Dense 分数偏低而被截断。最小 30 条候选确保表格数据不漏检。
    _n_files = len(file_ids) if file_ids else 0
    if _n_files > 50:
        fetch_limit = max(n_results * 6, 30)  # 数百份文件：扩大到 6x
    elif _n_files > 5:
        fetch_limit = max(n_results * 5, 30)  # 中等规模：5x
    else:
        fetch_limit = max(n_results * 4, 30)  # 少量文件：4x，最少 30 条

    # ── [Stage 2] 混合检索：Prefetch Dense + Sparse -> RRF Fusion ──
    try:
        results = client.query_points(
            collection_name=_collection_name,
            prefetch=[
                models.Prefetch(
                    query=query_dense,
                    using=_DENSE_VECTOR_NAME,
                    limit=fetch_limit,
                    filter=query_filter,
                ),
                models.Prefetch(
                    query=query_sparse,
                    using=_SPARSE_VECTOR_NAME,
                    limit=fetch_limit,
                    filter=query_filter,
                ),
            ],
            query=models.FusionQuery(
                fusion=models.Fusion.RRF
            ),
            limit=fetch_limit,
            with_payload=True,
        )
    except Exception as e:
        logger.error(f"Qdrant 混合检索失败: {e}")
        return []
    _t4 = _t.time()
    print(f"⚙️ [PERF] qdrant_search: {_t4-_t3:.2f}s | hits={len(results.points)}", flush=True)

    raw_docs = []
    for point in results.points:
        payload = point.payload or {}
        raw_docs.append({
            "content": payload.get("document", ""),
            "metadata": payload,
            "distance": point.score or 0.0,
        })

    if not raw_docs:
        return []

    from core.reranker import llm_rerank
    _RERANK_POOL = 15  # WHY: 恢复为 15，在保持高效率的同时，提供更宽泛的拼写偏差候选容灾

    # ── [Stage 2.5] 工程参数关键词强置顶 (Keyword Boosting) ──
    # WHY: 某些包含纯数据参数的 chunk，因为语句缺乏连贯性会被 Reranker 打低分。
    #      通过关键词拦截，强制将其抽出并在排序后置顶。
    _BOOST_KEYWORDS = {"高程", "标高", "管径", "坡比", "造价", "金额", "投资", "单价", "任务量", "指标", "定额"}
    boosted_docs = []
    normal_docs = []
    
    # 判断当前意图是否可能是查数据
    is_data_query = any(k in query_text for k in {"多少", "参数", "造价", "指标", "标准", "投资", "单价", "定额", "高程", "管径", "厚度", "深度"})
    
    if is_data_query:
        for doc in raw_docs[:_RERANK_POOL]:
            content = doc["content"]
            hit_count = sum(1 for k in _BOOST_KEYWORDS if k in content)
            # 如果文档包含数字并且命中了至少一个高价值工程词
            if hit_count >= 1 and any(char.isdigit() for char in content):
                # 再次校验查询词是否与内容有相关性（避免无脑置顶）
                # 要求 query 中的核心工程名词也在 chunk 中存在
                query_keywords = [k for k in _BOOST_KEYWORDS if k in query_text]
                if not query_keywords or any(qk in content for qk in query_keywords):
                    boosted_docs.append(doc)
                    continue
            normal_docs.append(doc)
    else:
        normal_docs = raw_docs[:_RERANK_POOL]

    if not normal_docs:  # 极端情况
        normal_docs = raw_docs[_RERANK_POOL:_RERANK_POOL+5]

    # ── [Stage 3] LLM Reranker 精排 ──
    # WHY: 原 CrossEncoder 在 ARM CPU 上 35-70s 不可接受。
    #      改用已常驻 GPU 的 qwen3.6 做排序，实测 ~1-4s，精度相当。
    #      只取 RRF 前 15 名送入 LLM，兼顾速度和召回率。
    #      超时/失败时自动降级为 RRF 原始排序。
    top_n_for_llm = max(n_results * 2 - len(boosted_docs), 1)
    reranked = llm_rerank(query_text, normal_docs, top_n=top_n_for_llm)
    
    if boosted_docs:
        print(f"🚀 [BOOST] 强制置顶 {len(boosted_docs)} 个参数数据 chunk!", flush=True)
        reranked = boosted_docs + reranked
    _t5 = _t.time()
    print(f"⚙️ [PERF] llm_reranker: {_t5-_t4:.2f}s", flush=True)

    # ── [Stage 4] 上下文增强 ──
    # WHY: 为每个命中 chunk 拉取前后相邻 chunk，补齐表格表头、
    #       脚注等被切片切断的上下文边界信息。
    expanded = _expand_context(reranked, window=1)

    # ── [Stage 5] 相邻合并 + 内容去重 ──
    docs = _merge_and_dedup(expanded, n_results)
    return docs



def _merge_and_dedup(docs: List[dict], n_results: int) -> List[dict]:
    """
    对检索结果进行相邻合并和内容去重。

    1. 相邻合并：同一文件中 chunk_index 连续的切片合并为一个连续文本块，
       保留最高分数作为该合并块的得分。
    2. 内容去重：如果两个 chunk 文本重叠度 > 70%，只保留得分更高的那个。

    WHY: 避免 LLM 的有限上下文窗口被冗余/重叠内容浪费。
         合并后每个 chunk 内容更完整，LLM 能看到完整段落而非碎片。
    """
    if not docs:
        return []

    # ── Step 1: 按 (file_id, chunk_index) 分组并排序 ──
    # 将同文件的 chunk 聚在一起，按 index 排序
    from collections import defaultdict

    file_groups: dict = defaultdict(list)
    for doc in docs:
        fid = doc["metadata"].get("file_id", "")
        idx = doc["metadata"].get("chunk_index", -1)
        file_groups[fid].append((idx, doc))

    merged: List[dict] = []

    for fid, items in file_groups.items():
        # 按 chunk_index 排序
        items.sort(key=lambda x: x[0])

        # 贪心合并：相邻 index（差 ≤ 1）的 chunk 合并
        current_indices = [items[0][0]]
        current_texts = [items[0][1]["content"]]
        current_best_score = items[0][1]["distance"]
        current_metadata = dict(items[0][1]["metadata"])

        for i in range(1, len(items)):
            prev_idx = current_indices[-1]
            curr_idx = items[i][0]

            if curr_idx - prev_idx <= 1 and curr_idx >= 0 and prev_idx >= 0:
                # 相邻，合并
                current_indices.append(curr_idx)
                current_texts.append(items[i][1]["content"])
                current_best_score = max(current_best_score, items[i][1]["distance"])
            else:
                # 不相邻，输出当前合并块，开始新的一组
                merged.append({
                    "content": "\n\n".join(current_texts),
                    "metadata": current_metadata,
                    "distance": current_best_score,
                })
                current_indices = [curr_idx]
                current_texts = [items[i][1]["content"]]
                current_best_score = items[i][1]["distance"]
                current_metadata = dict(items[i][1]["metadata"])

        # 最后一组
        merged.append({
            "content": "\n\n".join(current_texts),
            "metadata": current_metadata,
            "distance": current_best_score,
        })

    # ── Step 2: 按得分排序 ──
    merged.sort(key=lambda x: x["distance"], reverse=True)

    # ── Step 3: 内容去重（字符 3-gram Jaccard 相似度） ──
    # WHY: 单字符集 Jaccard 对中文短文本误判严重——常用字（的、了、是、在）
    #      大量重叠会导致完全不同的段落被误判为重复。
    #      改用 3-gram（三字滑窗）可以捕捉更多上下文信息，大幅降低误判率。
    def _trigrams(text: str) -> set:
        """将文本转为字符三元组集合。"""
        t = text.replace(" ", "").replace("\n", "")
        return {t[i:i+3] for i in range(len(t) - 2)} if len(t) >= 3 else {t}

    final: List[dict] = []
    for doc in merged:
        is_dup = False
        doc_grams = _trigrams(doc["content"])
        for accepted in final:
            accepted_grams = _trigrams(accepted["content"])
            intersection = len(doc_grams & accepted_grams)
            union = len(doc_grams | accepted_grams)
            if union > 0 and intersection / union > 0.6:
                is_dup = True
                break
        if not is_dup:
            final.append(doc)
        if len(final) >= n_results:
            break

    return final


def delete_by_file_id(file_id: str) -> int:
    """删除指定 file_id 在 Qdrant 中的所有向量切片。"""
    try:
        from core.database import delete_fts_by_file_id
        delete_fts_by_file_id(file_id)
        
        client = _get_client()
        count_filter = models.Filter(
            must=[
                models.FieldCondition(
                    key="file_id",
                    match=models.MatchValue(value=file_id),
                )
            ]
        )
        count_res = client.count(
            collection_name=_collection_name,
            count_filter=count_filter,
        )
        count = count_res.count
 
        if count > 0:
            client.delete(
                collection_name=_collection_name,
                points_selector=models.FilterSelector(filter=count_filter),
            )
            logger.info(f"🗑️ 已删除 file_id={file_id} 的 {count} 个向量切片")
        return count
    except Exception as e:
        logger.error(f"删除 Qdrant file_id={file_id} 失败: {e}")
        return 0
 
 
def delete_by_project_id(project_id: str) -> int:
    """删除指定 project_id 在 Qdrant 中的所有向量切片。"""
    try:
        from core.database import delete_fts_by_project_id
        delete_fts_by_project_id(project_id)
        
        client = _get_client()
        count_filter = models.Filter(
            must=[
                models.FieldCondition(
                    key="project_id",
                    match=models.MatchValue(value=project_id),
                )
            ]
        )
        count_res = client.count(
            collection_name=_collection_name,
            count_filter=count_filter,
        )
        count = count_res.count
 
        if count > 0:
            client.delete(
                collection_name=_collection_name,
                points_selector=models.FilterSelector(filter=count_filter),
            )
            logger.info(f"🗑️ 已删除 project_id={project_id} 的 {count} 个向量切片")
        return count
    except Exception as e:
        logger.error(f"删除 Qdrant project_id={project_id} 失败: {e}")
        return 0



def get_collection_stats() -> dict:
    """获取当前集合的统计信息。"""
    try:
        client = _get_client()
        count_res = client.count(collection_name=_collection_name)
        return {
            "name": _collection_name,
            "count": count_res.count,
        }
    except Exception as e:
        logger.error(f"获取集合统计失败: {e}")
        return {"name": _collection_name, "count": 0, "error": str(e)}


def get_file_metadata_multi_level(
    file_ids: List[str], current_project_id: str = ""
) -> Dict[str, Dict[str, Any]]:
    """
    通过 JSON -> SQLite -> Qdrant 三级反查机制获取每个 file_id 的 filename 和 project_id。
    返回格式: {file_id: {"project_id": project_id, "filename": filename}}
    """
    if not file_ids:
        return {}

    result = {}
    remaining_fids = list(file_ids)

    # 1. 优先从项目本地 documents 目录的 JSON 读元数据
    if current_project_id:
        try:
            from core.config import settings
            from pathlib import Path
            import json
            doc_dir = Path(settings.DATA_DIR) / "documents" / current_project_id
            if doc_dir.exists():
                for fid in list(remaining_fids):
                    fp = doc_dir / f"{fid}.json"
                    if fp.exists():
                        try:
                            data = json.loads(fp.read_text(encoding="utf-8"))
                            title = data.get("title") or data.get("filename")
                            if title:
                                result[fid] = {
                                    "project_id": current_project_id,
                                    "filename": title
                                }
                                remaining_fids.remove(fid)
                        except Exception:
                            pass
        except Exception:
            pass

    # 2. 从 SQLite 数据库中反查
    if remaining_fids:
        try:
            from core.database import get_db
            with get_db() as conn:
                placeholders = ",".join(["?"] * len(remaining_fids))
                rows = conn.execute(
                    f"SELECT DISTINCT file_id, project_id, filename FROM doc_chunks_fts WHERE file_id IN ({placeholders})",
                    remaining_fids
                ).fetchall()
                for row in rows:
                    fid = row["file_id"]
                    if fid not in result:
                        result[fid] = {
                            "project_id": row["project_id"] or "",
                            "filename": row["filename"] or ""
                        }
                        if fid in remaining_fids:
                            remaining_fids.remove(fid)
        except Exception as e:
            logger.warning(f"从 FTS 库获取文件名失败: {e}")

    # 3. 从 Qdrant 中反查
    if remaining_fids:
        try:
            client = _get_client()
            scroll_filter = models.Filter(
                must=[
                    models.FieldCondition(
                        key="file_id",
                        match=models.MatchAny(any=remaining_fids),
                    )
                ]
            )
            batch, _ = client.scroll(
                collection_name=_collection_name,
                scroll_filter=scroll_filter,
                limit=len(remaining_fids) * 5,
                with_vectors=False,
                with_payload=True,
            )
            for pt in batch:
                pld = pt.payload or {}
                fid = pld.get("file_id")
                if fid and fid not in result:
                    result[fid] = {
                        "project_id": pld.get("project_id", ""),
                        "filename": pld.get("filename", ""),
                    }
                    if fid in remaining_fids:
                        remaining_fids.remove(fid)
        except Exception as e:
            logger.warning(f"从 Qdrant 反查元数据失败: {e}")

    return result


def get_chunk_count(file_id: str) -> int:
    """查询指定 file_id 的切片数量。"""
    try:
        client = _get_client()
        count_filter = models.Filter(
            must=[
                models.FieldCondition(
                    key="file_id",
                    match=models.MatchValue(value=file_id),
                )
            ]
        )
        count_res = client.count(
            collection_name=_collection_name,
            count_filter=count_filter,
        )
        return count_res.count
    except Exception as e:
        logger.error(f"查询切片数量失败 (file_id={file_id}): {e}")
        return 0


def get_project_chunk_count(project_id: str) -> int:
    """查询指定 project_id 的切片总数量。"""
    try:
        client = _get_client()
        count_filter = models.Filter(
            must=[
                models.FieldCondition(
                    key="project_id",
                    match=models.MatchValue(value=project_id),
                )
            ]
        )
        count_res = client.count(
            collection_name=_collection_name,
            count_filter=count_filter,
        )
        return count_res.count
    except Exception as e:
        logger.error(f"查询项目切片数量失败 (project_id={project_id}): {e}")
        return 0


def get_all_chunks(file_id: str, limit: int = 500) -> List[str]:
    """
    提取指定 file_id 的全部 chunk 文本，按 chunk_index 排序。
    WHY: 网络/粘贴来源没有磁盘文件，预览时需要从向量库反查全文。
    """
    try:
        client = _get_client()
        scroll_filter = models.Filter(
            must=[
                models.FieldCondition(
                    key="file_id",
                    match=models.MatchValue(value=file_id),
                )
            ]
        )
        results, _next = client.scroll(
            collection_name=_collection_name,
            scroll_filter=scroll_filter,
            limit=limit,
            with_payload=True,
        )

        chunks = []
        for point in results:
            payload = point.payload or {}
            text = payload.get("document", "")
            idx = payload.get("chunk_index", 999)
            chunks.append((idx, text))

        chunks.sort(key=lambda x: x[0])
        return [text for _, text in chunks if text]
    except Exception as e:
        logger.error(f"提取全部 chunk 失败 (file_id={file_id}): {e}")
        return []


def get_all_chunks_with_payload(file_id: str, limit: int = 500) -> List[dict]:
    """
    提取指定 file_id 的全部 chunk 及其完整 payload，按 chunk_index 排序。
    """
    try:
        client = _get_client()
        scroll_filter = models.Filter(
            must=[
                models.FieldCondition(
                    key="file_id",
                    match=models.MatchValue(value=file_id),
                )
            ]
        )
        results, _next = client.scroll(
            collection_name=_collection_name,
            scroll_filter=scroll_filter,
            limit=limit,
            with_payload=True,
        )

        chunks = []
        for point in results:
            payload = point.payload or {}
            idx = payload.get("chunk_index", 999)
            chunks.append((idx, payload))

        chunks.sort(key=lambda x: x[0])
        return [payload for _, payload in chunks]
    except Exception as e:
        logger.error(f"提取全部 chunk payload 失败 (file_id={file_id}): {e}")
        return []



def verify_numbers(
    generated_text: str,
    rag_context: str,
    graph_context: str = "",
    slot_table: list = None,
    exemplar_content: str = "",
) -> List[dict]:
    """
    多源感知数值校验器——Self-RAG 的轻量级规则替代。

    WHY: LLM 生成报告时可能捏造数值（幻觉）。通过将生成文本中的
         数值与全部数据源的数值池做差集，标记「大数值 + 全源未覆盖」
         的可疑项，供前端展示"建议复核"提示。

    策略：
    1. 合并 RAG 上下文、图谱路径、Slot 映射表新值、范文底稿的所有数值
    2. 白名单过滤序号(0-31)、年份(1990-2035)、常见整数
    3. 仅标记 ≥10 的可疑大数值（小数值大概率是序号/百分比）
    4. 最多返回 3 个最大的可疑值，避免告警泛滥
    """
    all_sources = f"{rag_context} {graph_context} {exemplar_content}"
    if slot_table:
        all_sources += " " + " ".join(
            s.get("new", "") for s in slot_table if isinstance(s, dict)
        )

    source_nums = set(re.findall(r'\d+\.?\d*', all_sources))
    gen_nums = set(re.findall(r'\d+\.?\d*', generated_text))

    # WHY: 白名单覆盖常见无害数值，大幅降低误报率
    whitelist = {str(i) for i in range(32)}       # 序号/编号
    whitelist |= {str(y) for y in range(1990, 2035)}  # 年份
    whitelist |= {'100', '1000', '10000'}         # 常见整数

    suspicious = []
    for num_str in gen_nums - source_nums - whitelist:
        try:
            val = float(num_str)
            if val < 10:
                continue
            suspicious.append({
                "value": num_str,
                "severity": "high" if val > 1000 else "medium",
            })
        except ValueError:
            continue

    return sorted(suspicious, key=lambda x: -float(x["value"]))[:3]
