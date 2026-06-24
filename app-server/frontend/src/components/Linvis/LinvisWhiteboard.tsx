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
    <div className="w-full bg-[#1e2e22] border-8 border-[#5c3a21] rounded-3xl p-5 shadow-2xl relative overflow-hidden font-mono text-emerald-200">
      {/* 挂环 */}
      <div className="absolute top-2 left-1/4 w-12 h-3 bg-gray-600 rounded-full"></div>
      <div className="absolute top-2 right-1/4 w-12 h-3 bg-gray-600 rounded-full"></div>

      <div className="flex flex-col md:flex-row items-center justify-between gap-4">
        {/* 左侧：粉笔字标题 */}
        <div>
          <h2 className="text-2xl font-bold tracking-widest text-[#f3fbf2] drop-shadow-[0_2px_2px_rgba(0,0,0,0.8)] flex items-center gap-2">
            <span>📝</span> {status.linvis_name || '麟维斯'}
          </h2>
          <p className="text-xs text-emerald-400/80 mt-1">系统全景 AI 调度与资源队列监控</p>
        </div>

        {/* 中间：数据指标 (根据 whiteboard_items 过滤显示) */}
        <div className="flex flex-wrap items-center justify-center gap-6 text-sm">
          {showItem('total_projects') && (
            <div className="text-center bg-[#18251c] px-4 py-2 rounded-xl border border-emerald-900/40">
              <div className="text-xs text-emerald-400">进行中案件</div>
              <div className="text-xl font-bold text-[#faf0d0]">{wb.total_projects}</div>
            </div>
          )}
          {showItem('completed_percent') && (
            <div className="text-center bg-[#18251c] px-4 py-2 rounded-xl border border-emerald-900/40">
              <div className="text-xs text-emerald-400">总文件向量化率</div>
              <div className="text-xl font-bold text-[#faf0d0]">{wb.completed_percent}%</div>
            </div>
          )}
          {showItem('total_chunks') && (
            <div className="text-center bg-[#18251c] px-4 py-2 rounded-xl border border-emerald-900/40">
              <div className="text-xs text-emerald-400">向量切片总数</div>
              <div className="text-xl font-bold text-[#faf0d0]">{wb.total_chunks}</div>
            </div>
          )}
          {showItem('total_entities') && (
            <div className="text-center bg-[#18251c] px-4 py-2 rounded-xl border border-emerald-900/40">
              <div className="text-xs text-emerald-400">图谱实体总数</div>
              <div className="text-xl font-bold text-[#faf0d0]">{wb.total_entities}</div>
            </div>
          )}
          {showItem('queue_tasks') && (
            <div className="text-center bg-[#18251c] px-4 py-2 rounded-xl border border-emerald-900/40">
              <div className="text-xs text-emerald-400">队列任务深度</div>
              <div className="text-xl font-bold text-orange-300">
                慢速: {wb.slow_queue_tasks} | 快速: {wb.fast_queue_tasks}
              </div>
            </div>
          )}
        </div>

        {/* 右侧：纯文本展示搞笑级别 */}
        <div className="text-right">
          <div className="text-[11px] text-emerald-400/60 font-sans italic">
            角色活跃程度：{status.funny_level === 'low' ? '低' : status.funny_level === 'medium' ? '中' : '高'}
          </div>
        </div>
      </div>
    </div>
  );
}
