import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════
# 图片 OCR 文字识别模块
# WHY: 工程类文件含大量扫描件（地价分布图、规划图等），
#      必须通过 OCR 提取文字后才能入库供 AI 检索。
# 实现: 调用 macOS 原生 Vision 框架（Swift 编译工具），
#      零 Python 依赖，Apple Silicon 硬件加速。
# ═══════════════════════════════════════════════════════════════

# OCR 二进制缓存路径
_ocr_binary_cache: Optional[str] = None


def _get_ocr_binary() -> Optional[str]:
    """
    获取或编译 OCR 二进制工具。
    WHY: Swift 脚本每次执行需重新编译（约 2-3 秒），
         预编译为二进制后执行仅需毫秒级，适合批量处理。
    策略: 自动检测 Swift 源码变更，按需重新编译。
    """
    global _ocr_binary_cache
    if _ocr_binary_cache and Path(_ocr_binary_cache).exists():
        return _ocr_binary_cache

    tools_dir = Path(__file__).parent.parent / "tools"
    swift_src = tools_dir / "ocr_vision.swift"
    binary = tools_dir / "ocr_vision"

    if not swift_src.exists():
        logger.error(f"OCR Swift 源码不存在: {swift_src}")
        return None

    # 检查是否需要编译（二进制不存在或源码更新）
    need_compile = (
        not binary.exists()
        or binary.stat().st_mtime < swift_src.stat().st_mtime
    )

    if need_compile:
        import subprocess
        logger.info("正在编译 macOS Vision OCR 工具...")
        try:
            result = subprocess.run(
                ["swiftc", "-O", str(swift_src), "-o", str(binary)],
                capture_output=True, text=True, timeout=60
            )
            if result.returncode != 0:
                logger.error(f"编译 OCR 工具失败: {result.stderr}")
                return None
            logger.info("OCR 工具编译完成")
        except FileNotFoundError:
            logger.error("swiftc 不可用，请安装 Xcode Command Line Tools")
            return None
        except subprocess.TimeoutExpired:
            logger.error("OCR 工具编译超时")
            return None

    _ocr_binary_cache = str(binary)
    return _ocr_binary_cache


def _auto_rotate_image(file_path: str) -> str:
    """
    根据 EXIF 信息自动矫正图片旋转，返回矫正后的临时文件路径。
    如果没有旋转或失败，返回原路径。
    """
    try:
        from PIL import Image, ImageOps
        import tempfile
        
        img = Image.open(file_path)
        if hasattr(img, '_getexif') and img._getexif() is not None:
            corrected_img = ImageOps.exif_transpose(img)
            if corrected_img is not img:
                with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
                    corrected_img.save(tmp.name, format="PNG")
                    return tmp.name
    except Exception as e:
        logger.warning(f"图片自动旋转矫正失败 ({file_path}): {e}")
        
    return file_path


def _extract_image(file_path: str) -> str:
    """
    图片 OCR 文字提取（跨平台）。
    WHY: 工程扫描件（地价分布图、红线图等）必须 OCR 提取后才能检索。
    策略优先级: Vision LLM > pytesseract > macOS Vision
    """
    corrected_path_str = _auto_rotate_image(file_path)
    path = Path(corrected_path_str)
    
    result_text = ""

    # ── 策略 0：Vision LLM（深度视觉语义理解）──
    # WHY: Vision 模型不仅能 OCR 文字，还能理解图表、空间关系等
    try:
        from .vision_extractor import extract_image_vision
        vision_text = extract_image_vision(str(path))
        if vision_text and len(vision_text) > 20:
            result_text = vision_text
    except Exception as e:
        logger.debug(f"Vision LLM 不可用，降级到 OCR: {e}")

    # ── 策略 1：pytesseract（跨平台，Docker 内首选）──
    if not result_text:
        text = _ocr_with_tesseract(path)
        if text:
            result_text = text

    # ── 策略 2：macOS Vision（仅 macOS 原生环境可用）──
    if not result_text:
        text = _ocr_with_vision(path)
        if text:
            result_text = text

    if not result_text:
        logger.info(f"图片未识别到文字: {path.name}")
        result_text = f"[图片] {path.name}（未识别到文字内容）"

    # 清理临时文件
    try:
        if corrected_path_str != file_path:
            Path(corrected_path_str).unlink(missing_ok=True)
    except Exception:
        pass

    return result_text


def _ocr_with_tesseract(path: Path) -> str:
    """使用 pytesseract 进行 OCR，支持中英文混合。"""
    try:
        import pytesseract
        from PIL import Image, ImageEnhance, ImageFilter

        img = Image.open(str(path))
        
        # ── OCR 图像预处理增强 ──
        # WHY: 扫描件常常对比度低或有噪点，通过灰度化、对比度增强和锐化，提升 Tesseract 识别率
        try:
            if img.mode != 'L':
                img = img.convert('L')
            enhancer = ImageEnhance.Contrast(img)
            img = enhancer.enhance(2.0)
            img = img.filter(ImageFilter.SHARPEN)
        except Exception as e:
            logger.debug(f"图片预处理异常: {e}")

        # WHY: chi_sim+chi_tra+eng 覆盖简繁中英混合文档
        text = pytesseract.image_to_string(img, lang='chi_sim+chi_tra+eng')
        return text.strip()
    except ImportError:
        logger.debug("pytesseract 未安装，跳过 Tesseract OCR")
        return ""
    except Exception as e:
        logger.warning(f"Tesseract OCR 失败 ({path.name}): {e}")
        return ""


def _ocr_with_vision(path: Path) -> str:
    """macOS Vision 框架 OCR（仅 macOS 可用）。"""
    import subprocess

    ocr_bin = _get_ocr_binary()
    if ocr_bin is None:
        return ""

    try:
        result = subprocess.run(
            [ocr_bin, str(path.resolve())],
            capture_output=True, text=True, timeout=120
        )
        if result.returncode != 0:
            logger.error(f"Vision OCR 失败 ({path.name}): {result.stderr.strip()}")
            return ""
        return result.stdout.strip()
    except subprocess.TimeoutExpired:
        logger.error(f"Vision OCR 超时: {path.name}")
        return ""
    except Exception as e:
        logger.error(f"Vision OCR 异常 ({path.name}): {e}")
        return ""
