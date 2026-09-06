"""
食品伙伴网（Foodmate）标准批量检索与安全下载脚本。
实现了指数退避（Exponential Backoff，在发生错误后按指数级延长重试等待时间）
与请求速率限制（Rate Limiting，控制单位时间内的请求频次，防范503频控拦截）。
"""
import os
import re
import time
import random
import logging
import urllib.request
import urllib.parse
from pathlib import Path
from typing import Optional, Dict, List

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger("FoodmateDownloader")

USER_AGENTS = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/127.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Safari/605.1.15",
]

class FoodmateDownloader:
    """食品伙伴网标准自动化检索与安全下载器"""
    
    SEARCH_URL = "https://down.foodmate.net/standard/search.php"
    DOWN_BASE = "https://down.foodmate.net/standard/down.php"

    def __init__(self, output_dir: str):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.opener = urllib.request.build_opener()

    def _get_headers(self, referer: Optional[str] = None) -> Dict[str, str]:
        headers = {
            "User-Agent": random.choice(USER_AGENTS),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Connection": "keep-alive",
        }
        if referer:
            headers["Referer"] = referer
        return headers

    def search_standard(self, keyword: str, max_retries: int = 3) -> Optional[Dict[str, str]]:
        """按标准代号或关键字检索，返回首条权威匹配结果的 auth_id 及标题"""
        kw_gbk = urllib.parse.quote(keyword.encode("gbk", errors="ignore"))
        url = f"{self.SEARCH_URL}?fields=0&kw={kw_gbk}"
        
        delay = 2.0
        for attempt in range(max_retries):
            try:
                # 随机礼貌休眠，规避 503 频控
                time.sleep(random.uniform(1.8, 3.2))
                req = urllib.request.Request(url, headers=self._get_headers())
                with self.opener.open(req, timeout=15) as resp:
                    html = resp.read().decode("gbk", errors="ignore")
                    matches = re.findall(
                        r"href=[\"\x27](https://down\.foodmate\.net/standard/sort/\d+/(\d+)\.html)[\"\x27][^>]*>(.*?)</a>",
                        html
                    )
                    if matches:
                        link, auth_id, raw_title = matches[0]
                        clean_title = re.sub(r"<[^>]+>", "", raw_title).replace("&nbsp;", " ").strip()
                        return {"auth_id": auth_id, "detail_url": link, "title": clean_title}
                    else:
                        logger.warning("未检索到标准: %s", keyword)
                        return None
            except urllib.error.HTTPError as e:
                logger.warning("检索 HTTP 错误 [%s] (尝试 %d/%d): %s, 等待 %.1fs...", keyword, attempt + 1, max_retries, e, delay)
                time.sleep(delay)
                delay *= 2  # 指数退避
            except Exception as e:
                logger.error("检索异常 [%s] (尝试 %d/%d): %s", keyword, attempt + 1, max_retries, e)
                time.sleep(delay)
                delay *= 2
        return None

    def download_pdf(self, auth_id: str, title: str, max_retries: int = 3) -> Optional[str]:
        """依据 auth_id 请求下载重定向直链并落盘为 PDF 文件"""
        safe_name = re.sub(r'[\\/:*?"<>|]', '_', title).strip()
        if not safe_name.lower().endswith(".pdf"):
            safe_name += ".pdf"
        target_path = self.output_dir / safe_name
        
        if target_path.exists() and target_path.stat().st_size > 1024:
            logger.info("文件已存在，跳过下载: %s", target_path.name)
            return str(target_path)

        down_url = f"{self.DOWN_BASE}?auth={auth_id}"
        referer = f"https://down.foodmate.net/standard/sort/3/{auth_id}.html"
        delay = 2.5

        for attempt in range(max_retries):
            try:
                time.sleep(random.uniform(2.0, 3.5))
                req = urllib.request.Request(down_url, headers=self._get_headers(referer=referer))
                with self.opener.open(req, timeout=30) as resp:
                    data = resp.read()
                    if len(data) < 500 and b"503" in data:
                        raise urllib.error.HTTPError(down_url, 503, "Service Temporarily Unavailable", None, None)
                    if not data.startswith(b"%PDF"):
                        logger.warning("下载返回非标准 PDF 流 [%s], 首部: %s", title, data[:30])
                    with open(target_path, "wb") as f:
                        f.write(data)
                    logger.info("✅ 下载成功 [%.2f KB]: %s", len(data) / 1024, safe_name)
                    return str(target_path)
            except Exception as e:
                logger.warning("下载异常 [%s] (尝试 %d/%d): %s, 退避 %.1fs", title, attempt + 1, max_retries, e, delay)
                time.sleep(delay)
                delay *= 2
        return None

# 核心高频食品安全国家标准与高频执法类别标准清单
CORE_STANDARDS = [
    # ── 通用核心基础标准 ──
    "GB 7718-2011",   # 预包装食品标签通则
    "GB 28050-2011",  # 预包装食品营养标签通则
    "GB 14881-2013",  # 食品生产通用卫生规范
    "GB 2760-2024",   # 食品添加剂使用标准（最新版）
    "GB 2761-2017",   # 食品中真菌毒素限量
    "GB 2762-2022",   # 食品中污染物限量
    "GB 29921-2021",  # 预包装食品中致病菌限量
    "GB 31607-2021",  # 散装即食食品中致病菌限量
    "GB 31650-2019",  # 食品中兽药最大残留限量
    "GB 2763-2021",   # 食品中农药最大残留限量
    # ── 常见高频争议与执法产品标准 ──
    "GB 2726-2016",   # 熟肉制品
    "GB/T 23586-2009",# 酱卤肉制品
    "GB 2717-2018",   # 酱油
    "GB 2719-2018",   # 食醋
    "GB 19300-2014",  # 坚果与籽类食品
    "GB/T 22165-2008",# 坚果炒货食品通则
    "GB 7099-2015",   # 糕点、面包
    "GB 19295-2021",  # 速冻面米与调制食品
    "GB 2716-2018",   # 植物油
    "GB 7101-2022",   # 饮料
]

def batch_download_standards(output_dir: str, standards: List[str]) -> List[str]:
    downloader = FoodmateDownloader(output_dir)
    downloaded_files = []
    for kw in standards:
        logger.info("🔍 开始检索标准: %s", kw)
        meta = downloader.search_standard(kw)
        if meta:
            file_path = downloader.download_pdf(meta["auth_id"], meta["title"])
            if file_path:
                downloaded_files.append(file_path)
    return downloaded_files

if __name__ == "__main__":
    out = "/Volumes/macData/GenRAG_Files/uploads/food_standards_temp"
    batch_download_standards(out, CORE_STANDARDS[:5])

