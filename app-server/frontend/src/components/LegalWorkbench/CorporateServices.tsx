import { useState, useEffect, useRef } from 'react';
import { createPortal } from 'react-dom';
import { 
  Building2, Save, FileText, Calendar, RefreshCw, 
  Trash2, Plus, Play, Copy, AlertTriangle
} from 'lucide-react';
import { useAuthStore } from '../../store/authStore';

const API_BASE = import.meta.env.VITE_API_BASE || '';

interface CorporateServicesProps {
  projectId: string;
  canWrite: boolean;
}

export default function CorporateServices({ projectId, canWrite }: CorporateServicesProps) {
  // Tabs
  const [activeTab, setActiveTab] = useState<'project' | 'renewal' | 'retrospective'>('project');
  const [saveDocInfo, setSaveDocInfo] = useState<{ text: string; titlePrefix: string; title: string } | null>(null);
  const [ledgerToDelete, setLedgerToDelete] = useState<string | null>(null);
  
  // 客户档案 State
  const [profile, setProfile] = useState({
    clientName: '',
    industry: '',
    stance: '中立',
    clientType: '民营企业',
    specialPoints: '',
    searchLevel: '最高人民法院及各省高院'
  });
  const [isEditingProfile, setIsEditingProfile] = useState(false);
  const [isSavingProfile, setIsSavingProfile] = useState(false);

  // ================= 项目支持与日常咨询 State =================
  const [projectQuestion, setProjectQuestion] = useState('');
  const [projectFormat, setProjectFormat] = useState<'brief' | 'full'>('brief');
  const [enableSearch, setEnableSearch] = useState(false);
  const [projectOutput, setProjectOutput] = useState('');
  const [isGeneratingProject, setIsGeneratingProject] = useState(false);
  const abortControllerRef = useRef<AbortController | null>(null);

  // ================= 委托合同续约检查 State =================
  const [ledgerItems, setLedgerItems] = useState<any[]>([]);
  const [isLedgerLoading, setIsLedgerLoading] = useState(false);
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [newItem, setNewItem] = useState({
    clientName: '',
    contractName: '',
    startDate: '',
    endDate: '',
    annualFee: '',
    paymentMethod: '一次性付清',
    contactPerson: '',
    remark: ''
  });

  // ================= 合同审查复盘 State =================
  const [retroInput, setRetroInput] = useState('');
  const [retroOutput, setRetroOutput] = useState('');
  const [isGeneratingRetro, setIsGeneratingRetro] = useState(false);
  const retroAbortControllerRef = useRef<AbortController | null>(null);

  // ================= 自动滚动条控制逻辑 =================
  const projectOutputRef = useRef<HTMLDivElement | null>(null);
  useEffect(() => {
    if (isGeneratingProject && projectOutputRef.current) {
      const el = projectOutputRef.current;
      const timer = setTimeout(() => {
        el.scrollTop = el.scrollHeight;
      }, 30);
      return () => clearTimeout(timer);
    }
  }, [projectOutput, isGeneratingProject]);

  const retroOutputRef = useRef<HTMLDivElement | null>(null);
  useEffect(() => {
    if (isGeneratingRetro && retroOutputRef.current) {
      const el = retroOutputRef.current;
      const timer = setTimeout(() => {
        el.scrollTop = el.scrollHeight;
      }, 30);
      return () => clearTimeout(timer);
    }
  }, [retroOutput, isGeneratingRetro]);

  // 初始化获取客户档案
  useEffect(() => {
    async function loadProfile() {
      try {
        const { getAuthHeaders } = useAuthStore.getState();
        const res = await fetch(`${API_BASE}/api/projects/${projectId}/client_profile`, {
          headers: getAuthHeaders()
        });
        if (res.ok) {
          const data = await res.json();
          if (data && data.clientName) {
            setProfile(data);
          } else {
            // 默认配置
            setProfile({
              clientName: '未命名顾问单位',
              industry: '高新技术/法律服务等',
              stance: '中立',
              clientType: '民营企业',
              specialPoints: '暂无特殊审查要点',
              searchLevel: '最高人民法院及各省高院'
            });
          }
        }
      } catch (err) {
        console.error('获取客户档案失败', err);
      }
    }
    loadProfile();
  }, [projectId]);

  // 保存客户档案
  const handleSaveProfile = async () => {
    setIsSavingProfile(true);
    try {
      const { getAuthHeaders } = useAuthStore.getState();
      const res = await fetch(`${API_BASE}/api/projects/${projectId}/client_profile`, {
        method: 'POST',
        headers: { ...getAuthHeaders(), 'Content-Type': 'application/json' },
        body: JSON.stringify(profile)
      });
      if (res.ok) {
        setIsEditingProfile(false);
        alert('客户档案更新成功！');
      } else {
        throw new Error('保存失败');
      }
    } catch (err) {
      alert('保存客户档案失败');
    } finally {
      setIsSavingProfile(false);
    }
  };

  // ================= 项目支持流式生成 =================
  const handleStartProjectSupport = async () => {
    if (!projectQuestion.trim()) {
      alert('请输入您需要咨询的法律问题或项目信息！');
      return;
    }
    setIsGeneratingProject(true);
    setProjectOutput('');
    
    if (abortControllerRef.current) abortControllerRef.current.abort();
    abortControllerRef.current = new AbortController();

    try {
      const { token: authToken } = useAuthStore.getState();
      const res = await fetch(`${API_BASE}/api/legal/workflow/stream`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': authToken ? `Bearer ${authToken}` : ''
        },
        body: JSON.stringify({
          project_id: projectId,
          file_ids: [],
          skill_type: 'corporate_legal',
          stage_id: 'document_drafting',
          context_history: `【顾问单位名称】：${profile.clientName}\n【主营行业】：${profile.industry}\n【立场倾向】：${profile.stance}\n【企业分类】：${profile.clientType}\n【特殊要点】：${profile.specialPoints}\n【咨询类型】：${projectFormat === 'brief' ? '日常咨询解答 (精简回复)' : '法律意见书 (完整备忘录)'}\n【是否启用检索】：${enableSearch ? '是' : '否'}\n【日常咨询的具体问题】：${projectQuestion.trim()}`
        }),
        signal: abortControllerRef.current.signal
      });

      if (!res.ok) throw new Error('流式请求失败');
      const reader = res.body?.getReader();
      if (!reader) throw new Error('未能获取流读取器');

      const decoder = new TextDecoder();
      let done = false;
      while (!done) {
        const { value, done: doneReading } = await reader.read();
        done = doneReading;
        if (value) {
          const chunk = decoder.decode(value);
          setProjectOutput(prev => prev + chunk);
        }
      }
    } catch (err) {
      if (err instanceof Error && err.name === 'AbortError') {
        console.log('生成已中止');
        setProjectOutput(prev => prev + '\n\n🛑 生成已手动停止。');
      } else {
        console.error('项目分析失败', err);
        setProjectOutput(prev => prev + '\n\n❌ 大模型推理中途出错，请稍后重试。');
      }
    } finally {
      setIsGeneratingProject(false);
      abortControllerRef.current = null;
    }
  };

  // 保存生成的备忘录
  const handleSaveProjectDocument = (text: string, titlePrefix: string) => {
    if (!text) return;
    const defaultTitle = `[常法服务]-${titlePrefix}`;
    setSaveDocInfo({ text, titlePrefix, title: defaultTitle });
  };

  const executeSaveProjectDocument = async (text: string, docTitle: string) => {
    try {
      const { getAuthHeaders } = useAuthStore.getState();
      const docData = {
        id: crypto.randomUUID ? crypto.randomUUID() : Math.random().toString(36).substring(2),
        title: docTitle.trim(),
        content: text,
        timestamp: Date.now(),
        tokens: text.length,
        sections: [],
        isAutoSave: false
      };

      const res = await fetch(`${API_BASE}/api/projects/${projectId}/documents`, {
        method: 'POST',
        headers: { ...getAuthHeaders(), 'Content-Type': 'application/json' },
        body: JSON.stringify(docData)
      });

      if (!res.ok) throw new Error('接口响应失败');
      alert('保存成功！已同步至右侧文件列表。');
      window.dispatchEvent(new CustomEvent('documentSaved'));
    } catch (err) {
      alert('保存失败，请稍后重试');
    }
  };

  // ================= 委托续约台账方法 =================
  const loadLedgerItems = async () => {
    setIsLedgerLoading(true);
    try {
      const { getAuthHeaders } = useAuthStore.getState();
      const res = await fetch(`${API_BASE}/api/projects/${projectId}/renewal_ledger`, {
        headers: getAuthHeaders()
      });
      if (res.ok) {
        const data = await res.json();
        setLedgerItems(data || []);
      }
    } catch (err) {
      console.error('加载台账失败', err);
    } finally {
      setIsLedgerLoading(false);
    }
  };

  useEffect(() => {
    if (activeTab === 'renewal') {
      loadLedgerItems();
    }
  }, [activeTab, projectId]);

  const handleAddLedgerItem = async () => {
    if (!newItem.clientName || !newItem.contractName || !newItem.endDate) {
      alert('请填齐客户名、合同名以及到期时间！');
      return;
    }
    const item = {
      ...newItem,
      id: crypto.randomUUID ? crypto.randomUUID() : Math.random().toString(36).substring(2)
    };
    const updated = [...ledgerItems, item];
    try {
      const { getAuthHeaders } = useAuthStore.getState();
      const res = await fetch(`${API_BASE}/api/projects/${projectId}/renewal_ledger`, {
        method: 'POST',
        headers: { ...getAuthHeaders(), 'Content-Type': 'application/json' },
        body: JSON.stringify(updated)
      });
      if (res.ok) {
        setLedgerItems(updated);
        setIsModalOpen(false);
        setNewItem({
          clientName: '',
          contractName: '',
          startDate: '',
          endDate: '',
          annualFee: '',
          paymentMethod: '一次性付清',
          contactPerson: '',
          remark: ''
        });
      }
    } catch (err) {
      alert('添加失败，请重试');
    }
  };

  const handleDeleteLedgerItem = (id: string) => {
    setLedgerToDelete(id);
  };

  const executeDeleteLedgerItem = async (id: string) => {
    const updated = ledgerItems.filter(item => item.id !== id);
    try {
      const { getAuthHeaders } = useAuthStore.getState();
      const res = await fetch(`${API_BASE}/api/projects/${projectId}/renewal_ledger`, {
        method: 'POST',
        headers: { ...getAuthHeaders(), 'Content-Type': 'application/json' },
        body: JSON.stringify(updated)
      });
      if (res.ok) {
        setLedgerItems(updated);
      }
    } catch (err) {
      alert('删除失败，请重试');
    }
  };

  // ================= 审查复盘流式生成 =================
  const handleStartRetroAnalysis = async () => {
    if (!retroInput.trim()) {
      alert('请输入顾问单位近期合同审查的高频风险点或要点摘要！');
      return;
    }
    setIsGeneratingRetro(true);
    setRetroOutput('');

    if (retroAbortControllerRef.current) retroAbortControllerRef.current.abort();
    retroAbortControllerRef.current = new AbortController();

    try {
      const { token: authToken } = useAuthStore.getState();
      const res = await fetch(`${API_BASE}/api/projects/${projectId}/retrospective/stream`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': authToken ? `Bearer ${authToken}` : ''
        },
        body: JSON.stringify({ content: retroInput.trim() }),
        signal: retroAbortControllerRef.current.signal
      });

      if (!res.ok) throw new Error('流式分析失败');
      const reader = res.body?.getReader();
      if (!reader) throw new Error('未能获取流读取器');

      const decoder = new TextDecoder();
      let done = false;
      while (!done) {
        const { value, done: doneReading } = await reader.read();
        done = doneReading;
        if (value) {
          const chunk = decoder.decode(value);
          const lines = chunk.split('\n');
          for (const line of lines) {
            if (line.startsWith('data: ')) {
              const dataStr = line.slice(6).trim();
              if (dataStr === '[DONE]') continue;
              try {
                const parsed = JSON.parse(dataStr);
                if (parsed.token) {
                  setRetroOutput(prev => prev + parsed.token);
                } else if (parsed.error) {
                  setRetroOutput(prev => prev + `\n\n❌ 出错: ${parsed.error}`);
                }
              } catch (e) {
              }
            }
          }
        }
      }
    } catch (err: any) {
      if (err.name === 'AbortError') {
        console.log('复盘生成已中止');
        setRetroOutput(prev => prev + '\n\n🛑 生成已手动停止。');
      } else {
        console.error('复盘分析流出错', err);
        setRetroOutput(prev => prev + '\n\n❌ 大模型分析中途出错，请稍后重试。');
      }
    } finally {
      setIsGeneratingRetro(false);
    }
  };

  return (
    <div className="h-full w-full bg-slate-50 dark:bg-canvas-bg flex overflow-hidden">
      {/* 左侧：客户档案配置卡片 */}
      <div className="w-[320px] h-full border-r border-[#e9e5de] dark:border-border-soft bg-[#fdfcfa] dark:bg-panel-bg p-4 flex flex-col shrink-0">
        <div className="flex items-center justify-between pb-3 border-b border-[#e9e5de] dark:border-border-soft mb-4">
          <h3 className="text-sm font-bold text-stone-800 dark:text-text-main flex items-center gap-1.5">
            <Building2 className="w-4 h-4 text-amber-700" />
            顾问单位客户档案
          </h3>
          {canWrite && !isEditingProfile && (
            <button
              onClick={() => setIsEditingProfile(true)}
              className="text-xs text-amber-800 hover:text-amber-900 font-semibold bg-amber-50 hover:bg-amber-100/80 px-2 py-1 rounded transition-colors"
            >
              编辑档案
            </button>
          )}
        </div>

        {isEditingProfile ? (
          <div className="flex-1 overflow-y-auto space-y-3.5 pr-1 text-xs">
            <div>
              <label className="block text-stone-500 font-semibold mb-1">单位名称</label>
              <input
                type="text"
                value={profile.clientName}
                onChange={(e) => setProfile({ ...profile, clientName: e.target.value })}
                className="w-full px-2.5 py-1.5 border border-stone-200 rounded focus:border-amber-600 focus:outline-none bg-white text-stone-800"
              />
            </div>
            <div>
              <label className="block text-stone-500 font-semibold mb-1">主营行业</label>
              <input
                type="text"
                value={profile.industry}
                onChange={(e) => setProfile({ ...profile, industry: e.target.value })}
                className="w-full px-2.5 py-1.5 border border-stone-200 rounded focus:border-amber-600 focus:outline-none bg-white text-stone-800"
              />
            </div>
            <div>
              <label className="block text-stone-500 font-semibold mb-1">立场偏向</label>
              <select
                value={profile.stance}
                onChange={(e) => setProfile({ ...profile, stance: e.target.value })}
                className="w-full px-2.5 py-1.5 border border-stone-200 rounded focus:border-amber-600 focus:outline-none bg-white text-stone-800"
              >
                <option value="中立">中立 (顾问视角平衡立场)</option>
                <option value="保护我方利益">保护我方利益 (防守/限制相对方)</option>
                <option value="进取立场">进取立场 (促成交易/控制责任)</option>
              </select>
            </div>
            <div>
              <label className="block text-stone-500 font-semibold mb-1">客户分类</label>
              <select
                value={profile.clientType}
                onChange={(e) => setProfile({ ...profile, clientType: e.target.value })}
                className="w-full px-2.5 py-1.5 border border-stone-200 rounded focus:border-amber-600 focus:outline-none bg-white text-stone-800"
              >
                <option value="国有企业">国有企业 (合规高要求/流程严格)</option>
                <option value="民营企业">民营企业 (强调权利责任均等)</option>
                <option value="民企初创">民企初创 (轻量合规/快速落地)</option>
                <option value="外资企业">外资企业 (跨国规范/风控严格)</option>
              </select>
            </div>
            <div>
              <label className="block text-stone-500 font-semibold mb-1">检索案例范围</label>
              <input
                type="text"
                value={profile.searchLevel}
                onChange={(e) => setProfile({ ...profile, searchLevel: e.target.value })}
                className="w-full px-2.5 py-1.5 border border-stone-200 rounded focus:border-amber-600 focus:outline-none bg-white text-stone-800"
              />
            </div>
            <div>
              <label className="block text-stone-500 font-semibold mb-1">特殊审查要点</label>
              <textarea
                value={profile.specialPoints}
                onChange={(e) => setProfile({ ...profile, specialPoints: e.target.value })}
                rows={4}
                className="w-full px-2.5 py-1.5 border border-stone-200 rounded focus:border-amber-600 focus:outline-none bg-white text-stone-800 resize-none"
              />
            </div>
            <div className="flex gap-2 pt-2">
              <button
                onClick={handleSaveProfile}
                disabled={isSavingProfile}
                className="flex-1 py-1.5 bg-amber-700 hover:bg-amber-800 text-white rounded font-bold transition-all text-center disabled:opacity-50"
              >
                {isSavingProfile ? '正在保存...' : '保存'}
              </button>
              <button
                onClick={() => setIsEditingProfile(false)}
                className="px-3 py-1.5 border border-stone-200 text-stone-600 rounded hover:bg-stone-50 transition-colors text-center"
              >
                取消
              </button>
            </div>
          </div>
        ) : (
          <div className="flex-1 overflow-y-auto space-y-4 text-xs pr-1">
            <div className="bg-stone-50/60 p-3 rounded-lg border border-stone-200/50">
              <span className="text-[10px] text-stone-400 font-semibold block uppercase tracking-wider mb-0.5">公司名称</span>
              <div className="font-bold text-stone-800 text-[13px]">{profile.clientName}</div>
            </div>
            <div>
              <span className="text-[10px] text-stone-400 font-semibold block mb-0.5">主营行业</span>
              <div className="text-stone-700 font-medium">{profile.industry || '未设置'}</div>
            </div>
            <div className="grid grid-cols-2 gap-3">
              <div>
                <span className="text-[10px] text-stone-400 font-semibold block mb-0.5">立场偏向</span>
                <span className="inline-block bg-orange-50 text-orange-700 font-semibold px-2 py-0.5 rounded border border-orange-100">
                  {profile.stance}
                </span>
              </div>
              <div>
                <span className="text-[10px] text-stone-400 font-semibold block mb-0.5">客户类型</span>
                <span className="inline-block bg-blue-50 text-blue-700 font-semibold px-2 py-0.5 rounded border border-blue-100">
                  {profile.clientType}
                </span>
              </div>
            </div>
            <div>
              <span className="text-[10px] text-stone-400 font-semibold block mb-0.5">检索层级</span>
              <div className="text-stone-700 font-medium">{profile.searchLevel}</div>
            </div>
            <div>
              <span className="text-[10px] text-stone-400 font-semibold block mb-1">企业专项及特殊要点</span>
              <p className="text-stone-600 bg-stone-50 p-2.5 rounded border border-stone-100 leading-relaxed whitespace-pre-line text-[11px]">
                {profile.specialPoints || '无'}
              </p>
            </div>
          </div>
        )}
      </div>

      {/* 右侧：并列功能区 */}
      <div className="flex-1 h-full flex flex-col overflow-hidden bg-stone-50/20 dark:bg-canvas-bg/20">
        {/* Tab 切换栏 */}
        <div className="px-6 py-3 border-b border-[#e9e5de] dark:border-border-soft bg-[#faf8f5] dark:bg-outline-bg flex items-center justify-between shrink-0">
          <div className="flex gap-1.5">
            <button
              onClick={() => setActiveTab('project')}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold transition-all select-none ${
                activeTab === 'project'
                  ? 'bg-amber-700 text-white shadow-sm'
                  : 'text-stone-600 dark:text-text-muted hover:bg-stone-200/50 dark:hover:bg-outline-bg/40'
              }`}
            >
              <FileText className="w-3.5 h-3.5" />
              日常咨询与项目支持
            </button>
            <button
              onClick={() => setActiveTab('renewal')}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold transition-all select-none ${
                activeTab === 'renewal'
                  ? 'bg-amber-700 text-white shadow-sm'
                  : 'text-stone-600 dark:text-text-muted hover:bg-stone-200/50 dark:hover:bg-outline-bg/40'
              }`}
            >
              <Calendar className="w-3.5 h-3.5" />
              委托续约到期检查
            </button>
            <button
              onClick={() => setActiveTab('retrospective')}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold transition-all select-none ${
                activeTab === 'retrospective'
                  ? 'bg-amber-700 text-white shadow-sm'
                  : 'text-stone-600 dark:text-text-muted hover:bg-stone-200/50 dark:hover:bg-outline-bg/40'
              }`}
            >
              <RefreshCw className="w-3.5 h-3.5" />
              合同审查复盘报告
            </button>
          </div>
        </div>

        {/* Tab 内容区 */}
        <div className="flex-1 overflow-hidden p-6 flex flex-col">
          {activeTab === 'project' && (
            <div className="flex-1 flex flex-col gap-4 overflow-hidden">
              {/* 问题输入与参数配置 */}
              <div className="bg-white p-4 rounded-xl border border-stone-200 shadow-sm flex flex-col gap-3.5 shrink-0">
                <div>
                  <label className="block text-xs font-bold text-stone-700 mb-1.5 flex items-center gap-1">
                    <Building2 className="w-3.5 h-3.5 text-stone-500" />
                    描述日常咨询问题或项目概况
                  </label>
                  <textarea
                    value={projectQuestion}
                    onChange={(e) => setProjectQuestion(e.target.value)}
                    placeholder="例如：客户公司拟与某合作方签署一份为期三年的独家推广协议，合作方提出其不承担任何商业推广效果保证。请从常法顾问视角，分析其合规红线与违约责任设计，并出具一份法律备忘录框架。"
                    rows={3}
                    className="w-full text-xs px-3 py-2 border border-stone-200 rounded-lg focus:border-amber-600 focus:outline-none bg-stone-50/50 text-stone-800 leading-relaxed"
                  />
                </div>

                <div className="flex items-center justify-between pt-2 border-t border-stone-100">
                  <div className="flex gap-4 items-center">
                    <div className="flex items-center gap-2">
                      <span className="text-xs font-semibold text-stone-600">产出形式:</span>
                      <button
                        onClick={() => setProjectFormat('brief')}
                        className={`text-xs px-2.5 py-1 rounded border transition-colors ${
                          projectFormat === 'brief'
                            ? 'border-amber-600 bg-amber-50 text-amber-800 font-semibold'
                            : 'border-stone-200 bg-white text-stone-600 hover:bg-stone-50'
                        }`}
                      >
                        口头咨询简要回复
                      </button>
                      <button
                        onClick={() => setProjectFormat('full')}
                        className={`text-xs px-2.5 py-1 rounded border transition-colors ${
                          projectFormat === 'full'
                            ? 'border-amber-600 bg-amber-50 text-amber-800 font-semibold'
                            : 'border-stone-200 bg-white text-stone-600 hover:bg-stone-50'
                        }`}
                      >
                        正式备忘录意见书
                      </button>
                    </div>

                    <label className="flex items-center gap-1.5 cursor-pointer text-xs text-stone-600 font-semibold select-none">
                      <input
                        type="checkbox"
                        checked={enableSearch}
                        onChange={(e) => setEnableSearch(e.target.checked)}
                        className="rounded border-stone-300 text-amber-700 focus:ring-amber-600"
                      />
                      启用北大法宝案例检索
                    </label>
                  </div>

                  <div className="flex gap-2">
                    <button
                      onClick={handleStartProjectSupport}
                      disabled={isGeneratingProject}
                      className="flex items-center gap-1.5 px-4 py-2 bg-amber-700 hover:bg-amber-800 text-white rounded-lg text-xs font-bold shadow-sm transition-all disabled:opacity-50 disabled:cursor-not-allowed"
                    >
                      <Play className="w-3.5 h-3.5" />
                      {isGeneratingProject ? '正在分析中...' : 'AI 分析生成'}
                    </button>
                    {isGeneratingProject && (
                      <button
                        onClick={() => {
                          if (abortControllerRef.current) abortControllerRef.current.abort();
                        }}
                        className="flex items-center gap-1 px-3 py-2 bg-rose-600 hover:bg-rose-700 text-white rounded-lg text-xs font-bold shadow-sm transition-colors cursor-pointer"
                      >
                        停止
                      </button>
                    )}
                  </div>
                </div>
              </div>

              {/* 分析生成输出 */}
              <div className="flex-1 bg-white rounded-xl border border-stone-200 shadow-sm flex flex-col overflow-hidden">
                <div className="px-4 py-2 bg-stone-50 border-b border-stone-200 flex justify-between items-center shrink-0">
                  <span className="text-xs font-bold text-stone-700">AI 推理建议成果</span>
                  {projectOutput && (
                    <div className="flex gap-2">
                      <button
                        onClick={() => {
                          navigator.clipboard.writeText(projectOutput);
                          alert('复制成功！');
                        }}
                        className="flex items-center gap-1 px-2.5 py-1 bg-white border border-stone-200 text-stone-600 rounded text-xs font-semibold hover:bg-stone-50 transition-colors"
                      >
                        <Copy className="w-3.5 h-3.5" />
                        复制
                      </button>
                      {canWrite && (
                        <button
                          onClick={() => handleSaveProjectDocument(projectOutput, projectFormat === 'brief' ? '日常咨询解答' : '法律意见书')}
                          className="flex items-center gap-1 px-2.5 py-1 bg-emerald-600 text-white rounded text-xs font-semibold hover:bg-emerald-700 transition-colors"
                        >
                          <Save className="w-3.5 h-3.5" />
                          保存到列表
                        </button>
                      )}
                    </div>
                  )}
                </div>
                <div ref={projectOutputRef} className="flex-1 overflow-y-auto p-4 prose max-w-none text-xs text-stone-700 leading-relaxed whitespace-pre-wrap select-text bg-stone-50/20">
                  {projectOutput || (
                    <div className="text-stone-400 text-center py-16">
                      暂无生成建议，请配置上方参数并点击“AI 分析生成”开始。
                    </div>
                  )}
                </div>
              </div>
            </div>
          )}

          {/* 委托续约检查 Tab */}
          {activeTab === 'renewal' && (
            <div className="flex-1 flex flex-col gap-4 overflow-hidden relative">
              <div className="flex justify-between items-center shrink-0">
                <span className="text-xs font-bold text-stone-700">顾问合同台账列表</span>
                {canWrite && (
                  <button onClick={() => setIsModalOpen(true)} className="flex items-center gap-1 px-3 py-1.5 bg-amber-700 hover:bg-amber-800 text-white rounded text-xs font-bold shadow-sm">
                    <Plus className="w-3.5 h-3.5" /> 录入台账记录
                  </button>
                )}
              </div>

              {isLedgerLoading ? (
                <div className="text-stone-400 text-center py-16 text-xs">正在加载台账数据...</div>
              ) : ledgerItems.length === 0 ? (
                <div className="bg-white rounded-xl border border-stone-200 p-12 text-center text-stone-400 text-xs">
                  <Calendar className="w-12 h-12 mx-auto mb-2 text-stone-300" />
                  当前尚未录入常法委托台账。请点击右上角录入。
                </div>
              ) : (
                <div className="flex-1 overflow-y-auto space-y-3 pr-1">
                  {ledgerItems.map((item) => {
                    const diffDays = Math.ceil((new Date(item.endDate).getTime() - new Date().setHours(0, 0, 0, 0)) / (1000 * 60 * 60 * 24));
                    let statusLabel = '正常';
                    let badgeClass = 'bg-emerald-50 text-emerald-700 border-emerald-100';
                    let alertMsg = `距到期还有 ${diffDays} 天`;
                    if (diffDays < 0) {
                      statusLabel = '已过期';
                      badgeClass = 'bg-rose-50 text-rose-700 border-rose-100 animate-pulse';
                      alertMsg = `已过期 ${Math.abs(diffDays)} 天，请尽快联系续约！`;
                    } else if (diffDays <= 30) {
                      statusLabel = '紧急';
                      badgeClass = 'bg-orange-50 text-orange-700 border-orange-100';
                      alertMsg = `将在 ${diffDays} 天内到期，请立即联系续约！`;
                    } else if (diffDays <= 60) {
                      statusLabel = '关注';
                      badgeClass = 'bg-amber-50 text-amber-700 border-amber-100';
                      alertMsg = `将在 ${diffDays} 天内到期，建议准备续约。`;
                    }
                    return (
                      <div key={item.id} className="bg-white p-3.5 rounded-xl border border-stone-200 shadow-sm flex items-center justify-between text-xs">
                        <div className="space-y-1">
                          <div className="flex items-center gap-2">
                            <span className="font-bold text-stone-800 text-[13px]">{item.clientName}</span>
                            <span className="text-stone-400 text-[11px]">|</span>
                            <span className="text-stone-600 font-medium">{item.contractName}</span>
                          </div>
                          <div className="text-stone-500 flex gap-4 text-[11px]">
                            <span>期间：{item.startDate} ~ {item.endDate}</span>
                            <span>年费：¥{item.annualFee || '0'}</span>
                            <span>付款：{item.paymentMethod}</span>
                            <span>对接人：{item.contactPerson}</span>
                          </div>
                          <div className={`text-[11px] font-semibold mt-1 ${diffDays < 0 ? 'text-rose-600' : diffDays <= 30 ? 'text-orange-600' : 'text-stone-600'}`}>{alertMsg}</div>
                        </div>
                        <div className="flex items-center gap-3">
                          <span className={`px-2.5 py-0.5 rounded-full border text-[10px] font-bold ${badgeClass}`}>{statusLabel}</span>
                          {canWrite && (
                            <button onClick={() => handleDeleteLedgerItem(item.id)} className="text-stone-400 hover:text-rose-600 p-1 rounded">
                              <Trash2 className="w-4 h-4" />
                            </button>
                          )}
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}

              {isModalOpen && (
                <div className="absolute inset-0 bg-stone-900/40 backdrop-blur-sm flex items-center justify-center z-50 p-4">
                  <div className="bg-white rounded-xl border border-stone-200 shadow-xl w-full max-w-sm overflow-hidden flex flex-col">
                    <div className="px-4 py-3 bg-stone-50 border-b border-stone-200 flex justify-between items-center shrink-0">
                      <span className="text-xs font-bold text-stone-700">录入新委托服务台账</span>
                      <button onClick={() => setIsModalOpen(false)} className="text-stone-400 text-sm font-bold">✕</button>
                    </div>
                    <div className="p-4 space-y-3.5 text-xs overflow-y-auto flex-1 max-h-[320px]">
                      <div>
                        <label className="block text-stone-500 font-semibold mb-1">客户简称 / 合同名称</label>
                        <div className="grid grid-cols-2 gap-2">
                          <input type="text" placeholder="客户：腾讯科技" value={newItem.clientName} onChange={(e) => setNewItem({ ...newItem, clientName: e.target.value })} className="w-full px-2.5 py-1.5 border border-stone-200 text-stone-800 focus:outline-none focus:border-amber-600" />
                          <input type="text" placeholder="合同：2026顾问合同" value={newItem.contractName} onChange={(e) => setNewItem({ ...newItem, contractName: e.target.value })} className="w-full px-2.5 py-1.5 border border-stone-200 text-stone-800 focus:outline-none focus:border-amber-600" />
                        </div>
                      </div>
                      <div>
                        <label className="block text-stone-500 font-semibold mb-1">服务起始日 / 服务到期日</label>
                        <div className="grid grid-cols-2 gap-2">
                          <input type="date" value={newItem.startDate} onChange={(e) => setNewItem({ ...newItem, startDate: e.target.value })} className="w-full px-2.5 py-1.5 border border-stone-200 text-stone-800" />
                          <input type="date" value={newItem.endDate} onChange={(e) => setNewItem({ ...newItem, endDate: e.target.value })} className="w-full px-2.5 py-1.5 border border-stone-200 text-stone-800" />
                        </div>
                      </div>
                      <div className="grid grid-cols-2 gap-2">
                        <div>
                          <label className="block text-stone-500 font-semibold mb-1">年费金额 (元)</label>
                          <input type="text" placeholder="50000" value={newItem.annualFee} onChange={(e) => setNewItem({ ...newItem, annualFee: e.target.value })} className="w-full px-2.5 py-1.5 border border-stone-200 text-stone-800 focus:outline-none focus:border-amber-600" />
                        </div>
                        <div>
                          <label className="block text-stone-500 font-semibold mb-1">付款方式</label>
                          <select value={newItem.paymentMethod} onChange={(e) => setNewItem({ ...newItem, paymentMethod: e.target.value })} className="w-full px-2.5 py-1.5 border border-stone-200 text-stone-800">
                            <option value="一次性付清">一次性付清</option>
                            <option value="半年度支付">半年度支付</option>
                            <option value="按季度支付">按季度支付</option>
                          </select>
                        </div>
                      </div>
                      <div>
                        <label className="block text-stone-500 font-semibold mb-1">对接人 / 备注</label>
                        <input type="text" placeholder="张总 (总经理)" value={newItem.contactPerson} onChange={(e) => setNewItem({ ...newItem, contactPerson: e.target.value })} className="w-full px-2.5 py-1.5 border border-stone-200 text-stone-800 focus:outline-none focus:border-amber-600" />
                      </div>
                    </div>
                    <div className="px-4 py-3 bg-stone-50 border-t border-stone-200 flex gap-2 justify-end shrink-0">
                      <button onClick={handleAddLedgerItem} className="px-4 py-1.5 bg-amber-700 hover:bg-amber-800 text-white rounded font-bold transition-all text-xs">录入台账</button>
                      <button onClick={() => setIsModalOpen(false)} className="px-4 py-1.5 border border-stone-200 text-stone-600 rounded hover:bg-stone-50 transition-colors text-xs">取消</button>
                    </div>
                  </div>
                </div>
              )}
            </div>
          )}

          {/* 合同审查复盘 Tab */}
          {activeTab === 'retrospective' && (
            <div className="flex-1 flex flex-col gap-4 overflow-hidden">
              {/* 输入摘要 */}
              <div className="bg-white p-4 rounded-xl border border-stone-200 shadow-sm flex flex-col gap-3 shrink-0">
                <div>
                  <label className="block text-xs font-bold text-stone-700 mb-1.5 flex items-center gap-1">
                    <RefreshCw className="w-3.5 h-3.5 text-stone-500" />
                    输入顾问单位近期多份合同审查的主要修改摘要
                  </label>
                  <textarea
                    value={retroInput}
                    onChange={(e) => setRetroInput(e.target.value)}
                    placeholder="例如：在近期的5份采购及服务合同中，发现以下高频问题：1. 争议管辖条款全部写了‘由原告方所在地法院管辖’，但这在双务合同中易被认定无效；2. 对方交付延迟的违约金均被订为每日万分之一，而我方延迟交付的违约金却为每日万分之五，权利义务严重不对等；3. 全部缺少送达地址确认条款，导致纠纷发生时诉讼文书送达存在隐患。"
                    rows={3}
                    className="w-full text-xs px-3 py-2 border border-stone-200 rounded-lg focus:border-amber-600 focus:outline-none bg-stone-50/50 text-stone-800 leading-relaxed"
                  />
                </div>
                <div className="flex justify-end pt-1">
                  <div className="flex gap-2">
                    <button
                      onClick={handleStartRetroAnalysis}
                      disabled={isGeneratingRetro}
                      className="flex items-center gap-1.5 px-4 py-2 bg-amber-700 hover:bg-amber-800 text-white rounded-lg text-xs font-bold shadow-sm transition-all disabled:opacity-50 disabled:cursor-not-allowed"
                    >
                      <Play className="w-3.5 h-3.5" />
                      {isGeneratingRetro ? '正在分析生成...' : '一键开始深度复盘'}
                    </button>
                    {isGeneratingRetro && (
                      <button
                        onClick={() => {
                          if (retroAbortControllerRef.current) retroAbortControllerRef.current.abort();
                        }}
                        className="flex items-center gap-1 px-3 py-2 bg-rose-600 hover:bg-rose-700 text-white rounded-lg text-xs font-bold shadow-sm transition-colors cursor-pointer"
                      >
                        停止
                      </button>
                    )}
                  </div>
                </div>
              </div>

              {/* 报告输出 */}
              <div className="flex-1 bg-white rounded-xl border border-stone-200 shadow-sm flex flex-col overflow-hidden">
                <div className="px-4 py-2 bg-stone-50 border-b border-stone-200 flex justify-between items-center shrink-0">
                  <span className="text-xs font-bold text-stone-700">合同模板优化建议报告 (Markdown)</span>
                  {retroOutput && (
                    <div className="flex gap-2">
                      <button
                        onClick={() => {
                          navigator.clipboard.writeText(retroOutput);
                          alert('复制成功！');
                        }}
                        className="flex items-center gap-1 px-2.5 py-1 bg-white border border-stone-200 text-stone-600 rounded text-xs font-semibold hover:bg-stone-50 transition-colors"
                      >
                        <Copy className="w-3.5 h-3.5" />
                        复制
                      </button>
                      {canWrite && (
                        <button
                          onClick={() => handleSaveProjectDocument(retroOutput, '合同复盘及优化建议报告')}
                          className="flex items-center gap-1 px-2.5 py-1 bg-emerald-600 text-white rounded text-xs font-semibold hover:bg-emerald-700 transition-colors"
                        >
                          <Save className="w-3.5 h-3.5" />
                          保存到列表
                        </button>
                      )}
                    </div>
                  )}
                </div>
                <div ref={retroOutputRef} className="flex-1 overflow-y-auto p-4 prose max-w-none text-xs text-stone-700 leading-relaxed whitespace-pre-wrap select-text bg-stone-50/20">
                  {retroOutput || (
                    <div className="text-stone-400 text-center py-16">
                      请输入上方近期合同的审查修改点，点击“一键开始深度复盘”生成合同模板优化建议。
                    </div>
                  )}
                </div>
              </div>
            </div>
          )}
        </div>
      </div>

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
                    void executeSaveProjectDocument(saveDocInfo.text, saveDocInfo.title.trim());
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
                    void executeSaveProjectDocument(saveDocInfo.text, saveDocInfo.title.trim());
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

      {ledgerToDelete && createPortal(
        <div className="fixed inset-0 z-[9999] flex items-center justify-center p-4 select-none">
          <div 
            className="absolute inset-0 bg-[#0F0F11]/45 backdrop-blur-[2px] transition-opacity" 
            onClick={() => setLedgerToDelete(null)}
          />
          <div className="relative bg-white dark:bg-[#1E1F22] rounded-xl p-5 shadow-2xl border border-stone-200 dark:border-stone-850 max-w-sm w-full flex flex-col gap-4 animate-in fade-in zoom-in-95 duration-200" onClick={e => e.stopPropagation()}>
            <div className="flex items-start gap-3 text-stone-800 dark:text-stone-200">
              <div className="p-2.5 rounded-full bg-red-50 dark:bg-red-950/20 text-red-600 dark:text-red-400 shrink-0">
                <AlertTriangle className="w-5 h-5" />
              </div>
              <div className="flex flex-col gap-1 min-w-0">
                <h3 className="text-sm font-bold text-stone-900 dark:text-stone-100">
                  🗑️ 删除台账记录
                </h3>
                <p className="text-xs text-stone-500 dark:text-stone-400 leading-normal mt-3 whitespace-pre-wrap font-sans">
                  确定要彻底删除这条台账记录吗？此操作不可逆。
                </p>
              </div>
            </div>
            <div className="flex justify-end gap-2 mt-2">
              <button
                onClick={() => setLedgerToDelete(null)}
                className="px-4 py-1.5 text-xs font-semibold text-stone-600 dark:text-stone-300 hover:text-stone-800 dark:hover:text-stone-100 hover:bg-stone-50 dark:hover:bg-stone-800 rounded-lg transition-colors border border-stone-200 dark:border-stone-700 cursor-pointer"
              >
                取消
              </button>
              <button
                onClick={() => {
                  void executeDeleteLedgerItem(ledgerToDelete);
                  setLedgerToDelete(null);
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
    </div>
  );
}
