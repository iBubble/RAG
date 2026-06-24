package main

import (
	"crypto/hmac"
	"crypto/sha256"
	"encoding/base64"
	"encoding/json"
	"errors"
	"fmt"
	"net/http"
	"os"
	"strings"
	"time"

	"github.com/gin-gonic/gin"
)

// JWTClaims 定义 Payload 的数据结构
type JWTClaims struct {
	Sub  string `json:"sub"`
	Role string `json:"role"`
	Exp  int64  `json:"exp"`
}

var jwtSecret []byte

func initJWT() {
	secret := os.Getenv("JWT_SECRET")
	if secret == "" {
		secret = "FALLBACK_INSECURE_KEY_CHECK_ENV"
	}
	jwtSecret = []byte(secret)
}

// base64UrlDecode 解码 Base64Url 字符串
func base64UrlDecode(s string) ([]byte, error) {
	// 补全 Base64 填充符 '='
	switch len(s) % 4 {
	case 2:
		s += "=="
	case 3:
		s += "="
	}
	return base64.URLEncoding.DecodeString(s)
}

// verifyToken 原生验证 JWT 并返回 Claims
func verifyToken(tokenStr string) (*JWTClaims, error) {
	parts := strings.Split(tokenStr, ".")
	if len(parts) != 3 {
		return nil, errors.New("invalid jwt format")
	}

	// 1. 验证签名是否匹配
	mac := hmac.New(sha256.New, jwtSecret)
	mac.Write([]byte(parts[0] + "." + parts[1]))
	expectedSignature := mac.Sum(nil)

	signature, err := base64UrlDecode(parts[2])
	if err != nil {
		return nil, fmt.Errorf("decode signature fail: %v", err)
	}

	if !hmac.Equal(signature, expectedSignature) {
		return nil, errors.New("signature mismatch")
	}

	// 2. 解密并校验 Payload
	payloadBytes, err := base64UrlDecode(parts[1])
	if err != nil {
		return nil, fmt.Errorf("decode payload fail: %v", err)
	}

	var claims JWTClaims
	if err := json.Unmarshal(payloadBytes, &claims); err != nil {
		return nil, fmt.Errorf("unmarshal payload fail: %v", err)
	}

	// 3. 校验过期时间
	if claims.Exp < time.Now().Unix() {
		return nil, errors.New("token expired")
	}

	return &claims, nil
}

// AuthMiddleware 鉴权中间件，提取并验证 JWT Token
func AuthMiddleware() gin.HandlerFunc {
	return func(c *gin.Context) {
		tokenStr := ""

		// 1. 优先从 Authorization 头中提取
		authHeader := c.GetHeader("Authorization")
		if authHeader != "" {
			parts := strings.SplitN(authHeader, " ", 2)
			if len(parts) == 2 && strings.ToLower(parts[0]) == "bearer" {
				tokenStr = parts[1]
			}
		}

		// 2. 如果头部没有，则尝试从 Query 参数提取（支持 SSE/WebSocket 场景）
		if tokenStr == "" {
			tokenStr = c.Query("token")
		}

		if tokenStr == "" {
			c.JSON(http.StatusUnauthorized, gin.H{"detail": "未提供认证凭据"})
			c.Abort()
			return
		}

		claims, err := verifyToken(tokenStr)
		if err != nil {
			c.JSON(http.StatusUnauthorized, gin.H{"detail": fmt.Sprintf("凭据无效: %v", err)})
			c.Abort()
			return
		}

		// 将用户信息存入 context
		c.Set("user_id", claims.Sub)
		c.Set("role", claims.Role)
		c.Next()
	}
}
