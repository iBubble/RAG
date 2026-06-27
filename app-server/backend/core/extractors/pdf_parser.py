"""
PDF 智能解析与分流控制器 — 升级计划 D2。

根据 PDF 类型自动分流：
1. 数字化原生 PDF：通过 Docling 极速提取 (CPU 端，约 1.5页/秒)。
2. 扫描件 PDF / 复杂表格：
   - 如果处于 Fast Queue，主动触发 re-route 重路由至 Slow Queue 并退出。
   - 如果处于 Slow Queue，在当前进程同步调用 MinerU CLI 进行高精度布局与 OCR 视觉提取 (CPU 独占)。
"""
from __future__ import annotations
import os
import shutil
import subprocess
import tempfile
import logging
import re
import fitz  # PyMuPDF
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

def is_scanned_pdf(file_path: str) -> bool:
    """
    判断 PDF 是否为扫描件。
    平均每页可提取 the 文本少于 80 个字符即判定为扫描件。
    """
    try:
        doc = fitz.open(file_path)
        total_pages = len(doc)
        if total_pages == 0:
            return True
            
        total_text_len = 0
        for page in doc:
            text = page.get_text("text")
            total_text_len += len(text.strip())
            
        avg_len = total_text_len / total_pages
        logger.info(f"PDF 扫描件判定: {Path(file_path).name}, 总页数={total_pages}, 平均每页字数={avg_len:.1f}")
        return avg_len < 80
    except Exception as e:
        logger.error(f"判定 PDF 是否为扫描件时出错: {e}")
        return True  # 异常时保守判定为扫描件以触发深度视觉解析


def extract_with_mineru(file_path: str) -> Optional[str]:
    """
    通过 magic-pdf 命令行工具（CPU-only 模式）提取扫描件 PDF 的 Markdown 文本。
    
    WHY: 子进程执行 MinerU 能够在大文件解析完成后 100% 回收内存，
         彻底规避 Python 进程长期驻留 Paddle/PyTorch 大模型造成的内存泄露。
    """
    tmp_out_dir = tempfile.mkdtemp(prefix="mineru_out_")
    try:
        # 设置线程限制环境变量，防止 CPU 爆满
        env = os.environ.copy()
        env["OMP_NUM_THREADS"] = "4"
        env["MKL_NUM_THREADS"] = "4"
        env["OPENBLAS_NUM_THREADS"] = "4"
        env["VECLIB_MAXIMUM_THREADS"] = "4"
        env["NUMEXPR_NUM_THREADS"] = "4"

        # 构造 CLI 命令
        cmd = [
            "magic-pdf",
            "-p", file_path,
            "-o", tmp_out_dir,
            "-m", "auto"
        ]
        
        logger.info(f"🚀 启动 MinerU CPU 子进程解析: {Path(file_path).name}")
        # 执行子进程，超时时间 600 秒
        res = subprocess.run(
            cmd,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=600
        )
        
        if res.returncode != 0:
            logger.error(f"MinerU 子进程执行失败: code={res.returncode}, stderr={res.stderr}")
            return None

        # MinerU 会在输出目录下生成与文件名（无后缀）相同的子文件夹
        base_name = Path(file_path).stem
        target_dir = Path(tmp_out_dir) / base_name
        
        if not target_dir.exists():
            # 兼容非标准命名或多文件场景，查找第一个子文件夹
            subdirs = [d for d in Path(tmp_out_dir).iterdir() if d.is_dir()]
            if subdirs:
                target_dir = subdirs[0]
            else:
                logger.error(f"MinerU 输出目录不存在: {target_dir}")
                return None

        # 查找生成的 .md 文件
        md_files = list(target_dir.glob("*.md"))
        if not md_files:
            logger.error(f"MinerU 未在输出目录中生成 markdown 文件")
            return None

        # 读取内容
        md_content = md_files[0].read_text(encoding="utf-8")
        logger.info(f"✅ MinerU 视觉解析扫描件成功: {Path(file_path).name} ({len(md_content)} 字符)")
        return md_content

    except subprocess.TimeoutExpired:
        logger.error(f"MinerU 子进程解析 PDF 超时(600s)")
        return None
    except Exception as e:
        logger.error(f"MinerU 解析过程中出现致命异常: {e}")
        return None
    finally:
        # 清理临时文件
        shutil.rmtree(tmp_out_dir, ignore_errors=True)
        # 强制释放 PyTorch/MPS 显存缓存
        try:
            import torch
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
            elif hasattr(torch, "mps") and torch.mps.is_available():
                torch.mps.empty_cache()
        except Exception:
            pass


def _extract_pdf_smart(file_path: str, is_slow_queue: bool = False) -> str:
    """
    智能 PDF 解析主入口（替代原 PyMuPDF 暴力提取）。
    """
    from core.extractors.docling_parser import extract_with_docling, is_docling_available

    # 1. 判定是否是扫描件
    if is_scanned_pdf(file_path):
        if not is_slow_queue:
            # 处于快队列中，抛出标志异常告知上层执行 re-route
            raise ValueError("ROUTE_TO_SLOW_QUEUE")
        
        # 已经处于慢队列，同步执行 MinerU 视觉大模型抽取
        mineru_text = extract_with_mineru(file_path)
        if mineru_text:
            return mineru_text
        
        logger.warning("MinerU 视觉解析失败，回退到 PyMuPDF 纯文本提取")

    # 2. 数字化原生 PDF / 扫描件降级：Docling 优先
    if is_docling_available():
        docling_text = extract_with_docling(file_path)
        if docling_text:
            return docling_text

    # 3. 终极回退：PyMuPDF 纯文本提取
    logger.info(f"使用 PyMuPDF 基础提取器解析: {Path(file_path).name}")
    from core.extractors.pdf import _do_extract_pdf
    return _do_extract_pdf(file_path)


# ── DoCO 规范化统一节点语义映射 (D2 升级) ──
_MD_HEADING_RE = re.compile(r'^(?:#{1,6}\s+\S+|第[一二三四五六七八九十]+[章节条款篇].*)')
_MD_TABLE_RE = re.compile(r'^\s*\|.*\|\s*$', re.MULTILINE)
_MD_LIST_RE = re.compile(r'^\s*[-*+]\s+\S+|^\s*\d+\.\s+\S+')

def get_standard_semantic_role(chunk: str) -> str:
    """
    根据切片内容和排版特征，统一映射和预测其 Evidence Unit 的语义角色。
    标准化映射为 DoCO 规范定义的：
    - section_header (章节标题)
    - table (表格)
    - list_item (列表项)
    - text_block (普通文本段落)
    """
    import re
    if not chunk or not chunk.strip():
        return "text_block"
        
    stripped = chunk.strip()
    
    # 1. 判定是否为章节标题
    if _MD_HEADING_RE.match(stripped) or (len(stripped.split('\n')[0]) < 80 and _MD_HEADING_RE.match(stripped.split('\n')[0])):
        return "section_header"
        
    # 2. 判定是否为表格
    if "|" in stripped:
        lines = stripped.split("\n")
        table_lines = sum(1 for line in lines if _MD_TABLE_RE.match(line))
        if table_lines > 0 and table_lines / len(lines) >= 0.4:
            return "table"
            
    # 3. 判定是否为列表项
    if _MD_LIST_RE.match(stripped):
        return "list_item"
        
    return "text_block"
