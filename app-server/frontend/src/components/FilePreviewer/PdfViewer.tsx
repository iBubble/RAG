import { useState } from 'react';
import { ZoomIn, ZoomOut, Maximize2, Loader2 } from 'lucide-react';

interface PdfViewerProps {
  url: string;
  filename: string;
}

export default function PdfViewer({ url, filename }: PdfViewerProps) {
  const [scale, setScale] = useState(1);
  const [loading, setLoading] = useState(true);

  const handleZoomIn = () => setScale(prev => Math.min(Number((prev * 1.25).toFixed(2)), 3));
  const handleZoomOut = () => setScale(prev => Math.max(Number((prev / 1.25).toFixed(2)), 0.5));
  const resetZoom = () => setScale(1);

  // 默认 view=FitH 参数使 PDF 在打开时自适应视口宽度完整显示
  const iframeSrc = `${url}#view=FitH&toolbar=1`;

  return (
    <div className="relative w-full h-full overflow-hidden bg-[#1a1b1e] flex flex-col">
      {loading && (
        <div className="absolute inset-0 flex items-center justify-center gap-2 text-gray-300 z-10 bg-[#1a1b1e]/50 backdrop-blur-xs">
          <Loader2 className="w-6 h-6 animate-spin text-blue-400" />
          <span className="text-sm">正在载入 PDF 文档...</span>
        </div>
      )}

      {/* 可视滚动区：默认适应视口，放大后可自然滚动查看 */}
      <div className="flex-1 w-full h-full overflow-auto flex justify-center">
        <div
          style={{
            width: scale > 1 ? `${scale * 100}%` : '100%',
            height: scale > 1 ? `${scale * 100}%` : '100%',
            transform: scale < 1 ? `scale(${scale})` : undefined,
            transformOrigin: 'top center',
            transition: 'transform 0.15s ease-out, width 0.15s ease-out, height 0.15s ease-out',
          }}
          className="w-full h-full flex justify-center"
        >
          <iframe
            src={iframeSrc}
            onLoad={() => setLoading(false)}
            className="w-full h-full border-0 bg-white"
            title={`PDF预览: ${filename}`}
          />
        </div>
      </div>

      {/* 底部悬浮毛玻璃工具栏 */}
      <div className="absolute bottom-4 left-1/2 -translate-x-1/2 z-20 flex items-center gap-1 bg-gray-900/85 backdrop-blur-md px-3 py-1.5 rounded-full border border-white/10 shadow-2xl text-gray-300">
        <button
          type="button"
          onClick={handleZoomOut}
          className="p-1.5 hover:text-white hover:bg-white/10 rounded-full transition-colors"
          title="缩小"
        >
          <ZoomOut className="w-4 h-4" />
        </button>

        <button
          type="button"
          onClick={resetZoom}
          className="px-2 py-0.5 text-xs font-mono font-medium hover:text-white hover:bg-white/10 rounded-full transition-colors min-w-[52px] text-center"
          title="点击恢复适应视口宽度 (100%)"
        >
          {Math.round(scale * 100)}%
        </button>

        <button
          type="button"
          onClick={handleZoomIn}
          className="p-1.5 hover:text-white hover:bg-white/10 rounded-full transition-colors"
          title="放大"
        >
          <ZoomIn className="w-4 h-4" />
        </button>

        <div className="w-[1px] h-4 bg-white/15 mx-1" />

        <button
          type="button"
          onClick={resetZoom}
          className="p-1.5 hover:text-white hover:bg-white/10 rounded-full transition-colors"
          title="适应视口并重置"
        >
          <Maximize2 className="w-4 h-4" />
        </button>
      </div>
    </div>
  );
}
