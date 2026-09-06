import os, re, sys, json, ssl, time
import urllib.request, urllib.parse
from concurrent.futures import ThreadPoolExecutor, as_completed

TARGET_DIR = "/Volumes/macData/GenRAG_Files/uploads/fe2982b3820e"
CATEGORIES = [
    {"code": "1024", "name": "01-食品添加剂"},
    {"code": "1574", "name": "02-食品营养强化剂"},
    {"code": "1025", "name": "03-食品产品"},
    {"code": "1026", "name": "04-生产经营规范"},
    {"code": "2032", "name": "05-食品标签"},
    {"code": "1022", "name": "06-污染物与真菌毒素"},
    {"code": "1023", "name": "07-微生物限量"},
    {"code": "1077", "name": "08-农药残留"},
    {"code": "2030", "name": "09-兽药残留"},
    {"code": "1028", "name": "10-营养与特殊膳食食品"},
    {"code": "1027", "name": "11-食品相关产品与接触材料"},
    {"code": "1029", "name": "12-理化检验方法与规程"},
    {"code": "1030", "name": "13-微生物检验方法与规程"},
    {"code": "1031", "name": "14-毒理学评价方法与程序"},
    {"code": "2033", "name": "15-修改单与勘误"}
]

CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE
HEADERS = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)", "Content-Type": "application/x-www-form-urlencoded"}

def clean_fn(text):
    text = re.sub(r'[\/\\:\*\?\"<>\|]', '_', str(text).strip())
    return re.sub(r'\s+', ' ', text).strip()

def download_file(url, data_dict, dest_path):
    if os.path.exists(dest_path) and os.path.getsize(dest_path) > 5000:
        return True, "EXISTS", os.path.getsize(dest_path)
    data = urllib.parse.urlencode(data_dict).encode("utf-8")
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, data=data, headers=HEADERS)
            with urllib.request.urlopen(req, context=CTX, timeout=25) as resp:
                content = resp.read()
                if content.startswith(b"%PDF") or len(content) > 5000:
                    os.makedirs(os.path.dirname(dest_path), exist_ok=True)
                    tmp_path = dest_path + ".tmp"
                    with open(tmp_path, "wb") as f:
                        f.write(content)
                    os.rename(tmp_path, dest_path)
                    return True, "DOWNLOADED", len(content)
        except Exception:
            time.sleep(1.0 + attempt)
    return False, "FAILED", 0

def fetch_category_items(cat):
    data = urllib.parse.urlencode({"isLength": "9999", "num_tn": "2", "standard_type": cat["code"], "keyword": ""}).encode("utf-8")
    try:
        req = urllib.request.Request("https://sppt.cfsa.net.cn:8086/db?task=indexSearch", data=data, headers=HEADERS)
        with urllib.request.urlopen(req, context=CTX, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        print(f"[-] 获取分类 {cat['name']} 失败: {e}")
        return []

def main():
    os.makedirs(TARGET_DIR, exist_ok=True)
    all_tasks = []
    seen_guids = set()
    print("=== 开始拉取 CFSA 各分类标准元数据 ===")
    for cat in CATEGORIES:
        items = fetch_category_items(cat)
        cat_dir = os.path.join(TARGET_DIR, cat["name"])
        os.makedirs(cat_dir, exist_ok=True)
        print(f"[{cat['name']}] 获得 {len(items)} 部标准")
        for it in items:
            fjs = it.get("FJ") or []
            code = clean_fn(it.get("CODE") or "")
            title = clean_fn(it.get("TITLE") or "")
            for fj in fjs:
                id_f = fj.get("ID_F")
                if not id_f or id_f in seen_guids:
                    continue
                seen_guids.add(id_f)
                fn = f"{code} {title}.pdf" if code else f"{title}.pdf"
                dest_path = os.path.join(cat_dir, fn)
                all_tasks.append((id_f, dest_path, code, title, cat["name"]))

    print(f"\n元数据拉取完成，待处理官方标准附件总数: {len(all_tasks)}")
    success, skipped, failed = 0, 0, 0
    t0 = time.time()
    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = {executor.submit(download_file, "https://sppt.cfsa.net.cn:8086/cfsa_aiguo", {"task": "d_p", "file_guid": t[0]}, t[1]): t for t in all_tasks}
        for idx, fut in enumerate(as_completed(futures), 1):
            task_info = futures[fut]
            try:
                ok, status, sz = fut.result()
                if ok:
                    if status == "EXISTS":
                        skipped += 1
                    else:
                        success += 1
                        print(f"[{idx}/{len(all_tasks)}] 已下载: {task_info[2]} {task_info[3]} ({sz//1024} KB)")
                else:
                    failed += 1
                    print(f"[-] 下载失败: {task_info[2]} {task_info[3]}")
            except Exception as e:
                failed += 1
                print(f"[-] 异常: {e}")
            if idx % 50 == 0:
                print(f"--- 进度: {idx}/{len(all_tasks)} (已下:{success}, 已存在:{skipped}, 失败:{failed}, 耗时:{time.time()-t0:.1f}s) ---")
    print(f"\n🎉 全部完成! 成功下载: {success}, 跳过已存在: {skipped}, 失败: {failed}, 总耗时: {time.time()-t0:.1f}s")

if __name__ == "__main__":
    main()
