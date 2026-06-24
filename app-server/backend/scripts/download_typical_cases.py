import os
import json
import ssl
import re
import urllib.request
from pathlib import Path

# 定位 docs/flk/典型案例/
PROJECT_ROOT = Path(__file__).resolve().parents[3]
TYPICAL_DIR = PROJECT_ROOT / "docs" / "flk" / "典型案例"
TYPICAL_DIR.mkdir(parents=True, exist_ok=True)

ssl_ctx = ssl.create_default_context()
ssl_ctx.check_hostname = False
ssl_ctx.verify_mode = ssl.CERT_NONE

HEADERS = {'User-Agent': 'Mozilla/5.0'}

# 代理处理器
proxy_url = "http://127.0.0.1:7897"
proxy_handler = urllib.request.ProxyHandler({'http': proxy_url, 'https': proxy_url})
opener = urllib.request.build_opener(proxy_handler)
urllib.request.install_opener(opener)

def clean_title(title: str) -> str:
    """清理文件名中的非法字符"""
    for char in ['/', '\\', ':', '*', '?', '"', '<', '>', '|', '\r', '\n', '\t']:
        title = title.replace(char, "_")
    return title.strip()

def extract_case_title(query_text: str, default_id: str) -> str:
    """从判决书全文开头中正则匹配提取文书标题"""
    lines = [line.strip() for line in query_text.splitlines() if line.strip()]
    if not lines:
        return f"典型案例_{default_id}"
    
    title = ""
    # 优先在前5行中寻找含有特定司法文书关键字的一行
    for line in lines[:5]:
        if any(keyword in line for keyword in ["判决书", "裁定书", "决定书", "意见书", "调解书"]):
            # 用正则只截取到关键字为止，防止混入后面的长文
            match = re.search(r'^(.*?(?:判决书|裁定书|决定书|意见书|调解书))', line)
            if match:
                title = match.group(1)
                break
            else:
                title = line
                break
                
    if not title:
        title = lines[0]
        
    # 强制截断长度，防止文件名超长
    if len(title) > 40:
        title = title[:40]
        
    return title

def main():
    print("正在连接 GitHub 并获取典型案例数据库索引...")
    url = "https://api.github.com/repos/THUIR/LeCaRDv2/contents/query/query.json"
    
    try:
        req = urllib.request.Request(url, headers=HEADERS)
        with urllib.request.urlopen(req, context=ssl_ctx, timeout=15) as r:
            file_info = json.loads(r.read().decode())
        download_url = file_info["download_url"]
    except Exception as e:
        print(f"[Error] 获取下载索引失败: {e}")
        return
        
    print(f"正在从 {download_url} 下载典型案例数据...")
    try:
        req_dl = urllib.request.Request(download_url, headers=HEADERS)
        with urllib.request.urlopen(req_dl, context=ssl_ctx, timeout=30) as r_dl:
            # 这是一个 JSONL 文件
            lines = r_dl.read().decode('utf-8').splitlines()
    except Exception as e:
        print(f"[Error] 下载案例数据失败: {e}")
        return

    total_cases = len(lines)
    print(f"成功获取到 {total_cases} 件案例候选数据。开始导出前 100 件典型案例...")
    
    success_count = 0
    # 提取前 100 件
    for i in range(min(100, total_cases)):
        try:
            case_data = json.loads(lines[i])
            case_id = str(case_data.get("id", i + 1))
            query_text = case_data.get("query", "").strip()
            fact_text = case_data.get("fact", "").strip()
            
            if not query_text:
                continue
                
            raw_title = extract_case_title(query_text, case_id)
            title = clean_title(raw_title)
            
            # 拼装 Markdown
            md_content = f"""# {raw_title}

## 1. 案例基本信息
- **案例编号**：LeCaRD-{case_id}
- **案例类型**：典型案例 / 裁判文书

## 2. 案件事实与控辩指控摘要
{fact_text if fact_text else "暂无摘要"}

## 3. 裁判文书全文
```text
{query_text}
```
"""
            dest_file = TYPICAL_DIR / f"{title}.md"
            dest_file.write_text(md_content, encoding="utf-8")
            success_count += 1
        except Exception as e:
            print(f"[Warning] 导出第 {i+1} 件案例失败: {e}")
            
    print(f"\n🎉 成功导出裁判文书典型案例: 共 {success_count} 篇文档，存入 {TYPICAL_DIR}")

if __name__ == "__main__":
    main()
