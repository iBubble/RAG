/**
 * 全局 UI 色彩模式状态管理（Zustand + localStorage 持久化）
 * WHY: 支持“浅色/深色/跟随系统”色彩模式的响应式更新，并修改 DOM 节点属性。
 */
import { create } from 'zustand';
import { persist } from 'zustand/middleware';

export type ColorMode = 'light' | 'dark' | 'system';

interface ThemeState {
  colorMode: ColorMode;
  setColorMode: (mode: ColorMode) => void;
  applyTheme: () => void;
}

export const useThemeStore = create<ThemeState>()(
  persist(
    (set, get) => {
      // 辅助函数：根据当前的 colorMode 动态修改 HTML 元素的属性
      const updateDOM = (mode: ColorMode) => {
        const root = document.documentElement;
        
        // 解析实际的 dark/light 模式
        let resolvedMode: 'light' | 'dark' = 'light';
        if (mode === 'system') {
          const systemDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
          resolvedMode = systemDark ? 'dark' : 'light';
        } else {
          resolvedMode = mode;
        }
        
        root.setAttribute('data-mode', resolvedMode);
        
        // 为了保障兼容性，同时在 class 列表中切换 dark 类
        if (resolvedMode === 'dark') {
          root.classList.add('dark');
        } else {
          root.classList.remove('dark');
        }
      };

      return {
        colorMode: 'light',

        setColorMode: (mode) => {
          set({ colorMode: mode });
          get().applyTheme();
        },

        applyTheme: () => {
          const { colorMode } = get();
          updateDOM(colorMode);
        }
      };
    },
    {
      name: 'shengyao-theme-mode',
      partialize: (state) => ({
        colorMode: state.colorMode,
      }),
    }
  )
);
