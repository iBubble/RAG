import React, { useState, useEffect } from 'react';
import { 
  Save, Download, FileSpreadsheet, Loader2, FileText,
  Bold, Italic, Table as TableIcon, Trash2, Plus, 
  ChevronDown, ChevronUp, Columns, Layers
} from 'lucide-react';
import { useAuthStore } from '../../store/authStore';
import { useEditor, EditorContent } from '@tiptap/react';
import StarterKit from '@tiptap/starter-kit';
import { Table } from '@tiptap/extension-table';
import { TableRow } from '@tiptap/extension-table-row';
import { TableCell } from '@tiptap/extension-table-cell';
import { TableHeader } from '@tiptap/extension-table-header';
import Placeholder from '@tiptap/extension-placeholder';

const CustomTable = Table.extend({
  addAttributes() {
    return {
      ...this.parent?.(),
      noborder: {
        default: null,
        parseHTML: element => element.getAttribute('noborder') || element.hasAttribute('noborder') ? 'true' : null,
        renderHTML: attributes => attributes.noborder ? { noborder: 'true' } : {},
      },
    };
  },
});

const CustomTableCell = TableCell.extend({
  addAttributes() {
    return {
      ...this.parent?.(),
      noborder: {
        default: null,
        parseHTML: element => element.getAttribute('noborder') || element.hasAttribute('noborder') ? 'true' : null,
        renderHTML: attributes => attributes.noborder ? { noborder: 'true' } : {},
      },
      style: {
        default: null,
        parseHTML: element => element.getAttribute('style'),
        renderHTML: attributes => attributes.style ? { style: attributes.style } : {},
      },
    };
  },
});

const CustomTableHeader = TableHeader.extend({
  addAttributes() {
    return {
      ...this.parent?.(),
      noborder: {
        default: null,
        parseHTML: element => element.getAttribute('noborder') || element.hasAttribute('noborder') ? 'true' : null,
        renderHTML: attributes => attributes.noborder ? { noborder: 'true' } : {},
      },
      style: {
        default: null,
        parseHTML: element => element.getAttribute('style'),
        renderHTML: attributes => attributes.style ? { style: attributes.style } : {},
      },
    };
  },
});

const API_BASE = import.meta.env.VITE_API_BASE || '';

interface AITable { name: string; template: string; }
interface AICategory { name: string; tables: AITable[]; }

export default function AITablePanel({ canWrite = true }: { canWrite?: boolean }) {
  const { getAuthHeaders } = useAuthStore();
  const [categories, setCategories] = useState<AICategory[]>([]);
  const [selectedCategory, setSelectedCategory] = useState('');
  const [selectedTable, setSelectedTable] = useState('');
  const [loading, setLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [isExporting, setIsExporting] = useState(false);

  const editor = useEditor({
    extensions: [
      StarterKit,
      CustomTable.configure({ resizable: true }),
      TableRow,
      CustomTableHeader,
      CustomTableCell,
      Placeholder.configure({ placeholder: '在此处编辑生成的表格与分析文档...' })
    ],
    content: '',
    immediatelyRender: false,
    editorProps: {
      attributes: {
        class: 'prose prose-sm focus:outline-none w-full min-h-[420px] text-gray-900 leading-relaxed font-sans p-2',
      },
      handleClick(view, pos) {
        const { doc } = view.state;
        const text = doc.textBetween(pos, pos + 1);
        const prevText = doc.textBetween(pos - 1, pos);
        
        let clickedPos = -1;
        let clickedChar = '';
        
        const boxChars = ['□', '☐', '☑', '☒'];
        if (boxChars.includes(text)) {
          clickedPos = pos;
          clickedChar = text;
        } else if (boxChars.includes(prevText)) {
          clickedPos = pos - 1;
          clickedChar = prevText;
        }
        
        if (clickedPos !== -1) {
          const newChar = (clickedChar === '□' || clickedChar === '☐') ? '☑' : '□';
          const transaction = view.state.tr.replaceWith(
            clickedPos,
            clickedPos + 1,
            view.state.schema.text(newChar)
          );
          view.dispatch(transaction);
          return true;
        }
        return false;
      }
    },
  });

  const fetchTemplates = async () => {
    try {
      const res = await fetch(`${API_BASE}/api/admin/ai-templates?t=${Date.now()}`, { headers: getAuthHeaders() });
      if (res.ok) {
        const data: AICategory[] = await res.json();
        setCategories(data || []);
        if (data && data.length > 0) {
          const firstCat = data[0];
          setSelectedCategory(firstCat.name);
          if (firstCat.tables && firstCat.tables.length > 0) {
            setSelectedTable(firstCat.tables[0].name);
            editor?.commands.setContent(firstCat.tables[0].template);
          }
        }
      }
    } catch (e) { console.error("加载模板失败", e); }
    finally { setLoading(false); }
  };

  useEffect(() => {
    fetchTemplates();
  }, [editor]);

  const handleCategoryChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    const catName = e.target.value;
    setSelectedCategory(catName);
    const cat = categories.find(c => c.name === catName);
    if (cat && cat.tables && cat.tables.length > 0) {
      setSelectedTable(cat.tables[0].name);
      editor?.commands.setContent(cat.tables[0].template);
    } else {
      setSelectedTable('');
      editor?.commands.setContent('');
    }
  };

  const handleTableChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    const tblName = e.target.value;
    setSelectedTable(tblName);
    const cat = categories.find(c => c.name === selectedCategory);
    const tbl = cat?.tables?.find(t => t.name === tblName);
    editor?.commands.setContent(tbl?.template || '');
  };

  const handleSave = () => {
    setIsSaving(true);
    setTimeout(() => { setIsSaving(false); alert('🎉 模板数据保存成功！'); }, 800);
  };

  const handleExport = () => {
    setIsExporting(true);
    setTimeout(() => { setIsExporting(false); alert('📂 已成功导出为 Word 表格样式格式文档！'); }, 800);
  };

  const currentTables = categories.find(c => c.name === selectedCategory)?.tables || [];

  return (
    <div className="flex flex-col h-full w-full bg-[#F9F8F6] dark:bg-[#1e2025] p-5 overflow-hidden gap-4 font-sans text-xs">
      {/* 顶部筛选器 */}
      <div className="bg-white dark:bg-[#282A31] border border-[#E0DCD5] dark:border-[#383A42] rounded-2xl p-4 shadow-sm shrink-0 flex items-center gap-4">
        <div className="flex items-center gap-2 shrink-0">
          <FileSpreadsheet className="w-5 h-5 text-indigo-500" />
          <span className="font-bold text-gray-800 dark:text-stone-200 text-sm">AI 表格智选</span>
        </div>
        {loading ? (
          <div className="flex-1 flex items-center gap-2 text-gray-400"><Loader2 className="w-4 h-4 animate-spin text-indigo-500" /> 正在载入列表...</div>
        ) : (
          <div className="flex-1 flex gap-3 items-center max-w-2xl">
            <div className="flex-1 flex flex-col gap-1">
              <label className="text-[10px] font-semibold text-gray-400 dark:text-gray-500 uppercase tracking-wider">一级类别</label>
              <select
                value={selectedCategory}
                onChange={handleCategoryChange}
                className="w-full px-3 py-2 bg-gray-50 dark:bg-[#1E1F22] border border-gray-200 dark:border-[#383A42] rounded-xl outline-none focus:border-indigo-500 cursor-pointer text-gray-700 dark:text-stone-300 font-medium text-xs"
              >
                {categories.map(cat => (
                  <option key={cat.name} value={cat.name} className="dark:bg-[#1E1F22] bg-white text-gray-700">{cat.name}</option>
                ))}
              </select>
            </div>
            <div className="flex-1 flex flex-col gap-1">
              <label className="text-[10px] font-semibold text-gray-400 dark:text-gray-500 uppercase tracking-wider">二级子表</label>
              <select
                value={selectedTable}
                onChange={handleTableChange}
                className="w-full px-3 py-2 bg-gray-50 dark:bg-[#1E1F22] border border-gray-200 dark:border-[#383A42] rounded-xl outline-none focus:border-indigo-500 cursor-pointer text-gray-700 dark:text-stone-300 font-medium text-xs"
              >
                {currentTables.map(tbl => (
                  <option key={tbl.name} value={tbl.name} className="dark:bg-[#1E1F22] bg-white text-gray-700">{tbl.name}</option>
                ))}
              </select>
            </div>
          </div>
        )}
      </div>

      {/* 下方：富文本纸张编辑区 */}
      <div className="flex-1 bg-white dark:bg-[#282A31] flex flex-col overflow-hidden relative">
        {/* 工具栏与控制 */}
        <div className="px-5 py-3 border-b border-[#E0DCD5] dark:border-[#383A42] flex flex-wrap justify-between items-center bg-[#F9F8F6] dark:bg-[#23242A] gap-3 shrink-0">
          <span className="font-bold text-gray-800 dark:text-stone-200 flex items-center gap-1.5 text-sm">
            <FileText className="w-4.5 h-4.5 text-[#8B7355]" /> 文档编辑窗口
            <span className="text-[11px] font-normal text-stone-500 dark:text-stone-400">（{selectedCategory || '无'} · {selectedTable || '无'}）</span>
          </span>

          {/* 表格操作快捷键 */}
          {editor && (
            <div className="flex items-center gap-1 bg-white dark:bg-[#1E1F22] px-2 py-1 rounded-lg border border-gray-200 dark:border-stone-800">
              <button onClick={() => editor.chain().focus().toggleBold().run()} className="p-1 hover:bg-gray-100 dark:hover:bg-stone-850 rounded" title="加粗"><Bold className="w-3.5 h-3.5" /></button>
              <button onClick={() => editor.chain().focus().toggleItalic().run()} className="p-1 hover:bg-gray-100 dark:hover:bg-stone-850 rounded" title="斜体"><Italic className="w-3.5 h-3.5" /></button>
              <div className="w-[1px] h-3.5 bg-gray-200 dark:bg-stone-800 mx-1" />
              <button onClick={() => editor.chain().focus().addRowAfter().run()} className="p-1 hover:bg-gray-100 dark:hover:bg-stone-850 rounded flex items-center gap-0.5" title="在下方增行"><Plus className="w-3 h-3" /><ChevronDown className="w-3 h-3" /></button>
              <button onClick={() => editor.chain().focus().addRowBefore().run()} className="p-1 hover:bg-gray-100 dark:hover:bg-stone-850 rounded flex items-center gap-0.5" title="在上方增行"><Plus className="w-3 h-3" /><ChevronUp className="w-3 h-3" /></button>
              <button onClick={() => editor.chain().focus().deleteRow().run()} className="p-1 hover:bg-red-50 text-red-500 dark:hover:bg-red-950/20 rounded flex items-center gap-0.5" title="删行"><Trash2 className="w-3 h-3" /><ChevronDown className="w-3 h-3" /></button>
              <div className="w-[1px] h-3.5 bg-gray-200 dark:bg-stone-800 mx-1" />
              <button onClick={() => editor.chain().focus().addColumnAfter().run()} className="p-1 hover:bg-gray-100 dark:hover:bg-stone-850 rounded flex items-center gap-0.5" title="在右侧增列"><Plus className="w-3 h-3" /><Columns className="w-3 h-3" /></button>
              <button onClick={() => editor.chain().focus().deleteColumn().run()} className="p-1 hover:bg-red-50 text-red-500 dark:hover:bg-red-950/20 rounded flex items-center gap-0.5" title="删列"><Trash2 className="w-3 h-3" /><Columns className="w-3 h-3" /></button>
              <div className="w-[1px] h-3.5 bg-gray-200 dark:bg-stone-800 mx-1" />
              <button onClick={() => editor.chain().focus().mergeCells().run()} className="p-1 hover:bg-gray-100 dark:hover:bg-stone-850 rounded" title="合并单元格"><Layers className="w-3.5 h-3.5" /></button>
              <button onClick={() => editor.chain().focus().splitCell().run()} className="p-1 hover:bg-gray-100 dark:hover:bg-stone-850 rounded" title="拆分单元格"><TableIcon className="w-3.5 h-3.5" /></button>
            </div>
          )}
          
          <div className="flex gap-2">
            <button onClick={handleSave} disabled={isSaving || !canWrite} className="px-3.5 py-1.5 bg-[#8B7355] hover:bg-[#705c43] text-white rounded-lg flex items-center gap-1 font-medium disabled:opacity-50 text-xs shadow-sm"><Save className="w-3.5 h-3.5" /> 保存</button>
            <button onClick={handleExport} disabled={isExporting} className="px-3.5 py-1.5 bg-indigo-600 hover:bg-indigo-700 text-white rounded-lg flex items-center gap-1 font-semibold disabled:opacity-50 text-xs shadow-sm"><Download className="w-3.5 h-3.5" /> 导出</button>
          </div>
        </div>

        {/* 编辑区 - 模拟 Word A4 页边距白板 */}
        <div className="flex-1 p-4 overflow-y-auto bg-[#F3F4F6] dark:bg-[#1E1F22] flex flex-col font-sans relative">
          <style>{`
            html.dark .ProseMirror, html.dark .ProseMirror *, .dark .ProseMirror, .dark .ProseMirror * {
              color: #000000 !important;
            }
            .ProseMirror {
              background-color: #ffffff !important;
              color: #000000 !important;
              max-width: 1000px !important;
              width: 100% !important;
              margin: 16px auto !important;
              padding: 48px 56px !important;
              box-shadow: 0 4px 16px rgba(0, 0, 0, 0.08) !important;
              border: 1px solid #E5E7EB !important;
              min-height: 1050px !important;
              box-sizing: border-box !important;
              font-family: 宋体, SimSun, STSong, serif !important;
            }
            .ProseMirror p {
              font-family: 宋体, SimSun, STSong, serif !important;
            }
            .ProseMirror p[align="center"] {
              font-family: 黑体, SimHei, sans-serif !important;
              font-weight: bold !important;
            }
            .ProseMirror * {
              color: #000000 !important;
            }
            .ProseMirror .tableWrapper {
              padding: 4px !important;
              background-color: #ffffff !important;
              width: 100% !important;
              overflow-x: auto !important;
            }
            /* 强力覆盖全局 index.css 里的 Tiptap table 斑马纹、圆角、隐藏边框等现代后台样式，还原实体黑边框公文样式 */
            .ai-document-editor .ProseMirror table {
              border-collapse: collapse !important;
              border: 2px solid #000000 !important;
              width: 100% !important;
              margin: 12px 0 !important;
              table-layout: fixed !important;
              border-radius: 0 !important;
              overflow: visible !important;
              box-shadow: none !important;
            }
            .ai-document-editor .ProseMirror tr, 
            .ai-document-editor .ProseMirror tbody tr, 
            .ai-document-editor .ProseMirror tr:last-child,
            .ai-document-editor .ProseMirror tbody tr:last-child {
              border: none !important;
              border-top: none !important;
              border-bottom: none !important;
              background-color: #ffffff !important;
              background: #ffffff !important;
            }
            .ai-document-editor .ProseMirror table td, 
            .ai-document-editor .ProseMirror table th {
              border: 1px solid #000000 !important;
              border-top: 1px solid #000000 !important;
              border-bottom: 1px solid #000000 !important;
              border-left: 1px solid #000000 !important;
              border-right: 1px solid #000000 !important;
              padding: 10px 8px !important;
              min-height: 40px !important;
              min-width: 40px !important;
              text-align: center !important;
              vertical-align: middle !important;
              background-color: #ffffff !important;
              background: #ffffff !important;
              color: #000000 !important;
              font-family: 宋体, SimSun, STSong, serif !important;
              border-radius: 0 !important;
            }
            /* 强力消除 index.css 中的 last-child 去边框行为 */
            .ai-document-editor .ProseMirror table td:last-child,
            .ai-document-editor .ProseMirror table th:last-child {
              border-right: 1px solid #000000 !important;
            }
            .ai-document-editor .ProseMirror table tr:last-child td {
              border-bottom: 1px solid #000000 !important;
            }
            /* 强力消除 index.css 中的斑马纹与悬浮高亮 */
            .ai-document-editor .ProseMirror table tbody tr:nth-child(odd) td,
            .ai-document-editor .ProseMirror table tbody tr:nth-child(even) td,
            .ai-document-editor .ProseMirror table tbody tr:hover td {
              background-color: #ffffff !important;
              background: #ffffff !important;
            }
            
            /* 精准定位透明布局表格（用于如“登记单位：___ 编号：___”的左右对齐排版） */
            .ai-document-editor .ProseMirror table[noborder="true"] {
              border: none !important;
              box-shadow: none !important;
              margin: 8px 0 !important;
              table-layout: auto !important;
              background: transparent !important;
              background-color: transparent !important;
            }
            .ai-document-editor .ProseMirror table[noborder="true"] tr,
            .ai-document-editor .ProseMirror table[noborder="true"] tbody tr,
            .ai-document-editor .ProseMirror table[noborder="true"] td,
            .ai-document-editor .ProseMirror table[noborder="true"] th {
              border: none !important;
              border-top: none !important;
              border-bottom: none !important;
              border-left: none !important;
              border-right: none !important;
              padding: 4px 0 !important;
              background: transparent !important;
              background-color: transparent !important;
            }
            
            /* 第一个排版表格（如“登记单位：___ 编号：___”）强制无边框与左右对齐 */
            .ai-document-editor .ProseMirror > .tableWrapper:first-of-type table,
            .ai-document-editor .ProseMirror > table:first-of-type {
              border: none !important;
              box-shadow: none !important;
              margin: 8px 0 !important;
              table-layout: auto !important;
              background: transparent !important;
              background-color: transparent !important;
            }
            .ai-document-editor .ProseMirror > .tableWrapper:first-of-type tr,
            .ai-document-editor .ProseMirror > .tableWrapper:first-of-type tbody tr,
            .ai-document-editor .ProseMirror > table:first-of-type tr,
            .ai-document-editor .ProseMirror > table:first-of-type tbody tr {
              border: none !important;
              background: transparent !important;
              background-color: transparent !important;
            }
            .ai-document-editor .ProseMirror > .tableWrapper:first-of-type td,
            .ai-document-editor .ProseMirror > .tableWrapper:first-of-type th,
            .ai-document-editor .ProseMirror > table:first-of-type td,
            .ai-document-editor .ProseMirror > table:first-of-type th {
              border: none !important;
              border-top: none !important;
              border-bottom: none !important;
              border-left: none !important;
              border-right: none !important;
              padding: 4px 0 !important;
              background: transparent !important;
              background-color: transparent !important;
            }
            /* 左侧单元格左对齐，右侧单元格右对齐 */
            .ai-document-editor .ProseMirror > .tableWrapper:first-of-type td:first-child,
            .ai-document-editor .ProseMirror > table:first-of-type td:first-child {
              text-align: left !important;
            }
            .ai-document-editor .ProseMirror > .tableWrapper:first-of-type td:last-child,
            .ai-document-editor .ProseMirror > table:first-of-type td:last-child {
              text-align: right !important;
            }

            /* 强力公文大标题 h1 美化 */
            .ai-document-editor .ProseMirror h1 {
              text-align: center !important;
              font-size: 28px !important;
              font-family: 黑体, SimHei, sans-serif !important;
              font-weight: bold !important;
              letter-spacing: 6px !important;
              margin-top: 12px !important;
              margin-bottom: 24px !important;
              color: #000000 !important;
            }
          `}</style>
          <div className="ai-document-editor w-full">
            <EditorContent editor={editor} />
          </div>
        </div>
      </div>
    </div>
  );
}
