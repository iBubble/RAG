package main

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"os"
	"strings"

	"github.com/cloudwego/eino/schema"
)

type EinoAgentRequest struct {
	Message        string   `json:"message"`
	ProjectID      string   `json:"project_id"`
	FileIDs        []string `json:"file_ids"`
	Model          string   `json:"model"`
	ChatMode       string   `json:"chat_mode"`
	SupervisorName string   `json:"collab_supervisor_name"`
	LegalName      string   `json:"collab_legal_name"`
	ContrarianName string   `json:"collab_contrarian_name"`
	ArbiterName    string   `json:"collab_arbiter_name"`
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


func RunEinoOrchestration(ctx context.Context, req *EinoAgentRequest, w io.Writer) error {
	nameSupervisor := req.SupervisorName
	if nameSupervisor == "" {
		nameSupervisor = "【协同】文档秘书"
	}
	nameLegal := req.LegalName
	if nameLegal == "" {
		nameLegal = "【协同】行业分析专家"
	}
	nameContrarian := req.ContrarianName
	if nameContrarian == "" {
		nameContrarian = "【协同】审查员"
	}
	nameArbiter := req.ArbiterName
	if nameArbiter == "" {
		nameArbiter = "【协同】仲裁官"
	}

	llmModel := req.Model
	if llmModel == "" {
		llmModel = "qwen3.6:35b-q4"
	}
	llm8b := NewOllamaChat("qwen3:8b")
	llm35b := NewOllamaChat(llmModel)

	writeEvent(w, "supervisor", "routing", fmt.Sprintf("🧠 %s 正在分析任务...", nameSupervisor))

	enrichedMessage := req.Message
	if len(req.FileIDs) > 0 {
		enrichedMessage = fmt.Sprintf("【系统背景】\n当前已勾选关联以下文档作为知识库参考，如果问题与这些文档、内容或专业主题相关，请调用 ask_rag_agent 以检索文档内容。\n【用户问题】\n%s", req.Message)
	}

	supSysPrompt := "你名任务编排专家（Supervisor），负责分析用户请求并分配给最合适的专家。\n" +
		"你不直接回答用户的问题，而是通过调用工具将任务委派给专业 Agent。\n\n" +
		"可用的专家 Agent：\n" +
		"- ask_rag_agent: 知识检索专家，擅长从文档库中检索事实信息\n" +
		"- ask_legal_agent: 行业分析专家，擅长行业检索、知识分析、文档起草\n" +
		"- ask_service_agent: 文档审查专家，擅长文件审查、规范合规性检查\n" +
		"- ask_data_agent: 数据分析专家，擅长 SQL 统计、表格聚合计算\n" +
		"- direct_answer: 简单问题直接回答（问候、闲聊、常识）\n\n" +
		"路由与工作流规则：\n" +
		"1. 问文档/资料内容 → ask_rag_agent\n" +
		"2. 问专业知识/政策/行业标准/文档起草 → ask_legal_agent\n" +
		"3. 问文档审查/规范合规 → ask_service_agent\n" +
		"4. 问数据统计/多少/合计/占比 → ask_data_agent\n" +
		"5. 简单问候/闲聊 → direct_answer\n" +
		"你的回答应该只包含分配的专家名字，严禁做任何多余阐述，只输出以下专家名之一：ask_rag_agent, ask_legal_agent, ask_service_agent, ask_data_agent, direct_answer。"

	messages := []*schema.Message{
		{Role: schema.System, Content: supSysPrompt},
		{Role: schema.User, Content: enrichedMessage},
	}

	supResp, err := llm8b.Generate(ctx, messages)
	if err != nil {
		return fmt.Errorf("supervisor error: %v", err)
	}

	decision := strings.TrimSpace(supResp.Content)
	fmt.Printf("[Eino-Gateway] Supervisor routing decision: %s\n", decision)

	var workerAnswer string
	isSimple := true
	workerAgentName := "【协同】直答助手"
	var sources []string

	if strings.Contains(decision, "ask_rag_agent") {
		isSimple = false
		workerAgentName = "【协同】知识检索助手"
		writeEvent(w, "rag_agent", "executing", "📋 正在调用知识检索专家进行事实检索...")

		var rErr error
		var contextText string
		contextText, sources, rErr = callPythonInternalRag(ctx, req.Message, req.ProjectID, req.FileIDs)
		if rErr != nil {
			return rErr
		}

		ragSysPrompt := "你是一名专业的知识检索与事实问答专家。基于检索结果，给出精确、有据可查的回答。回答中必须标注信息来源文件名。如果检索结果不足以回答，如实告知。严禁编造数据。"
		ragUserPrompt := fmt.Sprintf("【参考资料】\n%s\n\n【用户问题】\n%s", contextText, req.Message)

		ragMessages := []*schema.Message{
			{Role: schema.System, Content: ragSysPrompt},
			{Role: schema.User, Content: ragUserPrompt},
		}

		ragResp, err := llm35b.Generate(ctx, ragMessages)
		if err != nil {
			return err
		}
		workerAnswer = ragResp.Content

	} else if strings.Contains(decision, "ask_legal_agent") || strings.Contains(decision, "ask_service_agent") || strings.Contains(decision, "ask_data_agent") {
		isSimple = false
		workerAgentName = nameLegal
		writeEvent(w, "legal_agent", "executing", fmt.Sprintf("📋 正在调用%s起草章节...", nameLegal))

		expertSysPrompt := "你是一个数十年工作经验的资深行业分析专家。请直接给出严谨、专业的分析。"
		expertMessages := []*schema.Message{
			{Role: schema.System, Content: expertSysPrompt},
			{Role: schema.User, Content: req.Message},
		}
		expertResp, err := llm35b.Generate(ctx, expertMessages)
		if err != nil {
			return err
		}
		workerAnswer = expertResp.Content
	} else {
		writeEvent(w, "direct_answer", "executing", "📋 正在由直答助手生成回答...")
		directSysPrompt := "你是一名智能助手。对于用户的日常闲聊、简单问候或基础常识，请给予友好、礼貌的回答。"
		directMessages := []*schema.Message{
			{Role: schema.System, Content: directSysPrompt},
			{Role: schema.User, Content: req.Message},
		}
		directResp, err := llm8b.Generate(ctx, directMessages)
		if err != nil {
			return err
		}
		workerAnswer = directResp.Content
	}

	// 如果属于简单问题，或者初稿太短，跳过质疑和仲裁
	if isSimple || len(workerAnswer) < 100 {
		_ = writeSSE(w, map[string]interface{}{
			"type":    "token",
			"content": workerAnswer,
		})
		_ = writeSSE(w, map[string]interface{}{
			"type": "done",
		})
		savePythonChatCache(req, workerAnswer, sources)
		return nil
	}

	// 4. 小杠质疑
	writeEvent(w, "contrarian", "critiquing", fmt.Sprintf("🤨 %s 正在审查回答中引用的依据和逻辑...", nameContrarian))
	contrarianSysPrompt := fmt.Sprintf("你是「%s」，一名专业的批判性审查专家。请审查专家回答中引用的依据、数据或争议事实。如果发现问题，逐条列出质疑意见，标注严重程度（⚠️严重/⚡一般/💡建议）。如果回答质量良好无明显问题，回复：「✅ 审查通过，回答质量良好。」每条不超过2句话。", nameContrarian)
	contrarianUserPrompt := fmt.Sprintf("## 用户问题\n%s\n\n## 专家回答\n%s", req.Message, workerAnswer)

	contrarianMessages := []*schema.Message{
		{Role: schema.System, Content: contrarianSysPrompt},
		{Role: schema.User, Content: contrarianUserPrompt},
	}

	contrarianResp, err := llm8b.Generate(ctx, contrarianMessages)
	if err != nil {
		return err
	}
	critique := contrarianResp.Content

	critiqueStatus := "⚠️ 发现逻辑漏洞"
	if strings.Contains(critique, "审查通过") {
		critiqueStatus = "✅ 审查通过"
	}
	writeEvent(w, "contrarian", "done", critiqueStatus)

	// 5. 大BOSS 仲裁（流式）
	writeEvent(w, "arbiter", "deciding", fmt.Sprintf("👑 %s 正在进行决策并流式润色回答...", nameArbiter))

	arbiterSysPrompt := fmt.Sprintf("你是「%s」，团队的最终决策者。\n你将收到：专家回答 + 审查员的质疑。根据审查员的质疑是否成立，做出最终裁决并生成回答。直接输出最终回答，使用 Markdown 格式，不要提及内部审查过程。", nameArbiter)
	arbitrationPrompt := fmt.Sprintf("## 用户问题\n%s\n\n## %s的回答\n%s\n\n## %s的质疑意见\n%s", req.Message, workerAgentName, workerAnswer, nameContrarian, critique)

	arbiterMessages := []*schema.Message{
		{Role: schema.System, Content: arbiterSysPrompt},
		{Role: schema.User, Content: arbitrationPrompt},
	}

	streamReader, err := llm35b.Stream(ctx, arbiterMessages)
	if err != nil {
		return err
	}
	defer streamReader.Close()

	var finalAnswerBuilder strings.Builder
	for {
		msg, rErr := streamReader.Recv()
		if rErr != nil {
			if rErr == io.EOF {
				break
			}
			return rErr
		}
		_ = writeSSE(w, map[string]interface{}{
			"type":    "token",
			"content": msg.Content,
		})
		finalAnswerBuilder.WriteString(msg.Content)
	}

	writeEvent(w, "arbiter", "done", "👑 决策完成")
	_ = writeSSE(w, map[string]interface{}{
		"type": "done",
	})

	savePythonChatCache(req, finalAnswerBuilder.String(), sources)

	return nil
}

func callPythonInternalRag(ctx context.Context, query, projectID string, fileIDs []string) (string, []string, error) {
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
		return "", nil, err
	}

	url := fmt.Sprintf("%s/api/internal/rag", pythonURL)
	req, err := http.NewRequestWithContext(ctx, "POST", url, bytes.NewBuffer(jsonBytes))
	if err != nil {
		return "", nil, err
	}
	req.Header.Set("Content-Type", "application/json")

	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		return "", nil, err
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		return "", nil, fmt.Errorf("python internal rag error status: %d", resp.StatusCode)
	}

	var ragResp InternalRagResponse
	if err := json.NewDecoder(resp.Body).Decode(&ragResp); err != nil {
		return "", nil, err
	}

	var parts []string
	seen := make(map[string]bool)
	var filenames []string
	for i, doc := range ragResp.Docs {
		parts = append(parts, fmt.Sprintf("【文档 #{%d}】来源: %s\n%s", i+1, doc.Filename, doc.Content))
		if doc.Filename != "" && !seen[doc.Filename] {
			seen[doc.Filename] = true
			filenames = append(filenames, doc.Filename)
		}
	}
	return strings.Join(parts, "\n\n"), filenames, nil
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
		if err == nil {
			resp.Body.Close()
		}
	}()
}

