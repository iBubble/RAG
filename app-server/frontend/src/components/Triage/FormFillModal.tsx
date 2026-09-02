import React, { useState, useEffect } from 'react';
import { 
  X, Save, Download, Printer, Sparkles, RotateCcw, 
  Loader2, CheckCircle2, FileText 
} from 'lucide-react';
import { useAuthStore } from '../../store/authStore';
import { useProjectStore } from '../../store/projectStore';
import { useEditor, EditorContent } from '@tiptap/react';
import StarterKit from '@tiptap/starter-kit';
import { Table } from '@tiptap/extension-table';
import { TableRow } from '@tiptap/extension-table-row';
import { TableCell } from '@tiptap/extension-table-cell';
import { TableHeader } from '@tiptap/extension-table-header';
import TextAlign from '@tiptap/extension-text-align';

const CustomTable = Table.extend({
  addAttributes() {
    return {
      ...this.parent?.(),
      noborder: {
        default: null,
        parseHTML: element => element.getAttribute('noborder') || element.hasAttribute('noborder') ? 'true' : null,
        renderHTML: attributes => attributes.noborder ? { noborder: 'true' } : {}
      }
    };
  }
});

const CustomTableCell = TableCell.extend({
  addAttributes() {
    return {
      ...this.parent?.(),
      noborder: {
        default: null,
        parseHTML: element => element.getAttribute('noborder') || element.hasAttribute('noborder') ? 'true' : null,
        renderHTML: attributes => attributes.noborder ? { noborder: 'true' } : {}
      },
      style: {
        default: null,
        parseHTML: element => element.getAttribute('style'),
        renderHTML: attributes => attributes.style ? { style: attributes.style } : {}
      }
    };
  }
});

const CustomTableHeader = TableHeader.extend({
  addAttributes() {
    return {
      ...this.parent?.(),
      noborder: {
        default: null,
        parseHTML: element => element.getAttribute('noborder') || element.hasAttribute('noborder') ? 'true' : null,
        renderHTML: attributes => attributes.noborder ? { noborder: 'true' } : {}
      },
      style: {
        default: null,
        parseHTML: element => element.getAttribute('style'),
        renderHTML: attributes => attributes.style ? { style: attributes.style } : {}
      }
    };
  }
});

interface FormFillModalProps {
  isOpen: boolean;
  onClose: () => void;
  formName: string;
  defaultTemplateHtml: string;
  projectId: string;
  onSaved: (formName: string, docId: string) => void;
}

const API_BASE = '';

export const FormFillModal: React.FC<FormFillModalProps> = ({
  isOpen,
  onClose,
  formName,
  defaultTemplateHtml,
  projectId,
  onSaved
}) => {
  const { getAuthHeaders } = useAuthStore();
  const checkedFileIds = useProjectStore(state => state.checkedFileIds);
  const checkedRefIds = useProjectStore(state => state.checkedRefIds);
  const selectedModel = useProjectStore(state => state.selectedModel);

  const [isLoading, setIsLoading] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [isAIFilling, setIsAIFilling] = useState(false);
  const [hasSavedDoc, setHasSavedDoc] = useState(false);

  const editor = useEditor({
    extensions: [
      StarterKit,
      CustomTable.configure({ resizable: true }),
      TableRow,
      CustomTableCell,
      CustomTableHeader,
      TextAlign.configure({ types: ['heading', 'paragraph', 'tableCell', 'tableHeader'] })
    ],
    content: defaultTemplateHtml || '',
    immediatelyRender: false,
    editorProps: {
      attributes: {
        class: 'prose prose-sm focus:outline-none w-full min-h-[500px] text-gray-900 leading-relaxed font-sans p-4'
      }
    }
  });

  const loadExistingOrAutoFill = async () => {
    if (!editor || !formName || !isOpen) return;
    setIsLoading(true);
    try {
      // 1. 查询当前项目是否已有保存的该表单记录
      const res = await fetch(`${API_BASE}/api/projects/${projectId || 'default'}/documents?t=${Date.now()}`, {
        headers: getAuthHeaders()
      });
      if (res.ok) {
        const docs = await res.json();
        if (Array.isArray(docs)) {
          const matched = docs
            .filter(d => d.title && d.title.startsWith(formName + '_'))
            .sort((a, b) => (b.timestamp || 0) - (a.timestamp || 0));

          if (matched.length > 0) {
            const detailRes = await fetch(`${API_BASE}/api/projects/${projectId || 'default'}/documents/${matched[0].id}`, {
              headers: getAuthHeaders()
            });
            if (detailRes.ok) {
              const fullDoc = await detailRes.json();
              if (fullDoc && fullDoc.content) {
                editor.commands.setContent(fullDoc.content);
                setHasSavedDoc(true);
                setIsLoading(false);
                return;
              }
            }
          }
        }
      }

      // 2. 如果没有保存记录，载入默认公文模板
      editor.commands.setContent(defaultTemplateHtml || '');
      setHasSavedDoc(false);
      // 异步在后台静默发起一次智能填表尝试（非阻塞，用户立即可见并可编辑）
      triggerAIFill(defaultTemplateHtml || '');
    } catch (e) {
      console.error('加载公文模板失败', e);
      editor.commands.setContent(defaultTemplateHtml || '');
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    if (isOpen && editor) {
      loadExistingOrAutoFill();
    }
  }, [isOpen, formName, editor]);

  const triggerAIFill = async (tplHtml: string) => {
    if (!editor) return;
    setIsAIFilling(true);
    try {
      const res = await fetch(`${API_BASE}/api/generate/fill-table`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...getAuthHeaders()
        },
        body: JSON.stringify({
          template_html: tplHtml || editor.getHTML(),
          project_id: projectId || 'default',
          file_ids: checkedFileIds,
          ref_ids: checkedRefIds,
          ref_global_lib: false,
          model: selectedModel
        })
      });
      if (res.ok) {
        const data = await res.json();
        if (data.html) {
          editor.commands.setContent(data.html);
          // 自动暂存
          await handleSave(data.html, true);
        }
      }
    } catch (e) {
      console.error('AI填表生成失败', e);
    } finally {
      setIsAIFilling(false);
    }
  };

  const handleSave = async (contentToSave?: string, quiet: boolean = false) => {
    if (!editor) return;
    if (!quiet) setIsSaving(true);
    try {
      const htmlContent = contentToSave || editor.getHTML();
      const now = new Date();
      const timeStr = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')} ${String(now.getHours()).padStart(2, '0')}:${String(now.getMinutes()).padStart(2, '0')}`;
      const title = `${formName}_${timeStr}`;
      const docId = 'doc_' + Math.random().toString(36).substr(2, 9);

      const docData = {
        id: docId,
        title: title,
        content: htmlContent,
        timestamp: Date.now(),
        tokens: htmlContent.length,
        sections: [],
        isAutoSave: quiet
      };

      const res = await fetch(`${API_BASE}/api/projects/${projectId || 'default'}/documents`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...getAuthHeaders()
        },
        body: JSON.stringify(docData)
      });

      if (res.ok) {
        setHasSavedDoc(true);
        onSaved(formName, docId);
        window.dispatchEvent(new CustomEvent('documentSaved'));
        if (!quiet) alert('🎉 表单保存成功！已同步至项目归档');
      }
    } catch (e: any) {
      console.error('保存表单失败', e);
      if (!quiet) alert(`❌ 保存失败: ${e.message}`);
    } finally {
      if (!quiet) setIsSaving(false);
    }
  };

  const handleResetFill = async () => {
    if (window.confirm(`确定要重新填写《${formName}》吗？将清空当前内容并重新使用大模型提取生成。`)) {
      editor?.commands.setContent(defaultTemplateHtml || '');
      await triggerAIFill(defaultTemplateHtml || '');
    }
  };

  const handleExport = () => {
    if (!editor) return;
    const htmlContent = `<!DOCTYPE html><html><head><meta charset="utf-8"><title>${formName}</title></head><body>${editor.getHTML()}</body></html>`;
    const blob = new Blob([htmlContent], { type: 'application/msword;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${formName}_${Date.now()}.doc`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  };

  const handlePrint = () => {
    if (!editor) return;
    const iframe = document.createElement('iframe');
    iframe.style.position = 'fixed';
    iframe.style.right = '0';
    iframe.style.bottom = '0';
    iframe.style.width = '0';
    iframe.style.height = '0';
    iframe.style.border = 'none';
    document.body.appendChild(iframe);
    const doc = iframe.contentWindow?.document;
    if (doc) {
      doc.open();
      doc.write(`<html><head><title>${formName}</title><style>
        @page { size: A4; margin: 0; }
        body { margin: 0; padding: 12mm 20mm; font-family: 宋体, SimSun, serif; font-size: 14px; line-height: 1.5; }
        table { border-collapse: collapse; border: 2px solid #000; width: 100%; }
        td, th { border: 1px solid #000; padding: 6px; }
        h1 { text-align: center; font-size: 26px; font-family: 黑体, SimHei, sans-serif; }
      </style></head><body>${editor.getHTML()}</body></html>`);
      doc.close();
      iframe.contentWindow?.focus();
      iframe.contentWindow?.print();
      setTimeout(() => { document.body.removeChild(iframe); }, 500);
    }
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm p-4 overflow-y-auto animate-fade-in">
      <div className="bg-white dark:bg-[#1e2025] w-full max-w-5xl h-[90vh] rounded-2xl shadow-2xl flex flex-col overflow-hidden border border-stone-200 dark:border-stone-700">
        
        {/* 顶部标题与操作栏 */}
        <div className="h-14 border-b border-stone-200 dark:border-stone-700 px-6 flex items-center justify-between bg-stone-50 dark:bg-[#25272D] shrink-0">
          <div className="flex items-center gap-2">
            <FileText className="w-5 h-5 text-indigo-600 dark:text-indigo-400" />
            <h3 className="font-bold text-base text-stone-800 dark:text-stone-100">{formName}</h3>
            {hasSavedDoc && (
              <span className="flex items-center gap-1 text-xs text-emerald-600 dark:text-emerald-400 bg-emerald-50 dark:bg-emerald-950/40 px-2 py-0.5 rounded-full border border-emerald-200 dark:border-emerald-800">
                <CheckCircle2 className="w-3 h-3" /> 已保存归档
              </span>
            )}
            {isAIFilling && (
              <span className="flex items-center gap-1 text-xs text-indigo-600 dark:text-indigo-400 bg-indigo-50 dark:bg-indigo-950/40 px-2 py-0.5 rounded-full animate-pulse">
                <Loader2 className="w-3 h-3 animate-spin" /> AI智能填报中...
              </span>
            )}
          </div>

          <div className="flex items-center gap-2">
            <button
              onClick={handleResetFill}
              disabled={isAIFilling}
              className="px-3 py-1.5 bg-stone-100 hover:bg-stone-200 dark:bg-stone-800 dark:hover:bg-stone-700 text-stone-700 dark:text-stone-300 rounded-lg flex items-center gap-1 text-xs font-medium border border-stone-300 dark:border-stone-700 shadow-sm"
              title="重新使用大模型提取生成"
            >
              <RotateCcw className="w-3.5 h-3.5" /> 重新填写
            </button>
            <button
              onClick={() => triggerAIFill(editor?.getHTML() || '')}
              disabled={isAIFilling}
              className="px-3 py-1.5 bg-gradient-to-r from-purple-600 to-indigo-600 hover:from-purple-700 hover:to-indigo-700 text-white rounded-lg flex items-center gap-1 text-xs font-semibold shadow-sm"
            >
              <Sparkles className="w-3.5 h-3.5" /> AI智能填报
            </button>
            <button
              onClick={() => handleSave()}
              disabled={isSaving}
              className="px-3.5 py-1.5 bg-[#8B7355] hover:bg-[#705c43] text-white rounded-lg flex items-center gap-1 text-xs font-medium shadow-sm"
            >
              <Save className="w-3.5 h-3.5" /> {isSaving ? '保存中...' : '保存'}
            </button>
            <button
              onClick={handleExport}
              className="px-3 py-1.5 bg-indigo-600 hover:bg-indigo-700 text-white rounded-lg flex items-center gap-1 text-xs font-semibold shadow-sm"
            >
              <Download className="w-3.5 h-3.5" /> 导出
            </button>
            <button
              onClick={handlePrint}
              className="px-3 py-1.5 bg-emerald-600 hover:bg-emerald-700 text-white rounded-lg flex items-center gap-1 text-xs font-semibold shadow-sm"
            >
              <Printer className="w-3.5 h-3.5" /> 打印
            </button>
            <button
              onClick={onClose}
              className="p-1.5 hover:bg-stone-200 dark:hover:bg-stone-700 rounded-lg text-stone-500 hover:text-stone-700 dark:text-stone-400 dark:hover:text-stone-200 transition-colors ml-2"
            >
              <X className="w-5 h-5" />
            </button>
          </div>
        </div>

        {/* 顶部 AI 后台填报状态条（非阻塞） */}
        {isAIFilling && (
          <div className="bg-gradient-to-r from-purple-500/15 via-indigo-500/15 to-purple-500/15 border-b border-indigo-200 dark:border-indigo-800/60 px-6 py-2.5 flex items-center justify-between text-xs text-indigo-700 dark:text-indigo-300 shrink-0">
            <div className="flex items-center gap-2">
              <Loader2 className="w-4 h-4 animate-spin text-indigo-600 dark:text-indigo-400 shrink-0" />
              <span className="font-medium">
                ✨ AI 正在结合案卷事实材料进行智能填报...（您可同步浏览或编辑，完成后将自动为您填充）
              </span>
            </div>
            <span className="text-[11px] text-stone-400 shrink-0">大模型后台推理中</span>
          </div>
        )}

        {/* 中间编辑区 - A4公文白板背景固定居中，仅正文内容在纸内独立平滑滚动 */}
        <div className="flex-1 overflow-hidden py-4 px-6 bg-[#E5E7EB] dark:bg-[#111215] flex justify-center items-stretch relative">
          <div className="bg-white text-black shadow-2xl border border-stone-300 w-full max-w-[860px] h-full rounded-sm flex flex-col relative overflow-hidden">
            {isLoading && (
              <div className="absolute inset-0 bg-white/60 dark:bg-black/40 flex items-center justify-center z-10">
                <Loader2 className="w-6 h-6 animate-spin text-indigo-500" />
              </div>
            )}
            <style>{`
              .ProseMirror table { border-collapse: collapse !important; border: 2px solid #000000 !important; width: 100% !important; margin: 12px 0 !important; table-layout: fixed !important; }
              .ProseMirror td, .ProseMirror th { border: 1px solid #000000 !important; padding: 6px 8px !important; font-size: 13px !important; color: #000000 !important; }
              .ProseMirror table[noborder="true"], .ProseMirror table[noborder="true"] td, .ProseMirror table[noborder="true"] th { border: none !important; }
              .ProseMirror td[noborder="true"], .ProseMirror th[noborder="true"] { border: none !important; }
              .ProseMirror p { color: #000000 !important; font-family: 宋体, SimSun, serif !important; line-height: 1.6 !important; }
              .ProseMirror h1 { color: #000000 !important; font-family: 黑体, SimHei, sans-serif !important; text-align: center !important; }
            `}</style>
            
            {/* 白纸内部独立滚动区域 */}
            <div className="flex-1 overflow-y-auto px-12 py-10 font-serif box-border select-text">
              <EditorContent editor={editor} className="prose prose-stone max-w-none focus:outline-none min-h-full" />
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
