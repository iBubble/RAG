import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════
# GIS 数据智能统计模块
# WHY: 国土/规划行业的 GDB/MDB/SHP 字段普遍使用拼音缩写，
#      AI 无法理解 TBMJ、DLMC 等含义，需要翻译为中文。
# ═══════════════════════════════════════════════════════════════

_GIS_FIELD_MAP = {
    # ── 标识类 ──
    "BSM": "标识码", "YSDM": "要素代码", "OBJECTID": "对象ID",
    "SHAPE_AREA": "图形面积", "SHAPE_LENGTH": "图形周长",
    "SHAPE_LENG": "图形周长",
    # ── 土地调查核心字段 ──
    "DLBM": "地类编码", "DLMC": "地类名称",
    "TBMJ": "图斑面积", "TBDLMJ": "图斑地类面积",
    "KCDLBM": "扣除地类编码", "KCMJ": "扣除面积", "KCXS": "扣除系数",
    "GDLX": "耕地类型", "GDPDJB": "耕地坡度级别",
    "CZCSXM": "城镇村属性码", "ZLDWDM": "坐落单位代码",
    "ZLDWMC": "坐落单位名称",
    "QSXZ": "权属性质", "QSDWDM": "权属单位代码",
    "QSDWMC": "权属单位名称",
    # ── 变更调查 ──
    "BGDLBM": "变更地类编码", "BGDLMC": "变更地类名称",
    "BGMJ": "变更面积", "BGHSXW": "变更后属性位",
    "XZQTZLX": "现状区调整类型",
    # ── 规划/用途管制 ──
    "GHDLBM": "规划地类编码", "GHDLMC": "规划地类名称",
    "YTFL": "用途分类", "TDYT": "土地用途",
    "GHYT": "规划用途", "GHGKFL": "规划管控分类",
    # ── 空间属性 ──
    "XZQDM": "行政区代码", "XZQMC": "行政区名称",
    "XZQHDM": "行政区划代码", "XZQHMC": "行政区划名称",
    "XIANG": "乡", "CUN": "村", "ZU": "组",
    # ── 权属/地籍 ──
    "ZDMJ": "宗地面积", "ZDDM": "宗地代码",
    "BDCDYH": "不动产单元号",
    "SYQMJ": "使用权面积",
    # ── 工程/项目 ──
    "GCMC": "工程名称", "XMMC": "项目名称",
    "JSDW": "建设单位", "PZWH": "批准文号",
    "PZMJ": "批准面积", "SJMJ": "实际面积",
    # ── 水利/水保 ──
    "LXMC": "流域名称", "SLLX": "水利类型",
    "HBMJ": "汇编面积",
    # ── 通用 ──
    "MC": "名称", "DM": "代码", "MJ": "面积",
    "BZ": "备注", "SJLY": "数据来源",
    "GXSJ": "更新时间", "FHDL": "符合地类",
}

# ── GIS 图层名语义映射 ──
# WHY: 图层名如 XZQ、CJDCQ、DLTB 是纯拼音缩写，
#      用户提问"乡镇""行政村"时，检索模型无法关联到 XZQ/CJDCQ，
#      必须在入库文本中注入中文同义词才能被语义匹配命中。
_GIS_LAYER_MAP = {
    # ── 基础地理 ──
    "XZQ": "行政区/乡镇/街道",
    "XZQJX": "行政区界线",
    "CJDCQ": "村级调查区/行政村/社区",
    "CJDCQJX": "村级调查区界线",
    # ── 土地调查核心 ──
    "DLTB": "地类图斑/土地现状",
    "YJJBNTTB": "永久基本农田图斑",
    "GDDB": "耕地等别/耕地质量",
    # ── 管制区/规划 ──
    "PZWJSTD": "批准未建设土地",
    "ZYXMYD": "重要项目用地",
    "KFYQ": "开发园区",
    "TTQ": "梯田区",
    "CCWJQ": "城镇村建设用地管制区",
    # ── 生态保护 ──
    "LMFW": "林木覆盖范围",
    "WJMHD": "未竣工变化地块",
    "GJGY": "国家公园",
    "ZRBHD": "自然保护地",
    "SLGY": "湿地/水利工程",
    "FJMSQ": "风景名胜区",
    "DZGY": "地质公园",
    # ── 控制点 ──
    "CLKZD": "测量控制点",
    "JZKZD": "界址控制点",
    # ── 其他 ──
    "GCZJD": "工程建设用地",
    "ZYCBHD": "重要草地保护地",
    "SDGY": "森林公园",
}

# 数值聚合关键词（字段名包含这些词时进行统计）
_NUMERIC_KEYWORDS = {"面积", "MJ", "AREA", "LENGTH", "长度", "周长",
                     "金额", "数量", "宽度", "高程", "坡度"}

# 500MB 阈值（字节）
_LARGE_FILE_THRESHOLD = 500 * 1024 * 1024


def _translate_layer(layer_name: str) -> str:
    """
    将 GIS 图层拼音缩写翻译为中文语义标签。
    WHY: 用户问"乡镇"时，检索模型需要在入库文本中找到"乡镇"才能命中。
         XZQ → XZQ(行政区/乡镇/街道) 让检索和 AI 都能理解。
    """
    upper = layer_name.upper().strip()
    if upper in _GIS_LAYER_MAP:
        return f"{layer_name}({_GIS_LAYER_MAP[upper]})"
    return layer_name


def _translate_field(field_name: str) -> str:
    """
    将 GIS 拼音缩写字段翻译为中文。
    WHY: GDB/MDB 中的字段名如 TBMJ、DLMC 对大模型完全不透明，
         翻译后 AI 才能理解"图斑面积"的语义并进行聚合计算。
    """
    upper = field_name.upper().strip()
    if upper in _GIS_FIELD_MAP:
        return f"{field_name}({_GIS_FIELD_MAP[upper]})"
    return field_name


def _generate_df_summary(df, layer_name: str = "",
                         max_sample: int = 20) -> str:
    """
    对 DataFrame 生成结构化统计摘要 + 键值对采样。
    WHY: GDB/MDB 动辄数万条记录，全量入库既浪费 Token 又淹没重点。
         宏观统计（总面积、地类分布）+ 精简采样是最优平衡。
    输出格式:
      [图层/表: xxx (共 N 条记录)]
      字段结构: BSM(标识码) | DLMC(地类名称) | TBMJ(图斑面积)
      === 统计摘要 ===
      数值字段: TBMJ(图斑面积) 总和=12345.67, 最大=89.01, 均值=1.23
      类别字段: DLMC(地类名称) 分布: 耕地(320), 林地(180), 水域(45)
      === 数据采样 (前20条) ===
      DLMC(地类名称): 耕地 | TBMJ(图斑面积): 12.5 | ...
    """
    import numpy as np

    texts = []
    record_count = len(df)

    # 标题（注入图层语义翻译）
    translated_layer = _translate_layer(layer_name) if layer_name else ""
    if layer_name:
        texts.append(f"[图层/表: {translated_layer} (共 {record_count} 条记录)]")

    # 在标题后注入高频实体名称，提升检索命中率
    # WHY: 如 XZQ 图层包含"大石镇、吉祥镇"等，注入后用户问"乡镇"时能被检索命中
    name_cols = [c for c in df.columns
                 if c.upper() in ("XZQMC", "ZLDWMC", "QSDWMC", "MC",
                                  "DLMC", "XMMC", "GCMC", "LXMC")]
    if name_cols:
        for nc in name_cols[:2]:  # 最多取 2 个名称列
            unique_vals = df[nc].dropna().unique()
            if 0 < len(unique_vals) <= 50:
                sample_names = ", ".join(str(v) for v in unique_vals[:10])
                tc = _translate_field(nc)
                texts.append(f"包含{tc}: {sample_names}")

    # 翻译字段名
    translated_cols = {col: _translate_field(col) for col in df.columns}
    texts.append("字段结构: " + " | ".join(
        translated_cols[c] for c in df.columns))

    # ── 统计摘要 ──
    texts.append("=== 统计摘要 ===")

    def _format_numeric_val(c_name: str, val: float) -> str:
        """启发式判断：如果是面积字段且数值特大（如平方米），自动在底层算好公顷注入，防止大模型口算出错"""
        if any(k in c_name for k in ("面积", "AREA", "MJ", "TBDLMQ")):
            if val > 10000:
                ha = val / 10000.0
                mu = val / (10000.0 / 15.0)
                return f"{val:.2f} (约 {ha:.2f} 公顷 / {mu:.2f} 亩)"
        return f"{val:.2f}"

    # 数值字段聚合
    numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
    for col in numeric_cols:
        col_upper = col.upper()
        # 仅对业务相关数值字段进行统计（跳过 OBJECTID 等）
        is_business = any(kw in col_upper or kw in translated_cols[col]
                         for kw in _NUMERIC_KEYWORDS)
        if not is_business:
            continue
        series = df[col].dropna()
        if series.empty:
            continue
        col_name = translated_cols[col]
        total = series.sum()
        max_val = series.max()
        mean_val = series.mean()
        texts.append(
            f"  数值字段: {col_name} "
            f"总和={_format_numeric_val(col_name, total)}, 最大值={_format_numeric_val(col_name, max_val)}, "
            f"均值={_format_numeric_val(col_name, mean_val)}, 非空数={len(series)}")

    # 类别字段分布
    object_cols = df.select_dtypes(
        include=["object", "category"]).columns.tolist()
    for col in object_cols:
        col_upper = col.upper()
        # 跳过无意义的 ID 类字段
        if col_upper in ("BSM", "OBJECTID", "FID", "SHAPE"):
            continue
        series = df[col].dropna()
        if series.empty or series.nunique() > 200:
            # 唯一值太多（如地址），只报告总数
            texts.append(
                f"  类别字段: {translated_cols[col]} "
                f"共 {series.nunique()} 个唯一值")
            continue
        top5 = series.value_counts().head(5)
        dist_str = ", ".join(f"{k}({v})" for k, v in top5.items())
        texts.append(
            f"  类别字段: {translated_cols[col]} "
            f"分布(Top5): {dist_str}")

    # ================= 新增：自动分类汇总 (Group By) =================
    # WHY: 以前只统计总面积和类别的条数分布，导致 AI 无法回答"旱地的总面积是多少"等精准归类问题。
    # 这里通过 Pandas 在底层预先按地类/类型等字段，对面积等核心量化指标进行聚合分组，注入到上下文中。
    group_cols = [
        c for c in object_cols 
        if any(k in translated_cols[c] or k in c.upper() 
               for k in ("地类", "类型", "名称", "DLMC", "XZQMC", "权属", "LX", "分类", "类别"))
    ]
    # 面积/长度等量化指标 (只取业务指标)
    area_cols = [
        c for c in numeric_cols 
        if any(k in translated_cols[c] or k in c.upper() 
               for k in ("面积", "AREA", "MJ", "TBDLMQ", "金额", "长度", "LENGTH"))
    ]
    
    if group_cols and area_cols:
        texts.append("=== 自动分类汇总 (类别与其对应的指标总和) ===")
        for gc in group_cols[:2]:     # 取权重最高的前2个分类属性
            for ac in area_cols[:1]:  # 取权重最高的前1个数值属性
                try:
                    grouped = df.groupby(gc)[ac].sum().sort_values(ascending=False)
                    # WHY: 扩大至 100 以覆盖三调全量地类（通常70多个二级地类），支持"列出所有地类"等长尾查询
                    grouped_top = grouped.head(100)
                    if not grouped_top.empty:
                        # 注入预运算后的公顷/亩
                        c_name = translated_cols[ac]
                        summary_str = ", ".join(f"{k}({_format_numeric_val(c_name, v)})" for k, v in grouped_top.items())
                        count_tag = "全量" if len(grouped) <= 100 else "Top100"
                        texts.append(f"  * 按 [{translated_cols[gc]}] 汇总 [{c_name}] ({count_tag}): {summary_str}")
                except Exception as e:
                    logger.debug(f"通过 Pandas 分类汇总失败: {e}")

    return "\n".join(texts)



def _generate_df_samples(df, max_sample: int = 20) -> str:
    """
    生成键值对格式的数据采样。
    WHY: 与 Excel 的键值对提取保持一致，确保 AI 能理解每个值对应哪个字段。
    """
    texts = []
    translated_cols = {col: _translate_field(col) for col in df.columns}
    sample_df = df.head(max_sample)

    if not sample_df.empty:
        texts.append(f"=== 数据采样 (前{len(sample_df)}条) ===")
        for _, row in sample_df.iterrows():
            pairs = []
            for col in df.columns:
                val = row[col]
                val_str = str(val).strip()
                if not val_str or val_str.lower() in ("nan", "none", ""):
                    continue
                # 省略零值
                try:
                    if float(val_str) == 0:
                        continue
                except (ValueError, TypeError):
                    pass
                pairs.append(f"{translated_cols[col]}: {val_str}")
            if pairs:
                texts.append(" | ".join(pairs))

    return "\n".join(texts)


def _extract_shp(file_path: str) -> str:
    """提取 Shapefile 的属性表：优先读同目录 .dbf 文件。"""
    dbf_path = Path(file_path).with_suffix(".dbf")
    if dbf_path.exists():
        return _extract_shp_dbf(str(dbf_path))
    return f"[Shapefile] {Path(file_path).name}（缺少 .dbf 属性表）"


def _extract_shp_dbf(file_path: str) -> str:
    """
    使用 dbfread 读取 .dbf 属性表 + 统计摘要。
    WHY: Shapefile 的属性数据独立存于 .dbf，是 GIS 最常见格式。
         数十万图斑记录的 DBF 不能全量加载到内存（会 OOM），
         需要流式迭代统计。
    策略:
      - ≤50,000 条: DataFrame 全量模式（精确统计 + 采样）
      - >50,000 条: 流式迭代模式（内存恒定 ~100MB）
    """
    from dbfread import DBF

    # 编码探测
    table = None
    for enc in ("utf-8", "gbk", "gb2312", "cp936", "big5", "latin-1"):
        try:
            table = DBF(file_path, encoding=enc,
                        char_decode_errors="replace",
                        ignore_missing_memofile=True)
            for _ in table:
                break
            break
        except Exception:
            table = None
            continue

    if table is None:
        logger.error(f"无法读取 DBF 文件（所有编码均失败）: {file_path}")
        return ""

    # WHY: 先用迭代器快速计数，决定走全量还是流式路径
    #      dbfread 每次 iter 会重新从文件头开始读，所以计数后可以再迭代
    record_count = sum(1 for _ in table)
    if record_count == 0:
        return f"[DBF] {Path(file_path).name}（空表）"

    layer_name = Path(file_path).stem

    # ── 小文件：保持原有 DataFrame 模式 ──
    if record_count <= 50000:
        import pandas as pd
        records = list(table)
        df = pd.DataFrame(records)
        file_size = Path(file_path).stat().st_size
        stats_only = file_size > _LARGE_FILE_THRESHOLD

        texts = []
        texts.append(_generate_df_summary(df, layer_name))
        if not stats_only:
            texts.append(_generate_df_samples(df, max_sample=20))
        else:
            texts.append("（大文件模式：仅提供统计，不采样数据行）")
        return "\n".join(texts)

    # ── 大文件：流式迭代统计（内存恒定） ──
    logger.info(
        f"📊 大规模 DBF 流式统计: {layer_name} ({record_count:,} 条记录)"
    )
    return _stream_dbf_summary(table, layer_name, record_count)


def _stream_dbf_summary(
    table, layer_name: str, record_count: int,
    max_sample: int = 20,
) -> str:
    """
    流式迭代 DBF 记录，生成统计摘要。
    WHY: 数十万条记录不能全量加载到 DataFrame（OOM 风险），
         用 Counter + 累加器做一趟扫描即可完成统计。
    内存占用: 恒定 ~50-100MB，与记录数无关。
    """
    from collections import Counter

    # ── 第一趟扫描：字段探测 ──
    field_names = table.field_names
    translated_cols = {f: _translate_field(f) for f in field_names}

    # 分类：数值字段 vs 文本字段
    numeric_fields = set()
    text_fields = set()
    skip_fields = {"BSM", "OBJECTID", "FID", "SHAPE"}

    # 用前 100 条记录探测字段类型
    probe_count = 0
    for record in table:
        for fname in field_names:
            val = record.get(fname)
            if val is None:
                continue
            if isinstance(val, (int, float)):
                numeric_fields.add(fname)
            elif isinstance(val, str):
                text_fields.add(fname)
        probe_count += 1
        if probe_count >= 100:
            break

    # ── 第二趟扫描：流式统计 ──
    # 数值累加器
    num_stats = {}
    for f in numeric_fields:
        num_stats[f] = {
            "sum": 0.0, "min": float("inf"), "max": float("-inf"),
            "count": 0,
        }

    # 文本分布计数器（限 Top200）
    text_counters = {}
    for f in text_fields:
        if f.upper() not in skip_fields:
            text_counters[f] = Counter()

    # 采样前 N 条
    samples = []
    # 分类汇总累加器: {(group_field, group_value, agg_field): sum}
    group_agg = {}

    # WHY: 预判哪些文本字段适合做 GroupBy 分类汇总
    group_candidates = [
        f for f in text_fields
        if any(k in translated_cols[f] or k in f.upper()
               for k in ("地类", "类型", "名称", "DLMC", "XZQMC",
                          "权属", "LX", "分类", "类别"))
    ]
    # WHY: 预判哪些数值字段适合做聚合
    agg_candidates = [
        f for f in numeric_fields
        if any(k in translated_cols[f] or k in f.upper()
               for k in ("面积", "AREA", "MJ", "TBDLMQ", "金额",
                          "长度", "LENGTH"))
    ]

    scan_count = 0
    for record in table:
        scan_count += 1

        # 采样
        if len(samples) < max_sample:
            samples.append(dict(record))

        # 数值累加
        for f in numeric_fields:
            val = record.get(f)
            if val is not None:
                try:
                    fval = float(val)
                    s = num_stats[f]
                    s["sum"] += fval
                    s["count"] += 1
                    if fval < s["min"]:
                        s["min"] = fval
                    if fval > s["max"]:
                        s["max"] = fval
                except (ValueError, TypeError):
                    pass

        # 文本分布
        for f, counter in text_counters.items():
            val = record.get(f)
            if val is not None and str(val).strip():
                counter[str(val).strip()] += 1

        # 分类汇总（流式 GroupBy）
        for gc in group_candidates[:2]:
            gval = record.get(gc)
            if gval is None or not str(gval).strip():
                continue
            gkey = str(gval).strip()
            for ac in agg_candidates[:1]:
                aval = record.get(ac)
                if aval is not None:
                    try:
                        key = (gc, gkey, ac)
                        group_agg[key] = group_agg.get(key, 0.0) + float(aval)
                    except (ValueError, TypeError):
                        pass

    # ── 组装输出 ──
    texts = []

    # 标题
    translated_layer = _translate_layer(layer_name)
    texts.append(
        f"[图层/表: {translated_layer} "
        f"(共 {record_count:,} 条记录 · 流式统计)]"
    )

    # 高频名称注入
    name_keys = {"XZQMC", "ZLDWMC", "QSDWMC", "MC",
                 "DLMC", "XMMC", "GCMC", "LXMC"}
    for f, counter in text_counters.items():
        if f.upper() in name_keys and 0 < len(counter) <= 50:
            sample_names = ", ".join(
                name for name, _ in counter.most_common(10)
            )
            texts.append(f"包含{translated_cols[f]}: {sample_names}")

    # 字段结构
    texts.append("字段结构: " + " | ".join(
        translated_cols[f] for f in field_names
    ))

    # 统计摘要
    texts.append("=== 统计摘要 ===")

    def _fmt(col_name: str, val: float) -> str:
        """面积字段自动转换公顷/亩。"""
        if any(k in col_name for k in ("面积", "AREA", "MJ")):
            if val > 10000:
                ha = val / 10000.0
                mu = val / (10000.0 / 15.0)
                return f"{val:,.2f} (约 {ha:,.2f} 公顷 / {mu:,.2f} 亩)"
        return f"{val:,.2f}"

    for f in numeric_fields:
        fu = f.upper()
        is_biz = any(
            k in fu or k in translated_cols[f]
            for k in _NUMERIC_KEYWORDS
        )
        if not is_biz:
            continue
        s = num_stats[f]
        if s["count"] == 0:
            continue
        cname = translated_cols[f]
        mean_val = s["sum"] / s["count"]
        texts.append(
            f"  数值字段: {cname} "
            f"总和={_fmt(cname, s['sum'])}, "
            f"最大值={_fmt(cname, s['max'])}, "
            f"均值={_fmt(cname, mean_val)}, "
            f"非空数={s['count']:,}"
        )

    # 类别分布
    for f, counter in text_counters.items():
        if not counter:
            continue
        cname = translated_cols[f]
        if len(counter) > 200:
            texts.append(
                f"  类别字段: {cname} 共 {len(counter)} 个唯一值"
            )
        else:
            top5 = counter.most_common(5)
            dist = ", ".join(f"{k}({v:,})" for k, v in top5)
            texts.append(
                f"  类别字段: {cname} 分布(Top5): {dist}"
            )

    # 分类汇总
    if group_agg:
        texts.append("=== 自动分类汇总 (类别与其对应的指标总和) ===")
        # 按 (gc, ac) 分组整理
        from collections import defaultdict
        grouped = defaultdict(dict)
        for (gc, gval, ac), total in group_agg.items():
            grouped[(gc, ac)][gval] = total

        for (gc, ac), vals in grouped.items():
            sorted_vals = sorted(
                vals.items(), key=lambda x: x[1], reverse=True
            )
            top100 = sorted_vals[:100]
            cname = translated_cols[ac]
            summary = ", ".join(
                f"{k}({_fmt(cname, v)})" for k, v in top100
            )
            tag = "全量" if len(sorted_vals) <= 100 else "Top100"
            texts.append(
                f"  * 按 [{translated_cols[gc]}] 汇总 "
                f"[{cname}] ({tag}): {summary}"
            )

    # 数据采样
    if samples:
        texts.append(f"=== 数据采样 (前{len(samples)}条) ===")
        for row in samples:
            pairs = []
            for f in field_names:
                val = row.get(f)
                val_str = str(val).strip() if val is not None else ""
                if not val_str or val_str.lower() in ("nan", "none", ""):
                    continue
                try:
                    if float(val_str) == 0:
                        continue
                except (ValueError, TypeError):
                    pass
                pairs.append(f"{translated_cols[f]}: {val_str}")
            if pairs:
                texts.append(" | ".join(pairs))

    return "\n".join(texts)


def _extract_gdb(file_path: str) -> str:
    """
    提取 ESRI File Geodatabase (.gdb) 中所有图层的统计摘要与属性采样。
    WHY: GDB 是国土调查的核心数据格式，包含数十个图层、数万条记录。
         旧版仅采样前 100 行裸数据，AI 无法进行全局统计（如"总面积"）。
         新版引入全量统计 + 字段翻译 + 键值对采样，兼顾宏观和微观。
    策略:
      - 文件夹 > 500MB：仅统计，不采样数据行
      - 图层 > 30 个：仅列出清单 + 前 10 个业务图层详细统计
    """
    path = Path(file_path)

    if not path.is_dir():
        logger.warning(f"GDB 路径不是文件夹: {file_path}")
        return ""

    try:
        import geopandas as gpd
        import pyogrio

        layers = pyogrio.list_layers(file_path)
        if len(layers) == 0:
            return f"[GDB] {path.name}（未找到图层）"

        layer_names = [str(l[0]) for l in layers]
        layer_types = [str(l[1]) if len(l) > 1 else "Unknown"
                       for l in layers]

        # 计算 GDB 文件夹总大小
        total_size = sum(
            f.stat().st_size for f in path.rglob("*") if f.is_file()
        )
        stats_only = total_size > _LARGE_FILE_THRESHOLD
        size_mb = total_size / (1024 * 1024)

        texts = [
            f"=== ESRI File Geodatabase 数据库 ===",
            f"名称: {path.name}",
            f"大小: {size_mb:.1f} MB",
            f"图层总数: {len(layer_names)}",
            f"图层清单: {', '.join(_translate_layer(n) for n in layer_names)}",
            f"===================================",
            ""
        ]

        if stats_only:
            texts.append("（大文件模式：仅提供统计摘要，不采样数据行）")
            texts.append("")

        # 如果图层过多，限制详细统计的图层数
        max_detail_layers = 10 if len(layer_names) > 30 else len(layer_names)

        for idx, layer_name in enumerate(layer_names):
            if idx >= max_detail_layers:
                texts.append(
                    f"\n... 还有 {len(layer_names) - max_detail_layers} "
                    f"个图层未详细展开（仅前 {max_detail_layers} 个）")
                break

            try:
                # 使用 pyogrio 读取，忽略几何加速统计
                gdf = gpd.read_file(
                    file_path, layer=layer_name, engine="pyogrio"
                )
                if "geometry" in gdf.columns:
                    df = gdf.drop(columns=["geometry"])
                else:
                    df = gdf

                if df.empty:
                    geom_type = layer_types[idx]
                    texts.append(
                        f"\n[图层/表: {layer_name} "
                        f"(空图层, 类型={geom_type})]")
                    continue

                # 统计摘要
                texts.append("")
                texts.append(_generate_df_summary(df, layer_name))

                # 数据采样（非大文件模式）
                if not stats_only:
                    sample_text = _generate_df_samples(df, max_sample=15)
                    if sample_text:
                        texts.append(sample_text)

            except Exception as e:
                texts.append(
                    f"\n[图层/表: {layer_name} (读取失败: {e})]")
                continue

        return "\n".join(texts)

    except ImportError:
        logger.error("缺少 geopandas/pyogrio 依赖，无法解析 GDB 格式")
        return ""
    except Exception as e:
        logger.error(f"读取 GDB 失败 {file_path}: {e}")
        return ""


def _extract_mdb(file_path: str) -> str:
    """
    提取 MS Access / Personal Geodatabase (.mdb) 的统计摘要与属性采样。
    WHY: MDB 在国土系统中用于 Personal Geodatabase，包含多张业务表。
         旧版仅采样前 100 行 CSV 裸数据，AI 无法进行全局统计。
         新版通过 mdb-export → pandas 实现全量聚合 + 键值对采样。
    依赖: brew install mdbtools
    """
    import subprocess
    import pandas as pd
    from io import StringIO

    path = Path(file_path)
    safe_path = str(path.resolve())

    if not path.exists() or not path.is_file():
        logger.error(f"MDB 文件不存在: {file_path}")
        return ""

    # 检查文件大小
    file_size = path.stat().st_size
    stats_only = file_size > _LARGE_FILE_THRESHOLD
    size_mb = file_size / (1024 * 1024)

    try:
        # 1. 获取所有表名
        tables_result = subprocess.run(
            ["mdb-tables", "-1", safe_path],
            capture_output=True, text=True, timeout=30
        )
        if tables_result.returncode != 0:
            logger.error(f"mdb-tables 失败: {tables_result.stderr}")
            return ""

        table_names = [
            t.strip() for t in tables_result.stdout.strip().split("\n")
            if t.strip()
        ]
        if not table_names:
            return f"[MDB] {path.name}（未找到数据表）"

        # 过滤 ESRI 系统内部表
        skip_prefixes = (
            "GDB_", "Selections", "SelectedObjects", "MSys"
        )
        user_tables = [
            t for t in table_names
            if not t.startswith(skip_prefixes)
        ]
        if not user_tables:
            user_tables = table_names

        texts = [
            f"=== MS Access / Personal Geodatabase ===",
            f"文件: {path.name}",
            f"大小: {size_mb:.1f} MB",
            f"数据表总数: {len(user_tables)}",
            f"表清单: {', '.join(user_tables)}",
            f"========================================",
            ""
        ]

        if stats_only:
            texts.append("（大文件模式：仅提供统计摘要，不采样数据行）")
            texts.append("")

        for table in user_tables:
            try:
                # 2. 用 mdb-export 导出表为 CSV
                export_result = subprocess.run(
                    ["mdb-export", safe_path, table],
                    capture_output=True, text=True, timeout=120
                )
                if export_result.returncode != 0:
                    texts.append(
                        f"\n[图层/表: {table} "
                        f"(导出失败: {export_result.stderr.strip()})]")
                    continue

                csv_data = export_result.stdout.strip()
                if not csv_data:
                    continue

                # 3. 解析为 DataFrame 进行统计
                try:
                    df = pd.read_csv(
                        StringIO(csv_data),
                        low_memory=False,
                        on_bad_lines="skip"
                    )
                except Exception:
                    # CSV 解析失败时回退为简单文本
                    lines = csv_data.split("\n")
                    texts.append(
                        f"\n[图层/表: {table} "
                        f"(共约 {len(lines) - 1} 条记录)]")
                    if lines:
                        # 翻译表头
                        header_fields = lines[0].split(",")
                        translated = [
                            _translate_field(f.strip().strip('"'))
                            for f in header_fields
                        ]
                        texts.append(
                            "字段结构: " + " | ".join(translated))
                    continue

                if df.empty:
                    texts.append(
                        f"\n[图层/表: {table} (空表)]")
                    continue

                # 4. 生成统计摘要
                texts.append("")
                texts.append(
                    _generate_df_summary(df, table))

                # 5. 数据采样（非大文件模式）
                if not stats_only:
                    sample_text = _generate_df_samples(
                        df, max_sample=15)
                    if sample_text:
                        texts.append(sample_text)

            except subprocess.TimeoutExpired:
                texts.append(
                    f"\n[图层/表: {table} (导出超时)]")
                continue
            except Exception as e:
                texts.append(
                    f"\n[图层/表: {table} (导出异常: {e})]")
                continue

        return "\n".join(texts)

    except FileNotFoundError:
        logger.error(
            "mdb-tables 命令不可用，请安装: brew install mdbtools")
        return ""
    except Exception as e:
        logger.error(f"读取 MDB 失败 {file_path}: {e}")
        return ""

