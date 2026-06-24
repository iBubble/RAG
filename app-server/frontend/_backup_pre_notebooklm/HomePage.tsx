import { useState, useEffect, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { Plus, Settings, X, Loader2, LogIn, Trash2, Globe, Lock, Library } from 'lucide-react';
import { useAuthStore } from '../../store/authStore';

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
  const [projects, setProjects] = useState<Project[]>([]);
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [newProjectName, setNewProjectName] = useState('');
  const [newProjectVisibility, setNewProjectVisibility] = useState('public');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [createError, setCreateError] = useState('');
  const [activeMenu, setActiveMenu] = useState<string | null>(null);
  const [userMenuOpen, setUserMenuOpen] = useState(false);
  const [newProjectType, setNewProjectType] = useState('case');
  const menuRef = useRef<HTMLDivElement>(null);
  const userMenuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (menuRef.current && !menuRef.current.contains(e.target as Node)) setActiveMenu(null);
      if (userMenuRef.current && !userMenuRef.current.contains(e.target as Node)) setUserMenuOpen(false);
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  useEffect(() => { void fetchProjects(); }, []);

  const fetchProjects = async () => {
    try {
      const res = await fetch(`${API_BASE}/api/projects`, { headers: getAuthHeaders() });
      if (res.ok) setProjects(await res.json());
    } catch (error) {
      console.error('Failed to fetch projects', error);
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

  const handleDeleteProject = async (projId: string, projName: string) => {
    if (!window.confirm(`❗ 确定要彻底删除案件「${projName}」吗？\n\n此操作将永久删除该案件的所有文件、归档文档和范文模板，不可恢复。`)) return;
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

  // 分区：我的案件 / 公共文档 / 其他人的公开案件
  const caseProjects = projects.filter(p => p.project_type !== 'library' && p.owner_id === user?.id);
  const libraryProjects = projects.filter(p => p.project_type === 'library');
  const publicProjects = projects.filter(p => p.project_type !== 'library' && p.owner_id !== user?.id);

  const avatarUrl = user?.avatar ? `${API_BASE}${user.avatar}` : '';

  // 渲染项目卡片
  const renderProjectCard = (proj: Project) => {
    const isLibrary = proj.project_type === 'library';
    const canEdit = proj.owner_id === user?.id || user?.role === 'admin';
    return (
    <div
      key={proj.id}
      onClick={() => navigate(`/project/${proj.id}`)}
      className={`h-56 border rounded-2xl p-5 flex flex-col cursor-pointer hover:shadow-md transition-all relative ${
        isLibrary ? 'bg-gradient-to-br from-blue-50 to-indigo-50 border-indigo-100/50' : 'bg-[#FDF8F5] border-orange-100/50'
      }`}
    >
      <div className="flex items-center justify-between mb-auto">
        <div className="text-7xl">{isLibrary ? '📚' : (proj.icon || '⚖️')}</div>
        <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${
          proj.visibility === 'private' ? 'bg-orange-100 text-orange-600' : 'bg-green-100 text-green-600'
        }`}>
          {proj.visibility === 'private' ? '🔒 私有' : '🌐 公开'}
        </span>
      </div>
      {/* 三点菜单 */}
      <div className="absolute top-4 right-4" ref={activeMenu === proj.id ? menuRef : null}>
        <button
          onClick={(e) => { e.stopPropagation(); setActiveMenu(activeMenu === proj.id ? null : proj.id); }}
          className="p-1.5 text-gray-400 hover:text-gray-700 hover:bg-gray-100 rounded-lg transition-colors"
        >
          <div className="flex flex-col gap-0.5">
            <div className="w-1 h-1 bg-current rounded-full"></div>
            <div className="w-1 h-1 bg-current rounded-full"></div>
            <div className="w-1 h-1 bg-current rounded-full"></div>
          </div>
        </button>
        {activeMenu === proj.id && (
          <div className="absolute right-0 top-full mt-1 w-40 bg-white border border-gray-200 rounded-xl shadow-lg py-1 z-50">
            <button onClick={(e) => { e.stopPropagation(); navigate(`/project/${proj.id}`); }} className="w-full px-4 py-2.5 text-left text-sm text-gray-700 hover:bg-gray-50 flex items-center gap-2.5">
              <LogIn className="w-4 h-4 text-blue-500" /> 进入
            </button>
            {canEdit && (
              <>
                <button onClick={(e) => { e.stopPropagation(); handleToggleVisibility(proj.id, proj.visibility || 'public'); }} className="w-full px-4 py-2.5 text-left text-sm text-gray-700 hover:bg-gray-50 flex items-center gap-2.5">
                  {proj.visibility === 'private' ? <><Globe className="w-4 h-4 text-green-500" /> 设为公开</> : <><Lock className="w-4 h-4 text-orange-500" /> 设为私有</>}
                </button>
                <button onClick={(e) => { e.stopPropagation(); handleDeleteProject(proj.id, proj.name); }} className="w-full px-4 py-2.5 text-left text-sm text-red-600 hover:bg-red-50 flex items-center gap-2.5">
                  <Trash2 className="w-4 h-4" /> 删除
                </button>
              </>
            )}
          </div>
        )}
      </div>
      <div className="flex items-end justify-between">
        <div>
          <h3 className="font-medium text-gray-900 text-lg leading-snug mb-2 line-clamp-2">{proj.name}</h3>
          <p className="text-xs text-gray-500">
            {formatDate(proj.createdAt)} · {proj.sourceCount} 个文档
          </p>
        </div>
        {proj.owner_name && (
          <span className="text-xs text-gray-400 shrink-0 ml-3">
            {proj.owner_name}
          </span>
        )}
      </div>
    </div>
    );
  };

  return (
    <>
      <div className="min-h-screen bg-[#FDFDFD] text-gray-800 font-sans">
        {/* Top Navigation */}
        <nav className="flex items-center justify-between px-6 py-4 border-b border-gray-100">
          <div className="flex items-center gap-2">
            <img src="/logo.png" alt="Logo" className="h-16 w-auto object-contain" />
            <span className="text-xl font-bold tracking-tight text-gray-900">貔貅法律知识库 V1.0.1</span>
          </div>
          
          <div className="flex items-center gap-3">
            {/* 管理员齿轮 */}
            {user?.role === 'admin' && (
              <button onClick={() => navigate('/admin')} className="p-2 hover:bg-gray-100 rounded-full transition-colors" title="后台管理">
                <Settings className="w-5 h-5 text-gray-600" />
              </button>
            )}
            {/* 用户头像菜单 */}
            <div className="relative" ref={userMenuRef}>
              <button onClick={() => setUserMenuOpen(!userMenuOpen)} className="w-9 h-9 rounded-full bg-gradient-to-br from-indigo-400 to-blue-500 text-white flex items-center justify-center font-bold text-sm overflow-hidden hover:ring-2 hover:ring-indigo-200 transition-all">
                {avatarUrl ? <img src={avatarUrl} alt="" className="w-full h-full object-cover" /> : (user?.username?.charAt(0) || 'U')}
              </button>
              {userMenuOpen && (
                <div className="absolute right-0 top-full mt-2 w-48 bg-white border border-gray-200 rounded-xl shadow-lg py-2 z-50">
                  <div className="px-4 py-2 border-b border-gray-100">
                    <p className="text-sm font-medium text-gray-900">{user?.username}</p>
                    <p className="text-xs text-gray-400">{user?.login_name}</p>
                  </div>
                  <button onClick={() => { navigate('/profile'); setUserMenuOpen(false); }} className="w-full px-4 py-2.5 text-left text-sm text-gray-700 hover:bg-gray-50 flex items-center gap-2">
                    <Settings className="w-4 h-4 text-gray-400" /> 个人设置
                  </button>
                  <button onClick={() => { logout(); navigate('/login'); }} className="w-full px-4 py-2.5 text-left text-sm text-red-600 hover:bg-red-50 flex items-center gap-2">
                    <LogIn className="w-4 h-4 rotate-180" /> 退出登录
                  </button>
                </div>
              )}
            </div>
          </div>
        </nav>

        {/* Main Content */}
        <main className="max-w-7xl mx-auto px-6 py-8">
          <div className="flex items-center justify-between mb-8">
            <div className="text-xl font-bold tracking-tight text-gray-800">案件空间</div>
            <div className="flex items-center gap-3">
              <button 
                onClick={() => { setNewProjectType('case'); setIsModalOpen(true); setCreateError(''); setNewProjectName(''); setNewProjectVisibility('public'); }}
                className="flex items-center gap-2 px-5 py-2.5 bg-gray-900 text-white rounded-full text-sm font-medium hover:bg-gray-800 shadow-md transition-all"
              >
                <Plus className="w-4 h-4" /> 新建案件
              </button>
              {user?.role === 'admin' && (
                <button 
                  onClick={() => { setNewProjectType('library'); setIsModalOpen(true); setCreateError(''); setNewProjectName(''); setNewProjectVisibility('public'); }}
                  className="flex items-center gap-2 px-5 py-2.5 bg-indigo-600 text-white rounded-full text-sm font-medium hover:bg-indigo-700 shadow-md transition-all"
                >
                  <Library className="w-4 h-4" /> 新建公共文档库
                </button>
              )}
            </div>
          </div>

          {/* 我的案件 */}
          <section className="mb-10">
            <h2 className="text-lg font-bold text-gray-900 mb-5 flex items-center gap-2">
              📋 我的案件 <span className="text-sm font-normal text-gray-400">({caseProjects.length})</span>
            </h2>
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
              <div 
                onClick={() => { setNewProjectType('case'); setIsModalOpen(true); setCreateError(''); setNewProjectName(''); }}
                className="h-56 bg-white border border-gray-200 rounded-2xl flex flex-col items-center justify-center cursor-pointer hover:shadow-md hover:border-blue-200 transition-all group"
              >
                <div className="w-14 h-14 bg-indigo-50 rounded-full flex items-center justify-center mb-4 group-hover:bg-indigo-100 transition-colors">
                  <Plus className="w-6 h-6 text-indigo-600" />
                </div>
                <span className="font-medium text-gray-700">新建案件空间</span>
              </div>
              {caseProjects.map(renderProjectCard)}
            </div>
          </section>

          {/* 公共文档 */}
          <section className="mb-10">
            <h2 className="text-lg font-bold text-gray-900 mb-5 flex items-center gap-2">
              📚 公共文档 <span className="text-sm font-normal text-gray-400">({libraryProjects.length})</span>
            </h2>
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
              {user?.role === 'admin' && (
                <div 
                  onClick={() => { setNewProjectType('library'); setIsModalOpen(true); setCreateError(''); setNewProjectName(''); }}
                  className="h-56 bg-white border border-indigo-200 rounded-2xl flex flex-col items-center justify-center cursor-pointer hover:shadow-md hover:border-indigo-300 transition-all group"
                >
                  <div className="w-14 h-14 bg-blue-50 rounded-full flex items-center justify-center mb-4 group-hover:bg-blue-100 transition-colors">
                    <Library className="w-6 h-6 text-indigo-600" />
                  </div>
                  <span className="font-medium text-indigo-700">新建公共文档库</span>
                </div>
              )}
              {libraryProjects.length === 0 && user?.role !== 'admin' && (
                <div className="col-span-full text-center text-gray-400 text-sm py-8">暂无公共文档库</div>
              )}
              {libraryProjects.map(renderProjectCard)}
            </div>
          </section>

          {/* 公开案件 */}
          {publicProjects.length > 0 && (
            <section>
              <h2 className="text-lg font-bold text-gray-900 mb-5 flex items-center gap-2">
                🌐 公开案件 <span className="text-sm font-normal text-gray-400">({publicProjects.length})</span>
              </h2>
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6">
                {publicProjects.map(renderProjectCard)}
              </div>
            </section>
          )}
        </main>
      </div>

      {/* 新建案件弹窗 */}
      {isModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm">
          <div className="bg-white rounded-2xl shadow-2xl w-[480px] p-6">
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-xl font-bold text-gray-900">
                {newProjectType === 'library' ? '📚 创建公共文档库' : '✨ 创建新案件空间'}
              </h2>
              <button onClick={() => setIsModalOpen(false)} className="p-1.5 hover:bg-gray-100 rounded-lg text-gray-400 hover:text-gray-600">
                <X className="w-5 h-5" />
              </button>
            </div>
            <p className="text-sm text-gray-500 mb-6">
              {newProjectType === 'library'
                ? '公共文档库用于存放公共法律法规等资料，可被各案件引用。'
                : '案件的知识库和文档将被独立隔离存放。'
              }
            </p>

            <div className="space-y-4">
              <div>
                <label className="text-sm font-medium text-gray-700 block mb-1">案件名称</label>
                <input 
                  type="text" autoFocus
                  value={newProjectName}
                  onChange={(e) => { setNewProjectName(e.target.value); if (createError) setCreateError(''); }}
                  onKeyDown={(e) => e.key === 'Enter' && handleCreateProject()}
                  placeholder={newProjectType === 'library' ? '例如：中国法律法规库' : '例如：张三诉李四伤害赔偿案'}
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
                <label className="text-sm font-medium text-gray-700 block mb-2">案件可见性</label>
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
    </>
  );
}
