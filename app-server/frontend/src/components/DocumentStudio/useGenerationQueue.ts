/**
 * useGenerationQueue.ts — 批量生成调度 Hook
 *
 * WHY: 从 DocumentStudio.tsx 解耦出来。
 *      三种批量生成模式（一键生成、范文替换、精确复刻）共享同一套：
 *      - 中断信号（abortBatchRef）
 *      - Ref 等待重试机制（React 渲染周期对齐）
 *      - 错误捕获与 401 统一处理
 *      - 周期性中间保存
 *      集中到一个 Hook 中，消除重复代码并降低主组件复杂度。
 */
import { useState, useRef } from 'react';
import { useProjectStore } from '../../store/projectStore';
import type { DocSection, SectionBlockHandle } from './types';

interface UseGenerationQueueOptions {
  sections: DocSection[];
  canWrite: boolean;
  sectionRefs: React.MutableRefObject<Record<string, SectionBlockHandle>>;
  abortControllerRef: React.MutableRefObject<AbortController | null>;
  performSave: (isAuto: boolean) => Promise<any>;
  showToast: (message: string, type: 'success' | 'warning' | 'error') => void;
  // WHY: 虚拟化编辑器架构下，同时只有 1 个 SectionBlock 挂载。
  //      批量生成前必须先激活目标章节，让 SectionBlock mount 并注册 ref。
  activateSection: (sectionId: string) => void;
}

/** 等待 SectionBlock ref 挂载（最多 10 × 200ms = 2s）
 *  WHY: 虚拟化架构下 SectionBlock 从 unmount → mount → Tiptap 初始化
 *       需要约 500ms~1s，增大重试次数确保 ref 可用。
 */
async function waitForRef(
  sectionRefs: React.MutableRefObject<Record<string, SectionBlockHandle>>,
  sectionId: string
): Promise<SectionBlockHandle | null> {
  let ref = sectionRefs.current[sectionId];
  if (ref) return ref;
  for (let retry = 0; retry < 10 && !ref; retry++) {
    await new Promise(r => setTimeout(r, 200));
    ref = sectionRefs.current[sectionId];
  }
  return ref || null;
}

export default function useGenerationQueue({
  sections,
  canWrite,
  sectionRefs,
  abortControllerRef,
  performSave,
  showToast,
  activateSection,
}: UseGenerationQueueOptions) {
  const [isGeneratingAll, setIsGeneratingAll] = useState(false);
  const [isReplacingAll, setIsReplacingAll] = useState(false);
  const [isCloningAll, setIsCloningAll] = useState(false);

  // WHY: 用 ref 而非 state 做中断信号，因为 async 循环中 state 读不到最新值
  const abortBatchRef = useRef(false);
  // WHY: 用 ref 记录"当前正在处理的一级目录标题"，在跨越一级目录边界时触发保存
  const currentTopSectionTitleRef = useRef<string | null>(null);

  const handleStopBatch = () => {
    abortBatchRef.current = true;
    // WHY: 立即中断当前正在进行的 SSE 流，而不是等它自然结束
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      abortControllerRef.current = null;
    }
  };

  // ─── 一键生成全文 ───
  const handleGenerateAll = async () => {
    if (isGeneratingAll || sections.length === 0) return;
    setIsGeneratingAll(true);
    abortBatchRef.current = false;
    currentTopSectionTitleRef.current = null;

    try {
      // WHY: 在循环开始时冻结一份章节 ID 列表。
      //      内容判断则实时从 store 读取，避免闭包捕获过期快照。
      const sectionIds = sections.map((s: DocSection) => s.id);

      for (const sectionId of sectionIds) {
        if (abortBatchRef.current) break;

        // WHY: 实时从 store 读取该章节的最新内容，而非使用循环开始时的旧快照。
        const latestSections = useProjectStore.getState().templateSections;
        const latestSection = latestSections.find((s: DocSection) => s.id === sectionId);
        if (!latestSection) continue;

        // WHY: 当遇到新的一级目录（level=1）时，说明上一个一级目录已全部完成。
        //      此时触发一次保存，而后更新当前追踪的一级目录标题。
        if (latestSection.level === 1) {
          if (currentTopSectionTitleRef.current !== null && canWrite) {
            try {
              await performSave(true);
              console.log(`[BatchSave] 一级目录「${currentTopSectionTitleRef.current}」生成完毕，已保存`);
            } catch (saveErr) {
              console.warn('[BatchSave] 一级目录保存失败，继续生成', saveErr);
            }
          }
          currentTopSectionTitleRef.current = latestSection.title;
        }

        // WHY: 过滤 HTML 标签后，还要排除 think 占位文字和纯空白
        const cleanText = (latestSection.content || '')
          .replace(/<[^>]*>?/gm, '')
          .replace(/💭.*推演中.*/g, '')
          .replace(/AI.*等待.*/g, '')
          .trim();
        if (cleanText.length > 5) continue; // 跳过已有内容的章节

        // WHY: 虚拟化架构——先激活目标章节让 SectionBlock mount，再等待 ref 注册
        activateSection(sectionId);
        const ref = await waitForRef(sectionRefs, sectionId);
        if (ref) {
          await ref.generate();
          // WHY: 给 React 多个渲染周期来稳定 DOM 和 ref 注册（500ms 间隔）
          await new Promise(r => setTimeout(r, 500));
        } else {
          console.warn(`[GenerateAll] 章节 ${sectionId}（${latestSection.title}）的编辑器 ref 未挂载，跳过`);
        }
      }
    } catch (err: any) {
      if (err.message === '401_UNAUTHORIZED') {
        abortBatchRef.current = true;
        showToast('登录凭证已过期失效，请刷新页面或重新登录', 'error');
      }
    } finally {
      // WHY: 生成结束（无论完成还是中断），为最后一个一级目录做最终保存
      try {
        if (sections.length > 0 && canWrite) {
          await performSave(true);
          const lastTitle = currentTopSectionTitleRef.current;
          console.log(`[BatchSave] 批量生成结束${lastTitle ? `，最后一级目录「${lastTitle}」` : ''}，最终保存完成`);
        }
      } catch (e) {
        console.warn('[BatchSave] 最终保存失败', e);
      }
      currentTopSectionTitleRef.current = null;
      abortBatchRef.current = false;
      setIsGeneratingAll(false);
    }
  };

  // ─── 范文智能替换 ───
  const handleReplaceAll = async () => {
    const hasExemplar = (useProjectStore.getState().exemplarSections || []).length > 0;
    if (isReplacingAll || sections.length === 0 || !hasExemplar) return;
    setIsReplacingAll(true);
    abortBatchRef.current = false;
    currentTopSectionTitleRef.current = null;

    let generatedCount = 0;
    let skippedCount = 0;

    try {
      const sectionIds = sections.map((s: DocSection) => s.id);
      for (const sectionId of sectionIds) {
        if (abortBatchRef.current) break;

        // WHY: 实时从 store 读取最新内容，在 L1 边界触发保存
        const latestSections = useProjectStore.getState().templateSections;
        const latestSection = latestSections.find((s: DocSection) => s.id === sectionId);
        if (!latestSection) continue;

        // WHY: 遇到 L1 级章节边界时保存进度，与 handleGenerateAll 行为一致
        if (latestSection.level === 1) {
          if (currentTopSectionTitleRef.current !== null && canWrite) {
            try {
              await performSave(true);
              console.log(`[ReplaceBatch] L1「${currentTopSectionTitleRef.current}」已完成，保存进度`);
            } catch (saveErr) {
              console.warn('[ReplaceBatch] 保存失败，继续生成', saveErr);
            }
          }
          currentTopSectionTitleRef.current = latestSection.title;
        }

        // WHY: 虚拟化架构——先激活目标章节
        activateSection(sectionId);
        const ref = await waitForRef(sectionRefs, sectionId);
        if (ref) {
          await ref.generate('replace');
          // WHY: 给 React 渲染周期时间更新 DOM，再检查生成结果
          await new Promise(r => setTimeout(r, 200));

          // 检查替换是否实际产生了内容
          const updatedSections = useProjectStore.getState().templateSections;
          const updated = updatedSections.find((s: DocSection) => s.id === sectionId);
          const cleanText = (updated?.content || '')
            .replace(/<[^>]*>?/gm, '').trim();
          if (cleanText.length > 5) {
            generatedCount++;
          } else {
            skippedCount++;
          }
        } else {
          skippedCount++;
        }
      }
    } catch (err: any) {
      if (err.message === '401_UNAUTHORIZED') {
        abortBatchRef.current = true;
        showToast('登录凭证已过期失效，请刷新页面或重新登录', 'error');
      }
    } finally {
      // 最终保存
      try {
        if (sections.length > 0 && canWrite) await performSave(true);
      } catch (e) {
        console.warn('[ReplaceBatch] 最终保存失败', e);
      }

      const msg = skippedCount > 0
        ? `范文智能替换完成：成功 ${generatedCount} 节，跳过 ${skippedCount} 节`
        : `范文智能替换完成：成功生成 ${generatedCount} 节`;
      showToast(msg, generatedCount > 0 ? 'success' : 'warning');

      currentTopSectionTitleRef.current = null;
      abortBatchRef.current = false;
      setIsReplacingAll(false);
    }
  };

  // ─── 范文精确复刻 ───
  const handleCloneAll = async () => {
    const storeState = useProjectStore.getState();
    const exemplarSections = storeState.exemplarSections || [];
    const exemplarTitle = storeState.exemplarTitle || '';
    const templateTitle = storeState.templateTitle || '';
    const hasExemplar = exemplarSections.length > 0;

    if (isCloningAll || !hasExemplar) return;
    setIsCloningAll(true);
    abortBatchRef.current = false;

    try {
      // 用范文的 sections 覆盖当前大纲
      const { setTemplateData } = useProjectStore.getState();
      const clonedSections = exemplarSections.map((es: any, idx: number) => ({
        id: `clone-${Date.now()}-${idx}`,
        title: es.title,
        level: es.level || 1,
        content: '',
      }));
      setTemplateData(templateTitle || exemplarTitle || '范文复刻', clonedSections);

      // 等一帧让 React 渲染新 sections
      await new Promise(r => setTimeout(r, 300));

      // Step 2: 逐章节用 clone 模式生成
      const latestSections = useProjectStore.getState().templateSections;
      const cloneIds = latestSections.map((s: DocSection) => s.id);
      for (const sectionId of cloneIds) {
        if (abortBatchRef.current) break;
        // WHY: 虚拟化架构——先激活目标章节
        activateSection(sectionId);
        const ref = await waitForRef(sectionRefs, sectionId);
        if (ref) {
          await ref.generate('clone');
          await new Promise(r => setTimeout(r, 100));
        }
      }
    } catch (err: any) {
      if (err.message === '401_UNAUTHORIZED') {
        abortBatchRef.current = true;
        showToast('登录凭证已过期失效，请刷新页面或重新登录', 'error');
      }
    } finally {
      abortBatchRef.current = false;
      setIsCloningAll(false);
    }
  };

  return {
    isGeneratingAll,
    isReplacingAll,
    isCloningAll,
    handleGenerateAll,
    handleReplaceAll,
    handleCloneAll,
    handleStopBatch,
  };
}
