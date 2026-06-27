# 深度思考（Smart）模式架构设计与 Multi-Agent 协同图编排

在智能体通用知识库 RAG 系统中，除了普通的“快速直答”模式外，还针对复杂的公文起草、政策冲突比对等场景，设计了 **“深度思考（Smart）模式”**。

本文详细总结了该模式背后的双层控制流与数据流后端架构设计，以及基于 Go Eino 拓扑编排的 Multi-Agent 协同工作机制。

---

## 1. 深度思考后端架构设计

深度思考模式采用了 **“Go 高并发网关 + Python 算法微服务”** 的混合双层架构。

```
                    ┌────────────────────────┐
                    │  用户客户端 (React App) │
                    └───────────┬────────────┘
                                │ (SSE 保持连接)
                                ▼
         ┌──────────────────────────────────────────────┐
         │     Go 核心网关 (Nexus-Gateway, Gin 路由)     │
         │ - Eino 拓扑有向无环图 (DAG) 状态机编排          │
         │ - 管理 SSE 数据流与级联取消（AbortSignal）     │
         └──────────────┬────────────────┬──────────────┘
                        │                │
     (RPC/HTTP 并行调用)│                │ (异步上报 LinvisStatus)
                        ▼                ▼
         ┌────────────────────────┐    ┌────────────────────────┐
         │     Python 算法后端    │    │     Python 协同大屏     │
         │  - 复杂向量与图谱检索   │    │  - 实时监控状态展示大屏│
         │  - 原生 Word 修改批注  │    │  - /api/internal/...   │
         └────────────────────────┘    └────────────────────────┘
```

* **Go 核心网关（控制流）**：负责拦截高并发的网络连接（JWT 校验、限流防刷、维持长连接通道）。流式聊天使用字节跳动的 Eino 编排框架，在内存中维护有向无环图（DAG）。通过 Eino 可轻松实现对底层 LLM 调用过程中的流式拦截、中途用户强行阻断、以及节点级联取消，防止显存算力空转。
* **Python 算法微服务（数据流）**：承载重型的离线算法（如 Whisper 语音识别、Tesseract OCR 复杂多模态解析、Neo4j 图关系扩散以及 Word 原生红线修订 XML 组装等），由 Go 后端通过非阻塞的 HttpClient 泛路由网关代理或 RPC 方式进行调用，实现动静分离与逻辑隔离。

---

## 2. 基于 Go Eino 的 Multi-Agent 协同图编排

深度思考的核心是一个由四个智能体节点组成的有向图（DAG），在 [eino_graph.go](file:///Users/gemini/Projects/Own/RAG/app-server/nexus-gateway/eino_graph.go) 中构建：

```
    ┌───────────┐      ┌───────────┐      ┌───────────┐      ┌───────────┐
───►│  Planner  ├─────►│  Worker   ├─────►│  Checker  ├─────►│  Auditor  ├────► (Done)
    │ (规划路由) │      │ (草稿撰写) │      │ (数据校验) │      │ (审计定稿) │
    └───────────┘      └───────────┘      └───────────┘      └───────────┘
```

1. **Planner (规划决策者)**：
   分析用户意图，对 Query 进行语义校正与知识扩散，选择执行路径：是进行知识库 RAG 检索（`ask_rag`）、调用专业算法模型起草（`ask_expert`），还是直接回复（`direct`）。
2. **Worker (草稿撰写者)**：
   负责核心知识内容的生成。如果是 `ask_rag`，它会异步并发调用 Python 后端的六路并行 RAG 检索管线（Qdrant + Neo4j + SQLite FTS5），拉取高价值上下文，撰写详尽的初稿。
3. **Checker (定量数据校验者)**：
   提取初稿中的核心数据（如金钱、时间、政策代号等），与检索到的知识库原始分片进行逐字对齐校验，发现虚假捏造、不一致的幻觉时，输出包含警告提示的定量校验报告。
4. **Auditor (定性终审定稿者)**：
   作为最终的“公文终审员”，接受 Worker 产出的初稿和 Checker 产出的校验警告，站在公文规章的合规性角度做定性润色与整合，消除所有的审理、仲裁等敏感司法用词，输出最纯净的 Markdown 格式定稿回复送给前端。

---

## 3. 林维斯协同状态监视上报（Linvis Integration）

为了能让外界（如管理大屏、协同工作室）实时监控当前节点在图里的跃迁状态，系统设计了 **Linvis 状态监视链路**。
在 Eino 图的每个 Lambda 节点被触发以及结束时，都会异步向 Python 后端上报当前的状态：

```go
func setLinvisStatus(agent, status, msg, projectName string) {
	backendURL := os.Getenv("PYTHON_BACKEND_URL")
	...
	url := fmt.Sprintf("%s/api/internal/linvis/set-status", backendURL)
	payload, _ := json.Marshal(map[string]string{
		"agent":        agent,       // 如 "planner", "checker", "auditor"
		"status":       status,      // 如 "working", "idle"
		"message":      msg,         // 节点当前的具体工作内容，如 "正在校验数据..."
		"project_name": projectName,  // 项目唯一标识符
	})
	go func() {
		resp, err := http.Post(url, "application/json", bytes.NewBuffer(payload))
		if err == nil {
			resp.Body.Close()
		}
	}()
}
```
* **意义**：这一设计解耦了前端 SSE 状态与后台物理协同看板状态，支持了大屏展示以及智能体圆桌协同的多方监控。

---

## 4. 推广与沉淀价值
* **强强联合**：Go + Python 混合架构，用 Go 做 Eino DAG 拓扑编排、连接控制和网关反向代理，用 Python 跑复杂数据模型和离线计算，在 RAG 项目中极具推广价值。
* **分阶段流式控制**：复杂 RAG 容易生成长篇废话。利用 Planner 过滤、Checker 挤出幻觉水分、Auditor 公文合规审查的渐进式 DAG 设计，确保了私有化大模型输出的高纯度和高可靠性。
