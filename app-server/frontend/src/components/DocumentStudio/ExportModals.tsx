/**
 * ExportModals.tsx — 文档导出弹窗 + 莫兰迪封面设计弹窗
 *
 * WHY: 从 DocumentStudio.tsx 解耦出来。
 *      导出与封面是独立的业务流程，不应与编辑器核心逻辑混杂。
 *      包含轮询后端 /docx-status 进行状态追踪、拉取文件、封面预览等逻辑。
 */
import { useState, useCallback } from 'react';
import { Download, FileDown, X, Loader2, Palette, Wand2, Image as ImageIcon } from 'lucide-react';
import { useAuthStore } from '../../store/authStore';
import type { DocSection } from './types';

const API_BASE = import.meta.env.VITE_API_BASE || '';

interface ExportModalsProps {
  projectId: string;
  templateTitle: string;
  sections: DocSection[];
  showToast: (message: string, type: 'success' | 'warning' | 'error') => void;
}

export default function ExportModals({ projectId, templateTitle, sections, showToast }: ExportModalsProps) {
  const [isExporting, setIsExporting] = useState(false);
  const [exportPercent, setExportPercent] = useState(-1);
  const [exportMessage, setExportMessage] = useState('');
  const [showExportModal, setShowExportModal] = useState(false);
  const [showCoverModal, setShowCoverModal] = useState(false);
  const [coverOrgName, setCoverOrgName] = useState('智能体');
  const [coverDateStr, setCoverDateStr] = useState('');
  const [coverPreview, setCoverPreview] = useState<string | null>(null);
  const [isCoverLoading, setIsCoverLoading] = useState(false);
  const { getAuthHeaders } = useAuthStore();

  const completedCount = sections.filter((s: DocSection) => {
    const plain = s.content.replace(/<[^>]*>?/gm, '').trim();
    return plain.length > 5;
  }).length;
  const progressPercent = sections.length > 0 ? Math.round((completedCount / sections.length) * 100) : 0;

  // WHY: 打开导出确认弹窗，同时触发封面预览生成
  const fetchCoverPreview = useCallback(async () => {
    setCoverPreview(null);
    setIsCoverLoading(true);
    try {
      const res = await fetch(`${API_BASE}/api/export/cover-preview`, {
        method: 'POST',
        headers: { ...getAuthHeaders(), 'Content-Type': 'application/json' },
        body: JSON.stringify({ title: templateTitle, org_name: coverOrgName, date_str: coverDateStr }),
      });
      if (res.ok) {
        const data = await res.json();
        setCoverPreview(data.image);
      }
    } catch (err) {
      console.warn('封面预览加载失败', err);
    } finally {
      setIsCoverLoading(false);
    }
  }, [templateTitle, coverOrgName, coverDateStr, getAuthHeaders]);

  const handleOpenExportModal = useCallback(async () => {
    setShowExportModal(true);
    await fetchCoverPreview();
  }, [fetchCoverPreview]);

  const handleExport = async () => {
    try {
      setIsExporting(true);
      setExportPercent(0);
      setExportMessage('初始化列队引擎...');
      
      const res = await fetch(`${API_BASE}/api/export/docx`, {
        method: 'POST',
        headers: {
          ...getAuthHeaders(),
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          project_id: projectId || 'default',
          filename: templateTitle,
          sections: sections
        })
      });

      if (!res.ok) throw new Error('提交排版任务失败');
      const data = await res.json();
      const taskId = data.task_id;

      // WHY: FRP HTTP 代理会缓冲 SSE 流式响应，导致浏览器 EventSource 永远收不到完成事件。
      //      改为 HTTP 轮询 /docx-status 端点，每 800ms 查询一次，100% 兼容所有代理层。
      const pollProgress = async () => {
        const maxRetries = 120; // 最多轮询 120 次 ≈ 96 秒
        for (let i = 0; i < maxRetries; i++) {
          try {
            const statusRes = await fetch(`${API_BASE}/api/export/docx-status?task_id=${taskId}`, {
              headers: getAuthHeaders()
            });
            if (!statusRes.ok) {
              await new Promise(r => setTimeout(r, 800));
              continue;
            }
            const eventData = await statusRes.json();
            setExportPercent(eventData.percent);
            setExportMessage(eventData.message);

            if (eventData.status === 'success') {
              showToast(`✅ 导出成功，开始下载`, 'success');
              
              // 执行文件下载
              const downloadRes = await fetch(`${API_BASE}/api/export/download/${taskId}`, {
                 headers: getAuthHeaders()
              });
              if (!downloadRes.ok) {
                showToast('文件流拉取失败', 'error');
                setIsExporting(false);
                return;
              }
              
              const blob = await downloadRes.blob();
              const url = window.URL.createObjectURL(blob);
              const a = document.createElement('a');
              a.href = url;
              a.download = `AI生成_排版_${templateTitle}.docx`;
              document.body.appendChild(a);
              a.click();
              window.URL.revokeObjectURL(url);
              document.body.removeChild(a);
              
              setIsExporting(false);
              setShowExportModal(false);
              return;
            } else if (eventData.status === 'failed') {
              showToast(`❌ C# 排版引擎抛出错误: ${eventData.message}`, 'error');
              setIsExporting(false);
              setShowExportModal(false);
              return;
            }
          } catch (pollErr) {
            console.warn('轮询异常，重试中...', pollErr);
          }
          await new Promise(r => setTimeout(r, 800));
        }
        // 超时
        showToast('❌ 导出超时，请重试', 'error');
        setIsExporting(false);
      };
      
      pollProgress();
      
    } catch (err) {
      console.error(err);
      showToast('❌ 导出提交失败，排版服务可能拥挤', 'error');
      setIsExporting(false);
    }
  };

  return (
    <>
      {/* 触发按钮组 — 嵌入父组件的 Header 工具栏 */}
      <button onClick={() => { setShowCoverModal(true); fetchCoverPreview(); }} className="px-3 py-1.5 border border-pink-200 text-pink-600 rounded text-xs font-medium hover:bg-pink-50 flex items-center gap-1.5 transition-colors">
        <Palette className="w-3.5 h-3.5" /> 封面
      </button>
      <button onClick={handleOpenExportModal} disabled={isExporting || sections.length === 0} className="px-3 py-1.5 border border-blue-600 text-blue-600 rounded text-xs font-medium hover:bg-blue-50 flex items-center gap-1 transition-colors disabled:opacity-50">
        {isExporting ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Download className="w-3.5 h-3.5" />} 导出
      </button>

      {/* WHY: 导出确认弹窗 — 展示封面预览缩略图，让用户确认外观后再导出 */}
      {showExportModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm animate-[fadeIn_0.2s_ease-out]">
          <div className="bg-white rounded-2xl shadow-2xl border border-gray-200 w-[520px] max-h-[90vh] overflow-hidden flex flex-col animate-[scaleIn_0.25s_ease-out]">
            {/* 弹窗标题栏 */}
            <div className="flex items-center justify-between px-6 py-4 border-b border-gray-100">
              <div className="flex items-center gap-2.5">
                <div className="w-8 h-8 rounded-lg bg-blue-50 flex items-center justify-center">
                  <FileDown className="w-4 h-4 text-blue-600" />
                </div>
                <div>
                  <h3 className="text-sm font-semibold text-gray-900">导出确认</h3>
                  <p className="text-[11px] text-gray-400">预览封面，确认后生成 Word 文档</p>
                </div>
              </div>
              <button onClick={() => setShowExportModal(false)} className="p-1.5 text-gray-400 hover:text-gray-600 hover:bg-gray-100 rounded-lg transition-colors">
                <X className="w-4 h-4" />
              </button>
            </div>

            {/* 封面预览区 */}
            <div className="px-6 py-5 flex-1 overflow-y-auto">
              <div className="text-xs font-medium text-gray-500 mb-3 flex items-center gap-1.5">
                <ImageIcon className="w-3.5 h-3.5" /> 莫兰迪封面预览
              </div>
              <div className="flex justify-center">
                <div className="w-[240px] bg-gray-50 rounded-lg border border-gray-200 overflow-hidden shadow-sm">
                  {isCoverLoading ? (
                    <div className="h-[340px] flex items-center justify-center">
                      <div className="flex flex-col items-center gap-2">
                        <Loader2 className="w-6 h-6 text-blue-400 animate-spin" />
                        <span className="text-[11px] text-gray-400">封面生成中…</span>
                      </div>
                    </div>
                  ) : coverPreview ? (
                    <img src={coverPreview} alt="封面预览" className="w-full h-auto" />
                  ) : (
                    <div className="h-[340px] flex items-center justify-center text-gray-400 text-xs">
                      封面预览不可用
                    </div>
                  )}
                </div>
              </div>

              {/* 导出信息摘要 */}
              <div className="mt-4 bg-gray-50 rounded-lg p-3 text-xs text-gray-600 space-y-1.5">
                <div className="flex justify-between">
                  <span className="text-gray-400">文档标题</span>
                  <span className="font-medium text-gray-700 truncate max-w-[280px]">{templateTitle}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-400">章节数量</span>
                  <span className="font-medium text-gray-700">{sections.length} 个章节</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-400">已完成</span>
                  <span className="font-medium text-green-600">{completedCount}/{sections.length} ({progressPercent}%)</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-gray-400">增值功能</span>
                  <span className="font-medium text-gray-700">AI 审阅批注 + 图表自动插入 + 质检</span>
                </div>
              </div>
            </div>

            {/* 底部按钮区 */}
            <div className="flex items-center justify-end gap-3 px-6 py-4 border-t border-gray-100 bg-gray-50/50">
              <button
                onClick={() => setShowExportModal(false)}
                className="px-4 py-2 text-sm text-gray-600 hover:text-gray-800 hover:bg-gray-100 rounded-lg transition-colors"
              >
                取消
              </button>
              <button
                onClick={handleExport}
                disabled={isExporting}
                className="px-5 py-2 text-sm font-medium text-white bg-blue-600 hover:bg-blue-700 rounded-lg shadow-sm transition-colors flex items-center gap-2 disabled:opacity-50 relative overflow-hidden"
              >
                {isExporting ? <Loader2 className="w-3.5 h-3.5 animate-spin relative z-10" /> : <Download className="w-3.5 h-3.5 relative z-10" />}
                <span className="relative z-10">{isExporting ? '本地排版中...' : '确认导出'}</span>
                
                {/* 注入进度条背景填充效应 */}
                {isExporting && exportPercent >= 0 && (
                  <div 
                    className="absolute left-0 bottom-0 top-0 bg-blue-500 z-0 transition-all duration-300 pointer-events-none" 
                    style={{ width: `${exportPercent}%` }}
                  />
                )}
              </button>
            </div>
            
            {/* 注入文本进度提示 overlay */}
            {isExporting && exportMessage && (
               <div className="absolute bottom-16 left-6 text-xs text-blue-600 flex items-center gap-1.5 animate-pulse bg-blue-50 px-2 py-1 rounded">
                 <span className="relative flex h-2 w-2">
                   <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-blue-400 opacity-75"></span>
                   <span className="relative inline-flex rounded-full h-2 w-2 bg-blue-500"></span>
                 </span>
                 {exportMessage} {exportPercent}%
               </div>
            )}
            
          </div>
        </div>
      )}

      {/* WHY: 封面设计专属控制面板 */}
      {showCoverModal && (
        <div className="fixed inset-0 z-[60] flex items-center justify-center bg-black/40 backdrop-blur-sm animate-[fadeIn_0.2s_ease-out]">
          <div className="bg-white rounded-2xl shadow-2xl border border-gray-200 w-[780px] max-h-[90vh] overflow-hidden flex animate-[scaleIn_0.25s_ease-out]">
            
            {/* 左侧配置栏 */}
            <div className="w-[320px] bg-gray-50 border-r border-gray-100 flex flex-col items-stretch">
              <div className="px-6 py-5 border-b border-gray-200 bg-white">
                 <div className="flex items-center gap-2 mb-1">
                   <Palette className="w-5 h-5 text-pink-500" />
                   <h3 className="text-base font-bold text-gray-900">封面美学实验室</h3>
                 </div>
                 <p className="text-xs text-gray-400">实时调整参数，所见即所得地生成高级莫兰迪封面。</p>
              </div>
              <div className="flex-1 overflow-y-auto px-6 py-6 space-y-6">
                 <div>
                   <label className="block text-xs font-semibold text-gray-700 mb-2">报告大标题</label>
                   <input disabled value={templateTitle} className="w-full bg-gray-100 text-gray-500 border border-gray-200 rounded-lg px-3 py-2 text-sm cursor-not-allowed" />
                   <p className="text-[10px] text-gray-400 mt-1">如需修改标题，请返回主界面顶部修改。</p>
                 </div>
                 <div>
                   <label className="block text-xs font-semibold text-gray-700 mb-2">单位/个人 (落款)</label>
                   <input type="text" value={coverOrgName} onChange={(e) => setCoverOrgName(e.target.value)} placeholder="智能体" className="w-full bg-white border border-gray-300 focus:border-pink-400 focus:ring-1 focus:ring-pink-400 rounded-lg px-3 py-2 text-sm outline-none transition-all" />
                 </div>
                 <div>
                   <label className="block text-xs font-semibold text-gray-700 mb-2">覆盖日期 (可选)</label>
                   <input type="text" value={coverDateStr} onChange={(e) => setCoverDateStr(e.target.value)} placeholder="如果不填，则默认为当前系统年月" className="w-full bg-white border border-gray-300 focus:border-pink-400 focus:ring-1 focus:ring-pink-400 rounded-lg px-3 py-2 text-sm outline-none transition-all" />
                 </div>
                 <button onClick={fetchCoverPreview} disabled={isCoverLoading} className="w-full py-2.5 mt-2 bg-pink-100 hover:bg-pink-200 text-pink-700 font-medium rounded-lg text-sm transition-colors flex items-center justify-center gap-2">
                    {isCoverLoading ? <Loader2 className="w-4 h-4 animate-spin" /> : <Wand2 className="w-4 h-4" />}
                    重新渲染预览图
                 </button>
              </div>
            </div>

            {/* 右侧实时预览 */}
            <div className="flex-1 p-6 flex flex-col bg-gray-200/50 relative">
               <button onClick={() => setShowCoverModal(false)} className="absolute top-4 right-4 p-2 bg-white/80 hover:bg-white text-gray-500 hover:text-gray-800 rounded-full shadow-sm transition-all z-10">
                 <X className="w-4 h-4" />
               </button>
               <div className="flex-1 flex items-center justify-center">
                  <div className="w-[300px] h-[424px] bg-white shadow-xl rotate-[1deg] hover:rotate-0 transition-transform duration-500 overflow-hidden relative group">
                    {isCoverLoading && (
                      <div className="absolute inset-0 z-10 bg-white/60 backdrop-blur-sm flex flex-col items-center justify-center">
                         <Loader2 className="w-8 h-8 text-pink-400 animate-spin mb-3" />
                         <span className="text-xs text-gray-500 font-medium tracking-widest">魔法重绘中...</span>
                      </div>
                    )}
                    {coverPreview ? (
                      <img src={coverPreview} alt="封面预览" className="w-full h-full object-cover" />
                    ) : (
                      <div className="w-full h-full flex items-center justify-center text-gray-400 text-sm">暂无预览</div>
                    )}
                  </div>
               </div>
            </div>

          </div>
        </div>
      )}
    </>
  );
}
