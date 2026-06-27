# 腾讯 Marvis 虚拟办公室 (linvis) 看板重构工作清单

## 🚀 阶段 1：后端 WebSocket 契约与网关广播 (Go Backend)
- [ ] 在 `nexus-gateway` 新增路由 `/api/eino/ws-status` 支持 WebSocket 连接与连接池管理
- [ ] 在 Go Eino Graph 中织入流程执行的 Callback Handlers (OnStart, OnEnd, OnInterrupt)
- [ ] 封装状态事件分发器，在节点状态变化时秒级通知网关进行全量广播

## 🎨 阶段 2：等距 2.5D 美术资源与工位动画定义
- [ ] 收集/设计 2.5D 等距办公室扁平高光矢量资源（工位桌、咖啡机、跑步机等）
- [ ] 导出 2.5D 獬豸小马（Xiezhi Pony）骨骼图层，并用 Spine 2D 制作 5 套高水准状态动画：
  - `anim_idle_sleeping` (打瞌睡 Zzz)
  - `anim_work_typing` (残影键盘敲击)
  - `anim_slacking_tea` (端干部杯喝茶)
  - `anim_waiting_approval` (挥手呼救)
  - `anim_crashed_error` (沮丧抱头)

## 🖥️ 阶段 3：前端 2.5D Isometric 场景布局与节点渲染
- [ ] 在 `Linvis.tsx` 中建立 WebSocket 订阅，接收状态并交由 Zustand 集中响应
- [ ] 采用 CSS Matrix 倾斜投影或等距坐标公式排布 2.5D 科室工作区与摸鱼区
- [ ] 升级 `LinvisDesk.tsx` 节点卡片：
  - 空闲时自动脱离工位渲染 Slacking 状态（小智喝茶，Planner 跑步，Checker/Auditor 睡觉）
  - 工作时闪现回座位渲染 Typing 打字，头顶悬浮微型 Token 监控气泡与时序消耗仪
  - 挂起时显示橙色警报灯并挥手，异常时显示电脑冒烟与死机沮丧动画

## 🤝 阶段 4：高阶人机审批与打印成果框整合
- [ ] 在 Auditor 挂起警报时，支持点击滑出精致的“法务复核看板”
- [ ] 整合左侧草稿编辑与右侧向量库/图谱法条追溯，点击“批准执行”提交 Go 挂起流
- [ ] 在办公室右侧常驻 2.5D 成果卷宗盒，完成后以文档卷宗滑入动效呈现，支持 iframe 留痕预览
