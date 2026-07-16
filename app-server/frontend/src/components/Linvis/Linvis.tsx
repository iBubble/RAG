import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { Home, RefreshCw } from 'lucide-react';
import { useAuthStore } from '../../store/authStore';
import LinvisWhiteboard from './LinvisWhiteboard';
import './Linvis3D.css';

// 导入2D卡通虚拟办公室美术资源
import deskSprite from '../../assets/office/desk.webp';
import roleChat from '../../assets/office/role_chat.png';
import rolePlanner from '../../assets/office/role_planner.png';
import roleSummary from '../../assets/office/role_summary.png';
import roleChecker from '../../assets/office/role_checker.png';
import roleAuditor from '../../assets/office/role_auditor.png';
import roleService from '../../assets/office/role_service.png';
import rolePrecompute from '../../assets/office/role_precompute.png';
import roleVectorizer from '../../assets/office/role_vectorizer.png';
import roleGraph from '../../assets/office/role_graph.png';
import roleLegal from '../../assets/office/role_legal.png';



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
  const [wsStatus, setWsStatus] = useState<'connecting' | 'online' | 'offline'>('connecting');

  const [showAuditModal, setShowAuditModal] = useState(false);
  const [auditProjectId, setAuditProjectId] = useState<string | null>(null);
  const [frozenData, setFrozenData] = useState<any>(null);
  const [editDraft, setEditDraft] = useState('');
  const [resumeStreamOutput, setResumeStreamOutput] = useState('');
  const [isResuming, setIsResuming] = useState(false);

  const API_BASE = import.meta.env.VITE_API_BASE || '';

  // 1. 统一朝向与样式的工位办公桌逻辑坐标定义 (SVG视口尺寸 940 * 512)
  // 1. 统一朝向与样式的工位办公桌逻辑坐标定义 (SVG视口尺寸 940 * 512)
  // 1. 统一朝向与样式的工位办公桌逻辑坐标定义 (SVG视口尺寸 940 * 512)
  const DEFAULT_POS: Record<string, { x: number; y: number }> = {
    planner: { x: 440, y: 280 },
    chat: { x: 210, y: 280 },
    summary: { x: 670, y: 280 },
    checker: { x: 280, y: 450 },
    service: { x: 480, y: 450 },
    auditor: { x: 600, y: 450 },
    precompute: { x: 210, y: 620 },
    vectorizer: { x: 440, y: 620 },
    legal: { x: 555, y: 620 },
    graph: { x: 670, y: 620 },
  };

  // Agent 实时物理坐标与动画状态 (x, y, 是否在行走, 是否在休息区)
  const [positions, setPositions] = useState<Record<string, { x: number; y: number; isWalking: boolean; isSlacking: boolean }>>({
    planner: { x: 440, y: 280, isWalking: false, isSlacking: false },
    chat: { x: 210, y: 280, isWalking: false, isSlacking: false },
    summary: { x: 670, y: 280, isWalking: false, isSlacking: false },
    checker: { x: 280, y: 450, isWalking: false, isSlacking: false },
    service: { x: 480, y: 450, isWalking: false, isSlacking: false },
    auditor: { x: 600, y: 450, isWalking: false, isSlacking: false },
    precompute: { x: 210, y: 620, isWalking: false, isSlacking: false },
    vectorizer: { x: 440, y: 620, isWalking: false, isSlacking: false },
    legal: { x: 555, y: 620, isWalking: false, isSlacking: false },
    graph: { x: 670, y: 620, isWalking: false, isSlacking: false },
  });

  // 獬豸办公室顶部卡通挂钟当前系统时间 (每分钟/每10秒同步刷新)
  const [currentTime, setCurrentTime] = useState(new Date());

  // 更新Agent状态时，检查：
  // 1) 是否刚刚被指派了新任务 (之前不是 working，最新是 working) -> 走前往门口拿任务拿卷宗动画
  // 2) 容错同步
  const updateAgentPositions = (agentsData: LinvisData["agents"]) => {
    // 门口坐标定义
    const DOOR_POS = { x: 145, y: 150 };

    setPositions(prev => {
      const next = { ...prev };
      let changed = false;

      for (const [key, info] of Object.entries(agentsData)) {
        const cur = prev[key];
        if (!cur) continue;

        // 获取前一次的真实 agent 状态
        const prevAgent = data.agents[key as keyof typeof data.agents];
        const wasWorking = prevAgent && prevAgent.status === 'working';
        const isNowWorking = info.status === 'working';

        // 触发条件：新接任务 (之前不是 working，现在是 working)
        if (isNowWorking && !wasWorking) {
          // 第一步：先开步行状态，坐标保留为原工位（以触发 transition 过渡动画）
          next[key] = {
            ...cur,
            isWalking: true,
            isSlacking: false
          };
          changed = true;

          // 2) 50ms后，等浏览器渲染好首帧，再将坐标设为门口！从而触发顺滑步行过渡！
          setTimeout(() => {
            setPositions(p => {
              if (p[key]) {
                return {
                  ...p,
                  [key]: {
                    ...p[key],
                    x: DOOR_POS.x,
                    y: DOOR_POS.y
                  }
                };
              }
              return p;
            });
          }, 50);

          // 1.55秒后：到达门口，停留一小会儿 (例如 800ms 拿取公文包)
          setTimeout(() => {
            // 2.35秒后：起步从门口走回工位
            setTimeout(() => {
              setPositions(p => {
                if (p[key]) {
                  return {
                    ...p,
                    [key]: {
                      ...p[key],
                      x: DEFAULT_POS[key].x,
                      y: DEFAULT_POS[key].y,
                      isWalking: true
                    }
                  };
                }
                return p;
              });

              // 3.85秒后：小人成功回到工位，安心坐下工作
              setTimeout(() => {
                setPositions(p => {
                  if (p[key] && !p[key].isSlacking) {
                    return {
                      ...p,
                      [key]: {
                        ...p[key],
                        isWalking: false
                      }
                    };
                  }
                  return p;
                });
              }, 1500); // 门口到工位步行 1.5s

            }, 800); // 在门口逗留 0.8s

          }, 1550); // 原工位到门口步行 1.5s + 50ms 延时
        }
        // 容错兜底：如果是空闲状态，且没有在行走/摸鱼，同步为它的工位点
        else if (info.status !== 'working' && !cur.isWalking && !cur.isSlacking) {
          if (cur.x !== DEFAULT_POS[key].x || cur.y !== DEFAULT_POS[key].y) {
            next[key] = {
              ...cur,
              x: DEFAULT_POS[key].x,
              y: DEFAULT_POS[key].y
            };
            changed = true;
          }
        }
      }

      return changed ? next : prev;
    });
  };

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
        const json = await res.json();
        setData(json);
        updateAgentPositions(json.agents);
      }
    } catch (e) {
      console.error("无法获取看板状态", e);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  };

  // Robust WebSocket 长连接生命周期
  useEffect(() => {
    let ws: WebSocket | null = null;
    let attempt = 0;
    let isCleanup = false;
    let fallbackTimer: any = null;

    const token = localStorage.getItem('token') || '';

    const connectWS = () => {
      if (isCleanup) return;
      setWsStatus('connecting');

      const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
      const host = window.location.host;
      const wsUrl = `${protocol}//${host}/api/eino/ws-status?token=${encodeURIComponent(token)}`;

      ws = new WebSocket(wsUrl);

      // 设置 3.5 秒连接超时，防止由于外部反代不支持 WS 而导致通道升级卡死
      const connTimeout = setTimeout(() => {
        if (ws && ws.readyState === WebSocket.CONNECTING) {
          console.warn("WebSocket 握手超时，强制关闭并降级为轮询");
          ws.close();
        }
      }, 3500);

      ws.onopen = () => {
        clearTimeout(connTimeout);
        setWsStatus('online');
        attempt = 0;
        if (fallbackTimer) {
          clearInterval(fallbackTimer);
          fallbackTimer = null;
        }
      };

      ws.onmessage = (event) => {
        try {
          const payload = JSON.parse(event.data);
          if (payload.system_status && payload.agents) {
            setData(payload);
            updateAgentPositions(payload.agents);
            setLoading(false);
          } else if (payload.type === 'linvis_status_update') {
            setData(prev => {
              const nextAgents = { ...prev.agents, [payload.agent]: {
                status: payload.status,
                funny_event: payload.status === 'funny' ? payload.message : null,
                current_project: payload.project_name || null,
                current_task: payload.status === 'working' ? payload.message : null
              }};
              updateAgentPositions(nextAgents);
              return { ...prev, agents: nextAgents };
            });
          } else if (payload.type === 'agent_event') {
            setData(prev => {
              const mappedStatus = payload.status === 'done' ? 'idle' : payload.status === 'error' ? 'error' : payload.status === 'waiting' ? 'interrupted' : 'working';
              const nextAgents = { ...prev.agents, [payload.agent]: {
                status: mappedStatus,
                funny_event: null,
                current_project: null,
                current_task: payload.message
              }};
              updateAgentPositions(nextAgents);
              return { ...prev, agents: nextAgents };
            });
          }
        } catch (e) {
          // 忽略解析错误
        }
      };

      ws.onclose = () => {
        clearTimeout(connTimeout);
        setWsStatus('offline');
        startFallbackPolling();
        if (!isCleanup) {
          const delay = Math.min(30000, 1000 * Math.pow(2, attempt));
          const jitter = delay * 0.2 * (Math.random() * 2 - 1);
          attempt++;
          setTimeout(connectWS, Math.max(1000, delay + jitter));
        }
      };

      ws.onerror = () => {
        clearTimeout(connTimeout);
        ws?.close();
      };
    };

    const startFallbackPolling = () => {
      if (fallbackTimer) return;
      fetchData();
      fallbackTimer = setInterval(fetchData, 5000);
    };

    fetchData();
    connectWS();

    // 实时同步挂钟时间，每 10 秒校验一次最新时间
    const clockTimer = setInterval(() => {
      setCurrentTime(new Date());
    }, 10000);

    return () => {
      isCleanup = true;
      if (ws) ws.close();
      if (fallbackTimer) clearInterval(fallbackTimer);
      clearInterval(clockTimer);
    };
  }, []);

  // 休息区物理工位点定义（第一排茶水柜、第二排大沙发、第三排大沙发）
  const REST_SEATS = [
    { x: 920, y: 280 }, // 第一排最右侧茶水桌站立点
    { x: 940, y: 450 }, // 第二排最右侧大沙发就座点
    { x: 940, y: 620 }  // 第三排最右侧大沙发就座点
  ];

  // 定时随机选择空闲角色前往摸鱼茶水区
  useEffect(() => {
    const restTimer = setInterval(() => {
      // 限制同时在休息区的人数不超过 3 个（每个茶水桌/沙发同一时间只容纳 1 人）
      const slackingCount = Object.values(positions).filter(p => p.isSlacking).length;
      if (slackingCount >= 3) return;

      const candidates = Object.keys(DEFAULT_POS).filter(key => {
        const agent = data.agents[key as keyof typeof data.agents];
        const pos = positions[key];
        return agent && (agent.status === 'idle' || agent.status === 'sleeping') && !pos.isSlacking && !pos.isWalking;
      });

      if (candidates.length === 0) return;
      const luckyKey = candidates[Math.floor(Math.random() * candidates.length)];

      // 寻找当前绝对没有被占用的休息点，确保同一时间只允许一个角色
      const occupiedPoints = Object.values(positions).filter(p => p.isSlacking).map(p => `${p.x},${p.y}`);
      const availableSeats = REST_SEATS.filter(s => !occupiedPoints.includes(`${s.x},${s.y}`));
      
      if (availableSeats.length === 0) return;
      const freeSeat = availableSeats[Math.floor(Math.random() * availableSeats.length)];

      // 走去休息区
      setPositions(prev => ({
        ...prev,
        [luckyKey]: {
          x: freeSeat.x,
          y: freeSeat.y,
          isWalking: true,
          isSlacking: true
        }
      }));

      setTimeout(() => {
        // 到达休息区，站立/就座
        setPositions(prev => {
          if (prev[luckyKey] && prev[luckyKey].isSlacking) {
            return { ...prev, [luckyKey]: { ...prev[luckyKey], isWalking: false } };
          }
          return prev;
        });

        // 摸鱼15秒后自动自觉走回各自的工位
        setTimeout(() => {
          setPositions(prev => {
            if (prev[luckyKey] && prev[luckyKey].isSlacking) {
              // 1.5秒走回动画结束
              setTimeout(() => {
                setPositions(p => {
                  if (p[luckyKey] && !p[luckyKey].isSlacking) {
                    return { ...p, [luckyKey]: { ...p[luckyKey], isWalking: false } };
                  }
                  return p;
                });
              }, 1500);

              // 启动走回工位
              return {
                ...prev,
                [luckyKey]: {
                  x: DEFAULT_POS[luckyKey].x,
                  y: DEFAULT_POS[luckyKey].y,
                  isWalking: true,
                  isSlacking: false
                }
              };
            }
            return prev;
          });
        }, 15000);

      }, 1500);
    }, 12000);

    return () => clearInterval(restTimer);
  }, [data.agents, positions]);

  const showAgent = (agentId: string) => {
    const list = data.system_status.visible_agents || [];
    return list.includes(agentId);
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

        <div className="flex items-center gap-2 px-4 py-2 bg-white border border-[#e0dcd5] rounded-xl shadow-sm text-xs font-bold text-gray-600 select-none">
          <span className={`w-2 h-2 rounded-full ${
            wsStatus === 'online' ? 'bg-emerald-500' :
            wsStatus === 'connecting' ? 'bg-amber-500 animate-pulse' : 'bg-rose-500'
          }`} />
          <span>
            {wsStatus === 'online' ? '🟢 实时广播已上线' :
             wsStatus === 'connecting' ? '🟡 正在升级通道...' : '🔴 离线状态 (轮询兜底)'}
          </span>
        </div>

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

        {/* ====== 獬豸卡通联合审批 AI 2D 虚拟办公室 ====== */}
        <div className="sdx-office-theatre" style={{ position: 'relative', width: '100%', height: '750px', background: '#fdfaf2', borderRadius: '16px', overflow: 'hidden', border: '1px solid #e0dcd5', boxShadow: '0 4px 12px rgba(0,0,0,0.05)' }}>
          
          <svg viewBox="0 0 1100 750" className="w-full h-full select-none" style={{ background: '#f8fafc' }}>
            {/* 1. 精美手绘卡通办公室背景 (墙壁 + 一体化木地板) */}
            {/* 墙面与踢脚线 */}
            <rect x={0} y={0} width={1100} height={130} fill="#fcf9f2" />
            <rect x={0} y={124} width={1100} height={6} fill="#8c6239" />

            {/* 一体化木纹地板 (一气呵成，从 y=130 铺满至底部 750) */}
            <rect x={0} y={130} width={1100} height={620} fill="#f5dfc6" />
            {Array.from({ length: 12 }).map((_, idx) => {
              const x = idx * 95;
              return <line key={`floor-line-${idx}`} x1={x} y1={130} x2={x} y2={750} stroke="#e4ceb4" strokeWidth="2" />;
            })}

            {/* 墙面装饰：精美卡通木门 (缩小一半) */}
            <g>
              {/* 门框 */}
              <rect x={60} y={25} width={50} height={100} rx={2} fill="#8c6239" />
              {/* 门板 */}
              <rect x={63} y={28} width={44} height={94} rx={1} fill="#d4a373" />
              {/* 门内立体凹凸面板 */}
              <rect x={68} y={33} width={34} height={38} fill="none" stroke="#a07146" strokeWidth="1.5" />
              <rect x={68} y={76} width={34} height={40} fill="none" stroke="#a07146" strokeWidth="1.5" />
              {/* 亮铜门把手 */}
              <circle cx={99} cy={74} r={2.5} fill="#b48a53" stroke="#2f2a26" strokeWidth="1" />
              <path d="M 99 74 L 94 74" stroke="#2f2a26" strokeWidth="2.0" strokeLinecap="round" />
            </g>

            {/* 墙面装饰：立体蓝天绿树窗户 (缩小一半) */}
            <g>
              {/* 窗外景物 */}
              <rect x={700} y={30} width={76} height={60} fill="#a7f3d0" />
              <circle cx={710} cy={78} r={20} fill="#34d399" opacity="0.6" />
              <circle cx={765} cy={73} r={17} fill="#059669" opacity="0.7" />
              <rect x={700} y={30} width={76} height={40} fill="#bae6fd" />
              <circle cx={735} cy={42} r={8} fill="#ffffff" opacity="0.9" />
              <circle cx={745} cy={42} r={10} fill="#ffffff" opacity="0.9" />
              {/* 窗框与分界 */}
              <rect x={698} y={28} width={80} height={64} fill="none" stroke="#8c6239" strokeWidth="4" rx={1} />
              <rect x={700} y={30} width={76} height={60} fill="none" stroke="#ffffff" strokeWidth="2" />
              <line x1={738} y1={30} x2={738} y2={90} stroke="#ffffff" strokeWidth="2" />
              {/* 玻璃斜反光 */}
              <path d="M 705 85 L 730 40" stroke="rgba(255,255,255,0.4)" strokeWidth="4" strokeLinecap="round" />
              <path d="M 745 80 L 765 45" stroke="rgba(255,255,255,0.4)" strokeWidth="3" strokeLinecap="round" />
            </g>

            {/* 墙面装饰：刻度圆挂钟 (尺寸翻倍，上移至顶端，与真实时间同步) */}
            <g transform="translate(480, 45)">
              <circle cx={0} cy={0} r={40} fill="#334155" />
              <circle cx={0} cy={0} r={35} fill="#ffffff" />
              {Array.from({ length: 12 }).map((_, i) => {
                const angle = (i * 30 * Math.PI) / 180;
                const x1 = Math.sin(angle) * 27;
                const y1 = -Math.cos(angle) * 27;
                const x2 = Math.sin(angle) * 32;
                const y2 = -Math.cos(angle) * 32;
                return <line key={`tick-${i}`} x1={x1} y1={y1} x2={x2} y2={y2} stroke="#475569" strokeWidth={i % 3 === 0 ? 2.5 : 1} />;
              })}
              {/* 时针 */}
              <line 
                x1={0} y1={0} 
                x2={0} y2={-18} 
                stroke="#1e293b" 
                strokeWidth="3.5" 
                strokeLinecap="round" 
                transform={`rotate(${((currentTime.getHours() % 12) * 30 + currentTime.getMinutes() * 0.5).toFixed(1)})`}
              />
              {/* 分针 */}
              <line 
                x1={0} y1={0} 
                x2={0} y2={-28} 
                stroke="#0f172a" 
                strokeWidth="2" 
                strokeLinecap="round" 
                transform={`rotate(${(currentTime.getMinutes() * 6).toFixed(1)})`}
              />
              <circle cx={0} cy={0} r={3} fill="#dc2626" />
            </g>

            {/* 落地绿植盆栽 (上移并缩小) */}
            <g transform="translate(950, 110) scale(0.65)">
              <polygon points="10,20 -10,20 -15,50 15,50" fill="#a1a1aa" stroke="#2f2a26" strokeWidth="2" />
              <path d="M 0 20 Q -20 -10 -15 -35 Q 0 -20 0 20" fill="#22c55e" stroke="#15803d" strokeWidth="2" />
              <path d="M 0 20 Q 20 -10 15 -35 Q 0 -20 0 20" fill="#15803d" stroke="#166534" strokeWidth="2" />
              <path d="M 0 20 Q -35 5 -40 -15 Q -15 -10 0 20" fill="#4ade80" stroke="#16a34a" strokeWidth="2" />
              <path d="M 0 20 Q 35 5 40 -15 Q 15 -10 0 20" fill="#16a34a" stroke="#15803d" strokeWidth="2" />
            </g>

            {/* 2. 摸鱼茶水休息区 (横跨三排的最右侧区域，完美落在 512px 以下的原木地板上) */}
            <g>
              {/* (A) 第一排最右侧：高保真红色卡通咖啡机茶水柜 (高度精确对齐工位 280) */}
              <g transform="translate(875, 228)">
                {/* 阴影 */}
                <ellipse cx={45} cy={55} rx={42} ry={6} fill="rgba(0,0,0,0.12)" />
                {/* 茶水桌柜体 */}
                <rect x={0} y={0} width={90} height={52} rx={4} fill="#8c6239" stroke="#2f2a26" strokeWidth="2.5" />
                {/* 门中线 */}
                <line x1={45} y1={5} x2={45} y2={47} stroke="#2f2a26" strokeWidth="2" />
                {/* 铜把手 */}
                <circle cx={40} cy={22} r={2.5} fill="#f59e0b" stroke="#2f2a26" strokeWidth="1" />
                <circle cx={50} cy={22} r={2.5} fill="#f59e0b" stroke="#2f2a26" strokeWidth="1" />
                {/* 桌上的卡通红色咖啡机 */}
                <rect x={15} y={-24} width={28} height={24} rx={3} fill="#ef4444" stroke="#2f2a26" strokeWidth="2.2" />
                {/* 冲煮头 */}
                <rect x={20} y={-10} width={18} height={3} fill="#9ca3af" stroke="#2f2a26" strokeWidth="1.5" />
                {/* 咖啡机手柄 */}
                <line x1={32} y1={-8} x2={42} y2={-8} stroke="#2f2a26" strokeWidth="2.5" strokeLinecap="round" />
                {/* 滴滤咖啡杯 */}
                <rect x={24} y={-7} width={9} height={7} rx={1} fill="#ffffff" stroke="#2f2a26" strokeWidth="1.2" />
                {/* 小按键 */}
                <circle cx={23} cy={-18} r={1.5} fill="#60a5fa" />
                <circle cx={29} cy={-18} r={1.5} fill="#34d399" />
                <circle cx={35} cy={-18} r={1.5} fill="#fbbf24" />
                {/* 柜子上的微型多肉绿植 */}
                <ellipse cx={70} cy={-2} rx={9} ry={3.5} fill="#d97706" stroke="#2f2a26" strokeWidth="1.5" />
                <path d="M 66 -2 Q 62 -12 65 -16 Q 71 -8 71 -2" fill="#22c55e" stroke="#15803d" strokeWidth="1.2" />
                <path d="M 70 -2 Q 78 -12 75 -16 Q 71 -8 71 -2" fill="#15803d" stroke="#166534" strokeWidth="1.2" />
              </g>

              {/* (B) 第二排最右侧：高保真卡通粉蓝色大沙发 (大小修改为与第三排大沙发一致，高度精确对齐工位 450) */}
              <g transform="translate(885, 395)">
                {/* 沙发底座阴影 */}
                <ellipse cx={70} cy={60} rx={65} ry={11} fill="rgba(0,0,0,0.15)" />
                {/* 沙发主体后靠背 */}
                <rect x={10} y={0} width={120} height={50} rx={12} fill="#93c5fd" stroke="#2f2a26" strokeWidth="3" />
                {/* 靠背中间折缝线 */}
                <line x1={70} y1={5} x2={70} y2={45} stroke="#2f2a26" strokeWidth="2.2" strokeDasharray="3 3" />
                {/* 坐垫 */}
                <rect x={12} y={30} width={116} height={25} rx={8} fill="#60a5fa" stroke="#2f2a26" strokeWidth="3" />
                {/* 坐垫中缝 */}
                <line x1={70} y1={30} x2={70} y2={55} stroke="#2f2a26" strokeWidth="2.2" />
                {/* 左扶手 */}
                <rect x={0} y={20} width={18} height={35} rx={6} fill="#93c5fd" stroke="#2f2a26" strokeWidth="3" />
                {/* 右扶手 */}
                <rect x={122} y={20} width={18} height={35} rx={6} fill="#93c5fd" stroke="#2f2a26" strokeWidth="3" />
                {/* 沙发矮木腿 */}
                <line x1={20} y1={55} x2={15} y2={64} stroke="#2f2a26" strokeWidth="4.5" strokeLinecap="round" />
                <line x1={120} y1={55} x2={125} y2={64} stroke="#2f2a26" strokeWidth="4.5" strokeLinecap="round" />
              </g>

              {/* (C) 第三排最右侧：暖橘黄色沙发与咖啡小圆桌 (高度精确对齐工位 620) */}
              <g transform="translate(885, 555)">
                {/* 沙发底座阴影 */}
                <ellipse cx={70} cy={60} rx={65} ry={11} fill="rgba(0,0,0,0.15)" />
                {/* 沙发主体后靠背 */}
                <rect x={10} y={0} width={120} height={50} rx={12} fill="#ffedd5" stroke="#2f2a26" strokeWidth="3" />
                {/* 靠背中间折缝线 */}
                <line x1={70} y1={5} x2={70} y2={45} stroke="#2f2a26" strokeWidth="2.2" strokeDasharray="3 3" />
                {/* 坐垫 */}
                <rect x={12} y={30} width={116} height={25} rx={8} fill="#fed7aa" stroke="#2f2a26" strokeWidth="3" />
                {/* 坐垫中缝 */}
                <line x1={70} y1={30} x2={70} y2={55} stroke="#2f2a26" strokeWidth="2.2" />
                {/* 左扶手 */}
                <rect x={0} y={20} width={18} height={35} rx={6} fill="#ffedd5" stroke="#2f2a26" strokeWidth="3" />
                {/* 右扶手 */}
                <rect x={122} y={20} width={18} height={35} rx={6} fill="#ffedd5" stroke="#2f2a26" strokeWidth="3" />
                {/* 沙发矮木腿 */}
                <line x1={20} y1={55} x2={15} y2={64} stroke="#2f2a26" strokeWidth="4.5" strokeLinecap="round" />
                <line x1={120} y1={55} x2={125} y2={64} stroke="#2f2a26" strokeWidth="4.5" strokeLinecap="round" />
              </g>

              {/* 咖啡小圆桌 */}
              <g transform="translate(980, 590)">
                <ellipse cx={0} cy={0} rx={30} ry={10} fill="#f59e0b" stroke="#2f2a26" strokeWidth="2.2" />
                <line x1={0} y1={0} x2={0} y2={30} stroke="#2f2a26" strokeWidth="4" />
                <ellipse cx={0} cy={30} rx={18} ry={6} fill="#b45309" stroke="#2f2a26" strokeWidth="2.2" />
                {/* 桌上的咖啡杯 */}
                <rect x={-13} y={-13} width={8} height={10} rx={1} fill="#ffffff" stroke="#2f2a26" strokeWidth="1.5" />
                <path d="M -5 -11 A 2 2 0 0 1 -2 -7" fill="none" stroke="#2f2a26" strokeWidth="1.5" />
              </g>
            </g>

            {/* 3. 动态角色与静态工位统一深度渲染 (从后到前深度画家算法排序，实现人走桌留且气泡无遮挡) */}
            {Object.keys(DEFAULT_POS).map((key) => {
              if (!showAgent(key)) return null;
              
              const pos = positions[key];
              const agent = data.agents[key as keyof typeof data.agents];
              const dPos = DEFAULT_POS[key];
              
              // 映射到高精角色原画
              let sprite = roleChat;
              switch(key) {
                case 'chat': sprite = roleChat; break;
                case 'planner': sprite = rolePlanner; break;
                case 'summary': sprite = roleSummary; break;
                case 'checker': sprite = roleChecker; break;
                case 'auditor': sprite = roleAuditor; break;
                case 'service': sprite = roleService; break;
                case 'precompute': sprite = rolePrecompute; break;
                case 'vectorizer': sprite = roleVectorizer; break;
                case 'graph': sprite = roleGraph; break;
                case 'legal': sprite = roleLegal; break;
                default: sprite = roleChat;
              }

              const isW = agent.status === 'working' && !pos.isWalking;
              const isI = agent.status === 'interrupted';
              const isWorking = agent.status === 'working';

              return (
                <g key={`station-${key}`}>
                  {/* (A) 角色小人层：使用 pos (支持行走移动，并以 scale 缩小身型) */}
                  <g 
                    transform={`translate(${pos.x}, ${pos.y}) scale(0.55)`}
                    style={{
                      transition: 'transform 1.5s ease-in-out'
                    }}
                  >
                    {/* 独立的动画承载层，与定位层隔离，防止 transform 动画覆盖定位 */}
                    <g 
                      className={`cursor-pointer ${pos.isWalking ? 'sdx-walk' : 'sdx-breathe'}`}
                      onClick={() => {
                        if (key === 'auditor' && agent.status === 'interrupted') {
                          const pid = agent.current_project;
                          if (pid) handleOpenAuditModal(pid);
                        }
                      }}
                    >
                      {/* 状态悬浮气泡 - 只有在回到工位静止状态下才常驻显示，去门口路上隐去 */}
                      {!pos.isWalking && (
                        <foreignObject x={-95} y={-170} width={190} height={70}>
                          <div className={
                            agent.status === 'working' ? 'task-bubble-w' :
                            agent.status === 'funny' ? 'task-bubble-f' : 'task-bubble-w'
                          } style={{ 
                            position: 'relative', 
                            top: 0, 
                            left: 0, 
                            transform: 'none',
                            border: agent.status === 'interrupted' ? '1.5px solid #ef4444' : 
                                    (agent.status === 'sleeping' || (pos.isSlacking && !pos.isWalking)) ? '1.5px solid #3b82f6' : 
                                    agent.status === 'idle' ? '1.5px solid #9ca3af' : undefined
                          }}>
                            {agent.status === 'working' && (
                              <>
                                <span>⚡ 执行中</span>
                                <p title={agent.current_task || ''}>{agent.current_task || '任务处理中...'}</p>
                              </>
                            )}
                            {agent.status === 'interrupted' && (
                              <>
                                <span style={{ backgroundColor: '#fee2e2', color: '#dc2626' }}>🚨 待审批</span>
                                <p title={agent.current_task || ''}>{agent.current_task || '等待人工通过...'}</p>
                              </>
                            )}
                            {agent.status === 'funny' && !pos.isSlacking && (
                              <>
                                <span>💭 摸鱼</span>
                                <p title={agent.funny_event || ''}>{agent.funny_event || '舒适咖啡时间...'}</p>
                              </>
                            )}
                            {(agent.status === 'sleeping' || (pos.isSlacking && !pos.isWalking)) ? (
                              <>
                                <span style={{ backgroundColor: '#eff6ff', color: '#1d4ed8' }}>💤 眯一下</span>
                                <p>打个盹，正在充电中...</p>
                              </>
                            ) : agent.status === 'idle' && (
                              <>
                                <span style={{ backgroundColor: '#f3f4f6', color: '#4b5563' }}>☕ 待命中</span>
                                <p>工位空闲，静候新指令...</p>
                              </>
                            )}
                          </div>
                        </foreignObject>
                      )}

                      {/* 角色正面贴图，脚对齐于局部原点(0, 0)，通过y偏移下移人物，使桌子完美遮挡整个下半身 */}
                      <image 
                        xlinkHref={sprite}
                        href={sprite} 
                        x={-81} 
                        y={-195} 
                        width={162} 
                        height={336} 
                        style={{
                          filter: (agent.status === 'sleeping' || agent.status === 'idle' || (pos.isSlacking && !pos.isWalking)) ? 'grayscale(0.25) opacity(0.85)' : 'none'
                        }}
                      />

                      {/* Zzz 睡觉冒泡气泡动效 */}
                      {(agent.status === 'sleeping' || (pos.isSlacking && !pos.isWalking)) && (
                        <g transform="translate(35, -200)">
                          <text className="zzz zzz-1" x={0} y={0} fill="#818cf8" fontSize="26" fontWeight="bold">z</text>
                          <text className="zzz zzz-2" x={8} y={-10} fill="#818cf8" fontSize="20" fontWeight="bold">z</text>
                          <text className="zzz zzz-3" x={14} y={-18} fill="#818cf8" fontSize="14" fontWeight="bold">z</text>
                        </g>
                      )}

                      {/* 警报灯和独角辉光 (随角色高度向上位移至头顶独角处) */}
                      {isI && <circle cx={30} cy={-180} r={6} fill="#ef4444" className="alert-lamp" style={{ position: 'static' }} />}
                      {isW && <circle cx={0} cy={-180} r={10} fill="none" className="horn-glow" style={{ position: 'static' }} />}

                    </g>
                  </g>

                  {/* (B) 办公桌遮挡层：使用 dPos (静态不移位，将尺寸放大以使人物能坐在桌后) */}
                  <g transform={`translate(${dPos.x}, ${dPos.y})`}>
                    {/* 屏幕背壳发光效果 */}
                    {isWorking && (
                      <ellipse cx={20} cy={-2} rx={25} ry={8} fill="rgba(16,185,129,0.3)" />
                    )}
                    {/* 静止办公桌贴图 - 尺寸放大为 136 * 82 */}
                    <image xlinkHref={deskSprite} href={deskSprite} x={-68} y={-34} width={136} height={82} preserveAspectRatio="xMidYMid meet" />
                  </g>

                  {/* (C) 挂在办公桌前挡板的席位卡：以 dPos 定位 (静态不移位)，名牌留存在桌前且永远盖在最上层 */}
                  <g transform={`translate(${dPos.x}, ${dPos.y})`}>
                    <foreignObject x={-63} y={22} width={126} height={55}>
                      <div className="agent-label" style={{ marginTop: 0, boxShadow: '0 2px 4px rgba(0,0,0,0.1)' }}>
                        <span className="label-name">
                          {(data.system_status as any)[`agent_${key}_name`] || key}
                        </span>
                        <span className="label-status" style={{
                          padding: '1px 6px',
                          backgroundColor: agent.status === 'working' ? '#ecfdf5' : agent.status === 'interrupted' ? '#fef2f2' : '#f9fafb',
                          color: agent.status === 'working' ? '#059669' : agent.status === 'interrupted' ? '#dc2626' : '#6b7280'
                        }}>
                          {agent.status === 'working' ? '工作中' : agent.status === 'interrupted' ? '待审批' : '空闲'}
                        </span>
                      </div>
                    </foreignObject>
                  </g>
                </g>
              );
            })}
          </svg>
        </div>
      </div>

      {/* 拟物化红头公文袋审批面板 */}
      {showAuditModal && (
        <div className="fixed inset-0 bg-slate-900/60 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div className="audit-kraft-folder w-full max-w-4xl max-h-[90vh] overflow-hidden flex flex-col select-none rounded-2xl">
            
            {/* 案卷头部 */}
            <div className="px-8 py-5 border-b-2 border-dashed border-[#b91c1c] flex items-center justify-between">
              <div className="flex items-center gap-3">
                <span className="text-3xl">⚖️</span>
                <div>
                  <h3 className="font-bold text-2xl audit-header-red">中华人民共和国市场监督管理局</h3>
                  <p className="text-xs text-stone-500 font-semibold tracking-wider mt-1">Eino行政决策与合规审查审批案卷</p>
                </div>
              </div>
              <button 
                onClick={() => setShowAuditModal(false)}
                className="text-stone-400 hover:text-stone-700 font-black text-xl p-2 hover:bg-stone-100 rounded-full cursor-pointer"
              >
                ✕
              </button>
            </div>

            {/* 案卷内页双联 */}
            <div className="flex-1 overflow-y-auto p-8 space-y-6">
              {!frozenData ? (
                <div className="flex flex-col items-center justify-center py-16 space-y-3">
                  <div className="w-10 h-10 border-4 border-red-600 border-t-transparent rounded-full animate-spin"></div>
                  <p className="text-sm text-stone-500 font-bold">正在调阅 Redis 案卷断点数据...</p>
                </div>
              ) : (
                <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
                  {/* 左联：事实调查与核校意见 */}
                  <div className="space-y-5 pr-4 border-r-2 border-dashed border-[#b91c1c]/20">
                    <div>
                      <h4 className="text-xs font-black text-stone-400 uppercase tracking-widest mb-1.5 flex items-center gap-1">
                        <span>👤</span> 原始案件线索 / 提问内容
                      </h4>
                      <div className="p-4 bg-stone-50/50 border border-stone-300/60 rounded-xl text-stone-800 text-sm font-medium leading-relaxed max-h-36 overflow-y-auto">
                        {frozenData.request?.message}
                      </div>
                    </div>

                    <div>
                      <h4 className="text-xs font-black text-red-600 uppercase tracking-widest mb-1.5 flex items-center gap-1">
                        <span>🚨</span> 案件合规核验 (Checker 定量意见)
                      </h4>
                      <div className="p-4 bg-red-50/30 border border-red-200 text-red-950 text-sm rounded-xl leading-relaxed max-h-56 overflow-y-auto whitespace-pre-wrap">
                        {frozenData.check_result}
                      </div>
                    </div>
                  </div>

                  {/* 右联：合规整改草稿 */}
                  <div className="space-y-5 flex flex-col h-full pl-2">
                    <div className="flex-1 flex flex-col min-h-[220px]">
                      <h4 className="text-xs font-black text-stone-400 uppercase tracking-widest mb-1.5 flex items-center gap-1">
                        <span>📝</span> 智能整改初稿修改器
                      </h4>
                      <textarea
                        value={editDraft}
                        onChange={(e) => setEditDraft(e.target.value)}
                        disabled={isResuming}
                        className="flex-1 p-4 border border-stone-300 rounded-xl text-sm font-medium leading-relaxed resize-none focus:outline-none focus:ring-2 focus:ring-red-600 focus:border-transparent bg-white text-stone-800"
                        placeholder="在此手写或编辑符合法规的整改文书草稿..."
                      />
                    </div>

                    {/* 最终审批流式输出 */}
                    {(resumeStreamOutput || isResuming) && (
                      <div className="animate-fade-in">
                        <h4 className="text-xs font-black text-red-600 uppercase tracking-widest mb-1.5 flex items-center gap-1 animate-pulse">
                          <span>⚖️</span> Auditor 终审流式产出
                        </h4>
                        <div className="p-4 bg-red-50/40 border border-red-100 rounded-xl text-stone-800 text-sm font-medium leading-relaxed max-h-36 overflow-y-auto whitespace-pre-wrap">
                          {resumeStreamOutput || "正在连接 Go 决策网关..."}
                        </div>
                      </div>
                    )}
                  </div>
                </div>
              )}
            </div>

            {/* 案卷落款与审批印章 */}
            <div className="px-8 py-5 border-t-2 border-dashed border-[#b91c1c]/30 bg-stone-50 flex items-center justify-between">
              <div className="text-stone-500 text-xs font-bold">
                注：行政审批一经盖章印记，即立刻恢复 Go Eino 图工作流执行。
              </div>
              <div className="flex gap-4 items-center">
                <button
                  onClick={() => setShowAuditModal(false)}
                  className="px-5 py-2.5 bg-white border border-stone-300 text-stone-700 rounded-xl hover:bg-stone-100 text-sm font-bold cursor-pointer"
                >
                  撤回案卷
                </button>
                <button
                  onClick={handleResume}
                  disabled={!frozenData || isResuming}
                  className="seal-stamp px-8 py-3 text-white rounded-full disabled:opacity-50 text-sm font-black tracking-widest cursor-pointer flex items-center gap-1.5"
                >
                  {isResuming ? (
                    <>
                      <div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin"></div>
                      <span>决策中...</span>
                    </>
                  ) : (
                    <>
                      <span>【 准予执行 (盖章) 】</span>
                    </>
                  )}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
