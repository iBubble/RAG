import { useEffect } from 'react';
import { marked } from 'marked';
import DOMPurify from 'dompurify';

interface MarkdownBlockProps {
  content: string;
  isStreaming?: boolean;
}

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

function normalizeMarkdown(text: string): string {
  return text
    .replace(/^[ 　]{1,4}(?=[^#\-\*\+\d\s])/gm, '')
    .replace(/([^\n])\n(#{1,6}\s)/g, '$1\n\n$2')
    .replace(/([^\n])\n([-*+]\s)/g, '$1\n\n$2')
    .replace(/([^\n])\n(\d+\.\s)/g, '$1\n\n$2')
    .replace(/([^\n])(#{1,6})/g, '$1\n\n$2')
    .replace(/([^\n])(\s*[-*+]\s)/g, '$1\n\n$2')
    .replace(/([^\n])(\s*\d+\.\s)/g, '$1\n\n$2')
    .replace(/^(#{1,6})([^\s#])/gm, '$1 $2')
    .replace(/(\d+)\.([^\s\d])/g, '$1. $2');
}

export default function MarkdownBlock({ content, isStreaming }: MarkdownBlockProps) {
  useEffect(() => {
    injectStyle();
  }, []);

  if (!content) {
    return <div className="whitespace-pre-wrap" />;
  }

  // 🌟 终极安全与性能优化：流式传输期间（生成中），直接以纯文本格式（保留换行）安全渲染。
  //    这能绝对避免由于模型输出的一半 HTML 标签未闭合或代码格式破损传入 dangerouslySetInnerHTML 
  //    从而导致浏览器内核为修正 DOM 树结构发生严重死循环或崩溃（STATUS_BREAKPOINT / OOM Error 5）。
  if (isStreaming) {
    return (
      <div className="whitespace-pre-wrap break-words leading-relaxed text-gray-700 dark:text-stone-300 font-sans">
        {content}
      </div>
    );
  }

  try {
    marked.setOptions({ breaks: true, gfm: true });
    const normalized = normalizeMarkdown(content);
    const rawHtml = marked.parse(normalized) as string;
    const cleanHtml = DOMPurify.sanitize(rawHtml);
    return (
      <div className="md-render" dangerouslySetInnerHTML={{ __html: cleanHtml }} />
    );
  } catch (err) {
    console.error('[MarkdownBlock] 解析渲染失败:', err);
    const escaped = content
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/\n/g, '<br/>');
    return <div className="md-render" dangerouslySetInnerHTML={{ __html: escaped }} />;
  }
}
