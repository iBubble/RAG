import { useEffect, useState, useRef, useCallback } from 'react';
import ForceGraph2D from 'react-force-graph-2d';
import { Loader2, AlertCircle } from 'lucide-react';
import { useAuthStore } from '../../store/authStore';

const API_BASE = import.meta.env.VITE_API_BASE || '';

interface Node {
  id: string;
  name: string;
  group: string;
  val?: number;
}

interface Link {
  source: string;
  target: string;
  label: string;
}

interface GraphData {
  nodes: Node[];
  links: Link[];
}

export function GraphVisualizer({ projectId }: { projectId: string }) {
  const [data, setData] = useState<GraphData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const fgRef = useRef<any>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  // WHY: ForceGraph2D 需要精确的像素宽度，不能用 CSS 百分比。
  //      用 ResizeObserver 实时监听容器尺寸，确保画布铺满整个面板。
  const [dimensions, setDimensions] = useState({ width: 800, height: 400 });
  const { getAuthHeaders } = useAuthStore();

  // WHY: 用来存储上一次稳定更新的尺寸，用于阈值过滤，防止布局反馈抖动
  const lastDimensions = useRef(dimensions);

  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;

    let timeoutId: any;

    const observer = new ResizeObserver((entries) => {
      for (const entry of entries) {
        const { width, height } = entry.contentRect;
        if (width > 0 && height > 0) {
          clearTimeout(timeoutId);
          timeoutId = setTimeout(() => {
            const w = Math.floor(width);
            const h = Math.floor(height);
            // WHY: 仅当宽度或高度变化超过 30px 时才触发状态更新，
            //      防止由于 Canvas 挂载、重绘或微调触发的布局反馈环死锁。
            const dx = Math.abs(w - lastDimensions.current.width);
            const dy = Math.abs(h - lastDimensions.current.height);
            if (dx > 30 || dy > 30) {
              const newDim = { width: w, height: h };
              lastDimensions.current = newDim;
              setDimensions(newDim);
              console.log('[GraphVisualizer] 触发防抖尺寸更新:', newDim);
            }
          }, 100);
        }
      }
    });
    observer.observe(el);
    return () => {
      observer.disconnect();
      clearTimeout(timeoutId);
    };
  }, [loading, data]);

  // WHY: 当 dimensions 状态改变且 Canvas 的 HTML width/height 被 React 应用后，
  //      延迟 150ms 强行纠正 D3 力模拟器的中心力点（forceCenter）并重新加热力引擎，
  //      最后调用 zoomToFit，保证无论如何拉伸，节点都能完美居中。
  useEffect(() => {
    if (fgRef.current && data) {
      const timer = setTimeout(() => {
        const center = fgRef.current.d3Force('center');
        if (center) {
          center.x(dimensions.width / 2).y(dimensions.height / 2);
        }
        fgRef.current.d3ReheatSimulation();
        fgRef.current.zoomToFit(400, 20);
        console.log('[GraphVisualizer] 力学中心及视口纠正完成:', dimensions);
      }, 150);
      return () => clearTimeout(timer);
    }
  }, [dimensions, data]);



  useEffect(() => {
    fetch(`${API_BASE}/api/projects/${projectId}/graph/sample`, {
      headers: getAuthHeaders()
    })
      .then(async res => {
        if (!res.ok) {
          let errText = '';
          try {
            errText = await res.text();
          } catch (e) {}
          throw new Error(`失败 (${res.status}): ${errText}`);
        }
        return res.json();
      })
      .then((d: GraphData) => {
        // Pre-process nodes to add a small value based on links
        const nodeDegrees = new Map();
        d.links.forEach(l => {
          nodeDegrees.set(l.source, (nodeDegrees.get(l.source) || 0) + 1);
          nodeDegrees.set(l.target, (nodeDegrees.get(l.target) || 0) + 1);
        });
        d.nodes.forEach(n => {
          n.val = Math.sqrt(nodeDegrees.get(n.id) || 1);
        });
        setData(d);
        setLoading(false);
      })
      .catch(err => {
        setError(err.message);
        setLoading(false);
      });
  }, [projectId]);

  const handleEngineClick = useCallback(() => {
    if (fgRef.current && data) {
      fgRef.current.zoomToFit(400);
    }
  }, [data]);

  if (loading) {
    return (
      <div className="h-[400px] w-full flex items-center justify-center bg-[#0d1117] rounded-xl border border-gray-800">
        <Loader2 className="w-8 h-8 animate-spin text-cyan-500" />
      </div>
    );
  }

  if (error || !data || data.nodes.length === 0) {
    return (
      <div className="h-[400px] w-full flex items-center justify-center bg-[#0d1117] rounded-xl border border-gray-800 text-gray-400 gap-2">
        <AlertCircle className="w-5 h-5" />
        {error || '暂无图谱数据可供可视化'}
      </div>
    );
  }

  // Generate color based on group
  const getNodeColor = (node: Node) => {
    const colors = ['#3b82f6', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6', '#06b6d4', '#f43f5e'];
    let hash = 0;
    for (let i = 0; i < node.group.length; i++) {
      hash = node.group.charCodeAt(i) + ((hash << 5) - hash);
    }
    return colors[Math.abs(hash) % colors.length];
  };

  return (
    <div
      ref={containerRef}
      className="h-[400px] w-full relative bg-[#0d1117] rounded-xl border border-gray-800 overflow-hidden shadow-inner group"
    >
      <div className="absolute top-3 left-4 z-10">
        <div className="text-cyan-400 text-sm font-bold opacity-80 flex items-center gap-2">
          <span className="w-2 h-2 rounded-full bg-cyan-400 animate-pulse"></span>
          星空图谱预览 (Nodes: {data.nodes.length}, Edges: {data.links.length}, Canvas: {dimensions.width}x{dimensions.height})
        </div>
      </div>
      <button 
        onClick={handleEngineClick}
        className="absolute top-3 right-4 z-10 px-3 py-1 bg-white/10 hover:bg-white/20 text-gray-300 rounded text-xs backdrop-blur transition-colors"
      >
        重置视角
      </button>
      <ForceGraph2D
        ref={fgRef}
        graphData={data}
        width={dimensions.width}
        height={dimensions.height}
        nodeLabel="name"
        nodeColor={getNodeColor}
        nodeRelSize={4}
        linkColor={() => 'rgba(255,255,255,0.2)'}
        linkDirectionalParticles={2}
        linkDirectionalParticleSpeed={0.005}
        d3VelocityDecay={0.3}
        onEngineStop={() => fgRef.current?.zoomToFit(400, 20)}
        backgroundColor="#0d1117"
      />
    </div>
  );
}
