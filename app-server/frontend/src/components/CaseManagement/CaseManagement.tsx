import { useState, useEffect } from 'react';
import { Sparkles, Play, Copy, Loader2, ClipboardList, CheckCircle2 } from 'lucide-react';
import { useProjectStore } from '../../store/projectStore';
import { useAuthStore } from '../../store/authStore';
import { CASE_STAGES, type AITool } from './caseData';
import useCaseAI from './useCaseAI';

const API_BASE = import.meta.env.VITE_API_BASE || '';

export default function CaseManagement({ projectId, canWrite = true }: { projectId: string; canWrite?: boolean }) {
  const { getAuthHeaders } = useAuthStore();
  const checkedFileIds = useProjectStore(state => state.checkedFileIds);
  const triggerRefresh = useProjectStore(state => state.triggerRefresh);
  
  const [overview, setOverview] = useState('');
  const [isEditingOverview, setIsEditingOverview] = useState(false);
  const [activeStageId, setActiveStageId] = useState('1');
  const [stageStatuses, setStageStatuses] = useState<Record<string, string>>({
    '1': '进行中', '2': '待启动', '3': '待启动', '4': '待启动', '5': '待启动'
  });

  const { isGenerating, runTool, generateOverview } = useCaseAI(projectId);
  const [selectedTool, setSelectedTool] = useState<AITool | null>(null);
  const [editorContent, setEditorContent] = useState('');
  const [isSavingDoc, setIsSavingDoc] = useState(false);

  // 加载元数据
  useEffect(() => {
    const loadMetadata = async () => {
      try {
        const res = await fetch(`${API_BASE}/api/projects/${projectId}`, { headers: getAuthHeaders() });
        if (res.ok) {
          const data = await res.json();
          const meta = data.metadata || {};
          if (meta.caseOverview) setOverview(meta.caseOverview);
          if (meta.caseProcesses) {
            try { setStageStatuses(JSON.parse(meta.caseProcesses)); } catch {}
          }
        }
      } catch {}
    };
    if (projectId) loadMetadata();
  }, [projectId]);

  // 保存元数据
  const saveMetadata = async (newOverview: string, newStatuses: Record<string, string>) => {
    try {
      await fetch(`${API_BASE}/api/projects/${projectId}`, {
        method: 'PUT',
        headers: { ...getAuthHeaders(), 'Content-Type': 'application/json' },
        body: JSON.stringify({
          metadata: { caseOverview: newOverview, caseProcesses: JSON.stringify(newStatuses) }
        })
      });
    } catch {}
  };

  const handleStatusChange = (stageId: string, status: string) => {
    const updated = { ...stageStatuses, [stageId]: status };
    setStageStatuses(updated);
    saveMetadata(overview, updated);
  };

  const handleSaveOverview = () => {
    setIsEditingOverview(false);
    saveMetadata(overview, stageStatuses);
  };

  const handleRunTool = (tool: AITool) => {
    if (checkedFileIds.length === 0) {
      alert('请先在左侧树状卷宗中勾选供 AI 参考的文件！');
      return;
    }
    setSelectedTool(tool);
    runTool(tool.prompt, (text) => setEditorContent(text));
  };

  const handleSaveToDocs = async () => {
    if (!editorContent.trim() || !selectedTool) return;
    setIsSavingDoc(true);
    try {
      const docId = `case-doc-${Date.now()}`;
      const docData = {
        id: docId,
        title: `${selectedTool.defaultTitle}.docx`,
        content: `# ${selectedTool.defaultTitle}\n\n${editorContent}`,
        timestamp: Date.now(),
        tokens: editorContent.length,
        isAutoSave: false,
        sections: [{ id: `sec-${Date.now()}`, title: selectedTool.name, level: 1, content: editorContent.replace(/\n/g, '<br/>') }]
      };
      const res = await fetch(`${API_BASE}/api/projects/${projectId}/documents`, {
        method: 'POST',
        headers: { ...getAuthHeaders(), 'Content-Type': 'application/json' },
        body: JSON.stringify(docData)
      });
      if (res.ok) {
        alert('🎉 文档已成功归档到本项目素材库中！');
        triggerRefresh();
      } else {
        alert('归档失败，请重试');
      }
    } catch {
      alert('归档异常');
    } finally {
      setIsSavingDoc(false);
    }
  };

  const activeStage = CASE_STAGES.find(s => s.id === activeStageId)!;

  return (
    <div className="flex h-full w-full bg-stone-50 text-gray-800 text-xs overflow-hidden">
      {/* 左栏 */}
      <div className="w-[320px] shrink-0 border-r border-[#E0DCD5] flex flex-col bg-white overflow-y-auto p-4 gap-4">
        {/* 项目概览 */}
        <div className="bg-[#F9F8F6] rounded-xl p-3 border border-[#EBE8E2] flex flex-col gap-2 relative">
          <div className="flex items-center justify-between">
            <span className="font-semibold text-[13px] text-gray-700 flex items-center gap-1">📋 项目基本概览</span>
            {canWrite && (
              <button
                onClick={() => {
                  if (isEditingOverview) handleSaveOverview();
                  else setIsEditingOverview(true);
                }}
                className="text-indigo-600 hover:text-indigo-800 font-medium cursor-pointer"
              >
                {isEditingOverview ? '保存' : '编辑'}
              </button>
            )}
          </div>
          {isEditingOverview ? (
            <textarea
              value={overview}
              onChange={e => setOverview(e.target.value)}
              className="w-full bg-white border border-[#E0DCD5] rounded p-2 focus:outline-none focus:ring-1 focus:ring-[#8B7355] h-36 text-xs resize-none"
              placeholder="请输入项目概述或点击下方AI生成..."
            />
          ) : (
            <div className="text-gray-600 leading-relaxed text-[11px] whitespace-pre-wrap min-h-[60px] max-h-56 overflow-y-auto">
              {overview || <span className="text-stone-400 italic">暂无概览，请编辑或使用 AI 生成</span>}
            </div>
          )}
          {canWrite && !isEditingOverview && (
            <button
              onClick={() => generateOverview((text) => { setOverview(text); saveMetadata(text, stageStatuses); })}
              disabled={isGenerating}
              className="w-full py-1.5 border border-dashed border-[#8B7355] text-[#8B7355] hover:bg-[#8B7355]/5 rounded flex items-center justify-center gap-1 transition-all cursor-pointer font-medium disabled:opacity-50"
            >
              {isGenerating ? <Loader2 className="w-3 h-3 animate-spin" /> : <Sparkles className="w-3 h-3" />}
              <span>一键 AI 提炼概览</span>
            </button>
          )}
        </div>

        {/* 阶段进度列表 */}
        <div className="flex flex-col gap-2">
          <div className="font-semibold text-[13px] text-gray-700 mb-1 flex items-center gap-1">🚀 项目流程推进</div>
          <div className="space-y-2">
            {CASE_STAGES.map((stage, idx) => {
              const isActive = stage.id === activeStageId;
              const status = stageStatuses[stage.id] || '待启动';
              const statusColors: Record<string, string> = {
                '已完成': 'bg-emerald-50 text-emerald-700 border-emerald-200',
                '进行中': 'bg-indigo-50 text-indigo-700 border-indigo-200',
                '待启动': 'bg-stone-50 text-stone-500 border-stone-200'
              };

              return (
                <div
                  key={stage.id}
                  onClick={() => setActiveStageId(stage.id)}
                  className={`p-3 rounded-xl border transition-all cursor-pointer flex flex-col gap-2 hover:scale-[1.01] ${
                    isActive 
                      ? 'border-[#8B7355] bg-[#8B7355]/5 shadow-sm' 
                      : 'border-transparent bg-white hover:bg-stone-50 border border-stone-200/60'
                  }`}
                >
                  <div className="flex items-center justify-between">
                    <span className={`font-medium text-xs ${isActive ? 'text-[#8B7355] font-semibold' : 'text-gray-700'}`}>
                      {idx + 1}. {stage.name}
                    </span>
                    <select
                      value={status}
                      onClick={e => e.stopPropagation()}
                      onChange={e => handleStatusChange(stage.id, e.target.value)}
                      className={`px-1.5 py-0.5 rounded text-[10px] border outline-none cursor-pointer ${statusColors[status]}`}
                    >
                      <option value="待启动">待启动</option>
                      <option value="进行中">进行中</option>
                      <option value="已完成">已完成</option>
                    </select>
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      </div>

      {/* 右栏 */}
      <div className="flex-1 flex flex-col bg-[#F9F8F6] p-5 overflow-hidden gap-4">
        {/* 阶段指引 */}
        <div className="bg-white border border-[#E0DCD5] rounded-2xl p-4 shadow-sm shrink-0 flex flex-col gap-1.5">
          <h2 className="text-[14px] font-bold text-gray-800 flex items-center gap-1.5">
            <ClipboardList className="w-4 h-4 text-[#8B7355]" />
            项目推进阶段：{activeStage.name}
          </h2>
          <p className="text-gray-600 leading-relaxed text-[11px]">{activeStage.target}</p>
        </div>

        {/* AI 工作室与生成画布 */}
        <div className="flex-1 flex gap-4 overflow-hidden">
          {/* AI 专属工具卡片 */}
          <div className="w-[240px] shrink-0 flex flex-col gap-3 overflow-y-auto pr-1">
            <span className="font-semibold text-gray-700 flex items-center gap-1">✨ AI 智能赋能工具</span>
            {activeStage.tools.map(tool => (
              <div
                key={tool.id}
                className="bg-white border border-[#EBE8E2] rounded-xl p-3.5 shadow-sm flex flex-col gap-2 justify-between hover:shadow-md transition-shadow"
              >
                <div className="flex flex-col gap-1">
                  <div className="font-semibold text-gray-800">{tool.name}</div>
                  <div className="text-gray-500 leading-normal text-[10px]">{tool.description}</div>
                </div>
                <button
                  onClick={() => handleRunTool(tool)}
                  disabled={isGenerating}
                  className="mt-2 py-1.5 px-3 bg-[#8B7355] hover:bg-[#705c43] text-white rounded-lg flex items-center justify-center gap-1.5 font-medium transition-all cursor-pointer disabled:opacity-50"
                >
                  <Play className="w-3 h-3 fill-white" />
                  <span>智能运行</span>
                </button>
              </div>
            ))}
          </div>

          {/* 生成预览区 */}
          <div className="flex-1 bg-white border border-[#E0DCD5] rounded-2xl shadow-sm flex flex-col overflow-hidden relative">
            <div className="px-4 py-3 border-b border-[#E0DCD5] flex justify-between items-center bg-[#F9F8F6]">
              <span className="font-bold text-gray-800 flex items-center gap-1">
                📝 AI 文档生成画布
                {selectedTool && <span className="text-[11px] font-normal text-stone-500">（{selectedTool.name}）</span>}
              </span>
              <div className="flex gap-2">
                <button
                  onClick={() => {
                    navigator.clipboard.writeText(editorContent);
                    alert('复制成功！');
                  }}
                  disabled={!editorContent}
                  className="px-2.5 py-1.5 hover:bg-stone-200 border border-stone-200 rounded-lg flex items-center gap-1 cursor-pointer transition-colors disabled:opacity-40"
                >
                  <Copy className="w-3.5 h-3.5" />
                  <span>复制</span>
                </button>
                <button
                  onClick={handleSaveToDocs}
                  disabled={!editorContent || isSavingDoc}
                  className="px-3 py-1.5 bg-indigo-600 hover:bg-indigo-700 text-white rounded-lg flex items-center gap-1 font-semibold cursor-pointer transition-colors disabled:opacity-40"
                >
                  {isSavingDoc ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <CheckCircle2 className="w-3.5 h-3.5" />}
                  <span>保存为项目文档</span>
                </button>
              </div>
            </div>

            {/* 编辑与内容预览区 */}
            <div className="flex-1 p-4 overflow-y-auto relative bg-[#FCFAF7]">
              {isGenerating && !editorContent && (
                <div className="absolute inset-0 flex items-center justify-center bg-[#FCFAF7]/80 z-10">
                  <div className="flex flex-col items-center gap-2 text-stone-500 font-medium">
                    <Loader2 className="w-6 h-6 animate-spin text-[#8B7355]" />
                    <span>大模型分析拼装中...</span>
                  </div>
                </div>
              )}
              <textarea
                value={editorContent}
                onChange={e => setEditorContent(e.target.value)}
                className="w-full h-full bg-transparent border-none outline-none resize-none prose prose-sm text-gray-700 font-sans leading-relaxed whitespace-pre-wrap"
                placeholder="点击左侧「智能运行」启动文案助理，自动基于项目素材和自定义策略撰写符合行业实践要求的管理规范、分析报告或文档大纲..."
              />
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
