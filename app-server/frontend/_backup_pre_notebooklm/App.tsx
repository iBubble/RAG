import React, { useState, useEffect, useRef, Component, type ReactNode, type ErrorInfo } from 'react';
import { createPortal } from 'react-dom';
import { Routes, Route, useNavigate, useParams, Navigate } from 'react-router-dom';
import DocumentStudio from './components/DocumentStudio/DocumentStudio';
import HomePage from './components/HomePage/HomePage';
import AgentChat from './components/AgentChat/AgentChat';
import FileUploader from './components/FileUploader/FileUploader';
import FilePreviewer from './components/FilePreviewer/FilePreviewer';
import ProjectInfo from './components/ProjectInfo/ProjectInfo';
import TreeView from './components/TreeView/TreeView';
import TemplateManager from './components/TemplateManager/TemplateManager';
import SavedDocumentsList from './components/SavedResults/SavedDocumentsList';
import SavedChatSnippets from './components/SavedResults/SavedChatSnippets';
import KnowledgeBasePanel from './components/KnowledgeBasePanel/KnowledgeBasePanel';
import ProjectPresence from './components/ProjectPresence/ProjectPresence';
import { useProjectStore, type PreviewFile } from './store/projectStore';
import { useAuthStore } from './store/authStore';
import LoginPage from './components/Auth/LoginPage';
import RegisterPage from './components/Auth/RegisterPage';
import AdminLayout from './components/Admin/AdminLayout';
import ProfilePage from './components/Profile/ProfilePage';
import { X } from 'lucide-react';


function SystemStatusIndicator() {
  const [ollamaStatus, setOllamaStatus] = useState<'checking'|'online'|'offline'>('checking');
  const [raidStatus, setRaidStatus] = useState<'checking'|'online'|'offline'>('checking');
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

        // 自动同步模型：取 Ollama 当前已加载的 qwen3.6 模型列表，确保 store 中的模型名有效
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
      }
    };
    checkStatus();
    const interval = setInterval(checkStatus, 15000);
    return () => clearInterval(interval);
  }, [getAuthHeaders, setSelectedModel]);

  if (ollamaStatus === 'checking') return <div className="text-[10px] text-gray-400">检测 AI 引擎...</div>;

  return (
    <>
      {raidStatus === 'offline' && (
        <div className="fixed top-0 left-0 w-full bg-[#ef4444] text-white z-[9999] px-4 py-2 text-center text-sm font-bold shadow-lg flex items-center justify-center gap-2">
          <span className="text-xl">🚨</span> 大载荷独立磁盘阵列（RAID）异常脱机！系统已降级运行。项目框架数据已锁定在固态盘安全生效，但重型图纸文件访问及全文高维检索暂时被阻断。请火速检查硬盘物理连线！
        </div>
      )}
      <div className={`flex items-center gap-1.5 px-3 py-1 rounded-full text-[11px] font-medium border shadow-sm ${
        ollamaStatus === 'online' ? 'bg-emerald-50 text-emerald-700 border-emerald-100' : 'bg-red-50 text-red-700 border-red-100'
      }`}>
      <div className={`w-2 h-2 rounded-full ${
        ollamaStatus === 'online' ? 'bg-emerald-500 shadow-[0_0_8px_rgba(34,197,94,0.6)] animate-[pulse_2s_ease-in-out_infinite]' : 
        'bg-red-500'
      }`} />
      
      <span className="tracking-wide ml-1">
        {ollamaStatus === 'online' ? '引擎在线' : '引擎离线'}
      </span>
    </div>
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
  const { isLoggedIn, fetchMe } = useAuthStore();

  // 启动时验证 Token 有效性
  useEffect(() => {
    if (isLoggedIn) fetchMe();
  }, []);

  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />
      <Route path="/register" element={<RegisterPage />} />
      <Route path="/" element={<ProtectedRoute><HomePage /></ProtectedRoute>} />
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
  const templateSections = useProjectStore(state => state.templateSections);
  const setTemplateData = useProjectStore(state => state.setTemplateData);
  const setCurrentDocId = useProjectStore(state => state.setCurrentDocId);
  const hasTemplate = templateSections.length > 0;
  const isUploadModalOpen = useProjectStore(state => state.isUploadModalOpen);
  const setUploadModalOpen = useProjectStore(state => state.setUploadModalOpen);
  const triggerRefresh = useProjectStore(state => state.triggerRefresh);
  const activePreviewFile = useProjectStore(state => state.activePreviewFile);
  const setActivePreviewFile = useProjectStore(state => state.setActivePreviewFile);
  const { getAuthHeaders, user } = useAuthStore();

  // WHY: 计算当前用户是否对此项目有写权限（Owner 或 Admin）
  const [projectOwnerId, setProjectOwnerId] = useState<string>('');
  const canWrite = user?.id === projectOwnerId || user?.role === 'admin';

  const API_BASE = import.meta.env.VITE_API_BASE || '';

  // 侧边栏拖拽调宽
  const [sidebarWidth, setSidebarWidth] = useState(420);
  const [isResizing, setIsResizing] = useState(false);

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
          setProjectIcon(data.icon || '⚖️');
          setProjectOwnerId(data.owner_id || '');
        }
      } catch {}
    };
    if (projectId) loadProject();
  }, [projectId]);

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
          // WHY: 不管有没有模板大纲，打开项目时始终默认显示智能问答 Tab，
          //      用户需要编写文档时自行切换。
          setActiveTab('智能问答');
        } else {
          setTemplateData('', []);
          setActiveTab('智能问答');
        }
      } catch {
        setTemplateData('', []);
        setActiveTab('智能问答');
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
    if (tabName === '文档编写' && !hasTemplate) {
      alert('🔒 必须先在右侧区域上传【.docx 大纲样文】，解析后方可进入编排台！');
      return;
    }
    setActiveTab(tabName);
  };

  const handleFilePreviewClick = (file: PreviewFile) => {
    setActivePreviewFile(file);
    setActiveTab('智能问答');
  };

  return (
    <>
    <div className="flex h-screen w-full bg-white overflow-hidden text-sm">
      {/* Left Sidebar: Resizable */}
      <aside 
        className="h-full border-r border-gray-200 flex flex-col shrink-0 relative transition-[width] duration-0"
        style={{ width: `${sidebarWidth}px`, userSelect: isResizing ? 'none' : 'auto' }}
      >
        {/* Resizer Handle */}
        <div 
          className="absolute top-0 -right-[3px] w-[6px] h-full cursor-col-resize hover:bg-blue-400 active:bg-blue-500 z-50 transition-colors"
          onMouseDown={(e) => {
            e.preventDefault();
            setIsResizing(true);
          }}
        />

        <div className="p-3 border-b border-gray-200 flex items-center gap-2">
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
               title="点击修改案件名称"
               onClick={() => { setEditName(projectName); setIsEditingName(true); }}
             >{projectName || '未命名案件'}</span>
           )}
           <button onClick={() => navigate('/')} className="text-blue-600 text-xs hover:underline shrink-0">返回</button>
        </div>
        <div className="flex-1 p-4 text-xs text-gray-500 overflow-y-auto">
           {canWrite && (
             <button onClick={() => setUploadModalOpen(true)} className="w-full py-2 mb-4 border border-dashed border-gray-300 rounded hover:border-blue-400 hover:text-blue-600 transition-colors">
               + 上传案件文件/卷宗
             </button>
           )}
           <div className="space-y-2">
             <TreeView projectId={projectId || 'default'} onFileClick={handleFilePreviewClick} canWrite={canWrite} />
           </div>
        </div>
      </aside>

      {/* Middle Core Panel: flex-1 */}
      <main className="flex-1 min-w-0 h-full flex flex-col bg-canvas-bg relative">
        <header className="h-[48px] bg-white border-b border-gray-200 flex items-center px-6 text-xs shadow-sm z-10 transition-all justify-between">
           <div className="flex gap-6 h-full">
             {['智能问答', '数据看板', '已存信息', '案件信息', '文档编写'].map(tab => (
               <div 
                 key={tab}
                 onClick={() => handleTabClick(tab)}
                 className={`cursor-pointer flex items-center h-full pt-1 transition-colors select-none ${
                   activeTab === tab 
                     ? 'text-blue-600 font-medium border-b-2 border-blue-600 pb-1' 
                     : 'text-gray-500 hover:text-gray-800 pb-[6px]'
                 }`}
               >
                 {tab} {tab === '文档编写' && !hasTemplate && <span className="ml-1 rounded-sm bg-orange-100/80 text-orange-600 border border-orange-200/50 px-1 py-[1px] text-[10px] transform scale-90">🔒锁定</span>}
               </div>
             ))}
           </div>
           
             {/* Global AI Status Light & Presence */}
           <div className="flex items-center gap-2">
             <ProjectPresence projectId={projectId || 'default'} />
             <SystemStatusIndicator />
           </div>
        </header>

        {/* Tab Contents */}
        <div className="flex-1 overflow-hidden transition-opacity duration-300">
          {activeTab === '文档编写' && <DocumentStudio canWrite={canWrite} projectName={projectName} />}

          {activeTab === '智能问答' && (
            <div className="flex h-full w-full">
               {/* 左侧：资料预览 */}
               <div 
                 className={`h-full relative shrink-0 overflow-hidden transition-[width] duration-300 ease-in-out ${
                   activePreviewFile ? 'border-r border-gray-200' : 'border-r-0'
                 }`}
                 style={{ width: `${activePreviewFile ? previewWidth : 0}px`, userSelect: isPreviewResizing ? 'none' : 'auto' }}
               >
                 {activePreviewFile && (
                   <div 
                     className="absolute top-0 -right-[3px] w-[6px] h-full cursor-col-resize hover:bg-blue-400 active:bg-blue-500 z-50 transition-colors"
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
          )}

          {activeTab === '已存信息' && (
            <div className="h-full">
               <SavedChatSnippets />
            </div>
          )}

          {activeTab === '数据看板' && (
            <div className="h-full">
               <KnowledgeBasePanel />
            </div>
          )}

          {activeTab === '案件信息' && (
            <div className="h-full overflow-hidden">
               <ProjectInfo projectId={projectId || 'default'} />
            </div>
          )}
        </div>
      </main>

      {/* Right Sidebar: 20% */}
      <aside className="w-[300px] h-full border-l border-gray-200 bg-white flex flex-col shadow-[-4px_0_24px_rgba(0,0,0,0.02)] z-10 relative shrink-0">
        <div className="h-[280px] shrink-0 border-b border-gray-200">
          <TemplateManager canWrite={canWrite} />
        </div>
        
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
            <h2 className="font-semibold text-gray-800 text-base">📂 上传案件卷宗</h2>
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
