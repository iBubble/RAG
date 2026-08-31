# 工作状态记录

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

## 📅 2026-08-31 18:26
*   **更新 README.md 与 CHANGELOG.md 并成功推送至 GitHub 远程仓库**：
    - ✅ Done:
      - 文档体系升级：升级 [README.md](file:///Users/gemini/Projects/Own/RAG/README.md) 至 v4.4.0，新增“硬件级高可用自愈与守护体系”章节与目录树更新；
      - 版本日志归档：更新 [CHANGELOG.md](file:///Users/gemini/Projects/Own/RAG/CHANGELOG.md) 记录 4.4.0 版本新增功能与缺陷修复；
      - Git 代码推送：完成 Commit 并成功推送至远程仓库 `https://github.com/iBubble/RAG.git` (main 分支)。
    - ⏳ To-Do:
      - 暂无