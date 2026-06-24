import { useState } from 'react';
import { useProjectStore } from '../../store/projectStore';
import { useAuthStore } from '../../store/authStore';

const API_BASE = import.meta.env.VITE_API_BASE || '';

export default function useCaseAI(projectId: string) {
  const [isGenerating, setIsGenerating] = useState(false);
  const [outputHtml, setOutputHtml] = useState('');
  const checkedFileIds = useProjectStore(state => state.checkedFileIds);
  const selectedModel = useProjectStore(state => state.selectedModel);
  const { getAuthHeaders } = useAuthStore();

  const runTool = async (promptText: string, onToken: (t: string) => void) => {
    if (isGenerating) return;
    setIsGenerating(true);
    setOutputHtml('');
    
    try {
      const res = await fetch(`${API_BASE}/api/chat`, {
        method: 'POST',
        headers: { ...getAuthHeaders(), 'Content-Type': 'application/json' },
        body: JSON.stringify({
          message: promptText,
          file_ids: checkedFileIds,
          project_id: projectId,
          history: [],
          model: selectedModel,
          chat_mode: 'stateless',
          stateless: true,
        }),
      });

      if (!res.ok) throw new Error(`HTTP 异常: ${res.status}`);

      const reader = res.body?.getReader();
      const decoder = new TextDecoder();
      if (!reader) throw new Error('流式读取错误');

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
            if (data.token) {
              setOutputHtml(prev => {
                const next = prev + data.token;
                onToken(next);
                return next;
              });
            }
          } catch {}
        }
      }
    } catch (err: any) {
      setOutputHtml(`❌ 运行失败: ${err.message || '未知错误'}`);
    } finally {
      setIsGenerating(false);
    }
  };

  const generateOverview = async (onComplete: (text: string) => void) => {
    const prompt = `你是一个资深诉讼律师，请仔细阅读我已勾选的本案全部卷宗和证据材料。请提炼并自动生成一份精炼且切中要害的“案件概览”，涵盖：当事人基本情况、案由核心、主要事实争议及涉案金额。字数控制在 250 字左右，输出必须是纯文本，不要带有 Markdown 标记，符合专业起诉状或卷宗摘要的语言规范。`;
    let overviewText = '';
    await runTool(prompt, (current) => {
      // 剥离 markdown
      const clean = current
        .replace(/`{3}[\s\S]*?`{3}/g, '')
        .replace(/[#*`>_-]/g, '')
        .trim();
      overviewText = clean;
    });
    onComplete(overviewText);
  };

  return {
    isGenerating,
    outputHtml,
    runTool,
    generateOverview,
  };
}
