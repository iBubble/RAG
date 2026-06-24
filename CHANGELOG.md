# Changelog

All notable changes to this project will be documented in this file.

## [3.6.0] - 2026-06-25

### Changed
- **全面去法律化与通用 RAG 平台重塑**：
  - 将系统名称从“貔貅法律知识库 (LawRAG)”全面改造为“力诺通用知识库 RAG (LinuoRAG)”。
  - 重塑多阶段工作流，将特化法律文书（起诉状、答辩状、合同审查、意见书、收案评估）转化为通用的文书起草、文档审阅、可行性方案、项目评估等企业顾问工作流。
  - 重命名并泛化系统默认 Agent 角色名（如“小貔 (Pixiu)” -> “小诺 (Linuo)”，“法律服务专家” -> “文档审查专家”）。
- **LOGO 与品牌形象重新设计**：
  - 生成并物理覆盖了科技美学的新版 Logo 及 Favicon 文件（包含 [logo.png](file:///Users/gemini/Projects/Own/RAG/app-server/frontend/public/logo.png)、[favicon.png](file:///Users/gemini/Projects/Own/RAG/app-server/frontend/public/favicon.png)）。

## [3.5.2] - 2026-06-11

### Changed
- **智能助手模式精炼与默认行为优化**：
  - 缩减智能助手（[AgentChat.tsx](file:///Users/gemini/Projects/Own/RAG/app-server/frontend/src/components/AgentChat/AgentChat.tsx)）的模式选项，仅保留“快速”和“协同”两种模式，移除“独立”、“深度”、“专家”、“通用”模式.
  - 将智能助手的默认初始化模式由“独立”模式变更为“快速”模式（`fast`），若启用协同聊天配置则自适应调整为“协同”模式（`smart`）。

### Fixed
- **解决已存对话片段在页面刷新/热更新时被覆盖清空的 Bug**：
  - 原因定位：前端底层使用基于 `idb-keyval` 的异步 IndexedDB 存储（`idbStorage`）。由于 `getItem` 是异步加载，当页面刚加载且数据尚未水合完毕时，若其他组件提早触发了 `set` 操作，会导致 zustand 将内存中的初始空状态 `[]` 错误地持久化写入 IndexedDB，将之前的存量片段覆盖抹除。另外，`addChatSnippet` 和 `removeChatSnippet` 中包含与 zustand persist 重合的手动 `idbGet`/`idbSet` 写入操作，引发时序冲突。
  - 修复方案：在 `idbStorage` 中引入 `hasLoaded` 拦截记录，保证在 `getItem` 异步完成水合前拒绝任何 `setItem` 写入，彻底阻断空状态覆盖；同时将 `addChatSnippet` 和 `removeChatSnippet` 精简重构为符合 Zustand 规范的单向状态流修改，统一交由底层 Persist 拦截器自动持久化。

### Added
- **新增“案件管理”工作流 Tab 模块**：
  - 新建一等 Tab 页面 [CaseManagement.tsx](file:///Users/gemini/Projects/Own/RAG/app-server/frontend/src/components/CaseManagement/CaseManagement.tsx)，整合了办案流程。
  - 左侧提供 AI 自动提炼并可直接编辑的案件概览（内容展示与编辑文本框的高度已整体调高 50% 以优化长文本的录入与阅读体验）、以及五大标准流程阶段（收案评估、诉前准备、立案庭前、一审开庭、结案执行），阶段进度状态支持“进行中/已完成/待启动”下拉切换，直接与 Project Metadata 持久化同步。
  - 右侧为阶段目标及 AI 智能工具箱（支持证据清单梳理、起诉大纲编写、沙盘模拟对抗等），文书流式生成后可一键“保存为案件文档”归档至本案素材库中。
- **定制文档增加自定义指令输入框并优化布局**：
  - 在大纲画布顶部新增自定义要求输入区，绑定 `customInstruction` state。
  - 将该输入框独立提到白色 A4 文档纸外侧的正上方，整体上移贴顶（Padding 调整为 pt-2），消除多余空白。
  - 去除双重外框及长引导占位符，限制为 2 行高度，使用轻量化扁平卡片（bg-[#fcfbf9] dark:bg-[#1a1b1e]）自适应切换浅色/深色主题。
  - 单章节生成和批量生成时，均向 `/api/generate/paragraph` 接口传递该自定义要求，后端将用户指令追加在 Prompt 末尾作为 `【⚠️ 强制用户自定义要求约束】`。
- **两侧卷宗栏与素材库栏支持对称平滑折叠**：
  - 在左侧卷宗栏与右侧素材库均引入了平滑侧向收起/展开功能，结合 CSS width、opacity、margins 的 transition 动画效果实现优雅过渡。
  - 采用了完全镜像对称的半圆形悬浮按钮设计（展开状态下悬浮在各自的分界线垂直中间，点击折叠；折叠后在中栏的左右两边缘绝对定位展现对应的展开按钮），方便灵活调节工作区可视空间。

## [3.5.1] - 2026-06-10

### Fixed
- **解决自动保存关闭下依然产生冗余归档文档的 Bug**：
  - 在 [DocumentStudio.tsx](file:///Users/gemini/Projects/Own/RAG/app-server/frontend/src/components/DocumentStudio/DocumentStudio.tsx) 中重构了 `performSave` 逻辑。当自动保存开关（`autoSaveEnabled`）为关闭状态且属于程序自动触发保存（`isAuto === true`）时，仅将当前的标题与大纲状态静默同步至后端主草稿模板（`/template`）以防内容丢失，不再向历史归档文档接口（`/documents`）发送数据，彻底杜绝了右侧列表无故产生带有黄色“自动保存”角标的临时多余历史文件的现象。
  - 物理清理了由于旧逻辑漏洞产生的包含“民事起诉状”在内的多余历史归档数据。

## [3.5.0] - 2026-06-09


### Added
- **前端多模态文件列表图标动态适配**：
  - 在 [TreeView.tsx](file:///Users/gemini/Projects/Own/RAG/app-server/frontend/src/components/TreeView/TreeView.tsx) 的文件列表和 [FileUploader.tsx](file:///Users/gemini/Projects/Own/RAG/app-server/frontend/src/components/FileUploader/FileUploader.tsx) 的排队列表中添加了依据文件后缀的自适应图标渲染机制。
  - 自动将音频文件（`.mp3`, `.wav`, `.m4a`）映射为 `Volume2` 图标，视频文件（`.mp4`, `.mov`, `.webm`, `.ogg`）映射为 `Video` 图标，改善一律使用文本图标所带来的体验不连贯问题。
- **拓展视频预览支持**：
  - 在 [FilePreviewer.tsx](file:///Users/gemini/Projects/Own/RAG/app-server/frontend/src/components/FilePreviewer/FilePreviewer.tsx) 的 `VIDEO_FORMATS` 中添加对 `.mov` 视频格式的直接预览支持，使得案发现场监控录像、行车记录仪等 `.mov` 文件可以直接通过前端原生播放器预览与播放。

### Changed
- **系统重构与底座奠基收官**：
  - 实现 Go 端 Eino 强类型有向图（Supervisor -> Contrarian -> Arbiter）的拓扑编排，Go 侧网关接管 `/api/chat` 流式 SSE。
  - 完成 Python 端核心算法的微服务挂载（RAG 检索微服务与 Word XML 留痕微服务），废弃 NATS 总线消息机制。
  - 完成 `steps.md` 部署任务清单的进度的更新归档，全站 5 大任务全数完成并打勾通过。

## [3.4.2] - 2026-06-09

### Fixed
- **解决多文件/跨项目任务干扰导致图谱社区摘要永久卡死（烂尾）的 Bug**：
  - **退避条件精细化**：优化了 [community_summarizer.py](file:///Users/gemini/Projects/Own/RAG/app-server/backend/core/community_summarizer.py) 中的自调度退避逻辑，不再单一依赖全局 `slow_queue` 队列长度，而是结合项目自身的提取完成状态进行智能判定。即便当前有其他项目的图谱任务正在排队，若本项目所有文件均已提取完毕，则绝不让出算力中断，而是持续自我调度接力，直到把当前项目的所有社区摘要生成完毕，从根本上消除了任务在中途退出后由于没有新触发源导致永久卡在中间进度的顽疾。
  - **后台服务重启与触发**：在 PM2 容器内重启慢队列服务 `shengyao-celery-slow` 以应用最新逻辑，并手动拉起恢复了受影响卡死项目（“国内法律”与“国内行政法规”）的进度生成。

## [3.4.1] - 2026-06-08

### Added
- **智能助手对话时间记录与呈现**：
  - 在前端状态存储层 `projectStore.ts` 的 `Message` 接口中添加了可选的 `timestamp?: number` 属性，并在发送和接收消息时自动抓取当前系统毫秒时间戳进行持久化存储。
  - 在 `AgentChat.tsx` 中编写了高抗错的 `formatMessageTime` 时间戳格式化辅助函数，能有效兜底并使用存量数字消息 ID 还原对话时间，同时自动隐藏系统欢迎语等无效时间。
  - 为用户对话气泡引入了外层垂直 flex 布局，在气泡右下方居右显示发送时间，并结合头像和间隙宽度（`mr-11`）进行完美偏移对齐，提升交互质感。
  - 在助手对话气泡的底部统计面板中，在生成速度（字符/s）后方无缝追加展示对话的具体产生时间。

### Fixed
- **解决协同模式大模型死锁导致“系统编排异常”故障**：
  - **指数退避重试**：重构了 `ollama_chat.py` 中的 `ollama_chat` 与 `ollama_chat_stream`，为 Ollama 的 `/api/chat` API 请求和流式通信建立引入了 `max_retries=3` 并实现了指数退避（1s, 2s, 4s）重试机制。有效避免了模型在首次加载或显存切换发生延迟时，直接因 `ReadTimeout` 造成整个协同会话中断崩溃的问题。
  - **显存占用优化**：将请求载荷中的 `"keep_alive": -1` 统一调整为自释放生命周期的 `"5m"`。防止了多个不同尺寸的大模型（如 8B、35B MoE）因无限锁死在 VRAM 中导致显存被彻底榨干而引发 llama-server 冻结死锁，提升了本地机器的并发弹性和资源鲁棒性。
- **解决色彩模式切换菜单穿透遮挡缺陷**：将 `App.tsx` 中的 `ThemeSwitcher` 下拉菜单背景改为完全自适应非透光背景（浅色模式白底，深色模式曜石黑底）并设置 `opacity: 1` 强制不透明；同时将外层父容器 `<header>` 设置为相对定位（`relative`）并将层级由 `z-10` 提升至 `z-30`。这确保了在 CSS 渲染中建立正确的层叠上下文，彻底阻断了由于内容区 `relative` 子元素（如智能助手顶栏的“配置/已存/清空”按钮）产生的叠放层级反置，从根源上治愈了下拉菜单被下层内容遮挡、穿透的问题。

## [3.4.0] - 2026-06-08

### Added
- 全局 UI 色彩模式管理：实现 `themeStore.ts` 用来管理浅色、深色、跟随系统模式的响应式更新。
- 引入 NotebookLM 风格的高清淡彩/深彩卡片配色矩阵（粉、黄、蓝、绿、紫），适配二级子 Tab。
- 实现高仿真 NotebookLM 的“设置”一级悬浮下拉菜单，提供“浅色模式”、“深色模式”、“设备模式”三项，且图标和文字根据当前选择模式动态改变。
- 挂载主页支持：在 HomePage.tsx 顶部栏中同样引入并渲染了设置菜单，确保在系统所有主要视图（首页与各案件工作台）下主题切换器均表现完美。

### Changed
- 优化主题切换器：将 `ThemeSwitcher` 胶囊按钮改造为纯图标圆形按钮，按钮图标动态展示当前选择的模式，提升极简质感。
- 修复色彩模式自适应问题：移除了按钮图标中硬编码的 `text-stone-500` 类，支持在深色和浅色模式下继承前景色，改善暗色状态下的辨识度。
- 重构全局样式 `index.css`，定义所有核心配色变量，并通过非侵入式深色模式代理实现了对既有大面积 `.bg-white`、`.text-gray-800` 等类名的自动兼容与优雅变色。
- 适配 Linvis 3D 看板样式，使大地板、各区域地毯以及 3D 悬浮粘土卡片完美适配深色模式，呈现夜间协同科技质感。

### Fixed
- **解决 Tailwind v4 切换失效问题**：在 `index.css` 声明自定义 `@variant dark` 适配属性选择器 `[data-mode="dark"]`，解决非系统暗色下 `dark:` 配色无法响应的底层问题。
- **修复智能对话不可读问题**：重写 `MarkdownBlock.tsx` 里的 `STYLE_CSS` 强行硬编码部分，在深色模式下自动漂白文本、标题及代码区块，解决文本不可读盲区。
- **修复案件管理本案文档白底缺陷**：利用代理机制自动将本案文档中选中的 `.bg-blue-50` 及 `.bg-blue-100` 等色块转化为曜石灰自适应底色，实现本案文档与公共文档样式在深色模式下的完美统一。
- **适配法律专家二级 Tab**：优化二级 Tab 未激活按钮在深色模式下的文字色与悬停高亮，建立渐变冷暖分级。
- **适配常法服务与合同审查配置区**：将顾问单位档案容器、顶部 Tab 选项栏以及审查面板配置区在深色模式下全部自动变暗并优化文字对比度。
- **适配定制文档与 Linvis 看板背景**：将 A4 纸容器阴影、章节大纲及 Linvis 米黄色背景 `bg-[#f7f5f0]` 分别适配为符合曜日黑主题底色，实现全站彻底暗色过渡。
- **适配首页头像 dropdown 下拉菜单**：解决下拉菜单文字 `text-gray-700` 在曜石灰面板上无法辨识的问题，漂白所有字体及图标选项。
- **适配右上角就绪状态圆点**：修正系统巡检小圈在深色背景下刺眼的白光外圈底色。
- **适配法律事务专家步骤流程条**：将起诉状/答辩状底下的分析步骤条（横向导航、进度圆点、协同复选框）、状态说明栏及文本域在深色模式下变暗为曜石黑/曜石灰。
- **强制漂白定制文档内联深颜色标题**：在 `index.css` 中增加对 `.ProseMirror` 的特异性样式覆盖。当用户导入 docx 时若包含 `#002060` 或 `#1f497d` 等 Word 内联深色标题字体，在深色模式下直接强制转换为高可读性的明亮文字色，而保留高对比度的警示色彩。
- **彻底解决定制文档内联深色字无法识别的顽疾**：还原了 index.css 针对 span 的特异性漂白，并采用双层属性选择器结构，增补支持了包含有空格与无空格的 hex 颜色（以 0-9, A, a 开头）及各种常用 rgb 十六进制反白规则。这保证了在任何标签节点上，深蓝色标题、灰黑色正文均能在深色模式下自适应呈现为亮白色，且不影响红色/绿色状态标志。
- **全栈三端彻底消除协同过程性提示残留且保留大纲标题**：在前端 marked 转换前对 rawMarkdown、后端 Word 导出、以及后端文档保存接口中重构了清洗截断算法。并在前端 `cleanMarkdownCollaborativeArtifacts` 清洗函数中，改用非 asterisks `**` 依赖 of 正则匹配，精准定位并删除流式生成完成后的过程废话；同时在后端 `projects.py` 的 `get_document`、`get_template` 及 `save_template` 路由中全面接入 `clean_collaborative_artifacts` 清洗函数，确保无论在数据生成、载入、保存，还是模板大纲流转时，协同废话均能被自动过滤。此外，针对流中断/超时（如 Ollama 读取超时导致 backend read timeout）或用户手动停止导致的最终大BOSS应答为空的极端场景，建立了“初稿回退提取容灾机制”，提取首稿并剥离多余协同内容直接上屏展示，规避了内容被全部清空的问题。
- **独立首页案件卡片背景颜色**：重新适配卡片在深色模式下的渐变起终点色与亮色边框。对于公共库展示深墨蓝色渐变，普通案件展示金褐色渐变，使卡片拥有轮廓明晰且各异的单独背景色，完美自适应大背景。

## [3.3.3] - 2026-06-07

### Changed
- 将后台图谱 Leiden 社区摘要提取模型由 `qwen3.6:35b-q4` 降级为 `qwen3:8b`。彻底解决了在 48GB 统一内存 M4 Max 上大模型频繁切换加载及内存 swap 换页导致的性能雪崩，使协同模式与普通模式的响应速度提升 6 倍以上。
- 彻底清理 Redis GPU 信号量死锁残留，全链路重启测试秒回，协同与普通问答全功能恢复极速流式响应。

## [3.3.2] - 2026-06-07

### Added
- 后端扩展公共配置接口 `/api/admin/settings/public` 以支持获取所有以 `agent_` 开头的自定义 Agent 属性（名字、性别、头像）。
- 前端 `projectStore.ts` 引入 `publicSettings` 状态管理和 `fetchPublicSettings` 方法拉取全局自定义设置。

### Changed
- 重构前台 Tab 导航：动态渲染“智能助手”、“法律事务专家”、“常法服务”、“合同审查”及“定制文档”的 Label 名称，与系统自定义 Agent 名称（如“小咨”、“老吴”、“小律”）保持同步。
- 动态联动问答面板：`AgentChat.tsx` 中的欢迎词、标题、思考提示语和聊天气泡左侧头像 Emoji 均根据系统后台配置的 Agent 自定义名称和头像动态切换。
- 高精度重构学习进度百分比：
  - 后端：在 `admin.py`、`projects.py` 与 `core/precompute.py` 中把百分比计算的 `int(...)` 截断改为 `round(..., 2)`。
  - 前端：重构 `LearningProgress.tsx` 看板，去除 `Math.round`。全局指标及列表详情中所有百分比输出均应用 `.toFixed(2)`。
  - 防御性防护：将浮点数精度比较 `=== 100` 改为安全性更高的 `>= 100`，杜绝溢出显示误差。
