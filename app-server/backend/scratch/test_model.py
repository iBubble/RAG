import sys
import os
import asyncio
import hashlib
from pathlib import Path

# 将 /app/backend 目录加入 sys.path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.llm_engine import stream_ollama
from core.config import settings

def get_file_text_from_disk(project_id: str, file_id: str) -> tuple[str, str]:
    from core.extractors import extract_text
    upload_root = Path(settings.UPLOAD_DIR)
    project_dir = upload_root / project_id
    if not project_dir.exists():
        return "", "未知文件"
        
    for root, dirs, files in os.walk(str(project_dir)):
        dirs[:] = [d for d in dirs if not d.startswith('.')]
        for f in files:
            if f.startswith('.'):
                continue
            fpath = Path(root) / f
            rel_path = str(fpath.relative_to(upload_root))
            fid = hashlib.md5(f"{project_id}_{rel_path}".encode("utf-8")).hexdigest()
            if fid == file_id:
                try:
                    text = extract_text(str(fpath))
                    return text or "", f
                except Exception as e:
                    return "", f
    return "", "未知文件"

async def test():
    template_html = """
<p>登记单位：_______</p>
<p>编号：_______</p>
<h1>投诉登记表</h1>
<table border="1">
    <tr>
        <th>姓名</th>
        <td></td>
        <th>联系电话</th>
        <td></td>
    </tr>
    <tr>
        <th>证件类型</th>
        <td></td>
        <th>证件号码</th>
        <td></td>
    </tr>
    <tr>
        <th>联系地址</th>
        <td colspan="3"></td>
    </tr>
    <tr>
        <th>消费者权益争议事实依据</th>
        <td colspan="3">_______</td>
    </tr>
</table>
"""
    # 模拟真实从磁盘读取
    # 假设 project_id 是 default
    project_id = "default"
    
    # 我们可以放一段模拟上下文
    context_str = """
### 系统当前环境上下文信息
【当前日期】：2026年06月25日
【当前时间】：2026年06月25日 22时30分
【当前关联的项目/案件名称】：投诉案例测试

### 案件背景事实材料
【文件来源: 案例一投诉人基本资料】
投诉人：张三，联系电话：13800138000，身份证：110101199001011234，住址：北京市朝阳区某某街道123号。是否同意公示投诉信息：是。是否同意委托调解：否。
被投诉人：某某科技有限公司，联系人：李四，地址：上海市浦东新区某某路456号，联系电话：13900139000。

【文件来源: 案例一注册商标专用权】
消费者权益争议事实依据：消费者于2026年05月15日在某某科技有限公司购买了一台笔记本电脑，价格为5000元。电脑在保修期内出现屏幕黑屏故障，经多次维修未果，双方产生争议。
"""

    prompt = f"""你是一个智能文档填表专家。你的任务是直接在给定的 HTML 模板中，将空白单元格或下划线占位符替换为对应的背景信息，并返回填充修改后的 HTML。

### 背景事实材料及系统环境上下文
{context_str}

### 待填充的 HTML 模板
{template_html}

### 填表要求：
1. 必须原封不动地保留输入模板中的所有 HTML 标签、属性及内联样式，只在空白单元格（如空的 td）或下划线占位符（如“______”）处填充上对应的真实事实。
2. 单元格内原有的固定字段文字（例如“姓名”、“联系电话”等）绝对不能修改或删除。
3. 绝对只能输出一份被填充修改后的完整 HTML 代码。严禁在输出中包含原有的空白模板，也严禁输出任何解释、分析、注意、说明或“```html”代码块包裹标记。

请直接输出替换后的完整 HTML：
"""

    print("--- Sending prompt ---")
    response_text = ""
    async for chunk in stream_ollama(prompt, model=settings.DEFAULT_LLM_MODEL, temperature=0.2, num_ctx=16384, num_predict=8192):
        response_text += chunk
        
    print("=== Raw Model Response ===")
    print(response_text)
    print("==========================")
        
if __name__ == "__main__":
    asyncio.run(test())
