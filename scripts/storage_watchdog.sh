#!/bin/bash
# ==============================================================================
# 外部存储 VirtioFS 挂载健康守护与自动自愈脚本 (macOS Storage Watchdog)
# WHY: 解决 MacBook Pro 合盖休眠唤醒后 Docker VirtioFS 挂载句柄断开导致脱机的问题。
# ==============================================================================

# 确保在 macOS cron、launchd 及无头环境下正确寻址 docker 等系统命令
export PATH="/usr/local/bin:/opt/homebrew/bin:/opt/homebrew/sbin:/usr/bin:/bin:/usr/sbin:/sbin:$PATH"

LOG_FILE="/tmp/storage_watchdog.log"
HOST_BASE_DIR="/Volumes/macData"
DEBOUNCE_SECS=30

log_msg() {
    local MSG="$1"
    echo "$(date '+%Y-%m-%d %H:%M:%S') - $MSG" >> "$LOG_FILE"
}

# 日志轮转保护（超过 2MB 时保留最后 1000 行）
if [ -f "$LOG_FILE" ] && [ "$(wc -c < "$LOG_FILE" 2>/dev/null || echo 0)" -gt 2097152 ]; then
    tail -n 1000 "$LOG_FILE" > "${LOG_FILE}.tmp" && mv "${LOG_FILE}.tmp" "$LOG_FILE"
fi

# 1. 检查宿主机外置磁盘挂载基准目录是否存在
if [ ! -d "$HOST_BASE_DIR" ]; then
    # 宿主机本身未连接外置盘，无需重启容器
    exit 0
fi

# 2. 定义待检查与自愈的容器矩阵 (格式: "容器名:宿主机路径:容器内路径")
CONTAINER_TARGETS=(
    "GenRAG-Server:/Volumes/macData/GenRAG_Files:/Volumes/macData/RAG_Files"
    "RAG-Server:/Volumes/macData/RAG_Files:/Volumes/SYRAID/RAG_Files"
)

for TARGET in "${CONTAINER_TARGETS[@]}"; do
    IFS=":" read -r CONTAINER_NAME HOST_PATH CONTAINER_PATH <<< "$TARGET"
    
    # 检查容器是否正在运行
    RUNNING_ID=$(docker ps -q -f "name=^${CONTAINER_NAME}$" -f "status=running" 2>/dev/null)
    if [ -z "$RUNNING_ID" ]; then
        continue
    fi

    # 如果宿主机路径存在，但容器内部路径无法访问，则判定为 VirtioFS 挂载断裂
    if [ -d "$HOST_PATH" ]; then
        # 首次探测容器内目录
        if ! docker exec "$CONTAINER_NAME" test -d "$CONTAINER_PATH" >/dev/null 2>&1; then
            # 短暂休眠 1.5 秒进行二次复验，排除休眠刚唤醒时的瞬态未就绪
            sleep 1.5
            if docker exec "$CONTAINER_NAME" test -d "$CONTAINER_PATH" >/dev/null 2>&1; then
                log_msg "ℹ️ 容器 [${CONTAINER_NAME}] 二次探测成功恢复，属瞬态挂载抖动，已自动平滑吸收。"
                continue
            fi

            LOCK_FILE="/tmp/.storage_watchdog_${CONTAINER_NAME}.lock"
            NOW=$(date +%s)
            LAST_RESTART=0
            if [ -f "$LOCK_FILE" ]; then
                LAST_RESTART=$(cat "$LOCK_FILE" 2>/dev/null || echo 0)
            fi

            DIFF=$((NOW - LAST_RESTART))
            if [ "$DIFF" -ge "$DEBOUNCE_SECS" ]; then
                log_msg "🚨 检测到容器 [${CONTAINER_NAME}] 外部存储挂载断裂 (VirtioFS 失效)！宿主机在线，立即执行自愈重启..."
                echo "$NOW" > "$LOCK_FILE"
                
                # 执行热重启恢复挂载通道
                if docker restart "$CONTAINER_NAME" >/dev/null 2>&1; then
                    log_msg "✅ 容器 [${CONTAINER_NAME}] 自愈重启成功，存储挂载已自动恢复！"
                else
                    log_msg "❌ 容器 [${CONTAINER_NAME}] 自愈重启失败，请人工介入检查！"
                fi
            else
                log_msg "⏳ 容器 [${CONTAINER_NAME}] 处于自愈防抖冷却期 (${DIFF}s < ${DEBOUNCE_SECS}s)，本次跳过。"
            fi
        fi
    fi
done

exit 0
