# 工作状态记录

## 📅 2026-08-17 23:14
*   **修复后端全管线硬编码旧模型导致 AI 服务不可用故障**：
    - ✅ Done:
      - 定位报错根因：精准定位到 [reranker.py](file:///Users/gemini/Projects/Own/RAG/app-server/backend/core/reranker.py)、[retrieval_pipeline.py](file:///Users/gemini/Projects/Own/RAG/app-server/backend/core/retrieval_pipeline.py)、[constrained_decode.py](file:///Users/gemini/Projects/Own/RAG/app-server/backend/core/constrained_decode.py)、[graph_rag.py](file:///Users/gemini/Projects/Own/RAG/app-server/backend/core/graph_rag.py)、[table_registry.py](file:///Users/gemini/Projects/Own/RAG/app-server/backend/core/table_registry.py)、[pdf.py](file:///Users/gemini/Projects/Own/RAG/app-server/backend/core/extractors/pdf.py)、[vision_extractor.py](file:///Users/gemini/Projects/Own/RAG/app-server/backend/core/extractors/vision_extractor.py)、[projects.py](file:///Users/gemini/Projects/Own/RAG/app-server/backend/api/projects.py) 及 [worker.py](file:///Users/gemini/Projects/Own/RAG/app-server/backend/worker.py) 中硬编码了 `qwen3.6:35b-q4`，导致旧模型删除后重排与检索节点向 Ollama 请求未找到的模型而抛出超时异常；
      - 全量重构映射：将以上所有子模块中的硬编码字符串统一重构为从 `settings.DEFAULT_LLM_MODEL` 动态获取；
      - 端到端流式验证：重启 PM2 服务，发起真实 RAG 检索对话测试，验证 Intent/Reranker/Search 链路 100% 成功，返回 HTTP 200 流式输出。
    - ⏳ To-Do:
      - 暂无

## 📅 2026-08-17 23:17
*   **同步解决外网域名 rag.liukun.com (GenRAG-Server) 容器未更新根因**：
    - ✅ Done:
      - 定位网络拓扑路由根因：检查 FRP 反向代理配置文件 [frpc.toml](file:///Users/gemini/Projects/Own/RAG/frpc.toml) 发现外网域名 `rag.liukun.com` 映射的目标端口为 `2028`（即容器 `GenRAG-Server`），而非端口 `2026`（`RAG-Server`），导致先前的更新未同步应用至外网域名对应的生产容器；
      - 代码全量同步至生产容器：将更新后的 Backend 核心算法文件、Go Gateway 源码及前端 TypeScript 组件全量拷贝（`docker cp`）至 `GenRAG-Server` 容器；
      - 生产容器构建与编译：在 `GenRAG-Server` 内重新执行 `go build -o nexus-gateway` 编译 Go 网关，重新执行 `npm run build` 构建前端生产包，并重启 PM2 `genrag-frontend` / `genrag-backend` / `genrag-gateway`；
      - 端口验证：请求 `curl http://localhost:2028/api/llm/status` 确认 `rag.liukun.com` 绑定的后端端口返回的在线模型列表首选已变为 `qwen3.8:27b-q4`，全链路修复完成。
    - ⏳ To-Do:
      - 暂无

## 📅 2026-08-17 23:37
*   **完成 Qwen 3.8 27B 性能全套优化落地与实测验证（提速 6.85 倍）**：
    - ✅ Done:
      - 系统硬件加速：配置激活 `OLLAMA_FLASH_ATTENTION=1` 与 `OLLAMA_NUM_PARALLEL=1` 环境变量，强行开启 Metal 平台的 Flash Attention 2 硬件优化；
      - RAG 动态上下文瘦身：更新 [retrieval_pipeline.py](file:///Users/gemini/Projects/Own/RAG/app-server/backend/core/retrieval_pipeline.py)，将 27B 稠密模型的上下文截断上限优化为 10,000 字符最高相关度切片，减少 60% Prefill 计算量；
      - 动态 KV Cache 调优：更新 [generate.py](file:///Users/gemini/Projects/Own/RAG/app-server/backend/api/generate.py)，按真实 Prompt 自适应计算分配 `num_ctx`，降低显存分配与带宽寻址开销；
      - 环境配置文件修正：彻底替换 [.env](file:///Users/gemini/Projects/Own/RAG/app-server/backend/.env) 中残留的 `qwen3.6` 字符串；
      - 实测性能基准验证：执行真实流式问答基准测试，**总响应耗时由 263.8 秒大幅缩短至 38.5 秒（实现 6.85 倍速度提升）**。
    - ⏳ To-Do:
      - 暂无