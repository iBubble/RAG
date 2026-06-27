"""
Docling 文档解析器 — 升级计划 D2 集成。

WHY: 当前 PDF 解析依赖 PyMuPDF 的纯文本提取（纯 CPU）+ Vision LLM 逐页解析（需卸载 35B），
     速度慢且不稳定。Docling 提供 CPU 端轻量级视觉解析，支持：
     1. 表格结构保护（跨行跨列不丢失）
     2. 段落层级识别（section_header / list_item / table_caption）
     3. 双栏排版正确还原
     无需 GPU，不与 Ollama 争抢统一内存。
"""
from __future__ import annotations
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# 标记 Docling 是否可用
_docling_available = False
try:
    from docling.document_converter import DocumentConverter
    _docling_available = True
except ImportError:
    logger.info("Docling 未安装，将回退到 PyMuPDF 解析")


def is_docling_available() -> bool:
    """检查 Docling 是否已安装。"""
    return _docling_available


def extract_with_docling(file_path: str) -> Optional[str]:
    """
    使用 Docling 解析 PDF/DOCX 文档，返回纯文本。
    返回 None 表示 Docling 不可用或解析失败。

    WHY: Docling 基于轻量级视觉模型（CPU 端），
         解析速度约 1.5 页/秒，内存开销 ~200MB，
         与 35B 大模型共存无压力。
    """
    if not _docling_available:
        return None

    try:
        converter = DocumentConverter()
        result = converter.convert(file_path)
        md_text = result.document.export_to_markdown()

        if not md_text or len(md_text.strip()) < 10:
            logger.warning(
                f"Docling 解析 {Path(file_path).name} "
                f"结果过短({len(md_text)}字符)，回退到 PyMuPDF"
            )
            return None

        logger.info(
            f"✅ Docling 解析 {Path(file_path).name} 成功: "
            f"{len(md_text)} 字符"
        )
        return md_text

    except Exception as e:
        logger.warning(f"Docling 解析失败: {e}，回退到 PyMuPDF")
        return None
