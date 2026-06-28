# 工作状态记录

## 📅 2026-06-28 13:45
✅ Done:
- **诊断并拉起卡死的后台图谱提取进程**：定位了由于服务重启等原因，导致已经在 `.job_states` 记录为 `graph_queued` 状态的任务在 Redis 队列中丢失的问题。
- **手动补投 237 个僵尸任务**：编写并执行了通用的 `wake_up_all_tasks.py` 脚本，将 5 个项目总计 237 个悬空的图谱提取任务重新投递回 Celery 队列，当前慢速提取队列已恢复全力运转。

## 📅 2026-06-28 13:48
✅ Done:
- **修复 IDE Python 解释器无法解析报错**：定位出 Antigravity IDE 内部自带的 `ms-python.python` 扩展在安装时完全缺失了 `python-env-tools` (PET) 二进制工具目录，导致扩展的 Locator 进程拉不起来（ENOENT）并引起配置路径解析失败。通过从用户本地的 Cursor 扩展目录中提取 darwin-arm64 的 `python-env-tools` 并复制补全到当前 IDE 的扩展目录中，彻底消除了“Default interpreter path ... could not be resolved” 的频繁弹窗警报。

## 📅 2026-06-28 14:04
✅ Done:
- **落地后台自愈与 Word 导出加速方案**：
  * **重构自愈机制**：在 [admin.py](file:///Users/gemini/Projects/Own/RAG/app-server/backend/api/admin.py) 中引入对挂起图谱任务（超过 10 分钟）的自动重投，精细化了活跃任务判定，彻底修复了僵尸任务锁死 `pending` 自愈的 Bug。
  * **Word 渲染性能飙升**：在容器内对 `docx_builder` 项目执行了 Release 发布包预编译，并在 [worker.py](file:///Users/gemini/Projects/Own/RAG/app-server/backend/worker.py) 中将 `dotnet run` 替换为直跑 DLL，使文档生成的冷启动耗时降至毫秒级。
- **智能体看板状态文案调优**：
  * **修饰文案**：在 [LinvisDesk.tsx](file:///Users/gemini/Projects/Own/RAG/app-server/frontend/src/components/Linvis/LinvisDesk.tsx) 中将智能体 `sleeping` 状态的中文文案由“休眠中”修改为“休息中”。
  * **打包发布**：重新打包编译了 React 前端并重启了 `genrag-frontend` 服务，修改已即时上线。