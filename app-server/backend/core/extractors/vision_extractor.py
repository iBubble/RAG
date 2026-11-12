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
from core.config import settings

logger = logging.getLogger(__name__)



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
_VISION_PROMPT_GENERAL = """请完整准确地识别并提取这张图片中的所有文字内容（包括标题、正文、品牌、宣传语、微小文字、角标等）。
保持原文结构，如有表格用 Markdown 表格格式输出；若为海报或宣传广告，在列出全部文字后可简要说明画面视觉主体。"""



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
    api_key: str = "",
) -> str:
    """
    调用 Vision 模型解析单张图片（支持 Ollama 与 OpenAI-compatible 兼容接口）。
    """
    from core.llm_config import normalize_endpoint
    b64_img = base64.b64encode(image_bytes).decode("utf-8")
    is_ollama = "11434" in ollama_url or "/api/" in ollama_url

    headers = {"Content-Type": "application/json"}
    if api_key and api_key.strip().upper() != "EMPTY":
        headers["Authorization"] = f"Bearer {api_key.strip()}"

    if is_ollama:
        req_url = f"{ollama_url.rstrip('/')}/api/chat"
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
            "keep_alive": "10m",
            "options": {
                "temperature": temperature,
                "num_predict": 6144,
            },
        }
    else:
        # OpenAI 兼容多模态端点 (如 http://40dd.shop:8000/v1)
        req_url = normalize_endpoint(ollama_url, is_openai_chat=True)
        payload = {
            "model": model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/png;base64,{b64_img}"}
                        }
                    ]
                }
            ],
            "max_tokens": 4096,
            "temperature": temperature,
            "stream": False,
        }

    import time as _time
    _max_retries = 3
    for _attempt in range(_max_retries):
        try:
            resp = httpx.post(
                req_url,
                json=payload,
                headers=headers,
                timeout=httpx.Timeout(float(timeout)),
            )
            resp.raise_for_status()
            data = resp.json()
            # 兼容 OpenAI 与 Ollama 格式
            if not is_ollama:
                choices = data.get("choices", [])
                content = choices[0].get("message", {}).get("content", "") if choices else ""
            else:
                content = data.get("message", {}).get("content", "")
            return content.strip()
        except httpx.TimeoutException:
            logger.warning(f"Vision LLM 超时 ({timeout}s)")
            return ""
        except Exception as e:
            status = getattr(getattr(e, "response", None), "status_code", 0)
            if status == 503 and _attempt < _max_retries - 1:
                logger.warning(f"Vision LLM 503 (attempt {_attempt+1}), 重试中...")
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
    from core.llm_config import get_active_vision_config
    
    vision_cfg = get_active_vision_config()
    _model = model or vision_cfg.get("model") or getattr(settings, "VISION_MODEL", "qwen3-vl-32b-awq")
    if not _model:
        logger.debug("Vision 模型未配置，跳过视觉解析")
        return ""

    _max_pages = max_pages or getattr(settings, "VISION_MAX_PAGES", 30)
    _dpi = dpi or getattr(settings, "VISION_DPI", 300)
    _timeout = timeout or int(vision_cfg.get("timeoutSeconds", 300))
    _ollama_url = vision_cfg.get("baseURL") or settings.OLLAMA_BASE_URL
    _api_key = vision_cfg.get("apiKey", "")
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
            json={"model": settings.DEFAULT_LLM_MODEL, "keep_alive": 0},
            timeout=10.0,
        )
        logger.info(f"🔄 已卸载 {settings.DEFAULT_LLM_MODEL}，为 Vision 模型腾出显存")
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
    _vision_prompt = _VISION_PROMPT_ISOLINE if _is_contour else _VISION_PROMPT_GENERAL
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
            api_key=_api_key,
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
                "model": settings.DEFAULT_LLM_MODEL,
                "keep_alive": -1,
                "prompt": "",
            },
            timeout=30.0,
        )
        logger.info(f"🔄 已重新预热 {settings.DEFAULT_LLM_MODEL}（Vision 完成）")
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


def optimize_image_for_vlm(
    image_bytes: bytes,
    max_dim: int = 2048,
    max_bytes: int = 1500000,
) -> bytes:
    """
    智能安全压缩与规范化待送入 Vision LLM 的图片数据。
    WHY: 手机实拍或高清扫描图（如 14850x10500、20MB+）直接 base64 会导致 HTTP 413 实体过大，
         或使远端 Gateway 超时中断。通过双线性降采样与 EXIF 转正，将体积压减到 1.5MB 以内。
    """
    if not image_bytes:
        return b""
    try:
        from PIL import Image, ImageOps
        Image.MAX_IMAGE_PIXELS = None

        with Image.open(io.BytesIO(image_bytes)) as img:
            img = ImageOps.exif_transpose(img)
            if img.mode not in ("RGB", "L"):
                img = img.convert("RGB")

            w, h = img.size
            if max(w, h) > max_dim:
                scale = max_dim / max(w, h)
                new_w, new_h = max(int(w * scale), 1), max(int(h * scale), 1)
                img = img.resize((new_w, new_h), Image.Resampling.LANCZOS)

            for quality in (85, 75, 65):
                buf = io.BytesIO()
                img.save(buf, format="JPEG", quality=quality, optimize=True)
                data = buf.getvalue()
                if len(data) <= max_bytes or quality == 65:
                    return data
    except Exception as exc:
        logger.warning("Vision 图片预处理压缩降级跳过: %s", exc)
    return image_bytes


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
    from core.llm_config import get_active_vision_config
    from .ocr_cleaner import is_garbled_text

    vision_cfg = get_active_vision_config()
    _model = model or vision_cfg.get("model") or getattr(settings, "VISION_MODEL", "qwen3-vl-32b-awq")
    if not _model:
        return ""

    _timeout = timeout or int(vision_cfg.get("timeoutSeconds", 300))
    _ollama_url = vision_cfg.get("baseURL") or getattr(settings, "OLLAMA_BASE_URL", "http://host.docker.internal:11434")
    _api_key = vision_cfg.get("apiKey", "")
    filename = Path(file_path).name

    is_ollama = "11434" in _ollama_url or "/api/" in _ollama_url
    # 仅针对本地 Ollama 执行模型存在性自检，外部 Gateway 直接透传
    if is_ollama:
        try:
            resp = httpx.get(f"{_ollama_url}/api/tags", timeout=5.0)
            if resp.status_code == 200:
                local_models = [m.get("name") for m in resp.json().get("models", [])]
                if _model not in local_models and f"{_model}:latest" not in local_models:
                    logger.warning(f"⚠️ 本地 Ollama 未检测到多模态模型 {_model}，执行降级自愈...")
                    if "qwen2.5vl:7b" in local_models or "qwen2.5vl:latest" in local_models:
                        _model = "qwen2.5vl:7b" if "qwen2.5vl:7b" in local_models else "qwen2.5vl:latest"
                    elif "minicpm-v:latest" in local_models:
                        _model = "minicpm-v:latest"
                    elif "moondream:latest" in local_models:
                        _model = "moondream:latest"
                    else:
                        logger.warning(f"❌ 本地无可用的多模态模型，降级启用本地 OCR")
                        return ""
        except Exception as check_err:
            logger.warning(f"模型存在性自检跳过: {check_err}")


    logger.info(f"🔍 Vision 图片解析: {filename} (model={_model})")

    try:
        with open(file_path, "rb") as f:
            image_bytes = f.read()
    except Exception as e:
        logger.error(f"读取图片失败 ({filename}): {e}")
        return ""

    # 智能预处理降采样，防范 413 Entity Too Large
    image_bytes = optimize_image_for_vlm(image_bytes)

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
    _vision_prompt_img = _VISION_PROMPT_ISOLINE if _is_contour_img else _VISION_PROMPT_GENERAL
    _vision_temp_img = 0.0 if _is_contour_img else 0.1

    text = _call_vision_llm(
        image_bytes=image_bytes,
        prompt=_vision_prompt_img,
        model=_model,
        ollama_url=_ollama_url,
        timeout=_timeout,
        temperature=_vision_temp_img,
        api_key=_api_key,
    )

    # 乱码拦截与即时自愈重试
    if text:
        garbled, reason = is_garbled_text(text)
        if garbled:
            logger.warning(f"⚠️ Vision 提取命中乱码 ({filename}): {reason}，触发防乱码二次重试分析...")
            retry_prompt = (
                "请仔细核对并提取该图片中的真实可见文字或图表标题。\n"
                "严格注意：\n"
                "1. 仅转写清晰可见的文字与数值；\n"
                "2. 严禁输出无意义的单个英文字母碎屑或连续符号网格；\n"
                "3. 若图片为纯场景/无文字，请用一段简练中文客观描述画面主体，禁止输出乱码字符。"
            )
            retry_text = _call_vision_llm(
                image_bytes=image_bytes,
                prompt=retry_prompt,
                model=_model,
                ollama_url=_ollama_url,
                timeout=_timeout,
                temperature=0.0,
                api_key=_api_key,
            )
            if retry_text and not is_garbled_text(retry_text)[0]:
                logger.info(f"✅ Vision 乱码自愈重试成功 ({filename})")
                text = retry_text
            else:
                logger.warning(f"Vision 重试仍判定为乱码，清空以便降级处理 ({filename})")
                text = ""

    # WHY: 单张图片解析后不卸载模型——可能后续还有同批次的其他图片。
    #      模型卸载由 Celery task 结束时统一处理。

    if text:
        # WHY: 不注入 [图片解析] 等元数据，避免污染向量检索空间
        return text

    return ""
