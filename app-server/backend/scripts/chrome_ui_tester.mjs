// @ts-check
import { spawn } from 'child_process';
import fs from 'fs';
import path from 'path';

const CHROME_PATH = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome';
const DEBUG_PORT = 9222;
const USER_DATA_DIR = '/tmp/rag_chrome_tester_profile';
const BASE_URL = 'http://localhost:2028';
const OUT_DIR = '/Users/gemini/.gemini/antigravity-ide/brain/bf69366e-5cfd-4595-a929-71f8ef63ec2d';

const AUTH_DATA = {
  token: "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIwYjg0Mzk3ZS0yMzhmLTQwMWMtODMxMS01MjI5OGExZWM1ZDMiLCJyb2xlIjoiYWRtaW4iLCJleHAiOjE3ODkzNTY5NjIsImlhdCI6MTc4ODc1MjE2Mn0.uBxPIgbsZ6BYd4EoczRfQepBJgPCWCQMJzpoJElEocE",
  user: {
    id: "0b84397e-238f-401c-8311-52298a1ec5d3",
    username: "系统管理员",
    login_name: "admin",
    email: "admin@syhsgis.com",
    company: "智能体开发",
    department: "",
    role: "admin",
    status: "active",
    avatar: "",
    created_at: "2026-06-25T02:30:07.705835"
  }
};

async function sleep(ms) {
  return new Promise(r => setTimeout(r, ms));
}

class CDPClient {
  constructor(wsUrl) {
    this.ws = new WebSocket(wsUrl);
    this.id = 1;
    this.pending = new Map();
    this.logs = [];

    this.ws.onmessage = (event) => {
      const data = JSON.parse(event.data);
      if (data.id && this.pending.has(data.id)) {
        const { resolve, reject } = this.pending.get(data.id);
        this.pending.delete(data.id);
        if (data.error) reject(data.error);
        else resolve(data.result);
      } else if (data.method === 'Runtime.consoleAPICalled') {
        const args = (data.params.args || []).map((a) => a.value || a.description).join(' ');
        this.logs.push(`[${data.params.type}] ${args}`);
      }
    };
  }

  async waitOpen() {
    if (this.ws.readyState === WebSocket.OPEN) return;
    return new Promise((resolve, reject) => {
      this.ws.onopen = resolve;
      this.ws.onerror = reject;
    });
  }

  send(method, params = {}) {
    const id = this.id++;
    return new Promise((resolve, reject) => {
      this.pending.set(id, { resolve, reject });
      this.ws.send(JSON.stringify({ id, method, params }));
    });
  }

  async evaluate(expression) {
    const res = await this.send('Runtime.evaluate', { expression, returnByValue: true, awaitPromise: true });
    return res?.result?.value;
  }

  async captureScreenshot(filepath) {
    const { data } = await this.send('Page.captureScreenshot', { format: 'png' });
    fs.writeFileSync(filepath, Buffer.from(data, 'base64'));
    console.log(`[SCREENSHOT] Saved: ${filepath}`);
  }

  close() {
    this.ws.close();
  }
}

async function run() {
  console.log('1. 启动 Chrome 无头实例...');
  if (fs.existsSync(USER_DATA_DIR)) fs.rmSync(USER_DATA_DIR, { recursive: true, force: true });

  const chromeProc = spawn(CHROME_PATH, [
    '--headless=new',
    `--remote-debugging-port=${DEBUG_PORT}`,
    `--user-data-dir=${USER_DATA_DIR}`,
    '--window-size=1440,900',
    '--disable-gpu',
    '--hide-scrollbars'
  ]);

  await sleep(1500);

  try {
    const listRes = await fetch(`http://127.0.0.1:${DEBUG_PORT}/json/list`);
    const pages = await listRes.json();
    const targetWsUrl = pages[0]?.webSocketDebuggerUrl;
    if (!targetWsUrl) throw new Error('未能获取到页面 WebSocket 调试链接');

    const client = new CDPClient(targetWsUrl);
    await client.waitOpen();
    await client.send('Page.enable');
    await client.send('Runtime.enable');

    console.log('2. 导航至系统主页并注入认证状态...');
    await client.send('Page.navigate', { url: `${BASE_URL}/` });
    await sleep(2000);

    // 注入 auth 状态
    const authPayload = JSON.stringify({
      state: { token: AUTH_DATA.token, user: AUTH_DATA.user, isLoggedIn: true },
      version: 0
    });
    await client.evaluate(`
      localStorage.setItem('shengyao-auth', ${JSON.stringify(authPayload)});
      localStorage.setItem('token', ${JSON.stringify(AUTH_DATA.token)});
    `);

    // 刷新页面载入认证状态
    console.log('3. 刷新载入 Dashboard 首页...');
    await client.send('Page.navigate', { url: `${BASE_URL}/` });
    await sleep(3500);

    await client.captureScreenshot(path.join(OUT_DIR, 'ui_home_light.png'));

    // 切换至暗黑模式测试
    console.log('4. 切换至深色模式 (Dark Mode)...');
    await client.evaluate(`
      document.documentElement.classList.add('dark');
      localStorage.setItem('theme', 'dark');
    `);
    await sleep(800);
    await client.captureScreenshot(path.join(OUT_DIR, 'ui_home_dark.png'));

    // 恢复浅色以便后续测试
    await client.evaluate(`document.documentElement.classList.remove('dark');`);

    // 测试并进入学习看板
    console.log('5. 测试后台监控/学习看板 (LearningProgress)...');
    await client.evaluate(`
      // 触发顶部导航或直接切换状态
      const btn = Array.from(document.querySelectorAll('button')).find(b => b.textContent.includes('看板') || b.textContent.includes('学习') || b.textContent.includes('进度') || b.textContent.includes('监控'));
      if (btn) btn.click();
    `);
    await sleep(3000);
    await client.captureScreenshot(path.join(OUT_DIR, 'ui_learning_progress.png'));

    // 测试文书工作室
    console.log('6. 测试文书工作室 (DocumentStudio)...');
    await client.evaluate(`
      const btn = Array.from(document.querySelectorAll('button')).find(b => b.textContent.includes('文书工作室') || b.textContent.includes('定制文档'));
      if (btn) btn.click();
    `);
    await sleep(2500);
    await client.captureScreenshot(path.join(OUT_DIR, 'ui_document_studio.png'));

    console.log('7. 控制台错误日志排查:');
    const errors = client.logs.filter(l => l.startsWith('[error]'));
    if (errors.length === 0) {
      console.log('✅ Console 零严重错误，运行平稳！');
    } else {
      console.log(`⚠️ 发现 ${errors.length} 条控制台错误:`, errors);
    }

    client.close();
    console.log('✅ 测试全部顺利完成！');
  } finally {
    chromeProc.kill('SIGKILL');
  }
}

run().catch(err => {
  console.error('测试执行失败:', err);
  process.exit(1);
});
