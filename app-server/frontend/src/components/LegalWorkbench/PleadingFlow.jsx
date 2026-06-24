import React, { useState, useEffect, useRef } from 'react';
import { createPortal } from 'react-dom';
import { useAuthStore } from '../../store/authStore';
import { useProjectStore } from '../../store/projectStore';
import { Play, CheckCircle2, Copy, ChevronRight, Save, AlertTriangle } from 'lucide-react';

const STAGES = {
  pleading_drafting: [
    { id: "fact_sorting", name: "事实整理与梳理" },
    { id: "procedural_review", name: "程序性审查与抗辩" },
    { id: "substantive_analysis", name: "实体法律分析（三段论）" },
    { id: "evidence_analysis", name: "证据分析与质证准备" },
    { id: "strategy_formulation", name: "答辩策略制定" },
    { id: "document_drafting", name: "正式答辩状撰写" },
  ],
  complaint_drafting: [
    { id: "fact_sorting", name: "事实整理与梳理" },
    { id: "claim_design", name: "诉讼请求与依据设计" },
    { id: "procedural_review", name: "程序与管辖权审查" },
    { id: "evidence_chain", name: "证据清单与证据链构建" },
    { id: "document_drafting", name: "正式起诉状撰写" },
  ]
};

export default function PleadingFlow({ projectId, canWrite, skillType }) {
  const { getAuthHeaders } = useAuthStore();
  const API_BASE = import.meta.env.VITE_API_BASE || '';
  const [collaborative, setCollaborative] = useState(false);
  const [showConfirmModal, setShowConfirmModal] = useState(false);
  const [saveDocInfo, setSaveDocInfo] = useState(null);
  const publicSettings = useProjectStore(state => state.publicSettings);
  const fetchPublicSettings = useProjectStore(state => state.fetchPublicSettings);

  useEffect(() => {
    if (!publicSettings) {
      fetchPublicSettings();
    }
  }, [publicSettings, fetchPublicSettings]);

  useEffect(() => {
    if (publicSettings) {
      setCollaborative(publicSettings.collab_pleading_enabled === 'true');
    }
  }, [publicSettings]);

  const checkedFileIds = useProjectStore(state => state.checkedFileIds);
  const checkedRefIds = useProjectStore(state => state.checkedRefIds);
  const selectedFileIds = [...checkedFileIds, ...checkedRefIds];

  const [skillsList, setSkillsList] = useState([]);
  const [currentStageIdx, setCurrentStageIdx] = useState(() => {
    try {
      const cached = localStorage.getItem(`pleading_flow_stage_idx_${projectId}_${skillType}`);
      return cached ? parseInt(cached, 10) : 0;
    } catch {
      return 0;
    }
  });
  const [stageOutputs, setStageOutputs] = useState(() => {
    try {
      const cached = localStorage.getItem(`pleading_flow_outputs_${projectId}_${skillType}`);
      const raw = cached ? JSON.parse(cached) : {};
      const validStageIds = (STAGES[skillType] || STAGES.pleading_drafting).map(s => s.id);
      const filtered = {};
      Object.keys(raw).forEach(k => {
        if (validStageIds.includes(k)) {
          const val = raw[k];
          if (typeof val === 'string' && !val.includes('❌') && !val.includes('发生错误')) {
            filtered[k] = val;
          }
        }
      });
      return filtered;
    } catch {
      return {};
    }
  });
  const [isGenerating, setIsGenerating] = useState(false);
  const isGeneratingRef = useRef(false);
  const [isAutoGenerating, setIsAutoGenerating] = useState(false);
  const isAutoGeneratingRef = useRef(false);
  const textareaRef = useRef(null);
  const abortControllerRef = useRef(null);

  const handleStopGeneration = () => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }
    isAutoGeneratingRef.current = false;
    setIsAutoGenerating(false);
    isGeneratingRef.current = false;
    setIsGenerating(false);
  };


  // 保存 stageOutputs 到 LocalStorage 缓存
  useEffect(() => {
    try {
      localStorage.setItem(`pleading_flow_outputs_${projectId}_${skillType}`, JSON.stringify(stageOutputs));
    } catch (e) {
      console.warn('写入步骤数据缓存失败', e);
    }
  }, [stageOutputs, projectId, skillType]);

  // 保存 currentStageIdx 到 LocalStorage 缓存
  useEffect(() => {
    try {
      localStorage.setItem(`pleading_flow_stage_idx_${projectId}_${skillType}`, currentStageIdx.toString());
    } catch (e) {
      console.warn('写入步骤索引缓存失败', e);
    }
  }, [currentStageIdx, projectId, skillType]);

  // 1. 加载法律技能列表
  useEffect(() => {
    const loadSkills = async () => {
      try {
        const res = await fetch(`${API_BASE}/api/legal/skills`, { headers: getAuthHeaders() });
        const data = res.ok ? await res.json() : {};
        if (data.skills) {
          setSkillsList(data.skills);
        }
      } catch (err) {
        console.error('加载法律技能列表失败', err);
      }
    };
    loadSkills();
  }, []);

  const stages = skillsList.find(s => s.id === skillType)?.stages || STAGES[skillType] || STAGES.pleading_drafting;
  const activeStage = stages[currentStageIdx] || stages[0] || { id: 'default', name: '分析生成' };

  // 监听流式字符写入，在生成中实时滚动文本框到底部
  useEffect(() => {
    if ((isGenerating || isAutoGenerating) && textareaRef.current) {
      const el = textareaRef.current;
      const timer = setTimeout(() => {
        el.scrollTop = el.scrollHeight;
      }, 30);
      return () => clearTimeout(timer);
    }
  }, [stageOutputs, activeStage.id, isGenerating, isAutoGenerating]);

  // 判定指定阶段是否真正完成（有输出、无报错且未在生成中）
  const isStageCompleted = (stageId) => {
    const content = stageOutputs[stageId];
    if (!content) return false;
    if (content.includes('❌ 发生错误')) return false;
    const stageIdx = stages.findIndex(s => s.id === stageId);
    if ((isGenerating || isGeneratingRef.current || isAutoGenerating || isAutoGeneratingRef.current) && stageIdx === currentStageIdx) return false;
    return true;
  };

  // 清洗缓存中的脏键和历史报错残留
  const cleanCachedOutputs = (rawObj) => {
    const validStageIds = stages.map(s => s.id);
    const filtered = {};
    Object.keys(rawObj || {}).forEach(k => {
      if (validStageIds.includes(k)) {
        const val = rawObj[k];
        if (typeof val === 'string' && !val.includes('❌') && !val.includes('发生错误')) {
          filtered[k] = val;
        }
      }
    });
    return filtered;
  };

  // 2. 技能或项目改变，从 LocalStorage 恢复数据
  useEffect(() => {
    try {
      const cachedIdx = localStorage.getItem(`pleading_flow_stage_idx_${projectId}_${skillType}`);
      setCurrentStageIdx(cachedIdx ? parseInt(cachedIdx, 10) : 0);
      
      const cached = localStorage.getItem(`pleading_flow_outputs_${projectId}_${skillType}`);
      const raw = cached ? JSON.parse(cached) : {};
      setStageOutputs(cleanCachedOutputs(raw));
    } catch (e) {
      setStageOutputs({});
    }
  }, [projectId, skillType]);

  // 3. 流式生成当前阶段内容（支持外部传参执行一键生成）
  const runStageAnalysis = async (targetStage = null, targetIdx = null) => {
    const runStage = targetStage || activeStage;
    const runIdx = targetIdx !== null ? targetIdx : currentStageIdx;

    if (isGenerating || isGeneratingRef.current || !runStage) return false;
    isGeneratingRef.current = true;
    setIsGenerating(true);
    setStageOutputs(prev => ({ ...prev, [runStage.id]: '' }));

    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }
    abortControllerRef.current = new AbortController();

    // WHY: 在协同模式下，由于每一步文本框内都包含 [分流] + [首稿] + [抗辩审查意见] + [最终定稿]，
    //      若直接拼入上下文会引入大量过期的冗余和质疑内容，导致后续大模型分析产生混淆。
    //      本函数利用标志图标（👑 *）逆向检索到仲裁官最终终审的位置，清洗并剥离所有过程文字，仅保留有效“定稿内容”。
    const cleanStageOutput = (text) => {
      if (!text) return '';
      const arbiterIndex = text.lastIndexOf('👑 *');
      if (arbiterIndex !== -1) {
        const titleEndIndex = text.indexOf('*', arbiterIndex + 3);
        if (titleEndIndex !== -1) {
          let contentStart = titleEndIndex + 1;
          while (contentStart < text.length && (text[contentStart] === '\n' || text[contentStart] === '\r' || text[contentStart] === ' ' || text[contentStart] === '\u200b')) {
            contentStart++;
          }
          return text.substring(contentStart).trim();
        }
      }
      return text.trim();
    };

    // 汇总前面所有阶段的输出作为上下文背景（自动清洗掉过程文本，仅传递纯定稿结论）
    const previousOutputs = stages
      .slice(0, runIdx)
      .map(st => `### ${st.name}\n${cleanStageOutput(stageOutputs[st.id] || '')}`)
      .join('\n\n');

    try {
      const res = await fetch(`${API_BASE}/api/legal/workflow/stream`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...getAuthHeaders() },
        body: JSON.stringify({
          project_id: projectId,
          file_ids: selectedFileIds,
          skill_type: skillType,
          stage_id: runStage.id,
          context_history: previousOutputs,
          collaborative: collaborative
        }),
        signal: abortControllerRef.current.signal
      });

      if (!res.ok) throw new Error('流式读取请求失败');
      const reader = res.body.getReader();
      const decoder = new TextDecoder();

      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        const chunk = decoder.decode(value);
        setStageOutputs(prev => ({
          ...prev,
          [runStage.id]: (prev[runStage.id] || '') + chunk
        }));
      }
      return true;
    } catch (e) {
      if (e.name === 'AbortError') {
        setStageOutputs(prev => ({
          ...prev,
          [runStage.id]: (prev[runStage.id] || '') + `\n\n🛑 生成已手动停止。`
        }));
      } else {
        setStageOutputs(prev => ({
          ...prev,
          [runStage.id]: (prev[runStage.id] || '') + `\n\n❌ 发生错误: ${e.message}`
        }));
      }
      return false;
    } finally {
      isGeneratingRef.current = false;
      setIsGenerating(false);
    }
  };

  // 4. 一键自动按顺序执行所有步骤的 AI 推理
  const startAutoPipeline = async () => {
    setShowConfirmModal(false);
    if (isGenerating || isGeneratingRef.current || isAutoGenerating || isAutoGeneratingRef.current) return;

    isAutoGeneratingRef.current = true;
    setIsAutoGenerating(true);

    // 一键清空所有步骤的输出以保持上下文的连贯和纯净
    const cleared = {};
    stages.forEach(st => { cleared[st.id] = ''; });
    setStageOutputs(cleared);

    try {
      for (let i = 0; i < stages.length; i++) {
        if (!isAutoGeneratingRef.current) break;
        setCurrentStageIdx(i);
        // 稍微延迟一下确保 UI 状态和 React 渲染帧同步
        await new Promise(resolve => setTimeout(resolve, 100));
        if (!isAutoGeneratingRef.current) break;
        const success = await runStageAnalysis(stages[i], i);
        if (!success) {
          if (isAutoGeneratingRef.current) {
            alert(`一键生成中断：在步骤“${stages[i].name}”执行时发生错误。`);
          }
          break;
        }
      }
    } catch (err) {
      console.error('一键生成异常', err);
    } finally {
      isAutoGeneratingRef.current = false;
      setIsAutoGenerating(false);
    }
  };

  return (
    <div className="h-full w-full bg-white dark:bg-canvas-bg flex flex-col overflow-hidden">
      {/* 顶部横向分析步骤子 Tab */}
      <div className="flex border-b border-[#e9e5de] dark:border-border-soft bg-[#faf8f5] dark:bg-outline-bg px-2 py-1.5 gap-1 overflow-x-auto select-none shrink-0 items-center justify-between">
        <div className="flex gap-0.5 items-center">
          {stages.map((st, idx) => {
            const isCurrent = idx === currentStageIdx;
            // 真正完成条件：调用统一的完成判定函数
            const isCompleted = isStageCompleted(st.id);
            // 真正解锁条件：第一步默认解锁；后续步骤要求前一步必须正常完成
            const isUnlocked = idx === 0 || isStageCompleted(stages[idx - 1].id);
            return (
              <React.Fragment key={st.id}>
                {idx > 0 && (
                  <ChevronRight 
                    className={`w-2.5 h-2.5 shrink-0 ${isUnlocked ? 'text-stone-400' : 'text-stone-300'}`} 
                  />
                )}
                <button
                  onClick={() => {
                    if (isGeneratingRef.current || isGenerating || isAutoGenerating || isAutoGeneratingRef.current) return;
                    if (!isUnlocked) return;
                    setCurrentStageIdx(idx);
                  }}
                  disabled={!isUnlocked || isGenerating || isGeneratingRef.current || isAutoGenerating || isAutoGeneratingRef.current}
                  className={`flex items-center gap-0.5 px-1.5 py-1 rounded-lg text-xs font-semibold transition-all shrink-0 select-none ${
                    isCurrent
                      ? 'bg-orange-600 text-white shadow-sm font-semibold'
                      : !isUnlocked
                        ? 'text-stone-400 cursor-not-allowed'
                        : 'text-stone-600 dark:text-text-muted hover:bg-stone-200/50 dark:hover:bg-outline-bg/40 hover:text-stone-800'
                  }`}
                >
                  {isCompleted ? (
                    <CheckCircle2 className="w-3 text-emerald-500 shrink-0" />
                  ) : (
                    <span className={`w-3 h-3 rounded-full flex items-center justify-center text-[9px] shrink-0 ${
                      !isUnlocked 
                        ? 'bg-stone-50 dark:bg-outline-bg text-stone-400 border border-stone-200 dark:border-border-soft' 
                        : 'bg-stone-200 dark:bg-outline-bg text-stone-700 dark:text-text-main'
                    }`}>
                      {idx + 1}
                    </span>
                  )}
                  {st.name}
                </button>
              </React.Fragment>
            );
          })}
          {stages.length > 0 && (
            <>
              <button
                onClick={(e) => {
                  e.preventDefault();
                  e.stopPropagation();
                  setShowConfirmModal(true);
                }}
                disabled={isGenerating || isGeneratingRef.current || isAutoGenerating || isAutoGeneratingRef.current}
                className={`flex items-center gap-0.5 px-1.5 py-1 rounded-lg text-xs font-bold transition-all shrink-0 select-none ml-1.5 shadow-sm ${
                  isAutoGenerating
                    ? 'bg-amber-100 text-amber-700 cursor-not-allowed border border-amber-200 animate-pulse'
                    : 'bg-emerald-600 hover:bg-emerald-700 text-white border border-transparent hover:scale-[1.02] active:scale-[0.98]'
                }`}
              >
                <Play className="w-3 h-3" />
                {isAutoGenerating ? '一键生成中...' : '⚡ 一键生成'}
              </button>
              <label className="flex items-center gap-0.5 cursor-pointer select-none border border-stone-200 dark:border-border-soft bg-white dark:bg-outline-bg hover:bg-stone-50 dark:hover:bg-panel-bg rounded-lg px-1.5 py-1 shrink-0 ml-1.5 text-xs font-bold text-stone-600 dark:text-text-muted shadow-sm">
                <input
                  type="checkbox"
                  checked={collaborative}
                  onChange={(e) => setCollaborative(e.target.checked)}
                  className="rounded text-emerald-600 focus:ring-emerald-500 w-3 h-3 cursor-pointer"
                />
                <span>协同</span>
              </label>
              {(isGenerating || isAutoGenerating) && (
                <button
                  onClick={(e) => {
                    e.preventDefault();
                    e.stopPropagation();
                    handleStopGeneration();
                  }}
                  className="flex items-center gap-0.5 px-1.5 py-1 rounded-lg text-xs font-bold bg-rose-600 hover:bg-rose-700 text-white border border-transparent hover:scale-[1.02] active:scale-[0.98] shrink-0 select-none ml-1.5 shadow-sm transition-all cursor-pointer"
                >
                  <span className="w-1.5 h-1.5 bg-white rounded-sm shrink-0 mr-0.5" />
                  停止
                </button>
              )}
            </>
          )}
        </div>

      </div>

      {/* 状态信息栏 */}
      <div className="px-6 py-2 bg-[#fcfbfa] dark:bg-outline-bg border-b border-[#e9e5de] dark:border-border-soft text-[10px] text-stone-500 dark:text-text-muted flex justify-between items-center shrink-0">
        <div className="flex items-center gap-3">
          <div className="flex items-center gap-1 shrink-0">
            <span className="font-semibold text-stone-700 dark:text-text-main">当前阶段：</span>
            <span className="text-amber-800 dark:text-amber-500 font-semibold">{activeStage.name}</span>
          </div>
          <button
            onClick={() => runStageAnalysis()}
            disabled={isGenerating || isGeneratingRef.current || isAutoGenerating || isAutoGeneratingRef.current || !activeStage}
            className={`flex items-center gap-1 px-3 py-1 bg-orange-600 hover:bg-orange-700 text-white rounded-lg text-[10px] font-semibold shadow-sm transition-colors select-none shrink-0 ${
              isGenerating || isAutoGenerating ? 'opacity-50 cursor-not-allowed' : ''
            }`}
          >
            <Play className="w-3 h-3" />
            {isGenerating ? '分析生成中...' : 'AI推理生成'}
          </button>
          {stageOutputs[activeStage.id] && (
            <div className="flex items-center gap-2 shrink-0 select-none">
              <button
                onClick={() => {
                  navigator.clipboard.writeText(stageOutputs[activeStage.id]);
                  alert('复制成功！');
                }}
                className="flex items-center gap-1 px-3 py-1 border border-stone-200 dark:border-border-soft hover:bg-stone-50 dark:hover:bg-outline-bg/40 text-stone-600 dark:text-text-muted rounded-lg text-[10px] font-semibold transition-colors select-none shrink-0"
              >
                <Copy className="w-3 h-3" />
                复制
              </button>

              {(() => {
                // 定义内部保存回调
                window.executeSaveDocument = async (content, docTitle) => {
                  try {
                    const docData = {
                      id: crypto.randomUUID ? crypto.randomUUID() : Math.random().toString(36).substring(2),
                      title: docTitle.trim(),
                      content: content,
                      timestamp: Date.now(),
                      tokens: content.length,
                      sections: [],
                      isAutoSave: false
                    };

                    const res = await fetch(`${API_BASE}/api/projects/${projectId || 'default'}/documents`, {
                      method: 'POST',
                      headers: { ...getAuthHeaders(), 'Content-Type': 'application/json' },
                      body: JSON.stringify(docData)
                    });

                    if (!res.ok) throw new Error('接口响应失败');
                    alert('保存成功！已同步至右侧文件列表。');
                    window.dispatchEvent(new CustomEvent('documentSaved'));
                  } catch (err) {
                    console.error('保存文档失败', err);
                    alert(`保存失败: ${err instanceof Error ? err.message : '未知错误'}`);
                  }
                };
                return null;
              })()}
              {currentStageIdx === stages.length - 1 && (
                <button
                  onClick={() => {
                    const SKILL_NAMES = {
                      complaint_drafting: '民事起诉状',
                      pleading_drafting: '民事答辩状',
                      project_opinion: '法律意见书',
                      pre_case_analysis: '委托前案件分析',
                      case_search: '案例检索分析',
                      corporate_legal: '常法服务'
                    };
                    const defaultTitle = `[生成结果]-${SKILL_NAMES[skillType] || '法律分析文档'}`;
                    setSaveDocInfo({ content: stageOutputs[activeStage.id], title: defaultTitle });
                  }}
                  disabled={isGenerating || isGeneratingRef.current || isAutoGenerating || isAutoGeneratingRef.current}
                  className="flex items-center gap-1 px-3 py-1 bg-emerald-600 hover:bg-emerald-700 text-white border border-transparent rounded-lg text-[10px] font-semibold shadow-sm transition-colors select-none shrink-0 disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  <Save className="w-3 h-3" />
                  保存
                </button>
              )}
            </div>
          )}
        </div>
        <div>
          <span>已自动关联左侧文档库：</span>
          <span className="text-amber-800 dark:text-amber-500 font-bold">{selectedFileIds.length}</span>
          <span> 份选中文件 (含公共文档)</span>
        </div>
      </div>

      {/* 下方的文本编辑与生成内容区域 */}
      <div className="flex-1 p-6 flex flex-col overflow-hidden bg-white dark:bg-canvas-bg">
        <textarea
          ref={textareaRef}
          value={stageOutputs[activeStage.id] || ''}
          onChange={e => setStageOutputs(prev => ({ ...prev, [activeStage.id]: e.target.value }))}
          placeholder="点击「AI推理生成」按钮，本地大模型将自动关联左侧所选材料进行检索，并为您在此处流式撰写当前阶段分析..."
          className="flex-1 w-full p-5 border border-stone-200 dark:border-border-soft rounded-xl outline-none focus:ring-1 focus:ring-amber-500 text-xs leading-relaxed font-mono resize-none bg-stone-50/20 dark:bg-outline-bg/25 text-gray-800 dark:text-text-main shadow-inner"
        />
      </div>

      {showConfirmModal && createPortal(
        <div className="fixed inset-0 z-[9999] flex items-center justify-center p-4 select-none">
          <div 
            className="absolute inset-0 bg-[#0F0F11]/45 backdrop-blur-[2px] transition-opacity" 
            onClick={() => setShowConfirmModal(false)}
          />
          <div className="relative bg-white dark:bg-[#1E1F22] rounded-xl p-5 shadow-2xl border border-stone-200 dark:border-stone-850 max-w-sm w-full flex flex-col gap-4 animate-in fade-in zoom-in-95 duration-200">
            <div className="flex items-start gap-3 text-stone-800 dark:text-stone-200">
              <div className="p-2.5 rounded-full bg-amber-50 dark:bg-amber-950/20 text-amber-600 dark:text-amber-400 shrink-0">
                <AlertTriangle className="w-5 h-5" />
              </div>
              <div className="flex flex-col gap-1 min-w-0">
                <h3 className="text-sm font-bold leading-none text-stone-900 dark:text-stone-100">
                  ⚡ 开始一键生成
                </h3>
                <p className="text-xs text-stone-500 dark:text-stone-400 leading-normal mt-3 whitespace-pre-wrap font-sans">
                  系统将按照顺序自动执行每一步推理并保存数据。这可能会覆盖之前已生成的文本内容，确定要继续吗？
                </p>
              </div>
            </div>
            <div className="flex justify-end gap-2 mt-2">
              <button
                onClick={() => setShowConfirmModal(false)}
                className="px-4 py-1.5 text-xs font-semibold text-stone-600 dark:text-stone-300 hover:text-stone-800 dark:hover:text-stone-100 hover:bg-stone-50 dark:hover:bg-stone-800 rounded-lg transition-colors border border-stone-200 dark:border-stone-700 cursor-pointer"
              >
                取消
              </button>
              <button
                onClick={startAutoPipeline}
                className="px-4 py-1.5 text-xs font-semibold text-white bg-emerald-600 hover:bg-emerald-700 active:scale-95 rounded-lg transition-all shadow-sm cursor-pointer"
              >
                确认生成
              </button>
            </div>
          </div>
        </div>,
        document.body
      )}

      {saveDocInfo && createPortal(
        <div className="fixed inset-0 z-[9999] flex items-center justify-center p-4 select-none">
          <div 
            className="absolute inset-0 bg-[#0F0F11]/45 backdrop-blur-[2px] transition-opacity" 
            onClick={() => setSaveDocInfo(null)}
          />
          <div className="relative bg-white dark:bg-[#1E1F22] rounded-xl p-5 shadow-2xl border border-stone-200 dark:border-stone-850 max-w-sm w-full flex flex-col gap-4 animate-in fade-in zoom-in-95 duration-200" onClick={e => e.stopPropagation()}>
            <div className="flex flex-col gap-1.5 min-w-0">
              <h3 className="text-sm font-bold text-stone-900 dark:text-stone-100 flex items-center gap-1.5">
                💾 保存分析文档
              </h3>
              <p className="text-[11px] text-stone-400 dark:text-stone-500 mt-0.5">
                请输入要保存的文档文件名称：
              </p>
              <input
                type="text"
                autoFocus
                placeholder="请输入文档名称..."
                value={saveDocInfo.title}
                onChange={e => setSaveDocInfo({ ...saveDocInfo, title: e.target.value })}
                onKeyDown={e => {
                  if (e.key === 'Enter' && saveDocInfo.title.trim()) {
                    void window.executeSaveDocument(saveDocInfo.content, saveDocInfo.title.trim());
                    setSaveDocInfo(null);
                  }
                }}
                className="mt-3 w-full px-3 py-2 text-xs border border-stone-200 dark:border-stone-700 rounded-lg bg-stone-50 dark:bg-stone-800 text-stone-800 dark:text-stone-100 focus:outline-none focus:ring-1 focus:ring-indigo-500"
              />
            </div>
            <div className="flex justify-end gap-2 mt-1">
              <button
                onClick={() => setSaveDocInfo(null)}
                className="px-4 py-1.5 text-xs font-semibold text-stone-600 dark:text-stone-300 hover:text-stone-800 dark:hover:text-stone-100 hover:bg-stone-50 dark:hover:bg-stone-800 rounded-lg transition-colors border border-stone-200 dark:border-stone-700 cursor-pointer"
              >
                取消
              </button>
              <button
                disabled={!saveDocInfo.title.trim()}
                onClick={() => {
                  if (saveDocInfo.title.trim()) {
                    void window.executeSaveDocument(saveDocInfo.content, saveDocInfo.title.trim());
                    setSaveDocInfo(null);
                  }
                }}
                className="px-4 py-1.5 text-xs font-semibold text-white bg-indigo-600 hover:bg-indigo-700 active:scale-95 disabled:opacity-40 disabled:pointer-events-none rounded-lg transition-all shadow-sm cursor-pointer"
              >
                确认保存
              </button>
            </div>
          </div>
        </div>,
        document.body
      )}
    </div>
  );
}
