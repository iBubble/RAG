/**
 * 认证状态管理（Zustand + localStorage 持久化）
 * WHY: JWT Token 和用户信息需要跨组件共享，且刷新页面后保持登录状态。
 */
import { create } from 'zustand';
import { persist } from 'zustand/middleware';

const API_BASE = import.meta.env.VITE_API_BASE || '';

export interface User {
  id: string;
  username: string;
  login_name: string;
  email: string;
  company: string;
  department: string;
  role: 'admin' | 'user';
  status: string;
  avatar: string;
  created_at: string;
}

interface AuthState {
  token: string | null;
  user: User | null;
  isLoggedIn: boolean;
  
  login: (login_name: string, password: string) => Promise<{ success: boolean; error?: string }>;
  register: (data: RegisterData) => Promise<{ success: boolean; error?: string }>;
  logout: () => void;
  updateUser: (user: User) => void;
  fetchMe: () => Promise<void>;
  getAuthHeaders: () => Record<string, string>;
}

export interface RegisterData {
  username: string;
  login_name: string;
  email: string;
  password: string;
  confirm_password: string;
  company?: string;
  department?: string;
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set, get) => ({
      token: null,
      user: null,
      isLoggedIn: false,

      login: async (login_name, password) => {
        try {
          const res = await fetch(`${API_BASE}/api/auth/login`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ login_name, password }),
          });
          const data = await res.json();
          if (!res.ok) {
            return { success: false, error: data.detail || '登录失败' };
          }
          set({ token: data.token, user: data.user, isLoggedIn: true });
          return { success: true };
        } catch {
          return { success: false, error: '系统服务连接超时' };
        }
      },

      register: async (data) => {
        try {
          const res = await fetch(`${API_BASE}/api/auth/register`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data),
          });
          const result = await res.json();
          if (!res.ok) {
            return { success: false, error: result.detail || '注册失败' };
          }
          return { success: true };
        } catch {
          return { success: false, error: '系统服务连接超时' };
        }
      },

      logout: () => {
        set({ token: null, user: null, isLoggedIn: false });
      },

      updateUser: (user) => {
        set({ user });
      },

      fetchMe: async () => {
        const { token } = get();
        if (!token) return;
        try {
          const res = await fetch(`${API_BASE}/api/auth/me`, {
            headers: { Authorization: `Bearer ${token}` },
          });
          if (res.ok) {
            const user = await res.json();
            set({ user, isLoggedIn: true });
          } else {
            // Token 过期或无效
            set({ token: null, user: null, isLoggedIn: false });
          }
        } catch {
          // 网络错误，不清除状态
        }
      },

      getAuthHeaders: () => {
        const { token } = get();
        if (!token) return { 'Cache-Control': 'no-cache', 'Pragma': 'no-cache' } as Record<string, string>;
        return { 
          Authorization: `Bearer ${token}`,
          'Cache-Control': 'no-cache',
          'Pragma': 'no-cache'
        } as Record<string, string>;
      },
    }),
    {
      name: 'shengyao-auth',
      partialize: (state) => ({
        token: state.token,
        user: state.user,
        isLoggedIn: state.isLoggedIn,
      }),
    }
  )
);
