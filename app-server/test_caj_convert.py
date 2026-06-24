import urllib.request
import urllib.parse
import subprocess
from pathlib import Path
import sys

# 1. 下载测试 KDH/CAJ 文件
rel_path = "flfg_3/民法/最高人民法院关于审理涉及夫妻债务纠纷案件适用法律有关问题的解释.caj"
base_url = "http://tsg.court.gov.cn/home/rdyd/"
url = base_url + urllib.parse.quote(rel_path)

caj_path = Path("/app/caj2pdf/test_夫妻债务.caj")
pdf_path = Path("/app/caj2pdf/test_夫妻债务.pdf")

print("1. Downloading CAJ file...")
headers = {
    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
}
req = urllib.request.Request(url, headers=headers)
with urllib.request.urlopen(req, timeout=15) as response:
    caj_path.write_bytes(response.read())
print("Downloaded. Size:", caj_path.stat().st_size, "bytes")

# 2. 调用 caj2pdf 转换
print("\n2. Converting CAJ to PDF via caj2pdf...")
try:
    cmd = ["python3", "/app/caj2pdf/caj2pdf", "convert", str(caj_path), "-o", str(pdf_path)]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    print("Stdout:", result.stdout)
    print("Stderr:", result.stderr)
    print("Exit code:", result.returncode)
except Exception as e:
    print("Conversion exception:", e)

# 3. 检查 PDF 并用 PyMuPDF 提取内容
if pdf_path.exists():
    print(f"\n3. PDF generated successfully ({pdf_path.stat().st_size} bytes). Extracting text...")
    try:
        import fitz
        doc = fitz.open(str(pdf_path))
        print("Page count:", len(doc))
        for idx in range(min(5, len(doc))):
            print(f"--- Page {idx+1} ---")
            print(doc[idx].get_text()[:400])
    except Exception as pe:
        print("Text extraction failed:", pe)
else:
    print("\n3. Error: PDF file was not generated.")
