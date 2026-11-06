import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import { QRCodeSVG } from 'qrcode.react';
import toast from 'react-hot-toast';
import { HiOutlineShieldCheck, HiOutlineLockClosed } from 'react-icons/hi';
import { Button, Field, Input } from '../components/ui';
import { platformAPI, errMsg } from './api';

export default function Login() {
  const [step, setStep] = useState('password');       // password | code
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [code, setCode] = useState('');
  const [mfa, setMfa] = useState(null);                // {mfa_token, enroll, secret, otpauth_uri}
  const [loading, setLoading] = useState(false);
  const [expired, setExpired] = useState(false);
  const navigate = useNavigate();

  useEffect(() => {
    if (sessionStorage.getItem('platform_expired')) {
      setExpired(true);
      sessionStorage.removeItem('platform_expired');
    }
  }, []);

  const submitPassword = async (e) => {
    e.preventDefault();
    if (!username || !password) return toast.error('أدخل اسم المستخدم وكلمة المرور');
    setLoading(true);
    try {
      const r = await platformAPI.login(username.trim(), password);
      setMfa(r.data);
      setPassword('');
      setStep('code');
    } catch (err) {
      toast.error(errMsg(err, 'تعذّر الدخول'));
    } finally { setLoading(false); }
  };

  const submitCode = async (e) => {
    e.preventDefault();
    if (code.replace(/\s/g, '').length !== 6) return toast.error('أدخل الرمز المكوّن من 6 أرقام');
    setLoading(true);
    try {
      await platformAPI.mfa(mfa.mfa_token, code);
      navigate('/tenants', { replace: true });
    } catch (err) {
      const status = err.response?.status;
      toast.error(errMsg(err, 'رمز التحقق غير صحيح'));
      setCode('');
      if (status === 429 || (status === 401 && /مهلة/.test(errMsg(err)))) {
        setStep('password'); setMfa(null);
      }
    } finally { setLoading(false); }
  };

  return (
    <div className="min-h-screen bg-slate-900 flex items-center justify-center p-4">
      <div className="w-full max-w-md">
        <div className="text-center mb-6 text-white">
          <div className="inline-flex w-14 h-14 rounded-2xl bg-amber-400/15 text-amber-300 items-center justify-center text-3xl mb-3">
            <HiOutlineShieldCheck />
          </div>
          <h1 className="text-2xl font-bold">إدارة المنصة</h1>
          <p className="text-slate-400 text-sm mt-1">للمشرفين المصرّح لهم فقط · كل العمليات مسجّلة</p>
        </div>

        <div className="bg-white rounded-2xl shadow-2xl p-7">
          {expired && step === 'password' && (
            <div className="mb-4 text-sm bg-amber-50 text-amber-800 rounded-xl px-4 py-3">انتهت الجلسة. سجّل الدخول مجدداً.</div>
          )}

          {step === 'password' && (
            <form onSubmit={submitPassword} className="space-y-4">
              <Field label="اسم المستخدم">
                <Input value={username} onChange={(e) => setUsername(e.target.value)} autoComplete="username" dir="ltr" autoFocus />
              </Field>
              <Field label="كلمة المرور">
                <Input type="password" value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="current-password" dir="ltr" />
              </Field>
              <Button type="submit" loading={loading} className="w-full !bg-slate-900 hover:!bg-slate-800" icon={<HiOutlineLockClosed />}>
                متابعة
              </Button>
            </form>
          )}

          {step === 'code' && mfa && (
            <form onSubmit={submitCode} className="space-y-4">
              {mfa.enroll ? (
                <div className="space-y-3">
                  <div className="text-sm text-slate-700 leading-7">
                    <p className="font-bold text-slate-900">تفعيل التحقق الثنائي (أول دخول)</p>
                    <p>١. افتح تطبيق المصادقة على جوالك (Google Authenticator أو Microsoft Authenticator أو Authy).</p>
                    <p>٢. امسح الرمز التالي، ثم أدخل الرقم المكوّن من 6 خانات الذي يظهر في التطبيق.</p>
                  </div>
                  <div className="flex justify-center p-3 bg-white border border-slate-200 rounded-xl">
                    <QRCodeSVG value={mfa.otpauth_uri} size={180} level="M" />
                  </div>
                  <details className="text-xs text-slate-500">
                    <summary className="cursor-pointer">لا يمكن المسح؟ أدخل المفتاح يدوياً</summary>
                    <div dir="ltr" className="mt-2 font-mono text-sm bg-slate-50 rounded-lg p-2 break-all select-all text-slate-800">
                      {mfa.secret.match(/.{1,4}/g).join(' ')}
                    </div>
                  </details>
                </div>
              ) : (
                <p className="text-sm text-slate-600">أدخل الرمز المكوّن من 6 أرقام من تطبيق المصادقة.</p>
              )}
              <Field label="رمز التحقق">
                <Input autoFocus value={code} inputMode="numeric" autoComplete="one-time-code" maxLength={7} dir="ltr"
                  className="text-center text-2xl tracking-[0.5em] font-mono"
                  onChange={(e) => setCode(e.target.value.replace(/[^\d]/g, ''))} />
              </Field>
              <Button type="submit" loading={loading} className="w-full !bg-slate-900 hover:!bg-slate-800">دخول</Button>
              <button type="button" className="w-full text-sm text-slate-500 hover:text-slate-700"
                onClick={() => { setStep('password'); setMfa(null); setCode(''); }}>رجوع</button>
            </form>
          )}
        </div>
      </div>
    </div>
  );
}
