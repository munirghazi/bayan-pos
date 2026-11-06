import { useEffect, useRef, useState } from 'react';
import toast from 'react-hot-toast';
import { HiOutlineOfficeBuilding, HiOutlineLocationMarker, HiOutlineSave, HiOutlineLockClosed, HiOutlineExclamation } from 'react-icons/hi';
import { settingsAPI, apiError } from '../services/api';
import { syncZATCAFromTenant } from '../utils/zatca';
import { getCapabilities } from '../utils/posSettings';

const REG_LABELS = {
  unified_number: 'الرقم الموحد',
  cr_number: 'رقم السجل التجاري',
  license_number: 'رقم الترخيص',
  freelance_doc_number: 'رقم وثيقة العمل الحر',
};

const EMPTY = {
  short_address: '', building_number: '', street_name: '', street_name_en: '',
  additional_number: '', district: '', district_en: '', postal_code: '',
  city: '', city_en: '', country: 'المملكة العربية السعودية', country_en: 'Kingdom of Saudi Arabia',
  region: '', address_proof_number: '', address_proof_expiry: '', show_en_address: false,
  website: '', receipt_thanks: '',
};

const daysUntil = (iso) => {
  if (!iso) return null;
  const end = new Date(`${iso}T00:00:00+03:00`);
  return Math.ceil((end - Date.now()) / 86400000);
};

/** One read-only value of the platform-controlled identity. */
const Ro = ({ label, value, ltr }) => (
  <div>
    <p className="text-xs text-gray-500 mb-1">{label}</p>
    <p className={`px-3 py-2 rounded-lg bg-gray-50 border border-gray-200 text-gray-800 min-h-[40px] ${ltr ? 'font-mono' : ''}`} dir={ltr ? 'ltr' : undefined}>
      {value || <span className="text-gray-300">—</span>}
    </p>
  </div>
);

/** A row of the address proof: label (ar / en) + Arabic input + English input. */
const Row = ({ ar, en, req, children }) => (
  <div className="grid grid-cols-12 gap-3 items-center py-2 border-b border-gray-100 last:border-0">
    <div className="col-span-12 md:col-span-3">
      <p className="text-sm font-medium text-gray-700">{ar}{req && <span className="text-red-500"> *</span>}</p>
      <p className="text-xs text-gray-400" dir="ltr">{en}</p>
    </div>
    {children}
  </div>
);

/**
 * "بيانات المنشأة"
 *  1. Identity — legal name, type, registration numbers, VAT: read-only here,
 *     maintained by the platform.
 *  2. National address — editable, in the SAME order as the official address
 *     proof (العنوان الوطني), Arabic on the right and English on the left.
 */
export default function OrgProfile() {
  const [s, setS] = useState(null);
  const [f, setF] = useState(EMPTY);
  const saving = useRef(false);

  const load = async () => {
    try {
      const { data } = await settingsAPI.getTenant();
      setS(data);
      setF(Object.fromEntries(Object.keys(EMPTY).map((k) => [k, data[k] ?? EMPTY[k]])));
      syncZATCAFromTenant(data);
    } catch (e) { toast.error(apiError(e, 'تعذّر تحميل البيانات')); }
  };
  useEffect(() => { load(); }, []);

  if (!s) return null;
  const set = (k, v) => setF((p) => ({ ...p, [k]: v }));
  const digits = (k, n) => (e) => set(k, e.target.value.replace(/\D/g, '').slice(0, n));

  const shortDigits = (f.short_address || '').slice(4);
  const shortMismatch = f.short_address?.length === 8 && f.building_number?.length === 4 && shortDigits !== f.building_number;
  const expiryDays = daysUntil(f.address_proof_expiry);

  const save = async () => {
    const needsInvoice = !!getCapabilities().sales_enabled;
    const t = (v) => (v || '').trim();
    if (t(f.short_address) && !/^[A-Za-z]{4}\d{4}$/.test(t(f.short_address).replace(/\s/g, ''))) { toast.error('العنوان المختصر: 4 حروف إنجليزية ثم 4 أرقام'); return; }
    if (needsInvoice) {
      if (!/^\d{4}$/.test(t(f.building_number))) { toast.error('رقم المبنى: 4 أرقام'); return; }
      if (!t(f.street_name)) { toast.error('اسم الشارع مطلوب'); return; }
      if (!t(f.district)) { toast.error('الحي مطلوب'); return; }
      if (!/^\d{5}$/.test(t(f.postal_code))) { toast.error('الرمز البريدي: 5 أرقام'); return; }
      if (!t(f.city)) { toast.error('المدينة مطلوبة'); return; }
    }
    if (t(f.additional_number) && !/^\d{4}$/.test(t(f.additional_number))) { toast.error('الرقم الفرعي: 4 أرقام'); return; }
    if (f.show_en_address && !(t(f.street_name_en) && t(f.district_en) && t(f.city_en))) {
      toast.error('لإظهار العنوان بالإنجليزية أكمل: الشارع والحي والمدينة بالإنجليزية'); return;
    }
    if (saving.current) return;
    saving.current = true;
    try {
      const body = { ...f, address_proof_expiry: f.address_proof_expiry || null };
      const { data } = await settingsAPI.updateTenant(body);
      setS(data);
      syncZATCAFromTenant(data);
      toast.success('تم حفظ بيانات المنشأة');
    } catch (e) {
      toast.error(apiError(e, 'خطأ في الحفظ'));
    } finally {
      saving.current = false;
    }
  };

  const inp = 'w-full px-3 py-2 rounded-lg border border-gray-300 focus:ring-2 focus:ring-bayan-green outline-none';
  const regFields = ['unified_number', s.primary_registration].filter((k, i, a) => k && a.indexOf(k) === i);

  return (
    <div className="space-y-6">
      {/* ===== Identity (read-only) ===== */}
      <div className="bg-white rounded-xl border p-6 space-y-4">
        <div className="flex items-start justify-between gap-4">
          <div>
            <h2 className="text-lg font-bold text-gray-800 flex items-center gap-2">
              <HiOutlineOfficeBuilding className="text-bayan-green" /> بيانات المنشأة
            </h2>
            <p className="text-sm text-gray-500 mt-1">تظهر في الفواتير والإيصالات ورمز QR المتوافق مع هيئة الزكاة والضريبة والجمارك</p>
          </div>
          <span className="flex items-center gap-1 text-xs text-gray-500 bg-gray-100 rounded-full px-3 py-1 whitespace-nowrap">
            <HiOutlineLockClosed /> تُعدَّل من إدارة المنصة
          </span>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <Ro label="الاسم النظامي" value={s.seller_name} />
          <Ro label="الاسم بالإنجليزية" value={s.name_en} ltr />
          <Ro label="نوع المنشأة" value={s.entity_type_label} />
          {regFields.map((k) => <Ro key={k} label={REG_LABELS[k]} value={s[k]} ltr />)}
          <Ro label="الرقم الضريبي" value={s.vat_number} ltr />
          <Ro label="التسجيل في ضريبة القيمة المضافة" value={s.vat_enabled ? `مسجّلة — ${s.vat_rate}%` : 'غير مسجّلة'} />
        </div>
        {s.primary_registration && !s[s.primary_registration] && (
          <p className="text-xs text-amber-700 bg-amber-50 border border-amber-200 rounded-lg p-2">
            {REG_LABELS[s.primary_registration]} غير مسجّل — تواصل مع إدارة المنصة لإكماله.
          </p>
        )}
        {s.entity_group !== 'nonprofit' && (
          <p className="text-xs text-gray-500">التبرعات متاحة للمنشآت غير الربحية فقط.</p>
        )}
      </div>

      {/* ===== National address (proof order, AR | EN) ===== */}
      <div className="bg-white rounded-xl border p-6 space-y-4">
        <div>
          <h2 className="text-lg font-bold text-gray-800 flex items-center gap-2">
            <HiOutlineLocationMarker className="text-bayan-green" /> العنوان الوطني
          </h2>
          <p className="text-sm text-gray-500 mt-1">بنفس ترتيب «إثبات العنوان» الصادر من العنوان الوطني — العربي يميناً والإنجليزي يساراً. الحقول المعلَّمة <span className="text-red-500">*</span> مطلوبة لإصدار الفواتير.</p>
        </div>

        {(() => {
          const need = [['building_number', 'رقم المبنى'], ['street_name', 'اسم الشارع'], ['district', 'الحي'],
            ['postal_code', 'الرمز البريدي'], ['city', 'المدينة']].filter(([k]) => !String(f[k] || '').trim()).map(([, l]) => l);
          const platform = s?.invoice_gaps?.platform || [];
          const savedOk = s?.invoice_gaps?.ready;
          const dirty = need.length === 0 && !savedOk && platform.length === 0;
          return (
            <div className={`rounded-lg p-3 text-sm border ${need.length || platform.length ? 'bg-amber-50 border-amber-200 text-amber-800' : dirty ? 'bg-blue-50 border-blue-200 text-blue-800' : 'bg-emerald-50 border-emerald-200 text-emerald-800'}`}>
              {need.length > 0 && <div>ناقص لإصدار الفواتير: <b>{need.join('، ')}</b></div>}
              {platform.length > 0 && <div>{platform.join('، ')} — يضبطه فريق إدارة المنصة، تواصل معهم.</div>}
              {!need.length && !platform.length && (dirty ? 'البيانات مكتملة — اضغط «حفظ البيانات» في أسفل الصفحة لاعتمادها.' : '✓ العنوان مكتمل ومحفوظ — يمكن إصدار الفواتير.')}
            </div>
          );
        })()}

        {expiryDays !== null && expiryDays <= 30 && (
          <div className={`flex items-center gap-2 text-sm rounded-lg p-3 border ${expiryDays < 0 ? 'bg-red-50 border-red-200 text-red-700' : 'bg-amber-50 border-amber-200 text-amber-800'}`}>
            <HiOutlineExclamation className="text-lg" />
            {expiryDays < 0 ? 'انتهت صلاحية إثبات العنوان — جدّده من سبل.' : `إثبات العنوان ينتهي خلال ${expiryDays} يوماً — جدّده من سبل.`}
          </div>
        )}

        <div>
          <Row ar="العنوان المختصر" en="Short Address">
            <div className="col-span-12 md:col-span-4">
              <input className={`${inp} font-mono tracking-widest text-center uppercase`} dir="ltr" maxLength={9}
                value={f.short_address} onChange={(e) => set('short_address', e.target.value.toUpperCase())} placeholder="مثال: JBRA6522" />
            </div>
            {shortMismatch && (
              <p className="col-span-12 md:col-span-5 text-xs text-amber-700">تنبيه: أرقام العنوان المختصر ({shortDigits}) لا تطابق رقم المبنى ({f.building_number}) — تحقّق من الإثبات.</p>
            )}
          </Row>
          <Row req ar="رقم المبنى / الشارع" en="Building No. / Street">
            <div className="col-span-4 md:col-span-2">
              <input className={`${inp} text-center font-mono`} dir="ltr" value={f.building_number} onChange={digits('building_number', 4)} placeholder="مثال: 6522" />
            </div>
            <div className="col-span-8 md:col-span-4">
              <input className={inp} value={f.street_name} onChange={(e) => set('street_name', e.target.value)} placeholder="مثال: معاذ التميمي" />
            </div>
            <div className="col-span-12 md:col-span-3">
              <input className={inp} dir="ltr" value={f.street_name_en} onChange={(e) => set('street_name_en', e.target.value)} placeholder="e.g. Muath Al Tamimi" />
            </div>
          </Row>
          <Row req ar="الرقم الفرعي / الحي" en="Secondary No. / District">
            <div className="col-span-4 md:col-span-2">
              <input className={`${inp} text-center font-mono`} dir="ltr" value={f.additional_number} onChange={digits('additional_number', 4)} placeholder="مثال: 4816" />
            </div>
            <div className="col-span-8 md:col-span-4">
              <input className={inp} value={f.district} onChange={(e) => set('district', e.target.value)} placeholder="مثال: حي الرويس" />
            </div>
            <div className="col-span-12 md:col-span-3">
              <input className={inp} dir="ltr" value={f.district_en} onChange={(e) => set('district_en', e.target.value)} placeholder="e.g. Ar Ruwais Dist." />
            </div>
          </Row>
          <Row req ar="الرمز البريدي" en="Postal Code">
            <div className="col-span-12 md:col-span-2">
              <input className={`${inp} text-center font-mono`} dir="ltr" value={f.postal_code} onChange={digits('postal_code', 5)} placeholder="مثال: 23214" />
            </div>
          </Row>
          <Row req ar="المدينة" en="City">
            <div className="col-span-6 md:col-span-6">
              <input className={inp} value={f.city} onChange={(e) => set('city', e.target.value)} placeholder="مثال: جدة" />
            </div>
            <div className="col-span-6 md:col-span-3">
              <input className={inp} dir="ltr" value={f.city_en} onChange={(e) => set('city_en', e.target.value)} placeholder="e.g. JEDDAH" />
            </div>
          </Row>
          <Row ar="الدولة" en="Country">
            <div className="col-span-6 md:col-span-6">
              <input className={inp} value={f.country} onChange={(e) => set('country', e.target.value)} />
            </div>
            <div className="col-span-6 md:col-span-3">
              <input className={inp} dir="ltr" value={f.country_en} onChange={(e) => set('country_en', e.target.value)} />
            </div>
          </Row>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 pt-2 border-t">
          <div>
            <label className="text-xs text-gray-500">رقم إثبات العنوان (اختياري)</label>
            <input className={`${inp} font-mono`} dir="ltr" value={f.address_proof_number} onChange={digits('address_proof_number', 20)} placeholder="مثال: 1089560005" />
          </div>
          <div>
            <label className="text-xs text-gray-500">تاريخ انتهاء الإثبات (للتذكير بالتجديد)</label>
            <input type="date" className={inp} value={f.address_proof_expiry || ''} onChange={(e) => set('address_proof_expiry', e.target.value)} />
          </div>
          <div>
            <label className="text-xs text-gray-500">المنطقة (اختياري — لا تُطبع)</label>
            <input className={inp} value={f.region} onChange={(e) => set('region', e.target.value)} placeholder="مثال: منطقة مكة المكرمة" />
          </div>
        </div>
        <label className="flex items-center gap-3 text-sm text-gray-700 cursor-pointer">
          <input type="checkbox" className="w-5 h-5" checked={!!f.show_en_address} onChange={(e) => set('show_en_address', e.target.checked)} />
          إظهار العنوان بالإنجليزية في الفاتورة (إضافةً إلى العربي)
        </label>
        {f.show_en_address && !(f.street_name_en && f.district_en && f.city_en) && (
          <p className="text-xs text-amber-700">أكمل الحقول الإنجليزية (الشارع، الحي، المدينة) — وإلا لن يُطبع العنوان الإنجليزي.</p>
        )}
      </div>

      {/* ===== Receipt details ===== */}
      <div className="bg-white rounded-xl border p-6 grid grid-cols-1 md:grid-cols-2 gap-4">
        <div>
          <label className="text-xs text-gray-500">الموقع الإلكتروني</label>
          <input className={inp} dir="ltr" value={f.website} onChange={(e) => set('website', e.target.value)} placeholder="e.g. www.example.sa" />
        </div>
        <div>
          <label className="text-xs text-gray-500">عبارة الختام في الإيصال</label>
          <input className={inp} value={f.receipt_thanks} onChange={(e) => set('receipt_thanks', e.target.value)} placeholder={s.default_thanks} />
          <p className="text-xs text-gray-400 mt-1">اتركها فارغة لاستخدام «{s.default_thanks}»</p>
        </div>
      </div>

      <div className="flex justify-end">
        <button onClick={save} className="flex items-center gap-2 bg-bayan-green hover:bg-bayan-dark text-white px-8 py-3 rounded-xl font-bold">
          <HiOutlineSave className="text-xl" /> حفظ البيانات
        </button>
      </div>
    </div>
  );
}
