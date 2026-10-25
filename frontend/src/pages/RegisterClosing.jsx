import { useState, useEffect } from 'react';
import { registersAPI, apiError } from '../services/api';
import { SarIcon } from '../components/SarIcon';
import toast from 'react-hot-toast';
import { HiOutlineCalculator, HiOutlineRefresh } from 'react-icons/hi';

export default function RegisterClosing() {
  const [registers, setRegisters] = useState([]);
  const [registerId, setRegisterId] = useState('');
  const [zreport, setZreport] = useState(null);
  const [closings, setClosings] = useState([]);
  const [countedCash, setCountedCash] = useState('');
  const [openingFloat, setOpeningFloat] = useState('');
  const [note, setNote] = useState('');
  const [busy, setBusy] = useState(false);

  useEffect(() => { loadRegisters(); }, []);
  useEffect(() => { if (registerId) { loadZ(); loadClosings(); } }, [registerId]);

  const loadRegisters = async () => {
    try {
      const { data } = await registersAPI.getAll();
      setRegisters(data);
      if (data.length && !registerId) setRegisterId(String(data[0].id));
    } catch (e) { toast.error(apiError(e, 'تعذر تحميل الصناديق')); }
  };
  const loadZ = async () => {
    try { const { data } = await registersAPI.zreport(registerId); setZreport(data); }
    catch (e) { setZreport(null); }
  };
  const loadClosings = async () => {
    try { const { data } = await registersAPI.closings(registerId); setClosings(data); }
    catch (e) { setClosings([]); }
  };

  const expectedCash = zreport
    ? (parseFloat(openingFloat || 0) + (zreport.by_method?.cash || 0))
    : 0;
  const variance = countedCash !== '' ? (parseFloat(countedCash || 0) - expectedCash) : null;

  const close = async () => {
    if (!registerId) { toast.error('اختر الصندوق'); return; }
    if (countedCash === '') { toast.error('أدخل النقد المعدود'); return; }
    if (busy) return;
    setBusy(true);
    try {
      const { data } = await registersAPI.close(registerId, {
        counted_cash: parseFloat(countedCash || 0),
        opening_float: parseFloat(openingFloat || 0),
        note: note || null,
      });
      toast.success('تم إغلاق الصندوق');
      setCountedCash(''); setOpeningFloat(''); setNote('');
      setZreport({ ...data, sales_count: 0, total_sales: 0, by_method: { cash: 0, card: 0, transfer: 0, other: 0 }, expected_cash: 0 });
      loadZ(); loadClosings();
    } catch (e) { toast.error(apiError(e, 'تعذر إغلاق الصندوق')); }
    finally { setBusy(false); }
  };

  const money = (n) => (n ?? 0).toFixed(2);

  return (
    <div className="max-w-4xl mx-auto space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-gray-800 flex items-center gap-2">
          <HiOutlineCalculator className="text-bayan-green" /> إغلاق الصندوق (تقرير Z)
        </h1>
        <button onClick={() => { loadZ(); loadClosings(); }}
                className="flex items-center gap-1 text-sm text-gray-500 hover:text-gray-700">
          <HiOutlineRefresh /> تحديث
        </button>
      </div>

      <div className="bg-white rounded-xl border p-4">
        <label className="text-sm text-gray-600">الصندوق</label>
        <select value={registerId} onChange={(e) => setRegisterId(e.target.value)}
                className="w-full mt-1 px-3 py-2 rounded-lg border border-gray-300 outline-none focus:ring-2 focus:ring-bayan-green">
          {registers.length === 0 && <option value="">لا توجد صناديق</option>}
          {registers.map((r) => <option key={r.id} value={r.id}>{r.name}</option>)}
        </select>
      </div>

      {/* Z-report preview */}
      <div className="bg-white rounded-xl border p-6 space-y-3">
        <h2 className="font-bold text-gray-800">ملخص الفترة الحالية (منذ آخر إغلاق)</h2>
        {zreport ? (
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-center">
            <Stat label="عدد المبيعات" value={zreport.sales_count} />
            <Stat label="نقدي" value={money(zreport.by_method?.cash)} sar />
            <Stat label="شبكة" value={money(zreport.by_method?.card)} sar />
            <Stat label="تحويل" value={money(zreport.by_method?.transfer)} sar />
            <Stat label="أخرى" value={money(zreport.by_method?.other)} sar />
            <Stat label="إجمالي المبيعات" value={money(zreport.total_sales)} sar />
            <Stat label="النقد المتوقع" value={money(zreport.expected_cash)} sar highlight />
          </div>
        ) : <p className="text-gray-400 text-sm">اختر صندوقاً لعرض التقرير.</p>}
      </div>

      {/* Close form */}
      <div className="bg-white rounded-xl border p-6 space-y-4">
        <h2 className="font-bold text-gray-800">جرد وإغلاق</h2>
        <div className="grid sm:grid-cols-2 gap-4">
          <Field label="رصيد افتتاحي (float)" value={openingFloat} onChange={setOpeningFloat} placeholder="0.00" />
          <Field label="النقد المعدود فعلياً" value={countedCash} onChange={setCountedCash} placeholder="0.00" />
        </div>
        <div>
          <label className="text-sm text-gray-600">ملاحظة</label>
          <input value={note} onChange={(e) => setNote(e.target.value)}
                 className="w-full mt-1 px-3 py-2 rounded-lg border border-gray-300 outline-none focus:ring-2 focus:ring-bayan-green" />
        </div>
        <div className="flex items-center justify-between pt-2 border-t">
          <div className="text-sm">
            <span className="text-gray-500">النقد المتوقع: </span>
            <span className="font-bold">{money(expectedCash)}</span>
            {variance !== null && (
              <span className={`ml-3 font-bold ${variance === 0 ? 'text-gray-600' : (variance > 0 ? 'text-green-600' : 'text-red-600')}`}>
                {' '}الفرق: {variance > 0 ? '+' : ''}{money(variance)}
              </span>
            )}
          </div>
          <button onClick={close} disabled={busy || !registerId}
                  className="bg-bayan-green hover:bg-bayan-dark disabled:opacity-40 text-white px-6 py-2 rounded-lg transition-all">
            إغلاق الصندوق
          </button>
        </div>
      </div>

      {/* History */}
      <div className="bg-white rounded-xl border p-6">
        <h2 className="font-bold text-gray-800 mb-3">سجل الإغلاقات</h2>
        {closings.length === 0 ? (
          <p className="text-gray-400 text-sm">لا يوجد إغلاقات بعد.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-gray-500 border-b">
                  <th className="py-2 text-right">التاريخ</th>
                  <th className="text-right">بواسطة</th>
                  <th className="text-right">مبيعات</th>
                  <th className="text-right">متوقع</th>
                  <th className="text-right">معدود</th>
                  <th className="text-right">الفرق</th>
                </tr>
              </thead>
              <tbody>
                {closings.map((c) => (
                  <tr key={c.id} className="border-b last:border-0">
                    <td className="py-2">{c.closed_at ? new Date(c.closed_at).toLocaleString('ar') : '—'}</td>
                    <td>{c.closed_by || '—'}</td>
                    <td>{money(c.total_sales)}</td>
                    <td>{money(c.expected_cash)}</td>
                    <td>{money(c.counted_cash)}</td>
                    <td className={c.variance === 0 ? '' : (c.variance > 0 ? 'text-green-600' : 'text-red-600')}>
                      {c.variance > 0 ? '+' : ''}{money(c.variance)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}

function Stat({ label, value, sar, highlight }) {
  return (
    <div className={`rounded-lg p-3 ${highlight ? 'bg-bayan-light/40' : 'bg-gray-50'}`}>
      <p className="text-xs text-gray-500">{label}</p>
      <p className="font-bold text-gray-800 flex items-center justify-center gap-1">
        {value}{sar && <SarIcon className="w-3.5 h-3.5" />}
      </p>
    </div>
  );
}

function Field({ label, value, onChange, placeholder }) {
  return (
    <div>
      <label className="text-sm text-gray-600">{label}</label>
      <input type="number" step="0.01" value={value} onChange={(e) => onChange(e.target.value)}
             placeholder={placeholder} dir="ltr"
             className="w-full mt-1 px-3 py-2 rounded-lg border border-gray-300 outline-none focus:ring-2 focus:ring-bayan-green text-right" />
    </div>
  );
}
