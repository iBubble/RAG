import { useState, useEffect } from 'react';
import { useAuthStore } from '../../store/authStore';
import { Trash2, Loader2, Globe, Lock } from 'lucide-react';

const API_BASE = import.meta.env.VITE_API_BASE || '';

interface ProjectItem {
  id: string;
  name: string;
  owner_id?: string;
  owner_name?: string;
  visibility?: string;
  createdAt: string;
  sourceCount: number;
}

export default function ProjectManagement() {
  const { getAuthHeaders } = useAuthStore();
  const [projects, setProjects] = useState<ProjectItem[]>([]);
  const [loading, setLoading] = useState(true);

  const fetchProjects = async () => {
    setLoading(true);
    try {
      const res = await fetch(`${API_BASE}/api/admin/projects`, { headers: getAuthHeaders() });
      if (res.ok) setProjects(await res.json());
    } catch { }
    setLoading(false);
  };

  useEffect(() => { fetchProjects(); }, []);

  const toggleVisibility = async (pid: string, current: string) => {
    const newVis = current === 'private' ? 'public' : 'private';
    try {
      const res = await fetch(`${API_BASE}/api/admin/projects/${pid}`, {
        method: 'PUT',
        headers: { ...getAuthHeaders(), 'Content-Type': 'application/json' },
        body: JSON.stringify({ visibility: newVis }),
      });
      if (res.ok) fetchProjects();
    } catch { }
  };

  const deleteProject = async (pid: string, name: string) => {
    if (!confirm(`确定要彻底删除项目「${name}」及其所有数据？`)) return;
    try {
      const res = await fetch(`${API_BASE}/api/admin/projects/${pid}`, {
        method: 'DELETE',
        headers: getAuthHeaders(),
      });
      if (res.ok) fetchProjects();
      else {
        const err = await res.json().catch(() => null);
        alert(err?.detail || '删除失败');
      }
    } catch { alert('网络错误'); }
  };

  return (
    <div>
      <div className="mb-6">
        <h2 className="text-xl font-bold text-gray-800">项目管理</h2>
        <p className="text-sm text-gray-500 mt-1">共 {projects.length} 个项目</p>
      </div>

      {loading ? (
        <div className="flex justify-center py-12"><Loader2 className="w-6 h-6 animate-spin text-gray-400" /></div>
      ) : (
        <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-gray-50 border-b border-gray-200">
              <tr>
                <th className="text-left px-4 py-3 font-medium text-gray-600">项目名称</th>
                <th className="text-left px-4 py-3 font-medium text-gray-600">所有者</th>
                <th className="text-left px-4 py-3 font-medium text-gray-600">可见性</th>
                <th className="text-left px-4 py-3 font-medium text-gray-600">创建时间</th>
                <th className="text-right px-4 py-3 font-medium text-gray-600">操作</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {projects.map(p => (
                <tr key={p.id} className="hover:bg-gray-50">
                  <td className="px-4 py-3 font-medium text-gray-900">{p.name}</td>
                  <td className="px-4 py-3 text-gray-600">{p.owner_name || '未知'}</td>
                  <td className="px-4 py-3">
                    <button
                      onClick={() => toggleVisibility(p.id, p.visibility || 'public')}
                      className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium transition-colors cursor-pointer ${
                        p.visibility === 'private'
                          ? 'bg-orange-100 text-orange-700 hover:bg-orange-200'
                          : 'bg-green-100 text-green-700 hover:bg-green-200'
                      }`}
                    >
                      {p.visibility === 'private' ? <><Lock className="w-3 h-3" /> 私有</> : <><Globe className="w-3 h-3" /> 公开</>}
                    </button>
                  </td>
                  <td className="px-4 py-3 text-gray-400 text-xs">{new Date(p.createdAt).toLocaleDateString()}</td>
                  <td className="px-4 py-3 text-right">
                    <button onClick={(e) => { e.stopPropagation(); deleteProject(p.id, p.name); }} className="p-1.5 text-red-500 hover:bg-red-50 rounded-lg" title="删除项目">
                      <Trash2 className="w-4 h-4" />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          {projects.length === 0 && <div className="text-center py-8 text-gray-400">暂无项目</div>}
        </div>
      )}
    </div>
  );
}
