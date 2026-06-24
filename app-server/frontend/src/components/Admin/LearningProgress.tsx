import { useState, useEffect, useMemo } from 'react';
import { useAuthStore } from '../../store/authStore';
import { Loader2, Database, AlertCircle, Network, BrainCircuit, Cpu, Activity, AlertTriangle, X, Copy, Eye, Square, Trash2, Play, Pause } from 'lucide-react';
import { GraphVisualizer } from './GraphVisualizer';
import LogoSpinner from '../LogoSpinner';

const API_BASE = import.meta.env.VITE_API_BASE || '';

interface StageProgress {
  total: number;
  completed: number;
  failed?: number;
  percent: number;
  status?: string;
  current_task?: {
    filename?: string;
    size?: string;
    section_title?: string;
  };
  total_chunks?: number;
  total_entities?: number;
}

interface SystemStats {
  celery: {
    fast_queue: number;
    slow_queue: number;
    active_tasks?: number;
    worker_hosts?: string[];
  };
  vector_db: {
    total_chunks: number;
  };
  graph_db: {
    total_entities: number;
    total_relationships: number;
  };
  system: {
    cpu_percent: number;
    memory_used_mb: number;
    memory_total_mb: number;
  };
}

interface ProjectProgress {
  id: string;
  name: string;
  priority: number;
  is_paused?: number;
  createdAt?: string;
  vectorization: StageProgress;
  graph_rag: StageProgress;
  community_summary: StageProgress;
  precompute: Record<string, StageProgress>;
}

export default function LearningProgress() {
  const { getAuthHeaders } = useAuthStore();
  const [projects, setProjects] = useState<ProjectProgress[]>([]);
  const [systemStats, setSystemStats] = useState<SystemStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  
  const [failedFiles, setFailedFiles] = useState<{filename: string, stage: string, error: string}[] | null>(null);
  const [loadingFailedFiles, setLoadingFailedFiles] = useState(false);
  const [selectedProjectId, setSelectedProjectId] = useState<string | null>(null);
  const [selectedProjectName, setSelectedProjectName] = useState<string | null>(null);
  const [activeGraphProject, setActiveGraphProject] = useState<string | null>(null);

  const sortedProjects = useMemo(() => {
    return [...projects].sort((a, b) => {
      const pA = a.priority ?? 2;
      const pB = b.priority ?? 2;
      if (pA !== pB) {
        return pA - pB; // 数值越小越靠前 (如 1级优先于 2级)
      }
      // 相同优先级时，创建时间最近优先 (降序)
      const dateA = a.createdAt || '';
      const dateB = b.createdAt || '';
      return dateB.localeCompare(dateA);
    });
  }, [projects]);

  const summaryData = useMemo(() => {
    if (projects.length === 0) return null;

    let totalProjects = projects.length;
    let totalVectorFiles = 0, completedVectorFiles = 0;
    let totalGraphFiles = 0, completedGraphFiles = 0;
    let totalSummaryFiles = 0, completedSummaryFiles = 0;
    let totalPrecomputeTasks = 0, completedPrecomputeTasks = 0;

    projects.forEach((p) => {
      totalVectorFiles += p.vectorization.total || 0;
      completedVectorFiles += p.vectorization.completed || 0;

      totalGraphFiles += p.graph_rag.total || 0;
      completedGraphFiles += p.graph_rag.completed || 0;

      totalSummaryFiles += p.community_summary.total || 0;
      completedSummaryFiles += p.community_summary.completed || 0;

      if (p.precompute) {
        Object.values(p.precompute).forEach((s) => {
          totalPrecomputeTasks += s.total || 0;
          completedPrecomputeTasks += s.completed || 0;
        });
      }
    });

    const vectorPercent = totalVectorFiles > 0 ? (completedVectorFiles / totalVectorFiles) * 100 : 0;
    const graphPercent = totalGraphFiles > 0 ? (completedGraphFiles / totalGraphFiles) * 100 : 0;
    const summaryPercent = totalSummaryFiles > 0 ? (completedSummaryFiles / totalSummaryFiles) * 100 : 0;
    const precomputePercent = totalPrecomputeTasks > 0 ? (completedPrecomputeTasks / totalPrecomputeTasks) * 100 : 0;

    const overallPercent = (vectorPercent + graphPercent + summaryPercent + precomputePercent) / 4;

    return {
      totalProjects,
      vector: { completed: completedVectorFiles, total: totalVectorFiles, percent: vectorPercent },
      graph: { completed: completedGraphFiles, total: totalGraphFiles, percent: graphPercent },
      summary: { completed: completedSummaryFiles, total: totalSummaryFiles, percent: summaryPercent },
      precompute: { completed: completedPrecomputeTasks, total: totalPrecomputeTasks, percent: precomputePercent },
      overallPercent
    };
  }, [projects]);



  const handleUpdatePriority = async (projectId: string, priority: number) => {
    try {
      const res = await fetch(`${API_BASE}/api/admin/projects/${projectId}`, {
        method: 'PUT',
        headers: {
          ...getAuthHeaders(),
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({ priority })
      });
      if (res.ok) {
        setProjects(prev => prev.map(p => p.id === projectId ? { ...p, priority } : p));
      } else {
        const data = await res.json();
        alert(`修改优先级失败: ${data.detail || '未知错误'}`);
      }
    } catch (e) {
      alert(`修改优先级失败: ${e}`);
    }
  };

  const handleTogglePause = async (projectId: string, currentPaused: number) => {
    const nextPaused = currentPaused === 1 ? 0 : 1;
    try {
      const res = await fetch(`${API_BASE}/api/admin/projects/${projectId}`, {
        method: 'PUT',
        headers: {
          ...getAuthHeaders(),
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({ is_paused: nextPaused })
      });
      if (res.ok) {
        setProjects(prev => prev.map(p => p.id === projectId ? { ...p, is_paused: nextPaused } : p));
      } else {
        const data = await res.json();
        alert(`操作失败: ${data.detail || '未知错误'}`);
      }
    } catch (e) {
      alert(`操作失败: ${e}`);
    }
  };

  const getProjectStatusLabel = (p: ProjectProgress) => {
    if (p.is_paused) {
      return { text: "暂停中", className: "bg-amber-50 text-amber-700 border-amber-200" };
    }
    const isSummaryRunning = p.community_summary.status === "running";
    
    const hasPendingVector = p.vectorization.completed < (p.vectorization.total - (p.vectorization.failed || 0)) && !p.vectorization.current_task;
    const hasPendingGraph = p.graph_rag.status === "pending" || p.graph_rag.status === "queued";
    
    if (p.vectorization.current_task || p.graph_rag.current_task || isSummaryRunning) {
      return { text: "学习中", className: "bg-emerald-50 text-emerald-700 border-emerald-200 animate-pulse" };
    }
    if (hasPendingVector || hasPendingGraph) {
      return { text: "排队中", className: "bg-blue-50 text-blue-700 border-blue-200" };
    }
    const isAllDone = p.vectorization.completed >= (p.vectorization.total - (p.vectorization.failed || 0)) && 
                      p.graph_rag.completed >= (p.graph_rag.total - (p.graph_rag.failed || 0));
    if (isAllDone) {
      return { text: "已完成", className: "bg-gray-50 text-gray-600 border-gray-200" };
    }
    return { text: "排队中", className: "bg-blue-50 text-blue-700 border-blue-200" };
  };
  
  const handleViewFailedFiles = async (projectId: string, projectName: string) => {
    setSelectedProjectId(projectId);
    setSelectedProjectName(projectName);
    setLoadingFailedFiles(true);
    setFailedFiles(null);
    try {
      const res = await fetch(`${API_BASE}/api/admin/projects/${projectId}/failed-files`, {
        headers: getAuthHeaders()
      });
      if (res.ok) {
        setFailedFiles(await res.json());
      } else {
        setFailedFiles([]);
      }
    } catch (e) {
      setFailedFiles([]);
    } finally {
      setLoadingFailedFiles(false);
    }
  };

  const copyFailedFiles = () => {
    if (!failedFiles) return;
    const text = failedFiles.map(f => f.filename).join('\\n');
    navigator.clipboard.writeText(text);
    alert('已复制失败文件名列表！');
  };

  const handleRetryFile = async (filename: string, stage: string) => {
    if (!selectedProjectId) return;
    try {
      const res = await fetch(`${API_BASE}/api/admin/projects/${selectedProjectId}/failed-files/retry`, {
        method: 'POST',
        headers: {
          ...getAuthHeaders(),
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({ filename, stage })
      });
      if (res.ok) {
        alert('重新执行任务已下发！请稍候刷新看板。');
        // 可选：将该文件从列表中移除
        setFailedFiles(prev => prev ? prev.filter(f => f.filename !== filename) : null);
        fetchProgress();
      } else {
        const err = await res.json();
        alert(`重新执行失败: ${err.detail || '未知错误'}`);
      }
    } catch (e) {
      alert('请求异常，请检查网络');
    }
  };

  const fetchProgress = async () => {
    try {
      const res = await fetch(`${API_BASE}/api/admin/learning-progress`, {
        headers: getAuthHeaders()
      });
      if (!res.ok) throw new Error('拉取进度失败');
      const data = await res.json();
      setProjects(data);
    } catch (err: any) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  const fetchSystemStats = async () => {
    try {
      const res = await fetch(`${API_BASE}/api/admin/system-stats`, {
        headers: getAuthHeaders()
      });
      if (res.ok) {
        setSystemStats(await res.json());
      }
    } catch (e) {}
  };

  const fetchData = async () => {
    await Promise.all([fetchProgress(), fetchSystemStats()]);
  };

  useEffect(() => {
    fetchData();
    const timer = setInterval(fetchData, 60000); // 每60秒(1分钟)刷新
    return () => clearInterval(timer);
  }, []);

  // WHY: 停止指定项目所有模式的预计算任务
  const handleStopPrecompute = async (projectId: string, projectName: string) => {
    if (!confirm(`确定停止「${projectName}」的所有预计算任务？\n正在运行的章节会被中断。`)) return;
    const modes = ['generate', 'replace', 'clone'];
    let stoppedCount = 0;
    for (const mode of modes) {
      try {
        const res = await fetch(`${API_BASE}/api/exemplar/project/${projectId}/precompute/stop`, {
          method: 'POST',
          headers: { ...getAuthHeaders(), 'Content-Type': 'application/json' },
          body: JSON.stringify({ mode }),
        });
        if (res.ok) stoppedCount++;
      } catch (e) {}
    }
    if (stoppedCount > 0) fetchProgress();
  };

  // WHY: 清除指定项目所有模式的预计算缓存
  const handleClearPrecompute = async (projectId: string, projectName: string) => {
    if (!confirm(`确定清除「${projectName}」的全部预计算缓存？\n已生成的所有章节草稿将被删除，需要重新触发预计算。`)) return;
    try {
      // 先停止运行中的任务
      const modes = ['generate', 'replace', 'clone'];
      for (const mode of modes) {
        await fetch(`${API_BASE}/api/exemplar/project/${projectId}/precompute/stop`, {
          method: 'POST',
          headers: { ...getAuthHeaders(), 'Content-Type': 'application/json' },
          body: JSON.stringify({ mode }),
        }).catch(() => {});
      }
      // 再清除缓存
      const res = await fetch(`${API_BASE}/api/exemplar/project/${projectId}/draft_cache`, {
        method: 'DELETE',
        headers: getAuthHeaders(),
      });
      if (res.ok) {
        fetchProgress();
      } else {
        alert('清除缓存失败');
      }
    } catch (e) {
      alert('请求异常，请检查网络');
    }
  };

  if (loading && projects.length === 0) {
    return <LogoSpinner size={72} overlay={false} />;
  }

  return (
    <div>
      <div className="mb-6">
        <h2 className="text-xl font-bold text-gray-800">学习进度看板</h2>
        <p className="text-sm text-gray-500 mt-1">
          全局监控所有案件的向量化入库、知识图谱提取与智能学习预计算状态
        </p>
      </div>

      {systemStats && (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
          <div className="bg-white/80 backdrop-blur-sm rounded-xl border border-gray-100 p-5 shadow-sm relative overflow-hidden">
            <div className="flex items-center gap-2 mb-3 text-gray-600">
              <Cpu className="w-5 h-5 text-blue-500" />
              <span className="font-semibold text-sm">计算资源利用率</span>
            </div>
            <div className="space-y-3">
              <div>
                <div className="flex justify-between text-xs mb-1">
                  <span className="text-gray-500">CPU 负载</span>
                  <span className="font-medium text-gray-700">{systemStats.system.cpu_percent.toFixed(1)}%</span>
                </div>
                <div className="w-full bg-gray-100 rounded-full h-1.5">
                  <div className={`h-full rounded-full transition-all duration-500 ${systemStats.system.cpu_percent > 80 ? 'bg-red-400' : 'bg-blue-400'}`} style={{ width: `${systemStats.system.cpu_percent}%` }}></div>
                </div>
              </div>
              <div>
                <div className="flex justify-between text-xs mb-1">
                  <span className="text-gray-500">内存占用</span>
                  <span className="font-medium text-gray-700">{(systemStats.system.memory_used_mb / 1024).toFixed(1)}GB / {(systemStats.system.memory_total_mb / 1024).toFixed(1)}GB</span>
                </div>
                <div className="w-full bg-gray-100 rounded-full h-1.5">
                  <div className={`h-full rounded-full transition-all duration-500 ${systemStats.system.memory_used_mb / systemStats.system.memory_total_mb > 0.8 ? 'bg-orange-400' : 'bg-emerald-400'}`} style={{ width: `${(systemStats.system.memory_used_mb / systemStats.system.memory_total_mb) * 100}%` }}></div>
                </div>
              </div>
            </div>
          </div>

          <div className="bg-white/80 backdrop-blur-sm rounded-xl border border-gray-100 p-5 shadow-sm">
            <div className="flex items-center gap-2 mb-3 text-gray-600">
              <Activity className="w-5 h-5 text-orange-500" />
              <span className="font-semibold text-sm">Celery 引擎积压</span>
            </div>
            <div className="flex justify-between items-end h-[52px]">
              <div className="text-center w-1/2 border-r border-gray-100">
                <div className="text-2xl font-bold text-gray-800">{systemStats.celery.fast_queue}</div>
                <div className="text-[10px] text-gray-400 uppercase tracking-wider">快速队列</div>
              </div>
              <div className="text-center w-1/2">
                <div className="text-2xl font-bold text-gray-800">{systemStats.celery.slow_queue}</div>
                <div className="text-[10px] text-gray-400 uppercase tracking-wider">慢速队列</div>
              </div>
            </div>
            {/* Worker 健康状态 */}
            {systemStats.celery.active_tasks !== undefined && (
              <div className="mt-2 pt-2 border-t border-gray-50 flex items-center justify-between text-[10px] text-gray-400">
                <span>
                  活跃任务: <span className="font-semibold text-gray-600">{systemStats.celery.active_tasks}</span>
                </span>
                <span className="flex items-center gap-1">
                  <span className={`inline-block w-1.5 h-1.5 rounded-full ${(systemStats.celery.worker_hosts?.length ?? 0) > 0 ? 'bg-emerald-400' : 'bg-red-400'}`}></span>
                  {(systemStats.celery.worker_hosts?.length ?? 0) > 0 ? `${systemStats.celery.worker_hosts?.length} Worker` : '离线'}
                </span>
              </div>
            )}
          </div>

          <div className="bg-white/80 backdrop-blur-sm rounded-xl border border-gray-100 p-5 shadow-sm">
            <div className="flex items-center gap-2 mb-3 text-gray-600">
              <Database className="w-5 h-5 text-indigo-500" />
              <span className="font-semibold text-sm">Qdrant 向量切片</span>
            </div>
            <div className="flex flex-col justify-end h-[52px]">
              <div className="text-3xl font-black" style={{
                background: 'linear-gradient(to right, #6366f1, #a855f7)',
                WebkitBackgroundClip: 'text',
                WebkitTextFillColor: 'transparent',
                backgroundClip: 'text',
              }}>
                {systemStats.vector_db.total_chunks.toLocaleString()}
              </div>
              <div className="text-[10px] text-gray-400 uppercase tracking-wider">总切片数</div>
            </div>
          </div>

          <div className="bg-white/80 backdrop-blur-sm rounded-xl border border-gray-100 p-5 shadow-sm">
            <div className="flex items-center gap-2 mb-3 text-gray-600">
              <Network className="w-5 h-5 text-cyan-500" />
              <span className="font-semibold text-sm">Neo4j 知识图谱</span>
            </div>
            <div className="flex justify-between items-end h-[52px]">
              <div className="text-left w-1/2">
                <div className="text-2xl font-bold text-gray-800">{systemStats.graph_db.total_entities.toLocaleString()}</div>
                <div className="text-[10px] text-gray-400 uppercase tracking-wider">总实体数</div>
              </div>
              <div className="text-right w-1/2">
                <div className="text-2xl font-bold text-cyan-600">{systemStats.graph_db.total_relationships.toLocaleString()}</div>
                <div className="text-[10px] text-gray-400 uppercase tracking-wider">总关系数</div>
              </div>
            </div>
          </div>
        </div>
      )}

      {summaryData && (
        <div className="bg-white/80 backdrop-blur-md rounded-2xl border border-gray-200/80 p-6 shadow-sm mb-8 animate-in fade-in slide-in-from-top-4 duration-300">
          <div className="flex items-center gap-2 mb-5 pb-3 border-b border-gray-100">
            <span className="text-lg">📊</span>
            <h3 className="font-bold text-gray-850 text-base">全局综合学习状态</h3>
            <span className="ml-auto text-xs text-gray-400 font-medium">共监控 {summaryData.totalProjects} 个活跃案件</span>
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-12 gap-8 items-center">
            {/* 左侧环形总体进度 */}
            <div className="lg:col-span-4 flex flex-col items-center justify-center bg-gray-50/50 rounded-xl p-5 border border-gray-100 relative overflow-hidden group">
              <div className="absolute top-0 right-0 w-24 h-24 bg-indigo-200/10 rounded-full blur-2xl group-hover:bg-indigo-200/20 transition-all duration-700"></div>
              <div className="absolute bottom-0 left-0 w-20 h-20 bg-cyan-200/10 rounded-full blur-2xl group-hover:bg-cyan-200/20 transition-all duration-700"></div>
              
              <div className="relative w-36 h-36 flex items-center justify-center">
                <svg className="w-full h-full transform -rotate-90">
                  <circle
                    cx="72"
                    cy="72"
                    r="60"
                    stroke="#F3F4F6"
                    strokeWidth="10"
                    fill="transparent"
                  />
                  <circle
                    cx="72"
                    cy="72"
                    r="60"
                    stroke="url(#gradientOverall)"
                    strokeWidth="10"
                    fill="transparent"
                    strokeDasharray={377}
                    strokeDashoffset={377 - (377 * summaryData.overallPercent) / 100}
                    strokeLinecap="round"
                    className="transition-all duration-1000 ease-out"
                  />
                  <defs>
                    <linearGradient id="gradientOverall" x1="0%" y1="0%" x2="100%" y2="100%">
                      <stop offset="0%" stopColor="#6366f1" />
                      <stop offset="50%" stopColor="#8b5cf6" />
                      <stop offset="100%" stopColor="#06b6d4" />
                    </linearGradient>
                  </defs>
                </svg>
                <div className="absolute flex flex-col items-center text-center">
                  <span className="text-3xl font-extrabold text-gray-800 tracking-tight">{summaryData.overallPercent.toFixed(2)}%</span>
                  <span className="text-[10px] text-gray-400 font-bold uppercase tracking-wider mt-0.5">总体学习完成率</span>
                </div>
              </div>
            </div>

            {/* 右侧四个阶段 */}
            <div className="lg:col-span-8 grid grid-cols-1 md:grid-cols-2 gap-4">
              <div className="bg-white rounded-xl border border-gray-100 p-4 shadow-sm hover:shadow-md transition-shadow">
                <div className="flex items-center justify-between mb-2">
                  <div className="flex items-center gap-2">
                    <div className="p-1.5 bg-indigo-50 rounded-lg">
                      <Database className="w-4 h-4 text-indigo-500" />
                    </div>
                    <span className="font-bold text-gray-700 text-xs">1. 向量化入库</span>
                  </div>
                  <span className="text-xs text-gray-400 font-semibold">{summaryData.vector.completed} / {summaryData.vector.total} 文件</span>
                </div>
                <div className="flex items-center gap-3">
                  <div className="flex-1 bg-gray-100 rounded-full h-2 overflow-hidden">
                    <div className="bg-indigo-500 h-full rounded-full transition-all duration-700" style={{ width: `${summaryData.vector.percent}%` }}></div>
                  </div>
                  <span className="text-xs font-bold text-indigo-600 w-12 text-right">{summaryData.vector.percent.toFixed(2)}%</span>
                </div>
              </div>

              <div className="bg-white rounded-xl border border-gray-100 p-4 shadow-sm hover:shadow-md transition-shadow">
                <div className="flex items-center justify-between mb-2">
                  <div className="flex items-center gap-2">
                    <div className="p-1.5 bg-cyan-50 rounded-lg">
                      <Network className="w-4 h-4 text-cyan-500" />
                    </div>
                    <span className="font-bold text-gray-700 text-xs">2. 知识图谱提取</span>
                  </div>
                  <span className="text-xs text-gray-400 font-semibold">{summaryData.graph.completed} / {summaryData.graph.total} 文件</span>
                </div>
                <div className="flex items-center gap-3">
                  <div className="flex-1 bg-gray-100 rounded-full h-2 overflow-hidden">
                    <div className="bg-cyan-500 h-full rounded-full transition-all duration-700" style={{ width: `${summaryData.graph.percent}%` }}></div>
                  </div>
                  <span className="text-xs font-bold text-cyan-600 w-12 text-right">{summaryData.graph.percent.toFixed(2)}%</span>
                </div>
              </div>

              <div className="bg-white rounded-xl border border-gray-100 p-4 shadow-sm hover:shadow-md transition-shadow">
                <div className="flex items-center justify-between mb-2">
                  <div className="flex items-center gap-2">
                    <div className="p-1.5 bg-pink-50 rounded-lg">
                      <Network className="w-4 h-4 text-pink-500" />
                    </div>
                    <span className="font-bold text-gray-700 text-xs">3. 图谱社区摘要</span>
                  </div>
                  <span className="text-xs text-gray-400 font-semibold">{summaryData.summary.completed} / {summaryData.summary.total} 段</span>
                </div>
                <div className="flex items-center gap-3">
                  <div className="flex-1 bg-gray-100 rounded-full h-2 overflow-hidden">
                    <div className="bg-pink-500 h-full rounded-full transition-all duration-700" style={{ width: `${summaryData.summary.percent}%` }}></div>
                  </div>
                  <span className="text-xs font-bold text-pink-600 w-12 text-right">{summaryData.summary.percent.toFixed(2)}%</span>
                </div>
              </div>

              <div className="bg-white rounded-xl border border-gray-100 p-4 shadow-sm hover:shadow-md transition-shadow">
                <div className="flex items-center justify-between mb-2">
                  <div className="flex items-center gap-2">
                    <div className="p-1.5 bg-purple-50 rounded-lg">
                      <BrainCircuit className="w-4 h-4 text-purple-500" />
                    </div>
                    <span className="font-bold text-gray-700 text-xs">4. 智能学习预计算</span>
                  </div>
                  <span className="text-xs text-gray-400 font-semibold">{summaryData.precompute.completed} / {summaryData.precompute.total} 项</span>
                </div>
                <div className="flex items-center gap-3">
                  <div className="flex-1 bg-gray-100 rounded-full h-2 overflow-hidden">
                    <div className="bg-purple-500 h-full rounded-full transition-all duration-700" style={{ width: `${summaryData.precompute.percent}%` }}></div>
                  </div>
                  <span className="text-xs font-bold text-purple-600 w-12 text-right">{summaryData.precompute.percent.toFixed(2)}%</span>
                </div>
              </div>
            </div>
          </div>
        </div>
      )}

      {error && (
        <div className="mb-4 p-3 bg-red-50 text-red-600 rounded-lg flex items-center gap-2 text-sm">
          <AlertCircle className="w-4 h-4" /> {error}
        </div>
      )}

      {sortedProjects.length === 0 ? (
        <div className="bg-white rounded-xl border border-gray-200 p-8 text-center text-gray-500">
          <Database className="w-12 h-12 mx-auto mb-3 text-gray-300" />
          <p>当前没有正在处理或包含有效文档的案件。</p>
        </div>
      ) : (
        <div className="flex flex-col gap-6">
          {sortedProjects.map((p) => (
            <div key={p.id} className="bg-white rounded-xl border border-gray-200 p-6 shadow-sm">
              <div className="flex items-center justify-between border-b border-gray-100 pb-4 mb-5">
                <h3 className="text-lg font-bold text-gray-800 truncate max-w-[50%]" title={p.name}>
                  {p.name}
                </h3>
                <div className="flex items-center gap-3 shrink-0">
                  {/* 1. 暂停/恢复按钮 */}
                  <button
                    onClick={() => handleTogglePause(p.id, p.is_paused || 0)}
                    className={`flex items-center gap-1 px-2.5 py-1 rounded-md text-xs font-bold transition-all border shadow-sm ${
                      p.is_paused === 1
                        ? "bg-amber-50 text-amber-700 border-amber-200 hover:bg-amber-100"
                        : "bg-white text-gray-700 border-gray-200 hover:bg-gray-50"
                    }`}
                    title={p.is_paused === 1 ? "恢复学习" : "暂停学习"}
                  >
                    {p.is_paused === 1 ? (
                      <>
                        <Play className="w-3 h-3 fill-current" />
                        <span>恢复</span>
                      </>
                    ) : (
                      <>
                        <Pause className="w-3 h-3 fill-current" />
                        <span>暂停</span>
                      </>
                    )}
                  </button>

                  {/* 2. 优先级下拉框 */}
                  <div className="flex items-center gap-1.5 bg-gray-50 border border-gray-100 rounded-md px-2 py-1 shadow-sm">
                    <span className="text-[10px] text-gray-400 font-bold uppercase tracking-wider">优先级</span>
                    <select
                      value={p.priority || 2}
                      onChange={(e) => handleUpdatePriority(p.id, parseInt(e.target.value))}
                      className="bg-transparent text-xs font-bold text-indigo-600 focus:outline-none cursor-pointer"
                    >
                      <option value="1">1级</option>
                      <option value="2">2级</option>
                      <option value="3">3级</option>
                    </select>
                  </div>

                  {/* 3. 状态显示 Label */}
                  {(() => {
                    const label = getProjectStatusLabel(p);
                    return (
                      <span className={`px-2 py-1 rounded-md text-xs font-bold border shadow-sm ${label.className}`}>
                        {label.text}
                      </span>
                    );
                  })()}

                  {/* 4. 查看异常按钮 */}
                  {((p.vectorization.failed || 0) > 0 || (p.graph_rag.failed || 0) > 0) && (
                    <button
                      onClick={() => handleViewFailedFiles(p.id, p.name)}
                      className="flex items-center gap-1 px-3 py-1 bg-red-50 text-red-600 rounded-md text-xs font-semibold hover:bg-red-100 transition-all border border-red-100 shadow-sm"
                    >
                      <AlertTriangle className="w-3.5 h-3.5" />
                      查看异常
                    </button>
                  )}
                </div>
              </div>

              <div className="grid grid-cols-1 lg:grid-cols-4 gap-8">
                {/* 1. 向量化入库 */}
                <div className="flex flex-col">
                  <div className="flex items-center justify-between mb-2">
                    <div className="flex items-center gap-2">
                      <Database className="w-4 h-4 text-indigo-500" />
                      <span className="font-semibold text-gray-700 text-sm">1. 向量化入库</span>
                    </div>
                    {p.vectorization.total_chunks !== undefined && (
                      <span className="px-2 py-0.5 rounded-md bg-indigo-50 text-indigo-700 text-[10px] font-medium border border-indigo-100/80 shadow-sm">
                        {p.vectorization.total_chunks.toLocaleString()} 切片
                      </span>
                    )}
                  </div>
                  <div className="flex justify-between text-xs text-gray-500 mb-2">
                    <span className="truncate pr-2 max-w-[70%]">
                      {p.vectorization.current_task ? (
                        <span className="flex items-center text-indigo-600 font-medium" title={p.vectorization.current_task.filename}>
                          <Loader2 className="w-3 h-3 mr-1 animate-spin shrink-0" />
                          <span className="truncate">正在处理: {p.vectorization.current_task.filename}</span>
                          <span className="ml-1 shrink-0">({p.vectorization.current_task.size})</span>
                        </span>
                      ) : (
                        p.vectorization.percent >= 100 ? '索引构建完成' : '切片向量化中...'
                      )}
                    </span>
                    <div className="flex items-center gap-2">
                      {p.vectorization.failed !== undefined && p.vectorization.failed > 0 && (
                        <span className="text-red-500 font-bold text-[11px]">{p.vectorization.failed} 失败</span>
                      )}
                      <span className="font-medium text-gray-600 whitespace-nowrap shrink-0">{p.vectorization.completed} / {p.vectorization.total}</span>
                    </div>
                  </div>
                  <div className="w-full bg-gray-100 rounded-full h-2 overflow-hidden relative">
                    <div className={`h-full transition-all duration-500 ${p.vectorization.percent >= 100 ? 'bg-indigo-500' : 'bg-indigo-400'}`} style={{ width: `${p.vectorization.percent}%` }}>
                      {p.vectorization.percent < 100 && <div className="absolute inset-0 bg-white/20 animate-pulse"></div>}
                    </div>
                  </div>
                  <div className="mt-1.5 text-right text-xs font-bold text-gray-400">{p.vectorization.percent.toFixed(2)}%</div>
                </div>

                {/* 2. 知识图谱提取 */}
                <div className="flex flex-col">
                  <div className="flex items-center justify-between mb-2">
                    <div className="flex items-center gap-2">
                      <Network className="w-4 h-4 text-cyan-500" />
                      <span className="font-semibold text-gray-700 text-sm">2. 知识图谱提取</span>
                    </div>
                    {p.graph_rag.total_entities !== undefined && (
                      <span className="px-2 py-0.5 rounded-md bg-emerald-50 text-emerald-700 text-[10px] font-medium border border-emerald-100/80 shadow-sm">
                        {p.graph_rag.total_entities.toLocaleString()} 实体
                      </span>
                    )}
                  </div>
                  <div className="flex justify-between text-xs text-gray-500 mb-2">
                    <span className="truncate pr-2 max-w-[70%]">
                      {p.graph_rag.current_task ? (
                        <span className="flex items-center text-cyan-600 font-medium" title={p.graph_rag.current_task.filename}>
                          <Loader2 className="w-3 h-3 mr-1 animate-spin shrink-0" />
                          <span className="truncate">正在提取: {p.graph_rag.current_task.filename}</span>
                          <span className="ml-1 shrink-0">({p.graph_rag.current_task.size})</span>
                        </span>
                      ) : (
                        p.graph_rag.status === 'pending' ? '等待向量化完成' : (p.graph_rag.percent >= 100 ? '实体关系提取完毕' : '构建节点与网络中...')
                      )}
                    </span>
                    <div className="flex items-center gap-2">
                      {p.graph_rag.failed !== undefined && p.graph_rag.failed > 0 && (
                        <span className="text-red-500 font-bold text-[11px]">{p.graph_rag.failed} 失败</span>
                      )}
                      <span className="font-medium text-gray-600 whitespace-nowrap shrink-0">{p.graph_rag.completed} / {p.graph_rag.total}</span>
                    </div>
                  </div>
                  <div className="w-full bg-gray-100 rounded-full h-2 overflow-hidden relative">
                    <div className={`h-full transition-all duration-500 ${p.graph_rag.percent >= 100 ? 'bg-cyan-500' : 'bg-cyan-400'}`} style={{ width: `${p.graph_rag.percent}%` }}>
                      {p.graph_rag.status === 'processing' && <div className="absolute inset-0 bg-white/20 animate-pulse"></div>}
                    </div>
                  </div>
                  <div className="mt-1.5 text-right text-xs font-bold text-gray-400">{p.graph_rag.percent.toFixed(2)}%</div>
                </div>

                {/* 3. 图谱社区摘要 */}
                <div className="flex flex-col">
                  <div className="flex items-center justify-between mb-2">
                    <div className="flex items-center gap-2">
                      <Network className="w-4 h-4 text-pink-500" />
                      <span className="font-semibold text-gray-700 text-sm">3. 图谱社区摘要</span>
                    </div>
                  </div>
                  <div className="flex justify-between text-xs text-gray-500 mb-2">
                    <span className="truncate pr-2 max-w-[70%]">
                      {p.community_summary.current_task ? (
                        <span className="flex items-center text-pink-600 font-medium" title={p.community_summary.current_task.filename}>
                          <Loader2 className="w-3 h-3 mr-1 animate-spin shrink-0" />
                          <span className="truncate">正在提炼: {p.community_summary.current_task.filename}</span>
                        </span>
                      ) : (
                        p.community_summary.status === 'pending' ? '等待图谱提取完成' : (p.community_summary.percent >= 100 ? '全局知识摘要完毕' : '分析节点簇群中...')
                      )}
                    </span>
                    <div className="flex items-center gap-2">
                      {p.community_summary.failed !== undefined && p.community_summary.failed > 0 && (
                        <span className="text-red-500 font-bold text-[11px]">{p.community_summary.failed} 失败</span>
                      )}
                      <span className="font-medium text-gray-600 whitespace-nowrap shrink-0">{p.community_summary.completed} / {p.community_summary.total}</span>
                    </div>
                  </div>
                  <div className="w-full bg-gray-100 rounded-full h-2 overflow-hidden relative">
                    <div className={`h-full transition-all duration-500 ${p.community_summary.percent >= 100 ? 'bg-pink-500' : 'bg-pink-400'}`} style={{ width: `${p.community_summary.percent}%` }}>
                      {p.community_summary.status === 'processing' && <div className="absolute inset-0 bg-white/20 animate-pulse"></div>}
                    </div>
                  </div>
                  <div className="mt-1.5 text-right text-xs font-bold text-gray-400">{p.community_summary.percent.toFixed(2)}%</div>
                </div>

                {/* 4. 智能学习预计算（三模式） */}
                <div className="flex flex-col">
                  <div className="flex items-center justify-between mb-2">
                    <div className="flex items-center gap-2">
                      <BrainCircuit className="w-4 h-4 text-purple-500" />
                      <span className="font-semibold text-gray-700 text-sm">4. 智能学习预计算</span>
                    </div>
                    <div className="flex items-center gap-1">
                      {/* 停止按钮：任一模式 running 时显示 */}
                      {Object.values(p.precompute || {}).some((s: any) => s.status === 'running') && (
                        <button
                          onClick={(e) => { e.stopPropagation(); handleStopPrecompute(p.id, p.name); }}
                          title="停止所有预计算任务"
                          className="p-1 text-orange-500 hover:text-orange-700 hover:bg-orange-50 rounded transition-colors"
                        >
                          <Square className="w-3.5 h-3.5" />
                        </button>
                      )}
                      {/* 清除按钮：任一模式有已完成的缓存时显示 */}
                      {Object.values(p.precompute || {}).some((s: any) => s.completed > 0) && (
                        <button
                          onClick={(e) => { e.stopPropagation(); handleClearPrecompute(p.id, p.name); }}
                          title="清除全部预计算缓存"
                          className="p-1 text-red-400 hover:text-red-600 hover:bg-red-50 rounded transition-colors"
                        >
                          <Trash2 className="w-3.5 h-3.5" />
                        </button>
                      )}
                    </div>
                  </div>
                  <div className="space-y-1.5">
                    {(['generate', 'replace', 'clone'] as const).map((mode) => {
                      const s = (p.precompute as Record<string, StageProgress>)?.[mode];
                      if (!s) return null;
                      const modeLabel: Record<string, string> = { generate: '全文生成', replace: '智能替换', clone: '精确复刻' };
                      const modeColor: Record<string, string> = { generate: 'purple', replace: 'teal', clone: 'amber' };
                      const c = modeColor[mode] || 'gray';
                      return (
                        <div key={mode}>
                          <div className="flex justify-between text-[10px] text-gray-500 mb-0.5">
                            <span className="truncate">
                              {s.current_task?.section_title ? (
                                <span className={`flex items-center text-${c}-600 font-medium`}>
                                  <Loader2 className="w-2.5 h-2.5 mr-1 animate-spin shrink-0" />
                                  <span className="truncate">{modeLabel[mode]}: {s.current_task.section_title}</span>
                                </span>
                              ) : (
                                <span>{modeLabel[mode]}: {s.status === 'running' ? 'GPU计算中' : s.percent >= 100 && s.completed > 0 ? '✅完成' : s.total === 0 ? '未配置' : '待触发'}</span>
                              )}
                            </span>
                            <span className="font-medium text-gray-600 whitespace-nowrap shrink-0">{s.completed}/{s.total}</span>
                          </div>
                          <div className="w-full bg-gray-100 rounded-full h-1.5 overflow-hidden relative">
                            <div className={`h-full transition-all duration-500 bg-${c}-400`} style={{ width: `${s.percent}%` }}>
                              {s.status === 'running' && <div className="absolute inset-0 bg-white/20 animate-pulse"></div>}
                            </div>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                  <div className="mt-1.5 flex justify-between items-center text-xs font-bold text-gray-400">
                    <button 
                      onClick={() => setActiveGraphProject(activeGraphProject === p.id ? null : p.id)}
                      className="text-cyan-600 hover:text-cyan-700 font-medium flex items-center gap-1 bg-cyan-50 px-2 py-0.5 rounded transition-colors border border-cyan-100"
                    >
                      <Eye className="w-3.5 h-3.5" />
                      {activeGraphProject === p.id ? '收起图谱可视化' : '预览知识图谱星空图'}
                    </button>
                  </div>
                </div>
              </div>
              
              {/* 图谱可视化展示区 */}
              {activeGraphProject === p.id && (
                <div className="mt-6 pt-6 border-t border-gray-100 animate-in fade-in slide-in-from-top-4 duration-300">
                  <GraphVisualizer projectId={p.id} />
                </div>
              )}
            </div>
          ))}
        </div>
      )}

      {/* Failed Files Modal */}
      {selectedProjectId && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm p-4">
          <div className="bg-white rounded-2xl shadow-xl w-full max-w-3xl flex flex-col max-h-[85vh] overflow-hidden">
            <div className="flex items-center justify-between px-6 py-4 border-b border-gray-100 bg-gray-50/50">
              <div className="flex items-center gap-2">
                <AlertTriangle className="w-5 h-5 text-red-500" />
                <h3 className="text-lg font-bold text-gray-800">失败详情 ({selectedProjectName})</h3>
              </div>
              <button 
                onClick={() => setSelectedProjectId(null)}
                className="p-2 text-gray-400 hover:text-gray-600 hover:bg-gray-100 rounded-lg transition-colors"
              >
                <X className="w-5 h-5" />
              </button>
            </div>
            
            <div className="flex-1 overflow-y-auto p-6">
              {loadingFailedFiles ? (
                <div className="flex flex-col items-center justify-center py-12 text-gray-400">
                  <Loader2 className="w-8 h-8 animate-spin mb-3" />
                  <p>正在读取底层状态文件...</p>
                </div>
              ) : failedFiles && failedFiles.length > 0 ? (
                <div className="overflow-x-auto">
                  <table className="w-full text-sm text-left">
                    <thead className="text-xs text-gray-500 uppercase bg-gray-50/80 sticky top-0">
                      <tr>
                        <th className="px-4 py-3 font-semibold rounded-tl-lg">文件名</th>
                        <th className="px-4 py-3 font-semibold w-32">失败阶段</th>
                        <th className="px-4 py-3 font-semibold">错误信息</th>
                        <th className="px-4 py-3 font-semibold w-24 text-right rounded-tr-lg">操作</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-gray-100">
                      {failedFiles.map((f, i) => (
                        <tr key={i} className="hover:bg-red-50/30 transition-colors">
                          <td className="px-4 py-3 font-medium text-gray-800">{f.filename}</td>
                          <td className="px-4 py-3 text-gray-600 whitespace-nowrap">
                            <span className="px-2 py-1 bg-gray-100 rounded text-[11px]">{f.stage}</span>
                          </td>
                          <td className="px-4 py-3 text-red-600/90 max-w-[200px] break-words text-xs">{f.error}</td>
                          <td className="px-4 py-3 text-right">
                            <button
                              onClick={() => handleRetryFile(f.filename, f.stage)}
                              className="px-2.5 py-1 text-[11px] font-semibold text-white bg-indigo-500 hover:bg-indigo-600 rounded shadow-sm transition-colors"
                            >
                              重试
                            </button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              ) : (
                <div className="text-center py-12 text-gray-500">
                  <p>没有找到失败的文件记录。</p>
                </div>
              )}
            </div>
            
            <div className="px-6 py-4 border-t border-gray-100 bg-gray-50 flex justify-end gap-3">
              <button
                onClick={() => setSelectedProjectId(null)}
                className="px-4 py-2 text-sm font-medium text-gray-600 bg-white border border-gray-200 rounded-lg hover:bg-gray-50 transition-colors shadow-sm"
              >
                关闭
              </button>
              {failedFiles && failedFiles.length > 0 && (
                <button
                  onClick={copyFailedFiles}
                  className="flex items-center gap-1.5 px-4 py-2 text-sm font-medium text-white bg-indigo-600 rounded-lg hover:bg-indigo-700 transition-colors shadow-sm"
                >
                  <Copy className="w-4 h-4" />
                  复制全部文件名
                </button>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
