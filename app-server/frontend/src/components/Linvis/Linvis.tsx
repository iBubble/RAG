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
  status: 'working' | 'sleeping' | 'funny' | 'idle';
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
    contrarian: AgentInfo;
    arbiter: AgentInfo;
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
    contrarian: { status: 'idle', funny_event: null, current_project: null, current_task: null },
    arbiter: { status: 'idle', funny_event: null, current_project: null, current_task: null }
  }
};

export default function Linvis() {
  const navigate = useNavigate();
  const { getAuthHeaders } = useAuthStore();
  const [data, setData] = useState<LinvisData>(defaultStatus);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);

  const API_BASE = import.meta.env.VITE_API_BASE || '';

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
    return () => {
      document.title = '力诺通用知识库RAG';
    };
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
          <span>返回案件空间</span>
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

        {/* 实际办公室环境 (一整片 3D 大地板，带地毯分区排布) */}
        <div className="linvis-office-floor w-full min-h-[500px] flex flex-col gap-6 relative">
          
          {/* 3D 办公室吊顶/吊灯投影效果 */}
          <div className="absolute inset-0 bg-gradient-to-tr from-transparent via-white/5 to-white/10 pointer-events-none z-20"></div>

          {/* 1. 接待区 (前台地毯) */}
          {hasVisibleInZone(['chat', 'service', 'contrarian', 'arbiter']) && (
            <div className="carpet-reception rounded-[24px] pt-10 pb-4 pl-24 pr-4 flex flex-col items-center relative z-10">
              {/* 3D 窗户光影投影 */}
              <div className="absolute right-[-10px] top-[-10px] w-48 h-48 bg-white/25 rotate-12 blur-sm pointer-events-none" style={{ clipPath: 'polygon(10% 0%, 100% 0%, 90% 100%, 0% 100%)' }}></div>
              <div className="absolute right-10 top-5 w-12 h-24 border border-white/10 opacity-30 pointer-events-none"></div>
              
              {/* 竖向 3D 挂牌 */}
              <div className="absolute left-8 top-1/2 -translate-y-1/2 flex flex-col items-center z-20">
                {/* 两个小挂钩 */}
                <div className="flex justify-between w-8 px-1.5">
                  <div className="w-2.5 h-2.5 rounded-full bg-gradient-to-br from-gray-200 via-gray-400 to-gray-600 shadow-[1px_2px_3px_rgba(0,0,0,0.2)] border border-gray-400"></div>
                  <div className="w-2.5 h-2.5 rounded-full bg-gradient-to-br from-gray-200 via-gray-400 to-gray-600 shadow-[1px_2px_3px_rgba(0,0,0,0.2)] border border-gray-400"></div>
                </div>
                {/* 挂绳 */}
                <div className="flex justify-between w-8 h-8 px-2.5 -mt-0.5 opacity-80">
                  <div className="w-[2px] h-full bg-gradient-to-b from-gray-500 to-[#f43f5e]"></div>
                  <div className="w-[2px] h-full bg-gradient-to-b from-gray-500 to-[#f43f5e]"></div>
                </div>
                {/* 吊牌本体 */}
                <div className="px-3 py-4 bg-gradient-to-b from-[#fff1f2] to-[#fda4af] border-2 border-[#f43f5e] border-b-4 border-r-4 rounded-2xl wood-sign-3d flex flex-col items-center gap-2 select-none animate-sign-swing">
                  <span className="text-lg animate-pulse filter drop-shadow-[0_2px_3px_rgba(0,0,0,0.15)]">🛎️</span>
                  <div className="flex flex-col items-center text-[11px] font-black text-rose-950 tracking-widest leading-none gap-0.5">
                    {"智能前台接待".split("").map((char, idx) => (
                      <span key={idx} className="filter drop-shadow-[0.5px_0.5px_0px_rgba(255,255,255,0.7)]">{char}</span>
                    ))}
                  </div>
                </div>
              </div>
              
              <div className="flex flex-wrap justify-center gap-16 z-10">
                {showAgent('chat') && <LinvisDesk agentKey="chat" {...getAgentProps('chat', '小诺 (Linuo)', 'male', 'horse')} roleTitle="智能对话专家" info={data.agents.chat} />}
                {showAgent('service') && <LinvisDesk agentKey="service" {...getAgentProps('service', '小管 (Manager)', 'female', 'horse')} roleTitle="文档审查专家" info={data.agents.service} />}
              </div>

              {/* 3D 粘土盆栽 */}
              <div className="absolute bottom-3 left-4 w-12 h-14 opacity-90 pointer-events-none z-10">
                <svg viewBox="0 0 40 50" className="w-full h-full drop-shadow-md">
                  <ellipse cx="20" cy="40" rx="10" ry="6" fill="#e11d48" />
                  <path d="M12,40 L15,28 L25,28 L28,40 Z" fill="#f43f5e" />
                  <ellipse cx="20" cy="28" rx="8" ry="3" fill="#fda4af" />
                  {/* 绿叶 */}
                  <path d="M20,28 Q20,10 12,14 Q20,20 20,28 Z" fill="#10b981" />
                  <path d="M20,28 Q25,8 28,18 Q22,22 20,28 Z" fill="#059669" />
                  <path d="M20,28 Q10,18 20,22 Z" fill="#34d399" />
                </svg>
              </div>
            </div>
          )}

          {/* 2. 项目处理区 (项目地毯) */}
          {hasVisibleInZone(['legal', 'precompute']) && (
            <div className="carpet-case rounded-[24px] pt-10 pb-4 pl-24 pr-4 flex flex-col items-center relative z-20">
              {/* 3D 窗户光影投影 */}
              <div className="absolute left-[-20px] top-[-10px] w-48 h-48 bg-white/30 -rotate-12 blur-sm pointer-events-none" style={{ clipPath: 'polygon(0% 0%, 90% 0%, 100% 100%, 10% 100%)' }}></div>
              
              {/* 竖向 3D 挂牌 */}
              <div className="absolute left-8 top-1/2 -translate-y-1/2 flex flex-col items-center z-20">
                {/* 两个小挂钩 */}
                <div className="flex justify-between w-8 px-1.5">
                  <div className="w-2.5 h-2.5 rounded-full bg-gradient-to-br from-gray-200 via-gray-400 to-gray-600 shadow-[1px_2px_3px_rgba(0,0,0,0.2)] border border-gray-400"></div>
                  <div className="w-2.5 h-2.5 rounded-full bg-gradient-to-br from-gray-200 via-gray-400 to-gray-600 shadow-[1px_2px_3px_rgba(0,0,0,0.2)] border border-gray-400"></div>
                </div>
                {/* 挂绳 */}
                <div className="flex justify-between w-8 h-8 px-2.5 -mt-0.5 opacity-80">
                  <div className="w-[2px] h-full bg-gradient-to-b from-gray-500 to-[#d97706]"></div>
                  <div className="w-[2px] h-full bg-gradient-to-b from-gray-500 to-[#d97706]"></div>
                </div>
                {/* 吊牌本体 */}
                <div className="px-3 py-4 bg-gradient-to-b from-[#fef3c7] to-[#f59e0b] border-2 border-[#d97706] border-b-4 border-r-4 rounded-2xl wood-sign-3d flex flex-col items-center gap-2 select-none animate-sign-swing-reverse">
                  <span className="text-lg filter drop-shadow-[0_2px_3px_rgba(0,0,0,0.15)]">💡</span>
                  <div className="flex flex-col items-center text-[11px] font-black text-amber-950 tracking-widest leading-none gap-0.5">
                    {"核心项目处理".split("").map((char, idx) => (
                      <span key={idx} className="filter drop-shadow-[0.5px_0.5px_0px_rgba(255,255,255,0.7)]">{char}</span>
                    ))}
                  </div>
                </div>
              </div>
              
              <div className="flex flex-wrap justify-center gap-16 z-10">
                {showAgent('legal') && <LinvisDesk agentKey="legal" {...getAgentProps('legal', '行业知识专家', 'male', 'horse')} roleTitle="行业知识专家" info={data.agents.legal} />}
                {showAgent('precompute') && <LinvisDesk agentKey="precompute" {...getAgentProps('precompute', '小预 (Precalc)', 'male', 'horse')} roleTitle="智能学习预计算" info={data.agents.precompute} />}
              </div>

              {/* 3D 粘土落地灯 */}
              <div className="absolute bottom-2 right-4 w-10 h-20 opacity-95 pointer-events-none z-10">
                <svg viewBox="0 0 30 60" className="w-full h-full drop-shadow-md">
                  <ellipse cx="15" cy="55" rx="10" ry="3" fill="#78350f" />
                  <line x1="15" y1="55" x2="15" y2="25" stroke="#d97706" strokeWidth="2.5" />
                  {/* 灯罩 */}
                  <path d="M7,25 L23,25 L19,12 L11,12 Z" fill="#fbbf24" />
                  <ellipse cx="15" cy="25" rx="8" ry="2.5" fill="#f59e0b" />
                  {/* 柔和的灯光漫反射圈 */}
                  <circle cx="15" cy="25" r="14" fill="#fbbf24" opacity="0.15" />
                </svg>
              </div>
            </div>
          )}

          {/* 3. 资料处理工作区 (资料地毯) */}
          {hasVisibleInZone(['vectorizer', 'graph', 'summary']) && (
            <div className="carpet-data rounded-[24px] pt-10 pb-4 pl-24 pr-4 flex flex-col items-center relative z-30">
              {/* 3D 窗户光影投影 */}
              <div className="absolute right-[-20px] top-[-10px] w-56 h-56 bg-white/25 rotate-45 blur-sm pointer-events-none" style={{ clipPath: 'polygon(15% 0%, 100% 0%, 85% 100%, 0% 100%)' }}></div>
              
              {/* 竖向 3D 挂牌 */}
              <div className="absolute left-8 top-1/2 -translate-y-1/2 flex flex-col items-center z-20">
                {/* 两个小挂钩 */}
                <div className="flex justify-between w-8 px-1.5">
                  <div className="w-2.5 h-2.5 rounded-full bg-gradient-to-br from-gray-200 via-gray-400 to-gray-600 shadow-[1px_2px_3px_rgba(0,0,0,0.2)] border border-gray-400"></div>
                  <div className="w-2.5 h-2.5 rounded-full bg-gradient-to-br from-gray-200 via-gray-400 to-gray-600 shadow-[1px_2px_3px_rgba(0,0,0,0.2)] border border-gray-400"></div>
                </div>
                {/* 挂绳 */}
                <div className="flex justify-between w-8 h-8 px-2.5 -mt-0.5 opacity-80">
                  <div className="w-[2px] h-full bg-gradient-to-b from-gray-500 to-[#0284c7]"></div>
                  <div className="w-[2px] h-full bg-gradient-to-b from-gray-500 to-[#0284c7]"></div>
                </div>
                {/* 吊牌本体 */}
                <div className="px-3 py-4 bg-gradient-to-b from-[#f0f9ff] to-[#7dd3fc] border-2 border-[#0284c7] border-b-4 border-r-4 rounded-2xl wood-sign-3d flex flex-col items-center gap-2 select-none animate-sign-swing">
                  <span className="text-lg filter drop-shadow-[0_2px_3px_rgba(0,0,0,0.15)]">📁</span>
                  <div className="flex flex-col items-center text-[11px] font-black text-sky-950 tracking-widest leading-none gap-0.5">
                    {"资料处理工作".split("").map((char, idx) => (
                      <span key={idx} className="filter drop-shadow-[0.5px_0.5px_0px_rgba(255,255,255,0.7)]">{char}</span>
                    ))}
                  </div>
                </div>
              </div>
              
              <div className="flex flex-wrap justify-center gap-16 z-10">
                {showAgent('vectorizer') && <LinvisDesk agentKey="vectorizer" {...getAgentProps('vectorizer', '小向 (Vector)', 'male', 'horse')} roleTitle="后端向量化入库" info={data.agents.vectorizer} />}
                {showAgent('graph') && <LinvisDesk agentKey="graph" {...getAgentProps('graph', '小图 (Graphy)', 'female', 'horse')} roleTitle="知识图谱提炼" info={data.agents.graph} />}
                {showAgent('summary') && <LinvisDesk agentKey="summary" {...getAgentProps('summary', '小聚 (Communer)', 'male', 'horse')} roleTitle="图谱社区摘要" info={data.agents.summary} />}
              </div>

              {/* 3D 粘土文件柜 */}
              <div className="absolute bottom-3 left-4 w-12 h-16 opacity-90 pointer-events-none z-10">
                <svg viewBox="0 0 35 48" className="w-full h-full drop-shadow-md">
                  {/* 外柜 */}
                  <rect x="2" y="2" width="31" height="44" rx="4" fill="#0284c7" />
                  <rect x="4" y="4" width="27" height="40" rx="2" fill="#0369a1" />
                  {/* 抽屉 1 */}
                  <rect x="6" y="8" width="23" height="10" rx="1.5" fill="#38bdf8" />
                  <circle cx="17.5" cy="13" r="1.8" fill="#e0f2fe" />
                  {/* 抽屉 2 */}
                  <rect x="6" y="20" width="23" height="10" rx="1.5" fill="#38bdf8" />
                  <circle cx="17.5" cy="25" r="1.8" fill="#e0f2fe" />
                  {/* 抽屉 3 */}
                  <rect x="6" y="32" width="23" height="10" rx="1.5" fill="#38bdf8" />
                  <circle cx="17.5" cy="37" r="1.8" fill="#e0f2fe" />
                </svg>
              </div>
            </div>
          )}

        </div>
      </div>
    </div>
  );
}
