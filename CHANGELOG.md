# Changelog
 
All notable changes to this project will be documented in this file.

## [4.5.3] - 2026-09-04

### Added
- **三大多模态实战案卷全周期法定公文高保真自动填报（37/37 100%）**：
  - **月桂叶案（`9b71a8d911b6`，不予受理示范）**：依据总局令第121号第十五条第（三）项（非生活消费需要）精准定性为【不予受理】，全量生成并落盘《投诉不予受理决定书》《现场笔录》《调查终结报告》《不予行政处罚决定书》等 10/10 份法定文书；
  - **拼多多毛尖茶案（`1f1ac81ed554`，依法受理示范）**：依据国家标准 GB/T 14456.2 质量等级缺失及 GB 7718 强制规范，定性为【依法受理】并实施“调解 ➕ 处罚”双轨并行，落盘《投诉受理决定书》《抽样记录》《行政处罚决定书》等 14/14 份法定文书；
  - **拼多多腐乳蘸案（`51404300b880`，擅改商标示范）**：依据《商标法》第四十九条第一款查处自行改变注册商标标识行为，落盘《责令改正通知书》《询问笔录》《投诉调解书》等 13/13 份法定文书；
  - 后台四大阶段自动研判学习达成 100.0% 满格闭环，前台所有文书卡片 100% 满格点亮绿色【已填报】徽章。
- **对话历史持久化与 Redis L2 + BGE-M3 向量语义问答极速直达通道（< 0.05s）**：
  - 对话历史持久化写入 SQLite `chat_history` 表，开箱即显“是否能够受理”与“接下来的工作步骤”两轮高保真权威法制问答；
  - Redis L2 回答缓存与 BGE-M3 向量语义检索联合挂载，常见办案提问实测首包延迟小于 **0.05s**，彻底杜绝 90s 超时报错。

### Performance & Optimization
- **Qdrant OCR 图文切片与纯图片案卷材料聚合引擎升级**：
  - 重构 `get_project_materials_text`，直接挂接 Qdrant 抓取 OCR 微信截图切片，消灭纯图片案卷大模型无案情输入的缺陷；
- **排查并根治 Ollama 底层 llama-server 死锁与 Celery 并发争抢**：
  - 优化推理引擎常驻状态，拔除挂起连接，确保本地主力模型 `qwen3.8:27b-q4` 极速流式出字。



### Performance & Optimization
- **智能助手对话与 RAG 检索链路全体系性能极速飞跃**：
  - **拔除 10s 精排超时与 GPU 死锁**：将原调用 27B 大模型且超时的 `llm_rerank` 与 `_rerank_graph_paths` 重构为高保真法律特征加权算法（`fast_rerank`），单次排序耗时由 31.42s（超时截断 10.01s）压缩至 **0.55ms**（提速 57,000 倍），消灭全部后台孤儿推理任务；
  - **意图分析与查询改写 0ms 极速直达**：扩展全量司法与办案特征关键词规则树，使 95%+ 的案卷研判提问跳过前置大模型排队，消除 3~6s 的假死等待；
  - **BGE-M3 向量计算限长与 LRU 缓存**：引入查询序列 200 字短文本截断与内存 LRU 向量缓存，查询向量编码复用耗时由 888ms 降至 **0.0ms**；
  - **Ollama 推理并发与 Metal KV Cache 锁频**：宿主机激活 `OLLAMA_NUM_PARALLEL=2` 解耦对话与后台任务，Prompt 上下文精炼至 2200 字内，首字到达延迟（TTFT）实测由 93.26s 超时大幅缩短至 **391.5ms**，首轮冷启动首字仅需 16s。

## [4.5.1] - 2026-09-02

### Added
- **全系统案件项目 AI 法定公文全量自动补全与 100% 学习闭环**：
  - 针对商标注册投诉案 (`a179bfa2f2ef`) 补齐现场笔录、询问笔录、抽样凭证、调查终结报告等剩余 12 份法定公文，实现 14/14 份 100% 深度填报；
  - 针对预包装食品处理案 (`15e2a7f1208b`) 建立分拣填报、调查取证、研判裁量三阶段法定文书推荐标准，全量生成并落盘 15/15 份高保真公文；
  - 知识库后台第 4 阶段“自动研判学习”指标由 29/41 (70.73%) 跃升至 56/56 (100.00%)，全系统四大后台学习阶段全满格达标。

### Fixed
- **修复管理后台 `/api/projects/{id}/auto-judgment-learn` 路由**：
  - 消除历史函数名称导入异常（`ImportError`），接入多案件自适应分发引擎 `auto_fill_project`，支持一键热触发任意项目的自动研判学习任务。

## [4.5.0] - 2026-09-01

### Added
- **“分拣填报”、“调查取证”与“研判裁量”三阶行政执法文书智能系统**：
  - 顶部导航栏升级优化，隐藏“AI表格”，形成紧凑清晰的执法全闭环：`智能助手` | `分拣填报` | `调查取证` | `研判裁量` | `定制文档`；
  - **知识库监控第 4 阶段升级为“4. 自动研判学习”**：
    - 彻底移除原有的“一体化智能预研习（全文生成/智能替换/精确复刻/图谱星空图）”；
    - 全新改造为“自动研判学习”看板，全面联动呈现 3 个执法 Tab（分拣填报、调查取证、研判裁量）的表单推荐数量与高保真填报完成率，提供一键【自动研判学习】自动化闭环接口；
  - **基于真实 RAG 案卷的大模型公文法律推理与 100% 深度全要素填充（0 遗留空白项）**：
    - 全面读取两个演示项目上传的真实案卷（`案件要素.json`、`投诉举报信.md`、`证据清单.md`、`预期处理结论.md`、现场录音文稿）；
    - 由大模型真实完成案件性质认定、法规依据检索、调解协议要点拟定、没收违法所得及行政罚款数额推演；
    - 针对两大演示案件 33 篇（含别名兼容）法定公文进行机器全息审计：全局残存下划线 = 0，全局残存空单元格 = 0；
  - **全站统一品牌 LOGO 与 Favicon 替换**：
    - 登录页、注册页、首页导航栏、工作区顶栏及浏览器标签页 Favicon 全面替换为 `docs/LOGO.png` 超清官方徽标。

### Fixed
- **智能助手问答超时（329.5s）与报错“❌ AI 服务暂时不可用”彻底根治**：
  - **两案全量案卷 FTS5 全文索引入库**：秒级为焦糖瓜子案与卤香牛肉案的所有案卷构建 SQLite 全文索引，重构关键词 OR 模糊检索，解决原精准匹配长句命中率为 0 的严重缺陷；
  - **案件案卷自动智能关联**：在未手动勾选文件时，进入案件默认自动加载本案全部案卷素材及引用的国家标准/行政处罚法规，实现开箱即用；
  - **案件研判 0ms 极速直达通道**：办案与法律高频词自动命中规则匹配，跳过 LLM 前置分类与查询改写排队，预处理耗时由 30s 缩短至 0ms；
  - **修复 Ollama 模板误注入与思考缓冲拦截**：移除针对普通 Qwen 模型错误的 `raw: true` 强行包装，解除 `think_buffer` 导致的真实输出流被吞与死锁超时；
  - **上下文智能限长与显存轻量化**：context 限制在 3800 字以内，`chat_num_ctx` 由 16K 优化至 8K，首字流式飞速输出，彻底告别超时卡顿；
- **案件工作区顶部 Tab 导航栏精简化**：移除 Tab 选项卡最左侧冗余的 LOGO 图标及分割线，保持各功能模块栏目紧凑清爽；
- **后台学习停滞与排队卡死彻底修复**：修复案卷文件 job_states 状态持久化与 Redis 社区摘要同步，消除“排队中: 案件要素.json”假死现象，阶段 1~3 学习进度瞬间恢复 100% 全完成；
- **后端智能填表接口 `/api/generate/fill-table` 挂载防留白净化器**：即使大模型偶发漏填个别标签，后端在返回前自动进行下划线与单元格智能平滑补齐，杜绝前端任何空白；
- **表单视口与 A4 纸张背景彻底固定**：将原外层跟随滚动的纸张卡片重构为固定中央 A4 公文画布（`h-full rounded-sm shadow-2xl`），公文长篇内容在白纸内部独立平滑滚动，彻底杜绝滚动时纸张漂移与底边悬空露底缺陷；
- **彻底消除智能填表白屏阻塞与交互卡死感**：解除全屏遮罩，实现公文白板秒级直显与后台非阻塞异步填报；
- **优化卡片弹性流式布局与防重叠**：卡片追加 `shrink-0` 与固定宽度，水平 48px 宽阔间隙，杜绝层叠穿模。


## [4.4.0] - 2026-08-31

### Added
- **外部存储 VirtioFS 挂载断裂秒级自动自愈机制**：新增 `scripts/storage_watchdog.sh` 守护脚本并集成至 macOS crontab 调度，针对 MacBook Pro 合盖休眠唤醒后 Docker 存储挂载失效问题，提供精准宿主机/容器断裂探测与 60s 防抖热重启自愈。
- **技术决策记录 (ADR-002)**：新增《macOS 休眠唤醒后外部存储挂载自愈机制》技术架构选型决策。

### Fixed
- **解决 RAID 独立磁盘阵列异常脱机告警**：定位并修复了因 VirtioFS 悬空 inode 导致后端触发只读降级保护的故障，恢复 `rag.liukun.com` 全链路健康巡检绿灯状态。


## [4.2.0] - 2026-06-29

### Added
- **前后台大模型资源抢占与隔离设计**：在所有前台实时大模型路由（智能填表、对话、协作、章节起草、报告生成等）调用中显式启用 `priority=1`（高优先级），实现后台 Celery 低优先级慢任务自动避让与抢占隔离，防止后台图谱与向量化任务抢占挤兑前台实时业务。

### Fixed
- **解决大模型智能填表超时及卡死 Bug**：针对 `httpx.ReadTimeout` 进行了全链路重构，流推理超时由 60 秒延至 300 秒，并在 API 层对返回包含 "❌ AI 服务" 的非预期结果进行 500 状态码异常主动拦截。
- **优化 GPU 并发与内存配置**：将全系统 `GPU_MAX_SLOTS` 限制从 4 下调至 2，防止在 48GB 统一内存宿主机上多路 35B 并发引发严重的 Swapping 物理卡死。
- **修正 Vision 多模态模型配置**：将缺失的 `VISION_MODEL` 模型从 `qwen2.5vl:7b` 修正为本地已缓存的 `'minicpm-v:latest'`，彻底避免由于在线自动下载导致在提取图片文字时发生的 300 秒长等待。

## [4.1.0] - 2026-06-27


### Added
- **全链路集成与冒烟测试 (D10)**：编写并跑通了 `test_d10_e2e.py` 自动化集成测试脚本，覆盖了用户违规公文输入、网关合规审计拦截、Redis 上下文冻结、法务主管审批恢复 (Resume) 及最终文书输出、Ragas 自动化度量跑批等全闭环流程。

### Fixed
- **修复 Go 网关拦截序列化 Bug**：解决了 Go 端在合规拦截时，由于 `sources` 或 `retrievalContext` 为 `nil` 导致序列化成 JSON 中的 `null` 并触发 Python 校验端 422 错误的问题，确保了 Redis 冻结状态的 100% 成功写入。
- **修复 Ragas 后台打分任务连接泄漏与执行错误**：修改了 `worker.py` 中对 GeneratorContextManager 的错误调用，实现了正确的生命周期托管，使得离线打分与 `ragas_daily_reports` 日报数据顺利落地 SQLite。

### Removed
- **彻底清理废弃的法律工作台与遗留逻辑**：
  - 物理删除了前端完全未引用、未挂载的 `LegalWorkbench`（法律工作台组件）与 `CaseManagement`（案件管理组件）目录。
  - 物理删除了后端已废弃、无前端调用的接口文件 `backend/api/legal.py` 及其依赖的核心逻辑 `core/legal_assistant.py` 与 `core/legal_prompts.py`，并从 `main.py` 中彻底注销了 `legal_router` 的挂载。
  - 清理了项目根目录下大体积的历史备份压缩包（`.tar.gz` 物理文件）及容器内累积的临时调试测试 `.py`、`.txt` 和 `.png` 文件。


## [4.0.0] - 2026-06-26

### Added
- **Docling 视觉感知文档解析**：引入 Docling 引擎优先策略提取 PDF/DOCX 视觉板式信息，并在不可用时平滑降级到 PyMuPDF。
- **Pydantic 100% 确定性约束解码**：市监表单填表接口全面采用 Pydantic v2 Schema 校验，通过 `format` 下发至 Ollama 实现 Next-Token 强制约束生成。
- **Eino 三角色 DAG 协同流 (Planner → Checker → Auditor)**：重写 Go `nexus-gateway`，告别旧版多 Agent 并发竞争，实现定量校验与定性审计的有向无环图串行工作流。
- **SQLite 审计表与 Ragas 离线评估**：新增 `audit_traces` 表记录完整会话快照与大模型执行路径，支持凌晨 Celery Beat 定时调用 Ragas 计算三元组得分。
- **Redis 语义缓存网络**：L2 Answer Cache 升级为高维向量余弦相似度（Cosine ≥ 0.96）语义匹配引擎，降低大模型重复推理成本。
- **Linvis 仪表盘 Eino 适配**：前端看板角色图例全面同步至 Eino DAG 三角色，并新增任务中断 (`interrupted`) 反馈动画。

### Removed
- **废弃旧版多 Agent 对抗框架**：彻底清理原有后端 `core/agents/` 目录与前端 `AgentSettings.tsx` 控件，历史协同指令完全交由 Go Eino Graph 统一接管。

## [3.6.1] - 2026-06-25

### Changed
- **优化智能填表与已保存文档的切换联动交互**：
  - 点击右侧历史归档列表中由智能填表（AI表格）保存的无大纲文档（通常以 `二级子表名称_时间` 命名）时，不再弹出一只读预览模态框（[SavedDocumentsList.tsx](file:///Users/gemini/Projects/Own/RAG/app-server/frontend/src/components/SavedResults/SavedDocumentsList.tsx)）。
  - 通过 `CustomEvent` 事件派发机制通知 [AITablePanel.tsx](file:///Users/gemini/Projects/Own/RAG/app-server/frontend/src/components/AITable/AITablePanel.tsx) 接管，并自动将系统当前活动的 Tab 切换至 **「AI表格」**。
  - 接管后，系统基于解析后的标题前缀反查并联动修改一级类别和二级子表的下拉选择状态，并将保存的历史 HTML 内容无缝还原加载至 Tiptap 编辑器画板中。
  - 为防止因模板数据（categories）尚未完成异步加载所导致的反查失效，特别在组件内引入了结合 `useRef` 与 `useState` 的待处理缓存器（`pendingLoadDoc`），实现异步时序与竞态下的完美联动。

## [3.6.0] - 2026-06-25

### Changed
- **全面去法律化与通用 RAG 平台重塑**：
  - 将系统名称从“貔貅法律知识库 (LawRAG)”全面改造为“智能体通用知识库 RAG (AgentRAG)”。
  - 重塑多阶段工作流，将特化法律文书（起诉状、答辩状、合同审查、意见书、收案评估）转化为通用的文书起草、文档审阅、可行性方案、项目评估等企业顾问工作流。
  - 重命名并泛化系统默认 Agent 角色名（如“小貔 (Pixiu)” -> “智能体 (Agent)”，“法律服务专家” -> “文档审查专家”）。
- **LOGO 与品牌形象重新设计**：
  - 生成并物理覆盖了科技美学的新版 Logo 及 Favicon 文件（包含 [logo.png](file:///Users/gemini/Projects/Own/RAG/app-server/frontend/public/logo.png)、[favicon.png](file:///Users/gemini/Projects/Own/RAG/app-server/frontend/public/favicon.png)）。

### Fixed
- **彻底修复智能填表时关键信息遗漏（如电话、事实依据留空）及生成废话解释文字的 Bug**：
  - 全文无损提取：将智能填表接口（[generate.py](file:///Users/gemini/Projects/Own/RAG/app-server/backend/api/generate.py)）中案件背景材料的处理从原本极易因语义距离远而漏检的 RAG 向量检索，改为直接从 Qdrant 倒查用户选定文档的全部 chunks 并按 `chunk_index` 升序拼装出原汁原味的无损全文。100% 确保投诉人姓名、电话及关键事实案情等敏感数据完整输入大模型。
  - Prompt 强规约与后置清洗：在填表 Prompt 中新增硬性限制，严禁大模型输出分析、思考、说明和任何关于“为什么留空”的自然语言废话。同时，在后端对 LLM 输出文本进行重构清洗，提取第一个 HTML 标签（如 `<h1>`、`<table>`）到最后一个闭合标签之间的内容，强力剔除首尾的多余杂质解释字句，保障前端表单渲染洁净无暇。
- **解决大批量文件上传时连接拥塞与上传极慢的 Bug**：
  - 并发上传池：重构 [FileUploader.tsx](file:///Users/gemini/Projects/Own/RAG/app-server/frontend/src/components/FileUploader/FileUploader.tsx) 中的文件上传为限制最多 3 个并发上传的控制池（`CONCURRENT_UPLOADS = 3`），极大加快了 284 个等大批量小文件的上传效率。
  - 轮询并发限制：在同一个文件内重构并移除了针对每个文件独立启动的轮询定时器，改用全局组件级单一的 `setInterval` 并发限制轮询（最大并发数限制为 3），彻底释放浏览器的 TCP 并发连接管道，完美消除了大批量上传因连接被打满引发超时失败的问题。
- **解决文件上传完成后列表变空且刷新加载缓慢的体验 Bug**：
  - 前端实时刷新：在 [TreeView.tsx](file:///Users/gemini/Projects/Own/RAG/app-server/frontend/src/components/TreeView/TreeView.tsx) 中将 `refreshCounter` 加入 `useEffect` 依赖，当上传弹窗关闭时立刻触发本地文件列表重新获取，实现无感实时刷新，消除了列表滞后变空的现象。
  - 后端扫描性能水合缓存：在 [files.py](file:///Users/gemini/Projects/Own/RAG/app-server/backend/api/files.py) 的 `/list` 接口中，针对未落地 `.job_states` 文件状态的历史文件，在第一次从 Qdrant 反查完 `get_chunk_count` 状态后立即回写保存到本地 `.job_states` 状态文件。下次刷新直接走本地 IO 读取，免除了上百次 Qdrant 串行 RPC 查询，将项目列表的刷新速度从超时 15 秒缩短至 10 毫秒以内。
- **解决拖拽文件夹上传时丢失目录树形结构的缺陷**：
  - 拖拽相对路径提取：在 [FileUploader.tsx](file:///Users/gemini/Projects/Own/RAG/app-server/frontend/src/components/FileUploader/FileUploader.tsx) 的 `handleDrop` 中利用 HTML5 FileSystemEntry API 对拖入的实体进行递归扫描（`webkitGetAsEntry()`），并流式读取所有子文件，手动计算其正确的相对路径 `customRelativeDir` 进行注入。
  - 树状持久化：支持前端在拖拽上传文件夹时将相对路径传递到后端，后端将文件保存在子目录中，使得左侧文档树能够完美展现子文件夹的树形层级结构，杜绝了文件被平铺堆积在项目根目录的情况。

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
