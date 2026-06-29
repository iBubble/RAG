#!/bin/bash
# ==============================================================================
# Ollama 宿主机自愈守护脚本 (macOS Watchdog)
# WHY: 解决 Ollama 后台 llama-server 进程长期挂载发生 Metal 显存死锁、503 堆积拒绝服务的问题。
# ==============================================================================

OLLAMA_API="http://127.0.0.1:11434/api/tags"
LOG_FILE="/tmp/ollama_watchdog.log"
TIMEOUT_SECS=8
MAX_RETRIES=3

log_msg() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') - $1" >> "$LOG_FILE"
}

check_ollama() {
    local response_code
    response_code=$(curl -s -o /dev/null -w "%{http_code}" --max-time $TIMEOUT_SECS "$OLLAMA_API")
    echo "$response_code"
}

restart_ollama() {
    log_msg "⚠️ 检测到 Ollama 推理引擎发生卡死或拒绝服务(503)！开始执行强制复苏..."
    
    # 1. 强杀所有相关进程
    killall -9 llama-server 2>/dev/null
    killall -9 Ollama 2>/dev/null
    killall -9 ollama 2>/dev/null
    sleep 2
    
    # 2. 重新冷拉起
    open -a Ollama
    
    log_msg "✅ Ollama 进程已强制重启完毕，显存已清空并重新初始化。"
}

# === 主控制流 ===
retry_count=0
while [ $retry_count -lt $MAX_RETRIES ]; do
    status_code=$(check_ollama)
    
    if [ "$status_code" = "200" ]; then
        exit 0
    else
        log_msg "⚠️ 探活尝试 ($((retry_count+1))/$MAX_RETRIES) 失败，HTTP CODE: $status_code"
        retry_count=$((retry_count+1))
        sleep 3
    fi
done

# 连续多次均未返回 200，执行重启
restart_ollama
