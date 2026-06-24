/**
 * DocumentStudio 共享类型定义
 */

export interface DocSection {
  id: string;
  title: string;
  level: number;
  content: string;
  sources?: string[];
}

/** SectionBlock 通过 ref 暴露给父组件的操作方法 */
export interface SectionBlockHandle {
  generate: (mode?: string) => Promise<void>;
  clear: () => void;
  /** WHY: 预计算缓存填充 — 直接设置编辑器内容，不走 LLM 流式生成 */
  fillContent: (html: string, sources?: string[]) => void;
}
