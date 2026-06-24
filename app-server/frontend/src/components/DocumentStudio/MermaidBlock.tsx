/**
 * MermaidBlock.tsx — 可视化 Mermaid 图表编辑器
 * 
 * WHY: 为 Tiptap 编辑器提供 Mermaid 图表的实时渲染预览和可视化编辑能力。
 *      支持三种模式：预览模式（SVG渲染）、代码模式（编辑 Mermaid 源码）、
 *      可视化模式（点击节点编辑、添加/删除节点）。
 */
import React, { useEffect, useState, useRef, useCallback } from 'react';
import mermaid from 'mermaid';

// WHY: 初始化 mermaid，禁用自动启动（由组件手动控制渲染时机）
mermaid.initialize({
  startOnLoad: false,
  theme: 'default',
  securityLevel: 'loose',
  fontFamily: '"Noto Sans SC", "PingFang SC", "Microsoft YaHei", sans-serif',
});

interface MermaidBlockProps {
  code: string;
  onChange: (newCode: string) => void;
  readOnly?: boolean;
}

// WHY: 简单的流程图节点解析器 — 从 Mermaid 源码中提取节点和连接关系
interface FlowNode {
  id: string;
  label: string;
  raw: string; // 原始匹配文本
}

interface FlowEdge {
  from: string;
  to: string;
  label?: string;
  raw: string;
}

function parseFlowChart(code: string): { nodes: FlowNode[]; edges: FlowEdge[]; direction: string } {
  const nodes: FlowNode[] = [];
  const edges: FlowEdge[] = [];
  const nodeMap = new Map<string, FlowNode>();
  let direction = 'TD';

  const lines = code.split('\n');
  for (const line of lines) {
    const trimmed = line.trim();

    // 检测方向声明
    const dirMatch = trimmed.match(/^(?:graph|flowchart)\s+(TD|TB|LR|RL|BT)/i);
    if (dirMatch) {
      direction = dirMatch[1].toUpperCase();
      continue;
    }

    // 检测边（连接关系）: A --> B 或 A -->|label| B
    const edgeMatch = trimmed.match(
      /^(\w+)(?:\[.*?\]|{.*?}|>.*?\]|\(.*?\))?\s*(-+>|=+>|-.->)\s*(?:\|([^|]*)\|\s*)?(\w+)(?:\[.*?\]|{.*?}|>.*?\]|\(.*?\))?/
    );
    if (edgeMatch) {
      const fromId = edgeMatch[1];
      const toId = edgeMatch[4];
      const label = edgeMatch[3] || undefined;
      edges.push({ from: fromId, to: toId, label, raw: trimmed });
    }

    // 检测节点定义：A[文本] 或 A{文本} 或 A(文本) 或 A>文本]
    const nodeMatches = trimmed.matchAll(/(\w+)\s*[\[({>]([^\]})]+)[\])}>]/g);
    for (const m of nodeMatches) {
      if (!nodeMap.has(m[1])) {
        const node: FlowNode = { id: m[1], label: m[2], raw: m[0] };
        nodes.push(node);
        nodeMap.set(m[1], node);
      }
    }
  }

  return { nodes, edges, direction };
}

function rebuildFlowChart(
  nodes: FlowNode[],
  edges: FlowEdge[],
  direction: string
): string {
  const lines = [`graph ${direction}`];

  // 先输出所有边关系（包含节点定义）
  const definedInEdge = new Set<string>();
  for (const edge of edges) {
    const fromNode = nodes.find(n => n.id === edge.from);
    const toNode = nodes.find(n => n.id === edge.to);
    const fromStr = fromNode ? `${fromNode.id}[${fromNode.label}]` : edge.from;
    const toStr = toNode ? `${toNode.id}[${toNode.label}]` : edge.to;
    const labelStr = edge.label ? `|${edge.label}|` : '';
    lines.push(`    ${fromStr} -->${labelStr} ${toStr}`);
    definedInEdge.add(edge.from);
    definedInEdge.add(edge.to);
  }

  // 输出没有出现在边关系中的孤立节点
  for (const node of nodes) {
    if (!definedInEdge.has(node.id)) {
      lines.push(`    ${node.id}[${node.label}]`);
    }
  }

  return lines.join('\n');
}

const MermaidBlock: React.FC<MermaidBlockProps> = ({ code, onChange, readOnly }) => {
  const [svg, setSvg] = useState<string>('');
  const [error, setError] = useState<string>('');
  const [mode, setMode] = useState<'preview' | 'code' | 'visual'>('preview');
  const [editCode, setEditCode] = useState(code);
  const [editingNodeId, setEditingNodeId] = useState<string | null>(null);
  const [editingLabel, setEditingLabel] = useState('');
  const renderRef = useRef(0);
  const containerRef = useRef<HTMLDivElement>(null);

  // WHY: 防抖渲染机制 — 避免每次击键都触发昂贵的 mermaid.render()
  const renderMermaid = useCallback(async (mermaidCode: string) => {
    const currentRender = ++renderRef.current;
    try {
      const id = `mermaid-render-${currentRender}-${Date.now()}`;
      const { svg: renderedSvg } = await mermaid.render(id, mermaidCode);
      if (currentRender === renderRef.current) {
        setSvg(renderedSvg);
        setError('');
      }
    } catch (err: any) {
      if (currentRender === renderRef.current) {
        setError(err.message || '图表语法错误');
        // WHY: 错误时清理 mermaid 生成的残留 DOM
        const errDiv = document.getElementById(`d${renderRef.current}`);
        if (errDiv) errDiv.remove();
      }
    }
  }, []);

  useEffect(() => {
    const timer = setTimeout(() => renderMermaid(editCode), 400);
    return () => clearTimeout(timer);
  }, [editCode, renderMermaid]);

  // WHY: 同步外部 code prop 变化（SSE 流式追加时）
  useEffect(() => {
    setEditCode(code);
  }, [code]);

  const parsed = parseFlowChart(editCode);

  // ── 可视化编辑操作 ──
  const handleNodeClick = (nodeId: string) => {
    if (readOnly) return;
    const node = parsed.nodes.find(n => n.id === nodeId);
    if (node) {
      setEditingNodeId(nodeId);
      setEditingLabel(node.label);
    }
  };

  const handleNodeSave = () => {
    if (!editingNodeId) return;
    const updatedNodes = parsed.nodes.map(n =>
      n.id === editingNodeId ? { ...n, label: editingLabel } : n
    );
    const newCode = rebuildFlowChart(updatedNodes, parsed.edges, parsed.direction);
    setEditCode(newCode);
    onChange(newCode);
    setEditingNodeId(null);
  };

  const handleAddNode = () => {
    const newId = String.fromCharCode(65 + parsed.nodes.length); // A, B, C...
    const newNode: FlowNode = {
      id: newId,
      label: '新步骤',
      raw: `${newId}[新步骤]`,
    };
    const updatedNodes = [...parsed.nodes, newNode];
    // 如果有节点，将新节点连接到最后一个节点
    const updatedEdges = [...parsed.edges];
    if (parsed.nodes.length > 0) {
      const lastNode = parsed.nodes[parsed.nodes.length - 1];
      updatedEdges.push({
        from: lastNode.id,
        to: newId,
        raw: `${lastNode.id} --> ${newId}`,
      });
    }
    const newCode = rebuildFlowChart(updatedNodes, updatedEdges, parsed.direction);
    setEditCode(newCode);
    onChange(newCode);
  };

  const handleDeleteNode = (nodeId: string) => {
    const updatedNodes = parsed.nodes.filter(n => n.id !== nodeId);
    // 删除与该节点相关的所有边，并尝试重连断开的链路
    const inEdges = parsed.edges.filter(e => e.to === nodeId);
    const outEdges = parsed.edges.filter(e => e.from === nodeId);
    let updatedEdges = parsed.edges.filter(e => e.from !== nodeId && e.to !== nodeId);

    // WHY: 智能重连 — 如果被删除节点有且仅有一个入边和一个出边，则将它们直接相连
    if (inEdges.length === 1 && outEdges.length === 1) {
      updatedEdges.push({
        from: inEdges[0].from,
        to: outEdges[0].to,
        raw: `${inEdges[0].from} --> ${outEdges[0].to}`,
      });
    }
    const newCode = rebuildFlowChart(updatedNodes, updatedEdges, parsed.direction);
    setEditCode(newCode);
    onChange(newCode);
  };

  const handleDirectionChange = (dir: string) => {
    const newCode = rebuildFlowChart(parsed.nodes, parsed.edges, dir);
    setEditCode(newCode);
    onChange(newCode);
  };

  const handleCodeChange = (newCode: string) => {
    setEditCode(newCode);
  };

  const handleCodeBlur = () => {
    onChange(editCode);
  };

  return (
    <div className="mermaid-block" ref={containerRef}>
      {/* 工具栏 */}
      <div className="mermaid-toolbar">
        <div className="mermaid-toolbar-left">
          <span className="mermaid-badge">📊 流程图</span>
          {!readOnly && (
            <>
              <button
                className={`mermaid-mode-btn ${mode === 'preview' ? 'active' : ''}`}
                onClick={() => setMode('preview')}
                title="预览模式"
              >
                👁 预览
              </button>
              <button
                className={`mermaid-mode-btn ${mode === 'visual' ? 'active' : ''}`}
                onClick={() => setMode('visual')}
                title="可视化编辑"
              >
                🎯 可视化
              </button>
              <button
                className={`mermaid-mode-btn ${mode === 'code' ? 'active' : ''}`}
                onClick={() => setMode('code')}
                title="代码编辑"
              >
                💻 代码
              </button>
            </>
          )}
        </div>
        {!readOnly && mode === 'visual' && (
          <div className="mermaid-toolbar-right">
            <button className="mermaid-action-btn add" onClick={handleAddNode} title="添加步骤">
              + 添加步骤
            </button>
            <select
              className="mermaid-direction-select"
              value={parsed.direction}
              onChange={e => handleDirectionChange(e.target.value)}
              title="布局方向"
            >
              <option value="TD">↓ 从上到下</option>
              <option value="LR">→ 从左到右</option>
              <option value="BT">↑ 从下到上</option>
              <option value="RL">← 从右到左</option>
            </select>
          </div>
        )}
      </div>

      {/* 内容区 */}
      {error ? (
        <div className="mermaid-error">
          <span>⚠️ 图表语法错误</span>
          <pre>{error}</pre>
        </div>
      ) : mode === 'code' ? (
        <div className="mermaid-code-editor">
          <textarea
            value={editCode}
            onChange={e => handleCodeChange(e.target.value)}
            onBlur={handleCodeBlur}
            spellCheck={false}
            rows={Math.max(5, editCode.split('\n').length + 1)}
          />
        </div>
      ) : mode === 'visual' ? (
        <div className="mermaid-visual-editor">
          {/* SVG 预览 */}
          <div
            className="mermaid-svg-container"
            dangerouslySetInnerHTML={{ __html: svg }}
          />
          {/* 节点列表编辑面板 */}
          <div className="mermaid-node-panel">
            <div className="mermaid-node-panel-title">节点编辑</div>
            {parsed.nodes.map(node => (
              <div
                key={node.id}
                className={`mermaid-node-item ${editingNodeId === node.id ? 'editing' : ''}`}
              >
                {editingNodeId === node.id ? (
                  <div className="mermaid-node-edit-row">
                    <input
                      type="text"
                      value={editingLabel}
                      onChange={e => setEditingLabel(e.target.value)}
                      onKeyDown={e => e.key === 'Enter' && handleNodeSave()}
                      autoFocus
                    />
                    <button className="mermaid-node-save" onClick={handleNodeSave}>✓</button>
                  </div>
                ) : (
                  <div className="mermaid-node-display-row">
                    <span className="mermaid-node-id">{node.id}</span>
                    <span
                      className="mermaid-node-label"
                      onClick={() => handleNodeClick(node.id)}
                      title="点击编辑"
                    >
                      {node.label}
                    </span>
                    <button
                      className="mermaid-node-delete"
                      onClick={() => handleDeleteNode(node.id)}
                      title="删除节点"
                    >
                      ×
                    </button>
                  </div>
                )}
              </div>
            ))}
          </div>

          {/* 节点编辑弹窗 */}
          {editingNodeId && (
            <div className="mermaid-edit-overlay" onClick={() => setEditingNodeId(null)} />
          )}
        </div>
      ) : (
        /* 预览模式 */
        <div
          className="mermaid-svg-container preview-only"
          dangerouslySetInnerHTML={{ __html: svg }}
          onDoubleClick={() => !readOnly && setMode('visual')}
          title={readOnly ? '' : '双击进入编辑模式'}
        />
      )}
    </div>
  );
};

export default MermaidBlock;
