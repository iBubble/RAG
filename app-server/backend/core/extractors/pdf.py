import logging
from typing import List
from pathlib import Path

logger = logging.getLogger(__name__)

from .image import _extract_image
from .utils import _table_to_markdown



def _filter_dimension_noise(text: str) -> str:
    """
    过滤 CAD 图纸中的坐标/尺寸标注噪音行。

    WHY: CAD 导出的 PDF 中包含大量尺寸标注数字（如 10、18、120），
         这些是离散定位的标注值，脱离图纸上下文后完全无意义，
         但会严重稀释向量检索的信噪比。

    过滤规则：
      - 移除仅含 ≤3 个 ASCII 字符的纯数字/符号行
      - 保留含中文字符的行
      - 保留含工程单位（mm/cm/m）的行
      - 保留含关键工程标识（C25、DN150、Ⅲ级 等）的行
      - 保留 Markdown 表格行（|...|）
      - 不改变段落结构，只移除非内容噪音行
    """
    if not text:
        return text

    import re
    lines = text.split('\n')
    filtered = []

    for line in lines:
        stripped = line.strip()

        # 空行直接保留（保持段落结构）
        if not stripped:
            filtered.append(line)
            continue

        # Markdown 表格行直接保留
        if stripped.startswith('|') or stripped.startswith('[本页数据表格检测]'):
            filtered.append(line)
            continue

        # 含中文 → 保留
        if re.search(r'[\u4e00-\u9fff]', stripped):
            filtered.append(line)
            continue

        # 含工程单位关键词 → 保留（如 "DN150"、"C25"、"Ⅲ级"）
        if re.search(
            r'(?:DN\d+|C\d{2}|[Ⅰ-Ⅻ]+级|mm|cm|m|MPa|kN|kg|m³|m²|°|%‰)',
            stripped,
        ):
            filtered.append(line)
            continue

        # 纯短数字行（≤3字符且不含字母）→ 坐标标注噪音，移除
        if len(stripped) <= 3 and re.match(r'^[\d\.\-\+\s]+$', stripped):
            continue

        # 长数字行（>3字符纯数字）也可能是噪音，检查是否含特殊模式
        if len(stripped) <= 6 and re.match(r'^[\d\.\-\+\s]+$', stripped):
            continue

        # 其他行保留
        filtered.append(line)

    result = '\n'.join(filtered)
    removed = len(text) - len(result)
    if removed > 0:
        logger.debug(
            f"坐标噪音过滤: 移除 {removed} 字符 "
            f"({len(lines) - len([l for l in filtered if l.strip()])} 行)"
        )
    return result


def _is_false_table(raw_data: list) -> bool:
    """
    检测 PyMuPDF find_tables() 的误检结果（假表格）。

    WHY: PyMuPDF 的表格检测算法在遇到 CAD 图纸的文字说明块时，
         可能将连续的多行文字误判为表格，产生损坏的 Markdown 输出。
         假表格注入到文本中会污染向量检索空间。

    判定规则：
      1. 非空单元格占比 < 50% → 假表格（大部分是空单元格）
      2. 有效数据列数 < 2 → 假表格（只有1列有数据，不是表格）
      3. 表格行数 < 2 → 假表格（只有表头没有数据）
      4. 任一单元格包含连续段落特征（含 。；、等标点且长度>20）→ 假表格
    """
    if not raw_data or len(raw_data) < 2:
        return True

    import re

    def _clean(val):
        if val is None:
            return ""
        return str(val).replace("\n", " ").strip()

    total_cells = 0
    non_empty_cells = 0
    cols_with_data = set()
    has_paragraph_text = False

    for row_idx, row in enumerate(raw_data):
        for col_idx, cell in enumerate(row):
            total_cells += 1
            cleaned = _clean(cell)
            if cleaned:
                non_empty_cells += 1
                cols_with_data.add(col_idx)

                # 检测段落特征：含中文标点且长度 > 20
                if (
                    len(cleaned) > 20
                    and re.search(r'[。；、，]', cleaned)
                ):
                    has_paragraph_text = True

    # 指标1: 非空占比
    fill_ratio = non_empty_cells / max(total_cells, 1)
    if fill_ratio < 0.50:
        logger.debug(
            f"假表格拒绝: 非空占比={fill_ratio:.0%} "
            f"({non_empty_cells}/{total_cells})"
        )
        return True

    # 指标2: 有效数据列数
    if len(cols_with_data) < 2:
        logger.debug(f"假表格拒绝: 有效列数={len(cols_with_data)} < 2")
        return True

    # 指标3: 行数（已在外层检查 len(raw_data) < 2，此处冗余确认）
    data_rows = [r for r in raw_data[1:] if any(_clean(c) for c in r)]
    if len(data_rows) < 1:
        logger.debug("假表格拒绝: 数据行数 < 1")
        return True

    # 指标4: 单元格包含连续段落文本
    if has_paragraph_text:
        logger.debug("假表格拒绝: 单元格含连续段落文本（非表格数据）")
        return True

    return False


def _extract_pdf(file_path: str) -> str:
    """
    使用 PyMuPDF (fitz) 极速提取 PDF 文本（带 35B 卸载/重载保护）。
    WHY: PDF 逐页进行 VLM 视觉解析时，若主力模型 qwen3.6:35b-q4 驻留在 GPU 中，
         Ollama 会因为显存分配冲突而无限队列挂起 Vision 模型加载请求。
         在解析前主动卸载 35B，在 finally 中重新预热载入 35B，确保流程绝对顺畅。
    """
    from core.config import settings
    import httpx

    _ollama_url = settings.OLLAMA_BASE_URL
    
    # ── Step 1: 解析前卸载 qwen3.6:35b-q4 ──
    try:
        httpx.post(
            f"{_ollama_url}/api/generate",
            json={"model": "qwen3.6:35b-q4", "keep_alive": 0},
            timeout=5.0,
        )
        logger.info("🔄 已卸载 qwen3.6:35b-q4，为 PDF 逐页 Vision 解析腾出显存")
    except Exception:
        pass

    try:
        return _do_extract_pdf(file_path)
    finally:
        # ── Step 2: 解析后重新预热 qwen3.6:35b-q4 ──
        try:
            httpx.post(
                f"{_ollama_url}/api/generate",
                json={
                    "model": "qwen3.6:35b-q4",
                    "keep_alive": -1,
                    "prompt": "",
                },
                timeout=10.0,
            )
            logger.info("🔄 已重新预热 qwen3.6:35b-q4（PDF 逐页 Vision 解析完成）")
        except Exception:
            pass


def _do_extract_pdf(file_path: str) -> str:
    """
    实际的 PDF 极速文本提取逻辑。
    """
    import fitz  # PyMuPDF
    from pathlib import Path

    _filename = Path(file_path).name
    texts = []
    try:
        doc = fitz.open(file_path)
        total_pages = len(doc)
        logger.info(f"PyMuPDF 开始解析: {_filename} ({total_pages} 页)")

        for page_num, page in enumerate(doc):
            text = page.get_text("text")

            # ── 逐页扫描混合检测 ──
            # WHY: 对于前几页是文本，后几页是扫描件的混合 PDF，
            #      直接对低文本页做 Vision LLM 提取。
            if len(text.strip()) < 30:
                try:
                    pix = page.get_pixmap(dpi=200)
                    import tempfile
                    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
                        tmp.write(pix.tobytes("png"))
                        tmp_path = tmp.name
                        
                    from .vision_extractor import extract_image_vision
                    vision_text = extract_image_vision(tmp_path)
                    
                    Path(tmp_path).unlink(missing_ok=True)
                    
                    if vision_text and len(vision_text) > 10:
                        text = vision_text
                        logger.info(f"PDF 扫描页解析 (第{page_num+1}页): {_filename}, {len(vision_text)} 字")
                except Exception as e:
                    logger.debug(f"PDF 逐页 Vision 解析异常 (第{page_num+1}页): {e}")

            # --- 注入 PDF 本页检测到的表格 (Markdown格式) ---
            # WHY: 增加假表格校验，防止 CAD 图纸的"说明"文本块被误检为表格
            if hasattr(fitz.Page, 'find_tables'):
                try:
                    page_tables = page.find_tables()
                    for tbl in page_tables.tables:
                        raw_data = tbl.extract()
                        if not raw_data or len(raw_data) < 2:
                            continue

                        # ── 假表格拒绝 ──
                        if _is_false_table(raw_data):
                            logger.info(
                                f"PDF 表格校验拒绝 (第{page_num+1}页): "
                                f"{_filename}"
                            )
                            continue

                        md_lines = [f"\n[本页数据表格检测]"]

                        def _clean(val):
                            if val is None: return ""
                            return str(val).replace("\n", " ").strip()

                        headers = [_clean(c) for c in raw_data[0]]
                        # 防止全空表头导致 Markdown 格式异常
                        if not any(headers):
                            headers = [f"列{i+1}" for i in range(len(headers))]

                        md_lines.append("| " + " | ".join(headers) + " |")
                        md_lines.append("|" + "|".join(["---"] * len(headers)) + "|")

                        for row in raw_data[1:]:
                            clean_row = [_clean(c) for c in row]
                            # 补齐列数
                            clean_row = clean_row + [""] * max(0, len(headers) - len(clean_row))
                            md_lines.append("| " + " | ".join(clean_row[:len(headers)]) + " |")

                        text += "\n" + "\n".join(md_lines)
                except Exception as e:
                    logger.debug(f"PDF 注入表格异常 (第{page_num+1}页): {e}")
            # --- 结束注入 ---

            if text and text.strip():
                texts.append(text.strip())
        doc.close()
    except Exception as e:
        logger.warning(f"PyMuPDF 读取失败 ({_filename}): {e}")

    full_text = "\n\n".join(texts).strip()

    # ── 策略 2: PyMuPDF 原生渲染 + Tesseract OCR ──
    if len(full_text) < 50:
        logger.info(f"PDF 文本过短 ({len(full_text)}字)，启动增强解析: {_filename}")

        # ── 策略 1: Vision LLM 深度语义解析（优先）──
        try:
            from .vision_extractor import extract_pdf_vision
            vision_text = extract_pdf_vision(file_path)
            if vision_text and len(vision_text) > 50:
                logger.info(f"Vision LLM 解析成功: {_filename}, {len(vision_text)} 字")
                return vision_text
        except Exception as vision_err:
            logger.warning(f"Vision LLM 解析异常（降级）: {vision_err}")

        # ── 策略 2: PyMuPDF 原生渲染 + Tesseract OCR ──
        # WHY: 不依赖 pdf2image/poppler，使用 PyMuPDF 原生 get_pixmap()
        #      在 ARM Docker 环境中零外部依赖。
        try:
            import fitz as fitz_ocr
            import tempfile

            doc_ocr = fitz_ocr.open(file_path)
            total_pages_ocr = min(len(doc_ocr), 10)  # OCR 最多处理 10 页
            ocr_results = []

            for page_idx in range(total_pages_ocr):
                page = doc_ocr[page_idx]
                # WHY: 200 DPI 足以保证中文 OCR 识别率
                pix = page.get_pixmap(dpi=200)
                with tempfile.NamedTemporaryFile(
                    suffix=".png", delete=True
                ) as tmp:
                    pix.save(tmp.name)
                    page_text = _extract_image(tmp.name)
                    if page_text and page_text.strip():
                        ocr_results.append(page_text.strip())

            doc_ocr.close()

            if ocr_results:
                return "\n\n".join(ocr_results)
        except Exception as ocr_err:
            logger.error(f"PDF OCR 解析过程异常: {ocr_err}")

    # ── 非 CAD 正常文档：返回过滤后的文本 ──
    # WHY: 对所有 PDF 文本做轻量级噪音过滤，不影响正常文档的段落结构
    return _filter_dimension_noise(full_text)

def _extract_tables_pdf(file_path: str) -> List[dict]:
    """
    从 PDF 文件提取结构化表格。
    WHY: PDF 中的表格被 PyMuPDF 纯文本提取后会变成散乱的行列文字，
         再被 _semantic_chunk 切碎后 LLM 完全无法还原。
         利用 PyMuPDF 的 find_tables() API 直接检测表格区域，
         提取出完整的结构化行列数据。
    """
    import fitz

    filename = Path(file_path).name
    tables = []

    try:
        doc = fitz.open(file_path)
    except Exception as e:
        logger.error(f"[PDF表格提取] 打开失败 {filename}: {e}")
        return []

    # WHY: 检查 PyMuPDF 版本是否支持 find_tables()（需要 v1.23.0+）
    if not hasattr(fitz.Page, 'find_tables'):
        logger.warning(
            f"[PDF表格提取] PyMuPDF 版本过低，不支持 find_tables()。"
            f"当前版本: {fitz.__version__}，需要 ≥1.23.0"
        )
        doc.close()
        return []

    for page_num, page in enumerate(doc):
        # WHY: 安全保护——如果单页的矢量路径数（drawings）过高（如 > 500 条），
        #      则说明它是 CAD 等高度复杂的工程图纸。
        #      在这类页面上运行 find_tables() 底层的几何求交算法会发生 O(N^2) 的复杂度爆炸，
        #      导致 Python 进程彻底卡死且吃满 CPU。
        #      跳过这类高密度矢量页面的表格检测，能保障解析服务的健壮性。
        try:
            drawings_count = len(page.get_drawings())
            if drawings_count > 500:
                logger.info(f"[PDF表格提取] 跳过第{page_num+1}页: 矢量路径数 ({drawings_count}) 过多，防卡死保护生效")
                continue
        except Exception:
            pass

        try:
            page_tables = page.find_tables()
        except Exception as e:
            logger.warning(f"[PDF表格提取] 第{page_num+1}页检测失败: {e}")
            continue

        for tbl_idx, tbl in enumerate(page_tables.tables):
            try:
                # extract() 返回 List[List[str|None]]，第一行通常是表头
                raw_data = tbl.extract()
                if not raw_data or len(raw_data) < 2:
                    continue

                # 清洗：将 None 转为空字符串，去除换行
                def _clean(val):
                    if val is None:
                        return ""
                    return str(val).replace("\n", " ").strip()

                # 第一行作为表头
                headers = [_clean(cell) for cell in raw_data[0]]

                # 过滤全空的列
                valid_cols = [
                    i for i in range(len(headers))
                    if headers[i] or any(
                        _clean(row[i]) if i < len(row) else ""
                        for row in raw_data[1:]
                    )
                ]
                if not valid_cols:
                    continue

                headers = [headers[i] for i in valid_cols]
                data_rows = []
                for row in raw_data[1:]:
                    cells = [
                        _clean(row[i]) if i < len(row) else ""
                        for i in valid_cols
                    ]
                    if any(c for c in cells):  # 至少有一个非空单元格
                        data_rows.append(cells)

                if len(data_rows) < 2:
                    continue

                # 尝试从表头上方区域提取表格标题
                title = f"表格 (第{page_num+1}页)"
                # WHY: 很多 PDF 表格上方有一行标题文字，
                #      尝试从表格区域上方提取文本作为标题
                try:
                    tbl_rect = tbl.bbox  # (x0, y0, x1, y1)
                    # 在表格上方 50px 范围内搜索标题
                    title_rect = fitz.Rect(
                        tbl_rect[0], max(0, tbl_rect[1] - 50),
                        tbl_rect[2], tbl_rect[1]
                    )
                    title_text = page.get_text("text", clip=title_rect).strip()
                    if title_text and len(title_text) < 100:
                        # 清理多行为单行
                        title = title_text.replace("\n", " ").strip()
                except Exception:
                    pass

                md = _table_to_markdown(title, "", headers, data_rows)

                tables.append({
                    "title": title,
                    "sheet_name": f"PDF第{page_num+1}页",
                    "headers": headers,
                    "rows": data_rows,
                    "unit": "",
                    "markdown": md,
                    "source_file": filename,
                    "row_count": len(data_rows),
                    "char_count": len(md),
                })

            except Exception as e:
                logger.warning(
                    f"[PDF表格提取] {filename} 第{page_num+1}页 "
                    f"表格{tbl_idx+1} 处理失败: {e}"
                )
                continue

    doc.close()
    logger.info(f"[PDF表格提取] {filename}: 提取到 {len(tables)} 张表格")
    return tables

