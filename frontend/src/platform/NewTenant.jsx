import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import toast from 'react-hot-toast';
import { HiOutlineCheckCircle, HiOutlineClipboardCopy } from 'react-icons/hi';
import { Button, Card, Field, Input, PageHeader, Spinner } from '../components/ui';
import { platformAPI, errMsg } from './api';
import { CapabilityFields, IdentityFields, identityPayload } from './forms';

const STEPS = ['الهوية', 'الصلاحيات', 'الدخول والفرع', 'المراجعة'];
const slugify = (s) => (s || '').toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '').slice(0, 50);

export default function NewTenant() {
  const [meta, setMeta] = useState(null);
  const [step, setStep] = useState(0);
  const [ident, setIdent] = useState({ entity_type: 'nonprofit_association', name: '', name_en: '', vat_enabled: false, vat_rate: 15 });
  const [caps, setCaps] = useState({ sales_enabled: true, donations_enabled: true, purchasing_enabled: true, inventory_enabled: true });
  const [access, setAccess] = useState({ slug: '', admin_username: 'admin', admin_full_name: 'مدير النظام', branch_name: 'الفرع الرئيسي' });
  const [slugTouched, setSlugTouched] = useState(false);
  const [saving, setSaving] = useState(false);
  const [result, setResult] = useState(null);
  const navigate = useNavigate();

  useEffect(() => { platformAPI.meta().then((r) => setMeta(r.data)).catch((e) => toast.error(errMsg(e))); }, []);
  useEffect(() => { if (!slugTouched) setAccess((a) => ({ ...a, slug: slugify(ident.name_en) })); }, [ident.name_en, slugTouched]);

  if (!meta) return <div className="p-10 flex justify-center text-slate-400"><Spinner size={28} /></div>;
  const type = meta.entity_types.find((t) => t.key === ident.entity_type);
  const nonprofit = type?.group === 'nonprofit';

  const check = () => {
    if (step === 0) {
      if (!ident.name.trim()) return 'الاسم القانوني (عربي) مطلوب';
      if (ident.unified_number && !/^7\d{9}$/.test(ident.unified_number)) return 'الرقم الموحد: 10 أرقام يبدأ بالرقم 7';
      if (ident.vat_enabled && !/^3\d{13}3$/.test(ident.vat_number || '')) return 'الرقم الضريبي: 15 رقماً يبدأ وينتهي بالرقم 3';
    }
    if (step === 1 && !caps.sales_enabled && !(caps.donations_enabled && nonprofit)) return 'فعّل البيع أو التبرعات على الأقل';
    if (step === 2) {
      if (!/^[a-z0-9](?:[a-z0-9-]{1,48}[a-z0-9])$/.test(access.slug)) return 'المعرّف: 3–50 حرفاً إنجليزياً صغيراً أو أرقاماً أو (-)';
      if (!/^[A-Za-z0-9_.-]{3,50}$/.test(access.admin_username)) return 'اسم مستخدم المدير: 3–50 حرفاً إنجليزياً أو أرقاماً';
    }
    return null;
  };
  const next = () => { const e = check(); if (e) return toast.error(e); setStep(step + 1); };

  const create = async () => {
    setSaving(true);
    try {
      const r = await platformAPI.createTenant({
        ...identityPayload(ident), ...caps, donations_enabled: caps.donations_enabled && nonprofit,
        ...access, vat_rate: ident.vat_enabled ? ident.vat_rate ?? 15 : 15,
      });
      setResult(r.data);
    } catch (e) { toast.error(errMsg(e)); } finally { setSaving(false); }
  };

  if (result) {
    const copy = () => navigator.clipboard?.writeText(result.temp_password).then(() => toast.success('تم النسخ'));
    return (
      <Card className="max-w-xl mx-auto text-center">
        <HiOutlineCheckCircle className="text-5xl text-emerald-500 mx-auto mb-2" />
        <h2 className="text-xl font-bold text-slate-800">تم إنشاء «{result.tenant.name}»</h2>
        <p className="text-sm text-slate-500 mt-1">أرسل بيانات الدخول التالية للمدير بطريقة آمنة. <b>لن تظهر كلمة المرور مرة أخرى.</b></p>
        <div className="mt-5 text-right bg-slate-50 rounded-xl p-4 space-y-2 text-sm">
          <Row k="الجهة (المعرّف)" v={result.tenant.slug} />
          <Row k="اسم المستخدم" v={result.admin_username} />
          <div className="flex items-center justify-between gap-3">
            <span className="text-slate-500">كلمة المرور المؤقتة</span>
            <span className="flex items-center gap-2">
              <span dir="ltr" className="font-mono font-bold text-slate-900 select-all">{result.temp_password}</span>
              <button onClick={copy} className="text-slate-500 hover:text-slate-800" title="نسخ"><HiOutlineClipboardCopy /></button>
            </span>
          </div>
        </div>
        <p className="text-xs text-slate-400 mt-3">{result.login_hint}</p>
        <div className="mt-5 flex justify-center gap-2">
          <Button variant="secondary" onClick={() => navigate('/tenants')}>العودة للقائمة</Button>
          <Button onClick={() => navigate(`/tenants/${result.tenant.id}`)}>فتح المنشأة</Button>
        </div>
      </Card>
    );
  }

  return (
    <div className="max-w-3xl mx-auto">
      <PageHeader title="منشأة جديدة" subtitle="الهوية والصلاحيات ومدير المنشأة وفرعها الأول" />
      <ol className="flex gap-2 mb-5 text-sm">
        {STEPS.map((s, i) => (
          <li key={s} className={`flex-1 rounded-xl px-3 py-2 text-center ${i === step ? 'bg-slate-900 text-white' : i < step ? 'bg-emerald-50 text-emerald-700' : 'bg-slate-100 text-slate-400'}`}>
            {i + 1}. {s}
          </li>
        ))}
      </ol>
      <Card>
        {step === 0 && <IdentityFields value={ident} onChange={setIdent} types={meta.entity_types} />}
        {step === 1 && <CapabilityFields value={caps} onChange={setCaps} nonprofit={nonprofit} />}
        {step === 2 && (
          <div className="grid sm:grid-cols-2 gap-4">
            <Field label="معرّف المنشأة (الجهة) *" hint="يكتبه المستخدمون في شاشة الدخول. لا يمكن تغييره لاحقاً.">
              <Input dir="ltr" value={access.slug} onChange={(e) => { setSlugTouched(true); setAccess({ ...access, slug: e.target.value.toLowerCase() }); }} />
            </Field>
            <Field label="اسم مستخدم المدير *">
              <Input dir="ltr" value={access.admin_username} onChange={(e) => setAccess({ ...access, admin_username: e.target.value })} />
            </Field>
            <Field label="اسم المدير">
              <Input value={access.admin_full_name} onChange={(e) => setAccess({ ...access, admin_full_name: e.target.value })} />
            </Field>
            <Field label="اسم الفرع الأول" hint="رمزه B01 ويُضاف له الصندوق 1 ووحدات القياس الافتراضية">
              <Input value={access.branch_name} onChange={(e) => setAccess({ ...access, branch_name: e.target.value })} />
            </Field>
            <p className="sm:col-span-2 text-xs text-slate-500 bg-slate-50 rounded-lg p-3">
              تُولَّد كلمة مرور مؤقتة تظهر مرة واحدة بعد الإنشاء، ويُطلب من المدير تغييرها عند أول دخول.
            </p>
          </div>
        )}
        {step === 3 && (
          <div className="space-y-2 text-sm">
            <Row k="النوع" v={type?.label} />
            <Row k="الاسم (عربي)" v={ident.name} />
            <Row k="الاسم (إنجليزي)" v={ident.name_en} />
            <Row k="الرقم الموحد" v={ident.unified_number} />
            {type?.primary_registration && <Row k={type.primary_registration_label} v={ident[type.primary_registration]} />}
            <Row k="ضريبة القيمة المضافة" v={ident.vat_enabled ? `${ident.vat_number} · ${ident.vat_rate ?? 15}%` : 'غير مسجلة'} />
            <Row k="الصلاحيات" v={[caps.sales_enabled && 'البيع', caps.donations_enabled && nonprofit && 'التبرعات',
              caps.purchasing_enabled && 'المشتريات', caps.inventory_enabled && 'المخزون'].filter(Boolean).join('، ')} />
            <Row k="المعرّف" v={access.slug} />
            <Row k="المدير" v={`${access.admin_username} (${access.admin_full_name})`} />
            <Row k="الفرع الأول" v={access.branch_name} />
            {type?.primary_registration && !ident[type.primary_registration] && (
              <p className="text-amber-700 bg-amber-50 rounded-lg p-3 mt-3">لم يُدخل {type.primary_registration_label}: يمكن إكماله لاحقاً من صفحة المنشأة، لكنه يُطبع على المستندات.</p>
            )}
          </div>
        )}
        <div className="flex justify-between mt-6 pt-4 border-t border-slate-100">
          <Button variant="secondary" onClick={() => (step === 0 ? navigate('/tenants') : setStep(step - 1))}>{step === 0 ? 'إلغاء' : 'السابق'}</Button>
          {step < 3 ? <Button onClick={next}>التالي</Button> : <Button loading={saving} onClick={create}>إنشاء المنشأة</Button>}
        </div>
      </Card>
    </div>
  );
}

function Row({ k, v }) {
  return (
    <div className="flex items-center justify-between gap-3 py-1 border-b border-slate-100 last:border-0">
      <span className="text-slate-500">{k}</span>
      <span className="font-medium text-slate-800 text-left">{v || '—'}</span>
    </div>
  );
}
