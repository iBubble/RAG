import React, { useState } from 'react';
import PleadingFlow from './PleadingFlow';
import ContractReview from './ContractReview';
import { Scale, FileText } from 'lucide-react';

export default function LegalWorkbench({ projectId, canWrite }) {
  const [activeTab, setActiveTab] = useState('workflow'); // 'workflow' | 'contract'

  return (
    <div className="h-full w-full bg-[#fcfbfa] flex flex-col overflow-hidden">
      {/* 顶部标题与技能切换 */}
      <div className="px-6 py-4 border-b border-[#e9e5de] bg-gradient-to-r from-stone-50 to-white flex items-center justify-between">
        <div>
          <h2 className="text-base font-bold text-stone-800 flex items-center gap-2">
            <Scale className="w-5 h-5 text-amber-700" />
            AI 法律专家工作台
          </h2>
          <p className="text-xs text-stone-500 mt-0.5">
            离线本地大模型与 RAG 双路混合检索增强，支持深度诉讼抗辩与合同合规性审查。
          </p>
        </div>

        {/* 技能 Tab 选项卡 */}
        <div className="flex bg-stone-100 p-1 rounded-xl border border-stone-200">
          <button
            onClick={() => setActiveTab('workflow')}
            className={`flex items-center gap-2 px-4 py-1.5 rounded-lg text-xs font-semibold transition-all ${
              activeTab === 'workflow'
                ? 'bg-white text-stone-800 shadow-sm'
                : 'text-stone-500 hover:text-stone-800'
            }`}
          >
            <Scale className="w-3.5 h-3.5" />
            文书起草工作流
          </button>
          <button
            onClick={() => setActiveTab('contract')}
            className={`flex items-center gap-2 px-4 py-1.5 rounded-lg text-xs font-semibold transition-all ${
              activeTab === 'contract'
                ? 'bg-white text-stone-800 shadow-sm'
                : 'text-stone-500 hover:text-stone-800'
            }`}
          >
            <FileText className="w-3.5 h-3.5" />
            合同一键审查
          </button>
        </div>
      </div>

      {/* 技能内容渲染区 */}
      <div className="flex-1 overflow-hidden">
        {activeTab === 'workflow' ? (
          <PleadingFlow projectId={projectId} canWrite={canWrite} />
        ) : (
          <ContractReview projectId={projectId} canWrite={canWrite} />
        )}
      </div>
    </div>
  );
}
