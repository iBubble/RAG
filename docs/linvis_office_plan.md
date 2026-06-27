# 腾讯 Marvis 虚拟办公室式 (linvis) 看板重构实施计划 (V2 - 獬豸小马版)

我们将把看板升级为类似 **腾讯 Marvis** 的“市监局联合审批 AI 虚拟办公室 (Virtual Office)”，将原有的玩具机器人彻底重塑为 **“獬豸（Xièzhì）小马”** 这一具有法治底蕴的市监小神兽。

---

## 🏢 1. 核心形象选择与视觉风格

1.  **中国法治神兽：獬豸（Xièzhì）小马作为市监化身**：
    *   獬豸是中国古代神话中辨明是非、行政合规的最高法治象征。
    *   在 2.5D 等距视角中，獬豸保留“额头正中的辨善恶独角”与“如意尾”，继承腾讯 Marvis 独角小马的动作资产，展现政务权威度。
2.  **视觉设计规则 (Ditch 3D, Go 2.5D Flat-Vector)**：
    *   **扁平高光矢量**：抛弃 3D 黏土模型，采用 2.5D 扁平、微弱渐变和硬边投影的矢量风格。边缘锐利，对浏览器 CPU 算力消耗极低。
    *   **官方权威色谱 (Authority Palette)**：
        *   `主色调 (60%)`：藏蓝色/警务深蓝 (`Regulatory Blue`)，体现极强法治权威。
        *   `辅助色 (30%)`：纯白与钛金灰，保障办公室背景的高通透感。
        *   `标识色 (10%)`：国徽金 (`Authority Gold`)、安全绿 (`Pass/Safe`)、警戒橙 (`Audit/Interrupt`)，专用于独角、市监徽章和指示灯。

---

## 💼 2. 办公室场景布局与八大角色工位细节

整体划分为三大功能区，各角色的工位道具与状态切换如下：

*   **核心办公区 (6张工位桌)**：
    *   `前台接待：小智 (Smart - 窗口咨询獬豸)`：戴耳麦。工位摆有“市监咨询窗口”立牌。工作时键盘起伏，摸鱼时手捧印有“为人民服务”的白瓷干部杯喝茶。
    *   `核心调度：规划者 (Planner - 主任规划獬豸)`：额头独角最大，戴黑框眼镜。工位堆放红头文件和任务看板。工作时挥舞金色指挥棒（拆解 Eino 多 Agent 运行图），空闲时在角落跑步机运动。
    *   `定量核验：校验员 (Checker - 闪电算术獬豸)`：双前蹄套着蓝色财务袖套。桌上摆有巨大发光计算器，上方悬浮发票、信用代码的 HUD 投影。工作时双手化为残影拍击，空闲时趴桌上睡大觉冒出 $z^z\text{Z}$。
    *   `定性合规：审计官 (Auditor - 法制审查高级獬豸)`：身披迷你法官袍。背后书架堆满《民法典》、《消保法》。工作时翻书，通过时敲击法槌。挂起时站起挥手呼救，头顶闪烁警务旋转灯。
    *   `文书专家：小管 (Service - 文书专家獬豸)`：坐在打印机前，负责最终文书生成与留痕修订。
    *   `政策预研：小预 (Precalc - 政策预研獬豸)`：工位放置高频业务模板缓存箱。
*   **后勤档案室 (2张检索台)**：
    *   `归档入库：小向 (Vector - 数字化归档员)`：戴口罩手套。旁边放置高速纸张扫描仪（代表 OCR/PDF 解析管道）。工作时文件塞入扫描仪放出绿光，`0101` 代码飞入背后的 Qdrant 蓝色大铁柜。
    *   `图谱提炼：小图 (Graphy - 关系穿引员)`：手持毛线针。工作时将悬浮的 Neo4j 实体关系圆球进行穿引连线，折射金光。
*   **趣味摸鱼区 (Slacking Zones)**：
    *   包含咖啡机茶水间（提供拉花）、跑步机健身区与洗手间。

---

## ⚙️ 3. 动态状态机 (FSM) 映射与 Spine 2D 骨骼动画驱动

### 状态实时映射契约
后端 [nexus-gateway](file:///Users/gemini/Projects/Own/RAG/app-server/nexus-gateway/main.go) 的 WebSocket 通过 Eino 的 Callback 广播状态，前端通过管理动作状态机控制播放：

| Eino 执行状态 | 状态机轨道 | 表现动作 (Animation Name) |
| :--- | :--- | :--- |
| **IDLE (空闲)** | `anim_slacking_tea` | 离开座位在摸鱼区喝茶、运动或趴在桌上均匀呼吸休眠。 |
| **RUNNING (工作中)** | `anim_work_typing` | 瞬移回工位极速打字，独角发光，头顶悬浮微型 Token/耗时气泡。 |
| **INTERRUPTED (审批)** | `anim_waiting_approval` | 对应的 Checker/Auditor 挥手作呼救状，桌上亮起警报，滑出双路人工复核面板。 |
| **ERROR (异常)** | `anim_crashed_error` | 电脑屏幕冒烟死机，Agent 抱头呈现沮丧状态。 |

---

## 🛠️ 4. 前端关键技术实现细节 (Technical Implementation)

### 4.1 2.5D CSS 等距投影与坐标变换 (CSS Isometric Projection)
使用 CSS 3D 变换将 3D 的逻辑工位坐标映射到 2D 屏幕，通过 GPU 硬件加速避免 Reflow：
*   **CSS 变换矩阵**：
    在等距网格（Isometric Grid）中，将平面绕 Z 轴旋转 $45^\circ$，再绕 X 轴旋转 $60^\circ$：
    ```css
    .isometric-office-floor {
      transform: rotateX(60deg) rotateZ(-45deg);
      transform-style: preserve-3d;
      will-change: transform;
    }
    ```
*   **坐标数学投影公式**：
    已知工位逻辑坐标为 $(x, y, z)$，求屏幕投影坐标 $(X_s, Y_s)$：
    $$X_s = (x - y) \cdot \cos(30^\circ) = (x - y) \cdot 0.866$$
    $$Y_s = (x + y) \cdot \sin(30^\circ) - z = (x + y) \cdot 0.5 - z$$

### 4.2 Spine 2D 骨骼动画集成与状态平滑过渡 (Animation Blending)
使用 `@esotericsoftware/spine-webplayer` 加载獬豸小马资源，使用混入数据（Mix Data）实现非突变的状态平滑切换（Crossfade）：
*   **React 19 初始化与过渡设置**：
    ```typescript
    import { SpinePlayer } from "@esotericsoftware/spine-webplayer";

    const initSpineAgent = (containerId: string) => {
      return new SpinePlayer(containerId, {
        jsonUrl: "/assets/spine/xiezhi_pony.json",
        atlasUrl: "/assets/spine/xiezhi_pony.atlas",
        showControls: false,
        alpha: true,
        success: (player) => {
          const state = player.animationState;
          state.data.defaultMix = 0.3; // 默认过渡时间 0.3s
          
          // 精确配置关键状态间的过渡混入
          state.data.setMix("anim_idle_sleeping", "anim_work_typing", 0.4);
          state.data.setMix("anim_work_typing", "anim_idle_sleeping", 0.5);
          state.data.setMix("anim_work_typing", "anim_waiting_approval", 0.2);
          state.data.setMix("anim_waiting_approval", "anim_work_typing", 0.3);
          
          state.setAnimation(0, "anim_idle_sleeping", true);
        }
      });
    };
    ```
*   **双轨道动画混写 (Multi-track Rendering)**：
    *   **Track 0** (基础动作轨)：处理核心行为（打字、摸鱼、趴桌睡觉、死机沮丧）。
    *   **Track 1** (独角叠加轨)：当工作状态吞吐率高时，在此轨道播放独角高频亮起的叠加动画 `anim_horn_glow`，其 `alpha` 权重与 Eino 运行速率挂钩。

### 4.3 WebSocket 断线指数退避与抖动重连 (Exponential Backoff with Jitter)
为了应对后端网关重启等情况引发客户端瞬时重连压垮网关（Thundering Herd 惊群效应），重连机制融入指数避让与随机抖动（Jitter）：
*   **重连退避公式**：
    $$T_{\text{retry}} = \min(T_{\text{max}}, T_{\text{base}} \cdot 2^{\text{attempt}}) \pm \text{RandomJitter}$$
*   **前端连接器实现**：
    ```typescript
    class RobustWebSocket {
      private ws: WebSocket | null = null;
      private attempt = 0;
      private baseDelay = 1000;  // 基础延迟 1s
      private maxDelay = 30000;  // 最大延迟 30s
      private jitterFactor = 0.2; // 20% 的上下抖动范围

      connect() {
        this.ws = new WebSocket("ws://localhost:2028/api/eino/ws-status");
        this.ws.onopen = () => {
          this.attempt = 0;
          this.sendPing();
        };
        this.ws.onclose = () => this.scheduleReconnect();
        this.ws.onerror = () => this.ws?.close();
      }

      private scheduleReconnect() {
        const delay = Math.min(this.maxDelay, this.baseDelay * Math.pow(2, this.attempt));
        const jitter = delay * this.jitterFactor * (Math.random() * 2 - 1);
        const finalDelay = Math.max(0, delay + jitter);
        
        this.attempt++;
        setTimeout(() => this.connect(), finalDelay);
      }
    }
    ```
