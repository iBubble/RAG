package main

import (
	"net/http"
	"net/http/httputil"
	"net/url"

	"github.com/gin-gonic/gin"
)

// ReverseProxy 返回一个反向代理处理器，将请求转发给 Python 后端
func ReverseProxy(targetURL string) gin.HandlerFunc {
	target, err := url.Parse(targetURL)
	if err != nil {
		panic(err)
	}

	proxy := httputil.NewSingleHostReverseProxy(target)

	return func(c *gin.Context) {
		// 自定义 Director 逻辑，确保转发的 Header 正常
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
