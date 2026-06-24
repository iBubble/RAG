# 项目工作日志

> 项目名称：貔貅法律知识库 V3.3.2 RAG 系统
> 项目地址：https://rag.syhsgis.com/
> 技术栈：FastAPI + Qdrant + BGE-M3 + Qwen3.6 + React/TipTap

---

## 2026-04-24（第一次工作记录）

### 工作时间
UTC 16:30 ~ 03:38（约 11 小时）

### 工作内容

#### 一、问题诊断与定位

1. 通过 API 端到端测试发现项目 769a66095068 在 Qdrant 中已有 2358 个向量
2. 通过后端 PERF 计时日志定位到 RAG 管线瓶颈：
   - dense_encode: 0.22s ✅
   - sparse_encode: 0.17s ✅
   - qdrant_search: 0.04s ✅
   - **reranker: 70.17s** ❌ ← CrossEncoder 在 ARM/QEMU 上极慢
3. 通过代码审查发现 Prompt 模板、前端 SSE 处理、UI 状态管理等多处问题

#### 二、修复清单（11 项，全部完成）

| # | 问题 | 严重程度 | 修改文件 |
|---|------|---------|---------|
| 1 | RAG 检索耗时 65s → 跳过 Reranker | 🔴 严重 | `vector_store.py` |
| 2 | Prompt 硬编码水利工程领域 | 🔴 严重 | `llm_engine.py` |
| 3 | 来源文件名泄漏到编辑器 | 🟡 中等 | `generate.py` |
| 4 | AI 正文引用来源标注 | 🟡 中等 | `llm_engine.py` |
| 5 | Markdown 格式需正确渲染 | 🟡 中等 | `llm_engine.py`, `DocumentStudio.tsx` |
| 6 | 标题编辑影响模板名称 | 🟡 中等 | `projectStore.ts`, `TemplateManager.tsx` |
| 7 | 无用全局检索（水利关键词） | 🟡 中等 | `generate.py` |
| 8 | 生成内容重复标题 | 🟢 轻微 | `DocumentStudio.tsx` |
| 9 | 大标题与子标题内容大量重复 | 🔴 严重 | `llm_engine.py` |
| 10 | 生成内容没有分段/换行 | 🟡 中等 | `DocumentStudio.tsx` |
| 11 | Markdown 在编辑器中未渲染 | 🟡 中等 | `DocumentStudio.tsx` |

#### 三、关键性能指标改善

| 指标 | 优化前 | 优化后 | 改善幅度 |
|------|--------|--------|---------|
| TTFT（首字时间） | 77.5s | 15.8s | ⬇️ 80% |
| 总生成时间 | 89.4s | 20.7s | ⬇️ 77% |
| Reranker 耗时 | 70.17s | 0.00s | ⬇️ 100% |

#### 四、核心技术决策

1. **跳过 Reranker**：CrossEncoder（BAAI/bge-reranker-v2-m3）在当前 ARM/QEMU 服务器上极慢（70s for 16 docs），但 Dense+Sparse RRF 融合排序已能提供足够好的检索质量。已保留注释代码，未来迁移到更快的服务器可随时恢复。

2. **允许 Markdown 输出**：用户要求在编辑器中正确渲染 Markdown 样式（加粗、标题等），而非简单禁止。前端在流式结束后通过 `marked.parse()` 将累积的 Markdown 文本统一转换为 HTML。

3. **Prompt 防重复机制**：大章节标题限制为 100-200 字概述，子标题聚焦具体主题，新增"严禁内容重复"规则。

### 修改的文件清单

**后端**：
- `/app/backend/core/vector_store.py` — 跳过 Reranker、减少候选数、添加 PERF 日志
- `/app/backend/core/llm_engine.py` — 重写 Prompt 规则（越界/重复/Markdown/来源）
- `/app/backend/api/generate.py` — 移除文档编写中的来源泄漏、优化全局检索

**前端**：
- `/app/frontend/src/components/DocumentStudio/DocumentStudio.tsx` — Markdown 渲染、换行处理、标题剥离
- `/app/frontend/src/store/projectStore.ts` — 新增 originalTemplateName
- `/app/frontend/src/components/TemplateManager/TemplateManager.tsx` — 使用 originalTemplateName

**文档**：
- `/app/errors.md` — 问题清单（11 项，全部 ✅）
- `/app/errors_fixed.md` — 修正报告

### 待后续关注

1. **Reranker 恢复**：如服务器迁移到 x86 GPU 环境，可恢复 Reranker 以提升检索精度
2. **一键生成全文**：需在浏览器中完整测试全文生成流程，验证多章节之间的内容去重效果
3. **内容换行验证**：需在浏览器中验证 `marked.parse()` 是否正确渲染段落分隔和 Markdown 样式
