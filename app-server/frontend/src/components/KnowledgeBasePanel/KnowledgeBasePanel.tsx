import { useState, useEffect } from 'react';
import { useParams } from 'react-router-dom';
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Cell, ScatterChart, Scatter, ZAxis } from 'recharts';
import { Database, FileText, Table2, Ruler, RefreshCw, TrendingUp, Layers, BarChart3, Sparkles, Network } from 'lucide-react';
import { useAuthStore } from '../../store/authStore';
import { GraphVisualizer } from '../Admin/GraphVisualizer';
import LogoSpinner from '../LogoSpinner';

const API_BASE = import.meta.env.VITE_API_BASE || '';

// WHY: 莫兰迪色系配色板——柔和高级感，与现有 UI 风格一致
const FILE_TYPE_COLORS: Record<string, string> = {
  pdf: '#5B8FB9',
  docx: '#6CA67C',
  xlsx: '#D4A053',
  pptx: '#C47E7E',
  web: '#9B7ED8',
  other: '#8896A7',
};

const DISTRIBUTION_COLOR = '#7C8DB5';

interface StatsData {
  total_files: number;
  total_chunks: number;
  total_tables: number;
  avg_chunk_length: number;
  file_stats: {
    file_id: string;
    filename: string;
    chunk_count: number;
    avg_length: number;
    file_type: string;
  }[];
  chunk_length_distribution: {
    range: string;
    count: number;
  }[];
}

interface VectorPoint {
  x: number;
  y: number;
  filename: string;
  preview: string;
  file_type: string;
}

// WHY: 动画计数器组件——数字从 0 跳到目标值，
//      提供"数据正在被加载"的视觉反馈。
function AnimatedCounter({ value, duration = 800 }: { value: number; duration?: number }) {
  const [display, setDisplay] = useState(0);

  useEffect(() => {
    if (value === 0) { setDisplay(0); return; }
    const start = performance.now();
    const from = 0;

    function tick(now: number) {
      const elapsed = now - start;
      const progress = Math.min(elapsed / duration, 1);
      // WHY: easeOutExpo 缓动函数，开头快结尾慢，更有"弹出"感
      const eased = 1 - Math.pow(2, -10 * progress);
      setDisplay(Math.round(from + (value - from) * eased));
      if (progress < 1) requestAnimationFrame(tick);
    }

    requestAnimationFrame(tick);
  }, [value, duration]);

  return <span>{display.toLocaleString()}</span>;
}

// WHY: 自定义 Tooltip 让悬停信息更清晰美观
function ChunkTooltip({ active, payload }: any) {
  if (!active || !payload?.length) return null;
  const data = payload[0].payload;
  return (
    <div className="bg-white/95 backdrop-blur-sm rounded-lg shadow-xl border border-gray-100 px-4 py-3 text-xs">
      <p className="font-semibold text-gray-800 mb-1 max-w-[200px] truncate">{data.filename || data.range}</p>
      <p className="text-gray-500">切片数量：<span className="text-gray-800 font-medium">{data.chunk_count || data.count}</span></p>
      {data.avg_length && <p className="text-gray-500">平均长度：<span className="text-gray-800 font-medium">{data.avg_length} 字</span></p>}
      {data.file_type && <p className="text-gray-500">类型：<span className="text-gray-800 font-medium">{data.file_type.toUpperCase()}</span></p>}
    </div>
  );
}

export default function KnowledgeBasePanel() {
  const { id: projectId } = useParams<{ id: string }>();
  const [stats, setStats] = useState<StatsData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  // WHY: 向量星云图数据独立管理——t-SNE 计算耗时较长，
  //      不应阻塞统计面板的首屏渲染。
  const [vectorPoints, setVectorPoints] = useState<VectorPoint[]>([]);
  const [vectorLoading, setVectorLoading] = useState(false);
  const [vectorError, setVectorError] = useState('');

  const fetchStats = async () => {
    setLoading(true);
    setError('');
    try {
      const token = useAuthStore.getState().token;
      const t = new Date().getTime();
      const res = await fetch(`${API_BASE}/api/knowledge/stats?project_id=${projectId || 'default'}&t=${t}`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      setStats(data);
    } catch (e: any) {
      setError(e.message || '加载失败');
    } finally {
      setLoading(false);
    }
  };

  const fetchVectors = async () => {
    setVectorLoading(true);
    setVectorError('');
    try {
      const token = useAuthStore.getState().token;
      const res = await fetch(`${API_BASE}/api/knowledge/vectors?project_id=${projectId || 'default'}`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      setVectorPoints(data.points || []);
    } catch (e: any) {
      setVectorError(e.message || '加载失败');
      console.warn('[VectorNebula] 加载失败:', e);
    } finally {
      setVectorLoading(false);
    }
  };

  useEffect(() => {
    fetchStats();
    // WHY: 延迟 500ms 后再请求向量数据，让统计面板先行渲染
    const timer = setTimeout(() => fetchVectors(), 500);
    return () => clearTimeout(timer);
  }, [projectId]);

  if (loading) {
    return (
      <div className="h-full flex items-center justify-center">
        <LogoSpinner size={72} overlay={false} text="正在分析知识库向量数据…" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="h-full flex items-center justify-center">
        <div className="text-center">
          <p className="text-red-500 text-sm mb-3">数据加载失败：{error}</p>
          <button onClick={fetchStats} className="text-xs px-4 py-2 bg-blue-50 text-blue-600 rounded-lg hover:bg-blue-100 transition">
            重试
          </button>
        </div>
      </div>
    );
  }

  if (!stats) return null;

  const statCards = [
    {
      icon: <FileText className="w-5 h-5" />,
      label: '已入库文件',
      value: stats.total_files,
      color: 'from-blue-500 to-blue-600',
      bgLight: 'bg-blue-50',
    },
    {
      icon: <Layers className="w-5 h-5" />,
      label: '总切片数',
      value: stats.total_chunks,
      color: 'from-emerald-500 to-emerald-600',
      bgLight: 'bg-emerald-50',
    },
    {
      icon: <Table2 className="w-5 h-5" />,
      label: '表格数',
      value: stats.total_tables,
      color: 'from-amber-500 to-amber-600',
      bgLight: 'bg-amber-50',
    },
    {
      icon: <Ruler className="w-5 h-5" />,
      label: '平均切片长度',
      value: stats.avg_chunk_length,
      color: 'from-purple-500 to-purple-600',
      bgLight: 'bg-purple-50',
      suffix: '字',
    },
  ];

  // WHY: 截断过长文件名，柱状图的 X 轴标签最多显示 8 个字符
  const barData = stats.file_stats.map(f => ({
    ...f,
    shortName: f.filename.length > 10
      ? f.filename.slice(0, 4) + '…' + f.filename.slice(-4)
      : f.filename,
  }));

  return (
    <div className="h-full overflow-y-auto bg-gradient-to-br from-gray-50 to-gray-100/50">
      <div className="max-w-[1400px] mx-auto px-8 py-8">
        {/* 标题栏 */}
        <div className="flex items-center justify-between mb-8">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 bg-gradient-to-br from-indigo-500 to-purple-600 rounded-xl flex items-center justify-center shadow-lg shadow-indigo-200">
              <Database className="w-5 h-5 text-white" />
            </div>
            <div>
              <h2 className="text-lg font-bold text-gray-800">知识库数据看板</h2>
              <p className="text-xs text-gray-400 mt-0.5">向量化资料入库全景分析</p>
            </div>
          </div>
          <button
            onClick={() => { fetchStats(); fetchVectors(); }}
            className="flex items-center gap-2 px-4 py-2 bg-white border border-gray-200 rounded-xl text-xs text-gray-500 hover:text-indigo-600 hover:border-indigo-200 hover:shadow-sm transition-all"
          >
            <RefreshCw className="w-3.5 h-3.5" />
            刷新数据
          </button>
        </div>

        {/* 统计卡片 */}
        <div className="grid grid-cols-4 gap-5 mb-8">
          {statCards.map((card) => (
            <div
              key={card.label}
              className="bg-white rounded-2xl p-5 border border-gray-100 shadow-sm hover:shadow-md transition-shadow group"
            >
              <div className="flex items-center justify-between mb-4">
                <div className={`w-10 h-10 ${card.bgLight} rounded-xl flex items-center justify-center text-gray-600 group-hover:scale-110 transition-transform`}>
                  {card.icon}
                </div>
                <TrendingUp className="w-4 h-4 text-gray-300" />
              </div>
              <div className="text-3xl font-bold text-gray-800 tracking-tight">
                <AnimatedCounter value={card.value} />
                {card.suffix && <span className="text-base font-normal text-gray-400 ml-1">{card.suffix}</span>}
              </div>
              <p className="text-xs text-gray-400 mt-1.5 font-medium">{card.label}</p>
            </div>
          ))}
        </div>

        {/* 图表区域 */}
        <div className="grid grid-cols-2 gap-6">
          {/* 文件切片柱状图 */}
          <div className="bg-white rounded-2xl p-6 border border-gray-100 shadow-sm">
            <div className="flex items-center gap-2 mb-5">
              <BarChart3 className="w-4 h-4 text-indigo-500" />
              <h3 className="text-sm font-semibold text-gray-700">文件切片数量分布</h3>
            </div>
            {barData.length > 0 ? (
              <ResponsiveContainer width="100%" height={320}>
                <BarChart data={barData} margin={{ top: 5, right: 20, left: 0, bottom: 60 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                  <XAxis
                    dataKey="shortName"
                    tick={{ fontSize: 10, fill: '#9ca3af' }}
                    angle={-35}
                    textAnchor="end"
                    interval={0}
                    height={80}
                  />
                  <YAxis tick={{ fontSize: 11, fill: '#9ca3af' }} />
                  <Tooltip content={<ChunkTooltip />} />
                  <Bar dataKey="chunk_count" radius={[6, 6, 0, 0]} maxBarSize={40}>
                    {barData.map((entry, idx) => (
                      <Cell key={idx} fill={FILE_TYPE_COLORS[entry.file_type] || FILE_TYPE_COLORS.other} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            ) : (
              <div className="h-[320px] flex items-center justify-center text-gray-300 text-sm">暂无文件数据</div>
            )}
            {/* 图例 */}
            <div className="flex flex-wrap gap-3 mt-4 justify-center">
              {Object.entries(FILE_TYPE_COLORS).map(([type, color]) => (
                <div key={type} className="flex items-center gap-1.5 text-[10px] text-gray-500">
                  <div className="w-2.5 h-2.5 rounded-sm" style={{ backgroundColor: color }} />
                  {type.toUpperCase()}
                </div>
              ))}
            </div>
          </div>

          {/* 切片长度分布图 */}
          <div className="bg-white rounded-2xl p-6 border border-gray-100 shadow-sm">
            <div className="flex items-center gap-2 mb-5">
              <Ruler className="w-4 h-4 text-purple-500" />
              <h3 className="text-sm font-semibold text-gray-700">切片长度分布（字符数）</h3>
            </div>
            {stats.chunk_length_distribution.some(d => d.count > 0) ? (
              <ResponsiveContainer width="100%" height={320}>
                <BarChart data={stats.chunk_length_distribution} margin={{ top: 5, right: 20, left: 0, bottom: 20 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                  <XAxis
                    dataKey="range"
                    tick={{ fontSize: 11, fill: '#9ca3af' }}
                  />
                  <YAxis tick={{ fontSize: 11, fill: '#9ca3af' }} />
                  <Tooltip content={<ChunkTooltip />} />
                  <Bar dataKey="count" fill={DISTRIBUTION_COLOR} radius={[6, 6, 0, 0]} maxBarSize={60}>
                    {stats.chunk_length_distribution.map((_, idx) => (
                      <Cell
                        key={idx}
                        fill={`hsl(${220 + idx * 15}, 45%, ${55 + idx * 5}%)`}
                      />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            ) : (
              <div className="h-[320px] flex items-center justify-center text-gray-300 text-sm">暂无切片数据</div>
            )}
            <p className="text-[10px] text-gray-400 text-center mt-3">
              💡 理想切片长度为 256-512 字符，过短信息密度低，过长检索精度降低
            </p>
          </div>
        </div>

        {/* 向量空间星云图 */}
        <div className="bg-gradient-to-br from-slate-900 via-indigo-950 to-slate-900 rounded-2xl p-6 border border-indigo-800/30 shadow-lg mt-6 relative overflow-hidden">
          {/* WHY: 背景装饰——模拟深空星云效果 */}
          <div className="absolute inset-0 opacity-10">
            <div className="absolute top-10 left-20 w-60 h-60 bg-purple-500 rounded-full blur-[100px]" />
            <div className="absolute bottom-10 right-20 w-80 h-80 bg-blue-500 rounded-full blur-[120px]" />
            <div className="absolute top-1/2 left-1/2 w-40 h-40 bg-cyan-400 rounded-full blur-[80px]" />
          </div>

          <div className="relative z-10">
            <div className="flex items-center justify-between mb-5">
              <div className="flex items-center gap-2">
                <Sparkles className="w-4 h-4 text-purple-400" />
                <h3 className="text-sm font-semibold text-white/90">向量空间星云图</h3>
                <span className="text-[10px] text-indigo-300/60 ml-2">t-SNE 降维可视化 · 语义相近的切片自然聚集</span>
              </div>
              {vectorPoints.length > 0 && (
                <span className="text-[10px] text-indigo-300/50">{vectorPoints.length} 个知识切片</span>
              )}
            </div>

            {vectorLoading ? (
              <div className="h-[400px] flex flex-col items-center justify-center gap-4">
                <div className="flex gap-2">
                  {[0, 1, 2, 3, 4].map(i => (
                    <div
                      key={i}
                      className="w-2 h-2 bg-purple-400 rounded-full animate-pulse"
                      style={{ animationDelay: `${i * 150}ms` }}
                    />
                  ))}
                </div>
                <p className="text-xs text-indigo-300/50 font-light">正在计算 t-SNE 降维投影...</p>
              </div>
            ) : vectorPoints.length > 0 ? (
              <>
                <ResponsiveContainer width="100%" height={400}>
                  <ScatterChart margin={{ top: 10, right: 30, bottom: 10, left: 10 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" />
                    <XAxis
                      dataKey="x"
                      type="number"
                      tick={{ fontSize: 9, fill: 'rgba(255,255,255,0.2)' }}
                      axisLine={{ stroke: 'rgba(255,255,255,0.08)' }}
                      name="t-SNE 维度 1"
                    />
                    <YAxis
                      dataKey="y"
                      type="number"
                      tick={{ fontSize: 9, fill: 'rgba(255,255,255,0.2)' }}
                      axisLine={{ stroke: 'rgba(255,255,255,0.08)' }}
                      name="t-SNE 维度 2"
                    />
                    <ZAxis range={[30, 30]} />
                    <Tooltip
                      content={({ active, payload }: any) => {
                        if (!active || !payload?.length) return null;
                        const d = payload[0].payload;
                        return (
                          <div className="bg-slate-800/95 backdrop-blur-md rounded-lg shadow-2xl border border-indigo-500/30 px-4 py-3 text-xs max-w-[280px]">
                            <p className="font-semibold text-indigo-200 mb-1 truncate">{d.filename}</p>
                            <p className="text-white/60 leading-relaxed line-clamp-3">{d.preview || '（无预览）'}</p>
                            <p className="text-indigo-400/50 mt-1.5 text-[10px]">{d.file_type?.toUpperCase()}</p>
                          </div>
                        );
                      }}
                    />
                    {/* WHY: 按文件名分组渲染多个 Scatter，每组独立着色 */}
                    {(() => {
                      const groups: Record<string, typeof vectorPoints> = {};
                      vectorPoints.forEach(p => {
                        const key = p.filename;
                        if (!groups[key]) groups[key] = [];
                        groups[key].push(p);
                      });
                      return Object.entries(groups).map(([filename, pts]) => {
                        const ft = pts[0]?.file_type || 'other';
                        const color = FILE_TYPE_COLORS[ft] || FILE_TYPE_COLORS.other;
                        return (
                          <Scatter
                            key={filename}
                            name={filename}
                            data={pts}
                            fill={color}
                            fillOpacity={0.7}
                          />
                        );
                      });
                    })()}
                  </ScatterChart>
                </ResponsiveContainer>

                {/* 文件图例 */}
                <div className="flex flex-wrap gap-3 mt-3 justify-center">
                  {(() => {
                    const seen = new Set<string>();
                    return vectorPoints
                      .filter(p => {
                        if (seen.has(p.filename)) return false;
                        seen.add(p.filename);
                        return true;
                      })
                      .slice(0, 12)
                      .map(p => (
                        <div key={p.filename} className="flex items-center gap-1.5 text-[10px] text-white/40">
                          <div
                            className="w-2 h-2 rounded-full"
                            style={{ backgroundColor: FILE_TYPE_COLORS[p.file_type] || FILE_TYPE_COLORS.other }}
                          />
                          <span className="max-w-[120px] truncate">{p.filename}</span>
                        </div>
                      ));
                  })()}
                  {(() => {
                    const uniqueFiles = new Set(vectorPoints.map(p => p.filename));
                    return uniqueFiles.size > 12 ? (
                      <span className="text-[10px] text-white/20">+{uniqueFiles.size - 12} 个文件</span>
                    ) : null;
                  })()}
                </div>
              </>
            ) : vectorError ? (
              <div className="h-[400px] flex flex-col items-center justify-center gap-3">
                <p className="text-red-400/60 text-xs">加载失败：{vectorError}</p>
                <button
                  onClick={fetchVectors}
                  className="text-[10px] px-3 py-1.5 bg-indigo-500/20 text-indigo-300 rounded-lg hover:bg-indigo-500/30 transition"
                >
                  重试
                </button>
              </div>
            ) : (
              <div className="h-[400px] flex items-center justify-center text-indigo-300/30 text-sm">
                暂无向量数据
              </div>
            )}
          </div>
        </div>

        {/* 知识图谱星空图 */}
        <div className="bg-gradient-to-br from-slate-900 via-gray-900 to-slate-900 rounded-2xl p-6 border border-gray-800/30 shadow-lg mt-6 relative overflow-hidden">
          <div className="relative z-10">
            <div className="flex items-center justify-between mb-5">
              <div className="flex items-center gap-2">
                <Network className="w-4 h-4 text-cyan-400" />
                <h3 className="text-sm font-semibold text-white/90">知识图谱星空图</h3>
                <span className="text-[10px] text-cyan-300/60 ml-2">知识实体与关联关系可视化</span>
              </div>
            </div>
            {/* projectId is guaranteed by the route, but useParams could theoretically be undefined, we default to empty string if missing */}
            <GraphVisualizer projectId={projectId || ''} />
          </div>
        </div>

        {/* 文件详情表格 */}
        {stats.file_stats.length > 0 && (
          <div className="bg-white rounded-2xl p-6 border border-gray-100 shadow-sm mt-6">
            <div className="flex items-center gap-2 mb-5">
              <FileText className="w-4 h-4 text-emerald-500" />
              <h3 className="text-sm font-semibold text-gray-700">文件入库明细</h3>
              <span className="text-[10px] text-gray-400 ml-auto">{stats.total_files} 个文件</span>
            </div>
            <div className="overflow-x-auto">
              <table className="w-full text-xs">
                <thead>
                  <tr className="border-b border-gray-100">
                    <th className="text-left py-3 px-4 text-gray-400 font-medium">文件名</th>
                    <th className="text-center py-3 px-4 text-gray-400 font-medium">类型</th>
                    <th className="text-center py-3 px-4 text-gray-400 font-medium">切片数</th>
                    <th className="text-center py-3 px-4 text-gray-400 font-medium">平均长度</th>
                    <th className="text-right py-3 px-4 text-gray-400 font-medium">占比</th>
                  </tr>
                </thead>
                <tbody>
                  {stats.file_stats.map((f) => {
                    const pct = stats.total_chunks > 0
                      ? ((f.chunk_count / stats.total_chunks) * 100).toFixed(1)
                      : '0';
                    return (
                      <tr key={f.file_id} className="border-b border-gray-50 hover:bg-gray-50/50 transition-colors">
                        <td className="py-3 px-4 text-gray-700 font-medium max-w-[300px] truncate" title={f.filename}>
                          {f.filename}
                        </td>
                        <td className="text-center py-3 px-4">
                          <span
                            className="inline-block px-2 py-0.5 rounded-md text-[10px] font-medium text-white"
                            style={{ backgroundColor: FILE_TYPE_COLORS[f.file_type] || FILE_TYPE_COLORS.other }}
                          >
                            {f.file_type.toUpperCase()}
                          </span>
                        </td>
                        <td className="text-center py-3 px-4 text-gray-600 font-mono">{f.chunk_count}</td>
                        <td className="text-center py-3 px-4 text-gray-500">{f.avg_length} 字</td>
                        <td className="text-right py-3 px-4">
                          <div className="flex items-center justify-end gap-2">
                            <div className="w-16 h-1.5 bg-gray-100 rounded-full overflow-hidden">
                              <div
                                className="h-full rounded-full bg-indigo-400"
                                style={{ width: `${Math.min(parseFloat(pct), 100)}%` }}
                              />
                            </div>
                            <span className="text-gray-500 w-10 text-right">{pct}%</span>
                          </div>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
