import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import Logo from '../components/Logo';
import { authAPI } from '../services/api';
import toast from 'react-hot-toast';

// Password change screen. Used both for the FORCED first-login change
// (must_change_password) and as a voluntary "change my password" screen.
export default function ChangePassword() {
  const navigate = useNavigate();
  const user = JSON.parse(localStorage.getItem('user') || '{}');
  const forced = !!user.must_change_password;

  const [currentPassword, setCurrentPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!currentPassword || !newPassword || !confirm) {
      toast.error('الرجاء تعبئة جميع الحقول');
      return;
    }
    if (newPassword.length < 8) {
      toast.error('كلمة المرور الجديدة يجب أن تكون 8 أحرف على الأقل');
      return;
    }
    if (newPassword !== confirm) {
      toast.error('كلمة المرور الجديدة وتأكيدها غير متطابقين');
      return;
    }
    setLoading(true);
    try {
      await authAPI.changePassword({ current_password: currentPassword, new_password: newPassword });
      // clear the flag locally so the guard lets the user through
      localStorage.setItem('user', JSON.stringify({ ...user, must_change_password: false }));
      toast.success('تم تغيير كلمة المرور بنجاح');
      navigate('/');
    } catch (err) {
      toast.error(err.response?.data?.detail || 'تعذّر تغيير كلمة المرور');
    } finally {
      setLoading(false);
    }
  };

  const handleLogout = async () => {
    try { await authAPI.logout(); } catch (e) {}
    localStorage.removeItem('token');
    localStorage.removeItem('user');
    navigate('/login');
  };

  return (
    <div className="min-h-screen bg-gradient-to-br from-bayan-dark via-bayan-green to-emerald-600 flex items-center justify-center p-4">
      <div className="bg-white rounded-2xl shadow-2xl w-full max-w-md p-8">
        <div className="text-center mb-8">
          <div className="w-16 h-16 mx-auto flex items-center justify-center mb-4">
            <Logo size={56} />
          </div>
          <h1 className="text-2xl font-bold text-gray-800">تغيير كلمة المرور</h1>
          <p className="text-gray-500 mt-2">
            {forced
              ? 'لأمان حسابك، يجب تغيير كلمة المرور قبل المتابعة'
              : 'اختر كلمة مرور جديدة لحسابك'}
          </p>
        </div>

        <form onSubmit={handleSubmit} className="space-y-5">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">كلمة المرور الحالية</label>
            <input
              type="password"
              value={currentPassword}
              onChange={(e) => setCurrentPassword(e.target.value)}
              className="w-full px-4 py-3 rounded-lg border border-gray-300 focus:ring-2 focus:ring-bayan-green focus:border-transparent outline-none transition-all text-right"
              placeholder="أدخل كلمة المرور الحالية"
              autoFocus
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">كلمة المرور الجديدة</label>
            <input
              type="password"
              value={newPassword}
              onChange={(e) => setNewPassword(e.target.value)}
              className="w-full px-4 py-3 rounded-lg border border-gray-300 focus:ring-2 focus:ring-bayan-green focus:border-transparent outline-none transition-all text-right"
              placeholder="8 أحرف على الأقل"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">تأكيد كلمة المرور الجديدة</label>
            <input
              type="password"
              value={confirm}
              onChange={(e) => setConfirm(e.target.value)}
              className="w-full px-4 py-3 rounded-lg border border-gray-300 focus:ring-2 focus:ring-bayan-green focus:border-transparent outline-none transition-all text-right"
              placeholder="أعد إدخال كلمة المرور الجديدة"
            />
          </div>

          <button
            type="submit"
            disabled={loading}
            className="w-full bg-bayan-green hover:bg-bayan-dark text-white font-bold py-3 px-4 rounded-lg transition-all duration-200 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {loading ? 'جاري الحفظ...' : 'تغيير كلمة المرور'}
          </button>
        </form>

        <div className="mt-6 text-center">
          <button onClick={handleLogout} className="text-sm text-gray-400 hover:text-gray-600">
            تسجيل الخروج
          </button>
        </div>
      </div>
    </div>
  );
}
