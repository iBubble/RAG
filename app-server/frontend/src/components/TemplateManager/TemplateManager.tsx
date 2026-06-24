import React, { useRef, useState } from 'react';
import { UploadCloud, FileText, Loader2, CheckCircle2 } from 'lucide-react';
import { useParams } from 'react-router-dom';
import { useProjectStore } from '../../store/projectStore';
import { useAuthStore } from '../../store/authStore';

const API_BASE = import.meta.env.VITE_API_BASE || '';

export default function TemplateManager({ canWrite = true }: { canWrite?: boolean }) {
  const { id: projectId } = useParams<{ id: string }>();
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [isUploading, setIsUploading] = useState(false);
  
  const templateTitle = useProjectStore(state => state.templateTitle);
  const originalTemplateName = useProjectStore(state => state.originalTemplateName);
  const templateSections = useProjectStore(state => state.templateSections);
  const setTemplateData = useProjectStore(state => state.setTemplateData);
  const setActiveTab = useProjectStore(state => state.setActiveTab);
  const { getAuthHeaders } = useAuthStore();

  const handleTemplateUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    try {
      setIsUploading(true);
      const formData = new FormData();
      formData.append('file', file);
      
      const res = await fetch(`${API_BASE}/api/template/parse`, {
        method: 'POST',
        headers: getAuthHeaders(),
        body: formData
      });
      if (!res.ok) throw new Error('上传解析失败');
      
      const data = await res.json();
      setTemplateData(data.filename, data.sections);
      const { setCurrentDocId } = useProjectStore.getState();
      setCurrentDocId(null);

      // WHY: 上传范文后同步保存到后端该项目专属路径，实现项目级范文隔离
      try {
        await fetch(`${API_BASE}/api/projects/${projectId || 'default'}/template`, {
          method: 'POST',
          headers: { ...getAuthHeaders(), 'Content-Type': 'application/json' },
          body: JSON.stringify({ title: data.filename, sections: data.sections })
        });
      } catch (saveErr) {
        console.warn('范文保存到后端失败', saveErr);
      }

      setActiveTab('文档编写');
      
    } catch (e) {
      alert("解析失败，请检查是否是合法的 .docx 格式");
      console.error(e);
    } finally {
      setIsUploading(false);
      if (fileInputRef.current) fileInputRef.current.value = '';
    }
  };

  return (
    <div className="flex flex-col h-full bg-white text-gray-800 border-b border-gray-100">
      <div className="border-b border-gray-100 p-4 shrink-0 flex items-center justify-between">
        <h2 className="font-semibold text-gray-800 flex items-center gap-2">
          <FileText className="w-5 h-5 text-indigo-500" />
          目标范文解析库
        </h2>
      </div>

      <div className="flex-1 p-4 flex flex-col items-center justify-center relative">
        {isUploading && (
          <div className="absolute inset-0 z-10 bg-white/80 backdrop-blur-sm flex flex-col items-center justify-center rounded-lg">
            <Loader2 className="w-8 h-8 text-indigo-500 animate-spin mb-2" />
            <span className="text-sm font-medium text-gray-600">正在剥离大纲与样式...</span>
          </div>
        )}

        {templateSections.length > 0 ? (
          <div className="w-full bg-emerald-50 border border-emerald-100 rounded-xl p-5 flex flex-col items-center text-center shadow-sm relative overflow-hidden group">
            <div className="absolute -right-4 -top-4 w-16 h-16 bg-emerald-100 rounded-full opacity-50 group-hover:scale-150 transition-transform duration-500" />
            <CheckCircle2 className="w-10 h-10 text-emerald-500 mb-3 relative z-10" />
            <h3 className="font-medium text-gray-900 text-sm mb-1 relative z-10 w-full truncate px-2" title={originalTemplateName || templateTitle}>
              {originalTemplateName || templateTitle}
            </h3>
            <p className="text-xs text-gray-500 mb-4 relative z-10">共成功挂载 {templateSections.length} 个骨干节点</p>
            
            {canWrite && (
              <>
                <input type="file" ref={fileInputRef} onChange={handleTemplateUpload} hidden />
                <button 
                  onClick={() => fileInputRef.current?.click()}
                  className="px-4 py-2 bg-white border border-gray-200 text-gray-700 rounded-lg text-xs font-medium hover:bg-gray-50 hover:text-indigo-600 transition-colors shadow-sm relative z-10 flex items-center gap-2"
                >
                  <UploadCloud className="w-4 h-4" /> 更换大纲模板
                </button>
              </>
            )}
          </div>
        ) : (
          <div 
            onClick={() => canWrite && fileInputRef.current?.click()}
            className={`w-full h-full min-h-[160px] border-2 border-dashed border-gray-200 rounded-xl flex flex-col items-center justify-center transition-all group p-4 text-center ${canWrite ? 'cursor-pointer hover:border-indigo-400 hover:bg-indigo-50/50' : 'cursor-default opacity-60'}`}
          >
            <input type="file" ref={fileInputRef} onChange={handleTemplateUpload} hidden />
            <div className={`w-12 h-12 bg-gray-50 rounded-full flex items-center justify-center mb-3 transition-colors duration-300 ${canWrite ? 'group-hover:bg-indigo-100 group-hover:scale-110' : ''}`}>
              <UploadCloud className={`w-6 h-6 text-gray-400 ${canWrite ? 'group-hover:text-indigo-600' : ''}`} />
            </div>
            <h3 className={`text-sm font-medium text-gray-700 mb-1 ${canWrite ? 'group-hover:text-indigo-700' : ''}`}>{canWrite ? '上传大纲模板 (.docx)' : '无大纲模板（仅项目所有者可上传）'}</h3>
            {canWrite && <p className="text-xs text-gray-400 px-4">拖拽或点击上传红头文件，提取章节大纲替换中央画布的架构</p>}
          </div>
        )}
      </div>
    </div>
  );
}
