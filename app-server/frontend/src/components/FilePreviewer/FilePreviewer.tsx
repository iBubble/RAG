/**
 * FilePreviewer - 资料预览主控组件
 * WHY: 按文件扩展名分发到不同的专业渲染器：
 *   - .docx → DocxViewer（mammoth.js 富文本）
 *   - .xlsx/.xls → ExcelViewer（SheetJS 表格）
 *   - .pdf/.png/.jpg → iframe 原生渲染
 *   - .dxf/.dwg → CadViewer（后续 P1）
 *   - .shp → MapViewer（后续 P1）
 *   - 其他 → 后端文本提取 + <pre> 兜底
 */
import { useState, useEffect } from 'react';
import { useParams } from 'react-router-dom';
import { useProjectStore } from '../../store/projectStore';
import { useAuthStore } from '../../store/authStore';
import { Eye, FileText, Download, X, Loader2 } from 'lucide-react';
import DocxViewer from './DocxViewer';
import ExcelViewer from './ExcelViewer';
import CadViewer from './CadViewer';

const API_BASE = import.meta.env.VITE_API_BASE || '';

// 浏览器原生可以在 iframe 中直接渲染的格式
const IFRAME_PREVIEWABLE = ['.pdf', '.png', '.jpg', '.jpeg', '.gif', '.webp', '.svg', '.bmp', '.caj'];

// 浏览器原生可直接播放的音视频格式
const VIDEO_FORMATS = ['.mp4', '.webm', '.ogg', '.mov'];
const AUDIO_FORMATS = ['.mp3', '.wav', '.m4a'];
const BLOB_PREVIEWABLE = [...IFRAME_PREVIEWABLE, ...VIDEO_FORMATS, ...AUDIO_FORMATS];

// 前端原生富文本渲染（下载 blob → 前端解析）
const RICH_PREVIEW = ['.docx', '.xlsx', '.xls', '.dxf', '.dwg'];

// 后端 /preview 接口可以提取文本的格式（兜底纯文本）
const TEXT_EXTRACTABLE = [
  '.doc', '.txt', '.csv', '.json', '.xml', '.html', '.htm',
  '.md', '.log', '.pptx',
  '.dbf',
];

function getFileExtension(filename: string): string {
  const dot = filename.lastIndexOf('.');
  return dot >= 0 ? filename.slice(dot).toLowerCase() : '';
}

interface PreviewData {
  type: 'text' | 'image' | 'unsupported';
  filename: string;
  content?: string;
  message?: string;
}

export default function FilePreviewer() {
  const activePreviewFile = useProjectStore(state => state.activePreviewFile);
  const setActivePreviewFile = useProjectStore(state => state.setActivePreviewFile);
  const [previewData, setPreviewData] = useState<PreviewData | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [blobUrl, setBlobUrl] = useState<string | null>(null);
  const [richBlob, setRichBlob] = useState<Blob | null>(null);
  const { getAuthHeaders } = useAuthStore();
  const { id: routeProjectId } = useParams<{ id: string }>();

  const ext = activePreviewFile ? getFileExtension(activePreviewFile.filename) : '';
  // WHY: web/text 来源没有磁盘文件，需要走专用 API 从向量库反查全文
  const isWebSource = activePreviewFile?.source_type === 'web' || activePreviewFile?.source_type === 'text';

  // WHY: 当预览文件变化时，根据来源类型选择对应的预览 API
  useEffect(() => {
    if (!activePreviewFile) {
      setPreviewData(null);
      return;
    }

    // Web/Text 来源：走专用预览接口
    if (isWebSource) {
      setLoading(true);
      setError(null);
      setPreviewData(null);
      // WHY: 从 __web__/{id} 路径中提取 source_id
      const sourceId = activePreviewFile.path.replace('__web__/', '');
      // WHY: project_id 从路由参数获取，web 资料的 path(__web__/{id}) 不含 project_id
      const projectId = routeProjectId || 'default';
      fetch(`${API_BASE}/api/web-ingest/preview/${sourceId}?project_id=${encodeURIComponent(projectId)}`, {
        headers: getAuthHeaders(),
      })
        .then(res => {
          if (!res.ok) throw new Error(`HTTP ${res.status}`);
          return res.json();
        })
        .then(data => setPreviewData(data))
        .catch(e => setError(`预览加载失败: ${e.message}`))
        .finally(() => setLoading(false));
      return;
    }

    const currentExt = getFileExtension(activePreviewFile.filename);
    if (TEXT_EXTRACTABLE.includes(currentExt)) {
      setLoading(true);
      setError(null);
      setPreviewData(null);
      fetch(`${API_BASE}/api/files/preview?file_path=${encodeURIComponent(activePreviewFile.path)}`, {
        headers: getAuthHeaders(),
      })
        .then(res => {
          if (!res.ok) throw new Error(`HTTP ${res.status}`);
          return res.json();
        })
        .then(data => setPreviewData(data))
        .catch(e => setError(`预览加载失败: ${e.message}`))
        .finally(() => setLoading(false));
    } else {
      setPreviewData(null);
    }
  }, [activePreviewFile?.id]);

  // WHY: iframe 与音视频播放器不支持自定义 Authorization Header，
  //      因此对需要 Blob URL 渲染的文件，改用统一的 Blob URL 模式
  useEffect(() => {
    if (blobUrl) {
      URL.revokeObjectURL(blobUrl);
      setBlobUrl(null);
    }
    if (!activePreviewFile) return;
    const currentExt = getFileExtension(activePreviewFile.filename);
    if (BLOB_PREVIEWABLE.includes(currentExt)) {
      const queryParams = currentExt === '.caj' ? '&as_pdf=true' : '';
      fetch(`${API_BASE}/api/files/download?file_path=${encodeURIComponent(activePreviewFile.path)}${queryParams}`, {
        headers: getAuthHeaders(),
      })
        .then(res => {
          if (!res.ok) throw new Error(`HTTP ${res.status}`);
          return res.blob();
        })
        .then(blob => setBlobUrl(URL.createObjectURL(blob)))
        .catch(e => setError(`文件加载失败: ${e.message}`));
    }
    return () => {
      if (blobUrl) URL.revokeObjectURL(blobUrl);
    };
  }, [activePreviewFile?.id]);

  // WHY: 富文本预览（docx/xlsx）需要下载完整 blob 后交给前端解析器
  useEffect(() => {
    setRichBlob(null);
    if (!activePreviewFile) return;
    const currentExt = getFileExtension(activePreviewFile.filename);
    if (RICH_PREVIEW.includes(currentExt)) {
      setLoading(true);
      setError(null);
      fetch(`${API_BASE}/api/files/download?file_path=${encodeURIComponent(activePreviewFile.path)}`, {
        headers: getAuthHeaders(),
      })
        .then(res => {
          if (!res.ok) throw new Error(`HTTP ${res.status}`);
          return res.blob();
        })
        .then(blob => {
          setRichBlob(blob);
          setLoading(false);
        })
        .catch(e => {
          setError(`文件加载失败: ${e.message}`);
          setLoading(false);
        });
    }
  }, [activePreviewFile?.id]);

  if (!activePreviewFile) {
    return (
      <div className="flex flex-col items-center justify-center h-full w-full bg-gray-50/50">
        <Eye className="w-16 h-16 text-gray-200 mb-4" />
        <p className="text-base font-medium text-gray-400">资料预览区</p>
        <p className="text-sm mt-2 text-gray-300 text-center">
          请在左侧资料阵列中<span className="text-blue-400 font-medium">点击文件名</span>，<br />
          即可在此视窗内预览其内容。
        </p>
      </div>
    );
  }

  const canPreviewInIframe = !isWebSource && IFRAME_PREVIEWABLE.includes(ext);
  const isVideo = !isWebSource && VIDEO_FORMATS.includes(ext);
  const isAudio = !isWebSource && AUDIO_FORMATS.includes(ext);
  const canRichPreview = !isWebSource && RICH_PREVIEW.includes(ext);
  const canExtractText = !isWebSource && TEXT_EXTRACTABLE.includes(ext);

  // 下载原件的通用处理器
  const handleDownload = async () => {
    try {
      const res = await fetch(`${API_BASE}/api/files/download?file_path=${encodeURIComponent(activePreviewFile.path)}`, {
        headers: getAuthHeaders(),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = activePreviewFile.filename;
      document.body.appendChild(a);
      a.click();
      URL.revokeObjectURL(url);
      document.body.removeChild(a);
    } catch {
      alert('下载失败');
    }
  };

  return (
    <div className="flex flex-col h-full w-full bg-white">
      {/* 顶部信息条 */}
      <div className="flex items-center justify-between px-5 py-3 border-b border-gray-200 bg-gradient-to-r from-blue-50/60 to-white shrink-0 gap-4">
        <div className="flex items-center gap-3 min-w-0 flex-1">
          <FileText className="w-5 h-5 text-blue-500 shrink-0" />
          <div className="min-w-0 flex-1">
            <p className="font-semibold text-gray-800 text-sm break-all whitespace-normal leading-relaxed" title={activePreviewFile.filename}>
              {activePreviewFile.filename}
            </p>
            <p className="text-[11px] text-gray-400 mt-0.5">
              {activePreviewFile.size >= 1024 * 1024
                ? `${(activePreviewFile.size / 1024 / 1024).toFixed(1)} MB`
                : `${(activePreviewFile.size / 1024).toFixed(1)} KB`}
              {' '}· {ext || '未知格式'}
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          <button
            onClick={handleDownload}
            className="p-2 text-blue-600 hover:text-white bg-blue-50 hover:bg-blue-600 rounded-xl transition-all shadow-sm shrink-0"
            title="下载原件"
          >
            <Download className="w-4 h-4" />
          </button>
          <button
            onClick={() => setActivePreviewFile(null)}
            className="p-2 hover:bg-gray-100 rounded-xl transition-colors text-gray-400 hover:text-gray-600 shrink-0"
            title="关闭预览"
          >
            <X className="w-4 h-4" />
          </button>
        </div>
      </div>

      {/* 预览内容区 */}
      <div className="flex-1 overflow-hidden bg-gray-50">
        {/* ─── 富文本预览：Word ─── */}
        {ext === '.docx' && richBlob && (
          <DocxViewer blob={richBlob} filename={activePreviewFile.filename} />
        )}

        {/* ─── 富文本预览：Excel ─── */}
        {(ext === '.xlsx' || ext === '.xls') && richBlob && (
          <ExcelViewer blob={richBlob} filename={activePreviewFile.filename} />
        )}



        {/* ─── CAD 图纸预览：DXF/DWG ─── */}
        {(ext === '.dxf' || ext === '.dwg') && (
          <CadViewer filePath={activePreviewFile.path} filename={activePreviewFile.filename} />
        )}



        {/* ─── 富文本加载中 ─── */}
        {canRichPreview && !richBlob && loading && (
          <div className="flex items-center justify-center h-full gap-3 text-gray-400">
            <Loader2 className="w-6 h-6 animate-spin" />
            <span className="text-sm">正在加载文件...</span>
          </div>
        )}

        {/* ─── iframe 原生渲染（PDF / 图片）─── */}
        {canPreviewInIframe && blobUrl && (
          <iframe
            src={blobUrl}
            className="w-full h-full border-0"
            title={`预览: ${activePreviewFile.filename}`}
          />
        )}
        {canPreviewInIframe && !blobUrl && !error && (
          <div className="flex items-center justify-center h-full gap-3 text-gray-400">
            <Loader2 className="w-6 h-6 animate-spin" />
            <span className="text-sm">正在加载文件...</span>
          </div>
        )}

        {/* ─── 视频播放预览 ─── */}
        {isVideo && blobUrl && (
          <div className="flex items-center justify-center h-full w-full p-6 bg-gray-950">
            <video
              src={blobUrl}
              controls
              className="max-w-full max-h-full rounded-lg shadow-2xl border border-gray-800"
              title={activePreviewFile.filename}
            />
          </div>
        )}
        {isVideo && !blobUrl && !error && (
          <div className="flex items-center justify-center h-full gap-3 text-gray-400">
            <Loader2 className="w-6 h-6 animate-spin" />
            <span className="text-sm">正在加载视频...</span>
          </div>
        )}

        {/* ─── 音频播放预览 ─── */}
        {isAudio && blobUrl && (
          <div className="flex flex-col items-center justify-center h-full w-full p-8 bg-gradient-to-br from-blue-50/20 via-gray-50 to-indigo-50/20">
            <div className="flex flex-col items-center w-full max-w-md p-8 bg-white/70 backdrop-blur-md rounded-2xl shadow-xl border border-white/40">
              <div className="flex items-end justify-center gap-1.5 h-16 mb-6">
                <div className="w-1.5 bg-blue-500 rounded-full animate-bounce h-8" />
                <div className="w-1.5 bg-indigo-500 rounded-full animate-bounce h-14" style={{ animationDelay: '0.2s' }} />
                <div className="w-1.5 bg-purple-500 rounded-full animate-bounce h-10" style={{ animationDelay: '0.4s' }} />
                <div className="w-1.5 bg-pink-500 rounded-full animate-bounce h-6" style={{ animationDelay: '0.1s' }} />
                <div className="w-1.5 bg-blue-400 rounded-full animate-bounce h-12" style={{ animationDelay: '0.3s' }} />
              </div>
              <p className="text-sm font-semibold text-gray-700 text-center mb-1 truncate w-full" title={activePreviewFile.filename}>
                {activePreviewFile.filename}
              </p>
              <p className="text-xs text-gray-400 mb-6">
                {activePreviewFile.size >= 1024 * 1024
                  ? `${(activePreviewFile.size / 1024 / 1024).toFixed(1)} MB`
                  : `${(activePreviewFile.size / 1024).toFixed(1)} KB`}
              </p>
              <audio
                src={blobUrl}
                controls
                className="w-full focus:outline-none"
              />
            </div>
          </div>
        )}
        {isAudio && !blobUrl && !error && (
          <div className="flex items-center justify-center h-full gap-3 text-gray-400">
            <Loader2 className="w-6 h-6 animate-spin" />
            <span className="text-sm">正在加载音频...</span>
          </div>
        )}

        {/* ─── 文本提取渲染（兜底）─── */}
        {canExtractText && (
          <div className="h-full overflow-y-auto">
            {loading && (
              <div className="flex items-center justify-center h-full gap-3 text-gray-400">
                <Loader2 className="w-6 h-6 animate-spin" />
                <span className="text-sm">正在提取文档内容...</span>
              </div>
            )}

            {previewData?.type === 'text' && previewData.content && (
              <pre className="max-w-[800px] mx-auto px-8 py-6 text-sm text-gray-700 whitespace-pre-wrap font-[system-ui] leading-relaxed">
                {previewData.content}
              </pre>
            )}
          </div>
        )}

        {/* ─── 错误提示 ─── */}
        {error && (
          <div className="flex items-center justify-center h-full text-red-400 text-sm">
            {error}
          </div>
        )}

        {/* ─── 网络/粘贴来源预览 ─── */}
        {isWebSource && (
          <div className="h-full overflow-y-auto">
            {loading && (
              <div className="flex items-center justify-center h-full gap-3 text-gray-400">
                <Loader2 className="w-6 h-6 animate-spin" />
                <span className="text-sm">正在从知识库加载内容...</span>
              </div>
            )}

            {previewData?.type === 'text' && previewData.content && (
              <div className="max-w-[800px] mx-auto px-8 py-6">
                {/* 来源标签 */}
                <div className="flex items-center gap-2 mb-4 pb-3 border-b border-gray-200">
                  <span className="text-lg">{activePreviewFile.source_type === 'web' ? '🌐' : '📋'}</span>
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium text-gray-700 truncate">{previewData.filename}</p>
                    {(previewData as any).source_url && (
                      <a
                        href={(previewData as any).source_url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-xs text-blue-500 hover:underline truncate block"
                      >
                        {(previewData as any).source_url}
                      </a>
                    )}
                  </div>
                  {(previewData as any).chunks && (
                    <span className="text-[11px] text-gray-400 bg-gray-100 px-2 py-0.5 rounded">
                      {(previewData as any).chunks} 个切片
                    </span>
                  )}
                </div>
                {/* 正文 */}
                <pre className="text-sm text-gray-700 whitespace-pre-wrap font-[system-ui] leading-relaxed">
                  {previewData.content}
                </pre>
              </div>
            )}
          </div>
        )}

        {/* ─── 完全不支持的格式 ─── */}
        {!isWebSource && !canPreviewInIframe && !canRichPreview && !canExtractText && !isVideo && !isAudio && (
          <div className="flex flex-col items-center justify-center h-full text-gray-400">
            <FileText className="w-20 h-20 text-gray-200 mb-4" />
            <p className="text-base font-medium text-gray-500">
              {ext} 格式暂不支持浏览器预览
            </p>
            <button
              onClick={handleDownload}
              className="mt-6 flex items-center gap-2 px-5 py-2.5 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors shadow-md text-sm font-medium"
            >
              <Download className="w-4 h-4" />
              点击下载到本地查看
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
