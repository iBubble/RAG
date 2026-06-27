package main

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"log"
	"net/http"
	"os"
	"strings"
	"time"

	"github.com/cloudwego/eino/compose"
	"github.com/cloudwego/eino/schema"
	"github.com/google/uuid"
)

// ── Eino DAG 三角色协同图 ──
// 架构：Planner(规划) → Checker(定量校验) → Auditor(定性审计)
// WHY: 取代旧的 Supervisor/Contrarian/Arbiter 四角色线性链路。
//      新架构支持 Interrupt/Resume 机制，当 Auditor 发现严重合规
//      风险时，可冻结状态到 Redis，等待人工审核后恢复执行。

type EinoAgentRequest struct {
	Message   string   `json:"message"`
	ProjectID string   `json:"project_id"`
	FileIDs   []string `json:"file_ids"`
	Model     string   `json:"model"`
	ChatMode  string   `json:"chat_mode"`
	Image     string   `json:"image"`
	// 新角色名（Go Eino DAG）
	PlannerName string `json:"planner_name"`
	CheckerName string `json:"checker_name"`
	AuditorName string `json:"auditor_name"`
	// 旧字段（向后兼容）
	SupervisorName string `json:"collab_supervisor_name"`
	LegalName      string `json:"collab_legal_name"`
	ContrarianName string `json:"collab_contrarian_name"`
	ArbiterName    string `json:"collab_arbiter_name"`
}

type InternalRagItem struct {
	Filename string `json:"filename"`
	Content  string `json:"content"`
}

type InternalRagResponse struct {
	Docs []InternalRagItem `json:"docs"`
}

func writeSSE(w io.Writer, payload map[string]interface{}) bool {
	jsonBytes, err := json.Marshal(payload)
	if err != nil {
		return false
	}
	_, err = w.Write([]byte("data: " + string(jsonBytes) + "\n\n"))
	if err != nil {
		return false
	}
	if flusher, ok := w.(http.Flusher); ok {
		flusher.Flush()
	}
	return true
}

func writeEvent(w io.Writer, agent, status, message string) bool {
	return writeSSE(w, map[string]interface{}{
		"type":    "agent_event",
		"agent":   agent,
		"status":  status,
		"message": message,
	})
}

type EinoContext struct {
	Req              *EinoAgentRequest
	Route            string
	Draft            string
	Sources          []string
	RetrievalContext []string // 新增：保存真实检索出的文本分片内容
	CheckResult      string
	FinalAnswer      string
	Interrupted      bool
	Writer           io.Writer
	TraceID          string
}

// getRetrievedDocsJSON 序列化真实检索切片或回退到文件名列表
func getRetrievedDocsJSON(input *EinoContext) string {
	if len(input.RetrievalContext) > 0 {
		b, err := json.Marshal(input.RetrievalContext)
		if err == nil {
			return string(b)
		}
	}
	b, err := json.Marshal(input.Sources)
	if err == nil {
		return string(b)
	}
	return "[]"
}

// freezeEinoState 将上下文状态冻结到 Redis（通过 Python API）
func freezeEinoState(sessionID string, req *EinoAgentRequest, draft string, checkResult string, sources []string, traceID string, retrievalContext []string) error {
	if sources == nil {
		sources = make([]string, 0)
	}
	if retrievalContext == nil {
		retrievalContext = make([]string, 0)
	}
	backendURL := os.Getenv("PYTHON_BACKEND_URL")
	if backendURL == "" {
		backendURL = "http://127.0.0.1:8002"
	}
	url := fmt.Sprintf("%s/api/internal/eino/freeze", backendURL)
	payload, err := json.Marshal(map[string]interface{}{
		"session_id":        sessionID,
		"request":           req,
		"draft":             draft,
		"check_result":      checkResult,
		"sources":           sources,
		"trace_id":          traceID,
		"retrieval_context": retrievalContext,
	})
	if err != nil {
		return err
	}
	resp, err := http.Post(url, "application/json", bytes.NewBuffer(payload))
	if err != nil {
		return err
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		body, _ := io.ReadAll(resp.Body)
		return fmt.Errorf("freeze error, status: %d, body: %s", resp.StatusCode, string(body))
	}
	return nil
}

// getFrozenState 从 Redis 中恢复已冻结的上下文（通过 Python API）
func getFrozenState(projectID string) (map[string]interface{}, error) {
	backendURL := os.Getenv("PYTHON_BACKEND_URL")
	if backendURL == "" {
		backendURL = "http://127.0.0.1:8002"
	}
	url := fmt.Sprintf("%s/api/eino/frozen/%s", backendURL, projectID)
	resp, err := http.Get(url)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("get frozen status failed: %d", resp.StatusCode)
	}
	var res map[string]interface{}
	if err := json.NewDecoder(resp.Body).Decode(&res); err != nil {
		return nil, err
	}
	if status, ok := res["status"].(string); !ok || status != "success" {
		return nil, fmt.Errorf("get frozen state fail: %v", res["message"])
	}
	data, ok := res["data"].(map[string]interface{})
	if !ok {
		return nil, fmt.Errorf("invalid data format")
	}
	return data, nil
}

// reportSpanToPython 向 Python 内部接口异步上报有向图节点性能及输入输出
func reportSpanToPython(traceID, nodeName, input, output string, startTime, endTime float64) {
	backendURL := os.Getenv("PYTHON_BACKEND_URL")
	if backendURL == "" {
		backendURL = "http://127.0.0.1:8002"
	}
	url := fmt.Sprintf("%s/api/internal/trace/span", backendURL)
	payload, err := json.Marshal(map[string]interface{}{
		"trace_id":   traceID,
		"name":       nodeName,
		"input":      input,
		"output":     output,
		"start_time": startTime,
		"end_time":   endTime,
	})
	if err != nil {
		return
	}
	// 在后台 goroutine 中发送请求，绝对不阻塞 DAG 主逻辑
	go func() {
		resp, err := http.Post(url, "application/json", bytes.NewBuffer(payload))
		if err == nil {
			resp.Body.Close()
		}
	}()
}

// reportAuditTraceToPython 向 Python 内部接口异步上报 RAG 最终审计状态
func reportAuditTraceToPython(traceID, userQuery, llmResponse, projectID, sessionID, retrievedDocs, dagNode, auditStatus, frozenState string) {
	backendURL := os.Getenv("PYTHON_BACKEND_URL")
	if backendURL == "" {
		backendURL = "http://127.0.0.1:8002"
	}
	url := fmt.Sprintf("%s/api/internal/trace/audit", backendURL)
	payload, err := json.Marshal(map[string]interface{}{
		"trace_id":       traceID,
		"user_query":     userQuery,
		"llm_response":    llmResponse,
		"project_id":     projectID,
		"session_id":     sessionID,
		"retrieved_docs": retrievedDocs,
		"dag_node":       dagNode,
		"audit_status":   auditStatus,
		"frozen_state":   frozenState,
	})
	if err != nil {
		return
	}
	go func() {
		resp, err := http.Post(url, "application/json", bytes.NewBuffer(payload))
		if err == nil {
			resp.Body.Close()
		}
	}()
}


// setLinvisStatus 通过 Python 后端将 DAG 节点状态写入 Redis
// WHY: Linvis 看板从 Redis 读取各节点状态，Go 端通过 HTTP 调用
//      Python 端的内部 API 写入，避免在 Go 端引入 Redis 客户端。
func setLinvisStatus(agent, status, msg, projectName string) {
	backendURL := os.Getenv("PYTHON_BACKEND_URL")
	if backendURL == "" {
		backendURL = "http://127.0.0.1:8002"
	}
	url := fmt.Sprintf("%s/api/internal/linvis/set-status", backendURL)
	payload, _ := json.Marshal(map[string]string{
		"agent":        agent,
		"status":       status,
		"message":      msg,
		"project_name": projectName,
	})
	go func() {
		resp, err := http.Post(url, "application/json", bytes.NewBuffer(payload))
		if err == nil {
			resp.Body.Close()
		}
	}()
}

// RunEinoOrchestration 执行 Eino DAG 三角色协同图。
func RunEinoOrchestration(ctx context.Context, req *EinoAgentRequest, w io.Writer) error {
	namePlanner := coalesce(req.PlannerName, req.SupervisorName, "【Eino】规划者")
	nameChecker := coalesce(req.CheckerName, req.ContrarianName, "【Eino】定量校验")
	nameAuditor := coalesce(req.AuditorName, req.ArbiterName, "【Eino】定性审计")

	llmModel := coalesce(req.Model, "qwen3.6:35b-q4")
	llm := NewOllamaChat(llmModel)

	g := compose.NewGraph[*EinoContext, *EinoContext]()

	_ = g.AddLambdaNode("planner", plannerNode(llm, namePlanner))
	_ = g.AddLambdaNode("worker", workerNode(llm))
	_ = g.AddLambdaNode("checker", checkerNode(llm, nameChecker))
	_ = g.AddLambdaNode("auditor", auditorNode(llm, nameAuditor))

	_ = g.AddEdge(compose.START, "planner")
	_ = g.AddEdge("planner", "worker")
	_ = g.AddEdge("worker", "checker")
	_ = g.AddEdge("checker", "auditor")
	_ = g.AddEdge("auditor", compose.END)

	r, err := g.Compile(ctx)
	if err != nil {
		return fmt.Errorf("compile graph error: %v", err)
	}

	initCtx := &EinoContext{
		Req:     req,
		Writer:  w,
		TraceID: uuid.NewString(),
	}

	if req.Image != "" {
		ctx = context.WithValue(ctx, "chat_image", req.Image)
	}

	_, err = r.Invoke(ctx, initCtx)
	return err
}

func coalesce(vals ...string) string {
	for _, v := range vals {
		if v != "" {
			return v
		}
	}
	return ""
}

func callPythonInternalRag(ctx context.Context, query, projectID string, fileIDs []string) (string, []string, []string, error) {
	pythonURL := os.Getenv("PYTHON_BACKEND_URL")
	if pythonURL == "" {
		pythonURL = "http://127.0.0.1:8002"
	}

	reqBody := map[string]interface{}{
		"query":      query,
		"project_id": projectID,
		"file_ids":   fileIDs,
		"top_k":      10,
	}
	jsonBytes, err := json.Marshal(reqBody)
	if err != nil {
		return "", nil, nil, err
	}

	url := fmt.Sprintf("%s/api/internal/rag", pythonURL)
	req, err := http.NewRequestWithContext(ctx, "POST", url, bytes.NewBuffer(jsonBytes))
	if err != nil {
		return "", nil, nil, err
	}
	req.Header.Set("Content-Type", "application/json")

	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		return "", nil, nil, err
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		return "", nil, nil, fmt.Errorf("python internal rag error: %d", resp.StatusCode)
	}

	var ragResp InternalRagResponse
	if err := json.NewDecoder(resp.Body).Decode(&ragResp); err != nil {
		return "", nil, nil, err
	}

	var parts []string
	seen := make(map[string]bool)
	var filenames []string
	var docContents []string
	for i, doc := range ragResp.Docs {
		parts = append(parts, fmt.Sprintf("【文档 #%d】来源: %s\n%s", i+1, doc.Filename, doc.Content))
		if doc.Filename != "" && !seen[doc.Filename] {
			seen[doc.Filename] = true
			filenames = append(filenames, doc.Filename)
		}
		docContents = append(docContents, doc.Content)
	}
	return strings.Join(parts, "\n\n"), filenames, docContents, nil
}

type InternalCacheSetRequest struct {
	ProjectID string   `json:"project_id"`
	Message   string   `json:"message"`
	ChatMode  string   `json:"chat_mode"`
	FileIDs   []string `json:"file_ids"`
	Answer    string   `json:"answer"`
	Sources   []string `json:"sources"`
}

func savePythonChatCache(req *EinoAgentRequest, answer string, sources []string) {
	if sources == nil {
		sources = make([]string, 0)
	}
	backendURL := os.Getenv("PYTHON_BACKEND_URL")
	if backendURL == "" {
		backendURL = "http://127.0.0.1:8002"
	}
	url := fmt.Sprintf("%s/api/internal/chat/cache/set", backendURL)

	payload := InternalCacheSetRequest{
		ProjectID: req.ProjectID,
		Message:   req.Message,
		ChatMode:  req.ChatMode,
		FileIDs:   req.FileIDs,
		Answer:    answer,
		Sources:   sources,
	}

	bodyBytes, err := json.Marshal(payload)
	if err != nil {
		return
	}

	go func() {
		resp, err := http.Post(url, "application/json", bytes.NewBuffer(bodyBytes))
		if err != nil {
			log.Printf("[Go-Gateway] ⚠️ 异步保存 Python 缓存 HTTP 失败: %v", err)
			return
		}
		defer resp.Body.Close()
		if resp.StatusCode != http.StatusOK {
			body, _ := io.ReadAll(resp.Body)
			log.Printf("[Go-Gateway] ⚠️ 异步保存 Python 缓存失败，状态码: %d, 返回: %s", resp.StatusCode, string(body))
		} else {
			log.Printf("[Go-Gateway] 💾 异步保存 Python 缓存请求成功发送")
		}
	}()
}

// ── Eino 节点 Lambda 辅助函数 ──

func plannerNode(llm *OllamaChat, namePlanner string) *compose.Lambda {
	return compose.InvokableLambda(func(ctx context.Context, input *EinoContext) (*EinoContext, error) {
		startTime := float64(time.Now().UnixNano()) / 1e9
		setLinvisStatus("planner", "working", "规划任务路由中...", input.Req.ProjectID)
		writeEvent(input.Writer, "planner", "routing", fmt.Sprintf("🧠 %s 正在分析任务...", namePlanner))

		enrichedMessage := input.Req.Message
		if len(input.Req.FileIDs) > 0 {
			enrichedMessage = fmt.Sprintf("【系统背景】\n已关联文档库作为参考。\n【用户问题】\n%s", input.Req.Message)
		}

		plannerPrompt := "你是任务规划专家（Planner），负责分析用户请求并选择执行路径。\n" +
			"可用路径：\n" +
			"- ask_rag: 知识检索（问文档/资料内容）\n" +
			"- ask_expert: 专业分析（政策/法规/文档起草）\n" +
			"- direct: 简单问答（问候/闲聊/常识）\n" +
			"只输出路径名，不做任何阐述。"

		plannerMessages := []*schema.Message{
			{Role: schema.System, Content: plannerPrompt},
			{Role: schema.User, Content: enrichedMessage},
		}
		planResp, err := llm.Generate(ctx, plannerMessages)
		if err != nil {
			return nil, err
		}
		input.Route = strings.TrimSpace(planResp.Content)
		setLinvisStatus("planner", "idle", "规划完成: "+input.Route, input.Req.ProjectID)
		endTime := float64(time.Now().UnixNano()) / 1e9
		reportSpanToPython(input.TraceID, "Planner", input.Req.Message, input.Route, startTime, endTime)
		return input, nil
	})
}

func workerNode(llm *OllamaChat) *compose.Lambda {
	return compose.InvokableLambda(func(ctx context.Context, input *EinoContext) (*EinoContext, error) {
		startTime := float64(time.Now().UnixNano()) / 1e9
		var err error
		var isSimple bool
		if strings.Contains(input.Route, "ask_rag") {
			setLinvisStatus("checker", "working", "知识检索中...", input.Req.ProjectID)
			writeEvent(input.Writer, "checker", "executing", "📋 正在检索知识库...")
			var contextText string
			var docContents []string
			contextText, input.Sources, docContents, err = callPythonInternalRag(ctx, input.Req.Message, input.Req.ProjectID, input.Req.FileIDs)
			if err != nil {
				return nil, err
			}
			input.RetrievalContext = docContents
			ragMessages := []*schema.Message{
				{Role: schema.System, Content: "你是知识检索专家。基于检索结果给出精确、有据可查的回答。标注来源文件名。严禁编造。"},
				{Role: schema.User, Content: fmt.Sprintf("【参考资料】\n%s\n\n【问题】\n%s", contextText, input.Req.Message)},
			}
			ragResp, rErr := llm.Generate(ctx, ragMessages)
			if rErr != nil {
				return nil, rErr
			}
			input.Draft = ragResp.Content
		} else if strings.Contains(input.Route, "ask_expert") {
			setLinvisStatus("checker", "working", "专家分析中...", input.Req.ProjectID)
			writeEvent(input.Writer, "checker", "executing", "📋 专家正在分析...")
			expertMessages := []*schema.Message{
				{Role: schema.System, Content: "你是资深行业分析专家，请直接给出严谨专业的分析。"},
				{Role: schema.User, Content: input.Req.Message},
			}
			expertResp, eErr := llm.Generate(ctx, expertMessages)
			if eErr != nil {
				return nil, eErr
			}
			input.Draft = expertResp.Content
		} else {
			isSimple = true
			writeEvent(input.Writer, "planner", "executing", "📋 直答中...")
			directMessages := []*schema.Message{
				{Role: schema.System, Content: "你是智能助手。请友好礼貌地回答。"},
				{Role: schema.User, Content: input.Req.Message},
			}
			directResp, dErr := llm.Generate(ctx, directMessages)
			if dErr != nil {
				return nil, dErr
			}
			input.Draft = directResp.Content
		}

		endTime := float64(time.Now().UnixNano()) / 1e9
		reportSpanToPython(input.TraceID, "Worker", input.Route, input.Draft, startTime, endTime)

		if isSimple || len(input.Draft) < 100 {
			input.FinalAnswer = input.Draft
			_ = writeSSE(input.Writer, map[string]interface{}{"type": "token", "content": input.Draft})
			_ = writeSSE(input.Writer, map[string]interface{}{"type": "done"})
			savePythonChatCache(input.Req, input.Draft, input.Sources)
			setLinvisStatus("planner", "idle", "任务完成", input.Req.ProjectID)
			
			retVal := getRetrievedDocsJSON(input)
			reportAuditTraceToPython(input.TraceID, input.Req.Message, input.Draft, input.Req.ProjectID, input.Req.ProjectID, retVal, "worker", "approved", "")
		}
		return input, nil
	})
}

func checkerNode(llm *OllamaChat, nameChecker string) *compose.Lambda {
	return compose.InvokableLambda(func(ctx context.Context, input *EinoContext) (*EinoContext, error) {
		if input.FinalAnswer != "" {
			return input, nil
		}

		startTime := float64(time.Now().UnixNano()) / 1e9
		setLinvisStatus("checker", "working", "定量规则校验中...", input.Req.ProjectID)
		writeEvent(input.Writer, "checker", "checking", fmt.Sprintf("🔍 %s 正在校验数据与格式...", nameChecker))

		checkerPrompt := fmt.Sprintf("你是「%s」，定量规则与合规校验专家。\n审查以下回答中的：\n1. 严重程序合规：是否存在剥夺申辩权、剥夺听证权或限制救济权利等严重违反行政程序法的表述；\n2. 大额处罚合规：罚款金额是否过大（例如超过100万）或超出合理裁量范围；\n3. 数字/日期/编码是否正确，法条引用编号是否存在且正确，格式是否规范。\n如果发现任何上述严重合规违规或错误，必须以“⚠️严重”开头逐条列出。如果完全合规且无问题，则回复「✅ 校验通过」。", nameChecker)
		checkerMessages := []*schema.Message{
			{Role: schema.System, Content: checkerPrompt},
			{Role: schema.User, Content: fmt.Sprintf("## 问题\n%s\n\n## 回答\n%s", input.Req.Message, input.Draft)},
		}
		checkResp, cErr := llm.Generate(ctx, checkerMessages)
		if cErr != nil {
			return nil, cErr
		}
		input.CheckResult = checkResp.Content
		fmt.Printf("[Go-Gateway] 🔍 Checker 校验输出内容为: %s\n", input.CheckResult)
		setLinvisStatus("checker", "idle", "校验完成", input.Req.ProjectID)
		endTime := float64(time.Now().UnixNano()) / 1e9
		reportSpanToPython(input.TraceID, "Checker", input.Draft, input.CheckResult, startTime, endTime)

		// 触发拦截机制
		if strings.Contains(input.CheckResult, "⚠️严重") || strings.Contains(input.CheckResult, "[INTERRUPT]") || strings.Contains(input.CheckResult, "严重") || strings.Contains(input.CheckResult, "违规") || strings.Contains(input.CheckResult, "不合规") {
			input.Interrupted = true
			setLinvisStatus("auditor", "interrupted", "发现严重合规风险，已挂起", input.Req.ProjectID)
			writeEvent(input.Writer, "auditor", "interrupted", "⚠️ 发现严重合规问题，已拦截挂起并提交法务人工审核")

			err := freezeEinoState(input.Req.ProjectID, input.Req, input.Draft, input.CheckResult, input.Sources, input.TraceID, input.RetrievalContext)
			if err != nil {
				writeEvent(input.Writer, "auditor", "error", fmt.Sprintf("❌ Redis 冻结失败: %v", err))
			}

			_ = writeSSE(input.Writer, map[string]interface{}{
				"type":         "interrupt",
				"session_id":   input.Req.ProjectID,
				"check_result": input.CheckResult,
			})

			stateMap := map[string]interface{}{
				"request":           input.Req,
				"draft":             input.Draft,
				"check_result":      input.CheckResult,
				"sources":           input.Sources,
				"trace_id":          input.TraceID,
				"retrieval_context": input.RetrievalContext,
			}
			stateJSON, _ := json.Marshal(stateMap)
			retVal := getRetrievedDocsJSON(input)
			reportAuditTraceToPython(input.TraceID, input.Req.Message, input.Draft, input.Req.ProjectID, input.Req.ProjectID, retVal, "checker", "interrupted", string(stateJSON))
		}
		return input, nil
	})
}

func auditorNode(llm *OllamaChat, nameAuditor string) *compose.Lambda {
	return compose.InvokableLambda(func(ctx context.Context, input *EinoContext) (*EinoContext, error) {
		if input.FinalAnswer != "" || input.Interrupted {
			return input, nil
		}

		startTime := float64(time.Now().UnixNano()) / 1e9
		setLinvisStatus("auditor", "working", "定性审计润色中...", input.Req.ProjectID)
		writeEvent(input.Writer, "auditor", "auditing", fmt.Sprintf("⚖️ %s 正在审计并润色最终回答...", nameAuditor))

		auditorPrompt := fmt.Sprintf("你是「%s」，最终定性审计专家。\n收到：专家回答 + 定量校验结果。\n据此做最终裁决并生成回答。直接输出 Markdown 格式回答。", nameAuditor)
		auditorInput := fmt.Sprintf("## 问题\n%s\n\n## 初稿\n%s\n\n## 定量校验\n%s", input.Req.Message, input.Draft, input.CheckResult)
		auditorMessages := []*schema.Message{
			{Role: schema.System, Content: auditorPrompt},
			{Role: schema.User, Content: auditorInput},
		}

		streamReader, sErr := llm.Stream(ctx, auditorMessages)
		if sErr != nil {
			return nil, sErr
		}
		defer streamReader.Close()

		var finalBuilder strings.Builder
		for {
			msg, rErr := streamReader.Recv()
			if rErr != nil {
				if rErr == io.EOF {
					break
				}
				return nil, rErr
			}
			_ = writeSSE(input.Writer, map[string]interface{}{"type": "token", "content": msg.Content})
			finalBuilder.WriteString(msg.Content)
		}

		input.FinalAnswer = finalBuilder.String()
		setLinvisStatus("auditor", "idle", "审计完成", input.Req.ProjectID)
		writeEvent(input.Writer, "auditor", "done", "⚖️ 审计完成")
		_ = writeSSE(input.Writer, map[string]interface{}{"type": "done"})

		endTime := float64(time.Now().UnixNano()) / 1e9
		reportSpanToPython(input.TraceID, "Auditor", auditorInput, input.FinalAnswer, startTime, endTime)

		savePythonChatCache(input.Req, input.FinalAnswer, input.Sources)
		retVal := getRetrievedDocsJSON(input)
		reportAuditTraceToPython(input.TraceID, input.Req.Message, input.FinalAnswer, input.Req.ProjectID, input.Req.ProjectID, retVal, "auditor", "pending", "")
		return input, nil
	})
}

func RunEinoResumeOrchestration(ctx context.Context, req *EinoAgentRequest, draft string, checkResult string, sources []string, w io.Writer, traceID string, retrievalContext []string) error {
	startTime := float64(time.Now().UnixNano()) / 1e9
	nameAuditor := coalesce(req.AuditorName, req.ArbiterName, "【Eino】定性审计")
	llmModel := coalesce(req.Model, "qwen3.6:35b-q4")
	llm := NewOllamaChat(llmModel)

	setLinvisStatus("auditor", "working", "人工审批通过，定性审计润色中...", req.ProjectID)
	writeEvent(w, "auditor", "auditing", fmt.Sprintf("⚖️ %s 正在根据审批后的初稿进行最终审计并润色...", nameAuditor))

	auditorPrompt := fmt.Sprintf("你是「%s」，最终定性审计专家。\n收到：人工批准/修改后的回答草稿 + 定量校验结果。\n据此做最终裁决并生成回答。直接输出 Markdown 格式回答。", nameAuditor)
	auditorInput := fmt.Sprintf("## 问题\n%s\n\n## 人工审批后的草稿\n%s\n\n## 原定量校验结果\n%s", req.Message, draft, checkResult)
	auditorMessages := []*schema.Message{
		{Role: schema.System, Content: auditorPrompt},
		{Role: schema.User, Content: auditorInput},
	}

	streamReader, sErr := llm.Stream(ctx, auditorMessages)
	if sErr != nil {
		return sErr
	}
	defer streamReader.Close()

	var finalBuilder strings.Builder
	for {
		msg, rErr := streamReader.Recv()
		if rErr != nil {
			if rErr == io.EOF {
				break
			}
			return rErr
		}
		_ = writeSSE(w, map[string]interface{}{"type": "token", "content": msg.Content})
		finalBuilder.WriteString(msg.Content)
	}

	setLinvisStatus("auditor", "idle", "审计完成", req.ProjectID)
	writeEvent(w, "auditor", "done", "⚖️ 审计完成")
	_ = writeSSE(w, map[string]interface{}{"type": "done"})

	endTime := float64(time.Now().UnixNano()) / 1e9
	reportSpanToPython(traceID, "Auditor_Resume", auditorInput, finalBuilder.String(), startTime, endTime)

	savePythonChatCache(req, finalBuilder.String(), sources)

	var retVal string
	if len(retrievalContext) > 0 {
		b, err := json.Marshal(retrievalContext)
		if err == nil {
			retVal = string(b)
		}
	}
	if retVal == "" {
		b, err := json.Marshal(sources)
		if err == nil {
			retVal = string(b)
		} else {
			retVal = "[]"
		}
	}
	reportAuditTraceToPython(traceID, req.Message, finalBuilder.String(), req.ProjectID, req.ProjectID, retVal, "auditor_resume", "pending", "")
	return nil
}


