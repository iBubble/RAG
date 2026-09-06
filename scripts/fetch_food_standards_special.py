"""
食品伙伴网「食品安全国家标准专题」(itemid=42, 共175页) 批量自动化下载流水线。
具备断点续传、请求速率限制(Rate Limiting)与指数退避(Exponential Backoff)，
安全平稳下载PDF原件至 /Volumes/macData/GenRAG_Files/uploads/fe2982b3820e/
"""
import os
import re
import sys
import time
import random
import logging
import urllib.request
import urllib.parse
from pathlib import Path
from typing import List, Dict, Optional

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger("FoodSpecialDownloader")

OUT_DIR = Path("/Volumes/macData/GenRAG_Files/uploads/fe2982b3820e")
OUT_DIR.mkdir(parents=True, exist_ok=True)

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) AppleWebKit/605.1.15 Mobile/15E148 Safari/604.1"
]

def get_headers(referer: Optional[str] = None) -> Dict[str, str]:
    h = {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        "Connection": "keep-alive"
    }
    if referer:
        h["Referer"] = referer
    return h

def get_page_standards(page: int, max_retries: int = 3) -> List[str]:
    """从WAP端专题页面提取指定页的标准标题列表"""
    url = f"https://down.foodmate.net/wap/index.php?moduleid=11&itemid=42&page={page}"
    delay = 2.0
    for attempt in range(max_retries):
        try:
            time.sleep(random.uniform(1.2, 2.0))
            req = urllib.request.Request(url, headers=get_headers())
            with urllib.request.urlopen(req, timeout=12) as resp:
                raw = resp.read().decode("gbk", errors="ignore")
                matches = re.findall(r"<li>.*?<a[^>]*><strong>(GB.*?)</strong></a></li>", raw)
                if matches:
                    return [re.sub(r"<[^>]+>", "", m).strip() for m in matches]
                return []

def search_and_download(standard_title: str, max_retries: int = 3) -> Optional[str]:
    """依据标准名称或编号检索 auth_id 并安全流式下载 PDF 原件"""
    # 提取标准号作为主要关键词（如 GB 31656.25-2026 或 GB 31656.25）
    kw_match = re.search(r"^(GB(?:/T)?\s*[\d\.\-]+)", standard_title)
    kw = kw_match.group(1).strip() if kw_match else standard_title[:20].strip()

    safe_filename = re.sub(r'[\\/:*?"<>|]', '_', standard_title).strip()
    if not safe_filename.lower().endswith(".pdf"):
        safe_filename += ".pdf"
    target_path = OUT_DIR / safe_filename

    if target_path.exists() and target_path.stat().st_size > 1024:
        logger.info("已存在文件，跳过: %s", target_path.name)
        return str(target_path)

    # 1. 检索 auth_id
    search_url = f"https://down.foodmate.net/standard/search.php?fields=0&kw={urllib.parse.quote(kw.encode('gbk', errors='ignore'))}"
    auth_id = None
    delay = 2.0
    for attempt in range(max_retries):
        try:
            time.sleep(random.uniform(1.5, 2.5))
            req = urllib.request.Request(search_url, headers=get_headers())
            with urllib.request.urlopen(req, timeout=12) as resp:
                html = resp.read().decode("gbk", errors="ignore")
                matches = re.findall(r"href=[\"\x27](?:https://down\.foodmate\.net)?/standard/sort/\d+/(\d+)\.html[\"\x27]", html)
                if matches:
                    auth_id = matches[0]
                    break
        except Exception as e:
            time.sleep(delay)
            delay *= 2

    if not auth_id:
        logger.warning("未检索到标准 auth_id: %s", standard_title)
        return None

    # 2. 流式下载 PDF
    down_url = f"https://down.foodmate.net/standard/down.php?auth={auth_id}"
    referer = f"https://down.foodmate.net/standard/sort/3/{auth_id}.html"
    delay = 2.5
    for attempt in range(max_retries):
        try:
            time.sleep(random.uniform(1.8, 2.8))
            req = urllib.request.Request(down_url, headers=get_headers(referer=referer))
            with urllib.request.urlopen(req, timeout=25) as resp:
                data = resp.read()
                if len(data) < 500 and b"503" in data:
                    raise urllib.error.HTTPError(down_url, 503, "Rate Limited", None, None)
                with open(target_path, "wb") as f:
                    f.write(data)
                logger.info("✅ 下载完成 [%.2f KB]: %s", len(data) / 1024, safe_filename)
                return str(target_path)
        except Exception as e:
            logger.warning("下载异常 [%s] (尝试 %d/%d): %s, 退避 %.1fs", standard_title, attempt + 1, max_retries, e, delay)
            time.sleep(delay)
            delay *= 2
    return None

def download_special_range(start_page: int = 1, end_page: int = 5):
    logger.info("🚀 启动食品安全国家标准专题下载，页码范围: %d -> %d", start_page, end_page)
    success_count = 0
    total_found = 0
    for page in range(start_page, end_page + 1):
        standards = get_page_standards(page)
        logger.info("第 %d 页解析出 %d 部标准", page, len(standards))
        total_found += len(standards)
        for std in standards:
            res = search_and_download(std)
            if res:
                success_count += 1
    logger.info("🎉 本轮下载结束: 成功 %d/%d 部标准落盘", success_count, total_found)

if __name__ == "__main__":
    sp = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    ep = int(sys.argv[2]) if len(sys.argv) > 2 else 5
    download_special_range(sp, ep)

