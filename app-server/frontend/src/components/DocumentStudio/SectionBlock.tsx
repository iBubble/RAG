/**
 * SectionBlock.tsx — 单章节编辑器组件（仅在激活时挂载）
 *
 * WHY: 虚拟化架构下此组件只在 isActive=true 时才被 mount。
 *      非激活章节由父组件用 StaticSectionView 渲染静态 HTML。
 *      这确保同时只有 1 个 Tiptap 编辑器实例，彻底解决 207 个
 *      编辑器撑爆 Chrome 渲染进程内存的问题。
 *
 * 通过 forwardRef + useImperativeHandle 向父组件暴露 generate / clear / fillContent 方法。
 */
import React, { useState, useEffect, useRef, forwardRef, useImperativeHandle } from 'react';
import { createPortal } from 'react-dom';
import { Wand2, Rocket, Trash2, ChevronDown, Square, Copy, Paperclip, AlertTriangle } from 'lucide-react';
import { useEditor, EditorContent } from '@tiptap/react';
import StarterKit from '@tiptap/starter-kit';
import { Table } from '@tiptap/extension-table';
import { TableRow } from '@tiptap/extension-table-row';
import { TableCell } from '@tiptap/extension-table-cell';
import { TableHeader } from '@tiptap/extension-table-header';
import Placeholder from '@tiptap/extension-placeholder';
import MermaidExtension from './MermaidExtension';
import { InlineMath, BlockMath } from './KatexExtension';
import 'katex/dist/katex.min.css';
import { useProjectStore } from '../../store/projectStore';
import { SmartChartRenderer } from './MorandiCharts';
import type { DocSection, SectionBlockHandle } from './types';

interface SectionBlockProps {
  section: DocSection;
  isActive: boolean;
  onSaveContent: (id: string, text: string) => void;
  onGenerate: (section: DocSection, editor: any, mode?: string) => void;
  onActivate: () => void;
  onStopGenerate: () => void;
  hasExemplar?: boolean;
}

const SectionBlock = forwardRef<SectionBlockHandle, SectionBlockProps>(({
  section,
  // WHY: isActive 不在组件内使用（此组件只在激活时挂载），但保留 props 接口兼容性
  isActive: _isActive,
  onSaveContent,
  onGenerate,
  onActivate,
  onStopGenerate,
  hasExemplar = false
}, ref) => {
  const [isGenerating, setIsGenerating] = useState(false);
  const [showModeMenu, setShowModeMenu] = useState(false);
  const [showClearConfirm, setShowClearConfirm] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);
  const lastUpdateRef = useRef<number>(0);
  const saveTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // WHY: 点击外部关闭下拉菜单
  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) {
        setShowModeMenu(false);
      }
    };
    if (showModeMenu) document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, [showModeMenu]);

  const editor = useEditor({
    extensions: [
      StarterKit.configure({ codeBlock: false }),
      MermaidExtension,
      InlineMath,
      BlockMath,
      Table.configure({ resizable: true }),
      TableRow,
      TableHeader,
      TableCell,
      Placeholder.configure({ placeholder: '请输入或智能编写...' })
    ],
    content: section.content,
    immediatelyRender: false,
    onUpdate: ({ editor }) => {
      const now = Date.now();
      const text = editor.getHTML();

      if (saveTimeoutRef.current) clearTimeout(saveTimeoutRef.current);
      if (now - lastUpdateRef.current > 800) {
        onSaveContent(section.id, text);
        lastUpdateRef.current = now;
      } else {
        saveTimeoutRef.current = setTimeout(() => {
          onSaveContent(section.id, text);
          lastUpdateRef.current = Date.now();
        }, 800);
      }
    },
    editorProps: {
      attributes: {
        class: 'prose prose-sm xl:prose-base focus:outline-none min-h-[50px] text-gray-700 font-light',
      },
    },
  });

  // WHY: 当 store content 变化时（如"一键清除"），同步到编辑器。
  //      isGenerating 守卫防止生成过程中竞态吞字。
  useEffect(() => {
    if (!editor || isGenerating) return;
    const editorPlain = editor.getHTML().replace(/<[^>]*>?/gm, '').trim();
    const storePlain = (section.content || '').replace(/<[^>]*>?/gm, '').trim();
    if (editorPlain !== storePlain) {
      if (storePlain.length === 0) {
        editor.commands.clearContent(false);
      } else {
        editor.commands.setContent(section.content, { emitUpdate: false });
      }
    }
  }, [section.content, editor, isGenerating]);

  const handleGenerateClick = async (e?: React.MouseEvent, mode?: string) => {
    if (e) e.stopPropagation();
    if (isGenerating) return;
    setIsGenerating(true);
    setShowModeMenu(false);
    try {
      await onGenerate(section, editor, mode);
    } finally {
      // WHY: 延迟 100ms，等待 React props 更新分发完毕后，再将 isGenerating 设为 false
      await new Promise(r => setTimeout(r, 100));
      setIsGenerating(false);
    }
  };

  const handleStopClick = (e: React.MouseEvent) => {
    e.stopPropagation();
    onStopGenerate();
  };

  useImperativeHandle(ref, () => ({
    generate: async (mode?: string) => {
      onActivate();
      await new Promise(r => requestAnimationFrame(() => setTimeout(r, 50)));
      await handleGenerateClick(undefined, mode);
    },
    clear: () => {
      if (editor) {
        editor.commands.clearContent(true);
        const { updateSectionSources } = useProjectStore.getState();
        updateSectionSources(section.id, []);
      }
    },
    fillContent: (_html: string, _sources?: string[]) => {
      // WHY: 虚拟化架构下批量填充由 setTemplateData 完成。
      //      如果当前章节恰好是激活的，useEffect 会自动同步。
    }
  }), [editor, section, isGenerating, onGenerate, onActivate]);

  return (
    <div
      className={`mb-8 bg-gray-50/80 dark:bg-panel-bg rounded-lg p-5 -ml-5 ring-1 ring-gray-100 dark:ring-border-soft shadow-sm relative group transition-all`}
      id={`sec-${section.id}`}
      onClick={onActivate}
    >
      <h3 className={`font-bold flex items-center gap-3 text-gray-900 dark:text-text-main mb-3 ${section.level === 1 ? 'text-xl' : 'text-base'}`}>
        {section.title}
        {isGenerating ? (
          <button
            onClick={handleStopClick}
            className="flex items-center gap-1.5 text-[13px] font-medium text-red-600 bg-red-50/80 px-3 py-1 rounded-md border border-red-200 hover:bg-red-100/80 transition-all shadow-sm">
            <Square className="w-3 h-3 fill-red-500" />
            停止生成
          </button>
        ) : (
          <div className="relative flex items-center gap-1.5" ref={menuRef}>
            <button
              onClick={(e) => {
                e.stopPropagation();
                setShowClearConfirm(true);
              }}
              className="flex items-center gap-1.5 text-[13px] font-medium text-gray-500 bg-gray-50/80 px-2 py-1 rounded-md border border-gray-200 hover:bg-gray-100/80 transition-all shadow-sm"
              title="清除本节内容">
              <Trash2 className="w-3.5 h-3.5" />
            </button>
            <div className="flex items-center">
              <button
                onClick={handleGenerateClick}
                className="flex items-center gap-1.5 text-[13px] font-medium text-indigo-600 bg-indigo-50/80 px-3 py-1 rounded-l-md border border-indigo-100 hover:bg-indigo-100/80 transition-all shadow-sm">
                <Rocket className="w-3.5 h-3.5" />
                智能编写
              </button>
              <button
                onClick={(e) => { e.stopPropagation(); setShowModeMenu(!showModeMenu); }}
                className="flex items-center text-[13px] font-medium text-indigo-600 bg-indigo-50/80 px-1.5 py-1 rounded-r-md border border-l-0 border-indigo-100 hover:bg-indigo-100/80 transition-all shadow-sm">
                <ChevronDown className="w-3.5 h-3.5" />
              </button>
            </div>
            {showModeMenu && (
              <div className="absolute left-0 top-full mt-1 bg-white rounded-lg shadow-lg border border-gray-200 py-1 z-50 min-w-[180px]">
                <button onClick={(e) => handleGenerateClick(e, 'generate')}
                  className="w-full text-left px-3 py-2 text-sm text-gray-700 hover:bg-indigo-50 flex items-center gap-2">
                  <Wand2 className="w-3.5 h-3.5 text-purple-500" /> AI 自由生成
                </button>
                <button onClick={(e) => handleGenerateClick(e, 'replace')}
                  disabled={!hasExemplar}
                  className="w-full text-left px-3 py-2 text-sm text-gray-700 hover:bg-teal-50 flex items-center gap-2 disabled:opacity-40 disabled:cursor-not-allowed">
                  🔄 智能替换
                </button>
                <button onClick={(e) => handleGenerateClick(e, 'clone')}
                  disabled={!hasExemplar}
                  className="w-full text-left px-3 py-2 text-sm text-gray-700 hover:bg-amber-50 flex items-center gap-2 disabled:opacity-40 disabled:cursor-not-allowed">
                  <Copy className="w-3.5 h-3.5 text-amber-600" /> 精确复刻
                </button>
              </div>
            )}
          </div>
        )}
      </h3>

      <div className="pl-2">
        <div className="tiptap-wrapper min-h-[50px]">
          <EditorContent editor={editor} />
        </div>
        <div className="chart-renderer-wrapper">
          <SmartChartRenderer htmlContent={section.content} />
        </div>
        {section.sources && section.sources.length > 0 && (
          <div className="mt-3 flex flex-wrap gap-2 pt-3 border-t border-gray-100/60">
            {section.sources.map((src, i) => (
              <span key={i} className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md bg-blue-50/80 text-blue-700 text-[11px] font-medium border border-blue-100 shadow-sm" title={`参考资料: ${src}`}>
                <Paperclip className="w-3 h-3 text-blue-500" />
                {src}
              </span>
            ))}
          </div>
        )}
        
        {showClearConfirm && createPortal(
          <div className="fixed inset-0 z-[9999] flex items-center justify-center p-4 select-none" onClick={e => e.stopPropagation()}>
            <div 
              className="absolute inset-0 bg-[#0F0F11]/45 backdrop-blur-[2px] transition-opacity" 
              onClick={() => setShowClearConfirm(false)}
            />
            <div className="relative bg-white dark:bg-[#1E1F22] rounded-xl p-5 shadow-2xl border border-stone-200 dark:border-stone-850 max-w-sm w-full flex flex-col gap-4 animate-in fade-in zoom-in-95 duration-200">
              <div className="flex items-start gap-3 text-stone-800 dark:text-stone-200">
                <div className="p-2.5 rounded-full bg-red-50 dark:bg-red-950/20 text-red-600 dark:text-red-400 shrink-0">
                  <AlertTriangle className="w-5 h-5" />
                </div>
                <div className="flex flex-col gap-1 min-w-0">
                  <h3 className="text-sm font-bold text-stone-900 dark:text-stone-100">
                    🗑️ 清空章节正文
                  </h3>
                  <p className="text-xs text-stone-500 dark:text-stone-400 leading-normal mt-3 whitespace-pre-wrap font-sans">
                    确定清除此章节所有的正文内容吗？清除后无法恢复。
                  </p>
                </div>
              </div>
              <div className="flex justify-end gap-2 mt-2">
                <button
                  onClick={() => setShowClearConfirm(false)}
                  className="px-4 py-1.5 text-xs font-semibold text-stone-600 dark:text-stone-300 hover:text-stone-800 dark:hover:text-stone-100 hover:bg-stone-50 dark:hover:bg-stone-800 rounded-lg transition-colors border border-stone-200 dark:border-stone-700 cursor-pointer"
                >
                  取消
                </button>
                <button
                  onClick={() => {
                    editor?.commands.clearContent(true);
                    const { updateSectionSources } = useProjectStore.getState();
                    updateSectionSources(section.id, []);
                    setShowClearConfirm(false);
                  }}
                  className="px-4 py-1.5 text-xs font-semibold text-white bg-red-600 hover:bg-red-700 active:scale-95 rounded-lg transition-all shadow-sm cursor-pointer"
                >
                  确认清除
                </button>
              </div>
            </div>
          </div>,
          document.body
        )}
      </div>
    </div>
  )
});

SectionBlock.displayName = 'SectionBlock';

export default SectionBlock;
