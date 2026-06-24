import { useState, useEffect } from 'react';
import { useAuthStore } from '../../store/authStore';
import { useProjectStore } from '../../store/projectStore';
import { Loader2, Save, Sparkles, Cpu, Layers, HelpCircle } from 'lucide-react';

const API_BASE = import.meta.env.VITE_API_BASE || '';

export default function AgentSettings() {
  const { getAuthHeaders } = useAuthStore();
  const triggerRefresh = useProjectStore(state => state.triggerRefresh);
  const fetchPublicSettings = useProjectStore(state => state.fetchPublicSettings);

  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState('');

  // 协同开启流程状态
  const [pleadingEnabled, setPleadingEnabled] = useState(false);
  const [contractEnabled, setContractEnabled] = useState(false);
  const [documentEnabled, setDocumentEnabled] = useState(false);
  const [chatEnabled, setChatEnabled] = useState(false);

  // 高级大模型与参数
  const [contrarianModel, setContrarianModel] = useState('qwen3:8b');
  const [contrarianTemp, setContrarianTemp] = useState(0.5);
  const [arbiterModel, setArbiterModel] = useState('qwen3.6:35b-q4');
  const [arbiterTemp, setArbiterTemp] = useState(0.3);
  const [simpleThreshold, setSimpleThreshold] = useState(500);

  // 协同角色名与设置
  const [supervisorName, setSupervisorName] = useState('【协同】文档秘书');
  const [legalName, setLegalName] = useState('【协同】法律分析专家');
  const [contrarianName, setContrarianName] = useState('【协同】审查员');
  const [arbiterName, setArbiterName] = useState('【协同】仲裁官');

  useEffect(() => {
    const fetchSettings = async () => {
      try {
        const res = await fetch(`${API_BASE}/api/admin/settings`, { headers: getAuthHeaders() });
        if (res.ok) {
          const data = await res.json();
          setPleadingEnabled(data.collab_pleading_enabled === 'true');
          setContractEnabled(data.collab_contract_enabled === 'true');
          setDocumentEnabled(data.collab_document_enabled === 'true');
          setChatEnabled(data.collab_chat_enabled === 'true');
          
          setContrarianModel(data.collab_contrarian_model || 'qwen3:8b');
          setContrarianTemp(parseFloat(data.collab_contrarian_temp) || 0.5);
          setArbiterModel(data.collab_arbiter_model || 'qwen3.6:35b-q4');
          setArbiterTemp(parseFloat(data.collab_arbiter_temp) || 0.3);
          setSimpleThreshold(parseInt(data.collab_simple_threshold) || 500);

          setSupervisorName(data.collab_supervisor_name || '【协同】文档秘书');
          setLegalName(data.collab_legal_name || '【协同】法律分析专家');
          setContrarianName(data.collab_contrarian_name || '【协同】审查员');
          setArbiterName(data.collab_arbiter_name || '【协同】仲裁官');
        }
      } catch (err) {
        console.error('获取协同配置失败:', err);
      }
      setLoading(false);
    };
    fetchSettings();
  }, []);

  const handleSave = async () => {
    setSaving(true);
    setMessage('');
    try {
      const body = {
        collab_pleading_enabled: pleadingEnabled,
        collab_contract_enabled: contractEnabled,
        collab_document_enabled: documentEnabled,
        collab_chat_enabled: chatEnabled,
        collab_contrarian_model: contrarianModel,
        collab_contrarian_temp: contrarianTemp,
        collab_arbiter_model: arbiterModel,
        collab_arbiter_temp: arbiterTemp,
        collab_simple_threshold: simpleThreshold,
        collab_supervisor_name: supervisorName,
        collab_legal_name: legalName,
        collab_contrarian_name: contrarianName,
        collab_arbiter_name: arbiterName,
      };
      const res = await fetch(`${API_BASE}/api/admin/settings`, {
        method: 'PUT',
        headers: { ...getAuthHeaders(), 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
      if (res.ok) {
        setMessage('保存成功');
        await fetchPublicSettings();
        triggerRefresh();
      } else {
        const err = await res.json().catch(() => null);
        setMessage(err?.detail || '保存失败');
      }
    } catch {
      setMessage('网络请求失败');
    }
    setSaving(false);
    setTimeout(() => setMessage(''), 3000);
  };

  if (loading) {
    return (
      <div className="flex h-[300px] w-full items-center justify-center">
        <Loader2 className="w-8 h-8 text-indigo-500 animate-spin" />
      </div>
    );
  }

  return (
    <div className="max-w-4xl pb-16">
      <div className="mb-6 border-b border-gray-100 pb-4 flex items-center gap-3">
        <Sparkles className="w-6 h-6 text-indigo-600 animate-pulse" />
        <div>
          <h2 className="text-xl font-bold text-gray-800">多Agent协同设置</h2>
          <p className="text-xs text-gray-400 mt-1">管理全局协同工作流的默认开启状态、角色专属名称及大模型高级推理参数。</p>
        </div>
      </div>

      <div className="space-y-6">
        {/* 1. 协同流全局开关 */}
        <div className="bg-white rounded-2xl border border-gray-200/80 p-6 shadow-sm hover:shadow-md/5 transition-all">
          <h3 className="text-sm font-bold text-gray-800 mb-4 flex items-center gap-2">
            <Layers className="w-4 h-4 text-indigo-500" />
            协同工作流全局默认启用
          </h3>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {[
              { label: '文书起草工作流', val: pleadingEnabled, set: setPleadingEnabled, desc: '法律专家事务下各类文书的一键起草，默认采用多 Agent 协同。' },
              { label: '合同一键审查', val: contractEnabled, set: setContractEnabled, desc: '对上传的合同进行合规性、风险隐患的一键排查与修改注入。' },
              { label: '段落生成与写作规划', val: documentEnabled, set: setDocumentEnabled, desc: '文书段落的生成与写作大纲编排。' },
              { label: '智能法律助手对话', val: chatEnabled, set: setChatEnabled, desc: '聊天问答框中默认采用多 Agent 编排分流，不开启则为单 Agent 问答。' }
            ].map((item, idx) => (
              <div
                key={idx}
                onClick={() => item.set(!item.val)}
                className={`p-4 rounded-xl border-2 cursor-pointer transition-all duration-200 flex items-center justify-between ${
                  item.val
                    ? 'border-indigo-500 bg-indigo-50/10 ring-1 ring-indigo-500/30'
                    : 'border-gray-100 hover:border-indigo-200 hover:bg-gray-50/30'
                }`}
              >
                <div className="pr-4 flex-1">
                  <span className="text-sm font-bold text-gray-800 block mb-0.5">{item.label}</span>
                  <span className="text-[11px] text-gray-400 leading-relaxed block">{item.desc}</span>
                </div>
                <button
                  className={`relative inline-flex h-5.5 w-10 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus:outline-none ${
                    item.val ? 'bg-indigo-500' : 'bg-gray-200'
                  }`}
                >
                  <span
                    className={`pointer-events-none inline-block h-4.5 w-4.5 transform rounded-full bg-white shadow transition duration-200 ease-in-out ${
                      item.val ? 'translate-x-4.5' : 'translate-x-0'
                    }`}
                  />
                </button>
              </div>
            ))}
          </div>
        </div>

        {/* 2. 协同角色冠名管理 */}
        <div className="bg-white rounded-2xl border border-gray-200/80 p-6 shadow-sm">
          <h3 className="text-sm font-bold text-gray-800 mb-4 flex items-center gap-2">
            <Cpu className="w-4 h-4 text-purple-500" />
            协同工作流专属角色冠名
          </h3>
          <p className="text-xs text-gray-400 mb-4">
            设置在多 Agent 协同推理过程中各个角色的特定显示名称（这与 Linvis 看板展示的实体工作角色已完全隔离，不产生混淆）。
          </p>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            {[
              { role: '文档秘书', val: supervisorName, set: setSupervisorName, color: 'border-blue-100 focus-within:border-blue-500 bg-blue-50/5', icon: '🧠' },
              { role: '法律分析专家', val: legalName, set: setLegalName, color: 'border-amber-100 focus-within:border-amber-500 bg-amber-50/5', icon: '⚖️' },
              { role: '审查员', val: contrarianName, set: setContrarianName, color: 'border-rose-100 focus-within:border-rose-500 bg-rose-50/5', icon: '🤨' },
              { role: '仲裁官', val: arbiterName, set: setArbiterName, color: 'border-purple-100 focus-within:border-purple-500 bg-purple-50/5', icon: '👑' }
            ].map((agent, index) => (
              <div key={index} className={`p-4 rounded-xl border-2 transition-all duration-200 ${agent.color} flex items-center gap-3`}>
                <span className="text-2xl filter drop-shadow-sm select-none">{agent.icon}</span>
                <div className="flex-1">
                  <label className="block text-xs font-bold text-gray-500 mb-1">协同角色：{agent.role}</label>
                  <input
                    type="text"
                    value={agent.val}
                    onChange={e => agent.set(e.target.value)}
                    className="w-full px-3 py-1.5 border border-gray-200/80 rounded-lg outline-none text-xs focus:ring-1 focus:ring-indigo-500 focus:border-transparent bg-white text-gray-700 font-medium"
                    placeholder="角色名称"
                  />
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* 3. 高级协同模型与控制参数 */}
        <div className="bg-white rounded-2xl border border-gray-200/80 p-6 shadow-sm">
          <h3 className="text-sm font-bold text-gray-800 mb-4 flex items-center gap-2">
            <HelpCircle className="w-4 h-4 text-emerald-500" />
            高级推理模型与温度参数微调
          </h3>
          <div className="space-y-4">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {/* 审查员参数 */}
              <div className="p-4 rounded-xl border border-gray-100 bg-gray-50/20">
                <span className="text-xs font-bold text-gray-800 block mb-3">🧐 协同审查员模型配置</span>
                <div className="space-y-3">
                  <div>
                    <label className="block text-[11px] font-semibold text-gray-500 mb-1">推理模型名称</label>
                    <input
                      type="text"
                      value={contrarianModel}
                      onChange={e => setContrarianModel(e.target.value)}
                      className="w-full px-3 py-1.5 border border-gray-200 rounded-lg outline-none text-xs bg-white text-gray-700"
                    />
                  </div>
                  <div>
                    <div className="flex items-center justify-between mb-1">
                      <label className="block text-[11px] font-semibold text-gray-500">模型温度 (Temperature)</label>
                      <span className="text-xs font-bold text-indigo-600 bg-indigo-50 px-2 py-0.5 rounded">{contrarianTemp}</span>
                    </div>
                    <input
                      type="range"
                      min="0.1"
                      max="1.5"
                      step="0.1"
                      value={contrarianTemp}
                      onChange={e => setContrarianTemp(parseFloat(e.target.value))}
                      className="w-full h-1.5 bg-gray-200 rounded-lg appearance-none cursor-pointer accent-indigo-500"
                    />
                  </div>
                </div>
              </div>

              {/* 仲裁官参数 */}
              <div className="p-4 rounded-xl border border-gray-100 bg-gray-50/20">
                <span className="text-xs font-bold text-gray-800 block mb-3">👑 协同仲裁官模型配置</span>
                <div className="space-y-3">
                  <div>
                    <label className="block text-[11px] font-semibold text-gray-500 mb-1">推理模型名称</label>
                    <input
                      type="text"
                      value={arbiterModel}
                      onChange={e => setArbiterModel(e.target.value)}
                      className="w-full px-3 py-1.5 border border-gray-200 rounded-lg outline-none text-xs bg-white text-gray-700"
                    />
                  </div>
                  <div>
                    <div className="flex items-center justify-between mb-1">
                      <label className="block text-[11px] font-semibold text-gray-500">模型温度 (Temperature)</label>
                      <span className="text-xs font-bold text-indigo-600 bg-indigo-50 px-2 py-0.5 rounded">{arbiterTemp}</span>
                    </div>
                    <input
                      type="range"
                      min="0.1"
                      max="1.5"
                      step="0.1"
                      value={arbiterTemp}
                      onChange={e => setArbiterTemp(parseFloat(e.target.value))}
                      className="w-full h-1.5 bg-gray-200 rounded-lg appearance-none cursor-pointer accent-indigo-500"
                    />
                  </div>
                </div>
              </div>
            </div>

            <hr className="border-gray-100" />

            <div>
              <div className="flex items-center justify-between mb-1.5">
                <label className="text-xs font-bold text-gray-800">协同触发字数阈值</label>
                <span className="text-xs font-bold text-indigo-600 bg-indigo-50 px-2 py-0.5 rounded">{simpleThreshold} 字</span>
              </div>
              <p className="text-[11px] text-gray-400 leading-relaxed mb-3">
                当首稿法律分析专家产出的初版草稿字数低于此阈值时，系统判定为简单问题，自动跳过审查员和小杠的辩论质疑，直接秒级输出，以提高推理效率。
              </p>
              <input
                type="range"
                min="100"
                max="2000"
                step="50"
                value={simpleThreshold}
                onChange={e => setSimpleThreshold(parseInt(e.target.value))}
                className="w-full h-1.5 bg-gray-200 rounded-lg appearance-none cursor-pointer accent-indigo-500"
              />
            </div>
          </div>
        </div>

        {/* 底部保存按钮 */}
        <div className="flex items-center gap-3 mt-6">
          <button
            onClick={handleSave}
            disabled={saving}
            className="px-5 py-2.5 bg-gradient-to-r from-indigo-500 to-purple-600 text-white font-semibold rounded-xl hover:from-indigo-600 hover:to-purple-700 transition-all duration-200 disabled:opacity-50 flex items-center gap-2 shadow-md hover:shadow-indigo-500/10 active:scale-[0.98] cursor-pointer"
          >
            {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />}
            保存配置
          </button>
          {message && (
            <span className={`text-sm font-semibold ${message === '保存成功' ? 'text-green-600' : 'text-red-500'}`}>
              {message}
            </span>
          )}
        </div>
      </div>
    </div>
  );
}
