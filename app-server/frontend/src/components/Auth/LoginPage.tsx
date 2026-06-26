import { useState, useEffect } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { useAuthStore } from '../../store/authStore';
import { Eye, EyeOff, LogIn, Loader2 } from 'lucide-react';
import { APP_VERSION, APP_NAME } from '../../version';

const API_BASE = import.meta.env.VITE_API_BASE || '';

export default function LoginPage() {
  const navigate = useNavigate();
  const { login, isLoggedIn } = useAuthStore();
  const [loginName, setLoginName] = useState('');
  const [password, setPassword] = useState('');
  const [showPwd, setShowPwd] = useState(false);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const [systemName, setSystemName] = useState(`${APP_NAME} V${APP_VERSION}`);

  useEffect(() => {
    if (isLoggedIn) navigate('/', { replace: true });
  }, [isLoggedIn]);

  // 获取系统名称用于品牌展示
  useEffect(() => {
    fetch(`${API_BASE}/api/admin/settings/public`)
      .then(r => r.json())
      .then(d => d.system_name && setSystemName(d.system_name))
      .catch(() => {});
  }, []);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!loginName.trim() || !password) {
      setError('请输入登录名和密码');
      return;
    }
    setError('');
    setLoading(true);
    const result = await login(loginName.trim(), password);
    setLoading(false);
    if (!result.success) {
      setError(result.error || '登录失败');
    }
  };

  return (
    <div className="min-h-screen bg-[#F0EDE8] flex items-center justify-center p-4 font-sans">
      <div className="w-full max-w-md">
        {/* 品牌标识 */}
        <div className="text-center mb-6">
          <div className="inline-flex items-center justify-center mb-3">
            <img src="/logo.png" alt="Logo" className="w-[210px] h-auto transition-transform hover:scale-[1.02] duration-300" />
          </div>
          <h1 className="text-xl font-bold text-gray-800 tracking-tight">{systemName}</h1>
          <p className="text-[11px] text-[#8B7355] font-semibold tracking-wider mt-1 uppercase">RAG 智能文档辅助系统</p>
        </div>

        {/* 登录卡片 */}
        <form onSubmit={handleSubmit} className="bg-white rounded-[24px] border border-[#E0DCD5] shadow-[0_6px_24px_rgba(139,115,85,0.05)] p-8 space-y-5">
          {error && (
            <div className="bg-red-50 border border-red-100 text-red-600 text-xs rounded-xl px-4 py-2.5">
              {error}
            </div>
          )}

          <div>
            <label className="block text-xs font-semibold text-gray-500 tracking-wider mb-1.5 uppercase">登录名</label>
            <input
              type="text"
              value={loginName}
              onChange={e => { setLoginName(e.target.value); setError(''); }}
              className="w-full px-4 py-2.5 bg-[#FBFBFA] border border-[#E0DCD5] rounded-xl focus:bg-white focus:border-[#8B7355] focus:ring-2 focus:ring-[#8B7355]/10 outline-none transition-all text-sm text-gray-800 placeholder-gray-400"
              placeholder="请输入登录名"
              autoFocus
            />
          </div>

          <div>
            <label className="block text-xs font-semibold text-gray-500 tracking-wider mb-1.5 uppercase">密码</label>
            <div className="relative">
              <input
                type={showPwd ? 'text' : 'password'}
                value={password}
                onChange={e => { setPassword(e.target.value); setError(''); }}
                className="w-full px-4 py-2.5 bg-[#FBFBFA] border border-[#E0DCD5] rounded-xl focus:bg-white focus:border-[#8B7355] focus:ring-2 focus:ring-[#8B7355]/10 outline-none transition-all text-sm pr-10 text-gray-800 placeholder-gray-400"
                placeholder="请输入密码"
              />
              <button
                type="button"
                onClick={() => setShowPwd(!showPwd)}
                className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 hover:text-[#8B7355] transition-colors"
              >
                {showPwd ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
              </button>
            </div>
          </div>

          <button
            type="submit"
            disabled={loading}
            className="w-full py-2.5 bg-[#8B7355] text-white font-semibold rounded-full hover:bg-[#7A6245] transition-all duration-200 shadow-sm disabled:opacity-50 flex items-center justify-center gap-2 text-sm mt-2 active:scale-[0.98]"
          >
            {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : <LogIn className="w-4 h-4" />}
            {loading ? '登录中...' : '登 录'}
          </button>

          <p className="text-center text-xs text-gray-500 mt-2">
            还没有账号？
            <Link to="/register" className="text-[#8B7355] hover:text-[#7A6245] hover:underline font-semibold ml-1 transition-colors">
              注册新账号
            </Link>
          </p>
        </form>

        <p className="text-center text-[10px] text-gray-400 tracking-widest mt-6 uppercase">
          © 智能体
        </p>
      </div>
    </div>
  );
}
