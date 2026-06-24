import { useState, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuthStore } from '../../store/authStore';
import { ArrowLeft, Save, Camera, Loader2, Lock } from 'lucide-react';

const API_BASE = import.meta.env.VITE_API_BASE || '';

export default function ProfilePage() {
  const navigate = useNavigate();
  const { user, getAuthHeaders, updateUser } = useAuthStore();
  const [form, setForm] = useState({
    username: user?.username || '',
    email: user?.email || '',
    company: user?.company || '',
    department: user?.department || '',
  });
  const [pwdForm, setPwdForm] = useState({ old_password: '', new_password: '', confirm_password: '' });
  const [saving, setSaving] = useState(false);
  const [savingPwd, setSavingPwd] = useState(false);
  const [message, setMessage] = useState('');
  const [pwdMessage, setPwdMessage] = useState('');
  const [uploadingAvatar, setUploadingAvatar] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  const update = (key: string, val: string) => setForm(prev => ({ ...prev, [key]: val }));

  const handleSaveProfile = async () => {
    setSaving(true);
    setMessage('');
    try {
      const res = await fetch(`${API_BASE}/api/auth/me`, {
        method: 'PUT',
        headers: { ...getAuthHeaders(), 'Content-Type': 'application/json' },
        body: JSON.stringify(form),
      });
      if (res.ok) {
        const updated = await res.json();
        updateUser(updated);
        setMessage('保存成功');
      } else {
        const err = await res.json().catch(() => null);
        setMessage(err?.detail || '保存失败');
      }
    } catch { setMessage('网络错误'); }
    setSaving(false);
    setTimeout(() => setMessage(''), 3000);
  };

  const handleChangePassword = async () => {
    if (pwdForm.new_password !== pwdForm.confirm_password) {
      setPwdMessage('两次输入的新密码不一致');
      return;
    }
    setSavingPwd(true);
    setPwdMessage('');
    try {
      const res = await fetch(`${API_BASE}/api/auth/me/password`, {
        method: 'PUT',
        headers: { ...getAuthHeaders(), 'Content-Type': 'application/json' },
        body: JSON.stringify(pwdForm),
      });
      if (res.ok) {
        setPwdMessage('密码修改成功');
        setPwdForm({ old_password: '', new_password: '', confirm_password: '' });
      } else {
        const err = await res.json().catch(() => null);
        setPwdMessage(err?.detail || '修改失败');
      }
    } catch { setPwdMessage('网络错误'); }
    setSavingPwd(false);
    setTimeout(() => setPwdMessage(''), 3000);
  };

  const handleAvatarUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    if (file.size > 10 * 1024 * 1024) {
      alert('头像文件不能超过 10MB');
      return;
    }
    setUploadingAvatar(true);
    const fd = new FormData();
    fd.append('file', file);
    try {
      const res = await fetch(`${API_BASE}/api/auth/me/avatar`, {
        method: 'POST',
        headers: getAuthHeaders(),
        body: fd,
      });
      if (res.ok) {
        const data = await res.json();
        if (user) updateUser({ ...user, avatar: data.avatar });
      }
    } catch { }
    setUploadingAvatar(false);
  };

  const avatarUrl = user?.avatar ? `${API_BASE}${user.avatar}` : '';
  const inputClass = "w-full px-4 py-2.5 border border-gray-200 rounded-xl focus:ring-2 focus:ring-indigo-500 focus:border-transparent outline-none text-sm";

  return (
    <div className="min-h-screen bg-gray-50">
      <div className="max-w-2xl mx-auto py-8 px-4">
        {/* 顶部 */}
        <button onClick={() => navigate('/')} className="flex items-center gap-2 text-gray-500 hover:text-gray-700 text-sm mb-6">
          <ArrowLeft className="w-4 h-4" /> 返回首页
        </button>

        <h1 className="text-2xl font-bold text-gray-900 mb-8">个人设置</h1>

        {/* 头像 */}
        <div className="bg-white rounded-xl border border-gray-200 p-6 mb-6">
          <h3 className="text-sm font-medium text-gray-700 mb-4">头像</h3>
          <div className="flex items-center gap-4">
            <div
              className="w-20 h-20 rounded-full bg-gradient-to-br from-indigo-400 to-blue-500 flex items-center justify-center text-white text-2xl font-bold overflow-hidden cursor-pointer relative group"
              onClick={() => fileRef.current?.click()}
            >
              {avatarUrl ? (
                <img src={avatarUrl} alt="头像" className="w-full h-full object-cover" />
              ) : (
                user?.username?.charAt(0) || 'U'
              )}
              <div className="absolute inset-0 bg-black/40 flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity">
                {uploadingAvatar ? <Loader2 className="w-5 h-5 animate-spin text-white" /> : <Camera className="w-5 h-5 text-white" />}
              </div>
            </div>
            <div>
              <p className="text-sm text-gray-600">点击头像更换</p>
              <p className="text-xs text-gray-400">支持 jpg/png/gif，最大 10MB</p>
            </div>
            <input ref={fileRef} type="file" accept="image/*" className="hidden" onChange={handleAvatarUpload} />
          </div>
        </div>

        {/* 基本信息 */}
        <div className="bg-white rounded-xl border border-gray-200 p-6 mb-6 space-y-4">
          <h3 className="text-sm font-medium text-gray-700">基本信息</h3>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-xs text-gray-500 mb-1">用户名</label>
              <input type="text" value={form.username} onChange={e => update('username', e.target.value)} className={inputClass} />
            </div>
            <div>
              <label className="block text-xs text-gray-500 mb-1">登录名 <span className="text-gray-300">（不可修改）</span></label>
              <input type="text" value={user?.login_name || ''} disabled className={`${inputClass} bg-gray-50 text-gray-400`} />
            </div>
          </div>
          <div>
            <label className="block text-xs text-gray-500 mb-1">邮箱</label>
            <input type="email" value={form.email} onChange={e => update('email', e.target.value)} className={inputClass} />
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-xs text-gray-500 mb-1">公司</label>
              <input type="text" value={form.company} onChange={e => update('company', e.target.value)} className={inputClass} />
            </div>
            <div>
              <label className="block text-xs text-gray-500 mb-1">部门</label>
              <input type="text" value={form.department} onChange={e => update('department', e.target.value)} className={inputClass} />
            </div>
          </div>
          <div className="flex items-center gap-3">
            <button onClick={handleSaveProfile} disabled={saving} className="px-5 py-2 bg-indigo-500 text-white rounded-xl hover:bg-indigo-600 text-sm font-medium flex items-center gap-2 disabled:opacity-50">
              {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />} 保存
            </button>
            {message && <span className={`text-sm ${message === '保存成功' ? 'text-green-600' : 'text-red-500'}`}>{message}</span>}
          </div>
        </div>

        {/* 修改密码 */}
        <div className="bg-white rounded-xl border border-gray-200 p-6 space-y-4">
          <h3 className="text-sm font-medium text-gray-700 flex items-center gap-2"><Lock className="w-4 h-4" /> 修改密码</h3>
          <div>
            <label className="block text-xs text-gray-500 mb-1">原密码</label>
            <input type="password" value={pwdForm.old_password} onChange={e => setPwdForm(p => ({ ...p, old_password: e.target.value }))} className={inputClass} />
          </div>
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="block text-xs text-gray-500 mb-1">新密码</label>
              <input type="password" value={pwdForm.new_password} onChange={e => setPwdForm(p => ({ ...p, new_password: e.target.value }))} className={inputClass} placeholder="至少 6 位" />
            </div>
            <div>
              <label className="block text-xs text-gray-500 mb-1">确认新密码</label>
              <input type="password" value={pwdForm.confirm_password} onChange={e => setPwdForm(p => ({ ...p, confirm_password: e.target.value }))} className={inputClass} />
            </div>
          </div>
          <div className="flex items-center gap-3">
            <button onClick={handleChangePassword} disabled={savingPwd} className="px-5 py-2 bg-gray-800 text-white rounded-xl hover:bg-gray-900 text-sm font-medium flex items-center gap-2 disabled:opacity-50">
              {savingPwd ? <Loader2 className="w-4 h-4 animate-spin" /> : <Lock className="w-4 h-4" />} 修改密码
            </button>
            {pwdMessage && <span className={`text-sm ${pwdMessage === '密码修改成功' ? 'text-green-600' : 'text-red-500'}`}>{pwdMessage}</span>}
          </div>
        </div>
      </div>
    </div>
  );
}
