import { useCallback, useEffect, useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import toast from 'react-hot-toast';
import { HiOutlineArrowRight, HiOutlineClipboardCopy, HiOutlineExclamation } from 'react-icons/hi';
import { Badge, Button, Card, Field, Input, Modal, Select, Spinner, Textarea } from '../components/ui';
import { platformAPI, errMsg } from './api';
import { CapabilityFields, IdentityFields, Toggle, identityPayload } from './forms';
import { ACTIONS, ROLES, VERIFICATION, describeDetail, fmt } from './labels';

const TABS = [['overview', 'نظرة عامة'], ['identity', 'الهوية'], ['capabilities', 'الصلاحيات'], ['users', 'المستخدمون'],
  ['branches', 'الفروع'], ['activity', 'النشاط'], ['danger', 'الإيقاف والحذف']];

export default function TenantPage() {
  const { id } = useParams();
  const [t, setT] = useState(null);
  const [meta, setMeta] = useState(null);
  const [tab, setTab] = useState('overview');

  const load = useCallback(() => platformAPI.tenant(id).then((r) => setT(r.data)).catch((e) => toast.error(errMsg(e))), [id]);
  useEffect(() => { load(); platformAPI.meta().then((r) => setMeta(r.data)); }, [load]);

  if (!t || !meta) return <div className="p-10 flex justify-center text-slate-400"><Spinner size={28} /></div>;

  return (
    <div>
      <Link to="/tenants" className="inline-flex items-center gap-1 text-sm text-slate-500 hover:text-slate-800 mb-3"><HiOutlineArrowRight />المنشآت</Link>
      <div className="flex flex-wrap items-start justify-between gap-3 mb-4">
        <div>
          <h1 className="text-2xl font-bold text-slate-800">{t.name}</h1>
          <div className="flex flex-wrap items-center gap-2 mt-1 text-sm text-slate-500">
            <span dir="ltr" className="font-mono">{t.slug}</span>·<span>{t.entity_type_label}</span>
            {t.is_active ? <Badge tone="green">فعّالة</Badge> : <Badge tone="red">موقوفة</Badge>}
            {t.verification_status !== 'verified' && <Badge tone="amber">{VERIFICATION[t.verification_status]}</Badge>}
          </div>
        </div>
      </div>
      {t.missing.length > 0 && (
        <div className="mb-4 flex items-center gap-2 text-sm bg-amber-50 text-amber-800 rounded-xl px-4 py-3">
          <HiOutlineExclamation className="text-lg shrink-0" />بيانات ناقصة تُطبع على المستندات: {t.missing.join('، ')}
        </div>
      )}
      <div className="flex gap-1 overflow-x-auto border-b border-slate-200 mb-5">
        {TABS.map(([v, l]) => (
          <button key={v} onClick={() => setTab(v)}
            className={`px-4 py-2.5 text-sm whitespace-nowrap border-b-2 -mb-px ${tab === v ? 'border-slate-900 text-slate-900 font-semibold' : 'border-transparent text-slate-500 hover:text-slate-700'}`}>{l}</button>
        ))}
      </div>

      {tab === 'overview' && <Overview t={t} />}
      {tab === 'identity' && <IdentityTab t={t} meta={meta} onSaved={load} />}
      {tab === 'capabilities' && <CapsTab t={t} meta={meta} onSaved={load} />}
      {tab === 'users' && <UsersTab t={t} onChanged={load} />}
      {tab === 'branches' && <BranchesTab t={t} />}
      {tab === 'activity' && <ActivityTab t={t} />}
      {tab === 'danger' && <DangerTab t={t} onChanged={load} />}
    </div>
  );
}

function Stat({ label, value }) {
  return <Card className="!p-4"><div className="text-xs text-slate-500">{label}</div><div className="text-2xl font-bold text-slate-800 mt-1">{value}</div></Card>;
}

function Overview({ t }) {
  const s = t.stats;
  const a = t.address || {};
  const addr = [a.short_address, a.building_number && `مبنى ${a.building_number}`, a.street_name,
    a.additional_number && `فرعي ${a.additional_number}`, a.district, a.postal_code, a.city, a.region].filter(Boolean).join('، ');
  return (
    <div className="space-y-5">
      <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-7 gap-3">
        <Stat label="المستخدمون" value={s.users} /><Stat label="الفروع" value={s.branches} />
        <Stat label="الصناديق" value={s.registers} /><Stat label="المنتجات" value={s.products} />
        <Stat label="الفواتير" value={s.sales} /><Stat label="إشعارات دائنة" value={s.credit_notes} />
        <Stat label="التبرعات" value={t.donations_effective ? s.donations : '—'} />
      </div>
      <Card>
        <dl className="grid sm:grid-cols-2 gap-x-8 gap-y-2 text-sm">
          {[['تاريخ الإنشاء', fmt(t.created_at, false)], ['آخر نشاط', fmt(s.last_activity_at)],
            ['ضريبة القيمة المضافة', t.vat_enabled ? `${t.vat_number || '—'} · ${t.vat_rate ?? 15}%` : 'غير مسجلة'],
            ['الرقم الموحد', t.unified_number || '—'],
            ['العنوان الوطني (تُدخله المنشأة)', addr || '—']].map(([k, v]) => (
            <div key={k} className="flex justify-between gap-3 border-b border-slate-100 py-1.5"><dt className="text-slate-500">{k}</dt><dd className="text-slate-800 text-left">{v}</dd></div>
          ))}
        </dl>
      </Card>
    </div>
  );
}

function IdentityTab({ t, meta, onSaved }) {
  const [v, setV] = useState(() => ({ ...t, vat_rate: t.vat_rate ?? 15 }));
  const [saving, setSaving] = useState(false);
  const type = meta.entity_types.find((x) => x.key === v.entity_type);
  const loseDonations = t.donations_enabled && type?.group !== 'nonprofit';
  const hasDocs = t.stats.documents > 0;

  const save = async () => {
    if (loseDonations && !window.confirm('النوع الجديد ليس غير ربحي: سيتم إيقاف التبرعات لهذه المنشأة. متابعة؟')) return;
    setSaving(true);
    try { await platformAPI.updateIdentity(t.id, identityPayload(v)); toast.success('تم حفظ الهوية'); onSaved(); }
    catch (e) { toast.error(errMsg(e)); } finally { setSaving(false); }
  };
  return (
    <Card className="max-w-3xl">
      {hasDocs && (
        <p className="text-xs text-slate-500 bg-slate-50 rounded-lg p-3 mb-4">
          المستندات الصادرة سابقاً تحتفظ بالهوية وقت إصدارها ولا تتغير؛ التعديل يسري على المستندات الجديدة فقط.
        </p>
      )}
      <IdentityFields value={v} onChange={setV} types={meta.entity_types} />
      <div className="flex justify-end mt-5"><Button loading={saving} onClick={save}>حفظ الهوية</Button></div>
    </Card>
  );
}

function CapsTab({ t, onSaved }) {
  const [v, setV] = useState(t);
  const [saving, setSaving] = useState(false);
  const nonprofit = t.entity_group === 'nonprofit';
  const save = async () => {
    setSaving(true);
    try {
      await platformAPI.updateCapabilities(t.id, {
        sales_enabled: v.sales_enabled, donations_enabled: v.donations_enabled && nonprofit,
        purchasing_enabled: v.purchasing_enabled, inventory_enabled: v.inventory_enabled,
        show_powered_by: v.show_powered_by, verification_status: v.verification_status,
      });
      toast.success('تم حفظ الصلاحيات'); onSaved();
    } catch (e) { toast.error(errMsg(e)); } finally { setSaving(false); }
  };
  return (
    <Card className="max-w-3xl">
      <CapabilityFields value={v} onChange={setV} nonprofit={nonprofit} />
      <div className="border-t border-slate-100 mt-2 pt-2">
        <Toggle checked={v.show_powered_by} onChange={(x) => setV({ ...v, show_powered_by: x })} label="إظهار «يعمل بواسطة» في الإيصالات" />
      </div>
      <div className="max-w-xs mt-3">
        <Field label="حالة التحقق">
          <Select value={v.verification_status} onChange={(e) => setV({ ...v, verification_status: e.target.value })}>
            {meta_statuses.map((s) => <option key={s} value={s}>{VERIFICATION[s]}</option>)}
          </Select>
        </Field>
      </div>
      <div className="flex justify-end mt-5"><Button loading={saving} onClick={save}>حفظ الصلاحيات</Button></div>
    </Card>
  );
}
const meta_statuses = ['verified', 'pending', 'limited', 'rejected'];

function UsersTab({ t, onChanged }) {
  const [shown, setShown] = useState(null);
  const reset = async (u) => {
    if (!window.confirm(`إعادة تعيين كلمة مرور «${u.username}»؟ ستتوقف كلمة المرور الحالية فوراً.`)) return;
    try { const r = await platformAPI.resetPassword(t.id, u.id); setShown(r.data); onChanged(); }
    catch (e) { toast.error(errMsg(e)); }
  };
  return (
    <Card padded={false} className="max-w-4xl">
      <table className="w-full text-sm">
        <thead className="bg-slate-50 text-slate-500 text-xs"><tr>
          <th className="text-right font-medium px-4 py-3">المستخدم</th><th className="text-right font-medium px-3 py-3">الدور</th>
          <th className="text-right font-medium px-3 py-3">الحالة</th><th className="px-3 py-3" />
        </tr></thead>
        <tbody className="divide-y divide-slate-100">
          {t.users.map((u) => (
            <tr key={u.id}>
              <td className="px-4 py-3"><div className="font-medium text-slate-800">{u.full_name}</div><div dir="ltr" className="text-xs text-slate-400 font-mono text-right">{u.username}</div></td>
              <td className="px-3 py-3">{ROLES[u.role] || u.role}</td>
              <td className="px-3 py-3"><div className="flex flex-wrap gap-1">
                {u.is_active ? <Badge tone="green">نشط</Badge> : <Badge tone="gray">معطل</Badge>}
                {u.must_change_password && <Badge tone="amber">بانتظار تغيير كلمة المرور</Badge>}
                {u.locked && <Badge tone="red">مقفل مؤقتاً</Badge>}
              </div></td>
              <td className="px-3 py-3 text-left"><Button size="sm" variant="outline" onClick={() => reset(u)}>إعادة تعيين كلمة المرور</Button></td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="text-xs text-slate-400 px-4 py-3">إضافة المستخدمين وتعديلهم يتم من داخل المنشأة (مدير المنشأة). هنا للطوارئ فقط.</p>
      {shown && (
        <Modal title="كلمة مرور مؤقتة" size="sm" onClose={() => setShown(null)} footer={<Button onClick={() => setShown(null)}>تم</Button>}>
          <p className="text-sm text-slate-600 mb-3">أرسلها للمستخدم بطريقة آمنة. لن تظهر مرة أخرى، وسيُطلب منه تغييرها عند الدخول.</p>
          <div className="flex items-center justify-between bg-slate-50 rounded-xl p-3">
            <span dir="ltr" className="font-mono font-bold">{shown.username} / {shown.temp_password}</span>
            <button onClick={() => navigator.clipboard?.writeText(shown.temp_password).then(() => toast.success('تم النسخ'))}><HiOutlineClipboardCopy /></button>
          </div>
        </Modal>
      )}
    </Card>
  );
}

function BranchesTab({ t }) {
  return (
    <Card padded={false} className="max-w-3xl">
      <table className="w-full text-sm">
        <thead className="bg-slate-50 text-slate-500 text-xs"><tr>
          <th className="text-right font-medium px-4 py-3">الرمز</th><th className="text-right font-medium px-3 py-3">الفرع</th>
          <th className="text-center font-medium px-3 py-3">الصناديق</th><th className="text-right font-medium px-3 py-3">الحالة</th>
        </tr></thead>
        <tbody className="divide-y divide-slate-100">
          {t.branches.map((b) => (
            <tr key={b.id}><td className="px-4 py-3 font-mono" dir="ltr">{b.code}</td><td className="px-3 py-3">{b.name}</td>
              <td className="px-3 py-3 text-center">{b.registers}</td>
              <td className="px-3 py-3">{b.is_active ? <Badge tone="green">نشط</Badge> : <Badge tone="gray">معطل</Badge>}</td></tr>
          ))}
        </tbody>
      </table>
      <p className="text-xs text-slate-400 px-4 py-3">الفروع والصناديق تُدار من داخل المنشأة.</p>
    </Card>
  );
}

function ActivityTab({ t }) {
  const [a, setA] = useState(null);
  useEffect(() => { platformAPI.activity(t.id).then((r) => setA(r.data)).catch((e) => toast.error(errMsg(e))); }, [t.id]);
  if (!a) return <div className="p-10 flex justify-center text-slate-400"><Spinner size={28} /></div>;
  return (
    <div className="grid lg:grid-cols-2 gap-5">
      <Card padded={false}>
        <h3 className="font-semibold text-slate-700 px-4 pt-4 pb-2">آخر 14 يوماً</h3>
        <table className="w-full text-sm">
          <thead className="text-slate-500 text-xs"><tr><th className="text-right font-medium px-4 py-2">اليوم</th>
            <th className="text-center font-medium px-3 py-2">الفواتير</th><th className="text-center font-medium px-3 py-2">المبيعات</th>
            {t.donations_effective && <th className="text-center font-medium px-3 py-2">التبرعات</th>}</tr></thead>
          <tbody className="divide-y divide-slate-100">
            {a.daily.map((d) => (
              <tr key={d.day} className={d.sales || d.donations ? '' : 'text-slate-300'}>
                <td className="px-4 py-1.5" dir="ltr">{d.day}</td><td className="px-3 py-1.5 text-center">{d.sales}</td>
                <td className="px-3 py-1.5 text-center">{d.sales_total.toFixed(2)}</td>
                {t.donations_effective && <td className="px-3 py-1.5 text-center">{d.donations}</td>}
              </tr>
            ))}
          </tbody>
        </table>
      </Card>
      <div className="space-y-5">
        <Card>
          <h3 className="font-semibold text-slate-700 mb-2">عمليات المنصة على هذه المنشأة</h3>
          <AuditList rows={a.platform_log} />
        </Card>
        <Card>
          <h3 className="font-semibold text-slate-700 mb-2">سجل المنشأة الداخلي</h3>
          {a.tenant_log.length === 0 ? <p className="text-sm text-slate-400">لا توجد عمليات</p> : (
            <ul className="divide-y divide-slate-100 text-sm">
              {a.tenant_log.map((r, i) => (
                <li key={i} className="py-2"><span className="text-slate-800">{r.action}</span> {r.target && <span className="text-slate-500">· {r.target}</span>}
                  <div className="text-xs text-slate-400">{fmt(r.created_at)} · {r.username || '—'}</div></li>
              ))}
            </ul>
          )}
        </Card>
      </div>
    </div>
  );
}

export function AuditList({ rows }) {
  if (!rows.length) return <p className="text-sm text-slate-400">لا توجد عمليات</p>;
  return (
    <ul className="divide-y divide-slate-100 text-sm">
      {rows.map((r) => (
        <li key={r.id} className="py-2">
          <span className="font-medium text-slate-800">{ACTIONS[r.action] || r.action}</span>
          {r.target && <span className="text-slate-500"> · {r.target}</span>}
          {r.detail && <div className="text-xs text-slate-500 mt-0.5">{describeDetail(r.detail)}</div>}
          <div className="text-xs text-slate-400">{fmt(r.created_at)} · {r.username || '—'} · <span dir="ltr">{r.ip || ''}</span></div>
        </li>
      ))}
    </ul>
  );
}

function DangerTab({ t, onChanged }) {
  const [reason, setReason] = useState('');
  const [confirm, setConfirm] = useState('');
  const [busy, setBusy] = useState(false);
  const navigate = useNavigate();

  const suspend = async () => {
    if (!reason.trim()) return toast.error('اكتب سبب الإيقاف');
    setBusy(true);
    try { await platformAPI.suspend(t.id, reason.trim()); toast.success('تم إيقاف المنشأة'); setReason(''); onChanged(); }
    catch (e) { toast.error(errMsg(e)); } finally { setBusy(false); }
  };
  const activate = async () => {
    setBusy(true);
    try { await platformAPI.activate(t.id); toast.success('تم تفعيل المنشأة'); onChanged(); }
    catch (e) { toast.error(errMsg(e)); } finally { setBusy(false); }
  };
  const remove = async () => {
    setBusy(true);
    try { await platformAPI.deleteTenant(t.id, confirm.trim()); toast.success('تم حذف المنشأة'); navigate('/tenants', { replace: true }); }
    catch (e) { toast.error(errMsg(e)); } finally { setBusy(false); }
  };

  return (
    <div className="space-y-5 max-w-3xl">
      <Card>
        {t.is_active ? (
          <>
            <h3 className="font-semibold text-slate-800">إيقاف المنشأة</h3>
            <p className="text-sm text-slate-500 mt-1 mb-3">يخرج كل مستخدميها فوراً ولا يمكنهم الدخول حتى تُفعَّل. لا تُحذف أي بيانات.</p>
            <Field label="السبب (يُسجَّل)"><Textarea value={reason} onChange={(e) => setReason(e.target.value)} maxLength={300} /></Field>
            <div className="flex justify-end mt-3"><Button variant="danger" loading={busy} onClick={suspend}>إيقاف</Button></div>
          </>
        ) : (
          <>
            <h3 className="font-semibold text-slate-800">المنشأة موقوفة</h3>
            <p className="text-sm text-slate-500 mt-1 mb-3">التفعيل يعيد لمستخدميها إمكانية الدخول.</p>
            <div className="flex justify-end"><Button loading={busy} onClick={activate}>تفعيل</Button></div>
          </>
        )}
      </Card>
      <Card className="border-red-200">
        <h3 className="font-semibold text-red-700">حذف المنشأة نهائياً</h3>
        {t.can_delete ? (
          <>
            <p className="text-sm text-slate-500 mt-1 mb-3">لم تُصدر هذه المنشأة أي مستند، لذا يمكن حذفها مع كل بياناتها. لا يمكن التراجع.</p>
            <Field label={`اكتب المعرّف «${t.slug}» للتأكيد`}><Input dir="ltr" value={confirm} onChange={(e) => setConfirm(e.target.value)} /></Field>
            <div className="flex justify-end mt-3">
              <Button variant="danger" loading={busy} disabled={confirm.trim() !== t.slug} onClick={remove}>حذف نهائي</Button>
            </div>
          </>
        ) : (
          <p className="text-sm text-slate-600 mt-1">
            أصدرت هذه المنشأة {t.stats.documents} مستنداً (فواتير وإشعارات دائنة وإيصالات تبرع). يجب حفظ المستندات 6 سنوات على الأقل وفق متطلبات هيئة الزكاة والضريبة والجمارك، لذا لا يمكن حذفها. استخدم الإيقاف.
          </p>
        )}
      </Card>
    </div>
  );
}
