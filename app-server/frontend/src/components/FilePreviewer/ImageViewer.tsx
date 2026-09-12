import React, { useState, useRef } from 'react';
import { ZoomIn, ZoomOut, Maximize2, RotateCw, RotateCcw, Loader2 } from 'lucide-react';

interface ImageViewerProps {
  url: string;
  filename: string;
}

export default function ImageViewer({ url, filename }: ImageViewerProps) {
  const [scale, setScale] = useState(1);
  const [position, setPosition] = useState({ x: 0, y: 0 });
  const [rotation, setRotation] = useState(0);
  const [isDragging, setIsDragging] = useState(false);
  const [dragStart, setDragStart] = useState({ x: 0, y: 0 });
  const [loading, setLoading] = useState(true);
  const containerRef = useRef<HTMLDivElement>(null);

  const resetView = () => {
    setScale(1);
    setPosition({ x: 0, y: 0 });
    setRotation(0);
  };

  const handleZoomIn = () => setScale(prev => Math.min(Number((prev * 1.25).toFixed(2)), 10));
  const handleZoomOut = () => setScale(prev => Math.max(Number((prev / 1.25).toFixed(2)), 0.1));
  const handleRotateRight = () => setRotation(prev => (prev + 90) % 360);
  const handleRotateLeft = () => setRotation(prev => (prev - 90 + 360) % 360);

  const handleWheel = (e: React.WheelEvent) => {
    e.preventDefault();
    const factor = e.deltaY < 0 ? 1.15 : 0.85;
    setScale(prev => Math.min(Math.max(Number((prev * factor).toFixed(2)), 0.1), 10));
  };

  const handleMouseDown = (e: React.MouseEvent) => {
    if (e.button !== 0) return;
    setIsDragging(true);
    setDragStart({ x: e.clientX - position.x, y: e.clientY - position.y });
  };

  const handleMouseMove = (e: React.MouseEvent) => {
    if (!isDragging) return;
    setPosition({ x: e.clientX - dragStart.x, y: e.clientY - dragStart.y });
  };

  const handleMouseUp = () => setIsDragging(false);

  const handleDoubleClick = () => {
    if (scale === 1 && position.x === 0 && position.y === 0) {
      setScale(2);
    } else {
      resetView();
    }
  };

  return (
    <div
      ref={containerRef}
      onWheel={handleWheel}
      onMouseDown={handleMouseDown}
      onMouseMove={handleMouseMove}
      onMouseUp={handleMouseUp}
      onMouseLeave={handleMouseUp}
      onDoubleClick={handleDoubleClick}
      className={`relative w-full h-full overflow-hidden bg-[#121316] flex items-center justify-center select-none ${
        isDragging ? 'cursor-grabbing' : 'cursor-grab'
      }`}
      title="滚轮缩放 / 拖拽平移 / 双击复位或放大"
    >
      {/* 网格透明底纹背景 */}
      <div
        className="absolute inset-0 opacity-15 pointer-events-none"
        style={{
          backgroundImage: `linear-gradient(45deg, #2b2d35 25%, transparent 25%),
            linear-gradient(-45deg, #2b2d35 25%, transparent 25%),
            linear-gradient(45deg, transparent 75%, #2b2d35 75%),
            linear-gradient(-45deg, transparent 75%, #2b2d35 75%)`,
          backgroundSize: '20px 20px',
          backgroundPosition: '0 0, 0 10px, 10px -10px, -10px 0px',
        }}
      />

      {loading && (
        <div className="absolute inset-0 flex items-center justify-center gap-2 text-gray-400 z-10">
          <Loader2 className="w-6 h-6 animate-spin text-blue-400" />
          <span className="text-sm">正在载入图片...</span>
        </div>
      )}

      {/* 核心图像渲染层：默认自适应居中完整显示 */}
      <div
        style={{
          transform: `translate(${position.x}px, ${position.y}px) scale(${scale}) rotate(${rotation}deg)`,
          transition: isDragging ? 'none' : 'transform 0.15s ease-out',
        }}
        className="flex items-center justify-center w-full h-full p-4 pointer-events-none"
      >
        <img
          src={url}
          alt={filename}
          onLoad={() => setLoading(false)}
          className="max-w-full max-h-full object-contain rounded shadow-2xl pointer-events-auto"
          draggable={false}
        />
      </div>

      {/* 底部悬浮毛玻璃工具栏 */}
      <div className="absolute bottom-4 left-1/2 -translate-x-1/2 z-20 flex items-center gap-1 bg-gray-900/85 backdrop-blur-md px-3 py-1.5 rounded-full border border-white/10 shadow-2xl text-gray-300">
        <button
          type="button"
          onClick={handleZoomOut}
          className="p-1.5 hover:text-white hover:bg-white/10 rounded-full transition-colors"
          title="缩小 (快捷: 向下滚轮)"
        >
          <ZoomOut className="w-4 h-4" />
        </button>

        <button
          type="button"
          onClick={resetView}
          className="px-2 py-0.5 text-xs font-mono font-medium hover:text-white hover:bg-white/10 rounded-full transition-colors min-w-[52px] text-center"
          title="点击恢复适应窗口 (100%)"
        >
          {Math.round(scale * 100)}%
        </button>

        <button
          type="button"
          onClick={handleZoomIn}
          className="p-1.5 hover:text-white hover:bg-white/10 rounded-full transition-colors"
          title="放大 (快捷: 向上滚轮)"
        >
          <ZoomIn className="w-4 h-4" />
        </button>

        <div className="w-[1px] h-4 bg-white/15 mx-1" />

        <button
          type="button"
          onClick={resetView}
          className="p-1.5 hover:text-white hover:bg-white/10 rounded-full transition-colors"
          title="适应窗口并重置"
        >
          <Maximize2 className="w-4 h-4" />
        </button>

        <button
          type="button"
          onClick={handleRotateLeft}
          className="p-1.5 hover:text-white hover:bg-white/10 rounded-full transition-colors"
          title="向左旋转90度"
        >
          <RotateCcw className="w-4 h-4" />
        </button>

        <button
          type="button"
          onClick={handleRotateRight}
          className="p-1.5 hover:text-white hover:bg-white/10 rounded-full transition-colors"
          title="向右旋转90度"
        >
          <RotateCw className="w-4 h-4" />
        </button>
      </div>
    </div>
  );
}
