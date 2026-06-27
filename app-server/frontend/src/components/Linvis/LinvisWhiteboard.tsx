interface WhiteboardProps {
  status: {
    active_tasks: number;
    funny_level: string;
    linvis_name: string;
    whiteboard_items: string[];
    visible_agents: string[];
    whiteboard: {
      total_projects: number;
      total_files: number;
      completed_percent: number;
      total_chunks: number;
      total_entities: number;
      slow_queue_tasks: number;
      fast_queue_tasks: number;
    };
  };
}

export default function LinvisWhiteboard({ status }: WhiteboardProps) {
  const wb = status.whiteboard;
  const items = status.whiteboard_items || [];

  const showItem = (itemId: string) => items.includes(itemId);

  return (
    <div className="w-full bg-white border border-[#e8dcc8] rounded-2xl p-3 px-4 shadow-sm flex flex-col sm:flex-row items-center justify-between gap-3 text-gray-700 select-none">
      {/* 左侧：轻量化标题 */}
      <div className="flex items-center gap-2">
        <span className="text-lg">📊</span>
        <div className="text-left">
          <h2 className="text-sm font-bold text-gray-800 tracking-wide">
            {status.linvis_name || '智能体工作看板'}
          </h2>
        </div>
      </div>

      {/* 中间：横向扁平指标 */}
      <div className="flex flex-wrap items-center justify-center gap-4 text-xs font-medium">
        {showItem('total_projects') && (
          <div className="flex items-center gap-1.5 bg-[#fefaf3] px-2.5 py-1 rounded-lg border border-[#f5e6d3]">
            <span className="text-gray-400">进行中事项:</span>
            <span className="font-bold text-amber-900">{wb.total_projects}</span>
          </div>
        )}
        {showItem('completed_percent') && (
          <div className="flex items-center gap-1.5 bg-[#fefaf3] px-2.5 py-1 rounded-lg border border-[#f5e6d3]">
            <span className="text-gray-400">总文件向量化率:</span>
            <span className="font-bold text-amber-900">{wb.completed_percent}%</span>
          </div>
        )}
        {showItem('total_chunks') && (
          <div className="flex items-center gap-1.5 bg-[#fefaf3] px-2.5 py-1 rounded-lg border border-[#f5e6d3]">
            <span className="text-gray-400">向量切片总数:</span>
            <span className="font-bold text-amber-900">{wb.total_chunks}</span>
          </div>
        )}
        {showItem('total_entities') && (
          <div className="flex items-center gap-1.5 bg-[#fefaf3] px-2.5 py-1 rounded-lg border border-[#f5e6d3]">
            <span className="text-gray-400">图谱实体总数:</span>
            <span className="font-bold text-amber-900">{wb.total_entities}</span>
          </div>
        )}
        {showItem('queue_tasks') && (
          <div className="flex items-center gap-1.5 bg-[#fffbeb] px-2.5 py-1 rounded-lg border border-[#fde68a]">
            <span className="text-gray-400">队列任务:</span>
            <span className="font-bold text-amber-800">
              慢速: {wb.slow_queue_tasks} | 快速: {wb.fast_queue_tasks}
            </span>
          </div>
        )}
      </div>

      {/* 右侧：紧凑字号 */}
      <div className="text-[10px] text-gray-400 italic">
        角色活跃度：{status.funny_level === 'low' ? '低' : status.funny_level === 'medium' ? '中' : '高'}
      </div>
    </div>
  );
}
