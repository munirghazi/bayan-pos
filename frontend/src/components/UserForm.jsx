// Add / edit user with per-user permissions (tester feedback: clear permissions).
import { useEffect, useMemo, useState } from 'react';
import toast from 'react-hot-toast';
import { HiOutlineCheck } from 'react-icons/hi';
import { authAPI, apiError } from '../services/api';
import { Button, Field, Input, Modal, Select } from './ui';

const ROLE_HINT = {
  admin: 'كل شيء، ومعه الإعدادات والمستخدمون والخصوصية.',
  cashier: 'البيع والتبرعات وإغلاق صندوقه فقط.',
  supervisor: 'البيع والمرتجعات والتقارير واستلام البضاعة وتعديل الكميات.',
  storekeeper: 'المنتجات والمخزون والمشتريات والموردون — بدون بيع.',
  custom: 'اختر الصلاحيات بنفسك.',
};

export default function UserForm({ user, locations, onClose, onSaved }) {
  const [cat, setCat] = useState(null);
  const [saving, setSaving] = useState(false);
  const [f, setF] = useState(() => ({
    username: user?.username || '', full_name: user?.full_name || '', password: '',
    role: user?.role || 'cashier', location_id: user?.location_id ? String(user.location_id) : '',
    permissions: user?.role && user.role !== 'admin' ? user.permissions || [] : null,
  }));

  useEffect(() => { authAPI.getPermissions().then((r) => setCat(r.data)).catch(() => {}); }, []);

  const templates = useMemo(() => Object.fromEntries((cat?.templates || []).map((t) => [t.key, t])), [cat]);
  const groups = useMemo(() => {
    const g = {};
    (cat?.permissions || []).forEach((p) => { (g[p.group] = g[p.group] || []).push(p); });
    return g;
  }, [cat]);

  // effective ticks shown: template defaults until the user changes something
  const ticks = f.role === 'admin' ? (cat?.permissions || []).map((p) => p.key)
    : f.permissions ?? (templates[f.role]?.permissions || []);

  const pickRole = (role) => setF({ ...f, role, permissions: role === 'admin' ? null : role === 'custom' ? ticks : null });
  const toggle = (key) => {
    if (f.role === 'admin') return;
    const next = ticks.includes(key) ? ticks.filter((k) => k !== key) : [...ticks, key];
    const tpl = Object.values(templates).find((t) => t.permissions.length === next.length && t.permissions.every((k) => next.includes(k)));
    setF({ ...f, role: tpl ? tpl.key : 'custom', permissions: next });
  };

  const save = async () => {
    if (!user && (!f.username.trim() || !f.full_name.trim() || !f.password)) return toast.error('اسم المستخدم والاسم الكامل وكلمة المرور مطلوبة');
    if (f.password && f.password.length < 8) return toast.error('كلمة المرور 8 أحرف على الأقل');
    if (f.role !== 'admin' && ticks.length === 0) return toast.error('اختر صلاحية واحدة على الأقل');
    const body = { full_name: f.full_name.trim(), role: f.role, permissions: f.role === 'admin' ? null : ticks };
    if (f.location_id) body.location_id = parseInt(f.location_id, 10);
    if (f.password) body.password = f.password;
    setSaving(true);
    try {
      if (user) await authAPI.updateUser(user.id, body);
      else await authAPI.createUser({ ...body, username: f.username.trim() });
      toast.success(user ? 'تم حفظ التعديلات' : 'تمت إضافة المستخدم — سيُطلب منه تغيير كلمة المرور عند أول دخول');
      onSaved();
    } catch (e) { toast.error(apiError(e, 'تعذّر الحفظ')); } finally { setSaving(false); }
  };

  return (
    <Modal title={user ? `تعديل المستخدم: ${user.full_name}` : 'إضافة مستخدم جديد'} size="xl" onClose={onClose}
      footer={<><Button variant="secondary" onClick={onClose}>إلغاء</Button><Button loading={saving} onClick={save}>{user ? 'حفظ التعديلات' : 'إضافة المستخدم'}</Button></>}>
      <div className="grid md:grid-cols-2 gap-4">
        {!user && (
          <Field label="اسم المستخدم (للدخول) *" hint="بالإنجليزية بدون مسافات">
            <Input dir="ltr" value={f.username} onChange={(e) => setF({ ...f, username: e.target.value.replace(/\s/g, '') })} />
          </Field>
        )}
        <Field label="الاسم الكامل *"><Input value={f.full_name} onChange={(e) => setF({ ...f, full_name: e.target.value })} /></Field>
        <Field label={user ? 'كلمة مرور جديدة (اتركها فارغة إن لم ترد التغيير)' : 'كلمة مرور مؤقتة *'} hint="8 أحرف على الأقل">
          <Input type="password" dir="ltr" value={f.password} onChange={(e) => setF({ ...f, password: e.target.value })} />
        </Field>
        <Field label="الفرع" hint="المستخدم المُعيّن لفرع يبيع في صناديق فرعه فقط">
          <Select value={f.location_id} onChange={(e) => setF({ ...f, location_id: e.target.value })}>
            <option value="">— كل الفروع —</option>
            {locations.map((l) => <option key={l.id} value={l.id}>{l.name}</option>)}
          </Select>
        </Field>
      </div>

      <h3 className="font-bold text-gray-800 mt-6 mb-2">الدور</h3>
      <div className="grid grid-cols-2 md:grid-cols-5 gap-2">
        {[['admin', 'مدير النظام'], ...Object.values(templates).map((t) => [t.key, t.label]), ['custom', 'مخصص']].map(([key, label]) => (
          <button key={key} type="button" onClick={() => pickRole(key)}
            className={`text-right rounded-xl border p-3 transition-all ${f.role === key ? 'border-bayan-green bg-bayan-light/40 ring-2 ring-bayan-green/30' : 'border-gray-200 hover:border-gray-300'}`}>
            <div className="font-semibold text-sm text-gray-800">{label}</div>
            <div className="text-xs text-gray-500 mt-1 leading-5">{ROLE_HINT[key]}</div>
          </button>
        ))}
      </div>

      <h3 className="font-bold text-gray-800 mt-6 mb-1">الصلاحيات</h3>
      <p className="text-xs text-gray-500 mb-3">
        {f.role === 'admin' ? 'مدير النظام يملك كل الصلاحيات.' : 'اضغط على أي صلاحية لإضافتها أو إزالتها. يمكن البدء من دور جاهز ثم التعديل.'}
      </p>
      {!cat ? <p className="text-sm text-gray-400">جارٍ التحميل…</p> : (
        <div className="grid md:grid-cols-3 gap-3">
          {Object.entries(groups).map(([g, items]) => (
            <div key={g} className="rounded-xl border border-gray-200 p-3">
              <div className="text-xs font-bold text-gray-500 mb-2">{g}</div>
              <div className="space-y-1">
                {items.map((p) => {
                  const on = ticks.includes(p.key);
                  return (
                    <button key={p.key} type="button" onClick={() => toggle(p.key)} disabled={f.role === 'admin'}
                      className={`w-full flex items-start gap-2 text-right rounded-lg px-2 py-2 transition-all ${on ? 'bg-emerald-50' : 'hover:bg-gray-50'} disabled:cursor-default`}>
                      <span className={`mt-0.5 w-5 h-5 shrink-0 rounded-md border flex items-center justify-center ${on ? 'bg-emerald-500 border-emerald-500 text-white' : 'border-gray-300 bg-white'}`}>
                        {on && <HiOutlineCheck className="text-sm" />}
                      </span>
                      <span>
                        <span className="block text-sm text-gray-800">{p.label}</span>
                        <span className="block text-xs text-gray-400 leading-5">{p.description}</span>
                      </span>
                    </button>
                  );
                })}
              </div>
            </div>
          ))}
        </div>
      )}
      <p className="text-xs text-gray-400 mt-3">
        للمدير فقط دائماً: {cat?.admin_only?.join('، ')}. تغيير صلاحيات مستخدم يُخرجه من جلسته ليدخل بالصلاحيات الجديدة.
      </p>
    </Modal>
  );
}

/** Who-can-do-what table for the users screen. */
export function PermissionsTable() {
  const [cat, setCat] = useState(null);
  useEffect(() => { authAPI.getPermissions().then((r) => setCat(r.data)).catch(() => {}); }, []);
  if (!cat) return null;
  const cols = [{ key: 'admin', label: 'مدير النظام' }, ...cat.templates];
  const has = (col, p) => col.key === 'admin' || col.permissions.includes(p);
  return (
    <div className="bg-white rounded-xl border overflow-x-auto">
      <table className="w-full text-sm">
        <thead className="bg-gray-50 text-gray-500 text-xs">
          <tr>
            <th className="text-right font-medium px-4 py-3">الصلاحية</th>
            {cols.map((c) => <th key={c.key} className="font-medium px-3 py-3 text-center whitespace-nowrap">{c.label}</th>)}
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-100">
          {cat.permissions.map((p) => (
            <tr key={p.key}>
              <td className="px-4 py-2"><div className="text-gray-800">{p.label}</div><div className="text-xs text-gray-400">{p.description}</div></td>
              {cols.map((c) => <td key={c.key} className="text-center px-3">{has(c, p.key) ? <span className="text-emerald-600 font-bold">✓</span> : <span className="text-gray-300">—</span>}</td>)}
            </tr>
          ))}
          {cat.admin_only.map((a) => (
            <tr key={a} className="bg-purple-50/40">
              <td className="px-4 py-2 text-gray-800">{a}</td>
              {cols.map((c) => <td key={c.key} className="text-center px-3">{c.key === 'admin' ? <span className="text-emerald-600 font-bold">✓</span> : <span className="text-gray-300">—</span>}</td>)}
            </tr>
          ))}
        </tbody>
      </table>
      <p className="text-xs text-gray-400 px-4 py-2">الأدوار الجاهزة نقطة بداية: يمكن إضافة أو إزالة أي صلاحية لكل مستخدم على حدة.</p>
    </div>
  );
}
