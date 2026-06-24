"""
LaTeX → Word 原生公式 (OMML) 转换器。

WHY: LLM 生成的报告含数学公式（如灌溉水利用系数 η渠×η田=0.65×0.85），
     导出 Word 时需要渲染为可双击编辑的原生数学公式，而非纯文本。

转换链路: LaTeX → MathML (latex2mathml) → OMML (纯 Python lxml 递归转换)

示例:
    >>> from core.latex_to_omml import split_text_and_math
    >>> segments = split_text_and_math("灌溉系数为 $$\\eta=0.65$$ 。")
    >>> # [{"type":"text","value":"灌溉系数为 "},
    >>> #  {"type":"omml","value":"<m:oMath>...</m:oMath>"},
    >>> #  {"type":"text","value":" 。"}]
"""
from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)

# WHY: OMML 命名空间是 Word 数学公式的固定前缀
OMML_NS = "http://schemas.openxmlformats.org/officeDocument/2006/math"
_OMML = "{" + OMML_NS + "}"


def _make_run(text: str):
    """创建 OMML 文本 run 节点 <m:r><m:t>text</m:t></m:r>。"""
    from lxml import etree
    r = etree.Element(f"{_OMML}r")
    t = etree.SubElement(r, f"{_OMML}t")
    t.text = text or ""
    return r


def _mml_to_omml(elem) -> list:
    """
    递归将 MathML 元素转为 OMML 元素列表。

    WHY: 覆盖工程报告中常见的数学结构：
         mi/mo/mn(标识符/运算符/数字)、mfrac(分数)、msub/msup(下标/上标)、
         msubsup(上下标)、msqrt/mroot(根号)、mfenced(括号)、mover/munder(上下标记)。
    """
    from lxml import etree

    tag = etree.QName(elem).localname if isinstance(elem.tag, str) else ""

    if tag == "math":
        # 顶层 <math> → <m:oMath>
        omath = etree.Element(f"{_OMML}oMath")
        for child in elem:
            for node in _mml_to_omml(child):
                omath.append(node)
        return [omath]

    elif tag == "mrow":
        # WHY: mrow 是纯分组容器，展平其子元素
        results = []
        for child in elem:
            results.extend(_mml_to_omml(child))
        return results

    elif tag in ("mi", "mo", "mn", "mtext"):
        text = (elem.text or "").strip()
        return [_make_run(text)] if text else []

    elif tag == "mfrac":
        children = list(elem)
        if len(children) >= 2:
            f = etree.Element(f"{_OMML}f")
            num = etree.SubElement(f, f"{_OMML}num")
            den = etree.SubElement(f, f"{_OMML}den")
            for node in _mml_to_omml(children[0]):
                num.append(node)
            for node in _mml_to_omml(children[1]):
                den.append(node)
            return [f]
        return []

    elif tag == "msub":
        children = list(elem)
        if len(children) >= 2:
            s = etree.Element(f"{_OMML}sSub")
            e = etree.SubElement(s, f"{_OMML}e")
            sub = etree.SubElement(s, f"{_OMML}sub")
            for node in _mml_to_omml(children[0]):
                e.append(node)
            for node in _mml_to_omml(children[1]):
                sub.append(node)
            return [s]
        return []

    elif tag == "msup":
        children = list(elem)
        if len(children) >= 2:
            s = etree.Element(f"{_OMML}sSup")
            e = etree.SubElement(s, f"{_OMML}e")
            sup = etree.SubElement(s, f"{_OMML}sup")
            for node in _mml_to_omml(children[0]):
                e.append(node)
            for node in _mml_to_omml(children[1]):
                sup.append(node)
            return [s]
        return []

    elif tag == "msubsup":
        children = list(elem)
        if len(children) >= 3:
            s = etree.Element(f"{_OMML}sSubSup")
            e = etree.SubElement(s, f"{_OMML}e")
            sub = etree.SubElement(s, f"{_OMML}sub")
            sup = etree.SubElement(s, f"{_OMML}sup")
            for node in _mml_to_omml(children[0]):
                e.append(node)
            for node in _mml_to_omml(children[1]):
                sub.append(node)
            for node in _mml_to_omml(children[2]):
                sup.append(node)
            return [s]
        return []

    elif tag == "msqrt":
        rad = etree.Element(f"{_OMML}rad")
        # WHY: OMML 的 rad 需要 radPr 指定隐藏次数
        rpr = etree.SubElement(rad, f"{_OMML}radPr")
        deg_hide = etree.SubElement(rpr, f"{_OMML}degHide")
        deg_hide.set(f"{_OMML}val", "1")
        deg = etree.SubElement(rad, f"{_OMML}deg")  # 空的次数
        e = etree.SubElement(rad, f"{_OMML}e")
        for child in elem:
            for node in _mml_to_omml(child):
                e.append(node)
        return [rad]

    elif tag == "mroot":
        children = list(elem)
        if len(children) >= 2:
            rad = etree.Element(f"{_OMML}rad")
            deg = etree.SubElement(rad, f"{_OMML}deg")
            e = etree.SubElement(rad, f"{_OMML}e")
            for node in _mml_to_omml(children[0]):
                e.append(node)
            for node in _mml_to_omml(children[1]):
                deg.append(node)
            return [rad]
        return []

    elif tag == "mfenced":
        # WHY: <mfenced open="(" close=")"> → OMML 的 <m:d>
        d = etree.Element(f"{_OMML}d")
        dPr = etree.SubElement(d, f"{_OMML}dPr")
        beg = etree.SubElement(dPr, f"{_OMML}begChr")
        beg.set(f"{_OMML}val", elem.get("open", "("))
        end_chr = etree.SubElement(dPr, f"{_OMML}endChr")
        end_chr.set(f"{_OMML}val", elem.get("close", ")"))
        e = etree.SubElement(d, f"{_OMML}e")
        for child in elem:
            for node in _mml_to_omml(child):
                e.append(node)
        return [d]

    elif tag in ("mover", "munder"):
        # WHY: 上/下标记（如 ∑ 的上下界）降级为简单文本拼接
        results = []
        for child in elem:
            results.extend(_mml_to_omml(child))
        return results

    elif tag == "mspace":
        return [_make_run(" ")]

    # WHY: 未识别的标签，尝试递归处理子元素
    results = []
    if elem.text and elem.text.strip():
        results.append(_make_run(elem.text.strip()))
    for child in elem:
        results.extend(_mml_to_omml(child))
    return results


def latex_to_omml(latex_str: str) -> str | None:
    """
    将单个 LaTeX 公式转为 OMML XML 字符串。

    WHY: 失败时返回 None，调用方可降级为纯文本输出。

    Args:
        latex_str: 不含 $ 定界符的纯 LaTeX 公式

    Returns:
        OMML XML 字符串（含 m:oMath 根节点），失败返回 None
    """
    try:
        from latex2mathml.converter import convert
        from lxml import etree

        # 注册命名空间前缀，使输出更易读
        etree.register_namespace("m", OMML_NS)

        mathml_str = convert(latex_str)
        mathml_tree = etree.fromstring(mathml_str.encode("utf-8"))
        omml_nodes = _mml_to_omml(mathml_tree)

        if not omml_nodes:
            return None

        # 取第一个（应该就是 oMath 根节点）
        omml_root = omml_nodes[0]
        return etree.tostring(omml_root, encoding="unicode")

    except Exception as e:
        logger.warning(f"LaTeX→OMML 转换失败: {e} | latex={latex_str[:50]}")
        return None


def split_text_and_math(text: str) -> list[dict]:
    """
    将含公式的文本拆分为 text/omml 交替片段。

    WHY: 一个段落中可能混合自然语言和数学公式，
         需要拆分后分别处理——文本用 Word Run，公式用 OMML。

    Args:
        text: 含 $...$ 或 $$...$$ 的文本

    Returns:
        片段列表，每个片段为 {"type": "text"|"omml", "value": "..."}
    """
    # WHY: 先匹配 $$...$$ (块级)，再匹配 $...$ (行内)，避免 $$ 被拆成两个 $
    pattern = re.compile(r"\$\$(.+?)\$\$|\$(.+?)\$", re.DOTALL)

    segments: list[dict] = []
    last_end = 0

    for m in pattern.finditer(text):
        # 前面的纯文本
        if m.start() > last_end:
            segments.append({
                "type": "text",
                "value": text[last_end:m.start()],
            })

        latex = m.group(1) or m.group(2)
        omml = latex_to_omml(latex.strip())
        if omml:
            segments.append({"type": "omml", "value": omml})
        else:
            # WHY: 降级——保留原始 LaTeX 文本，不阻断导出
            segments.append({"type": "text", "value": m.group(0)})

        last_end = m.end()

    # 尾部文本
    if last_end < len(text):
        segments.append({"type": "text", "value": text[last_end:]})

    return segments
