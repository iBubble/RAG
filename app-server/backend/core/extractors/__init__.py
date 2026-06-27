"""
多模态文档文本提取器。
"""
from __future__ import annotations
import logging
from pathlib import Path
from typing import Optional, List

logger = logging.getLogger(__name__)

from .plain import _extract_txt
from .pdf import _extract_pdf, _extract_tables_pdf
from .pdf_parser import _extract_pdf_smart
from .office import _extract_unstructured, _extract_doc, _extract_docx, _extract_xlsx, _extract_xls, _extract_pptx, _extract_tables_xlsx, _extract_tables_docx, _extract_tables_xls, _extract_tables_pptx
from .image import _extract_image
from .caj import _extract_caj
from .gis import _extract_shp, _extract_shp_dbf, _extract_gdb, _extract_mdb, _GIS_FIELD_MAP, _GIS_LAYER_MAP
from .audio_video import _extract_audio_video
from .docling_parser import extract_with_docling, is_docling_available


def _extract_docx_smart(file_path: str) -> str:
    """DOCX 智能提取：Docling 优先 → _extract_unstructured 回退。"""
    if is_docling_available():
        result = extract_with_docling(file_path)
        if result:
            return result
    return _extract_unstructured(file_path)

def extract_text(file_path: str, is_slow_queue: bool = False) -> Optional[str]:
    """
    根据文件扩展名自动选择合适的提取器，返回纯文本。
    返回 None 表示不支持该格式。
    """
    path = Path(file_path)
    suffix = path.suffix.lower()

    extractors = {
        ".txt": _extract_txt,
        ".md": _extract_txt,
        ".csv": _extract_txt,
        ".log": _extract_txt,
        ".json": _extract_txt,
        ".xml": _extract_txt,
        ".html": _extract_txt,
        ".htm": _extract_txt,
        ".pdf": _extract_pdf_smart,
        ".doc": _extract_doc,
        ".docx": _extract_docx_smart,
        ".xlsx": _extract_xlsx,
        ".xls": _extract_xls,
        ".pptx": _extract_unstructured,
        ".caj": _extract_caj,
        ".shp": _extract_shp,
        ".dbf": _extract_shp_dbf,
        ".gdb": _extract_gdb,
        ".mdb": _extract_mdb,
        # 图片（OCR 文字识别）
        ".jpg": _extract_image,
        ".jpeg": _extract_image,
        ".png": _extract_image,
        ".bmp": _extract_image,
        ".tiff": _extract_image,
        ".tif": _extract_image,
        ".webp": _extract_image,
        # 音视频识别
        ".mp3": _extract_audio_video,
        ".wav": _extract_audio_video,
        ".mp4": _extract_audio_video,
        ".mov": _extract_audio_video,
    }

    extractor = extractors.get(suffix)
    if extractor is None:
        logger.warning(f"不支持的文件格式: {suffix} ({path.name})")
        return None

    try:
        if suffix == ".pdf":
            text = extractor(str(path), is_slow_queue=is_slow_queue)
        else:
            text = extractor(str(path))
        logger.info(f"成功提取 {path.name}：{len(text)} 字符")
        return text
    except Exception as e:
        logger.error(f"提取 {path.name} 失败: {e}")
        return None


def extract_tables(file_path: str) -> List[dict]:
    """
    统一入口：从文件中提取所有结构化表格实体。
    返回 List[dict]，每个 dict 包含完整的表格结构和 Markdown 渲染。
    WHY: 与 extract_text() 并行调用，extract_text 产出文本切片用于语义检索，
         extract_tables 产出完整表格用于精确直插入。
    """
    path = Path(file_path)
    suffix = path.suffix.lower()

    try:
        if suffix == ".xlsx":
            return _extract_tables_xlsx(file_path)
        elif suffix == ".xls":
            # 复用 xlrd 读取后转为与 xlsx 相同的矩阵格式
            return _extract_tables_xls(file_path)
        elif suffix == ".docx":
            return _extract_tables_docx(file_path)
        elif suffix == ".pdf":
            return _extract_tables_pdf(file_path)
        elif suffix == ".pptx":
            return _extract_tables_pptx(file_path)
        else:
            return []
    except Exception as e:
        logger.error(f"[表格提取] 提取失败 {path.name}: {e}")
        return []

