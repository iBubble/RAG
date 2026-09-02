import React, { useState, useEffect } from 'react';
import { 
  GitFork, Sparkles, RotateCcw, Loader2, 
  FileCheck2, Info
} from 'lucide-react';
import { useAuthStore } from '../../store/authStore';
import { useProjectStore } from '../../store/projectStore';
import { PaperFormCard, type FormCardItem } from './PaperFormCard';
import { FormFillModal } from './FormFillModal';

interface IntakeSortingPanelProps {
  projectId?: string;
  canWrite?: boolean;
}

const API_BASE = '';

export const IntakeSortingPanel: React.FC<IntakeSortingPanelProps> = ({
  projectId = 'default',
  canWrite = true
}) => {
  const { getAuthHeaders } = useAuthStore();
  const selectedModel = useProjectStore(state => state.selectedModel);

  const [loading, setLoading] = useState(false);
  const [isInferring, setIsInferring] = useState(false);
  const [hasDoneTriage, setHasDoneTriage] = useState(false);
  const [track, setTrack] = useState<string>('');
  const [summary, setSummary] = useState<string>('');
  const [formList, setFormList] = useState<FormCardItem[]>([]);
  const [allTemplates, setAllTemplates] = useState<any[]>([]);

  // 选中的弹窗表单状态
  const [activeForm, setActiveForm] = useState<FormCardItem | null>(null);
  const [isModalOpen, setIsModalOpen] = useState(false);

  // 加载系统模板与已分拣数据
  const loadData = async () => {
    setLoading(true);
    try {
      // 1. 获取官方模板库
      const tplRes = await fetch(`${API_BASE}/api/admin/ai-templates?t=${Date.now()}`, {
        headers: getAuthHeaders()
      });
      if (tplRes.ok) {
        const cats = await tplRes.json();
        const cat = cats.find((c: any) => c.name.includes('投诉举报'));
        if (cat && cat.tables) {
          setAllTemplates(cat.tables);
        }
      }

      // 2. 获取项目已保存文档（判断是否已填报）
      const docRes = await fetch(`${API_BASE}/api/projects/${projectId}/documents?t=${Date.now()}`, {
        headers: getAuthHeaders()
      });
      let savedTitles: string[] = [];
      if (docRes.ok) {
        const docs = await docRes.json();
        if (Array.isArray(docs)) {
          savedTitles = docs.map((d: any) => d.title || '');
        }
      }

      // 3. 获取此前持久化的分拣推荐
      const recRes = await fetch(`${API_BASE}/api/projects/${projectId}/triage/recommend?t=${Date.now()}`, {
        headers: getAuthHeaders()
      });
      if (recRes.ok) {
        const recJson = await recRes.json();
        const recData = recJson.data || recJson;
        if (recData && recData.recommended_forms && recData.recommended_forms.length > 0) {
          setHasDoneTriage(true);
          setTrack(recData.track || '投诉轨');
          setSummary(recData.summary || '');
          
          const mapped: FormCardItem[] = recData.recommended_forms.map((rf: any) => {
            const isFilled = savedTitles.some(t => t.startsWith(rf.name + '_'));
            return {
              name: rf.name,
              reason: rf.reason || '根据办案程序法定规则推荐',
              required: rf.required ?? false,
              isFilled
            };
          });
          setFormList(mapped);
        } else {
          setHasDoneTriage(false);
          setFormList([]);
        }
      }
    } catch (e) {
      console.error('加载分拣数据失败', e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
  }, [projectId]);

  const handleTriggerTriage = async () => {
    setIsInferring(true);
    try {
      const res = await fetch(`${API_BASE}/api/projects/${projectId}/triage/recommend`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...getAuthHeaders()
        },
        body: JSON.stringify({
          model: selectedModel,
          force_refresh: true
        })
      });
      if (res.ok) {
        const json = await res.json();
        const data = json.data;
        if (data && data.recommended_forms) {
          setHasDoneTriage(true);
          setTrack(data.track || '投诉轨');
          setSummary(data.summary || '');
          const mapped: FormCardItem[] = data.recommended_forms.map((rf: any) => ({
            name: rf.name,
            reason: rf.reason || '根据办案程序法定规则推荐',
            required: rf.required ?? false,
            isFilled: false
          }));
          setFormList(mapped);
        }
      }
    } catch (e: any) {
      console.error('分拣推荐失败', e);
      alert(`❌ 分拣失败: ${e.message}`);
    } finally {
      setIsInferring(false);
    }
  };

  const handleCardClick = (item: FormCardItem) => {
    setActiveForm(item);
    setIsModalOpen(true);
  };

  const handleFormSaved = (formName: string) => {
    setFormList(prev => prev.map(f => f.name === formName ? { ...f, isFilled: true } : f));
  };

  const getActiveTemplateHtml = () => {
    if (!activeForm) return '';
    const match = allTemplates.find((t: any) => t.name === activeForm.name || activeForm.name.endsWith(t.name) || t.name.endsWith(activeForm.name));
    return match ? match.template : '<p>模板加载中...</p>';
  };

  return (
    <div className="flex flex-col h-full w-full bg-[#F9F8F6] dark:bg-[#18191C] overflow-y-auto p-6 font-sans">
      
      {/* 顶部控制台 */}
      <div className="bg-white dark:bg-[#25272D] border border-stone-200 dark:border-stone-700 rounded-2xl p-5 shadow-sm mb-6 flex flex-col md:flex-row items-start md:items-center justify-between gap-4 shrink-0">
        <div className="flex items-center gap-3.5">
          <div className="w-11 h-11 rounded-xl bg-indigo-50 dark:bg-indigo-950/50 border border-indigo-100 dark:border-indigo-900 flex items-center justify-center text-indigo-600 dark:text-indigo-400 shrink-0">
            <GitFork className="w-6 h-6" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h2 className="text-base font-bold text-stone-800 dark:text-stone-100">分拣填报</h2>
              {hasDoneTriage && (
                <span className={`text-[11px] font-semibold px-2 py-0.5 rounded-full border ${
                  track === '举报轨' 
                    ? 'bg-rose-50 text-rose-600 border-rose-200 dark:bg-rose-950/40 dark:text-rose-400 dark:border-rose-900' 
                    : 'bg-indigo-50 text-indigo-600 border-indigo-200 dark:bg-indigo-950/40 dark:text-indigo-400 dark:border-indigo-900'
                }`}>
                  {track}
                </span>
              )}
            </div>
            <p className="text-xs text-stone-400 dark:text-stone-500 mt-0.5">
              依据《市场监督管理投诉举报处理办法》（总局令第121号）第9条执行分别处理，智能推荐适用表单
            </p>
          </div>
        </div>

        <button
          onClick={handleTriggerTriage}
          disabled={isInferring || !canWrite}
          className="px-5 py-2.5 bg-gradient-to-r from-indigo-600 to-purple-600 hover:from-indigo-700 hover:to-purple-700 text-white rounded-xl flex items-center gap-2 text-xs font-semibold shadow-md hover:shadow-lg disabled:opacity-50 transition-all duration-200 cursor-pointer shrink-0"
        >
          {isInferring ? (
            <>
              <Loader2 className="w-4 h-4 animate-spin" />
              <span>大模型智能分拣中...</span>
            </>
          ) : (
            <>
              {hasDoneTriage ? <RotateCcw className="w-4 h-4" /> : <Sparkles className="w-4 h-4" />}
              <span>{hasDoneTriage ? '重新分拣' : '开始分拣'}</span>
            </>
          )}
        </button>
      </div>

      {/* AI 分诊分析摘要条 */}
      {hasDoneTriage && summary && (
        <div className="bg-indigo-50/60 dark:bg-indigo-950/20 border border-indigo-100 dark:border-indigo-900/40 rounded-2xl p-4 mb-8 flex items-start gap-3 shadow-xs">
          <Info className="w-5 h-5 text-indigo-500 shrink-0 mt-0.5" />
          <div className="text-xs leading-relaxed text-stone-700 dark:text-stone-300">
            <span className="font-bold text-indigo-700 dark:text-indigo-300 mr-1.5">【AI 分诊研判结论】:</span>
            {summary}
          </div>
        </div>
      )}

      {/* 核心展示区：图二样式的纸张卡片网格 */}
      <div className="flex-1">
        {loading ? (
          <div className="flex flex-col items-center justify-center py-20 gap-3 text-stone-400">
            <Loader2 className="w-8 h-8 animate-spin text-indigo-500" />
            <p className="text-xs">加载分拣表单中...</p>
          </div>
        ) : !hasDoneTriage ? (
          <div className="bg-white dark:bg-[#25272D] border border-dashed border-stone-300 dark:border-stone-700 rounded-2xl p-16 flex flex-col items-center justify-center text-center">
            <div className="w-16 h-16 rounded-full bg-indigo-50 dark:bg-indigo-950/50 flex items-center justify-center text-indigo-500 mb-4">
              <FileCheck2 className="w-8 h-8" />
            </div>
            <h3 className="text-base font-bold text-stone-800 dark:text-stone-200">暂未进行来件智能分拣</h3>
            <p className="text-xs text-stone-400 dark:text-stone-500 max-w-md mt-1.5 leading-relaxed">
              请点击右上角“开始分拣”按钮，大模型将自动读取项目材料、依据《智能呈报》规范进行线索定性与表单互斥推荐。
            </p>
          </div>
        ) : formList.length === 0 ? (
          <div className="text-center py-16 text-stone-400 text-xs">未匹配到推荐文书表单</div>
        ) : (
          <div>
            <div className="flex items-center justify-between mb-6">
              <h3 className="text-xs font-bold text-stone-500 uppercase tracking-wider flex items-center gap-1.5">
                <span>推荐文书表单（共 {formList.length} 项）</span>
              </h3>
              <span className="text-[11px] text-stone-400">点击任意卡片即可弹窗调用 AI 智能填报</span>
            </div>

            {/* 图二样式的现代多卡片排列：采用明确间距的 Flex 布局，防止挤压重叠 */}
            <div className="flex flex-wrap items-start gap-x-12 gap-y-10 py-2">
              {formList.map(item => (
                <PaperFormCard
                  key={item.name}
                  item={item}
                  onClick={() => handleCardClick(item)}
                />
              ))}
            </div>
          </div>
        )}
      </div>

      {/* 弹窗填报编辑器 */}
      {activeForm && (
        <FormFillModal
          isOpen={isModalOpen}
          onClose={() => { setIsModalOpen(false); setActiveForm(null); }}
          formName={activeForm.name}
          defaultTemplateHtml={getActiveTemplateHtml()}
          projectId={projectId}
          onSaved={handleFormSaved}
        />
      )}
    </div>
  );
};
