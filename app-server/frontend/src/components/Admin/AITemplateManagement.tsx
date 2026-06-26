import React, { useState, useEffect, useRef } from 'react';
import { useAuthStore } from '../../store/authStore';
import { 
  FolderOpen, FileSpreadsheet, Trash2, Plus, 
  Save, Loader2, RefreshCw, AlertCircle, FileUp,
  Bold, Italic, Table as TableIcon, ChevronDown, ChevronUp, Columns, Layers
} from 'lucide-react';
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

interface AITable {
  name: string;
  template: string;
}

interface AICategory {
  name: string;
  tables: AITable[];
}

export default function AITemplateManagement() {
  const { getAuthHeaders } = useAuthStore();
  const [categories, setCategories] = useState<AICategory[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  // 选中的大类和子表
  const [activeCategory, setActiveCategory] = useState<string>('');
  const [activeTable, setActiveTable] = useState<string>('');

  // 各项操作状态
  const [saving, setSaving] = useState<boolean>(false);
  const [uploading, setUploading] = useState<boolean>(false);
  const [newTableNames, setNewTableNames] = useState<Record<string, string>>({});
  const fileInputRef = useRef<HTMLInputElement>(null);

  const editor = useEditor({
    extensions: [
      StarterKit,
      CustomTable.configure({ resizable: true }),
      TableRow,
      CustomTableHeader,
      CustomTableCell,
      Placeholder.configure({ placeholder: '在此编辑模板结构，支持直接插入和调整表格...' })
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

  // 加载数据
  const fetchTemplates = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`${API_BASE}/api/admin/ai-templates?t=${Date.now()}`, {
        headers: getAuthHeaders(),
      });
      if (res.ok) {
        const data = await res.json();
        setCategories(data || []);
      } else {
        const errData = await res.json().catch(() => ({}));
        setError(errData.detail || '拉取模板列表失败');
      }
    } catch (err: any) {
      setError(err.message || '网络请求错误，请重试');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchTemplates();
  }, []);

  // 选中二级表单
  const handleSelectTable = (catName: string, tbl: AITable) => {
    setActiveCategory(catName);
    setActiveTable(tbl.name);
    editor?.commands.setContent(tbl.template);
  };
  // 上传 PDF 提取模板
  const handleUploadPDF = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setUploading(true);
    setError(null);
    const formData = new FormData();
    formData.append('file', file);
    try {
      const res = await fetch(`${API_BASE}/api/admin/ai-templates/extract`, {
        method: 'POST',
        headers: getAuthHeaders(),
        body: formData,
      });
      if (res.ok) {
        await fetchTemplates();
        if (fileInputRef.current) fileInputRef.current.value = '';
      } else {
        const errData = await res.json().catch(() => ({}));
        setError(errData.detail || '提取模板失败');
      }
    } catch (err: any) {
      setError(err.message || '网络请求错误，请重试');
    } finally {
      setUploading(false);
    }
  };

  // 保存修改后的二级表单模板
  const handleUpdateTable = async () => {
    if (!activeCategory || !activeTable || !editor) return;
    const currentHTML = editor.getHTML();
    setSaving(true);
    setError(null);
    try {
      const res = await fetch(`${API_BASE}/api/admin/ai-templates/update-table`, {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
          ...getAuthHeaders(),
        },
        body: JSON.stringify({
          categoryName: activeCategory,
          tableName: activeTable,
          newTemplate: currentHTML,
        }),
      });
      if (res.ok) {
        // 更新本地状态，避免重新拉取
        setCategories(prev => prev.map(cat => {
          if (cat.name === activeCategory) {
            return {
              ...cat,
              tables: cat.tables.map(tbl => 
                tbl.name === activeTable ? { ...tbl, template: currentHTML } : tbl
              )
            };
          }
          return cat;
        }));
        alert('保存成功！');
      } else {
        const errData = await res.json().catch(() => ({}));
        setError(errData.detail || '更新模板失败');
      }
    } catch (err: any) {
      setError(err.message || '保存请求失败，请重试');
    } finally {
      setSaving(false);
    }
  };

  // 添加新的二级表单
  const handleAddTable = async (catName: string) => {
    const tableName = newTableNames[catName]?.trim();
    if (!tableName) return;
    setError(null);
    try {
      const res = await fetch(`${API_BASE}/api/admin/ai-templates/add-table`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...getAuthHeaders(),
        },
        body: JSON.stringify({
          categoryName: catName,
          tableName: tableName,
        }),
      });
      if (res.ok) {
        await fetchTemplates();
        setNewTableNames(prev => ({ ...prev, [catName]: '' }));
      } else {
        const errData = await res.json().catch(() => ({}));
        setError(errData.detail || '添加子表失败');
      }
    } catch (err: any) {
      setError(err.message || '网络请求错误，请重试');
    }
  };

  // 删除二级表单
  const handleDeleteTable = async (catName: string, tableName: string) => {
    if (!window.confirm(`确定要删除子表“${tableName}”吗？`)) return;
    setError(null);
    try {
      const res = await fetch(`${API_BASE}/api/admin/ai-templates/delete-table`, {
        method: 'DELETE',
        headers: {
          'Content-Type': 'application/json',
          ...getAuthHeaders(),
        },
        body: JSON.stringify({
          categoryName: catName,
          tableName: tableName,
        }),
      });
      if (res.ok) {
        await fetchTemplates();
        if (activeCategory === catName && activeTable === tableName) {
          setActiveCategory('');
          setActiveTable('');
          editor?.commands.setContent('');
        }
      } else {
        const errData = await res.json().catch(() => ({}));
        setError(errData.detail || '删除子表失败');
      }
    } catch (err: any) {
      setError(err.message || '请求失败，请重试');
    }
  };

  // 删除大类
  const handleDeleteCategory = async (catName: string) => {
    if (!window.confirm(`确定要删除大类“${catName}”及其所有子表模板吗？`)) return;
    setError(null);
    try {
      const res = await fetch(`${API_BASE}/api/admin/ai-templates/delete-category`, {
        method: 'DELETE',
        headers: {
          'Content-Type': 'application/json',
          ...getAuthHeaders(),
        },
        body: JSON.stringify({
          categoryName: catName,
        }),
      });
      if (res.ok) {
        await fetchTemplates();
        if (activeCategory === catName) {
          setActiveCategory('');
          setActiveTable('');
          editor?.commands.setContent('');
        }
      } else {
        const errData = await res.json().catch(() => ({}));
        setError(errData.detail || '删除大类失败');
      }
    } catch (err: any) {
      setError(err.message || '请求失败，请重试');
    }
  };

  return (
    <div className="h-[calc(100vh-12rem)] flex flex-col gap-4">
      {/* 头部状态与操作 */}
      <div className="flex items-center justify-between bg-white p-4 rounded-2xl border border-gray-100 shadow-sm">
        <div>
          <h2 className="text-xl font-bold text-gray-800 flex items-center gap-2">
            <FileSpreadsheet className="w-6 h-6 text-indigo-500" />
            AI 模板管理
          </h2>
          <p className="text-xs text-gray-500 mt-1">管理员可通过上传 PDF 智能拆分大类并提取二级格式。支持实时调整各级文书骨架。</p>
        </div>
        <div className="flex items-center gap-3">
          <input
            type="file"
            accept=".pdf"
            className="hidden"
            ref={fileInputRef}
            onChange={handleUploadPDF}
          />
          <button
            onClick={() => fileInputRef.current?.click()}
            disabled={uploading}
            className="flex items-center gap-2 px-4 py-2 bg-indigo-600 text-white rounded-xl text-sm font-medium hover:bg-indigo-700 disabled:opacity-50 transition-all shadow-sm shadow-indigo-100"
          >
            {uploading ? <Loader2 className="w-4 h-4 animate-spin" /> : <FileUp className="w-4 h-4" />}
            {uploading ? '解析提取中...' : '上传 PDF 提取'}
          </button>
          <button
            onClick={fetchTemplates}
            className="p-2 text-gray-500 hover:text-indigo-600 hover:bg-indigo-50 rounded-xl transition-all"
            title="刷新"
          >
            <RefreshCw className="w-4 h-4" />
          </button>
        </div>
      </div>

      {error && (
        <div className="p-3.5 bg-red-50 border border-red-100 text-red-700 rounded-xl text-xs flex items-center gap-2">
          <AlertCircle className="w-4 h-4 flex-shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {/* 主面板左右布局 */}
      <div className="flex-1 bg-white border border-gray-200/80 rounded-2xl flex overflow-hidden shadow-sm">
        {loading ? (
          <div className="flex-1 flex flex-col items-center justify-center gap-2 text-gray-400">
            <Loader2 className="w-8 h-8 animate-spin text-indigo-500" />
            <span className="text-sm">正在载入模板列表...</span>
          </div>
        ) : (
          <>
            {/* 左侧大类子表列表树 */}
            <div className="w-80 border-r border-gray-100 flex flex-col bg-gray-50/50">
              <div className="p-4 border-b border-gray-100 bg-white">
                <span className="text-xs font-bold text-gray-400 uppercase tracking-wider">模板目录 ({categories.length})</span>
              </div>
              <div className="flex-1 overflow-y-auto p-3 space-y-3">
                {categories.map(cat => (
                  <div key={cat.name} className="bg-white rounded-xl border border-gray-100 p-2.5 shadow-sm space-y-2">
                    <div className="flex items-center justify-between gap-2 group/cat">
                      <div className="flex items-center gap-1.5 min-w-0">
                        <FolderOpen className="w-4 h-4 text-amber-500 flex-shrink-0" />
                        <span className="text-sm font-semibold text-gray-700 truncate" title={cat.name}>{cat.name}</span>
                      </div>
                      <button
                        onClick={() => handleDeleteCategory(cat.name)}
                        className="p-1 text-gray-400 hover:text-red-500 rounded hover:bg-red-50 opacity-0 group-hover/cat:opacity-100 transition-all flex-shrink-0"
                        title="删除大类"
                      >
                        <Trash2 className="w-3.5 h-3.5" />
                      </button>
                    </div>

                    <div className="space-y-1 pl-3.5 border-l border-gray-100">
                      {cat.tables?.map(tbl => {
                        const isSelected = activeCategory === cat.name && activeTable === tbl.name;
                        return (
                          <div
                            key={tbl.name}
                            onClick={() => handleSelectTable(cat.name, tbl)}
                            className={`flex items-center justify-between gap-2 px-2.5 py-1.5 rounded-lg text-xs cursor-pointer group/tbl transition-all ${
                              isSelected ? 'bg-indigo-50 text-indigo-700 font-medium' : 'text-gray-600 hover:bg-gray-50'
                            }`}
                          >
                            <span className="truncate flex-1" title={tbl.name}>{tbl.name}</span>
                            <button
                              onClick={(e) => { e.stopPropagation(); handleDeleteTable(cat.name, tbl.name); }}
                              className="p-0.5 text-gray-400 hover:text-red-500 rounded hover:bg-red-50 opacity-0 group-hover/tbl:opacity-100 transition-all flex-shrink-0"
                            >
                              <Trash2 className="w-3 h-3" />
                            </button>
                          </div>
                        );
                      })}
                      {/* 添加子模板表单 */}
                      <div className="flex items-center gap-1 mt-2 pt-2 border-t border-dashed border-gray-100">
                        <input
                          type="text"
                          placeholder="新子表名"
                          value={newTableNames[cat.name] || ''}
                          onChange={(e) => setNewTableNames(prev => ({ ...prev, [cat.name]: e.target.value }))}
                          className="flex-1 px-2 py-1 text-xs border border-gray-200 rounded-md focus:outline-none focus:border-indigo-400"
                        />
                        <button
                          onClick={() => handleAddTable(cat.name)}
                          className="p-1 bg-indigo-50 text-indigo-600 rounded-md hover:bg-indigo-100 transition-all"
                          title="添加子模板"
                        >
                          <Plus className="w-3.5 h-3.5" />
                        </button>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </div>

            {/* 右侧编辑器区域 */}
            <div className="flex-1 flex flex-col bg-white">
              {activeTable ? (
                <div className="flex-1 flex flex-col h-full overflow-hidden">
                  <div className="flex flex-wrap items-center justify-between px-6 py-4 border-b border-gray-100 gap-3">
                    <div className="min-w-0">
                      <span className="text-xs text-indigo-500 font-medium">{activeCategory}</span>
                      <h3 className="text-sm font-bold text-gray-800 truncate mt-0.5">{activeTable}</h3>
                    </div>
                    {/* 表格操作快捷键 */}
                    {editor && (
                      <div className="flex items-center gap-1 bg-white dark:bg-[#1E1F22] px-2 py-1 rounded-lg border border-gray-200 dark:border-stone-850">
                        <button onClick={() => editor.chain().focus().toggleBold().run()} className="p-1 hover:bg-gray-100 dark:hover:bg-stone-850 rounded" title="加粗"><Bold className="w-3.5 h-3.5" /></button>
                        <button onClick={() => editor.chain().focus().toggleItalic().run()} className="p-1 hover:bg-gray-100 dark:hover:bg-stone-850 rounded" title="斜体"><Italic className="w-3.5 h-3.5" /></button>
                        <div className="w-[1px] h-3.5 bg-gray-200 dark:bg-stone-800 mx-1" />
                        <button onClick={() => editor.chain().focus().addRowAfter().run()} className="p-1 hover:bg-gray-100 dark:hover:bg-stone-850 rounded flex items-center gap-0.5" title="下方增行"><Plus className="w-3 h-3" /><ChevronDown className="w-3 h-3" /></button>
                        <button onClick={() => editor.chain().focus().addRowBefore().run()} className="p-1 hover:bg-gray-100 dark:hover:bg-stone-850 rounded flex items-center gap-0.5" title="上方增行"><Plus className="w-3 h-3" /><ChevronUp className="w-3 h-3" /></button>
                        <button onClick={() => editor.chain().focus().deleteRow().run()} className="p-1 hover:bg-red-50 text-red-500 dark:hover:bg-red-950/20 rounded flex items-center gap-0.5" title="删行"><Trash2 className="w-3 h-3" /><ChevronDown className="w-3 h-3" /></button>
                        <div className="w-[1px] h-3.5 bg-gray-200 dark:bg-stone-800 mx-1" />
                        <button onClick={() => editor.chain().focus().addColumnAfter().run()} className="p-1 hover:bg-gray-100 dark:hover:bg-stone-850 rounded flex items-center gap-0.5" title="右侧增列"><Plus className="w-3 h-3" /><Columns className="w-3 h-3" /></button>
                        <button onClick={() => editor.chain().focus().deleteColumn().run()} className="p-1 hover:bg-red-50 text-red-500 dark:hover:bg-red-950/20 rounded flex items-center gap-0.5" title="删列"><Trash2 className="w-3 h-3" /><Columns className="w-3 h-3" /></button>
                        <div className="w-[1px] h-3.5 bg-gray-200 dark:bg-stone-800 mx-1" />
                        <button onClick={() => editor.chain().focus().mergeCells().run()} className="p-1 hover:bg-gray-100 dark:hover:bg-stone-850 rounded" title="合并单元格"><Layers className="w-3.5 h-3.5" /></button>
                        <button onClick={() => editor.chain().focus().splitCell().run()} className="p-1 hover:bg-gray-100 dark:hover:bg-stone-850 rounded" title="拆分单元格"><TableIcon className="w-3.5 h-3.5" /></button>
                      </div>
                    )}
                    <button
                      onClick={handleUpdateTable}
                      disabled={saving}
                      className="flex items-center gap-1.5 px-4 py-2 bg-indigo-600 text-white rounded-xl text-xs font-semibold hover:bg-indigo-700 disabled:opacity-50 transition-all shadow-sm"
                    >
                      {saving ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Save className="w-3.5 h-3.5" />}
                      {saving ? '保存中...' : '保存更改'}
                    </button>
                  </div>
                  {/* 编辑区 - 模拟 Word A4 页边距白板 */}
                  <div className="flex-1 p-4 overflow-y-auto bg-[#F3F4F6] dark:bg-[#1E1F22] flex flex-col font-sans">
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
                      
                      /* 带有 noborder="true" 或 noborder 属性的排版/布局表格强制无边框 */
                      .ai-document-editor .ProseMirror table[noborder="true"],
                      .ai-document-editor .ProseMirror table[noborder] {
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
                      .ai-document-editor .ProseMirror table[noborder] th {
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
              ) : (
                <div className="flex-1 flex flex-col items-center justify-center text-gray-400 gap-2">
                  <FileSpreadsheet className="w-12 h-12 text-gray-200" />
                  <p className="text-sm">请在左侧选择一个子表模板进行编辑和管理</p>
                </div>
              )}
            </div>
          </>
        )}
      </div>
    </div>
  );
}

