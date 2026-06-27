import { useState, useEffect } from 'react';
import { useAuthStore } from '../../store/authStore';
import { CheckCircle, Trash2, Loader2, UserCheck, UserX, Edit, X } from 'lucide-react';

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

  const [editingUser, setEditingUser] = useState<UserItem | null>(null);
  const [editUsername, setEditUsername] = useState('');
  const [editEmail, setEditEmail] = useState('');
  const [editRole, setEditRole] = useState('user');
  const [editCompany, setEditCompany] = useState('');
  const [editDepartment, setEditDepartment] = useState('');
  const [editSaving, setEditSaving] = useState(false);

  const handleEditClick = (u: UserItem) => {
    setEditingUser(u);
    setEditUsername(u.username || '');
    setEditEmail(u.email || '');
    setEditRole(u.role || 'user');
    setEditCompany(u.company || '');
    setEditDepartment(u.department || '');
  };

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

  const handleSaveEdit = async () => {
    if (!editingUser) return;
    setEditSaving(true);
    try {
      const res = await fetch(`${API_BASE}/api/admin/users/${editingUser.id}`, {
        method: 'PUT',
        headers: { ...getAuthHeaders(), 'Content-Type': 'application/json' },
        body: JSON.stringify({
          username: editUsername,
          email: editEmail,
          role: editRole,
          company: editCompany,
          department: editDepartment
        })
      });
      if (res.ok) {
        setEditingUser(null);
        fetchUsers();
      } else {
        const err = await res.json().catch(() => null);
        alert(err?.detail || '修改失败');
      }
    } catch {
      alert('网络错误');
    }
    setEditSaving(false);
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
                      <button onClick={() => handleEditClick(u)} className="p-1.5 text-indigo-600 hover:bg-indigo-50 rounded-lg" title="编辑">
                        <Edit className="w-4 h-4" />
                      </button>
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

      {/* 编辑用户弹窗 Modal */}
      {editingUser && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/45 backdrop-blur-sm p-4 animate-in fade-in duration-200">
          <div className="bg-white rounded-2xl shadow-xl w-full max-w-md flex flex-col overflow-hidden border border-gray-100 animate-in zoom-in-95 duration-200">
            <div className="flex items-center justify-between px-5 py-4 border-b border-gray-100 bg-gray-50/50">
              <span className="text-sm font-bold text-gray-800 flex items-center gap-1.5">
                📝 编辑用户属性 ({editingUser.login_name})
              </span>
              <button 
                onClick={() => setEditingUser(null)}
                className="p-1.5 text-gray-400 hover:text-gray-600 hover:bg-gray-100 rounded-lg transition-colors"
              >
                <X className="w-4 h-4" />
              </button>
            </div>
            
            <div className="p-5 space-y-4 text-xs">
              <div>
                <label className="block text-gray-500 mb-1 font-semibold">用户名</label>
                <input
                  type="text"
                  value={editUsername}
                  onChange={e => setEditUsername(e.target.value)}
                  className="w-full px-3 py-2 border border-gray-200 rounded-lg focus:ring-1 focus:ring-indigo-500 focus:border-transparent outline-none text-gray-800"
                  placeholder="请输入用户名"
                />
              </div>

              <div>
                <label className="block text-gray-500 mb-1 font-semibold">电子邮箱</label>
                <input
                  type="email"
                  value={editEmail}
                  onChange={e => setEditEmail(e.target.value)}
                  className="w-full px-3 py-2 border border-gray-200 rounded-lg focus:ring-1 focus:ring-indigo-500 focus:border-transparent outline-none text-gray-800"
                  placeholder="请输入电子邮箱"
                />
              </div>

              <div>
                <label className="block text-gray-500 mb-1 font-semibold">公司名称</label>
                <input
                  type="text"
                  value={editCompany}
                  onChange={e => setEditCompany(e.target.value)}
                  className="w-full px-3 py-2 border border-gray-200 rounded-lg focus:ring-1 focus:ring-indigo-500 focus:border-transparent outline-none text-gray-800"
                  placeholder="请输入所属公司"
                />
              </div>

              <div>
                <label className="block text-gray-500 mb-1 font-semibold">部门名称</label>
                <input
                  type="text"
                  value={editDepartment}
                  onChange={e => setEditDepartment(e.target.value)}
                  className="w-full px-3 py-2 border border-gray-200 rounded-lg focus:ring-1 focus:ring-indigo-500 focus:border-transparent outline-none text-gray-800"
                  placeholder="请输入所属部门"
                />
              </div>

              <div>
                <label className="block text-gray-500 mb-1 font-semibold">用户角色</label>
                <select
                  value={editRole}
                  onChange={e => setEditRole(e.target.value)}
                  className="w-full px-3 py-2 border border-gray-200 rounded-lg focus:ring-1 focus:ring-indigo-500 focus:border-transparent bg-white outline-none text-gray-800 cursor-pointer font-medium"
                >
                  <option value="user">普通用户</option>
                  <option value="admin">系统管理员</option>
                </select>
              </div>
            </div>
            
            <div className="px-5 py-3.5 border-t border-gray-100 bg-gray-50 flex justify-end gap-2.5">
              <button
                onClick={() => setEditingUser(null)}
                className="px-3.5 py-2 text-xs font-semibold text-gray-600 bg-white border border-gray-200 rounded-lg hover:bg-gray-50 transition-colors shadow-sm"
              >
                取消
              </button>
              <button
                onClick={handleSaveEdit}
                disabled={editSaving}
                className="px-3.5 py-2 text-xs font-semibold text-white bg-indigo-500 hover:bg-indigo-600 disabled:opacity-50 rounded-lg transition-colors shadow-sm flex items-center gap-1.5"
              >
                {editSaving ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : null}
                保存更改
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
