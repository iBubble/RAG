import { useState, useEffect, useCallback } from 'react';
import { createPortal } from 'react-dom';
import { useParams } from 'react-router-dom';
import { useProjectStore } from '../../store/projectStore';
import { useAuthStore } from '../../store/authStore';
import { Trash2, Clock, Database, FileText, Download, X, RotateCcw, AlertTriangle } from 'lucide-react';

const API_BASE = import.meta.env.VITE_API_BASE || '';

export default function SavedDocumentsList() {
  const { id: projectId } = useParams<{ id: string }>();
  const [docs, setDocs] = useState<Record<string, any>[]>([]);
  const [previewDoc, setPreviewDoc] = useState<Record<string, any> | null>(null);
  
  const [isSelectionMode, setIsSelectionMode] = useState(false);
  const [selectedIds, setSelectedIds] = useState<Set<string>>(new Set());
  const [isDeleting, setIsDeleting] = useState(false);
  const [docToDelete, setDocToDelete] = useState<Record<string, any> | null>(null);
  const [docToLoad, setDocToLoad] = useState<Record<string, any> | null>(null);
  
  const removeSavedDocumentStore = useProjectStore(state => state.removeSavedDocument);
  const setTemplateData = useProjectStore(state => state.setTemplateData);
  const setCurrentDocId = useProjectStore(state => state.setCurrentDocId);

  const fetchDocuments = useCallback(async () => {
    try {
      const { getAuthHeaders } = useAuthStore.getState();
      const res = await fetch(`${API_BASE}/api/projects/${projectId || 'default'}/documents`, {
        headers: getAuthHeaders()
      });
      if (res.ok) {
        const data = await res.json();
        setDocs(data);
      }
    } catch (err) {
      console.error('Failed to fetch saved documents', err);
    }
  }, [projectId]);

  useEffect(() => {
    void fetchDocuments();
    
    const handleDocSaved = () => { void fetchDocuments(); };
    window.addEventListener('documentSaved', handleDocSaved);
    
    return () => {
      window.removeEventListener('documentSaved', handleDocSaved);
    };
  }, [fetchDocuments]);

  const executeRemoveSavedDocument = async (id: string) => {
    try {
      const { getAuthHeaders } = useAuthStore.getState();
      await fetch(`${API_BASE}/api/projects/${projectId || 'default'}/documents/${id}`, {
        method: 'DELETE',
        headers: getAuthHeaders()
      });
      setDocs(prev => prev.filter(d => d.id !== id));
      removeSavedDocumentStore(id);
    } catch (err) {
      console.error('Failed to delete document', err);
      alert('删除失败');
    }
  };

  const handleBatchDelete = async () => {
    if (selectedIds.size === 0) return;
    setIsDeleting(true);
    
    try {
      const { getAuthHeaders } = useAuthStore.getState();
      const idsToDelete = Array.from(selectedIds);
      
      await Promise.all(idsToDelete.map(id => 
        fetch(`${API_BASE}/api/projects/${projectId || 'default'}/documents/${id}`, {
          method: 'DELETE',
          headers: getAuthHeaders()
        })
      ));

      setDocs(prev => prev.filter(d => !selectedIds.has(d.id)));
      idsToDelete.forEach(id => removeSavedDocumentStore(id));
      setSelectedIds(new Set());
      setIsSelectionMode(false);
    } catch (err) {
      console.error('Batch deletion failed', err);
      alert('批量删除部分或全部失败，请重试');
      void fetchDocuments();
    } finally {
      setIsDeleting(false);
    }
  };

  const handleDownload = async (e: React.MouseEvent, doc: Record<string, any>) => {
    e.stopPropagation();
    // WHY: 列表接口已不含 content，需按需请求完整文档再下载
    try {
      const { getAuthHeaders } = useAuthStore.getState();
      const res = await fetch(`${API_BASE}/api/projects/${projectId || 'default'}/documents/${doc.id}`, {
        headers: getAuthHeaders()
      });
      if (!res.ok) throw new Error('获取文档失败');
      const fullDoc = await res.json();
      const blob = new Blob([fullDoc.content], { type: 'text/markdown;charset=utf-8;' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `${fullDoc.title || '归档文档'}.md`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    } catch (err) {
      console.error('下载文档失败', err);
      alert('下载失败，请重试');
    }
  };

  // WHY: 点击含 sections 的文档 → 确认后将大纲和编辑内容还原到画布，可继续编写。
  //      点击不含 sections 的旧文档 → 降级为只读弹窗预览模式。
  const executeLoadDocument = async (doc: Record<string, any>) => {
    try {
      const { getAuthHeaders } = useAuthStore.getState();
      const res = await fetch(`${API_BASE}/api/projects/${projectId || 'default'}/documents/${doc.id}`, {
        headers: getAuthHeaders()
      });
      if (!res.ok) throw new Error('获取文档失败');
      const fullDoc = await res.json();

      setTemplateData(fullDoc.title || '未命名实施方案', fullDoc.sections);
      setCurrentDocId(fullDoc.id);
    } catch (err) {
      console.error('加载文档失败', err);
      alert('加载文档失败，请重试');
    }
  };

  const handleDocClick = async (doc: Record<string, any>) => {
    // WHY: 列表接口已不含 sections，需按需请求完整文档。
    //      用 sectionCount > 0 判断是否可还原（替代之前直接读 doc.sections）。
    const hasSections = (doc.sectionCount || 0) > 0;

    if (hasSections) {
      setDocToLoad(doc);
    } else {
      // WHY: 旧数据无 sections，按需拉取 content 后弹窗预览
      try {
        const { getAuthHeaders } = useAuthStore.getState();
        const res = await fetch(`${API_BASE}/api/projects/${projectId || 'default'}/documents/${doc.id}`, {
          headers: getAuthHeaders()
        });
        if (!res.ok) throw new Error('获取文档失败');
        const fullDoc = await res.json();
        setPreviewDoc(fullDoc);
      } catch (err) {
        console.error('预览文档失败', err);
        alert('预览文档失败，请重试');
      }
    }
  };

  if (docs.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center p-8 text-gray-400 h-full bg-slate-50 border-t border-gray-200">
        <FileText className="w-12 h-12 text-gray-200 mb-3" />
        <p className="text-sm font-medium text-gray-500">尚无成稿文档</p>
        <p className="text-[11px] mt-1 text-center">在"文档编写"画板中点击保存</p>
      </div>
    );
  }

  return (
    <div className="flex flex-col h-full bg-slate-50 border-t border-gray-200 relative">
      <div className="px-4 py-3 border-b border-gray-200 bg-white items-center justify-between flex shrink-0">
        <h3 className="font-medium text-gray-700 text-sm flex items-center gap-1.5">
          <Database className="w-4 h-4 text-emerald-500" />
          编辑后保存的文件
        </h3>
        <div className="flex items-center gap-2">
          {!isSelectionMode ? (
            <>
              <span className="text-[10px] bg-emerald-50 text-emerald-600 px-2 py-0.5 rounded-full border border-emerald-100">
                共 {docs.length} 篇
              </span>
              {docs.length > 0 && (
                <button 
                  onClick={() => setIsSelectionMode(true)}
                  className="text-xs text-gray-500 hover:text-indigo-600 hover:bg-indigo-50 px-2 py-1 rounded transition-colors"
                >
                  批量管理
                </button>
              )}
            </>
          ) : (
            <>
              <span className="text-[10px] text-gray-500">已选 {selectedIds.size}/{docs.length}</span>
              <button 
                onClick={() => {
                  if (selectedIds.size === docs.length) {
                    setSelectedIds(new Set());
                  } else {
                    setSelectedIds(new Set(docs.map(d => d.id)));
                  }
                }}
                className="text-xs text-indigo-600 hover:bg-indigo-50 px-2 py-1 rounded transition-colors"
              >
                {selectedIds.size === docs.length ? '取消全选' : '全选'}
              </button>
              <button 
                onClick={() => {
                  setIsSelectionMode(false);
                  setSelectedIds(new Set());
                }}
                className="text-xs text-gray-500 hover:bg-gray-100 px-2 py-1 rounded transition-colors"
              >
                退出
              </button>
            </>
          )}
        </div>
      </div>

      {isSelectionMode && selectedIds.size > 0 && (
        <div className="px-4 py-2 bg-red-50 border-b border-red-100 flex justify-between items-center shrink-0">
          <span className="text-xs text-red-600 font-medium">确认删除这 {selectedIds.size} 篇文档？</span>
          <button 
            disabled={isDeleting}
            onClick={handleBatchDelete}
            className={`flex items-center gap-1 px-3 py-1 bg-red-500 text-white rounded shadow-sm text-xs transition-colors hover:bg-red-600 ${isDeleting ? 'opacity-50 cursor-not-allowed' : ''}`}
          >
            <Trash2 className="w-3.5 h-3.5" />
            {isDeleting ? '删除中...' : '删除'}
          </button>
        </div>
      )}
      
      <div className="flex-1 overflow-y-auto p-4 space-y-3">
        {docs.map(doc => {
          const hasSections = (doc.sectionCount || 0) > 0;
          return (
            <div 
              key={doc.id} 
              className={`bg-white rounded-lg border p-3 shadow-sm transition-all group relative cursor-pointer ${
                isSelectionMode && selectedIds.has(doc.id) 
                  ? 'border-indigo-400 ring-1 ring-indigo-400 bg-indigo-50/30' 
                  : 'border-gray-200 hover:shadow hover:border-emerald-200'
              }`}
              onClick={() => {
                if (isSelectionMode) {
                  const newSet = new Set(selectedIds);
                  if (newSet.has(doc.id)) newSet.delete(doc.id);
                  else newSet.add(doc.id);
                  setSelectedIds(newSet);
                } else {
                  handleDocClick(doc);
                }
              }}
              title={isSelectionMode ? '点击选择/取消选择' : (hasSections ? '点击加载此文档到画布继续编辑' : '点击预览文档详情')}
            >
              {isSelectionMode && (
                <div className="absolute left-3 top-1/2 -translate-y-1/2">
                  <div className={`w-4 h-4 rounded border flex items-center justify-center transition-colors ${
                    selectedIds.has(doc.id) ? 'bg-indigo-500 border-indigo-500' : 'border-gray-300 bg-white'
                  }`}>
                    {selectedIds.has(doc.id) && <svg className="w-3 h-3 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={3} d="M5 13l4 4L19 7" /></svg>}
                  </div>
                </div>
              )}
              <div className={`${isSelectionMode ? 'pl-7' : ''} transition-all`}>
                <div className="flex items-center gap-2 text-[10px] text-gray-400 mb-2">
                  <Clock className="w-3 h-3" />
                  {new Date(doc.timestamp).toLocaleString()}
                  {doc.isAutoSave && (
                    <span className="ml-1 bg-amber-50 text-amber-500 px-1.5 py-0.5 rounded border border-amber-100 text-[9px]">自动保存</span>
                  )}
                  <span className="ml-auto bg-gray-50 px-1.5 py-0.5 rounded border border-gray-100">{doc.tokens} 字</span>
                </div>
                
                <div className="font-medium text-gray-800 text-[13px] pr-2 break-all line-clamp-2">
                  {hasSections ? (
                    <RotateCcw className="w-3.5 h-3.5 inline-block mr-1 text-indigo-400" />
                  ) : (
                    <FileText className="w-3.5 h-3.5 inline-block mr-1 text-gray-400" />
                  )}
                  {doc.title || `未知归档_${new Date(doc.timestamp).toLocaleTimeString()}`}
                </div>
                
                {hasSections && (
                  <div className="text-[10px] text-indigo-400 mt-1.5">
                    含 {doc.sectionCount} 个章节大纲 · 可还原编辑
                  </div>
                )}
              </div>
              
              {!isSelectionMode && (
                <div className="flex items-center gap-1 opacity-0 group-hover:opacity-100 transition-opacity absolute right-2 bottom-2 bg-white/90 shadow-sm p-1 rounded-md border border-gray-100" onClick={e => e.stopPropagation()}>
                  <button 
                    onClick={(e) => handleDownload(e, doc)}
                    className="p-1 hover:bg-emerald-50 text-emerald-600 rounded transition-colors"
                    title="下载 Markdown 文件"
                  >
                    <Download className="w-3.5 h-3.5" />
                  </button>
                  <button 
                    onClick={(e) => {
                      e.stopPropagation();
                      setDocToDelete(doc);
                    }}
                    className="p-1 hover:bg-red-50 text-red-500 rounded transition-colors"
                    title="删除归档"
                  >
                    <Trash2 className="w-3.5 h-3.5" />
                  </button>
                </div>
              )}
            </div>
          );
        })}
      </div>

      {/* 降级只读预览弹窗 —— 仅用于不含 sections 的旧文档 */}
      {previewDoc && (
        <div className="fixed inset-0 z-[100] flex items-center justify-center bg-black/40 backdrop-blur-md transition-opacity">
          <div className="bg-white rounded-xl shadow-2xl w-[700px] max-w-[90vw] h-[85vh] flex flex-col overflow-hidden relative animate-in zoom-in-95 duration-200">
            <div className="flex items-center justify-between px-6 py-4 border-b border-gray-200 bg-gray-50 shrink-0">
               <h3 className="font-semibold text-gray-800 flex items-center gap-2">
                 <FileText className="w-5 h-5 text-emerald-500" />
                 {previewDoc.title || '归档文档内容预览'}
               </h3>
               <div className="flex items-center gap-3">
                 <button onClick={(e) => handleDownload(e, previewDoc)} className="flex items-center gap-1.5 px-3 py-1.5 bg-emerald-50 text-emerald-600 hover:bg-emerald-100 border border-emerald-200 rounded-md text-sm font-medium transition-colors shadow-sm">
                   <Download className="w-4 h-4" /> 另存为 MD
                 </button>
                 <div className="w-px h-5 bg-gray-300 mx-1"></div>
                 <button onClick={(() => setPreviewDoc(null))} className="p-1 hover:bg-gray-200 text-gray-500 hover:text-gray-800 rounded transition-colors">
                   <X className="w-6 h-6" />
                 </button>
               </div>
            </div>
            <div className="flex-1 overflow-y-auto p-8 bg-white text-[13px] text-gray-700 whitespace-pre-wrap leading-relaxed prose prose-sm max-w-none">
               {previewDoc.content}
            </div>
          </div>
        </div>
      )}

      {docToDelete && createPortal(
        <div className="fixed inset-0 z-[9999] flex items-center justify-center p-4 select-none">
          <div 
            className="absolute inset-0 bg-[#0F0F11]/45 backdrop-blur-[2px] transition-opacity" 
            onClick={() => setDocToDelete(null)}
          />
          <div className="relative bg-white dark:bg-[#1E1F22] rounded-xl p-5 shadow-2xl border border-stone-200 dark:border-stone-850 max-w-sm w-full flex flex-col gap-4 animate-in fade-in zoom-in-95 duration-200" onClick={e => e.stopPropagation()}>
            <div className="flex items-start gap-3 text-stone-800 dark:text-stone-200">
              <div className="p-2.5 rounded-full bg-red-50 dark:bg-red-950/20 text-red-600 dark:text-red-400 shrink-0">
                <AlertTriangle className="w-5 h-5" />
              </div>
              <div className="flex flex-col gap-1 min-w-0">
                <h3 className="text-sm font-bold text-stone-900 dark:text-stone-100">
                  🗑️ 删除归档文档
                </h3>
                <p className="text-xs text-stone-500 dark:text-stone-400 leading-normal mt-3 whitespace-pre-wrap font-sans">
                  确定要删除这份归档文档 "{docToDelete.title}" 吗？此操作不可逆。
                </p>
              </div>
            </div>
            <div className="flex justify-end gap-2 mt-2">
              <button
                onClick={() => setDocToDelete(null)}
                className="px-4 py-1.5 text-xs font-semibold text-stone-600 dark:text-stone-300 hover:text-stone-800 dark:hover:text-stone-100 hover:bg-stone-50 dark:hover:bg-stone-800 rounded-lg transition-colors border border-stone-200 dark:border-stone-700 cursor-pointer"
              >
                取消
              </button>
              <button
                onClick={() => {
                  void executeRemoveSavedDocument(docToDelete.id);
                  setDocToDelete(null);
                }}
                className="px-4 py-1.5 text-xs font-semibold text-white bg-red-600 hover:bg-red-700 active:scale-95 rounded-lg transition-all shadow-sm cursor-pointer"
              >
                确认删除
              </button>
            </div>
          </div>
        </div>,
        document.body
      )}

      {docToLoad && createPortal(
        <div className="fixed inset-0 z-[9999] flex items-center justify-center p-4 select-none">
          <div 
            className="absolute inset-0 bg-[#0F0F11]/45 backdrop-blur-[2px] transition-opacity" 
            onClick={() => setDocToLoad(null)}
          />
          <div className="relative bg-white dark:bg-[#1E1F22] rounded-xl p-5 shadow-2xl border border-stone-200 dark:border-stone-850 max-w-sm w-full flex flex-col gap-4 animate-in fade-in zoom-in-95 duration-200" onClick={e => e.stopPropagation()}>
            <div className="flex items-start gap-3 text-stone-800 dark:text-stone-200">
              <div className="p-2.5 rounded-full bg-indigo-50 dark:bg-indigo-950/20 text-indigo-600 dark:text-indigo-400 shrink-0">
                <AlertTriangle className="w-5 h-5" />
              </div>
              <div className="flex flex-col gap-1 min-w-0">
                <h3 className="text-sm font-bold text-stone-900 dark:text-stone-100">
                  ⚠️ 覆盖画布内容
                </h3>
                <p className="text-xs text-stone-500 dark:text-stone-400 leading-normal mt-3 whitespace-pre-wrap font-sans">
                  将会覆盖当前画布内容，确认加载文档 "{docToLoad.title}" 的历史状态并继续编辑？
                </p>
              </div>
            </div>
            <div className="flex justify-end gap-2 mt-2">
              <button
                onClick={() => setDocToLoad(null)}
                className="px-4 py-1.5 text-xs font-semibold text-stone-600 dark:text-stone-300 hover:text-stone-800 dark:hover:text-stone-100 hover:bg-stone-50 dark:hover:bg-stone-800 rounded-lg transition-colors border border-stone-200 dark:border-stone-700 cursor-pointer"
              >
                取消
              </button>
              <button
                onClick={() => {
                  void executeLoadDocument(docToLoad);
                  setDocToLoad(null);
                }}
                className="px-4 py-1.5 text-xs font-semibold text-white bg-indigo-600 hover:bg-indigo-700 active:scale-95 rounded-lg transition-all shadow-sm cursor-pointer"
              >
                确认加载
              </button>
            </div>
          </div>
        </div>,
        document.body
      )}
    </div>
  );
}
