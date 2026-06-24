"""
DuckDB 全量数据精确分析引擎。

WHY: RAG 架构的 context 窗口无法容纳 1000+ 行的完整表格，
     导致全表聚合/统计类问题无法精确回答。
     本模块将 Excel 数据加载到 DuckDB 内存数据库，
     让 LLM 生成 SQL → 程序精确执行 → 结果注入 context。

设计：
- 数据来源：table_registry JSON 中已保存的 headers + rows
- 多 Sheet 支持：每个 Sheet 注册为独立 DuckDB 表
- SQL 安全：白名单关键词 + 只允许 SELECT
- 借鉴 DeepParseX analyze_data_with_ai 架构
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Optional

import duckdb
import pandas as pd

from core.config import settings

logger = logging.getLogger(__name__)

# WHY: SQL 生成仅需输出 ≤100 tokens 的结构化语句，8B 小模型完全胜任，
#      推理速度比 35B 快 10x（30-50 tok/s vs 3-5 tok/s）。
_SQL_MODEL = settings.DEFAULT_LLM_MODEL
_SQL_NUM_CTX = 4096  # SQL prompt 通常 ≤2K 字符，4K 上下文已足够


# ── 分析结果容器 ─────────────────────────────────────────

@dataclass
class DataAnalysisResult:
    """DuckDB 数据分析结果。"""
    sql: str = ""
    result_text: str = ""
    result_table: str = ""
    row_count: int = 0
    tables_used: list = field(default_factory=list)
    error: Optional[str] = None


# ── SQL 安全校验 ──────────────────────────────────────────

_FORBIDDEN_KEYWORDS = re.compile(
    r'\b(DROP|DELETE|INSERT|UPDATE|ALTER|CREATE|TRUNCATE|'
    r'EXEC|EXECUTE|GRANT|REVOKE|COPY|EXPORT|IMPORT|ATTACH)\b',
    re.IGNORECASE,
)


def _validate_sql(sql: str) -> Optional[str]:
    """
    校验 SQL 安全性。

    Returns: 错误信息（如果不安全），None 表示安全。
    """
    cleaned = sql.strip().rstrip(';')

    if not cleaned.upper().startswith('SELECT'):
        return "SQL 必须以 SELECT 开头"

    match = _FORBIDDEN_KEYWORDS.search(cleaned)
    if match:
        return f"SQL 包含禁止关键词: {match.group()}"

    return None


# ── Schema 摘要构建 ───────────────────────────────────────

def _build_schema_summary(
    table_infos: list[dict],
) -> str:
    """
    构建精简的 Schema 摘要供 LLM 生成 SQL。

    WHY: LLM 只需要看列名 + 类型 + 几行样本就能写出正确 SQL，
         无需看到全部数据行。这样 prompt ≈ 500~2000 字符，
         远小于直接注入 192K 字符的 Markdown。
    """
    parts = []

    for info in table_infos:
        df: pd.DataFrame = info["df"]
        tbl_name = info["table_name"]
        display = info["display_name"]
        source = info["source_file"]
        sheet = info.get("sheet_name", "")

        # WHY: 寻找可作为分组去重键的列（地块编号、序号等）
        group_by_candidates = [
            c for c in df.columns
            if any(kw in c for kw in ("地块", "编号", "名称"))
        ]
        if not group_by_candidates:
            group_by_candidates = [
                c for c in df.columns if "序号" in c
            ]
        group_by_tip = (
            group_by_candidates[0] if group_by_candidates
            else "整治地块编号"
        )

        # WHY: 自动检测合并单元格导致的重复值列。
        #      两种来源：1) 元数据中的 merged_cols 字段（新数据）
        #               2) 运行时数据分析（旧数据兼容）
        #      当数值列的唯一值占比 < 30% 且存在分组键，
        #      说明该列的值被合并单元格复制到了多行。
        explicit_merged = set(info.get("merged_cols", []))
        detected_merged: set[str] = set()

        if len(df) >= 10:  # 仅对足够大的表做检测
            group_by_col = group_by_candidates[0] if group_by_candidates else None
            for col in df.columns:
                dtype = str(df[col].dtype)
                is_numeric = any(
                    t in dtype for t in ("float", "int", "double", "num")
                )
                if not is_numeric:
                    continue
                if col in group_by_candidates:
                    continue  # 分组键本身不标记

                non_null = df[col].notna().sum()
                if non_null < 10:
                    continue

                n_unique = df[col].nunique()
                # WHY: 唯一值占比 < 30% 说明全局大量重复（合并单元格填充）
                if n_unique / non_null < 0.3:
                    # 进一步校验：检查分组键内的值变化情况，以防将取值类型较少的分类属性列（如田坎宽度、高度）误判
                    if group_by_col:
                        grouped_nunique = df.groupby(group_by_col)[col].nunique()
                        valid_groups = grouped_nunique[grouped_nunique > 0]
                        if len(valid_groups) > 0:
                            single_value_ratio = (valid_groups == 1).sum() / len(valid_groups)
                            # 90% 以上的分组内其非空数值都是唯一的，说明确实是合并单元格
                            if single_value_ratio >= 0.9:
                                detected_merged.add(col)
                        else:
                            detected_merged.add(col)
                    else:
                        detected_merged.add(col)

        all_merged = explicit_merged | detected_merged

        # 列信息
        col_lines = []
        for col in df.columns:
            dtype = str(df[col].dtype)
            non_null = df[col].notna().sum()

            if col in all_merged:
                col_lines.append(
                    f'    {col} ({dtype}, {non_null}行有值, '
                    f'[⚠️注意: 此列为合并单元格值重复填充，'
                    f'直接SUM/AVG统计会放大，'
                    f'必须先按 "{group_by_tip}" 分组并使用'
                    f' FIRST() 去重后再进行聚合计算])'
                )
            else:
                col_lines.append(f"    {col} ({dtype}, {non_null}行有值)")

        # 前 5 行样本
        sample_md = df.head(5).to_markdown(index=False)

        part = (
            f"### 表: {tbl_name}\n"
            f"  显示名称: {display}\n"
            f"  来源文件: {source}\n"
            f"  Sheet: {sheet}\n"
            f"  行数: {len(df)}, 列数: {len(df.columns)}\n"
            f"  列定义:\n" + "\n".join(col_lines) + "\n"
            f"  前5行样本:\n{sample_md}\n"
        )
        parts.append(part)

    return "\n".join(parts)


# ── SQL 生成 Prompt ───────────────────────────────────────

_SQL_SYSTEM_PROMPT = """你是一个专业的 SQL 数据分析专家。根据用户问题和数据表结构，生成 DuckDB SQL 查询语句。

规则：
1. 只返回一条 SQL 语句，不要包含解释
2. SQL 必须以 SELECT 开头
3. 使用 DuckDB 语法（兼容标准 SQL）
4. 列名包含中文或特殊字符时用双引号包裹，如 "面积(亩)"
5. 聚合函数：COUNT、SUM、AVG、MIN、MAX
6. 分组使用 GROUP BY，排序使用 ORDER BY
7. 数值列可能存储为 VARCHAR，需要 CAST("列名" AS DOUBLE) 转换后再计算
8. ⚠️列名精确对应：表中可能存在多个含有“面积”或“长度”等相似字眼的列名（例如“预计新增耕地面积”、“图斑面积”、“整治区面积”等），必须**仔细甄别并完全精准对应**用户问题中所指的业务指标，绝对不能混淆或选错列名。
9. 如果表中有"合计"/"总计"/"小计"行，在统计时要排除这些行。
10. ⚠️重要：若对非 VARCHAR 类型（如双精度浮点数 double/float 或整型 int/bigint 的列）使用 LIKE/NOT LIKE 进行“合计”过滤，必须显式先将列 CAST 为 VARCHAR，例如 `CAST("数值列" AS VARCHAR) NOT LIKE '%合计%'`；或者直接对其他文本型列进行过滤。
11. ⚠️合并单元格去重：如果列定义中标注了"⚠️注意: 此列为合并单元格值重复填充"，说明该列的值被 Excel 合并单元格复制到了多行。对这种列做 SUM/AVG/COUNT 前，必须先用子查询按指定的分组列做 FIRST() 去重。示例：`SELECT SUM(sub.面积) FROM (SELECT FIRST("面积") AS 面积 FROM t1 GROUP BY "地块编号") sub`
12. ⚠️避免并列截断：当查询“最...”（如最高、最大、最长、最小等）的数据时，如果可能存在并列的结果，**禁止直接使用 `ORDER BY ... LIMIT 1`**。应当使用子查询最大值/最小值过滤，例如 `WHERE "列名" = (SELECT MAX("列名") FROM 表名)`，以便能返回所有并列的数据。仅当用户明确要求“前 N 个”或“第 1 个”时才使用 LIMIT。
13. ⚠️“仅有/只有”逻辑：当查询“仅有/只有”某种属性（如“仅有土埂的地块”）时，**禁止直接使用单一的相等条件（如 WHERE "材质" = '土埂'）**。必须使用差集排除（`EXCEPT`）或 `HAVING` 聚合判定，将混杂了其他属性（如既有土埂又有石埂）的数据剔除。示例：`SELECT "地块" FROM t1 WHERE "材质" = '土埂' EXCEPT SELECT "地块" FROM t1 WHERE "材质" != '土埂' OR "材质" IS NULL`
14. ⚠️避免模糊匹配误伤：当过滤“地块编号”、“田坎编号”等特定编号（例如“27#地块”）时，**禁止直接使用宽泛的 %LIKE% 模糊条件（如 LIKE '%27#%'）**，以防误配到“127#”等包含子串的其他行。必须参考表内数据样本的典型格式进行等值匹配，优先使用 `IN`（例如 `WHERE "整治地块编号" IN ('开发复垦027#', '开发复垦036#')`）。
15. ⚠️避免全局过滤污染多指标：当同时查询多个指标且其中部分指标有额外过滤条件（例如“统计总面积，并计算宽度大于1米的田坎面积”）时，**禁止将特定指标的过滤条件作为全局 WHERE 条件**（否则会导致不满足该特定条件的地块在主指标统计中被漏算）。必须使用**条件聚合（Conditional Aggregation）**来隔离不同指标 of 过滤，例如 `SUM(CASE WHEN "平均宽度" >= 1.0 THEN "田坎面积" ELSE 0 END)`，以确保主要指标的统计范围不受污染。
16. ⚠️隔离合并列与非合并列统计：若一个查询同时涉及“合并单元格去重统计（如预计新增耕地面积）”和“非合并列的细粒度统计（如田坎宽度/面积等）”，**绝对禁止**在同一个 GROUP BY 分组子查询里对非合并列进行 `FIRST()` 或 `AVG()` 聚合去重，这会导致细粒度数据被错误压缩丢弃；同时，**绝对禁止**将去重子查询与多行明细主表直接进行 JOIN（无论是 ON 1=1 还是 ON 分组键），因为多行乘积或重复累加会把合并列总和或非合并列总和放大数倍。必须把合并列 of 去重求和单独作为独立的**标量子查询**计算，而在最外层直接对非合并列进行统计。例如：`SELECT (SELECT SUM(sub."合并列") FROM (SELECT FIRST("合并列") AS "合并列" FROM t1 WHERE 条件 GROUP BY "分组键") sub) AS "合并列总和", SUM(CASE WHEN "非合并列A" >= 1.0 THEN "非合并列B" ELSE 0 END) AS "非合并列总和" FROM t1 WHERE 条件`
17. 只输出 SQL，不要加 ```sql 代码块标记"""


def _build_sql_prompt(
    question: str,
    schema_summary: str,
) -> str:
    """构建 SQL 生成的完整 prompt。"""
    return (
        f"{_SQL_SYSTEM_PROMPT}\n\n"
        f"## 可用数据表\n\n{schema_summary}\n\n"
        f"## 用户问题\n{question}\n\n"
        f"请生成 SQL 查询语句："
    )


# ── LLM 调用生成 SQL ─────────────────────────────────────

async def _generate_sql(
    question: str,
    schema_summary: str,
    model: str = _SQL_MODEL,
) -> str:
    """
    调用 Ollama LLM 生成 SQL。

    WHY: 用 raw prompt 模式 + /no_think 跳过推理链，
         快速得到纯 SQL 文本。
    """
    from core.llm_engine import get_client, _gpu_semaphore
    from core.config import settings

    url = f"{settings.OLLAMA_BASE_URL}/api/generate"
    prompt_text = _build_sql_prompt(question, schema_summary)

    raw_prompt = (
        f"<|im_start|>system\n{_SQL_SYSTEM_PROMPT}<|im_end|>\n"
        f"<|im_start|>user\n"
        f"## 可用数据表\n\n{schema_summary}\n\n"
        f"## 用户问题\n{question}<|im_end|>\n"
        f"<|im_start|>assistant\n<think>\n</think>\n"
    )

    payload = {
        "model": model,
        "prompt": raw_prompt,
        "raw": True,
        "stream": True,
        "think": False,
        "keep_alive": -1,
        "options": {
            "temperature": 0,
            "num_predict": 512,
            "num_ctx": _SQL_NUM_CTX,
            "repeat_penalty": 1.0,
        },
    }

    try:
        async with _gpu_semaphore:
            client = get_client()
            tokens = []
            async with client.stream("POST", url, json=payload, timeout=300.0) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line.strip():
                        continue
                    try:
                        import json
                        data = json.loads(line)
                        token = data.get("response", "")
                        if token:
                            tokens.append(token)
                    except json.JSONDecodeError:
                        continue
            raw_text = "".join(tokens).strip()

        if not raw_text:
            return ""

        # 清理 <think> 残留
        raw_text = re.sub(
            r'<think>.*?(</think>|$)', '', raw_text, flags=re.DOTALL
        ).strip()

        # 提取 SQL（去除可能的 ```sql 包裹）
        if '```sql' in raw_text:
            m = re.search(r'```sql\s*(.*?)\s*```', raw_text, re.DOTALL)
            if m:
                return m.group(1).strip()

        if '```' in raw_text:
            m = re.search(r'```\s*(.*?)\s*```', raw_text, re.DOTALL)
            if m:
                return m.group(1).strip()

        # 提取第一条 SELECT 语句
        m = re.search(
            r'(SELECT\b.*?)(?:;|\Z)', raw_text,
            re.IGNORECASE | re.DOTALL,
        )
        if m:
            return m.group(1).strip()

        return raw_text.strip().rstrip(';')

    except Exception as e:
        logger.warning(f"[data_analyzer] SQL 生成失败: {repr(e)}")
        return ""


# ── SQL 自愈纠错 Prompt 与生成 ─────────────────────────────────

def _build_repair_prompt(
    question: str,
    schema_summary: str,
    failed_sql: str,
    error_msg: str,
) -> str:
    """构建 SQL 纠错生成的完整 prompt。"""
    return (
        f"{_SQL_SYSTEM_PROMPT}\n\n"
        f"## 可用数据表\n\n{schema_summary}\n\n"
        f"## 之前生成的错误 SQL\n```sql\n{failed_sql}\n```\n\n"
        f"## 执行该 SQL 时的报错信息\n```\n{error_msg}\n```\n\n"
        f"## 用户问题\n{question}\n\n"
        f"请修复上述错误，重新生成一条正确的 SQL 查询语句："
    )


async def _generate_repair_sql(
    question: str,
    schema_summary: str,
    failed_sql: str,
    error_msg: str,
    model: str = _SQL_MODEL,
) -> str:
    """
    调用 Ollama LLM 纠错并重新生成 SQL。
    """
    from core.llm_engine import get_client, _gpu_semaphore
    from core.config import settings

    url = f"{settings.OLLAMA_BASE_URL}/api/generate"

    raw_prompt = (
        f"<|im_start|>system\n{_SQL_SYSTEM_PROMPT}<|im_end|>\n"
        f"<|im_start|>user\n"
        f"## 可用数据表\n\n{schema_summary}\n\n"
        f"## 之前生成的错误 SQL\n```sql\n{failed_sql}\n```\n\n"
        f"## 执行该 SQL 时的报错信息\n```\n{error_msg}\n```\n\n"
        f"## 用户问题\n{question}<|im_end|>\n"
        f"<|im_start|>assistant\n<think>\n</think>\n"
    )

    payload = {
        "model": model,
        "prompt": raw_prompt,
        "raw": True,
        "stream": True,
        "think": False,
        "keep_alive": -1,
        "options": {
            "temperature": 0,
            "num_predict": 512,
            "num_ctx": _SQL_NUM_CTX,
            "repeat_penalty": 1.0,
        },
    }

    try:
        async with _gpu_semaphore:
            client = get_client()
            tokens = []
            async with client.stream("POST", url, json=payload, timeout=300.0) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line.strip():
                        continue
                    try:
                        import json
                        data = json.loads(line)
                        token = data.get("response", "")
                        if token:
                            tokens.append(token)
                    except json.JSONDecodeError:
                        continue
            raw_text = "".join(tokens).strip()

        if not raw_text:
            return ""

        # 清理 <think> 残留
        raw_text = re.sub(
            r'<think>.*?(</think>|$)', '', raw_text, flags=re.DOTALL
        ).strip()

        # 提取 SQL（去除可能的 ```sql 包裹）
        if '```sql' in raw_text:
            m = re.search(r'```sql\s*(.*?)\s*```', raw_text, re.DOTALL)
            if m:
                return m.group(1).strip()

        if '```' in raw_text:
            m = re.search(r'```\s*(.*?)\s*```', raw_text, re.DOTALL)
            if m:
                return m.group(1).strip()

        # 提取第一条 SELECT 语句
        m = re.search(
            r'(SELECT\b.*?)(?:;|\Z)', raw_text,
            re.IGNORECASE | re.DOTALL,
        )
        if m:
            return m.group(1).strip()

        return raw_text.strip().rstrip(';')

    except Exception as e:
        logger.warning(f"[data_analyzer] SQL 纠错生成失败: {repr(e)}")
        return ""


# ── 结果格式化 ────────────────────────────────────────────


def _format_result(
    result_df: pd.DataFrame,
    sql: str,
    max_rows: int = 100,
) -> tuple[str, str]:
    """
    将 DuckDB 查询结果格式化为文本和 Markdown 表格。

    Returns: (result_text, result_table_markdown)
    """
    if result_df.empty:
        return "查询结果为空", ""

    # 截断过长的结果
    truncated = False
    if len(result_df) > max_rows:
        result_df = result_df.head(max_rows)
        truncated = True

    # 规整数值精度，消除二进制浮点计算累加造成的微小精度误差，确保表格与文字回答显示一致
    try:
        result_df = result_df.round(10)
    except Exception:
        pass

    # Markdown 表格
    table_md = result_df.to_markdown(index=False)

    # 纯文本摘要（用于 context 注入）
    text_parts = []
    for _, row in result_df.iterrows():
        items = []
        for col in result_df.columns:
            val = row[col]
            if pd.notna(val):
                items.append(f"{col}={val}")
        text_parts.append(", ".join(items))

    result_text = "\n".join(text_parts)
    if truncated:
        result_text += f"\n...（结果已截断，仅显示前 {max_rows} 行）"

    return result_text, table_md


# ── 主入口 ────────────────────────────────────────────────

async def analyze_data(
    question: str,
    project_id: str,
    file_ids: list[str] | None,
    model: str = settings.DEFAULT_LLM_MODEL,
) -> DataAnalysisResult:
    """
    DuckDB 数据分析主入口。

    流程：
    1. 从 table_registry 加载全部表格 → DataFrame
    2. 注册到 DuckDB 内存数据库
    3. LLM 生成 SQL
    4. DuckDB 执行 SQL
    5. 格式化结果

    Args:
        question: 用户原始问题
        project_id: 项目 ID
        file_ids: 文件 ID 过滤（None = 全部）
        model: Ollama 模型名

    Returns:
        DataAnalysisResult 包含 SQL、结果、错误信息
    """
    from core.table_registry import load_tables_as_dataframes

    result = DataAnalysisResult()

    # ── 1. 加载表格 ──
    try:
        table_infos = load_tables_as_dataframes(project_id, file_ids)
    except Exception as e:
        logger.warning(f"[data_analyzer] 加载表格失败: {repr(e)}")
        result.error = f"加载表格数据失败: {e}"
        return result

    if not table_infos:
        result.error = "项目中没有可分析的表格数据"
        return result

    result.tables_used = [
        {
            "name": t["table_name"],
            "display": t["display_name"],
            "rows": t["row_count"],
        }
        for t in table_infos
    ]

    print(
        f"📊 [DataAnalyzer] 加载 {len(table_infos)} 张表, "
        f"总行数 {sum(t['row_count'] for t in table_infos)}",
        flush=True,
    )

    # ── 2. 构建 Schema 摘要 ──
    schema_summary = _build_schema_summary(table_infos)

    # ── 3. LLM 生成 SQL ──
    # WHY: 降级后统一使用 settings.DEFAULT_LLM_MODEL
    sql_model = settings.DEFAULT_LLM_MODEL
    sql = await _generate_sql(question, schema_summary, sql_model)

    if not sql:
        result.error = "AI 未能生成有效的 SQL 查询"
        return result

    result.sql = sql
    print(f"📊 [DataAnalyzer] 生成 SQL: {sql[:200]}", flush=True)

    # ── 4. 安全校验 ──
    safety_err = _validate_sql(sql)
    if safety_err:
        result.error = f"SQL 安全校验失败: {safety_err}"
        return result

    # ── 5. DuckDB 执行与自愈重试 ──
    conn = None
    try:
        conn = duckdb.connect(":memory:")

        # 注册所有表
        for info in table_infos:
            conn.register(info["table_name"], info["df"])

        # 第一次尝试执行
        try:
            query_result = conn.execute(sql).fetchdf()
            result.row_count = len(query_result)
            
            # WHY: 如果执行成功但结果为空或计算值全为 NaN，说明 SQL 条件编写逻辑错误，
            #      强制抛出异常以激活自愈重试机制。
            is_empty_or_nan = result.row_count == 0 or (
                result.row_count == 1 and query_result.iloc[0].isna().all()
            )
            if is_empty_or_nan:
                raise Exception("查询结果为空或计算值全部为 NaN，可能是 SQL 过滤条件不匹配或误伤")

            result.result_text, result.result_table = _format_result(
                query_result, sql,
            )
            print(
                f"📊 [DataAnalyzer] 查询成功, {result.row_count} 行结果",
                flush=True,
            )
        except Exception as first_err:
            first_err_msg = str(first_err)
            print(
                f"⚠️ [DataAnalyzer] 首次 SQL 执行失败，启动自愈重试。错误: {first_err_msg}",
                flush=True,
            )
            
            # 调用 AI 进行 SQL 纠错重试
            repaired_sql = await _generate_repair_sql(
                question, schema_summary, sql, first_err_msg, sql_model
            )
            if not repaired_sql:
                raise first_err  # 纠错失败，抛出原异常
            
            # 安全校验纠错后的 SQL
            safety_err = _validate_sql(repaired_sql)
            if safety_err:
                raise Exception(f"修复后的 SQL 安全校验失败: {safety_err}")
                
            print(
                f"📊 [DataAnalyzer] 纠错后重新执行 SQL: {repaired_sql[:200]}",
                flush=True,
            )
            result.sql = repaired_sql  # 更新返回的 SQL
            
            # 重新执行
            query_result = conn.execute(repaired_sql).fetchdf()
            result.row_count = len(query_result)
            
            # 自愈后仍然进行空值与 NaN 校验
            is_empty_or_nan = result.row_count == 0 or (
                result.row_count == 1 and query_result.iloc[0].isna().all()
            )
            if is_empty_or_nan:
                raise Exception("自愈修复后的查询结果仍为空或计算值全部为 NaN")

            result.result_text, result.result_table = _format_result(
                query_result, repaired_sql,
            )
            print(
                f"📊 [DataAnalyzer] 自愈后查询成功, {result.row_count} 行结果",
                flush=True,
            )

    except Exception as e:
        err_msg = str(e)
        logger.warning(f"[data_analyzer] SQL 执行失败: {err_msg}")
        # WHY: DuckDB 错误信息可能包含列名建议，透传给用户有助调试
        result.error = f"SQL 执行失败: {err_msg}"

    finally:
        if conn:
            try:
                conn.close()
            except Exception:
                pass

    return result
