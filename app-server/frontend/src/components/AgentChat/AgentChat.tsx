import { useState, useEffect, useRef } from 'react';
import { User, Loader2, Save, Trash2, Settings as SettingsIcon, X, ArrowUp, Square, FileText } from 'lucide-react';
import { useProjectStore, useChatStore } from '../../store/projectStore';
import { useAuthStore } from '../../store/authStore';
import type { Message } from '../../store/projectStore';
import DataTable from './DataTable';
import MarkdownBlock from './MarkdownBlock';
import SavedChatSnippets from '../SavedResults/SavedChatSnippets';

const API_BASE = import.meta.env.VITE_API_BASE || '';



type OllamaStatus = 'checking' | 'online' | 'offline';

export default function AgentChat({ projectId }: { projectId: string }) {
  const [input, setInput] = useState('');

  const formatMessageTime = (ts?: number | string) => {
    let timestamp = typeof ts === 'number' ? ts : Number(ts);
    if (!timestamp || isNaN(timestamp) || timestamp < 1000000000000) {
      return '';
    }
    try {
      const date = new Date(timestamp);
      if (isNaN(date.getTime())) return '';
      const yyyy = date.getFullYear();
      const mm = String(date.getMonth() + 1).padStart(2, '0');
      const dd = String(date.getDate()).padStart(2, '0');
      const timeStr = date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false });
      return `${yyyy}-${mm}-${dd} ${timeStr}`;
    } catch {
      return '';
    }
  };
  
  const checkedFileIds = useProjectStore(state => state.checkedFileIds);
  const checkedRefIds = useProjectStore(state => state.checkedRefIds);
  // WHY: 合并本案文档 + 公共文档的勾选 ID，确保两者都参与检索
  const allCheckedIds = [...checkedFileIds, ...checkedRefIds];
  const agentMessagesByProject = useProjectStore(state => state.agentMessagesByProject);
  const setProjectMessages = useProjectStore(state => state.setProjectMessages);
  
  const chatStreamingState = useChatStore(state => state.chatStreamingState);
  const sendAgentMessage = useChatStore(state => state.sendAgentMessage);
  const stopAgentMessage = useChatStore(state => state.stopAgentMessage);
  const isGenerating = chatStreamingState.projectId === projectId && chatStreamingState.isGenerating;

  const publicSettings = useProjectStore(state => state.publicSettings);
  const chatAgentNameRaw = publicSettings?.agent_chat_name || '小智 (Agent)';
  const chatAgentName = chatAgentNameRaw.split(' ')[0].split('(')[0].split('（')[0];

  const getAgentAvatarEmoji = (avatar?: string) => {
    if (avatar === 'ox') return '🐮';
    if (avatar === 'horse') return '🐴';
    if (avatar === 'human') return '👤';
    if (avatar === 'robot') return '🤖';
    return '💡';
  };

  const defaultWelcome = `您好！我是您的智能体知识问答助手${chatAgentName}，由本地模型驱动。请问有什么可以帮您？`;
  const messages = agentMessagesByProject[projectId] || [{ id: '1', role: 'agent', content: defaultWelcome }];
  const setMessages = (updater: Message[] | ((prev: Message[]) => Message[])) => setProjectMessages(projectId, updater);

  const addChatSnippet = useProjectStore(state => state.addChatSnippet);
  const selectedModel = useProjectStore(state => state.selectedModel);
  const templateSections = useProjectStore(state => state.templateSections);
  const { getAuthHeaders } = useAuthStore();
  
  const [ollamaStatus, setOllamaStatus] = useState<OllamaStatus>('checking');
  const [isSettingsOpen, setIsSettingsOpen] = useState(false);
  const [isSavedSnippetsOpen, setIsSavedSnippetsOpen] = useState(false);
  const [localPersona, setLocalPersona] = useState('');
  const [isSavingSettings, setIsSavingSettings] = useState(false);
  const [isRecommending, setIsRecommending] = useState(false);

  const [chatMode, setChatMode] = useState<string>('fast');
  const [pastedImage, setPastedImage] = useState<string | null>(null);
  const fetchPublicSettings = useProjectStore(state => state.fetchPublicSettings);
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);

  // 切换项目或加载时，自动 focus 输入框
  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.focus();
    }
  }, [projectId]);

  // 全局拦截粘贴事件并将其定向到当前对话框中
  useEffect(() => {
    const handleGlobalPaste = (e: ClipboardEvent) => {
      const activeEl = document.activeElement;
      // 如果焦点当前在其他的 input 或 textarea 上，不要干涉它
      if (activeEl && (
        activeEl.tagName === 'INPUT' || 
        (activeEl.tagName === 'TEXTAREA' && activeEl !== textareaRef.current)
      )) {
        return;
      }

      const clipboardData = e.clipboardData;
      if (!clipboardData) return;

      let hasImage = false;
      
      // 1. 优先读取 files 里的图片（如本地复制的图片文件、系统截图等）
      const files = clipboardData.files;
      if (files && files.length > 0) {
        for (let i = 0; i < files.length; i++) {
          const file = files[i];
          if (file.type.startsWith('image/')) {
            hasImage = true;
            const reader = new FileReader();
            reader.onload = (event) => {
              if (event.target?.result) {
                setPastedImage(event.target.result as string);
              }
            };
            reader.readAsDataURL(file);
            break;
          }
        }
      }

      // 2. 如果没有读取到，读取 items
      if (!hasImage) {
        const items = clipboardData.items;
        if (items && items.length > 0) {
          for (let i = 0; i < items.length; i++) {
            const item = items[i];
            if (item.type.startsWith('image/') || item.kind === 'file') {
              const file = item.getAsFile();
              if (file && file.type.startsWith('image/')) {
                hasImage = true;
                const reader = new FileReader();
                reader.onload = (event) => {
                  if (event.target?.result) {
                    setPastedImage(event.target.result as string);
                  }
                };
                reader.readAsDataURL(file);
                break;
              }
            }
          }
        }
      }

      // 3. 读取 HTML 里的 img 标签
      if (!hasImage) {
        const htmlText = clipboardData.getData('text/html');
        if (htmlText) {
          const match = htmlText.match(/<img[^>]+src=["'](data:image\/[^"']+)["']/i);
          if (match && match[1]) {
            hasImage = true;
            setPastedImage(match[1]);
          }
        }
      }

      // 如果成功拦截图片，阻止默认操作（例如粘贴本地路径等），并强制聚焦输入框
      if (hasImage) {
        e.preventDefault();
        textareaRef.current?.focus();
      } else {
        // 如果是纯文本粘贴，且当前焦点并不在输入框，将其自动追加并聚焦
        if (activeEl !== textareaRef.current) {
          const text = clipboardData.getData('text/plain');
          if (text) {
            e.preventDefault();
            setInput(prev => prev + text);
            textareaRef.current?.focus();
          }
        }
      }
    };

    window.addEventListener('paste', handleGlobalPaste);
    return () => {
      window.removeEventListener('paste', handleGlobalPaste);
    };
  }, []);

  useEffect(() => {
    if (!publicSettings) {
      fetchPublicSettings();
    }
  }, [publicSettings, fetchPublicSettings]);



  const messagesEndRef = useRef<HTMLDivElement>(null);

  const streamingContent = isGenerating ? chatStreamingState.streamingContent : '';
  const streamingSources = isGenerating ? chatStreamingState.streamingSources : [];

  // When settings open, fetch current persona
  useEffect(() => {
    if (isSettingsOpen) {
      const fetchProjectSettings = async () => {
        try {
          const res = await fetch(`${API_BASE}/api/projects/${projectId || 'default'}`, { headers: getAuthHeaders() });
          if (res.ok) {
            const data = await res.json();
            setLocalPersona(data.metadata?.aiPersona || '');
          }
        } catch {
          // ignore
        }
      };
      fetchProjectSettings();
    }
  }, [isSettingsOpen, projectId]);

  // 轮询 Ollama 状态
  useEffect(() => {
    const checkStatus = async () => {
      try {
        const res = await fetch(`${API_BASE}/api/llm/status`, { headers: getAuthHeaders() });
        const data = await res.json();
        setOllamaStatus(data.status === 'online' ? 'online' : 'offline');
      } catch {
        setOllamaStatus('offline');
      }
    };

    checkStatus();
    const interval = setInterval(checkStatus, 15000); // 每 15 秒刷新
    return () => clearInterval(interval);
  }, []);

  // 自动滚动到底部
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  // 从后端同步当前项目的历史聊天记录，并自动清理可能遗留的流式状态
  useEffect(() => {
    if (!projectId) return;

    const localMsgs = useProjectStore.getState().agentMessagesByProject[projectId];
    const isGeneratingThis = useChatStore.getState().chatStreamingState?.projectId === projectId && useChatStore.getState().chatStreamingState?.isGenerating;

    if (isGeneratingThis || (localMsgs && localMsgs.length > 1)) {
      return;
    }

    const syncChatHistory = async () => {
      try {
        const res = await fetch(`${API_BASE}/api/chat/history?project_id=${projectId}`, { headers: getAuthHeaders() });
        if (res.ok) {
          const data = await res.json();
          if (data.messages && data.messages.length > 0) {
            // 清理异常退出的 isStreaming 状态标记
            const cleaned = data.messages.map((m: any) =>
              m.isStreaming ? { ...m, isStreaming: false, content: m.content || '（回答未完成，已中断）' } : m
            );
            setProjectMessages(projectId, cleaned);
            return;
          }
        }
      } catch (err) {
        console.error('[AgentChat] 同步聊天历史失败:', err);
      }

      // 如果后端无历史记录或获取失败，初始化为默认欢迎语
      setProjectMessages(projectId, [
        { id: '1', role: 'agent', content: defaultWelcome }
      ]);
    };

    syncChatHistory();
  }, [projectId]);

  const handlePaste = (e: React.ClipboardEvent<HTMLTextAreaElement>) => {
    const clipboardData = e.clipboardData;
    if (!clipboardData) return;

    // 1. 优先检查 files 列表（适用于复制本地图片文件、拖拽、截图直接粘贴等情况）
    const files = clipboardData.files;
    if (files && files.length > 0) {
      for (let i = 0; i < files.length; i++) {
        const file = files[i];
        if (file.type.startsWith('image/')) {
          const reader = new FileReader();
          reader.onload = (event) => {
            if (event.target?.result) {
              setPastedImage(event.target.result as string);
            }
          };
          reader.readAsDataURL(file);
          e.preventDefault(); // 阻止默认的文件路径粘贴
          return;
        }
      }
    }

    // 2. 检查 items 列表（适用于微信、飞书、剪切板截图、网页右键复制图片等情况）
    const items = clipboardData.items;
    if (items && items.length > 0) {
      for (let i = 0; i < items.length; i++) {
        const item = items[i];
        if (item.type.startsWith('image/') || item.kind === 'file') {
          const file = item.getAsFile();
          if (file && file.type.startsWith('image/')) {
            const reader = new FileReader();
            reader.onload = (event) => {
              if (event.target?.result) {
                setPastedImage(event.target.result as string);
              }
            };
            reader.readAsDataURL(file);
            e.preventDefault();
            return;
          }
        }
      }
    }

    // 3. 检查是否为 HTML 格式并带有 <img> 标签（部分网页右键“复制图片”可能会放入 HTML）
    const htmlText = clipboardData.getData('text/html');
    if (htmlText) {
      const match = htmlText.match(/<img[^>]+src=["'](data:image\/[^"']+)["']/i);
      if (match && match[1]) {
        setPastedImage(match[1]);
        e.preventDefault();
        return;
      }
    }
  };

  const handleSend = async () => {
    if ((!input.trim() && !pastedImage) || isGenerating) return;
    if (ollamaStatus === 'offline') {
      alert('Ollama 算力服务当前处于离线状态，请先在算力配置中确认或启动服务。');
      return;
    }
    const textToSend = input;
    const imageToSend = pastedImage || undefined;
    setInput('');
    setPastedImage(null);
    sendAgentMessage(projectId, textToSend, chatMode, getAuthHeaders, allCheckedIds, selectedModel, imageToSend);
  };

  const handleStop = () => {
    stopAgentMessage();
  };

  const handleClear = async () => {
    setMessages([{ id: '1', role: 'agent', content: defaultWelcome }]);
    if (projectId) {
      try {
        await fetch(`${API_BASE}/api/chat/history?project_id=${projectId}`, {
          method: 'DELETE',
          headers: getAuthHeaders()
        });
      } catch (err) {
        console.error('[AgentChat] 清空聊天历史失败:', err);
      }
    }
  };

  const handleDeleteMessage = async (messageId: string) => {
    if (!window.confirm('确定要永久删除这条对话记录吗？')) return;
    const updated = messages.filter(m => m.id !== messageId);
    setMessages(updated);
    if (projectId) {
      try {
        await fetch(`${API_BASE}/api/chat/history`, {
          method: 'POST',
          headers: { ...getAuthHeaders(), 'Content-Type': 'application/json' },
          body: JSON.stringify({ project_id: projectId, messages: updated })
        });
      } catch (err) {
        console.error('[AgentChat] 删除单条消息时同步失败:', err);
      }
    }
  };



    const renderMessageContent = (content: string, isStreaming?: boolean) => {
      // WHY: 解析 DuckDB 分析元数据标记
      let daMeta: { sql?: string; result_markdown?: string; row_count?: number; tables_used?: Array<{display: string; name: string; rows: number}> } | null = null;
      let textContent = content;

      const daMatch = content.match(/<!--DA_META:(.+?):DA_META-->/);
      if (daMatch) {
        try {
          daMeta = JSON.parse(daMatch[1]);
        } catch { /* ignore */ }
        textContent = content.replace(/<!--DA_META:.+?:DA_META-->\n?/, '');
      }

      // WHY: 数据分析模式的结果包含 Markdown 表格和 SQL 代码块，
      //      需要特殊渲染组件来展示。
      const renderEnhancedContent = (text: string, isStreaming?: boolean) => {
        // 拆分成段落，识别三种特殊块：Markdown表格、SQL代码块、普通文本
        const blocks: Array<{type: 'text' | 'table' | 'sql', content: string}> = [];
        const lines = text.split('\n');
        let i = 0;

        while (i < lines.length) {
          const line = lines[i];

          // SQL 代码块: ```sql ... ```
          if (line.trim().startsWith('```sql')) {
            const sqlLines: string[] = [];
            i++;
            while (i < lines.length && !lines[i].trim().startsWith('```')) {
              sqlLines.push(lines[i]);
              i++;
            }
            if (i < lines.length) i++; // 跳过 ```
            blocks.push({ type: 'sql', content: sqlLines.join('\n') });
            continue;
          }

          // Markdown 表格: 连续的 | 开头的行
          if (line.trim().startsWith('|') && line.trim().endsWith('|')) {
            const tableLines: string[] = [line];
            i++;
            while (i < lines.length && lines[i].trim().startsWith('|') && lines[i].trim().endsWith('|')) {
              tableLines.push(lines[i]);
              i++;
            }
            if (tableLines.length >= 2) {
              blocks.push({ type: 'table', content: tableLines.join('\n') });
            } else {
              blocks.push({ type: 'text', content: tableLines.join('\n') });
            }
            continue;
          }

          // 普通文本
          const textLines: string[] = [line];
          i++;
          while (i < lines.length
            && !lines[i].trim().startsWith('|')
            && !lines[i].trim().startsWith('```sql')
          ) {
            textLines.push(lines[i]);
            i++;
          }
          blocks.push({ type: 'text', content: textLines.join('\n') });
        }

        return (
          <div className="space-y-2">
            {blocks.map((block, idx) => {
              if (block.type === 'sql') {
                return (
                  <details key={idx} className="group">
                    <summary className="text-xs text-teal-600 font-medium cursor-pointer select-none hover:text-teal-700 flex items-center gap-1.5 w-max py-1">
                      <span className="opacity-80 transition-transform group-open:rotate-90">▹</span>
                      查看执行的 SQL
                    </summary>
                    <div className="mt-1 p-3 bg-gray-900 rounded-lg text-[13px] text-green-400 font-mono whitespace-pre-wrap leading-relaxed overflow-x-auto border border-gray-700">
                      {block.content}
                    </div>
                  </details>
                );
              }

              if (block.type === 'table') {
                return <DataTable key={idx} markdown={block.content} />;
              }

              return (
                <MarkdownBlock key={idx} content={block.content} isStreaming={isStreaming} />
              );
            })}
          </div>
        );
      };

      // WHY: DuckDB 分析元数据由 SSE 直接推送，独立渲染在 LLM 回复之前
      const daBlock = daMeta ? (
        <div className="mb-3">
          {/* SQL 折叠 */}
          {daMeta.sql && (
            <details className="group mb-2">
              <summary className="text-xs text-teal-600 font-medium cursor-pointer select-none hover:text-teal-700 flex items-center gap-1.5 w-max py-1">
                <span className="opacity-80 transition-transform group-open:rotate-90">▹</span>
                查看执行的 SQL
              </summary>
              <div className="mt-1 p-3 bg-gray-900 rounded-lg text-[13px] text-green-400 font-mono whitespace-pre-wrap leading-relaxed overflow-x-auto border border-gray-700">
                {daMeta.sql}
              </div>
            </details>
          )}
          {/* 结果表格 */}
          {daMeta.result_markdown && (
            <DataTable markdown={daMeta.result_markdown} />
          )}
          {/* 数据源标签 */}
          {daMeta.tables_used && daMeta.tables_used.length > 0 && (
            <div className="flex flex-wrap gap-1.5 mt-1.5">
              {daMeta.tables_used.map((t, i) => (
                <span key={i} className="text-[10px] px-2 py-0.5 bg-teal-50 text-teal-600 rounded-full border border-teal-100">
                  📊 {t.display} ({t.rows}行)
                </span>
              ))}
            </div>
          )}
        </div>
      ) : null;

      // 检测回复中是否包含 Markdown 表格或 SQL
      const hasTable = textContent.includes('|') && textContent.includes('---');
      const hasSql = textContent.includes('```sql');
      const needsEnhanced = hasTable || hasSql;

      if (!textContent.includes('<think>')) {
        return (
          <>
            {daBlock}
            {needsEnhanced
              ? renderEnhancedContent(textContent, isStreaming)
              : <MarkdownBlock content={textContent} isStreaming={isStreaming} />
            }
            {isStreaming && (
              <span className="inline-block w-1.5 h-4 bg-indigo-500 ml-0.5 animate-pulse rounded-sm mt-1 align-middle" />
            )}
          </>
        );
      }

    const thinkStartIdx = content.indexOf('<think>');
    const thinkEndIdx = content.indexOf('</think>');
    const preThinkText = content.substring(0, thinkStartIdx);

    if (thinkEndIdx !== -1) {
      const thinkStr = content.substring(thinkStartIdx + 7, thinkEndIdx).trim();
      const normalStr = content.substring(thinkEndIdx + 8);
      return (
        <div className="space-y-3">
          {preThinkText && <MarkdownBlock content={preThinkText} isStreaming={isStreaming} />}
          {thinkStr && (
            <details className="mb-3 group">
              <summary className="text-xs text-indigo-400 font-medium cursor-pointer select-none hover:text-indigo-500 flex items-center gap-1.5 w-max">
                <span className="opacity-80 transition-transform group-open:rotate-90">▹</span>
                深度思考过程
              </summary>
              <div className="mt-2 p-3 bg-gray-50/80 rounded-lg text-[13px] text-gray-500 border border-gray-100 whitespace-pre-wrap leading-relaxed shadow-sm">
                {thinkStr}
              </div>
            </details>
          )}
          {normalStr && <MarkdownBlock content={normalStr} isStreaming={isStreaming} />}
        </div>
      );
    } else {
      const thinkStr = content.substring(thinkStartIdx + 7).trim();
      const isTruncated = !isStreaming;
      return (
        <div className="space-y-3">
          {preThinkText && <MarkdownBlock content={preThinkText} isStreaming={isStreaming} />}
          <div className="mb-3">
            <div className={`text-xs font-medium pb-1.5 flex items-center gap-1.5 w-max border-b ${isTruncated ? 'text-amber-500 border-amber-200' : 'text-indigo-400 border-indigo-100'}`}>
              {isTruncated ? (
                <><span className="opacity-80">⚠️</span> 推理过程被截断（输出已达上限）</>
              ) : (
                <><Loader2 className="w-3.5 h-3.5 animate-spin" /> AI 正在推理思考中...</>
              )}
            </div>
            <div className={`mt-2 p-3 rounded-lg text-[13px] whitespace-pre-wrap leading-relaxed border overflow-hidden relative flex flex-col justify-end max-h-[4.5rem] ${isTruncated ? 'bg-amber-50/40 text-amber-600/80 border-amber-100' : 'bg-indigo-50/40 text-indigo-500/80 border-indigo-50'}`}>
              <div className="opacity-80">
                {thinkStr.length > 150 ? '...' + thinkStr.slice(-150) : thinkStr}
                {isStreaming && !isTruncated && <span className="inline-block w-1.5 h-3.5 bg-indigo-400 ml-1 animate-pulse align-middle" />}
              </div>
            </div>
          </div>
        </div>
      );
    }
  };



  return (
    <div className="flex flex-col h-full bg-white text-gray-800">
      {/* Header with LLM Status Indicator */}
      {/* Header */}
      <div className="p-3 pb-2 shrink-0 flex items-center justify-between bg-white relative">
        <h2 className="font-semibold text-gray-700 flex items-center gap-2 text-sm z-10">
          <span className="text-base">{getAgentAvatarEmoji(publicSettings?.agent_chat_avatar)}</span>
          {chatAgentName}
        </h2>
        <div className="flex items-center gap-1 z-10">
          <button
            onClick={() => setIsSettingsOpen(true)}
            className="p-1.5 text-gray-400 hover:text-[#8B7355] hover:bg-gray-50 rounded transition-colors flex items-center gap-1 text-xs"
            title="助手与算力设定"
          >
            <SettingsIcon className="w-3.5 h-3.5" />
            配置
          </button>
          <button
            onClick={() => setIsSavedSnippetsOpen(true)}
            className="p-1.5 text-gray-400 hover:text-[#8B7355] hover:bg-gray-50 rounded transition-colors flex items-center gap-1 text-xs"
            title="查看已存对话素材"
          >
            <FileText className="w-3.5 h-3.5" />
            已存信息
          </button>
          <button
            onClick={handleClear}
            className="p-1.5 text-gray-400 hover:text-red-500 hover:bg-gray-50 rounded transition-colors flex items-center gap-1 text-xs"
            title="清空对话历史"
          >
            <Trash2 className="w-3.5 h-3.5" />
            清空
          </button>
        </div>

        {/* Saved Snippets Modal */}
        {isSavedSnippetsOpen && (
          <div className="fixed inset-0 bg-stone-900/40 backdrop-blur-sm flex items-center justify-center z-50 p-4">
            <div className="bg-white rounded-xl border border-stone-200 shadow-xl w-full max-w-2xl max-h-[80vh] overflow-hidden flex flex-col">
              <div className="px-4 py-3 bg-stone-50 border-b border-stone-200 flex justify-between items-center shrink-0">
                <span className="text-xs font-bold text-stone-700">AI 对话素材库 (已存信息)</span>
                <button 
                  onClick={() => setIsSavedSnippetsOpen(false)} 
                  className="text-stone-400 hover:text-stone-600 text-sm font-bold p-1 hover:bg-stone-100 rounded-full transition-colors"
                >
                  <X className="w-4 h-4" />
                </button>
              </div>
              <div className="flex-1 overflow-y-auto min-h-0">
                <SavedChatSnippets />
              </div>
            </div>
          </div>
        )}

        {/* Settings Dropdown Overlay */}
        {isSettingsOpen && (
          <div className="absolute top-full left-0 right-0 z-50 bg-white/95 backdrop-blur-md p-4 pb-4 flex flex-col shadow-xl border-b border-gray-200 animate-in fade-in slide-in-from-top-2 duration-200" style={{ maxHeight: '60vh', height: '360px' }}>
            <button 
              onClick={() => setIsSettingsOpen(false)}
              className="absolute top-3 right-3 p-1 text-gray-400 hover:text-gray-700 hover:bg-gray-100 rounded-full transition-colors"
            >
              <X className="w-4 h-4" />
            </button>
            <h3 className="text-gray-800 font-semibold mb-4 text-sm flex items-center gap-2">
              <SettingsIcon className="w-[18px] h-[18px] text-indigo-500" />
              AI助手配置
            </h3>
            
            <div className="space-y-4 flex-1 overflow-y-auto pr-1">
              
              <div className="space-y-1.5">
                <label className="text-xs font-semibold text-gray-600">项目专属系统角色词 (Prompt Persona)</label>
                <textarea 
                  value={localPersona}
                  onChange={(e) => setLocalPersona(e.target.value)}
                  placeholder="【Qwen 模型最佳示范 - 您可直接照抄修改】&#10;1. 身份定位：你是一个极其专业且严谨的企业管理顾问与文档编写专家，没有任何情感色彩。&#10;2. 核心任务：根据上传的背景资料，输出干练的报告、分析大纲、摘要或规划书，绝不捏造任何未提供的数据。&#10;3. 风格红线约束：&#10;   - 【极度禁止】输出任何客服废话（如：好的、首先、希望对您有帮助）。&#10;   - 直接抛出第一句正文干货，客观冰冷，直奔主题。&#10;   - 专业表述严格遵循相关行业标准及企业管理规范。"
                  className="w-full h-40 resize-none text-[13px] p-2.5 bg-gray-50 border border-gray-200 rounded-lg focus:outline-none focus:ring-1 focus:ring-indigo-500 placeholder:text-gray-400 placeholder:leading-relaxed leading-relaxed"
                />
                <button
                  onClick={async () => {
                    setIsRecommending(true);
                    try {
                      const res = await fetch(`${API_BASE}/api/recommend-persona`, {
                        method: 'POST',
                        headers: { ...getAuthHeaders(), 'Content-Type': 'application/json' },
                        body: JSON.stringify({ 
                          project_id: projectId || 'default',
                          model: selectedModel,
                          // WHY: 传入大纲标题让后端推断报告类型
                          template_sections: templateSections
                            .map(s => s.title)
                            .filter(Boolean),
                        })
                      });
                      if (res.ok) {
                        const text = await res.text();
                        // WHY: 后端使用 StreamingResponse 保活，body 可能以大量空格开头。
                        //      trim 后再 parse JSON，确保兼容。
                        const trimmed = text.trim();
                        if (!trimmed) {
                          alert('推荐结果为空，请稍后重试');
                        } else {
                          try {
                            const data = JSON.parse(trimmed);
                            if (data.persona) {
                               setLocalPersona(data.persona);
                            } else if (data.detail) {
                              alert(data.detail);
                            } else {
                              alert('推荐结果格式异常');
                            }
                          } catch {
                            alert('推荐结果解析失败');
                          }
                        }
                      } else {
                        const err = await res.json().catch(() => ({}));
                        alert(err.detail || '推荐失败，请稍后重试');
                      }
                    } catch (e) {
                      console.error(e);
                      alert('网络异常，请稍后重试');
                    } finally {
                      setIsRecommending(false);
                    }
                  }}
                  disabled={isRecommending}
                  className="mt-1.5 px-3 py-1.5 text-[12px] font-medium text-indigo-600 bg-indigo-50 hover:bg-indigo-100 border border-indigo-200 rounded-lg transition-colors flex items-center gap-1.5 disabled:opacity-50"
                >
                  {isRecommending ? <Loader2 className="w-3 h-3 animate-spin" /> : <span>🪄</span>}
                  {isRecommending ? '正在分析案件资料...' : '根据资料智能推荐'}
                </button>
              </div>
            </div>

            <div className="pt-3 mt-auto flex justify-end gap-2 border-t border-gray-100">
              <button 
                onClick={() => setIsSettingsOpen(false)}
                className="px-4 py-1.5 text-[13px] text-gray-500 hover:bg-gray-100 rounded-lg transition-colors"
              >
                取消
              </button>
              <button 
                onClick={async () => {
                  setIsSavingSettings(true);
                  try {
                    const pRes = await fetch(`${API_BASE}/api/projects/${projectId || 'default'}`, { headers: getAuthHeaders() });
                    const pData = await pRes.json();
                    const existingMeta = pData.metadata || {};
                    const saveRes = await fetch(`${API_BASE}/api/projects/${projectId || 'default'}`, {
                      method: 'PUT',
                      headers: { ...getAuthHeaders(), 'Content-Type': 'application/json' },
                      body: JSON.stringify({ metadata: { ...existingMeta, aiPersona: localPersona } })
                    });
                    if (saveRes.ok) setIsSettingsOpen(false);
                  } catch(e) {
                    console.error(e);
                  } finally {
                    setIsSavingSettings(false);
                  }
                }}
                disabled={isSavingSettings}
                className="px-4 py-1.5 text-[13px] font-medium bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 transition-shadow shadow-sm flex items-center gap-1.5"
              >
                {isSavingSettings ? <Loader2 className="w-3.5 h-3.5 animate-spin"/> : <Save className="w-3.5 h-3.5" />}
                保存设定
              </button>
            </div>
          </div>
        )}
      </div>

      {/* Message List */}
      <div className="flex-1 overflow-y-auto p-4 space-y-6">
        {messages.map(msg => (
          <div key={msg.id} className="flex flex-col">
            <div className={`flex gap-3 ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
              {msg.role === 'agent' && (
                <div className="w-8 h-8 rounded-full bg-gray-50 flex items-center justify-center shrink-0 border border-gray-100" title={chatAgentName}>
                  <span className="text-base">{getAgentAvatarEmoji(publicSettings?.agent_chat_avatar)}</span>
                </div>
              )}

              <div className={`max-w-[75%] px-4 py-2.5 rounded-2xl text-sm leading-relaxed group relative ${
                msg.role === 'user'
                  ? 'bg-[#D6CCF9] text-gray-800 rounded-tr-sm shadow-sm'
                  : 'bg-white text-gray-800 shadow-sm border border-[#E0DCD5]/60 rounded-tl-sm'
              }`}>
                {!msg.isStreaming && msg.id !== '1' && (
                  <button
                    onClick={() => handleDeleteMessage(msg.id)}
                    className={`absolute top-2 right-2 opacity-0 group-hover:opacity-100 transition-opacity duration-200 p-1.5 rounded-lg cursor-pointer ${
                      msg.role === 'user'
                        ? 'text-purple-700 hover:text-red-700 hover:bg-[#c5b8f7]'
                        : 'text-gray-400 hover:text-red-500 hover:bg-gray-100'
                    }`}
                    title="永久删除此条对话"
                  >
                    <Trash2 className="w-3.5 h-3.5" />
                  </button>
                )}
                {/* WHY: 用户消息不需要 Markdown 解析，直接纯文本渲染保持白色字体；
                         Agent 消息使用 MarkdownBlock 渲染结构化内容 */}
                {msg.role === 'user'
                  ? (
                    <div className="space-y-2">
                      {msg.image && (
                        <div className="relative">
                          <img 
                            src={msg.image} 
                            alt="Pasted content" 
                            className="max-w-[240px] max-h-40 object-contain rounded-xl border border-[#C4B5A0]/30 shadow-sm cursor-zoom-in hover:brightness-95 transition-all bg-white" 
                            onClick={() => {
                              const w = window.open();
                              if (w) w.document.write(`<img src="${msg.image}" style="max-width:100%; max-height:99vh; display:block; margin:auto;" />`);
                            }}
                          />
                        </div>
                      )}
                      <div className="whitespace-pre-wrap">{msg.content}</div>
                    </div>
                  )
                  : renderMessageContent(msg.isStreaming ? streamingContent : msg.content, msg.isStreaming)
                }
                
                {((msg.isStreaming ? streamingSources : msg.sources) || []).length > 0 && (
                  <div className="mt-3 pt-2 border-t border-gray-100 flex flex-wrap gap-1.5 items-center text-gray-500">
                    <span className="text-[11px] text-gray-400 mr-0.5 whitespace-nowrap">参考来源：</span>
                    {(msg.isStreaming ? streamingSources : msg.sources)!.map((src, i) => (
                      <span key={i} className="text-[11px] px-1.5 py-0.5 bg-gray-200/50 rounded text-gray-600 border border-gray-200/60 max-w-[180px] truncate" title={src}>
                        {src}
                      </span>
                    ))}
                  </div>
                )}

                {msg.role === 'agent' && !msg.isStreaming && msg.stats && (
                  <div className="mt-3 pt-2 border-t border-gray-200/60 flex items-center justify-between text-[11px] text-gray-400 select-none">
                    <div className="flex items-center gap-3">
                      <span>用时: {msg.stats.time}s</span>
                      <span>长度: {msg.stats.tokens} 字</span>
                      <span>速度: {msg.stats.speed} 字符/s</span>
                      {formatMessageTime(msg.timestamp || msg.id) && (
                        <span className="opacity-80">时间: {formatMessageTime(msg.timestamp || msg.id)}</span>
                      )}
                    </div>
                    <button 
                      onClick={(e) => {
                        navigator.clipboard.writeText(msg.content);
                        addChatSnippet({
                          id: Date.now().toString(),
                          content: msg.content,
                          timestamp: Date.now(),
                          tokens: msg.stats?.tokens || msg.content.length
                        });
                        const btn = e.currentTarget;
                        const originalHtml = btn.innerHTML;
                        btn.innerHTML = '<span class="text-[#8B7355] font-medium">已保存至剪贴板 ✓</span>';
                        setTimeout(() => { btn.innerHTML = originalHtml; }, 2000);
                      }}
                      className="flex items-center gap-1 hover:text-[#8B7355] transition-colors cursor-pointer text-gray-500 hover:bg-gray-100 px-2 py-0.5 rounded shadow-sm border border-transparent hover:border-gray-200"
                      title="复制到剪贴板并存入已存结果"
                    >
                      <Save className="w-3 h-3" />
                      保存
                    </button>
                  </div>
                )}
              </div>

              {msg.role === 'user' && (
                <div className="w-8 h-8 rounded-full bg-[#E8E2FC] flex items-center justify-center shrink-0">
                  <User className="w-4 h-4 text-[#6A4FC2]" />
                </div>
              )}
            </div>
            {msg.role === 'user' && formatMessageTime(msg.timestamp || msg.id) && (
              <div className="text-[10px] text-gray-400 mt-1 mr-11 select-none text-right">
                {formatMessageTime(msg.timestamp || msg.id)}
              </div>
            )}
          </div>
        ))}
        <div ref={messagesEndRef} />
      </div>

      <div className="p-4 border-t border-[#E0DCD5]/60 bg-transparent shrink-0">
        {/* Chat Mode Switch Pills */}
        <div className="flex items-center gap-1 mb-3 bg-[#F6F5F2] border border-[#E0DCD5] rounded-full p-0.5 w-fit select-none">
          <button
            type="button"
            onClick={() => setChatMode('fast')}
            className={`flex items-center gap-1 px-4 py-1.5 rounded-full text-xs font-semibold cursor-pointer transition-all duration-200 ${
              chatMode === 'fast'
                ? 'bg-[#1F2937] text-white shadow-sm'
                : 'text-gray-500 hover:text-gray-800'
            }`}
          >
            <span>⚡</span>
            <span>快速</span>
          </button>
          <button
            type="button"
            onClick={() => setChatMode('smart')}
            className={`flex items-center gap-1 px-4 py-1.5 rounded-full text-xs font-semibold cursor-pointer transition-all duration-200 ${
              chatMode === 'smart'
                ? 'bg-[#1F2937] text-white shadow-sm'
                : 'text-gray-500 hover:text-gray-800'
            }`}
          >
            <span>🧠</span>
            <span>深度思考</span>
          </button>
        </div>

        {pastedImage && (
          <div className="relative inline-block mb-3 p-1.5 bg-white/75 backdrop-blur-md border border-[#E0DCD5] rounded-2xl shadow-md shrink-0">
            <img 
              src={pastedImage} 
              alt="Pasted Preview" 
              className="max-h-24 max-w-[150px] object-contain rounded-xl border border-gray-100 bg-white" 
            />
            <button
              onClick={() => setPastedImage(null)}
              className="absolute -top-1.5 -right-1.5 w-5 h-5 rounded-full bg-[#EA4335]/90 hover:bg-[#EA4335] text-white flex items-center justify-center text-[10px] cursor-pointer shadow-md transition-colors font-bold"
              title="移除图片"
            >
              ✕
            </button>
          </div>
        )}
        <div className="relative">
          <textarea
            ref={textareaRef}
            value={input}
            onChange={e => setInput(e.target.value)}
            onPaste={handlePaste}
            onKeyDown={e => {
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                handleSend();
              }
            }}
            placeholder="提问或创作内容"
            className="w-full resize-none bg-white border border-[#C4B5A0] rounded-[28px] pr-28 pl-5 py-3 text-sm focus:outline-none focus:ring-2 focus:ring-[#8B7355]/40 focus:border-[#8B7355] shadow-sm disabled:bg-gray-100 disabled:text-gray-400"
            rows={1}
            style={{ minHeight: '48px' }}
          />
          <div className="absolute right-2 top-[45%] -translate-y-1/2 flex items-center gap-1.5">
            {allCheckedIds.length > 0 && (
              <span className="text-[11px] text-gray-600 bg-[#F0EDE8] px-2 py-1 rounded-full border border-[#E0DCD5] shrink-0 font-medium select-none" title={`本案 ${checkedFileIds.length} + 公共 ${checkedRefIds.length}`}>
                {allCheckedIds.length} 个来源
              </span>
            )}
            {isGenerating ? (
              <button
                onClick={handleStop}
                className="w-9 h-9 rounded-full bg-[#EA4335] text-white hover:bg-[#D93025] flex items-center justify-center transition-colors shadow-sm"
                title="停止生成"
              >
                <Square className="w-3.5 h-3.5 fill-white" />
              </button>
            ) : (
              <button
                onClick={handleSend}
                disabled={!input.trim() && !pastedImage}
                className="w-9 h-9 rounded-full bg-[#5F6368] text-white hover:bg-[#474B4F] disabled:bg-gray-200 disabled:text-gray-400 disabled:cursor-not-allowed flex items-center justify-center transition-colors shadow-sm"
              >
                <ArrowUp className="w-4 h-4" />
              </button>
            )}
          </div>
        </div>
        {isGenerating && (
          <div className="mt-2 flex items-center gap-2 text-xs text-[#8B7355]">
            <Loader2 className="w-3 h-3 animate-spin" />
            {chatAgentName}正在思考...
          </div>
        )}
      </div>
    </div>
  );
}
