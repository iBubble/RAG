import { chromium } from 'playwright';
import path from 'path';

const DOCX_PATH = '/Users/shengyao/Projects/ShengyaoRAG/docs/2024年水利发展资金峨边彝族自治县夏家沟项目区实施方案（报批稿624）.docx';

const delay = (ms) => new Promise(res => setTimeout(res, ms));

async function runTest() {
  console.log('启动浏览器环境测试...');
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext();
  const page = await context.newPage();

  // 1. 打开首页
  await page.goto('http://localhost:8008', { waitUntil: 'domcontentloaded', timeout: 60000 });
  console.log('页面已加载。');
  
  // 等待项目加载并点击第一个项目
  await page.waitForSelector('p:text("Test Project")', { timeout: 10000 }).catch(() => {});
  await page.click('h3.font-medium'); // 点击第一个项目卡片
  console.log('进入项目工作台...');
  
  // 2. 切换到“文档编写”Tab
  await page.waitForSelector('button:has-text("文档编写")');
  await page.click('button:has-text("文档编写")');
  await delay(1000);

  // 3. 上传大纲（解除锁定）
  console.log('上传大纲...');
  const fileInput = await page.locator('input[type="file"]').first();
  await fileInput.setInputFiles(DOCX_PATH);
  
  // 等待上传和解析完成 (出现“共成功挂载 X 个骨干节点”)
  await page.waitForSelector('text=共成功挂载', { timeout: 30000 });
  console.log('大纲已加载成功，文档编写台解锁。');
  await delay(1000);

  // 开始循环测试大模型
  const models = ["deepseek-r1:32b", "qwen3.5:35b-q8", "qwen3.5:35b-q4"];
  const results = [];

  for (const model of models) {
    console.log(`\n============================`);
    console.log(`正在测试模型: ${model}`);
    console.log(`============================`);
    
    // 切换模型
    // 选择下拉框
    await page.selectOption('select.text-sm.border-gray-300', model);
    await page.click('button:has-text("换")'); // 点击切换按钮
    
    const loadStart = Date.now();
    console.log('切换指令已发送，等待引擎在线...');
    
    // 等到出现“引擎在线”绿灯
    await page.waitForSelector('text=引擎在线', { timeout: 60000 });
    const loadTime = ((Date.now() - loadStart) / 1000).toFixed(2);
    console.log(`[+] 模型 ${model} 切换完成，耗时: ${loadTime}s`);

    // 定位目标：项目背景
    // 先获取“项目背景”右侧的“快速编写”按钮
    // 在右侧画布寻找内容
    
    const testTrials = async (trial) => {
        console.log(`\n--- 试运行 ${trial} 针对【项目背景】---`);
        // 清空文本框（寻找具有 .tiptap 或者富文本区的容器，或者点击左侧标题聚焦）
        // 因为Tiptap无缝编辑，我们直接清空画布上对应的 section
        // 实际上可以用 JS 强行清空
        
        // 点击左侧大纲找到按钮
        const sectionTitle = await page.locator('div.w-full:has-text("项目背景")').first();
        // hover it or find the action button nearby
        
        // 最好直接找包含“快速编写本节内容”并紧挨着“项目背景”相关的区块。
        // 或者清空状态：如果内容不为空，点击内容并全选删除
        // 但我们直接使用 evaluate 来清理 zustand store 或操作 DOM 比较鲁棒
        await page.evaluate(() => {
            const editorElems = document.querySelectorAll('.ProseMirror');
            for (let el of editorElems) {
               // 非常暴力的清理
               el.innerHTML = '<p><br class="ProseMirror-trailingBreak"></p>';
            }
        });
        await delay(500);

        // 查找“快速编写本节内容”的火箭按钮，由于只对第一层渲染，可能有很多，找到第一个 visible 的
        const writeBtns = await page.locator('button:has-text("快速编写本节内容")').all();
        // 我们假设第一个就是“项目背景”（通常第一章）
        let writeBtn = writeBtns[0]; 
        
        const genStart = Date.now();
        await writeBtn.click();
        
        console.log('已点击生成，等待第一个字...');
        
        // 监听 Tiptap 文本内容变化来测定 T1
        // 找出生成的 textarea 或 ProseMirror
        const pm = page.locator('.ProseMirror').first();
        let T1 = null;
        
        // 轮询内容
        while (true) {
            const text = await pm.innerText();
            if (text.trim().length > 0 && !T1) {
                T1 = ((Date.now() - genStart) / 1000).toFixed(2);
                console.log(`[+] 首字出词耗时 (T1): ${T1}s`);
                break;
            }
            await delay(100);
            if (Date.now() - genStart > 45000 && !T1) {
                console.log('等待超时...');
                break;
            }
        }
        
        // 等待生成结束 (按钮文字变回，或不包含 loader)
        console.log('生成中，等待完成...');
        // 生成结束时按钮的图标改变，或者 .animate-spin 消失
        await page.locator('.animate-spin').waitFor({ state: 'detached', timeout: 120000 });
        
        const T2 = ((Date.now() - genStart) / 1000 - T1).toFixed(2);
        console.log(`[+] 生成完成，正文生成耗时 (T2): ${T2}s`);
        
        return { T1, T2 };
    };

    const trial1 = await testTrials(1);
    const trial2 = await testTrials(2);
    
    results.push({
        model,
        loadTime,
        trial1,
        trial2
    });
  }

  await browser.close();
  
  // 打印最终报表
  console.log('\n\n======================================================');
  console.log('测试结束，以下为大模型加载与处理耗时对比（模拟真实交互）');
  console.log('======================================================\n');
  
  console.log('| 模型 | 切换/加载时长 | 第 1 次 (T1首字 / T2生成) | 第 2 次 (T1首字 / T2生成) |');
  console.log('|---|---|---|---|');
  results.forEach(r => {
      console.log(`| ${r.model} | \t${r.loadTime}s | \t${r.trial1.T1}s  /  ${r.trial1.T2}s | \t${r.trial2.T1}s  /  ${r.trial2.T2}s |`);
  });

  process.exit(0);
}

runTest().catch(console.error);
