"""
共享的标题层级判断工具函数。
WHY: template.py（纯骨架抽取）和 exemplar.py（带正文的范文解构）
     都需要判断段落是否为标题及其层级，抽取为独立模块避免代码重复。
"""
import re


def determine_level_from_text(text: str) -> int:
    """
    根据常见中文或数字序号特征强制推断 heading level。
    Level 1: 一、 / 第一章 / 1 xxx（纯数字+空格）
    Level 2: 1.1 / （一）/ 第N节
    Level 3: 1.1.1
    Level 4: 1.1.1.1
    如果没有明显匹配，默认返回 0（非结构化正文）。
    """
    text = text.strip()
    # Level 1 特征: 一、 前言 或者 第一章
    if re.match(r'^(?:[一二三四五六七八九十百千万]+、|第[一二三四五六七八九十百千万]+章\s)', text):
        return 1

    # Level 4: 1.1.1.1 四级数字编号
    if re.match(r'^\d+\.\d+\.\d+\.\d+', text):
        return 4

    # Level 3: 1.1.1 三级数字编号
    if re.match(r'^\d+\.\d+\.\d+', text):
        return 3

    # Level 2: 1.1 二级数字编号
    if re.match(r'^\d+\.\d+', text):
        return 2

    # Level 2: （一） 中文二级
    if re.match(r'^（[一二三四五六七八九十百千万]+）', text):
        return 2

    # Level 1: "1 综合说明" 一级数字编号
    # WHY: 要求数字后必须跟空格，排除 "1.自然因素" 这种列表项被误判为 L1 标题。
    #       "1." 这种孤立情况也要求后面紧跟空格（如 "1. 综合说明"），而不是中文。
    if re.match(r'^\d+\s+\S', text):
        return 1
    if re.match(r'^\d+\.\s+\S', text):
        return 1

    # Level 2: "第N节"
    if re.match(r'^第\d+节\s', text):
        return 2

    return 0
