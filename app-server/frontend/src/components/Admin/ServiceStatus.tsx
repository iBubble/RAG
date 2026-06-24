import { useState, useEffect, useCallback } from 'react';
import { useAuthStore } from '../../store/authStore';
import {
  Loader2, Power, PowerOff, RefreshCw,
  CheckCircle2, XCircle,
} from 'lucide-react';
import {
  LineChart, Line, XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer, Legend,
} from 'recharts';
import LogoSpinner from '../LogoSpinner';

const API_BASE = import.meta.env.VITE_API_BASE || '';

interface ServiceItem {
  id: string;
  name: string;
  online: boolean;
  detail: string;
  controllable: boolean;
  metrics?: Record<string, unknown>;
}

interface MetricsPoint {
  recorded_at: string;
  vectors: number;
  entities: number;
  relations: number;
  communities: number;
  redis_mem_mb: number;
  redis_keys: number;
}

const METRIC_LABELS: Record<string, Record<string, string>> = {
  ollama: {
    model_name: '模型',
    parameter_size: '参数量',
    quantization: '量化',
    vram_gb: '显存',
    context_length: '上下文',
    family: '架构',
    available_models: '可用模型',
  },
  qdrant: {
    collections: '集合',
    total_vectors: '向量数',
  },
  neo4j: {
    entities: '实体',
    relationships: '关系',
    communities: '社区',
    heap_max: '堆上限',
    pagecache: '页缓存',
  },
  redis: {
    used_memory_mb: '内存',
    peak_memory_mb: '峰值',
    fast_queue: '快队列',
    slow_queue: '慢队列',
    total_keys: '键数',
    connected_clients: '连接',
  },
  celery: {
    workers: 'Worker',
    active_tasks: '执行中',
    reserved_tasks: '排队',
  },
};

function fmtVal(key: string, val: unknown): string {
  if (val === null || val === undefined) return '-';
  if (Array.isArray(val)) return val.join('、') || '-';
  if (key === 'vram_gb') return `${val}G`;
  if (key.endsWith('_mb')) return `${val}M`;
  if (key === 'context_length') return `${(Number(val)/1000).toFixed(0)}k`;
  if (['total_vectors','entities','relationships','communities'].includes(key))
    return Number(val).toLocaleString();
  return String(val);
}

// ── 曲线图颜色 ──
const CHART_COLORS = {
  vectors: '#6366f1',
  entities: '#10b981',
  relations: '#f59e0b',
  communities: '#ec4899',
  redis_mem_mb: '#8b5cf6',
  redis_keys: '#06b6d4',
};

const CHART_LABELS: Record<string, string> = {
  vectors: '向量数',
  entities: '实体数',
  relations: '关系数',
  communities: '社区数',
  redis_mem_mb: 'Redis 内存 (MB)',
  redis_keys: 'Redis 键数',
};

// ── 曲线图子组件 ──
function MetricsChart({ headers }: { headers: Record<string, string> }) {
  const [history, setHistory] = useState<MetricsPoint[]>([]);
  const [loading, setLoading] = useState(true);
  const [days, setDays] = useState(7);

  const fetchHistory = useCallback(async () => {
    try {
      const res = await fetch(
        `${API_BASE}/api/admin/metrics/history?days=${days}`,
        { headers },
      );
      if (res.ok) setHistory(await res.json());
    } catch { /* 静默 */ }
    setLoading(false);
  }, [headers, days]);

  useEffect(() => {
    fetchHistory();
  }, [fetchHistory]);

  // WHY: 格式化时间轴标签，只显示 MM-DD HH:mm
  const fmtTime = (iso: string) => {
    try {
      const dateStr = iso.replace('T', ' ').replace(/-/g, '/');
      const d = new Date(dateStr);
      return `${(d.getMonth()+1).toString().padStart(2,'0')}-${d.getDate().toString().padStart(2,'0')} ${d.getHours().toString().padStart(2,'0')}:${d.getMinutes().toString().padStart(2,'0')}`;
    } catch { return iso; }
  };

  const chartData = history.map(p => ({
    ...p,
    time: fmtTime(p.recorded_at),
  }));

  // WHY: 将指标分为两组渲染两张图：
  //   图1 — 存储规模指标（向量数、实体数、关系数、社区数）
  //   图2 — Redis 运行指标（内存、键数）
  const storageKeys = ['vectors', 'entities', 'relations', 'communities'] as const;
  const redisKeys = ['redis_mem_mb', 'redis_keys'] as const;

  if (loading) {
    return <LogoSpinner size={56} overlay={false} />;
  }

  if (history.length === 0) {
    return (
      <div className="text-center py-8 text-gray-400 text-sm">
        暂无历史数据，系统将每 5 分钟自动采集一次快照
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* 时间范围选择 */}
      <div className="flex items-center gap-2">
        {[1, 3, 7, 30].map(d => (
          <button key={d} onClick={() => setDays(d)}
            className={`px-3 py-1 text-xs font-medium rounded-lg transition-colors ${
              days === d
                ? 'bg-indigo-500 text-white shadow-sm'
                : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
            }`}>
            {d === 1 ? '24小时' : `${d}天`}
          </button>
        ))}
      </div>

      {/* 图1：存储规模趋势 */}
      <div className="bg-white rounded-xl border border-gray-200 p-4">
        <h4 className="text-sm font-semibold text-gray-700 mb-3">📊 存储规模趋势</h4>
        <div className="h-[260px]">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={chartData} margin={{ top: 5, right: 20, left: 10, bottom: 5 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
              <XAxis dataKey="time" tick={{ fontSize: 10, fill: '#9ca3af' }} tickLine={false} />
              <YAxis tick={{ fontSize: 10, fill: '#9ca3af' }} tickLine={false} axisLine={false}
                tickFormatter={(v: number) => v >= 1000 ? `${(v/1000).toFixed(1)}k` : String(v)} />
              <Tooltip
                contentStyle={{ borderRadius: 8, border: 'none', boxShadow: '0 4px 12px rgba(0,0,0,0.1)', fontSize: 12 }}
                labelFormatter={(label: any) => `时间: ${label}`}
              />
              <Legend wrapperStyle={{ fontSize: 12 }} />
              {storageKeys.map(key => (
                <Line key={key} type="monotone" dataKey={key}
                  name={CHART_LABELS[key]} stroke={CHART_COLORS[key]}
                  strokeWidth={2} dot={false} activeDot={{ r: 4 }} />
              ))}
            </LineChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* 图2：Redis 运行趋势 */}
      <div className="bg-white rounded-xl border border-gray-200 p-4">
        <h4 className="text-sm font-semibold text-gray-700 mb-3">🔴 Redis 运行趋势</h4>
        <div className="h-[220px]">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={chartData} margin={{ top: 5, right: 20, left: 10, bottom: 5 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
              <XAxis dataKey="time" tick={{ fontSize: 10, fill: '#9ca3af' }} tickLine={false} />
              <YAxis tick={{ fontSize: 10, fill: '#9ca3af' }} tickLine={false} axisLine={false} />
              <Tooltip
                contentStyle={{ borderRadius: 8, border: 'none', boxShadow: '0 4px 12px rgba(0,0,0,0.1)', fontSize: 12 }}
                labelFormatter={(label: any) => `时间: ${label}`}
              />
              <Legend wrapperStyle={{ fontSize: 12 }} />
              {redisKeys.map(key => (
                <Line key={key} type="monotone" dataKey={key}
                  name={CHART_LABELS[key]} stroke={CHART_COLORS[key]}
                  strokeWidth={2} dot={false} activeDot={{ r: 4 }} />
              ))}
            </LineChart>
          </ResponsiveContainer>
        </div>
      </div>
    </div>
  );
}


export default function ServiceStatus() {
  const { getAuthHeaders } = useAuthStore();
  const [services, setServices] = useState<ServiceItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [toggling, setToggling] = useState<string | null>(null);
  const [message, setMessage] = useState('');
  const [msgType, setMsgType] = useState<'ok' | 'err'>('ok');

  const fetchStatus = useCallback(async () => {
    try {
      const headers = getAuthHeaders();
      const res = await fetch(
        `${API_BASE}/api/admin/service-status`,
        { headers },
      );
      if (res.ok) setServices(await res.json());

      // WHY: 每次拉取状态时，顺便触发后端指标快照采集（后端有 5 分钟节流）
      fetch(`${API_BASE}/api/admin/metrics/snapshot`, {
        method: 'POST', headers,
      }).catch(() => {});
    } catch { /* 静默 */ }
    setLoading(false);
  }, [getAuthHeaders]);

  useEffect(() => {
    fetchStatus();
    const t = setInterval(fetchStatus, 60000);
    return () => clearInterval(t);
  }, [fetchStatus]);

  const showMsg = (text: string, type: 'ok' | 'err') => {
    setMessage(text);
    setMsgType(type);
    setTimeout(() => setMessage(''), 4000);
  };

  const toggle = async (id: string, action: 'start' | 'stop') => {
    setToggling(id);
    try {
      const res = await fetch(
        `${API_BASE}/api/admin/service/${id}/toggle`,
        {
          method: 'POST',
          headers: { ...getAuthHeaders(), 'Content-Type': 'application/json' },
          body: JSON.stringify({ action }),
        },
      );
      const data = await res.json();
      if (res.ok) {
        showMsg(data.message || '操作成功', 'ok');
        setTimeout(fetchStatus, 1500);
      } else {
        showMsg(data.detail || '操作失败', 'err');
      }
    } catch { showMsg('网络错误', 'err'); }
    setToggling(null);
  };

  if (loading) {
    return <LogoSpinner size={72} overlay={false} />;
  }

  const hasControllable = services.some((s) => s.controllable);

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-xl font-bold text-gray-800">系统状态</h2>
        <div className="flex items-center gap-2">
          {message && (
            <span className={`text-xs font-semibold px-3 py-1 rounded-full ${
              msgType === 'ok' ? 'bg-emerald-50 text-emerald-600' : 'bg-rose-50 text-rose-600'
            }`}>{message}</span>
          )}
          <button onClick={fetchStatus}
            className="p-1.5 rounded-lg hover:bg-gray-100 text-gray-400 hover:text-gray-600 transition-colors"
            title="刷新状态">
            <RefreshCw className="w-4 h-4" />
          </button>
        </div>
      </div>

      {hasControllable && (
        <div className="flex gap-2 mb-3">
          <button onClick={() => toggle('all', 'start')} disabled={toggling === 'all'}
            className="flex items-center gap-1 px-3 py-1.5 bg-emerald-500 hover:bg-emerald-600
                       text-white text-xs font-semibold rounded-lg transition-colors disabled:opacity-50 shadow-sm">
            {toggling === 'all' ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Power className="w-3.5 h-3.5" />}
            全部启动
          </button>
          <button onClick={() => toggle('all', 'stop')} disabled={toggling === 'all'}
            className="flex items-center gap-1 px-3 py-1.5 bg-rose-500 hover:bg-rose-600
                       text-white text-xs font-semibold rounded-lg transition-colors disabled:opacity-50 shadow-sm">
            {toggling === 'all' ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <PowerOff className="w-3.5 h-3.5" />}
            全部停止
          </button>
        </div>
      )}

      {/* 服务卡片 — 2×3 网格布局 */}
      <div className="grid grid-cols-2 gap-2">
        {services.map((svc) => {
          const labels = METRIC_LABELS[svc.id] || {};
          const metrics = svc.metrics || {};
          const metricEntries = Object.entries(metrics).filter(([k]) => labels[k]);

          return (
            <div key={svc.id}
              className="bg-white rounded-xl border border-gray-200 px-4 py-2.5
                         hover:shadow-sm transition-shadow">
              {/* 第一行：状态灯 + 名称 + 状态标签 + 控制按钮 */}
              <div className="flex items-center gap-2">
                {svc.online
                  ? <CheckCircle2 className="w-4 h-4 text-emerald-500 shrink-0" />
                  : <XCircle className="w-4 h-4 text-rose-400 shrink-0" />}
                <span className="text-sm font-semibold text-gray-800 whitespace-nowrap truncate">
                  {svc.name}
                </span>

                <div className="flex items-center gap-2 ml-auto shrink-0">
                  <span className={`text-[11px] font-semibold px-2 py-0.5 rounded-full ${
                    svc.online ? 'bg-emerald-50 text-emerald-600' : 'bg-rose-50 text-rose-500'
                  }`}>
                    {svc.online ? '运行中' : '已停止'}
                  </span>

                  {svc.controllable && (
                    <button
                      onClick={() => toggle(svc.id, svc.online ? 'stop' : 'start')}
                      disabled={toggling === svc.id}
                      className={`flex items-center gap-1 px-2.5 py-1 text-[11px] font-semibold
                                  rounded-lg border transition-all disabled:opacity-50 shadow-sm ${
                        svc.online
                          ? 'bg-rose-50 hover:bg-rose-100 text-rose-600 border-rose-200/60'
                          : 'bg-emerald-50 hover:bg-emerald-100 text-emerald-600 border-emerald-200/60'
                      }`}>
                      {toggling === svc.id
                        ? <Loader2 className="w-3 h-3 animate-spin" />
                        : svc.online ? <PowerOff className="w-3 h-3" /> : <Power className="w-3 h-3" />}
                      {svc.online ? '停止' : '启动'}
                    </button>
                  )}
                </div>
              </div>

              {/* 第二行：指标标签 */}
              {metricEntries.length > 0 && (
                <div className="flex items-center gap-x-3 gap-y-0.5 flex-wrap mt-1.5
                                min-w-0 overflow-hidden">
                  {metricEntries.map(([key, val]) => (
                    <span key={key} className="text-[11px] text-gray-500 whitespace-nowrap">
                      <span className="text-gray-400">{labels[key]}</span>
                      {' '}
                      <span className="font-semibold text-gray-700">{fmtVal(key, val)}</span>
                    </span>
                  ))}
                </div>
              )}

              {/* Ollama 常驻多模型列表渲染 */}
              {svc.id === 'ollama' && Array.isArray(metrics.loaded_models) && metrics.loaded_models.length > 0 && (
                <div className="mt-2 pt-2 border-t border-dashed border-stone-200">
                  <div className="text-[10px] text-stone-400 font-bold mb-1">🧠 显存常驻多模型监测：</div>
                  <div className="flex flex-col gap-1">
                    {metrics.loaded_models.map((m: any, idx: number) => (
                      <div key={idx} className="flex justify-between items-center bg-stone-50 border border-stone-100 rounded px-2 py-0.5 text-[11px]">
                        <span className="font-medium text-stone-700 truncate mr-2" title={m.name}>{m.name}</span>
                        <span className="text-[10px] bg-stone-200/60 text-stone-500 rounded px-1.5 py-0.2 shrink-0">{m.vram_gb}G</span>
                      </div>
                    ))}
                  </div>
                </div>
              )}

              {/* 无指标时显示 detail */}
              {metricEntries.length === 0 && svc.detail && (
                <span className="text-xs text-gray-400 mt-1 block truncate">{svc.detail}</span>
              )}
            </div>
          );
        })}
      </div>

      {/* ── 指标趋势曲线图 ── */}
      <div className="mt-6">
        <h3 className="text-base font-bold text-gray-800 mb-3">📈 指标趋势</h3>
        <MetricsChart headers={getAuthHeaders()} />
      </div>
    </div>
  );
}
