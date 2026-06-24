"""
docx_charts.py — Word 文档自动图表生成器。

从 Kimi generate_chart.py 迁移核心绘图逻辑，
适配本项目的"标记驱动"出图协议。

触发标记：[可视化：柱状图，标题：XXX] 或 [可视化：饼图，标题：XXX]
紧随标记的 Markdown 表格将被解析为绘图数据源。

WHY: 莫兰迪色系（低饱和度）是工程咨询报告的主流视觉风格，
     避免刺眼的高饱和色，提升文档专业感。
"""
from __future__ import annotations

import os
import re
import tempfile
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# ── 延迟导入，避免启动时 import 失败阻塞整个服务 ──
_MPL_READY = False


def _ensure_matplotlib():
    """延迟初始化 matplotlib，设置中文字体和莫兰迪色系。"""
    global _MPL_READY
    if _MPL_READY:
        return
    try:
        import matplotlib
        matplotlib.use("Agg")  # WHY: 服务器无 GUI，必须用 Agg 后端
        import matplotlib.pyplot as plt

        # WHY: macOS 可用 STHeiti/Songti SC，Linux 回退 WenQuanYi
        plt.rcParams["font.sans-serif"] = [
            "STHeiti", "Songti SC", "STFangsong",
            "PingFang HK", "SimHei", "WenQuanYi Micro Hei",
            "Noto Sans CJK SC", "Arial",
        ]
        plt.rcParams["axes.unicode_minus"] = False
        _MPL_READY = True
        logger.info("Matplotlib 初始化完成")
    except ImportError:
        logger.warning("matplotlib 未安装，图表功能不可用")


# ── 莫兰迪色板（与 Kimi generate_chart.py 一致） ──
MORANDI = {
    "green": "#7C9885",
    "blue": "#8B9DC3",
    "beige": "#B4A992",
    "brown": "#C4A484",
    "rose": "#C9A9A6",
    "sage": "#9CAF88",
}
COLORS = list(MORANDI.values())


def generate_bar_chart(
    title: str,
    labels: list[str],
    values: list[float],
    output_path: Optional[str] = None,
) -> Optional[str]:
    """
    生成莫兰迪柱状图并保存为 PNG。

    Args:
        title: 图表标题
        labels: X 轴类目（如 ["一区", "二区", ...]）
        values: Y 轴数值
        output_path: 输出路径，None 则自动生成临时文件

    Returns:
        PNG 文件路径，失败返回 None
    """
    _ensure_matplotlib()
    if not _MPL_READY:
        return None

    import matplotlib.pyplot as plt
    import numpy as np

    try:
        if not output_path:
            fd, output_path = tempfile.mkstemp(suffix=".png", prefix="chart_bar_")
            os.close(fd)

        fig, ax = plt.subplots(figsize=(10, 5.5), dpi=150)

        x = np.arange(len(labels))
        bar_colors = [COLORS[i % len(COLORS)] for i in range(len(labels))]
        bars = ax.bar(x, values, width=0.6, color=bar_colors, edgecolor="none")

        # 数值标签
        for bar in bars:
            h = bar.get_height()
            ax.annotate(
                f"{h:,.0f}" if h == int(h) else f"{h:,.1f}",
                xy=(bar.get_x() + bar.get_width() / 2, h),
                xytext=(0, 4),
                textcoords="offset points",
                ha="center", va="bottom",
                fontsize=10, color="#555555",
            )

        ax.set_xticks(x)
        ax.set_xticklabels(labels, fontsize=11, color="#333333")
        ax.set_title(title, fontsize=14, color="#333333", pad=12, fontweight="bold")

        # 样式：去除顶部和右侧边框
        ax.spines["top"].set_visible(False)
        ax.spines["right"].set_visible(False)
        ax.spines["left"].set_color("#e0e0e0")
        ax.spines["bottom"].set_color("#e0e0e0")
        ax.yaxis.grid(True, linestyle="--", alpha=0.3, color="#cccccc")
        ax.set_axisbelow(True)

        plt.tight_layout()
        plt.savefig(output_path, dpi=150, bbox_inches="tight",
                    facecolor="white", edgecolor="none")
        plt.close(fig)

        logger.info(f"柱状图已生成: {output_path}")
        return output_path

    except Exception as exc:
        logger.error(f"柱状图生成失败: {exc}", exc_info=True)
        plt.close("all")
        return None


def generate_pie_chart(
    title: str,
    labels: list[str],
    values: list[float],
    output_path: Optional[str] = None,
) -> Optional[str]:
    """
    生成莫兰迪饼图并保存为 PNG。

    Args:
        title: 图表标题
        labels: 类目名称
        values: 对应数值（自动计算百分比）
        output_path: 输出路径

    Returns:
        PNG 文件路径，失败返回 None
    """
    _ensure_matplotlib()
    if not _MPL_READY:
        return None

    import matplotlib.pyplot as plt

    try:
        if not output_path:
            fd, output_path = tempfile.mkstemp(suffix=".png", prefix="chart_pie_")
            os.close(fd)

        fig, ax = plt.subplots(figsize=(8, 6), dpi=150)

        pie_colors = [COLORS[i % len(COLORS)] for i in range(len(labels))]
        explode = [0.02] * len(labels)

        wedges, texts, autotexts = ax.pie(
            values,
            explode=explode,
            labels=labels,
            colors=pie_colors,
            autopct="%1.1f%%",
            startangle=90,
            pctdistance=0.6,
            wedgeprops={"edgecolor": "white", "linewidth": 2},
        )

        for t in texts:
            t.set_fontsize(11)
            t.set_color("#333333")
        for at in autotexts:
            at.set_fontsize(10)
            at.set_color("white")
            at.set_weight("bold")

        ax.set_title(title, fontsize=14, color="#333333", pad=16, fontweight="bold")
        ax.axis("equal")

        plt.tight_layout()
        plt.savefig(output_path, dpi=150, bbox_inches="tight",
                    facecolor="white", edgecolor="none")
        plt.close(fig)

        logger.info(f"饼图已生成: {output_path}")
        return output_path

    except Exception as exc:
        logger.error(f"饼图生成失败: {exc}", exc_info=True)
        plt.close("all")
        return None


def generate_radar_chart(
    title: str,
    categories: list[str],
    series: dict[str, list[float]],
    output_path: Optional[str] = None,
) -> Optional[str]:
    """
    生成莫兰迪雷达图并保存为 PNG。

    WHY: 雷达图适合多维度对比（如方案 A vs B 在安全/经济/工期等指标上的表现），
         在工程测算中常用于综合评价。

    Args:
        title: 图表标题
        categories: 各维度名称（如 ["安全性", "经济性", "工期"]）
        series: {系列名: [数值列表]}，支持多系列对比
        output_path: 输出路径

    Returns:
        PNG 文件路径，失败返回 None
    """
    _ensure_matplotlib()
    if not _MPL_READY:
        return None

    import matplotlib.pyplot as plt
    import numpy as np

    try:
        if not output_path:
            fd, output_path = tempfile.mkstemp(suffix=".png", prefix="chart_radar_")
            os.close(fd)

        n = len(categories)
        # WHY: 雷达图需要闭合，所以角度数组多一个回到起点
        angles = np.linspace(0, 2 * np.pi, n, endpoint=False).tolist()
        angles += angles[:1]

        fig, ax = plt.subplots(figsize=(8, 8), dpi=150,
                               subplot_kw={"projection": "polar"})

        for i, (name, vals) in enumerate(series.items()):
            color = COLORS[i % len(COLORS)]
            closed_vals = vals + vals[:1]
            ax.plot(angles, closed_vals, "o-", linewidth=2,
                    label=name, color=color, markersize=6)
            ax.fill(angles, closed_vals, alpha=0.15, color=color)

        ax.set_xticks(angles[:-1])
        ax.set_xticklabels(categories, fontsize=11, color="#333333")

        # WHY: 设置 y 轴范围为数据最大值的 110%，留出标注空间
        all_vals = [v for vs in series.values() for v in vs]
        ax.set_ylim(0, max(all_vals) * 1.15 if all_vals else 100)
        ax.yaxis.grid(True, linestyle="--", alpha=0.3, color="#cccccc")
        ax.xaxis.grid(True, linestyle="-", alpha=0.2, color="#e0e0e0")

        ax.set_title(title, fontsize=14, color="#333333",
                     pad=20, fontweight="bold")

        if len(series) > 1:
            ax.legend(loc="upper right", bbox_to_anchor=(1.25, 1.1),
                      fontsize=10, framealpha=0.8)

        plt.tight_layout()
        plt.savefig(output_path, dpi=150, bbox_inches="tight",
                    facecolor="white", edgecolor="none")
        plt.close(fig)

        logger.info(f"雷达图已生成: {output_path}")
        return output_path

    except Exception as exc:
        logger.error(f"雷达图生成失败: {exc}", exc_info=True)
        plt.close("all")
        return None


# ── 标记解析 ──
# 匹配 [可视化：柱状图/饼图/雷达图，标题：XXX]
CHART_MARKER_RE = re.compile(
    r"\[可视化[：:]"
    r"\s*(柱状图|饼图|雷达图)\s*"
    r"[，,]\s*标题[：:]\s*(.+?)\s*\]"
)


def parse_chart_marker(text: str) -> Optional[dict]:
    """
    从文本行中解析图表标记。

    Returns:
        {"type": "bar"|"pie"|"radar", "title": "..."} 或 None
    """
    m = CHART_MARKER_RE.search(text)
    if not m:
        return None
    type_map = {"柱状图": "bar", "饼图": "pie", "雷达图": "radar"}
    return {"type": type_map.get(m.group(1), "bar"), "title": m.group(2)}


def _parse_raw_rows(lines: list[str]) -> list[list[str]]:
    """从 Markdown 表格行中提取原始数据行（跳过分隔行）。"""
    sep_re = re.compile(r"^\|\s*[-:]+\s*(\|\s*[-:]+\s*)*\|$")
    rows = []
    for line in lines:
        stripped = line.strip()
        if not stripped.startswith("|") or not stripped.endswith("|"):
            break
        if sep_re.match(stripped):
            continue
        cells = [c.strip() for c in stripped.strip("|").split("|")]
        if len(cells) >= 2:
            rows.append(cells)
    return rows


def _extract_number(text: str) -> Optional[float]:
    """从文本中提取数字（去掉逗号、单位等）。"""
    raw = re.sub(r"[,\s元亩万%分]", "", text)
    try:
        return float(raw)
    except ValueError:
        return None


def parse_table_data(lines: list[str]) -> Optional[tuple[list[str], list[float]]]:
    """
    从 Markdown 表格行中解析标签和数值（两列模式）。

    Returns:
        (labels, values) 或 None
    """
    data_rows = _parse_raw_rows(lines)
    if len(data_rows) < 2:
        return None

    labels = []
    values = []
    for row in data_rows[1:]:
        val = _extract_number(row[1])
        if val is not None:
            labels.append(row[0])
            values.append(val)
        else:
            logger.warning(f"无法解析数值: {row[1]!r}，跳过此行")

    if not labels or not values or len(labels) != len(values):
        return None
    return labels, values


def parse_table_data_multi(
    lines: list[str],
) -> Optional[tuple[list[str], dict[str, list[float]]]]:
    """
    从 Markdown 表格行中解析多系列数据（雷达图专用）。
    WHY: 雷达图常用于多方案对比，表格有 3+ 列：
         | 指标 | 方案A | 方案B |

    Returns:
        (categories, {series_name: [values]}) 或 None
    """
    data_rows = _parse_raw_rows(lines)
    if len(data_rows) < 2:
        return None

    header = data_rows[0]
    if len(header) < 2:
        return None

    series_names = header[1:]  # 第一列是分类，其余列是系列
    categories = []
    series: dict[str, list[float]] = {name: [] for name in series_names}

    for row in data_rows[1:]:
        categories.append(row[0])
        for j, name in enumerate(series_names):
            col_idx = j + 1
            if col_idx < len(row):
                val = _extract_number(row[col_idx])
                series[name].append(val if val is not None else 0)
            else:
                series[name].append(0)

    if not categories or len(categories) < 3:
        logger.warning("雷达图至少需要 3 个维度")
        return None

    return categories, series


def generate_chart_from_marker(
    chart_info: dict,
    table_lines: list[str],
) -> Optional[str]:
    """
    根据标记信息和表格数据生成图表。

    Args:
        chart_info: parse_chart_marker 的返回值
        table_lines: 紧随标记的 Markdown 表格行

    Returns:
        生成的 PNG 文件路径，失败返回 None
    """
    if chart_info["type"] == "radar":
        # WHY: 雷达图使用多系列解析器
        parsed = parse_table_data_multi(table_lines)
        if not parsed:
            logger.warning(f"雷达图 '{chart_info['title']}' 数据解析失败")
            return None
        categories, series = parsed
        return generate_radar_chart(chart_info["title"], categories, series)

    # 柱状图 / 饼图使用两列解析器
    parsed = parse_table_data(table_lines)
    if not parsed:
        logger.warning(f"图表 '{chart_info['title']}' 数据解析失败")
        return None

    labels, values = parsed

    if chart_info["type"] == "bar":
        return generate_bar_chart(chart_info["title"], labels, values)
    elif chart_info["type"] == "pie":
        return generate_pie_chart(chart_info["title"], labels, values)
    else:
        logger.warning(f"不支持的图表类型: {chart_info['type']}")
        return None
