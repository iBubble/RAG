/**
 * LinvisDesk.tsx - 獬豸小马工位 V7 (最终版)
 *
 * 动画方案：JavaScript setInterval 精确切帧
 * - 工作时：4帧循环，每300ms切一帧
 * - 睡眠：停在第1帧 + 灰度滤镜
 * - 摸鱼：停在第4帧
 * - 中断：停在第2帧 + 警报灯
 * - 空闲：停在第1帧
 *
 * 不使用任何 CSS transform 抖动
 */

import { useState, useEffect } from 'react';

interface AgentInfo {
  status: 'working' | 'sleeping' | 'funny' | 'idle' | 'interrupted';
  funny_event: string | null;
  current_project: string | null;
  current_task: string | null;
}

interface DeskProps {
  agentKey: string;
  name: string;
  gender?: 'male' | 'female';
  avatar?: string;
  roleTitle: string;
  info: AgentInfo;
}

const BADGE: Record<string, string> = {
  chat: '🎧', planner: '🧠', checker: '🧮', auditor: '⚖️',
  service: '🖨️', vectorizer: '📂', graph: '🕸️',
  precompute: '🔮', legal: '⚖️', summary: '📝',
};

const STC: Record<string, { l: string; fg: string; bg: string }> = {
  working:     { l: '⚡ 工作中',   fg: '#059669', bg: '#ecfdf5' },
  sleeping:    { l: '💤 休息中',   fg: '#6366f1', bg: '#eef2ff' },
  idle:        { l: '😴 空闲',     fg: '#6b7280', bg: '#f9fafb' },
  funny:       { l: '☕ 摸鱼中',   fg: '#d97706', bg: '#fffbeb' },
  interrupted: { l: '🚨 等待审批', fg: '#dc2626', bg: '#fef2f2' },
};



export default function LinvisDesk({
  agentKey, name, roleTitle, info
}: DeskProps) {
  const badge = BADGE[agentKey] || '🐴';
  const st = STC[info.status] || STC.idle;
  const isW = info.status === 'working';
  const isS = info.status === 'sleeping' || info.status === 'idle';
  const isI = info.status === 'interrupted';
  const isF = info.status === 'funny';
  const stripUrl = `/assets/sprites/${agentKey}_strip.png`;

  // 只有工作状态才有帧动画，其他状态静止帧1
  const [frameIdx, setFrameIdx] = useState(0);
  useEffect(() => {
    if (isW) {
      const timer = setInterval(() => {
        setFrameIdx(i => (i + 1) % 4);
      }, 300);
      return () => clearInterval(timer);
    }
    setFrameIdx(0); // 非工作状态固定帧1
  }, [info.status, isW]);

  // 帧偏移
  const offsetPct = -(frameIdx * 25);

  return (
    <div className={`workstation ${isW ? 'ws-working' : ''}`}>
      {/* 任务气泡 */}
      {isW && info.current_task && (
        <div className="task-bubble-w">
          <span>⚡ 处理中</span>
          <p>{info.current_task}</p>
        </div>
      )}
      {isF && info.funny_event && (
        <div className="task-bubble-f">
          <span>💭 摸鱼</span>
          <p>{info.funny_event}</p>
        </div>
      )}

      {/* ====== 逐帧动画精灵（无边框，融入场景） ====== */}
      <div className="sprite-viewport">
        <img
          src={stripUrl}
          alt={name}
          draggable={false}
          className="sprite-strip"
          style={{ transform: `translateX(${offsetPct}%)` }}
        />
        {isS && (
          <div className="zzz-overlay">
            <span className="zzz zzz-1">Z</span>
            <span className="zzz zzz-2">z</span>
            <span className="zzz zzz-3">z</span>
          </div>
        )}
        {isI && <div className="alert-lamp" />}
        {isW && <div className="horn-glow" />}
      </div>

      {/* 悬浮名牌（无卡片背景） */}
      <div className="agent-label">
        <span className="label-name">{badge} {name}</span>
        <span className="label-role">{roleTitle}</span>
        <span className="label-status" style={{ backgroundColor: st.bg, color: st.fg }}>
          {st.l}
        </span>
      </div>
    </div>
  );
}
