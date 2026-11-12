import { useState, useEffect, useCallback } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import {
  FolderKanban,
  Image as ImageIcon,
  Video,
  FileAudio,
  FileText,
  Smartphone,
  Sparkles,
  Eye,
  RefreshCw,
  Trash2,
  Search,
  ExternalLink,
  Loader2,
  CheckCircle2,
  AlertCircle,
  X,
  Download,
  Layers,
} from 'lucide-react';
import { useAuthStore } from '../../store/authStore';

const API_BASE = import.meta.env.VITE_API_BASE || '';

interface ProjectOverviewItem {
  id: string;
  name: string;
  icon: string;
  project_type: string;
  visibility: string;
  owner_name: string;
  created_at: string;
  stats: {
    total: number;
    image_count: number;
    video_count: number;
    audio_count: number;
    document_count: number;
    mobile_count: number;
    analyzed_count: number;
    processing_count: number;
    failed_count: number;
    total_chunks: number;
    latest_upload_at: string;
  };
}

interface OverviewTotals {
  project_count: number;
  total_materials: number;
  total_images: number;
  total_videos: number;
  total_audios: number;
  total_documents: number;
  total_mobile: number;
  total_analyzed: number;
}

interface MaterialItem {
  file_id: string;
  project_id: string;
  filename: string;
  sub_folder: string;
  media_category: 'image' | 'video' | 'audio' | 'document';
  mime_type: string;
  size: number;
  upload_source: string;
  remark: string;
  uploader_name: string;
  created_at: string;
  updated_at: string;
  ingest_status: string;
  status_label: string;
  chunks: number;
  error_message: string;
  graph_info: string;
  analysis_preview: string;
}

interface AnalysisDetail {
  file_id: string;
  project_id: string;
  filename: string;
  media_category: string;
  mime_type: string;
  size: number;
  upload_source: string;
  remark: string;
  uploader_name: string;
  created_at: string;
  ingest_status: string;
  status_label: string;
  chunks_count: number;
  error_message: string;
  extracted_text: string;
  chunks: { chunk_index: number | string; content: string }[];
}

function formatBytes(bytes: number): string {
  if (bytes >= 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(2)} MB`;
  if (bytes >= 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${bytes} B`;
}

function formatTime(iso: string): string {
  if (!iso) return '-';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso.slice(0, 16).replace('T', ' ');
  return d.toLocaleString('zh-CN', { hour12: false });
}

export default function MaterialManagement() {
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const { getAuthHeaders } = useAuthStore();

  const [totals, setTotals] = useState<OverviewTotals | null>(null);
  const [projects, setProjects] = useState<ProjectOverviewItem[]>([]);
  const [projectKeyword, setProjectKeyword] = useState('');
  const [selectedProjectId, setSelectedProjectId] = useState<string>(
    searchParams.get('project_id') || ''
  );
  const [loadingOverview, setLoadingOverview] = useState(true);

  const [materials, setMaterials] = useState<MaterialItem[]>([]);
  const [loadingMaterials, setLoadingMaterials] = useState(false);
  const [mediaFilter, setMediaFilter] = useState<string>('all');
  const [sourceFilter, setSourceFilter] = useState<string>('all');
  const [searchQuery, setSearchQuery] = useState<string>('');

  const [notice, setNotice] = useState<{ type: 'success' | 'error' | 'info'; text: string } | null>(
    null
  );

  // 原件预览弹窗状态
  const [previewTarget, setPreviewTarget] = useState<MaterialItem | null>(null);
  const [previewBlobUrl, setPreviewBlobUrl] = useState<string | null>(null);
  const [previewLoading, setPreviewLoading] = useState(false);

  // AI 分析详情弹窗状态
  const [analysisTarget, setAnalysisTarget] = useState<AnalysisDetail | null>(null);
  const [analysisModalOpen, setAnalysisModalOpen] = useState(false);
  const [analysisLoading, setAnalysisLoading] = useState(false);

  // 删除确认弹窗状态（不使用原生 confirm）
  const [deleteTarget, setDeleteTarget] = useState<MaterialItem | null>(null);
  const [deleting, setDeleting] = useState(false);

  const fetchOverview = useCallback(async () => {
    setLoadingOverview(true);
    try {
      const res = await fetch(`${API_BASE}/api/mobile/admin/overview`, {
        headers: getAuthHeaders(),
      });
      if (res.ok) {
        const data = await res.json();
        const list: ProjectOverviewItem[] = data.projects || [];
        setTotals(data.totals || null);
        setProjects(list);
        setSelectedProjectId((prev) => {
          if (prev && list.some((p) => p.id === prev)) return prev;
          const withFiles = list.find((p) => p.stats.total > 0);
          return withFiles ? withFiles.id : (list[0]?.id || '');
        });
      }
    } catch {
      setNotice({ type: 'error', text: '加载全项目资料汇总失败' });
    } finally {
      setLoadingOverview(false);
    }
  }, [getAuthHeaders]);

  const fetchProjectMaterials = useCallback(
    async (silent = false) => {
      if (!selectedProjectId) return;
      if (!silent) setLoadingMaterials(true);
      try {
        const params = new URLSearchParams({
          media_category: mediaFilter,
          source: sourceFilter,
          q: searchQuery.trim(),
        });
        const res = await fetch(
          `${API_BASE}/api/mobile/projects/${encodeURIComponent(selectedProjectId)}/materials?${params.toString()}`,
          { headers: getAuthHeaders() }
        );
        if (res.ok) {
          const data = await res.json();
          setMaterials(data.materials || []);
        }
      } catch {
        if (!silent) setNotice({ type: 'error', text: '读取该项目资料列表失败' });
      } finally {
        if (!silent) setLoadingMaterials(false);
      }
    },
    [selectedProjectId, mediaFilter, sourceFilter, searchQuery, getAuthHeaders]
  );

  useEffect(() => {
    void fetchOverview();
  }, [fetchOverview]);

  useEffect(() => {
    if (selectedProjectId) {
      setSearchParams({ project_id: selectedProjectId }, { replace: true });
      void fetchProjectMaterials(false);
    }
  }, [selectedProjectId, mediaFilter, sourceFilter, searchQuery, fetchProjectMaterials, setSearchParams]);

  // 自动轮询正在后台解析中的资料状态
  useEffect(() => {
    const hasPending = materials.some((m) =>
      ['pending', 'processing', 'graph_queued', 'graph_extracting'].includes(m.ingest_status)
    );
    if (!hasPending) return;
    const timer = setInterval(() => {
      void fetchProjectMaterials(true);
    }, 4000);
    return () => clearInterval(timer);
  }, [materials, fetchProjectMaterials]);

  useEffect(() => {
    return () => {
      if (previewBlobUrl) URL.revokeObjectURL(previewBlobUrl);
    };
  }, [previewBlobUrl]);

  const selectedProject = projects.find((p) => p.id === selectedProjectId) || null;
  const filteredProjects = projects.filter((p) =>
    p.name.toLowerCase().includes(projectKeyword.toLowerCase())
  );

  const handleOpenPreview = async (item: MaterialItem) => {
    if (previewBlobUrl) {
      URL.revokeObjectURL(previewBlobUrl);
      setPreviewBlobUrl(null);
    }
    setPreviewTarget(item);
    setPreviewLoading(true);
    try {
      const res = await fetch(
        `${API_BASE}/api/mobile/projects/${encodeURIComponent(item.project_id)}/materials/${encodeURIComponent(item.file_id)}/media`,
        { headers: getAuthHeaders() }
      );
      if (!res.ok) throw new Error('媒体读取失败');
      const raw = await res.blob();
      const typed = new Blob([raw], { type: item.mime_type || raw.type });
      setPreviewBlobUrl(URL.createObjectURL(typed));
    } catch {
      setNotice({ type: 'error', text: '无法加载该资料原件进行预览' });
      setPreviewTarget(null);
    } finally {
      setPreviewLoading(false);
    }
  };

  const handleDownloadFile = async (item: MaterialItem) => {
    try {
      const res = await fetch(
        `${API_BASE}/api/mobile/projects/${encodeURIComponent(item.project_id)}/materials/${encodeURIComponent(item.file_id)}/media`,
        { headers: getAuthHeaders() }
      );
      if (!res.ok) throw new Error('下载失败');
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = item.filename;
      document.body.appendChild(a);
      a.click();
      URL.revokeObjectURL(url);
      document.body.removeChild(a);
    } catch {
      setNotice({ type: 'error', text: '下载资料原件失败' });
    }
  };

  const handleOpenAnalysis = async (item: MaterialItem) => {
    setAnalysisModalOpen(true);
    setAnalysisLoading(true);
    setAnalysisTarget(null);
    try {
      const res = await fetch(
        `${API_BASE}/api/mobile/projects/${encodeURIComponent(item.project_id)}/materials/${encodeURIComponent(item.file_id)}/analysis`,
        { headers: getAuthHeaders() }
      );
      if (!res.ok) throw new Error('查询失败');
      setAnalysisTarget(await res.json());
    } catch {
      setNotice({ type: 'error', text: '获取 AI 多模态分析结果失败' });
      setAnalysisModalOpen(false);
    } finally {
      setAnalysisLoading(false);
    }
  };

  const handleReanalyze = async (item: MaterialItem) => {
    try {
      const res = await fetch(
        `${API_BASE}/api/mobile/projects/${encodeURIComponent(item.project_id)}/materials/${encodeURIComponent(item.file_id)}/reanalyze`,
        { method: 'POST', headers: getAuthHeaders() }
      );
      const data = await res.json().catch(() => ({}));
      if (res.ok) {
        setNotice({ type: 'info', text: data.message || '已重新提交后台多模态解析' });
        void fetchProjectMaterials(true);
      } else {
        setNotice({ type: 'error', text: data.detail || '提交重分析失败' });
      }
    } catch {
      setNotice({ type: 'error', text: '网络请求异常' });
    }
  };

  const confirmDeleteMaterial = async () => {
    if (!deleteTarget) return;
    setDeleting(true);
    try {
      const res = await fetch(
        `${API_BASE}/api/mobile/projects/${encodeURIComponent(deleteTarget.project_id)}/materials/${encodeURIComponent(deleteTarget.file_id)}`,
        { method: 'DELETE', headers: getAuthHeaders() }
      );
      const data = await res.json().catch(() => ({}));
      if (res.ok) {
        setNotice({ type: 'success', text: data.message || '已删除资料并清理向量索引' });
        setDeleteTarget(null);
        await fetchProjectMaterials(false);
        await fetchOverview();
      } else {
        setNotice({ type: 'error', text: data.detail || '删除失败' });
      }
    } catch {
      setNotice({ type: 'error', text: '删除请求网络异常' });
    } finally {
      setDeleting(false);
    }
  };

  return (
    <div className="space-y-6">
      {/* 标题与快捷跳转 */}
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h2 className="text-xl font-bold text-gray-800 flex items-center gap-2">
            <Layers className="w-5 h-5 text-indigo-600" />
            项目资料库管理（按项目查看手机端与多模态资料）
          </h2>
          <p className="text-sm text-gray-500 mt-1">
            集中查看各项目上传的图片、视频、音频与文档资料，在线核验原件及 AI 多模态入库分析结果
          </p>
        </div>

        <div className="flex items-center gap-2.5">
          <button
            type="button"
            onClick={() =>
              navigate(
                selectedProjectId
                  ? `/mobile?project_id=${encodeURIComponent(selectedProjectId)}`
                  : '/mobile'
              )
            }
            className="px-3.5 py-2 rounded-xl bg-indigo-600 hover:bg-indigo-700 text-white text-xs font-semibold flex items-center gap-1.5 shadow-sm cursor-pointer"
          >
            <Smartphone className="w-4 h-4" />
            打开手机端上传入口
          </button>
          <button
            type="button"
            onClick={() => {
              void fetchOverview();
              void fetchProjectMaterials(false);
            }}
            className="px-3.5 py-2 rounded-xl bg-white border border-gray-200 hover:bg-gray-50 text-xs font-medium text-gray-700 flex items-center gap-1.5 cursor-pointer"
          >
            <RefreshCw className="w-3.5 h-3.5" />
            刷新数据
          </button>
        </div>
      </div>

      {/* 通知提示条 */}
      {notice && (
        <div
          className={`px-4 py-3 rounded-xl text-xs flex items-center justify-between border ${
            notice.type === 'success'
              ? 'bg-emerald-50 border-emerald-200 text-emerald-800'
              : notice.type === 'error'
              ? 'bg-rose-50 border-rose-200 text-rose-800'
              : 'bg-indigo-50 border-indigo-200 text-indigo-800'
          }`}
        >
          <div className="flex items-center gap-2">
            {notice.type === 'success' ? (
              <CheckCircle2 className="w-4 h-4 text-emerald-600" />
            ) : (
              <AlertCircle className="w-4 h-4" />
            )}
            <span>{notice.text}</span>
          </div>
          <button onClick={() => setNotice(null)} className="text-gray-400 hover:text-gray-600">
            <X className="w-4 h-4" />
          </button>
        </div>
      )}

      {/* 全局汇总指标卡 */}
      {totals && (
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
          <div className="bg-white rounded-xl border border-gray-200 p-4">
            <p className="text-xs text-gray-500">项目资料库总数</p>
            <p className="text-2xl font-bold text-gray-900 mt-1">{totals.project_count}</p>
          </div>
          <div className="bg-white rounded-xl border border-gray-200 p-4">
            <p className="text-xs text-gray-500">全部归档资料</p>
            <p className="text-2xl font-bold text-indigo-600 mt-1">{totals.total_materials}</p>
          </div>
          <div className="bg-white rounded-xl border border-gray-200 p-4">
            <p className="text-xs text-gray-500">图片资料</p>
            <p className="text-2xl font-bold text-teal-600 mt-1">{totals.total_images}</p>
          </div>
          <div className="bg-white rounded-xl border border-gray-200 p-4">
            <p className="text-xs text-gray-500">视频资料</p>
            <p className="text-2xl font-bold text-amber-600 mt-1">{totals.total_videos}</p>
          </div>
          <div className="bg-white rounded-xl border border-gray-200 p-4">
            <p className="text-xs text-gray-500">手机端采集上传</p>
            <p className="text-2xl font-bold text-blue-600 mt-1">{totals.total_mobile}</p>
          </div>
          <div className="bg-white rounded-xl border border-gray-200 p-4">
            <p className="text-xs text-gray-500">已完成入库分析</p>
            <p className="text-2xl font-bold text-emerald-600 mt-1">{totals.total_analyzed}</p>
          </div>
        </div>
      )}

      {/* 主体双栏：左侧按项目切换，右侧展示该项目对应的全部资料 */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-5 items-start">
        {/* 左侧项目树列表 */}
        <div className="lg:col-span-4 xl:col-span-3 bg-white rounded-2xl border border-gray-200 overflow-hidden">
          <div className="p-3.5 border-b border-gray-100 space-y-2.5">
            <div className="flex items-center justify-between">
              <span className="text-xs font-bold text-gray-700 flex items-center gap-1.5">
                <FolderKanban className="w-4 h-4 text-indigo-500" />
                按项目选择资料库
              </span>
              <span className="text-[11px] text-gray-400">{filteredProjects.length} 个项目</span>
            </div>
            <div className="relative">
              <Search className="w-3.5 h-3.5 text-gray-400 absolute left-3 top-1/2 -translate-y-1/2" />
              <input
                type="text"
                value={projectKeyword}
                onChange={(e) => setProjectKeyword(e.target.value)}
                placeholder="筛选项目名称..."
                className="w-full pl-8 pr-3 py-1.5 rounded-lg bg-gray-50 border border-gray-200 text-xs outline-none focus:border-indigo-400"
              />
            </div>
          </div>

          <div className="max-h-[620px] overflow-y-auto divide-y divide-gray-50">
            {loadingOverview ? (
              <div className="py-12 flex justify-center">
                <Loader2 className="w-5 h-5 animate-spin text-gray-400" />
              </div>
            ) : (
              filteredProjects.map((p) => {
                const active = p.id === selectedProjectId;
                return (
                  <button
                    key={p.id}
                    type="button"
                    onClick={() => setSelectedProjectId(p.id)}
                    className={`w-full px-4 py-3 text-left transition-colors cursor-pointer ${
                      active ? 'bg-indigo-50/90 border-l-4 border-indigo-600' : 'hover:bg-gray-50'
                    }`}
                  >
                    <div className="flex items-center justify-between gap-2">
                      <div className="flex items-center gap-2 min-w-0">
                        <span>{p.icon}</span>
                        <span
                          className={`text-xs font-semibold truncate ${
                            active ? 'text-indigo-700' : 'text-gray-800'
                          }`}
                        >
                          {p.name}
                        </span>
                      </div>
                      <span className="px-2 py-0.5 rounded-full text-[11px] font-bold bg-gray-100 text-gray-700 shrink-0">
                        {p.stats.total}
                      </span>
                    </div>
                    <div className="flex flex-wrap items-center gap-2 mt-1.5 text-[10px] text-gray-500">
                      <span>图片 {p.stats.image_count}</span>
                      <span>· 视频 {p.stats.video_count}</span>
                      {p.stats.mobile_count > 0 && (
                        <span className="text-indigo-600 font-medium">
                          · 📱手机 {p.stats.mobile_count}
                        </span>
                      )}
                    </div>
                  </button>
                );
              })
            )}
          </div>
        </div>

        {/* 右侧：所选项目的资料列表与分析详情 */}
        <div className="lg:col-span-8 xl:col-span-9 bg-white rounded-2xl border border-gray-200 overflow-hidden">
          {selectedProject ? (
            <>
              {/* 项目头部信息与过滤器 */}
              <div className="p-5 border-b border-gray-100 space-y-4">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div>
                    <div className="flex items-center gap-2">
                      <span className="text-xl">{selectedProject.icon}</span>
                      <h3 className="text-base font-bold text-gray-900">{selectedProject.name}</h3>
                      <span className="px-2 py-0.5 rounded-full text-[11px] bg-gray-100 text-gray-600">
                        负责人：{selectedProject.owner_name}
                      </span>
                    </div>
                    <p className="text-xs text-gray-500 mt-1">
                      共 {selectedProject.stats.total} 份资料 · 已入库切片{' '}
                      {selectedProject.stats.total_chunks} 块 · 已完成分析{' '}
                      {selectedProject.stats.analyzed_count} 份
                    </p>
                  </div>

                  <button
                    type="button"
                    onClick={() => navigate(`/project/${encodeURIComponent(selectedProject.id)}`)}
                    className="px-3 py-1.5 rounded-lg border border-indigo-200 bg-indigo-50 hover:bg-indigo-100 text-indigo-700 text-xs font-medium flex items-center gap-1.5 cursor-pointer"
                  >
                    <ExternalLink className="w-3.5 h-3.5" />
                    进入该项目智能研判台
                  </button>
                </div>

                {/* 多维过滤栏 */}
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div className="flex flex-wrap items-center gap-1.5">
                    {[
                      { id: 'all', label: '全部资料' },
                      { id: 'image', label: '图片' },
                      { id: 'video', label: '视频' },
                      { id: 'audio', label: '音频' },
                      { id: 'document', label: '文档' },
                    ].map((t) => (
                      <button
                        key={t.id}
                        type="button"
                        onClick={() => setMediaFilter(t.id)}
                        className={`px-3 py-1.5 rounded-lg text-xs font-medium cursor-pointer ${
                          mediaFilter === t.id
                            ? 'bg-indigo-600 text-white'
                            : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
                        }`}
                      >
                        {t.label}
                      </button>
                    ))}

                    <select
                      value={sourceFilter}
                      onChange={(e) => setSourceFilter(e.target.value)}
                      className="ml-1 px-2.5 py-1.5 rounded-lg bg-gray-100 text-xs text-gray-700 outline-none border border-transparent focus:border-indigo-400"
                    >
                      <option value="all">全部来源</option>
                      <option value="mobile">仅看手机端上传</option>
                      <option value="web">仅看桌面Web上传</option>
                    </select>
                  </div>

                  <div className="relative w-full sm:w-64">
                    <Search className="w-3.5 h-3.5 text-gray-400 absolute left-3 top-1/2 -translate-y-1/2" />
                    <input
                      type="text"
                      value={searchQuery}
                      onChange={(e) => setSearchQuery(e.target.value)}
                      placeholder="搜索文件名、备注或提取内容..."
                      className="w-full pl-8 pr-3 py-1.5 rounded-lg bg-gray-50 border border-gray-200 text-xs outline-none focus:border-indigo-400"
                    />
                  </div>
                </div>
              </div>

              {/* 资料数据表 */}
              {loadingMaterials ? (
                <div className="py-16 flex justify-center">
                  <Loader2 className="w-6 h-6 animate-spin text-indigo-500" />
                </div>
              ) : materials.length === 0 ? (
                <div className="py-16 text-center text-sm text-gray-400">
                  该项目下暂无符合条件的资料记录
                </div>
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full text-xs">
                    <thead className="bg-gray-50 border-b border-gray-200 text-gray-600">
                      <tr>
                        <th className="text-left px-4 py-3 font-semibold">资料名称与备注</th>
                        <th className="text-left px-3 py-3 font-semibold">类型 / 来源</th>
                        <th className="text-left px-3 py-3 font-semibold">大小 / 上传时间</th>
                        <th className="text-left px-3 py-3 font-semibold">知识库分析状态</th>
                        <th className="text-right px-4 py-3 font-semibold">操作</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-gray-100">
                      {materials.map((m) => {
                        const isReady =
                          ['vectorized', 'graph_queued', 'graph_extracting'].includes(
                            m.ingest_status
                          ) || m.chunks > 0;
                        const isRunning = ['pending', 'processing'].includes(m.ingest_status);
                        return (
                          <tr key={m.file_id} className="hover:bg-gray-50/80 align-top">
                            <td className="px-4 py-3.5 max-w-md">
                              <div className="flex items-start gap-2.5">
                                <div
                                  className={`p-2 rounded-lg shrink-0 mt-0.5 ${
                                    m.media_category === 'image'
                                      ? 'bg-teal-50 text-teal-600'
                                      : m.media_category === 'video'
                                      ? 'bg-amber-50 text-amber-600'
                                      : m.media_category === 'audio'
                                      ? 'bg-violet-50 text-violet-600'
                                      : 'bg-blue-50 text-blue-600'
                                  }`}
                                >
                                  {m.media_category === 'image' ? (
                                    <ImageIcon className="w-4 h-4" />
                                  ) : m.media_category === 'video' ? (
                                    <Video className="w-4 h-4" />
                                  ) : m.media_category === 'audio' ? (
                                    <FileAudio className="w-4 h-4" />
                                  ) : (
                                    <FileText className="w-4 h-4" />
                                  )}
                                </div>
                                <div className="min-w-0 space-y-1">
                                  <p className="font-semibold text-gray-900 break-all">
                                    {m.filename}
                                  </p>
                                  {m.sub_folder && (
                                    <p className="text-[11px] text-gray-400">
                                      归档目录：{m.sub_folder}
                                    </p>
                                  )}
                                  {m.remark && (
                                    <p className="text-[11px] text-indigo-700 bg-indigo-50 px-2 py-1 rounded">
                                      现场备注：{m.remark}
                                    </p>
                                  )}
                                  {m.analysis_preview && (
                                    <p className="text-[11px] text-gray-500 line-clamp-2">
                                      分析摘要：{m.analysis_preview}
                                    </p>
                                  )}
                                </div>
                              </div>
                            </td>

                            <td className="px-3 py-3.5 whitespace-nowrap">
                              <div className="space-y-1">
                                <span className="inline-block px-2 py-0.5 rounded bg-gray-100 text-gray-700 font-medium">
                                  {m.media_category === 'image'
                                    ? '图片'
                                    : m.media_category === 'video'
                                    ? '视频'
                                    : m.media_category === 'audio'
                                    ? '音频'
                                    : '文档'}
                                </span>
                                <div>
                                  {m.upload_source === 'mobile' ? (
                                    <span className="inline-flex items-center gap-1 text-[11px] text-indigo-600 font-medium">
                                      <Smartphone className="w-3 h-3" /> 手机端
                                    </span>
                                  ) : (
                                    <span className="text-[11px] text-gray-400">Web端</span>
                                  )}
                                  {m.uploader_name ? (
                                    <span className="text-[11px] text-gray-400">
                                      {' '}
                                      · {m.uploader_name}
                                    </span>
                                  ) : null}
                                </div>
                              </div>
                            </td>

                            <td className="px-3 py-3.5 whitespace-nowrap text-gray-500 space-y-1">
                              <p className="font-medium text-gray-700">{formatBytes(m.size)}</p>
                              <p className="text-[11px]">{formatTime(m.created_at)}</p>
                            </td>

                            <td className="px-3 py-3.5 whitespace-nowrap">
                              <div className="space-y-1">
                                <span
                                  className={`inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-[11px] font-semibold ${
                                    isReady
                                      ? 'bg-emerald-50 text-emerald-700 border border-emerald-200'
                                      : isRunning
                                      ? 'bg-indigo-50 text-indigo-700 border border-indigo-200'
                                      : 'bg-rose-50 text-rose-700 border border-rose-200'
                                  }`}
                                >
                                  {isRunning && <Loader2 className="w-3 h-3 animate-spin" />}
                                  {m.status_label}
                                </span>
                                <p className="text-[11px] text-gray-400">
                                  知识切片：{m.chunks} 块 {m.graph_info ? `· ${m.graph_info}` : ''}
                                </p>
                              </div>
                            </td>

                            <td className="px-4 py-3.5 text-right whitespace-nowrap">
                              <div className="inline-flex items-center gap-1.5">
                                <button
                                  type="button"
                                  onClick={() => void handleOpenPreview(m)}
                                  className="px-2.5 py-1.5 rounded-lg bg-gray-100 hover:bg-gray-200 text-gray-700 font-medium flex items-center gap-1 cursor-pointer"
                                  title="在线预览图片或播放音视频"
                                >
                                  <Eye className="w-3.5 h-3.5" />
                                  预览
                                </button>
                                <button
                                  type="button"
                                  onClick={() => void handleOpenAnalysis(m)}
                                  className="px-2.5 py-1.5 rounded-lg bg-indigo-50 hover:bg-indigo-100 text-indigo-700 font-medium flex items-center gap-1 cursor-pointer"
                                  title="查看知识库多模态提取文本与向量切片"
                                >
                                  <Sparkles className="w-3.5 h-3.5" />
                                  分析详情
                                </button>
                                <button
                                  type="button"
                                  onClick={() => void handleDownloadFile(m)}
                                  className="p-1.5 rounded-lg text-gray-500 hover:bg-gray-100 cursor-pointer"
                                  title="下载原件"
                                >
                                  <Download className="w-3.5 h-3.5" />
                                </button>
                                <button
                                  type="button"
                                  onClick={() => void handleReanalyze(m)}
                                  className="p-1.5 rounded-lg text-indigo-600 hover:bg-indigo-50 cursor-pointer"
                                  title="重新触发多模态分析"
                                >
                                  <RefreshCw className="w-3.5 h-3.5" />
                                </button>
                                <button
                                  type="button"
                                  onClick={() => setDeleteTarget(m)}
                                  className="p-1.5 rounded-lg text-rose-500 hover:bg-rose-50 cursor-pointer"
                                  title="删除该资料"
                                >
                                  <Trash2 className="w-3.5 h-3.5" />
                                </button>
                              </div>
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              )}
            </>
          ) : (
            <div className="py-20 text-center text-gray-400 text-sm">请先在左侧选择一个项目</div>
          )}
        </div>
      </div>

      {/* 原件在线预览模态框 */}
      {previewTarget && (
        <div className="fixed inset-0 z-50 bg-black/75 flex items-center justify-center p-6">
          <div className="bg-white rounded-2xl max-w-4xl w-full max-h-[88vh] flex flex-col overflow-hidden shadow-2xl">
            <div className="px-5 py-3.5 border-b border-gray-200 flex items-center justify-between">
              <div className="min-w-0 pr-4">
                <h4 className="font-bold text-sm text-gray-800 truncate">
                  {previewTarget.filename}
                </h4>
                <p className="text-xs text-gray-400">
                  {formatBytes(previewTarget.size)} · {previewTarget.mime_type}
                </p>
              </div>
              <button
                onClick={() => {
                  if (previewBlobUrl) URL.revokeObjectURL(previewBlobUrl);
                  setPreviewBlobUrl(null);
                  setPreviewTarget(null);
                }}
                className="p-1.5 rounded-lg hover:bg-gray-100 text-gray-500"
              >
                <X className="w-5 h-5" />
              </button>
            </div>
            <div className="flex-1 bg-slate-900 flex items-center justify-center p-4 overflow-auto min-h-[360px]">
              {previewLoading ? (
                <Loader2 className="w-8 h-8 animate-spin text-white" />
              ) : previewBlobUrl ? (
                previewTarget.media_category === 'image' ? (
                  <img
                    src={previewBlobUrl}
                    alt={previewTarget.filename}
                    className="max-h-[70vh] max-w-full object-contain rounded-lg"
                  />
                ) : previewTarget.media_category === 'video' ? (
                  <video
                    src={previewBlobUrl}
                    controls
                    className="max-h-[70vh] max-w-full rounded-lg bg-black"
                  />
                ) : previewTarget.media_category === 'audio' ? (
                  <div className="bg-white rounded-2xl p-8 w-full max-w-md text-center space-y-4">
                    <FileAudio className="w-12 h-12 text-violet-600 mx-auto" />
                    <p className="text-sm font-semibold text-gray-800 break-all">
                      {previewTarget.filename}
                    </p>
                    <audio src={previewBlobUrl} controls className="w-full" />
                  </div>
                ) : previewTarget.mime_type.includes('pdf') ? (
                  <iframe
                    src={previewBlobUrl}
                    title={previewTarget.filename}
                    className="w-full h-[70vh] bg-white rounded-lg"
                  />
                ) : (
                  <div className="bg-white rounded-2xl p-8 text-center space-y-4">
                    <FileText className="w-12 h-12 text-blue-600 mx-auto" />
                    <p className="text-sm text-gray-700">
                      该文档格式建议下载原件或点击「分析详情」直接审阅提取文本
                    </p>
                    <button
                      type="button"
                      onClick={() => void handleDownloadFile(previewTarget)}
                      className="px-4 py-2 rounded-xl bg-indigo-600 text-white text-xs font-semibold"
                    >
                      下载原件
                    </button>
                  </div>
                )
              ) : null}
            </div>
          </div>
        </div>
      )}

      {/* AI 多模态分析详情与向量切片查看器 */}
      {analysisModalOpen && (
        <div className="fixed inset-0 z-50 bg-black/50 flex items-center justify-center p-6">
          <div className="bg-white rounded-2xl max-w-3xl w-full max-h-[86vh] flex flex-col overflow-hidden shadow-2xl">
            <div className="px-6 py-4 border-b border-gray-200 flex items-center justify-between">
              <h4 className="font-bold text-base text-gray-800 flex items-center gap-2">
                <Sparkles className="w-5 h-5 text-indigo-600" />
                知识库多模态分析详情与向量切片
              </h4>
              <button
                onClick={() => setAnalysisModalOpen(false)}
                className="p-1.5 rounded-lg hover:bg-gray-100 text-gray-500"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            <div className="flex-1 overflow-y-auto p-6 space-y-5">
              {analysisLoading ? (
                <div className="py-16 flex justify-center">
                  <Loader2 className="w-7 h-7 animate-spin text-indigo-500" />
                </div>
              ) : analysisTarget ? (
                <>
                  <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 bg-gray-50 rounded-xl p-4 text-xs">
                    <div>
                      <span className="text-gray-400 block">资料名称</span>
                      <span className="font-semibold text-gray-800 break-all">
                        {analysisTarget.filename}
                      </span>
                    </div>
                    <div>
                      <span className="text-gray-400 block">分析状态</span>
                      <span className="font-semibold text-indigo-700">
                        {analysisTarget.status_label}
                      </span>
                    </div>
                    <div>
                      <span className="text-gray-400 block">入库向量切片</span>
                      <span className="font-semibold text-emerald-700">
                        {analysisTarget.chunks_count} 块
                      </span>
                    </div>
                    <div>
                      <span className="text-gray-400 block">上传来源</span>
                      <span className="font-semibold text-gray-800">
                        {analysisTarget.upload_source === 'mobile' ? '📱 手机端上传' : '💻 Web端'}
                      </span>
                    </div>
                  </div>

                  {analysisTarget.remark && (
                    <div className="bg-indigo-50 border border-indigo-100 rounded-xl p-3.5 text-xs text-indigo-900">
                      <span className="font-bold">现场上传备注：</span>
                      {analysisTarget.remark}
                    </div>
                  )}

                  <div>
                    <h5 className="text-xs font-bold text-gray-700 mb-2">
                      多模态识别与转写全文（OCR / Vision 视觉模型 / Whisper 语音转写）
                    </h5>
                    {analysisTarget.extracted_text ? (
                      <pre className="whitespace-pre-wrap break-words text-xs text-gray-800 bg-slate-50 border border-gray-200 rounded-xl p-4 max-h-72 overflow-y-auto font-sans leading-relaxed">
                        {analysisTarget.extracted_text}
                      </pre>
                    ) : (
                      <div className="p-6 rounded-xl bg-gray-50 text-center text-xs text-gray-400">
                        {['pending', 'processing'].includes(analysisTarget.ingest_status)
                          ? '该资料正在后台执行多模态提取与向量化分析，请稍后刷新查看...'
                          : analysisTarget.error_message || '暂未提取到有效文本内容'}
                      </div>
                    )}
                  </div>

                  {analysisTarget.chunks.length > 0 && (
                    <div>
                      <h5 className="text-xs font-bold text-gray-700 mb-2">
                        Qdrant / FTS5 知识库切片明细（共 {analysisTarget.chunks.length} 块）
                      </h5>
                      <div className="space-y-2 max-h-64 overflow-y-auto">
                        {analysisTarget.chunks.map((c, idx) => (
                          <div
                            key={idx}
                            className="p-3 rounded-xl border border-gray-200 bg-white text-xs space-y-1"
                          >
                            <span className="inline-block px-2 py-0.5 rounded bg-indigo-50 text-indigo-700 font-semibold text-[10px]">
                              Chunk #{c.chunk_index}
                            </span>
                            <p className="text-gray-700 whitespace-pre-wrap break-words leading-relaxed">
                              {c.content}
                            </p>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}
                </>
              ) : null}
            </div>
          </div>
        </div>
      )}

      {/* 安全删除确认框 */}
      {deleteTarget && (
        <div className="fixed inset-0 z-50 bg-black/50 flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl max-w-md w-full p-6 space-y-4 shadow-xl">
            <h4 className="font-bold text-base text-gray-900">确认删除项目资料</h4>
            <p className="text-xs text-gray-600 leading-relaxed">
              确定要从当前项目资料库中彻底删除《{deleteTarget.filename}》吗？删除后将同步清理该资料的向量切片与索引数据。
            </p>
            <div className="flex justify-end gap-2.5">
              <button
                type="button"
                onClick={() => setDeleteTarget(null)}
                className="px-4 py-2 rounded-xl bg-gray-100 text-xs font-medium text-gray-700"
              >
                取消
              </button>
              <button
                type="button"
                disabled={deleting}
                onClick={() => void confirmDeleteMaterial()}
                className="px-4 py-2 rounded-xl bg-rose-600 hover:bg-rose-700 text-xs font-semibold text-white disabled:opacity-50"
              >
                {deleting ? '删除中...' : '确认删除'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

