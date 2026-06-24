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

	"github.com/cloudwego/eino/components/model"
	"github.com/cloudwego/eino/schema"
)

type OllamaChat struct {
	BaseURL string
	Model   string
}

type OllamaMessage struct {
	Role    string `json:"role" xml:"role"`
	Content string `json:"content" xml:"content"`
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
		return nil, fmt.Errorf("ollama response error: %s", string(body))
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
		resp.Body.Close()
		return nil, fmt.Errorf("ollama status error: %d", resp.StatusCode)
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
