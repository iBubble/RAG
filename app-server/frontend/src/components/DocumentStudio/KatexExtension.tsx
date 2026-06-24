/**
 * KatexExtension.tsx — Tiptap 扩展：LaTeX 公式渲染
 *
 * WHY: LLM 生成的技术报告包含 $...$ 行内公式和 $$...$$ 独立公式。
 *      此扩展在 Tiptap 编辑器中将 LaTeX 语法渲染为可视化数学公式。
 *
 * 实现策略：使用 Tiptap Node Extension 创建两种节点类型：
 *   1. inlineMath: 行内公式 $...$
 *   2. blockMath: 独立公式 $$...$$
 *
 * 渲染采用 KaTeX 库，轻量且不依赖外部服务。
 */
import { Node, mergeAttributes } from '@tiptap/react';
import katex from 'katex';

/**
 * 行内数学公式节点 — 匹配 $...$ 并用 KaTeX 渲染。
 */
export const InlineMath = Node.create({
  name: 'inlineMath',
  group: 'inline',
  inline: true,
  atom: true,

  addAttributes() {
    return {
      latex: { default: '' },
    };
  },

  parseHTML() {
    return [{ tag: 'span[data-latex]' }];
  },

  renderHTML({ HTMLAttributes }) {
    const latex = HTMLAttributes.latex || '';
    let rendered = '';
    try {
      rendered = katex.renderToString(latex, {
        throwOnError: false,
        displayMode: false,
      });
    } catch {
      rendered = `<code>${latex}</code>`;
    }
    return [
      'span',
      mergeAttributes(HTMLAttributes, {
        'data-latex': latex,
        class: 'katex-inline',
      }),
      rendered,
    ];
  },
});

/**
 * 块级数学公式节点 — 匹配 $$...$$ 并用 KaTeX 渲染。
 */
export const BlockMath = Node.create({
  name: 'blockMath',
  group: 'block',
  atom: true,

  addAttributes() {
    return {
      latex: { default: '' },
    };
  },

  parseHTML() {
    return [{ tag: 'div[data-latex]' }];
  },

  renderHTML({ HTMLAttributes }) {
    const latex = HTMLAttributes.latex || '';
    let rendered = '';
    try {
      rendered = katex.renderToString(latex, {
        throwOnError: false,
        displayMode: true,
      });
    } catch {
      rendered = `<pre>${latex}</pre>`;
    }
    return [
      'div',
      mergeAttributes(HTMLAttributes, {
        'data-latex': latex,
        class: 'katex-block',
      }),
      rendered,
    ];
  },
});

/**
 * 将原始 Markdown/HTML 文本中的 LaTeX 公式转为 KaTeX HTML。
 *
 * WHY: SSE 流式接收和 marked.parse 输出的文本中，LaTeX 公式仍为
 *      纯文本 $...$ 或 $$...$$。此函数将其转换为 KaTeX 渲染后的 HTML，
 *      供 Tiptap setContent 和静态 HTML 渲染使用。
 *
 * 处理顺序：先处理 $$...$$ (块级)，再处理 $...$ (行内)，
 * 避免行内匹配误伤块级公式。
 */
export function renderLatexInHtml(html: string): string {
  if (!html) return html;

  // 先处理块级公式 $$...$$
  // WHY: 使用非贪婪匹配 [\s\S]*? 支持多行公式
  let result = html.replace(
    /\$\$([\s\S]*?)\$\$/g,
    (_match, latex: string) => {
      try {
        const rendered = katex.renderToString(latex.trim(), {
          throwOnError: false,
          displayMode: true,
        });
        return `<div class="katex-block" data-latex="${encodeURIComponent(latex.trim())}">${rendered}</div>`;
      } catch {
        return `<pre class="katex-error">${latex}</pre>`;
      }
    }
  );

  // 再处理行内公式 $...$
  // WHY: 排除已被块级处理的 $$，排除货币符号（$后紧跟数字无空格的情况通过前瞻处理）
  //      使用负向前瞻 (?!\$) 确保不匹配 $$ 的第二个 $
  result = result.replace(
    /(?<!\$)\$(?!\$)((?:[^$\\]|\\.)+?)\$/g,
    (_match, latex: string) => {
      // WHY: 纯数字（如 "$100"）不是公式，跳过
      if (/^\d+([.,]\d+)?$/.test(latex.trim())) return _match;
      try {
        const rendered = katex.renderToString(latex.trim(), {
          throwOnError: false,
          displayMode: false,
        });
        return `<span class="katex-inline" data-latex="${encodeURIComponent(latex.trim())}">${rendered}</span>`;
      } catch {
        return `<code class="katex-error">${latex}</code>`;
      }
    }
  );

  return result;
}
