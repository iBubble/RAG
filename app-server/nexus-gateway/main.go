package main

import (
	"log"
	"os"
	"time"

	"github.com/gin-gonic/gin"
	"github.com/joho/godotenv"
)

func main() {
	// 1. 尝试加载 Python 后端的环境变量
	_ = godotenv.Load("backend/.env")
	_ = godotenv.Load("../backend/.env")

	// 2. 初始化 JWT 模块
	initJWT()


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

	// 核心对话流式接口：由 Go 本地 Eino.Graph 编排处理
	r.POST("/api/chat", AuthMiddleware(), ChatHandler())
	r.POST("/api/eino/resume", AuthMiddleware(), ResumeHandler())

	// 针对前端资源和 API 分流代理
	frontendURL := "http://127.0.0.1:2028"
	r.NoRoute(func(c *gin.Context) {
		path := c.Request.URL.Path
		if len(path) >= 4 && path[:4] == "/api" {
			ReverseProxy(backendURL)(c)
		} else {
			ReverseProxy(frontendURL)(c)
		}
	})

	port := os.Getenv("GATEWAY_PORT")
	if port == "" {
		port = "8001"
	}

	log.Printf("[Go-Gateway] 核心网关启动成功，正在监听端口 :%s，反向代理后端: %s", port, backendURL)
	if err := r.Run(":" + port); err != nil {
		log.Fatalf("[Go-Gateway] 网关运行出错: %v", err)
	}
}
