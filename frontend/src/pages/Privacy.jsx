import { useState, useEffect } from 'react';
import { privacyAPI, customersAPI, settingsAPI, apiError } from '../services/api';
import toast from 'react-hot-toast';
import { HiOutlineShieldCheck, HiOutlineSearch, HiOutlineDownload, HiOutlineTrash } from 'react-icons/hi';

export default function Privacy() {
  const [query, setQuery] = useState('');
  const [results, setResults] = useState([]);
  const [donorName, setDonorName] = useState('');
  const [retentionMonths, setRetentionMonths] = useState('');
  const [savedMonths, setSavedMonths] = useState(null);
  const [preview, setPreview] = useState(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => { loadRetention(); }, []);

  const loadRetention = async () => {
    try {
      const { data } = await settingsAPI.getTenant();
      if (data.data_retention_months != null) {
        setRetentionMonths(String(data.data_retention_months));
        setSavedMonths(data.data_retention_months);
      }
    } catch (e) {}
  };

  const search = async () => {
    try {
      const { data } = await customersAPI.getAll(query);
      setResults(data);
      if (data.length === 0) toast('لا توجد نتائج', { icon: 'ℹ️' });
    } catch (e) { toast.error(apiError(e, 'تعذر البحث')); }
  };

  const exportCustomer = async (c) => {
    try {
      const { data } = await privacyAPI.exportCustomer(c.id);
      const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url; a.download = `customer-${c.id}-data.json`; a.click();
      URL.revokeObjectURL(url);
      toast.success('تم تصدير بيانات العميل');
    } catch (e) { toast.error(apiError(e, 'تعذر التصدير')); }
  };

  const eraseCustomer = async (c) => {
    if (!window.confirm(`محو البيانات الشخصية للعميل "${c.name}"؟ ستبقى السجلات المالية.`)) return;
    try {
      await privacyAPI.eraseCustomer(c.id);
      toast.success('تم محو البيانات الشخصية');
      search();
    } catch (e) { toast.error(apiError(e, 'تعذر المحو')); }
  };

  const eraseDonor = async () => {
    const name = donorName.trim();
    if (!name) { toast.error('أدخل اسم المتبرع'); return; }
    if (!window.confirm(`محو بيانات المتبرع "${name}" من سجلات التبرعات؟`)) return;
    try {
      const { data } = await privacyAPI.eraseDonor(name);
      toast.success(`تم محو ${data.affected} سجل`);
      setDonorName('');
    } catch (e) { toast.error(apiError(e, 'تعذر المحو')); }
  };

  const saveRetention = async () => {
    const m = parseInt(retentionMonths);
    if (isNaN(m) || m < 0) { toast.error('أدخل عدد أشهر صحيح'); return; }
    try {
      await settingsAPI.updateTenant({ data_retention_months: m || null });
      setSavedMonths(m || null);
      toast.success('تم حفظ مدة الاحتفاظ');
    } catch (e) { toast.error(apiError(e, 'تعذر الحفظ')); }
  };

  const doPreview = async () => {
    try {
      const { data } = await privacyAPI.retentionPreview(retentionMonths || undefined);
      setPreview(data);
    } catch (e) { setPreview(null); toast.error(apiError(e, 'تعذر المعاينة')); }
  };

  const applyRetention = async () => {
    if (!window.confirm('تطبيق سياسة الاحتفاظ ومحو بيانات العملاء غير النشطين؟')) return;
    if (busy) return; setBusy(true);
    try {
      const { data } = await privacyAPI.retentionApply(retentionMonths || undefined);
      toast.success(`تم محو ${data.erased} عميل`);
      setPreview(null);
    } catch (e) { toast.error(apiError(e, 'تعذر التطبيق')); }
    finally { setBusy(false); }
  };

  return (
    <div className="max-w-4xl mx-auto space-y-6">
      <h1 className="text-2xl font-bold text-gray-800 flex items-center gap-2">
        <HiOutlineShieldCheck className="text-bayan-green" /> الخصوصية وحماية البيانات (PDPL)
      </h1>
      <p className="text-sm text-gray-500">
        أدوات حقوق أصحاب البيانات: الوصول (تصدير)، والمحو (مع الاحتفاظ بالسجلات المالية المطلوبة نظاماً)، وسياسة الاحتفاظ.
      </p>

      {/* Customer access / erasure */}
      <div className="bg-white rounded-xl border p-6 space-y-4">
        <h2 className="font-bold text-gray-800">طلبات العملاء (وصول / محو)</h2>
        <div className="flex gap-2">
          <input value={query} onChange={(e) => setQuery(e.target.value)}
                 onKeyDown={(e) => e.key === 'Enter' && search()}
                 placeholder="ابحث بالاسم أو الجوال"
                 className="flex-1 px-4 py-2 rounded-lg border border-gray-300 outline-none focus:ring-2 focus:ring-bayan-green text-right" />
          <button onClick={search} className="flex items-center gap-2 bg-bayan-green hover:bg-bayan-dark text-white px-5 py-2 rounded-lg">
            <HiOutlineSearch /> بحث
          </button>
        </div>
        {results.length > 0 && (
          <div className="divide-y border rounded-lg">
            {results.map((c) => (
              <div key={c.id} className="flex items-center justify-between p-3">
                <div>
                  <p className="font-medium text-gray-800">{c.name}</p>
                  <p className="text-xs text-gray-500">{c.phone || '—'}{c.erased_at ? ' · (محذوف)' : ''}</p>
                </div>
                <div className="flex gap-2">
                  <button onClick={() => exportCustomer(c)}
                          className="flex items-center gap-1 text-sm bg-gray-100 hover:bg-gray-200 text-gray-700 px-3 py-1.5 rounded-lg">
                    <HiOutlineDownload /> تصدير
                  </button>
                  <button onClick={() => eraseCustomer(c)} disabled={!!c.erased_at}
                          className="flex items-center gap-1 text-sm bg-red-50 hover:bg-red-100 disabled:opacity-40 text-red-600 px-3 py-1.5 rounded-lg">
                    <HiOutlineTrash /> محو
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Donor erasure */}
      <div className="bg-white rounded-xl border p-6 space-y-3">
        <h2 className="font-bold text-gray-800">محو بيانات متبرع</h2>
        <p className="text-sm text-gray-500">يزيل اسم المتبرع من سجلات التبرعات مع الاحتفاظ بالمبالغ.</p>
        <div className="flex gap-2">
          <input value={donorName} onChange={(e) => setDonorName(e.target.value)}
                 placeholder="اسم المتبرع"
                 className="flex-1 px-4 py-2 rounded-lg border border-gray-300 outline-none focus:ring-2 focus:ring-bayan-green text-right" />
          <button onClick={eraseDonor} className="bg-red-50 hover:bg-red-100 text-red-600 px-5 py-2 rounded-lg">محو</button>
        </div>
      </div>

      {/* Retention */}
      <div className="bg-white rounded-xl border p-6 space-y-4">
        <h2 className="font-bold text-gray-800">سياسة الاحتفاظ بالبيانات</h2>
        <p className="text-sm text-gray-500">
          محو بيانات العملاء غير النشطين بعد المدة المحددة (بالأشهر). المتروك فارغاً = الاحتفاظ دائماً.
        </p>
        <div className="flex items-end gap-2">
          <div>
            <label className="text-sm text-gray-600">مدة الاحتفاظ (أشهر)</label>
            <input type="number" min="0" value={retentionMonths} dir="ltr"
                   onChange={(e) => setRetentionMonths(e.target.value)}
                   className="w-40 mt-1 px-3 py-2 rounded-lg border border-gray-300 outline-none focus:ring-2 focus:ring-bayan-green text-right" />
          </div>
          <button onClick={saveRetention} className="bg-bayan-green hover:bg-bayan-dark text-white px-4 py-2 rounded-lg">حفظ</button>
          <button onClick={doPreview} className="bg-gray-100 hover:bg-gray-200 text-gray-700 px-4 py-2 rounded-lg">معاينة المؤهلين</button>
          <button onClick={applyRetention} disabled={busy}
                  className="bg-red-50 hover:bg-red-100 disabled:opacity-40 text-red-600 px-4 py-2 rounded-lg">تطبيق</button>
        </div>
        {savedMonths != null && <p className="text-xs text-gray-400">المحفوظ حالياً: {savedMonths} شهر</p>}
        {preview && (
          <div className="text-sm bg-gray-50 rounded-lg p-3">
            <p className="text-gray-700">
              مؤهل للمحو: <span className="font-bold">{preview.eligible_count}</span> عميل
              (قبل {preview.cutoff ? new Date(preview.cutoff).toLocaleDateString('ar') : '—'})
            </p>
            {preview.customers?.length > 0 && (
              <ul className="mt-2 text-gray-500 list-disc pr-5 space-y-0.5 max-h-40 overflow-auto">
                {preview.customers.map((c) => <li key={c.id}>{c.name}</li>)}
              </ul>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
