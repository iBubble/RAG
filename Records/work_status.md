# 工作状态记录

## 📅 2026-08-18 23:33
*   **深度重构 README.md 详述四大核心技术架构并推送到 GitHub**：
    - ✅ Done:
      - 详述四大核心体系：系统化梳理并扩充“法律专属语义分块”、“六路并行混合召回与过滤”、“GPU 常驻 LLM-based 极速重排”及“端到端工程落地全景架构”四大重磅章节；
      - 文档升级与版本归档：升级 [README.md](file:///Users/gemini/Projects/Own/RAG/README.md) 至 v4.3.0，归档 [work_records_20260818_2333.md](file:///Users/gemini/Projects/Own/RAG/Records/work_records_20260818_2333.md)；
      - GitHub 远程推送：执行 `git commit` 与 `git push` 成功同步至远程仓库 `https://github.com/iBubble/RAG.git` (main 分支)。
    - ⏳ To-Do:
      - 暂无

## 📅 2026-08-31 18:22
*   **排查并恢复外置存储挂载失效与脱机告警故障**：
    - ✅ Done:
      - 故障定位：定位到 `rag.liukun.com` 所代理的 `GenRAG-Server` 容器因宿主机休眠导致 Docker VirtioFS 挂载点断开（出现悬空 inode 导致 watchdog 触发脱机保护）；
      - 容器重启与挂载重建：重启 `GenRAG-Server` 容器重建 `/Volumes/macData/GenRAG_Files` 挂载通道；
      - 全链路巡检恢复：验证 `curl http://localhost:8003/api/llm/status` 状态恢复为 `green` (在线)，顶部脱机警告横幅已自动解除。
    - ⏳ To-Do:
      - 暂无

## 📅 2026-08-31 18:25
*   **建设 MacBook Pro 休眠唤醒后外部存储挂载自动恢复与健康自愈机制**：
    - ✅ Done:
      - 自愈守护脚本落地：编写 [storage_watchdog.sh](file:///Users/gemini/Projects/Own/RAG/scripts/storage_watchdog.sh)，纳管 `GenRAG-Server` 与 `RAG-Server`，支持断裂检测与 60s 防抖热重启；
      - 宿主机 crontab 调度挂载：配置每分钟常驻巡检任务，MacBook Pro 合盖唤醒后自动秒级恢复存储通道；
      - ADR 技术决策与记录归档：更新 [技术决策记录.md](file:///Users/gemini/Projects/Own/RAG/技术决策记录.md) (ADR-002) 并归档 [work_records_20260831_1825.md](file:///Users/gemini/Projects/Own/RAG/Records/work_records_20260831_1825.md)。
    - ⏳ To-Do:
      - 暂无