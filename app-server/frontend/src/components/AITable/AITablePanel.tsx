import React, { useState, useEffect } from 'react';
import { Save, Download, FileSpreadsheet, Loader2, FileText } from 'lucide-react';

export default function AITablePanel({ canWrite = true }: { canWrite?: boolean }) {
  const [selectedCategory, setSelectedCategory] = useState('类别1');
  const [selectedTable, setSelectedTable] = useState('表格1-1');
  const [editorContent, setEditorContent] = useState('');
  const [isSaving, setIsSaving] = useState(false);
  const [isExporting, setIsExporting] = useState(false);

  // 1-10 类别与表格名称生成
  const categories = Array.from({ length: 10 }, (_, i) => `类别${i + 1}`);
  
  // 联动逻辑：获取当前类别的 10 个子表格
  const getTablesForCategory = (cat: string) => {
    const num = cat.replace('类别', '');
    return Array.from({ length: 10 }, (_, i) => `表格${num}-${i + 1}`);
  };

  // 一级菜单改变时，自动将二级菜单更新为该子类的第一个
  const handleCategoryChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    const cat = e.target.value;
    setSelectedCategory(cat);
    const tables = getTablesForCategory(cat);
    setSelectedTable(tables[0]);
    setEditorContent(`【${cat} - ${tables[0]}】\n这里是表格的编辑与生成区域。\n可以进行数据填充与文档编写...`);
  };

  useEffect(() => {
    setEditorContent(`【${selectedCategory} - ${selectedTable}】\n这里是表格的编辑与生成区域。\n可以进行数据填充与文档编写...`);
  }, []);

  const handleSave = () => {
    setIsSaving(true);
    setTimeout(() => {
      setIsSaving(false);
      alert('🎉 保存成功！');
    }, 800);
  };

  const handleExport = () => {
    setIsExporting(true);
    setTimeout(() => {
      setIsExporting(false);
      alert('📂 导出成功！');
    }, 800);
  };

  return (
    <div className="flex flex-col h-full w-full bg-[#F9F8F6] dark:bg-[#1e2025] p-5 overflow-hidden gap-4 font-sans text-xs">
      {/* 上方：联动二级下拉菜单 */}
      <div className="bg-white dark:bg-[#282A31] border border-[#E0DCD5] dark:border-[#383A42] rounded-2xl p-4 shadow-sm shrink-0 flex items-center gap-4">
        <div className="flex items-center gap-2 shrink-0">
          <FileSpreadsheet className="w-5 h-5 text-indigo-500" />
          <span className="font-bold text-gray-800 dark:text-stone-200 text-sm">AI 表格智选</span>
        </div>
        
        <div className="flex-1 flex gap-3 items-center max-w-xl">
          {/* 一级下拉菜单 */}
          <div className="flex-1 flex flex-col gap-1">
            <label className="text-[10px] font-semibold text-gray-400 dark:text-gray-500 uppercase tracking-wider">一级类别</label>
            <select
              value={selectedCategory}
              onChange={handleCategoryChange}
              className="w-full px-3 py-2 bg-gray-50 dark:bg-[#1E1F22] border border-gray-200 dark:border-[#383A42] rounded-xl outline-none focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100 transition-all cursor-pointer text-gray-700 dark:text-stone-300 font-medium text-xs"
            >
              {categories.map(cat => (
                <option key={cat} value={cat} className="dark:bg-[#1E1F22] dark:text-stone-300 bg-white text-gray-700">{cat}</option>
              ))}
            </select>
          </div>

          {/* 二级下拉菜单 */}
          <div className="flex-1 flex flex-col gap-1">
            <label className="text-[10px] font-semibold text-gray-400 dark:text-gray-500 uppercase tracking-wider">二级子表</label>
            <select
              value={selectedTable}
              onChange={(e) => {
                setSelectedTable(e.target.value);
                setEditorContent(`【${selectedCategory} - ${e.target.value}】\n这里是表格的编辑与生成区域。\n可以进行数据填充与文档编写...`);
              }}
              className="w-full px-3 py-2 bg-gray-50 dark:bg-[#1E1F22] border border-gray-200 dark:border-[#383A42] rounded-xl outline-none focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100 transition-all cursor-pointer text-gray-700 dark:text-stone-300 font-medium text-xs"
            >
              {getTablesForCategory(selectedCategory).map(tbl => (
                <option key={tbl} value={tbl} className="dark:bg-[#1E1F22] dark:text-stone-300 bg-white text-gray-700">{tbl}</option>
              ))}
            </select>
          </div>
        </div>
      </div>

      {/* 下方：文档编辑窗口 */}
      <div className="flex-1 bg-white dark:bg-[#282A31] border border-[#E0DCD5] dark:border-[#383A42] rounded-2xl shadow-sm flex flex-col overflow-hidden relative">
        {/* 编辑窗口控制条 */}
        <div className="px-5 py-3.5 border-b border-[#E0DCD5] dark:border-[#383A42] flex justify-between items-center bg-[#F9F8F6] dark:bg-[#23242A] shrink-0">
          <span className="font-bold text-gray-800 dark:text-stone-200 flex items-center gap-1.5 text-sm">
            <FileText className="w-4.5 h-4.5 text-[#8B7355]" />
            文档编辑窗口
            <span className="text-[11px] font-normal text-stone-500 dark:text-stone-400">
              （{selectedCategory} · {selectedTable}）
            </span>
          </span>
          
          <div className="flex gap-2">
            <button
              onClick={handleSave}
              disabled={isSaving || !canWrite}
              className="px-3.5 py-1.5 bg-[#8B7355] hover:bg-[#705c43] text-white rounded-lg flex items-center justify-center gap-1.5 font-medium transition-all cursor-pointer disabled:opacity-50 text-xs shadow-sm hover:shadow"
            >
              {isSaving ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Save className="w-3.5 h-3.5" />}
              <span>保存</span>
            </button>
            <button
              onClick={handleExport}
              disabled={isExporting}
              className="px-3.5 py-1.5 bg-indigo-600 hover:bg-indigo-700 text-white rounded-lg flex items-center justify-center gap-1.5 font-semibold transition-all cursor-pointer disabled:opacity-50 text-xs shadow-sm hover:shadow"
            >
              {isExporting ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Download className="w-3.5 h-3.5" />}
              <span>导出</span>
            </button>
          </div>
        </div>

        {/* 编辑器内容输入区 */}
        <div className="flex-1 p-5 overflow-y-auto relative bg-[#FCFAF7] dark:bg-[#1E1F22]">
          <textarea
            value={editorContent}
            onChange={e => setEditorContent(e.target.value)}
            className="w-full h-full bg-transparent border-none outline-none resize-none text-gray-700 dark:text-stone-200 font-sans leading-relaxed whitespace-pre-wrap focus:ring-0 text-xs animate-[fadeIn_0.3s_ease-out]"
            placeholder="在此编辑生成的表格与分析文档..."
          />
        </div>
      </div>
    </div>
  );
}
