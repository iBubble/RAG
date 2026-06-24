import { useState } from 'react';
import { useProjectStore } from '../../store/projectStore';
import { Trash2, Copy, Clock, MessageSquareQuote, Minimize2 } from 'lucide-react';

export default function SavedChatSnippets() {
  const savedChatSnippets = useProjectStore(state => state.savedChatSnippets);
  const removeChatSnippet = useProjectStore(state => state.removeChatSnippet);
  const [expandedId, setExpandedId] = useState<string | null>(null);

  if (savedChatSnippets.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center p-12 text-gray-400 h-full w-full">
        <MessageSquareQuote className="w-16 h-16 text-gray-200 mb-4" />
        <p className="text-base font-medium text-gray-500">尚无对话片段素材</p>
        <p className="text-sm mt-2 text-center text-gray-400">在“AI助手”对话中点击各气泡底部的「保存至已存结果」<br/>您的灵感和参考语料将汇聚于此。</p>
      </div>
    );
  }

  // 按时间戳倒序排列
  const sortedSnippets = [...savedChatSnippets].sort((a, b) => b.timestamp - a.timestamp);

  // 精确格式化年月日时分秒时间
  const formatDateTime = (timestamp: number) => {
    const date = new Date(timestamp);
    const yyyy = date.getFullYear();
    const mm = String(date.getMonth() + 1).padStart(2, '0');
    const dd = String(date.getDate()).padStart(2, '0');
    const hh = String(date.getHours()).padStart(2, '0');
    const min = String(date.getMinutes()).padStart(2, '0');
    const ss = String(date.getSeconds()).padStart(2, '0');
    return `${yyyy}-${mm}-${dd} ${hh}:${min}:${ss}`;
  };

  // 如果处于展开态
  if (expandedId !== null) {
    const snippet = savedChatSnippets.find(s => s.id === expandedId);
    
    // 容错：如果找不到（例如刚好被删除），重置为 null
    if (!snippet) {
      setExpandedId(null);
      return null;
    }

    return (
      <div className="w-full h-full px-[10px] py-4 bg-slate-50 overflow-y-auto">
        <div className="w-full bg-white rounded-xl border border-indigo-200 p-6 shadow-md flex flex-col relative animate-in fade-in zoom-in-95 duration-200">
          
          {/* 顶栏控制区域 */}
          <div className="flex items-center justify-between pb-3 mb-4 border-b border-gray-100">
            <div className="flex items-center gap-2 text-xs font-semibold text-gray-500">
              <Clock className="w-4 h-4 text-indigo-500" />
              <span>{formatDateTime(snippet.timestamp)}</span>
              <span className="px-2 py-0.5 bg-indigo-50 text-indigo-700 rounded-md border border-indigo-100 text-[10px]">
                {snippet.tokens} 字
              </span>
            </div>

            <div className="flex items-center gap-3">
              {/* 操作按钮 */}
              <div className="flex items-center gap-1.5">
                <button 
                  onClick={() => {
                    navigator.clipboard.writeText(snippet.content);
                  }}
                  className="p-2 hover:bg-emerald-50 text-emerald-600 rounded-lg transition-colors flex items-center gap-1 text-xs font-medium"
                  title="一键复制"
                >
                  <Copy className="w-4 h-4" />
                  <span>复制</span>
                </button>
                <button 
                  onClick={() => {
                    removeChatSnippet(snippet.id);
                    setExpandedId(null);
                  }}
                  className="p-2 hover:bg-red-50 text-red-500 rounded-lg transition-colors flex items-center gap-1 text-xs font-medium"
                  title="删除此素材"
                >
                  <Trash2 className="w-4 h-4" />
                  <span>删除</span>
                </button>
              </div>

              {/* 还原折叠按钮 */}
              <button
                onClick={() => setExpandedId(null)}
                className="p-2 text-gray-400 hover:text-indigo-600 hover:bg-indigo-50 rounded-lg transition-colors border border-gray-200 hover:border-indigo-200"
                title="收回至列表"
              >
                <Minimize2 className="w-4 h-4" />
              </button>
            </div>
          </div>

          {/* 展开的文本正文 */}
          <div className="text-sm text-gray-700 whitespace-pre-wrap leading-relaxed select-text overflow-y-auto max-h-[50vh] pr-2">
            {snippet.content}
          </div>
        </div>
      </div>
    );
  }

  // 默认双列 Grid 状态
  return (
    <div className="w-full h-full px-[10px] py-4 overflow-y-auto bg-slate-50">
      <div className="mb-4 flex items-center justify-end">
        <span className="text-xs bg-indigo-50 text-indigo-700 px-3 py-1 rounded-full font-medium border border-indigo-100 shadow-sm">
          共收纳 {savedChatSnippets.length} 块核心片段
        </span>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 w-full pb-4">
        {sortedSnippets.map(snippet => (
          <div 
            key={snippet.id} 
            onClick={() => setExpandedId(snippet.id)}
            className="bg-white rounded-xl border border-gray-200 p-4 shadow-sm hover:shadow-md hover:border-indigo-300 transition-all duration-200 group relative flex flex-col cursor-pointer min-h-[140px] max-h-[180px] overflow-hidden select-none"
            title="点击方块展开查看"
          >
            <div className="flex items-center justify-between mb-2 pb-1.5 border-b border-gray-50">
              <div className="flex items-center gap-1.5 text-[11px] font-medium text-gray-400">
                <Clock className="w-3 h-3" />
                <span>{formatDateTime(snippet.timestamp)}</span>
              </div>
              
              <div className="flex items-center gap-1">
                <span className="px-1.5 py-0.5 bg-gray-50 rounded text-[9px] text-gray-400 border border-gray-100 mr-1">
                  {snippet.tokens} 字
                </span>
                <div className="flex items-center opacity-0 group-hover:opacity-100 transition-opacity">
                  <button 
                    onClick={(e) => {
                      e.stopPropagation();
                      navigator.clipboard.writeText(snippet.content);
                    }}
                    className="p-1 hover:bg-emerald-50 text-emerald-600 rounded transition-colors"
                    title="一键复制"
                  >
                    <Copy className="w-3.5 h-3.5" />
                  </button>
                  <button 
                    onClick={(e) => {
                      e.stopPropagation();
                      removeChatSnippet(snippet.id);
                    }}
                    className="p-1 hover:bg-red-50 text-red-500 rounded transition-colors"
                    title="丢弃"
                  >
                    <Trash2 className="w-3.5 h-3.5" />
                  </button>
                </div>
              </div>
            </div>
            
            {/* 列表态正文：使用 line-clamp-4 截断以保持方块一致性 */}
            <div className="text-xs text-gray-600 whitespace-pre-wrap leading-relaxed overflow-hidden line-clamp-4 mt-1">
              {snippet.content}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
