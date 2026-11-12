import React, { useState, useEffect, useRef, useCallback } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import {
  Camera,
  Video,
  Image as ImageIcon,
  FileUp,
  FolderKanban,
  CheckCircle2,
  Loader2,
  AlertCircle,
  AlertTriangle,
  Eye,
  Sparkles,
  RefreshCw,
  Plus,
  LogOut,
  X,
  Trash2,
  Smartphone,
  ShieldCheck,
  FileAudio,
  FileText,
  ChevronDown,
  Search,
  Download,
  ShieldAlert,
  FileCheck2,
} from 'lucide-react';
import { useAuthStore } from '../../store/authStore';

const API_BASE = import.meta.env.VITE_API_BASE || '';

interface MobileProject {
  id: string;
  name: string;
  icon: string;
  project_type: string;
  visibility: string;
  owner_name: string;
  source_count: number;
  can_upload: boolean;
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
  ingest_status: string;
  status_label: string;
  chunks: number;
  error_message: string;
  analysis_preview: string;
  is_garbled?: boolean;
  garbled_reason?: string;
  compliance_status?: 'compliant' | 'warning' | 'violation' | string;
  compliance_score?: number;
}

interface MaterialSummary {
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
}

interface ComplianceReportData {
  compliance_status: 'compliant' | 'warning' | 'violation' | string;
  compliance_label: string;
  compliance_score: number;
  check_type: string;
  summary: string;
  applied_standards?: { title: string; clause: string; requirement: string }[];
  findings?: { item: string; status: 'pass' | 'warning' | 'fail' | string; detail: string }[];
  recommendations?: string[];
  checked_at?: string;
}

interface AnalysisDetail {
  file_id: string;
  project_id?: string;
  filename: string;
  media_category: string;
  mime_type: string;
  size: number;
  remark: string;
  uploader_name: string;
  created_at: string;
  ingest_status: string;
  status_label: string;
  chunks_count: number;
  error_message: string;
  extracted_text: string;
  is_garbled?: boolean;
  garbled_reason?: string;
  compliance_status?: string;
  compliance_score?: number;
  compliance_report?: ComplianceReportData | null;
  compliance_checked_at?: string;
  chunks: { chunk_index: number | string; content: string }[];
}

const PRESET_FOLDERS = ['手机端上传', '现场照片', '视频取证', '录音材料', '文书扫描件'];

function formatBytes(bytes: number): string {
  if (bytes >= 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(2)} MB`;
  if (bytes >= 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${bytes} B`;
}

function formatDateTime(iso: string): string {
  if (!iso) return '';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso.slice(0, 16).replace('T', ' ');
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${d.getMonth() + 1}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

export default function MobileUploadPage() {
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const { user, isLoggedIn, login, logout, getAuthHeaders } = useAuthStore();

  // 登录表单状态（未登录时在手机端就地登录）
  const [loginName, setLoginName] = useState('');
  const [loginPassword, setLoginPassword] = useState('');
  const [loginLoading, setLoginLoading] = useState(false);
  const [loginError, setLoginError] = useState('');

  // 项目与筛选状态
  const [projects, setProjects] = useState<MobileProject[]>([]);
  const [selectedProjectId, setSelectedProjectId] = useState<string>(searchParams.get('project_id') || '');
  const [projectPickerOpen, setProjectPickerOpen] = useState(false);
  const [projectSearch, setProjectSearch] = useState('');
  const [loadingProjects, setLoadingProjects] = useState(false);

  // 新建项目弹窗状态
  const [createProjOpen, setCreateProjOpen] = useState(false);
  const [newProjName, setNewProjName] = useState('');
  const [creatingProj, setCreatingProj] = useState(false);

  // 待上传队列状态
  const [pendingFiles, setPendingFiles] = useState<File[]>([]);
  const [categoryFolder, setCategoryFolder] = useState('手机端上传');
  const [remark, setRemark] = useState('');
  const [uploading, setUploading] = useState(false);
  const [uploadPercent, setUploadPercent] = useState(0);

  // 提示消息横幅（替代原生 alert）
  const [banner, setBanner] = useState<{ type: 'success' | 'error' | 'info'; text: string } | null>(null);

  // 项目已上传资料列表
  const [materials, setMaterials] = useState<MaterialItem[]>([]);
  const [summary, setSummary] = useState<MaterialSummary | null>(null);
  const [categoryFilter, setCategoryFilter] = useState<string>('all');
  const [loadingMaterials, setLoadingMaterials] = useState(false);

  // 原件预览与 AI 分析抽屉
  const [previewItem, setPreviewItem] = useState<MaterialItem | null>(null);
  const [previewBlobUrl, setPreviewBlobUrl] = useState<string | null>(null);
  const [previewLoading, setPreviewLoading] = useState(false);

  const [analysisDetail, setAnalysisDetail] = useState<AnalysisDetail | null>(null);
  const [analysisOpen, setAnalysisOpen] = useState(false);
  const [analysisLoading, setAnalysisLoading] = useState(false);
  const [analysisTab, setAnalysisTab] = useState<'compliance' | 'extraction'>('compliance');
  const [checkingCompliance, setCheckingCompliance] = useState(false);
  const [reanalyzingId, setReanalyzingId] = useState<string | null>(null);

  // 隐藏文件输入引用
  const cameraPhotoRef = useRef<HTMLInputElement>(null);
  const cameraVideoRef = useRef<HTMLInputElement>(null);
  const galleryRef = useRef<HTMLInputElement>(null);
  const docAudioRef = useRef<HTMLInputElement>(null);

  const selectedProject = projects.find((p) => p.id === selectedProjectId) || null;

  const showNotice = useCallback((type: 'success' | 'error' | 'info', text: string) => {
    setBanner({ type, text });
  }, []);

  // 获取项目列表
  const loadProjects = useCallback(async () => {
    if (!isLoggedIn) return;
    setLoadingProjects(true);
    try {
      const res = await fetch(`${API_BASE}/api/mobile/projects`, {
        headers: getAuthHeaders(),
      });
      if (res.status === 401) {
        logout();
        return;
      }
      if (res.ok) {
        const data = await res.json();
        const list: MobileProject[] = data.projects || [];
        setProjects(list);

        setSelectedProjectId((prev) => {
          if (prev && list.some((p) => p.id === prev)) return prev;
          const writable = list.find((p) => p.can_upload);
          return writable ? writable.id : (list[0]?.id || '');
        });
      }
    } catch {
      showNotice('error', '无法连接服务器获取项目列表');
    } finally {
      setLoadingProjects(false);
    }
  }, [isLoggedIn, getAuthHeaders, logout, showNotice]);

  // 获取当前选中项目的资料库列表
  const loadMaterials = useCallback(
    async (silent = false) => {
      if (!isLoggedIn || !selectedProjectId) return;
      if (!silent) setLoadingMaterials(true);
      try {
        const params = new URLSearchParams({
          media_category: categoryFilter,
        });
        const res = await fetch(
          `${API_BASE}/api/mobile/projects/${encodeURIComponent(selectedProjectId)}/materials?${params.toString()}`,
          { headers: getAuthHeaders() }
        );
        if (res.ok) {
          const data = await res.json();
          setMaterials(data.materials || []);
          setSummary(data.summary || null);
        }
      } catch {
        if (!silent) showNotice('error', '加载项目资料列表失败');
      } finally {
        if (!silent) setLoadingMaterials(false);
      }
    },
    [isLoggedIn, selectedProjectId, categoryFilter, getAuthHeaders, showNotice]
  );

  useEffect(() => {
    if (isLoggedIn) {
      void loadProjects();
    }
  }, [isLoggedIn, loadProjects]);

  useEffect(() => {
    if (selectedProjectId) {
      setSearchParams({ project_id: selectedProjectId }, { replace: true });
      void loadMaterials(false);
    }
  }, [selectedProjectId, categoryFilter, loadMaterials, setSearchParams]);

  // 当存在排队或解析中的资料时，每 4 秒自动静默刷新分析状态
  useEffect(() => {
    if (!isLoggedIn || !selectedProjectId) return;
    const hasActiveTask = materials.some((m) =>
      ['pending', 'processing', 'graph_queued', 'graph_extracting'].includes(m.ingest_status)
    );
    if (!hasActiveTask) return;
    const timer = setInterval(() => {
      void loadMaterials(true);
    }, 4000);
    return () => clearInterval(timer);
  }, [isLoggedIn, selectedProjectId, materials, loadMaterials]);

  // 释放预览 Blob URL
  useEffect(() => {
    return () => {
      if (previewBlobUrl) {
        URL.revokeObjectURL(previewBlobUrl);
      }
    };
  }, [previewBlobUrl]);

  const handleMobileLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!loginName.trim() || !loginPassword) {
      setLoginError('请输入登录账号与密码');
      return;
    }
    setLoginLoading(true);
    setLoginError('');
    const result = await login(loginName.trim(), loginPassword);
    setLoginLoading(false);
    if (!result.success) {
      setLoginError(result.error || '登录失败');
    } else {
      setLoginPassword('');
    }
  };

  const handleSafeLogout = () => {
    setProjects([]);
    setMaterials([]);
    setPendingFiles([]);
    logout();
    window.location.href = '/mobile';
  };

  const handleSelectFiles = (e: React.ChangeEvent<HTMLInputElement>) => {
    const chosen = Array.from(e.target.files || []);
    if (chosen.length > 0) {
      setPendingFiles((prev) => [...prev, ...chosen].slice(0, 20));
    }
    e.target.value = '';
  };

  const removePendingFile = (idx: number) => {
    setPendingFiles((prev) => prev.filter((_, i) => i !== idx));
  };

  const handleCreateProject = async () => {
    const trimmed = newProjName.trim();
    if (!trimmed) return;
    setCreatingProj(true);
    try {
      const res = await fetch(`${API_BASE}/api/projects`, {
        method: 'POST',
        headers: { ...getAuthHeaders(), 'Content-Type': 'application/json' },
        body: JSON.stringify({ name: trimmed, visibility: 'public', project_type: 'case' }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        showNotice('error', data.detail || '新建项目失败');
        return;
      }
      setNewProjName('');
      setCreateProjOpen(false);
      await loadProjects();
      if (data.id) {
        setSelectedProjectId(data.id);
      }
      showNotice('success', `项目「${trimmed}」已创建并自动选中`);
    } catch {
      showNotice('error', '新建项目时网络异常');
    } finally {
      setCreatingProj(false);
    }
  };

  // 执行带进度条的多模态上传
  const handleUploadSubmit = () => {
    if (!selectedProjectId) {
      showNotice('error', '请先选择要归档的目标项目');
      return;
    }
    if (pendingFiles.length === 0) {
      showNotice('error', '请先拍摄或选择至少一份图片/视频资料');
      return;
    }

    const formData = new FormData();
    formData.append('project_id', selectedProjectId);
    formData.append('category_folder', categoryFolder.trim() || '手机端上传');
    formData.append('remark', remark.trim());
    pendingFiles.forEach((f) => formData.append('files', f));

    setUploading(true);
    setUploadPercent(0);
    setBanner(null);

    const xhr = new XMLHttpRequest();
    xhr.open('POST', `${API_BASE}/api/mobile/upload`, true);

    const headers = getAuthHeaders();
    Object.entries(headers).forEach(([k, v]) => {
      xhr.setRequestHeader(k, v);
    });

    xhr.upload.onprogress = (ev) => {
      if (ev.lengthComputable) {
        setUploadPercent(Math.round((ev.loaded / ev.total) * 100));
      }
    };

    xhr.onload = () => {
      setUploading(false);
      let respData: { message?: string; detail?: string } = {};
      try {
        respData = JSON.parse(xhr.responseText || '{}');
      } catch {
        respData = {};
      }
      if (xhr.status >= 200 && xhr.status < 300) {
        setPendingFiles([]);
        setRemark('');
        setUploadPercent(100);
        showNotice('success', respData.message || '上传成功，后台已启动多模态智能解析入库');
        void loadMaterials(false);
        void loadProjects();
      } else {
        showNotice('error', respData.detail || `上传失败 (HTTP ${xhr.status})`);
      }
    };

    xhr.onerror = () => {
      setUploading(false);
      showNotice('error', '网络中断，上传未能完成，请检查网络连接');
    };

    xhr.send(formData);
  };

  // 在线安全预览媒体（通过受控 Blob 加载）
  const openMediaPreview = async (item: MaterialItem) => {
    if (previewBlobUrl) {
      URL.revokeObjectURL(previewBlobUrl);
      setPreviewBlobUrl(null);
    }
    setPreviewItem(item);
    setPreviewLoading(true);
    try {
      const res = await fetch(
        `${API_BASE}/api/mobile/projects/${encodeURIComponent(item.project_id)}/materials/${encodeURIComponent(item.file_id)}/media`,
        { headers: getAuthHeaders() }
      );
      if (!res.ok) throw new Error('加载失败');
      const rawBlob = await res.blob();
      const typedBlob = new Blob([rawBlob], { type: item.mime_type || rawBlob.type });
      setPreviewBlobUrl(URL.createObjectURL(typedBlob));
    } catch {
      showNotice('error', '媒体原件读取失败');
      setPreviewItem(null);
    } finally {
      setPreviewLoading(false);
    }
  };

  // 查看 AI 分析与 RAG 规范检测结果
  const openAnalysisSheet = async (item: MaterialItem) => {
    setAnalysisOpen(true);
    setAnalysisLoading(true);
    setAnalysisDetail(null);
    setAnalysisTab(item.compliance_status ? 'compliance' : 'extraction');
    try {
      const res = await fetch(
        `${API_BASE}/api/mobile/projects/${encodeURIComponent(item.project_id)}/materials/${encodeURIComponent(item.file_id)}/analysis`,
        { headers: getAuthHeaders() }
      );
      if (!res.ok) throw new Error('查询失败');
      const data: AnalysisDetail = await res.json();
      data.project_id = item.project_id;
      setAnalysisDetail(data);
      // 如果已存在规范检测报告，默认切到规范检测 Tab
      if (data.compliance_status || data.compliance_report) {
        setAnalysisTab('compliance');
      } else {
        setAnalysisTab('extraction');
      }
    } catch {
      showNotice('error', '获取分析详情失败');
      setAnalysisOpen(false);
    } finally {
      setAnalysisLoading(false);
    }
  };

  const handleReanalyze = async (item: MaterialItem) => {
    setReanalyzingId(item.file_id);
    try {
      const res = await fetch(
        `${API_BASE}/api/mobile/projects/${encodeURIComponent(item.project_id)}/materials/${encodeURIComponent(item.file_id)}/reanalyze`,
        { method: 'POST', headers: getAuthHeaders() }
      );
      const data = await res.json().catch(() => ({}));
      if (res.ok) {
        showNotice('info', data.message || '已重新提交至智能分析自愈队列');
        void loadMaterials(true);
        if (analysisOpen) {
          setAnalysisOpen(false);
        }
      } else {
        showNotice('error', data.detail || '重新分析失败');
      }
    } catch {
      showNotice('error', '网络请求失败');
    } finally {
      setReanalyzingId(null);
    }
  };

  const handleCheckCompliance = async (item: { project_id: string; file_id: string; filename: string }) => {
    setCheckingCompliance(true);
    try {
      const res = await fetch(
        `${API_BASE}/api/mobile/projects/${encodeURIComponent(item.project_id)}/materials/${encodeURIComponent(item.file_id)}/compliance-check`,
        { method: 'POST', headers: getAuthHeaders() }
      );
      const data = await res.json().catch(() => ({}));
      if (res.ok) {
        showNotice('success', data.message || `已完成《${item.filename}》的 RAG 规范检测`);
        void loadMaterials(true);
        if (analysisDetail && analysisDetail.file_id === item.file_id) {
          setAnalysisDetail((prev) => prev ? {
            ...prev,
            compliance_status: data.compliance_status,
            compliance_score: data.compliance_score,
            compliance_report: data.report,
          } : null);
          setAnalysisTab('compliance');
        }
      } else {
        showNotice('error', data.detail || '规范检测执行失败');
      }
    } catch {
      showNotice('error', '网络请求失败');
    } finally {
      setCheckingCompliance(false);
    }
  };

  // ── 未登录视图（手机端专属登录页） ──────────────────────────
  if (!isLoggedIn) {
    return (
      <div className="min-h-screen bg-gradient-to-b from-slate-900 via-indigo-950 to-slate-900 flex flex-col justify-center px-5 py-10 text-white">
        <div className="max-w-md w-full mx-auto bg-white/10 backdrop-blur-md border border-white/15 rounded-3xl p-6 shadow-2xl">
          <div className="flex items-center gap-3 mb-5">
            <div className="w-12 h-12 rounded-2xl bg-indigo-500 flex items-center justify-center shadow-lg">
              <Smartphone className="w-6 h-6 text-white" />
            </div>
            <div>
              <h1 className="text-lg font-bold tracking-tight">手机端资料采集中心</h1>
              <p className="text-xs text-indigo-200 mt-0.5">选定项目 · 拍照录像上传 · 自动入库智能分析</p>
            </div>
          </div>

          {loginError && (
            <div className="mb-4 px-3.5 py-2.5 rounded-xl bg-rose-500/20 border border-rose-400/40 text-xs text-rose-100 flex items-center gap-2">
              <AlertCircle className="w-4 h-4 shrink-0" />
              <span>{loginError}</span>
            </div>
          )}

          <form onSubmit={handleMobileLogin} className="space-y-4">
            <div>
              <label className="block text-xs text-indigo-200 mb-1.5">登录账号</label>
              <input
                type="text"
                autoComplete="username"
                value={loginName}
                onChange={(e) => setLoginName(e.target.value)}
                placeholder="请输入登录名（如 admin）"
                className="w-full px-4 py-3 rounded-xl bg-white/10 border border-white/20 text-sm text-white placeholder-indigo-200/50 outline-none focus:border-indigo-400"
              />
            </div>
            <div>
              <label className="block text-xs text-indigo-200 mb-1.5">登录密码</label>
              <input
                type="password"
                autoComplete="current-password"
                value={loginPassword}
                onChange={(e) => setLoginPassword(e.target.value)}
                placeholder="请输入密码"
                className="w-full px-4 py-3 rounded-xl bg-white/10 border border-white/20 text-sm text-white placeholder-indigo-200/50 outline-none focus:border-indigo-400"
              />
            </div>
            <button
              type="submit"
              disabled={loginLoading}
              className="w-full py-3.5 rounded-xl bg-indigo-500 hover:bg-indigo-600 active:scale-[0.99] transition-all font-semibold text-sm flex items-center justify-center gap-2 shadow-lg cursor-pointer disabled:opacity-50"
            >
              {loginLoading ? <Loader2 className="w-4 h-4 animate-spin" /> : null}
              <span>登录进入手机采集台</span>
            </button>
          </form>
        </div>
      </div>
    );
  }

  const filteredProjects = projects.filter((p) =>
    p.name.toLowerCase().includes(projectSearch.toLowerCase())
  );

  // ── 已登录手机端主工作台 ────────────────────────────────────
  return (
    <div className="min-h-screen bg-slate-50 text-slate-900 pb-16">
      {/* 顶部栏 */}
      <header className="sticky top-0 z-30 bg-gradient-to-r from-indigo-600 to-blue-600 text-white px-4 py-3.5 shadow-md">
        <div className="max-w-xl mx-auto flex items-center justify-between gap-2">
          <div className="flex items-center gap-2.5 min-w-0">
            <div className="w-8 h-8 rounded-xl bg-white/20 flex items-center justify-center shrink-0">
              <Smartphone className="w-4 h-4" />
            </div>
            <div className="min-w-0">
              <h1 className="text-sm font-bold truncate">移动端现场资料上传</h1>
              <p className="text-[11px] text-indigo-100 truncate">
                当前登录：{user?.username || '用户'}
              </p>
            </div>
          </div>

          <div className="flex items-center gap-1.5 shrink-0">
            <button
              onClick={() => navigate('/m2')}
              className="px-2.5 py-1.5 rounded-lg bg-amber-500 hover:bg-amber-400 text-slate-950 text-xs font-bold flex items-center gap-1 cursor-pointer shadow-sm transition"
              title="切换至食品生产检查要点表 (/m2)"
            >
              <FileCheck2 className="w-3.5 h-3.5" />
              <span>要点表(/m2)</span>
            </button>
            {user?.role === 'admin' && (
              <button
                onClick={() => navigate(`/admin/materials?project_id=${encodeURIComponent(selectedProjectId)}`)}
                className="px-2.5 py-1.5 rounded-lg bg-white/15 hover:bg-white/25 text-xs font-medium flex items-center gap-1 cursor-pointer"
                title="进入后台管理查看"
              >
                <ShieldCheck className="w-3.5 h-3.5" />
                <span>后台查看</span>
              </button>
            )}
            <button
              onClick={handleSafeLogout}
              className="p-2 rounded-lg bg-white/15 hover:bg-white/25 cursor-pointer"
              title="退出登录"
            >
              <LogOut className="w-4 h-4" />
            </button>
          </div>
        </div>
      </header>

      <main className="max-w-xl mx-auto px-4 pt-4 space-y-4">
        {/* 状态提示横幅 */}
        {banner && (
          <div
            className={`px-4 py-3 rounded-2xl text-xs flex items-start justify-between gap-2 shadow-sm border ${
              banner.type === 'success'
                ? 'bg-emerald-50 border-emerald-200 text-emerald-800'
                : banner.type === 'error'
                ? 'bg-rose-50 border-rose-200 text-rose-800'
                : 'bg-blue-50 border-blue-200 text-blue-800'
            }`}
          >
            <div className="flex items-start gap-2">
              {banner.type === 'success' ? (
                <CheckCircle2 className="w-4 h-4 shrink-0 text-emerald-600 mt-0.5" />
              ) : (
                <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" />
              )}
              <span className="leading-relaxed">{banner.text}</span>
            </div>
            <button onClick={() => setBanner(null)} className="text-slate-400 hover:text-slate-600">
              <X className="w-4 h-4" />
            </button>
          </div>
        )}

        {/* 第一步：选择归属项目/资料库 */}
        <section className="bg-white rounded-2xl p-4 shadow-sm border border-slate-200/80">
          <div className="flex items-center justify-between mb-2.5">
            <span className="text-xs font-bold text-slate-600 flex items-center gap-1.5">
              <FolderKanban className="w-4 h-4 text-indigo-600" />
              1. 选择目标项目（对应资料库）
            </span>
            <button
              onClick={() => setCreateProjOpen(true)}
              className="text-xs text-indigo-600 font-semibold flex items-center gap-1 hover:text-indigo-700 cursor-pointer"
            >
              <Plus className="w-3.5 h-3.5" />
              新建项目
            </button>
          </div>

          <button
            type="button"
            onClick={() => setProjectPickerOpen(true)}
            className="w-full px-3.5 py-3 rounded-xl bg-slate-50 hover:bg-slate-100 border border-slate-200 flex items-center justify-between text-left transition-colors cursor-pointer"
          >
            {loadingProjects ? (
              <span className="text-xs text-slate-400 flex items-center gap-2">
                <Loader2 className="w-4 h-4 animate-spin" /> 正在加载项目...
              </span>
            ) : selectedProject ? (
              <div className="min-w-0 flex-1 pr-2">
                <div className="flex items-center gap-2">
                  <span className="text-lg">{selectedProject.icon}</span>
                  <span className="font-bold text-sm text-slate-800 truncate">{selectedProject.name}</span>
                  {selectedProject.can_upload ? (
                    <span className="px-2 py-0.5 text-[10px] rounded-full bg-emerald-100 text-emerald-700 font-medium shrink-0">
                      可上传
                    </span>
                  ) : (
                    <span className="px-2 py-0.5 text-[10px] rounded-full bg-amber-100 text-amber-700 font-medium shrink-0">
                      只读
                    </span>
                  )}
                </div>
                <p className="text-[11px] text-slate-500 mt-1">
                  已有资料 {selectedProject.source_count} 份 · 类型：{selectedProject.project_type === 'library' ? '公共法规/标准库' : '项目/案件资料库'}
                </p>
              </div>
            ) : (
              <span className="text-sm text-slate-400">点击选择或新建一个项目...</span>
            )}
            <ChevronDown className="w-4 h-4 text-slate-400 shrink-0" />
          </button>
        </section>

        {/* 第二步：拍摄/选择图片视频并上传入库 */}
        <section className="bg-white rounded-2xl p-4 shadow-sm border border-slate-200/80 space-y-3.5">
          <div className="flex items-center justify-between">
            <span className="text-xs font-bold text-slate-600 flex items-center gap-1.5">
              <Sparkles className="w-4 h-4 text-indigo-600" />
              2. 采集上传图片 / 视频等资料
            </span>
            <span className="text-[11px] text-slate-400">自动 OCR / 视觉 / 语音转写</span>
          </div>

          {/* 隐藏原生 input */}
          <input
            ref={cameraPhotoRef}
            type="file"
            accept="image/*"
            capture="environment"
            onChange={handleSelectFiles}
            className="hidden"
          />
          <input
            ref={cameraVideoRef}
            type="file"
            accept="video/*"
            capture="environment"
            onChange={handleSelectFiles}
            className="hidden"
          />
          <input
            ref={galleryRef}
            type="file"
            accept="image/*,video/*"
            multiple
            onChange={handleSelectFiles}
            className="hidden"
          />
          <input
            ref={docAudioRef}
            type="file"
            accept="audio/*,.pdf,.doc,.docx,.xls,.xlsx,.pptx,.txt,.md,.csv"
            multiple
            onChange={handleSelectFiles}
            className="hidden"
          />

          {/* 四个大触控按钮 */}
          <div className="grid grid-cols-2 gap-2.5">
            <button
              type="button"
              onClick={() => cameraPhotoRef.current?.click()}
              className="flex items-center gap-3 p-3.5 rounded-2xl bg-indigo-50/80 hover:bg-indigo-100/80 active:scale-[0.98] border border-indigo-100 text-left transition-all cursor-pointer"
            >
              <div className="w-10 h-10 rounded-xl bg-indigo-600 text-white flex items-center justify-center shrink-0 shadow-sm">
                <Camera className="w-5 h-5" />
              </div>
              <div>
                <div className="text-xs font-bold text-slate-800">拍照上传</div>
                <div className="text-[10px] text-slate-500 mt-0.5">调起手机相机</div>
              </div>
            </button>

            <button
              type="button"
              onClick={() => cameraVideoRef.current?.click()}
              className="flex items-center gap-3 p-3.5 rounded-2xl bg-amber-50/80 hover:bg-amber-100/80 active:scale-[0.98] border border-amber-100 text-left transition-all cursor-pointer"
            >
              <div className="w-10 h-10 rounded-xl bg-amber-500 text-white flex items-center justify-center shrink-0 shadow-sm">
                <Video className="w-5 h-5" />
              </div>
              <div>
                <div className="text-xs font-bold text-slate-800">录制视频</div>
                <div className="text-[10px] text-slate-500 mt-0.5">现场录像取证</div>
              </div>
            </button>

            <button
              type="button"
              onClick={() => galleryRef.current?.click()}
              className="flex items-center gap-3 p-3.5 rounded-2xl bg-teal-50/80 hover:bg-teal-100/80 active:scale-[0.98] border border-teal-100 text-left transition-all cursor-pointer"
            >
              <div className="w-10 h-10 rounded-xl bg-teal-600 text-white flex items-center justify-center shrink-0 shadow-sm">
                <ImageIcon className="w-5 h-5" />
              </div>
              <div>
                <div className="text-xs font-bold text-slate-800">相册选图/视频</div>
                <div className="text-[10px] text-slate-500 mt-0.5">支持批量多选</div>
              </div>
            </button>

            <button
              type="button"
              onClick={() => docAudioRef.current?.click()}
              className="flex items-center gap-3 p-3.5 rounded-2xl bg-violet-50/80 hover:bg-violet-100/80 active:scale-[0.98] border border-violet-100 text-left transition-all cursor-pointer"
            >
              <div className="w-10 h-10 rounded-xl bg-violet-600 text-white flex items-center justify-center shrink-0 shadow-sm">
                <FileUp className="w-5 h-5" />
              </div>
              <div>
                <div className="text-xs font-bold text-slate-800">音频 / 文档</div>
                <div className="text-[10px] text-slate-500 mt-0.5">录音/PDF/Word</div>
              </div>
            </button>
          </div>

          {/* 归档目录快捷标签 */}
          <div>
            <label className="block text-[11px] font-medium text-slate-500 mb-1.5">归档分类子目录</label>
            <div className="flex flex-wrap gap-1.5 mb-2">
              {PRESET_FOLDERS.map((folder) => (
                <button
                  key={folder}
                  type="button"
                  onClick={() => setCategoryFolder(folder)}
                  className={`px-2.5 py-1 rounded-full text-[11px] font-medium transition-colors cursor-pointer ${
                    categoryFolder === folder
                      ? 'bg-indigo-600 text-white'
                      : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
                  }`}
                >
                  {folder}
                </button>
              ))}
            </div>
            <input
              type="text"
              maxLength={40}
              value={categoryFolder}
              onChange={(e) => setCategoryFolder(e.target.value)}
              placeholder="输入或选择子目录名称"
              className="w-full px-3 py-2 rounded-xl bg-slate-50 border border-slate-200 text-xs outline-none focus:border-indigo-400"
            />
          </div>

          {/* 现场备注说明 */}
          <div>
            <label className="block text-[11px] font-medium text-slate-500 mb-1">
              资料说明备注（选填，将同步注入知识库辅助 AI 研判分析）
            </label>
            <textarea
              rows={2}
              maxLength={500}
              value={remark}
              onChange={(e) => setRemark(e.target.value)}
              placeholder="例如：涉案商品正面标签照片、门店现场录像等..."
              className="w-full px-3 py-2 rounded-xl bg-slate-50 border border-slate-200 text-xs outline-none focus:border-indigo-400 resize-none"
            />
          </div>

          {/* 待上传文件清单 */}
          {pendingFiles.length > 0 && (
            <div className="rounded-xl bg-slate-50 border border-slate-200 p-3 space-y-2">
              <div className="flex items-center justify-between text-xs font-semibold text-slate-700">
                <span>待上传队列（{pendingFiles.length} 份）</span>
                <button
                  type="button"
                  onClick={() => setPendingFiles([])}
                  className="text-[11px] text-rose-500 hover:underline"
                >
                  清空
                </button>
              </div>
              <div className="max-h-44 overflow-y-auto space-y-1.5">
                {pendingFiles.map((f, idx) => (
                  <div
                    key={`${f.name}-${idx}`}
                    className="flex items-center justify-between gap-2 bg-white px-2.5 py-2 rounded-lg border border-slate-100 text-xs"
                  >
                    <div className="min-w-0 flex-1">
                      <p className="font-medium text-slate-800 truncate">{f.name}</p>
                      <p className="text-[10px] text-slate-400">{formatBytes(f.size)}</p>
                    </div>
                    <button
                      type="button"
                      onClick={() => removePendingFile(idx)}
                      className="p-1 text-slate-400 hover:text-rose-500"
                    >
                      <Trash2 className="w-3.5 h-3.5" />
                    </button>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* 上传进度条 */}
          {uploading && (
            <div className="space-y-1">
              <div className="flex justify-between text-[11px] text-indigo-600 font-medium">
                <span>正在加密传输至项目资料库...</span>
                <span>{uploadPercent}%</span>
              </div>
              <div className="w-full h-2 rounded-full bg-indigo-100 overflow-hidden">
                <div
                  className="h-full bg-indigo-600 transition-all duration-200"
                  style={{ width: `${uploadPercent}%` }}
                />
              </div>
            </div>
          )}

          {/* 提交按钮 */}
          <button
            type="button"
            disabled={uploading || pendingFiles.length === 0 || !selectedProject?.can_upload}
            onClick={handleUploadSubmit}
            className="w-full py-3.5 rounded-xl bg-gradient-to-r from-indigo-600 to-blue-600 hover:from-indigo-700 hover:to-blue-700 text-white font-bold text-sm shadow-md active:scale-[0.99] transition-all flex items-center justify-center gap-2 cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {uploading ? (
              <>
                <Loader2 className="w-4 h-4 animate-spin" />
                <span>上传中 ({uploadPercent}%)...</span>
              </>
            ) : (
              <>
                <Sparkles className="w-4 h-4" />
                <span>
                  上传至「{selectedProject?.name || '所选项目'}」并智能分析
                  {pendingFiles.length > 0 ? ` (${pendingFiles.length})` : ''}
                </span>
              </>
            )}
          </button>
        </section>

        {/* 第三步：当前项目资料库与智能分析状态 */}
        <section className="bg-white rounded-2xl p-4 shadow-sm border border-slate-200/80 space-y-3">
          <div className="flex items-center justify-between">
            <div>
              <h2 className="text-xs font-bold text-slate-700">
                3. 本项目资料库与分析进度
              </h2>
              {summary && (
                <p className="text-[11px] text-slate-400 mt-0.5">
                  共 {summary.total} 份（图 {summary.image_count} · 视 {summary.video_count} · 音 {summary.audio_count} · 文 {summary.document_count}）· 已完成分析 {summary.analyzed_count} 份
                </p>
              )}
            </div>
            <button
              type="button"
              onClick={() => void loadMaterials(false)}
              className="p-2 rounded-xl bg-slate-100 hover:bg-slate-200 text-slate-600 cursor-pointer"
              title="刷新列表"
            >
              <RefreshCw className={`w-3.5 h-3.5 ${loadingMaterials ? 'animate-spin' : ''}`} />
            </button>
          </div>

          {/* 分类筛选胶囊 */}
          <div className="flex gap-1.5 overflow-x-auto pb-1">
            {[
              { id: 'all', label: '全部' },
              { id: 'image', label: '图片' },
              { id: 'video', label: '视频' },
              { id: 'audio', label: '音频' },
              { id: 'document', label: '文档' },
            ].map((tab) => (
              <button
                key={tab.id}
                type="button"
                onClick={() => setCategoryFilter(tab.id)}
                className={`px-3 py-1 rounded-full text-xs font-medium whitespace-nowrap cursor-pointer ${
                  categoryFilter === tab.id
                    ? 'bg-slate-900 text-white'
                    : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
                }`}
              >
                {tab.label}
              </button>
            ))}
          </div>

          {/* 列表内容 */}
          {loadingMaterials ? (
            <div className="py-10 flex justify-center">
              <Loader2 className="w-6 h-6 animate-spin text-indigo-500" />
            </div>
          ) : materials.length === 0 ? (
            <div className="py-10 text-center text-xs text-slate-400">
              当前项目暂无符合筛选条件的资料，请通过上方按钮拍照或选文件上传
            </div>
          ) : (
            <div className="space-y-2.5">
              {materials.map((item) => {
                const isReady =
                  ['vectorized', 'graph_queued', 'graph_extracting'].includes(item.ingest_status) ||
                  item.chunks > 0;
                const isProcessing = ['pending', 'processing'].includes(item.ingest_status);
                return (
                  <div
                    key={item.file_id}
                    className="p-3 rounded-xl border border-slate-200/80 bg-slate-50/50 space-y-2"
                  >
                    <div className="flex items-start justify-between gap-2">
                      <div className="flex items-start gap-2.5 min-w-0">
                        <div
                          className={`p-2 rounded-xl shrink-0 ${
                            item.media_category === 'image'
                              ? 'bg-teal-100 text-teal-700'
                              : item.media_category === 'video'
                              ? 'bg-amber-100 text-amber-700'
                              : item.media_category === 'audio'
                              ? 'bg-violet-100 text-violet-700'
                              : 'bg-blue-100 text-blue-700'
                          }`}
                        >
                          {item.media_category === 'image' ? (
                            <ImageIcon className="w-4 h-4" />
                          ) : item.media_category === 'video' ? (
                            <Video className="w-4 h-4" />
                          ) : item.media_category === 'audio' ? (
                            <FileAudio className="w-4 h-4" />
                          ) : (
                            <FileText className="w-4 h-4" />
                          )}
                        </div>
                        <div className="min-w-0">
                          <p className="text-xs font-bold text-slate-800 break-all">{item.filename}</p>
                          <p className="text-[10px] text-slate-400 mt-0.5">
                            {formatBytes(item.size)}
                            {item.sub_folder ? ` · ${item.sub_folder}` : ''}
                            {item.created_at ? ` · ${formatDateTime(item.created_at)}` : ''}
                            {item.upload_source === 'mobile' ? ' · 📱手机上传' : ''}
                          </p>
                        </div>
                      </div>

                      <div className="flex flex-col items-end gap-1 shrink-0">
                        <span
                          className={`px-2 py-0.5 rounded-full text-[10px] font-semibold shrink-0 flex items-center gap-1 ${
                            isReady
                              ? 'bg-emerald-100 text-emerald-700'
                              : isProcessing
                              ? 'bg-indigo-100 text-indigo-700'
                              : 'bg-rose-100 text-rose-700'
                          }`}
                        >
                          {isProcessing && <Loader2 className="w-2.5 h-2.5 animate-spin" />}
                          {item.status_label}
                          {item.chunks > 0 ? ` (${item.chunks}块)` : ''}
                        </span>

                        {['image', 'video'].includes(item.media_category) && (
                          item.compliance_status ? (
                            <span
                              className={`px-2 py-0.5 rounded-full text-[10px] font-bold flex items-center gap-1 border ${
                                item.compliance_status === 'compliant'
                                  ? 'bg-emerald-50 text-emerald-700 border-emerald-300'
                                  : item.compliance_status === 'warning'
                                  ? 'bg-amber-50 text-amber-700 border-amber-300'
                                  : 'bg-rose-50 text-rose-700 border-rose-300'
                              }`}
                            >
                              <ShieldCheck className="w-2.5 h-2.5" />
                              {item.compliance_status === 'compliant'
                                ? `规范合格 (${item.compliance_score || 90}分)`
                                : item.compliance_status === 'warning'
                                ? `合规存疑 (${item.compliance_score || 70}分)`
                                : `违反规范 (${item.compliance_score || 40}分)`}
                            </span>
                          ) : isProcessing ? (
                            <span className="px-2 py-0.5 rounded-full text-[10px] font-medium bg-slate-100 text-slate-500 flex items-center gap-1">
                              <ShieldAlert className="w-2.5 h-2.5 animate-pulse text-indigo-500" />
                              RAG规范检测中
                            </span>
                          ) : null
                        )}
                      </div>
                    </div>

                    {/* 乱码告警条及重新分析指引 */}
                    {item.is_garbled && (
                      <div className="flex items-center justify-between text-[11px] text-amber-900 bg-amber-50 border border-amber-200 px-2.5 py-1.5 rounded-lg">
                        <span className="flex items-center gap-1">
                          <AlertTriangle className="w-3.5 h-3.5 text-amber-600 shrink-0" />
                          <span>图片文字解析疑似乱码：{item.garbled_reason || '存在异常噪声'}</span>
                        </span>
                        <button
                          type="button"
                          disabled={reanalyzingId === item.file_id}
                          onClick={() => void handleReanalyze(item)}
                          className="text-[10px] font-bold text-amber-950 bg-amber-200/90 hover:bg-amber-300 px-2.5 py-1 rounded-md shrink-0 flex items-center gap-1 cursor-pointer transition-colors"
                        >
                          {reanalyzingId === item.file_id ? (
                            <Loader2 className="w-3 h-3 animate-spin" />
                          ) : (
                            <RefreshCw className="w-3 h-3" />
                          )}
                          重新分析
                        </button>
                      </div>
                    )}

                    {item.remark && (
                      <p className="text-[11px] text-indigo-700 bg-indigo-50 px-2.5 py-1.5 rounded-lg">
                        备注：{item.remark}
                      </p>
                    )}

                    {item.analysis_preview && (
                      <p className="text-[11px] text-slate-600 bg-white px-2.5 py-1.5 rounded-lg border border-slate-100 line-clamp-2">
                        AI提取摘要：{item.analysis_preview}
                      </p>
                    )}

                    <div className="flex items-center justify-end gap-2 pt-1">
                      <button
                        type="button"
                        onClick={() => void openMediaPreview(item)}
                        className="px-2.5 py-1 rounded-lg bg-white border border-slate-200 text-[11px] font-medium text-slate-700 hover:bg-slate-100 flex items-center gap-1 cursor-pointer"
                      >
                        <Eye className="w-3 h-3" />
                        预览原件
                      </button>

                      {['image', 'video'].includes(item.media_category) && (
                        <button
                          type="button"
                          onClick={() => void openAnalysisSheet(item)}
                          className={`px-2.5 py-1 rounded-lg border text-[11px] font-medium flex items-center gap-1 cursor-pointer ${
                            item.compliance_status === 'violation'
                              ? 'bg-rose-50 border-rose-200 text-rose-700 hover:bg-rose-100'
                              : item.compliance_status === 'warning'
                              ? 'bg-amber-50 border-amber-200 text-amber-700 hover:bg-amber-100'
                              : 'bg-emerald-50 border-emerald-200 text-emerald-700 hover:bg-emerald-100'
                          }`}
                        >
                          <ShieldCheck className="w-3 h-3" />
                          RAG规范
                        </button>
                      )}

                      <button
                        type="button"
                        onClick={() => void openAnalysisSheet(item)}
                        className="px-2.5 py-1 rounded-lg bg-indigo-50 border border-indigo-200 text-[11px] font-medium text-indigo-700 hover:bg-indigo-100 flex items-center gap-1 cursor-pointer"
                      >
                        <Sparkles className="w-3 h-3" />
                        提取详情
                      </button>
                      {!isProcessing && selectedProject?.can_upload && (
                        <button
                          type="button"
                          disabled={reanalyzingId === item.file_id}
                          onClick={() => void handleReanalyze(item)}
                          className="px-2 py-1 rounded-lg text-[11px] text-slate-500 hover:bg-slate-100 cursor-pointer flex items-center gap-0.5"
                          title="重新进行多模态分析与切片自愈"
                        >
                          {reanalyzingId === item.file_id && <Loader2 className="w-2.5 h-2.5 animate-spin" />}
                          重分析
                        </button>
                      )}
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </section>
      </main>

      {/* 项目选择抽屉弹窗 */}
      {projectPickerOpen && (
        <div className="fixed inset-0 z-50 bg-black/50 flex items-end sm:items-center justify-center">
          <div className="bg-white w-full max-w-lg rounded-t-3xl sm:rounded-3xl max-h-[80vh] flex flex-col overflow-hidden">
            <div className="px-5 py-4 border-b border-slate-100 flex items-center justify-between">
              <h3 className="font-bold text-sm text-slate-800">选择要上传资料的项目</h3>
              <button onClick={() => setProjectPickerOpen(false)} className="p-1 text-slate-400">
                <X className="w-5 h-5" />
              </button>
            </div>
            <div className="p-3 border-b border-slate-100">
              <div className="relative">
                <Search className="w-4 h-4 text-slate-400 absolute left-3 top-1/2 -translate-y-1/2" />
                <input
                  type="text"
                  value={projectSearch}
                  onChange={(e) => setProjectSearch(e.target.value)}
                  placeholder="搜索项目名称..."
                  className="w-full pl-9 pr-3 py-2 rounded-xl bg-slate-100 text-xs outline-none"
                />
              </div>
            </div>
            <div className="flex-1 overflow-y-auto p-3 space-y-2">
              {filteredProjects.map((proj) => (
                <button
                  key={proj.id}
                  type="button"
                  onClick={() => {
                    setSelectedProjectId(proj.id);
                    setProjectPickerOpen(false);
                  }}
                  className={`w-full p-3 rounded-xl border text-left flex items-center justify-between transition-colors cursor-pointer ${
                    proj.id === selectedProjectId
                      ? 'border-indigo-500 bg-indigo-50/60'
                      : 'border-slate-200 hover:bg-slate-50'
                  }`}
                >
                  <div className="min-w-0 pr-2">
                    <div className="flex items-center gap-2">
                      <span>{proj.icon}</span>
                      <span className="text-xs font-bold text-slate-800 truncate">{proj.name}</span>
                    </div>
                    <p className="text-[11px] text-slate-400 mt-0.5">
                      资料数：{proj.source_count} · 负责人：{proj.owner_name || '系统'}
                    </p>
                  </div>
                  <span
                    className={`px-2 py-0.5 rounded-full text-[10px] font-medium shrink-0 ${
                      proj.can_upload
                        ? 'bg-emerald-100 text-emerald-700'
                        : 'bg-slate-100 text-slate-500'
                    }`}
                  >
                    {proj.can_upload ? '可上传' : '仅查看'}
                  </span>
                </button>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* 新建项目弹窗 */}
      {createProjOpen && (
        <div className="fixed inset-0 z-50 bg-black/50 flex items-center justify-center p-4">
          <div className="bg-white w-full max-w-sm rounded-2xl p-5 space-y-4 shadow-xl">
            <div className="flex items-center justify-between">
              <h3 className="font-bold text-sm text-slate-800">新建项目资料库</h3>
              <button onClick={() => setCreateProjOpen(false)} className="text-slate-400">
                <X className="w-4 h-4" />
              </button>
            </div>
            <input
              type="text"
              maxLength={80}
              value={newProjName}
              onChange={(e) => setNewProjName(e.target.value)}
              placeholder="请输入项目或案件名称..."
              className="w-full px-3.5 py-2.5 rounded-xl border border-slate-200 text-xs outline-none focus:border-indigo-500"
            />
            <div className="flex justify-end gap-2">
              <button
                type="button"
                onClick={() => setCreateProjOpen(false)}
                className="px-4 py-2 rounded-xl bg-slate-100 text-xs font-medium text-slate-600"
              >
                取消
              </button>
              <button
                type="button"
                disabled={creatingProj || !newProjName.trim()}
                onClick={() => void handleCreateProject()}
                className="px-4 py-2 rounded-xl bg-indigo-600 text-xs font-semibold text-white disabled:opacity-50"
              >
                {creatingProj ? '创建中...' : '创建并选中'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* 媒体原件预览弹窗 */}
      {previewItem && (
        <div className="fixed inset-0 z-50 bg-black/80 flex flex-col justify-between p-4">
          <div className="flex items-center justify-between text-white">
            <span className="text-xs font-medium truncate pr-3">{previewItem.filename}</span>
            <button
              onClick={() => {
                if (previewBlobUrl) URL.revokeObjectURL(previewBlobUrl);
                setPreviewBlobUrl(null);
                setPreviewItem(null);
              }}
              className="p-2 rounded-full bg-white/15"
            >
              <X className="w-5 h-5" />
            </button>
          </div>

          <div className="flex-1 flex items-center justify-center overflow-hidden my-4">
            {previewLoading ? (
              <Loader2 className="w-8 h-8 animate-spin text-white" />
            ) : previewBlobUrl ? (
              previewItem.media_category === 'image' ? (
                <img
                  src={previewBlobUrl}
                  alt={previewItem.filename}
                  className="max-h-[75vh] max-w-full object-contain rounded-xl"
                />
              ) : previewItem.media_category === 'video' ? (
                <video
                  src={previewBlobUrl}
                  controls
                  playsInline
                  className="max-h-[75vh] max-w-full rounded-xl bg-black"
                />
              ) : previewItem.media_category === 'audio' ? (
                <div className="bg-white rounded-2xl p-6 w-full max-w-sm text-center space-y-3">
                  <FileAudio className="w-10 h-10 text-violet-600 mx-auto" />
                  <p className="text-xs font-semibold text-slate-800 break-all">{previewItem.filename}</p>
                  <audio src={previewBlobUrl} controls className="w-full" />
                </div>
              ) : (
                <div className="bg-white rounded-2xl p-6 w-full max-w-sm text-center space-y-4">
                  <FileText className="w-10 h-10 text-blue-600 mx-auto" />
                  <p className="text-xs font-semibold text-slate-800 break-all">{previewItem.filename}</p>
                  <a
                    href={previewBlobUrl}
                    download={previewItem.filename}
                    className="inline-flex items-center gap-1.5 px-4 py-2 rounded-xl bg-indigo-600 text-white text-xs font-semibold"
                  >
                    <Download className="w-4 h-4" />
                    下载查看文档
                  </a>
                </div>
              )
            ) : null}
          </div>
        </div>
      )}

      {/* AI 分析与 RAG 规范检测详情抽屉 */}
      {analysisOpen && (
        <div className="fixed inset-0 z-50 bg-black/50 flex items-end sm:items-center justify-center">
          <div className="bg-white w-full max-w-lg rounded-t-3xl sm:rounded-3xl max-h-[88vh] flex flex-col overflow-hidden">
            <div className="px-5 py-3.5 border-b border-slate-100 flex items-center justify-between">
              <div className="flex items-center gap-1.5 min-w-0">
                <ShieldCheck className="w-4 h-4 text-indigo-600 shrink-0" />
                <h3 className="font-bold text-sm text-slate-800 truncate">
                  资料分析与 RAG 规范检测
                </h3>
              </div>
              <button onClick={() => setAnalysisOpen(false)} className="p-1 text-slate-400 hover:text-slate-600">
                <X className="w-5 h-5" />
              </button>
            </div>

            {/* 顶栏 Tab 切换 */}
            {analysisDetail && (
              <div className="flex border-b border-slate-100 bg-slate-50/70 px-4 pt-1">
                <button
                  type="button"
                  onClick={() => setAnalysisTab('compliance')}
                  className={`flex-1 py-2 text-xs font-bold border-b-2 flex items-center justify-center gap-1.5 transition-colors cursor-pointer ${
                    analysisTab === 'compliance'
                      ? 'border-indigo-600 text-indigo-600'
                      : 'border-transparent text-slate-500 hover:text-slate-700'
                  }`}
                >
                  <ShieldCheck className="w-3.5 h-3.5" />
                  RAG 规范合规检测
                  {analysisDetail.compliance_score ? ` (${analysisDetail.compliance_score}分)` : ''}
                </button>
                <button
                  type="button"
                  onClick={() => setAnalysisTab('extraction')}
                  className={`flex-1 py-2 text-xs font-bold border-b-2 flex items-center justify-center gap-1.5 transition-colors cursor-pointer ${
                    analysisTab === 'extraction'
                      ? 'border-indigo-600 text-indigo-600'
                      : 'border-transparent text-slate-500 hover:text-slate-700'
                  }`}
                >
                  <Sparkles className="w-3.5 h-3.5" />
                  识别提取文本
                  {analysisDetail.is_garbled && (
                    <span className="w-2 h-2 rounded-full bg-amber-500 shrink-0" />
                  )}
                </button>
              </div>
            )}

            <div className="flex-1 overflow-y-auto p-4 space-y-3">
              {analysisLoading ? (
                <div className="py-12 flex justify-center">
                  <Loader2 className="w-6 h-6 animate-spin text-indigo-500" />
                </div>
              ) : analysisDetail ? (
                <>
                  <div className="bg-slate-50 rounded-xl p-3 text-xs space-y-1 border border-slate-100">
                    <p className="font-bold text-slate-800 break-all">{analysisDetail.filename}</p>
                    <p className="text-slate-500">
                      状态：{analysisDetail.status_label} · 切片：{analysisDetail.chunks_count} 块
                      {analysisDetail.compliance_checked_at ? ` · 规范检测时间：${formatDateTime(analysisDetail.compliance_checked_at)}` : ''}
                    </p>
                    {analysisDetail.remark && (
                      <p className="text-indigo-700">现场备注：{analysisDetail.remark}</p>
                    )}
                  </div>

                  {/* Tab 1: RAG 规范检测报告 */}
                  {analysisTab === 'compliance' && (
                    <div className="space-y-3">
                      {analysisDetail.compliance_report ? (
                        <>
                          {/* 评级主卡片 */}
                          <div
                            className={`p-3.5 rounded-xl border space-y-2 ${
                              analysisDetail.compliance_status === 'compliant'
                                ? 'bg-emerald-50/80 border-emerald-200 text-emerald-950'
                                : analysisDetail.compliance_status === 'warning'
                                ? 'bg-amber-50/80 border-amber-200 text-amber-950'
                                : 'bg-rose-50/80 border-rose-200 text-rose-950'
                            }`}
                          >
                            <div className="flex items-center justify-between">
                              <span className="font-bold text-sm flex items-center gap-1.5">
                                <ShieldCheck className="w-4 h-4" />
                                {analysisDetail.compliance_report.compliance_label || '规范研判完成'}
                              </span>
                              <span className="text-xs font-black px-2.5 py-0.5 rounded-full bg-white/80 shadow-xs">
                                得分：{analysisDetail.compliance_report.compliance_score || 90} / 100
                              </span>
                            </div>
                            <p className="text-xs leading-relaxed opacity-90">
                              {analysisDetail.compliance_report.summary}
                            </p>
                          </div>

                          {/* 依据的标准规范条款 */}
                          {analysisDetail.compliance_report.applied_standards && analysisDetail.compliance_report.applied_standards.length > 0 && (
                            <div className="bg-slate-50 rounded-xl p-3 border border-slate-200/80 space-y-1.5">
                              <h4 className="text-xs font-bold text-slate-700 flex items-center gap-1">
                                <span>📚</span> 检索依据的法律与行业规范标准
                              </h4>
                              <div className="space-y-1.5 pt-0.5">
                                {analysisDetail.compliance_report.applied_standards.map((std, sIdx) => (
                                  <div key={sIdx} className="bg-white p-2 rounded-lg border border-slate-100 text-[11px] space-y-0.5">
                                    <p className="font-bold text-slate-800">{std.title} {std.clause}</p>
                                    <p className="text-slate-600 line-clamp-3 leading-relaxed">{std.requirement}</p>
                                  </div>
                                ))}
                              </div>
                            </div>
                          )}

                          {/* 逐项核验发现 */}
                          {analysisDetail.compliance_report.findings && analysisDetail.compliance_report.findings.length > 0 && (
                            <div className="space-y-1.5">
                              <h4 className="text-xs font-bold text-slate-700 flex items-center gap-1">
                                <span>🔍</span> 逐项规范比对分析
                              </h4>
                              <div className="space-y-1.5">
                                {analysisDetail.compliance_report.findings.map((f, fIdx) => (
                                  <div
                                    key={fIdx}
                                    className={`p-2.5 rounded-xl border text-xs space-y-1 ${
                                      f.status === 'pass'
                                        ? 'bg-emerald-50/50 border-emerald-200/60'
                                        : f.status === 'warning'
                                        ? 'bg-amber-50/50 border-amber-200/60'
                                        : 'bg-rose-50/50 border-rose-200/60'
                                    }`}
                                  >
                                    <div className="flex items-center justify-between font-bold">
                                      <span className="text-slate-800">{f.item}</span>
                                      <span
                                        className={`text-[10px] px-1.5 py-0.5 rounded ${
                                          f.status === 'pass'
                                            ? 'text-emerald-700 bg-emerald-100'
                                            : f.status === 'warning'
                                            ? 'text-amber-700 bg-amber-100'
                                            : 'text-rose-700 bg-rose-100'
                                        }`}
                                      >
                                        {f.status === 'pass' ? '符合' : f.status === 'warning' ? '存疑' : '违规'}
                                      </span>
                                    </div>
                                    <p className="text-[11px] text-slate-600 leading-relaxed">{f.detail}</p>
                                  </div>
                                ))}
                              </div>
                            </div>
                          )}

                          {/* 采信与整改建议 */}
                          {analysisDetail.compliance_report.recommendations && analysisDetail.compliance_report.recommendations.length > 0 && (
                            <div className="bg-indigo-50/60 border border-indigo-100 rounded-xl p-3 space-y-1 text-xs">
                              <h4 className="font-bold text-indigo-900 flex items-center gap-1">
                                <span>💡</span> 整改与证据采信建议
                              </h4>
                              <ul className="list-disc list-inside text-[11px] text-indigo-800 space-y-1 pl-1">
                                {analysisDetail.compliance_report.recommendations.map((rec, rIdx) => (
                                  <li key={rIdx} className="leading-relaxed">{rec}</li>
                                ))}
                              </ul>
                            </div>
                          )}
                        </>
                      ) : (
                        <div className="py-8 text-center text-xs text-slate-400 space-y-2">
                          <p>暂无该资料的 RAG 规范检测报告</p>
                          <p className="text-[11px] text-slate-500">点击下方按钮可立即依据法规与标准库启动合规研判</p>
                        </div>
                      )}

                      {/* 重新触发检测按钮 */}
                      <div className="pt-1">
                        <button
                          type="button"
                          disabled={checkingCompliance}
                          onClick={() => {
                            if (analysisDetail.project_id) {
                              void handleCheckCompliance({
                                project_id: analysisDetail.project_id,
                                file_id: analysisDetail.file_id,
                                filename: analysisDetail.filename,
                              });
                            }
                          }}
                          className="w-full py-2.5 rounded-xl bg-indigo-600 hover:bg-indigo-700 text-white text-xs font-bold flex items-center justify-center gap-1.5 cursor-pointer shadow-xs disabled:opacity-50"
                        >
                          {checkingCompliance ? (
                            <Loader2 className="w-3.5 h-3.5 animate-spin" />
                          ) : (
                            <RefreshCw className="w-3.5 h-3.5" />
                          )}
                          {checkingCompliance ? 'RAG 检索与大模型合规研判中...' : '重新检测规范'}
                        </button>
                      </div>
                    </div>
                  )}

                  {/* Tab 2: 提取文本详情 */}
                  {analysisTab === 'extraction' && (
                    <div className="space-y-3">
                      {/* 乱码识别告警横幅 */}
                      {analysisDetail.is_garbled && (
                        <div className="p-3 rounded-xl bg-amber-50 border border-amber-200 text-amber-900 text-xs space-y-2">
                          <div className="flex items-start gap-2">
                            <AlertTriangle className="w-4 h-4 text-amber-600 shrink-0 mt-0.5" />
                            <div>
                              <p className="font-bold">检测到文本解析异常（疑似乱码）</p>
                              <p className="text-[11px] text-amber-800 mt-0.5">
                                原因：{analysisDetail.garbled_reason || '存在高比例碎屑无序字符或特殊符号'}。
                              </p>
                            </div>
                          </div>
                          <button
                            type="button"
                            disabled={reanalyzingId === analysisDetail.file_id}
                            onClick={() => {
                              const found = materials.find((m) => m.file_id === analysisDetail.file_id);
                              if (found) void handleReanalyze(found);
                            }}
                            className="w-full py-2 rounded-lg bg-amber-200/90 hover:bg-amber-300 text-amber-950 font-bold text-xs flex items-center justify-center gap-1 cursor-pointer"
                          >
                            {reanalyzingId === analysisDetail.file_id ? (
                              <Loader2 className="w-3.5 h-3.5 animate-spin" />
                            ) : (
                              <RefreshCw className="w-3.5 h-3.5" />
                            )}
                            立即重新分析图片并自愈
                          </button>
                        </div>
                      )}

                      <div>
                        <div className="flex items-center justify-between mb-1.5">
                          <h4 className="text-xs font-bold text-slate-700">AI 提取与转写全文</h4>
                          {!['pending', 'processing'].includes(analysisDetail.ingest_status) && (
                            <button
                              type="button"
                              onClick={() => {
                                const found = materials.find((m) => m.file_id === analysisDetail.file_id);
                                if (found) void handleReanalyze(found);
                              }}
                              className="text-[11px] text-indigo-600 hover:text-indigo-800 font-medium flex items-center gap-1 cursor-pointer"
                            >
                              <RefreshCw className="w-3 h-3" />
                              重新分析
                            </button>
                          )}
                        </div>

                        {analysisDetail.extracted_text ? (
                          <pre className="whitespace-pre-wrap break-words text-xs text-slate-700 bg-slate-50 border border-slate-200 rounded-xl p-3 max-h-80 overflow-y-auto font-sans leading-relaxed">
                            {analysisDetail.extracted_text}
                          </pre>
                        ) : (
                          <div className="text-xs text-slate-400 bg-slate-50 rounded-xl p-4 text-center">
                            {['pending', 'processing'].includes(analysisDetail.ingest_status)
                              ? '后台正在执行多模态解析（OCR / 视觉识别 / 语音转写），请稍候几秒刷新查看...'
                              : analysisDetail.error_message || '暂无提取文本'}
                          </div>
                        )}
                      </div>
                    </div>
                  )}
                </>
              ) : null}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

