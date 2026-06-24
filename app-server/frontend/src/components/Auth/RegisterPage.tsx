import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useAuthStore } from '../../store/authStore';
import { Eye, EyeOff, UserPlus, Loader2, CheckCircle } from 'lucide-react';

export default function RegisterPage() {
  const navigate = useNavigate();
  const { register } = useAuthStore();
  const [form, setForm] = useState({
    username: '',
    login_name: '',
    email: '',
    password: '',
    confirm_password: '',
    company: '',
    department: '',
  });
  const [showPwd, setShowPwd] = useState(false);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const [success, setSuccess] = useState(false);

  const update = (key: string, val: string) => {
    setForm(prev => ({ ...prev, [key]: val }));
    setError('');
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    // 前端校验
    if (!form.username.trim()) return setError('请输入用户名');
    if (!form.login_name.trim()) return setError('请输入登录名');
    if (!/^[a-zA-Z0-9_]+$/.test(form.login_name)) return setError('登录名只能包含字母、数字和下划线');
    if (!form.email.trim()) return setError('请输入邮箱');
    if (!/\S+@\S+\.\S+/.test(form.email)) return setError('邮箱格式不正确');
    if (form.password.length < 6) return setError('密码长度不能少于 6 位');
    if (form.password !== form.confirm_password) return setError('两次输入的密码不一致');

    setLoading(true);
    const result = await register(form);
    setLoading(false);
    if (result.success) {
      setSuccess(true);
    } else {
      setError(result.error || '注册失败');
    }
  };

  if (success) {
    return (
      <div className="min-h-screen bg-[#F0EDE8] flex items-center justify-center p-4 font-sans">
        <div className="bg-white rounded-[24px] border border-[#E0DCD5] shadow-[0_6px_24px_rgba(139,115,85,0.05)] p-8 max-w-md w-full text-center space-y-5">
          <CheckCircle className="w-12 h-12 text-green-600 mx-auto" />
          <h2 className="text-lg font-bold text-gray-800">注册成功！</h2>
          <p className="text-sm text-gray-600 leading-relaxed">您的账号正在等待管理员审批，审批通过后即可登录使用。</p>
          <button
            onClick={() => navigate('/login')}
            className="w-full py-2.5 bg-[#8B7355] text-white rounded-full hover:bg-[#7A6245] transition-all font-semibold text-sm active:scale-[0.98] shadow-sm mt-2"
          >
            返回登录
          </button>
        </div>
      </div>
    );
  }

  const inputClass = "w-full px-4 py-2.5 bg-[#FBFBFA] border border-[#E0DCD5] rounded-xl focus:bg-white focus:border-[#8B7355] focus:ring-2 focus:ring-[#8B7355]/10 outline-none transition-all text-sm text-gray-800 placeholder-gray-400";

  return (
    <div className="min-h-screen bg-[#F0EDE8] flex items-center justify-center p-4 font-sans">
      <div className="w-full max-w-md">
        {/* 品牌标识 */}
        <div className="text-center mb-6">
          <div className="inline-flex items-center justify-center mb-3">
            <img src="/logo.png" alt="Logo" className="w-[160px] h-auto transition-transform hover:scale-[1.02] duration-300" />
          </div>
          <h1 className="text-xl font-bold text-gray-800 tracking-tight">注册新账号</h1>
          <p className="text-[11px] text-[#8B7355] font-semibold tracking-wider mt-1 uppercase">加入 RAG 智能文档辅助系统</p>
        </div>

        <form onSubmit={handleSubmit} className="bg-white rounded-[24px] border border-[#E0DCD5] shadow-[0_6px_24px_rgba(139,115,85,0.05)] p-8 space-y-4">
          {error && (
            <div className="bg-red-50 border border-red-100 text-red-600 text-xs rounded-xl px-4 py-2.5">
              {error}
            </div>
          )}

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-xs font-semibold text-gray-500 tracking-wider mb-1.5 uppercase">用户名 <span className="text-red-500">*</span></label>
              <input type="text" value={form.username} onChange={e => update('username', e.target.value)} className={inputClass} placeholder="您的姓名" />
            </div>
            <div>
              <label className="block text-xs font-semibold text-gray-500 tracking-wider mb-1.5 uppercase">登录名 <span className="text-red-500">*</span></label>
              <input type="text" value={form.login_name} onChange={e => update('login_name', e.target.value)} className={inputClass} placeholder="字母数字下划线" />
            </div>
          </div>

          <div>
            <label className="block text-xs font-semibold text-gray-500 tracking-wider mb-1.5 uppercase">邮箱 <span className="text-red-500">*</span></label>
            <input type="email" value={form.email} onChange={e => update('email', e.target.value)} className={inputClass} placeholder="example@email.com" />
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-xs font-semibold text-gray-500 tracking-wider mb-1.5 uppercase">密码 <span className="text-red-500">*</span></label>
              <div className="relative">
                <input type={showPwd ? 'text' : 'password'} value={form.password} onChange={e => update('password', e.target.value)} className={`${inputClass} pr-10`} placeholder="至少 6 位" />
                <button type="button" onClick={() => setShowPwd(!showPwd)} className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 hover:text-[#8B7355] transition-colors">
                  {showPwd ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
                </button>
              </div>
            </div>
            <div>
              <label className="block text-xs font-semibold text-gray-500 tracking-wider mb-1.5 uppercase">确认密码 <span className="text-red-500">*</span></label>
              <input type={showPwd ? 'text' : 'password'} value={form.confirm_password} onChange={e => update('confirm_password', e.target.value)} className={inputClass} placeholder="再次输入密码" />
            </div>
          </div>

          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-xs font-semibold text-gray-500 tracking-wider mb-1.5 uppercase">公司名称</label>
              <input type="text" value={form.company} onChange={e => update('company', e.target.value)} className={inputClass} placeholder="可选" />
            </div>
            <div>
              <label className="block text-xs font-semibold text-gray-500 tracking-wider mb-1.5 uppercase">部门</label>
              <input type="text" value={form.department} onChange={e => update('department', e.target.value)} className={inputClass} placeholder="可选" />
            </div>
          </div>

          <button
            type="submit"
            disabled={loading}
            className="w-full py-2.5 bg-[#8B7355] text-white font-semibold rounded-full hover:bg-[#7A6245] transition-all duration-200 shadow-sm disabled:opacity-50 flex items-center justify-center gap-2 text-sm mt-4 active:scale-[0.98]"
          >
            {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : <UserPlus className="w-4 h-4" />}
            {loading ? '提交中...' : '注 册'}
          </button>

          <p className="text-center text-xs text-gray-500 mt-2">
            已有账号？
            <Link to="/login" className="text-[#8B7355] hover:text-[#7A6245] hover:underline font-semibold ml-1 transition-colors">
              返回登录
            </Link>
          </p>
        </form>
      </div>
    </div>
  );
}
