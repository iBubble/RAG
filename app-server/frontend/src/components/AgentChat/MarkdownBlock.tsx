/**
 * MarkdownBlock — 将 Markdown 文本渲染为结构化 HTML。
 *
 * WHY: AgentChat 之前直接用 whitespace-pre-wrap 渲染纯文本，
 *      导致 LLM 输出的 Markdown 标记（##、**粗体**、- 列表）
 *      全部显示为原始符号，用户看到的是一坨不可读的文字墙。
 *
 * 设计决策：
 * 1. 使用 useState + useEffect + async import 模式（与 DocumentStudio 一致）
 *    以兼容 marked.parse() 可能返回 Promise 的版本。
 * 2. CSS 样式用组件内 <style> 标签注入，避免被 Tailwind v4 tree-shaking 删除。
 */
import { useState, useEffect, useRef } from 'react';

interface MarkdownBlockProps {
  content: string;
}

// WHY: 全局只注入一次 CSS，避免每个 MarkdownBlock 实例重复创建 <style>
let _styleInjected = false;
const STYLE_CSS = `
.md-render { line-height: 1.7; word-break: break-word; }
.md-render h1,.md-render h2,.md-render h3,.md-render h4 {
  font-weight: 700; color: #1F2937; margin-top: 14px; margin-bottom: 6px; line-height: 1.4;
}
.md-render h1 { font-size: 18px; }
.md-render h2 { font-size: 16px; border-bottom: 1px solid #E5E7EB; padding-bottom: 4px; }
.md-render h3 { font-size: 14px; color: #374151; }
.md-render h4 { font-size: 13px; color: #4B5563; }
.md-render p { text-indent: 2em; text-align: justify; margin: 12px 0; color: #374151; line-height: 1.8; }
.md-render strong { font-weight: 700; color: #111827; }
.md-render em { font-style: italic; color: #4B5563; }
.md-render ul { list-style-type: disc; padding-left: 22px; margin: 6px 0; }
.md-render ol { list-style-type: decimal; padding-left: 22px; margin: 6px 0; }
.md-render li { margin: 3px 0; color: #374151; line-height: 1.7; }
.md-render li > ul,.md-render li > ol { margin: 2px 0; }
.md-render blockquote {
  border-left: 3px solid #818CF8; background: #F0F4FF;
  padding: 6px 12px; margin: 8px 0; border-radius: 0 6px 6px 0; color: #4B5563;
}
.md-render code {
  background: #EEF2FF; color: #4338CA; padding: 1px 4px;
  border-radius: 3px; font-size: 0.9em;
}
.md-render pre {
  background: #1F2937; color: #E5E7EB; padding: 10px 14px;
  border-radius: 8px; overflow-x: auto; margin: 8px 0; font-size: 13px;
}
.md-render pre code { background: transparent; color: inherit; padding: 0; }
.md-render hr { border: none; border-top: 1px solid #E5E7EB; margin: 12px 0; }
.md-render a { color: #4F46E5; text-decoration: none; }
.md-render a:hover { text-decoration: underline; }
.md-render table { border-collapse: collapse; width: 100%; margin: 8px 0; font-size: 13px; }
.md-render th,.md-render td { border: 1px solid #E5E7EB; padding: 5px 8px; text-align: left; }
.md-render th { background: #F3F4F6; font-weight: 600; }

[data-mode="dark"] .md-render h1,
[data-mode="dark"] .md-render h2,
[data-mode="dark"] .md-render h3,
[data-mode="dark"] .md-render h4,
[data-mode="dark"] .md-render p,
[data-mode="dark"] .md-render li {
  color: var(--text-main);
}
[data-mode="dark"] .md-render h2,
[data-mode="dark"] .md-render hr,
[data-mode="dark"] .md-render table,
[data-mode="dark"] .md-render th,
[data-mode="dark"] .md-render td {
  border-color: var(--border-soft);
}
[data-mode="dark"] .md-render strong {
  color: #FFFFFF;
}
[data-mode="dark"] .md-render em {
  color: var(--text-muted);
}
[data-mode="dark"] .md-render blockquote {
  background: var(--outline-bg);
  color: var(--text-main);
}
[data-mode="dark"] .md-render code {
  background: var(--outline-bg);
  color: var(--text-main);
}
[data-mode="dark"] .md-render th {
  background: var(--outline-bg);
}
`;

function injectStyle() {
  if (_styleInjected) return;
  const tag = document.createElement('style');
  tag.textContent = STYLE_CSS;
  document.head.appendChild(tag);
  _styleInjected = true;
}

export default function MarkdownBlock({ content }: MarkdownBlockProps) {
  const [html, setHtml] = useState('');
  const mountedRef = useRef(true);

  useEffect(() => {
    injectStyle();
    mountedRef.current = true;
    return () => { mountedRef.current = false; };
  }, []);

  useEffect(() => {
    if (!content) { setHtml(''); return; }

    (async () => {
      try {
        const { marked } = await import('marked');
        const DOMPurify = (await import('dompurify')).default;
        marked.setOptions({ breaks: true, gfm: true });

        // WHY: LLM 经常输出不规范 Markdown：
        //   1. 换行符可能因 SSE 传输或模型输出不连贯导致挤在同一行
        //   2. "##标题" 缺少 # 后的空格 → marked 不识别为标题
        //   3. 标题、无序列表（-/*）、有序列表（1.）前缺少空行，且可能没有换行直接与前文相连
        //   4. 有序列表点号后缺少空格（"1.标题" -> "1. 标题"）
        //   5. 清理每段行首的冗余全角/半角空格防止与 CSS text-indent 缩进叠加
        let normalized = content
          // 1) 仅清除普通文本段落行首的冗余全角/半角空格，防止与 CSS text-indent 缩进叠加，不误伤列表缩进
          .replace(/^[ 　]{1,4}(?=[^#\-\*\+\d\s])/gm, '')
          // 2) 如果标题、列表项前只有单个换行符，自动补齐为双换行符以符合标准段落分割
          .replace(/([^\n])\n(#{1,6}\s)/g, '$1\n\n$2')
          .replace(/([^\n])\n([-*+]\s)/g, '$1\n\n$2')
          .replace(/([^\n])\n(\d+\.\s)/g, '$1\n\n$2')
          // 3) 如果标题、列表项前完全没有换行符，强行补齐双换行符以实现新段落
          .replace(/([^\n])(#{1,6})/g, '$1\n\n$2')
          .replace(/([^\n])(\s*[-*+]\s)/g, '$1\n\n$2')
          .replace(/([^\n])(\s*\d+\.\s)/g, '$1\n\n$2')
          // 4) 确保标题 # 后有空格（如 "##标题" -> "## 标题"）
          .replace(/^(#{1,6})([^\s#])/gm, '$1 $2')
          // 5) 确保有序列表点号后有空格（如 "1.标题" -> "1. 标题"）
          .replace(/(\d+)\.([^\s\d])/g, '$1. $2');

        const rawHtml = await marked.parse(normalized);
        if (mountedRef.current) {
          setHtml(DOMPurify.sanitize(rawHtml));
        }
      } catch (err) {
        console.error('[MarkdownBlock] 解析失败:', err);
        if (mountedRef.current) {
          // 降级：转义后显示纯文本
          const escaped = content
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/\n/g, '<br/>');
          setHtml(escaped);
        }
      }
    })();
  }, [content]);

  if (!html) {
    return <div className="whitespace-pre-wrap">{content}</div>;
  }

  return (
    <div className="md-render" dangerouslySetInnerHTML={{ __html: html }} />
  );
}
