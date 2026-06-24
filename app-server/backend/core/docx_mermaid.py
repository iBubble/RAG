"""
Mermaid 图表转 PNG 渲染模块。
WHY: Word 文档不支持 SVG 或 Mermaid 语法，需要将 Mermaid 代码块
     渲染为 PNG 图片后嵌入 DOCX。

策略（按优先级降序）：
1. 使用 mermaid.ink 在线 API（免费、无需本地依赖、ARM 兼容）
2. 降级为纯文本代码块插入 Word
"""
import os
import re
import uuid
import base64
import logging
import tempfile
import urllib.parse
import urllib.request

logger = logging.getLogger(__name__)

# WHY: 检测 Mermaid 代码块的正则
MERMAID_BLOCK_RE = re.compile(r'```mermaid\s*\n(.*?)```', re.DOTALL)


def render_mermaid_to_png(mermaid_code: str) -> str | None:
    """
    将 Mermaid 代码渲染为 PNG 图片。
    返回临时 PNG 文件路径，调用方负责清理。失败时返回 None。

    WHY: 使用 mermaid.ink API 而非本地 mmdc，因为：
         1. OrbStack ARM64 容器无法运行 Puppeteer/Chromium（架构不兼容）
         2. mermaid.ink 免费、无需安装、支持所有图表类型
         3. 渲染质量与官方 Mermaid Live Editor 完全一致
    """
    if not mermaid_code or not mermaid_code.strip():
        return None

    try:
        # WHY: mermaid.ink API 接受 base64 编码的 Mermaid 代码
        #       URL 格式: https://mermaid.ink/img/{base64_code}?type=png&bgColor=white
        encoded = base64.urlsafe_b64encode(
            mermaid_code.strip().encode('utf-8')
        ).decode('ascii')

        url = f"https://mermaid.ink/img/{encoded}?type=png&bgColor=white"

        tmp_dir = tempfile.gettempdir()
        output_path = os.path.join(tmp_dir, f"mermaid_{uuid.uuid4().hex[:8]}.png")

        # WHY: 使用 urllib 而非 httpx/requests，避免引入额外异步依赖
        req = urllib.request.Request(url, headers={
            'User-Agent': 'ShengyaoRAG-DocExport/1.0',
        })
        with urllib.request.urlopen(req, timeout=15) as response:
            data = response.read()

        if len(data) < 100:
            logger.error(f"mermaid.ink 返回数据异常（{len(data)} bytes）")
            return None

        with open(output_path, 'wb') as f:
            f.write(data)

        logger.info(f"Mermaid 渲染成功 (mermaid.ink): {output_path} ({len(data)} bytes)")
        return output_path

    except urllib.error.URLError as exc:
        logger.error(f"mermaid.ink API 请求失败: {exc}")
        return None
    except Exception as exc:
        logger.error(f"Mermaid 渲染异常: {exc}")
        return None


def extract_mermaid_blocks(content: str) -> list[tuple[str, str]]:
    """
    从 HTML/Markdown 混合内容中提取所有 Mermaid 代码块。
    返回 [(原始匹配文本, Mermaid代码), ...] 列表。
    """
    results = []
    for match in MERMAID_BLOCK_RE.finditer(content):
        results.append((match.group(0), match.group(1).strip()))
    return results
