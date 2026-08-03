import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { authAPI, settingsAPI } from '../services/api';
import toast from 'react-hot-toast';

export default function Login() {
  const [tenant, setTenant] = useState('');
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const [logoUrl, setLogoUrl] = useState('');
  const navigate = useNavigate();

  useEffect(() => {
    settingsAPI.getLogo().then((res) => {
      if (res.data.url) setLogoUrl(res.data.url);
    }).catch(() => {});
  }, []);

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!tenant || !username || !password) {
      toast.error('الرجاء إدخال الجهة واسم المستخدم وكلمة المرور');
      return;
    }

    setLoading(true);
    try {
      const res = await authAPI.login(username, password, tenant.trim());
      localStorage.setItem('token', res.data.access_token);
      localStorage.setItem('user', JSON.stringify(res.data.user));
      localStorage.setItem('tenant_name', res.data.tenant_name || '');
      localStorage.setItem('tenant_slug', res.data.tenant_slug || '');
      toast.success(`مرحباً ${res.data.user.full_name}`);
      navigate('/');
    } catch (err) {
      toast.error(err.response?.data?.detail || 'خطأ في تسجيل الدخول');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-bayan-dark via-bayan-green to-emerald-600 flex items-center justify-center p-4">
      <div className="bg-white rounded-2xl shadow-2xl w-full max-w-md p-8">
        {/* Header */}
        <div className="text-center mb-8">
          {logoUrl ? (
            <img
              src={logoUrl}
              alt="شعار الجمعية"
              className="h-20 mx-auto mb-4 object-contain"
            />
          ) : (
            <div className="w-20 h-20 bg-bayan-green rounded-full mx-auto flex items-center justify-center mb-4">
              <span className="text-3xl text-white font-bold">بيان</span>
            </div>
          )}
          <h1 className="text-2xl font-bold text-gray-800">نظام نقاط البيع</h1>
          <p className="text-gray-500 mt-2">تسجيل دخول الجهة</p>
        </div>

        {/* Form */}
        <form onSubmit={handleSubmit} className="space-y-5">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">
              الجهة
            </label>
            <input
              type="text"
              value={tenant}
              onChange={(e) => setTenant(e.target.value)}
              className="w-full px-4 py-3 rounded-lg border border-gray-300 focus:ring-2 focus:ring-bayan-green focus:border-transparent outline-none transition-all text-right"
              placeholder="معرّف الجهة (مثال: bayan)"
              autoFocus
              dir="ltr"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">
              اسم المستخدم
            </label>
            <input
              type="text"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              className="w-full px-4 py-3 rounded-lg border border-gray-300 focus:ring-2 focus:ring-bayan-green focus:border-transparent outline-none transition-all text-right"
              placeholder="أدخل اسم المستخدم"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">
              كلمة المرور
            </label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full px-4 py-3 rounded-lg border border-gray-300 focus:ring-2 focus:ring-bayan-green focus:border-transparent outline-none transition-all text-right"
              placeholder="أدخل كلمة المرور"
            />
          </div>

          <button
            type="submit"
            disabled={loading}
            className="w-full bg-bayan-green hover:bg-bayan-dark text-white font-bold py-3 px-4 rounded-lg transition-all duration-200 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {loading ? 'جاري الدخول...' : 'تسجيل الدخول'}
          </button>
        </form>

        {/* Footer */}
        <div className="mt-8 text-center">
          <p className="text-xs text-gray-400">
            نظام نقاط البيع متعدد الجهات
          </p>
        </div>
      </div>
    </div>
  );
}
