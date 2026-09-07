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
USER_DATA = "/tmp/rag_chrome_cdp_profile"
BASE_URL = "http://localhost:2028"
OUT_DIR = "/Users/gemini/.gemini/antigravity-ide/brain/bf69366e-5cfd-4595-a929-71f8ef63ec2d"

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

async def main():
    if os.path.exists(USER_DATA):
        shutil.rmtree(USER_DATA, ignore_errors=True)
    print("🚀 启动本地无头 Chrome 实例...")
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
            await asyncio.sleep(1.5)

            # 注入用户认证与默认设置
            auth_str = json.dumps(json.dumps(AUTH_PAYLOAD, ensure_ascii=False))
            token_str = json.dumps(AUTH_PAYLOAD["state"]["token"])
            init_js = f"""
                localStorage.setItem('shengyao-auth', {auth_str});
                localStorage.setItem('token', {token_str});
            """
            await send_cmd(ws, req_id, "Runtime.evaluate", {"expression": init_js}); req_id += 1

            # 1. 测试并审查后台学习进度看板 (LearningProgress)
            print("📊 1. 深度测试后台学习监控看板 (/admin/learning-progress)...")
            await send_cmd(ws, req_id, "Page.navigate", {"url": f"{BASE_URL}/admin/learning-progress"}); req_id += 1
            await asyncio.sleep(3.0)
            await snap(ws, req_id, "ui_learning_progress.png"); req_id += 1

            # 2. 测试服务状态看板 (/admin/service-status)
            print("🖥️ 2. 深度测试服务状态监控看板 (/admin/service-status)...")
            await send_cmd(ws, req_id, "Page.navigate", {"url": f"{BASE_URL}/admin/service-status"}); req_id += 1
            await asyncio.sleep(2.5)
            await snap(ws, req_id, "ui_service_status.png"); req_id += 1

            # 3. 获取第一个真实项目 ID 并进入项目工作室 (Studio)
            print("💼 3. 深度测试项目工作台 (Studio / 文书与填报)...")
            js_get_proj = "fetch('/api/projects').then(r => r.json()).then(d => d.projects[0]?.id || '')"
            proj_res = await send_cmd(ws, req_id, "Runtime.evaluate", {"expression": js_get_proj, "awaitPromise": True}); req_id += 1
            proj_id = proj_res.get("result", {}).get("value", "1")
            print(f"   -> 进入项目 ID: {proj_id}")
            await send_cmd(ws, req_id, "Page.navigate", {"url": f"{BASE_URL}/project/{proj_id}"}); req_id += 1
            await asyncio.sleep(4.0)
            await snap(ws, req_id, "ui_project_studio.png"); req_id += 1

            # 4. 测试全局深色模式 (Dark Mode)
            print("🌙 4. 深度测试全局深色模式下的对比度与立体边框...")
            dark_theme = json.dumps(json.dumps({"state": {"colorMode": "dark"}, "version": 0}))
            js_dark = f"""
                localStorage.setItem('colorMode_admin', 'dark');
                localStorage.setItem('shengyao-theme-mode', {dark_theme});
                document.documentElement.setAttribute('data-mode', 'dark');
                document.documentElement.classList.add('dark');
            """
            await send_cmd(ws, req_id, "Runtime.evaluate", {"expression": js_dark}); req_id += 1
            await asyncio.sleep(1.0)
            await snap(ws, req_id, "ui_project_studio_dark.png"); req_id += 1

            # 5. 导航回首页在暗黑模式下的表现
            await send_cmd(ws, req_id, "Page.navigate", {"url": f"{BASE_URL}/"}); req_id += 1
            await asyncio.sleep(3.0)
            await snap(ws, req_id, "ui_home_dark_real.png"); req_id += 1

            print("✨ 全前台高保真渲染快照已全部生成！")
    finally:
        proc.kill()

if __name__ == "__main__":
    asyncio.run(main())
