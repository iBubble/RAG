import React from 'react';
import { CheckCircle2, FileText, Sparkles, Clock } from 'lucide-react';

export interface FormCardItem {
  name: string;
  reason: string;
  required?: boolean;
  isFilled?: boolean;
  filledDocId?: string;
  updatedAt?: string;
}

interface PaperFormCardProps {
  item: FormCardItem;
  onClick: () => void;
}

export const PaperFormCard: React.FC<PaperFormCardProps> = ({ item, onClick }) => {
  return (
    <div
      onClick={onClick}
      className="group cursor-pointer flex flex-col items-center select-none w-48 shrink-0 relative transition-transform duration-200 hover:-translate-y-1.5"
    >
      {/* 模拟图二的精致 A4 纸张卡片 */}
      <div className="relative w-48 h-64 bg-white dark:bg-[#25272D] rounded-2xl border border-stone-200 dark:border-stone-700 shadow-md group-hover:shadow-2xl transition-all duration-300 p-4 flex flex-col justify-between overflow-hidden">
        
        {/* 顶部微型 Logo 与状态徽标 */}
        <div className="flex items-center justify-between border-b border-stone-100 dark:border-stone-800 pb-2">
          <div className="flex items-center gap-1">
            <span className="w-2 h-2 rounded-full bg-emerald-500 animate-pulse" />
            <span className="text-[10px] font-bold tracking-wider text-stone-400 dark:text-stone-500 uppercase">市监智审</span>
          </div>
          {item.isFilled ? (
            <span className="flex items-center gap-0.5 text-[10px] font-semibold text-emerald-600 dark:text-emerald-400 bg-emerald-50 dark:bg-emerald-950/40 px-1.5 py-0.5 rounded-full border border-emerald-200 dark:border-emerald-800">
              <CheckCircle2 className="w-2.5 h-2.5" /> 已填报
            </span>
          ) : (
            <span className="flex items-center gap-0.5 text-[10px] text-amber-600 dark:text-amber-400 bg-amber-50 dark:bg-amber-950/40 px-1.5 py-0.5 rounded-full border border-amber-200 dark:border-amber-800">
              <Clock className="w-2.5 h-2.5" /> 待填报
            </span>
          )}
        </div>

        {/* 纸张骨架视觉设计（仿图二排版纹理） */}
        <div className="my-auto space-y-2.5 py-2 px-1">
          {/* 抬头红头/主标题骨架 */}
          <div className="w-2/3 h-2 bg-stone-300 dark:bg-stone-600 rounded-full mx-auto" />
          <div className="w-1/2 h-1.5 bg-stone-200 dark:bg-stone-700 rounded-full mx-auto" />
          
          {/* 中部图二风格的黄金/主题色块与表格分割线条 */}
          <div className="grid grid-cols-3 gap-1.5 pt-2">
            <div className="col-span-2 space-y-1.5">
              <div className="w-full h-1 bg-stone-100 dark:bg-stone-800 rounded" />
              <div className="w-5/6 h-1 bg-stone-100 dark:bg-stone-800 rounded" />
              <div className="w-full h-1 bg-stone-100 dark:bg-stone-800 rounded" />
              <div className="w-4/5 h-1 bg-stone-100 dark:bg-stone-800 rounded" />
            </div>
            {/* 彩色提亮区块 */}
            <div className="h-12 bg-amber-100/70 dark:bg-amber-950/30 rounded-lg border border-amber-200/50 dark:border-amber-800/50 flex items-center justify-center p-1 text-center">
              <FileText className="w-4 h-4 text-amber-600 dark:text-amber-400 opacity-60 group-hover:scale-110 transition-transform" />
            </div>
          </div>

          {/* 底部段落骨架线条 */}
          <div className="space-y-1.5 pt-1">
            <div className="w-full h-1 bg-stone-100 dark:bg-stone-800 rounded" />
            <div className="w-11/12 h-1 bg-stone-100 dark:bg-stone-800 rounded" />
            <div className="w-3/4 h-1 bg-stone-100 dark:bg-stone-800 rounded" />
          </div>
        </div>

        {/* 纸张底部提示 */}
        <div className="border-t border-dashed border-stone-200 dark:border-stone-800 pt-2 flex items-center justify-between text-[9px] text-stone-400">
          <span>{item.required ? '法定必需文书' : '建议制作文书'}</span>
          <span className="flex items-center gap-0.5 text-indigo-500 group-hover:underline">
            <Sparkles className="w-2.5 h-2.5" /> 点击生成
          </span>
        </div>
      </div>

      {/* 卡片下方的中文大字标题（严格对齐图二） */}
      <div className="mt-3 text-center w-full px-1">
        <h4 className="font-bold text-sm text-stone-800 dark:text-stone-100 group-hover:text-indigo-600 dark:group-hover:text-indigo-400 transition-colors line-clamp-1">
          {item.name}
        </h4>
        <p className="text-[11px] text-stone-400 dark:text-stone-500 mt-0.5 line-clamp-2 leading-tight" title={item.reason}>
          {item.reason}
        </p>
      </div>
    </div>
  );
};
