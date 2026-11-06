import { useEffect, useState } from 'react';
import { NavLink, Outlet, useNavigate } from 'react-router-dom';
import toast from 'react-hot-toast';
import { HiOutlineShieldCheck, HiOutlineOfficeBuilding, HiOutlineClipboardList, HiOutlineKey, HiOutlineLogout } from 'react-icons/hi';
import { Button, Field, Input, Modal, Spinner } from '../components/ui';
import { platformAPI, errMsg } from './api';
import { fmt } from './labels';

export default function Layout() {
  const [me, setMe] = useState(null);
  const [pwOpen, setPwOpen] = useState(false);
  const navigate = useNavigate();

  useEffect(() => {
    platformAPI.me().then((r) => setMe(r.data)).catch(() => navigate('/login', { replace: true }));
  }, [navigate]);

  const logout = async () => {
    try { await platformAPI.logout(); } catch (e) { /* ignore */ }
    navigate('/login', { replace: true });
  };

  if (!me) return <div className="min-h-screen flex items-center justify-center text-slate-400"><Spinner size={32} /></div>;

  const link = ({ isActive }) =>
    `inline-flex items-center gap-2 px-3 py-2 rounded-lg text-sm font-medium ${isActive ? 'bg-white/10 text-white' : 'text-slate-300 hover:text-white'}`;

  return (
    <div className="min-h-screen bg-slate-50">
      <header className="bg-slate-900 text-white">
        <div className="max-w-7xl mx-auto px-3 sm:px-4 h-14 flex items-center gap-2 sm:gap-4">
          <div className="flex items-center gap-2 font-bold whitespace-nowrap">
            <HiOutlineShieldCheck className="text-amber-300 text-xl" />
            <span className="hidden sm:inline">إدارة المنصة</span>
          </div>
          <nav className="flex items-center gap-1">
            <NavLink to="/tenants" className={link}><HiOutlineOfficeBuilding />المنشآت</NavLink>
            <NavLink to="/audit" className={link}><HiOutlineClipboardList /><span className="whitespace-nowrap">السجل</span></NavLink>
          </nav>
          <div className="mr-auto flex items-center gap-3 text-sm">
            <span className="hidden sm:inline text-slate-300" title={`آخر دخول: ${fmt(me.admin.last_login_at)} من ${me.admin.last_login_ip || '—'}`}>
              {me.admin.full_name}
            </span>
            <button onClick={() => setPwOpen(true)} className="text-slate-300 hover:text-white" title="تغيير كلمة المرور"><HiOutlineKey className="text-lg" /></button>
            <button onClick={logout} className="inline-flex items-center gap-1 text-slate-300 hover:text-white whitespace-nowrap" title="خروج"><HiOutlineLogout className="text-lg" /><span className="hidden sm:inline">خروج</span></button>
          </div>
        </div>
      </header>
      <main className="max-w-7xl mx-auto px-4 py-6">
        <Outlet />
      </main>
      <footer className="max-w-7xl mx-auto px-4 pb-6 text-xs text-slate-400">
        تنتهي الجلسة بعد {me.session_minutes} دقيقة من عدم النشاط. كل عملية هنا تُسجَّل باسمك.
      </footer>
      {pwOpen && <ChangePassword onClose={() => setPwOpen(false)} onDone={() => navigate('/login', { replace: true })} />}
    </div>
  );
}

function ChangePassword({ onClose, onDone }) {
  const [f, setF] = useState({ current_password: '', new_password: '', confirm: '', code: '' });
  const [saving, setSaving] = useState(false);
  const set = (k) => (e) => setF({ ...f, [k]: e.target.value });

  const save = async () => {
    if (f.new_password !== f.confirm) return toast.error('كلمتا المرور غير متطابقتين');
    setSaving(true);
    try {
      await platformAPI.changePassword({ current_password: f.current_password, new_password: f.new_password, code: f.code });
      toast.success('تم تغيير كلمة المرور. سجّل الدخول مجدداً.');
      onDone();
    } catch (e) { toast.error(errMsg(e)); } finally { setSaving(false); }
  };

  return (
    <Modal title="تغيير كلمة المرور" size="sm" onClose={onClose}
      footer={<><Button variant="secondary" onClick={onClose}>إلغاء</Button><Button loading={saving} onClick={save}>حفظ</Button></>}>
      <div className="space-y-3">
        <Field label="كلمة المرور الحالية"><Input type="password" dir="ltr" value={f.current_password} onChange={set('current_password')} /></Field>
        <Field label="كلمة المرور الجديدة" hint="12 حرفاً على الأقل، حروف وأرقام">
          <Input type="password" dir="ltr" value={f.new_password} onChange={set('new_password')} />
        </Field>
        <Field label="تأكيد كلمة المرور الجديدة"><Input type="password" dir="ltr" value={f.confirm} onChange={set('confirm')} /></Field>
        <Field label="رمز التحقق من التطبيق">
          <Input dir="ltr" inputMode="numeric" maxLength={6} className="text-center font-mono tracking-widest"
            value={f.code} onChange={(e) => setF({ ...f, code: e.target.value.replace(/\D/g, '') })} />
        </Field>
      </div>
    </Modal>
  );
}
