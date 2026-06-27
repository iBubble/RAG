import React, { useState, useEffect, useRef } from 'react';
import { createPortal } from 'react-dom';
import { FileText, CheckCircle2, Wand2, List, Save, Plus, Trash2, ChevronRight, ChevronLeft, X, Square, Loader2, UploadCloud, AlertTriangle } from 'lucide-react';
import { useParams } from 'react-router-dom';
import { useProjectStore } from '../../store/projectStore';
import { useAuthStore } from '../../store/authStore';
import SectionBlock from './SectionBlock';
import ExportModals from './ExportModals';
import useGenerationQueue from './useGenerationQueue';
import { convertMarkdownTables, sanitizeTableMarkdown, removeHrFromHtml } from './markdownUtils';
import { renderLatexInHtml } from './KatexExtension';
import type { DocSection, SectionBlockHandle } from './types';

const API_BASE = import.meta.env.VITE_API_BASE || '';

// WHY: convertMarkdownTables, DocSection, SectionBlock 已抽离至独立模块

export default function DocumentStudio({ canWrite = true, projectName = '' }: { canWrite?: boolean; projectName?: string }) {
  const { id: projectId } = useParams<{ id: string }>();
  const [collaborative, setCollaborative] = useState(false);
  const publicSettings = useProjectStore((state: any) => state.publicSettings);
  const fetchPublicSettings = useProjectStore((state: any) => state.fetchPublicSettings);

  useEffect(() => {
    if (!publicSettings) {
      fetchPublicSettings();
    }
  }, [publicSettings, fetchPublicSettings]);

  useEffect(() => {
    if (publicSettings) {
      setCollaborative(publicSettings.collab_document_enabled === 'true');
    }
  }, [publicSettings]);
  const [activeHeadingId, setActiveHeadingId] = useState<string>('');
  const [autoSaveEnabled, setAutoSaveEnabled] = useState(false);
  const [customInstruction, setCustomInstruction] = useState('');
  const [sectionToDelete, setSectionToDelete] = useState<any | null>(null);
  const [showClearContentConfirm, setShowClearContentConfirm] = useState(false);
  const [showAddChapterModal, setShowAddChapterModal] = useState(false);
  const [addChapterTitle, setAddChapterTitle] = useState('');
  const [subsectionToAdd, setSubsectionToAdd] = useState<{ index: number; level: number } | null>(null);
  const [newSubSectionTitle, setNewSubSectionTitle] = useState('');


  const handleClearAllContent = () => {
    setShowClearContentConfirm(false);
    const { setTemplateData } = useProjectStore.getState();
    const emptySections = sections.map((s: DocSection) => ({ ...s, content: '', sources: [] }));
    setTemplateData(templateTitle || projectName || '新报告', emptySections);
    fetch(`${API_BASE}/api/projects/${projectId || 'default'}/template`, {
      method: 'POST',
      headers: { ...getAuthHeaders(), 'Content-Type': 'application/json' },
      body: JSON.stringify({ title: templateTitle || projectName || '新报告', sections: emptySections })
    }).then(() => showToast('已清空并完成同步')).catch((err) => console.error('同步清空状态至数据库失败', err));
  };
  // WHY: toast 通知 — 轻量内联实现，不引入外部依赖
  const [toast, setToast] = useState<{ message: string; type: 'success' | 'warning' | 'error' } | null>(null);
  const toastTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const sectionRefs = React.useRef<Record<string, SectionBlockHandle>>({});
  // WHY: AbortController 用于中断正在进行的 SSE fetch 请求
  const abortControllerRef = useRef<AbortController | null>(null);

  const originalTemplateName = useProjectStore((state: any) => state.originalTemplateName);
  const [showTemplateModal, setShowTemplateModal] = useState(false);
  const [isUploadingTemplate, setIsUploadingTemplate] = useState(false);
  const templateFileInputRef = useRef<HTMLInputElement>(null);

  const handleTemplateUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    try {
      setIsUploadingTemplate(true);
      const formData = new FormData();
      formData.append('file', file);
      
      const res = await fetch(`${API_BASE}/api/template/parse`, {
        method: 'POST',
        headers: getAuthHeaders(),
        body: formData
      });
      if (!res.ok) throw new Error('上传解析失败');
      
      const data = await res.json();
      const { setTemplateData, setCurrentDocId } = useProjectStore.getState();
      setTemplateData(data.filename, data.sections);
      setCurrentDocId(null);

      try {
        await fetch(`${API_BASE}/api/projects/${projectId || 'default'}/template`, {
          method: 'POST',
          headers: { ...getAuthHeaders(), 'Content-Type': 'application/json' },
          body: JSON.stringify({ title: data.filename, sections: data.sections })
        });
      } catch (saveErr) {
        console.warn('大纲模板保存到后端失败', saveErr);
      }

      showToast('大纲模板上传并应用成功');
    } catch (err) {
      alert("解析失败，请检查是否是合法的 .docx 格式");
      console.error(err);
    } finally {
      setIsUploadingTemplate(false);
      if (templateFileInputRef.current) templateFileInputRef.current.value = '';
    }
  };

  const checkedFileIds = useProjectStore((state: any) => state.checkedFileIds);
  const templateTitle = useProjectStore((state: any) => state.templateTitle);
  const setTemplateTitle = useProjectStore((state: any) => state.setTemplateTitle);
  const sections = useProjectStore((state: any) => state.templateSections);
  const updateSectionContent = useProjectStore((state: any) => state.updateSectionContent);
  const addSavedDocument = useProjectStore((state: any) => state.addSavedDocument);
  const selectedModel = useProjectStore((state: any) => state.selectedModel);
  const addTemplateSection = useProjectStore((state: any) => state.addTemplateSection);
  const removeTemplateSection = useProjectStore((state: any) => state.removeTemplateSection);
  const updateTemplateSectionLevel = useProjectStore((state: any) => state.updateTemplateSectionLevel);
  const reorderTemplateSections = useProjectStore((state: any) => state.reorderTemplateSections);
  const currentDocId = useProjectStore((state: any) => state.currentDocId);

  // WHY: 范文状态用于双路 Prompt 引擎的 Track B
  const exemplarSections = useProjectStore((state: any) => state.exemplarSections);
  const hasExemplar = exemplarSections && exemplarSections.length > 0;
  const { getAuthHeaders } = useAuthStore();
  
  const [draggedIndex, setDraggedIndex] = useState<number | null>(null);
  const [dragOverIndex, setDragOverIndex] = useState<number | null>(null);
  // WHY: 缓存填充状态
  const [isFillingCache, setIsFillingCache] = useState(false);

  // Calculate Progress
  const completedCount = sections.filter((s: DocSection) => {
    // Remove empty html tags usually generated by tiptap
    const plain = s.content.replace(/<[^>]*>?/gm, '').trim();
    return plain.length > 5;
  }).length;
  const progressPercent = sections.length > 0 ? Math.round((completedCount / sections.length) * 100) : 0;

  // WHY: 封装保存逻辑为通用函数，供自动保存和手动保存复用
  const performSave = async (isAuto: boolean, isAutoSaveAction: boolean = false) => {
    // WHY: 必须实时从 store 读取最新 sections，而非使用 React 闭包中的 sections。
    //      闭包中的 sections 是上一次渲染时的快照，在批量生成期间已过期。
    //      之前用闭包快照保存，会导致刚生成的内容被空内容覆盖（"内容被吃了"的根因）。
    const liveSections = useProjectStore.getState().templateSections;
    let liveTitle = useProjectStore.getState().templateTitle;
    if (liveSections.length === 0) return;

    // 如果属于程序自动触发保存，但用户没有开启自动保存开关，则仅保存至 template 接口，不写 documents
    if (isAuto && !autoSaveEnabled) {
      if (!isAutoSaveAction) {
        await fetch(`${API_BASE}/api/projects/${projectId || 'default'}/template`, {
          method: 'POST',
          headers: { ...getAuthHeaders(), 'Content-Type': 'application/json' },
          body: JSON.stringify({ title: liveTitle, sections: liveSections })
        }).catch(() => {});
      }
      return;
    }

    // 如果当前没有文档 ID，则创建一个
    let docId = useProjectStore.getState().currentDocId;
    if (isAutoSaveAction) {
      docId = 'autosave';
      let baseTitle = liveTitle;
      if (baseTitle.endsWith('.docx')) {
        baseTitle = baseTitle.slice(0, -5);
      }
      baseTitle = baseTitle.replace(/（自动保存）$/, '').replace(/\(自动保存\)$/, '');
      liveTitle = baseTitle + '（自动保存）.docx';
    } else {
      if (!docId || docId === 'autosave') {
        docId = Date.now().toString();
        useProjectStore.getState().setCurrentDocId(docId);
      }
    }

    const fullText = `# ${liveTitle}\n\n` + liveSections.map((s: DocSection) => {
      let text = s.content.replace(/<(?:br|\/?(?:p|div|li|ul|ol|h[1-6]|table|tr))[^>]*>/gi, '\n');
      text = text.replace(/<[^>]+>/g, '');
      text = text.replace(/(\[可视化[：:].+?\])/g, '\n$1\n');
      text = text.replace(/\n{3,}/g, '\n\n');
      return `## ${s.title}\n${text.trim()}`;
    }).join('\n\n');

    const docData = {
      id: docId,
      title: liveTitle,
      content: fullText,
      timestamp: Date.now(),
      tokens: fullText.length,
      sections: liveSections,
      isAutoSave: isAuto || isAutoSaveAction
    };

    const res = await fetch(`${API_BASE}/api/projects/${projectId || 'default'}/documents`, {
      method: 'POST',
      headers: { ...getAuthHeaders(), 'Content-Type': 'application/json' },
      body: JSON.stringify(docData)
    });

    // WHY: 同步将文档最新状态存入 /template，确保其他设备登录时主界面加载到最新文本 (自动保存除外)
    if (!isAutoSaveAction) {
      await fetch(`${API_BASE}/api/projects/${projectId || 'default'}/template`, {
        method: 'POST',
        headers: { ...getAuthHeaders(), 'Content-Type': 'application/json' },
        body: JSON.stringify({ title: liveTitle, sections: liveSections })
      }).catch(() => {});
    }

    if (!res.ok) throw new Error('保存失败');

    addSavedDocument(docData);
    window.dispatchEvent(new CustomEvent('documentSaved'));
    return docData;
  };

  // WHY: 只有在打开自动保存开关时才启动每 10 分钟一次的自动保存。
  const autoSaveTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  useEffect(() => {
    if (autoSaveTimerRef.current) {
      clearInterval(autoSaveTimerRef.current);
      autoSaveTimerRef.current = null;
    }

    if (!autoSaveEnabled) return;

    autoSaveTimerRef.current = setInterval(async () => {
      try {
        if (sections.length > 0 && canWrite) {
          await performSave(true, true);
          console.log('[AutoSave] 自动保存成功', new Date().toLocaleTimeString());
        }
      } catch (err) {
        console.warn('[AutoSave] 自动保存失败', err);
      }
    }, 10 * 60 * 1000); // 10分钟自动保存一次

    return () => {
      if (autoSaveTimerRef.current) {
        clearInterval(autoSaveTimerRef.current);
        autoSaveTimerRef.current = null;
      }
    };
  }, [autoSaveEnabled, sections, templateTitle, currentDocId, projectId, canWrite]);

  // WHY: 显示浮动 toast 通知，自动 4 秒消失
  const showToast = (message: string, type: 'success' | 'warning' | 'error' = 'success') => {
    if (toastTimerRef.current) clearTimeout(toastTimerRef.current);
    setToast({ message, type });
    toastTimerRef.current = setTimeout(() => setToast(null), 4000);
  };


  const {
    isGeneratingAll,
    handleGenerateAll, handleStopBatch,
  } = useGenerationQueue({
    sections, canWrite, sectionRefs, abortControllerRef, performSave, showToast,
    activateSection: setActiveHeadingId,
  });





  // WHY: 🛡️ 紧急保存 — 用户关闭/刷新页面时同步保存当前进度到后端。
  //      beforeunload 中不能用 async fetch，只能用 navigator.sendBeacon。
  //      visibilitychange 在切后台/最小化时触发，作为额外保险。
  useEffect(() => {
    const emergencySave = () => {
      if (sections.length === 0 || !canWrite) return;
      try {
        const { getAuthHeaders: getHeaders } = useAuthStore.getState();
        const commonHeaders = { ...getHeaders(), 'Content-Type': 'application/json' };

        // WHY: 如果没有活动的文档 ID，且自动保存开关是关闭的，我们无需向 documents 列表中创建孤立的“自动保存”备份文件。
        //      因为 template 接口的同步已经足够保存当前的进度，下次打开直接能还原草稿。
        if (!currentDocId && !autoSaveEnabled) {
          fetch(`${API_BASE}/api/projects/${projectId || 'default'}/template`, {
            method: 'POST',
            headers: commonHeaders,
            body: JSON.stringify({ title: templateTitle, sections: sections }),
            keepalive: true,
          }).catch(() => {});
          console.log('[EmergencySave] 无活跃文档ID且自动保存关闭，仅紧急同步至主模板大纲');
          return;
        }

        // 否则（有活跃的文档ID，或者开启了自动保存），我们执行备份到 /documents
        // 如果开启了自动保存但 docId 为空，使用固定 ID 'autosave'，这样在后端只会覆盖同一条自动保存快照记录，避免产生多份冗余文件。
        const docId = currentDocId || 'autosave';

        const fullText = `# ${templateTitle}\n\n` + sections.map((s: DocSection) => {
          let text = s.content.replace(/<(?:br|\/?(?:p|div|li|ul|ol|h[1-6]|table|tr))[^>]*>/gi, '\n');
          text = text.replace(/<[^>]+>/g, '');
          text = text.replace(/(\[可视化[：:].+?\])/g, '\n$1\n');
          text = text.replace(/\n{3,}/g, '\n\n');
          return `## ${s.title}\n${text.trim()}`;
        }).join('\n\n');

        const docData = {
          id: docId,
          title: docId === 'autosave' ? `${templateTitle.replace(/（自动保存）$/, '').replace(/\(自动保存\)$/, '')}（自动保存）.docx` : templateTitle,
          content: fullText,
          timestamp: Date.now(),
          tokens: fullText.length,
          sections: sections,
          isAutoSave: true
        };

        const url = `${API_BASE}/api/projects/${projectId || 'default'}/documents`;
        
        fetch(url, {
          method: 'POST',
          headers: commonHeaders,
          body: JSON.stringify(docData),
          keepalive: true,  // WHY: 关键！让浏览器在页面卸载后也继续发送请求
        }).catch(() => {});

        // WHY: 页面退出时紧急将状态合并至主模板，防止别的设备打开空白
        fetch(`${API_BASE}/api/projects/${projectId || 'default'}/template`, {
          method: 'POST',
          headers: commonHeaders,
          body: JSON.stringify({ title: templateTitle, sections: sections }),
          keepalive: true,
        }).catch(() => {});
        console.log('[EmergencySave] 页面关闭前紧急保存已发送');
      } catch (err) {
        console.warn('[EmergencySave] 紧急保存失败', err);
      }
    };

    const handleBeforeUnload = (e: BeforeUnloadEvent) => {
      // WHY: 如果正在生成中，弹出确认框，给用户一个挽回的机会
      if (isGeneratingAll) {
        e.preventDefault();
        e.returnValue = '文档正在生成中，关闭页面可能导致未保存的内容丢失。确定离开吗？';
      }
      emergencySave();
    };

    const handleVisibilityChange = () => {
      // WHY: 页面切到后台时也触发一次保存，覆盖移动端/平板"直接切走"的场景
      if (document.visibilityState === 'hidden' && sections.length > 0 && canWrite) {
        emergencySave();
      }
    };

    window.addEventListener('beforeunload', handleBeforeUnload);
    document.addEventListener('visibilitychange', handleVisibilityChange);

    return () => {
      window.removeEventListener('beforeunload', handleBeforeUnload);
      document.removeEventListener('visibilitychange', handleVisibilityChange);
    };
  }, [sections, templateTitle, currentDocId, projectId, canWrite, isGeneratingAll]);


  const handleSaveToLibrary = async (e: React.MouseEvent<HTMLButtonElement>) => {
    const btn = e.currentTarget;
    const originalHtml = btn.innerHTML;
    try {
      btn.innerHTML = '<span class="text-indigo-600 font-medium">✨ 归档中...</span>';

      // WHY: 手动保存标记 isAutoSave=false，覆盖自动保存的弱标识
      await performSave(false);

      btn.innerHTML = '<span class="text-indigo-600 font-medium">✨ 已归档至右侧素材库</span>';
    } catch (err) {
      console.error(err);
      btn.innerHTML = '<span class="text-red-500 font-medium">❌ 归档失败</span>';
    }
    setTimeout(() => { btn.innerHTML = originalHtml; }, 2000);
  };

  // WHY: 范文上传处理 — 调用 /api/exemplar/parse 解析带正文的范文，
  //      然后持久化存储到项目路径并更新前端状态。

  /**
   * 从预计算缓存填充所有章节（防内存溢出版本）。
   * WHY: 207 个 Tiptap 编辑器同时存在于 DOM，如果在一帧内全部
   *      调用 setContent + 触发 store 更新，会产生 O(n²) 的
   *      reconciliation 风暴直接撑爆 Chrome 渲染进程。
   *
   * 策略：
   *   1. 先将所有缓存内容通过一次 setTemplateData 批量写入 store
   *   2. 再分批（每批 BATCH_SIZE 个）把 HTML 注入 Tiptap 编辑器 DOM
   *      每批之间 yield 一帧时间让浏览器 GC 喘息
   */
  const fillFromCache = async (cachedSections: any[]) => {
    setIsFillingCache(true);
    const { marked } = await import('marked');
    marked.setOptions({ breaks: true, gfm: true });

    // ── 第一步：匹配 + 转换 HTML（纯计算，不碰 DOM） ──
    const liveSections = useProjectStore.getState().templateSections as DocSection[];
    const titleToIdx: Record<string, number> = {};
    for (let i = 0; i < liveSections.length; i++) {
      const s = liveSections[i];
      const normTitle = s.title.replace(/^[一二三四五六七八九十\d\.（()）)、\s]+/, '').trim();
      titleToIdx[normTitle] = i;
      titleToIdx[s.title] = i;
    }

    // WHY: 预解析所有缓存内容为 HTML，记录匹配结果
    const matchedItems: { idx: number; sid: string; html: string; sources: string[] }[] = [];
    for (const cached of cachedSections) {
      if (cached.status !== 'ok' || !cached.markdown?.trim()) continue;
      const cachedTitle = cached.title || '';
      const normCachedTitle = cachedTitle.replace(/^[一二三四五六七八九十\d\.（()）)、\s]+/, '').trim();
      const matchedIdx = titleToIdx[cachedTitle] ?? titleToIdx[normCachedTitle];
      if (matchedIdx === undefined) continue;

      let html = await marked.parse(sanitizeTableMarkdown(cached.markdown));
      html = removeHrFromHtml(html);
      html = renderLatexInHtml(html);
      const tableHtml = convertMarkdownTables(html);
      if (tableHtml !== html) html = tableHtml;
      matchedItems.push({ idx: matchedIdx, sid: liveSections[matchedIdx].id, html, sources: cached.sources || [] });
    }

    if (matchedItems.length === 0) {
      setIsFillingCache(false);
      showToast('⚠️ 预计算缓存与当前大纲无匹配章节', 'warning');
      return;
    }

    // ── 第二步：一次性批量更新 Store（仅 1 次 Zustand set）──
    const updatedSections = [...liveSections];
    for (const item of matchedItems) {
      updatedSections[item.idx] = {
        ...updatedSections[item.idx],
        content: item.html,
        sources: item.sources,
      };
    }
    const { setTemplateData } = useProjectStore.getState();
    const liveTitle = useProjectStore.getState().templateTitle;
    setTemplateData(liveTitle || templateTitle || projectName || '新报告', updatedSections);

    // WHY: 虚拟化编辑器架构下，非激活章节用 dangerouslySetInnerHTML 直接
    //      从 store 渲染静态 HTML，无需手动注入 Tiptap DOM。
    //      setTemplateData 更新 store 后 React 自动 re-render 即可显示内容。

    // 滚动到第一个填充的章节
    if (matchedItems.length > 0) {
      const firstEl = document.getElementById(`sec-${matchedItems[0].sid}`);
      if (firstEl) firstEl.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }

    setIsFillingCache(false);
    showToast(`✅ 已从预计算缓存加载 ${matchedItems.length} 个章节`, 'success');
    // 自动保存
    if (matchedItems.length > 0 && canWrite) {
      try { await performSave(true); } catch (e) { /* ignore */ }
    }
  };

  /**
   * 检查指定模式的预计算缓存，有则填充，无则回退到实时生成。
   * 返回 true 表示已从缓存填充，false 表示无缓存。
   */
  const tryUseDraftCache = async (mode: string): Promise<boolean> => {
    try {
      const res = await fetch(
        `${API_BASE}/api/exemplar/project/${projectId || 'default'}/draft_cache/${mode}`,
        { headers: getAuthHeaders() }
      );
      if (!res.ok) return false;
      const data = await res.json();
      if (!Array.isArray(data) || data.length === 0) return false;
      // WHY: 范文和模板大纲的章节数可能不同，放宽阈值：只要有缓存就尝试匹配
      const okCount = data.filter((d: any) => d.status === 'ok' && d.markdown?.trim()).length;
      if (okCount === 0) return false;
      await fillFromCache(data);
      return true;
    } catch {
      return false;
    }
  };

  const handleGenerateSection = async (section: DocSection, editor: any, mode?: string) => {
    // WHY: 每次生成创建新的 AbortController，供 handleStopBatch 中断
    const controller = new AbortController();
    abortControllerRef.current = controller;

    // WHY: FRPS 服务端的 vhostHTTPTimeout 默认仅 60s，大模型长思考时代理会直接砍断 SSE 连接。
    //      如果流中断后编辑器内容仍为空，说明这次中断发生在"代理层"而非"LLM 层"，
    //      此时自动重试一次可以大概率成功（因为模型已预热、RAG 已缓存）。
    const MAX_RETRIES = 2;
    for (let attempt = 0; attempt < MAX_RETRIES; attempt++) {

    try {
      // 聚合历史上下文，给大模型参考
      const currentIndex = sections.findIndex((s: DocSection) => s.id === section.id);
      const historyText = sections.slice(0, currentIndex).map((s: DocSection) => s.content.replace(/<[^>]*>?/gm, '')).join('\n');
      
      const response = await fetch(`${API_BASE}/api/generate/paragraph`, {
        method: "POST",
        headers: { ...getAuthHeaders(), "Content-Type": "application/json" },
        signal: controller.signal,
        body: JSON.stringify({
           title: section.title,
           context: historyText.slice(-2000),
           file_ids: checkedFileIds,
           project_id: projectId,
           model: selectedModel,
           project_name: projectName,
           exemplar_id: hasExemplar ? projectId : '',
           section_index: currentIndex,
           section_level: section.level,
           mode: mode || 'generate',
           collaborative: collaborative,
           custom_instruction: customInstruction,
        })
      });
      
      if (!response.ok) {
        if (response.status === 401) {
           throw new Error('401_UNAUTHORIZED');
        }
        throw new Error(`服务器拒绝或出现问题，状态码：${response.status}`);
      }
      
      if (!response.body) return;
      
      const reader = response.body.getReader();
      const decoder = new TextDecoder('utf-8');
      
      let isFirstChunk = true;
      let titleChecked = false;
      let rawMarkdown = '';  // WHY: 累积原始 Markdown 文本，流式结束后统一转 HTML
      let tokenBatchBuf = '';  // WHY: Token 批次合并缓冲区
      let tokenBatchFlushCount = 0;  // WHY: 批次计数，控制 scrollIntoView 频率
      
      const coreTitle = section.title ? section.title.replace(/^[一二三四五六七八九十\d（()）)、.\s]+/, '').trim() : '';
      const TITLE_BUF_LIMIT = coreTitle ? coreTitle.length + 15 : 20;
      
      const stripTitleFromText = (text: string): string => {
        if (!coreTitle) return text;
        
        try {
          const escapedCore = coreTitle.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
          const escapedFull = section.title.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
          // WHY: 归一化所有的字面量 \\n 为真实的换行符 \n，以便正则的 ^ 匹配能在换行首位生效。
          let cleaned = text.replace(/\\n/g, '\n');
          cleaned = cleaned
            .replace(new RegExp('^\\s*(?:[#*]+\\s*)?(?:[一二三四五六七八九十\\d（()）)、.\\s]*?)?' + escapedCore + '[*]*\\s*\\n?'), '')
            .replace(new RegExp('^\\s*(?:[#*]+\\s*)?' + escapedFull + '[*]*\\s*\\n?'), '');
          cleaned = cleaned.replace(/^\n+/, '');
          return cleaned;
        } catch {
          return text;
        }
      };

      const cleanMarkdownCollaborativeArtifacts = (markdown: string): string => {
        if (!markdown) return markdown;
        
        const settings = useProjectStore.getState().publicSettings;
        const contrarianName = settings?.collab_contrarian_name || '【协同】合规审查员';
        const arbiterName = settings?.collab_arbiter_name || '【协同】公文终审员';
        const escContrarian = contrarianName.replace(/[.*+?^${}()|[\\\]]/g, '\\$&');
        const escArbiter = arbiterName.replace(/[.*+?^${}()|[\\\]]/g, '\\$&');
        
        const expertMatch = markdown.match(/(?:⚖️|\[段落起草专家\])/);
        const bossMatch = markdown.match(new RegExp(`(?:👑|\\[大BOSS\\]|\\[${escArbiter}\\])`));
        
        if (expertMatch && bossMatch && bossMatch.index! > expertMatch.index!) {
          const bossEndRegex = new RegExp(`(?:👑|\\[大BOSS\]|\\[${escArbiter}\\]).*?(?:最终措辞润色|逻辑修正).*?(?:\n|$)`, 's');
          const endMatch = markdown.substring(bossMatch.index!).match(bossEndRegex);
          if (endMatch) {
            const endIdx = bossMatch.index! + endMatch.index! + endMatch[0].length;
            let headerPart = markdown.substring(0, expertMatch.index!).trim();
            headerPart = headerPart.replace(/(?:⚖️|[\u2696\ufe0f⚖️]|\s|\*|<strong>|<p>|<hr\s*\/?>)+$/, '').trim();
            const bodyPart = markdown.substring(endIdx).trim();
            
            if (bodyPart.length > 5) {
              return (headerPart + '\n\n' + bodyPart).trim();
            }
          }
        }
        
        if (expertMatch) {
          const expertEndRegex = /(?:⚖️|\[段落起草专家\]).*?正在起草章节初稿.*?(?:\n|$)/s;
          const endMatch = markdown.substring(expertMatch.index!).match(expertEndRegex);
          if (endMatch) {
            const endIdx = expertMatch.index! + endMatch.index! + endMatch[0].length;
            let headerPart = markdown.substring(0, expertMatch.index!).trim();
            headerPart = headerPart.replace(/(?:⚖️|[\u2696\ufe0f⚖️]|\s|\*|<strong>|<p>|<hr\s*\/?>)+$/, '').trim();
            
            let draftPart = markdown.substring(endIdx);
            const contrarianMatch = draftPart.match(new RegExp(`(?:🤨|\\[小杠\\]|\\[${escContrarian}\]|👑|\\[大BOSS\\]|\\[${escArbiter}\]|---)`));
            if (contrarianMatch) {
              draftPart = draftPart.substring(0, contrarianMatch.index!);
            }
            draftPart = draftPart.trim();
            return (headerPart + '\n\n' + draftPart).trim();
          }
        }
        
        return markdown;
      };
      
      let streamBuffer = '';
      
      while (true) {
         if (controller.signal.aborted) {
           await reader.cancel();
           break;
         }
         const { done, value } = await reader.read();
         if (done) {
           if (!titleChecked) {
             const currentText = editor.getText();
             // Fix: Don't let leading newlines prematurely trigger the check
             const textWithoutLeadingSpaces = currentText.replace(/^\s+/, '');
             if (textWithoutLeadingSpaces.length >= TITLE_BUF_LIMIT || (textWithoutLeadingSpaces.length > 5 && textWithoutLeadingSpaces.includes('\n'))) {
                 titleChecked = true;
                 const cleaned = stripTitleFromText(currentText);
                 if (cleaned !== currentText) {
                     editor.chain().setContent(cleaned.replace(/\n/g, '<br/>')).focus('end').run();
                 }
             }
           }
           if (streamBuffer) {
              // process residual SSE lines
           }

           // WHY: flush 残余 tokenBatchBuf — 流结束时可能还有 <200 字的尾巴未 flush
           if (tokenBatchBuf) {
             const htmlToken = tokenBatchBuf
               .replace(/\n\n/g, '</p><p>')
               .replace(/\n/g, '<br/>');
             editor.commands.insertContent(htmlToken);
             tokenBatchBuf = '';
           }

           // WHY: 流式完毕后将累积的 Markdown 统一转 HTML，渲染加粗/标题/列表等
           if (rawMarkdown.trim()) {
              rawMarkdown = stripTitleFromText(rawMarkdown);
              if (!titleChecked) {
                  titleChecked = true;
                  const cleaned = stripTitleFromText(editor.getText());
                  if (cleaned !== editor.getText()) {
                      editor.chain().setContent(cleaned.replace(/\n\n/g, '</p><p>').replace(/\n/g, '<br/>')).focus('end').run();
                  }
              }
             try {
                const { marked } = await import('marked');
                marked.setOptions({ breaks: true, gfm: true });
                const cleanedMarkdown = cleanMarkdownCollaborativeArtifacts(rawMarkdown);
                 let html = await marked.parse(sanitizeTableMarkdown(cleanedMarkdown));
                html = removeHrFromHtml(html);
                html = renderLatexInHtml(html);
                const tableHtml = convertMarkdownTables(html);
                if (tableHtml !== html) html = tableHtml;
                editor.commands.setContent(html);
             } catch (e) {
               console.warn('Markdown parse failed', e);
               const ch = editor.getHTML();
               const th = convertMarkdownTables(ch);
               if (th !== ch) editor.commands.setContent(th);
             }
           }

           // WHY: 立即同步编辑器内容到 store，防止批量保存竞态条件。
           //      Tiptap onUpdate 有 800ms 节流，handleGenerateAll 在 generate() 返回后
           //      可能立即 performSave()，此时 store 还是旧快照（空），导致丢内容。
           {
             const finalHtml = editor.getHTML();
             if (finalHtml && finalHtml !== '<p></p>') {
               const { updateSectionContent } = useProjectStore.getState();
               updateSectionContent(section.id, finalHtml);
             }
           }

           break;
         }
         
         streamBuffer += decoder.decode(value, { stream: true });
         let newlineIndex;
         
         while ((newlineIndex = streamBuffer.indexOf('\n\n')) >= 0) {
             const chunk = streamBuffer.slice(0, newlineIndex);
             streamBuffer = streamBuffer.slice(newlineIndex + 2);
             
             const lines = chunk.split('\n');
             for (const line of lines) {
                 if (line.startsWith('data: ')) {
                     try {
                         const data = JSON.parse(line.slice(6));
                         if (data.skip) return;
                         if (data.sources) {
                             const { updateSectionSources } = useProjectStore.getState();
                             updateSectionSources(section.id, data.sources);
                         }
                         // WHY: Slot-Filling Phase 2 映射表预览 — 在正文生成前展示即将执行的变量替换，
                         //      让用户能看到"船山区→蓬溪县"等具体替换项，增强信任感。
                         //      使用临时 DOM 元素（类似 think-indicator），生成完毕后自动清除。
                         if (data.slots && Array.isArray(data.slots) && data.slots.length > 0) {
                             const secEl = document.getElementById(`sec-${section.id}`);
                             if (secEl && !secEl.querySelector('.slot-preview')) {
                               const slotDiv = document.createElement('div');
                               slotDiv.className = 'slot-preview';
                               slotDiv.style.cssText = 'background: linear-gradient(135deg, #f0fdf4 0%, #ecfdf5 100%); border: 1px solid #86efac; border-radius: 8px; padding: 8px 12px; margin-bottom: 8px; font-size: 12px; color: #166534; max-height: 120px; overflow-y: auto;';
                               const title = document.createElement('div');
                               title.style.cssText = 'font-weight: 600; margin-bottom: 4px; display: flex; align-items: center; gap: 4px;';
                               title.textContent = `🔄 变量映射表 (${data.slots.length} 项)`;
                               slotDiv.appendChild(title);
                               const list = document.createElement('div');
                               list.style.cssText = 'display: flex; flex-wrap: wrap; gap: 4px;';
                               data.slots.slice(0, 12).forEach((s: any) => {
                                 const tag = document.createElement('span');
                                 tag.style.cssText = `display: inline-flex; align-items: center; gap: 2px; padding: 2px 6px; border-radius: 4px; font-size: 11px; ${s.new === '[待补充]' ? 'background: #fef3c7; color: #92400e;' : 'background: #dbeafe; color: #1e40af;'}`;
                                 tag.textContent = `${s.old} → ${s.new}`;
                                 list.appendChild(tag);
                               });
                               if (data.slots.length > 12) {
                                 const more = document.createElement('span');
                                 more.style.cssText = 'color: #6b7280; font-size: 11px; padding: 2px 4px;';
                                 more.textContent = `+${data.slots.length - 12} 项...`;
                                 list.appendChild(more);
                               }
                               slotDiv.appendChild(list);
                               secEl.insertBefore(slotDiv, secEl.firstChild);
                             }
                         }
                         // WHY: Self-Check 数值校验告警 — 后端在流结束前推送可疑数值列表，
                         //      前端渲染为"数据溯源提示"面板，帮助用户识别可能的幻觉数值。
                         if (data.verify_warnings && Array.isArray(data.verify_warnings) && data.verify_warnings.length > 0) {
                             const secEl = document.getElementById(`sec-${section.id}`);
                             if (secEl && !secEl.querySelector('.verify-warnings')) {
                               const warnDiv = document.createElement('div');
                               warnDiv.className = 'verify-warnings';
                               warnDiv.style.cssText = 'background: linear-gradient(135deg, #fffbeb 0%, #fef3c7 100%); border: 1px solid #fcd34d; border-radius: 8px; padding: 8px 12px; margin-top: 8px; font-size: 12px; color: #92400e;';
                               const title = document.createElement('div');
                               title.style.cssText = 'font-weight: 600; margin-bottom: 4px; display: flex; align-items: center; gap: 4px;';
                               title.textContent = '📋 数据溯源提示（非错误，建议复核）';
                               warnDiv.appendChild(title);
                               const list = document.createElement('div');
                               list.style.cssText = 'display: flex; flex-wrap: wrap; gap: 4px;';
                               data.verify_warnings.forEach((w: any) => {
                                 const tag = document.createElement('span');
                                 const bgColor = w.severity === 'high' ? 'background: #fee2e2; color: #991b1b;' : 'background: #fef3c7; color: #92400e;';
                                 tag.style.cssText = `display: inline-flex; align-items: center; gap: 2px; padding: 2px 8px; border-radius: 4px; font-size: 11px; ${bgColor}`;
                                 tag.textContent = `⚠️ "${w.value}" 未在参考资料中直接出现`;
                                 list.appendChild(tag);
                               });
                               warnDiv.appendChild(list);
                               secEl.appendChild(warnDiv);
                             }
                         }
                         if (data.type === 'agent_event') {
                             const secEl = document.getElementById(`sec-${section.id}`);
                             if (secEl) {
                               const oldInd = secEl.querySelector('.agent-collab-indicator');
                               if (oldInd) oldInd.remove();
                               
                               const indicator = document.createElement('div');
                               indicator.className = 'agent-collab-indicator';
                               indicator.style.cssText = 'color: #4f46e5; font-weight: 600; font-size: 11px; padding: 6px 12px; background: #f5f3ff; border: 1px solid #ddd6fe; border-radius: 6px; margin-bottom: 8px; display: inline-flex; align-items: center; gap: 6px; width: fit-content;';
                               
                               const agentEmojis: Record<string, string> = {
                                 supervisor: '🧠', rag: '📚', rag_agent: '📚',
                                 legal: '⚖️', legal_agent: '⚖️',
                                 service: '📝', service_agent: '📝',
                                 data: '📊', data_agent: '📊',
                                 contrarian: '🤨', arbiter: '📝',
                               };
                               const emoji = agentEmojis[data.agent] || '🤖';
                               const settings = useProjectStore.getState().publicSettings;
                               const roleNameMap: Record<string, string> = {
                                 supervisor: settings?.collab_supervisor_name || '【协同】公文秘书',
                                 contrarian: settings?.collab_contrarian_name || '【协同】合规审查员',
                                 arbiter: settings?.collab_arbiter_name || '【协同】公文终审员',
                                 rag_agent: '【协同】知识检索助手',
                                 direct_answer: '【协同】直答助手',
                               };
                               const roleName = roleNameMap[data.agent] || '协同';
                               indicator.textContent = `${emoji} [${roleName}] ${data.message}`;
                               secEl.insertBefore(indicator, secEl.firstChild);
                             }
                         }
                         if (data.think_active) {
                             // WHY: think 提示文字不写入编辑器内容，改为动态插入临时 DOM 元素。
                             //      避免中途中断时残留在编辑器中被误判为「已有内容」导致下次生成跳过。
                             const secEl = document.getElementById(`sec-${section.id}`);
                             if (secEl && !secEl.querySelector('.think-indicator')) {
                               const indicator = document.createElement('div');
                               indicator.className = 'think-indicator';
                               indicator.style.cssText = 'color: #818cf8; font-style: italic; font-size: 13px; padding: 8px 0; animation: pulse 2s infinite;';
                               indicator.textContent = '💭 AI 知识深度推演中... (视复杂度可能等待数十秒，请耐心等待)';
                               secEl.appendChild(indicator);
                             }
                         }
                         if (data.think_end) {
                             // WHY: 推理结束，移除临时 DOM 提示，编辑器内容保持干净
                             const secEl = document.getElementById(`sec-${section.id}`);
                             const indicator = secEl?.querySelector('.think-indicator');
                             if (indicator) indicator.remove();
                         }
                         
                         if (data.token !== undefined) {
                             if (isFirstChunk) {
                                 editor.chain().setContent('').focus('end').run();
                                 isFirstChunk = false;
                             }
                             rawMarkdown += data.token;  // 累积原始 Markdown

                             // WHY: Token 批次合并 — 逐 token 调用 insertContent + scrollIntoView
                             //      会在 207 个章节的大 DOM 中触发海量 reconciliation，导致 OOM。
                             //      累积到 200 字或遇到段落分隔符时才批量 flush 一次，
                             //      将 DOM 更新次数降低 50-100 倍。
                             tokenBatchBuf += data.token;
                             const TOKEN_BATCH_SIZE = 200;
                             const shouldFlush = tokenBatchBuf.length >= TOKEN_BATCH_SIZE
                                               || tokenBatchBuf.includes('\n\n');
                             if (shouldFlush) {
                               const htmlToken = tokenBatchBuf
                                 .replace(/\n\n/g, '</p><p>')
                                 .replace(/\n/g, '<br/>');
                               editor.commands.insertContent(htmlToken);
                               tokenBatchBuf = '';
                               tokenBatchFlushCount++;

                               // 每 5 次 flush 才滚动一次（~1000 字/次），避免频繁滚动
                               if (tokenBatchFlushCount % 5 === 0) {
                                 const el = document.getElementById(`sec-${section.id}`);
                                 if (el) el.scrollIntoView({ behavior: 'smooth', block: 'end' });
                               }
                             }
                             
                             if (!titleChecked) {
                                 const currentText = editor.getText();
                                 const textWithoutLeadingSpaces = currentText.replace(/^\s+/, '');
                                 if (textWithoutLeadingSpaces.length >= TITLE_BUF_LIMIT || (textWithoutLeadingSpaces.length > 5 && textWithoutLeadingSpaces.includes('\n'))) {
                                     titleChecked = true;
                                     const cleaned = stripTitleFromText(currentText);
                                     if (cleaned !== currentText) {
                                         editor.chain().setContent(cleaned.replace(/\n/g, '<br/>')).focus('end').run();
                                         rawMarkdown = stripTitleFromText(rawMarkdown);
                                     }
                                 }
                             }
                         }
                 } catch (e) {
                     console.error("Parse error:", e, "Line:", line);
                 }
             }
         }
        }
      }

      // WHY: 成功完成后跳出重试循环
      break;

    } catch (err) {
      const e = err as any;
      // WHY: AbortError 是用户主动停止，不弹 alert
      if (e.name === 'AbortError') {
        console.log('生成已被用户手动停止');
        const finalHtml = editor.getHTML();
        if (finalHtml && finalHtml !== '<p></p>') {
          const { updateSectionContent } = useProjectStore.getState();
          updateSectionContent(section.id, finalHtml);
        }
        return;
      }
      if (e.message === '401_UNAUTHORIZED') {
        const finalHtml = editor.getHTML();
        if (finalHtml && finalHtml !== '<p></p>') {
          const { updateSectionContent } = useProjectStore.getState();
          updateSectionContent(section.id, finalHtml);
        }
        throw e;
      }

      // WHY: 检测编辑器当前内容 — 如果已经有实质性内容写入，说明 LLM 确实输出了部分结果，
      //      此时不应重试（重试会覆盖已有的部分内容），而是保留现有结果继续下一章节。
      //      只有编辑器完全为空时才重试（说明代理层在首字之前就断了连接）。
      const editorText = editor.getText().replace(/<[^>]*>?/gm, '').trim();
      if (editorText.length > 5 || attempt >= MAX_RETRIES - 1) {
        console.error('生成异常:', e);
        console.warn(`章节「${section.title}」生成中断: ${e.message || '网络异常'}，将继续处理下一章节`);
        const finalHtml = editor.getHTML();
        if (finalHtml && finalHtml !== '<p></p>') {
          const { updateSectionContent } = useProjectStore.getState();
          updateSectionContent(section.id, finalHtml);
        }
        break; // 有内容或已到最后一次重试，跳出
      }

      // WHY: 无内容且还有重试机会 — 很可能是 FRPS vhostHTTPTimeout=60s 在 Prefill 阶段砍断了连接。
      //      等待 2 秒后重试：此时模型已预热、RAG 检索结果已缓存，第二次请求通常能快速拿到首字。
      console.warn(`章节「${section.title}」代理超时（编辑器为空），2s 后自动重试 (${attempt + 1}/${MAX_RETRIES})...`);
      await new Promise(r => setTimeout(r, 2000));

    } finally {
      // WHY: 无论成功/中断/异常，都必须清理 think-indicator 和 slot-preview DOM 元素，
      //      避免中途失败后临时提示永久残留在页面上。
      const secEl = document.getElementById(`sec-${section.id}`);
      const indicator = secEl?.querySelector('.think-indicator');
      if (indicator) indicator.remove();
      const slotPreview = secEl?.querySelector('.slot-preview');
      if (slotPreview) slotPreview.remove();
      const collabInd = secEl?.querySelector('.agent-collab-indicator');
      if (collabInd) collabInd.remove();
      abortControllerRef.current = null;
    }

    } // end retry loop
  };

  const saveContent = (id: string, htmlContent: string) => {
    updateSectionContent(id, htmlContent);
  };

  const calculateIndent = (level: number) => {
    switch (level) {
      case 1: return 'pl-2';
      case 2: return 'pl-5';
      case 3: return 'pl-8';
      case 4: return 'pl-11';
      default: return 'pl-2';
    }
  };

  return (
    <div className="flex flex-col h-full w-full bg-white">
      {/* Studio Header */}
      <header className="flex-shrink-0 border-b border-gray-200 bg-white flex flex-col">
        {/* Row 1: Title */}
        <div className="px-6 py-3 border-b border-gray-100 flex items-center gap-3">
          <FileText className="w-6 h-6 text-blue-600 shrink-0" />
          <input 
            value={templateTitle}
            onChange={(e) => setTemplateTitle(e.target.value)}
            onBlur={async () => {
              // WHY: 标题修改后失焦即保存，不需要等 5 分钟自动保存周期
              if (sections.length > 0 && canWrite) {
                try {
                  await performSave(true);
                } catch {}
              }
            }}
            className="text-lg font-semibold text-gray-800 bg-transparent border-b border-transparent hover:border-gray-300 focus:border-indigo-400 focus:ring-0 px-2 py-1 outline-none transition-colors flex-1 min-w-0"
            title="点击修改报表标题"
          />
          {canWrite && (
            <div className="flex items-center gap-2 shrink-0 ml-auto bg-stone-50 border border-stone-200/60 rounded-xl px-3 py-1.5 shadow-sm">
              <span className="text-xs text-stone-500 font-medium select-none">自动保存 (10分钟)</span>
              <button
                onClick={() => setAutoSaveEnabled(!autoSaveEnabled)}
                className={`relative inline-flex h-5 w-9 items-center rounded-full transition-colors duration-300 outline-none ${
                  autoSaveEnabled ? 'bg-indigo-500' : 'bg-stone-200'
                }`}
                title={autoSaveEnabled ? '点击关闭自动保存' : '点击开启10分钟定时自动保存'}
              >
                <span
                  className={`inline-block h-3.5 w-3.5 transform rounded-full bg-white shadow transition-transform duration-300 ${
                    autoSaveEnabled ? 'translate-x-4.5' : 'translate-x-1'
                  }`}
                />
              </button>
            </div>
          )}
        </div>
        {/* Row 2: Actions — 三组分布 */}
        <div className="px-6 py-2.5 flex items-center bg-gray-50/50">
          {/* 一组：靠左 — 一键成文 + 一键清除 + 协同 */}
          <div className="flex items-center gap-2">

            {/* 0. 大纲模板 */}
            <button
              onClick={() => setShowTemplateModal(true)}
              className="px-3 py-1.5 border border-indigo-200 text-indigo-600 bg-indigo-50/30 rounded text-xs font-medium hover:bg-indigo-50 flex items-center gap-1.5 transition-colors shrink-0"
              title="更换或上传大纲模板"
            >
              <FileText className="w-3.5 h-3.5" /> 大纲模板
            </button>

            {/* 1. 一键成文 */}
            {isGeneratingAll ? (
              <button onClick={handleStopBatch} className="px-3 py-1.5 border border-red-300 text-red-600 bg-red-50 rounded text-xs font-medium hover:bg-red-100 flex items-center gap-1.5 transition-colors">
                <Square className="w-3 h-3 fill-red-500" /> 停止生成
              </button>
            ) : (
              <button onClick={async () => { if (!(await tryUseDraftCache('generate'))) handleGenerateAll(); }} disabled={isFillingCache || sections.length === 0} className="px-3 py-1.5 border border-purple-200 text-purple-600 rounded text-xs font-medium hover:bg-purple-50 flex items-center gap-1.5 transition-colors disabled:opacity-50">
                <Wand2 className="w-3.5 h-3.5" /> 一键成文
              </button>
            )}

            {/* 2. 一键清除 */}
            <button
               onClick={(e) => {
                 e.preventDefault();
                 e.stopPropagation();
                 setShowClearContentConfirm(true);
               }}
               disabled={sections.length === 0}
               className="px-3 py-1.5 border border-gray-200 text-gray-600 bg-white rounded text-xs font-medium hover:bg-red-50 hover:text-red-600 hover:border-red-200 flex items-center gap-1.5 transition-colors disabled:opacity-50"
               title="清空所有章节的正文内容"
            >
               <Trash2 className="w-3.5 h-3.5" /> 一键清除
            </button>


          </div>

          {/* 靠中占位符 */}
          <div className="flex-1"></div>


          {/* 三组：靠右 — 保存 + 封面 + 导出 */}
          <div className="flex items-center gap-2">
            {/* 7. 保存 */}
            {canWrite && (
              <button onClick={handleSaveToLibrary} disabled={sections.length === 0} className="px-3 py-1.5 border border-indigo-200 text-indigo-600 rounded text-xs font-medium hover:bg-indigo-50 flex items-center gap-1.5 transition-colors disabled:opacity-50">
                <Save className="w-3.5 h-3.5" /> 保存
              </button>
            )}
            {/* 8. 封面 + 9. 导出 */}
            <ExportModals projectId={projectId || 'default'} templateTitle={templateTitle} sections={sections} showToast={showToast} />
          </div>
        </div>
      </header>

      {/* Workspace Split */}
      <div className="flex-1 overflow-hidden flex">
        {/* Left Outline */}
        <div className="w-[300px] flex-shrink-0 bg-gray-50 border-r border-gray-200 flex flex-col pt-4">
          <div className="px-4 pb-4 border-b border-gray-200 flex justify-between items-center text-xs font-medium text-gray-800">
            <span>总完成进度：<span className="text-blue-600">{progressPercent}%</span></span>
            <div className="w-24 h-1.5 bg-gray-200 rounded-full overflow-hidden">
                <div className="h-full bg-blue-500 transition-all duration-500" style={{ width: `${progressPercent}%` }}></div>
            </div>
          </div>
          <div className="px-4 py-3 border-b border-gray-100 flex justify-between items-center text-xs font-medium text-gray-700 bg-white shadow-sm z-10">
            <span>提纲目录</span>
            <div className="flex items-center gap-1.5">
              <button onClick={() => {
                setAddChapterTitle('');
                setShowAddChapterModal(true);
              }} className="p-0.5 text-gray-400 hover:text-indigo-600 transition-colors bg-gray-50 hover:bg-indigo-50 rounded" title="追加一级新章节">
                 <Plus className="w-4 h-4" />
              </button>
              <div className="w-px h-3 bg-gray-200"></div>
              <List className="w-4 h-4 text-gray-400" />
            </div>
          </div>
          
          <div className="flex-1 overflow-y-auto px-2 pt-2 pb-10 space-y-1 text-xs text-gray-600 select-none">
            {sections.length === 0 ? (
              <div className="text-center mt-10 text-gray-400 p-4 border border-dashed border-gray-300 rounded-lg mx-2">
                请在右侧区域上传规范 .docx 样稿，或者点击上方 + 号手动添加第一章节大纲。
              </div>
            ) : (
              sections.map((section: DocSection, index: number) => (
                <div 
                  key={section.id}
                  draggable
                  onDragStart={(e) => {
                     setDraggedIndex(index);
                     e.dataTransfer.effectAllowed = 'move';
                  }}
                  onDragEnter={(e) => {
                     e.preventDefault();
                     setDragOverIndex(index);
                  }}
                  onDragOver={(e) => {
                     e.preventDefault();
                     e.dataTransfer.dropEffect = 'move';
                  }}
                  onDragEnd={() => {
                     setDraggedIndex(null);
                     setDragOverIndex(null);
                  }}
                  onDrop={(e) => {
                     e.preventDefault();
                     if (draggedIndex !== null && draggedIndex !== index) {
                        reorderTemplateSections(draggedIndex, index);
                     }
                     setDraggedIndex(null);
                     setDragOverIndex(null);
                  }}
                  className={`py-1.5 px-2 rounded flex items-center gap-1 cursor-grab active:cursor-grabbing transition-all group relative ${calculateIndent(section.level)} ${
                    activeHeadingId === section.id ? 'bg-white shadow-sm font-medium text-indigo-600 border border-gray-100' : 'hover:bg-gray-200 text-gray-700'
                  } ${draggedIndex === index ? 'opacity-30' : ''} ${
                    dragOverIndex === index && draggedIndex !== index ? 'border-t-2 border-t-indigo-500 rounded-none' : ''
                  }`}
                  onClick={() => {
                     setActiveHeadingId(section.id);
                     document.getElementById(`sec-${section.id}`)?.scrollIntoView({ behavior: 'smooth', block: 'center' });

                  }}
                >
                  <span className="truncate pr-16">{section.title}</span>
                  {/* 完成标识 */}
                  {section.content.replace(/<[^>]*>?/gm, '').trim().length > 5 && (
                    <CheckCircle2 className="w-3 h-3 text-green-500 ml-auto shrink-0 group-hover:opacity-0 transition-opacity" />
                  )}

                  {/* 悬浮操作栏 */}
                  <div className="absolute right-1 top-1/2 -translate-y-1/2 flex items-center bg-white shadow-sm rounded border border-gray-200 opacity-0 group-hover:opacity-100 transition-opacity z-20" onClick={e => e.stopPropagation()}>
                    <button 
                       onClick={() => updateTemplateSectionLevel(section.id, -1)}
                       className="p-1 px-1.5 text-gray-400 hover:text-indigo-600 hover:bg-indigo-50 border-r border-gray-100" title="升级 (左移)">
                       <ChevronLeft className="w-3.5 h-3.5" />
                    </button>
                    <button 
                       onClick={() => updateTemplateSectionLevel(section.id, 1)}
                       className="p-1 px-1.5 text-gray-400 hover:text-indigo-600 hover:bg-indigo-50 border-r border-gray-100" title="降级 (右移)">
                       <ChevronRight className="w-3.5 h-3.5" />
                    </button>
                    <button 
                       onClick={() => {
                          setNewSubSectionTitle('');
                          setSubsectionToAdd({ index: index + 1, level: section.level });
                       }}
                       className="p-1 px-1.5 text-gray-400 hover:text-indigo-600 hover:bg-indigo-50 border-r border-gray-100" title="在此之后添加同级小节">
                       <Plus className="w-3.5 h-3.5" />
                    </button>
                    <button 
                       onClick={() => {
                          setSectionToDelete(section);
                       }}
                       className="p-1 px-1.5 text-gray-400 hover:text-red-500 hover:bg-red-50" title="彻底删除此小节">
                       <Trash2 className="w-3.5 h-3.5" />
                    </button>
                  </div>
                </div>
              ))
            )}
          </div>
        </div>

        {/* Right Canvas + Exemplar Preview */}
        <div className="flex-1 bg-gray-100 relative flex pt-2 pb-8 overflow-hidden gap-4 px-4 justify-center">
           {/* Main A4 Canvas */}
            <div className="w-[850px] max-w-full h-full transition-all duration-300 flex flex-col gap-4">
             {/* 自定义要求输入框（扁平无外框、自适应主题模式） */}
             <div className="bg-[#fcfbf9] dark:bg-[#1a1b1e] text-stone-850 dark:text-stone-200 p-3 rounded-xl shadow-sm border border-stone-200 dark:border-[#2e3035] flex flex-col gap-1.5 shrink-0">
               <div className="flex items-center gap-1.5 text-stone-500 dark:text-stone-400 font-bold text-xs select-none">
                 <Wand2 className="w-3.5 h-3.5 text-[#8B7355] dark:text-[#C4B5A0]" />
                 <span>文档要求</span>
               </div>
               <textarea
                 value={customInstruction}
                 onChange={(e) => setCustomInstruction(e.target.value)}
                 placeholder="请输入文档生成自定义要求..."
                 rows={2}
                 className="w-full text-xs px-1 py-0.5 bg-transparent border-none focus:outline-none text-stone-800 dark:text-stone-100 placeholder-stone-400 dark:placeholder-stone-600 leading-relaxed resize-none transition-colors"
               />
             </div>

             {sections.length > 0 ? (
               <div className="flex-1 bg-white shadow-md border border-gray-200 relative flex flex-col overflow-hidden">
                 {/* 剪纸线 Crop Marks */}
                 <div className="absolute top-4 left-4 w-4 h-4 border-t border-l border-gray-300 pointer-events-none z-10"></div>
                 <div className="absolute top-4 right-4 w-4 h-4 border-t border-r border-gray-300 pointer-events-none z-10"></div>
                 <div className="absolute bottom-4 left-4 w-4 h-4 border-b border-l border-gray-300 pointer-events-none z-10"></div>
                 <div className="absolute bottom-4 right-4 w-4 h-4 border-b border-r border-gray-300 pointer-events-none z-10"></div>
                 
                 {/* 画板标签 */}
                 <div className="absolute top-2 left-1/2 -translate-x-1/2 text-[10px] text-gray-400 bg-gray-50 px-2 py-0.5 rounded-b z-10">生成文档</div>
                 
                 {/* 内部文本流区域（独立滚动） */}
                 {/* WHY: 虚拟化编辑器——只有激活的章节渲染 SectionBlock（含 Tiptap 编辑器），
                          其余 206 个章节用纯静态 HTML 渲染，零编辑器开销。
                          这将同时存在的 Tiptap 实例从 207 个降为 1 个，防止 Chrome OOM 崩溃。 */}
                 <div className="flex-1 overflow-y-auto scroll-smooth px-12 pt-12 pb-32">
                   {sections.map((section: DocSection) => {
                     const isActive = activeHeadingId === section.id;
                     if (isActive) {
                       return (
                         <SectionBlock
                           key={section.id}
                           section={section}
                           isActive={true}
                           onActivate={() => setActiveHeadingId(section.id)}
                           onSaveContent={saveContent}
                           onGenerate={handleGenerateSection}
                           onStopGenerate={handleStopBatch}
                           ref={(methods) => {
                             if (methods) {
                               sectionRefs.current[section.id] = methods;
                             }
                           }}
                         />
                       );
                     }
                     // WHY: 非激活章节 — 纯静态 HTML，不创建 Tiptap 编辑器
                     const plainText = section.content.replace(/<[^>]*>?/gm, '').trim();
                     const hasContent = plainText.length > 0;
                     return (
                       <div
                         key={section.id}
                         className="mb-8 group cursor-pointer transition-all"
                         id={`sec-${section.id}`}
                         onClick={() => setActiveHeadingId(section.id)}
                       >
                         <h3 className={`font-bold flex items-center gap-3 text-gray-900 mb-3 ${section.level === 1 ? 'text-xl' : 'text-base'}`}>
                           {section.title}
                           <Wand2 className="w-4 h-4 text-indigo-400 opacity-30 group-hover:opacity-100 transition-opacity" />
                         </h3>
                         <div className={section.level > 1 ? 'pl-6' : ''}>
                           {hasContent ? (
                             <div
                               className="prose prose-sm xl:prose-base text-gray-700 font-light min-h-[50px]"
                               dangerouslySetInnerHTML={{ __html: section.content }}
                             />
                           ) : (
                             <p className="text-gray-400 text-sm italic min-h-[50px]">请输入或智能编写...</p>
                           )}
                           {section.sources && section.sources.length > 0 && (
                             <div className="mt-3 flex flex-wrap gap-2 pt-3 border-t border-gray-100/60">
                               {section.sources.map((src: string, i: number) => (
                                 <span key={i} className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md bg-blue-50/80 text-blue-700 text-[11px] font-medium border border-blue-100 shadow-sm">
                                   {src}
                                 </span>
                               ))}
                             </div>
                           )}
                         </div>
                       </div>
                     );
                   })}
                 </div>
               </div>
             ) : (
               <div className="flex-1 flex items-center justify-center min-h-[600px] bg-white shadow-md border border-gray-200 text-gray-400 rounded-xl">
                 A4 智能画板等待样稿映射...
               </div>
             )}
           </div>

        </div>
      </div>

      {/* WHY: 浮动 Toast 通知 — 导出质检结果、操作反馈 */}
      {toast && (
        <div className={`fixed bottom-8 left-1/2 -translate-x-1/2 z-50 px-5 py-3 rounded-lg shadow-lg border flex items-center gap-3 animate-[fadeInUp_0.3s_ease-out] ${
          toast.type === 'success' ? 'bg-green-50 border-green-200 text-green-800' :
          toast.type === 'warning' ? 'bg-amber-50 border-amber-200 text-amber-800' :
          'bg-red-50 border-red-200 text-red-800'
        }`}>
          <span className="text-sm font-medium">{toast.message}</span>
          <button onClick={() => setToast(null)} className="text-current opacity-50 hover:opacity-100 transition-opacity">
            <X className="w-3.5 h-3.5" />
          </button>
        </div>
      )}

      {showTemplateModal && createPortal(
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 backdrop-blur-sm">
          <div className="bg-white rounded-2xl shadow-2xl w-[500px] overflow-hidden flex flex-col relative animate-[fadeInUp_0.2s_ease-out]">
            {isUploadingTemplate && (
              <div className="absolute inset-0 z-50 bg-white/80 backdrop-blur-sm flex flex-col items-center justify-center">
                <Loader2 className="w-8 h-8 text-indigo-500 animate-spin mb-2" />
                <span className="text-sm font-medium text-gray-600">正在剥离大纲与样式...</span>
              </div>
            )}
            
            <div className="flex items-center justify-between px-6 py-4 border-b border-gray-100">
              <h3 className="font-semibold text-gray-800 flex items-center gap-2">
                <FileText className="w-5 h-5 text-indigo-500" />
                目标大纲模板解析库
              </h3>
              <button 
                onClick={() => setShowTemplateModal(false)}
                className="text-gray-400 hover:text-gray-600 transition-colors"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            <div className="p-6 flex flex-col items-center justify-center min-h-[220px]">
              {sections.length > 0 ? (
                <div className="w-full bg-emerald-50/50 border border-emerald-100 rounded-xl p-6 flex flex-col items-center text-center shadow-sm relative overflow-hidden group animate-[fadeInUp_0.2s_ease-out]">
                  <div className="absolute -right-4 -top-4 w-16 h-16 bg-emerald-100/50 rounded-full opacity-50 group-hover:scale-150 transition-transform duration-500" />
                  <CheckCircle2 className="w-12 h-12 text-emerald-500 mb-3 relative z-10" />
                  <h4 className="font-semibold text-gray-900 text-sm mb-1 relative z-10 w-full truncate px-2" title={originalTemplateName || templateTitle}>
                    {originalTemplateName || templateTitle}
                  </h4>
                  <p className="text-xs text-gray-500 mb-6 relative z-10">共成功挂载 {sections.length} 个骨干节点</p>
                  
                  {canWrite && (
                    <div className="flex items-center gap-3 relative z-10">
                      <input type="file" ref={templateFileInputRef} onChange={handleTemplateUpload} hidden />
                      <button 
                        onClick={() => setShowTemplateModal(false)}
                        className="px-5 py-2.5 bg-indigo-600 hover:bg-indigo-700 text-white rounded-lg text-xs font-semibold transition-all shadow-sm hover:shadow flex items-center gap-2"
                      >
                        确定
                      </button>
                      <button 
                        onClick={() => templateFileInputRef.current?.click()}
                        className="px-5 py-2.5 bg-white border border-gray-200 text-gray-700 rounded-lg text-xs font-semibold hover:bg-gray-50 hover:text-indigo-600 transition-all shadow-sm hover:shadow flex items-center gap-2"
                      >
                        <UploadCloud className="w-4 h-4" /> 更换大纲模板
                      </button>
                    </div>
                  )}
                </div>
              ) : (
                <div 
                  onClick={() => canWrite && templateFileInputRef.current?.click()}
                  className={`w-full min-h-[180px] border-2 border-dashed border-gray-200 rounded-xl flex flex-col items-center justify-center transition-all group p-6 text-center ${canWrite ? 'cursor-pointer hover:border-indigo-400 hover:bg-indigo-50/40' : 'cursor-default opacity-60'}`}
                >
                  <input type="file" ref={templateFileInputRef} onChange={handleTemplateUpload} hidden />
                  <div className={`w-12 h-12 bg-gray-50 rounded-full flex items-center justify-center mb-4 transition-colors duration-300 ${canWrite ? 'group-hover:bg-indigo-100 group-hover:scale-110' : ''}`}>
                    <UploadCloud className={`w-6 h-6 text-gray-400 ${canWrite ? 'group-hover:text-indigo-600' : ''}`} />
                  </div>
                  <h4 className={`text-sm font-semibold text-gray-700 mb-1.5 ${canWrite ? 'group-hover:text-indigo-700' : ''}`}>
                    {canWrite ? '上传大纲模板 (.docx)' : '无大纲模板（仅限项目所有者上传）'}
                  </h4>
                  {canWrite && (
                    <p className="text-xs text-gray-400 px-4 leading-relaxed">
                      拖拽或点击上传样稿文件，我们将提取其中的章节大纲结构并自动替换当前的画板框架。
                    </p>
                  )}
                </div>
              )}
            </div>
          </div>
        </div>,
        document.body
      )}



      {showClearContentConfirm && createPortal(
        <div className="fixed inset-0 z-[9999] flex items-center justify-center p-4 select-none">
          <div 
            className="absolute inset-0 bg-[#0F0F11]/45 backdrop-blur-[2px] transition-opacity" 
            onClick={() => setShowClearContentConfirm(false)}
          />
          <div className="relative bg-white dark:bg-[#1E1F22] rounded-xl p-5 shadow-2xl border border-stone-200 dark:border-stone-850 max-w-sm w-full flex flex-col gap-4 animate-in fade-in zoom-in-95 duration-200">
            <div className="flex items-start gap-3 text-stone-800 dark:text-stone-200">
              <div className="p-2.5 rounded-full bg-red-50 dark:bg-red-950/20 text-red-600 dark:text-red-400 shrink-0">
                <AlertTriangle className="w-5 h-5" />
              </div>
              <div className="flex flex-col gap-1 min-w-0">
                <h3 className="text-sm font-bold text-stone-900 dark:text-stone-100">
                  🗑️ 清空章节正文
                </h3>
                <p className="text-xs text-stone-500 dark:text-stone-400 leading-normal mt-3 whitespace-pre-wrap font-sans">
                  确定清除所有章节已生成的正文内容吗？大纲骨架与结构将被完整保留，但此操作不可逆。
                </p>
              </div>
            </div>
            <div className="flex justify-end gap-2 mt-2">
              <button
                onClick={() => setShowClearContentConfirm(false)}
                className="px-4 py-1.5 text-xs font-semibold text-stone-600 dark:text-stone-300 hover:text-stone-800 dark:hover:text-stone-100 hover:bg-stone-50 dark:hover:bg-stone-800 rounded-lg transition-colors border border-stone-200 dark:border-stone-700 cursor-pointer"
              >
                取消
              </button>
              <button
                onClick={handleClearAllContent}
                className="px-4 py-1.5 text-xs font-semibold text-white bg-red-600 hover:bg-red-700 active:scale-95 rounded-lg transition-all shadow-sm cursor-pointer"
              >
                确认清除
              </button>
            </div>
          </div>
        </div>,
        document.body
      )}

      {sectionToDelete && createPortal(
        <div className="fixed inset-0 z-[9999] flex items-center justify-center p-4 select-none">
          <div 
            className="absolute inset-0 bg-[#0F0F11]/45 backdrop-blur-[2px] transition-opacity" 
            onClick={() => setSectionToDelete(null)}
          />
          <div className="relative bg-white dark:bg-[#1E1F22] rounded-xl p-5 shadow-2xl border border-stone-200 dark:border-stone-850 max-w-sm w-full flex flex-col gap-4 animate-in fade-in zoom-in-95 duration-200">
            <div className="flex items-start gap-3 text-stone-800 dark:text-stone-200">
              <div className="p-2.5 rounded-full bg-red-50 dark:bg-red-950/20 text-red-600 dark:text-red-400 shrink-0">
                <AlertTriangle className="w-5 h-5" />
              </div>
              <div className="flex flex-col gap-1 min-w-0">
                <h3 className="text-sm font-bold text-stone-900 dark:text-stone-100">
                  🗑️ 删除大纲小节
                </h3>
                <p className="text-xs text-stone-500 dark:text-stone-400 leading-normal mt-3 whitespace-pre-wrap font-sans">
                  确定删除小节 "{sectionToDelete.title}" 吗？此操作将彻底丢弃该章节已写的所有正文内容。
                </p>
              </div>
            </div>
            <div className="flex justify-end gap-2 mt-2">
              <button
                onClick={() => setSectionToDelete(null)}
                className="px-4 py-1.5 text-xs font-semibold text-stone-600 dark:text-stone-300 hover:text-stone-800 dark:hover:text-stone-100 hover:bg-stone-50 dark:hover:bg-stone-800 rounded-lg transition-colors border border-stone-200 dark:border-stone-700 cursor-pointer"
              >
                取消
              </button>
              <button
                onClick={() => {
                  removeTemplateSection(sectionToDelete.id);
                  setSectionToDelete(null);
                }}
                className="px-4 py-1.5 text-xs font-semibold text-white bg-red-600 hover:bg-red-700 active:scale-95 rounded-lg transition-all shadow-sm cursor-pointer"
              >
                确认删除
              </button>
            </div>
          </div>
        </div>,
        document.body
      )}

      {showAddChapterModal && createPortal(
        <div className="fixed inset-0 z-[9999] flex items-center justify-center p-4 select-none">
          <div 
            className="absolute inset-0 bg-[#0F0F11]/45 backdrop-blur-[2px] transition-opacity" 
            onClick={() => setShowAddChapterModal(false)}
          />
          <div className="relative bg-white dark:bg-[#1E1F22] rounded-xl p-5 shadow-2xl border border-stone-200 dark:border-stone-850 max-w-sm w-full flex flex-col gap-4 animate-in fade-in zoom-in-95 duration-200" onClick={e => e.stopPropagation()}>
            <div className="flex flex-col gap-1.5 min-w-0">
              <h3 className="text-sm font-bold text-stone-900 dark:text-stone-100 flex items-center gap-1.5">
                ➕ 追加一级新章节
              </h3>
              <p className="text-[11px] text-stone-400 dark:text-stone-500 mt-0.5">
                在当前提纲的大纲列表末尾添加一级新章节。
              </p>
              <input
                type="text"
                autoFocus
                placeholder="请输入大章节标题..."
                value={addChapterTitle}
                onChange={e => setAddChapterTitle(e.target.value)}
                onKeyDown={e => {
                  if (e.key === 'Enter' && addChapterTitle.trim()) {
                    addTemplateSection(sections.length, addChapterTitle.trim(), 1);
                    setShowAddChapterModal(false);
                  }
                }}
                className="mt-3 w-full px-3 py-2 text-xs border border-stone-200 dark:border-stone-700 rounded-lg bg-stone-50 dark:bg-stone-800 text-stone-800 dark:text-stone-100 focus:outline-none focus:ring-1 focus:ring-indigo-500"
              />
            </div>
            <div className="flex justify-end gap-2 mt-1">
              <button
                onClick={() => setShowAddChapterModal(false)}
                className="px-4 py-1.5 text-xs font-semibold text-stone-600 dark:text-stone-300 hover:text-stone-800 dark:hover:text-stone-100 hover:bg-stone-50 dark:hover:bg-stone-800 rounded-lg transition-colors border border-stone-200 dark:border-stone-700 cursor-pointer"
              >
                取消
              </button>
              <button
                disabled={!addChapterTitle.trim()}
                onClick={() => {
                  if (addChapterTitle.trim()) {
                    addTemplateSection(sections.length, addChapterTitle.trim(), 1);
                    setShowAddChapterModal(false);
                  }
                }}
                className="px-4 py-1.5 text-xs font-semibold text-white bg-indigo-600 hover:bg-indigo-700 active:scale-95 disabled:opacity-40 disabled:pointer-events-none rounded-lg transition-all shadow-sm cursor-pointer"
              >
                确认添加
              </button>
            </div>
          </div>
        </div>,
        document.body
      )}

      {subsectionToAdd && createPortal(
        <div className="fixed inset-0 z-[9999] flex items-center justify-center p-4 select-none">
          <div 
            className="absolute inset-0 bg-[#0F0F11]/45 backdrop-blur-[2px] transition-opacity" 
            onClick={() => setSubsectionToAdd(null)}
          />
          <div className="relative bg-white dark:bg-[#1E1F22] rounded-xl p-5 shadow-2xl border border-stone-200 dark:border-stone-850 max-w-sm w-full flex flex-col gap-4 animate-in fade-in zoom-in-95 duration-200" onClick={e => e.stopPropagation()}>
            <div className="flex flex-col gap-1.5 min-w-0">
              <h3 className="text-sm font-bold text-stone-900 dark:text-stone-100 flex items-center gap-1.5">
                ➕ 添加同级小节
              </h3>
              <p className="text-[11px] text-stone-400 dark:text-stone-500 mt-0.5">
                在此小节之后追加一节同级内容大纲。
              </p>
              <input
                type="text"
                autoFocus
                placeholder="请输入新小节标题..."
                value={newSubSectionTitle}
                onChange={e => setNewSubSectionTitle(e.target.value)}
                onKeyDown={e => {
                  if (e.key === 'Enter' && newSubSectionTitle.trim()) {
                    addTemplateSection(subsectionToAdd.index, newSubSectionTitle.trim(), subsectionToAdd.level);
                    setSubsectionToAdd(null);
                  }
                }}
                className="mt-3 w-full px-3 py-2 text-xs border border-stone-200 dark:border-stone-700 rounded-lg bg-stone-50 dark:bg-stone-800 text-stone-800 dark:text-stone-100 focus:outline-none focus:ring-1 focus:ring-indigo-500"
              />
            </div>
            <div className="flex justify-end gap-2 mt-1">
              <button
                onClick={() => setSubsectionToAdd(null)}
                className="px-4 py-1.5 text-xs font-semibold text-stone-600 dark:text-stone-300 hover:text-stone-800 dark:hover:text-stone-100 hover:bg-stone-50 dark:hover:bg-stone-800 rounded-lg transition-colors border border-stone-200 dark:border-stone-700 cursor-pointer"
              >
                取消
              </button>
              <button
                disabled={!newSubSectionTitle.trim()}
                onClick={() => {
                  if (newSubSectionTitle.trim()) {
                    addTemplateSection(subsectionToAdd.index, newSubSectionTitle.trim(), subsectionToAdd.level);
                    setSubsectionToAdd(null);
                  }
                }}
                className="px-4 py-1.5 text-xs font-semibold text-white bg-indigo-600 hover:bg-indigo-700 active:scale-95 disabled:opacity-40 disabled:pointer-events-none rounded-lg transition-all shadow-sm cursor-pointer"
              >
                确认添加
              </button>
            </div>
          </div>
        </div>,
        document.body
      )}

    </div>
  );
}
