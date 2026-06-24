"""
表格注册表——完整表格的存储、检索与管理。
WHY: 大型统计表格被 chunk_size=512 的切片器打碎后，LLM 无法还原。
     本模块将每张表格作为完整实体存储在本地 JSON 中，同时在 Qdrant 中
     建立标题+表头的语义索引。在报告生成时通过语义匹配直接注入完整
     Markdown 表格，绕开 LLM 的"重新生成"环节，实现零损耗直插入。
"""
from __future__ import annotations

import json
import logging
import uuid
from pathlib import Path
from typing import List

from .config import settings
from .vector_store import (
    _get_client, _get_dense_model, _compute_sparse_vectors,
    ensure_collection, _collection_name,
    _DENSE_VECTOR_NAME, _SPARSE_VECTOR_NAME,
)
from qdrant_client import models

logger = logging.getLogger(__name__)

# 表格注册表的本地存储目录
_TABLE_DIR = Path(settings.DATA_DIR) / "tables"


def _table_dir(project_id: str) -> Path:
    """返回项目级表格存储目录，不存在则创建。"""
    d = _TABLE_DIR / project_id
    d.mkdir(parents=True, exist_ok=True)
    return d


def _table_point_id(file_id: str, table_idx: int) -> str:
    """为表格索引向量生成稳定的 UUID。"""
    return str(uuid.uuid5(uuid.NAMESPACE_OID, f"{file_id}__table_{table_idx}"))


def _generate_table_summary(title: str, markdown: str) -> str:
    """调用本地 LLM 异步/同步生成表格的语义摘要，用于增强表格检索的语义空间。"""
    from core.config import settings
    import requests
    import re
    
    prompt = f"""请简要总结以下表格的结构和数据内容。用一句话概括：该表是一张关于什么的表格，包含哪些核心字段和数据类型。
表格标题：{title}
表格内容（部分）：
{markdown[:2000]}

仅输出总结的一句话，不要解释，不要输出“根据表格”等废话。"""

    payload = {
        "model": "qwen3.6:35b-q4",
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": 0.1,
            "num_predict": 150,
        }
    }
    url = f"{settings.OLLAMA_BASE_URL}/api/generate"
    try:
        # WHY: 缩短请求超时时间到 15s，防止在 Ollama 队列拥堵时无限死等导致 Celery 任务软超时
        resp = requests.post(url, json=payload, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        summary = data.get("response", "").strip()
        # 清除模型可能输出的 <think> 标签
        summary = re.sub(r'<think>.*?</think>', '', summary, flags=re.DOTALL).strip()
        return summary
    except Exception as e:
        logger.warning(f"表格摘要生成失败: {e}")
        return ""



def register_tables(
    tables: List[dict],
    file_id: str,
    filename: str,
    project_id: str = "default",
) -> int:
    """
    将提取到的表格列表注册到本地 JSON + Qdrant 向量索引。
    返回成功注册的表格数量。
    """
    if not tables:
        return 0

    # ── 1. 存储到本地 JSON ──
    storage = {
        "file_id": file_id,
        "filename": filename,
        "tables": [],
    }
    for i, t in enumerate(tables):
        table_id = f"{file_id}__table_{i}"
        entry = {
            "table_id": table_id,
            **t,
        }
        storage["tables"].append(entry)

    out_path = _table_dir(project_id) / f"{file_id}.json"
    out_path.write_text(json.dumps(storage, ensure_ascii=False, indent=2), encoding="utf-8")

    # ── 2. 写入 Qdrant 向量索引（标题 + 表头作为检索文本）──
    client = _get_client()
    ensure_collection()

    # WHY: 对于已存在的 collection，chunk_type 索引是新增字段，需安全补建
    try:
        client.create_payload_index(
            collection_name=_collection_name,
            field_name="chunk_type",
            field_schema=models.PayloadSchemaType.KEYWORD,
        )
    except Exception:
        pass  # 索引已存在则忽略

    dense_model = _get_dense_model()

    index_texts = []
    points = []
    for i, t in enumerate(tables):
        # WHY: 限制单个文档中进行 LLM 摘要生成的表格数量上限为 15，
        #      对于 >15 张表的超大 Excel / PDF，后续表格跳过大模型调用直接使用空摘要。
        #      因为标题、表头和数据行采样依然会被写入向量索引，不影响检索效果，同时能绝对避免 Celery 任务软超时。
        if i >= 15:
            summary = ""
        else:
            summary = _generate_table_summary(t['title'], t['markdown'])
        # WHY: 数据行采样 — 将前 15 行前 8 列的关键值注入 search_text。
        #      仅靠标题+表头做向量检索时，附件5等文件名无法覆盖行级术语
        #      （如"耕作层剥离和回填"），导致 RRF 得分低于 0.35 被丢弃。
        #      注入数据行后，BGE-M3 可直接匹配行级关键词。
        #      之前 sample_cols=3 导致宽表格（如 8 列的耕地现状统计表）后 5 列丢失。
        data_sample = ""
        rows = t.get('rows', [])
        import re
        code_pattern = re.compile(r'[a-zA-Z]?\d+\+\d+(?:\.\d+)?|(?:(?=[a-zA-Z0-9_-]*[a-zA-Z])(?=[a-zA-Z0-9_-]*\d)[a-zA-Z0-9_-]{4,20})')
        extracted_codes = set()
        
        if rows:
            sample_cols = min(8, len(t.get('headers', [])))
            sample_vals = []
            for row_idx, row in enumerate(rows):
                for v in row:
                    if v is not None:
                        s_val = str(v).strip()
                        if s_val and len(extracted_codes) < 50:
                            extracted_codes.update(code_pattern.findall(s_val))
                            
                if row_idx < 15:
                    vals = [str(v).strip() for v in row[:sample_cols]
                            if v is not None and str(v).strip()]
                    if vals:
                        sample_vals.append(' '.join(vals))
            
            data_sample_parts = []
            if sample_vals:
                _data_row_text = ' | '.join(sample_vals[:10])
                # WHY: 限制总字符数防止 chunk 过长（sample_cols 增大后单行更长）
                if len(_data_row_text) > 1200:
                    _data_row_text = _data_row_text[:1200] + '...'
                data_sample_parts.append("\n数据行: " + _data_row_text)
            if extracted_codes:
                data_sample_parts.append("\n特征码: " + ' '.join(list(extracted_codes)[:50]))
            data_sample = "".join(data_sample_parts)
        file_basename = Path(filename).stem
        if summary:
            logger.info(f"生成表格摘要: {t['title']} -> {summary[:50]}...")
            # 用标题 + 表头 + 数据行采样 + LLM 摘要合并为检索文本，并追加文件名增强语义
            search_text = f"{t['title']} {' '.join(t['headers'])}{data_sample}\n摘要: {summary}\n来源文件: {file_basename}"
        else:
            # 用标题 + 表头 + 数据行采样合并为检索文本
            search_text = f"{t['title']} {' '.join(t['headers'])}{data_sample}\n来源文件: {file_basename}"
        
        index_texts.append(search_text)

    if not index_texts:
        return 0

    # Dense 编码
    dense_vecs = dense_model.encode(
        index_texts, show_progress_bar=False, normalize_embeddings=True, batch_size=8,
    )
    dense_vecs = [v.tolist() for v in dense_vecs]

    # Sparse 编码
    sparse_vecs = _compute_sparse_vectors(index_texts)

    for i, t in enumerate(tables):
        table_id = f"{file_id}__table_{i}"
        point_id = _table_point_id(file_id, i)
        points.append(
            models.PointStruct(
                id=point_id,
                vector={
                    _DENSE_VECTOR_NAME: dense_vecs[i],
                    _SPARSE_VECTOR_NAME: sparse_vecs[i],
                },
                payload={
                    "document": index_texts[i],
                    "file_id": file_id,
                    "filename": filename,
                    "project_id": project_id,
                    "chunk_type": "table_index",
                    "table_id": table_id,
                    "table_title": t["title"],
                    "row_count": t["row_count"],
                    "char_count": t["char_count"],
                },
            )
        )

    try:
        client.upsert(collection_name=_collection_name, points=points)
    except Exception as e:
        logger.error(f"[表格注册] Qdrant 写入失败: {e}")
        return 0

    logger.info(
        f"[表格注册] {filename}: 注册 {len(tables)} 张表格 "
        f"(本地JSON + Qdrant向量索引)"
    )
    return len(tables)


def query_tables(
    query_text: str,
    project_id: str,
    file_ids: List[str] = None,
    max_tables: int = 2,
    score_threshold: float = 0.35,
    exclude_table_ids: List[str] = None,
) -> List[dict]:
    """
    按章节标题语义检索匹配的完整表格。
    返回 List[dict]，每个 dict 包含 title, markdown, row_count, source_file, table_id, score。

    WHY: 用 Qdrant 的混合检索匹配表格标题+表头，
         命中后从本地 JSON 读取完整 Markdown，实现零损耗直插入。

    参数:
        score_threshold: 最低匹配分数门槛，低于此值的结果直接丢弃。
                         RRF 融合的分数通常在 0.0~1.0 之间，0.35 为保守阈值。
        exclude_table_ids: 已在前序章节注入过的 table_id 列表，
                           命中则跳过，防止同表在相邻章节重复出现。
    """
    if exclude_table_ids is None:
        exclude_table_ids = []

    client = _get_client()
    ensure_collection()
    dense_model = _get_dense_model()

    # 编码查询
    query_dense = dense_model.encode(
        [query_text], normalize_embeddings=True
    )[0].tolist()
    query_sparse = _compute_sparse_vectors([query_text])[0]

    # 构建过滤器：必须是 table_index 类型 + 项目匹配
    must_conditions = [
        models.FieldCondition(
            key="chunk_type",
            match=models.MatchValue(value="table_index"),
        ),
    ]
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

    query_filter = models.Filter(must=must_conditions)

    # WHY: 多取一些候选（max_tables * 4），后续用分数门槛和去重过滤
    fetch_limit = max(max_tables * 4, 8)

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
            query=models.FusionQuery(fusion=models.Fusion.RRF),
            limit=fetch_limit,
            with_payload=True,
        )
    except Exception as e:
        logger.error(f"[表格检索] Qdrant 查询失败: {e}")
        return []

    # 从本地 JSON 读取完整 Markdown，同时应用分数门槛 + 去重
    matched = []
    skipped_low_score = 0
    skipped_duplicate = 0

    for point in results.points:
        # ── 分数门槛过滤 ──
        score = point.score or 0.0
        if score < score_threshold:
            skipped_low_score += 1
            continue

        payload = point.payload or {}
        table_id = payload.get("table_id", "")
        file_id = payload.get("file_id", "")
        pid = payload.get("project_id", "default")

        # ── 跨章节去重 ──
        if table_id in exclude_table_ids:
            skipped_duplicate += 1
            continue

        json_path = _table_dir(pid) / f"{file_id}.json"
        if not json_path.exists():
            continue

        try:
            data = json.loads(json_path.read_text(encoding="utf-8"))
            for t in data.get("tables", []):
                if t.get("table_id") == table_id:
                    matched.append({
                        "title": t["title"],
                        "markdown": t["markdown"],
                        "row_count": t["row_count"],
                        "source_file": t["source_file"],
                        "table_id": table_id,
                        "score": score,
                    })
                    break
        except Exception as e:
            logger.warning(f"[表格检索] 读取本地JSON失败: {e}")

        # 达到所需数量就停止
        if len(matched) >= max_tables:
            break

    logger.info(
        f"[表格检索] query='{query_text[:40]}' → "
        f"命中 {len(matched)} 张表格 "
        f"(丢弃: {skipped_low_score}低分 + {skipped_duplicate}重复)"
    )
    return matched


def delete_tables(file_id: str, project_id: str = "default") -> int:
    """
    删除指定 file_id 的所有注册表格（本地 JSON + Qdrant 向量）。
    WHY: 当用户删除或重新上传文件时，需要同步清理旧的表格注册。
    """
    # 删除本地 JSON
    json_path = _table_dir(project_id) / f"{file_id}.json"
    if json_path.exists():
        json_path.unlink()

    # 删除 Qdrant 中的 table_index 向量
    try:
        client = _get_client()
        client.delete(
            collection_name=_collection_name,
            points_selector=models.FilterSelector(
                filter=models.Filter(
                    must=[
                        models.FieldCondition(
                             key="file_id",
                            match=models.MatchValue(value=file_id),
                        ),
                        models.FieldCondition(
                            key="chunk_type",
                            match=models.MatchValue(value="table_index"),
                        ),
                    ]
                )
            ),
        )
        return 1
    except Exception as e:
        logger.error(f"[表格注册] 删除失败: {e}")
        return 0


def get_all_tables(
    project_id: str,
    file_ids: List[str] = None,
) -> List[dict]:
    """
    获取项目下的所有完整表格（不走向量检索，直接读本地 JSON）。

    WHY: 统计/聚合类问题需要遍历全量数据（如"总共有多少地块"），
         向量检索的 top_k 无法覆盖全部表格。
         本函数直接从文件系统读取完整表格，供程序化计算使用。

    返回: List[dict]，每个 dict 包含 title, markdown, row_count, source_file。
    """
    table_dir = _table_dir(project_id)
    results = []

    for json_path in sorted(table_dir.glob("*.json")):
        try:
            data = json.loads(json_path.read_text(encoding="utf-8"))
        except Exception:
            continue

        # 按 file_ids 过滤（如果指定了）
        fid = data.get("file_id", "")
        if file_ids and fid and fid not in file_ids:
            continue

        # WHY: JSON 结构是 {file_id, filename, tables: [{title, markdown, ...}]}
        #      每个文件可能包含多张表（多个 sheet），需遍历 tables 数组。
        for tbl in data.get("tables", []):
            results.append({
                "title": tbl.get("title", ""),
                "markdown": tbl.get("markdown", ""),
                "row_count": tbl.get("row_count", 0),
                "source_file": tbl.get("source_file", data.get("filename", "")),
                "columns": tbl.get("headers", []),
            })

    return results


def load_tables_as_dataframes(
    project_id: str,
    file_ids: List[str] = None,
) -> List[dict]:
    """
    将项目下的全部表格加载为 pandas DataFrame。

    WHY: DuckDB 数据分析引擎需要 DataFrame 来注册为内存表。
         直接使用 JSON 中已保存的 headers + rows 构建，
         不重新解析原始 Excel 文件，性能更好。

    表名规则: t_{file_id前6位}_{sheet序号}
    - 避免中文表名导致 SQL 语法错误
    - 多 Sheet 注册为独立表，支持 JOIN/UNION 跨 Sheet 查询

    Returns: List[dict]，每个 dict 包含：
        table_name: DuckDB 表名
        display_name: 原始中文标题
        source_file: 来源文件名
        sheet_name: Sheet 名
        df: pd.DataFrame
        row_count: 数据行数
    """
    import pandas as pd

    table_dir = _table_dir(project_id)
    results = []

    for json_path in sorted(table_dir.glob("*.json")):
        try:
            data = json.loads(json_path.read_text(encoding="utf-8"))
        except Exception:
            continue

        fid = data.get("file_id", "")
        if file_ids and fid and fid not in file_ids:
            continue

        fid_short = fid[:6] if fid else json_path.stem[:6]

        for idx, tbl in enumerate(data.get("tables", [])):
            headers = tbl.get("headers", [])
            rows = tbl.get("rows", [])

            if not headers or not rows:
                continue

            # WHY: 跳过只有 1~2 行的微型表格（通常是标题页/签名页）
            if len(rows) < 3:
                continue

            # 构建 DataFrame
            try:
                df = pd.DataFrame(rows, columns=headers)
            except Exception:
                # 列数不匹配时截断或补齐
                try:
                    trimmed = [r[:len(headers)] for r in rows]
                    df = pd.DataFrame(trimmed, columns=headers)
                except Exception:
                    continue

            # WHY: 自动尝试将数值列转为数字类型，使 SUM/AVG 等聚合正确
            for col in df.columns:
                converted = pd.to_numeric(df[col], errors="coerce")
                # WHY: 仅当超过半数为有效数字时才转换，避免文本列被强制置 NaN
                if converted.notna().sum() > len(df) * 0.5:
                    df[col] = converted

            # 生成 DuckDB 安全表名
            table_name = f"t_{fid_short}_{idx}"

            results.append({
                "table_name": table_name,
                "display_name": tbl.get("title", f"表格_{idx}"),
                "source_file": tbl.get(
                    "source_file", data.get("filename", ""),
                ),
                "sheet_name": tbl.get("sheet_name", ""),
                "df": df,
                "row_count": len(df),
                "merged_cols": tbl.get("merged_cols", []),
            })

    return results


# ── 表名归一化匹配（Clone 模式专用） ──────────────────────


def _normalize_table_name(name: str) -> str:
    """
    去掉地名和编号，提取核心表名关键词。
    WHY: 范文表名「西充县各基本评价单元主要农产品年产量统计表」
         与资料库「蓬溪县各区片行政村（社区）主要农产品年产量统计表」
         只是地名不同，核心词「主要农产品年产量统计表」完全一致。
         去掉地名和编号后做模糊匹配即可命中。
    """
    import re
    # 1. 去掉表格编号前缀 (表1-1, 表19, 续表5-11, etc.)
    name = re.sub(r'^[续附]?表[\d\-\.]*\s*', '', name)
    # 2. 去掉地名 (XX省/市/县/区/镇/乡/村/街道/社区)
    name = re.sub(
        r'[\u4e00-\u9fa5]{1,8}(?:省|市|县|区|镇|乡|村|街道|社区)',
        '', name,
    )
    # 3. 去掉括号内的补充说明（如「（社区）」「（亩）」）
    name = re.sub(r'[（(][^）)]*[）)]', '', name)
    # 4. 去掉多余空白
    name = re.sub(r'\s+', '', name)
    return name.strip()


def match_tables_by_name(
    exemplar_table_names: List[str],
    project_id: str,
    file_ids: List[str] = None,
    similarity_threshold: float = 0.55,
) -> dict:
    """
    根据范文中的表名，在资料库中按名称匹配表格。
    WHY: Clone 模式下范文表格需要被资料库的同类表格直接替换。
         语义检索对表名匹配不够精准（表名短且高度结构化），
         用字符串相似度做归一化匹配更可靠。

    参数:
        exemplar_table_names: 范文中提取的表名列表
        project_id: 项目 ID
        file_ids: 可选的文件 ID 过滤
        similarity_threshold: 归一化表名的最低相似度（0~1）

    返回:
        dict: {范文表名: {title, markdown, source_file, match_score, ...}}
        仅包含成功匹配的表名。
    """
    from difflib import SequenceMatcher

    all_tables = get_all_tables(project_id, file_ids)
    if not all_tables:
        return {}

    # 预计算资料库所有表格的归一化名称
    norm_cache = []
    for tbl in all_tables:
        norm = _normalize_table_name(tbl['title'])
        if norm and len(norm) >= 3:
            norm_cache.append((norm, tbl))

    results = {}
    used_indices = set()  # 防止同一张资料表被多次匹配

    for ex_name in exemplar_table_names:
        norm_ex = _normalize_table_name(ex_name)
        if not norm_ex or len(norm_ex) < 3:
            continue

        best_idx = -1
        best_score = 0.0
        best_tbl = None

        for idx, (norm_tbl, tbl) in enumerate(norm_cache):
            if idx in used_indices:
                continue
            score = SequenceMatcher(None, norm_ex, norm_tbl).ratio()
            if score > best_score:
                best_score = score
                best_idx = idx
                best_tbl = tbl

        if best_tbl and best_score >= similarity_threshold:
            used_indices.add(best_idx)
            results[ex_name] = {
                **best_tbl,
                'match_score': best_score,
            }
            logger.info(
                f"[表名匹配] '{ex_name}' → '{best_tbl['title']}' "
                f"(score={best_score:.2f})"
            )

    logger.info(
        f"[表名匹配] 输入 {len(exemplar_table_names)} 个范文表名, "
        f"命中 {len(results)} 个"
    )
    return results
