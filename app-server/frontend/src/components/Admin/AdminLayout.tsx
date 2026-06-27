
import { Routes, Route, NavLink, useNavigate } from 'react-router-dom';
import { useAuthStore } from '../../store/authStore';
import UserManagement from './UserManagement';
import ProjectManagement from './ProjectManagement';
import LogManagement from './LogManagement';
import SystemSettings from './SystemSettings';
import LearningProgress from './LearningProgress';
import ServiceStatus from './ServiceStatus';
import LinvisSettings from './LinvisSettings';
import RagasEvaluation from './RagasEvaluation';
// AgentSettings 已移除 — 旧 Agent 配置已被 Go Eino 替代
import AITemplateManagement from './AITemplateManagement';
import { Users, FolderKanban, ScrollText, Settings, ArrowLeft, ShieldCheck, ActivitySquare, Activity, FileSpreadsheet, LineChart } from 'lucide-react';

const navItems = [
  { path: '/admin', label: '用户管理', icon: Users, end: true },
  { path: '/admin/projects', label: '项目管理', icon: FolderKanban },
  { path: '/admin/logs', label: '日志管理', icon: ScrollText },
  { path: '/admin/ai-templates', label: 'AI模板管理', icon: FileSpreadsheet },
  { path: '/admin/learning-progress', label: '学习进度', icon: ActivitySquare },
  { path: '/admin/service-status', label: '系统状态', icon: Activity },
  { path: '/admin/ragas-eval', label: '质量评测', icon: LineChart },
  { path: '/admin/linvis', label: '可视化看板', icon: FolderKanban },
  // { path: '/admin/agents', label: '多Agent协同', icon: Sparkles }, // 已移除，Go Eino 替代
  { path: '/admin/settings', label: '系统设置', icon: Settings },
];

export default function AdminLayout() {
  const navigate = useNavigate();
  const { user } = useAuthStore();

  if (user?.role !== 'admin') {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-50">
        <div className="text-center">
          <ShieldCheck className="w-16 h-16 text-red-400 mx-auto mb-4" />
          <h2 className="text-xl font-bold text-gray-800">无权限访问</h2>
          <p className="text-gray-500 mt-2">仅管理员可进入后台管理</p>
          <button onClick={() => navigate('/')} className="mt-4 px-4 py-2 bg-indigo-500 text-white rounded-lg">返回首页</button>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gray-50 flex">
      {/* 左侧导航 */}
      <aside className="w-56 bg-white border-r border-gray-200 flex flex-col">
        <div className="p-5 border-b border-gray-100">
          <h1 className="text-lg font-bold text-gray-800 flex items-center gap-2">
            <ShieldCheck className="w-5 h-5 text-indigo-500" />
            后台管理
          </h1>
        </div>
        <nav className="flex-1 p-3 space-y-1">
          {navItems.map(item => (
            <NavLink
              key={item.path}
              to={item.path}
              end={item.end}
              className={({ isActive }) =>
                `flex items-center gap-2.5 px-4 py-2.5 rounded-xl text-sm font-medium transition-colors ${
                  isActive ? 'bg-indigo-50 text-indigo-700' : 'text-gray-600 hover:bg-gray-50'
                }`
              }
            >
              <item.icon className="w-4 h-4" />
              {item.label}
            </NavLink>
          ))}
          {/* 返回首页直接置于系统设置下方，带优雅淡色分割线 */}
          <div className="my-2 border-t border-gray-100" />
          <button
            onClick={() => navigate('/')}
            className="flex items-center gap-2.5 px-4 py-2.5 text-sm text-gray-600 hover:bg-gray-50 w-full rounded-xl transition-colors font-medium"
          >
            <ArrowLeft className="w-4 h-4" /> 返回首页
          </button>
        </nav>
      </aside>

      {/* 右侧内容区 */}
      <main className="flex-1 p-8 overflow-auto">
        <Routes>
          <Route index element={<UserManagement />} />
          <Route path="projects" element={<ProjectManagement />} />
          <Route path="logs" element={<LogManagement />} />
          <Route path="learning-progress" element={<LearningProgress />} />
          <Route path="service-status" element={<ServiceStatus />} />
          <Route path="settings" element={<SystemSettings />} />
          <Route path="linvis" element={<LinvisSettings />} />
          <Route path="ragas-eval" element={<RagasEvaluation />} />
          {/* agents 路由已移除 — 旧 Agent 配置已被 Go Eino 替代 */}
          <Route path="ai-templates" element={<AITemplateManagement />} />
        </Routes>
      </main>
    </div>
  );
}
