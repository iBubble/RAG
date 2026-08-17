# Linvis 协同状态流式监视大屏开发复用文档

本文档详细介绍了 Linvis 虚拟办公室协同状态看板的设计架构、文件结构与接口通信协议，便于在其他智能体项目（如 LawRAG）中快速复用。

## 1. 架构设计与流转机制

Linvis 看板采用的是 **“工作流状态主动上报 -> 统一暂存 -> 网关轮询广播 -> 前端流式消费”** 的架构模式：

1. **状态上报**：有向图（DAG）节点在流转时，调用 Go 端 `setLinvisStatus` 发起 HTTP 请求将状态同步至 Python API。
2. **状态暂存**：Python API 接收并更新 Redis 缓存（Key 格式 `linvis:active:{agent_key}`），并提供带 15秒 TTL 的汇总查询接口。
3. **网关广播**：Go 端 WebSocket 网关定时轮询 Python API 汇聚的数据，并通过 WS 连接实时向前端推送广播（事件 `linvis_status_update`）。
4. **流式消费**：前端 React 接收到 WS 数据后，驱动 SVG 办公室中的 10 个角色执行对应动作（工作中、休息、摸鱼等）。

## 2. 核心复用目录与文件

复用本项目时，应在对应位置引入以下结构：

```text
├── frontend/src/
│   ├── assets/office/            # 2D 卡通办公桌、角色雪碧图资源 (.webp / .png)
│   └── components/Linvis/        # 核心看板组件目录
│       ├── Linvis.tsx            # SVG 办公室场景、WebSocket 订阅与状态机核心
│       ├── Linvis3D.css          # 格子地板、工位悬浮、Zzz 及独角发光动画样式
│       └── LinvisWhiteboard.tsx  # 看板右侧的“电子白板”统计分析面板
├── nexus-gateway/                # Go 中转网关
│   ├── eino_graph.go             # 节点状态上报逻辑（提供 setLinvisStatus 方法）
│   └── websocket.go              # WebSocket 长连接生命周期与定时广播逻辑
└── backend/                      # 后端状态处理
    ├── api/generate.py           # 状态上报的 HTTP 路由 (/internal/linvis/set-status)
    ├── api/projects.py           # 状态查询与 15s 数据缓存接口 (/linvis-status)
    └── core/redis_client.py      # 底层 Redis 读写缓存操作
```

## 3. 接口通信协议

### 3.1 状态上报接口（Go -> Python）
- **路径**：`POST /api/internal/linvis/set-status`
- **请求体 (JSON)**：
  ```json
  {
    "agent": "planner",
    "status": "working",
    "msg": "规划任务路由中...",
    "project_name": "demo_project"
  }
  ```

### 3.2 状态汇总接口（Python -> Go/前端）
- **路径**：`GET /api/projects/linvis-status`
- **返回体 (JSON)**：
  ```json
  {
    "system_status": {
      "active_tasks": 1,
      "funny_level": "low",
      "linvis_name": "麟维斯",
      "whiteboard": { "total_projects": 10, "completed_percent": 85 }
    },
    "agents": {
      "planner": { "status": "working", "current_task": "规划任务路由中..." }
    }
  }
  ```

## 4. 前端复用实现要点

1. **精确定时切帧（JavaScript）**：
   在 `working` 状态下，使用 `setInterval` 每隔 300ms 改变 `frameIdx` (0~3)；非工作状态重置为 0。利用 `transform: translateX(-frameIdx * 25%)` 实现单张雪碧图的动作切帧。
2. **SVG 无缝定位**：
   在 `Linvis.tsx` 中使用 SVG 标签 `<image>` 定位办公桌及角色，避免使用传统的 Div 绝对定位，使角色、座椅和气泡可以在各种分辨率下保持贴合。
