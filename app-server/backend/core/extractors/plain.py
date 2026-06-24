from pathlib import Path


def _extract_txt(file_path: str) -> str:
    """纯文本 / Markdown / CSV 直读。"""
    return Path(file_path).read_text(encoding="utf-8", errors="ignore")

