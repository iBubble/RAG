import React, { useState, useEffect, useRef } from 'react';
import { useAuthStore } from '../../store/authStore';
import { useProjectStore } from '../../store/projectStore';
import { File, AlertTriangle, Download, Loader2, ArrowRight } from 'lucide-react';

export default function ContractReview({ projectId, canWrite }) {
  const { getAuthHeaders } = useAuthStore();
  const API_BASE = import.meta.env.VITE_API_BASE || '';
  const [collaborative, setCollaborative] = useState(false);
  const publicSettings = useProjectStore(state => state.publicSettings);
  const fetchPublicSettings = useProjectStore(state => state.fetchPublicSettings);
  const checkedFileIds = useProjectStore(state => state.checkedFileIds);
  const checkedRefIds = useProjectStore(state => state.checkedRefIds);
  const [reviewSteps, setReviewSteps] = useState([]);

  useEffect(() => {
    if (!publicSettings) {
      fetchPublicSettings();
    }
  }, [publicSettings, fetchPublicSettings]);

  useEffect(() => {
    if (publicSettings) {
      setCollaborative(publicSettings.collab_contract_enabled === 'true');
    }
  }, [publicSettings]);

  const [docxFiles, setDocxFiles] = useState([]);
  const [selectedFilePath, setSelectedFilePath] = useState('');
  const [position, setPosition] = useState('甲方'); // '甲方' | '乙方' | '中立'
  const [amountLevel, setAmountLevel] = useState('B'); // 'A' (大额) | 'B' (中等) | 'C' (小额)
  const [isReviewing, setIsReviewing] = useState(false);
  const [isUploading, setIsUploading] = useState(false);
  const [reviewResult, setReviewResult] = useState(null); // { comments: [], injected_count: 0 }
  const abortControllerRef = useRef(null);

  const handleStopReview = () => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }
    setIsReviewing(false);
  };

  // 加载该项目下的 docx 文件列表
  const loadDocxFiles = async () => {
    try {
      // 1. 本地文件
      const resLocal = await fetch(`${API_BASE}/api/files/list?project_id=${projectId}`, { headers: getAuthHeaders() });
      const dataLocal = resLocal.ok ? await resLocal.json() : {};
      const localList = dataLocal.files || [];

      // 2. 引用的公共文档
      const resRef = await fetch(`${API_BASE}/api/projects/${projectId}/ref-files`, { headers: getAuthHeaders() });
      const dataRef = resRef.ok ? await resRef.json() : {};
      const refList = dataRef.files || [];

      // 合并并过滤 docx 后缀
      const docxList = [...localList, ...refList].filter(f =>
        f.filename.toLowerCase().endsWith('.docx')
      );
      setDocxFiles(docxList);
      if (docxList.length > 0 && !selectedFilePath) {
        setSelectedFilePath(docxList[0].path);
      }
    } catch (err) {
      console.error('加载合同列表失败', err);
    }
  };

  useEffect(() => {
    loadDocxFiles();
  }, [projectId]);

  // 直接上传新合同文件
  const handleFileUpload = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setIsUploading(true);
    const formData = new FormData();
    formData.append('files', file);
    formData.append('project_id', projectId);
    formData.append('relative_path', '');

    try {
      const res = await fetch(`${API_BASE}/api/files/upload`, {
        method: 'POST',
        headers: {
          'Authorization': getAuthHeaders().Authorization
        },
        body: formData,
      });
      if (!res.ok) throw new Error('上传失败');
      alert('合同上传成功，已加入当前案卷列表');
      loadDocxFiles();
    } catch (err) {
      alert(`上传失败: ${err.message}`);
    } finally {
      setIsUploading(false);
    }
  };

  // 轮询合同审查的多 Agent 协同/流转状态
  useEffect(() => {
    let timer = null;
    if (isReviewing) {
      setReviewSteps([
        { id: 'retrieval', text: '正在检索左侧所选知识库文档...', status: 'doing' }
      ]);

      const pollStatus = async () => {
        try {
          const res = await fetch(`${API_BASE}/api/projects/linvis-status`, {
            headers: getAuthHeaders()
          });
          if (!res.ok) return;
          const data = await res.json();
          const agents = data.agents || {};

          setReviewSteps(prev => {
            const next = [...prev];
            
            const updateStep = (id, text, status) => {
              const idx = next.findIndex(s => s.id === id);
              if (idx > -1) {
                if (next[idx].status !== status) {
                  next[idx].status = status;
                }
              } else {
                next.forEach(s => {
                  if (s.status === 'doing') s.status = 'done';
                });
                next.push({ id, text, status });
              }
            };

            // 1. 检查 service (法律服务专家)
            if (agents.service?.status === 'working') {
              updateStep('retrieval', '正在检索左侧所选知识库文档...', 'done');
              const text = collaborative 
                ? '【协同】法律服务专家：正在进行初审分析...' 
                : '【法律服务专家】正在对合同文本进行深度语义审查...';
              updateStep('service', text, 'doing');
            }

            // 2. 检查 contrarian (审查员)
            if (collaborative && agents.contrarian?.status === 'working') {
              updateStep('retrieval', '正在检索左侧所选知识库文档...', 'done');
              updateStep('service', '【协同】法律服务专家：正在进行初审分析...', 'done');
              updateStep('contrarian', '【协同】审查员：正在进行交叉抗辩与风险排查...', 'doing');
            }

            // 3. 检查 arbiter (仲裁官)
            if (collaborative && agents.arbiter?.status === 'working') {
              updateStep('retrieval', '正在检索左侧所选知识库文档...', 'done');
              updateStep('service', '【协同】法律服务专家：正在进行初审分析...', 'done');
              updateStep('contrarian', '【协同】审查员：正在进行交叉抗辩与风险排查...', 'done');
              updateStep('arbiter', '【协同】仲裁官：正在进行最终定稿与格式化...', 'doing');
            }

            return next;
          });
        } catch (err) {
          console.error('轮询状态失败', err);
        }
      };

      pollStatus();
      timer = setInterval(pollStatus, 1500);
    } else {
      if (timer) clearInterval(timer);
    }

    return () => {
      if (timer) clearInterval(timer);
    };
  }, [isReviewing, collaborative]);

  // 执行一键审查
  const handleReview = async () => {
    if (!selectedFilePath) {
      alert('请先选择或上传合同文件！');
      return;
    }
    setIsReviewing(true);
    setReviewResult(null);

    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }
    abortControllerRef.current = new AbortController();

    try {
      const res = await fetch(`${API_BASE}/api/legal/contract/review`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ...getAuthHeaders() },
        body: JSON.stringify({
          file_path: selectedFilePath,
          project_id: projectId,
          collaborative: collaborative,
          file_ids: [...checkedFileIds, ...checkedRefIds]
        }),
        signal: abortControllerRef.current.signal
      });
      if (!res.ok) throw new Error('大模型分析超时或接口异常');
      const data = await res.json();
      setReviewResult(data);
      setReviewSteps(prev => {
        const next = prev.map(s => ({ ...s, status: 'done' }));
        next.push({ id: 'success', text: '批注物理回写完成，报告生成成功！', status: 'done' });
        return next;
      });
    } catch (err) {
      if (err.name === 'AbortError') {
        setReviewSteps(prev => {
          const next = prev.map(s => s.status === 'doing' ? { ...s, status: 'error' } : s);
          next.push({ id: 'error', text: `审查任务已手动停止。`, status: 'error' });
          return next;
        });
      } else {
        alert(`审查失败: ${err.message}`);
        setReviewSteps(prev => {
          const next = prev.map(s => s.status === 'doing' ? { ...s, status: 'error' } : s);
          next.push({ id: 'error', text: `审查失败: ${err.message}`, status: 'error' });
          return next;
        });
      }
    } finally {
      setIsReviewing(false);
    }
  };

  // 下载审查并批注后的 Word
  const handleDownload = async () => {
    if (!selectedFilePath) return;
    try {
      const res = await fetch(`${API_BASE}/api/files/download?file_path=${encodeURIComponent(selectedFilePath)}`, {
        headers: getAuthHeaders(),
      });
      if (!res.ok) throw new Error('下载失败');
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `[AI审校版]-${selectedFilePath.split('/').pop()}`;
      document.body.appendChild(a);
      a.click();
      URL.revokeObjectURL(url);
      document.body.removeChild(a);
    } catch {
      alert('下载文件失败');
    }
  };

  // 统计风险等级
  const highRiskCount = reviewResult?.comments?.filter(c => c.risk_level?.includes('HIGH')).length || 0;
  const medRiskCount = reviewResult?.comments?.filter(c => c.risk_level?.includes('MEDIUM')).length || 0;

  return (
    <div className="h-full flex overflow-hidden">
      {/* 左栏：上传与配置 */}
      <div className="w-[320px] border-r border-[#e9e5de] dark:border-border-soft bg-[#faf8f5] dark:bg-panel-bg flex flex-col p-4 space-y-4 shrink-0 overflow-y-auto">
        <div>
          <label className="text-xs font-bold text-stone-500 block mb-1">上传待审合同 (.docx)</label>
          <input
            type="file"
            accept=".docx"
            onChange={handleFileUpload}
            disabled={isUploading}
            className="w-full text-xs text-stone-500 file:mr-2 file:py-1 file:px-2.5 file:rounded-md file:border-0 file:text-[10px] file:font-semibold file:bg-stone-200 file:text-stone-700 hover:file:bg-stone-300 cursor-pointer"
          />
          {isUploading && <p className="text-[10px] text-amber-700 mt-1">文件上传及文本解析中...</p>}
        </div>

        <div>
          <label className="text-xs font-bold text-stone-500 block mb-1">选择已存合同</label>
          <select
            value={selectedFilePath}
            onChange={e => setSelectedFilePath(e.target.value)}
            className="w-full px-3 py-2 bg-white border border-stone-200 rounded-lg text-xs outline-none focus:ring-1 focus:ring-amber-500"
          >
            {docxFiles.map(f => (
              <option key={f.id} value={f.path}>{f.filename}</option>
            ))}
          </select>
        </div>

        <div>
          <label className="text-xs font-bold text-stone-500 block mb-1.5">审查利益立场</label>
          <div className="grid grid-cols-3 gap-1 bg-stone-200/50 dark:bg-outline-bg p-1 rounded-lg">
            {['甲方', '乙方', '中立'].map(pos => (
              <button
                key={pos}
                onClick={() => setPosition(pos)}
                className={`py-1 rounded text-[11px] font-semibold transition-all ${
                  position === pos ? 'bg-white dark:bg-panel-bg text-stone-800 dark:text-text-main shadow-sm' : 'text-stone-500 dark:text-text-muted'
                }`}
              >
                {pos}
              </button>
            ))}
          </div>
        </div>

        <div>
          <label className="text-xs font-bold text-stone-500 block mb-1.5">合同金额等级</label>
          <div className="grid grid-cols-3 gap-1 bg-stone-200/50 dark:bg-outline-bg p-1 rounded-lg">
            {[['C', '小额'], ['B', '中等'], ['A', '大额']].map(([lvl, name]) => (
              <button
                key={lvl}
                onClick={() => setAmountLevel(lvl)}
                className={`py-1 rounded text-[11px] font-semibold transition-all ${
                  amountLevel === lvl ? 'bg-white dark:bg-panel-bg text-stone-800 dark:text-text-main shadow-sm' : 'text-stone-500 dark:text-text-muted'
                }`}
              >
                {name}
              </button>
            ))}
          </div>
        </div>

        <div className="flex items-center py-1 gap-2">
          <label className="flex items-center gap-1.5 cursor-pointer select-none">
            <input
              type="checkbox"
              checked={collaborative}
              onChange={(e) => setCollaborative(e.target.checked)}
              className="rounded text-amber-700 focus:ring-amber-500 w-3.5 h-3.5 cursor-pointer"
            />
            <span className="text-xs font-bold text-stone-500">协同</span>
          </label>
          {isReviewing && (
            <button
              onClick={(e) => {
                e.preventDefault();
                e.stopPropagation();
                handleStopReview();
              }}
              className="flex items-center gap-0.5 px-1.5 py-0.5 rounded text-[10px] font-bold bg-rose-600 hover:bg-rose-700 text-white transition-all shadow-sm cursor-pointer"
            >
              停止
            </button>
          )}
        </div>

        <button
          onClick={handleReview}
          disabled={isReviewing || !selectedFilePath}
          className="w-full py-2.5 bg-amber-700 hover:bg-amber-800 disabled:opacity-50 text-white rounded-lg text-xs font-bold shadow transition-colors flex items-center justify-center gap-1"
        >
          {isReviewing ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : '🚀 开始一键 AI 审查'}
        </button>

        {reviewSteps.length > 0 && (
          <div className="border border-stone-200 dark:border-border-soft bg-[#fbfaf8] dark:bg-outline-bg rounded-xl p-3.5 space-y-2.5 shadow-sm text-xs mt-3">
            <div className="flex items-center justify-between border-b border-stone-200 dark:border-border-soft pb-1.5 mb-1.5">
              <span className="font-extrabold text-stone-700">🔍 审查进度监控</span>
              {isReviewing && <Loader2 className="w-3.5 h-3.5 animate-spin text-amber-700" />}
            </div>
            <div className="space-y-2">
              {reviewSteps.map((step) => (
                <div key={step.id} className="flex items-start gap-2.5">
                  <span className="shrink-0 mt-0.5">
                    {step.status === 'done' ? (
                      <span className="text-emerald-600 font-bold">✓</span>
                    ) : step.status === 'doing' ? (
                      <span className="inline-block w-3 h-3 border-2 border-amber-700 border-t-transparent rounded-full animate-spin shrink-0" />
                    ) : step.status === 'error' ? (
                      <span className="text-red-500 font-bold">✗</span>
                    ) : (
                      <span className="text-stone-300">○</span>
                    )}
                  </span>
                  <span className={`text-[11px] leading-relaxed ${
                    step.status === 'doing' ? 'text-amber-800 font-semibold' :
                    step.status === 'done' ? 'text-stone-600' :
                    step.status === 'error' ? 'text-red-600 font-semibold' : 'text-stone-400'
                  }`}>
                    {step.text}
                  </span>
                </div>
              ))}
            </div>
            {isReviewing && (
              <p className="text-[10px] text-stone-400 mt-2 text-center border-t border-stone-100 pt-2">
                ☕ 本地大模型深度推理中，约耗时 1.5 - 2 分钟，请稍候...
              </p>
            )}
          </div>
        )}
      </div>

      {/* 右栏：结果展示区 */}
      <div className="flex-1 bg-white p-6 flex flex-col overflow-hidden">
        {isReviewing ? (
          <div className="flex-1 flex flex-col items-center justify-center text-stone-400 gap-3">
            <Loader2 className="w-8 h-8 animate-spin text-amber-700" />
            <span className="text-xs font-medium">本地大模型正在以 {position} 立场对合同进行四层链式审查，请耐心等待（约耗时 15-45 秒）...</span>
          </div>
        ) : reviewResult ? (
          <div className="flex-1 flex flex-col overflow-hidden space-y-4">
            {/* 顶栏卡片：汇总 */}
            <div className="grid grid-cols-3 gap-4 shrink-0">
              <div className="bg-red-50/50 border border-red-100 rounded-xl p-3.5 flex items-center justify-between">
                <div>
                  <p className="text-[10px] text-red-700 font-bold uppercase">重大风险条款</p>
                  <p className="text-xl font-extrabold text-red-700 mt-1">{highRiskCount} <span className="text-xs font-medium">处</span></p>
                </div>
                <AlertTriangle className="w-8 h-8 text-red-500/80" />
              </div>
              <div className="bg-amber-50/50 border border-amber-100 rounded-xl p-3.5 flex items-center justify-between">
                <div>
                  <p className="text-[10px] text-amber-700 font-bold uppercase">中等风险缺陷</p>
                  <p className="text-xl font-extrabold text-amber-700 mt-1">{medRiskCount} <span className="text-xs font-medium">处</span></p>
                </div>
                <AlertTriangle className="w-8 h-8 text-amber-500/80" />
              </div>
              <div className="bg-[#f6f5f3] border border-[#e9e5de] rounded-xl p-3.5 flex items-center justify-between">
                <div>
                  <p className="text-[10px] text-stone-600 font-bold">已在 Word 原文中注入批注</p>
                  <button
                    onClick={handleDownload}
                    className="mt-1 flex items-center gap-1 px-3 py-1.5 bg-stone-800 hover:bg-stone-900 text-white rounded-lg text-[10px] font-bold shadow-sm transition-colors"
                  >
                    <Download className="w-3 h-3" />
                    下载带批注 Word
                  </button>
                </div>
                <File className="w-8 h-8 text-stone-400" />
              </div>
            </div>

            {/* 条款列表 */}
            <div className="flex-1 border border-stone-200 rounded-xl overflow-hidden flex flex-col">
              <div className="bg-stone-50 px-4 py-2 text-xs font-bold text-stone-600 border-b border-stone-200 grid grid-cols-12 gap-4 shrink-0">
                <div className="col-span-3">合同原文争议条款</div>
                <div className="col-span-2">风险等级</div>
                <div className="col-span-7">AI 审查及替换建议</div>
              </div>
              <div className="flex-1 overflow-y-auto divide-y divide-stone-100">
                {reviewResult.comments.map((c, i) => (
                  <div key={i} className="px-4 py-3 text-xs grid grid-cols-12 gap-4 hover:bg-stone-50/50 transition-colors">
                    <div className="col-span-3 text-stone-700 font-mono break-all">{c.target_text}</div>
                    <div className="col-span-2">
                      <span className={`inline-block px-2 py-0.5 rounded text-[9px] font-bold ${
                        c.risk_level?.includes('HIGH') ? 'bg-red-100 text-red-700' :
                        c.risk_level?.includes('MEDIUM') ? 'bg-amber-100 text-amber-700' :
                        'bg-blue-100 text-blue-700'
                      }`}>{c.risk_level}</span>
                    </div>
                    <div className="col-span-7 text-stone-600 break-all leading-relaxed">{c.suggested_comment}</div>
                  </div>
                ))}
              </div>
            </div>
          </div>
        ) : (
          <div className="flex-1 flex flex-col items-center justify-center text-stone-400 gap-2">
            <File className="w-12 h-12 text-stone-200" />
            <span className="text-xs">请在左侧上传或选择一份 docx 合同，点击「开始一键 AI 审查」...</span>
          </div>
        )}
      </div>
    </div>
  );
}
