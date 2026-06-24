/**
 * CadViewer - DXF/DWG 图纸预览组件
 * WHY: 后端将 CAD 文件渲染为 SVG 或 PNG（大图纸）返回，
 *      前端在深色背景上展示，支持鼠标滚轮缩放和拖拽平移。
 */
import { useState, useEffect, useRef, useCallback } from 'react';
import { Loader2, AlertCircle, ZoomIn, ZoomOut, Maximize2 } from 'lucide-react';
import { useAuthStore } from '../../store/authStore';

const API_BASE = import.meta.env.VITE_API_BASE || '';

interface CadViewerProps {
  filePath: string;
  filename: string;
}

export default function CadViewer({ filePath, filename }: CadViewerProps) {
  const [svgContent, setSvgContent] = useState<string>('');
  const [pngUrl, setPngUrl] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [scale, setScale] = useState(1);
  const [translate, setTranslate] = useState({ x: 0, y: 0 });
  const [dragging, setDragging] = useState(false);
  const [dragStart, setDragStart] = useState({ x: 0, y: 0 });
  const containerRef = useRef<HTMLDivElement>(null);
  const { getAuthHeaders } = useAuthStore();

  useEffect(() => {
    setLoading(true);
    setError(null);
    setSvgContent('');
    setPngUrl(null);
    setScale(1);
    setTranslate({ x: 0, y: 0 });

    fetch(`${API_BASE}/api/files/preview-cad?file_path=${encodeURIComponent(filePath)}`, {
      headers: getAuthHeaders(),
    })
      .then(res => {
        if (!res.ok) return res.text().then(t => { throw new Error(t); });
        const contentType = res.headers.get('content-type') || '';
        if (contentType.includes('image/png')) {
          // WHY: 大型图纸后端会返回 PNG 以避免 60MB+ SVG 卡死浏览器
          return res.blob().then(blob => {
            setPngUrl(URL.createObjectURL(blob));
            setLoading(false);
          });
        } else {
          // SVG 文本
          return res.text().then(svg => {
            setSvgContent(svg);
            setLoading(false);
          });
        }
      })
      .catch(e => {
        setError(e.message);
        setLoading(false);
      });

    return () => {
      // 清理 blob URL
      if (pngUrl) URL.revokeObjectURL(pngUrl);
    };
  }, [filePath]);

  // WHY: 鼠标滚轮缩放
  const handleWheel = useCallback((e: React.WheelEvent) => {
    e.preventDefault();
    const factor = e.deltaY > 0 ? 0.9 : 1.1;
    setScale(prev => Math.min(Math.max(prev * factor, 0.1), 20));
  }, []);

  // WHY: 鼠标拖拽平移
  const handleMouseDown = useCallback((e: React.MouseEvent) => {
    if (e.button !== 0) return;
    setDragging(true);
    setDragStart({ x: e.clientX - translate.x, y: e.clientY - translate.y });
  }, [translate]);

  const handleMouseMove = useCallback((e: React.MouseEvent) => {
    if (!dragging) return;
    setTranslate({
      x: e.clientX - dragStart.x,
      y: e.clientY - dragStart.y,
    });
  }, [dragging, dragStart]);

  const handleMouseUp = useCallback(() => {
    setDragging(false);
  }, []);

  const resetView = useCallback(() => {
    setScale(1);
    setTranslate({ x: 0, y: 0 });
  }, []);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full gap-3 text-gray-400 bg-gray-900">
        <Loader2 className="w-6 h-6 animate-spin text-gray-500" />
        <span className="text-sm text-gray-500">正在渲染 CAD 图纸（大型图纸可能需要 1-3 分钟）...</span>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex flex-col items-center justify-center h-full bg-gray-900 text-red-400 gap-3">
        <AlertCircle className="w-8 h-8" />
        <span className="text-sm text-center max-w-md">{error}</span>
      </div>
    );
  }

  return (
    <div className="relative h-full w-full bg-[#1e1e2e] overflow-hidden">
      {/* 绘图画布 */}
      <div
        ref={containerRef}
        className="h-full w-full cursor-grab active:cursor-grabbing"
        onWheel={handleWheel}
        onMouseDown={handleMouseDown}
        onMouseMove={handleMouseMove}
        onMouseUp={handleMouseUp}
        onMouseLeave={handleMouseUp}
      >
        <div
          className="cad-canvas"
          style={{
            transform: `translate(${translate.x}px, ${translate.y}px) scale(${scale})`,
            transformOrigin: 'center center',
            transition: dragging ? 'none' : 'transform 0.1s ease-out',
          }}
        >
          {svgContent ? (
            <div dangerouslySetInnerHTML={{ __html: svgContent }} />
          ) : pngUrl ? (
            <img
              src={pngUrl}
              alt={filename}
              style={{ maxWidth: '100%', maxHeight: '100%', objectFit: 'contain' }}
              draggable={false}
            />
          ) : null}
        </div>
      </div>

      {/* 缩放控制工具栏 */}
      <div className="absolute top-3 right-3 z-10 flex flex-col gap-1 bg-gray-800/80 backdrop-blur-sm rounded-lg p-1.5 shadow-lg">
        <button
          onClick={() => setScale(prev => Math.min(prev * 1.3, 20))}
          className="p-1.5 text-gray-400 hover:text-white hover:bg-gray-700 rounded transition-colors"
          title="放大"
        >
          <ZoomIn className="w-4 h-4" />
        </button>
        <button
          onClick={() => setScale(prev => Math.max(prev * 0.7, 0.1))}
          className="p-1.5 text-gray-400 hover:text-white hover:bg-gray-700 rounded transition-colors"
          title="缩小"
        >
          <ZoomOut className="w-4 h-4" />
        </button>
        <div className="border-t border-gray-700 my-0.5" />
        <button
          onClick={resetView}
          className="p-1.5 text-gray-400 hover:text-white hover:bg-gray-700 rounded transition-colors"
          title="重置视图"
        >
          <Maximize2 className="w-4 h-4" />
        </button>
      </div>

      {/* 底部信息栏 */}
      <div className="absolute bottom-3 left-3 z-10 bg-gray-800/80 backdrop-blur-sm rounded-lg px-3 py-1.5 text-xs text-gray-400 flex items-center gap-3">
        <span>{filename}</span>
        <span className="text-gray-600">|</span>
        <span>{Math.round(scale * 100)}%</span>
        {pngUrl && <span className="text-yellow-500">栅格模式</span>}
      </div>

      <style>{`
        .cad-canvas {
          display: flex;
          align-items: center;
          justify-content: center;
          width: 100%;
          height: 100%;
        }
        .cad-canvas svg {
          max-width: 95%;
          max-height: 95%;
          filter: invert(1) hue-rotate(180deg);
        }
        .cad-canvas img {
          filter: invert(1) hue-rotate(180deg);
        }
      `}</style>
    </div>
  );
}
