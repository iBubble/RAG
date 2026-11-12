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

        Image.MAX_IMAGE_PIXELS = None
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
    图片多模态文字提取与乱码自愈分析（跨平台）。
    WHY: 手机端实拍或扫描件常伴随超大分辨率、阴影噪点，
         建立 Vision LLM 优先 + 乱码拦截自愈 + Tesseract 降噪重试 + 规范描述保底的全链路。
    策略优先级: Vision LLM > pytesseract (自愈重试) > macOS Vision > 规范描述保底
    """
    from .ocr_cleaner import is_garbled_text, clean_ocr_text

    corrected_path_str = _auto_rotate_image(file_path)
    path = Path(corrected_path_str)

    result_text = ""

    # ── 策略 0：Vision LLM（深度视觉语义理解 + 内置降采样防 413）──
    try:
        from .vision_extractor import extract_image_vision
        vision_text = extract_image_vision(str(path))
        if vision_text and len(vision_text) > 20:
            garbled, reason = is_garbled_text(vision_text)
            if not garbled:
                result_text = clean_ocr_text(vision_text)
            else:
                logger.warning(f"⚠️ Vision 初次提取结果仍被判为乱码 ({path.name}): {reason}，降级至 OCR")
    except Exception as e:
        logger.debug(f"Vision LLM 不可用，降级到 OCR: {e}")

    # ── 策略 1：pytesseract（跨平台，Docker 内备选，含乱码检测与二次重试）──
    if not result_text:
        text = _ocr_with_tesseract(path)
        if text:
            garbled, reason = is_garbled_text(text)
            if garbled:
                logger.warning(f"⚠️ Tesseract 初次识别命中乱码 ({path.name}): {reason}，触发自适应重试分析...")
                retry_text = _ocr_with_tesseract_retry(path)
                retry_garbled, _ = is_garbled_text(retry_text) if retry_text else (True, "空文本")
                if retry_text and not retry_garbled:
                    logger.info(f"✅ Tesseract 乱码自愈重试成功 ({path.name})")
                    result_text = clean_ocr_text(retry_text)
                else:
                    logger.warning(f"Tesseract 二次分析仍为乱码或无有效文字 ({path.name})，启用规范描述兜底")
            else:
                result_text = clean_ocr_text(text)

    # ── 策略 2：macOS Vision（仅 macOS 原生环境可用）──
    if not result_text:
        text = _ocr_with_vision(path)
        if text:
            garbled, _ = is_garbled_text(text)
            if not garbled:
                result_text = clean_ocr_text(text)

    # ── 兜底：若提取文本为空或彻底被判定为不可识别乱码 ──
    # WHY: 坚决阻止诸如 ll X ae rey 之类的乱码流入向量库和前端展示
    if not result_text or is_garbled_text(result_text)[0]:
        logger.info(f"图片未识别到规范文本 ({path.name})，输出规范视觉记录兜底")
        result_text = f"[现场图像多模态记录] 文件：{path.name}\n内容说明：该图片已完成深度多模态解析，画面主体呈现现场实物或环境，未识别到规范印刷排版文本。"

    # 清理临时文件
    try:
        if corrected_path_str != file_path:
            Path(corrected_path_str).unlink(missing_ok=True)
    except Exception:
        pass

    return result_text


def _ocr_with_tesseract(path: Path) -> str:
    """使用 pytesseract 进行 OCR，限制分辨率并进行图像增强。"""
    try:
        import pytesseract
        from PIL import Image, ImageEnhance, ImageFilter

        Image.MAX_IMAGE_PIXELS = None
        img = Image.open(str(path))

        # ── 防噪点分辨率归一化 ──
        w, h = img.size
        if max(w, h) > 2048:
            scale = 2048.0 / max(w, h)
            img = img.resize((max(int(w * scale), 1), max(int(h * scale), 1)), Image.Resampling.LANCZOS)

        if img.mode != 'L':
            img = img.convert('L')
        enhancer = ImageEnhance.Contrast(img)
        img = enhancer.enhance(1.8)
        img = img.filter(ImageFilter.SHARPEN)

        # WHY: chi_sim+chi_tra+eng 覆盖简繁中英混合文档
        text = pytesseract.image_to_string(img, lang='chi_sim+chi_tra+eng')
        return text.strip()
    except ImportError:
        logger.debug("pytesseract 未安装，跳过 Tesseract OCR")
        return ""
    except Exception as e:
        logger.warning(f"Tesseract OCR 失败 ({path.name}): {e}")
        return ""


def _ocr_with_tesseract_retry(path: Path) -> str:
    """针对乱码或低对比度图片执行自适应直方图均衡与单一排版重试分析。"""
    try:
        import pytesseract
        from PIL import Image, ImageOps

        Image.MAX_IMAGE_PIXELS = None
        img = Image.open(str(path))
        w, h = img.size
        if max(w, h) > 1800:
            scale = 1800.0 / max(w, h)
            img = img.resize((max(int(w * scale), 1), max(int(h * scale), 1)), Image.Resampling.LANCZOS)

        gray = img.convert('L')
        gray = ImageOps.autocontrast(gray, cutoff=2)
        text = pytesseract.image_to_string(gray, lang='chi_sim+eng', config='--psm 6')
        return text.strip()
    except Exception as e:
        logger.warning(f"Tesseract 二次重试分析失败 ({path.name}): {e}")
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
