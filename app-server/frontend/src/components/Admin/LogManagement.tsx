import { useState, useEffect, useMemo } from 'react';
import { useAuthStore } from '../../store/authStore';
import {
  Loader2, ChevronLeft, ChevronRight, Search, Filter, Users,
  Activity, Clock, LogIn, Upload, FileText, Sparkles, Download,
  Settings, UserCog, Shield, X
} from 'lucide-react';

const API_BASE = import.meta.env.VITE_API_BASE || '';

interface LogItem {
  id: string;
  user_id: string;
  user_name: string;
  action: string;
  detail: string;
  timestamp: string;
}

interface UserActivity {
  user: {
    id: string;
    username: string;
    login_name?: string;
    role?: string;
  };
  total_ops: number;
  last_login: string | null;
  last_active: string | null;
  action_counts: Record<string, number>;
}

/**
 * 操作类型配置表。
 * WHY: 集中管理所有 action 的中文标签、颜色和图标，新增操作类型只需加一行。
 */
const actionConfig: Record<string, { label: string; color: string; icon: typeof LogIn }> = {
  user_login:           { label: '用户登录',   color: 'bg-blue-50 text-blue-700 border-blue-200',         icon: LogIn },
  user_register:        { label: '用户注册',   color: 'bg-emerald-50 text-emerald-700 border-emerald-200', icon: UserCog },
  user_update_profile:  { label: '修改信息',   color: 'bg-cyan-50 text-cyan-700 border-cyan-200',         icon: UserCog },
  user_change_password: { label: '修改密码',   color: 'bg-amber-50 text-amber-700 border-amber-200',       icon: Shield },
  file_upload:          { label: '上传文件',   color: 'bg-violet-50 text-violet-700 border-violet-200',   icon: Upload },
  file_delete:          { label: '删除文件',   color: 'bg-red-50 text-red-600 border-red-200',             icon: X },
  folder_delete:        { label: '删除文件夹', color: 'bg-red-50 text-red-600 border-red-200',             icon: X },
  document_save:        { label: '保存文档',   color: 'bg-sky-50 text-sky-700 border-sky-200',             icon: FileText },
  document_export:      { label: '导出文档',   color: 'bg-indigo-50 text-indigo-700 border-indigo-200',   icon: Download },
  content_generate:     { label: 'AI生成',     color: 'bg-purple-50 text-purple-700 border-purple-200',   icon: Sparkles },
  project_create:       { label: '创建案件',   color: 'bg-green-50 text-green-700 border-green-200',       icon: FileText },
  project_delete:       { label: '删除案件',   color: 'bg-red-50 text-red-600 border-red-200',             icon: X },
  project_visibility:   { label: '修改可见性', color: 'bg-orange-50 text-orange-700 border-orange-200',   icon: Settings },
  admin_approve_user:   { label: '审批用户',   color: 'bg-emerald-50 text-emerald-700 border-emerald-200', icon: Shield },
  admin_disable_user:   { label: '禁用用户',   color: 'bg-amber-50 text-amber-700 border-amber-200',       icon: Shield },
  admin_enable_user:    { label: '启用用户',   color: 'bg-blue-50 text-blue-700 border-blue-200',         icon: Shield },
  admin_delete_user:    { label: '删除用户',   color: 'bg-red-50 text-red-600 border-red-200',             icon: Shield },
  admin_delete_project: { label: '删除案件',   color: 'bg-red-50 text-red-600 border-red-200',             icon: Shield },
  admin_update_project: { label: '修改案件',   color: 'bg-indigo-50 text-indigo-700 border-indigo-200',   icon: Shield },
  admin_update_settings:{ label: '修改设置',   color: 'bg-purple-50 text-purple-700 border-purple-200',   icon: Settings },
};

/** 时间格式化：优先显示"几分钟前"等相对时间 */
function relativeTime(ts: string): string {
  const dateStr = ts.replace('T', ' ').replace(/-/g, '/');
  const d = new Date(dateStr);
  const now = Date.now();
  const diff = now - d.getTime();
  if (diff < 60_000) return '刚刚';
  if (diff < 3600_000) return `${Math.floor(diff / 60_000)}分钟前`;
  if (diff < 86400_000) return `${Math.floor(diff / 3600_000)}小时前`;
  if (diff < 172800_000) return '昨天';
  return d.toLocaleDateString('zh-CN', { month: '2-digit', day: '2-digit' }) + ' ' +
         d.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' });
}

export default function LogManagement() {
  const { getAuthHeaders } = useAuthStore();
  const [logs, setLogs] = useState<LogItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);
  const pageSize = 30;

  // 筛选状态
  const [filterUserId, setFilterUserId] = useState('');
  const [filterAction, setFilterAction] = useState('');

  // 用户活跃概览
  const [userActivity, setUserActivity] = useState<UserActivity[]>([]);
  const [activityLoading, setActivityLoading] = useState(true);

  // 用户列表（用于下拉选择）
  const [userList, setUserList] = useState<{ id: string; username: string }[]>([]);

  // 当前视图切换
  const [activeTab, setActiveTab] = useState<'logs' | 'activity'>('logs');

  // 获取用户列表
  useEffect(() => {
    fetch(`${API_BASE}/api/admin/users`, { headers: getAuthHeaders() })
      .then(res => res.ok ? res.json() : [])
      .then(users => setUserList(users.map((u: any) => ({ id: u.id, username: u.username }))))
      .catch(() => {});
  }, []);

  // 获取用户活跃概览
  useEffect(() => {
    setActivityLoading(true);
    fetch(`${API_BASE}/api/admin/user-activity`, { headers: getAuthHeaders() })
      .then(res => res.ok ? res.json() : [])
      .then(data => setUserActivity(data))
      .catch(() => {})
      .finally(() => setActivityLoading(false));
  }, []);

  // 获取日志（带筛选）
  const fetchLogs = async () => {
    setLoading(true);
    try {
      const params = new URLSearchParams({ page: page.toString(), page_size: pageSize.toString() });
      if (filterUserId) params.set('user_id', filterUserId);
      if (filterAction) params.set('action', filterAction);
      const res = await fetch(`${API_BASE}/api/admin/logs?${params}`, { headers: getAuthHeaders() });
      if (res.ok) {
        const data = await res.json();
        setLogs(data.logs);
        setTotal(data.total);
      }
    } catch { }
    setLoading(false);
  };

  useEffect(() => { fetchLogs(); }, [page, filterUserId, filterAction]);

  // 页码在筛选变化时重置
  useEffect(() => { setPage(1); }, [filterUserId, filterAction]);

  const totalPages = Math.ceil(total / pageSize);

  // 统计卡片数据
  const stats = useMemo(() => {
    const today = new Date().toDateString();
    const todayLogins = new Set(
      userActivity
        .filter(a => a.last_login && new Date(a.last_login).toDateString() === today)
        .map(a => a.user.id)
    );
    return {
      totalLogs: total,
      todayActiveUsers: todayLogins.size,
      totalUsers: userActivity.length,
    };
  }, [total, userActivity]);

  return (
    <div>
      {/* 标题 + 标签切换 */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h2 className="text-xl font-bold text-gray-800">操作审计</h2>
          <p className="text-sm text-gray-500 mt-1">查看用户的登录记录和系统操作</p>
        </div>
        <div className="flex bg-gray-100 rounded-xl p-1">
          <button
            onClick={() => setActiveTab('logs')}
            className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
              activeTab === 'logs'
                ? 'bg-white text-gray-800 shadow-sm'
                : 'text-gray-500 hover:text-gray-700'
            }`}
          >
            <Activity className="w-4 h-4 inline mr-1.5" />操作日志
          </button>
          <button
            onClick={() => setActiveTab('activity')}
            className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
              activeTab === 'activity'
                ? 'bg-white text-gray-800 shadow-sm'
                : 'text-gray-500 hover:text-gray-700'
            }`}
          >
            <Users className="w-4 h-4 inline mr-1.5" />用户活跃
          </button>
        </div>
      </div>

      {/* 统计卡片 */}
      <div className="grid grid-cols-3 gap-4 mb-6">
        <div className="bg-white rounded-xl border border-gray-200 p-4 flex items-center gap-4">
          <div className="w-10 h-10 rounded-xl bg-indigo-50 flex items-center justify-center">
            <Activity className="w-5 h-5 text-indigo-500" />
          </div>
          <div>
            <div className="text-2xl font-bold text-gray-800">{stats.totalLogs}</div>
            <div className="text-xs text-gray-500">操作记录总数</div>
          </div>
        </div>
        <div className="bg-white rounded-xl border border-gray-200 p-4 flex items-center gap-4">
          <div className="w-10 h-10 rounded-xl bg-green-50 flex items-center justify-center">
            <Users className="w-5 h-5 text-green-500" />
          </div>
          <div>
            <div className="text-2xl font-bold text-gray-800">{stats.todayActiveUsers}</div>
            <div className="text-xs text-gray-500">今日活跃用户</div>
          </div>
        </div>
        <div className="bg-white rounded-xl border border-gray-200 p-4 flex items-center gap-4">
          <div className="w-10 h-10 rounded-xl bg-blue-50 flex items-center justify-center">
            <Clock className="w-5 h-5 text-blue-500" />
          </div>
          <div>
            <div className="text-2xl font-bold text-gray-800">{stats.totalUsers}</div>
            <div className="text-xs text-gray-500">有操作记录的用户</div>
          </div>
        </div>
      </div>

      {/* ========== 操作日志 Tab ========== */}
      {activeTab === 'logs' && (
        <>
          {/* 筛选栏 */}
          <div className="flex items-center gap-3 mb-4">
            <div className="relative flex-1 max-w-xs">
              <Filter className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
              <select
                value={filterUserId}
                onChange={e => setFilterUserId(e.target.value)}
                className="w-full pl-9 pr-3 py-2.5 bg-white border border-gray-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-indigo-200 appearance-none"
              >
                <option value="">全部用户</option>
                {userList.map(u => (
                  <option key={u.id} value={u.id}>{u.username}</option>
                ))}
              </select>
            </div>
            <div className="relative flex-1 max-w-xs">
              <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
              <select
                value={filterAction}
                onChange={e => setFilterAction(e.target.value)}
                className="w-full pl-9 pr-3 py-2.5 bg-white border border-gray-200 rounded-xl text-sm focus:outline-none focus:ring-2 focus:ring-indigo-200 appearance-none"
              >
                <option value="">全部操作</option>
                {Object.entries(actionConfig).map(([key, cfg]) => (
                  <option key={key} value={key}>{cfg.label}</option>
                ))}
              </select>
            </div>
            {(filterUserId || filterAction) && (
              <button
                onClick={() => { setFilterUserId(''); setFilterAction(''); }}
                className="px-3 py-2.5 text-sm text-gray-500 hover:text-gray-700 hover:bg-gray-100 rounded-xl transition-colors"
              >
                <X className="w-4 h-4 inline mr-1" />清除
              </button>
            )}
            <div className="ml-auto text-sm text-gray-500">
              共 {total} 条记录
            </div>
          </div>

          {/* 日志表格 */}
          {loading ? (
            <div className="flex justify-center py-12"><Loader2 className="w-6 h-6 animate-spin text-gray-400" /></div>
          ) : (
            <>
              <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
                <table className="w-full text-sm">
                  <thead className="bg-gray-50 border-b border-gray-200">
                    <tr>
                      <th className="text-left px-4 py-3 font-medium text-gray-600 w-40">时间</th>
                      <th className="text-left px-4 py-3 font-medium text-gray-600 w-28">操作人</th>
                      <th className="text-left px-4 py-3 font-medium text-gray-600 w-36">操作类型</th>
                      <th className="text-left px-4 py-3 font-medium text-gray-600">详情</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-100">
                    {logs.map(log => {
                      const cfg = actionConfig[log.action] || { label: log.action, color: 'bg-gray-50 text-gray-600 border-gray-200', icon: Activity };
                      const IconComp = cfg.icon;
                      return (
                        <tr key={log.id} className="hover:bg-gray-50/50 transition-colors">
                          <td className="px-4 py-3 text-gray-400 text-xs whitespace-nowrap font-mono">
                            {relativeTime(log.timestamp)}
                          </td>
                          <td className="px-4 py-3">
                            <button
                              onClick={() => setFilterUserId(log.user_id || '')}
                              className="text-gray-700 font-medium hover:text-indigo-600 transition-colors"
                              title="点击筛选此用户"
                            >
                              {log.user_name}
                            </button>
                          </td>
                          <td className="px-4 py-3">
                            <span className={`inline-flex items-center gap-1 px-2.5 py-1 rounded-lg text-xs font-medium border whitespace-nowrap ${cfg.color}`}>
                              <IconComp className="w-3 h-3" />
                              {cfg.label}
                            </span>
                          </td>
                          <td className="px-4 py-3 text-gray-600 max-w-md truncate" title={log.detail}>
                            {log.detail}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
                {logs.length === 0 && <div className="text-center py-12 text-gray-400">暂无匹配的日志记录</div>}
              </div>

              {/* 分页 */}
              {totalPages > 1 && (
                <div className="flex items-center justify-center gap-3 mt-4">
                  <button
                    onClick={() => setPage(p => Math.max(1, p - 1))}
                    disabled={page === 1}
                    className="p-2 rounded-lg hover:bg-gray-100 disabled:opacity-30 transition-colors"
                  >
                    <ChevronLeft className="w-4 h-4" />
                  </button>
                  <span className="text-sm text-gray-600">第 {page} / {totalPages} 页</span>
                  <button
                    onClick={() => setPage(p => Math.min(totalPages, p + 1))}
                    disabled={page === totalPages}
                    className="p-2 rounded-lg hover:bg-gray-100 disabled:opacity-30 transition-colors"
                  >
                    <ChevronRight className="w-4 h-4" />
                  </button>
                </div>
              )}
            </>
          )}
        </>
      )}

      {/* ========== 用户活跃 Tab ========== */}
      {activeTab === 'activity' && (
        <>
          {activityLoading ? (
            <div className="flex justify-center py-12"><Loader2 className="w-6 h-6 animate-spin text-gray-400" /></div>
          ) : (
            <div className="space-y-3">
              {userActivity.length === 0 && (
                <div className="text-center py-12 text-gray-400">暂无用户活跃数据</div>
              )}
              {userActivity.map(item => {
                const loginCount = item.action_counts['user_login'] || 0;
                const generateCount = item.action_counts['content_generate'] || 0;
                const uploadCount = item.action_counts['file_upload'] || 0;
                const saveCount = item.action_counts['document_save'] || 0;
                const exportCount = item.action_counts['document_export'] || 0;

                return (
                  <div
                    key={item.user.id}
                    className="bg-white rounded-xl border border-gray-200 p-5 hover:shadow-sm transition-shadow"
                  >
                    <div className="flex items-center justify-between">
                      {/* 用户信息 */}
                      <div className="flex items-center gap-4">
                        <div className="w-10 h-10 rounded-full bg-gradient-to-br from-indigo-400 to-purple-500 flex items-center justify-center text-white font-bold text-sm">
                          {(item.user.username || '?')[0]}
                        </div>
                        <div>
                          <div className="font-semibold text-gray-800">{item.user.username}</div>
                          <div className="text-xs text-gray-400 mt-0.5">
                            {item.user.login_name && <span className="mr-3">@{item.user.login_name}</span>}
                            {item.user.role === 'admin' && (
                              <span className="px-1.5 py-0.5 bg-amber-50 text-amber-600 rounded text-[10px] font-medium border border-amber-200">管理员</span>
                            )}
                          </div>
                        </div>
                      </div>

                      {/* 最近活跃 */}
                      <div className="text-right">
                        <div className="text-xs text-gray-400">最近登录</div>
                        <div className="text-sm font-medium text-gray-700">
                          {item.last_login ? relativeTime(item.last_login) : '从未登录'}
                        </div>
                      </div>
                    </div>

                    {/* 操作统计 */}
                    <div className="flex items-center gap-6 mt-4 pt-3 border-t border-gray-100">
                      <div className="flex items-center gap-1.5 text-xs text-gray-500">
                        <LogIn className="w-3.5 h-3.5 text-blue-400" />
                        登录 <span className="font-semibold text-gray-700">{loginCount}</span>
                      </div>
                      <div className="flex items-center gap-1.5 text-xs text-gray-500">
                        <Sparkles className="w-3.5 h-3.5 text-purple-400" />
                        AI生成 <span className="font-semibold text-gray-700">{generateCount}</span>
                      </div>
                      <div className="flex items-center gap-1.5 text-xs text-gray-500">
                        <Upload className="w-3.5 h-3.5 text-violet-400" />
                        上传 <span className="font-semibold text-gray-700">{uploadCount}</span>
                      </div>
                      <div className="flex items-center gap-1.5 text-xs text-gray-500">
                        <FileText className="w-3.5 h-3.5 text-sky-400" />
                        保存 <span className="font-semibold text-gray-700">{saveCount}</span>
                      </div>
                      <div className="flex items-center gap-1.5 text-xs text-gray-500">
                        <Download className="w-3.5 h-3.5 text-indigo-400" />
                        导出 <span className="font-semibold text-gray-700">{exportCount}</span>
                      </div>
                      <div className="ml-auto text-xs text-gray-400">
                        共 <span className="font-semibold text-gray-600">{item.total_ops}</span> 次操作
                      </div>
                      <button
                        onClick={() => { setFilterUserId(item.user.id); setActiveTab('logs'); }}
                        className="px-3 py-1.5 text-xs text-indigo-600 hover:bg-indigo-50 rounded-lg transition-colors font-medium"
                      >
                        查看详情 →
                      </button>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </>
      )}
    </div>
  );
}
