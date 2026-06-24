import os
import re
import time
import urllib.request
import urllib.parse
from pathlib import Path

BASE_URL = "http://tsg.court.gov.cn/home/rdyd/"
PAGE_URL = BASE_URL + "flfg_3.html"
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
}

# 根目录定位，指向 RAG 项目的根路径下的 docs
PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEST_ROOT = PROJECT_ROOT / "docs" / "flk" / "司法解释"

# 映射表：将链接里的路径简称映射到用户要求的标准子目录名
CATEGORY_MAPPING = {
    "民法": "民法",
    "商法": "商法",
    "民诉": "民事诉讼法",
    "刑法": "刑法",
    "刑诉": "刑事诉讼法",
    "行政": "行政法"
}

def fetch_page_content(url: str, retries: int = 5) -> str:
    """请求网页内容，并支持指数退避重试"""
    delay = 1.0
    for i in range(retries):
        try:
            req = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=15) as response:
                html = response.read()
                try:
                    return html.decode('utf-8')
                except UnicodeDecodeError:
                    return html.decode('gbk', errors='ignore')
        except Exception as e:
            print(f"[Warning] 请求 {url} 失败: {e}，第 {i+1} 次重试，等待 {delay}s...")
            time.sleep(delay)
            delay *= 2.0
    raise RuntimeError(f"无法请求页面 {url}")

def download_file(url: str, dest_path: Path, retries: int = 5):
    """下载单个文件，支持指数退避重试"""
    delay = 1.0
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    for i in range(retries):
        try:
            req = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=20) as response:
                dest_path.write_bytes(response.read())
            print(f"[Success] 已成功下载: {dest_path.name} ({dest_path.stat().st_size} bytes)")
            return
        except Exception as e:
            print(f"[Warning] 下载 {url} 失败: {e}，第 {i+1} 次重试，等待 {delay}s...")
            time.sleep(delay)
            delay *= 2.0
    print(f"[Error] 彻底下载失败: {dest_path.name}")

def main():
    print("开始获取司法解释下载列表...")
    try:
        html = fetch_page_content(PAGE_URL)
    except Exception as e:
        print(f"获取页面失败: {e}")
        return

    # 正则提取所有的 caj 链接
    caj_links = re.findall(r'href="([^"]+\.caj)"', html, re.IGNORECASE)
    if not caj_links:
        caj_links = re.findall(r"href='([^']+\.caj)'", html, re.IGNORECASE)
    
    print(f"共发现 {len(caj_links)} 个 CAJ 文件链接。开始分类下载...")
    
    for rel_path in caj_links:
        # 例如: flfg_3/民法/最高人民法院关于审理涉及夫妻债务纠纷案件适用法律有关问题的解释.caj
        parts = rel_path.split('/')
        category = "其他"
        if len(parts) >= 2:
            raw_cat = parts[-2]
            category = CATEGORY_MAPPING.get(raw_cat, raw_cat)
            
        filename = parts[-1]
        dest_file = DEST_ROOT / category / filename
        
        # 拼接下载的完整 URL
        download_url = BASE_URL + urllib.parse.quote(rel_path)
        
        # 如果文件已存在且大小不为0，则跳过
        if dest_file.exists() and dest_file.stat().st_size > 0:
            print(f"[Skip] 文件已存在，跳过: {dest_file.name}")
            continue
            
        print(f"正在下载 [{category}] -> {filename}...")
        download_file(download_url, dest_file)
        time.sleep(0.5)

if __name__ == "__main__":
    main()
