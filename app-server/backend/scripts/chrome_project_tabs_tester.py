import asyncio
import base64
import json
import os
import shutil
import subprocess
import time
import urllib.request
import websockets

CHROME_BIN = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
PORT = 9222
USER_DATA = "/tmp/rag_chrome_tabs_profile"
BASE_URL = "http://localhost:2028"
OUT_DIR = "/Users/gemini/.gemini/antigravity-ide/brain/bf69366e-5cfd-4595-a929-71f8ef63ec2d"
PROJ_ID = "51404300b880"  # 拼多多腐乳蘸项目

AUTH_PAYLOAD = {
    "state": {
        "token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIwYjg0Mzk3ZS0yMzhmLTQwMWMtODMxMS01MjI5OGExZWM1ZDMiLCJyb2xlIjoiYWRtaW4iLCJleHAiOjE3ODkzNTY5NjIsImlhdCI6MTc4ODc1MjE2Mn0.uBxPIgbsZ6BYd4EoczRfQepBJgPCWCQMJzpoJElEocE",
        "user": {
            "id": "0b84397e-238f-401c-8311-52298a1ec5d3", "username": "系统管理员",
            "login_name": "admin", "email": "admin@syhsgis.com",
            "company": "智能体开发", "department": "", "role": "admin",
            "status": "active", "avatar": "", "created_at": "2026-06-25T02:30:07.705835"
        },
        "isLoggedIn": True
    },
    "version": 0
}

async def send_cmd(ws, req_id, method, params=None):
    await ws.send(json.dumps({"id": req_id, "method": method, "params": params or {}}))
    while True:
        data = json.loads(await asyncio.wait_for(ws.recv(), timeout=10.0))
        if data.get("id") == req_id:
            return data.get("result")

async def snap(ws, req_id, filename):
    res = await send_cmd(ws, req_id, "Page.captureScreenshot", {"format": "png"})
    filepath = os.path.join(OUT_DIR, filename)
    with open(filepath, "wb") as f:
        f.write(base64.b64decode(res["data"]))
    print(f"   📸 已保存快照: {filename}")

async def click_tab_by_index(ws, req_id, index):
    js = f"""
        const tabs = document.querySelectorAll('header .overflow-x-auto > div');
        if (tabs[{index}]) {{
            tabs[{index}].click();
            true;
        }} else {{
            false;
        }}
    """
    res = await send_cmd(ws, req_id, "Runtime.evaluate", {"expression": js, "returnByValue": True})
    return res.get("result", {}).get("value", False)

async def main():
    if os.path.exists(USER_DATA):
        shutil.rmtree(USER_DATA, ignore_errors=True)
    print("🚀 启动 Chrome 实例深入审查各业务功能 Tab...")
    proc = subprocess.Popen([
        CHROME_BIN, "--headless=new", f"--remote-debugging-port={PORT}",
        f"--user-data-dir={USER_DATA}", "--window-size=1440,900",
        "--disable-gpu", "--hide-scrollbars"
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(1.5)

    try:
        req = urllib.request.Request(f"http://127.0.0.1:{PORT}/json/new?{BASE_URL}/", method="PUT")
        with urllib.request.urlopen(req) as resp:
            ws_url = json.loads(resp.read().decode())["webSocketDebuggerUrl"]

        async with websockets.connect(ws_url, max_size=20*1024*1024) as ws:
            req_id = 1
            await send_cmd(ws, req_id, "Page.enable"); req_id += 1
            await send_cmd(ws, req_id, "Runtime.enable"); req_id += 1

            # 注入鉴权
            auth_str = json.dumps(json.dumps(AUTH_PAYLOAD, ensure_ascii=False))
            token_str = json.dumps(AUTH_PAYLOAD["state"]["token"])
            init_js = f"""
                localStorage.setItem('shengyao-auth', {auth_str});
                localStorage.setItem('token', {token_str});
                localStorage.setItem('colorMode_admin', 'light');
            """
            await send_cmd(ws, req_id, "Runtime.evaluate", {"expression": init_js}); req_id += 1

            # 导航至真实业务项目
            print(f"💼 导航至真实项目 [{PROJ_ID}] 工作台...")
            await send_cmd(ws, req_id, "Page.navigate", {"url": f"{BASE_URL}/project/{PROJ_ID}"}); req_id += 1
            await asyncio.sleep(4.0)
            await snap(ws, req_id, "ui_tab_chat.png"); req_id += 1

            # 测试分拣填报 (index 1)
            print("📋 点击切换至「分拣填报」...")
            await click_tab_by_index(ws, req_id, 1); req_id += 1
            await asyncio.sleep(2.5)
            await snap(ws, req_id, "ui_tab_triage.png"); req_id += 1

            # 测试调查取证 (index 2)
            print("🔍 点击切换至「调查取证」...")
            await click_tab_by_index(ws, req_id, 2); req_id += 1
            await asyncio.sleep(2.5)
            await snap(ws, req_id, "ui_tab_evidence.png"); req_id += 1

            # 测试研判裁量 (index 3)
            print("⚖️ 点击切换至「研判裁量」...")
            await click_tab_by_index(ws, req_id, 3); req_id += 1
            await asyncio.sleep(2.5)
            await snap(ws, req_id, "ui_tab_adjudication.png"); req_id += 1

            # 测试定制文档（文书工作室） (index 4)
            print("📄 点击切换至「定制文档」文书工作室...")
            await click_tab_by_index(ws, req_id, 4); req_id += 1
            await asyncio.sleep(3.0)
            await snap(ws, req_id, "ui_tab_docstudio.png"); req_id += 1

            print("🎉 业务 Tab 自动化深度审查完成！")
    finally:
        proc.kill()

if __name__ == "__main__":
    asyncio.run(main())
