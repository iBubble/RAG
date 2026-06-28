import { useState, useEffect, useRef } from 'react';
import { createPortal } from 'react-dom';
import { useNavigate } from 'react-router-dom';
import { Plus, Settings, X, Loader2, LogIn, Trash2, Globe, Lock, Library, Search, AlertTriangle, LayoutGrid, List } from 'lucide-react';
import { useAuthStore } from '../../store/authStore';
import { SystemStatusIndicator, ThemeSwitcher } from '../../App';
import { APP_VERSION, APP_NAME } from '../../version';
import LogoSpinner from '../LogoSpinner';

const API_BASE = import.meta.env.VITE_API_BASE || '';

interface Project {
  id: string;
  name: string;
  createdAt: string;
  sourceCount: number;
  owner_id?: string;
  owner_name?: string;
  visibility?: string;
  project_type?: string;
  icon?: string;
}

export default function HomePage() {
  const navigate = useNavigate();
  const { user, logout, getAuthHeaders } = useAuthStore();
  const [systemName, setSystemName] = useState(`${APP_NAME} V${APP_VERSION}`);
  const [linvisName, setLinvisName] = useState('麟维斯');
  const [projects, setProjects] = useState<Project[]>([]);
  const [searchQuery, setSearchQuery] = useState('');
  const [viewMode, setViewMode] = useState<'list' | 'card'>(() => (localStorage.getItem('home_view_mode') as 'list' | 'card') || 'list');
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [newProjectName, setNewProjectName] = useState('');
  const [newProjectVisibility, setNewProjectVisibility] = useState('public');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [createError, setCreateError] = useState('');
  const [activeMenu, setActiveMenu] = useState<string | null>(null);
  const [userMenuOpen, setUserMenuOpen] = useState(false);
  const [newProjectType, setNewProjectType] = useState('case');
  const [pageLoading, setPageLoading] = useState(true);
  const [projectToDelete, setProjectToDelete] = useState<{ id: string; name: string } | null>(null);
  const menuRef = useRef<HTMLDivElement>(null);
  const userMenuRef = useRef<HTMLDivElement>(null);

  // 预设图标列表
  const PRESET_ICONS = [
    '⚖️', '📚', '📖', '📋', '📁', '📂', '🏛️', '🔍', 
    '📝', '💼', '🏢', '💻', '🤝', '🚗', '🏥', '👨‍⚖️', 
    '👩‍⚖️', '📜', '🔒', '🛡️', '🔑', '💰', '🏠', '📅', 
    '📌', '👶', '📦', '🧑‍🤝‍🧑', '⚠️', '📊', '🖋️', '✉️'
  ];

  // 图标选择器 — 记录当前打开的项目 ID
  const [iconPickerFor, setIconPickerFor] = useState<string | null>(null);

  // 拖拽排序状态与事件处理
  const [draggedProject, setDraggedProject] = useState<Project | null>(null);

  const handleDragStart = (e: React.DragEvent, proj: Project) => {
    setDraggedProject(proj);
    e.dataTransfer.effectAllowed = 'move';
  };

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
  };

  const handleDrop = async (e: React.DragEvent, targetProj: Project) => {
    e.preventDefault();
    if (!draggedProject || draggedProject.id === targetProj.id) return;

    // 限制仅允许在各自的区域内（同为 library 或同为 case）拖拽排序，不允许跨区混拽
    if (draggedProject.project_type !== targetProj.project_type) {
      setDraggedProject(null);
      return;
    }

    const newProjects = [...projects];
    const draggedIdx = newProjects.findIndex(p => p.id === draggedProject.id);
    const targetIdx = newProjects.findIndex(p => p.id === targetProj.id);

    if (draggedIdx !== -1 && targetIdx !== -1) {
      const [removed] = newProjects.splice(draggedIdx, 1);
      newProjects.splice(targetIdx, 0, removed);
      
      // 乐观更新 UI
      setProjects(newProjects);

      try {
        const sortedIds = newProjects.map(p => p.id);
        const res = await fetch(`${API_BASE}/api/projects/reorder`, {
          method: 'PUT',
          headers: { ...getAuthHeaders(), 'Content-Type': 'application/json' },
          body: JSON.stringify({ ids: sortedIds }),
        });
        if (!res.ok) {
          console.error('更新排序失败，恢复列表');
          void fetchProjects();
        }
      } catch (err) {
        console.error('更新排序网络错误', err);
        void fetchProjects();
      }
    }
    setDraggedProject(null);
  };

  const handleDragEnd = () => {
    setDraggedProject(null);
  };

  const handleChangeIcon = async (projId: string, icon: string) => {
    try {
      const res = await fetch(`${API_BASE}/api/projects/${projId}/icon`, {
        method: 'PUT',
        headers: { ...getAuthHeaders(), 'Content-Type': 'application/json' },
        body: JSON.stringify({ icon }),
      });
      if (res.ok) fetchProjects();
    } catch { console.error('修改图标失败'); }
    setIconPickerFor(null);
    setActiveMenu(null);
  };

  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) setActiveMenu(null);
      if (userMenuRef.current && !userMenuRef.current.contains(e.target as Node)) setUserMenuOpen(false);
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  useEffect(() => {
    fetch(`${API_BASE}/api/admin/settings/public`)
      .then(r => r.json())
      .then(d => {
        if (d.system_name) setSystemName(d.system_name);
        if (d.linvis_name) setLinvisName(d.linvis_name);
      })
      .catch(() => {});
  }, []);

  useEffect(() => { void fetchProjects(); }, []);

  const fetchProjects = async () => {
    try {
      const res = await fetch(`${API_BASE}/api/projects`, { headers: getAuthHeaders() });
      if (res.ok) setProjects(await res.json());
    } catch (error) {
      console.error('Failed to fetch projects', error);
    } finally {
      setPageLoading(false);
    }
  };

  const handleCreateProject = async () => {
    if (!newProjectName.trim()) return;
    setCreateError('');
    setIsSubmitting(true);
    try {
      const res = await fetch(`${API_BASE}/api/projects`, {
        method: 'POST',
        headers: { ...getAuthHeaders(), 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: newProjectName.trim(), visibility: newProjectVisibility, project_type: newProjectType })
      });
      if (res.ok) {
        const newProject = await res.json();
        // WHY: 使用硬跳转（非 SPA navigate），确保项目页从零加载
        //      SPA 路由在弹窗卸载 + 新页挂载时存在竞态白屏风险
        window.location.href = `/project/${newProject.id}`;
      } else {
        const errData = await res.json().catch(() => null);
        setCreateError(errData?.detail || `创建失败（状态码 ${res.status}）`);
      }
    } catch {
      setCreateError('网络连接异常，无法访问服务器');
    } finally {
      setIsSubmitting(false);
    }
  };

  const formatDate = (isoString: string) => {
    const d = new Date(isoString);
    return `${d.getFullYear()}年${d.getMonth() + 1}月${d.getDate()}日`;
  };

  const handleDeleteProject = (projId: string, projName: string) => {
    setProjectToDelete({ id: projId, name: projName });
  };

  const executeDeleteProject = async (projId: string) => {
    try {
      const res = await fetch(`${API_BASE}/api/projects/${projId}`, { method: 'DELETE', headers: getAuthHeaders() });
      if (res.ok) setProjects(prev => prev.filter(p => p.id !== projId));
      else { const err = await res.json().catch(() => null); alert(err?.detail || '删除失败'); }
    } catch { alert('网络错误，删除失败'); }
    setActiveMenu(null);
  };

  const handleToggleVisibility = async (projId: string, currentVis: string) => {
    const newVis = currentVis === 'private' ? 'public' : 'private';
    try {
      const res = await fetch(`${API_BASE}/api/projects/${projId}/visibility`, {
        method: 'PUT',
        headers: { ...getAuthHeaders(), 'Content-Type': 'application/json' },
        body: JSON.stringify({ visibility: newVis }),
      });
      if (res.ok) fetchProjects();
    } catch { console.error('Toggling visibility failed'); }
    setActiveMenu(null);
  };

  // 分区：我的案件 / 公共文档 / 其他人的公开案件 (支持卡片名称过滤)
  const filteredProjects = projects.filter(p => 
    p.name.toLowerCase().includes(searchQuery.toLowerCase())
  );
  const caseProjects = filteredProjects.filter(p => p.project_type !== 'library' && p.owner_id === user?.id);
  const libraryProjects = filteredProjects.filter(p => p.project_type === 'library');
  const publicProjects = filteredProjects.filter(p => p.project_type !== 'library' && p.visibility === 'public');
  const privateProjects = filteredProjects.filter(p => p.project_type !== 'library' && p.visibility === 'private');

  const avatarUrl = user?.avatar ? `${API_BASE}${user.avatar}` : '';

  // 渲染项目卡片 (政务化扁平微缩版)
  const renderProjectCard = (proj: Project, section: string) => {
    const canEdit = proj.owner_id === user?.id || user?.role === 'admin';
    const isPrivate = proj.visibility === 'private';
    const isAdmin = user?.role === 'admin';
    const isDragged = draggedProject?.id === proj.id;
    const menuKey = `${section}-${proj.id}`;
    return (
    <div
      key={proj.id}
      onClick={() => navigate(`/project/${proj.id}`)}
      draggable={isAdmin}
      onDragStart={(e) => handleDragStart(e, proj)}
      onDragOver={handleDragOver}
      onDrop={(e) => handleDrop(e, proj)}
      onDragEnd={handleDragEnd}
      className={`h-36 rounded-lg p-4 flex flex-col cursor-pointer transition-all duration-200 relative overflow-hidden group border
        ${isAdmin ? 'cursor-grab active:cursor-grabbing' : ''}
        ${isDragged 
          ? 'opacity-40 border-dashed border-[#0052D9] bg-[#E1ECFF]/20' 
          : 'hover:border-[#0052D9] hover:shadow-sm'
        }
        bg-white dark:bg-panel-bg border-gray-200 dark:border-border-soft`}
    >
      {/* 规整的扁平化角标 */}
      <div className="absolute top-3.5 right-3.5 flex items-center gap-1.5">
        <span className={`px-2 py-0.5 rounded text-[10px] font-semibold ${
          isPrivate
            ? 'bg-amber-50 text-amber-700 border border-amber-250/50 dark:bg-amber-950/20 dark:text-amber-400'
            : 'bg-emerald-50 text-emerald-700 border border-emerald-250/50 dark:bg-emerald-950/20 dark:text-emerald-400'
        }`}>
          {isPrivate ? '私有' : '公开'}
        </span>
      </div>

      <div className="flex items-start gap-2.5 mb-auto pr-12">
        <span className="text-2xl shrink-0 drop-shadow-sm transition-transform duration-300 group-hover:scale-110">
          {proj.icon || '📚'}
        </span>
        <h3 className="font-semibold text-gray-950 dark:text-text-main text-sm leading-snug line-clamp-2">{proj.name}</h3>
      </div>

      {/* 三点菜单 */}
      <div 
        className="absolute bottom-3 right-3 z-20" 
        ref={activeMenu === menuKey ? menuRef : null}
        onClick={(e) => e.stopPropagation()}
      >
        <button
          onClick={(e) => { e.stopPropagation(); setActiveMenu(activeMenu === menuKey ? null : menuKey); }}
          className="w-7 h-7 bg-white dark:bg-panel-bg border border-gray-200 dark:border-border-soft shadow-sm rounded-md flex flex-col items-center justify-center gap-0.5 hover:bg-gray-50 dark:hover:bg-outline-bg active:scale-95 transition-all opacity-0 group-hover:opacity-100 cursor-pointer z-10"
        >
          <div className="w-1 h-1 bg-gray-600 dark:bg-gray-400 rounded-full pointer-events-none"></div>
          <div className="w-1 h-1 bg-gray-600 dark:bg-gray-400 rounded-full pointer-events-none"></div>
          <div className="w-1 h-1 bg-gray-600 dark:bg-gray-400 rounded-full pointer-events-none"></div>
        </button>
        {activeMenu === menuKey && (
          <div className="absolute right-0 bottom-full mb-1 w-40 bg-white dark:bg-panel-bg border border-gray-200 dark:border-border-soft rounded-lg shadow-lg py-1 z-50">
            <button onClick={(e) => { e.stopPropagation(); navigate(`/project/${proj.id}`); }} className="w-full px-3 py-2 text-left text-xs text-gray-700 dark:text-text-main hover:bg-gray-50 dark:hover:bg-outline-bg flex items-center gap-2 cursor-pointer">
              <LogIn className="w-3.5 h-3.5 text-[#0052D9]" /> 进入
            </button>
            {canEdit && (
              <>
                <button onClick={(e) => { e.stopPropagation(); setIconPickerFor(proj.id); setActiveMenu(null); }} className="w-full px-3 py-2 text-left text-xs text-gray-700 dark:text-text-main hover:bg-gray-50 dark:hover:bg-outline-bg flex items-center gap-2 cursor-pointer">
                  <span>🎨</span> 修改图标
                </button>
                <button onClick={(e) => { e.stopPropagation(); handleToggleVisibility(proj.id, proj.visibility || 'public'); }} className="w-full px-3 py-2 text-left text-xs text-gray-700 dark:text-text-main hover:bg-gray-50 dark:hover:bg-outline-bg flex items-center gap-2 cursor-pointer">
                  {isPrivate ? <><Globe className="w-3.5 h-3.5 text-green-500" /> 设为公开</> : <><Lock className="w-3.5 h-3.5 text-orange-500" /> 设为私有</>}
                </button>
                <button onClick={(e) => { e.stopPropagation(); handleDeleteProject(proj.id, proj.name); }} className="w-full px-3 py-2 text-left text-xs text-red-600 hover:bg-red-50 dark:hover:bg-red-950/20 flex items-center gap-2 cursor-pointer">
                  <Trash2 className="w-3.5 h-3.5" /> 删除
                </button>
              </>
            )}
          </div>
        )}
      </div>

      <div className="flex items-center justify-between mt-auto">
        <p className="text-[11px] text-gray-400 dark:text-text-muted">
          {formatDate(proj.createdAt)} · {proj.sourceCount} 个文档
        </p>
        {proj.owner_name && (
          <span className="text-[10px] text-gray-400 dark:text-text-muted shrink-0 ml-3 bg-gray-50 dark:bg-outline-bg px-2 py-0.5 rounded transition-opacity duration-200 group-hover:opacity-0">
            {proj.owner_name}
          </span>
        )}
      </div>
    </div>
    );
  };

  // 渲染项目列表表格 (高信息密度政务版)
  const renderProjectListTable = (projectsList: Project[], section: string) => {
    return (
      <div className="overflow-x-auto border border-gray-200 dark:border-border-soft rounded-lg shadow-sm bg-white dark:bg-panel-bg">
        <table className="min-w-full divide-y divide-gray-200 dark:divide-border-soft text-left text-xs font-sans">
          <thead className="bg-gray-50 dark:bg-outline-bg text-gray-500 dark:text-text-muted uppercase tracking-wider text-[11px] font-semibold">
            <tr>
              <th className="px-5 py-3 w-[80px] text-center">图标</th>
              <th className="px-5 py-3">项目名称</th>
              <th className="px-5 py-3 w-[120px]">权限状态</th>
              <th className="px-5 py-3 w-[120px]">文档数量</th>
              <th className="px-5 py-3 w-[150px]">负责人</th>
              <th className="px-5 py-3 w-[180px]">创建时间</th>
              <th className="px-5 py-3 w-[100px] text-center">操作</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-150 dark:divide-border-soft/60 text-gray-700 dark:text-text-main">
            {projectsList.map((proj) => {
              const isPrivate = proj.visibility === 'private';
              const canEdit = proj.owner_id === user?.id || user?.role === 'admin';
              const menuKey = `${section}-${proj.id}`;
              return (
                <tr 
                  key={proj.id} 
                  onClick={() => navigate(`/project/${proj.id}`)}
                  className="hover:bg-gray-50 dark:hover:bg-outline-bg/40 cursor-pointer transition-colors"
                >
                  <td className="px-5 py-3 text-center text-lg">{proj.icon || '📚'}</td>
                  <td className="px-5 py-3 font-semibold text-gray-900 dark:text-text-main hover:text-[#0052D9] transition-colors">{proj.name}</td>
                  <td className="px-5 py-3">
                    <span className={`px-2 py-0.5 rounded text-[10px] font-semibold ${
                      isPrivate 
                        ? 'bg-amber-50 text-amber-700 border border-amber-200/60 dark:bg-amber-950/20 dark:text-amber-400' 
                        : 'bg-emerald-50 text-emerald-700 border border-emerald-200/60 dark:bg-emerald-950/20 dark:text-emerald-400'
                    }`}>
                      {isPrivate ? '私有' : '公开'}
                    </span>
                  </td>
                  <td className="px-5 py-3 text-gray-500 dark:text-text-muted">{proj.sourceCount} 个文档</td>
                  <td className="px-5 py-3 text-gray-550 dark:text-text-muted">{proj.owner_name || '系统'}</td>
                  <td className="px-5 py-3 text-gray-400 dark:text-text-muted">{formatDate(proj.createdAt)}</td>
                  <td className="px-5 py-3 text-center" onClick={e => e.stopPropagation()}>
                    <div className="relative inline-block text-left" ref={activeMenu === menuKey ? menuRef : null}>
                      <button 
                        onClick={(e) => { e.stopPropagation(); setActiveMenu(activeMenu === menuKey ? null : menuKey); }}
                        className="text-gray-400 hover:text-gray-650 px-2 py-1 rounded hover:bg-gray-150 dark:hover:bg-outline-bg cursor-pointer transition-colors font-bold"
                      >
                        •••
                      </button>
                      {activeMenu === menuKey && (
                        <div className="absolute right-0 mt-1 w-36 bg-white dark:bg-panel-bg border border-gray-200 dark:border-border-soft rounded-lg shadow-lg py-1 z-50">
                          <button onClick={() => navigate(`/project/${proj.id}`)} className="w-full px-3 py-2 text-left text-xs text-gray-700 dark:text-text-main hover:bg-gray-50 dark:hover:bg-outline-bg flex items-center gap-2 cursor-pointer">
                            <LogIn className="w-3.5 h-3.5 text-[#0052D9]" /> 进入项目
                          </button>
                          {canEdit && (
                            <>
                              <button onClick={() => { setIconPickerFor(proj.id); setActiveMenu(null); }} className="w-full px-3 py-2 text-left text-xs text-gray-700 dark:text-text-main hover:bg-gray-50 dark:hover:bg-outline-bg flex items-center gap-2 cursor-pointer">
                                <span>🎨</span> 修改图标
                              </button>
                              <button onClick={() => { handleToggleVisibility(proj.id, proj.visibility || 'public'); setActiveMenu(null); }} className="w-full px-3 py-2 text-left text-xs text-gray-700 dark:text-text-main hover:bg-gray-50 dark:hover:bg-outline-bg flex items-center gap-2 cursor-pointer">
                                {isPrivate ? <><Globe className="w-3.5 h-3.5 text-green-500" /> 设为公开</> : <><Lock className="w-3.5 h-3.5 text-orange-500" /> 设为私有</>}
                              </button>
                              <button onClick={() => { handleDeleteProject(proj.id, proj.name); setActiveMenu(null); }} className="w-full px-3 py-2 text-left text-xs text-red-650 hover:bg-red-50 dark:hover:bg-red-950/20 flex items-center gap-2 cursor-pointer">
                                <Trash2 className="w-3.5 h-3.5" /> 删除项目
                              </button>
                            </>
                          )}
                        </div>
                      )}
                    </div>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    );
  };


  return (
    <>
      <div className="min-h-screen bg-[#F0EDE8] dark:bg-canvas-bg text-gray-800 dark:text-text-main font-sans">
        {/* Top Navigation */}
        <nav className="flex items-center justify-between px-6 py-4 bg-white/80 dark:bg-panel-bg/80 backdrop-blur-sm border-b border-[#E0DCD5] dark:border-border-soft sticky top-0 z-30">
          <div className="flex items-center gap-2">
            <img src="/logo.png" alt="Logo" className="h-16 w-auto object-contain" />
            <span className="text-xl font-bold tracking-tight text-gray-900 dark:text-text-main">{systemName}</span>
          </div>
          
          <div className="flex items-center gap-3">
            {/* 主题风格切换设置 */}
            <ThemeSwitcher />
            {/* 智能巡检健康指示灯 */}
            <SystemStatusIndicator />
            {/* 可视化看板（原齿轮设置按钮） */}
            <button 
              onClick={() => navigate('/linvis')} 
              className="flex items-center gap-1.5 px-3 py-1.5 rounded-full bg-gradient-to-r from-indigo-500/10 to-purple-500/10 border border-indigo-500/20 text-indigo-700 hover:from-indigo-500/20 hover:to-purple-500/20 transition-all font-semibold text-xs shadow-sm cursor-pointer" 
              title={`进入${linvisName}`}
            >
              <Settings className="w-3.5 h-3.5" />
              <span>{linvisName}</span>
            </button>
            {/* 用户头像菜单 */}
            <div className="relative" ref={userMenuRef}>
              <button onClick={() => setUserMenuOpen(!userMenuOpen)} className="w-9 h-9 rounded-full bg-gradient-to-br from-indigo-400 to-blue-500 text-white flex items-center justify-center font-bold text-sm overflow-hidden hover:ring-2 hover:ring-indigo-200 transition-all">
                {avatarUrl ? <img src={avatarUrl} alt="" className="w-full h-full object-cover" /> : (user?.username?.charAt(0) || 'U')}
              </button>
              {userMenuOpen && (
                <div className="absolute right-0 top-full mt-2 w-48 bg-white dark:bg-panel-bg border border-gray-200 dark:border-border-soft rounded-xl shadow-lg py-2 z-50">
                  <div className="px-4 py-2 border-b border-gray-100 dark:border-border-soft">
                    <p className="text-sm font-medium text-gray-900 dark:text-text-main">{user?.username}</p>
                    <p className="text-xs text-gray-400 dark:text-text-muted">{user?.login_name}</p>
                  </div>
                  {user?.role === 'admin' && (
                    <button onClick={() => { navigate('/admin'); setUserMenuOpen(false); }} className="w-full px-4 py-2.5 text-left text-sm text-gray-700 dark:text-text-main hover:bg-gray-50 dark:hover:bg-outline-bg flex items-center gap-2 border-b border-gray-100 dark:border-border-soft">
                      <span className="text-base text-indigo-500">⚙️</span> 后台管理
                    </button>
                  )}
                  <button onClick={() => { navigate('/profile'); setUserMenuOpen(false); }} className="w-full px-4 py-2.5 text-left text-sm text-gray-700 dark:text-text-main hover:bg-gray-50 dark:hover:bg-outline-bg flex items-center gap-2">
                    <Settings className="w-4 h-4 text-gray-400" /> 个人设置
                  </button>
                  <button onClick={() => { logout(); navigate('/login'); }} className="w-full px-4 py-2.5 text-left text-sm text-red-600 hover:bg-red-50 dark:hover:bg-red-950/20 flex items-center gap-2">
                    <LogIn className="w-4 h-4 rotate-180" /> 退出登录
                  </button>
                </div>
              )}
            </div>
          </div>
        </nav>

        {/* Main Content */}
        <main className="max-w-7xl mx-auto px-6 py-8">
          {pageLoading && <LogoSpinner size={72} overlay={false} />}
          <div className="flex items-center justify-between mb-8">
            <div className="flex items-center gap-4">
              <div className="text-xl font-bold tracking-tight text-gray-850 dark:text-text-main">项目空间</div>
              {/* 视图切换按钮组 */}
              <div className="flex items-center border border-gray-200 dark:border-border-soft rounded-lg p-0.5 bg-gray-100/60 dark:bg-outline-bg">
                <button
                  onClick={() => { setViewMode('list'); localStorage.setItem('home_view_mode', 'list'); }}
                  title="列表展示"
                  className={`p-1.5 rounded-md transition-all cursor-pointer ${
                    viewMode === 'list' 
                      ? 'bg-white dark:bg-panel-bg text-[#0052D9] shadow-sm font-semibold border border-gray-200/40' 
                      : 'text-gray-400 hover:text-gray-600'
                  }`}
                >
                  <List className="w-4 h-4" />
                </button>
                <button
                  onClick={() => { setViewMode('card'); localStorage.setItem('home_view_mode', 'card'); }}
                  title="卡片展示"
                  className={`p-1.5 rounded-md transition-all cursor-pointer ${
                    viewMode === 'card' 
                      ? 'bg-white dark:bg-panel-bg text-[#0052D9] shadow-sm font-semibold border border-gray-200/40' 
                      : 'text-gray-400 hover:text-gray-600'
                  }`}
                >
                  <LayoutGrid className="w-4 h-4" />
                </button>
              </div>
            </div>
            <div className="relative flex items-center gap-3">
              <Search className="w-4 h-4 text-gray-400 absolute left-3.5 pointer-events-none" />
              <input
                type="text"
                placeholder="搜索项目或公共文档库名称..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                className="pl-9 pr-8 py-2 w-64 bg-white border border-[#E0DCD5] rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-indigo-200 focus:border-indigo-500 transition-all placeholder:text-gray-400 shadow-sm"
              />
              {searchQuery && (
                <button 
                  onClick={() => setSearchQuery('')}
                  className="absolute right-2.5 p-1 hover:bg-gray-100 rounded-full text-gray-400 hover:text-gray-600 transition-colors"
                >
                  <X className="w-3.5 h-3.5" />
                </button>
              )}
            </div>
          </div>

          {/* 我的项目 */}
          <section className="mb-10">
            <h2 className="text-lg font-bold text-gray-900 mb-5 flex items-center justify-between">
              <span className="flex items-center gap-2">📋 我的项目 <span className="text-sm font-normal text-gray-400">({caseProjects.length})</span></span>
              {viewMode === 'list' && !searchQuery && (
                <button 
                  onClick={() => { setNewProjectType('case'); setIsModalOpen(true); setCreateError(''); setNewProjectName(''); }}
                  className="text-xs font-semibold text-[#0052D9] hover:text-[#003EB3] flex items-center gap-1.5 cursor-pointer bg-white dark:bg-panel-bg px-3 py-1.5 border border-gray-200 dark:border-border-soft rounded hover:shadow-sm transition-all"
                >
                  <Plus className="w-3.5 h-3.5" /> 新建项目
                </button>
              )}
            </h2>
            {viewMode === 'list' ? (
              renderProjectListTable(caseProjects, 'case')
            ) : (
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
                {!searchQuery && (
                  <div 
                    onClick={() => { setNewProjectType('case'); setIsModalOpen(true); setCreateError(''); setNewProjectName(''); }}
                    className="h-36 bg-white dark:bg-panel-bg border-2 border-dashed border-gray-300 dark:border-border-soft rounded-lg flex flex-col items-center justify-center cursor-pointer hover:shadow-sm hover:border-[#0052D9] transition-all duration-300 group"
                  >
                    <div className="w-10 h-10 bg-gray-50 dark:bg-outline-bg rounded-full flex items-center justify-center mb-2 group-hover:bg-[#E1ECFF] transition-colors">
                      <Plus className="w-4 h-4 text-gray-500 dark:text-[#0052D9]" />
                    </div>
                    <span className="text-xs font-medium text-gray-600 dark:text-text-muted">新建项目空间</span>
                  </div>
                )}
                {caseProjects.map(p => renderProjectCard(p, 'case'))}
              </div>
            )}
          </section>

          {/* 公开项目 */}
          {publicProjects.length > 0 && (
            <section className="mb-10">
              <h2 className="text-lg font-bold text-gray-900 mb-5 flex items-center gap-2">
                🌐 公开项目 <span className="text-sm font-normal text-gray-400">({publicProjects.length})</span>
              </h2>
              {viewMode === 'list' ? (
                renderProjectListTable(publicProjects, 'public')
              ) : (
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
                  {publicProjects.map(p => renderProjectCard(p, 'public'))}
                </div>
              )}
            </section>
          )}

          {/* 私有项目 */}
          {user?.role === 'admin' && privateProjects.length > 0 && (
            <section className="mb-10">
              <h2 className="text-lg font-bold text-gray-900 mb-5 flex items-center gap-2">
                🔒 私有项目 <span className="text-sm font-normal text-gray-400">({privateProjects.length})</span>
              </h2>
              {viewMode === 'list' ? (
                renderProjectListTable(privateProjects, 'private')
              ) : (
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
                  {privateProjects.map(p => renderProjectCard(p, 'private'))}
                </div>
              )}
            </section>
          )}

          {/* 公共文档 */}
          <section className="mb-10">
            <h2 className="text-lg font-bold text-gray-900 mb-5 flex items-center justify-between">
              <span className="flex items-center gap-2">📚 公共文档 <span className="text-sm font-normal text-gray-400">({libraryProjects.length})</span></span>
              {viewMode === 'list' && user?.role === 'admin' && !searchQuery && (
                <button 
                  onClick={() => { setNewProjectType('library'); setIsModalOpen(true); setCreateError(''); setNewProjectName(''); }}
                  className="text-xs font-semibold text-[#0052D9] hover:text-[#003EB3] flex items-center gap-1.5 cursor-pointer bg-white dark:bg-panel-bg px-3 py-1.5 border border-gray-200 dark:border-border-soft rounded hover:shadow-sm transition-all"
                >
                  <Plus className="w-3.5 h-3.5" /> 新建公共文档库
                </button>
              )}
            </h2>
            {viewMode === 'list' ? (
              renderProjectListTable(libraryProjects, 'library')
            ) : (
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
                {user?.role === 'admin' && !searchQuery && (
                  <div 
                    onClick={() => { setNewProjectType('library'); setIsModalOpen(true); setCreateError(''); setNewProjectName(''); }}
                    className="h-36 bg-white dark:bg-panel-bg border-2 border-dashed border-gray-300 dark:border-border-soft rounded-lg flex flex-col items-center justify-center cursor-pointer hover:shadow-sm hover:border-[#0052D9] transition-all duration-300 group"
                  >
                    <div className="w-10 h-10 bg-gray-50 dark:bg-outline-bg rounded-full flex items-center justify-center mb-2 group-hover:bg-[#E1ECFF] transition-colors">
                      <Library className="w-4 h-4 text-gray-500 dark:text-[#0052D9]" />
                    </div>
                    <span className="text-xs font-medium text-gray-600 dark:text-text-muted">新建公共文档库</span>
                  </div>
                )}
                {libraryProjects.length === 0 && user?.role !== 'admin' && (
                  <div className="col-span-full text-center text-gray-400 text-sm py-8">暂无公共文档库</div>
                )}
                {libraryProjects.map(p => renderProjectCard(p, 'library'))}
              </div>
            )}
          </section>
        </main>
      </div>

      {/* 新建项目弹窗 */}
      {isModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm">
          <div className="bg-white rounded-2xl shadow-2xl w-[480px] p-6">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-xl font-bold text-gray-900">
                {newProjectType === 'library' ? '📚 创建公共文档库' : '✨ 创建新项目空间'}
              </h2>
              <button onClick={() => setIsModalOpen(false)} className="p-1.5 hover:bg-gray-100 rounded-lg text-gray-400 hover:text-gray-600">
                <X className="w-5 h-5" />
              </button>
            </div>
            <p className="text-sm text-gray-500 mb-6">
              {newProjectType === 'library'
                ? '公共文档库用于存放公共法律法规等资料，可被各项目引用。'
                : '项目的知识库 and 文档将被独立隔离存放。'
              }
            </p>

            <div className="space-y-4">
              <div>
                <label className="text-sm font-medium text-gray-700 block mb-1">项目名称</label>
                <input 
                  type="text" autoFocus
                  value={newProjectName}
                  onChange={(e) => { setNewProjectName(e.target.value); if (createError) setCreateError(''); }}
                  onKeyDown={(e) => e.key === 'Enter' && handleCreateProject()}
                  placeholder={newProjectType === 'library' ? '例如：中国法律法规库' : '例如：智能体管理制度规范'}
                  className={`w-full px-4 py-2.5 bg-gray-50 border rounded-xl outline-none transition-all placeholder:text-gray-400 ${
                    createError ? 'border-red-300 focus:border-red-500 focus:ring-2 focus:ring-red-200' : 'border-gray-200 focus:border-indigo-500 focus:ring-2 focus:ring-indigo-200'
                  }`}
                />
                {createError && (
                  <p className="text-red-500 text-xs mt-1.5 flex items-center gap-1">
                    <span className="inline-block w-1 h-1 bg-red-500 rounded-full"></span>
                    {createError}
                  </p>
                )}
              </div>

              {/* 可见性选择 */}
              <div>
                <label className="text-sm font-medium text-gray-700 block mb-2">项目可见性</label>
                <div className="flex gap-3">
                  <button
                    onClick={() => setNewProjectVisibility('public')}
                    className={`flex-1 px-4 py-2.5 rounded-xl border text-sm font-medium flex items-center justify-center gap-2 transition-all ${
                      newProjectVisibility === 'public' ? 'border-green-400 bg-green-50 text-green-700' : 'border-gray-200 text-gray-500 hover:bg-gray-50'
                    }`}
                  >
                    <Globe className="w-4 h-4" /> 公开
                  </button>
                  <button
                    onClick={() => setNewProjectVisibility('private')}
                    className={`flex-1 px-4 py-2.5 rounded-xl border text-sm font-medium flex items-center justify-center gap-2 transition-all ${
                      newProjectVisibility === 'private' ? 'border-orange-400 bg-orange-50 text-orange-700' : 'border-gray-200 text-gray-500 hover:bg-gray-50'
                    }`}
                  >
                    <Lock className="w-4 h-4" /> 私有
                  </button>
                </div>
              </div>
            </div>

            <div className="mt-6 flex items-center justify-end gap-3">
              <button onClick={() => setIsModalOpen(false)} className="px-5 py-2.5 text-sm font-medium text-gray-600 hover:bg-gray-100 rounded-xl">取消</button>
              <button 
                onClick={handleCreateProject}
                disabled={isSubmitting || !newProjectName.trim()}
                className="px-5 py-2.5 text-sm font-medium text-white bg-indigo-600 hover:bg-indigo-700 rounded-xl shadow-sm disabled:opacity-50 flex items-center gap-2"
              >
                {isSubmitting && <Loader2 className="w-4 h-4 animate-spin" />}
                {newProjectType === 'library' ? '创建公共文档库' : '创建并进入工作台'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* 图标选择弹窗 (全局 Modal) */}
      {iconPickerFor && (
        <div className="fixed inset-0 z-[100] flex items-center justify-center bg-black/30 backdrop-blur-sm" onClick={() => setIconPickerFor(null)}>
          <div className="bg-white rounded-2xl border border-[#E0DCD5] shadow-2xl w-80 p-5" onClick={e => e.stopPropagation()}>
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-sm font-bold text-gray-800">选择空间图标</h3>
              <button onClick={() => setIconPickerFor(null)} className="p-1 hover:bg-gray-100 rounded-lg text-gray-400 hover:text-gray-600 transition-colors">
                <X className="w-4.5 h-4.5" />
              </button>
            </div>
            <div className="grid grid-cols-5 gap-2 max-h-60 overflow-y-auto pr-1">
              {PRESET_ICONS.map(icon => (
                <button
                  key={icon}
                  onClick={() => handleChangeIcon(iconPickerFor, icon)}
                  className="w-11 h-11 flex items-center justify-center text-2xl rounded-xl hover:bg-gray-50 active:scale-95 transition-all"
                >
                  {icon}
                </button>
              ))}
            </div>
          </div>
        </div>
      )}

      {projectToDelete && createPortal(
        <div className="fixed inset-0 z-[9999] flex items-center justify-center p-4 select-none">
          <div 
            className="absolute inset-0 bg-[#0F0F11]/45 backdrop-blur-[2px] transition-opacity" 
            onClick={() => setProjectToDelete(null)}
          />
          <div className="relative bg-white dark:bg-[#1E1F22] rounded-xl p-5 shadow-2xl border border-stone-200 dark:border-stone-850 max-w-sm w-full flex flex-col gap-4 animate-in fade-in zoom-in-95 duration-200" onClick={e => e.stopPropagation()}>
            <div className="flex items-start gap-3 text-stone-800 dark:text-stone-200">
              <div className="p-2.5 rounded-full bg-red-50 dark:bg-red-950/20 text-red-600 dark:text-red-400 shrink-0">
                <AlertTriangle className="w-5 h-5" />
              </div>
              <div className="flex flex-col gap-1 min-w-0">
                <h3 className="text-sm font-bold text-stone-900 dark:text-stone-100">
                  🗑️ 彻底删除项目空间
                </h3>
                <p className="text-xs text-stone-500 dark:text-stone-400 leading-normal mt-3 whitespace-pre-wrap font-sans">
                  确定要彻底删除项目「{projectToDelete.name}」吗？此操作将永久删除该项目的所有文件、归档文档和范文模板，不可恢复。
                </p>
              </div>
            </div>
            <div className="flex justify-end gap-2 mt-2">
              <button
                onClick={() => setProjectToDelete(null)}
                className="px-4 py-1.5 text-xs font-semibold text-stone-600 dark:text-stone-300 hover:text-stone-800 dark:hover:text-stone-100 hover:bg-stone-50 dark:hover:bg-stone-800 rounded-lg transition-colors border border-stone-200 dark:border-stone-700 cursor-pointer"
              >
                取消
              </button>
              <button
                onClick={() => {
                  void executeDeleteProject(projectToDelete.id);
                  setProjectToDelete(null);
                }}
                className="px-4 py-1.5 text-xs font-semibold text-white bg-red-600 hover:bg-red-700 active:scale-95 rounded-lg transition-all shadow-sm cursor-pointer"
              >
                确认彻底删除
              </button>
            </div>
          </div>
        </div>,
        document.body
      )}
    </>
  );
}
