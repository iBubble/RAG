import { useState, useEffect } from 'react';
import { useAuthStore } from '../../store/authStore';
import { useProjectStore } from '../../store/projectStore';
import { Loader2, Save, RefreshCw, Zap, Leaf, PauseCircle } from 'lucide-react';
import LogoSpinner from '../LogoSpinner';

const API_BASE = import.meta.env.VITE_API_BASE || '';

export default function SystemSettings() {
  const { getAuthHeaders } = useAuthStore();
  const selectedModel = useProjectStore(state => state.selectedModel);
  const setSelectedModel = useProjectStore(state => state.setSelectedModel);
  const [systemName, setSystemName] = useState('');
  const [adminLoginName, setAdminLoginName] = useState('');
  const [adminPassword, setAdminPassword] = useState('');
  const [heartbeatEnabled, setHeartbeatEnabled] = useState(true);
  const [systemRunMode, setSystemRunMode] = useState('full');
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [unloading, setUnloading] = useState(false);
  const [message, setMessage] = useState('');
  // 模型切换相关状态
  const [availableModels, setAvailableModels] = useState<{name:string; size_gb:number; parameter_size:string; quantization_level?:string}[]>([]);
  const [stagingModel, setStagingModel] = useState(selectedModel);
  const [switching, setSwitching] = useState(false);
  const [modelMessage, setModelMessage] = useState('');

  useEffect(() => {
    const fetchSettings = async () => {
      try {
        const res = await fetch(`${API_BASE}/api/admin/settings`, { headers: getAuthHeaders() });
        if (res.ok) {
          const data = await res.json();
          setSystemName(data.system_name || '');
          setHeartbeatEnabled(data.heartbeat_enabled !== false);
          setSystemRunMode(data.system_run_mode || 'full');
        }
      } catch { }
      setLoading(false);
    };
    fetchSettings();
  }, []);

  // 加载 Ollama 可用模型列表
  useEffect(() => {
    const fetchModels = async () => {
      try {
        const res = await fetch(`${API_BASE}/api/llm/status`, { headers: getAuthHeaders() });
        if (res.ok) {
          const data = await res.json();
          if (data.status === 'online' && Array.isArray(data.models)) {
            const qwenModels = data.models.filter((m: any) =>
              m.name.toLowerCase().includes('qwen3.6')
            );
            setAvailableModels(qwenModels);
          }
        }
      } catch { }
    };
    fetchModels();
  }, [switching]); // 切换完成后重新加载

  const handleModelSwitch = async () => {
    if (stagingModel === selectedModel || switching) return;
    setSwitching(true);
    setModelMessage('');
    try {
      const res = await fetch(`${API_BASE}/api/llm/switch`, {
        method: 'POST',
        headers: { ...getAuthHeaders(), 'Content-Type': 'application/json' },
        body: JSON.stringify({ new_model: stagingModel, previous_model: selectedModel }),
      });
      if (!res.ok) throw new Error('切换失败');
      setSelectedModel(stagingModel);
      setModelMessage('模型切换成功');
    } catch {
      setModelMessage('模型切换失败，请检查 Ollama 服务');
    }
    setSwitching(false);
    setTimeout(() => setModelMessage(''), 4000);
  };

  const handleSave = async () => {
    setSaving(true);
    setMessage('');
    try {
      const body: Record<string, any> = {};
      if (systemName) body.system_name = systemName;
      if (adminLoginName) body.admin_login_name = adminLoginName;
      if (adminPassword) body.admin_password = adminPassword;
      body.heartbeat_enabled = heartbeatEnabled;
      body.system_run_mode = systemRunMode;
      
      const res = await fetch(`${API_BASE}/api/admin/settings`, {
        method: 'PUT',
        headers: { ...getAuthHeaders(), 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      if (res.ok) {
        setMessage('保存成功');
        setAdminPassword('');
        setAdminLoginName('');
      } else {
        const err = await res.json().catch(() => null);
        setMessage(err?.detail || '保存失败');
      }
    } catch { setMessage('网络错误'); }
    setSaving(false);
    setTimeout(() => setMessage(''), 3000);
  };

  const handleUnloadModel = async () => {
    setUnloading(true);
    setMessage('');
    try {
      const res = await fetch(`${API_BASE}/api/admin/llm/unload`, {
        method: 'POST',
        headers: getAuthHeaders(),
      });
      if (res.ok) {
        setMessage('大模型已从显存中卸载');
      } else {
        const err = await res.json().catch(() => null);
        setMessage(err?.detail || '释放显存失败');
      }
    } catch {
      setMessage('网络错误');
    }
    setUnloading(false);
    setTimeout(() => setMessage(''), 3000);
  };

  if (loading) return <LogoSpinner size={72} overlay={false} />;

  return (
    <div>
      <h2 className="text-xl font-bold text-gray-800 mb-6">系统设置</h2>

      <div className="bg-white rounded-xl border border-gray-200 p-6 space-y-6 max-w-lg">
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1.5">系统名称</label>
          <input
            type="text"
            value={systemName}
            onChange={e => setSystemName(e.target.value)}
            className="w-full px-4 py-2.5 border border-gray-200 rounded-xl focus:ring-2 focus:ring-indigo-500 focus:border-transparent outline-none text-sm"
            placeholder="系统显示名称"
          />
          <p className="text-xs text-gray-400 mt-1">修改后会显示在登录页标题</p>
        </div>

        <hr className="border-gray-100" />

        {/* 大模型选择与切换 */}
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1.5">推理模型选择</label>
          <p className="text-xs text-gray-400 mb-3">
            选择用于对话和文档生成的大语言模型。Q4 量化速度更快、显存占用更小；Q5 量化精度更高。
          </p>
          <div className="flex items-center gap-3">
            <select
              value={stagingModel}
              onChange={e => setStagingModel(e.target.value)}
              disabled={switching}
              className="flex-1 px-4 py-2.5 border border-gray-200 rounded-xl focus:ring-2 focus:ring-indigo-500 focus:border-transparent outline-none text-sm disabled:opacity-50 bg-white"
            >
              {availableModels.length > 0 ? (
                availableModels.map(m => (
                  <option key={m.name} value={m.name}>
                    {m.name} ({m.size_gb}GB, {m.parameter_size})
                  </option>
                ))
              ) : (
                <option value={selectedModel}>{selectedModel}</option>
              )}
            </select>
            {stagingModel !== selectedModel && (
              <button
                onClick={handleModelSwitch}
                disabled={switching}
                className="px-4 py-2.5 bg-blue-500 text-white font-medium rounded-xl hover:bg-blue-600 transition-colors disabled:opacity-50 flex items-center gap-2 whitespace-nowrap"
              >
                {switching ? <Loader2 className="w-4 h-4 animate-spin" /> : <RefreshCw className="w-4 h-4" />}
                {switching ? '切换中...' : '切换模型'}
              </button>
            )}
          </div>
          <div className="mt-2 flex items-center gap-2">
            <span className="text-xs text-gray-400">当前使用：</span>
            <span className="text-xs font-semibold text-indigo-600 bg-indigo-50 px-2 py-0.5 rounded-md">{selectedModel}</span>
            {modelMessage && (
              <span className={`text-xs font-medium ${modelMessage.includes('成功') ? 'text-green-600' : 'text-red-500'}`}>
                {modelMessage}
              </span>
            )}
          </div>
        </div>

        <hr className="border-gray-100" />

        {/* 系统运行模式与资源控制 */}
        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1.5">系统运行模式（后台资源开关）</label>
          <p className="text-xs text-gray-400 mb-3 leading-relaxed">
            设定此演示工作电脑上后台任务的算力配比。完全挂起模式下仅保留核心的 Web 查询服务，不占用多余算力。
          </p>
          <div className="grid grid-cols-1 gap-3">
            {/* 全速模式 */}
            <div
              onClick={() => setSystemRunMode('full')}
              className={`p-3.5 rounded-xl border-2 cursor-pointer transition-all duration-200 hover:shadow-sm ${
                systemRunMode === 'full'
                  ? 'border-indigo-500 bg-indigo-50/20 ring-1 ring-indigo-500/50'
                  : 'border-gray-200 hover:border-indigo-200 hover:bg-gray-50/20'
              }`}
            >
              <div className="flex items-center gap-2 mb-1">
                <Zap className={`w-4 h-4 ${systemRunMode === 'full' ? 'text-indigo-600' : 'text-gray-400'}`} />
                <span className="text-sm font-semibold text-gray-800">全速学习模式 (Full Speed)</span>
              </div>
              <p className="text-xs text-gray-500 pl-6 leading-relaxed">
                同时启用文本向量化与知识图谱构建。本地大模型保持常驻并满负荷运行，以最快速度完成所有法律文档的学习。
              </p>
            </div>

            {/* 节能模式 */}
            <div
              onClick={() => setSystemRunMode('vector_only')}
              className={`p-3.5 rounded-xl border-2 cursor-pointer transition-all duration-200 hover:shadow-sm ${
                systemRunMode === 'vector_only'
                  ? 'border-amber-500 bg-amber-50/20 ring-1 ring-amber-500/50'
                  : 'border-gray-200 hover:border-amber-200 hover:bg-gray-50/20'
              }`}
            >
              <div className="flex items-center gap-2 mb-1">
                <Leaf className={`w-4 h-4 ${systemRunMode === 'vector_only' ? 'text-amber-600' : 'text-gray-400'}`} />
                <span className="text-sm font-semibold text-gray-800">节能运行模式 (Vector Only)</span>
              </div>
              <p className="text-xs text-gray-500 pl-6 leading-relaxed">
                仅启用轻量级文件切片与向量化。图谱提取挂起，并自动卸载大模型以**释放全部 23GB 显存**，适合日常办公时使用。
              </p>
            </div>

            {/* 完全挂起 */}
            <div
              onClick={() => setSystemRunMode('suspended')}
              className={`p-3.5 rounded-xl border-2 cursor-pointer transition-all duration-200 hover:shadow-sm ${
                systemRunMode === 'suspended'
                  ? 'border-rose-500 bg-rose-50/20 ring-1 ring-rose-500/50'
                  : 'border-gray-200 hover:border-rose-200 hover:bg-gray-50/20'
              }`}
            >
              <div className="flex items-center gap-2 mb-1">
                <PauseCircle className={`w-4 h-4 ${systemRunMode === 'suspended' ? 'text-rose-600' : 'text-gray-400'}`} />
                <span className="text-sm font-semibold text-gray-800">完全挂起模式 (Suspended)</span>
              </div>
              <p className="text-xs text-gray-500 pl-6 leading-relaxed">
                完全停止所有后台的导入和学习任务，卸载大模型，保持 0% 背景 CPU 占用。**仅保持 Web 页面和 API 接口最低限度常驻**以供普通查询。
              </p>
            </div>
          </div>
        </div>

        <hr className="border-gray-100" />

        <div className="flex items-center justify-between">
          <div className="pr-4">
            <label className="block text-sm font-medium text-gray-700">常驻大模型 (LLM Warmup)</label>
            <p className="text-xs text-gray-400 mt-1">
              开启时大模型常驻显存以实现秒级问答；关闭时大模型在空闲后会自动从显存中卸载以节省开发机器内存/显存资源（开发期间强烈建议关闭）。
            </p>
            <button
              onClick={handleUnloadModel}
              disabled={unloading}
              className="mt-3 px-3 py-1.5 bg-rose-50 hover:bg-rose-100/80 active:bg-rose-100 text-rose-600 disabled:opacity-50 text-xs font-semibold rounded-xl border border-rose-200/60 transition-all flex items-center gap-1.5 shadow-sm"
            >
              {unloading ? <Loader2 className="w-3 animate-spin" /> : null}
              手工停止大模型 (立即释放显存)
            </button>
          </div>
          <button
            onClick={() => setHeartbeatEnabled(!heartbeatEnabled)}
            className={`relative inline-flex h-6 w-11 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:ring-offset-2 ${
              heartbeatEnabled ? 'bg-indigo-500' : 'bg-gray-200'
            }`}
          >
            <span
              className={`pointer-events-none inline-block h-5 w-5 transform rounded-full bg-white shadow ring-0 transition duration-200 ease-in-out ${
                heartbeatEnabled ? 'translate-x-5' : 'translate-x-0'
              }`}
            />
          </button>
        </div>

        <hr className="border-gray-100" />

        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1.5">修改管理员登录名</label>
          <input
            type="text"
            value={adminLoginName}
            onChange={e => setAdminLoginName(e.target.value)}
            className="w-full px-4 py-2.5 border border-gray-200 rounded-xl focus:ring-2 focus:ring-indigo-500 focus:border-transparent outline-none text-sm"
            placeholder="留空则不修改"
          />
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-700 mb-1.5">修改管理员密码</label>
          <input
            type="password"
            value={adminPassword}
            onChange={e => setAdminPassword(e.target.value)}
            className="w-full px-4 py-2.5 border border-gray-200 rounded-xl focus:ring-2 focus:ring-indigo-500 focus:border-transparent outline-none text-sm"
            placeholder="留空则不修改，至少 6 位"
          />
        </div>

        <div className="flex items-center gap-3">
          <button
            onClick={handleSave}
            disabled={saving}
            className="px-5 py-2.5 bg-indigo-500 text-white font-medium rounded-xl hover:bg-indigo-600 transition-colors disabled:opacity-50 flex items-center gap-2"
          >
            {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />}
            保存设置
          </button>
          {message && (
            <span className={`text-sm font-medium ${message === '保存成功' ? 'text-green-600' : 'text-red-500'}`}>
              {message}
            </span>
          )}
        </div>
      </div>
    </div>
  );
}
