# 多模态 RAG 检索增强设计与模型自适应路由实现

本系统不仅支持纯文本知识库 RAG 问答，还深度集成了针对图片（如发票、证据照片、业务标准图表、公文扫描件等）的**多模态 RAG 图文问答**功能。

本文详细总结了本系统在多模态架构设计、模型自适应探测路由，以及防非视觉节点图片污染隔离方面的关键技术实现。

---

## 1. 系统架构与多模态流

在多模态问答场景下，用户不仅输入提问，还会上传 Base64 格式的图片数据。
由于系统采用多智能体协同图（Multi-Agent Collaboration Graph）进行任务处理，如果将大体积的图片数据盲目传递给图里的每一个节点，会导致极大的网络传输负担及非多模态节点的内存枯竭。

因此，系统设计了**多模态精准路由与隔离流**：

```
                    ┌──────────────────┐
                    │ 用户输入: 问 + 图│
                    └────────┬─────────┘
                             ▼
              Go 网关: RunEinoOrchestration
                             │
       ┌─────────────────────┴─────────────────────┐
       ▼ (图片剥离与隔离)                          ▼ (视觉节点动态路由)
   Planner / Checker / Auditor 节点              Worker 节点 (加载视觉模型)
  - 显式擦除 Context 中的图片数据               - getBestMultimodalModel 智能替换
  - 只处理文本提示语以节省显存                  - 本地探测 minicpm-v / moondream
  - 防止不支持多模态的节点加载图片 OOM          - 发送 Base64 图片进行多模态直答
```

---

## 2. 核心技术实现

### 2.1 动态最佳多模态模型自适应路由（Model Adaptation）
系统在宿主机上运行了多种模型。在接收到用户传入的图片时，如果当前选择的主模型（如 21GB 的 `qwen3.6:35b-q4`）是不支持多模态的普通文本模型，Go 网关会自动触发本地多模态模型的**动态匹配算法**，将其自适应路由给本地最轻量、效果最佳的多模态视觉大模型：

在 [eino_model.go](file:///Users/gemini/Projects/Own/RAG/app-server/nexus-gateway/eino_model.go) 中：
```go
// getBestMultimodalModel 动态检测并匹配本地可用的最佳多模态视觉大模型
func getBestMultimodalModel() string {
	models := getLocalOllamaModels()
	// 匹配优先级：minicpm-v (中英双语顶尖多模态) > qwen-vl > llava > moondream
	priority := []string{"minicpm-v", "qwen", "llava", "moondream"}
	for _, pref := range priority {
		for _, m := range models {
			if strings.Contains(strings.ToLower(m), pref) {
				// 若匹配到 qwen，需确保其为 vl 多模态版本以防误判
				if pref == "qwen" && !strings.Contains(strings.ToLower(m), "vl") {
					continue
				}
				return m
			}
		}
	}
	return "minicpm-v:latest" // 默认保底模型
}
```

### 2.2 非视觉节点图片污染隔离（Context Erasure）
在 Go Eino 有向图中，`Planner` (规划者)、`Checker` (定量校验) 和 `Auditor` (定稿终审) 仅需要处理文本决策和合规审计，无需加载图片数据。
为了防止大体积的 Base64 字符串传递给这些文本模型导致 HTTP 包体过大、显存突发溢出，我们在这些 Lambda 节点入口的 `context.Context` 中进行了**图片数据的物理擦除隔离**：

在 [eino_graph.go](file:///Users/gemini/Projects/Own/RAG/app-server/nexus-gateway/eino_graph.go) 中：
```go
func plannerNode(llm *OllamaChat, namePlanner string) *compose.Lambda {
	return compose.InvokableLambda(func(ctx context.Context, input *EinoContext) (*EinoContext, error) {
		// 🌟 物理隔离：显式将 Context 中的图片键清空，防止底层通信框架向上反序列化图片数据
		ctx = context.WithValue(ctx, "chat_image", "") 
		...
		plannerMessages := []*schema.Message{
			{Role: schema.System, Content: plannerPrompt},
			{Role: schema.User, Content: enrichedMessage}, // 仅包含文本
		}
		planResp, err := llm.Generate(ctx, plannerMessages)
		...
	})
}
```
同样的隔离措施部署在 `checkerNode` 和 `auditorNode` 之前。只有真正需要进行图文识别的 `workerNode` 才会通过 `context.WithValue(ctx, "chat_image", input.Req.Image)` 重新注入图片，并在 Ollama 的请求 payload 中加入 `images` 数组实现识别。

### 2.3 多模态 Prompt 强约束与中文化（System Prompt Tuning）
针对多模态模型（如 `minicpm-v`）在识别图文信息时容易受到图片中英文偏置的影响、从而用英文回答的问题，系统在 Worker 节点的多模态系统提示词中设计了**强约束强制中文化 Prompt 模版**：

```go
workerPrompt := "你是专业的图像文本提取与公文处理专家。\n" +
	"你收到了一张公文/表格/发票或关联材料的图片，以及用户的提问。\n" +
	"【强约束命令】\n" +
	"1. 必须使用中文回答，严禁输出任何英文字词及翻译腔，确保用语符合政府公文规范。\n" +
	"2. 请仔细识别并提取图像中与用户问题关联的文字、数字、时间及印章信息。\n" +
	"3. 紧扣图像中的事实进行整理，如果图片中不存在相关信息，请直接回答'图像中未检索到相关事实'，严禁胡编乱造。"
```

---

## 3. 经验总结与日后推广
1. **多模型分工**：在私有化 RAG 中，文字分析（如法规比对）使用重型普通 LLM，图文提取（多模态）使用轻量级 Vision LLM。不要用一个大模型做所有事。
2. **零拷贝隔离**：在有向图中，必须建立上下文（Context）过滤拦截器，把非当前节点所需的大体积二进制/Base64 数据就地擦除，极大地降低微服务间的 RPC/网络传输延迟，防范大包导致的系统崩溃。
3. **本地模型优先级探测**：动态拉取物理宿主机的可用模型列表，优先路由到性能更佳的本地多模态模型（如 minicpm-v，识别精度高、推理速度极快且占用显存低）。
