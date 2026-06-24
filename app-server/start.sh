#!/bin/bash
# start.sh for Docker container

# WHY: Docker Desktop 会向容器注入 ALL_PROXY=socks5://host.docker.internal:7897 等代理变量，
#      导致 Python httpx、qdrant_client、fastembed 等库向本地服务（Ollama、Qdrant）
#      发请求时全部被 SOCKS 代理拦截并失败。生产环境不需要翻墙代理，彻底清除。
unset http_proxy https_proxy all_proxy no_proxy
unset HTTP_PROXY HTTPS_PROXY ALL_PROXY NO_PROXY

# WHY: HF 镜像源环境变量，确保运行时如需下载模型时走国内镜像
export HF_ENDPOINT=https://hf-mirror.com

# Start SSH daemon for external Antigravity connections
service ssh start

# WHY: 模型预热由 main.py 的 on_startup 钩子在 uvicorn 进程内完成，
#      不需要在此处启动独立进程预热（独立进程的模型无法跨进程传递给 uvicorn）。
#      main.py on_startup 会预加载：
#        1) Ollama LLM (warmup + heartbeat)
#        2) BGE-M3 Dense + Sparse 编码器
#      参见 main.py:on_startup()

# WHY: 容器启动时自动编译最新 Go 网关代码，并确保编译产物在 PM2 运行前就绪
echo "🔨 正在编译 Go 网关服务 (nexus-gateway)..."
export GOPROXY=https://goproxy.cn,direct
cd /app/nexus-gateway
go mod tidy 2>&1
go build -v -o nexus-gateway . 2>&1
cd /app

# We run pm2-runtime to keep the container foreground
pm2-runtime start ecosystem.config.js
