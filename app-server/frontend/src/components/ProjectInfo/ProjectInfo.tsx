import { useState, useEffect, useRef } from 'react';
import { createPortal } from 'react-dom';
import { Save, Loader2, Sparkles, FileText, CheckCircle2, AlertTriangle } from 'lucide-react';
import { useProjectStore } from '../../store/projectStore';
import { useAuthStore } from '../../store/authStore';

const API_BASE = import.meta.env.VITE_API_BASE || '';

/**
 * 案件信息 Tab — 从勾选文档中 AI 总结生成标准案件信息，
 * 支持流式输出 + 手动编辑 + 持久化保存。
 */
export default function ProjectInfo({ projectId }: { projectId: string }) {
  const [content, setContent] = useState('');
  const [isGenerating, setIsGenerating] = useState(false);
  const [saving, setSaving] = useState(false);
  const [saveSuccess, setSaveSuccess] = useState(false);
  const [loading, setLoading] = useState(true);
  const [showConfirmModal, setShowConfirmModal] = useState(false);
  const abortRef = useRef<AbortController | null>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const { checkedFileIds } = useProjectStore();
  const { getAuthHeaders } = useAuthStore();

  // 加载已保存的案件信息
  useEffect(() => {
    (async () => {
      setLoading(true);
      try {
        const res = await fetch(
          `${API_BASE}/api/projects/${projectId}`,
          { headers: getAuthHeaders() }
        );
        if (res.ok) {
          const data = await res.json();
          const saved = data.metadata?.caseInfo || '';
          setContent(saved);
        }
      } catch (e) {
        console.error('加载案件信息失败', e);
      } finally {
        setLoading(false);
      }
    })();
  }, [projectId]);

  const triggerGenerate = (e?: React.MouseEvent) => {
    if (e) {
      e.preventDefault();
      e.stopPropagation();
    }
    if (checkedFileIds.length === 0) {
      alert('请先在左侧勾选需要分析的文档');
      return;
    }
    if (content) {
      setShowConfirmModal(true);
    } else {
      executeGenerate();
    }
  };

  const executeGenerate = async () => {
    setShowConfirmModal(false);
    setIsGenerating(true);
    setContent('');
    const ctrl = new AbortController();
    abortRef.current = ctrl;

    try {
      const res = await fetch(
        `${API_BASE}/api/projects/${projectId}/generate-case-info`,
        {
          method: 'POST',
          headers: { ...getAuthHeaders(), 'Content-Type': 'application/json' },
          body: JSON.stringify({ file_ids: checkedFileIds }),
          signal: ctrl.signal,
        }
      );

      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        throw new Error(err.detail || `HTTP ${res.status}`);
      }

      const reader = res.body?.getReader();
      const decoder = new TextDecoder();
      let buffer = '';

      while (reader) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });

        // SSE 解析
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';
        for (const line of lines) {
          if (line.startsWith('data: ')) {
            const payload = line.slice(6);
            if (payload === '[DONE]') continue;
            try {
              const parsed = JSON.parse(payload);
              if (parsed.token) {
                setContent(prev => prev + parsed.token);
              }
            } catch {
              // 非 JSON，直接当文本
              setContent(prev => prev + payload);
            }
          }
        }
      }
    } catch (e: unknown) {
      if (e instanceof Error && e.name !== 'AbortError') {
        console.error('生成案件信息失败', e);
        alert(`生成失败: ${e.message}`);
      }
    } finally {
      setIsGenerating(false);
      abortRef.current = null;
    }
  };

  const handleStop = () => {
    abortRef.current?.abort();
    setIsGenerating(false);
  };

  // 保存到后端
  const handleSave = async () => {
    setSaving(true);
    setSaveSuccess(false);
    try {
      // 先获取现有 metadata 再合并
      const getRes = await fetch(
        `${API_BASE}/api/projects/${projectId}`,
        { headers: getAuthHeaders() }
      );
      const existing = getRes.ok ? await getRes.json() : {};
      const merged = { ...(existing.metadata || {}), caseInfo: content };

      const res = await fetch(`${API_BASE}/api/projects/${projectId}`, {
        method: 'PUT',
        headers: { ...getAuthHeaders(), 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: existing.name, metadata: merged }),
      });
      if (res.ok) {
        setSaveSuccess(true);
        setTimeout(() => setSaveSuccess(false), 3000);
      }
    } catch (e) {
      console.error('保存失败', e);
      alert('保存失败');
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return (
      <div className="flex flex-col items-center justify-center h-full">
        <Loader2 className="w-6 h-6 animate-spin text-indigo-400 mb-3" />
        <p className="text-gray-400 text-sm">加载中...</p>
      </div>
    );
  }

  // 无内容时：显示生成按钮
  if (!content && !isGenerating) {
    return (
      <div className="flex flex-col items-center justify-center h-full gap-6">
        <div className="w-20 h-20 rounded-full bg-gradient-to-br from-indigo-100 to-purple-100 flex items-center justify-center">
          <FileText className="w-10 h-10 text-indigo-400" />
        </div>
        <div className="text-center">
          <h3 className="text-lg font-semibold text-gray-700 mb-2">
            尚未生成案件信息
          </h3>
          <p className="text-sm text-gray-400 max-w-sm">
            请在左侧勾选案件相关文档，点击下方按钮，
            AI 将自动分析并总结生成标准案件信息。
          </p>
        </div>
        <button
          onClick={triggerGenerate}
          disabled={checkedFileIds.length === 0}
          className="flex items-center gap-2.5 px-8 py-3.5 bg-gradient-to-r from-indigo-500 to-purple-500 text-white rounded-xl text-sm font-semibold hover:from-indigo-600 hover:to-purple-600 transition-all shadow-lg shadow-indigo-200 disabled:opacity-40 disabled:cursor-not-allowed disabled:shadow-none"
        >
          <Sparkles className="w-5 h-5" />
          生成案件信息
          {checkedFileIds.length > 0 && (
            <span className="bg-white/20 px-2 py-0.5 rounded text-xs">
              {checkedFileIds.length} 个文档
            </span>
          )}
        </button>
        {checkedFileIds.length === 0 && (
          <p className="text-xs text-orange-400">
            ⚠ 请先在左侧文件列表中勾选文档
          </p>
        )}
      </div>
    );
  }

  // 有内容 / 生成中：显示编辑区
  return (
    <div className="h-full flex flex-col">
      {/* 顶部工具栏 */}
      <div className="flex items-center justify-between px-6 py-3 border-b border-gray-100 bg-white shrink-0">
        <h3 className="text-sm font-semibold text-gray-700 flex items-center gap-2">
          <FileText className="w-4 h-4 text-indigo-500" />
          案件信息
          {isGenerating && (
            <span className="text-xs text-indigo-500 font-normal flex items-center gap-1">
              <Loader2 className="w-3 h-3 animate-spin" /> 生成中...
            </span>
          )}
        </h3>
        <div className="flex items-center gap-2">
          {isGenerating ? (
            <button
              onClick={handleStop}
              className="px-3 py-1.5 border border-red-200 text-red-500 rounded-lg text-xs font-medium hover:bg-red-50 transition-colors"
            >
              停止生成
            </button>
          ) : (
            <button
              onClick={triggerGenerate}
              disabled={checkedFileIds.length === 0}
              className="px-3 py-1.5 border border-indigo-200 text-indigo-600 rounded-lg text-xs font-medium hover:bg-indigo-50 flex items-center gap-1 transition-colors disabled:opacity-40"
            >
              <Sparkles className="w-3 h-3" /> 重新生成
            </button>
          )}
          <button
            onClick={handleSave}
            disabled={saving || isGenerating}
            className="px-3 py-1.5 bg-gray-900 text-white rounded-lg text-xs font-medium hover:bg-gray-800 flex items-center gap-1 transition-colors disabled:opacity-50"
          >
            {saving ? <Loader2 className="w-3 h-3 animate-spin" /> : <Save className="w-3 h-3" />}
            {saving ? '保存中...' : '保存'}
          </button>
          {saveSuccess && (
            <span className="text-xs text-emerald-500 flex items-center gap-1">
              <CheckCircle2 className="w-3 h-3" /> 已保存
            </span>
          )}
        </div>
      </div>

      {/* 编辑区 */}
      <div className="flex-1 overflow-hidden p-6 bg-[#f8f9fb]">
        <textarea
          ref={textareaRef}
          value={content}
          onChange={e => setContent(e.target.value)}
          className="w-full h-full resize-none bg-white border border-gray-200 rounded-xl p-6 text-sm text-gray-700 leading-relaxed outline-none focus:border-indigo-300 focus:ring-4 focus:ring-indigo-50 transition-all font-[system-ui]"
          placeholder="AI 生成的案件信息将显示在此处，您也可以手动编辑..."
          readOnly={isGenerating}
        />
      </div>

      {showConfirmModal && createPortal(
        <div className="fixed inset-0 z-[9999] flex items-center justify-center p-4 select-none">
          <div 
            className="absolute inset-0 bg-[#0F0F11]/45 backdrop-blur-[2px] transition-opacity" 
            onClick={() => setShowConfirmModal(false)}
          />
          <div className="relative bg-white dark:bg-[#1E1F22] rounded-xl p-5 shadow-2xl border border-stone-200 dark:border-stone-800 max-w-sm w-full flex flex-col gap-4 animate-in fade-in zoom-in-95 duration-200">
            <div className="flex items-start gap-3 text-stone-800 dark:text-stone-200">
              <div className="p-2.5 rounded-full bg-amber-50 dark:bg-amber-950/20 text-amber-600 dark:text-amber-400 shrink-0">
                <AlertTriangle className="w-5 h-5" />
              </div>
              <div className="flex flex-col gap-1 min-w-0">
                <h3 className="text-sm font-bold text-stone-900 dark:text-stone-100">
                  ⚡ 重新生成案件信息
                </h3>
                <p className="text-xs text-stone-500 dark:text-stone-400 leading-normal mt-3 whitespace-pre-wrap font-sans">
                  重新生成案件信息将会覆盖当前的文本内容。确定要继续并覆盖吗？
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
                onClick={executeGenerate}
                className="px-4 py-1.5 text-xs font-semibold text-white bg-emerald-600 hover:bg-emerald-700 active:scale-95 rounded-lg transition-all shadow-sm cursor-pointer"
              >
                确认生成
              </button>
            </div>
          </div>
        </div>,
        document.body
      )}
    </div>
  );
}
