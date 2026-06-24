"""
docx_cover.py — 莫兰迪封面背景图生成器。

使用 Pillow 绘制 A4 尺寸封面背景（300DPI），
包含渐变底色、几何装饰元素、项目标题和编制信息。

WHY: 替代 Playwright 方案，零额外依赖，启动快。
     封面以简约几何 + 莫兰迪色系为主，Pillow 完全胜任。
"""
from __future__ import annotations

import os
import math
import tempfile
import logging
from datetime import datetime
from typing import Optional

from PIL import Image, ImageDraw, ImageFont

logger = logging.getLogger(__name__)

# ── A4 @300DPI 尺寸 ──
A4_W, A4_H = 2480, 3508

# ── 莫兰迪色板 ──
MORANDI = {
    "bg_top": (201, 192, 182),      # #C9C0B6 温暖灰棕
    "bg_bottom": (232, 224, 216),    # #E8E0D8 浅暖灰
    "accent_1": (139, 157, 195),     # #8B9DC3 雾蓝
    "accent_2": (156, 175, 136),     # #9CAF88 灰绿
    "accent_3": (196, 164, 132),     # #C4A484 驼色
    "accent_4": (201, 169, 166),     # #C9A9A6 玫瑰灰
    "line": (124, 152, 133),         # #7C9885 深灰绿
    "title": (60, 60, 60),           # #3C3C3C 深灰
    "subtitle": (100, 100, 100),     # #646464 中灰
    "white": (255, 255, 255),
}


def _gradient_bg(draw: ImageDraw.Draw, w: int, h: int):
    """绘制垂直渐变背景（从 bg_top 到 bg_bottom）。"""
    r1, g1, b1 = MORANDI["bg_top"]
    r2, g2, b2 = MORANDI["bg_bottom"]
    for y in range(h):
        ratio = y / h
        r = int(r1 + (r2 - r1) * ratio)
        g = int(g1 + (g2 - g1) * ratio)
        b = int(b1 + (b2 - b1) * ratio)
        draw.line([(0, y), (w, y)], fill=(r, g, b))


def _decorative_elements(draw: ImageDraw.Draw, w: int, h: int):
    """绘制几何装饰元素：色块、圆形、线条。"""
    # 左上角大色块（雾蓝）
    draw.rectangle(
        [0, 0, int(w * 0.35), int(h * 0.12)],
        fill=MORANDI["accent_1"] + (60,),  # 半透明
    )

    # 右下角斜切色块（驼色）
    points = [
        (int(w * 0.6), h),
        (w, int(h * 0.82)),
        (w, h),
    ]
    draw.polygon(points, fill=MORANDI["accent_3"] + (50,))

    # 右上角小圆（灰绿，半透明）
    cx, cy, radius = int(w * 0.85), int(h * 0.08), int(w * 0.08)
    draw.ellipse(
        [cx - radius, cy - radius, cx + radius, cy + radius],
        fill=MORANDI["accent_2"] + (45,),
    )

    # 左下角小圆（玫瑰灰）
    cx2, cy2, r2 = int(w * 0.12), int(h * 0.88), int(w * 0.06)
    draw.ellipse(
        [cx2 - r2, cy2 - r2, cx2 + r2, cy2 + r2],
        fill=MORANDI["accent_4"] + (50,),
    )

    # 水平装饰线（标题区域上方）
    line_y = int(h * 0.32)
    draw.line(
        [(int(w * 0.15), line_y), (int(w * 0.85), line_y)],
        fill=MORANDI["line"] + (80,),
        width=4,
    )

    # 水平装饰线（标题区域下方）
    line_y2 = int(h * 0.52)
    draw.line(
        [(int(w * 0.15), line_y2), (int(w * 0.85), line_y2)],
        fill=MORANDI["line"] + (80,),
        width=4,
    )

    # 细装饰线条（底部）
    line_y3 = int(h * 0.78)
    draw.line(
        [(int(w * 0.25), line_y3), (int(w * 0.75), line_y3)],
        fill=MORANDI["accent_1"] + (60,),
        width=2,
    )


def _find_font(names: list[str], size: int) -> ImageFont.FreeTypeFont:
    """
    按优先级搜索系统字体。
    WHY: macOS 字体文件名含空格（如 'STHeiti Medium.ttc'），
         需要遍历目录模糊匹配而非拼接精确路径。
    """
    search_dirs = [
        "/System/Library/Fonts",
        "/System/Library/Fonts/Supplemental",
        "/Library/Fonts",
        os.path.expanduser("~/Library/Fonts"),
        "/usr/share/fonts/truetype",
        "/usr/share/fonts/opentype",
        "/usr/share/fonts/truetype/wqy",
        "/usr/share/fonts/opentype/noto",
    ]
    
    # 自动追加 Linux 常用的开源中文字体作为保底
    extended_names = names + ["wqy-zenhei", "NotoSansCJK-Regular"]

    for name in extended_names:
        name_lower = name.lower()
        for d in search_dirs:
            if not os.path.isdir(d):
                continue
            try:
                for f in os.listdir(d):
                    if name_lower in f.lower() and f.lower().endswith(
                        (".ttf", ".ttc", ".otf")
                    ):
                        path = os.path.join(d, f)
                        try:
                            return ImageFont.truetype(path, size)
                        except Exception:
                            continue
            except OSError:
                continue
                
    # 硬编码直接路径作为最后一道防线
    fallback_linux = "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc"
    if os.path.exists(fallback_linux):
        try:
            return ImageFont.truetype(fallback_linux, size)
        except:
            pass
            
    # 回退到默认字体(这在 Pillow 旧版中不支持渲染中文字符，会导致微小横线)
    logger.warning(f"未找到字体 {extended_names}，使用默认字体，可能导致乱码或字体失真过小")
    return ImageFont.load_default()



def _draw_centered_text(
    draw: ImageDraw.Draw,
    text: str,
    y: int,
    w: int,
    font: ImageFont.FreeTypeFont,
    fill: tuple,
):
    """水平居中绘制文字。"""
    bbox = draw.textbbox((0, 0), text, font=font)
    tw = bbox[2] - bbox[0]
    x = (w - tw) // 2
    draw.text((x, y), text, font=font, fill=fill)


def _wrap_title(text: str, max_chars: int = 18) -> list[str]:
    """
    将长标题拆分为多行。
    WHY: 封面标题过长会溢出，需自动换行。
    """
    if len(text) <= max_chars:
        return [text]

    lines = []
    while text:
        if len(text) <= max_chars:
            lines.append(text)
            break
        # 优先在标点处断行
        cut = max_chars
        for sep in ["—", "（", "）", "·", " ", "、"]:
            idx = text[:max_chars].rfind(sep)
            if idx > max_chars // 3:
                cut = idx + 1
                break
        lines.append(text[:cut])
        text = text[cut:]
    return lines


def generate_cover_image(
    title: str,
    org_name: str = "云南力诺科技有限公司",
    date_str: Optional[str] = None,
) -> Optional[str]:
    """
    生成莫兰迪封面背景图。

    Args:
        title: 项目/报告标题
        org_name: 编制单位名称
        date_str: 日期字符串，默认当前年月

    Returns:
        生成的 PNG 文件路径，失败返回 None
    """
    try:
        if not date_str:
            date_str = datetime.now().strftime("%Y年%m月")

        # WHY: 使用 RGBA 模式以支持半透明色块
        img = Image.new("RGBA", (A4_W, A4_H), MORANDI["bg_top"] + (255,))
        draw = ImageDraw.Draw(img, "RGBA")

        # 1. 渐变背景
        _gradient_bg(draw, A4_W, A4_H)

        # 重新创建 RGBA draw 以绘制半透明元素
        overlay = Image.new("RGBA", (A4_W, A4_H), (0, 0, 0, 0))
        overlay_draw = ImageDraw.Draw(overlay, "RGBA")

        # 2. 几何装饰
        _decorative_elements(overlay_draw, A4_W, A4_H)
        img = Image.alpha_composite(img.convert("RGBA"), overlay)
        draw = ImageDraw.Draw(img, "RGBA")

        # 3. 标题文字
        title_font = _find_font(
            ["STHeiti", "SimHei", "PingFang SC", "Heiti SC"], 120
        )
        title_lines = _wrap_title(title, max_chars=16)
        title_start_y = int(A4_H * 0.35)
        line_gap = 160

        for i, line in enumerate(title_lines):
            _draw_centered_text(
                draw, line,
                title_start_y + i * line_gap,
                A4_W, title_font,
                MORANDI["title"],
            )

        # 4. 编制单位
        org_font = _find_font(
            ["STHeiti", "Songti", "STFangsong", "FangSong"], 72
        )
        org_y = int(A4_H * 0.68)
        _draw_centered_text(
            draw, org_name, org_y, A4_W, org_font, MORANDI["subtitle"]
        )

        # 5. 日期
        date_font = _find_font(
            ["STFangsong", "FangSong", "Songti", "STHeiti"], 64
        )
        date_y = int(A4_H * 0.74)
        _draw_centered_text(
            draw, date_str, date_y, A4_W, date_font, MORANDI["subtitle"]
        )

        # 6. 底部品牌标识线
        brand_y = int(A4_H * 0.92)
        brand_font = _find_font(
            ["STFangsong", "FangSong", "Songti", "STHeiti"], 36
        )
        _draw_centered_text(
            draw, "— ShengyaoRAG 智能生成 —",
            brand_y, A4_W, brand_font,
            MORANDI["accent_1"] + (120,),
        )

        # 保存
        fd, output_path = tempfile.mkstemp(suffix=".png", prefix="cover_")
        os.close(fd)
        img.convert("RGB").save(output_path, "PNG", dpi=(300, 300))
        logger.info(f"封面背景图已生成: {output_path}")
        return output_path

    except Exception as exc:
        logger.error(f"封面背景图生成失败: {exc}", exc_info=True)
        return None
