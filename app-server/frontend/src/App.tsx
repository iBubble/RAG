import React, { useState, useEffect, useRef, Component, type ReactNode, type ErrorInfo } from 'react';
import { createPortal } from 'react-dom';
import { Routes, Route, useNavigate, useParams, Navigate, useLocation } from 'react-router-dom';
import DocumentStudio from './components/DocumentStudio/DocumentStudio';
import HomePage from './components/HomePage/HomePage';
import AgentChat from './components/AgentChat/AgentChat';
import FileUploader from './components/FileUploader/FileUploader';
import FilePreviewer from './components/FilePreviewer/FilePreviewer';
import TreeView from './components/TreeView/TreeView';
import SavedDocumentsList from './components/SavedResults/SavedDocumentsList';
import KnowledgeBasePanel from './components/KnowledgeBasePanel/KnowledgeBasePanel';
import ProjectPresence from './components/ProjectPresence/ProjectPresence';
import { useProjectStore, useChatStore, type PreviewFile } from './store/projectStore';
import { useAuthStore } from './store/authStore';
import LoginPage from './components/Auth/LoginPage';
import RegisterPage from './components/Auth/RegisterPage';
import AdminLayout from './components/Admin/AdminLayout';
import ProfilePage from './components/Profile/ProfilePage';
import Linvis from './components/Linvis/Linvis';
import AITablePanel from './components/AITable/AITablePanel';
import { 
  X, 
  LayoutDashboard, 
  Sparkles, 
  Wand2,
  Loader2,
  Sun,
  Moon,
  SunMoon,
  ChevronLeft,
  ChevronRight,
  Table
} from 'lucide-react';
import { useThemeStore } from './store/themeStore';
import { APP_VERSION, APP_NAME } from './version';

const TAB_ITEMS = [
  { id: '智能助手', label: '智能助手', icon: Sparkles },
  { id: 'AI表格', label: 'AI表格', icon: Table },
  { id: '定制文档', label: '定制文档', icon: Wand2 }
] as const;

export function ThemeSwitcher() {
  const [isOpen, setIsOpen] = useState(false);
  const { colorMode, setColorMode } = useThemeStore();
  const { user } = useAuthStore();
  const dropdownRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
        setIsOpen(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const getModeIcon = () => {
    if (colorMode === 'light') return <Sun className="w-4 h-4" />;
    if (colorMode === 'dark') return <Moon className="w-4 h-4" />;
    return <SunMoon className="w-4 h-4" />;
  };

  const getModeLabel = () => {
    if (colorMode === 'light') return '浅色模式';
    if (colorMode === 'dark') return '深色模式';
    return '设备模式';
  };

  return (
    <div className="relative" ref={dropdownRef}>
      {/* 纯图标按钮，图标为当前选择的模式图标 */}
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="flex items-center justify-center w-8 h-8 rounded-full border border-border-soft bg-panel-bg text-text-muted hover:text-text-main hover:bg-outline-bg transition-all duration-150 active:scale-95 cursor-pointer shadow-sm"
        title={`切换主题（当前：${getModeLabel()}）`}
      >
        {getModeIcon()}
      </button>

      {isOpen && (
        <div 
          className="absolute right-0 mt-2 w-40 rounded-xl bg-white dark:bg-[#202124] py-1.5 shadow-2xl z-50 text-stone-800 dark:text-stone-200 border border-stone-200 dark:border-stone-800 animate-[scaleIn_0.15s_ease-out] select-none"
          style={{ opacity: 1 }}
        >
          <div className="flex flex-col">
            {[
              { id: 'light', label: '浅色模式', icon: Sun },
              { id: 'dark', label: '深色模式', icon: Moon },
              { id: 'system', label: '设备模式', icon: SunMoon },
            ].map(item => {
              const Icon = item.icon;
              const isSelected = colorMode === item.id;
              return (
                <button
                  key={item.id}
                  onClick={() => {
                    setColorMode(item.id as any);
                    if (user?.login_name) {
                      localStorage.setItem(`colorMode_${user.login_name}`, item.id);
                    }
                    setIsOpen(false);
                  }}
                  className={`flex items-center gap-2.5 w-full px-4 py-2.5 text-left text-xs transition-colors cursor-pointer ${
                    isSelected
                      ? 'bg-stone-100 dark:bg-stone-800 text-stone-900 dark:text-white font-semibold'
                      : 'hover:bg-stone-50 dark:hover:bg-stone-800 text-stone-600 dark:text-stone-300'
                  }`}
                >
                  <Icon className="w-4 h-4 text-stone-400 dark:text-stone-500" />
                  <span>{item.label}</span>
                </button>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}

export function SystemStatusIndicator({ mode = 'dot' }: { mode?: 'dot' | 'capsule' }) {
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [ollamaStatus, setOllamaStatus] = useState<'checking'|'online'|'offline'>('checking');
  const [raidStatus, setRaidStatus] = useState<'checking'|'online'|'offline'>('checking');
  const [health, setHealth] = useState<{
    status: 'green'|'yellow'|'red';
    details: string;
    metrics?: {
      slow_queue: number;
      fast_queue: number;
      ollama: string;
      qdrant: string;
      neo4j: string;
      raid: string;
    }
  } | null>(null);

  const selectedModel = useProjectStore(state => state.selectedModel);
  const setSelectedModel = useProjectStore(state => state.setSelectedModel);
  const { getAuthHeaders } = useAuthStore();

  const selectedModelRef = useRef(selectedModel);
  useEffect(() => {
    selectedModelRef.current = selectedModel;
  }, [selectedModel]);

  useEffect(() => {
    const checkStatus = async () => {
      try {
        const API_BASE = import.meta.env.VITE_API_BASE || '';
        const res = await fetch(`${API_BASE}/api/llm/status`, { headers: getAuthHeaders() });
        const data = await res.json();
        setOllamaStatus(data.status === 'online' ? 'online' : 'offline');
        if (data.raid_status) {
          setRaidStatus(data.raid_status);
        }
        if (data.health) {
          setHealth(data.health);
        }

        // 自动同步模型
        if (data.status === 'online' && Array.isArray(data.models)) {
          const qwenModels = data.models
            .map((m: any) => m.name)
            .filter((name: string) => name.toLowerCase().includes('qwen3.6'));
          
          if (qwenModels.length > 0) {
            const currentSelected = selectedModelRef.current;
            if (!qwenModels.includes(currentSelected)) {
              const defaultModel = qwenModels.find((name: string) => name.includes('qwen3.6:35b-q4')) || qwenModels[0];
              setSelectedModel(defaultModel);
            }
          }
        }
      } catch {
        setOllamaStatus('offline');
        setHealth({ status: 'red', details: '无法连接后端API网关' });
      }
    };
    checkStatus();
    const interval = setInterval(checkStatus, 60000);
    return () => clearInterval(interval);
  }, [getAuthHeaders, setSelectedModel]);

  if (ollamaStatus === 'checking') {
    return mode === 'capsule' ? (
      <div className="flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-gray-100 border border-gray-200 text-[11px] text-gray-500 font-medium">
        <Loader2 className="w-3.5 h-3.5 animate-spin" />
        <span>系统诊断中...</span>
      </div>
    ) : (
      <div className="text-[10px] text-gray-400">检测 AI 引擎...</div>
    );
  }

  const statusColorMap = {
    green: {
      bg: 'bg-emerald-50 dark:bg-emerald-950/20 border-emerald-100 dark:border-emerald-900/30 text-emerald-700 dark:text-emerald-400 hover:bg-emerald-100/50 dark:hover:bg-emerald-900/40',
      dot: 'bg-emerald-500 shadow-[0_0_8px_rgba(34,197,94,0.6)] animate-[pulse_2s_ease-in-out_infinite]',
      text: 'AI 引擎就绪',
      capsuleBg: 'bg-gradient-to-r from-emerald-500/10 to-teal-500/10 border-emerald-500/20 text-emerald-700 hover:from-emerald-500/20 hover:to-teal-500/20'
    },
    yellow: {
      bg: 'bg-amber-50 dark:bg-amber-950/20 border-amber-100 dark:border-amber-900/30 text-amber-700 dark:text-amber-400 hover:bg-amber-100/50 dark:hover:bg-amber-900/40',
      dot: 'bg-amber-500 shadow-[0_0_8px_rgba(245,158,11,0.6)] animate-[pulse_1s_ease-in-out_infinite]',
      text: '系统处理队列积压',
      capsuleBg: 'bg-gradient-to-r from-amber-500/10 to-orange-500/10 border-amber-500/20 text-amber-700 hover:from-amber-500/20 hover:to-orange-500/20'
    },
    red: {
      bg: 'bg-red-50 dark:bg-red-950/20 border-red-100 dark:border-red-900/30 text-red-700 dark:text-red-400 hover:bg-red-100/50 dark:hover:bg-red-900/40',
      dot: 'bg-red-500 shadow-[0_0_12px_rgba(239,68,68,0.9)] animate-[pulse_0.4s_ease-in-out_infinite]',
      text: '系统严重异常',
      capsuleBg: 'bg-gradient-to-r from-red-500/10 to-rose-500/10 border-red-500/20 text-red-700 hover:from-red-500/20 hover:to-rose-500/20 animate-pulse'
    }
  };

  const currentStatus = (ollamaStatus === 'offline' || health?.metrics?.ollama === 'offline')
    ? 'red'
    : (health?.status || 'green');
  const color = statusColorMap[currentStatus];

  if (mode === 'capsule') {
    return (
      <>
        <div 
          className={`flex items-center gap-2 px-3 py-1.5 rounded-full border shadow-sm transition-all duration-300 cursor-pointer ${color.capsuleBg}`}
          title={`${health?.details || color.text}\n当前模型: ${ollamaStatus === 'online' ? selectedModel : '离线'}\n\n[点击查看全系统健康指标]`}
          onClick={() => setIsModalOpen(true)}
        >
          <div className={`w-2 h-2 rounded-full shrink-0 ${color.dot}`} />
          <span className="text-[11px] font-bold tracking-wide select-none">{color.text}</span>
        </div>

        {isModalOpen && createPortal(
          <div className="fixed inset-0 z-[9999] flex items-center justify-center p-4">
            <div 
              className="absolute inset-0 bg-[#0F0F11]/45 backdrop-blur-[2px] transition-opacity" 
              onClick={() => setIsModalOpen(false)}
            />
            <div className="relative bg-panel-bg text-text-main rounded-xl p-5 shadow-2xl border border-border-soft max-w-sm w-full flex flex-col gap-4 animate-in fade-in zoom-in-95 duration-200">
              <div className="flex items-start gap-3">
                <div className="p-2.5 rounded-full bg-[#10b981]/15 text-emerald-500 shrink-0">
                  <div className={`w-2 h-2 rounded-full shrink-0 ${color.dot}`} />
                </div>
                <div className="flex flex-col gap-1 min-w-0 flex-1">
                  <h3 className="text-sm font-semibold leading-none text-text-main flex items-center gap-1.5">
                    🛡️ 全链路智能巡检结果
                  </h3>
                  <div className="text-xs text-text-muted leading-relaxed mt-3 whitespace-pre-wrap font-sans border-t border-border-soft pt-3 space-y-2">
                    <p>🔹 <strong>巡检诊断：</strong>{health?.details || color.text}</p>
                    <p>🔹 <strong>当前模型：</strong>{ollamaStatus === 'online' ? `🟢 ${selectedModel}` : '🔴 离线'}</p>
                    <p>🔹 <strong>AI推理服务：</strong>{health?.metrics?.ollama === 'online' ? '🟢 正常' : '🔴 异常/未装载'}</p>
                    <p>🔹 <strong>向量存储 (Qdrant)：</strong>{health?.metrics?.qdrant === 'online' ? '🟢 正常' : '🔴 连接超时'}</p>
                    <p>🔹 <strong>知识图谱 (Neo4j)：</strong>{health?.metrics?.neo4j === 'online' ? '🟢 正常' : '🔴 连接超时'}</p>
                    <p>🔹 <strong>NAS存储 (RAID)：</strong>{health?.metrics?.raid === 'online' ? '🟢 正常' : '🔴 离线'}</p>
                    <div className="border-t border-dashed border-border-soft pt-2 mt-2 flex justify-between text-[11px]">
                      <span>🔹 慢速队列：{health?.metrics?.slow_queue ?? 0} 个</span>
                      <span>🔹 快速队列：{health?.metrics?.fast_queue ?? 0} 个</span>
                    </div>
                  </div>
                </div>
              </div>
              <div className="flex justify-end gap-2 mt-2">
                <button
                  onClick={() => setIsModalOpen(false)}
                  className="px-4 py-1.5 text-xs font-semibold text-white bg-indigo-600 hover:bg-indigo-700 active:scale-95 rounded-lg transition-all shadow-sm cursor-pointer"
                >
                  我知道了
                </button>
              </div>
            </div>
          </div>,
          document.body
        )}
      </>
    );
  }

  return (
    <>
      {raidStatus === 'offline' && (
        <div className="fixed top-0 left-0 w-full bg-[#ef4444] text-white z-[9999] px-4 py-2 text-center text-sm font-bold shadow-lg flex items-center justify-center gap-2">
          <span className="text-xl">🚨</span> 大载荷独立磁盘阵列（RAID）异常脱机！系统已降级运行。项目框架数据已锁定在固态盘安全生效，但重型图纸文件访问及全文高维检索暂时被阻断。请火速检查硬盘物理连线！
        </div>
      )}
      <div 
        className={`flex items-center justify-center w-5 h-5 rounded-full border shadow-sm shrink-0 transition-all duration-300 cursor-pointer hover:scale-110 active:scale-95 ${color.bg}`} 
        title={`${health?.details || (ollamaStatus === 'online' ? 'AI 引擎在线' : 'AI 引擎离线')}\n当前模型: ${ollamaStatus === 'online' ? selectedModel : '离线'}\n\n[点击查看全系统健康指标]`}
        onClick={() => setIsModalOpen(true)}
      >
        <div className={`w-2 h-2 rounded-full shrink-0 transition-all duration-300 ${color.dot}`} />
      </div>

      {isModalOpen && createPortal(
        <div className="fixed inset-0 z-[9999] flex items-center justify-center p-4">
          <div 
            className="absolute inset-0 bg-[#0F0F11]/45 backdrop-blur-[2px] transition-opacity" 
            onClick={() => setIsModalOpen(false)}
          />
          <div className="relative bg-panel-bg text-text-main rounded-xl p-5 shadow-2xl border border-border-soft max-w-sm w-full flex flex-col gap-4 animate-in fade-in zoom-in-95 duration-200">
            <div className="flex items-start gap-3">
              <div className="p-2.5 rounded-full bg-[#10b981]/15 text-emerald-500 shrink-0">
                <div className={`w-2 h-2 rounded-full shrink-0 ${color.dot}`} />
              </div>
              <div className="flex flex-col gap-1 min-w-0 flex-1">
                <h3 className="text-sm font-semibold leading-none text-text-main flex items-center gap-1.5">
                  🛡️ 全链路智能巡检结果
                </h3>
                <div className="text-xs text-text-muted leading-relaxed mt-3 whitespace-pre-wrap font-sans border-t border-border-soft pt-3 space-y-2">
                  <p>🔹 <strong>巡检诊断：</strong>{health?.details || color.text}</p>
                  <p>🔹 <strong>当前模型：</strong>{ollamaStatus === 'online' ? `🟢 ${selectedModel}` : '🔴 离线'}</p>
                  <p>🔹 <strong>AI推理服务：</strong>{health?.metrics?.ollama === 'online' ? '🟢 正常' : '🔴 异常/未装载'}</p>
                  <p>🔹 <strong>向量存储 (Qdrant)：</strong>{health?.metrics?.qdrant === 'online' ? '🟢 正常' : '🔴 连接超时'}</p>
                  <p>🔹 <strong>知识图谱 (Neo4j)：</strong>{health?.metrics?.neo4j === 'online' ? '🟢 正常' : '🔴 连接超时'}</p>
                  <p>🔹 <strong>NAS存储 (RAID)：</strong>{health?.metrics?.raid === 'online' ? '🟢 正常' : '🔴 离线'}</p>
                  <div className="border-t border-dashed border-border-soft pt-2 mt-2 flex justify-between text-[11px]">
                    <span>🔹 慢速队列：{health?.metrics?.slow_queue ?? 0} 个</span>
                    <span>🔹 快速队列：{health?.metrics?.fast_queue ?? 0} 个</span>
                  </div>
                </div>
              </div>
            </div>
            <div className="flex justify-end gap-2 mt-2">
              <button
                onClick={() => setIsModalOpen(false)}
                className="px-4 py-1.5 text-xs font-semibold text-white bg-indigo-600 hover:bg-indigo-700 active:scale-95 rounded-lg transition-all shadow-sm cursor-pointer"
              >
                我知道了
              </button>
            </div>
          </div>
        </div>,
        document.body
      )}
    </>
  );
}

// WHY: Error Boundary 兜底 — 当 StudioLayout 渲染崩溃时，
//      显示错误信息和刷新按钮，避免用户看到白屏。
interface EBProps { children: ReactNode }
interface EBState { hasError: boolean; error: Error | null }

class StudioErrorBoundary extends Component<EBProps, EBState> {
  constructor(props: EBProps) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error: Error): EBState {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    console.error('[StudioErrorBoundary] 组件渲染崩溃:', error, errorInfo);
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="flex h-screen w-full items-center justify-center bg-gray-50">
          <div className="text-center max-w-md p-8">
            <div className="text-4xl mb-4">⚠️</div>
            <h2 className="text-xl font-bold text-gray-800 mb-2">页面加载异常</h2>
            <p className="text-gray-500 mb-1 text-sm">
              {this.state.error?.message || '未知错误'}
            </p>
            <button
              onClick={() => window.location.reload()}
              className="mt-4 px-6 py-2.5 bg-indigo-600 text-white rounded-xl hover:bg-indigo-700 transition-colors font-medium"
            >
              刷新页面
            </button>
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}

// WHY: 未登录用户重定向到登录页
function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const { isLoggedIn } = useAuthStore();
  if (!isLoggedIn) return <Navigate to="/login" replace />;
  return <>{children}</>;
}

function App() {
  const { isLoggedIn, user, fetchMe } = useAuthStore();
  const applyTheme = useThemeStore(state => state.applyTheme);
  const colorMode = useThemeStore(state => state.colorMode);
  const location = useLocation();
  const fetchPublicSettings = useProjectStore(state => state.fetchPublicSettings);
  const publicSettings = useProjectStore(state => state.publicSettings);

  const systemName = publicSettings?.system_name || `${APP_NAME} V${APP_VERSION}`;

  // 初始化主题并监听系统深色模式变化
  useEffect(() => {
    // 强制重置：如果全局默认主题为 'system'，则强行重置为 'light'，确保所有未手动调整过的历史页面均显示为浅色模式
    if (useThemeStore.getState().colorMode === 'system') {
      useThemeStore.getState().setColorMode('light');
    }

    applyTheme();

    const mediaQuery = window.matchMedia('(prefers-color-scheme: dark)');
    const handleSystemThemeChange = () => {
      if (useThemeStore.getState().colorMode === 'system') {
        applyTheme();
      }
    };

    mediaQuery.addEventListener('change', handleSystemThemeChange);
    return () => mediaQuery.removeEventListener('change', handleSystemThemeChange);
  }, [applyTheme, colorMode]);

  // 当用户登录状态或者用户名改变时，加载并应用该用户的专属色彩主题模式
  useEffect(() => {
    if (user?.login_name) {
      const savedUserMode = localStorage.getItem(`colorMode_${user.login_name}`);
      if (savedUserMode) {
        useThemeStore.getState().setColorMode(savedUserMode as any);
      } else {
        // 如果该账号之前没有保存过主题模式，默认采用“浅色模式（light）”
        useThemeStore.getState().setColorMode('light');
      }
    } else {
      // 未登录时，默认也用浅色模式
      useThemeStore.getState().setColorMode('light');
    }
  }, [user?.login_name]);

  // 启动时验证 Token 有效性，并获取公共设置
  useEffect(() => {
    if (isLoggedIn) fetchMe();
    fetchPublicSettings();
  }, [isLoggedIn, fetchPublicSettings]);

  // 监听路由与系统设置，动态同步浏览器网页标题
  useEffect(() => {
    const path = location.pathname;
    if (path.startsWith('/project/')) {
      // 项目详情页的标题由 StudioLayout 自行设置，避免与此处路由监听冲突
      return;
    }
    if (path === '/login') {
      document.title = `登录 - ${systemName}`;
    } else if (path === '/register') {
      document.title = `注册 - ${systemName}`;
    } else if (path === '/profile') {
      document.title = `个人中心 - ${systemName}`;
    } else if (path.startsWith('/admin')) {
      document.title = `后台管理 - ${systemName}`;
    } else if (path === '/linvis') {
      document.title = `知识图谱 - ${systemName}`;
    } else if (path === '/') {
      document.title = systemName;
    } else {
      document.title = systemName;
    }
  }, [location.pathname, systemName]);

  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/register" element={<RegisterPage />} />
      <Route path="/" element={<ProtectedRoute><HomePage /></ProtectedRoute>} />
      <Route path="/linvis" element={<ProtectedRoute><Linvis /></ProtectedRoute>} />
      <Route path="/project/:id" element={<ProtectedRoute><StudioErrorBoundary><StudioLayout /></StudioErrorBoundary></ProtectedRoute>} />
      <Route path="/admin/*" element={<ProtectedRoute><AdminLayout /></ProtectedRoute>} />
      <Route path="/profile" element={<ProtectedRoute><ProfilePage /></ProtectedRoute>} />
    </Routes>
  )
}

function StudioLayout() {
  const navigate = useNavigate();
  const { id: projectId } = useParams<{ id: string }>();
  const activeTab = useProjectStore(state => state.activeTab);
  const setActiveTab = useProjectStore(state => state.setActiveTab);
  const setTemplateData = useProjectStore(state => state.setTemplateData);
  const setCurrentDocId = useProjectStore(state => state.setCurrentDocId);
  const isUploadModalOpen = useProjectStore(state => state.isUploadModalOpen);
  const setUploadModalOpen = useProjectStore(state => state.setUploadModalOpen);
  const triggerRefresh = useProjectStore(state => state.triggerRefresh);
  const activePreviewFile = useProjectStore(state => state.activePreviewFile);
  const setActivePreviewFile = useProjectStore(state => state.setActivePreviewFile);
  const { getAuthHeaders, user } = useAuthStore();
  const isGenerating = useChatStore(state => state.chatStreamingState.isGenerating);

  const fetchPublicSettings = useProjectStore(state => state.fetchPublicSettings);
  const publicSettings = useProjectStore(state => state.publicSettings);
  const systemName = publicSettings?.system_name || `${APP_NAME} V${APP_VERSION}`;

  useEffect(() => {
    fetchPublicSettings();
  }, [fetchPublicSettings]);

  const getTabLabel = (_id: string, defaultLabel: string) => {
    return defaultLabel;
  };

  // WHY: 计算当前用户是否对此项目有写权限（Owner 或 Admin）
  const [projectOwnerId, setProjectOwnerId] = useState<string>('');
  const canWrite = user?.id === projectOwnerId || user?.role === 'admin';

  const API_BASE = import.meta.env.VITE_API_BASE || '';

  // 侧边栏拖拽调宽
  const [sidebarWidth, setSidebarWidth] = useState(300);
  const [isResizing, setIsResizing] = useState(false);
  const [isSidebarCollapsed, setIsSidebarCollapsed] = useState(false);
  const [isRightSidebarCollapsed, setIsRightSidebarCollapsed] = useState(false);

  useEffect(() => {
    if (!isResizing) return;
    const handleMouseMove = (e: MouseEvent) => {
      // 最小 150px，最大限制为 800px 或屏幕的 50%
      const newWidth = Math.max(150, Math.min(e.clientX, window.innerWidth * 0.5, 800));
      setSidebarWidth(newWidth);
    };
    const handleMouseUp = () => setIsResizing(false);
    
    document.addEventListener('mousemove', handleMouseMove);
    document.addEventListener('mouseup', handleMouseUp);
    return () => {
      document.removeEventListener('mousemove', handleMouseMove);
      document.removeEventListener('mouseup', handleMouseUp);
    };
  }, [isResizing]);

  // 中间预览区拖拽调宽
  const [previewWidth, setPreviewWidth] = useState(500);
  const [isPreviewResizing, setIsPreviewResizing] = useState(false);

  useEffect(() => {
    if (!isPreviewResizing) return;
    const handleMouseMove = (e: MouseEvent) => {
      // preview 区域左侧起始位置是 sidebarWidth
      const newWidth = Math.max(300, Math.min(e.clientX - sidebarWidth, window.innerWidth - sidebarWidth - 300));
      setPreviewWidth(newWidth);
    };
    const handleMouseUp = () => setIsPreviewResizing(false);
    
    document.addEventListener('mousemove', handleMouseMove);
    document.addEventListener('mouseup', handleMouseUp);
    return () => {
      document.removeEventListener('mousemove', handleMouseMove);
      document.removeEventListener('mouseup', handleMouseUp);
    };
  }, [isPreviewResizing, sidebarWidth]);

  // 案件名称/图标编辑
  const [projectName, setProjectName] = useState('');
  const [projectIcon, setProjectIcon] = useState('⚖️');
  const [isEditingName, setIsEditingName] = useState(false);
  const [editName, setEditName] = useState('');
  const nameInputRef = useRef<HTMLInputElement>(null);

  // 加载项目信息
  useEffect(() => {
    const loadProject = async () => {
      try {
        const res = await fetch(`${API_BASE}/api/projects/${projectId}`, { headers: getAuthHeaders() });
        if (res.ok) {
          const data = await res.json();
          setProjectName(data.name || '');
          setProjectIcon(data.icon || (data.project_type === 'library' ? '📚' : '⚖️'));
          setProjectOwnerId(data.owner_id || '');
        }
      } catch {}
    };
    if (projectId) loadProject();
  }, [projectId]);

  // 动态修改项目详情页的网页标题
  useEffect(() => {
    if (projectName) {
      document.title = `${projectName} - ${systemName}`;
    } else {
      document.title = systemName;
    }
  }, [projectName, systemName]);

  // 保存项目名
  const saveProjectName = async () => {
    if (!editName.trim() || editName.trim() === projectName) { setIsEditingName(false); return; }
    try {
      const res = await fetch(`${API_BASE}/api/projects/${projectId}`, {
        method: 'PUT',
        headers: { ...getAuthHeaders(), 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: editName.trim() }),
      });
      if (res.ok) setProjectName(editName.trim());
    } catch {}
    setIsEditingName(false);
  };

  useEffect(() => {
    if (isEditingName && nameInputRef.current) nameInputRef.current.focus();
  }, [isEditingName]);

  // WHY: 进入项目时从后端加载该项目独有的范文大纲
  const setExemplarData = useProjectStore(state => state.setExemplarData);
  const clearExemplar = useProjectStore(state => state.clearExemplar);

  useEffect(() => {
    const loadProjectTemplate = async () => {
      try {
        const res = await fetch(`${API_BASE}/api/projects/${projectId || 'default'}/template`, { headers: getAuthHeaders() });
        if (res.ok) {
          const data = await res.json();
          const sections = data.sections || [];
          setTemplateData(data.title || '', sections);
          // WHY: 不管有没有模板大纲，打开项目时始终默认显示智能助手 Tab，
          //      用户需要编写文档时自行切换。
          setActiveTab('智能助手');
        } else {
          setTemplateData('', []);
          setActiveTab('智能助手');
        }
      } catch {
        setTemplateData('', []);
        setActiveTab('智能助手');
      }
      setCurrentDocId(null);
    };

    // WHY: 并行加载写作范文（exemplar），恢复范文挂载状态
    const loadProjectExemplar = async () => {
      try {
        const res = await fetch(`${API_BASE}/api/exemplar/project/${projectId || 'default'}`, { headers: getAuthHeaders() });
        if (res.ok) {
          const data = await res.json();
          if (data.title && data.sections?.length > 0) {
            setExemplarData(data.title, data.sections);
          } else {
            clearExemplar();
          }
        } else {
          clearExemplar();
        }
      } catch {
        clearExemplar();
      }
    };

    loadProjectTemplate();
    loadProjectExemplar();
  }, [projectId]);

  const handleTabClick = (tabName: string) => {
    setActiveTab(tabName);
  };

  const handleFilePreviewClick = (file: PreviewFile) => {
    setActivePreviewFile(file);
    setActiveTab('智能助手');
  };

  return (
    <>
    <div className="flex h-screen w-full bg-[#F0EDE8] p-3 gap-3 overflow-hidden text-sm">
      {/* Left Sidebar: Resizable */}
      <aside 
        className="h-full bg-white rounded-2xl border-none shadow-sm flex flex-col shrink-0 relative"
        style={{ 
          width: isSidebarCollapsed ? '0px' : `${sidebarWidth}px`, 
          opacity: isSidebarCollapsed ? 0 : 1,
          marginRight: isSidebarCollapsed ? '-12px' : '0px',
          overflow: isSidebarCollapsed ? 'hidden' : 'visible',
          userSelect: isResizing ? 'none' : 'auto',
          transition: 'width 0.3s cubic-bezier(0.4, 0, 0.2, 1), opacity 0.3s ease, margin-right 0.3s ease'
        }}
      >
        {/* Resizer Handle */}
        {!isSidebarCollapsed && (
          <>
            <div 
              className="absolute top-0 -right-[3px] w-[6px] h-full cursor-col-resize hover:bg-[#C4B5A0] active:bg-[#A89A87] z-50 transition-colors"
              onMouseDown={(e) => {
                e.preventDefault();
                setIsResizing(true);
              }}
            />
            {/* 贴在左栏和中栏分界线中间的收起按钮 */}
            <button
              onClick={() => setIsSidebarCollapsed(true)}
              className="absolute left-full top-1/2 -translate-y-1/2 w-4 h-10 bg-white dark:bg-[#202124] border border-stone-200 dark:border-stone-850 border-l-0 rounded-r-lg shadow-md flex items-center justify-center text-stone-500 hover:text-[#8B7355] dark:hover:text-[#C4B5A0] hover:bg-stone-50 dark:hover:bg-stone-800 cursor-pointer z-50 transition-all duration-200"
              title="收起材料栏"
            >
              <ChevronLeft className="w-3.5 h-3.5" />
            </button>
          </>
        )}

        <div className="p-3 border-b border-[#E0DCD5] rounded-t-2xl flex items-center gap-2">
           <span className="text-lg cursor-pointer hover:scale-110 transition-transform" title="点击修改图标">{projectIcon}</span>
           {isEditingName ? (
             <input
               ref={nameInputRef}
               value={editName}
               onChange={e => setEditName(e.target.value)}
               onBlur={saveProjectName}
               onKeyDown={e => { if (e.key === 'Enter') saveProjectName(); if (e.key === 'Escape') setIsEditingName(false); }}
               className="flex-1 px-2 py-1 border border-indigo-300 rounded-lg text-sm font-medium outline-none focus:ring-2 focus:ring-indigo-200 min-w-0"
             />
           ) : (
             <span
               className="flex-1 font-semibold text-gray-800 truncate cursor-pointer hover:text-indigo-600 transition-colors text-sm"
               title="点击修改项目名称"
               onClick={() => { setEditName(projectName); setIsEditingName(true); }}
             >{projectName || '未命名项目'}</span>
           )}
           <button onClick={() => navigate('/')} className="text-blue-600 text-xs hover:underline shrink-0">返回</button>
        </div>
        <div className="flex-1 p-4 text-xs text-gray-500 overflow-y-auto">
           {canWrite && (
             <button onClick={() => setUploadModalOpen(true)} className="w-full py-2 mb-4 border border-solid border-gray-300 rounded hover:border-blue-400 hover:text-blue-600 transition-colors">
               + 上传项目文件/资料
             </button>
           )}
           <div className="space-y-2">
             <TreeView projectId={projectId || 'default'} onFileClick={handleFilePreviewClick} canWrite={canWrite} />
           </div>
        </div>
      </aside>

      <main className="flex-1 min-w-0 h-full flex flex-col bg-white rounded-2xl border-none shadow-sm overflow-hidden relative">
        {isSidebarCollapsed && (
          <button
            onClick={() => setIsSidebarCollapsed(false)}
            className="absolute left-0 top-1/2 -translate-y-1/2 w-5 h-12 bg-[#8B7355] text-white hover:bg-[#705c43] shadow-md flex items-center justify-center rounded-r-lg cursor-pointer z-[99] transition-all duration-200"
            title="展开材料栏"
          >
            <ChevronRight className="w-4 h-4" />
          </button>
        )}
        {isRightSidebarCollapsed && (
          <button
            onClick={() => setIsRightSidebarCollapsed(false)}
            className="absolute right-0 top-1/2 -translate-y-1/2 w-5 h-12 bg-[#8B7355] text-white hover:bg-[#705c43] shadow-md flex items-center justify-center rounded-l-lg cursor-pointer z-[99] transition-all duration-200"
            title="展开素材库"
          >
            <ChevronLeft className="w-4 h-4" />
          </button>
        )}
        <header className="h-[48px] bg-white border-b border-[#E0DCD5] flex items-center px-6 text-xs z-30 transition-all justify-between relative">
           <div className="flex gap-6 h-full overflow-x-auto items-center">
             {TAB_ITEMS.map(item => {
               const IconComponent = item.icon;
               const isSelected = activeTab === item.id;
               return (
                 <div 
                   key={item.id}
                   onClick={() => handleTabClick(item.id)}
                   className={`cursor-pointer flex items-center gap-1.5 h-full pt-1 transition-colors select-none whitespace-nowrap ${
                     isSelected 
                       ? 'text-[#8B7355] font-semibold border-b-2 border-[#8B7355] pb-1' 
                       : 'text-gray-500 hover:text-gray-800 pb-[6px]'
                   }`}
                 >
                   <IconComponent className={`w-3.5 h-3.5 transition-colors ${isSelected ? 'text-[#8B7355]' : 'text-gray-400'}`} />
                   <span>{getTabLabel(item.id, item.label)}</span>
                 </div>
               );
             })}
           </div>
           
             {/* Global AI Status Light & Presence */}
           <div className="flex items-center gap-2">
             <button
               onClick={() => handleTabClick('数据看板')}
               className={`p-1.5 rounded-lg border transition-all duration-200 flex items-center justify-center hover:scale-105 active:scale-95 ${
                 activeTab === '数据看板'
                   ? 'bg-[#8B7355]/10 border-[#8B7355]/30 text-[#8B7355] shadow-sm'
                   : 'bg-white border-stone-200 text-stone-500 hover:text-stone-700 hover:bg-stone-50'
               }`}
               title="数据看板"
             >
               <LayoutDashboard className="w-3.5 h-3.5" />
             </button>
              <ProjectPresence 
                projectId={projectId || 'default'} 
                activeTab={activeTab}
                isGenerating={isGenerating}
              />
              <ThemeSwitcher />
              <SystemStatusIndicator />
           </div>
        </header>

          {/* Tab Contents */}
          <div className="flex-1 overflow-hidden transition-opacity duration-300 relative">
            <div className="h-full" style={{ display: activeTab === '定制文档' ? 'block' : 'none' }}>
              <DocumentStudio canWrite={canWrite} projectName={projectName} />
            </div>

            <div className="h-full" style={{ display: activeTab === 'AI表格' ? 'block' : 'none' }}>
              <AITablePanel projectId={projectId} canWrite={canWrite} />
            </div>

            <div className="h-full" style={{ display: activeTab === '智能助手' ? 'block' : 'none' }}>
            <div className="flex h-full w-full">
               {/* 左侧：资料预览 */}
               <div 
                 className={`h-full relative shrink-0 overflow-hidden transition-[width] duration-300 ease-in-out ${
                   activePreviewFile ? 'border-r border-[#E0DCD5]' : 'border-r-0'
                 }`}
                 style={{ width: `${activePreviewFile ? previewWidth : 0}px`, userSelect: isPreviewResizing ? 'none' : 'auto' }}
               >
                 {activePreviewFile && (
                   <div 
                     className="absolute top-0 -right-[3px] w-[6px] h-full cursor-col-resize hover:bg-[#C4B5A0] active:bg-[#A89A87] z-50 transition-colors"
                     onMouseDown={(e) => {
                       e.preventDefault();
                       setIsPreviewResizing(true);
                     }}
                   />
                 )}
                 <FilePreviewer />
               </div>
                {/* 右侧：AI 助手 */}
                <div className="flex-1 h-full min-w-0">
                  <AgentChat projectId={projectId || 'default'} />
                </div>
             </div>
            </div>

            <div className="h-full" style={{ display: activeTab === '数据看板' ? 'block' : 'none' }}>
               <KnowledgeBasePanel />
            </div>
          </div>
      </main>

      {/* Right Sidebar: 20% */}
      <aside 
        className="h-full bg-white rounded-2xl border-none shadow-sm flex flex-col shrink-0 relative"
        style={{
          width: isRightSidebarCollapsed ? '0px' : '300px',
          opacity: isRightSidebarCollapsed ? 0 : 1,
          marginLeft: isRightSidebarCollapsed ? '-12px' : '0px',
          overflow: isRightSidebarCollapsed ? 'hidden' : 'visible',
          transition: 'width 0.3s cubic-bezier(0.4, 0, 0.2, 1), opacity 0.3s ease, margin-left 0.3s ease'
        }}
      >
        {!isRightSidebarCollapsed && (
          <button
            onClick={() => setIsRightSidebarCollapsed(true)}
            className="absolute right-full top-1/2 -translate-y-1/2 w-4 h-10 bg-white dark:bg-[#202124] border border-stone-200 dark:border-stone-850 border-r-0 rounded-l-lg shadow-md flex items-center justify-center text-stone-500 hover:text-[#8B7355] dark:hover:text-[#C4B5A0] hover:bg-stone-50 dark:hover:bg-stone-800 cursor-pointer z-50 transition-all duration-200"
            title="收起素材库"
          >
            <ChevronRight className="w-3.5 h-3.5" />
          </button>
        )}
        <div className="flex-1 overflow-hidden">
          <SavedDocumentsList />
        </div>
      </aside>
    </div>

    {/* WHY: 弹窗和遮罩用 Portal 渲染到 document.body，
       避免 Fragment 子节点动态增减导致 insertBefore DOM 崩溃 */}
    {isUploadModalOpen && createPortal(
      <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm">
        <div className="bg-white rounded-2xl shadow-2xl w-[700px] max-h-[80vh] overflow-hidden flex flex-col">
          <div className="flex items-center justify-between px-6 py-4 border-b border-gray-200 bg-gradient-to-r from-blue-50 to-white">
            <h2 className="font-semibold text-gray-800 text-base">📂 上传项目文档</h2>
            <button
              onClick={() => { setUploadModalOpen(false); triggerRefresh(); }}
              className="p-1.5 hover:bg-gray-100 rounded-lg transition-colors text-gray-400 hover:text-gray-600"
            >
              <X className="w-5 h-5" />
            </button>
          </div>
          <div className="flex-1 overflow-y-auto">
            <FileUploader projectId={projectId || 'default'} />
          </div>
          <div className="px-6 py-4 border-t border-gray-200 bg-gray-50 flex justify-end shrink-0">
            <button
              onClick={() => { setUploadModalOpen(false); triggerRefresh(); }}
              className="px-6 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors font-medium text-sm shadow-sm"
            >
              ✅ 完成
            </button>
          </div>
        </div>
      </div>,
      document.body
    )}

    {(isResizing || isPreviewResizing) && createPortal(
      <div className="fixed inset-0 z-[9999] cursor-col-resize bg-transparent" />,
      document.body
    )}
    </>
  );
}

export default App;
