# GenRAG（通用版检索增强生成知识库 V3.3.2 RAG）

[![GitHub Repo](https://img.shields.io/badge/GitHub-scsygczx/RAG-181717?logo=github)](https://github.com/scsygczx/RAG)
![Version](https://img.shields.io/badge/Version-3.3.2-blue)
![License](https://img.shields.io/badge/License-Proprietary-red)

Law RAG 是**云南力诺科技有限公司**为律师事务所量身定制的业务体系的**多用户协同高密度知识库与 AI 文档辅助生成系统**。

系统已全面升级为基于 Docker (OrbStack) 的微服务编排网格，通过热挂载实现全景隔离与实时构建，包含内置代理通讯隧道、JWT 严格鉴权与严格租户隔离机制，用于深度保障企业图纸等核心机密。

---

## 📐 系统架构总览

```
┌──────────────────────────────────────────────────────────────┐
│                     Mac Studio 宿主机 (ARM64)                 │
│  ┌─────────────┐  ┌──────────────┐  ┌────────────────────┐  │
│  │   Ollama     │  │  OrbStack    │  │   RAID 磁盘阵列     │  │
│  │  LLM 推理    │  │  Docker 引擎  │  │  /Volumes/SYRAID   │  │
│  │  :11434      │  │              │  │  (uploads/db)      │  │
│  └──────┬───────┘  └──────┬───────┘  └────────┬───────────┘  │
│         │                 │                    │              │
│  ───────┼─────────────────┼────────────────────┼──────────    │
│         │      Docker Network (bridge)         │              │
│  ┌──────┴──────────────────────────────────────┴───────────┐  │
│  │              RAG-Server (Ubuntu 22.04 ARM64)            │  │
│  │  ┌──────────┐ ┌──────────┐ ┌────────┐ ┌─────────────┐  │  │
│  │  │ FastAPI  │ │ Vite     │ │ Celery │ │ FRPC v0.56  │  │  │
│  │  │ :8001    │ │ :2026    │ │ Worker │ │ → 云端穿透   │  │  │
│  │  └──────────┘ └──────────┘ └────────┘ └─────────────┘  │  │
│  │                    PM2 进程守护                           │  │
│  └─────────────────────────────────────────────────────────┘  │
│  ┌─────────────┐  ┌─────────────────┐                        │
│  │  RAG-Redis  │  │  RAG-Database   │                        │
│  │  Celery队列  │  │  Qdrant 向量库   │                        │
│  │  :6379      │  │  :6333          │                        │
│  └─────────────┘  └─────────────────┘                        │
└──────────────────────────────────────────────────────────────┘
         │
     FRP + Caddy
          ↓
   https://rag.liukun.com  (公网入口)
```

---

## 🛠️ 技术栈全景

### 前端 (React SPA)

| 技术 | 版本 | 用途 |
|------|------|------|
| **React** | 19 | UI 框架 |
| **TypeScript** | 5.9 | 类型安全 |
| **Vite** | 8 | 构建工具 + 开发服务器 + SSE 代理 |
| **TailwindCSS** | 4 | 原子化样式引擎 |
| **Tiptap** | 3 | Document Studio 富文本编辑器 |
| **Zustand** | 5 | 状态管理（含 LocalStorage 持久化） |
| **React Router** | 7 | 前端路由 |
| **Recharts** | 3 | 数据可视化图表 |
| **Leaflet** | 1.9 | 地理信息地图展示 |
| **Mermaid** | 11 | 流程图/架构图渲染 |
| **Lucide React** | — | 图标库 |
| **DOMPurify** | 3 | XSS 防护 |
| **Mammoth** | 1.12 | DOCX 在线预览 |
| **Playwright** | 1.58 | E2E 自动化测试 |

### 后端 (FastAPI + Python)

| 技术 | 版本 | 用途 |
|------|------|------|
| **FastAPI** | ≥0.128 | 异步 Web 框架 |
| **Uvicorn** | 0.30 | ASGI 服务器 |
| **Pydantic Settings** | 2.5 | 配置管理 |
| **SQLite** (WAL) | — | 关系型数据（用户/项目/日志） |
| **Qdrant** | ≥1.7 | 向量数据库（Dense 1024d + Sparse） |
| **PyTorch** | — | ML 推理后端 |
| **SentenceTransformers** | ≥5.0 | BGE-M3 编码器封装 |
| **httpx** | ≥0.27 | 异步 HTTP 客户端（Ollama 通信） |
| **SSE-Starlette** | ≥3.0 | Server-Sent Events 流式推送 |
| **Celery** | ≥5.3 | 异步任务队列 |
| **Redis** | ≥5.0 | 消息代理 + 缓存 |
| **PyJWT + bcrypt** | — | JWT 鉴权 + 密码哈希 |
| **PyMuPDF** | ≥1.24 | PDF 文本/表格提取 |
| **Unstructured** | ≥0.16 | Office 文档解析（docx/xlsx/pptx） |
| **GeoPandas + pyogrio** | — | GIS 数据处理（Shapefile/GDB/MDB） |
| **Tesseract OCR** | — | 图片文字识别（中英文） |

### 文档导出引擎 (C# / .NET)

| 技术 | 版本 | 用途 |
|------|------|------|
| **.NET SDK** | 8.0 | 运行时 |
| **DocumentFormat.OpenXml** | 3.0.2 | 纯血 OpenXML 文档渲染 |
| **KimiDocx** | 自研 | 商用级三线表、封面、目录、图表生成 |

### AI 大模型

| 模型 | 参数规模 | 用途 |
|------|---------|------|
| **Qwen3.6-35B-A3B** | 35B (Q4/Q8) | 主力生成模型（当前默认） |
| **Qwen3.5-35B** | 35B (Q4/Q8) | 备选生成模型 |
| **DeepSeek-R1** | 32B | 深度推理模型 |
| **BAAI/bge-m3** | 568M | 多语言嵌入（Dense 1024d + Sparse） |
| **BAAI/bge-reranker-v2-m3** | ~300M | 交叉编码器精排 |

### DevOps 基础设施

| 技术 | 版本 | 用途 |
|------|------|------|
| **Docker** (OrbStack) | — | 容器编排引擎 |
| **Ubuntu** | 22.04 LTS | 容器基础镜像 (ARM64) |
| **PM2** | — | 进程守护（4 服务常驻） |
| **FRP** | 0.56 | 内网穿透隧道 |
| **Node.js** | 20.x | 前端运行时 |
| **OpenSSH** | — | 远程开发通道 |

---

## 🧠 RAG 检索管线（五级流水线）

```
用户查询
    │
    ▼
┌──────────────────────────────────────────────────┐
│  Stage 1: 多级索引预筛选                           │
│  搜索 doc_summary 确定最相关的 Top-K 文件           │
│  → 防止跨文件数据串联污染                           │
└────────────────────┬─────────────────────────────┘
                     ▼
┌──────────────────────────────────────────────────┐
│  Stage 2: Dense + Sparse 混合检索                 │
│  BGE-M3 Dense (1024d, 语义匹配)                   │
│  BGE-M3 Sparse (词级精确匹配)                      │
│  → RRF (Reciprocal Rank Fusion) 融合排序          │
└────────────────────┬─────────────────────────────┘
                     ▼
┌──────────────────────────────────────────────────┐
│  Stage 3: Reranker 精排                           │
│  BGE-Reranker-v2-m3 交叉编码器逐对打分              │
│  → 区分"泛泛提及"与"包含实际设计参数"               │
└────────────────────┬─────────────────────────────┘
                     ▼
┌──────────────────────────────────────────────────┐
│  Stage 4: 上下文增强（邻域膨胀）                    │
│  拉取命中 chunk 的前后相邻切片                      │
│  → 补齐表头、脚注等被切片切断的边界信息              │
└────────────────────┬─────────────────────────────┘
                     ▼
┌──────────────────────────────────────────────────┐
│  Stage 5: 相邻合并 + 内容去重                      │
│  同文件连续 chunk 合并为完整文本块                   │
│  重叠度 >70% 的冗余 chunk 去重                     │
└────────────────────┬─────────────────────────────┘
                     ▼
            LLM 生成 / 问答
```

### 智能切片引擎

- **语义感知切片**：按段落（空行）→ 章节标题 → 句末标点三级优先级切割
- **表格原子保护**：Markdown 表格行被视为不可分割单元，整表进入单个 chunk
- **多级索引**：每个文件自动生成 `doc_summary` 摘要 Point，用于粗粒度文档级检索

### 动态检索增强机制

- **全局项目元数据注入**：针对“章节标题语义检索盲区”，利用宽泛数据关键词进行二次 RAG 检索，确保地价、面积、统计指标等核心量化数据始终被 LLM 捕获。
- **地名正字约束校对**：从 RAG 检索参考资料中动态提取高频地名，强行注入 Prompt，彻底杜绝中文大语言模型常犯的同音字替代错误（如“蓬溪”写成“彭溪”）。

### GPU 推理调度器

- 基于最小堆的优先级调度，保证聊天问答（PRIORITY_HIGH）优先于批量段落生成（PRIORITY_LOW）获得 GPU 推理槽位
- 与 Ollama `NUM_PARALLEL=2` 协同，应用层控制并发上限
- 支持客户端中途断开时的槽位安全回收

---

## ✨ 核心功能模块

### 📂 全景工程目录解析
- 前端基于 `webkitdirectory` 原生支持，直接拖拽上传嵌套工程文件夹
- 使用 `MD5(project_id + relative_path)` 生成文件全球唯一散列标识

### ✍️ Document Studio 智能文档编排台
- **长文编辑器**：基于 Tiptap 3 的流文本大屏面板，所见即所得
- **抗掉电持久化**：Zustand 本地持久化 + `try/finally` 异步解锁机制
- **流式无缝渲染防截断**：消除 `useEffect` 状态卸载与组件同步间的 Race Condition，保障长段落文本输出不再吞字清空。
- **一键串行生成**：通过 `forwardRef` 透传，串行触发大模型撰写各级大纲
- **结构性标题跳过机制**：自动比对范文结构，精准跳过不包含正文内容的纯目录型大章节。
- **精准图件占位**：仅当参考范文中本章节真实包含图片时，才在末尾智能生成 `[插入图件：...]` 标记。
- **五种生成模式**：
  - `PARAGRAPH` — 标准 RAG 段落生成
  - `DUAL_TRACK` — 项目事实 + 范文风格双轨注入
  - `REPLACE` — 范文底稿智能替换（仅换地名/数据）
  - `CLONE` — 范文精确复刻（逐句 1:1 替换）
  - `CHAT` — 知识库问答

### 🤖 AI Agent 对话
- 四种对话模式：⚡快速 / 🧠深度思考 / 👷工程专家 / 🤖通用AI
- **`<think>` 推演流透传**：将模型内部冗长的深度推演链通过 `format` 模式转化为 Markdown 引用块直达前端，保持 SSE 连接活跃以防超时死锁。
- **FSM 实时拦截**：针对简单问候及 `fast` 模式，采用指令级（`/no_think`）与流拦截双重保险，将 TTFT 压制到毫秒级。
- 每项目独立 AI 人格（aiPersona），隔离不同项目的对话风格

### 🕹️ C# 高级渲染与导出
- .NET 8.0 SDK (KimiDocx) 生成商用级别 Word 文档
- 支持动态封面、目录体系、三线表、环霸统计图
- 导出后自动注入 AI 审阅批注 + 质检预演
- Celery 异步执行，实时进度百分比回传前端

### 📄 多模态文件提取器
| 格式 | 处理方式 |
|------|---------|
| PDF | PyMuPDF 文本 + 表格结构化提取 |
| DOCX/XLSX/PPTX | Unstructured 引擎解析 |
| XLS/DOC | xlrd / antiword 兼容 |
| DWG/DXF | 自研 dwg2dxf 工具 + ezdxf SVG 渲染 |
| Shapefile/GDB/MDB | GeoPandas + pyogrio GIS 解析 |
| 图片 (JPG/PNG/TIFF) | Tesseract OCR（中英双语） |
| 纯文本 (TXT/CSV/JSON/XML/HTML) | 直读 |

### 🔐 安全与权限
- JWT HS256 鉴权（7 天有效期）
- 角色访问控制：admin / user / pending
- 项目级权限隔离（owner + visibility）
- ReadOnly 中间件（守护外挂存储状态）
- 代理环境变量全局清除（防止 Docker 注入 SOCKS 代理干扰内网通信）

---

## 🏗️ 容器化微服务拓扑

### 🐳 容器角色

| 容器 | 基础镜像 | 职责 |
|------|---------|------|
| **RAG-Server** | Ubuntu 22.04 (ARM64) | 核心中枢：FastAPI + Vite + Celery + FRPC + OpenSSH, PM2 常驻守护 |
| **RAG-Redis** | Alpine | Celery 消息队列 + 缓存 |
| **RAG-Database** | Qdrant 官方镜像 | 向量存储（Dense 1024d + Sparse，RRF 融合检索） |

### PM2 守护进程编排

| 进程名 | 类型 | 端口 | 内存上限 |
|--------|------|------|---------|
| `shengyao-backend` | Uvicorn (FastAPI) | 8001 | 8G |
| `shengyao-frontend` | Vite Preview | 2026 | 1G |
| `shengyao-celery` | Celery Worker | — | 8G |
| `rag-frpc` | FRP Client | — | — |

### 存储策略

- **RAID 外置卷** (`/Volumes/SYRAID/RAG_Files`)：海量上传文件 + SQLite 数据库
- **本地降级** (`backend/local_data`)：RAID 不可用时自动切换
- **自动探测**：启动时写入测试文件验证 RAID 可用性与权限

---

## 📁 项目目录结构

```
/app
├── README.md                       # 本架构指南
├── CHANGELOG.md                    # 变更日志
├── Structure.md                    # 容器白皮书
├── Dockerfile                      # 容器构建定义
├── ecosystem.config.js             # PM2 进程编排配置
├── start.sh                        # 容器启动入口
├── Records/                        # Micro-Checkpoint Protocol（工作状态追溯）
│
├── frontend/                       # React 前端 (Vite + TypeScript)
│   ├── src/
│   │   ├── App.tsx                 # 主应用（路由 + 布局）
│   │   ├── components/
│   │   │   ├── DocumentStudio/     # Tiptap 文档编排台
│   │   │   ├── AgentChat/          # AI 对话面板
│   │   │   ├── FileUploader/       # 工程目录上传
│   │   │   ├── FilePreviewer/      # 文件在线预览
│   │   │   ├── TreeView/           # 文件树浏览器
│   │   │   ├── KnowledgeBasePanel/ # 知识库数据看板
│   │   │   ├── TemplateManager/    # 大纲模板管理
│   │   │   ├── Auth/               # 登录/注册
│   │   │   ├── Admin/              # 后台管理
│   │   │   └── ...
│   │   └── store/
│   │       ├── authStore.ts        # JWT 鉴权状态
│   │       └── projectStore.ts     # 项目/画布/模板持久化状态
│   └── vite.config.ts              # Vite + SSE 代理配置
│
├── backend/                        # FastAPI Python 后端
│   ├── main.py                     # 应用入口 + 中间件 + 预热
│   ├── worker.py                   # Celery 异步任务（文档处理 + DOCX 生成）
│   ├── requirements.txt            # Python 依赖清单
│   ├── api/                        # API 路由层
│   │   ├── auth.py                 # 认证接口
│   │   ├── admin.py                # 管理后台接口
│   │   ├── files.py                # 文件管理接口
│   │   ├── generate.py             # SSE 流式生成接口
│   │   ├── export.py               # DOCX 异步导出接口
│   │   ├── knowledge.py            # 知识库检索接口
│   │   ├── projects.py             # 项目 CRUD
│   │   ├── template.py             # 大纲模板接口
│   │   ├── exemplar.py             # 写作范文管理
│   │   ├── ingest.py               # 文档向量化入口
│   │   └── web_ingest.py           # 网页内容抓取入库
│   ├── core/                       # 核心引擎层
│   │   ├── llm_engine.py           # Ollama 推理封装 + GPU 调度器 + 心跳
│   │   ├── vector_store.py         # Qdrant 五级检索管线 + 语义切片
│   │   ├── reranker.py             # BGE-Reranker 交叉编码器精排
│   │   ├── think_filter.py         # <think> 标签 FSM 流式拦截器
│   │   ├── config.py               # 全局配置 (Pydantic Settings)
│   │   ├── database.py             # SQLite DAL (WAL 模式)
│   │   ├── auth_deps.py            # JWT 认证依赖注入
│   │   ├── graph_rag.py            # 图谱 RAG 预留 (Neo4j, Phase 2)
│   │   ├── extractors/             # 多模态文件提取器
│   │   │   ├── pdf.py              # PDF 提取
│   │   │   ├── office.py           # Office 文档提取
│   │   │   ├── image.py            # 图片 OCR
│   │   │   ├── cad.py              # CAD 图纸提取
│   │   │   ├── gis.py              # GIS 数据提取
│   │   │   └── plain.py            # 纯文本提取
│   │   ├── docx_charts.py          # 数据可视化图表检测
│   │   ├── docx_comments.py        # AI 审阅批注注入
│   │   ├── docx_cover.py           # 封面生成
│   │   ├── docx_validator.py       # 导出文档质检
│   │   └── watchdog.py             # 外挂存储守护 + ReadOnly 中间件
│   └── docx_builder/               # C# 高级 Word 渲染引擎
│       ├── KimiDocx.csproj         # .NET 8 项目文件
│       ├── Program.cs              # 入口 + 进度回报
│       ├── DocumentHelpers.cs      # 核心排版渲染逻辑
│       └── assets/                 # 模板资产（字体/图片）
│
├── frp_config/                     # FRP 穿透配置
├── data/                           # 挂载数据卷
├── vector_db/                      # 向量库存储卷
└── debug/                          # 开发调试脚本
```

---

## 🚀 起锚与操作指南

### 1. 业务访问入口
| 入口 | 地址 |
|------|------|
| **公网总闸** | `https://rag.liukun.com` |
| **本地调试** | `http://localhost:2028` |
| **API 文档** | `https://rag.liukun.com/api/docs` 或 `http://localhost:8003/docs` |

### 2. 宿主级操作
```bash
# 在包含 docker-compose.yml 的项目根目录执行
docker-compose up -d --build   # 拉起整套微服务网格
docker-compose down            # 优雅停机
docker-compose logs -f         # 尾随全局日志
```

### 3. 容器内操作
```bash
# 通过 SSH 进入容器 (60022 端口隧道)
ssh -p 60022 root@47.103.55.200

# PM2 操作
pm2 status          # 查看业务健康度
pm2 logs            # 监听联合日志
pm2 restart all     # 平滑重启
```

### 4. 双通道安全隧穿
| 通道 | 用途 | 访问方式 |
|------|------|---------|
| **统帅上帝舱** | 宿主管理 (docker-compose) | `ssh -p 50022 gemini@...`（容器端口 2223 映射新项目 SSH） |
| **开发直连舱** | 容器内代码编写 (/app) | `ssh -p 60022 root@47.103.55.200` |

---

## 🔥 性能瓶颈与处理规范

### 1. 显存击穿与大模型假死 (SWAP 灾难)
- **表现**：生成时前端假死转圈，推理速度断崖至 0.5 docs/s
- **根因**：过大的 `num_ctx` 撑爆 Mac Studio 统一内存，触发 SSD Swap
- **已修复**：`llm_engine.py` 硬性限制 `num_ctx=8192`，心跳机制保持模型常驻 GPU

### 2. 前端异步并发死锁 (UI Lock)
- **表现**：某接口报 500 后，"正在生成"按钮永久置灰
- **根因**：`await generate()` 未被 `try/finally` 包裹，异步队列断裂
- **已修复**：所有异步操作强制 `try {...} finally { setIsGenerating(false) }`

### 3. Zustand 草稿易失性雪崩 (Draft Loss)
- **表现**：编辑内容在 F5 刷新后丢失
- **已修复**：`templateSections` 注入 Zustand `partialize` 持久化白名单

### 4. 向量库阻塞主线程 (Event Loop Block)
- **表现**：点击生成后硬卡 3-4 秒才出首字节
- **根因**：Qdrant 离线时同步连接超时阻塞 Uvicorn 工作线程
- **已修复**：`QdrantClient` 初始化嵌入 `timeout=1.0s` 容错

### 5. 模型冷启动惩罚 (Cold Start)
- **表现**：首次推理 TTFT 高达 85 秒
- **已修复**：启动时自动预热（空 prompt 触发模型加载）+ 4 分钟间隔心跳守护

---

## 🔄 AI 状态流转机制

本工作流搭载原生 `Records/work_status.md`（Micro-Checkpoint Protocol）记忆。
> 🤖 **AI Agent 开机协议**: AI Helper 在执行任何跨会话开发前，将嗅探读取此文件继承历史上下文。

---

*本架构拓扑已于 2026 年完成全真机物理映射脱离，最终解释权归 **云南力诺科技有限公司** 独家所有。*
