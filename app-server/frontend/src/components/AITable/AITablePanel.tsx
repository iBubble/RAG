import React, { useState, useEffect, useRef } from 'react';
import { 
  Save, Download, FileSpreadsheet, Loader2, FileText,
  Bold, Italic, Table as TableIcon, Trash2, Plus, 
  ChevronDown, ChevronUp, Columns, Layers, Sparkles, Printer
} from 'lucide-react';
import { useAuthStore } from '../../store/authStore';
import { useProjectStore } from '../../store/projectStore';
import { useEditor, EditorContent } from '@tiptap/react';
import StarterKit from '@tiptap/starter-kit';
import { Table } from '@tiptap/extension-table';
import { TableRow } from '@tiptap/extension-table-row';
import { TableCell } from '@tiptap/extension-table-cell';
import { TableHeader } from '@tiptap/extension-table-header';
import Placeholder from '@tiptap/extension-placeholder';
import TextAlign from '@tiptap/extension-text-align';


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

export default function AITablePanel({ projectId = 'default', canWrite = true }: { projectId?: string; canWrite?: boolean }) {
  const { getAuthHeaders } = useAuthStore();
  const checkedFileIds = useProjectStore(state => state.checkedFileIds);
  const checkedRefIds = useProjectStore(state => state.checkedRefIds);
  const selectedModel = useProjectStore(state => state.selectedModel);
  const [refGlobalLib] = useState(false);
  const [isAIFilling, setIsAIFilling] = useState(false);

  const [categories, setCategories] = useState<AICategory[]>([]);
  const [selectedCategory, setSelectedCategory] = useState('');
  const [selectedTable, setSelectedTable] = useState('');
  const [loading, setLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [isExporting, setIsExporting] = useState(false);

  const hasInitializedContentRef = useRef(false);
  const pendingDocRef = useRef<any>(null);
  const [pendingLoadDoc, setPendingLoadDoc] = useState<any>(null);

  const editor = useEditor({
    extensions: [
      StarterKit,
      CustomTable.configure({ resizable: true }),
      TableRow,
      CustomTableHeader,
      CustomTableCell,
      TextAlign.configure({
        types: ['heading', 'paragraph', 'tableCell', 'tableHeader'],
      }),
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

  const loadLatestSavedTableDocument = async (tableName: string, defaultTemplate: string) => {
    if (!editor || !tableName) return;
    try {
      const res = await fetch(`${API_BASE}/api/projects/${projectId || 'default'}/documents?t=${Date.now()}`, {
        headers: getAuthHeaders()
      });
      if (res.ok) {
        const docs = await res.json();
        if (Array.isArray(docs)) {
          const matchedDocs = docs
            .filter(d => d.title && d.title.startsWith(tableName + '_'))
            .sort((a, b) => (b.timestamp || 0) - (a.timestamp || 0));
          
          if (matchedDocs.length > 0) {
            const targetDoc = matchedDocs[0];
            const detailRes = await fetch(`${API_BASE}/api/projects/${projectId || 'default'}/documents/${targetDoc.id}`, {
              headers: getAuthHeaders()
            });
            if (detailRes.ok) {
              const fullDoc = await detailRes.json();
              if (fullDoc && fullDoc.content) {
                editor.commands.setContent(fullDoc.content);
                return;
              }
            }
          }
        }
      }
    } catch (e) {
      console.error('加载项目下已保存的表格文档失败', e);
    }
    editor.commands.setContent(defaultTemplate || '');
  };

  const fetchTemplates = async () => {
    try {
      const res = await fetch(`${API_BASE}/api/admin/ai-templates?t=${Date.now()}`, { headers: getAuthHeaders() });
      if (res.ok) {
        const data: AICategory[] = await res.json();
        setCategories(data || []);
      }
    } catch (e) { console.error("加载模板失败", e); }
    finally { setLoading(false); }
  };

  useEffect(() => {
    fetchTemplates();
  }, [editor]);

  useEffect(() => {
    hasInitializedContentRef.current = false;
  }, [projectId]);

  useEffect(() => {
    if (editor && categories.length > 0 && !pendingLoadDoc && !pendingDocRef.current && !hasInitializedContentRef.current) {
      const firstCat = categories[0];
      setSelectedCategory(firstCat.name);
      if (firstCat.tables && firstCat.tables.length > 0) {
        setSelectedTable(firstCat.tables[0].name);
        loadLatestSavedTableDocument(firstCat.tables[0].name, firstCat.tables[0].template);
      }
      hasInitializedContentRef.current = true;
    }
  }, [editor, categories, pendingLoadDoc]);

  const loadDocToTable = (fullDoc: any) => {
    if (!editor || !fullDoc) return;
    const title = fullDoc.title || '';
    const parts = title.split('_');
    const tableName = parts[0];
    
    let foundCategory = '';
    let foundTable = '';
    
    for (const cat of categories) {
      const tbl = cat.tables?.find(t => t.name === tableName);
      if (tbl) {
        foundCategory = cat.name;
        foundTable = tbl.name;
        break;
      }
    }
    
    if (foundCategory && foundTable) {
      setSelectedCategory(foundCategory);
      setSelectedTable(foundTable);
    }
    
    editor.commands.setContent(fullDoc.content || '');
  };

  useEffect(() => {
    const handleLoadDocument = (e: Event) => {
      const customEvent = e as CustomEvent;
      const detail = customEvent.detail;
      if (!detail || !editor) return;

      const fullDoc = detail.doc ? detail.doc : detail;
      const onHandled = detail.onHandled;

      const title = fullDoc.title || '';
      if (title.includes('_')) {
        useProjectStore.getState().setActiveTab('AI表格');
        if (onHandled) onHandled();
      }

      pendingDocRef.current = fullDoc;
      if (categories.length === 0) {
        setPendingLoadDoc(fullDoc);
      } else {
        loadDocToTable(fullDoc);
      }
    };
    
    window.addEventListener('loadSavedTableDocument', handleLoadDocument);
    return () => {
      window.removeEventListener('loadSavedTableDocument', handleLoadDocument);
    };
  }, [editor, categories]);

  useEffect(() => {
    if (categories.length > 0 && pendingLoadDoc && editor) {
      loadDocToTable(pendingLoadDoc);
      setPendingLoadDoc(null);
      pendingDocRef.current = null;
    }
  }, [categories, pendingLoadDoc, editor]);

  const handleCategoryChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    const catName = e.target.value;
    setSelectedCategory(catName);
    const cat = categories.find(c => c.name === catName);
    if (cat && cat.tables && cat.tables.length > 0) {
      setSelectedTable(cat.tables[0].name);
      loadLatestSavedTableDocument(cat.tables[0].name, cat.tables[0].template);
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
    loadLatestSavedTableDocument(tblName, tbl?.template || '');
  };

  const saveDocumentContent = async (htmlContent: string, quiet: boolean = false) => {
    if (!editor) return;
    if (!quiet) setIsSaving(true);
    try {
      const now = new Date();
      const year = now.getFullYear();
      const month = String(now.getMonth() + 1).padStart(2, '0');
      const day = String(now.getDate()).padStart(2, '0');
      const hours = String(now.getHours()).padStart(2, '0');
      const minutes = String(now.getMinutes()).padStart(2, '0');
      const formattedTime = `${year}-${month}-${day} ${hours}:${minutes}`;
      const title = `${selectedTable || '智能表单'}_${formattedTime}`;
      
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
      
      if (!res.ok) {
        throw new Error('保存文档失败');
      }
      
      window.dispatchEvent(new CustomEvent('documentSaved'));
      if (!quiet) {
        alert('🎉 模板数据保存成功！');
      }
    } catch (e: any) {
      console.error(e);
      if (!quiet) {
        alert(`❌ 保存失败: ${e.message}`);
      }
    } finally {
      if (!quiet) setIsSaving(false);
    }
  };

  const handleSave = async () => {
    if (!editor) return;
    await saveDocumentContent(editor.getHTML(), false);
  };

  const handleExport = () => {
    if (!editor) return;
    setIsExporting(true);
    
    try {
      const now = new Date();
      const year = now.getFullYear();
      const month = String(now.getMonth() + 1).padStart(2, '0');
      const day = String(now.getDate()).padStart(2, '0');
      const hours = String(now.getHours()).padStart(2, '0');
      const minutes = String(now.getMinutes()).padStart(2, '0');
      const formattedTime = `${year}${month}${day}_${hours}${minutes}`;
      const fileName = `${selectedTable || '智能表单'}_${formattedTime}.doc`;
      
      const htmlContent = `
        <!DOCTYPE html>
        <html>
        <head>
          <meta charset="utf-8">
          <title>${selectedTable || '智能表单'}</title>
          <style>
            table { border-collapse: collapse; width: 100%; font-family: SimSun, Arial, sans-serif; }
            td, th { border: 1px solid #000000; padding: 8px; text-align: left; }
            th { background-color: #f2f2f2; font-weight: bold; }
            h1, p { font-family: SimSun, Arial, sans-serif; }
            h1 { text-align: center; }
          </style>
        </head>
        <body>
          ${editor.getHTML()}
        </body>
        </html>
      `;
      
      const blob = new Blob([htmlContent], { type: 'application/msword;charset=utf-8' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = fileName;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    } catch (e: any) {
      console.error('导出失败', e);
      alert('导出失败，请重试');
    } finally {
      setIsExporting(false);
    }
  };

  const handlePrint = () => {
    const contentHtml = editor?.getHTML() || '';
    
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
      doc.write(`
        <html>
          <head>
            <title>打印文档</title>
            <style>
              @page {
                size: A4;
                margin: 0; /* 强制消除页眉页脚（消除 localhost 等 URL 及日期信息） */
              }
              html, body {
                max-height: 296mm; /* A4物理高度为 297mm，限制在此范围内绝对防止分出第二页 */
                overflow: hidden;
              }
              body {
                margin: 0;
                padding: 12mm 20mm 12mm 20mm; /* 稍微缩减上下内边距，提供更充裕的高度安全冗余 */
                box-sizing: border-box;
                background: #ffffff;
                color: #000000;
                font-family: 宋体, SimSun, STSong, serif;
                font-size: 14px;
                line-height: 1.52;
                white-space: pre-wrap;
              }
              /* 自动隐藏编辑器末尾不小心多按出来的空段落，防止其挤占高度产生空白页 */
              .ProseMirror > p:empty,
              .ProseMirror > p:last-child:empty,
              .ProseMirror > p:last-child:has(br:only-child) {
                display: none !important;
                margin: 0 !important;
                padding: 0 !important;
                height: 0 !important;
              }
              h1 {
                text-align: center !important;
                font-size: 26px !important; /* 稍微缩小标题字号提供单页更多空间 */
                font-family: 黑体, SimHei, sans-serif !important;
                font-weight: bold !important;
                letter-spacing: 6px !important;
                margin-top: 5mm !important; /* 缩小顶部外边距，紧凑排版 */
                margin-bottom: 8mm !important;
                color: #000000 !important;
              }
              table {
                border-collapse: collapse !important;
                border: 2px solid #000000 !important;
                width: 100% !important;
                margin: 8px 0 !important;
                table-layout: fixed !important;
                background: transparent !important;
              }
              tr {
                border: none !important;
                background-color: #ffffff !important;
              }
              td, th {
                border: 1px solid #000000 !important;
                padding: 8px 6px !important; /* 缩小内边距保证一页排下 */
                text-align: center !important;
                vertical-align: middle !important;
                color: #000000 !important;
                font-family: 宋体, SimSun, STSong, serif !important;
              }
              table[noborder="true"],
              table[noborder],
              table:has(td[noborder="true"]),
              table:has(td[noborder]) {
                border: none !important;
              }
              table[noborder="true"] tr,
              table[noborder] tr,
              table[noborder="true"] td,
              table[noborder] td,
              table[noborder="true"] th,
              table[noborder] th,
              table td[noborder="true"],
              table th[noborder="true"],
              table td[noborder],
              table th[noborder] {
                border: none !important;
                background: transparent !important;
                background-color: transparent !important;
              }
              table[noborder="true"] td:first-child:nth-last-child(2),
              table[noborder] td:first-child:nth-last-child(2) {
                text-align: left !important;
              }
              table[noborder="true"] td:first-child:nth-last-child(2) ~ td,
              table[noborder] td:first-child:nth-last-child(2) ~ td {
                text-align: right !important;
              }
              p {
                margin: 4px 0 !important; /* 缩小段落的上下间距 */
              }
              tr, img {
                page-break-inside: avoid;
              }
            </style>
          </head>
          <body>
            <div class="ProseMirror">
              ${contentHtml}
            </div>
            <script>
              window.onload = function() {
                window.focus();
                window.print();
                setTimeout(function() {
                  window.parent.document.body.removeChild(window.frameElement);
                }, 500);
              };
            </script>
          </body>
        </html>
      `);
      doc.close();
    }
  };

  const handleAIFill = async () => {
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
          template_html: editor.getHTML(),
          project_id: projectId,
          file_ids: checkedFileIds,
          ref_ids: checkedRefIds,
          ref_global_lib: refGlobalLib,
          model: selectedModel
        })
      });
      if (!res.ok) {
        const errData = await res.json();
        throw new Error(errData.detail || '填表生成失败');
      }
      const data = await res.json();
      if (data.html) {
        editor.commands.setContent(data.html);
        // AI 填充成功后，自动且静默地进行持久化保存
        await saveDocumentContent(data.html, true);
      } else {
        alert('⚠️ 未能生成有效的内容，请检查勾选的参考文件。');
      }
    } catch (e: any) {
      console.error(e);
      alert(`❌ AI智能填表失败: ${e.message}`);
    } finally {
      setIsAIFilling(false);
    }
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
            <button
              onClick={handleAIFill}
              disabled={isAIFilling || !editor}
              className="px-3.5 py-1.5 bg-gradient-to-r from-purple-600 to-indigo-600 hover:from-purple-700 hover:to-indigo-700 text-white rounded-lg flex items-center gap-1.5 font-semibold disabled:opacity-50 text-xs shadow-sm transition-all duration-200"
            >
              {isAIFilling ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Sparkles className="w-3.5 h-3.5" />}
              AI智能填表
            </button>
            <button onClick={handleSave} disabled={isSaving || !canWrite} className="px-3.5 py-1.5 bg-[#8B7355] hover:bg-[#705c43] text-white rounded-lg flex items-center gap-1 font-medium disabled:opacity-50 text-xs shadow-sm"><Save className="w-3.5 h-3.5" /> 保存</button>
            <button onClick={handleExport} disabled={isExporting} className="px-3.5 py-1.5 bg-indigo-600 hover:bg-indigo-700 text-white rounded-lg flex items-center gap-1 font-semibold disabled:opacity-50 text-xs shadow-sm"><Download className="w-3.5 h-3.5" /> 导出</button>
            <button onClick={handlePrint} disabled={!editor} className="px-3.5 py-1.5 bg-emerald-600 hover:bg-emerald-700 text-white rounded-lg flex items-center gap-1 font-semibold text-xs shadow-sm"><Printer className="w-3.5 h-3.5" /> 打印</button>
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
            .ProseMirror, .ProseMirror p, .ProseMirror td, .ProseMirror th, .ProseMirror div {
              white-space: pre-wrap !important;
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
            .ai-document-editor .ProseMirror table:has(td[noborder]) tr:last-child td,
            .ai-document-editor .ProseMirror table:has(td[noborder="true"]) tr:last-child td,
            .ai-document-editor .ProseMirror table tr:last-child td[noborder],
            .ai-document-editor .ProseMirror table tr:last-child td[noborder="true"] {
              border-bottom: none !important;
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
            
            /* 带有 noborder="true" 或 noborder 属性的排版/布局表格强制无边框 */
            .ai-document-editor .ProseMirror table[noborder="true"],
            .ai-document-editor .ProseMirror table[noborder],
            .ai-document-editor .ProseMirror table:has(td[noborder="true"]),
            .ai-document-editor .ProseMirror table:has(td[noborder]) {
              border: none !important;
              box-shadow: none !important;
              background: transparent !important;
              background-color: transparent !important;
            }
            .ai-document-editor .ProseMirror table[noborder="true"] tr,
            .ai-document-editor .ProseMirror table[noborder] tr,
            .ai-document-editor .ProseMirror table[noborder="true"] td,
            .ai-document-editor .ProseMirror table[noborder] td,
            .ai-document-editor .ProseMirror table[noborder="true"] th,
            .ai-document-editor .ProseMirror table[noborder] th,
            .ai-document-editor .ProseMirror table td[noborder="true"],
            .ai-document-editor .ProseMirror table th[noborder="true"],
            .ai-document-editor .ProseMirror table td[noborder],
            .ai-document-editor .ProseMirror table th[noborder] {
              border: none !important;
              border-top: none !important;
              border-bottom: none !important;
              border-left: none !important;
              border-right: none !important;
              background: transparent !important;
              background-color: transparent !important;
            }
            /* 对于 2 列的 noborder 布局表格（如登记单位和编号），做两端对齐 */
            .ai-document-editor .ProseMirror table[noborder="true"] td:first-child:nth-last-child(2),
            .ai-document-editor .ProseMirror table[noborder] td:first-child:nth-last-child(2) {
              text-align: left !important;
            }
            .ai-document-editor .ProseMirror table[noborder="true"] td:first-child:nth-last-child(2) ~ td,
            .ai-document-editor .ProseMirror table[noborder] td:first-child:nth-last-child(2) ~ td {
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
