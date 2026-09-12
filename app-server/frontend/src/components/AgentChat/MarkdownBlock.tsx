import { useEffect, useRef } from 'react';
import { marked } from 'marked';
import DOMPurify from 'dompurify';

export interface CitationInfo {
  raw: string;
  text: string;
  law: string;
  section: string;
}

interface MarkdownBlockProps {
  content: string;
  isStreaming?: boolean;
  onCitationHover?: (info: CitationInfo | null, rect?: DOMRect) => void;
  onCitationClick?: (info: CitationInfo) => void;
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

/* 🏛️ 法条与公共文档斜体高亮交互样式 */
.legal-citation {
  display: inline-flex !important;
  align-items: baseline !important;
  font-style: italic !important;
  font-weight: 600 !important;
  color: #4f46e5 !important;
  background-color: rgba(99, 102, 241, 0.08) !important;
  border-bottom: 1.5px dashed #6366f1 !important;
  padding: 0 5px !important;
  margin: 0 2px !important;
  border-radius: 4px !important;
  cursor: pointer !important;
  text-indent: 0 !important;
  transition: all 0.2s ease !important;
  user-select: text !important;
}
.legal-citation:hover {
  background-color: rgba(99, 102, 241, 0.18) !important;
  color: #312e81 !important;
  border-bottom-style: solid !important;
  transform: translateY(-1px) !important;
  box-shadow: 0 2px 5px rgba(99, 102, 241, 0.15) !important;
}

[data-mode="dark"] .legal-citation {
  color: #a5b4fc !important;
  background-color: rgba(99, 102, 241, 0.2) !important;
  border-bottom-color: #818cf8 !important;
}
[data-mode="dark"] .legal-citation:hover {
  color: #e0e7ff !important;
  background-color: rgba(99, 102, 241, 0.35) !important;
  box-shadow: 0 2px 6px rgba(0, 0, 0, 0.4) !important;
}

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
  if (!text) return text;
  // 1. 强力消除在中文中括号 【...】 内部产生的非预期断行和空格，保持引用的整体连贯性
  let cleaned = text.replace(/【([^】]+)】/g, (_, p1) => {
    return '【' + p1.replace(/[\r\n]+/g, '').replace(/\s+/g, '') + '】';
  });
  // 2. 强力消除在英文中括号 [...] 内部产生的非预期断行和空格（排除 markdown 链接图片，只针对普通引用）
  cleaned = cleaned.replace(/\[([^\]\(\)]+)\]/g, (_, p1) => {
    return '[' + p1.replace(/[\r\n]+/g, '').replace(/\s+/g, '') + ']';
  });

  // 3. 规范化星号包围的法条引用：消除 * 与 《 之间，以及条文与结束 * 之间的意外空格
  // 例如：* 《中华人民共和国商标法》第六十条* -> *《中华人民共和国商标法》第六十条*
  cleaned = cleaned.replace(/\*\s*(《[^》\n\r]+》[^\n\*]*?)\s*\*/g, '*$1*');
  // 4. 将连续两个相邻的斜体法条合并（如 *《法条》* *第X条* -> *《法条》第X条*）
  cleaned = cleaned.replace(/\*(《[^》\n\r]+》)\*\s*\*(第[^\n\*]+?)\*/g, '*$1$2*');

  return cleaned
    .replace(/^[ 　]{1,4}(?=[^#\-\*\+\d\s])/gm, '')
    .replace(/([^\n])\n(#{1,6}\s)/g, '$1\n\n$2')
    .replace(/([^\n])\n([-*+]\s)/g, '$1\n\n$2')
    .replace(/([^\n])\n(\d+\.\s)/g, '$1\n\n$2')
    .replace(/([^\n])(\s*[-*+]\s)/g, '$1\n\n$2')
    .replace(/([^\n])(\s*\d+\.\s)/g, '$1\n\n$2')
    .replace(/^(#{1,6})([^\s#])/gm, '$1 $2')
    .replace(/(\d+)\.([^\s\d])/g, '$1. $2');
}

function enhanceCitationsInHtml(html: string): string {
  if (!html) return html;

  // 1. 优先处理已经被 marked 解析为 <em> 的法条：<em>《法规名》具体章节条目</em>，兼容吞并紧随其后被截断的条文
  html = html.replace(/<em>\s*(《([^》]+)》([^<]*?))\s*<\/em>(\s*(?:第?[0-9一二三四五六七八九十百千万]+[条章节款项目录]+(?:第[（(]?[0-9一二三四五六七八九十]+[）)]?款)?(?:第[（(]?[0-9一二三四五六七八九十]+[）)]?项)?))?/g, (_match, _fullText, lawName, sectionPart, overflowSec) => {
    const cleanLaw = (lawName || '').trim();
    const cleanSec = ((sectionPart || '') + (overflowSec || '')).trim();
    const citationText = `《${cleanLaw}》${cleanSec}`;
    return `<span class="legal-citation" data-citation="${citationText}" data-law="${cleanLaw}" data-section="${cleanSec}" title="点击查看【${citationText}】条文全文">⚖️ <em>${citationText}</em></span>`;
  });

  // 2. 全局法条智能嗅探：处理未被 marked 解析为 <em> 的裸法条或带残余星号的法条
  // 将 HTML 按标签和文本进行分片，仅对文本部分进行法条匹配替换，避免破坏已有的 HTML 标签与属性
  const segments = html.split(/(<[^>]+>)/g);
  // 法规条文匹配正则：匹配形如 * 《商标法》第六十条* 或 《食品安全法》第一百二十四条第一款 等
  const LEGAL_REGEX = /(?:\*\s*)?《([^》\r\n]+)》(?:\s*(第[0-9一二三四五六七八九十百千万]+[条章节款项目录]+(?:之[一二三四五六七八九十]+)?(?:\s*第[0-9一二三四五六七八九十百千万]+[条章节款项目录]+)*(?:第[（(]?[0-9一二三四五六七八九十]+[）)]?款)?(?:第[（(]?[0-9一二三四五六七八九十]+[）)]?项)?))?(?:\s*\*+)?/g;

  for (let i = 0; i < segments.length; i++) {
    // 偶数索引是普通文本内容，奇数索引是 HTML 标签（如 <p>, <span> 等）
    if (i % 2 === 0 && segments[i]) {
      segments[i] = segments[i].replace(LEGAL_REGEX, (_m, lawName, secName) => {
        const cleanLaw = (lawName || '').trim();
        const cleanSec = (secName || '').trim();
        const citationText = `《${cleanLaw}》${cleanSec}`;
        return `<span class="legal-citation" data-citation="${citationText}" data-law="${cleanLaw}" data-section="${cleanSec}" title="点击查看【${citationText}】条文全文">⚖️ <em>${citationText}</em></span>`;
      });
    }
  }

  return segments.join('');
}

export default function MarkdownBlock({
  content,
  isStreaming,
  onCitationHover,
  onCitationClick,
}: MarkdownBlockProps) {
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    injectStyle();
  }, []);

  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;

    const handleMouseOver = (e: MouseEvent) => {
      const citationEl = (e.target as HTMLElement).closest('.legal-citation') as HTMLElement | null;
      if (citationEl) {
        const citation = citationEl.getAttribute('data-citation') || citationEl.innerText;
        const law = citationEl.getAttribute('data-law') || '';
        const section = citationEl.getAttribute('data-section') || '';
        const rect = citationEl.getBoundingClientRect();
        onCitationHover?.({ raw: citationEl.innerText, text: citation, law, section }, rect);
      }
    };

    const handleMouseOut = (e: MouseEvent) => {
      const citationEl = (e.target as HTMLElement).closest('.legal-citation') as HTMLElement | null;
      if (!citationEl) return;
      const related = e.relatedTarget as HTMLElement | null;
      // 若鼠标是移向该法条元素内部的子元素（如 <em>、文本等），不触发关闭
      if (related && citationEl.contains(related)) {
        return;
      }
      // 只要鼠标移出了当前法条，通知准备关闭浮窗
      onCitationHover?.(null);
    };

    const handleClick = (e: MouseEvent) => {
      const target = (e.target as HTMLElement).closest('.legal-citation') as HTMLElement;
      if (!target) return;
      e.preventDefault();
      e.stopPropagation();
      const citation = target.getAttribute('data-citation') || target.innerText;
      const law = target.getAttribute('data-law') || '';
      const section = target.getAttribute('data-section') || '';
      onCitationClick?.({ raw: target.innerText, text: citation, law, section });
    };

    el.addEventListener('mouseover', handleMouseOver);
    el.addEventListener('mouseout', handleMouseOut);
    el.addEventListener('click', handleClick);

    return () => {
      el.removeEventListener('mouseover', handleMouseOver);
      el.removeEventListener('mouseout', handleMouseOut);
      el.removeEventListener('click', handleClick);
    };
  }, [onCitationHover, onCitationClick]);

  if (!content) {
    return <div className="whitespace-pre-wrap" />;
  }

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
    const sanitizedHtml = DOMPurify.sanitize(rawHtml, {
      ADD_ATTR: ['data-citation', 'data-law', 'data-section', 'target'],
    });
    const enhancedHtml = enhanceCitationsInHtml(sanitizedHtml);

    return (
      <>
        <div className="debug-raw-content" style={{ display: 'none' }}>{content}</div>
        <div className="debug-normalized-content" style={{ display: 'none' }}>{normalized}</div>
        <div ref={containerRef} className="md-render" dangerouslySetInnerHTML={{ __html: enhancedHtml }} />
      </>
    );
  } catch (err) {
    console.error('[MarkdownBlock] 解析渲染失败:', err);
    const escaped = content
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/\n/g, '<br/>');
    return <div ref={containerRef} className="md-render" dangerouslySetInnerHTML={{ __html: escaped }} />;
  }
}
