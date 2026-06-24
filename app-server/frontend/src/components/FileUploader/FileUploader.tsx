import { useState, useRef, useCallback, useEffect } from 'react';
import { UploadCloud, FileText, FileSpreadsheet, FileImage, FileVideo, FileAudio, FileQuestion, Trash2, CheckCircle2, Loader2, AlertCircle, RefreshCw, Library, CheckSquare, Square, Search, X } from 'lucide-react';
import { useAuthStore } from '../../store/authStore';

const API_BASE = import.meta.env.VITE_API_BASE || '';

type UploadStatus = 'pending' | 'uploading' | 'done' | 'error';

interface TrackedFile {
  file: File;
  status: UploadStatus;
  progress?: number;      // 上传进度 0-100
  fileId?: string;        // 后端返回的文件 ID（用于轮询入库状态）
  serverPath?: string;
  ingestStatus?: string;  // vectorized / unsupported_format / skipped / pending
  chunks?: number;        // 向量化切片数
  parseProgress?: number; // 后台解析进度估算 (0-99%)
  error?: string;
}

interface FileUploaderProps {
  projectId: string;
}

const renderTrackedFileIcon = (tracked: TrackedFile) => {
  const isFailed = tracked.ingestStatus === 'failed' || tracked.ingestStatus === 'unsupported_format' || tracked.status === 'error';
  if (isFailed) {
    return (
      <div 
        className="p-2 rounded-md shrink-0 flex items-center justify-center bg-rose-50 text-rose-500 border border-rose-100 dark:bg-rose-950/20 dark:text-rose-400 dark:border-rose-900/30 animate-pulse"
        title={tracked.ingestStatus === 'unsupported_format' ? '格式待支持：此文件格式暂不支持解析向量化' : `解析失败：${tracked.error || '未知异常'}`}
      >
        <FileQuestion className="w-4 h-4" />
      </div>
    );
  }

  const name = tracked.file.name.toLowerCase();
  
  if (name.endsWith('.mp3') || name.endsWith('.wav') || name.endsWith('.m4a')) {
    return (
      <div className="p-2 bg-violet-50 text-violet-600 border border-violet-100 dark:bg-violet-950/30 dark:text-violet-400 dark:border-violet-900/50 rounded-md shrink-0 flex items-center justify-center" title="音频文件">
        <FileAudio className="w-4 h-4" />
      </div>
    );
  }
  
  if (name.endsWith('.mp4') || name.endsWith('.mov') || name.endsWith('.webm') || name.endsWith('.ogg')) {
    return (
      <div className="p-2 bg-amber-50 text-amber-600 border border-amber-100 dark:bg-amber-950/30 dark:text-amber-400 dark:border-amber-900/50 rounded-md shrink-0 flex items-center justify-center" title="视频文件">
        <FileVideo className="w-4 h-4" />
      </div>
    );
  }

  if (name.endsWith('.xlsx') || name.endsWith('.xls') || name.endsWith('.csv')) {
    return (
      <div className="p-2 bg-emerald-50 text-emerald-600 border border-emerald-100 dark:bg-emerald-950/30 dark:text-emerald-400 dark:border-emerald-900/50 rounded-md shrink-0 flex items-center justify-center" title="电子表格">
        <FileSpreadsheet className="w-4 h-4" />
      </div>
    );
  }

  if (name.endsWith('.png') || name.endsWith('.jpg') || name.endsWith('.jpeg') || name.endsWith('.webp') || name.endsWith('.svg') || name.endsWith('.bmp') || name.endsWith('.gif')) {
    return (
      <div className="p-2 bg-teal-50 text-teal-600 border border-teal-100 dark:bg-teal-950/30 dark:text-teal-400 dark:border-teal-900/50 rounded-md shrink-0 flex items-center justify-center" title="图像文件">
        <FileImage className="w-4 h-4" />
      </div>
    );
  }

  if (name.endsWith('.pdf')) {
    return (
      <div className="p-2 bg-red-50 text-red-600 border border-red-100 dark:bg-red-950/30 dark:text-red-400 dark:border-red-900/50 rounded-md shrink-0 flex items-center justify-center" title="PDF文档">
        <FileText className="w-4 h-4" />
      </div>
    );
  }

  if (name.endsWith('.docx') || name.endsWith('.doc')) {
    return (
      <div className="p-2 bg-blue-50 text-blue-600 border border-blue-100 dark:bg-blue-950/30 dark:text-blue-400 dark:border-blue-900/50 rounded-md shrink-0 flex items-center justify-center" title="Word文档">
        <FileText className="w-4 h-4" />
      </div>
    );
  }

  return (
    <div className="p-2 bg-gray-50 text-gray-500 border border-gray-200 dark:bg-gray-900/30 dark:text-gray-400 dark:border-gray-800/50 rounded-md shrink-0 flex items-center justify-center" title="文本文档">
      <FileText className="w-4 h-4" />
    </div>
  );
};

export default function FileUploader({ projectId }: FileUploaderProps) {
  const [isDragging, setIsDragging] = useState(false);
  const [trackedFiles, setTrackedFiles] = useState<TrackedFile[]>([]);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const folderInputRef = useRef<HTMLInputElement>(null);
  const { getAuthHeaders } = useAuthStore();
  // WHY: 存储所有活跃的轮询定时器 ID，组件卸载时统一清理防止内存泄漏
  const pollTimers = useRef<Set<ReturnType<typeof setTimeout>>>(new Set());

  // 组件卸载时清理所有轮询定时器
  useEffect(() => {
    return () => {
      pollTimers.current.forEach(id => clearTimeout(id));
      pollTimers.current.clear();
    };
  }, []);

  /**
   * 轮询后台入库状态，直到入库完成或超时。
   * WHY: 后台解析（OCR/GIS）耗时 1-120 秒不等，
   *      需要异步轮询而非阻塞等待，确保 UI 能实时反映进度。
   */
  const pollIngestStatus = useCallback((fileId: string, fileRef: File) => {
    const POLL_INTERVAL = 3000;  // 3 秒
    const MAX_ATTEMPTS = 600;    // 最多 1800 秒 (30 分钟)
    let attempt = 0;

    const poll = () => {
      attempt++;
      if (attempt > MAX_ATTEMPTS) {
        // 超时：标记为解析超时/中断，避免用户迷惑
        setTrackedFiles(prev =>
          prev.map(t =>
            t.file === fileRef && t.ingestStatus === 'pending'
              ? { ...t, ingestStatus: 'timeout' }
              : t
          )
        );
        return;
      }

      const timerId = setTimeout(async () => {
        try {
          const tokenParam = localStorage.getItem('token') ? `&token=${localStorage.getItem('token')}` : '';
          const res = await fetch(
            `${API_BASE}/api/files/ingest-status?file_id=${encodeURIComponent(fileId)}&project_id=${encodeURIComponent(projectId)}${tokenParam}`,
            { headers: getAuthHeaders() }
          );
          if (res.status === 401) {
             window.location.href = '/login';
             return;
          }
          if (!res.ok) { poll(); return; }

          const data = await res.json();
          // WHY: 后端会返回多种终态，只有 pending 和 processing 才需要继续轮询
          const terminalStates = ['vectorized', 'empty_text', 'failed', 'unsupported_format', 'too_large'];
          if (terminalStates.includes(data.status)) {
            setTrackedFiles(prev =>
              prev.map(t =>
                t.file === fileRef
                  ? { ...t, ingestStatus: data.status, chunks: data.chunks || 0, parseProgress: 100 }
                  : t
              )
            );
            pollTimers.current.delete(timerId);
            return;
          } else {
            // WHY: 对于仍处于 pending/processing 状态的，基于尝试次数计算渐进式假进度
            // 公式: 100 - 100 / (1 + (时间(秒) / 30)) -> 30秒时50%, 90秒时75%, 300秒时91%
            const elapsedSeconds = attempt * (POLL_INTERVAL / 1000);
            const progress = Math.min(99, Math.round(100 - 100 / (1 + elapsedSeconds / 30)));
            setTrackedFiles(prev =>
              prev.map(t =>
                t.file === fileRef
                  ? { ...t, parseProgress: progress }
                  : t
              )
            );
          }
        } catch { /* 网络异常静默重试 */ }

        pollTimers.current.delete(timerId);
        poll(); // pending/processing → 继续下一轮
      }, POLL_INTERVAL);

      pollTimers.current.add(timerId);
    };

    poll();
  }, [projectId, getAuthHeaders]);

  // WHY：将文件添加并立即触发上传，保证每一份文件都持久化到服务端磁盘
  const addAndUpload = useCallback(async (newFiles: File[]) => {
    const newTracked: TrackedFile[] = newFiles.map(f => ({
      file: f,
      status: 'pending' as UploadStatus,
    }));

    setTrackedFiles(prev => [...prev, ...newTracked]);

    // 逐个上传（避免瞬间并发把小型服务打爆）
    for (let i = 0; i < newFiles.length; i++) {
      const file = newFiles[i];

      // 更新状态为 uploading
      setTrackedFiles(prev =>
        prev.map(t =>
          t.file === file ? { ...t, status: 'uploading' as UploadStatus } : t
        )
      );

      try {
        const formData = new FormData();
        formData.append('files', file);
        formData.append('project_id', projectId);
        // file.webkitRelativePath 包含了文件连同目录的相对路径，例如 "my_folder/sub_folder/doc.txt"
        // 我们需要剔除最后一级的文件名，只保留相对目录 "my_folder/sub_folder"
        const relativeDir = file.webkitRelativePath ? file.webkitRelativePath.split('/').slice(0, -1).join('/') : '';
        formData.append('relative_path', relativeDir);

        const data = await new Promise<any>((resolve, reject) => {
          const xhr = new XMLHttpRequest();
          xhr.open('POST', `${API_BASE}/api/files/upload`);
          
          const authHeaders = getAuthHeaders() as Record<string, string>;
          Object.keys(authHeaders).forEach(key => {
            xhr.setRequestHeader(key, authHeaders[key]);
          });

          xhr.upload.onprogress = (event) => {
            if (event.lengthComputable) {
              const progress = Math.round((event.loaded * 100) / event.total);
              setTrackedFiles(prev =>
                prev.map(t =>
                  t.file === file ? { ...t, progress } : t
                )
              );
            }
          };

          xhr.onload = () => {
            if (xhr.status >= 200 && xhr.status < 300) {
              try {
                resolve(JSON.parse(xhr.responseText));
              } catch (e) {
                resolve(xhr.responseText);
              }
            } else {
              try {
                const errData = JSON.parse(xhr.responseText);
                reject(new Error(errData.detail || `HTTP ${xhr.status}`));
              } catch (e) {
                reject(new Error(`HTTP ${xhr.status}`));
              }
            }
          };

          xhr.onerror = () => reject(new Error('网络请求失败/中断'));
          xhr.send(formData);
        });
        const serverFile = data.files?.[0];
        const serverPath = serverFile?.path || '';
        const ingestStatus = serverFile?.ingest_status || 'skipped';
        const chunks = serverFile?.chunks || 0;

        setTrackedFiles(prev =>
          prev.map(t =>
            t.file === file
              ? { ...t, status: 'done' as UploadStatus, fileId: serverFile?.id, serverPath, ingestStatus, chunks }
              : t
          )
        );

        // 🔗 如果后台正在解析，启动轮询直到入库完成
        if (ingestStatus === 'pending' && serverFile?.id) {
          pollIngestStatus(serverFile.id, file);
        }
      } catch (err: unknown) {
        const msg = err instanceof Error ? err.message : '未知错误';
        setTrackedFiles(prev =>
          prev.map(t =>
            t.file === file
              ? { ...t, status: 'error' as UploadStatus, error: msg }
              : t
          )
        );
      }
    }
  }, []);

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(true);
  };

  const handleDragLeave = () => setIsDragging(false);

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      addAndUpload(Array.from(e.dataTransfer.files));
    }
  };

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files.length > 0) {
      addAndUpload(Array.from(e.target.files));
      // 重置 input 以便重复选择同名文件
      e.target.value = '';
    }
  };

  const removeFile = async (index: number) => {
    const target = trackedFiles[index];

    // 如果已上传成功，同步删除服务端文件
    if (target.status === 'done' && target.serverPath) {
      try {
        await fetch(
          `${API_BASE}/api/files/delete?file_path=${encodeURIComponent(target.serverPath)}`,
          { method: 'DELETE', headers: getAuthHeaders() }
        );
      } catch {
        // 静默处理：前端侧仍然移除
      }
    }

    setTrackedFiles(prev => prev.filter((_, i) => i !== index));
  };

  const handleRetry = (index: number) => {
    const target = trackedFiles[index];
    if (!target) return;
    
    setTrackedFiles(prev => prev.filter((_, i) => i !== index));
    addAndUpload([target.file]);
  };

  const statusBadge = (tracked: TrackedFile) => {
    switch (tracked.status) {
      case 'pending':
        return (
          <span className="text-[11px] px-2 py-0.5 bg-gray-100 text-gray-500 border border-gray-200 rounded-full">
            排队中
          </span>
        );
      case 'uploading':
        return (
          <div className="flex flex-col items-end gap-1.5">
            <span className="text-[11px] px-2 py-0.5 bg-blue-50 text-blue-600 border border-blue-100 rounded-full flex items-center gap-1">
              <Loader2 className="w-3 h-3 animate-spin" /> 上传中 {tracked.progress !== undefined ? `${tracked.progress}%` : ''}
            </span>
            {tracked.progress !== undefined && (
              <div className="w-20 h-1 bg-gray-100 rounded-full overflow-hidden">
                <div 
                  className="h-full bg-blue-500 transition-all duration-300" 
                  style={{ width: `${tracked.progress}%` }} 
                />
              </div>
            )}
          </div>
        );
      case 'done':
        if (tracked.ingestStatus === 'vectorized') {
          return (
            <span className="text-[11px] px-2 py-0.5 bg-emerald-50 text-emerald-700 border border-emerald-200 rounded-full flex items-center gap-1">
              <CheckCircle2 className="w-3 h-3" /> 已向量化 ({tracked.chunks} chunks)
            </span>
          );
        } else if (tracked.ingestStatus === 'unsupported_format') {
          return (
            <span className="text-[11px] px-2 py-0.5 bg-yellow-50 text-yellow-700 border border-yellow-200 rounded-full flex items-center gap-1">
              <AlertCircle className="w-3 h-3" /> 已保存 (格式待支持)
            </span>
          );
        } else if (tracked.ingestStatus === 'empty_text') {
          return (
            <span className="text-[11px] px-2 py-0.5 bg-orange-50 text-orange-600 border border-orange-200 rounded-full flex items-center gap-1" title="该文件为纯图片扫描件或内容为空，未能提取有效文字。文件已保存。">
              <AlertCircle className="w-3 h-3" /> 扫描件 (无可提取文字)
            </span>
          );
        } else if (tracked.ingestStatus === 'failed') {
          return (
            <span className="text-[11px] px-2 py-0.5 bg-red-50 text-red-600 border border-red-200 rounded-full flex items-center gap-1" title="后台解析过程中发生异常，文件已保存但未入库。">
              <AlertCircle className="w-3 h-3" /> 解析失败
            </span>
          );
        } else if (tracked.ingestStatus === 'too_large') {
          return (
            <span className="text-[11px] px-2 py-0.5 bg-orange-50 text-orange-600 border border-orange-200 rounded-full flex items-center gap-1" title="超大文件体积（>512MB），为保护系统内存已跳过 AI 知识库解析。">
              <AlertCircle className="w-3 h-3" /> 触碰体积界限
            </span>
          );
        } else if (tracked.ingestStatus === 'timeout') {
          return (
            <span className="text-[11px] px-2 py-0.5 bg-red-50 text-red-600 border border-red-200 rounded-full flex items-center gap-1" title="文件复杂可能触发了服务端解析崩溃，或者等待队列超时。文件已保留，但未能进入向量库。">
              <AlertCircle className="w-3 h-3" /> 解析意外中断
            </span>
          );
        } else if (tracked.ingestStatus === 'pending') {
          return (
            <div className="flex flex-col items-end gap-1.5 w-32">
              <span className="text-[11px] px-2 py-0.5 bg-indigo-50 text-indigo-600 border border-indigo-200 rounded-full flex items-center gap-1 animate-pulse">
                <Loader2 className="w-3 h-3 animate-spin" /> 后台解析中 {tracked.parseProgress !== undefined ? `${tracked.parseProgress}%` : ''}
              </span>
              <div className="w-full h-1 bg-gray-100 rounded-full overflow-hidden">
                <div 
                  className="h-full bg-indigo-400 transition-all duration-[3000ms] ease-out" 
                  style={{ width: `${tracked.parseProgress || 0}%` }} 
                />
              </div>
            </div>
          );
        }
        return (
          <span className="text-[11px] px-2 py-0.5 bg-emerald-50 text-emerald-700 border border-emerald-200 rounded-full flex items-center gap-1">
            <CheckCircle2 className="w-3 h-3" /> 已持久化
          </span>
        );
      case 'error':
        return (
          <span className="text-[11px] px-2 py-0.5 bg-red-50 text-red-600 border border-red-200 rounded-full flex items-center gap-1" title={tracked.error}>
            <AlertCircle className="w-3 h-3" /> 失败
          </span>
        );
    }
  };

  // ─── 网络材料入库状态 ───
  const [activeUploadTab, setActiveUploadTab] = useState<'file' | 'url' | 'text' | 'ref'>('file');
  // 公共文档引用状态
  const [refLibraries, setRefLibraries] = useState<any[]>([]);
  const [refLibFiles, setRefLibFiles] = useState<Record<string, any[]>>({});
  const [selectedRefFiles, setSelectedRefFiles] = useState<string[]>([]);
  const [refSelectedLib, setRefSelectedLib] = useState<string>('');
  const [refSearchQuery, setRefSearchQuery] = useState<string>('');
  const [refLoading, setRefLoading] = useState(false);
  const [refSubmitting, setRefSubmitting] = useState(false);
  const [refResult, setRefResult] = useState('');
  const [webUrl, setWebUrl] = useState('');
  const [webTitle, setWebTitle] = useState('');
  const [webLoading, setWebLoading] = useState(false);
  const [webResult, setWebResult] = useState<string>('');
  const [pasteTitle, setPasteTitle] = useState('');
  const [pasteContent, setPasteContent] = useState('');
  const [pasteLoading, setPasteLoading] = useState(false);
  const [pasteResult, setPasteResult] = useState<string>('');

  // 🪄 智能推荐公共文档状态
  const [showRecArea, setShowRecArea] = useState(false);
  const [recommendedFiles, setRecommendedFiles] = useState<any[]>([]);
  const [selectedRecFiles, setSelectedRecFiles] = useState<string[]>([]);
  const [recLoading, setRecLoading] = useState(false);
  const [recSubmitting, setRecSubmitting] = useState(false);
  const [recResult, setRecResult] = useState('');

  const handleWebIngest = async () => {
    if (!webUrl.trim() || webLoading) return;
    setWebLoading(true);
    setWebResult('');
    try {
      const res = await fetch(`${API_BASE}/api/web-ingest/from-url`, {
        method: 'POST',
        headers: { ...getAuthHeaders(), 'Content-Type': 'application/json' },
        body: JSON.stringify({ url: webUrl.trim(), title: webTitle.trim(), project_id: projectId }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || `HTTP ${res.status}`);
      setWebResult(`✅ 「${data.title}」已入库（${data.chunks} 个向量块，${data.text_length} 字）`);
      setWebUrl('');
      setWebTitle('');
    } catch (err: unknown) {
      setWebResult(`❌ ${err instanceof Error ? err.message : '抓取失败'}`);
    } finally {
      setWebLoading(false);
    }
  };

  const handleTextIngest = async () => {
    if (!pasteTitle.trim() || !pasteContent.trim() || pasteLoading) return;
    setPasteLoading(true);
    setPasteResult('');
    try {
      const res = await fetch(`${API_BASE}/api/web-ingest/from-text`, {
        method: 'POST',
        headers: { ...getAuthHeaders(), 'Content-Type': 'application/json' },
        body: JSON.stringify({ title: pasteTitle.trim(), content: pasteContent.trim(), project_id: projectId }),
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || `HTTP ${res.status}`);
      setPasteResult(`✅ 「${data.title}」已入库（${data.chunks} 个向量块，${data.text_length} 字）`);
      setPasteTitle('');
      setPasteContent('');
    } catch (err: unknown) {
      setPasteResult(`❌ ${err instanceof Error ? err.message : '入库失败'}`);
    } finally {
      setPasteLoading(false);
    }
  };

  const doneCount = trackedFiles.filter(f => f.status === 'done').length;

  return (
    <div className="flex flex-col h-full bg-gray-50/30 p-8 text-sm">
      <h2 className="text-lg font-semibold text-gray-800 mb-1 flex items-center gap-2">
        <UploadCloud className="w-5 h-5 text-indigo-500" />
        多模态项目知识资料解析上传舱
      </h2>
      <p className="text-xs text-gray-400 mb-4">支持本地文件上传、网页链接抓取和文本粘贴入库</p>

      {/* Tab 切换 */}
      <div className="flex gap-1 mb-5 bg-gray-100 p-1 rounded-lg w-fit">
        {([
          { key: 'file' as const, label: '📁 上传文件' },
          { key: 'url' as const, label: '🌐 网页链接' },
          { key: 'text' as const, label: '📋 粘贴文本' },
          { key: 'ref' as const, label: '📚 引用公共文档' },
        ]).map(tab => (
          <button
            key={tab.key}
            onClick={() => setActiveUploadTab(tab.key)}
            className={`px-4 py-1.5 rounded-md text-xs font-medium transition-all ${
              activeUploadTab === tab.key
                ? 'bg-white text-indigo-700 shadow-sm'
                : 'text-gray-500 hover:text-gray-700'
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      {/* ─── Tab: 上传文件 ─── */}
      {activeUploadTab === 'file' && (
        <>
          <div
            className={`border-2 border-dashed rounded-xl p-8 flex flex-col items-center justify-center transition-colors ${
              isDragging ? 'border-indigo-400 bg-indigo-50/50' : 'border-gray-300 bg-white'
            }`}
            onDragOver={handleDragOver}
            onDragLeave={handleDragLeave}
            onDrop={handleDrop}
          >
            <div className="w-16 h-16 bg-gray-100 rounded-full flex items-center justify-center mb-4 cursor-default">
              <UploadCloud className="w-8 h-8 text-gray-400" />
            </div>
            <p className="text-base text-gray-700 font-medium mb-4">拖拽 <span className="text-indigo-600">任意项目目录</span> 或各类文档至此区域</p>
            
            <div className="flex gap-4 mb-4">
              <button 
                 onClick={(e) => {
                   e.stopPropagation();
                   if (fileInputRef.current) fileInputRef.current.click();
                 }}
                 className="px-4 py-2 bg-white border border-gray-200 text-gray-700 rounded-lg hover:bg-gray-50 flex items-center gap-2 transition"
              >
                📄 上传文件
              </button>
              
              <button 
                 onClick={(e) => {
                   e.stopPropagation();
                   if (folderInputRef.current) folderInputRef.current.click();
                 }}
                 className="px-4 py-2 bg-indigo-50 border border-indigo-100 text-indigo-700 rounded-lg hover:bg-indigo-100 flex items-center gap-2 transition"
              >
                📁 按目录层级上传项目目录
              </button>
            </div>

            <input
              type="file"
              multiple
              hidden
              ref={fileInputRef}
              onChange={handleChange}
            />
            
            {/* @ts-expect-error - webkitdirectory is non-standard but works */}
            <input type="file" multiple hidden ref={folderInputRef} onChange={handleChange} webkitdirectory="true" />
            
            <p className="text-gray-500 text-xs text-center max-w-md mt-2">
              已挂载特种管道：天然支持技术规范、管理制度、汇报PPT、音频转写、政策标准及其它常规办公文档。系统将自动持久化至后台目录。
            </p>
          </div>

          {trackedFiles.length > 0 && (
            <div className="mt-8">
              <h3 className="text-gray-800 font-medium mb-4 flex justify-between items-center">
                文件列表（{doneCount}/{trackedFiles.length} 已持久化）
                <button
                  onClick={() => setTrackedFiles([])}
                  className="text-xs text-red-500 font-normal hover:underline"
                >
                  全部清空
                </button>
              </h3>
              <div className="space-y-3 max-h-[50vh] overflow-y-auto pr-1">
                {trackedFiles.map((tracked, i) => (
                  <div key={i} className="flex items-center justify-between p-3 bg-white border border-gray-100 rounded-lg shadow-sm">
                    <div className="flex items-center gap-3 min-w-0">
                      {renderTrackedFileIcon(tracked)}
                      <div className="min-w-0">
                        <h4 className="text-gray-700 font-medium text-sm truncate">{tracked.file.name}</h4>
                        <p className="text-gray-400 text-[10px]">
                          {(tracked.file.size / 1024 / 1024).toFixed(2)} MB
                          {tracked.serverPath && (
                            <span className="ml-2 text-gray-300">→ {tracked.serverPath}</span>
                          )}
                        </p>
                      </div>
                    </div>
                    <div className="flex items-center gap-3 shrink-0">
                      {statusBadge(tracked)}
                      {tracked.status === 'error' && (
                        <button onClick={() => handleRetry(i)} className="text-gray-400 hover:text-blue-500" title="重试上传">
                          <RefreshCw className="w-4 h-4" />
                        </button>
                      )}
                      <button onClick={() => removeFile(i)} className="text-gray-400 hover:text-red-500" title="删除">
                        <Trash2 className="w-4 h-4" />
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </>
      )}

      {/* ─── Tab: 网页链接 ─── */}
      {activeUploadTab === 'url' && (
        <div className="bg-white border border-gray-200 rounded-xl p-6 space-y-4">
          <div>
            <label className="block text-xs font-medium text-gray-600 mb-1.5">网页 URL <span className="text-red-400">*</span></label>
            <input
              type="url"
              value={webUrl}
              onChange={e => setWebUrl(e.target.value)}
              placeholder="https://www.pengxi.gov.cn/..."
              className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-indigo-200 focus:border-indigo-400"
            />
          </div>
          <div>
            <label className="block text-xs font-medium text-gray-600 mb-1.5">自定义标题（可选，留空则自动提取）</label>
            <input
              type="text"
              value={webTitle}
              onChange={e => setWebTitle(e.target.value)}
              placeholder="如：蓬溪县2025年政府工作报告"
              className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-indigo-200 focus:border-indigo-400"
            />
          </div>
          <button
            onClick={handleWebIngest}
            disabled={!webUrl.trim() || webLoading}
            className="px-5 py-2 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 disabled:opacity-50 disabled:cursor-not-allowed text-sm font-medium transition-colors flex items-center gap-2"
          >
            {webLoading ? <><Loader2 className="w-4 h-4 animate-spin" /> 正在抓取...</> : '🌐 抓取并入库'}
          </button>
          {webResult && (
            <p className={`text-xs mt-2 p-3 rounded-lg ${webResult.startsWith('✅') ? 'bg-emerald-50 text-emerald-700' : 'bg-red-50 text-red-600'}`}>
              {webResult}
            </p>
          )}
          <p className="text-[11px] text-gray-400">支持政府公报、新闻网页、统计年鉴等公开页面。需要登录的页面请使用「📋 粘贴文本」。</p>
        </div>
      )}

      {/* ─── Tab: 粘贴文本 ─── */}
      {activeUploadTab === 'text' && (
        <div className="bg-white border border-gray-200 rounded-xl p-6 space-y-4">
          <div>
            <label className="block text-xs font-medium text-gray-600 mb-1.5">标题 <span className="text-red-400">*</span></label>
            <input
              type="text"
              value={pasteTitle}
              onChange={e => setPasteTitle(e.target.value)}
              placeholder="如：蓬溪县社会经济概况"
              className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-indigo-200 focus:border-indigo-400"
            />
          </div>
          <div>
            <label className="block text-xs font-medium text-gray-600 mb-1.5">内容 <span className="text-red-400">*</span></label>
            <textarea
              value={pasteContent}
              onChange={e => setPasteContent(e.target.value)}
              placeholder="粘贴网页正文、PDF 复制内容、或手动输入..."
              rows={8}
              className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-indigo-200 focus:border-indigo-400 resize-none"
            />
            <p className="text-[10px] text-gray-400 mt-1 text-right">{pasteContent.length} 字</p>
          </div>
          <button
            onClick={handleTextIngest}
            disabled={!pasteTitle.trim() || !pasteContent.trim() || pasteLoading}
            className="px-5 py-2 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 disabled:opacity-50 disabled:cursor-not-allowed text-sm font-medium transition-colors flex items-center gap-2"
          >
            {pasteLoading ? <><Loader2 className="w-4 h-4 animate-spin" /> 入库中...</> : '📋 入库'}
          </button>
          {pasteResult && (
            <p className={`text-xs mt-2 p-3 rounded-lg ${pasteResult.startsWith('✅') ? 'bg-emerald-50 text-emerald-700' : 'bg-red-50 text-red-600'}`}>
              {pasteResult}
            </p>
          )}
        </div>
      )}

      {/* ─── Tab: 引用公共文档 ─── */}
      {activeUploadTab === 'ref' && (
        <div className="bg-white border border-gray-200 rounded-xl p-6 space-y-4">
          <p className="text-sm text-gray-600 mb-2">从公共文档库中选择文件引用到当前项目，引用不会复制文件。</p>

          <div className="flex flex-wrap gap-3 items-center">
            {refLibraries.length === 0 && !refLoading && (
              <button
                onClick={async () => {
                  setRefLoading(true);
                  setShowRecArea(false);
                  try {
                    const res = await fetch(`${API_BASE}/api/projects`, { headers: getAuthHeaders() });
                    if (res.ok) {
                      const all = await res.json();
                      setRefLibraries(all.filter((p: any) => p.project_type === 'library'));
                    }
                  } catch (e) { console.error(e); }
                  finally { setRefLoading(false); }
                }}
                className="px-4 py-2 bg-indigo-50 text-indigo-600 rounded-lg text-xs font-semibold hover:bg-indigo-100 transition-colors flex items-center gap-2 shadow-sm border border-indigo-100"
              >
                <Library className="w-3.5 h-3.5" /> 加载公共文档库列表
              </button>
            )}

            {!recLoading && (
              <button
                onClick={async () => {
                  setRecLoading(true);
                  setRecResult('');
                  setRefSelectedLib('');
                  setShowRecArea(true);
                  try {
                    const res = await fetch(`${API_BASE}/api/projects/${projectId}/recommend-refs`, { headers: getAuthHeaders() });
                    if (res.ok) {
                      const data = await res.json();
                      const recommended = data.recommended || [];
                      setRecommendedFiles(recommended);
                      setSelectedRecFiles(recommended.map((f: any) => f.id));
                    } else {
                      setRecResult('❌ 智能推荐获取失败');
                    }
                  } catch (e) {
                    setRecResult('❌ 获取推荐网络错误');
                  } finally {
                    setRecLoading(false);
                  }
                }}
                className="px-4 py-2 bg-purple-50 text-purple-700 rounded-lg text-xs font-semibold hover:bg-purple-100 transition-colors flex items-center gap-2 shadow-sm border border-purple-100"
              >
                <span>🪄</span> 智能推荐关联知识 (10部)
              </button>
            )}

            {refLibraries.length > 0 && showRecArea && (
              <button
                onClick={() => {
                  setShowRecArea(false);
                  setRefSelectedLib('');
                }}
                className="px-3 py-1.5 text-xs text-gray-500 hover:text-gray-700 border border-gray-200 rounded-lg bg-white"
              >
                返回常规库列表
              </button>
            )}
          </div>

          {refLoading && <div className="flex justify-center py-4"><Loader2 className="w-5 h-5 animate-spin text-indigo-500" /></div>}

          {/* ─── AI智能推荐展示区 ─── */}
          {showRecArea && (
            <div className="space-y-4 border border-purple-100 bg-purple-50/20 p-5 rounded-xl animate-in fade-in slide-in-from-top-3 duration-300">
              <div className="flex items-center justify-between">
                <div>
                  <h4 className="text-xs font-bold text-purple-950 flex items-center gap-1.5">
                    <span>✨</span>
                    根据项目初步理解，为您智能推荐以下 10 部关联参考文档
                  </h4>
                  <p className="text-[10px] text-purple-500/80 mt-0.5">默认全选，可手动调整后一键关联引用</p>
                </div>
                {recommendedFiles.length > 0 && (
                  <button
                    onClick={() => {
                      if (selectedRecFiles.length === recommendedFiles.length) {
                        setSelectedRecFiles([]);
                      } else {
                        setSelectedRecFiles(recommendedFiles.map(f => f.id));
                      }
                    }}
                    className="text-xs text-purple-650 hover:text-purple-800 hover:underline font-semibold"
                  >
                    {selectedRecFiles.length === recommendedFiles.length ? '取消全选' : '全部勾选'}
                  </button>
                )}
              </div>

              {recLoading && (
                <div className="flex flex-col items-center justify-center py-8 text-purple-600/70">
                  <Loader2 className="w-6 h-6 animate-spin mb-2" />
                  <span className="text-xs">智能模型正在通读分析已上传文档，请稍候...</span>
                </div>
              )}

              {!recLoading && recommendedFiles.length === 0 && (
                <div className="text-center py-6 text-gray-400 text-xs">
                  暂未提取到足够项目特征，或公共库暂无文件。
                </div>
              )}

              {!recLoading && recommendedFiles.length > 0 && (
                <div className="border border-purple-100 rounded-lg max-h-60 overflow-y-auto bg-white">
                  {recommendedFiles.map((file: any) => {
                    const isChecked = selectedRecFiles.includes(file.id);
                    return (
                      <div
                        key={file.id}
                        onClick={() => {
                          setSelectedRecFiles(prev =>
                            prev.includes(file.id)
                              ? prev.filter(id => id !== file.id)
                              : [...prev, file.id]
                          );
                        }}
                        className={`flex items-center gap-2 px-3 py-2.5 text-xs cursor-pointer border-b border-purple-50/50 last:border-b-0 transition-colors ${
                          isChecked ? 'bg-purple-50/40 text-purple-950' : 'hover:bg-purple-50/10 text-gray-700'
                        }`}
                      >
                        <div className="shrink-0">
                          {isChecked ? <CheckSquare className="w-4 h-4 text-purple-600" /> : <Square className="w-4 h-4 text-purple-200" />}
                        </div>
                        <div className="flex-1 min-w-0">
                          <span className="font-semibold block truncate" title={file.filename}>{file.filename}</span>
                          <span className="text-[9px] text-purple-400 font-medium mt-0.5 block">来自公共库：📚 {file.library_name}</span>
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}

              {!recLoading && selectedRecFiles.length > 0 && (
                <button
                  onClick={async () => {
                    setRecSubmitting(true);
                    setRecResult('');
                    try {
                      const groupedRefs: Record<string, string[]> = {};
                      recommendedFiles.forEach(f => {
                        if (selectedRecFiles.includes(f.id)) {
                          if (!groupedRefs[f.library_id]) {
                            groupedRefs[f.library_id] = [];
                          }
                          groupedRefs[f.library_id].push(f.id);
                        }
                      });

                      const refsPayload = Object.entries(groupedRefs).map(([libId, fids]) => ({
                        library_id: libId,
                        file_ids: fids
                      }));

                      const res = await fetch(`${API_BASE}/api/projects/${projectId}/refs/batch`, {
                        method: 'POST',
                        headers: { ...getAuthHeaders(), 'Content-Type': 'application/json' },
                        body: JSON.stringify({ refs: refsPayload }),
                      });

                      if (res.ok) {
                        setRecResult(`✅ 成功关联引用 ${selectedRecFiles.length} 个公共文档`);
                        setSelectedRecFiles([]);
                        setRecommendedFiles([]);
                        setShowRecArea(false);
                      } else {
                        const err = await res.json().catch(() => ({}));
                        setRecResult(`❌ 关联失败: ${err.detail || '未知错误'}`);
                      }
                    } catch (e) {
                      setRecResult('❌ 关联时网络异常');
                    } finally {
                      setRecSubmitting(false);
                    }
                  }}
                  disabled={recSubmitting}
                  className="px-5 py-2 bg-purple-600 text-white rounded-lg hover:bg-purple-700 disabled:opacity-50 text-xs font-semibold transition-colors flex items-center gap-2 shadow-sm"
                >
                  {recSubmitting ? <><Loader2 className="w-3.5 h-3.5 animate-spin" /> 正在引用...</> : `一键引用已选 ${selectedRecFiles.length} 部参考文档`}
                </button>
              )}

              {recResult && (
                <p className={`text-xs p-3 rounded-lg ${recResult.startsWith('✅') ? 'bg-emerald-50 text-emerald-700' : 'bg-red-50 text-red-600'}`}>
                  {recResult}
                </p>
              )}
            </div>
          )}

          {/* 公共文档库卡片 */}
          {!showRecArea && refLibraries.length > 0 && (
            <div className="space-y-2">
              <label className="block text-xs font-medium text-gray-600 mb-1">选择公共文档库</label>
              <div className="flex flex-wrap gap-2">
                {refLibraries.map((lib: any) => (
                  <button
                    key={lib.id}
                    onClick={async () => {
                      setRefSelectedLib(lib.id);
                      setSelectedRefFiles([]);
                      setRefSearchQuery('');
                      if (!refLibFiles[lib.id]) {
                        try {
                          const res = await fetch(
                            `${API_BASE}/api/files/list?project_id=${lib.id}`,
                            { headers: getAuthHeaders() }
                          );
                          if (res.ok) {
                            const data = await res.json();
                            setRefLibFiles(prev => ({ ...prev, [lib.id]: data.files || [] }));
                          }
                        } catch (e) { console.error(e); }
                      }
                    }}
                    className={`px-3 py-2 rounded-lg text-sm font-medium border transition-all ${
                      refSelectedLib === lib.id
                        ? 'border-indigo-400 bg-indigo-50 text-indigo-700'
                        : 'border-gray-200 text-gray-600 hover:bg-gray-50'
                    }`}
                  >
                    📚 {lib.name}
                  </button>
                ))}
              </div>
            </div>
          )}

          {/* 🔍 模糊查询过滤框 */}
          {!showRecArea && refSelectedLib && refLibFiles[refSelectedLib] && refLibFiles[refSelectedLib].length > 0 && (
            <div className="relative">
              <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
                <Search className="h-4 w-4 text-gray-400" />
              </div>
              <input
                type="text"
                value={refSearchQuery}
                onChange={(e) => setRefSearchQuery(e.target.value)}
                placeholder="输入文件名进行模糊过滤..."
                className="w-full pl-9 pr-8 py-2 border border-gray-200 rounded-lg text-xs focus:outline-none focus:ring-2 focus:ring-indigo-200 focus:border-indigo-400 placeholder-gray-400 bg-gray-50/50"
              />
              {refSearchQuery && (
                <button
                  onClick={() => setRefSearchQuery('')}
                  className="absolute inset-y-0 right-0 pr-3 flex items-center text-gray-400 hover:text-gray-600"
                >
                  <X className="h-4 w-4" />
                </button>
              )}
            </div>
          )}

          {/* 文件勾选列表 */}
          {!showRecArea && refSelectedLib && refLibFiles[refSelectedLib] && (() => {
            const filteredRefFiles = refLibFiles[refSelectedLib].filter((file: any) =>
              (file.filename || '').toLowerCase().includes(refSearchQuery.toLowerCase())
            );
            return (
              <div className="border border-gray-100 rounded-lg max-h-60 overflow-y-auto">
                {refLibFiles[refSelectedLib].length === 0 ? (
                  <p className="text-sm text-gray-400 text-center py-4">该库暂无文件</p>
                ) : filteredRefFiles.length === 0 ? (
                  <p className="text-xs text-gray-400 text-center py-6">无匹配的文档（当前库共 {refLibFiles[refSelectedLib].length} 个文件）</p>
                ) : (
                  filteredRefFiles.map((file: any) => {
                    const isChecked = selectedRefFiles.includes(file.id);
                    return (
                      <div
                        key={file.id}
                        onClick={() => {
                          setSelectedRefFiles(prev =>
                            prev.includes(file.id)
                              ? prev.filter(id => id !== file.id)
                              : [...prev, file.id]
                          );
                        }}
                        className={`flex items-center gap-2 px-3 py-2 text-sm cursor-pointer transition-colors ${
                          isChecked ? 'bg-indigo-50 text-indigo-700' : 'hover:bg-gray-50 text-gray-700'
                        }`}
                      >
                        <div className="shrink-0">
                          {isChecked ? <CheckSquare className="w-4 h-4 text-indigo-500" /> : <Square className="w-4 h-4 text-gray-300" />}
                        </div>
                        <span className="truncate flex-1">{file.filename}</span>
                        <span className="text-[10px] text-gray-400 shrink-0">{(file.size / 1024).toFixed(1)} KB</span>
                      </div>
                    );
                  })
                )}
              </div>
            );
          })()}

          {/* 提交按钮 */}
          {!showRecArea && refSelectedLib && selectedRefFiles.length > 0 && (
            <button
              onClick={async () => {
                setRefSubmitting(true);
                setRefResult('');
                try {
                  const res = await fetch(`${API_BASE}/api/projects/${projectId}/refs`, {
                    method: 'POST',
                    headers: { ...getAuthHeaders(), 'Content-Type': 'application/json' },
                    body: JSON.stringify({ library_id: refSelectedLib, file_ids: selectedRefFiles }),
                  });
                  if (res.ok) {
                    setRefResult(`✅ 成功引用 ${selectedRefFiles.length} 个公共文档`);
                    setSelectedRefFiles([]);
                  } else {
                    const err = await res.json().catch(() => ({}));
                    setRefResult(`❌ ${err.detail || '引用失败'}`);
                  }
                } catch (e) {
                  setRefResult('❌ 网络错误');
                } finally {
                  setRefSubmitting(false);
                }
              }}
              disabled={refSubmitting}
              className="px-5 py-2 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 disabled:opacity-50 text-sm font-medium transition-colors flex items-center gap-2"
            >
              {refSubmitting ? <><Loader2 className="w-4 h-4 animate-spin" /> 引用中...</> : `📚 引用 ${selectedRefFiles.length} 个文件`}
            </button>
          )}
          {refResult && (
            <p className={`text-xs mt-2 p-3 rounded-lg ${refResult.startsWith('✅') ? 'bg-emerald-50 text-emerald-700' : 'bg-red-50 text-red-600'}`}>
              {refResult}
            </p>
          )}
        </div>
      )}
    </div>
  );
}
