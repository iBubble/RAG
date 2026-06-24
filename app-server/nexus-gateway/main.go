package main

import (
	"log"
	"os"
	"time"

	"github.com/gin-gonic/gin"
	"github.com/joho/godotenv"
	"github.com/nats-io/nats.go"
)

func main() {
	// 1. 尝试加载 Python 后端的环境变量
	_ = godotenv.Load("backend/.env")
	_ = godotenv.Load("../backend/.env")

	// 2. 初始化 JWT 模块
	initJWT()

	// 3. 连接 NATS 消息总线（带重试机制，应对容器启动顺序）
	natsURL := os.Getenv("NATS_URL")
	if natsURL == "" {
		natsURL = "nats://rag-nats:4222"
	}

	var nc *nats.Conn
	var err error
	for i := 0; i < 10; i++ {
		log.Printf("[Go-Gateway] 正在连接 NATS 服务 (%s)... 尝试 %d/10", natsURL, i+1)
		nc, err = nats.Connect(natsURL, nats.Name("Go-Nexus-Gateway"), nats.Timeout(5*time.Second))
		if err == nil {
			break
		}
		time.Sleep(2 * time.Second)
	}

	if err != nil {
		log.Fatalf("[Go-Gateway] 连接 NATS 服务最终失败: %v", err)
	}
	defer nc.Close()
	log.Println("[Go-Gateway] NATS 连接成功！")

	// 4. 路由配置与启动
	gin.SetMode(gin.ReleaseMode)
	r := gin.New()
	r.Use(gin.Recovery())

	// 日志中间件
	r.Use(func(c *gin.Context) {
		start := time.Now()
		c.Next()
		latency := time.Since(start)
		log.Printf("[Go-Gateway] %s %s %d %s", c.Request.Method, c.Request.URL.Path, c.Writer.Status(), latency)
	})

	// 获取 Python 后端的实际地址，容器内默认为 http://127.0.0.1:8002
	backendURL := os.Getenv("PYTHON_BACKEND_URL")
	if backendURL == "" {
		backendURL = "http://127.0.0.1:8002"
	}

	// 核心对话流式接口：由 Go + NATS 自行处理
	r.POST("/api/chat", AuthMiddleware(), ChatHandler(nc))

	// 泛解析：使用 NoRoute 机制将其他所有未精确匹配接口转发至 Python 后端 (8002 端口)
	r.NoRoute(ReverseProxy(backendURL))

	port := os.Getenv("GATEWAY_PORT")
	if port == "" {
		port = "8001"
	}

	log.Printf("[Go-Gateway] 核心网关启动成功，正在监听端口 :%s，反向代理后端: %s", port, backendURL)
	if err := r.Run(":" + port); err != nil {
		log.Fatalf("[Go-Gateway] 网关运行出错: %v", err)
	}
}
