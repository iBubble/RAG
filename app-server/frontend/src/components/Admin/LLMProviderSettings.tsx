import { useState, useEffect } from 'react';
import { useAuthStore } from '../../store/authStore';
import { Bot, Eye, Loader2, CheckCircle2, AlertCircle, EyeOff, Save, Activity, RefreshCw, ListFilter, Edit3 } from 'lucide-react';
import LogoSpinner from '../LogoSpinner';

const API_BASE = import.meta.env.VITE_API_BASE || '';

interface ProviderConfig {
  baseURL: string;
  apiKey: string;
  model: string;
  timeoutSeconds: number;
}


const PRESET_PROVIDERS = [
  'DeepSeek-R1 (离线规则研判内置引擎)',
  '通用 兼容 Gateway',
  'Ollama 本地私有化部署'
];

const PRESET_VISION_PROVIDERS = [
  '通用 兼容 Gateway',
  'Ollama 本地私有化部署'
];

export default function LLMProviderSettings() {
  const { getAuthHeaders } = useAuthStore();
  const [loading, setLoading] = useState(true);
  
  // 主力大模型状态
  const [activeProvider, setActiveProvider] = useState<string>('通用 兼容 Gateway');
  const [providers, setProviders] = useState<Record<string, ProviderConfig>>({
    'DeepSeek-R1 (离线规则研判内置引擎)': {
      baseURL: 'https://deepseek-api2.pages.dev/v1',
      apiKey: 'EMPTY',
      model: 'deepseek-r1',
      timeoutSeconds: 300
    },
    '通用 兼容 Gateway': {
      baseURL: 'http://40dd.shop:8001/v1',
      apiKey: 'EMPTY',
      model: 'qwen38-27b-q4',
      timeoutSeconds: 300
    },
    'Ollama 本地私有化部署': {
      baseURL: 'http://host.docker.internal:11434',
      apiKey: '',
      model: 'qwen3.8:27b-q4',
      timeoutSeconds: 180
    }
  });
  const [mainShowKey, setMainShowKey] = useState(false);
  const [mainSaving, setMainSaving] = useState(false);
  const [mainTesting, setMainTesting] = useState(false);
  const [mainTestResult, setMainTestResult] = useState<{ success: boolean; msg: string } | null>(null);
  
  // 主力模型动态读取列表
  const [mainModelList, setMainModelList] = useState<string[]>([]);
  const [mainFetchingModels, setMainFetchingModels] = useState(false);
  const [mainModelFetchMsg, setMainModelFetchMsg] = useState<{ success: boolean; msg: string } | null>(null);
  const [mainManualInput, setMainManualInput] = useState(false);

  // 多模态视觉模型状态（支持多服务商独立配置切换）
  const [visionMode, setVisionMode] = useState<'same_as_main' | 'standalone'>('standalone');
  const [activeVisionProvider, setActiveVisionProvider] = useState<string>('通用 兼容 Gateway');
  const [visionProviders, setVisionProviders] = useState<Record<string, ProviderConfig>>({
    '通用 兼容 Gateway': {
      baseURL: 'http://40dd.shop:8000/v1',
      apiKey: 'EMPTY',
      model: 'qwen3-vl-32b-awq',
      timeoutSeconds: 300
    },
    'Ollama 本地私有化部署': {
      baseURL: 'http://host.docker.internal:11434',
      apiKey: '',
      model: 'qwen2.5vl:7b',
      timeoutSeconds: 180
    }
  });
  const [visionShowKey, setVisionShowKey] = useState(false);
  const [visionSaving, setVisionSaving] = useState(false);
  const [visionTesting, setVisionTesting] = useState(false);
  const [visionTestResult, setVisionTestResult] = useState<{ success: boolean; msg: string } | null>(null);

  // 视觉模型动态读取列表
  const [visionModelList, setVisionModelList] = useState<string[]>([]);
  const [visionFetchingModels, setVisionFetchingModels] = useState(false);
  const [visionModelFetchMsg, setVisionModelFetchMsg] = useState<{ success: boolean; msg: string } | null>(null);
  const [visionManualInput, setVisionManualInput] = useState(false);

  // 加载已保存的配置
  useEffect(() => {
    const fetchConfig = async () => {
      try {
        const res = await fetch(`${API_BASE}/api/admin/llm/providers`, { headers: getAuthHeaders() });
        if (res.ok) {
          const data = await res.json();
          if (data.llm) {
            setActiveProvider(data.llm.active_provider || '通用 兼容 Gateway');
            if (data.llm.providers) {
              setProviders(prev => ({ ...prev, ...data.llm.providers }));
            }
          }
          if (data.vision) {
            setVisionMode(data.vision.mode || 'standalone');
            if (data.vision.active_provider) {
              setActiveVisionProvider(data.vision.active_provider);
            }
            if (data.vision.providers) {
              setVisionProviders(prev => ({ ...prev, ...data.vision.providers }));
            } else if (data.vision.baseURL) {
              const prov = data.vision.provider || '通用 兼容 Gateway';
              setVisionProviders(prev => ({
                ...prev,
                [prov]: {
                  baseURL: data.vision.baseURL,
                  apiKey: data.vision.apiKey || '',
                  model: data.vision.model,
                  timeoutSeconds: data.vision.timeoutSeconds || 300
                }
              }));
            }
          }
        }
      } catch (err) {
        console.error('加载LLM配置失败', err);
      } finally {
        setLoading(false);
      }
    };
    fetchConfig();
  }, []);

  const currentMainConfig = providers[activeProvider] || {
    baseURL: '',
    apiKey: '',
    model: '',
    timeoutSeconds: 300
  };

  const handleMainFieldChange = (field: keyof ProviderConfig, value: any) => {
    setProviders(prev => ({
      ...prev,
      [activeProvider]: {
        ...prev[activeProvider],
        [field]: value
      }
    }));
  };

  const currentVisionConfig = visionProviders[activeVisionProvider] || {
    baseURL: '',
    apiKey: '',
    model: '',
    timeoutSeconds: 300
  };

  const handleVisionFieldChange = (field: keyof ProviderConfig, value: any) => {
    setVisionProviders(prev => ({
      ...prev,
      [activeVisionProvider]: {
        ...prev[activeVisionProvider],
        [field]: value
      }
    }));
  };

  // 动态拉取主力模型列表
  const handleFetchMainModels = async () => {
    if (!currentMainConfig.baseURL) {
      setMainModelFetchMsg({ success: false, msg: '请先填写 API 服务端点 URL' });
      return;
    }
    setMainFetchingModels(true);
    setMainModelFetchMsg(null);
    try {
      const res = await fetch(`${API_BASE}/api/admin/llm/remote-models`, {
        method: 'POST',
        headers: { ...getAuthHeaders(), 'Content-Type': 'application/json' },
        body: JSON.stringify({
          baseURL: currentMainConfig.baseURL,
          apiKey: currentMainConfig.apiKey
        })
      });
      const data = await res.json();
      if (res.ok && data.success && data.models && data.models.length > 0) {
        setMainModelList(data.models);
        setMainManualInput(false);
        setMainModelFetchMsg({ success: true, msg: `成功从 API 读取到 ${data.models.length} 个可用模型` });
        if (!currentMainConfig.model || !data.models.includes(currentMainConfig.model)) {
          handleMainFieldChange('model', data.models[0]);
        }
      } else {
        setMainModelFetchMsg({ success: false, msg: data.message || '未获取到模型' });
      }
    } catch {
      setMainModelFetchMsg({ success: false, msg: '网络异常，无法获取模型列表' });
    } finally {
      setMainFetchingModels(false);
    }
  };

  const handleSaveMain = async () => {
    setMainSaving(true);
    setMainTestResult(null);
    try {
      const res = await fetch(`${API_BASE}/api/admin/llm/providers`, {
        method: 'POST',
        headers: { ...getAuthHeaders(), 'Content-Type': 'application/json' },
        body: JSON.stringify({ active_provider: activeProvider, providers })
      });
      const data = await res.json();
      if (res.ok && data.success) {
        setMainTestResult({ success: true, msg: '主力大模型配置保存成功并已立即生效' });
      } else {
        setMainTestResult({ success: false, msg: data.message || '保存失败' });
      }
    } catch {
      setMainTestResult({ success: false, msg: '网络错误，保存失败' });
    } finally {
      setMainSaving(false);
    }
  };

  const handleTestMain = async () => {
    setMainTesting(true);
    setMainTestResult(null);
    try {
      const res = await fetch(`${API_BASE}/api/admin/llm/test-connection`, {
        method: 'POST',
        headers: { ...getAuthHeaders(), 'Content-Type': 'application/json' },
        body: JSON.stringify({
          baseURL: currentMainConfig.baseURL,
          apiKey: currentMainConfig.apiKey,
          model: currentMainConfig.model,
          is_vision: false
        })
      });
      const data = await res.json();
      if (res.ok && data.success) {
        setMainTestResult({ success: true, msg: `连通成功！${data.message} (延迟: ${data.latency_ms}ms)` });
      } else {
        setMainTestResult({ success: false, msg: `连接失败: ${data.message || '未知错误'}` });
      }
    } catch (e: any) {
      setMainTestResult({ success: false, msg: `网络异常: ${e.message}` });
    } finally {
      setMainTesting(false);
    }
  };

  // 动态拉取视觉模型列表
  const handleFetchVisionModels = async () => {
    const targetURL = visionMode === 'same_as_main' ? currentMainConfig.baseURL : currentVisionConfig.baseURL;
    const targetKey = visionMode === 'same_as_main' ? currentMainConfig.apiKey : currentVisionConfig.apiKey;
    if (!targetURL) {
      setVisionModelFetchMsg({ success: false, msg: '请先填写多模态服务端点 URL' });
      return;
    }
    setVisionFetchingModels(true);
    setVisionModelFetchMsg(null);
    try {
      const res = await fetch(`${API_BASE}/api/admin/llm/remote-models`, {
        method: 'POST',
        headers: { ...getAuthHeaders(), 'Content-Type': 'application/json' },
        body: JSON.stringify({
          baseURL: targetURL,
          apiKey: targetKey
        })
      });
      const data = await res.json();
      if (res.ok && data.success && data.models && data.models.length > 0) {
        setVisionModelList(data.models);
        setVisionManualInput(false);
        setVisionModelFetchMsg({ success: true, msg: `成功从 API 读取到 ${data.models.length} 个可用多模态模型` });
        if (visionMode === 'standalone') {
          if (!currentVisionConfig.model || !data.models.includes(currentVisionConfig.model)) {
            handleVisionFieldChange('model', data.models[0]);
          }
        }
      } else {
        setVisionModelFetchMsg({ success: false, msg: data.message || '未获取到模型' });
      }
    } catch {
      setVisionModelFetchMsg({ success: false, msg: '网络异常，无法获取模型列表' });
    } finally {
      setVisionFetchingModels(false);
    }
  };

  const handleSaveVision = async () => {
    setVisionSaving(true);
    setVisionTestResult(null);
    try {
      const payload = {
        mode: visionMode,
        active_provider: activeVisionProvider,
        providers: visionProviders,
        provider: activeVisionProvider,
        baseURL: currentVisionConfig.baseURL,
        apiKey: currentVisionConfig.apiKey,
        model: currentVisionConfig.model,
        timeoutSeconds: currentVisionConfig.timeoutSeconds
      };
      const res = await fetch(`${API_BASE}/api/admin/llm/vision-config`, {
        method: 'POST',
        headers: { ...getAuthHeaders(), 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });
      const data = await res.json();
      if (res.ok && data.success) {
        setVisionTestResult({ success: true, msg: '视觉识别多模态大模型配置已保存并生效' });
      } else {
        setVisionTestResult({ success: false, msg: data.message || '保存失败' });
      }
    } catch {
      setVisionTestResult({ success: false, msg: '网络错误，保存失败' });
    } finally {
      setVisionSaving(false);
    }
  };

  const handleTestVision = async () => {
    setVisionTesting(true);
    setVisionTestResult(null);
    try {
      const targetBaseURL = visionMode === 'same_as_main' ? currentMainConfig.baseURL : currentVisionConfig.baseURL;
      const targetApiKey = visionMode === 'same_as_main' ? currentMainConfig.apiKey : currentVisionConfig.apiKey;
      const targetModel = visionMode === 'same_as_main' ? currentMainConfig.model : currentVisionConfig.model;
      
      const res = await fetch(`${API_BASE}/api/admin/llm/test-connection`, {
        method: 'POST',
        headers: { ...getAuthHeaders(), 'Content-Type': 'application/json' },
        body: JSON.stringify({
          baseURL: targetBaseURL,
          apiKey: targetApiKey,
          model: targetModel,
          is_vision: true
        })
      });
      const data = await res.json();
      if (res.ok && data.success) {
        setVisionTestResult({ success: true, msg: `连通成功！${data.message} (延迟: ${data.latency_ms}ms)` });
      } else {
        setVisionTestResult({ success: false, msg: `连接失败: ${data.message || '未知错误'}` });
      }
    } catch (e: any) {
      setVisionTestResult({ success: false, msg: `网络异常: ${e.message}` });
    } finally {
      setVisionTesting(false);
    }
  };

  if (loading) return <LogoSpinner size={72} overlay={false} />;

  return (
    <div className="space-y-8 pb-16 max-w-4xl">
      {/* 顶部标题栏 */}
      <div>
        <h2 className="text-2xl font-bold text-gray-900 flex items-center gap-2">
          <span>🤖</span> 离线政务引擎 API 配置
        </h2>
        <p className="text-sm text-gray-500 mt-1">
          配置本地 DeepSeek / 规则引擎 Gateway 接口与密钥，多模型引擎服务商热切换
        </p>
      </div>

      {/* 1. 主力大模型 API 配置卡片 */}
      <div className="bg-white rounded-2xl border border-gray-200 shadow-sm p-7 space-y-6">
        <div className="flex items-center justify-between border-b border-gray-100 pb-4">
          <div className="flex items-center gap-2.5">
            <div className="p-2 rounded-xl bg-indigo-50 text-indigo-600">
              <Bot className="w-5 h-5" />
            </div>
            <div>
              <h3 className="text-base font-semibold text-gray-800">主力推理大模型 API 配置</h3>
              <p className="text-xs text-gray-400">负责案卷智能问答、法律裁量推演及报告生成的逻辑底座</p>
            </div>
          </div>
          <span className="text-xs font-semibold px-2.5 py-1 rounded-full bg-emerald-50 text-emerald-600 border border-emerald-200/60">
            活跃生效中
          </span>
        </div>

        {/* 模型引擎服务商下拉框 */}
        <div>
          <label className="block text-sm font-semibold text-gray-700 mb-2">模型引擎服务商</label>
          <select
            value={activeProvider}
            onChange={e => {
              setActiveProvider(e.target.value);
              setMainTestResult(null);
            }}
            className="w-full px-4 py-3 border border-gray-300 rounded-xl focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 outline-none text-sm bg-white font-medium shadow-sm transition-all"
          >
            {PRESET_PROVIDERS.map(p => (
              <option key={p} value={p}>{p}</option>
            ))}
          </select>
          <p className="text-xs text-gray-400 mt-1.5">
            切换不同服务商将自动调出并回填该服务商之前保存的专属端点与密钥配置
          </p>
        </div>

        {/* API 服务端点 (Endpoint URL) */}
        <div>
          <label className="block text-sm font-semibold text-gray-700 mb-2">API 服务端点 (Endpoint URL)</label>
          <div className="relative">
            <input
              type="text"
              value={currentMainConfig.baseURL}
              onChange={e => handleMainFieldChange('baseURL', e.target.value)}
              placeholder="例如: http://40dd.shop:8001/v1 或 http://host.docker.internal:11434"
              className="w-full px-4 py-3 border border-gray-300 rounded-xl focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 outline-none text-sm font-mono shadow-sm transition-all pr-12"
            />
            <div className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 text-xs px-1.5 py-0.5 rounded bg-gray-100 border border-gray-200">
              URL
            </div>
          </div>
        </div>

        {/* API Key 访问密钥 */}
        <div>
          <label className="block text-sm font-semibold text-gray-700 mb-2">API Key 访问密钥</label>
          <div className="relative">
            <input
              type={mainShowKey ? 'text' : 'password'}
              value={currentMainConfig.apiKey}
              onChange={e => handleMainFieldChange('apiKey', e.target.value)}
              placeholder="无密钥请填 EMPTY，或输入 sk-..."
              className="w-full px-4 py-3 border border-gray-300 rounded-xl focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 outline-none text-sm font-mono shadow-sm transition-all pr-12"
            />
            <button
              type="button"
              onClick={() => setMainShowKey(!mainShowKey)}
              className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600 p-1 rounded-lg transition-colors cursor-pointer"
            >
              {mainShowKey ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
            </button>
          </div>
        </div>

        {/* 选用的模型名称与超时时间 */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div className="md:col-span-2">
            <div className="flex items-center justify-between mb-2">
              <label className="text-sm font-semibold text-gray-700">选用的模型名称 (Model Name)</label>
              <div className="flex items-center space-x-2">
                {mainModelList.length > 0 && (
                  <button
                    type="button"
                    onClick={() => setMainManualInput(!mainManualInput)}
                    className="text-xs text-indigo-600 hover:text-indigo-800 font-medium flex items-center space-x-1 cursor-pointer transition-colors"
                  >
                    <Edit3 className="w-3 h-3" />
                    <span>{mainManualInput ? '切换为下拉选取' : '手动输入'}</span>
                  </button>
                )}
                <button
                  type="button"
                  onClick={handleFetchMainModels}
                  disabled={mainFetchingModels}
                  className="text-xs px-2.5 py-1 rounded-lg bg-indigo-50 hover:bg-indigo-100 text-indigo-700 border border-indigo-200/70 font-medium flex items-center space-x-1 cursor-pointer transition-all disabled:opacity-50"
                  title="从上方服务端点拉取可用模型列表"
                >
                  {mainFetchingModels ? (
                    <Loader2 className="w-3 h-3 animate-spin text-indigo-600" />
                  ) : (
                    <RefreshCw className="w-3 h-3 text-indigo-600" />
                  )}
                  <span>{mainFetchingModels ? '正在读取...' : '读取可用模型'}</span>
                </button>
              </div>
            </div>

            {mainModelList.length > 0 && !mainManualInput ? (
              <div className="relative">
                <select
                  value={currentMainConfig.model}
                  onChange={e => handleMainFieldChange('model', e.target.value)}
                  className="w-full px-4 py-3 border border-indigo-300 rounded-xl focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 outline-none text-sm font-mono bg-indigo-50/20 text-gray-800 shadow-sm transition-all cursor-pointer appearance-none pr-10"
                >
                  {currentMainConfig.model && !mainModelList.includes(currentMainConfig.model) && (
                    <option value={currentMainConfig.model}>{currentMainConfig.model} (当前保存)</option>
                  )}
                  {mainModelList.map(m => (
                    <option key={m} value={m}>{m}</option>
                  ))}
                </select>
                <div className="absolute right-3 top-1/2 -translate-y-1/2 pointer-events-none text-indigo-500">
                  <ListFilter className="w-4 h-4" />
                </div>
              </div>
            ) : (
              <input
                type="text"
                value={currentMainConfig.model}
                onChange={e => handleMainFieldChange('model', e.target.value)}
                placeholder="例如: qwen38-27b-q4, deepseek-r1"
                className="w-full px-4 py-3 border border-gray-300 rounded-xl focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 outline-none text-sm font-mono shadow-sm transition-all"
              />
            )}

            {mainModelFetchMsg && (
              <p className={`text-xs mt-1.5 flex items-center space-x-1 ${mainModelFetchMsg.success ? 'text-emerald-600' : 'text-amber-600'}`}>
                <span>{mainModelFetchMsg.success ? '✓' : 'ℹ'}</span>
                <span>{mainModelFetchMsg.msg}</span>
              </p>
            )}
          </div>
          <div>
            <label className="block text-sm font-semibold text-gray-700 mb-2">超时时间 (秒)</label>
            <input
              type="number"
              value={currentMainConfig.timeoutSeconds || 300}
              onChange={e => handleMainFieldChange('timeoutSeconds', parseInt(e.target.value) || 300)}
              className="w-full px-4 py-3 border border-gray-300 rounded-xl focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 outline-none text-sm font-mono shadow-sm transition-all"
            />
          </div>
        </div>

        {/* 测试反馈提示 */}
        {mainTestResult && (
          <div className={`p-3.5 rounded-xl border flex items-center gap-2.5 text-xs font-medium animate-in fade-in duration-200 ${
            mainTestResult.success 
              ? 'bg-emerald-50 border-emerald-200 text-emerald-700' 
              : 'bg-red-50 border-red-200 text-red-700'
          }`}>
            {mainTestResult.success ? <CheckCircle2 className="w-4 h-4 shrink-0" /> : <AlertCircle className="w-4 h-4 shrink-0" />}
            <span>{mainTestResult.msg}</span>
          </div>
        )}

        {/* 操作按钮组 */}
        <div className="flex items-center gap-3 pt-2">
          <button
            onClick={handleSaveMain}
            disabled={mainSaving}
            className="flex-1 px-6 py-3.5 bg-[#172554] hover:bg-[#1e3a8a] active:scale-[0.99] text-white font-semibold rounded-xl transition-all shadow-md flex items-center justify-center gap-2 disabled:opacity-50 cursor-pointer"
          >
            {mainSaving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />}
            <span>保存主力大模型配置</span>
          </button>
          <button
            onClick={handleTestMain}
            disabled={mainTesting}
            className="px-6 py-3.5 bg-white border border-gray-300 hover:bg-gray-50 active:scale-[0.99] text-gray-700 font-semibold rounded-xl transition-all shadow-sm flex items-center justify-center gap-2 disabled:opacity-50 cursor-pointer whitespace-nowrap"
          >
            {mainTesting ? <Loader2 className="w-4 h-4 animate-spin text-indigo-600" /> : <Activity className="w-4 h-4 text-indigo-600" />}
            <span>测试 Gateway 连通性</span>
          </button>
        </div>
      </div>

      {/* 2. 多模态视觉识别大模型独立配置卡片 */}
      <div className="bg-white rounded-2xl border border-gray-200 shadow-sm p-7 space-y-6">
        <div className="flex items-center justify-between border-b border-gray-100 pb-4">
          <div className="flex items-center gap-2.5">
            <div className="p-2 rounded-xl bg-purple-50 text-purple-600">
              <Eye className="w-5 h-5" />
            </div>
            <div>
              <h3 className="text-base font-semibold text-gray-800">多模态视觉识别大模型 API 配置 (Vision LLM)</h3>
              <p className="text-xs text-gray-400">负责工程 CAD 图纸、扫描件 OCR 增强、等值线图等视觉多模态理解</p>
            </div>
          </div>
          <span className="text-xs font-semibold px-2.5 py-1 rounded-full bg-purple-50 text-purple-600 border border-purple-200/60">
            {visionMode === 'same_as_main' ? '与主力同用' : '独立专用'}
          </span>
        </div>

        {/* 运行模式选择 */}
        <div>
          <label className="block text-sm font-semibold text-gray-700 mb-2">多模态引擎运行模式</label>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
            <label className={`flex items-center gap-3 p-3.5 rounded-xl border-2 cursor-pointer transition-all ${
              visionMode === 'same_as_main'
                ? 'border-purple-500 bg-purple-50/20 ring-1 ring-purple-500/30'
                : 'border-gray-200 hover:border-gray-300'
            }`}>
              <input
                type="radio"
                name="vision_mode"
                checked={visionMode === 'same_as_main'}
                onChange={() => setVisionMode('same_as_main')}
                className="w-4 h-4 text-purple-600 focus:ring-purple-500"
              />
              <div>
                <span className="text-sm font-semibold text-gray-800">与主力大模型同用</span>
                <p className="text-xs text-gray-400 mt-0.5">自动继承上方主力大模型的服务端口、密钥与模型</p>
              </div>
            </label>

            <label className={`flex items-center gap-3 p-3.5 rounded-xl border-2 cursor-pointer transition-all ${
              visionMode === 'standalone'
                ? 'border-purple-500 bg-purple-50/20 ring-1 ring-purple-500/30'
                : 'border-gray-200 hover:border-gray-300'
            }`}>
              <input
                type="radio"
                name="vision_mode"
                checked={visionMode === 'standalone'}
                onChange={() => setVisionMode('standalone')}
                className="w-4 h-4 text-purple-600 focus:ring-purple-500"
              />
              <div>
                <span className="text-sm font-semibold text-gray-800">独立第三方多模态引擎</span>
                <p className="text-xs text-gray-400 mt-0.5">独立指向高性能视觉专用端点（如 qwen3-vl 等）</p>
              </div>
            </label>
          </div>
        </div>

        {/* 独立配置字段 */}
        {visionMode === 'standalone' ? (
          <div className="space-y-4 pt-1 animate-in fade-in duration-200">
            {/* 模型引擎服务商下拉框 */}
            <div>
              <label className="block text-sm font-semibold text-gray-700 mb-2">模型引擎服务商</label>
              <select
                value={activeVisionProvider}
                onChange={e => {
                  setActiveVisionProvider(e.target.value);
                  setVisionTestResult(null);
                  setVisionModelFetchMsg(null);
                }}
                className="w-full px-4 py-3 border border-gray-300 rounded-xl focus:ring-2 focus:ring-purple-500 focus:border-purple-500 outline-none text-sm bg-white font-medium shadow-sm transition-all"
              >
                {PRESET_VISION_PROVIDERS.map(p => (
                  <option key={p} value={p}>{p}</option>
                ))}
              </select>
              <p className="text-xs text-gray-400 mt-1.5">
                切换不同服务商将自动调出并回填该服务商之前保存的专属端点与密钥配置
              </p>
            </div>

            {/* API 服务端点 (Endpoint URL) */}
            <div>
              <label className="block text-sm font-semibold text-gray-700 mb-2">多模态 API 服务端点 (Endpoint URL)</label>
              <div className="relative">
                <input
                  type="text"
                  value={currentVisionConfig.baseURL}
                  onChange={e => handleVisionFieldChange('baseURL', e.target.value)}
                  placeholder="例如: http://40dd.shop:8000/v1"
                  className="w-full px-4 py-3 border border-gray-300 rounded-xl focus:ring-2 focus:ring-purple-500 focus:border-purple-500 outline-none text-sm font-mono shadow-sm transition-all pr-12"
                />
                <div className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 text-xs px-1.5 py-0.5 rounded bg-gray-100 border border-gray-200">
                  URL
                </div>
              </div>
            </div>

            {/* API Key 访问密钥 */}
            <div>
              <label className="block text-sm font-semibold text-gray-700 mb-2">多模态 API Key 访问密钥</label>
              <div className="relative">
                <input
                  type={visionShowKey ? 'text' : 'password'}
                  value={currentVisionConfig.apiKey}
                  onChange={e => handleVisionFieldChange('apiKey', e.target.value)}
                  placeholder="无密钥请填 EMPTY，或输入 sk-..."
                  className="w-full px-4 py-3 border border-gray-300 rounded-xl focus:ring-2 focus:ring-purple-500 focus:border-purple-500 outline-none text-sm font-mono shadow-sm transition-all pr-12"
                />
                <button
                  type="button"
                  onClick={() => setVisionShowKey(!visionShowKey)}
                  className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600 p-1 rounded-lg transition-colors cursor-pointer"
                >
                  {visionShowKey ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                </button>
              </div>
            </div>

            {/* 选用的视觉模型名称与超时时间 */}
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <div className="md:col-span-2">
                <div className="flex items-center justify-between mb-2">
                  <label className="text-sm font-semibold text-gray-700">选用的视觉模型名称 (Model Name)</label>
                  <div className="flex items-center space-x-2">
                    {visionModelList.length > 0 && (
                      <button
                        type="button"
                        onClick={() => setVisionManualInput(!visionManualInput)}
                        className="text-xs text-purple-600 hover:text-purple-800 font-medium flex items-center space-x-1 cursor-pointer transition-colors"
                      >
                        <Edit3 className="w-3 h-3" />
                        <span>{visionManualInput ? '切换为下拉选取' : '手动输入'}</span>
                      </button>
                    )}
                    <button
                      type="button"
                      onClick={handleFetchVisionModels}
                      disabled={visionFetchingModels}
                      className="text-xs px-2.5 py-1 rounded-lg bg-purple-50 hover:bg-purple-100 text-purple-700 border border-purple-200/70 font-medium flex items-center space-x-1 cursor-pointer transition-all disabled:opacity-50"
                      title="从上方服务端点拉取可用多模态模型列表"
                    >
                      {visionFetchingModels ? (
                        <Loader2 className="w-3 h-3 animate-spin text-purple-600" />
                      ) : (
                        <RefreshCw className="w-3 h-3 text-purple-600" />
                      )}
                      <span>{visionFetchingModels ? '正在读取...' : '读取可用模型'}</span>
                    </button>
                  </div>
                </div>

                {visionModelList.length > 0 && !visionManualInput ? (
                  <div className="relative">
                    <select
                      value={currentVisionConfig.model}
                      onChange={e => handleVisionFieldChange('model', e.target.value)}
                      className="w-full px-4 py-3 border border-purple-300 rounded-xl focus:ring-2 focus:ring-purple-500 focus:border-purple-500 outline-none text-sm font-mono bg-purple-50/20 text-gray-800 shadow-sm transition-all cursor-pointer appearance-none pr-10"
                    >
                      {currentVisionConfig.model && !visionModelList.includes(currentVisionConfig.model) && (
                        <option value={currentVisionConfig.model}>{currentVisionConfig.model} (当前保存)</option>
                      )}
                      {visionModelList.map(m => (
                        <option key={m} value={m}>{m}</option>
                      ))}
                    </select>
                    <div className="absolute right-3 top-1/2 -translate-y-1/2 pointer-events-none text-purple-500">
                      <ListFilter className="w-4 h-4" />
                    </div>
                  </div>
                ) : (
                  <input
                    type="text"
                    value={currentVisionConfig.model}
                    onChange={e => handleVisionFieldChange('model', e.target.value)}
                    placeholder="例如: qwen3-vl-32b-awq, qwen2.5vl:7b"
                    className="w-full px-4 py-3 border border-gray-300 rounded-xl focus:ring-2 focus:ring-purple-500 focus:border-purple-500 outline-none text-sm font-mono shadow-sm transition-all"
                  />
                )}

                {visionModelFetchMsg && (
                  <p className={`text-xs mt-1.5 flex items-center space-x-1 ${visionModelFetchMsg.success ? 'text-emerald-600' : 'text-amber-600'}`}>
                    <span>{visionModelFetchMsg.success ? '✓' : 'ℹ'}</span>
                    <span>{visionModelFetchMsg.msg}</span>
                  </p>
                )}
              </div>
              <div>
                <label className="block text-sm font-semibold text-gray-700 mb-2">超时时间 (秒)</label>
                <input
                  type="number"
                  value={currentVisionConfig.timeoutSeconds || 300}
                  onChange={e => handleVisionFieldChange('timeoutSeconds', parseInt(e.target.value) || 300)}
                  className="w-full px-4 py-3 border border-gray-300 rounded-xl focus:ring-2 focus:ring-purple-500 focus:border-purple-500 outline-none text-sm font-mono shadow-sm transition-all"
                />
              </div>
            </div>
          </div>
        ) : (
          <div className="p-4 rounded-xl bg-gray-50 border border-gray-200 text-xs text-gray-600 space-y-1">
            <p>🔹 <strong>当前跟随主力模型：</strong>{currentMainConfig.model || '未指定'}</p>
            <p>🔹 <strong>当前服务端点：</strong>{currentMainConfig.baseURL || '未指定'}</p>
          </div>
        )}

        {/* 测试反馈提示 */}
        {visionTestResult && (
          <div className={`p-3.5 rounded-xl border flex items-center gap-2.5 text-xs font-medium animate-in fade-in duration-200 ${
            visionTestResult.success 
              ? 'bg-emerald-50 border-emerald-200 text-emerald-700' 
              : 'bg-red-50 border-red-200 text-red-700'
          }`}>
            {visionTestResult.success ? <CheckCircle2 className="w-4 h-4 shrink-0" /> : <AlertCircle className="w-4 h-4 shrink-0" />}
            <span>{visionTestResult.msg}</span>
          </div>
        )}

        {/* 独立操作按钮 */}
        <div className="flex items-center gap-3 pt-2">
          <button
            onClick={handleSaveVision}
            disabled={visionSaving}
            className="flex-1 px-6 py-3.5 bg-purple-700 hover:bg-purple-800 active:scale-[0.99] text-white font-semibold rounded-xl transition-all shadow-md flex items-center justify-center gap-2 disabled:opacity-50 cursor-pointer"
          >
            {visionSaving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />}
            <span>保存多模态识别配置</span>
          </button>
          <button
            onClick={handleTestVision}
            disabled={visionTesting}
            className="px-6 py-3.5 bg-white border border-gray-300 hover:bg-gray-50 active:scale-[0.99] text-gray-700 font-semibold rounded-xl transition-all shadow-sm flex items-center justify-center gap-2 disabled:opacity-50 cursor-pointer whitespace-nowrap"
          >
            {visionTesting ? <Loader2 className="w-4 h-4 animate-spin text-purple-600" /> : <Activity className="w-4 h-4 text-purple-600" />}
            <span>测试视觉 Gateway 连通性</span>
          </button>
        </div>
      </div>
    </div>
  );
}


