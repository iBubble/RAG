import { useState, useEffect, useRef } from 'react';
import { Send, Bot, User, Loader2, Power, Save, Trash2, Settings as SettingsIcon, X } from 'lucide-react';
import { useProjectStore } from '../../store/projectStore';
import { useAuthStore } from '../../store/authStore';
import type { Message } from '../../store/projectStore';
import DataTable from './DataTable';
import MarkdownBlock from './MarkdownBlock';

const API_BASE = import.meta.env.VITE_API_BASE || '';



type OllamaStatus = 'checking' | 'online' | 'offline';

export default function AgentChat({ projectId }: { projectId: string }) {
  const [input, setInput] = useState('');
  const [isGenerating, setIsGenerating] = useState(false);
  const checkedFileIds = useProjectStore(state => state.checkedFileIds);
  const agentMessagesByProject = useProjectStore(state => state.agentMessagesByProject);
  const setProjectMessages = useProjectStore(state => state.setProjectMessages);
  
  const messages = agentMessagesByProject[projectId] || [{ id: '1', role: 'agent', content: '您好！我是案件法律文档问答助手，由本地模型驱动。请问有什么可以帮您？' }];
  const setMessages = (updater: Message[] | ((prev: Message[]) => Message[])) => setProjectMessages(projectId, updater);

  const addChatSnippet = useProjectStore(state => state.addChatSnippet);
  const selectedModel = useProjectStore(state => state.selectedModel);
  const templateSections = useProjectStore(state => state.templateSections);
  const { getAuthHeaders } = useAuthStore();
  
  const [ollamaStatus, setOllamaStatus] = useState<OllamaStatus>('checking');
  const [isSettingsOpen, setIsSettingsOpen] = useState(false);
  const [localPersona, setLocalPersona] = useState('');
  const [isSavingSettings, setIsSavingSettings] = useState(false);
  const [isRecommending, setIsRecommending] = useState(false);

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

  const [chatMode, setChatMode] = useState<string>('stateless');
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const abortControllerRef = useRef<AbortController | null>(null);

  // 引入专门应对长推流引发全局 React Store OOM 的高频保护插槽
  const [streamingContent, setStreamingContent] = useState('');
  const [streamingSources, setStreamingSources] = useState<string[]>([]);

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
        { id: '1', role: 'agent', content: '您好！我是案件法律文档问答助手，由本地模型驱动。请问有什么可以帮您？' }
      ]);
    };

    syncChatHistory();
  }, [projectId]);

  const handleSend = async () => {
    if (!input.trim() || isGenerating) return;

    const userMsg: Message = { id: Date.now().toString(), role: 'user', content: input };
    const agentMsgId = (Date.now() + 1).toString();

    setMessages(prev => [...prev, userMsg, {
      id: agentMsgId,
      role: 'agent',
      content: '',
      isStreaming: true,
    }]);
    setInput('');
    setIsGenerating(true);

    // 立即从 Zustand Store 同步获取合并了用户问题的最新消息列表，并上传后端提供容灾
    const currentMsgs = useProjectStore.getState().agentMessagesByProject[projectId] || [];
    const updatedMessages = [
      ...currentMsgs.filter(m => m.id !== agentMsgId),
      { id: agentMsgId, role: 'agent', content: '', isStreaming: true }
    ];
    if (projectId) {
      fetch(`${API_BASE}/api/chat/history`, {
        method: 'POST',
        headers: {
          ...getAuthHeaders(),
          'Content-Type': 'application/json'
        },
        body: JSON.stringify({
          project_id: projectId,
          messages: updatedMessages
        })
      }).catch(err => console.error('[AgentChat] 发送消息时暂存历史失败:', err));
    }

    // 重置并剥离流缓存，严禁边跑边动底层大库
    setStreamingContent('');
    setStreamingSources([]);
    let localBufferContent = '';
    let localBufferSources: string[] = [];

    // 创建 AbortController 以支持停止生成
    const controller = new AbortController();
    abortControllerRef.current = controller;
    const startTime = Date.now();

    try {
      // WHY: 发送历史消息让大模型保持对话上下文，但后端会做滑窗截断控制总量
      // WHY: stateless 模式下不发送任何历史，每次对话完全独立
      const isStateless = chatMode === 'stateless';
      const history = isStateless
        ? []
        : messages
            .filter(m => m.id !== '1') // 排除系统欢迎消息
            .map(m => ({ role: m.role, content: m.content }));

      const res = await fetch(`${API_BASE}/api/chat`, {
        method: 'POST',
        headers: { ...getAuthHeaders(), 'Content-Type': 'application/json' },
        body: JSON.stringify({
          message: userMsg.content,
          file_ids: checkedFileIds,
          project_id: projectId,
          history,
          model: selectedModel,
          chat_mode: chatMode,
          stateless: isStateless,

        }),
        signal: controller.signal,
      });

      if (!res.ok) throw new Error(`HTTP ${res.status}`);

      const reader = res.body?.getReader();
      const decoder = new TextDecoder();

      if (!reader) throw new Error('No response body');

      let buffer = '';
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';

        for (const line of lines) {
          if (!line.startsWith('data: ')) continue;
          try {
            const data = JSON.parse(line.slice(6));
            if (data.done) break;
            if (data.sources) {
              localBufferSources = data.sources;
              // 喂给表面视图层局部变量
              setStreamingSources(localBufferSources);
            }
            // WHY: status 事件用于在 DuckDB 分析等慢操作期间
            //      给用户展示进度提示，消除"卡死"感知。
            if (data.status) {
              localBufferContent += `\n\n⏳ ${data.status}\n\n`;
              setStreamingContent(localBufferContent);
            }
            // WHY: DuckDB 分析结果通过独立 SSE 事件推送，
            //      用特殊标记包裹注入消息前缀，前端渲染时解析。
            if (data.data_analysis) {
              // WHY: 收到精确分析结果后，清除之前的 status 临时提示
              localBufferContent = localBufferContent.replace(/\n\n⏳ .*?\n\n/g, '');
              const daTag = `<!--DA_META:${JSON.stringify(data.data_analysis)}:DA_META-->\n`;
              localBufferContent = daTag + localBufferContent;
              setStreamingContent(localBufferContent);
            }
            if (data.token) {
              localBufferContent += data.token;
              // 仅引发局部 DOM 更新水波纹，不深层复制全局巨型对象
              setStreamingContent(localBufferContent);
            }
          } catch {
            // 忽略解析错误
          }
        }
      }
    } catch (err: unknown) {
      if (err instanceof DOMException && err.name === 'AbortError') {
        // 用户手动停止
        localBufferContent += '\n\n⏹️ _生成已被用户中断_';
        setStreamingContent(localBufferContent);
      } else {
        const msg = err instanceof Error ? err.message : '未知错误';
        localBufferContent += `\n❌ 生成失败: ${msg}`;
        setStreamingContent(localBufferContent);
      }
    } finally {
      setIsGenerating(false);
      abortControllerRef.current = null;

      // 1. 计算 agent 消息完全生成后的最终对象
      const finalAgentMsg: Message = {
        id: agentMsgId,
        role: 'agent',
        content: localBufferContent,
        sources: localBufferSources,
        isStreaming: false,
        stats: {
          time: Number(((Date.now() - startTime) / 1000).toFixed(1)),
          tokens: localBufferContent.length,
          speed: Number((localBufferContent.length / ((Date.now() - startTime) / 1000 || 1)).toFixed(1))
        }
      };

      // 2. 将最终对象同步归档至前端 store
      setMessages(prev =>
        prev.map(m => m.id === agentMsgId ? finalAgentMsg : m)
      );

      // 3. 避开异步更新延迟，直接从 store 获取最新的全部消息记录，并同步保存到后端
      const currentMsgs = useProjectStore.getState().agentMessagesByProject[projectId] || [];
      const updatedMessages = currentMsgs.map(m => m.id === agentMsgId ? finalAgentMsg : m);

      if (projectId && updatedMessages.length > 0) {
        fetch(`${API_BASE}/api/chat/history`, {
          method: 'POST',
          headers: {
            ...getAuthHeaders(),
            'Content-Type': 'application/json'
          },
          body: JSON.stringify({
            project_id: projectId,
            messages: updatedMessages
          })
        }).catch(err => console.error('[AgentChat] 保存聊天历史失败:', err));
      }
    }
  };

  const handleStop = () => {
    abortControllerRef.current?.abort();
  };

  const handleClear = async () => {
    setMessages([{ id: '1', role: 'agent', content: '您好！我是案件法律文档问答助手，由本地模型驱动。请问有什么可以帮您？' }]);
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
      const renderEnhancedContent = (text: string) => {
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
                <MarkdownBlock key={idx} content={block.content} />
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
              ? renderEnhancedContent(textContent)
              : <MarkdownBlock content={textContent} />
            }
            {isStreaming && (
              <span className="inline-block w-1.5 h-4 bg-indigo-500 ml-0.5 animate-pulse rounded-sm mt-1 align-middle" />
            )}
          </>
        );
      }

    const parts = content.split('<think>');
    const firstPart = parts.shift() || '';

    return (
      <div className="space-y-3">
        {firstPart && <MarkdownBlock content={firstPart} />}
        {parts.map((p, idx) => {
          const isLast = idx === parts.length - 1;
          const endIdx = p.indexOf('</think>');
          
          if (endIdx !== -1) {
            const thinkStr = p.substring(0, endIdx).trim();
            const normalStr = p.substring(endIdx + 8);
            return (
              <div key={idx}>
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
                {normalStr && <MarkdownBlock content={normalStr} />}
                {isLast && isStreaming && <span className="inline-block w-1.5 h-4 bg-indigo-500 ml-0.5 animate-pulse rounded-sm mt-1 align-middle" />}
              </div>
            );
          } else {
            // Unclosed think tag: still streaming OR truncated
            const thinkStr = p.trim();
            const isTruncated = !isStreaming; // 流结束但标签未闭合 = 被截断
            return (
              <div key={idx}>
                <details className="mb-3" open={!isTruncated}>
                  <summary className={`text-xs font-medium cursor-pointer select-none border-b pb-1.5 flex items-center gap-1.5 w-max ${isTruncated ? 'text-amber-500 border-amber-200' : 'text-indigo-400 border-indigo-100'}`}>
                    {isTruncated ? (
                      <><span className="opacity-80">⚠️</span> 推理过程被截断（输出已达上限）</>
                    ) : (
                      <><Loader2 className="w-3.5 h-3.5 animate-spin" /> AI 正在推理思考中...</>
                    )}
                  </summary>
                  <div className={`mt-2 p-3 rounded-lg text-[13px] whitespace-pre-wrap leading-relaxed border overflow-hidden relative flex flex-col justify-end max-h-[4.5rem] ${isTruncated ? 'bg-amber-50/40 text-amber-600/80 border-amber-100' : 'bg-indigo-50/40 text-indigo-500/80 border-indigo-50'}`}>
                    <div className="opacity-80">
                      {thinkStr.length > 150 ? '...' + thinkStr.slice(-150) : thinkStr}
                      {isStreaming && !isTruncated && <span className="inline-block w-1.5 h-3.5 bg-indigo-400 ml-1 animate-pulse align-middle" />}
                    </div>
                  </div>
                </details>
              </div>
            );
          }
        })}
      </div>
    );
  };



  return (
    <div className="flex flex-col h-full bg-white text-gray-800">
      {/* Header with LLM Status Indicator */}
      {/* Header */}
      <div className="border-b border-gray-100 p-3 shrink-0 flex items-center justify-between bg-white shadow-sm relative">
        <h2 className="font-semibold text-gray-800 flex items-center gap-2 text-sm z-10">
          <Bot className="w-4 h-4 text-indigo-500" />
          智能法律助手
        </h2>
        <div className="flex items-center gap-1 z-10">
          <button
            onClick={() => setIsSettingsOpen(true)}
            className="p-1.5 text-gray-400 hover:text-indigo-600 hover:bg-indigo-50 rounded transition-colors flex items-center gap-1 text-xs"
            title="助手与算力设定"
          >
            <SettingsIcon className="w-3.5 h-3.5" />
            配置
          </button>
          <button
            onClick={handleClear}
            className="p-1.5 text-gray-400 hover:text-red-500 hover:bg-red-50 rounded transition-colors flex items-center gap-1 text-xs"
            title="清空对话历史"
          >
            <Trash2 className="w-3.5 h-3.5" />
            清空
          </button>
        </div>

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
                <label className="text-xs font-semibold text-gray-600">案件专属系统角色词 (Prompt Persona)</label>
                <textarea 
                  value={localPersona}
                  onChange={(e) => setLocalPersona(e.target.value)}
                  placeholder="【Qwen 模型最佳示范 - 您可直接照抄修改】&#10;1. 身份定位：你是一个极其专业且严谨的民商事诉讼律师与法律文书编写机器，没有任何情感色彩。&#10;2. 核心任务：根据上传资料，输出干练的起诉状、代理词、证据清单或结论，绝不捏造任何未提供的数据。&#10;3. 风格红线约束：&#10;   - 【极度禁止】输出任何客服废话（如：好的、首先、希望对您有帮助）。&#10;   - 直接抛出第一句正文干货，必须使用无主语句式，客观冰冷。&#10;   - 专业表述严格遵循诉讼法及相关司法解释（如引用具体条文、判例规则）。"
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
          <div key={msg.id} className={`flex gap-3 ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
            {msg.role === 'agent' && (
              <div className="w-8 h-8 rounded-full bg-indigo-50 flex items-center justify-center shrink-0 border border-indigo-100">
                <Bot className="w-4 h-4 text-indigo-600" />
              </div>
            )}

            <div className={`max-w-[75%] px-4 py-2.5 rounded-2xl text-sm leading-relaxed ${
              msg.role === 'user'
                ? 'bg-blue-600 text-white rounded-tr-sm'
                : 'bg-gray-50 text-gray-800 border border-gray-100 rounded-tl-sm'
            }`}>
              {/* WHY: 用户消息不需要 Markdown 解析，直接纯文本渲染保持白色字体；
                       Agent 消息使用 MarkdownBlock 渲染结构化内容 */}
              {msg.role === 'user'
                ? <div className="whitespace-pre-wrap">{msg.content}</div>
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
                      btn.innerHTML = '<span class="text-indigo-600 font-medium">已保存至剪贴板 ✓</span>';
                      setTimeout(() => { btn.innerHTML = originalHtml; }, 2000);
                    }}
                    className="flex items-center gap-1 hover:text-indigo-600 transition-colors cursor-pointer text-gray-500 hover:bg-gray-100 px-2 py-0.5 rounded shadow-sm border border-transparent hover:border-gray-200"
                    title="复制到剪贴板并存入已存结果"
                  >
                    <Save className="w-3 h-3" />
                    保存
                  </button>
                </div>
              )}
            </div>

            {msg.role === 'user' && (
              <div className="w-8 h-8 rounded-full bg-blue-100 flex items-center justify-center shrink-0">
                <User className="w-4 h-4 text-blue-600" />
              </div>
            )}
          </div>
        ))}
        <div ref={messagesEndRef} />
      </div>

      <div className="p-4 border-t border-gray-100 bg-gray-50/50 shrink-0">
        {/* 对话框前方的模式切换 */}
        <div className="flex items-center gap-2 mb-3">
          <div className="flex items-center bg-white border border-gray-200 rounded-lg p-1 shadow-sm">
            <button
              onClick={() => setChatMode('stateless')}
              className={`text-xs px-3 py-1.5 rounded-md transition-all ${chatMode === 'stateless' ? 'bg-gray-100 text-gray-800 font-semibold shadow-sm border border-gray-300' : 'text-gray-500 hover:bg-gray-50 hover:text-gray-700 border border-transparent'}`}
              title="每次提问完全独立，不读取对话历史，仅根据当前问题和项目资料回答"
            >
              🔒 独立对话
            </button>
            <button
              onClick={() => setChatMode('fast')}
              className={`text-xs px-3 py-1.5 rounded-md transition-all ${chatMode === 'fast' ? 'bg-emerald-50 text-emerald-700 font-semibold shadow-sm border border-emerald-200/60' : 'text-gray-500 hover:bg-gray-50 hover:text-gray-700 border border-transparent'}`}
              title="隐藏思考过程，结合项目资料直接输出专属答案"
            >
              ⚡ 快速
            </button>
            <button
              onClick={() => setChatMode('deep')}
              className={`text-xs px-3 py-1.5 rounded-md transition-all ${chatMode === 'deep' ? 'bg-indigo-50 text-indigo-700 font-semibold shadow-sm border border-indigo-200/60' : 'text-gray-500 hover:bg-gray-50 hover:text-gray-700 border border-transparent'}`}
              title="允许大模型进行深度推导与自我反思"
            >
              🧠 深度思考
            </button>
            <button
              onClick={() => setChatMode('expert')}
              className={`text-xs px-3 py-1.5 rounded-md transition-all ${chatMode === 'expert' ? 'bg-amber-50 text-amber-700 font-semibold shadow-sm border border-amber-200/60' : 'text-gray-500 hover:bg-gray-50 hover:text-gray-700 border border-transparent'}`}
              title="以资深法律专家口吻严谨解析复杂法律问题"
            >
              ⚖️ 法律专家
            </button>
            <button
              onClick={() => setChatMode('general')}
              className={`text-xs px-3 py-1.5 rounded-md transition-all ${chatMode === 'general' ? 'bg-blue-50 text-blue-700 font-semibold shadow-sm border border-blue-200/60' : 'text-gray-500 hover:bg-gray-50 hover:text-gray-700 border border-transparent'}`}
              title="不绑定任何专门案件，作为全能助手回答通用问题"
            >
              🤖 通用AI
            </button>

          </div>

        </div>

        <div className="relative">
          <textarea
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={e => {
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                handleSend();
              }
            }}
            placeholder={ollamaStatus === 'online' ? '输入您关于案件资料的疑问...' : 'Ollama 服务离线，请先启动...'}
            disabled={ollamaStatus === 'offline'}
            className="w-full resize-none bg-white border border-gray-200 rounded-xl pr-24 pl-4 py-3 text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent shadow-sm disabled:bg-gray-100 disabled:text-gray-400"
            rows={1}
            style={{ minHeight: '44px' }}
          />
          <div className="absolute right-2 bottom-1.5 flex items-center gap-1">
            {isGenerating ? (
              <button
                onClick={handleStop}
                className="p-2 bg-red-500 text-white rounded-lg hover:bg-red-600 transition-colors"
                title="停止生成"
              >
                <Power className="w-4 h-4" />
              </button>
            ) : (
              <button
                onClick={handleSend}
                disabled={!input.trim() || ollamaStatus === 'offline'}
                className="p-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:bg-gray-200 disabled:text-gray-400 disabled:cursor-not-allowed transition-colors"
              >
                <Send className="w-4 h-4" />
              </button>
            )}
          </div>
        </div>
        {isGenerating && (
          <div className="mt-2 flex items-center gap-2 text-xs text-indigo-600">
            <Loader2 className="w-3 h-3 animate-spin" />
            AI助手正在思考...
          </div>
        )}
      </div>
    </div>
  );
}
