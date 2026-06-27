import { useState, useEffect } from 'react';
import { useAuthStore } from '../../store/authStore';
import { Save, Loader2, CheckSquare, Square } from 'lucide-react';

const ALL_WB_ITEMS = [
  { id: 'total_projects', label: '进行中项目数' },
  { id: 'completed_percent', label: '总文件向量化率' },
  { id: 'total_chunks', label: '向量切片总数' },
  { id: 'total_entities', label: '图谱实体总数' },
  { id: 'queue_tasks', label: '队列任务深度' },
];

const ALL_AGENTS = [
  { id: 'chat', label: '智能前台接待 (Chat)' },
  { id: 'service', label: '企业管理顾问 (Service)' },
  { id: 'planner', label: 'Eino任务规划 (Planner)' },
  { id: 'checker', label: 'Eino定量校验 (Checker)' },
  { id: 'auditor', label: 'Eino定性审计 (Auditor)' },
  { id: 'precompute', label: '智能学习预计算' },
  { id: 'vectorizer', label: '后端向量化入库' },
  { id: 'graph', label: '知识图谱提炼' },
  { id: 'summary', label: '图谱社区摘要' },
];

export interface AgentCustomProp {
  name: string;
  gender: 'male' | 'female';
  avatar: 'ox' | 'horse' | 'human' | 'robot';
}

export default function LinvisSettings() {
  const { getAuthHeaders } = useAuthStore();
  const API_BASE = import.meta.env.VITE_API_BASE || '';

  const [linvisName, setLinvisName] = useState('麟维斯');
  const [activeLevel, setActiveLevel] = useState('low');
  const [wbItems, setWbItems] = useState<string[]>([]);
  const [agents, setAgents] = useState<string[]>([]);
  const [agentsCustom, setAgentsCustom] = useState<Record<string, AgentCustomProp>>({});
  
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [msg, setMsg] = useState('');

  useEffect(() => {
    const loadSettings = async () => {
      try {
        const res = await fetch(`${API_BASE}/api/admin/settings`, { headers: getAuthHeaders() });
        if (res.ok) {
          const d = await res.json();
          setLinvisName(d.linvis_name || '麟维斯');
          setActiveLevel(d.active_level || d.funny_level || 'low');
          setWbItems(d.whiteboard_items ? d.whiteboard_items.split(',') : []);
          setAgents(d.visible_agents ? d.visible_agents.split(',') : []);
          
          const custom: Record<string, AgentCustomProp> = {};
          ALL_AGENTS.forEach(a => {
            custom[a.id] = {
              name: d[`agent_${a.id}_name`] || '',
              gender: d[`agent_${a.id}_gender`] || 'male',
              avatar: d[`agent_${a.id}_avatar`] || 'horse'
            };
          });
          setAgentsCustom(custom);
        }
      } catch (e) {
        console.error(e);
      } finally {
        setLoading(false);
      }
    };
    loadSettings();
  }, []);

  const handleToggle = (id: string, list: string[], setList: (l: string[]) => void) => {
    if (list.includes(id)) {
      setList(list.filter(item => item !== id));
    } else {
      setList([...list, id]);
    }
  };

  const handleSave = async () => {
    setSaving(true);
    setMsg('');
    try {
      const res = await fetch(`${API_BASE}/api/admin/settings`, {
        method: 'PUT',
        headers: { ...getAuthHeaders(), 'Content-Type': 'application/json' },
        body: JSON.stringify({
          linvis_name: linvisName.trim(),
          active_level: activeLevel,
          funny_level: activeLevel, // 同时发送保证老版本兼容
          whiteboard_items: wbItems.join(','),
          visible_agents: agents.join(','),
          agents_custom: agentsCustom
        }),
      });
      if (res.ok) {
        setMsg('✅ 麟维斯看板配置已更新！');
      } else {
        setMsg('❌ 更新失败，请检查参数');
      }
    } catch {
      setMsg('❌ 网络连接异常');
    } finally {
      setSaving(false);
    }
  };

  if (loading) {
    return <div className="text-gray-500 py-6 text-sm">正在载入配置...</div>;
  }

  return (
    <div className="max-w-2xl bg-white border border-gray-200 rounded-2xl p-6 shadow-sm">
      <h2 className="text-lg font-bold text-gray-800 mb-6 flex items-center gap-2">⚙️ 可视化看板配置</h2>

      {msg && (
        <div className={`p-3 rounded-xl text-sm font-semibold mb-6 ${msg.startsWith('✅') ? 'bg-emerald-50 text-emerald-800' : 'bg-red-50 text-red-800'}`}>
          {msg}
        </div>
      )}

      <div className="space-y-6">
        <div>
          <label className="text-sm font-semibold text-gray-700 block mb-2">看板名称</label>
          <input
            type="text"
            value={linvisName}
            onChange={e => setLinvisName(e.target.value)}
            className="w-full px-4 py-2.5 bg-gray-50 border border-gray-200 rounded-xl focus:ring-2 focus:ring-indigo-200 focus:border-indigo-500 outline-none text-sm"
            placeholder="例如：麟维斯"
          />
        </div>

        <div>
          <label className="text-sm font-semibold text-gray-700 block mb-2">看板活跃程度</label>
          <select
            value={activeLevel}
            onChange={e => setActiveLevel(e.target.value)}
            className="px-4 py-2 bg-gray-50 border border-gray-200 rounded-xl focus:ring-2 focus:ring-indigo-200 focus:border-indigo-500 outline-none text-sm cursor-pointer"
          >
            <option value="low">低 (极度严谨 / 偶尔搞怪)</option>
            <option value="medium">中 (轻松有趣 / 经常搞怪)</option>
            <option value="high">高 (极度活跃 / 摸鱼狂欢)</option>
          </select>
        </div>

        <div>
          <label className="text-sm font-semibold text-gray-700 block mb-2">白板展示指标勾选</label>
          <div className="grid grid-cols-2 gap-3">
            {ALL_WB_ITEMS.map(item => {
              const checked = wbItems.includes(item.id);
              return (
                <button
                  key={item.id}
                  onClick={() => handleToggle(item.id, wbItems, setWbItems)}
                  className={`flex items-center gap-2 px-3 py-2 border rounded-xl text-left text-sm transition-all cursor-pointer ${
                    checked ? 'border-indigo-400 bg-indigo-50/30 text-indigo-800' : 'border-gray-200 text-gray-600 hover:bg-gray-50'
                  }`}
                >
                  {checked ? <CheckSquare className="w-4 h-4 text-indigo-600" /> : <Square className="w-4 h-4 text-gray-400" />}
                  <span>{item.label}</span>
                </button>
              );
            })}
          </div>
        </div>

        <div>
          <label className="text-sm font-semibold text-gray-700 block mb-2">看板可见 Agent 勾选</label>
          <div className="grid grid-cols-2 gap-3">
            {ALL_AGENTS.map(agent => {
              const checked = agents.includes(agent.id);
              return (
                <button
                  key={agent.id}
                  onClick={() => handleToggle(agent.id, agents, setAgents)}
                  className={`flex items-center gap-2 px-3 py-2 border rounded-xl text-left text-sm transition-all cursor-pointer ${
                    checked ? 'border-indigo-400 bg-indigo-50/30 text-indigo-800' : 'border-gray-200 text-gray-600 hover:bg-gray-50'
                  }`}
                >
                  {checked ? <CheckSquare className="w-4 h-4 text-indigo-600" /> : <Square className="w-4 h-4 text-gray-400" />}
                  <span>{agent.label}</span>
                </button>
              );
            })}
          </div>
        </div>

        <div>
          <label className="text-sm font-semibold text-gray-700 block mb-2.5">Agent 形象与个性配置</label>
          <div className="space-y-2.5 max-h-[300px] overflow-y-auto pr-1.5 border border-gray-100 rounded-2xl p-3 bg-gray-50/50">
            {ALL_AGENTS.map(agent => {
              const custom = agentsCustom[agent.id] || { name: '', gender: 'male', avatar: 'horse' };
              return (
                <div key={agent.id} className="bg-white p-3 rounded-xl border border-gray-100 shadow-sm flex flex-col sm:flex-row gap-3 items-center justify-between">
                  <span className="text-xs font-bold text-gray-700 w-28 shrink-0">{agent.label}</span>
                  <div className="flex flex-wrap gap-2 w-full justify-end">
                    <input
                      type="text"
                      value={custom.name}
                      onChange={e => {
                        setAgentsCustom({
                          ...agentsCustom,
                          [agent.id]: { ...custom, name: e.target.value }
                        });
                      }}
                      placeholder="修改名字"
                      className="px-2 py-1.5 border border-gray-200 rounded-lg text-xs w-28 focus:ring-1 focus:ring-indigo-300 outline-none"
                    />
                    <select
                      value={custom.gender}
                      onChange={e => {
                        setAgentsCustom({
                          ...agentsCustom,
                          [agent.id]: { ...custom, gender: e.target.value as any }
                        });
                      }}
                      className="px-2 py-1.5 border border-gray-200 rounded-lg text-xs focus:ring-1 focus:ring-indigo-300 outline-none cursor-pointer"
                    >
                      <option value="male">男 ♂</option>
                      <option value="female">女 ♀</option>
                    </select>
                    <select
                      value={custom.avatar}
                      onChange={e => {
                        setAgentsCustom({
                          ...agentsCustom,
                          [agent.id]: { ...custom, avatar: e.target.value as any }
                        });
                      }}
                      className="px-2 py-1.5 border border-gray-200 rounded-lg text-xs focus:ring-1 focus:ring-indigo-300 outline-none cursor-pointer"
                    >
                      <option value="horse">马 🐴</option>
                      <option value="ox">牛 🐮</option>
                      <option value="human">人 👤</option>
                      <option value="robot">机器人 🤖</option>
                    </select>
                  </div>
                </div>
              );
            })}
          </div>
        </div>

        <button
          onClick={handleSave}
          disabled={saving || !linvisName.trim()}
          className="flex items-center justify-center gap-2 w-full py-3 bg-indigo-600 hover:bg-indigo-700 disabled:opacity-50 text-white rounded-xl font-bold shadow-sm transition-all cursor-pointer mt-4"
        >
          {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />}
          <span>保存配置</span>
        </button>
      </div>
    </div>
  );
}
