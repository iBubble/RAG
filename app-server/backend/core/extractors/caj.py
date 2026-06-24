import os
import subprocess
import tempfile
import logging
from pathlib import Path
from core.extractors.pdf import _extract_pdf

logger = logging.getLogger(__name__)

def _extract_caj(file_path: str) -> str:
    """
    通过调用项目自带的 caj2pdf 工具，将 KDH/CAJ 文件解壳转换为 PDF，
    并提取其中的文本内容。
    """
    caj_path = Path(file_path)
    if not caj_path.exists():
        raise FileNotFoundError(f"CAJ 文件不存在: {file_path}")

    # 动态定位 caj2pdf 脚本的相对位置，自适应本地与容器环境
    caj2pdf_script = Path(__file__).parents[3] / "caj2pdf" / "caj2pdf"
    if not caj2pdf_script.exists():
        # 兼容性回退
        caj2pdf_script = Path("/app/caj2pdf/caj2pdf")

    # 创建唯一的临时 PDF 文件
    temp_dir = tempfile.gettempdir()
    temp_pdf = Path(temp_dir) / f"caj_conv_{caj_path.stem}.pdf"

    try:
        logger.info(f"开始解壳 CAJ 文件: {caj_path.name}")
        cmd = ["python3", str(caj2pdf_script), "convert", str(caj_path), "-o", str(temp_pdf)]
        
        # 运行转换，设置 45 秒超时保护防止阻塞
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=45)
        
        if result.returncode != 0:
            logger.error(f"caj2pdf 转换失败. stdout: {result.stdout}, stderr: {result.stderr}")
            raise RuntimeError(f"CAJ 转换 PDF 失败 (Exit code {result.returncode})")

        if not temp_pdf.exists():
            raise FileNotFoundError("caj2pdf 返回 0，但未生成目标 PDF 文件")

        logger.info(f"解壳成功，生成临时 PDF: {temp_pdf.name}。开始提取正文...")
        # 复用系统原生成熟的 PDF 提取器，天然支持文本及 CAD 乱码判定
        text = _extract_pdf(str(temp_pdf))
        return text

    except Exception as e:
        logger.error(f"解析 CAJ 异常: {e}")
        raise RuntimeError(f"解析 CAJ 文件失败: {str(e)}")

    finally:
        # 清除临时生成的中间 PDF，避免磁盘垃圾堆积
        if temp_pdf.exists():
            try:
                temp_pdf.unlink()
                logger.info(f"已清理临时 PDF 文件: {temp_pdf.name}")
            except Exception as ue:
                logger.warning(f"清理临时 PDF 失败: {ue}")
