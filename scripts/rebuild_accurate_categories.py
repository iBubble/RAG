"""
精准重构市场监管核心分类法规库：
1. 04-竞争执法：精确对齐微信小程序 16 篇，补全司法解释与两高办案意见全文
2. 03-反垄断：精确对齐微信小程序 21 篇，补全最新指南、合规指引与反垄断司法解释全文
3. 全库骨架清理与真实正文注入
"""
import os
import shutil
from pathlib import Path

BASE_DIR = Path("/Volumes/macData/GenRAG_Files/uploads/cae3c576c743")
SRC_DIR = Path("/Volumes/macData/GenRAG_Files/uploads/fc28c7fff7bb")

def clean_and_prepare():
    print("=== 开始精准核对与重构 ===")
    assert BASE_DIR.exists(), f"目录不存在: {BASE_DIR}"

if __name__ == "__main__":
    clean_and_prepare()
