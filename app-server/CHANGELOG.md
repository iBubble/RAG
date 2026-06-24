# 变更日志 (CHANGELOG)

本项目记录所有的架构级调整、重大功能新增与关键修复。
记录原则：按日期倒序排列，单日内按重要性先后排列。

## [2026-06-09]
### 🌟 核心特性升级 (Critical Features)
- **Go+Python 高性能有向图编排改造收官 (Go Eino & Python Microservice)**
  - [后端] 彻底废弃 NATS 消息总线订阅模式，由 Go 侧网关直接基于字节跳动 Eino 强类型引擎构建 Agent 有向图状态流转（Supervisor -> Contrarian -> Arbiter），直接接管 `/api/chat` SSE 流式输出。
  - [后端] 将 Python 侧算法组件化剥离为 HTTP 微服务接口（`/api/internal/rag` 向量检索微服务，与 `/api/internal/docx/annotate` Word 留痕微服务），实现业务与算法解耦，消除 Python 进程死锁隐患并极大优化 TTFT 首字时延。
- **前端多模态文件图标与预览优化**
  - [前端] 改造 [TreeView.tsx](file:///Users/gemini/Projects/Own/RAG/app-server/frontend/src/components/TreeView/TreeView.tsx) 与 [FileUploader.tsx](file:///Users/gemini/Projects/Own/RAG/app-server/frontend/src/components/FileUploader/FileUploader.tsx) 中的文件图标渲染逻辑，根据后缀动态匹配音频（`.mp3`/`.wav`/`.m4a` -> `Volume2`）和视频（`.mp4`/`.mov`/`.webm`/`.ogg` -> `Video`）图标。
  - [前端] 在 [FilePreviewer.tsx](file:///Users/gemini/Projects/Own/RAG/app-server/frontend/src/components/FilePreviewer/FilePreviewer.tsx) 中扩充 `VIDEO_FORMATS` 以支持 `.mov` 视频格式的原生播放器预览。
  - [工程] 物理核对并补全 `steps.md` 部署任务清单的进度标志。

## [2026-06-04]
### 🌟 核心特性升级 (Critical Features)
- **一键顺序生成所有步骤功能 (One-Click Auto Pipeline)**
  - [前端] 在 `PleadingFlow.jsx` 中，于顶部横向步骤 Tab 栏最右侧新增了“⚡ 一键生成所有步骤”按钮。
  - [前端] 点击后，系统自动清空之前所有步骤的输出以保持生成的独立性和纯净性。随后通过异步任务链（`runAutoPipeline` 逻辑）顺序控制各步骤组件挂载与 API 推理调用，逐个执行每一步的 AI 推理生成并自动切换步骤，直至最后一步的文档全部推理编写完成。
  - [前端] 增加了流水线级别的锁定机制。在一键生成运行期间，强制锁定所有步骤导航按钮、单个生成按钮以及保存按钮以防重入冲突；在任意步骤生成出错时自动中断并抛出友好告警。
- **多模块归档保存功能 (Document Archiving)**
  - [前端] 在 `PleadingFlow.jsx` 中，对“民事起诉状”、“民事答辩状”、“法律意见书”、“委托前案件分析”、“案例检索分析”等所有基于工作流的技能模块，在其最后一步的内容区域上方增加了“保存”按钮。
  - [前端] 点击后通过 `window.prompt` 智能引导用户自定义文档标题，并向后端 `/api/projects/{id}/documents` 发送 `POST` 请求以对生成的文书内容进行物理归档保存。
  - [前端] 保存成功后自动向全局分发 `documentSaved` 自定义事件，无缝驱动右侧 `SavedDocumentsList` 文件列表组件实时更新渲染。

### 🛠 修复与微调 (Fixes & Tweaks)
- **工作流组件重用竞态与脏缓存过滤优化**
  - [前端] 在 `App.tsx` 中为 `<PleadingFlow />` 组件显式绑定唯一的 `key` 属性（结合 `projectId` 与 `skillType`）。在用户切换不同的文书技能 Tab 时强制卸载并重新创建组件实例，彻底消除了由组件重用导致的 state 错乱、未完成 fetch 异步数据写入污染以及 `useEffect` 在渲染帧之间的竞态条件。
  - [前端] 在 `PleadingFlow.jsx` 中重构状态读取机制，引入本地缓存清洗函数 `cleanCachedOutputs`。在从 `localStorage` 加载缓存数据时，自动过滤清洗掉不属于当前技能的脏键，并主动抹除包含 `❌ 发生错误` 标识的历史失败数据，确保页面刷新或切换后不会呈现历史残留的错误内容。
- **文书起草工作流步骤锁定逻辑重构**
  - [前端] 在 `PleadingFlow.jsx` 中引入 `useRef` 声明同步生成状态锁 `isGeneratingRef`。在点击切换步骤的 `onClick` 和 `disabled` 属性中实施同步拦截，消除由于 React 状态更新延迟导致的竞态切换。
  - [前端] 优化解锁判定逻辑，新增统一的 `isStageCompleted` 辅助函数。只有当前一步完全生成成功（即内容非空，且不包含错误提示 `❌ 发生错误`，且没有在生成中）时，下一步骤才被判定为解锁（`isUnlocked`）。彻底解决了“步骤2在AI推理中，或者推理出错后，步骤3依然可以点击”的逻辑漏洞。

## [2026-04-05] (下午追加)
### 🌟 核心特性升级 (Critical Features)
- **LLM 上下文窗口解锁 (num_ctx 8K → 32K)**
  - [后端] 在 `stream_ollama()` 中显式注入 `num_ctx: 32768`，充分利用 M4 Max 64GB 统一内存。此前 Ollama 默认仅 8K 窗口，导致 RAG 检索结果被静默截断，大模型实际上只看到了部分参考资料。
- **全局项目元数据注入 (Global Project Context)**
  - [后端] 新增 `_get_global_project_context()` 函数，在生成每个章节时用宽泛数据关键词（面积/价格/统计/区片/地价等）做二次 RAG 检索，确保 Excel 中的核心量化指标（地价、面积、变化幅度等）始终出现在 LLM 上下文中，解决"章节标题语义检索盲区"导致表格数据全部填 `[待补充]` 的问题。

### 🛠 修复与微调 (Fixes & Tweaks)
- **范文替换 Prompt 柔性化**
  - [后端] 重写 `REPLACE_PROMPT` 和 `DUAL_TRACK_PROMPT`，增加"结构严格保持"约束：范文没有表格不得擅自添加、段落数量必须对齐、可视化标记仅在范文已有数据表格时才允许插入。解决了 AI "过度热心"自行扩写大量内容和表格的问题。
- **DWG 预览 dwg2dxf 容错增强**
  - [后端] 修改 `dwg2dxf` 错误判断逻辑，从依赖退出码改为检查输出文件是否存在且体积非零。解决了部分复杂 DWG 因 HATCH 警告导致 exit code 非零但实际已成功转换的误判问题。
- **大图纸 PNG 回退渲染**
  - [后端] 当 SVG 输出超过 5MB 时，自动回退 Matplotlib 生成高分辨率 PNG（0.6MB vs 63MB SVG），防止浏览器因巨量 DOM 节点卡死。
  - [前端] CadViewer 同步支持 SVG/PNG 双格式响应，底部显示"栅格模式"标记。

## [2026-04-05]
### 🌟 核心特性升级 (Critical Features)
- **AI 项目人格物理隔离机制 (Persona Isolation)** 
  - [前端] 在“项目信息”页（`ProjectInfo.tsx`）新增 “项目专属 AI Agent 角色定义” 文本框。
  - [后端] 重构系统提示词逻辑（`generate.py`），使每个项目拥有相互独立、互不干扰的 AI 角色设定（自动写入工程元数据的 `aiPersona` 字段）。
- **多维度对话模式 (Multi-Mode AI Chat UI)** 
  - [前端] 于对话框输入栏正上方重构了4个情境按钮：**⚡快速**、**🧠深度思考**、**👷工程专家**、**🤖通用AI**。
  - [后端] 彻底移除原有的死板 `fast_mode` 开关，引入灵活的 `chat_mode` 参数流传机制。

### 🚀 优化与扩展 (Enhancements)
- **大模型响应约束强化** 
  - [后端] 针对 `fast` (快速) 与 `general` (通用AI) 模式注入了严格指令，在流式输出层（`core.think_filter`）彻底屏蔽并压制大模型的英文推演或内部 `<think>` 标签输出。
  - [后端] 结合自定义 Persona 与具体 Mode，动态向大模型注入“极其严谨的工程师”等隐性系统词缀。

### 🛠 修复与微调 (Fixes & Tweaks)
- **DWG 矢量图纸预览修复**
  - [后端] 排查并定位了 `dwg2dxf` 导致部分核心图层默认为“关闭/冻结”状态的问题，在 DXF 解析引擎前暴力启用及解冻所有图层。
  - [后端] 摒弃了因未自适应坐标轴与内存暴涨而导致出现空白画面的 `MatplotlibBackend` 渲染器，替换为 `ezdxf` 原生的 `SVGBackend` 引擎。大幅度提升了 10~100MB 级别巨型 CAD DWG 文件在浏览器内的渲染速度与稳定性。
- **开机引导协议注入 (Boot Protocol)** 
  - [工程环境] 在 `README.md` 的指令设定中加入了强约束机制，确保系统重置后，助手在首次对话时会自动追溯 `CHANGELOG.md` 和微状态存档日志（`work_status.md`），以继承历史开发上下文。
- **UI/UX 改进**：修复了原先将聊天模式切换器误置于顶部导致不符合直觉的问题，将其下放至最底部的输入区组件（`AgentChat.tsx`）内。
- **Logo 展示路径**：核校了顶部项目展示及登录接口的图片引用方式，使其正确映射至 `public/logo.png`。
