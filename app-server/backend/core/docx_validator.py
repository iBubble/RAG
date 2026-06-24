"""
docx_validator.py — 导出 Word 文件的质量验证器。
WHY: 借鉴 Kimi docx skill 的业务规则检查逻辑，
     在导出 .docx 后自动检测常见排版问题并记录警告日志。
     仅搬运对 python-docx 生成文件有意义的检查项，
     跳过 C# OpenXML SDK 特有的 element order 问题。
"""
from __future__ import annotations

import logging
import struct
import zipfile
import tempfile
from pathlib import Path
from xml.etree import ElementTree as ET

logger = logging.getLogger(__name__)

# ── XML 命名空间常量 ──
W_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
R_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
WP_NS = "http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing"
A_NS = "http://schemas.openxmlformats.org/drawingml/2006/main"
RELS_NS = "http://schemas.openxmlformats.org/package/2006/relationships"


def _check_table_grid(root: ET.Element) -> list[str]:
    """
    检查表格 gridCol 与 tcW 宽度一致性。
    WHY: 如果二者偏差 >5%，Word 渲染时表格列会歪斜。
    """
    errors = []
    tables = root.findall(f".//{{{W_NS}}}tbl")
    for idx, tbl in enumerate(tables, 1):
        grid = tbl.find(f"{{{W_NS}}}tblGrid")
        if grid is None:
            errors.append(
                f"TABLE[{idx}]: 缺少 tblGrid 定义，可能导致渲染异常"
            )
            continue

        grid_cols = grid.findall(f"{{{W_NS}}}gridCol")
        grid_widths = []
        for gc in grid_cols:
            w_val = gc.get(f"{{{W_NS}}}w")
            grid_widths.append(int(w_val) if w_val else None)

        first_row = tbl.find(f"{{{W_NS}}}tr")
        if first_row is None:
            continue

        cells = first_row.findall(f"{{{W_NS}}}tc")
        for col_idx, (cell, gw) in enumerate(zip(cells, grid_widths)):
            if gw is None:
                continue
            tc_pr = cell.find(f"{{{W_NS}}}tcPr")
            if tc_pr is None:
                continue
            tc_w = tc_pr.find(f"{{{W_NS}}}tcW")
            if tc_w is None:
                continue
            tc_width = tc_w.get(f"{{{W_NS}}}w")
            if tc_width:
                tc_int = int(tc_width)
                if abs(tc_int - gw) > gw * 0.05:
                    errors.append(
                        f"TABLE[{idx}]: 列{col_idx} gridCol={gw} ≠ tcW={tc_int}，列宽会歪斜"
                    )
    return errors


def _get_image_dimensions(data: bytes) -> tuple:
    """从 PNG/JPEG 二进制数据中读取原始宽高。"""
    try:
        if data[:8] == b"\x89PNG\r\n\x1a\n":
            w, h = struct.unpack(">II", data[16:24])
            return w, h
        if data[:2] == b"\xff\xd8":
            i = 2
            while i < len(data) - 9:
                if data[i] == 0xFF:
                    marker = data[i + 1]
                    if marker in (0xC0, 0xC2):
                        h, w = struct.unpack(">HH", data[i + 5 : i + 9])
                        return w, h
                    elif marker == 0xD9:
                        break
                    elif marker in range(0xD0, 0xD8) or marker in (0x01, 0x00):
                        i += 2
                    else:
                        length = struct.unpack(">H", data[i + 2 : i + 4])[0]
                        i += 2 + length
                else:
                    i += 1
    except Exception:
        pass
    return None, None


def _check_images(root: ET.Element, extract_dir: Path) -> list[str]:
    """
    检查图片显示比例是否与原始图片宽高比一致。
    WHY: 如果 cx/cy 与原图不等比，Word 中图片会被拉伸变形。
    """
    errors = []
    rels_map: dict[str, str] = {}
    rels_path = extract_dir / "word" / "_rels" / "document.xml.rels"
    if rels_path.exists():
        rels_root = ET.parse(rels_path).getroot()
        for rel in rels_root.findall(f".//{{{RELS_NS}}}Relationship"):
            rid = rel.get("Id")
            target = rel.get("Target")
            if rid and target:
                if not target.startswith("/"):
                    target = "word/" + target
                else:
                    target = target[1:]
                rels_map[rid] = target

    for img_idx, drawing in enumerate(
        root.findall(f".//{{{W_NS}}}drawing"), 1
    ):
        extent = drawing.find(f".//{{{WP_NS}}}extent")
        if extent is None:
            continue
        cx = extent.get("cx")
        cy = extent.get("cy")
        if not cx or not cy:
            continue
        cx_val, cy_val = int(cx), int(cy)
        if cy_val == 0:
            continue
        display_ratio = cx_val / cy_val

        blip = drawing.find(f".//{{{A_NS}}}blip")
        if blip is None:
            continue
        embed_id = blip.get(f"{{{R_NS}}}embed")
        if not embed_id or embed_id not in rels_map:
            continue

        image_path = extract_dir / rels_map[embed_id]
        if not image_path.exists():
            continue

        aw, ah = _get_image_dimensions(image_path.read_bytes())
        if aw is None or ah is None or ah == 0:
            continue
        actual_ratio = aw / ah

        if abs(display_ratio - actual_ratio) / actual_ratio > 0.05:
            errors.append(
                f"IMAGE[{img_idx}] {image_path.name}: "
                f"显示比={display_ratio:.2f} ≠ 原图比={actual_ratio:.2f}，"
                f"图片会变形"
            )
    return errors


def _check_empty_sections(root: ET.Element) -> list[str]:
    """
    检测有标题但缺少正文的章节（连续两个标题之间无段落）。
    WHY: 这是 AI 生成跳过或中断的信号，提醒用户该章节内容为空。
    """
    warnings = []
    body = root.find(f".//{{{W_NS}}}body")
    if body is None:
        return warnings

    last_heading_text = None
    has_content_after_heading = False

    for para in body.findall(f"{{{W_NS}}}p"):
        pPr = para.find(f"{{{W_NS}}}pPr")
        style_id = ""
        if pPr is not None:
            pStyle = pPr.find(f"{{{W_NS}}}pStyle")
            if pStyle is not None:
                style_id = pStyle.get(f"{{{W_NS}}}val", "")

        is_heading = style_id.startswith("Heading")

        # 获取段落文本
        text = "".join(
            t.text or ""
            for t in para.findall(f".//{{{W_NS}}}t")
        ).strip()

        if is_heading:
            if last_heading_text and not has_content_after_heading:
                warnings.append(
                    f"EMPTY: 标题「{last_heading_text}」之后无正文内容"
                )
            last_heading_text = text
            has_content_after_heading = False
        elif text:
            has_content_after_heading = True

    # 检查最后一个标题
    if last_heading_text and not has_content_after_heading:
        warnings.append(
            f"EMPTY: 标题「{last_heading_text}」之后无正文内容"
        )
    return warnings


def _check_font_consistency(root: ET.Element) -> list[str]:
    """
    检查文档中是否存在非预期的字体。
    WHY: python-docx 生成文件时，如果某些 run 漏设字体，
         Word 会回退到 Calibri 导致中文显示异常。
    """
    warnings = []
    unexpected_fonts = set()
    # WHY: 本项目标准字体集
    expected_fonts = {
        "SimHei", "FangSong", "Times New Roman",
        "SimSun", "KaiTi", "Calibri", ""
    }

    for rFonts in root.findall(f".//{{{W_NS}}}rFonts"):
        ea = rFonts.get(f"{{{W_NS}}}eastAsia", "")
        if ea and ea not in expected_fonts:
            unexpected_fonts.add(ea)

    if unexpected_fonts:
        warnings.append(
            f"FONT: 发现非标准中文字体 {unexpected_fonts}，"
            f"可能导致其他机器上显示异常"
        )
    return warnings


def validate_exported_docx(docx_path: str) -> dict:
    """
    对导出的 .docx 文件执行全套质量检查。
    返回 {"errors": [...], "warnings": [...]}。
    errors = 严重问题（表格歪斜、图片变形）
    warnings = 提示信息（空章节、非标准字体）
    """
    errors: list[str] = []
    warnings: list[str] = []

    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            extract_dir = Path(tmpdir) / "extracted"

            with zipfile.ZipFile(docx_path, "r") as zf:
                zf.extractall(extract_dir)

            doc_path = extract_dir / "word" / "document.xml"
            if not doc_path.exists():
                errors.append("STRUCTURE: word/document.xml 缺失，文件损坏")
                return {"errors": errors, "warnings": warnings}

            root = ET.parse(doc_path).getroot()

            # ── 执行各检查项 ──
            errors.extend(_check_table_grid(root))
            errors.extend(_check_images(root, extract_dir))
            warnings.extend(_check_empty_sections(root))
            warnings.extend(_check_font_consistency(root))

    except zipfile.BadZipFile:
        errors.append("STRUCTURE: 文件损坏，不是有效的 .docx")
    except Exception as e:
        errors.append(f"VALIDATE: 验证过程异常 — {e}")

    # 记录日志
    if errors:
        logger.warning(f"导出质检发现 {len(errors)} 个错误: {errors}")
    if warnings:
        logger.info(f"导出质检提示 {len(warnings)} 条: {warnings}")
    if not errors and not warnings:
        logger.info("导出质检通过 ✅")

    return {"errors": errors, "warnings": warnings}
