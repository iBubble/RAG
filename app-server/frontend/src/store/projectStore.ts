import { create } from 'zustand';
import { persist, createJSONStorage } from 'zustand/middleware';
import { get as idbGet, set as idbSet, del as idbDel } from 'idb-keyval';

const idbStorage = {
  hasLoaded: {} as Record<string, boolean>,
  getItem: async (name: string): Promise<string | null> => {
    const val = await idbGet(name);
    idbStorage.hasLoaded[name] = true;
    return val || null;
  },
  setItem: async (name: string, value: string): Promise<void> => {
    if (idbStorage.hasLoaded[name]) {
      await idbSet(name, value);
    }
  },
  removeItem: async (name: string): Promise<void> => {
    await idbDel(name);
  },
};

export interface Message {
  id: string;
  role: 'user' | 'agent';
  content: string;
  isStreaming?: boolean;
  sources?: string[];
  stats?: {
    time: number;
    tokens: number;
    speed: number;
  };
  timestamp?: number;
}

export interface ChatStreamingState {
  isGenerating: boolean;
  projectId: string | null;
  streamingContent: string;
  streamingSources: string[];
  abortController: AbortController | null;
}

export interface SavedResult {
  id: string;
  content: string;
  timestamp: number;
  tokens: number;
  title?: string;
  sections?: DocSection[];    // WHY: 大纲结构随文档持久化，用于还原编辑状态
  isAutoSave?: boolean;       // WHY: 区分自动保存与手动保存
}

export interface DocSection {
  id: string;
  title: string;
  level: number;
  content: string;
  sources?: string[];
}

// WHY: 范文段落保留完整正文用于风格模仿（双路 Prompt Track B）
export interface ExemplarSection {
  title: string;
  level: number;
  content: string;
}

export interface PreviewFile {
  id: string;
  filename: string;
  path: string;
  size: number;
  source_type?: string;  // WHY: web/text 来源走专用预览路径而非文件系统
  source_url?: string;
}

interface ProjectState {
  checkedFileIds: string[];
  checkedRefIds: string[];
  templateTitle: string;
  templateSections: DocSection[];
  toggleFileCheck: (fileId: string) => void;
  setCheckedFiles: (fileIds: string[]) => void;
  clearCheckedFiles: () => void;
  setCheckedRefIds: (ids: string[]) => void;
  toggleRefCheck: (fileId: string) => void;
  setTemplateData: (title: string, sections: DocSection[]) => void;
  setTemplateTitle: (title: string) => void;
  updateSectionContent: (id: string, content: string) => void;
  updateSectionSources: (id: string, sources: string[]) => void;
  addTemplateSection: (index: number, title: string, level: number) => void;
  removeTemplateSection: (id: string) => void;
  updateTemplateSectionLevel: (id: string, delta: number) => void;
  reorderTemplateSections: (startIndex: number, endIndex: number) => void;
  // WHY: 范文状态（exemplar）独立于模板骨架（template），两者共存
  originalTemplateName: string;
  exemplarTitle: string;
  exemplarSections: ExemplarSection[];
  setExemplarData: (title: string, sections: ExemplarSection[]) => void;
  clearExemplar: () => void;
  agentMessagesByProject: Record<string, Message[]>;
  setProjectMessages: (projectId: string, updater: Message[] | ((prev: Message[]) => Message[])) => void;
  savedChatSnippets: SavedResult[];
  addChatSnippet: (result: SavedResult) => void;
  removeChatSnippet: (id: string) => void;
  savedDocuments: SavedResult[];
  addSavedDocument: (result: SavedResult) => void;
  removeSavedDocument: (id: string) => void;
  selectedModel: string;
  setSelectedModel: (modelName: string) => void;
  isUploadModalOpen: boolean;
  setUploadModalOpen: (open: boolean) => void;
  activePreviewFile: PreviewFile | null;
  setActivePreviewFile: (file: PreviewFile | null) => void;
  activeTab: string;
  setActiveTab: (tab: string) => void;
  currentDocId: string | null;
  setCurrentDocId: (id: string | null) => void;
  refreshCounter: number;
  triggerRefresh: () => void;
  chatStreamingState: ChatStreamingState;
  sendAgentMessage: (
    projectId: string,
    input: string,
    chatMode: string,
    getAuthHeaders: () => Record<string, string>,
    checkedFileIds: string[],
    selectedModel: string
  ) => Promise<void>;
  stopAgentMessage: () => void;
  publicSettings: Record<string, any> | null;
  fetchPublicSettings: () => Promise<void>;
}

// WHY: 使用 Zustand 进行轻量级跨组件通信，
//      让左侧树的勾选状态（checkedFileIds）可以直接贯通映射到中间的智能体请求上下文中。
export const useProjectStore = create<ProjectState>()(
  persist(
    (set, get) => ({
  checkedFileIds: [],
  checkedRefIds: [],
  templateTitle: '未命名实施方案',
  templateSections: [],
  originalTemplateName: '',
  toggleFileCheck: (fileId) =>
    set((state) => ({
      checkedFileIds: state.checkedFileIds.includes(fileId)
        ? state.checkedFileIds.filter((id) => id !== fileId)
        : [...state.checkedFileIds, fileId],
    })),
  setCheckedFiles: (fileIds) => set({ checkedFileIds: fileIds }),
  clearCheckedFiles: () => set({ checkedFileIds: [] }),
  setCheckedRefIds: (ids) => set({ checkedRefIds: ids }),
  toggleRefCheck: (fileId) =>
    set((state) => ({
      checkedRefIds: state.checkedRefIds.includes(fileId)
        ? state.checkedRefIds.filter((id) => id !== fileId)
        : [...state.checkedRefIds, fileId],
    })),
  setTemplateData: (title, sections) => set((state) => ({
    templateTitle: title,
    templateSections: sections,
    // WHY: 首次设置模板时记录原始名称，后续编辑标题不会影响模板名
    originalTemplateName: state.originalTemplateName || title,
  })),
  setTemplateTitle: (title) => set({ templateTitle: title }),
  updateSectionContent: (id, content) => set((state) => ({
    templateSections: state.templateSections.map(s => s.id === id ? { ...s, content } : s)
  })),
  updateSectionSources: (id, sources) => set((state) => ({
    templateSections: state.templateSections.map(s => s.id === id ? { ...s, sources } : s)
  })),
  addTemplateSection: (index, title, level) => set((state) => {
    const newSection: DocSection = {
      id: Date.now().toString(),
      title,
      level,
      content: ''
    };
    const newSections = [...state.templateSections];
    newSections.splice(index, 0, newSection);
    return { templateSections: newSections };
  }),
  removeTemplateSection: (id) => set((state) => ({
    templateSections: state.templateSections.filter(s => s.id !== id)
  })),
  updateTemplateSectionLevel: (id, delta) => set((state) => ({
    templateSections: state.templateSections.map(s => {
      if (s.id === id) {
        const newLevel = Math.max(1, Math.min(6, s.level + delta)); // Limit 1~6
        return { ...s, level: newLevel };
      }
      return s;
    })
  })),
  reorderTemplateSections: (startIndex, endIndex) => set((state) => {
    const result = Array.from(state.templateSections);
    const [removed] = result.splice(startIndex, 1);
    result.splice(endIndex, 0, removed);
    return { templateSections: result };
  }),
  // WHY: 范文状态独立管理，不影响模板骨架
  exemplarTitle: '',
  exemplarSections: [],
  setExemplarData: (title, sections) => set({ exemplarTitle: title, exemplarSections: sections }),
  clearExemplar: () => set({ exemplarTitle: '', exemplarSections: [] }),
  agentMessagesByProject: {},
  // WHY: 每项目聊天记录限制最多 100 条，防止长期使用后 IndexedDB 膨胀触发 OOM。
  //      超过 100 条时丢弃最早的消息。
  setProjectMessages: (projectId, updater) => set((state) => {
    const prevMsg = state.agentMessagesByProject[projectId] || [{ id: '1', role: 'agent', content: '您好！我是力诺通用知识库问答助手，由本地模型驱动。请问有什么可以帮您？' }];
    const nextMsg = typeof updater === 'function' ? updater(prevMsg) : updater;
    const _MAX_MESSAGES = 100;
    const trimmed = nextMsg.length > _MAX_MESSAGES ? nextMsg.slice(-_MAX_MESSAGES) : nextMsg;
    return {
      agentMessagesByProject: {
        ...state.agentMessagesByProject,
        [projectId]: trimmed
      }
    };
  }),
  savedChatSnippets: [],
  addChatSnippet: (result) => {
    set((state) => {
      const exist = state.savedChatSnippets.some((s: SavedResult) => s.content === result.content);
      if (exist) return state;
      return {
        savedChatSnippets: [result, ...state.savedChatSnippets]
      };
    });
  },
  removeChatSnippet: (id) => {
    set((state) => ({
      savedChatSnippets: state.savedChatSnippets.filter(r => r.id !== id)
    }));
  },
  savedDocuments: [],
  // WHY: 保留最多 5 个文档快照，防止无限累积导致 IndexedDB / 内存膨胀。
  //      后端 /api/projects/{pid}/documents 已持久化完整文档，前端仅保留最近几条用于 UI 展示。
  addSavedDocument: (result) => set((state) => ({
    savedDocuments: [result, ...state.savedDocuments].slice(0, 5)
  })),
  removeSavedDocument: (id) => set((state) => ({
    savedDocuments: state.savedDocuments.filter(r => r.id !== id)
  })),
  selectedModel: 'qwen3.6:35b-q4',
  setSelectedModel: (model) => set({ selectedModel: model }),
  isUploadModalOpen: false,
  setUploadModalOpen: (open) => set({ isUploadModalOpen: open }),
  activePreviewFile: null,
  setActivePreviewFile: (file) => set({ activePreviewFile: file }),
  activeTab: '智能助手',
  setActiveTab: (tab) => set({ activeTab: tab }),
  currentDocId: null,
  setCurrentDocId: (id) => set({ currentDocId: id }),
  refreshCounter: 0,
  publicSettings: null,
  fetchPublicSettings: async () => {
    const API_BASE = import.meta.env.VITE_API_BASE || '';
    try {
      const res = await fetch(`${API_BASE}/api/admin/settings/public`);
      if (res.ok) {
        const data = await res.json();
        set({ publicSettings: data });
      }
    } catch (err) {
      console.error('[projectStore] 获取公共系统设置失败:', err);
    }
  },
  triggerRefresh: () => set((state) => ({ refreshCounter: state.refreshCounter + 1 })),
  chatStreamingState: {
    isGenerating: false,
    projectId: null,
    streamingContent: '',
    streamingSources: [],
    abortController: null,
  },
  sendAgentMessage: async (projectId, input, chatMode, getAuthHeaders, checkedFileIds, selectedModel) => {
    const currentStreaming = useProjectStore.getState().chatStreamingState;
    if (currentStreaming.isGenerating) return;

    const API_BASE = import.meta.env.VITE_API_BASE || '';
    const userMsg: Message = { id: Date.now().toString(), role: 'user', content: input, timestamp: Date.now() };
    const agentMsgId = (Date.now() + 1).toString();

    useProjectStore.getState().setProjectMessages(projectId, (prev) => [
      ...prev,
      userMsg,
      { id: agentMsgId, role: 'agent', content: '', isStreaming: true }
    ]);

    const currentMsgs = useProjectStore.getState().agentMessagesByProject[projectId] || [];
    const updatedMessages = [
      ...currentMsgs.filter(m => m.id !== agentMsgId),
      { id: agentMsgId, role: 'agent', content: '', isStreaming: true }
    ];
    fetch(`${API_BASE}/api/chat/history`, {
      method: 'POST',
      headers: { ...getAuthHeaders(), 'Content-Type': 'application/json' },
      body: JSON.stringify({ project_id: projectId, messages: updatedMessages })
    }).catch(err => console.error('[projectStore] 发送消息时暂存历史失败:', err));

    const controller = new AbortController();
    set({
      chatStreamingState: {
        isGenerating: true,
        projectId,
        streamingContent: '',
        streamingSources: [],
        abortController: controller,
      }
    });

    let localBufferContent = '';
    let localBufferSources: string[] = [];
    const startTime = Date.now();

    try {
      const isStateless = chatMode === 'stateless';
      const history = isStateless
        ? []
        : currentMsgs
            .filter(m => m.id !== '1')
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
          collab_supervisor_name: get().publicSettings?.collab_supervisor_name,
          collab_legal_name: get().publicSettings?.collab_legal_name,
          collab_contrarian_name: get().publicSettings?.collab_contrarian_name,
          collab_arbiter_name: get().publicSettings?.collab_arbiter_name,
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
            }
            if (data.status) {
              const statusTranslations: Record<string, string> = {
                routing: '任务路由中',
                executing: '任务执行中',
                thinking: '深度推演中',
                critiquing: '结果审查中',
                deciding: '最终决策中',
                done: '执行完成'
              };
              const zhStatus = statusTranslations[data.status] || data.status;
              localBufferContent += `\n\n⏳ ${zhStatus}\n\n`;
            }
            if (data.data_analysis) {
              localBufferContent = localBufferContent.replace(/\n\n⏳ .*?\n\n/g, '');
              const daTag = `<!--DA_META:${JSON.stringify(data.data_analysis)}:DA_META-->\n`;
              localBufferContent = daTag + localBufferContent;
            }
            // WHY: 多 Agent 协同模式（smart）的协作事件推送。
            //      agent_event 携带 Agent 名称和状态，渲染为可视化状态指示器。
            if (data.type === 'agent_event') {
              const agentEmojis: Record<string, string> = {
                supervisor: '🧠', rag: '📚', rag_agent: '📚',
                legal: '⚖️', legal_agent: '⚖️',
                service: '📝', service_agent: '📝',
                data: '📊', data_agent: '📊',
                contrarian: '🤨', arbiter: '👑',
              };
              const emoji = agentEmojis[data.agent] || '🤖';
              localBufferContent += `\n\n${emoji} *${data.message}*\n\n`;
            }
            if (data.type === 'token' && data.content) {
              // 多 Agent 模式的 token 推送（清除之前的状态行）
              localBufferContent = localBufferContent.replace(/\n\n[🧠📚⚖️📝📊🤨👑🤖] \*.*?\*\n\n/g, '');
              localBufferContent += data.content;
            }
            if (data.token) {
              localBufferContent += data.token;
            }
            set((state) => ({
              chatStreamingState: {
                ...state.chatStreamingState,
                streamingContent: localBufferContent,
                streamingSources: localBufferSources,
              }
            }));
          } catch {
            // ignore
          }
        }
      }
    } catch (err: unknown) {
      if (err instanceof DOMException && err.name === 'AbortError') {
        localBufferContent += '\n\n⏹️ _生成已被用户中断_';
      } else {
        const msg = err instanceof Error ? err.message : '未知错误';
        localBufferContent += `\n❌ 生成失败: ${msg}`;
      }
      set((state) => ({
        chatStreamingState: {
          ...state.chatStreamingState,
          streamingContent: localBufferContent,
        }
      }));
    } finally {
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
        },
        timestamp: Date.now()
      };

      useProjectStore.getState().setProjectMessages(projectId, (prev) =>
        prev.map(m => m.id === agentMsgId ? finalAgentMsg : m)
      );

      const currentMsgsAfter = useProjectStore.getState().agentMessagesByProject[projectId] || [];
      const updatedMessagesAfter = currentMsgsAfter.map(m => m.id === agentMsgId ? finalAgentMsg : m);

      if (projectId && updatedMessagesAfter.length > 0) {
        fetch(`${API_BASE}/api/chat/history`, {
          method: 'POST',
          headers: { ...getAuthHeaders(), 'Content-Type': 'application/json' },
          body: JSON.stringify({ project_id: projectId, messages: updatedMessagesAfter })
        }).catch(err => console.error('[projectStore] 保存聊天历史失败:', err));
      }

      set({
        chatStreamingState: {
          isGenerating: false,
          projectId: null,
          streamingContent: '',
          streamingSources: [],
          abortController: null,
        }
      });
    }
  },
  stopAgentMessage: () => {
    const streamState = useProjectStore.getState().chatStreamingState;
    streamState.abortController?.abort();
    set({
      chatStreamingState: {
        isGenerating: false,
        projectId: null,
        streamingContent: streamState.streamingContent + '\n\n⏹️ _生成已被用户中断_',
        streamingSources: streamState.streamingSources,
        abortController: null,
      }
    });
  },
    }),
    {
      name: 'shengyao-rag-storage',
      storage: createJSONStorage(() => idbStorage),
      // WHY: 持久化范围极简化——savedDocuments 已移除（后端有持久化，前端冗余副本是 OOM 根因）。
      //      agentMessagesByProject 通过 setProjectMessages 已有 100 条上限。
      //      savedChatSnippets 体积小（纯文本片段），保留。
      partialize: (state) => ({
        savedChatSnippets: state.savedChatSnippets,
        // WHY: 持久化聊天记录时，截断每个项目到最近 50 条，
        //      避免 JSON 序列化时体积过大。
        agentMessagesByProject: Object.fromEntries(
          Object.entries(state.agentMessagesByProject).map(
            ([pid, msgs]) => [pid, (msgs as Message[]).slice(-50)]
          )
        ),
      })
    }
  )
);
