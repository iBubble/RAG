# 开发工作记录 (Work Record)

- **日期**：2026-06-25
- **修改目的**：简化工作台 Tab 导航、引入全新的 AI表格 UI 模块并进行深色模式与宽度排版优化，并在前后端彻底替换“卷宗”/“案件”为“项目”/“资料”以完成通用化去法律化重构。

---

## 修改文件明细

### 1. 前端 Tab 重构与 UI 集成

#### [App.tsx](file:///Users/gemini/Projects/Own/RAG/app-server/frontend/src/App.tsx)
- 导入 `AITablePanel` 组件，从 `lucide-react` 引入 `Table` 图标。
- 精简 `TAB_ITEMS` 变量，移除了 4 个旧 Tab（“知识工作台”、“项目管理”、“顾问服务”、“文档审查”），在“智能助手”和“定制文档”间挂载“AI表格”。
- 清理 `App.tsx` 顶部的无用组件导入及 `LEGAL_SUB_TABS` 常量、`activeLegalSubTab` 状态以防止 unused 编译报错。
- 侧边栏按钮由 `+ 上传案件文件/卷宗` 变更为 `+ 上传项目文件/资料`。

#### [AITablePanel.tsx](file:///Users/gemini/Projects/Own/RAG/app-server/frontend/src/components/AITable/AITablePanel.tsx)
- 增加了 Tailwind `dark:` 类名前缀，解决其在深色主题下对比度缺失、选择器白屏和文档编辑区字体不可见的问题。
- 移除了编辑框 `textarea` 上的 `prose` 和 `prose-sm` 类名限制（其自带的 `max-width: 65ch` 导致了窗口只占屏幕一半的缺陷），使其能横向自适应占满整个编辑区。

### 2. 前端“去卷宗化”替换

#### [FileUploader.tsx](file:///Users/gemini/Projects/Own/RAG/app-server/frontend/src/components/FileUploader/FileUploader.tsx)
- 拖拽提示语中由“任意卷宗目录” $\rightarrow$ “任意项目目录”；
- 文件夹上传按钮由“📁 按目录层级上传卷宗目录” $\rightarrow$ “📁 按目录层级上传项目目录”。

#### [CaseManagement.tsx](file:///Users/gemini/Projects/Own/RAG/app-server/frontend/src/components/CaseManagement/CaseManagement.tsx)
- 警示弹窗中由“在左侧树状卷宗中勾选” $\rightarrow$ “在左侧树状目录中勾选”。

#### [caseData.ts](file:///Users/gemini/Projects/Own/RAG/app-server/frontend/src/components/CaseManagement/caseData.ts)
- 更新质证框架、评估报告等工具提示和 Prompt 常量，移除所有涉及“卷宗事实”和“本案卷宗”的法律描述，采用通用的项目管理/项目文档词汇。

#### [useCaseAI.ts](file:///Users/gemini/Projects/Own/RAG/app-server/frontend/src/components/CaseManagement/useCaseAI.ts)
- 重构自动生成概览的内置 Prompt 文本，替换“诉讼律师/案件卷宗”为“分析专家/项目材料”，案由及争议更改为项目核心与关键财务数据。

### 3. 后端“去卷宗化”替换

#### [projects.py](file:///Users/gemini/Projects/Own/RAG/app-server/backend/api/projects.py)
- 更新心跳日志的任务状态库，将 `low` 任务中的“审阅案件卷宗”修改为“审阅项目资料”。

#### [legal_assistant.py](file:///Users/gemini/Projects/Own/RAG/app-server/backend/core/legal_assistant.py)
- 将 RAG 检索失败的兜底文本修改为“暂无参考法规/项目文本”。
- 替换流式事件输出中的天平（⚖️）图标为编辑笔记本（📝），日志输出修改为“结合项目事实进行起草与推理”。

---

## 构建与测试验证
- **本地编译**：在 `app-server/frontend` 下运行 `npm run build` 成功完成，无报错。
- **外观测试**：利用子智能体在浏览器上确认深色模式下 AI 表格面板全部自适应填充，联动二级菜单工作正常，编辑框实现全宽占满；上传模块中的所有“卷宗”字样已顺利更名为“项目”。
