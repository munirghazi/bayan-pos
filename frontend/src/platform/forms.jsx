// Shared form pieces for the wizard and the tenant page.
import { Field, Input, Select } from '../components/ui';

export function Toggle({ checked, onChange, label, hint, disabled }) {
  return (
    <label className={`flex items-start gap-3 py-2 ${disabled ? 'opacity-50' : 'cursor-pointer'}`}>
      <span className="relative inline-flex mt-0.5">
        <input type="checkbox" className="sr-only peer" checked={!!checked} disabled={disabled}
          onChange={(e) => onChange(e.target.checked)} />
        <span className="w-10 h-6 rounded-full bg-slate-300 peer-checked:bg-emerald-500 transition-colors" />
        <span className="absolute top-0.5 right-0.5 w-5 h-5 rounded-full bg-white shadow transition-transform peer-checked:-translate-x-4" />
      </span>
      <span>
        <span className="block text-sm font-medium text-slate-700">{label}</span>
        {hint && <span className="block text-xs text-slate-400">{hint}</span>}
      </span>
    </label>
  );
}

const REG_FIELD_LABEL = {
  license_number: 'رقم الترخيص', cr_number: 'رقم السجل التجاري', freelance_doc_number: 'رقم وثيقة العمل الحر',
};

/** value: identity object; onChange(next); types: meta.entity_types */
export function IdentityFields({ value, onChange, types }) {
  const set = (k) => (e) => onChange({ ...value, [k]: e.target.value });
  const type = types.find((t) => t.key === value.entity_type);
  const primary = type?.primary_registration;
  const groups = [['nonprofit', 'غير ربحية'], ['commercial', 'تجارية'], ['other', 'أخرى']];

  return (
    <div className="space-y-4">
      <Field label="نوع المنشأة" hint={type?.group === 'nonprofit' ? 'يمكنها استقبال التبرعات' : 'لا تستقبل تبرعات (منشأة غير ربحية فقط)'}>
        <Select value={value.entity_type} onChange={set('entity_type')}>
          {groups.map(([g, gl]) => (
            <optgroup key={g} label={gl}>
              {types.filter((t) => t.group === g).map((t) => <option key={t.key} value={t.key}>{t.label}</option>)}
            </optgroup>
          ))}
        </Select>
      </Field>
      <div className="grid sm:grid-cols-2 gap-4">
        <Field label="الاسم القانوني (عربي) *"><Input value={value.name || ''} onChange={set('name')} /></Field>
        <Field label="الاسم القانوني (إنجليزي)"><Input dir="ltr" value={value.name_en || ''} onChange={set('name_en')} /></Field>
        <Field label="الرقم الموحد" hint="10 أرقام يبدأ بـ 7">
          <Input dir="ltr" inputMode="numeric" maxLength={10} value={value.unified_number || ''} onChange={set('unified_number')} />
        </Field>
        {primary && (
          <Field label={`${REG_FIELD_LABEL[primary]} *`} hint="يُطبع على الفواتير والإيصالات">
            <Input dir="ltr" value={value[primary] || ''} onChange={set(primary)} />
          </Field>
        )}
      </div>
      <div className="rounded-xl border border-slate-200 p-4 space-y-3">
        <Toggle checked={value.vat_enabled} onChange={(v) => onChange({ ...value, vat_enabled: v })}
          label="مسجلة في ضريبة القيمة المضافة" hint="عند الإيقاف لا يُطلب الرقم الضريبي" />
        {value.vat_enabled && (
          <div className="grid sm:grid-cols-2 gap-4">
            <Field label="الرقم الضريبي *" hint="15 رقماً يبدأ وينتهي بـ 3">
              <Input dir="ltr" inputMode="numeric" maxLength={15} value={value.vat_number || ''} onChange={set('vat_number')} />
            </Field>
            <Field label="نسبة الضريبة %">
              <Input dir="ltr" type="number" min={0} max={100} step="0.01" value={value.vat_rate ?? 15}
                onChange={(e) => onChange({ ...value, vat_rate: e.target.value === '' ? null : Number(e.target.value) })} />
            </Field>
          </div>
        )}
      </div>
    </div>
  );
}

/** Only the identity keys the API accepts; the primary registration of other types is left untouched. */
export function identityPayload(v) {
  const keys = ['name', 'name_en', 'entity_type', 'unified_number', 'cr_number', 'license_number',
    'freelance_doc_number', 'vat_enabled', 'vat_number', 'vat_rate'];
  const out = {};
  keys.forEach((k) => { if (v[k] !== undefined) out[k] = typeof v[k] === 'string' ? v[k].trim() : v[k]; });
  if (!out.vat_enabled) delete out.vat_rate;
  return out;
}

export function CapabilityFields({ value, onChange, nonprofit }) {
  const t = (k) => (v) => onChange({ ...value, [k]: v });
  return (
    <div className="divide-y divide-slate-100">
      <Toggle checked={value.sales_enabled} onChange={t('sales_enabled')} label="البيع ونقاط البيع" hint="الفواتير الضريبية المبسطة والمرتجعات" />
      <Toggle checked={value.donations_enabled && nonprofit} onChange={t('donations_enabled')} disabled={!nonprofit}
        label="التبرعات" hint={nonprofit ? 'إيصالات تبرع (بطاقة أو تحويل فقط)' : 'متاحة للمنشآت غير الربحية فقط'} />
      <Toggle checked={value.purchasing_enabled} onChange={t('purchasing_enabled')} label="المشتريات" hint="أوامر الشراء وسندات الاستلام" />
      <Toggle checked={value.inventory_enabled} onChange={t('inventory_enabled')} label="المخزون" hint="تتبع الكميات وحركات المخزون" />
    </div>
  );
}
