"""
Vision LLM 图件解析模块。

WHY: 扫描型 PDF（等值线图册、工程图纸、规划图等）没有可提取的文字层，
     传统 OCR（Tesseract）只能识别零散地名，无法理解等值线数值的空间分布。
     通过多模态 Vision LLM 进行逐页视觉语义理解，将空间图形信息
     转化为结构化文本，供 RAG 检索使用。

架构: PDF → PyMuPDF 渲染 PNG → base64 编码 → Ollama /api/chat → 结构化文本
"""
from __future__ import annotations

import base64
import io
import json
import logging
import time
from pathlib import Path
from typing import Optional

import httpx

logger = logging.getLogger(__name__)

# WHY: 7B Vision 模型在复杂 CAD 工程图纸上使用分析型 Prompt 会产生
#      严重的重复幻觉（如 200+ 行重复"比例尺：1:25"）。
#      OCR-focused Prompt 更简洁、更精准，28s 内可提取完整的"说明"文本块，
#      包括关键的钢筋保护层、混凝土标号等参数。
# WHY: 2026-05-22 重大修正 — qwen2.5vl:7b 在中文密集等值线图上产生严重重复幻觉。
#      经过多轮实验，以下策略最有效：
#      1) 使用英文 Prompt（模型幻觉率显著降低）
#      2) 结构化 "name: value" 格式强制逐项输出
#      3) 配合 temperature=0 + "only visible content" 约束
#      4) 非等值线图使用中文技术 Prompt，保留工程图纸特性
_VISION_PROMPT_ISOLINE = """Please extract ALL visible Chinese city/county names from this contour/isoline map, along with the contour value written next to each name.
Format EXACTLY as:
[中文地名]: value
[中文地名]: value
Rules:
- Output the names and title in original Chinese text, DO NOT translate to English.
- Only list names and values you can ACTUALLY see on the map
- Do NOT hallucinate, guess, or repeat
- Include the map title in Chinese if visible
- Include legend items in Chinese"""
_VISION_PROMPT_TECH = """请完整准确地识别这张工程图纸中的所有文字内容。
特别注意：
1. 图纸角落的"说明"文字块（通常包含材料规格、钢筋保护层、施工要求等）
2. 表格中的所有数据
3. 标题栏信息（设计单位、审核人、图号等）
4. 所有标注的数值参数和单位
5. 如果图纸方向不正（横向、倒置或旋转），请先在心中将其旋转到正确方向后再识别
保持原文的段落结构，如有表格用 Markdown 表格格式输出。"""


def _render_pdf_pages(
    file_path: str,
    dpi: int = 300,
    max_pages: int = 30,
    max_dimension: int = 2048,
) -> list[tuple[int, bytes]]:
    """
    使用 PyMuPDF 将 PDF 每页渲染为 PNG 字节流。

    WHY: 不依赖 pdf2image/poppler，PyMuPDF 原生渲染，
         零额外系统依赖，且支持 ARM Docker 环境。

    返回: [(页码, png_bytes), ...]
    """
    import fitz

    doc = fitz.open(file_path)
    total = min(len(doc), max_pages)
    results = []

    for page_idx in range(total):
        page = doc[page_idx]
        # WHY: DPI 控制清晰度。72 DPI 是 PDF 默认，200 DPI 约放大 2.8x
        zoom = dpi / 72.0
        mat = fitz.Matrix(zoom, zoom)

        # WHY: CAD 导出的横向工程图（A1/A3）通常带 /Rotate 90 或 270，
        #      PyMuPDF 的 get_pixmap() 默认不应用页面旋转，
        #      导致渲染出的图片是侧翻的，Vision 模型识别率大幅下降。
        #      检测 page.rotation 并用反旋转矩阵矫正图像方向。
        rotation = page.rotation  # 0, 90, 180, 270
        if rotation:
            mat = mat.prerotate(-rotation)
            logger.info(
                f"  🔄 第 {page_idx+1} 页旋转矫正: {rotation}° → 0°"
            )

        pix = page.get_pixmap(matrix=mat)

        # WHY: 限制最大边长，防止超大页面撑爆 Vision 模型的图像编码器
        w, h = pix.width, pix.height
        if max(w, h) > max_dimension:
            scale = max_dimension / max(w, h)
            new_w = int(w * scale)
            new_h = int(h * scale)
            # WHY: 用 PIL 缩放比 fitz 更灵活（支持抗锯齿）
            from PIL import Image
            img = Image.frombytes("RGB", (w, h), pix.samples)
            img = img.resize((new_w, new_h), Image.LANCZOS)
            buf = io.BytesIO()
            img.save(buf, format="PNG", optimize=True)
            png_bytes = buf.getvalue()
        else:
            png_bytes = pix.tobytes("png")

        # === 表格旋转检测（基于图像内容） ===
        # WHY: page.rotation 只处理 PDF 内嵌的 /Rotate 标记，
        #      无法处理扫描件内容本身是旋转的情况（如横向表格扫描后未旋转保存）。
        #      通过灰度梯度方向分析检测文字实际方向，补充内容级旋转矫正。
        try:
            from .table_rotation import auto_rotate_from_bytes
            png_bytes, angle = auto_rotate_from_bytes(png_bytes)
            if angle:
                logger.info(f"  📐 第 {page_idx+1} 页内容旋转矫正: {angle}°")
        except Exception as rot_err:
            logger.debug(f"旋转检测跳过 (第{page_idx+1}页): {rot_err}")

        results.append((page_idx + 1, png_bytes))

    doc.close()
    logger.info(
        f"PDF 渲染完成: {Path(file_path).name}, "
        f"{total} 页, DPI={dpi}"
    )
    return results


def _call_vision_llm(
    image_bytes: bytes,
    prompt: str,
    model: str,
    ollama_url: str,
    timeout: int = 300,
    temperature: float = 0.1,
) -> str:
    """
    调用 Ollama Vision 模型解析单张图片。

    WHY: 使用同步 httpx（Celery Worker 是同步进程），
         通过 /api/chat 端点发送 base64 编码的图片。
    """
    b64_img = base64.b64encode(image_bytes).decode("utf-8")

    payload = {
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": prompt,
                "images": [b64_img],
            }
        ],
        "stream": False,
        # WHY: keep_alive="10m" 让 Vision 模型在首次加载后
        #      保留 10 分钟不被卸载，后续文件无需冷加载。
        #      10 分钟后无调用则自动释放，避免长期占用 GPU。
        "keep_alive": "10m",
        "options": {
            "temperature": temperature,
            "num_predict": 6144,
        },
    }

    # WHY: Ollama 在模型切换时偶发 503，加重试避免单页解析失败。
    import time as _time
    _max_retries = 3
    for _attempt in range(_max_retries):
        try:
            resp = httpx.post(
                f"{ollama_url}/api/chat",
                json=payload,
                timeout=httpx.Timeout(float(timeout)),
            )
            resp.raise_for_status()
            data = resp.json()
            content = data.get("message", {}).get("content", "")
            return content.strip()
        except httpx.TimeoutException:
            logger.warning(f"Vision LLM 超时 ({timeout}s)")
            return ""
        except Exception as e:
            status = getattr(getattr(e, "response", None), "status_code", 0)
            if status == 503 and _attempt < _max_retries - 1:
                logger.warning(f"Vision LLM 503 (attempt {_attempt+1}), 重试中...")
                # WHY: 503 说明模型正在切换，等待后重试
                _time.sleep(3 + _attempt * 2)
                continue
            logger.error(f"Vision LLM 调用失败: {e}")
            return ""
    return ""


def _unload_vision_model(model: str, ollama_url: str):
    """
    主动卸载 Vision 模型释放显存。

    WHY: Vision 模型按需加载，解析完毕应立即释放，
         避免与常驻的 Qwen 3.6 推理模型争抢统一内存。
    """
    try:
        httpx.post(
            f"{ollama_url}/api/generate",
            json={"model": model, "keep_alive": 0},
            timeout=10.0,
        )
        logger.info(f"🔻 Vision 模型已卸载: {model}")
    except Exception as e:
        logger.warning(f"卸载 Vision 模型失败（非致命）: {e}")


def _ocr_fallback_from_bytes(png_bytes: bytes, page_num: int = 0) -> str:
    """
    Vision LLM 超时后的 Tesseract OCR 降级方案。

    WHY: 复杂 CAD 工程图纸（大尺寸、高密度标注）可能导致 Vision LLM
         超时（5 分钟）。降级到 Tesseract OCR 虽然精度较低，
         但至少能提取部分文字入库，避免该页完全空白。
    """
    try:
        import pytesseract
        from PIL import Image
        img = Image.open(io.BytesIO(png_bytes))
        text = pytesseract.image_to_string(img, lang='chi_sim+chi_tra+eng')
        text = text.strip()
        if text and len(text) > 10:
            logger.info(
                f"  🔄 第 {page_num} 页 OCR 降级成功: {len(text)} 字"
            )
            return text
        else:
            logger.warning(f"  ❌ 第 {page_num} 页 OCR 降级结果为空或过短")
            return ""
    except ImportError:
        logger.warning("pytesseract 未安装，OCR 降级不可用")
        return ""
    except Exception as e:
        logger.warning(f"  ❌ 第 {page_num} 页 OCR 降级失败: {e}")
        return ""


def extract_pdf_vision(
    file_path: str,
    model: Optional[str] = None,
    max_pages: Optional[int] = None,
    dpi: Optional[int] = None,
    timeout: Optional[int] = None,
) -> str:
    """
    使用 Vision LLM 对扫描型 PDF 逐页进行视觉语义理解。

    返回合并后的结构化文本描述，可直接入库供 RAG 检索。
    如果 Vision 模型未配置或调用失败，返回空字符串。
    """
    from core.config import settings

    _model = model or settings.VISION_MODEL
    if not _model:
        logger.debug("Vision 模型未配置，跳过视觉解析")
        return ""

    _max_pages = max_pages or settings.VISION_MAX_PAGES
    _dpi = dpi or settings.VISION_DPI
    _timeout = timeout or settings.VISION_TIMEOUT
    _ollama_url = settings.OLLAMA_BASE_URL
    filename = Path(file_path).name

    logger.info(
        f"🔍 启动 Vision LLM 图件解析: {filename} "
        f"(model={_model}, dpi={_dpi}, max_pages={_max_pages})"
    )

    # WHY: qwen3.6:35b-q4 keep_alive=-1 永驻 GPU（23GB），
    #      导致 Vision 模型无内存可加载。调用前先卸下 q4，
    #      解析完成后心跳守护会自动重载 q4。
    try:
        httpx.post(
            f"{_ollama_url}/api/generate",
            json={"model": "qwen3.6:35b-q4", "keep_alive": 0},
            timeout=10.0,
        )
        logger.info("🔄 已卸载 qwen3.6:35b-q4，为 Vision 模型腾出显存")
    except Exception:
        pass  # 模型本就未加载时忽略

    t_start = time.time()

    # ── Step 1: 渲染 PDF 为图片 ──
    try:
        pages = _render_pdf_pages(
            file_path, dpi=_dpi, max_pages=_max_pages
        )
    except Exception as e:
        logger.error(f"PDF 渲染失败 ({filename}): {e}")
        return ""

    if not pages:
        return ""

    # ── Step 2: 逐页调用 Vision LLM ──
    # WHY: 等值线图使用英文 prompt + temperature=0 以减少重复幻觉，
    #      技术图纸使用中文 prompt 以保留工程细节。
    _is_contour = any(kw in filename for kw in ('等值线', '等高线', '等降雨量', 'isoline', 'contour'))
    _vision_prompt = _VISION_PROMPT_ISOLINE if _is_contour else _VISION_PROMPT_TECH
    _vision_temp = 0.0 if _is_contour else 0.1

    if _is_contour:
        logger.info(f"  🗺️ 检测到等值线图，使用专用 prompt (temperature={_vision_temp})")

    page_results = []
    for page_num, png_bytes in pages:
        logger.info(
            f"  📄 解析第 {page_num}/{len(pages)} 页 ({filename})..."
        )
        t_page = time.time()

        text = _call_vision_llm(
            image_bytes=png_bytes,
            prompt=_vision_prompt,
            model=_model,
            ollama_url=_ollama_url,
            timeout=_timeout,
            temperature=_vision_temp,
        )

        elapsed = time.time() - t_page
        if text:
            # WHY: 等值线图 Vision 输出常有重复行（如 "泸州: 16" 重复 200+ 次），
            #      通过逐行去重保留唯一数据，大幅减少幻觉噪音。
            if _is_contour and len(text) > 1000:
                lines = text.strip().split('\n')
                seen = set()
                unique_lines = []
                for line in lines:
                    stripped = line.strip()
                    if stripped and stripped not in seen:
                        seen.add(stripped)
                        unique_lines.append(line)
                text = '\n'.join(unique_lines)
                logger.info(
                    f"  🔄 等值线去重: {len(lines)} -> {len(unique_lines)} 行"
                )
            page_results.append(
                f"--- 第 {page_num} 页 ---\n{text}"
            )
            logger.info(
                f"  ✅ 第 {page_num} 页完成: "
                f"{len(text)} 字, {elapsed:.1f}s"
            )
        else:
            # WHY: Vision LLM 超时或失败时，降级到 Tesseract OCR
            logger.warning(
                f"  ⚠️ 第 {page_num} 页 Vision 无结果 ({elapsed:.1f}s)，"
                f"尝试 OCR 降级..."
            )
            ocr_text = _ocr_fallback_from_bytes(png_bytes, page_num)
            if ocr_text:
                page_results.append(
                    f"--- 第 {page_num} 页 (OCR 降级) ---\n{ocr_text}"
                )

    # ── Step 3: Vision 模型驻留 10 分钟 ──
    # WHY: _call_vision_llm 已设置 keep_alive="10m"，
    #      后续同批次文件可直接复用加载好的模型，避免重复冷加载。
    #      Ollama 在 10 分钟无调用后自动卸载。

    # ── Step 3.1: 立刻重新预热 qwen3.6:35b-q4 ──
    # WHY: 不依赖 heartbeat 周期（原 4 分钟间隔），Vision 解析完成后
    #      立即把主力模型装回 GPU，确保后续 chat/图谱提取立即可用。
    try:
        httpx.post(
            f"{_ollama_url}/api/generate",
            json={
                "model": "qwen3.6:35b-q4",
                "keep_alive": -1,
                "prompt": "",
            },
            timeout=30.0,
        )
        logger.info("🔄 已重新预热 qwen3.6:35b-q4（Vision 完成）")
    except Exception:
        pass  # 预热失败由 heartbeat 兜底

    if not page_results:
        logger.warning(f"Vision 解析无结果: {filename}")
        return ""

    # ── Step 4: 组装最终文本 ──
    # WHY: 不再在输出文本中嵌入系统元数据（模型名、时间戳等），
    #      避免下游图谱提取大模型把 "qwen2.5vl:7b" 等系统标识误识别为业务实体。
    #      元数据已通过 logger.info 记录，不会丢失。
    full_text = f"[图件解析] {filename}\n\n" + "\n\n".join(page_results)

    logger.info(
        f"🔍 Vision 解析完成: {filename}, "
        f"{len(page_results)}/{len(pages)} 页, "
        f"{len(full_text)} 字, {time.time() - t_start:.1f}s"
    )
    return full_text


def extract_image_vision(
    file_path: str,
    model: Optional[str] = None,
    timeout: Optional[int] = None,
) -> str:
    """
    使用 Vision LLM 对单张图片进行 OCR + 语义理解。

    WHY: 替代 image.py 中的 _extract_image_vlm 占位函数。
         对工程扫描件、地价分布图等进行深度视觉理解。
    """
    from core.config import settings

    _model = model or settings.VISION_MODEL
    if not _model:
        return ""

    _timeout = timeout or settings.VISION_TIMEOUT
    _ollama_url = settings.OLLAMA_BASE_URL
    filename = Path(file_path).name

    logger.info(f"🔍 Vision 图片解析: {filename} (model={_model})")

    try:
        with open(file_path, "rb") as f:
            image_bytes = f.read()
    except Exception as e:
        logger.error(f"读取图片失败 ({filename}): {e}")
        return ""

    # === 表格旋转检测（基于图像内容） ===
    # WHY: 单张图片可能是旋转的扫描件，在送入 Vision LLM 前矫正方向。
    try:
        from .table_rotation import auto_rotate_from_bytes
        image_bytes, angle = auto_rotate_from_bytes(image_bytes)
        if angle:
            logger.info(f"  📐 图片旋转矫正: {filename} → {angle}°")
    except Exception as rot_err:
        logger.debug(f"旋转检测跳过 ({filename}): {rot_err}")

    # WHY: 等值线图使用专用 prompt 减少幻觉
    _is_contour_img = any(kw in filename for kw in ('等值线', '等高线', '等降雨量', 'isoline', 'contour'))
    _vision_prompt_img = _VISION_PROMPT_ISOLINE if _is_contour_img else _VISION_PROMPT_TECH
    _vision_temp_img = 0.0 if _is_contour_img else 0.1

    text = _call_vision_llm(
        image_bytes=image_bytes,
        prompt=_vision_prompt_img,
        model=_model,
        ollama_url=_ollama_url,
        timeout=_timeout,
        temperature=_vision_temp_img,
    )

    # WHY: 单张图片解析后不卸载模型——可能后续还有同批次的其他图片。
    #      模型卸载由 Celery task 结束时统一处理。

    if text:
        # WHY: 不注入 [图片解析] 等元数据，避免污染向量检索空间
        return text

    return ""
