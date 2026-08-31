#!/bin/bash
# ==============================================================================
# 外部存储 VirtioFS 挂载健康守护与自动自愈脚本 (macOS Storage Watchdog)
# WHY: 解决 MacBook Pro 合盖休眠唤醒后 Docker VirtioFS 挂载句柄断开导致脱机的问题。
# ==============================================================================

LOG_FILE="/tmp/storage_watchdog.log"
HOST_BASE_DIR="/Volumes/macData"
DEBOUNCE_SECS=60

log_msg() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') - $1" >> "$LOG_FILE"
}

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
        # 探测容器内目录
        if ! docker exec "$CONTAINER_NAME" test -d "$CONTAINER_PATH" >/dev/null 2>&1; then
            LOCK_FILE="/tmp/.storage_watchdog_${CONTAINER_NAME}.lock"
            NOW=$(date +%s)
            LAST_RESTART=0
            if [ -f "$LOCK_FILE" ]; then
                LAST_RESTART=$(cat "$LOCK_FILE" 2>/dev/null || echo 0)
            fi

            DIFF=$((NOW - LAST_RESTART))
            if [ "$DIFF" -ge "$DEBOUNCE_SECS" ]; then
                log_msg "🚨 检测到容器 [${CONTAINER_NAME}] 外部存储挂载断裂 (VirtioFS失效)！宿主机在线，立即执行自愈重启..."
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
