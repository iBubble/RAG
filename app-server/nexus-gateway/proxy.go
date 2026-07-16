package main

import (
	"net/http"
	"net/http/httputil"
	"net/url"

	"github.com/gin-gonic/gin"
)

// ReverseProxy 返回一个反向代理处理器，将请求转发给 Python 后端
// WHY: 每次请求创建新的 proxy 实例，避免并发修改共享 Director 导致的 data race。
func ReverseProxy(targetURL string) gin.HandlerFunc {
	target, err := url.Parse(targetURL)
	if err != nil {
		panic(err)
	}

	return func(c *gin.Context) {
		proxy := httputil.NewSingleHostReverseProxy(target)
		originalDirector := proxy.Director
		proxy.Director = func(req *http.Request) {
			originalDirector(req)
			req.Host = target.Host
			// 传递真实客户端 IP
			req.Header.Set("X-Real-IP", c.ClientIP())
			req.Header.Set("X-Forwarded-For", c.Request.Header.Get("X-Forwarded-For"))
			if c.Request.TLS != nil {
				req.Header.Set("X-Forwarded-Proto", "https")
			} else {
				req.Header.Set("X-Forwarded-Proto", "http")
			}
		}

		// 执行代理
		proxy.ServeHTTP(c.Writer, c.Request)
	}
}
