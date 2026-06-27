# 智能体通用知识库 RAG (AgentRAG)

[![GitHub Repo](https://img.shields.io/badge/GitHub-iBubble/RAG-181717?logo=github)](https://github.com/iBubble/RAG)
![Version](https://img.shields.io/badge/Version-4.1.0-blue)
![Go](https://img.shields.io/badge/Go-1.18+-00ADD8?logo=go&logoColor=white)
![Python](https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.128+-009688?logo=fastapi&logoColor=white)
![React](https://img.shields.io/badge/React-19-61DAFB?logo=react&logoColor=black)
![Docker](https://img.shields.io/badge/Docker-OrbStack-2496ED?logo=docker&logoColor=white)

**智能体通用知识库 RAG (AgentRAG)** 是一套专为**中大型集团企业、研发机构与管理部门**量身定制的私有化多模态 RAG (Retrieval-Augmented Generation，检索增强生成) 知识库与智能文书协同编排系统。

系统针对本地物理算力环境（如 macOS M 系列芯片统一内存架构）进行极致深度优化，采用先进的 **Go 核心网关 + Python 算法微服务** 混合架构。完美打通了技术标准、管理规范、汇报PPT、业务口述录音的多模态文档解析处理，并利用高性能 Go Eino 编排框架、六路并行 RAG 检索管线与多智能体协同网络（Multi-Agent Collaboration Network）提供商用级、无幻觉的文书生成与审查服务。

---

## 📐 系统架构与拓扑设计

本系统采用私有化本地双层拓扑架构，将高并发网关控制流与重型算法推理、多模态解析及向量化处理进行物理隔离：

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    macOS 宿主机 (Unified Memory 统一内存架构)             │
│  ┌───────────────────────┐   ┌─────────────────┐   ┌─────────────────┐  │
│  │   Ollama 服务端        │   │    OrbStack     │   │   本地 RAID     │  │
│  │  - qwen3.6:35b-q4 驻留│   │   Docker 引擎   │   │  物理磁盘存储    │  │
│  │  - 共享本地 GPU 算力   │   │                 │   │  /Volumes/SYRAID│  │
│  └──────────┬────────────┘   └────────┬────────┘   └────────┬────────┘  │
│             │                         │                     │           │
│             └───────────────┐         │         ┌───────────┘           │
│              Bridge Network │         │         │                       │
│  ┌──────────────────────────┴─────────┴─────────┴─────────────────────┐  │
│  │                     RAG-Server 业务容器 (PM2 守护)                  │  │
│  │  ┌──────────────────────────────────────────────────────────────┐  │  │
│  │  │               Go 核心网关 (Nexus-Gateway, Port 8003)         │  │  │
│  │  │  - 全局高并发接入与 JWT 校验  - L2 Redis 缓存拦截与异步回写   │  │  │
│  │  │  - 核心聊天流基于 Eino 框架图编排流程                        │  │  │
│  │  └──────────────────────────────┬───────────────────────────────┘  │  │
│  │                                 │ (NoRoute 泛路由反向代理)         │  │
│  │  ┌──────────────────────────────▼───────────────┐                  │  │
│  │  │           Python 算法后端 (Port 8004)         │                  │  │
│  │  │  - 复杂业务工作流流式生成   - 原生 Word 修订留痕与批注          │  │  │
│  │  │  - Whisper / Tesseract 多模态文件解析服务                    │  │  │
│  │  └──────────────┬───────────────┬───────────────┬───────────────┘  │  │
│  │                 │               │               │                  │  │
│  │                 ▼               ▼               ▼                  │  │
│  │          ┌─────────────┐ ┌─────────────┐ ┌─────────────┐           │  │
│  │          │Neo4j 图数据  │ │Qdrant 向量库 │ │Redis 缓存    │           │  │
│  │          │(Port 7474)  │ │(Port 6333)  │ │& 消息总线    │           │  │
│  │          └─────────────┘ └─────────────┘ └─────────────┘           │  │
│  └────────────────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────┘
```

### 混合架构核心技术设计：
1. **高性能 Go 网关与 Eino 编排**：由 Go 承载高并发网络连接（如长连接心跳、大纲编辑、文件上传与系统健康上报），单机协程（Goroutine）内存占用低，将 high 并发压力物理屏蔽。核心对话流引入字节跳动开源的 Eino 编排框架，支持复杂的条件路由与有向图多 Agent 协同，并提供毫秒级的级联取消支持，避免模型算力空转。
2. **反向代理与微服务分工**：Go 网关作为最前端流量控制层，直接利用高性能反向代理（Reverse Proxy）将重型、低频的业务事务流式分析及文档审查请求转发给 Python 微服务，充分结合 Go 的高并发吞吐能力与 Python 丰富的 NLP/AI 算法库生态。
3. **PM2 多进程守护与资源编排**：容器内使用 PM2 启动和守护 Go 核心网关、FastAPI 异步微服务实例、`celery-fast` 吞吐队列以及 `celery-slow`（单并发慢任务队列，物理防 OOM），保障 macOS 物理宿主机及显卡资源稳定。


---

## 🛠️ 核心技术栈

| 模块分层 | 核心技术 | 实际应用与技术选型价值 |
| :--- | :--- | :--- |
| **表现层** | React 19 + TypeScript + Vite + Zustand | 支持单页应用（SPA）的高性能状态树管理与防 Tab 切换中断设计。 |
| **网关服务** | Go (Gin) + Eino 编排框架 + JWT | 维持高并发长连接（心跳、上报），管理 L2 缓存拦截，驱动核心对话流图编排。 |
| **富文本** | Tiptap 3 + Document Studio | 所见即所得的长文编辑器，新增联动二级下拉选择的 AI 表格智选面板，支持前后文感知及 Zustand 持久化防断电丢草稿。 |
| **算法服务** | FastAPI + Uvicorn + Python 3.12 | 异步处理通用工作流、ASR 转写、OCR 及 docx 批注，暴露纯净算法微服务。 |
| **异步队列** | Celery + Redis | 负责文档解析、Leiden 社区摘要提取、知识图谱提炼等重度后台离线任务。 |
| **向量数据库** | Qdrant (Dense + Sparse 混合检索) | 毫秒级支持 Dense 稠密向量与 Sparse 稀疏向量的检索与 RRF 融合。 |
| **图数据库** | Neo4j 5.18 | 存储实体与三元组关系，提取高维实体关系扩散路径，绘制星空知识图谱。 |
| **多模态解析** | Whisper-Base + Tesseract OCR + CAJ2PDF | 本地语音自动转写（ASR）、证据图片光学识别、CAJ 格式高清渲染缓存。 |
| **大模型推理** | Local Ollama + Qwen3.6-35B-Q4 | 本地 GPU 满载加速，主责深度法理推演、大纲撰写与多 Agent 编排。 |
| **文档生成** | .NET 8 (C#) / KimiDocx 引擎 | 支持微软 Word 的原生 XML 后处理，具备批注与原生红线修订追踪功能。 |

---

## 🧠 六路并行 RAG 检索管线与数据解析

系统内置高表现力、面向企业通用场景的检索增强生成（RAG）管道，采用六路并行检索融合机制：

```
                    ┌─────────────────┐
                    │  用户业务查询   │
                    └────────┬────────┘
                             │ (意图分类与 Query 语义改写)
       ┌─────────────────────┼──────────────────────┬─────────────────────┐
 ┌─────┴─────┐         ┌─────┴─────┐          ┌─────┴─────┐         ┌─────┴─────┐
 |  Qdrant   |         |   Neo4j   |          |   Neo4j   |         |  DuckDB   |
 | 混合检索  |         | 实体路径  |          | 子图问答  |         | 结构分析  |
 └─────┬─────┘         └─────┬─────┘          └─────┬─────┘         └─────┬─────┘
       │ Dense+Sparse        │ 关联度传导           │ 事实三元组          │ SQL 内存
       └─────────────────────┼──────────────────────┼─────────────────────┘
                             │ asyncio.gather 并行融合
                    ┌────────┴────────┐
                    │ RRF 混合融合    │ (Qdrant Dense 与 SQLite FTS5)
                    └────────┬────────┘
                             │ (地名正字校对 + 结构化表格原子注入)
                    ┌────────┴────────┐
                    │ 增强版 Prompt   │ $\rightarrow$ LLM 本地推理生成
                    └─────────────────┘

---

## 🖼️ 多模态 RAG 检索与模型自适应路由

针对图片、扫描件等非结构化证据材料，系统实现了视觉多模态 RAG 通道：
* **本地模型自适应检测与路由**：当网关层接收到图片输入时，若默认的 35B 文本大模型不支持视觉，系统会利用 `getBestMultimodalModel` 算法探测宿主机可用模型，并自适应将流量路由给本地最佳的多模态视觉大模型（如 `minicpm-v` / `moondream`），实现图文识别直答。
* **非视觉节点图片物理隔离**：在 Go Eino DAG 工作流中，将大体积图片数据从 `Planner`、`Checker` 和 `Auditor` 等文本节点的 Context 中显式擦除清空，只保留在 `Worker` 视觉节点中加载，实现零拷贝数据安全物理隔离，防范大包传输带来的网络和显存 OOM。

---

## 🌟 核心系统功能与技术实现方式

### 1. 多源文档解析管线与 DoCO 语义归一
*   **多源智能分流**：重构了文件解析入口，自适应识别文档版式。数字化原生文档通过 [docling_parser.py](file:///Users/gemini/Projects/Own/RAG/app-server/backend/core/extractors/docling_parser.py) 极速清洗；手写图片、复杂扫描件或多维表格重路由至慢任务队列，在 [pdf_parser.py](file:///Users/gemini/Projects/Own/RAG/app-server/backend/core/extractors/pdf_parser.py#L47) 中调用 `MinerU` 进行视觉布局识别与 OCR 提取，配置 4 线程硬限制，并在结束后清空 MPS / CUDA 显存。
*   **DoCO 节点语义表征**：使用 DoCO 本体将不同解析器的输出映射为标准化节点（`section_header` 标题, `table` 表格, `list_item` 列表, `text_block` 普通文本），空间坐标与逻辑层级在切片时与 Qdrant Point Payload 及 Neo4j 拓扑无缝绑定，实现精准的段落物理位置回溯与前端高亮。

### 2. 100% 确定性约束填表与自纠错
*   **Pydantic Schema 模型规约**：在 [market_supervision.py](file:///Users/gemini/Projects/Own/RAG/app-server/backend/core/schemas/market_supervision.py) 中，将市场监督表单（统一社会信用代码、法定处罚种类、裁量金额范围）抽象为标准的 Pydantic 校验模型。
*   **Ollama 掩码解码约束**：在 [constrained_decode.py](file:///Users/gemini/Projects/Own/RAG/app-server/backend/core/constrained_decode.py#L35-L44) 中，直接提取模型的 JSON Schema 并透传给本地 Ollama 推理服务的 `format` 字段，使模型大类 Token 的输出概率在推理层受状态机强控制，避免输出非 JSON 杂质。若校验失败，系统会自动捕获 `ValidationError` 堆栈，作为上下文提示词发回大模型，在毫秒级内自动闭环修正生成。

### 3. Eino Multi-Agent 协同图与深度思考 (Smart) 模式编排
*   **Go Eino 拓扑编排（Smart 模式核心）**：核心对话流基于 [eino_graph.go](file:///Users/gemini/Projects/Own/RAG/app-server/nexus-gateway/eino_graph.go) 编排成 Planner (公文秘书) -> Worker (定量数据校验) -> Checker (合规审查员) -> Auditor (公文终审员) 的有向图，利用 Goroutine 极小内存开销避免高并发拥堵。在 System Prompt 中加入刚性规则，绝对屏蔽司法裁决色彩和 `🏛️` 等图形，严格使用庄重的政府公文风格。
*   **林维斯协同状态流式监视（Linvis）**：在有向图每个 Lambda 节点状态流转时，通过 `setLinvisStatus` 实时向后台大屏异步推送最新的状态详情，支持了智能体圆桌会议大屏的实时展示。
*   **中断与恢复 (Interrupt & Resume)**：当公文终审员判定当前的文书草案触发严重合规预警（如程序违规或大额惩罚）时，Eino 流执行中断，通过 [generate.py](file:///Users/gemini/Projects/Own/RAG/app-server/backend/api/generate.py#L2858) 底层路由将有向图快照冻结至 Redis `eino:frozen_state:{project_id}`（TTL 24小时），前台看板琥珀色报警并拉起法务控制台。法务主管人工批改后，通过 [chat_handler.go](file:///Users/gemini/Projects/Own/RAG/app-server/nexus-gateway/chat_handler.go#L154) 接收合规修改，拉起 `Resume` 恢复执行后续图流程。

### 4. 向量级 Redis 语义缓存网络 (L2 Answer Cache)
*   **高维语义相似度命中**：在 [semantic_cache.py](file:///Users/gemini/Projects/Own/RAG/app-server/backend/core/semantic_cache.py) 中，对用户的提问进行 BGE-M3 稠密向量转换并归一化，通过 `np.dot` 与 Redis Hash 结构中历史提问向量计算余弦相似度。若大于匹配阈值 `0.96`，直接从缓存获取最终文书，返回时间从大模型推理的 2分多钟骤降至 **0.37s**，配置 1 小时过期 TTL 自动释放空闲哈希。

### 5. 双层 Neo4j 拓扑关系图谱
*   **第一层：DoCO 文档物理树**：基于 Document 节点层层分级建立 `(:Document)→[:HAS_ELEMENT]→(:EvidenceUnit)`，维护切片物理坐标。
*   **第二层：FormField-EvidenceUnit 拓扑关系网**：通过正则与实体识别，在 [graph_rag.py](file:///Users/gemini/Projects/Own/RAG/app-server/backend/core/graph_rag.py#L740-L764) 中提取营业执照统一信用代码、当事人企业名称等关键表单字段，自动生成 `(:FormField)-[:EVIDENCE_BY]->(:EvidenceUnit)` 的指向，实现行政审计的全链路事实一致性交叉追溯。

### 6. 异步 OTel 追踪与 Ragas 错峰离线评测
*   **Langfuse 分布式链路监控**：利用异步线程上报 OTel 规范的 Trace ID (32位十六进制小写) 及节点 Span，主请求线程无任何网络等待损耗，实时渲染 Eino 拓扑链。
*   **Ragas 离线跑批打分**：在 [worker.py](file:///Users/gemini/Projects/Own/RAG/app-server/backend/worker.py#L155) 中配置 Celery 凌晨定时打分任务，废除随机数 Mock，使用 Ragas 框架计算上下文相关性、回答相关性及忠实度指标，并将计算平均值回写至 SQLite 的 `ragas_daily_reports` 日报表中，保障系统生成公文与决策的严肃质量。

---

## 📊 AI 表格 (AITable) 核心功能与技术实现

系统内置了针对大型复杂统计图表设计的**AI 表格注册与无损直接注入模块**（`table_registry.py`），完美解决了大文件被切片打碎后大模型无法还原复杂表格的技术难题：

### 1. 表格解析、注册与语义增强
*   **完整实体离线存储**：在文档解析阶段（Word/PDF/Excel），系统自动提取完整的 HTML/Markdown 表格，并将其作为独立实体存放在本地磁盘的 JSON 注册表内，避免被 chunk_size 拆碎。
*   **大模型智能摘要**：为每张注册表格调用本地 `qwen3.6:35b-q4` 生成一句话语义摘要，涵盖表格标题、核心表头、数据类型与包含的主要内容，用于扩大检索的语义命中空间。
*   **混合向量索引**：将表格的标题、表头结构以及模型生成的摘要合并，利用 Qdrant 稠密 + 稀疏双路混合向量进行嵌入建库，提供极高的召回率。

### 2. 前端智选面板与零损耗注入
*   **Tiptap 智选面板**：在前端富文本编辑器中，用户可点击工具栏直接唤起“AI 表格智选面板”，通过语义搜索快速查找并预览相关历史表格。
*   **一键无损直插**：找到表格后，用户可一键将其以干净的 HTML 格式直插到当前编辑器光标处，**100% 避免了 LLM 重新生成表格时出现的格式坍塌、数值错乱和 Token 限制截断**。

---

## 📄 定制长文档段落编排与原生 Word 修订留痕

针对大型企业报告、建议书和市监文书撰写场景，系统设计了高表现力的**定制文档段落编排管道与原生修改留痕机制**：

### 1. 范文高保真仿写与空标题过滤 (Slot-Filling)
*   **多模式流式生成**：支持段落与大纲的“生成、替换、克隆”三种编排模式，配合 Server-Sent Events (SSE) 流式平滑输出。
*   **结构性章节智能跳过**：在克隆/替换模式下，如果匹配到的范文章节内容为空（如纯结构性目录标题），系统会自动拦截并**物理跳过**生成过程，强制输出空内容，防止大模型自由发挥甚至产生幻觉。
*   **范文主题词 RAG 提取**：在仿写（Clone）阶段，从范文段落中提取核心主题词，过滤掉地名和数值，作为精准的 Query 去向量库和图谱中检索关联知识，使生成的章节能精准填充当前案情的特定事实分析。

### 2. 微软 Word 原生修订追踪与批注后处理
*   **OpenXML 底层注入**：后端导出模块 (`docx_comments.py`) 将生成的文档视为标准 ZIP 压缩包进行解包，通过修改 `word/document.xml`，自动把大模型输出的修订文本替换为微软 Office 标准的原生 `<w:del>`（删除线红字）和 `<w:ins>`（下划线插入）标签。
*   **修订追踪强制激活锁**：在 `word/settings.xml` 配置中强行闭合并注入 `<w:trackRevisions/>`，保证用户在 Microsoft Word、WPS 等 Office 软件打开文档时，**默认自动开启且锁定“修订留痕模式”**，便于审查所有修改动作。

---

## 🔌 算力控制与三档运行模式

系统在后台管理中内置了专为本地开发与日常办公设计的 **后台系统运行模式与资源控制总开关**：

- **全速学习模式 (Full Speed)**：后台同时启动文本向量化进程、Neo4j 图谱三元组构建以及 Louvain 社区摘要计算任务。大语言模型常驻 GPU 内存，后台多并发火力全开，以最高吞吐量处理新上传项目文件。
- **节能运行模式 (Vector Only)**：图谱三元组提炼与社区摘要任务自动挂起并留在 Redis 队列中缓存；仅执行秒级的轻量文件切片与向量入库。大语言模型自动从 GPU 显存中卸载释放（**腾退全部 23GB 显存**），确保本地设备有充足显存进行前端设计或代码开发。
- **完全挂起模式 (Suspended)**：通过 PM2 物理命令将后台 Celery `slow_queue` 等慢队列进程强制挂起，Redis 任务进度 100% 留存，不丢失任何上下文。完全释放 GPU 与 CPU 资源，背景 CPU 占用保持在 0%，仅保持 Web 页面与最低限度 API 响应。

---

## 📝 Word 原生修订留痕与后处理

系统基于 **Office Open XML (OOXML)** 规范自主开发了**微软 Word 原生修订追踪与红线留痕后处理模块** (`docx_comments.py`)：

1. **原件解压与 XML 正则处理**：后端将导出的 `.docx` 格式文件视为标准 ZIP 压缩包，解压读取其核心内容区 `word/document.xml` 以及配置项 `word/settings.xml`。
2. **原生 `<w:del>` / `<w:ins>` 注入**：编写专有正则表达式，扫描正文中的 `[修改前: A -> 修改后: B]` 语法块，将其精准转写为符合微软标准的原生 OpenXML 修订标记。
3. **修订追踪强制激活锁**：在 `word/settings.xml` 配置文件中强行注入并闭合 `<w:trackRevisions/>` 标签，使导出的 Word 文档在被 Microsoft Word、WPS 或 Pages 打开时，**默认自动开启并锁定“修订模式”**，红线留痕及侧边修改批注能够 100% 完美呈现。


---

## ⚡ 前端高频重绘防爆与 I/O 写入防抖安全盾

针对深度思考模式下高频流式 SSE 推理的极端场景，前端设计了高性能防护架构：
* **无持久化内存 Store 隔离**：将长文流式生成状态 `chatStreamingState` 彻底剥离至不带持久化（persist）中间件的独立 `useChatStore` 内存容器中，避免了每次大模型吐出 Token 时 Zustand 频繁进行序列化深度克隆以及对 IndexedDB 写入导致的磁盘 I/O 线程阻塞。
* **磁盘持久化 500ms 写入防抖安全盾**：针对 `useProjectStore` 等需要写盘的常规操作，在底座 `idbStorage.setItem` 增加 500ms 防抖限制。不论状态更新频率多高，500ms 内向物理磁盘写入的次数强行合并为至多 1 次，消除了高频数据库锁死导致的浏览器标签页崩溃（STATUS_BREAKPOINT / Error 5）。
* **渲染 Batching 与 Markdown 纯文本降级防护**：在 SSE 字符解析读取循环中仅累加状态，在循环结束后单次批量触发 `set` 重绘，使渲染频率降低 95%。并在流式打字生成期间采用纯文本降级容器渲染，防止大模型未闭合的残缺 HTML 代码块引起剧烈的 DOM 树回流，待生成彻底结束后无缝切换为完整 Markdown AST 呈现。

---

## 🔐 生产级私有化安全保障

作为专为企业严苛场景量身打造的系统，AgentRAG 在私有部署上构建了极其稳固的系统安全性设计：

- **物理与路由级数据隔离**：支持项目级的隔离权限校验，非本项目授权用户无法通过 API 获取该项目的知识文档。
- **防止路径穿越与上传投毒**：头像及附件上传严格限制在配置的沙箱目录中，执行严格的扩展名白名单检测。对拼接后的物理路径进行真实物理路径校验，从根源上规避通过 `../` 侵入写入的漏洞。
- **独立审计日志滚动清理**：核心操作审计日志由独立进程接管。设置 30 天滑动清理窗口，过期审计日志在后台自动抹除，绝不无限制膨胀堆积。
- **FTS5 全文检索安全层**：对全局模糊搜索（SQLite FTS5）中的特殊控制字符和操作符进行强制过滤，防止注入式拒绝服务。

---

## 📁 项目目录结构

```
├── README.md                       # 本产品介绍手册
├── app-server
│   ├── Dockerfile                  # RAG-Server 统一容器构建配方
│   ├── start.sh                    # 容器内 PM2 服务一键联启脚本
│   ├── ecosystem.config.js         # PM2 多进程集群配置文件
│   ├── nexus-gateway               # Go 核心网关源码 (Port 8003)
│   │   ├── main.go                 # 网关入口与反向代理路由
│   │   ├── chat_handler.go         # L2 缓存拦截与 Eino 图调用控制
│   │   └── eino_graph.go           # 核心聊天流有向图 Eino 编排
│   ├── backend                     # Python FastAPI 算法微服务源码 (Port 8004)
│   ├── frontend                    # React 19 + TypeScript + Vite 前端源码
│   ├── data                        # 本地 SQLite、向量数据及物理文件存储目录
│   └── Records                     # 项目滚动开发状态微状态日志目录
```

---

## 🚀 启动与部署 (Docker 私有部署)

系统已实现容器化一键秒级部署。在项目根目录下，直接通过启动脚本即可拉起全部混合微服务架构：

```bash
# 1. 运行宿主机上的一键联启脚本
./app-server/start.sh
```

此脚本将在 `RAG-Server` 业务容器中通过 **PM2 守护进程** 并行拉起并监控以下 5 大核心微服务集群，保证全天候稳健运行：
* **`genrag-gateway` (Go 核心网关)**：监听 `8003` 端口，作为外部流量的唯一接入网关，将业务流量代理转发至后端。
* **`genrag-backend` (Python 算法微服务)**：监听 `8004` 端口，处理由网关转发的流式生成与文书编排。
* **`genrag-frontend` (React 前端服务)**：运行在 `2028` 端口，托管并渲染前端 SPA 静态页面。
* **`genrag-celery-fast` / `slow`**：后台高并发切片吞吐及慢速大计算量（Louvain 社区摘要、知识图谱提炼）队列，守护本地资源防 OOM。
```,StartLine:170,TargetContent:
