import { useState, useEffect } from 'react';
import { useAuthStore } from '../../store/authStore';
import { CheckCircle, Trash2, Loader2, UserCheck, UserX } from 'lucide-react';

const API_BASE = import.meta.env.VITE_API_BASE || '';

interface UserItem {
  id: string;
  username: string;
  login_name: string;
  email: string;
  company: string;
  department: string;
  role: string;
  status: string;
  created_at: string;
}

export default function UserManagement() {
  const { getAuthHeaders } = useAuthStore();
  const [users, setUsers] = useState<UserItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState('all');

  const fetchUsers = async () => {
    setLoading(true);
    try {
      const url = filter === 'all' ? `${API_BASE}/api/admin/users` : `${API_BASE}/api/admin/users?status=${filter}`;
      const res = await fetch(url, { headers: getAuthHeaders() });
      if (res.ok) setUsers(await res.json());
    } catch { }
    setLoading(false);
  };

  useEffect(() => { fetchUsers(); }, [filter]);

  const handleAction = async (uid: string, action: string) => {
    if (action === 'delete' && !confirm('确定要删除此用户？')) return;
    const method = action === 'delete' ? 'DELETE' : 'PUT';
    const url = action === 'delete'
      ? `${API_BASE}/api/admin/users/${uid}`
      : `${API_BASE}/api/admin/users/${uid}/${action}`;
    try {
      const res = await fetch(url, { method, headers: getAuthHeaders() });
      if (res.ok) fetchUsers();
      else {
        const err = await res.json().catch(() => null);
        alert(err?.detail || '操作失败');
      }
    } catch { alert('网络错误'); }
  };

  const statusBadge = (status: string) => {
    const map: Record<string, string> = {
      active: 'bg-green-100 text-green-700',
      pending: 'bg-amber-100 text-amber-700',
      disabled: 'bg-red-100 text-red-700',
    };
    const labels: Record<string, string> = {
      active: '正常', pending: '待审批', disabled: '已禁用',
    };
    return <span className={`px-2.5 py-0.5 rounded-full text-xs font-medium ${map[status] || 'bg-gray-100 text-gray-600'}`}>{labels[status] || status}</span>;
  };

  const pendingCount = users.filter(u => u.status === 'pending').length;

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <div>
          <h2 className="text-xl font-bold text-gray-800">用户管理</h2>
          <p className="text-sm text-gray-500 mt-1">共 {users.length} 个用户{pendingCount > 0 && <span className="text-amber-600 font-medium">，{pendingCount} 个待审批</span>}</p>
        </div>
        <div className="flex gap-2">
          {['all', 'pending', 'active', 'disabled'].map(f => (
            <button
              key={f}
              onClick={() => setFilter(f)}
              className={`px-3 py-1.5 text-xs font-medium rounded-lg transition-colors ${filter === f ? 'bg-indigo-100 text-indigo-700' : 'bg-gray-100 text-gray-600 hover:bg-gray-200'}`}
            >
              {{ all: '全部', pending: '待审批', active: '正常', disabled: '已禁用' }[f]}
            </button>
          ))}
        </div>
      </div>

      {loading ? (
        <div className="flex justify-center py-12"><Loader2 className="w-6 h-6 animate-spin text-gray-400" /></div>
      ) : (
        <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-gray-50 border-b border-gray-200">
              <tr>
                <th className="text-left px-4 py-3 font-medium text-gray-600">用户名</th>
                <th className="text-left px-4 py-3 font-medium text-gray-600">登录名</th>
                <th className="text-left px-4 py-3 font-medium text-gray-600">邮箱</th>
                <th className="text-left px-4 py-3 font-medium text-gray-600">公司</th>
                <th className="text-left px-4 py-3 font-medium text-gray-600">状态</th>
                <th className="text-left px-4 py-3 font-medium text-gray-600">角色</th>
                <th className="text-left px-4 py-3 font-medium text-gray-600">注册时间</th>
                <th className="text-right px-4 py-3 font-medium text-gray-600">操作</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {users.map(u => (
                <tr key={u.id} className={`hover:bg-gray-50 ${u.status === 'pending' ? 'bg-amber-50/50' : ''}`}>
                  <td className="px-4 py-3 font-medium text-gray-900">{u.username}</td>
                  <td className="px-4 py-3 text-gray-600">{u.login_name}</td>
                  <td className="px-4 py-3 text-gray-600">{u.email}</td>
                  <td className="px-4 py-3 text-gray-500">{u.company || '-'}</td>
                  <td className="px-4 py-3">{statusBadge(u.status)}</td>
                  <td className="px-4 py-3 text-gray-500">{u.role === 'admin' ? '管理员' : '用户'}</td>
                  <td className="px-4 py-3 text-gray-400 text-xs">{new Date(u.created_at).toLocaleDateString()}</td>
                  <td className="px-4 py-3 text-right">
                    <div className="flex items-center justify-end gap-1">
                      {u.status === 'pending' && (
                        <button onClick={() => handleAction(u.id, 'approve')} className="p-1.5 text-green-600 hover:bg-green-50 rounded-lg" title="审批通过">
                          <UserCheck className="w-4 h-4" />
                        </button>
                      )}
                      {u.status === 'active' && u.role !== 'admin' && (
                        <button onClick={() => handleAction(u.id, 'disable')} className="p-1.5 text-amber-600 hover:bg-amber-50 rounded-lg" title="禁用">
                          <UserX className="w-4 h-4" />
                        </button>
                      )}
                      {u.status === 'disabled' && (
                        <button onClick={() => handleAction(u.id, 'enable')} className="p-1.5 text-blue-600 hover:bg-blue-50 rounded-lg" title="启用">
                          <CheckCircle className="w-4 h-4" />
                        </button>
                      )}
                      {u.role !== 'admin' && (
                        <button onClick={(e) => { e.stopPropagation(); handleAction(u.id, 'delete'); }} className="p-1.5 text-red-500 hover:bg-red-50 rounded-lg" title="删除">
                          <Trash2 className="w-4 h-4" />
                        </button>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {users.length === 0 && <div className="text-center py-8 text-gray-400">暂无用户数据</div>}
        </div>
      )}
    </div>
  );
}
