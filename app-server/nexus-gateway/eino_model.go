package main

import (
	"bufio"
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"os"
	"strings"

	"github.com/cloudwego/eino/components/model"
	"github.com/cloudwego/eino/schema"
)

type OllamaChat struct {
	BaseURL string
	Model   string
}

type OllamaMessage struct {
	Role    string   `json:"role" xml:"role"`
	Content string   `json:"content" xml:"content"`
	Images  []string `json:"images,omitempty"`
}

type OllamaChatRequest struct {
	Model    string          `json:"model"`
	Messages []OllamaMessage `json:"messages"`
	Stream   bool            `json:"stream"`
}

type OllamaChatResponse struct {
	Message OllamaMessage `json:"message"`
	Done    bool          `json:"done"`
}

func NewOllamaChat(modelName string) *OllamaChat {
	baseURL := os.Getenv("OLLAMA_BASE_URL")
	if baseURL == "" {
		baseURL = "http://host.docker.internal:11434"
	}
	return &OllamaChat{
		BaseURL: baseURL,
		Model:   modelName,
	}
}

func (o *OllamaChat) Generate(ctx context.Context, input []*schema.Message, opts ...model.Option) (*schema.Message, error) {
	imageVal := ctx.Value("chat_image")
	var images []string
	if imageVal != nil {
		if base64Str, ok := imageVal.(string); ok && base64Str != "" {
			cleaned := base64Str
			if idx := strings.Index(base64Str, ","); idx != -1 {
				cleaned = base64Str[idx+1:]
			}
			images = []string{cleaned}
		}
	}

	reqBody := OllamaChatRequest{
		Model:    o.Model,
		Messages: make([]OllamaMessage, len(input)),
		Stream:   false,
	}
	for i, msg := range input {
		reqBody.Messages[i] = OllamaMessage{
			Role:    string(msg.Role),
			Content: msg.Content,
		}
		if i == len(input)-1 && string(msg.Role) == "user" && len(images) > 0 {
			reqBody.Messages[i].Images = images
		}
	}
	jsonBytes, err := json.Marshal(reqBody)
	if err != nil {
		return nil, err
	}
	url := fmt.Sprintf("%s/api/chat", o.BaseURL)
	req, err := http.NewRequestWithContext(ctx, "POST", url, bytes.NewBuffer(jsonBytes))
	if err != nil {
		return nil, err
	}
	req.Header.Set("Content-Type", "application/json")
	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()
	if resp.StatusCode != http.StatusOK {
		body, _ := io.ReadAll(resp.Body)
		bodyStr := string(body)
		if strings.Contains(bodyStr, "image input is not supported") || strings.Contains(bodyStr, "mmproj") {
			return nil, fmt.Errorf("【模型不支持多模态】您当前选择的模型 %s 为纯文本模型，不支持图片输入。请在左下角配置中切换为支持视觉的多模态模型（如 moondream、minicpm-v），或者在宿主机运行 `ollama run moondream` 拉取后重试", o.Model)
		}
		return nil, fmt.Errorf("ollama response error: %s", bodyStr)
	}
	var chatResp OllamaChatResponse
	if err := json.NewDecoder(resp.Body).Decode(&chatResp); err != nil {
		return nil, err
	}
	return &schema.Message{
		Role:    schema.RoleType(chatResp.Message.Role),
		Content: chatResp.Message.Content,
	}, nil
}

func (o *OllamaChat) Stream(ctx context.Context, input []*schema.Message, opts ...model.Option) (*schema.StreamReader[*schema.Message], error) {
	imageVal := ctx.Value("chat_image")
	var images []string
	if imageVal != nil {
		if base64Str, ok := imageVal.(string); ok && base64Str != "" {
			cleaned := base64Str
			if idx := strings.Index(base64Str, ","); idx != -1 {
				cleaned = base64Str[idx+1:]
			}
			images = []string{cleaned}
		}
	}

	reqBody := OllamaChatRequest{
		Model:    o.Model,
		Messages: make([]OllamaMessage, len(input)),
		Stream:   true,
	}
	for i, msg := range input {
		reqBody.Messages[i] = OllamaMessage{
			Role:    string(msg.Role),
			Content: msg.Content,
		}
		if i == len(input)-1 && string(msg.Role) == "user" && len(images) > 0 {
			reqBody.Messages[i].Images = images
		}
	}
	jsonBytes, err := json.Marshal(reqBody)
	if err != nil {
		return nil, err
	}
	url := fmt.Sprintf("%s/api/chat", o.BaseURL)
	req, err := http.NewRequestWithContext(ctx, "POST", url, bytes.NewBuffer(jsonBytes))
	if err != nil {
		return nil, err
	}
	req.Header.Set("Content-Type", "application/json")
	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		return nil, err
	}
	if resp.StatusCode != http.StatusOK {
		body, _ := io.ReadAll(resp.Body)
		resp.Body.Close()
		bodyStr := string(body)
		if strings.Contains(bodyStr, "image input is not supported") || strings.Contains(bodyStr, "mmproj") {
			return nil, fmt.Errorf("【模型不支持多模态】您当前选择的模型 %s 为纯文本模型，不支持图片输入。请在左下角配置中切换为支持视觉的多模态模型（如 moondream、minicpm-v），或者在宿主机运行 `ollama run moondream` 拉取后重试", o.Model)
		}
		return nil, fmt.Errorf("ollama status error: %d, detail: %s", resp.StatusCode, bodyStr)
	}
	sr, sw := schema.Pipe[*schema.Message](100)
	go func() {
		defer resp.Body.Close()
		defer sw.Close()
		reader := bufio.NewReader(resp.Body)
		for {
			line, err := reader.ReadBytes('\n')
			if err != nil {
				if err != io.EOF {
					_ = sw.Send(&schema.Message{Role: schema.Assistant, Content: fmt.Sprintf("\n❌ Stream error: %v", err)}, nil)
				}
				break
			}
			line = bytes.TrimSpace(line)
			if len(line) == 0 {
				continue
			}
			var chunk OllamaChatResponse
			if err := json.Unmarshal(line, &chunk); err != nil {
				continue
			}
			_ = sw.Send(&schema.Message{
				Role:    schema.Assistant,
				Content: chunk.Message.Content,
			}, nil)
			if chunk.Done {
				break
			}
		}
	}()
	return sr, nil
}
