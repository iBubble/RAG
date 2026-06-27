import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { Home, RefreshCw } from 'lucide-react';
import { useAuthStore } from '../../store/authStore';
import LinvisWhiteboard from './LinvisWhiteboard';
import LinvisDesk from './LinvisDesk';
import './Linvis3D.css';


interface SystemStatus {
  active_tasks: number;
  funny_level: string;
  linvis_name: string;
  whiteboard_items: string[];
  visible_agents: string[];
  whiteboard: {
    total_projects: number;
    total_files: number;
    completed_percent: number;
    total_chunks: number;
    total_entities: number;
    slow_queue_tasks: number;
    fast_queue_tasks: number;
  };
}

interface AgentInfo {
  status: 'working' | 'sleeping' | 'funny' | 'idle' | 'interrupted';
  funny_event: string | null;
  current_project: string | null;
  current_task: string | null;
}

interface LinvisData {
  system_status: SystemStatus;
  agents: {
    vectorizer: AgentInfo;
    graph: AgentInfo;
    summary: AgentInfo;
    precompute: AgentInfo;
    chat: AgentInfo;
    legal: AgentInfo;
    service: AgentInfo;
    planner: AgentInfo;
    checker: AgentInfo;
    auditor: AgentInfo;
  };
}

const defaultStatus: LinvisData = {
  system_status: {
    active_tasks: 0,
    funny_level: 'low',
    linvis_name: '麟维斯',
    whiteboard_items: ['total_projects', 'completed_percent', 'total_chunks', 'total_entities', 'queue_tasks'],
    visible_agents: ['vectorizer', 'graph', 'summary', 'precompute', 'chat', 'legal', 'service'],
    whiteboard: {
      total_projects: 0,
      total_files: 0,
      completed_percent: 100,
      total_chunks: 0,
      total_entities: 0,
      slow_queue_tasks: 0,
      fast_queue_tasks: 0
    }
  },
  agents: {
    vectorizer: { status: 'idle', funny_event: null, current_project: null, current_task: null },
    graph: { status: 'idle', funny_event: null, current_project: null, current_task: null },
    summary: { status: 'idle', funny_event: null, current_project: null, current_task: null },
    precompute: { status: 'idle', funny_event: null, current_project: null, current_task: null },
    chat: { status: 'idle', funny_event: null, current_project: null, current_task: null },
    legal: { status: 'idle', funny_event: null, current_project: null, current_task: null },
    service: { status: 'idle', funny_event: null, current_project: null, current_task: null },
    planner: { status: 'idle', funny_event: null, current_project: null, current_task: null },
    checker: { status: 'idle', funny_event: null, current_project: null, current_task: null },
    auditor: { status: 'idle', funny_event: null, current_project: null, current_task: null }
  }
};

export default function Linvis() {
  const navigate = useNavigate();
  const { getAuthHeaders } = useAuthStore();
  const [data, setData] = useState<LinvisData>(defaultStatus);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  const [showAuditModal, setShowAuditModal] = useState(false);
  const [auditProjectId, setAuditProjectId] = useState<string | null>(null);
  const [frozenData, setFrozenData] = useState<any>(null);
  const [editDraft, setEditDraft] = useState('');
  const [resumeStreamOutput, setResumeStreamOutput] = useState('');
  const [isResuming, setIsResuming] = useState(false);

  const API_BASE = import.meta.env.VITE_API_BASE || '';

  const handleOpenAuditModal = async (projectId: string) => {
    try {
      setAuditProjectId(projectId);
      setFrozenData(null);
      setEditDraft('');
      setResumeStreamOutput('');
      setIsResuming(false);
      setShowAuditModal(true);

      const res = await fetch(`${API_BASE}/api/eino/frozen/${projectId}`, {
        headers: getAuthHeaders()
      });
      if (res.ok) {
        const json = await res.json();
        if (json.status === 'success') {
          setFrozenData(json.data);
          setEditDraft(json.data.draft || '');
        }
      }
    } catch (e) {
      console.error("加载冻结状态失败", e);
    }
  };

  const handleResume = async () => {
    if (!auditProjectId) return;
    setIsResuming(true);
    setResumeStreamOutput('');
    try {
      const response = await fetch(`${API_BASE}/api/eino/resume`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          ...getAuthHeaders()
        },
        body: JSON.stringify({
          project_id: auditProjectId,
          draft: editDraft
        })
      });

      if (!response.ok) {
        throw new Error(`HTTP status ${response.status}`);
      }

      const reader = response.body?.getReader();
      const decoder = new TextDecoder();
      if (!reader) return;

      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        const chunk = decoder.decode(value);
        const lines = chunk.split('\n');
        for (const line of lines) {
          if (line.startsWith('data: ')) {
            try {
              const payload = JSON.parse(line.slice(6));
              if (payload.type === 'token') {
                setResumeStreamOutput(prev => prev + payload.content);
              }
            } catch (e) {
              // 忽略解析异常
            }
          }
        }
      }
    } catch (e) {
      console.error("恢复执行失败", e);
      setResumeStreamOutput(prev => prev + `\n❌ 恢复失败: ${e}`);
    } finally {
      setIsResuming(false);
      fetchData();
    }
  };

  const fetchData = async () => {
    try {
      setRefreshing(true);
      const res = await fetch(`${API_BASE}/api/projects/linvis-status`, {
        headers: getAuthHeaders()
      });
      if (res.ok) {
        setData(await res.json());
      }
    } catch (e) {
      console.error("无法获取看板状态", e);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  };

  useEffect(() => {
    fetchData();
    const timer = setInterval(fetchData, 5000); // 5秒自动轮询，实现看板近实时联动
    return () => clearInterval(timer);
  }, []);

  const showAgent = (agentId: string) => {
    const list = data.system_status.visible_agents || [];
    return list.includes(agentId);
  };

  const hasVisibleInZone = (zoneAgents: string[]) => {
    return zoneAgents.some(a => showAgent(a));
  };

  const getAgentProps = (key: string, defaultName: string, defaultGender: 'male' | 'female', defaultAvatar: 'ox' | 'horse' | 'human' | 'robot') => {
    const s = data.system_status as any;
    return {
      name: s[`agent_${key}_name`] || defaultName,
      gender: (s[`agent_${key}_gender`] || defaultGender) as 'male' | 'female',
      avatar: (s[`agent_${key}_avatar`] || defaultAvatar) as 'ox' | 'horse' | 'human' | 'robot'
    };
  };

  // 设置网页 Title 随配置动态改变
  useEffect(() => {
    if (data.system_status.linvis_name) {
      document.title = data.system_status.linvis_name;
    }
  }, [data.system_status.linvis_name]);

  if (loading) {
    return (
      <div className="flex flex-col h-screen w-full items-center justify-center bg-[#f0ede8]">
        <RefreshCw className="w-10 h-10 text-indigo-600 animate-spin mb-4" />
        <p className="text-gray-500 font-medium">麟维斯办公室正在开门中...</p>
      </div>
    );
  }



  return (
    <div className="min-h-screen bg-[#f7f5f0] dark:bg-canvas-bg p-4 font-sans relative pb-8">
      
      {/* 顶部工具栏 */}
      <div className="max-w-7xl mx-auto flex items-center justify-between mb-4">
        <button
          onClick={() => navigate('/')}
          className="flex items-center gap-2 px-4 py-2.5 bg-white border border-[#e0dcd5] rounded-xl hover:bg-gray-50 text-gray-700 text-sm font-semibold transition-all shadow-sm cursor-pointer"
        >
          <Home className="w-4 h-4 text-gray-500" />
          <span>返回事项空间</span>
        </button>

        <button
          onClick={fetchData}
          disabled={refreshing}
          className="p-2.5 bg-white border border-[#e0dcd5] rounded-xl hover:bg-gray-50 text-gray-600 disabled:opacity-50 transition-all shadow-sm cursor-pointer"
          title="手动刷新"
        >
          <RefreshCw className={`w-4 h-4 ${refreshing ? 'animate-spin' : ''}`} />
        </button>
      </div>

      <div className="max-w-7xl mx-auto space-y-4">
        {/* 粉笔白板 */}
        <LinvisWhiteboard status={data.system_status} />

        {/* ====== 简洁办公室场景 ====== */}
        <div className="office-scene">
          <div className="office-floor" />

          <div className="office-content">
            {/* 第一排：业务处理区 */}
            {/* 第一排：业务处理区 */}
            {/* 第一排：业务处理区 */}
            {hasVisibleInZone(['chat', 'service', 'planner', 'checker', 'auditor']) && (
              <div className="office-zone">
                <div className="zone-sign-arrow-container">
                  <svg width="110" height="150" viewBox="0 0 110 150" className="zone-arrow-svg">
                    <path 
                      d="M 15 150 L 15 50 Q 15 25 35 25 L 75 25 L 75 10 L 105 42.5 L 75 75 L 75 60 L 55 60 Q 50 60 50 65 L 50 150 Z" 
                      fill="#b91c1c" 
                      stroke="#ffffff" 
                      strokeWidth="3.5"
                      strokeLinejoin="round"
                    />
                    <path 
                      d="M 18 147 L 18 50 Q 18 28 35 28 L 73 28 L 73 18 L 98 42.5 L 73 67 L 73 57 L 55 57 Q 53 57 53 62 L 53 147 Z" 
                      fill="none" 
                      stroke="#ffffff" 
                      strokeWidth="1.5" 
                      strokeDasharray="3 3"
                      opacity="0.9"
                    />
                    <text x="32.5" y="65" fill="#ffffff" fontSize="13" textAnchor="middle">🛎️</text>
                    <text 
                      x="32.5" 
                      y="78" 
                      fill="#ffffff" 
                      fontSize="11" 
                      fontWeight="900" 
                      textAnchor="middle" 
                      letterSpacing="3"
                      style={{ writingMode: 'vertical-rl' }}
                    >
                      业务处理
                    </text>
                  </svg>
                </div>
                <div className="desk-row">
                  {showAgent('chat') && <LinvisDesk agentKey="chat" {...getAgentProps('chat', '小智(Smart)', 'male', 'horse')} roleTitle="智能客服咨询" info={data.agents.chat} />}
                  {showAgent('planner') && <LinvisDesk agentKey="planner" {...getAgentProps('planner', '小划 (Planner)', 'male', 'robot')} roleTitle="Eino任务规划" info={data.agents.planner} />}
                  {showAgent('checker') && <LinvisDesk agentKey="checker" {...getAgentProps('checker', '小定量 (Checker)', 'female', 'robot')} roleTitle="Eino定量校验" info={data.agents.checker} />}
                  {showAgent('auditor') && (
                    <div
                      onClick={() => {
                        if (data.agents.auditor.status === 'interrupted') {
                          const pid = data.agents.auditor.current_project;
                          if (pid) handleOpenAuditModal(pid);
                        }
                      }}
                      className={data.agents.auditor.status === 'interrupted' ? 'cursor-pointer' : ''}
                    >
                      <LinvisDesk agentKey="auditor" {...getAgentProps('auditor', '小定性 (Auditor)', 'male', 'robot')} roleTitle="Eino定性审计" info={data.agents.auditor} />
                    </div>
                  )}
                </div>
              </div>
            )}

            {/* 第二排：项目处理组 */}
            {hasVisibleInZone(['legal', 'precompute', 'service']) && (
              <div className="office-zone">
                <div className="zone-sign-arrow-container">
                  <svg width="110" height="150" viewBox="0 0 110 150" className="zone-arrow-svg">
                    <path 
                      d="M 15 150 L 15 50 Q 15 25 35 25 L 75 25 L 75 10 L 105 42.5 L 75 75 L 75 60 L 55 60 Q 50 60 50 65 L 50 150 Z" 
                      fill="#ea580c" 
                      stroke="#ffffff" 
                      strokeWidth="3.5"
                      strokeLinejoin="round"
                    />
                    <path 
                      d="M 18 147 L 18 50 Q 18 28 35 28 L 73 28 L 73 18 L 98 42.5 L 73 67 L 73 57 L 55 57 Q 53 57 53 62 L 53 147 Z" 
                      fill="none" 
                      stroke="#ffffff" 
                      strokeWidth="1.5" 
                      strokeDasharray="3 3"
                      opacity="0.9"
                    />
                    <text x="32.5" y="65" fill="#ffffff" fontSize="13" textAnchor="middle">💡</text>
                    <text 
                      x="32.5" 
                      y="78" 
                      fill="#ffffff" 
                      fontSize="11" 
                      fontWeight="900" 
                      textAnchor="middle" 
                      letterSpacing="3"
                      style={{ writingMode: 'vertical-rl' }}
                    >
                      核心项目
                    </text>
                  </svg>
                </div>
                <div className="desk-row">
                  {showAgent('service') && <LinvisDesk agentKey="service" {...getAgentProps('service', '小管 (Manager)', 'female', 'horse')} roleTitle="文书审查专家" info={data.agents.service} />}
                  {showAgent('legal') && <LinvisDesk agentKey="legal" {...getAgentProps('legal', '执法知识专家', 'male', 'horse')} roleTitle="执法知识专家" info={data.agents.legal} />}
                  {showAgent('precompute') && <LinvisDesk agentKey="precompute" {...getAgentProps('precompute', '小预 (Precalc)', 'male', 'horse')} roleTitle="智能学习预计算" info={data.agents.precompute} />}
                </div>
              </div>
            )}

            {/* 第三排：资料处理组 */}
            {hasVisibleInZone(['vectorizer', 'graph', 'summary']) && (
              <div className="office-zone">
                <div className="zone-sign-arrow-container">
                  <svg width="110" height="150" viewBox="0 0 110 150" className="zone-arrow-svg">
                    <path 
                      d="M 15 150 L 15 50 Q 15 25 35 25 L 75 25 L 75 10 L 105 42.5 L 75 75 L 75 60 L 55 60 Q 50 60 50 65 L 50 150 Z" 
                      fill="#851c1c" 
                      stroke="#ffffff" 
                      strokeWidth="3.5"
                      strokeLinejoin="round"
                    />
                    <path 
                      d="M 18 147 L 18 50 Q 18 28 35 28 L 73 28 L 73 18 L 98 42.5 L 73 67 L 73 57 L 55 57 Q 53 57 53 62 L 53 147 Z" 
                      fill="none" 
                      stroke="#ffffff" 
                      strokeWidth="1.5" 
                      strokeDasharray="3 3"
                      opacity="0.9"
                    />
                    <text x="32.5" y="65" fill="#ffffff" fontSize="13" textAnchor="middle">📁</text>
                    <text 
                      x="32.5" 
                      y="78" 
                      fill="#ffffff" 
                      fontSize="11" 
                      fontWeight="900" 
                      textAnchor="middle" 
                      letterSpacing="3"
                      style={{ writingMode: 'vertical-rl' }}
                    >
                      资料工坊
                    </text>
                  </svg>
                </div>
                <div className="desk-row">
                  {showAgent('vectorizer') && <LinvisDesk agentKey="vectorizer" {...getAgentProps('vectorizer', '小向 (Vector)', 'male', 'horse')} roleTitle="后端向量化入库" info={data.agents.vectorizer} />}
                  {showAgent('graph') && <LinvisDesk agentKey="graph" {...getAgentProps('graph', '小图 (Graphy)', 'female', 'horse')} roleTitle="知识图谱提炼" info={data.agents.graph} />}
                  {showAgent('summary') && <LinvisDesk agentKey="summary" {...getAgentProps('summary', '小聚 (Communer)', 'male', 'horse')} roleTitle="图谱社区摘要" info={data.agents.summary} />}
                </div>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* 法务人工审核控制台 (Modal) */}
      {showAuditModal && (
        <div className="fixed inset-0 bg-slate-900/60 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div className="bg-white rounded-3xl border border-[#e0dcd5] shadow-2xl w-full max-w-4xl max-h-[85vh] overflow-hidden flex flex-col select-none">
            
            {/* Modal 头部 */}
            <div className="px-6 py-4 bg-gradient-to-r from-amber-50 to-orange-50 border-b border-[#e0dcd5] flex items-center justify-between">
              <div className="flex items-center gap-2.5">
                <span className="text-2xl">⚖️</span>
                <div>
                  <h3 className="font-bold text-gray-900 text-base">Eino 法务合规审查控制台</h3>
                  <p className="text-xs text-gray-500">发现严重合规警报，正在人机共创拦截挂起中</p>
                </div>
              </div>
              <button 
                onClick={() => setShowAuditModal(false)}
                className="text-gray-400 hover:text-gray-600 font-bold text-lg p-1.5 hover:bg-gray-100 rounded-full cursor-pointer"
              >
                ✕
              </button>
            </div>

            {/* Modal 内容 */}
            <div className="flex-1 overflow-y-auto p-6 space-y-4">
              {!frozenData ? (
                <div className="flex flex-col items-center justify-center py-12 space-y-3">
                  <div className="w-8 h-8 border-4 border-amber-500 border-t-transparent rounded-full animate-spin"></div>
                  <p className="text-sm text-gray-500">正在恢复断点并加载 Redis 冻结状态...</p>
                </div>
              ) : (
                <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
                  {/* 左边：审查上下文 */}
                  <div className="space-y-4">
                    <div>
                      <h4 className="text-xs font-black text-gray-400 uppercase tracking-widest mb-1.5">👤 原始用户提问</h4>
                      <div className="p-3 bg-gray-50 border border-gray-200 rounded-2xl text-gray-800 text-sm font-medium leading-relaxed max-h-32 overflow-y-auto">
                        {frozenData.request?.message}
                      </div>
                    </div>

                    <div>
                      <h4 className="text-xs font-black text-amber-600 uppercase tracking-widest mb-1.5 flex items-center gap-1">
                        ⚠️ 定量规则校验 (Checker 拦截意见)
                      </h4>
                      <div className="p-3 bg-amber-50 border border-amber-200 text-amber-900 text-sm rounded-2xl leading-relaxed max-h-48 overflow-y-auto whitespace-pre-wrap">
                        {frozenData.check_result}
                      </div>
                    </div>
                  </div>

                  {/* 右边：草稿编辑与输出 */}
                  <div className="space-y-4 flex flex-col h-full">
                    <div className="flex-1 flex flex-col min-h-[220px]">
                      <h4 className="text-xs font-black text-gray-400 uppercase tracking-widest mb-1.5">📝 智能初稿修改器</h4>
                      <textarea
                        value={editDraft}
                        onChange={(e) => setEditDraft(e.target.value)}
                        disabled={isResuming}
                        className="flex-1 p-3 border border-gray-200 rounded-2xl text-sm font-medium leading-relaxed resize-none focus:outline-none focus:ring-2 focus:ring-amber-500 focus:border-transparent bg-white text-gray-800"
                        placeholder="在此修改违规草稿，确保合规后点击恢复..."
                      />
                    </div>

                    {/* 流式输出 */}
                    {(resumeStreamOutput || isResuming) && (
                      <div>
                        <h4 className="text-xs font-black text-indigo-600 uppercase tracking-widest mb-1.5 flex items-center gap-1 animate-pulse">
                          ⚖️ Auditor 定性最终流式输出
                        </h4>
                        <div className="p-3 bg-indigo-50/50 border border-indigo-100 rounded-2xl text-gray-800 text-sm font-medium leading-relaxed max-h-36 overflow-y-auto whitespace-pre-wrap">
                          {resumeStreamOutput || "正在连接 Go 网关恢复端点..."}
                        </div>
                      </div>
                    )}
                  </div>
                </div>
              )}
            </div>

            {/* Modal 底部 */}
            <div className="px-6 py-4 border-t border-[#e0dcd5] bg-gray-50 flex justify-end gap-3">
              <button
                onClick={() => setShowAuditModal(false)}
                className="px-5 py-2.5 bg-white border border-gray-200 text-gray-700 rounded-xl hover:bg-gray-100 text-sm font-bold cursor-pointer"
              >
                取消
              </button>
              <button
                onClick={handleResume}
                disabled={!frozenData || isResuming}
                className="px-6 py-2.5 bg-gradient-to-r from-amber-500 to-orange-600 hover:from-amber-600 hover:to-orange-700 text-white rounded-xl disabled:opacity-50 text-sm font-bold shadow-md cursor-pointer flex items-center gap-1.5"
              >
                {isResuming ? (
                  <>
                    <div className="w-3.5 h-3.5 border-2 border-white border-t-transparent rounded-full animate-spin"></div>
                    <span>正在恢复生成...</span>
                  </>
                ) : (
                  <>
                    <span>批准通过并恢复 (Resume)</span>
                  </>
                )}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
