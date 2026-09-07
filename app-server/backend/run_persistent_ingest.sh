#!/bin/bash
PROJECT_DIR="/Users/gemini/Projects/Own/RAG"
PY_BIN="/Users/gemini/Software/PythonRuntime/python312/bin/python3"
SCRIPT_PATH="$PROJECT_DIR/app-server/backend/scripts_internal_ingest_standards.py"
LOG_PATH="$PROJECT_DIR/Records/ingest_standards_mps.log"
PROJ_ID="fe2982b3820e"

while true; do
    echo "$(date '+%Y-%m-%d %H:%M:%S') [SUPERVISOR] 启动入库主引擎..." >> "$LOG_PATH"
    $PY_BIN -u "$SCRIPT_PATH" "$PROJ_ID" >> "$LOG_PATH" 2>&1
    EXIT_CODE=$?
    echo "$(date '+%Y-%m-%d %H:%M:%S') [SUPERVISOR] 引擎退出，返回码: $EXIT_CODE" >> "$LOG_PATH"
    
    # 检查是否全部入库完成
    VEC_CNT=$($PY_BIN -c "import os, json; from pathlib import Path; p = Path('/Volumes/macData/GenRAG_Files/uploads/$PROJ_ID/.job_states'); print(len([f for f in p.glob('*.json') if json.loads(f.read_text()).get('status') == 'vectorized']))" 2>/dev/null || echo "0")
    if [ "$VEC_CNT" -ge 1740 ]; then
        echo "$(date '+%Y-%m-%d %H:%M:%S') [SUPERVISOR] 🎉 全库全部完成，守护脚本正常退出！" >> "$LOG_PATH"
        break
    fi
    echo "$(date '+%Y-%m-%d %H:%M:%S') [SUPERVISOR] 当前已完成 $VEC_CNT 部标准，3秒后自动复活并秒级跳过已完成项接续..." >> "$LOG_PATH"
    sleep 3
done
