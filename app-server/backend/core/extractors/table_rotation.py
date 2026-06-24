"""
扫描件表格自动旋转检测。

WHY: 工程图纸/水利文档中大量横向表格（90°旋转），
     Vision LLM 对旋转表格的识别率很低。
     借鉴 RAGFlow DeepDoc 的 Table Auto-Rotation：
     评估 0°/90°/180°/270° 四个角度的文字置信度，选最优方向。

     本模块使用纯 Python 方案（基于文字行方向检测），
     不依赖外部 tesseract OCR。
"""
from __future__ import annotations

import logging
from io import BytesIO
from typing import Optional

from PIL import Image

logger = logging.getLogger(__name__)


def _estimate_text_orientation(image: Image.Image) -> float:
    """
    用图像边缘分析估计文字方向得分。
    WHY: 正确方向的文本图片中水平边缘比垂直边缘更密集。
         通过统计灰度梯度的方向分布来判断。
    返回: 0-1 的置信度（越高越可能是正确方向）。
    """
    try:
        import numpy as np

        # 转灰度、缩放加速
        gray = image.convert("L")
        w, h = gray.size
        scale = min(1.0, 800 / max(w, h))
        if scale < 1.0:
            gray = gray.resize(
                (int(w * scale), int(h * scale)),
                Image.Resampling.LANCZOS,
            )

        arr = np.array(gray, dtype=np.float32)

        # WHY: 正确方向的文本，水平梯度（字间距）应该比垂直梯度（行间距）更弱。
        #      正确方向下 vertical_energy / horizontal_energy 比值更高。
        grad_h = np.abs(np.diff(arr, axis=1))  # 水平梯度
        grad_v = np.abs(np.diff(arr, axis=0))  # 垂直梯度

        h_energy = float(grad_h.mean())
        v_energy = float(grad_v.mean())

        if h_energy + v_energy == 0:
            return 0.5

        # WHY: 文本行是横排时，垂直梯度（行间距跳变）更显著。
        #      score 越高说明越像正确方向。
        score = v_energy / (h_energy + v_energy)
        return score

    except ImportError:
        logger.warning("numpy 不可用，跳过旋转检测")
        return 0.5
    except Exception as e:
        logger.warning(f"旋转检测异常: {e}")
        return 0.5


def find_best_rotation(image: Image.Image) -> int:
    """
    评估 4 个旋转角度的文字方向得分，返回最优旋转角度。

    返回: 0, 90, 180, 或 270（度），表示应对原图施加的旋转角度。
    """
    best_angle = 0
    best_score = -1.0

    for angle in [0, 90, 180, 270]:
        if angle == 0:
            rotated = image
        else:
            rotated = image.rotate(angle, expand=True)

        score = _estimate_text_orientation(rotated)
        logger.debug(f"旋转 {angle}°: 方向得分 = {score:.4f}")

        if score > best_score:
            best_score = score
            best_angle = angle

    if best_angle != 0:
        logger.info(f"📐 检测到表格需旋转 {best_angle}°（得分: {best_score:.4f}）")
    return best_angle


def auto_rotate_table_image(image: Image.Image) -> tuple[Image.Image, int]:
    """
    自动检测并旋转表格图片到正确方向。

    返回: (旋转后的图片, 旋转角度)
    """
    angle = find_best_rotation(image)
    if angle == 0:
        return image, 0
    rotated = image.rotate(angle, expand=True)
    return rotated, angle


def auto_rotate_from_bytes(
    image_bytes: bytes, format: str = "PNG"
) -> tuple[bytes, int]:
    """
    从 bytes 输入自动旋转，返回旋转后的 bytes 和角度。
    WHY: 便于集成到 Vision LLM 处理管线中。
    """
    image = Image.open(BytesIO(image_bytes))
    rotated, angle = auto_rotate_table_image(image)
    if angle == 0:
        return image_bytes, 0

    buf = BytesIO()
    rotated.save(buf, format=format)
    return buf.getvalue(), angle
