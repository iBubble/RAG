"""
OCR 文本清洗、乱码检测算法与自愈重试过滤器。
WHY: 移动端实拍或扫描图片常常因为分辨率异常、噪点阴影或旋转产生无序字符碎屑（如 ll X ae rey 了加 "二 PRESET），
     必须通过多维特征检测识别乱码并触发自愈重试，杜绝乱码污染知识库与前端界面。
"""
from __future__ import annotations

import re
import unicodedata
from typing import Tuple

# 常见无意义碎片单字与高频 OCR 识别噪点词
_JUNK_TOKENS = {
    "ll", "oe", "ae", "rey", "fe", "wm", "he", "am", "sor", "ecm", "te",
    "ie", "ot", "oo", "no", "ok", "cd", "mo", "pm", "len",
}

# 常见正常英文基础单词白名单（用于区分正常中英混排与无序碎片）
_VALID_EN_WORDS = {
    "the", "be", "to", "of", "and", "a", "in", "that", "have", "i",
    "it", "for", "not", "on", "with", "he", "as", "you", "do", "at",
    "this", "but", "his", "by", "from", "they", "we", "say", "her", "she",
    "or", "an", "will", "my", "one", "all", "would", "there", "their", "what",
    "so", "up", "out", "if", "about", "who", "get", "which", "go", "me",
    "name", "date", "time", "page", "total", "code", "no", "status", "type",
    "company", "address", "tel", "fax", "email", "http", "https", "www",
}


def is_garbled_text(text: str) -> Tuple[bool, str]:
    """
    智能检测文本是否属于 OCR 乱码或编码异常损坏内容。
    返回 (is_garbled, reason)。
    """
    if not text or not text.strip():
        return False, ""

    raw = text.strip()

    # 1. 检测非法 Unicode 替换字符与常见编码转义错误 (Mojibake)
    if "\ufffd" in raw or "\x00" in raw:
        return True, "包含替换字符(\ufffd)或空字节，编码已损坏"

    mojibake_patterns = [
        r"[ÃÂ][\x80-\xbf]",  # UTF-8 被误按 Latin-1 解码
        r"[æåçé][\x80-\xbf]{2}",
    ]
    for pat in mojibake_patterns:
        if len(re.findall(pat, raw)) >= 3:
            return True, "命中典型 UTF-8 编码误解乱码序列"

    # 2. 统计字符类型分布
    total_len = len(raw)
    if total_len < 10:
        return False, ""

    # 中文字符（CJK 统一表意文字）
    cjk_count = len(re.findall(r"[\u4e00-\u9fa5]", raw))
    # 英文字母
    alpha_count = len(re.findall(r"[a-zA-Z]", raw))
    # 数字
    digit_count = len(re.findall(r"[0-9]", raw))
    # 换行与空白
    space_count = len(re.findall(r"\s", raw))
    # 标点符号与特殊字符
    symbols = re.findall(r"[^\w\s\u4e00-\u9fa5]", raw)
    symbol_count = len(symbols)

    effective_chars = max(total_len - space_count, 1)

    # 3. 极高符号碎片比率检测（如大量 |、-、=、~、/、_ 组成的噪声网格）
    high_noise_symbols = re.findall(r"[|/\\_~^#*+=()[\]{}<>@$%&`'\"—–]", raw)
    if len(high_noise_symbols) / effective_chars > 0.35 and cjk_count < 20:
        return True, f"特殊标点符号占比过高({len(high_noise_symbols)/effective_chars:.1%})，且无连贯文本"

    # 4. 连续重复单字噪声检测（如：fe加加加加加點、NO NO NO NO NO 一人 一人）
    repeated_char_match = re.search(r"([\u4e00-\u9fa5a-zA-Z])\1{4,}", raw)
    if repeated_char_match and cjk_count < 40:
        return True, f"包含异常连续重复字符 '{repeated_char_match.group(1)}'"

    # 5. 碎片化孤立英文短 Token 比例（OCR 误识产生的碎片）
    words = [w.lower() for w in re.findall(r"\b[a-zA-Z]+\b", raw)]
    if len(words) >= 8 and cjk_count < 15:
        junk_matches = sum(1 for w in words if w in _JUNK_TOKENS or (len(w) <= 2 and w not in _VALID_EN_WORDS))
        if junk_matches / len(words) > 0.55:
            return True, f"充斥无意义英文碎片词({junk_matches}/{len(words)})"

    # 6. 长文本中缺乏有效中文语义与英文词汇（文字熵过低或无词序）
    if total_len > 120 and cjk_count < 8:
        valid_words = sum(1 for w in words if w in _VALID_EN_WORDS)
        if valid_words < 5 and (alpha_count / effective_chars) > 0.4:
            return True, "长文本中有效中英文词汇密度极低，疑似扫描噪点"

    return False, ""


def clean_ocr_text(text: str) -> str:
    """对提取出的文字进行轻量排版降噪，移除多余的连续孤立标点与空行。"""
    if not text:
        return ""
    lines = [line.strip() for line in text.splitlines()]
    cleaned_lines = []
    for line in lines:
        if not line:
            if cleaned_lines and cleaned_lines[-1] != "":
                cleaned_lines.append("")
            continue
        # 移除纯符号行（如只有 | | --- ===）
        if re.match(r"^[-=_|/\\~*#\s]+$", line) and len(line) < 30:
            continue
        cleaned_lines.append(line)
    return "\n".join(cleaned_lines).strip()

