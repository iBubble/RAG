/**
 * MermaidExtension.tsx — Tiptap Mermaid CodeBlock 扩展
 * 
 * WHY: 使用 .tsx 后缀以支持 JSX 语法。
 *      检测 language=mermaid 的 CodeBlock 并用 MermaidBlock 可视化组件替换。
 */
import { Node, mergeAttributes } from '@tiptap/core';
import { ReactNodeViewRenderer, NodeViewWrapper } from '@tiptap/react';
import { useCallback } from 'react';
import MermaidBlock from './MermaidBlock';

// WHY: Tiptap NodeView 组件 — 包装 MermaidBlock，桥接 Tiptap 节点数据
function MermaidNodeView({ node, updateAttributes, editor }: any) {
  const code = node.textContent || '';
  const readOnly = !editor.isEditable;

  const handleChange = useCallback((newCode: string) => {
    // WHY: 通过 commands 替换 CodeBlock 内容而非直接操作 DOM
    // 简化方案：存储到 attribute，由 onUpdate 回调处理
    updateAttributes({ mermaidCode: newCode });
  }, [updateAttributes]);

  return (
    <NodeViewWrapper className="mermaid-node-wrapper">
      <MermaidBlock code={code} onChange={handleChange} readOnly={readOnly} />
    </NodeViewWrapper>
  );
}

// WHY: 自定义 Mermaid 节点 — 复用 codeBlock 语义但使用自定义 NodeView 渲染
const MermaidExtension = Node.create({
  name: 'mermaidBlock',
  group: 'block',
  content: 'text*',
  marks: '',
  code: true,
  defining: true,

  addAttributes() {
    return {
      language: {
        default: 'mermaid',
      },
      mermaidCode: {
        default: null,
      },
    };
  },

  parseHTML() {
    return [
      {
        tag: 'pre',
        preserveWhitespace: 'full' as const,
        getAttrs: (element: HTMLElement) => {
          const code = element.querySelector('code');
          if (!code) return false;
          const lang = code.getAttribute('class')?.replace('language-', '') || '';
          if (lang !== 'mermaid') return false;
          return { language: 'mermaid' };
        },
      },
    ];
  },

  renderHTML({ HTMLAttributes }) {
    return [
      'pre',
      mergeAttributes(HTMLAttributes),
      ['code', { class: 'language-mermaid' }, 0],
    ];
  },

  addNodeView() {
    return ReactNodeViewRenderer(MermaidNodeView);
  },
});

export default MermaidExtension;
