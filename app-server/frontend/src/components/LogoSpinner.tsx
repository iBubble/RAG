/**
 * LogoSpinner — 统一全局 Loading 动画组件
 * WHY: 围绕项目 logo 外圈转动的渐变环状动画，提供两种模式：
 *   1. overlay（默认）: 半透明遮罩 + 毛玻璃背景，覆盖父容器居中显示
 *   2. inline: 无遮罩，较小尺寸，直接嵌入内容流中
 *
 * 用法:
 *   <LogoSpinner />                      — overlay 模式（父容器需 relative）
 *   <LogoSpinner size={56} overlay={false} />  — inline 模式
 */
import { useEffect } from 'react';

// WHY: 动态注入 CSS keyframes，避免在每个使用页面重复定义
const STYLE_ID = 'logo-spinner-keyframes';

function ensureStyles() {
  if (typeof document === 'undefined') return;
  if (document.getElementById(STYLE_ID)) return;
  const style = document.createElement('style');
  style.id = STYLE_ID;
  style.textContent = `
    @keyframes logo-ring-spin {
      0%   { transform: rotate(0deg); }
      100% { transform: rotate(360deg); }
    }
    @keyframes logo-ring-pulse {
      0%, 100% { opacity: 0.7; }
      50%      { opacity: 1; }
    }
    .logo-spinner-ring {
      animation: logo-ring-spin 1.4s cubic-bezier(0.4, 0, 0.2, 1) infinite;
    }
    .logo-spinner-pulse {
      animation: logo-ring-pulse 2s ease-in-out infinite;
    }
  `;
  document.head.appendChild(style);
}

interface LogoSpinnerProps {
  /** logo + 环的整体尺寸，默认 80 */
  size?: number;
  /** 是否以半透明遮罩覆盖父容器（父容器需 position: relative），默认 true */
  overlay?: boolean;
  /** 自定义提示文案 */
  text?: string;
}

export default function LogoSpinner({
  size = 80,
  overlay = true,
  text = '加载中…',
}: LogoSpinnerProps) {
  useEffect(ensureStyles, []);

  const ringSize = size + 20;
  const strokeW = 3;
  const r = (ringSize - strokeW) / 2;
  const circ = 2 * Math.PI * r;

  const content = (
    <div className="flex flex-col items-center gap-2 logo-spinner-pulse">
      <div className="relative" style={{ width: ringSize, height: ringSize }}>
        {/* 旋转渐变环 */}
        <svg className="logo-spinner-ring absolute inset-0"
          width={ringSize} height={ringSize}>
          <circle cx={ringSize / 2} cy={ringSize / 2} r={r}
            fill="none" stroke="url(#logo-grad)" strokeWidth={strokeW}
            strokeLinecap="round"
            strokeDasharray={`${circ * 0.3} ${circ * 0.7}`}
          />
          <defs>
            <linearGradient id="logo-grad" x1="0%" y1="0%" x2="100%" y2="100%">
              <stop offset="0%" stopColor="#6366f1" />
              <stop offset="50%" stopColor="#10b981" />
              <stop offset="100%" stopColor="#6366f1" stopOpacity="0.2" />
            </linearGradient>
          </defs>
        </svg>
        {/* 居中 Logo */}
        <img src="/logo.png" alt="Loading"
          className="absolute"
          style={{
            width: size * 0.55, height: size * 0.55,
            top: '50%', left: '50%',
            transform: 'translate(-50%, -50%)',
            borderRadius: '50%',
            objectFit: 'contain',
          }}
        />
      </div>
      {text && (
        <span className="text-xs text-gray-400 font-medium tracking-wide">
          {text}
        </span>
      )}
    </div>
  );

  if (overlay) {
    return (
      <div className="absolute inset-0 z-20 flex items-center justify-center"
        style={{
          backgroundColor: 'rgba(248, 250, 252, 0.75)',
          backdropFilter: 'blur(2px)',
        }}>
        {content}
      </div>
    );
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center"
      style={{ backgroundColor: 'rgba(248, 250, 252, 0.65)' }}>
      {content}
    </div>
  );
}
