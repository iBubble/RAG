package main

import (
	"fmt"
	"io"
	"log"
	"net/http"
	"os"
	"sync"
	"time"

	"github.com/gin-gonic/gin"
	"github.com/gorilla/websocket"
)

var upgrader = websocket.Upgrader{
	ReadBufferSize:  1024,
	WriteBufferSize: 1024,
	CheckOrigin: func(r *http.Request) bool {
		return true // 允许跨域
	},
}

// Client 每一个活动的客户端连接
type Client struct {
	hub   *Hub
	conn  *websocket.Conn
	send  chan []byte
	token string // 保存握手时传入的 JWT Token
}

// Hub 连接池管理
type Hub struct {
	clients    map[*Client]bool
	broadcast  chan []byte
	register   chan *Client
	unregister chan *Client
	mu         sync.Mutex
}

var globalHub = &Hub{
	clients:    make(map[*Client]bool),
	broadcast:  make(chan []byte),
	register:   make(chan *Client),
	unregister: make(chan *Client),
}

func (h *Hub) Run() {
	// 启动定时拉取器：每2秒轮询一次Python后端状态并广播给连接的客户端
	go h.pollPythonBackendLoop()

	for {
		select {
		case client := <-h.register:
			h.mu.Lock()
			h.clients[client] = true
			h.mu.Unlock()
			log.Printf("[Go-WS] 🔌 新客户端已连接，当前活跃连接数: %d", len(h.clients))
		case client := <-h.unregister:
			h.mu.Lock()
			if _, ok := h.clients[client]; ok {
				delete(h.clients, client)
				close(client.send)
				log.Printf("[Go-WS] ❌ 客户端已断开，当前活跃连接数: %d", len(h.clients))
			}
			h.mu.Unlock()
		case message := <-h.broadcast:
			h.mu.Lock()
			for client := range h.clients {
				select {
				case client.send <- message:
				default:
					close(client.send)
					delete(h.clients, client)
				}
			}
			h.mu.Unlock()
		}
	}
}

// ServeWs 升级 HTTP 路由为 WebSocket
func ServeWs(c *gin.Context) {
	token := c.Query("token")
	conn, err := upgrader.Upgrade(c.Writer, c.Request, nil)
	if err != nil {
		log.Printf("[Go-WS] 升级 WebSocket 失败: %v", err)
		return
	}

	client := &Client{
		hub:   globalHub,
		conn:  conn,
		send:  make(chan []byte, 256),
		token: token,
	}
	globalHub.register <- client

	// 开启双工读写协程
	go client.writePump()
	go client.readPump()
}

func (c *Client) readPump() {
	defer func() {
		c.hub.unregister <- c
		c.conn.Close()
	}()
	for {
		_, _, err := c.conn.ReadMessage()
		if err != nil {
			break
		}
	}
}

func (c *Client) writePump() {
	defer func() {
		c.conn.Close()
	}()
	for {
		select {
		case message, ok := <-c.send:
			if !ok {
				_ = c.conn.WriteMessage(websocket.CloseMessage, []byte{})
				return
			}
			_ = c.conn.WriteMessage(websocket.TextMessage, message)
		}
	}
}

// BroadcastMessage 全局广播函数
func BroadcastMessage(data []byte) {
	select {
	case globalHub.broadcast <- data:
	default:
		// 避免无客户端时死锁
	}
}

// pollPythonBackendLoop 定时拉取Python后端看板数据并进行广播
func (h *Hub) pollPythonBackendLoop() {
	ticker := time.NewTicker(2000 * time.Millisecond)
	defer ticker.Stop()

	// 专门为拉取状态设置超时较短的 client
	httpClient := &http.Client{Timeout: 3 * time.Second}

	for range ticker.C {
		h.mu.Lock()
		clientCount := len(h.clients)
		var activeToken string
		if clientCount > 0 {
			// 随机挑一个带有 Token 的 Client
			for c := range h.clients {
				if c.token != "" {
					activeToken = c.token
					break
				}
			}
		}
		h.mu.Unlock()

		// 如果没有活跃的客户端连接，或者所有连接均未携带 token，则不进行拉取，以节省开销
		if clientCount == 0 || activeToken == "" {
			continue
		}

		backendURL := os.Getenv("PYTHON_BACKEND_URL")
		if backendURL == "" {
			backendURL = "http://127.0.0.1:8002"
		}
		url := fmt.Sprintf("%s/api/projects/linvis-status", backendURL)

		req, err := http.NewRequest("GET", url, nil)
		if err != nil {
			log.Printf("[Go-WS] 无法创建请求: %v", err)
			continue
		}
		req.Header.Set("Authorization", "Bearer "+activeToken)

		resp, err := httpClient.Do(req)
		if err != nil {
			log.Printf("[Go-WS] 后台轮询 Python /api/projects/linvis-status 失败: %v", err)
			continue
		}

		bodyBytes, err := io.ReadAll(resp.Body)
		resp.Body.Close()
		if err != nil {
			log.Printf("[Go-WS] 读取拉取的状态响应体失败: %v", err)
			continue
		}

		if resp.StatusCode != http.StatusOK {
			// Token 可能会失效或非项目成员
			continue
		}

		// 广播最新的状态数据给所有连接的前端
		BroadcastMessage(bodyBytes)
	}
}
