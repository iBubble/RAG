package main

import (
	"bytes"
	"encoding/json"
	"fmt"
	"io"
	"log"
	"net/http"
	"os"
	"time"

	"github.com/gin-gonic/gin"
	"github.com/nats-io/nats.go"
)

// ChatHandler 处理 /api/chat 的流式生成请求
func ChatHandler(nc *nats.Conn) gin.HandlerFunc {
	return func(c *gin.Context) {
		// 1. 读取并克隆请求体原始字节，以防非 smart 模式下后续转发时 Body 为空
		bodyBytes, err := io.ReadAll(c.Request.Body)
		if err != nil {
			c.JSON(http.StatusBadRequest, gin.H{"detail": "读取请求体失败"})
			return
		}
		// 恢复 Request.Body，确保反向代理时可以读取到完整 POST 载荷
		c.Request.Body = io.NopCloser(bytes.NewBuffer(bodyBytes))

		// 2. 反序列化结构体
		var req EinoAgentRequest
		if err := json.Unmarshal(bodyBytes, &req); err != nil {
			c.JSON(http.StatusBadRequest, gin.H{"detail": "解析请求体 JSON 失败"})
			return
		}

		log.Printf("[Go-Gateway] 📌 收到 /api/chat 请求: ChatMode=%q, Message=%q, FileIDs=%v", req.ChatMode, req.Message, req.FileIDs)

		// 3. 拦截检查系统 L2 (Redis) 缓存指纹
		log.Printf("[Go-Gateway] 🔍 正在检索系统缓存指纹...")
		if cacheRes, err := checkPythonChatCache(bodyBytes); err == nil && cacheRes.Hit {
			log.Printf("[Go-Gateway] 🎯 缓存指纹命中！正在直接以极速流式回复...")
			c.Writer.Header().Set("Content-Type", "text/event-stream")
			c.Writer.Header().Set("Cache-Control", "no-cache")
			c.Writer.Header().Set("Connection", "keep-alive")
			c.Writer.Header().Set("Transfer-Encoding", "chunked")
			c.Writer.Header().Set("X-Accel-Buffering", "no")

			streamCachedResponse(c.Writer, cacheRes)
			return
		}
		log.Printf("[Go-Gateway] 💨 缓存未命中，继续执行实时推理流...")

		// 4. 非协同 (smart) 模式（例如独立、快速、深度等模式）下，直接反向代理至 Python 后端
		if req.ChatMode != "smart" {
			backendURL := os.Getenv("PYTHON_BACKEND_URL")
			if backendURL == "" {
				backendURL = "http://127.0.0.1:8002"
			}
			log.Printf("[Go-Gateway] 🔀 非 smart 协同模式，正在将请求转发给 Python 后端: %s", backendURL)
			proxyHandler := ReverseProxy(backendURL)
			proxyHandler(c)
			return
		}

		log.Printf("[Go-Gateway] 🤝 协同模式 (smart)，开始执行 Go Eino 编排有向图流程...")

		// 5. 设置响应头为 SSE (协同模式下由 Go 接管渲染)
		c.Writer.Header().Set("Content-Type", "text/event-stream")
		c.Writer.Header().Set("Cache-Control", "no-cache")
		c.Writer.Header().Set("Connection", "keep-alive")
		c.Writer.Header().Set("Transfer-Encoding", "chunked")
		c.Writer.Header().Set("X-Accel-Buffering", "no")

		// 6. 执行 Eino Agent 图协同编排
		ctx := c.Request.Context()
		err = RunEinoOrchestration(ctx, &req, c.Writer)
		if err != nil {
			log.Printf("[Go-Gateway] RunEinoOrchestration error: %v", err)
			_ = writeSSE(c.Writer, map[string]interface{}{
				"type":    "token",
				"content": fmt.Sprintf("\n❌ 系统编排协同异常: %v", err),
			})
			_ = writeSSE(c.Writer, map[string]interface{}{
				"type": "done",
			})
		}
	}
}

type InternalCacheGetResponse struct {
	Hit              bool                   `json:"hit"`
	Answer           string                 `json:"answer"`
	Sources          []string               `json:"sources"`
	DataAnalysisMeta map[string]interface{} `json:"data_analysis_meta"`
}

func checkPythonChatCache(bodyBytes []byte) (*InternalCacheGetResponse, error) {
	backendURL := os.Getenv("PYTHON_BACKEND_URL")
	if backendURL == "" {
		backendURL = "http://127.0.0.1:8002"
	}
	url := fmt.Sprintf("%s/api/internal/chat/cache/get", backendURL)

	resp, err := http.Post(url, "application/json", bytes.NewBuffer(bodyBytes))
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		return nil, fmt.Errorf("http status %d", resp.StatusCode)
	}

	var res InternalCacheGetResponse
	if err := json.NewDecoder(resp.Body).Decode(&res); err != nil {
		return nil, err
	}
	return &res, nil
}

func streamCachedResponse(w io.Writer, res *InternalCacheGetResponse) {
	_ = writeSSE(w, map[string]interface{}{"cached": true})
	if len(res.Sources) > 0 {
		_ = writeSSE(w, map[string]interface{}{"sources": res.Sources})
	}
	if res.DataAnalysisMeta != nil {
		_ = writeSSE(w, map[string]interface{}{"data_analysis": res.DataAnalysisMeta})
	}

	// 极速流式模拟输出缓存文本
	runes := []rune(res.Answer)
	chunkSize := 40
	for i := 0; i < len(runes); i += chunkSize {
		end := i + chunkSize
		if end > len(runes) {
			end = len(runes)
		}
		token := string(runes[i:end])
		_ = writeSSE(w, map[string]interface{}{
			"type":    "token",
			"content": token,
		})
		time.Sleep(5 * time.Millisecond)
	}

	_ = writeSSE(w, map[string]interface{}{"done": true})
}
