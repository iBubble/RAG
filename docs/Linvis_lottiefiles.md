# 獬豸办公室大屏 (Linvis) 卡通角色 Lottie 与 SVG 动画技术规划建议书

为了提升联合审批大屏中 2D 虚拟角色的表现力、高保真度以及流畅的动效，本篇建议书归纳了基于 **LottieFiles (JSON)** 以及免 AE 的 **轻量级 SVG 肢体骨骼动画** 两大升级技术原型的路线与控制思路。

---

## 1. 方案一：Lottie 动作捕捉与 React 交互控制器

### 1.1 工作流设计
1. **美术原画 (我方提供设计蓝图/静态图)**：生成不同职业特征的角色视觉原稿；
2. **骨骼动画 (AE/Bodymovin)**：在 After Effects 中进行骨骼绑定，并导出为 `.json` 格式；
3. **前端渲染控制 (lottie-web)**：React 前端引入控制组件，根据 API 动态同步状态。

### 1.2 前端控制器原型代码 (脚手架)
当获取到 Lottie 动画 JSON 后，在前端组件中通过关键帧区间（Segments）控制行为状态：

```tsx
import React, { useRef, useEffect } from 'react';
import { Player } from '@lottiefiles/react-lottie-player';

interface AgentProps {
  status: 'working' | 'sleeping' | 'idle';
  agentKey: string;
}

export const LinvisLottieAgent: React.FC<AgentProps> = ({ status, agentKey }) => {
  const playerRef = useRef<Player>(null);

  useEffect(() => {
    const player = playerRef.current;
    if (!player) return;

    // 动态映射不同状态到 JSON 中的特定帧段 (Frame Segments)
    switch (status) {
      case 'working':
        // 循环播放走路帧 (例如第 50 帧到 100 帧)
        player.playSegments([50, 100], true);
        break;
      case 'sleeping':
        // 播放打瞌睡帧 (例如第 120 帧到 200 帧)
        player.playSegments([120, 200], true);
        break;
      case 'idle':
      default:
        // 播放待命呼吸帧 (例如第 0 帧到 49 帧)
        player.playSegments([0, 49], true);
        break;
    }
  }, [status]);

  return (
    <Player
      ref={playerRef}
      autoplay
      loop
      src={`/assets/office/lottie_${agentKey}.json`}
      style={{ width: '100px', height: '100px' }}
    />
  );
};
```

---

## 2. 方案二：免 AE 的轻量级 SVG 多肢体图层动画原型

若在无专业设计师或无动画软件的初期阶段，可以直接将 SVG 中的角色拆分为独立肢体图层，利用 React 的时钟定时器与 CSS Keyframes 组合成简易的“骨骼动画”，不仅无需外部依赖，而且完全受代码逻辑掌控。

### 2.1 结构拆解思路
在 SVG `<g>` 标签内部将小人重构为独立的子图层图元：
- **`#body-container`**：整体定位层。
- **`#agent-head`**：头部与五官层，添加微幅 `translate` 运动。
- **`#agent-eyes`**：眼睛椭圆图层，定期由 React 触发高度变化实现眨眼。
- **`#agent-left-leg` / `#agent-right-leg`**：双腿路径层，通过改变旋转角度模拟走路迈步。

### 2.2 肢体旋转动画原型代码
当 `isWalking` 为 `true` 时，开启双腿以各自髋关节为圆心的周期性摆动：

```css
/* 双腿在走路状态下交替旋转关键帧 */
.sdx-leg-left-walk {
  animation: legSwingLeft 0.6s infinite ease-in-out alternate;
  transform-origin: 50% 80%; /* 髋关节中心 */
}
.sdx-leg-right-walk {
  animation: legSwingRight 0.6s infinite ease-in-out alternate;
  transform-origin: 50% 80%;
}

@keyframes legSwingLeft {
  0% { transform: rotate(-15deg); }
  100% { transform: rotate(15deg); }
}
@keyframes legSwingRight {
  0% { transform: rotate(15deg); }
  100% { transform: rotate(-15deg); }
}
```
