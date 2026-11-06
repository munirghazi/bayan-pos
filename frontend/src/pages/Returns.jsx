import { useState, useEffect, useRef } from 'react';
import { can } from '../utils/perms';
import { returnsAPI, salesAPI, apiError } from '../services/api';
import toast from 'react-hot-toast';
import { HiOutlineReceiptRefund, HiOutlineSearch, HiOutlinePrinter, HiOutlineArrowRight } from 'react-icons/hi';
import DocumentModal from '../components/DocumentModal';
import { fmtDateTime } from '../utils/datetime';

const METHOD_AR = { cash: 'نقدي', card: 'شبكة', transfer: 'تحويل', mixed: 'متعدد' };
const riyadhToday = () => new Date().toLocaleDateString('en-CA', { timeZone: 'Asia/Riyadh' });
const daysAgo = (n) => {
  const d = new Date(Date.now() - n * 86400000);
  return d.toLocaleDateString('en-CA', { timeZone: 'Asia/Riyadh' });
};
const EMPTY = { q: '', customer: '', date_from: daysAgo(30), date_to: riyadhToday(), amount_min: '', amount_max: '', method: '' };

export default function Returns() {
  const currentUser = JSON.parse(localStorage.getItem('user') || '{}');
  const isAdmin = can('returns');   // permission, not role

  // ---- invoice finder
  const [filters, setFilters] = useState(EMPTY);
  const [results, setResults] = useState({ count: 0, rows: [] });
  const [searching, setSearching] = useState(false);

  // ---- selected invoice
  const [saleData, setSaleData] = useState(null);
  const [qty, setQty] = useState({});
  const [reason, setReason] = useState('');
  const [refundMethod, setRefundMethod] = useState('');
  const [recent, setRecent] = useState([]);
  const [printDoc, setPrintDoc] = useState(null);
  const submittingRef = useRef(false);

  useEffect(() => { loadRecent(); search(EMPTY); }, []);

  const loadRecent = async () => {
    try { setRecent((await returnsAPI.getAll()).data); } catch (err) {}
  };

  const search = async (f = filters) => {
    setSearching(true);
    try {
      const params = Object.fromEntries(Object.entries(f).filter(([, v]) => v !== '' && v !== null));
      const { data } = await salesAPI.search({ ...params, limit: 50 });
      setResults(data);
    } catch (err) {
      toast.error(apiError(err, 'تعذّر البحث'));
    } finally {
      setSearching(false);
    }
  };

  const setF = (k, v) => setFilters((p) => ({ ...p, [k]: v }));

  const openInvoice = async (number) => {
    try {
      const res = await returnsAPI.getForInvoice(number);
      setSaleData(res.data);
      setQty({});
      setReason('');
      setRefundMethod(res.data.refund_methods.length === 1 ? res.data.refund_methods[0]
        : (res.data.payment_method !== 'mixed' ? res.data.payment_method : ''));
    } catch (err) {
      setSaleData(null);
      toast.error(apiError(err, 'تعذّر فتح الفاتورة'));
    }
  };

  const setItemQty = (pid, val, max) => {
    let n = parseFloat(val);
    if (isNaN(n) || n < 0) n = 0;
    if (n > max) n = max;
    setQty((prev) => ({ ...prev, [pid]: n }));
  };

  const refundTotal = saleData
    ? saleData.items.reduce((sum, it) => sum + (qty[it.product_id] || 0) * it.price, 0)
    : 0;

  const submit = async () => {
    if (!saleData) return;
    const items = saleData.items
      .filter((it) => (qty[it.product_id] || 0) > 0)
      .map((it) => ({ product_id: it.product_id, quantity: qty[it.product_id] }));
    if (items.length === 0) { toast.error('حدد كمية واحدة على الأقل للإرجاع'); return; }
    if (!reason.trim()) { toast.error('سبب الإرجاع مطلوب لإصدار الإشعار الدائن'); return; }
    if (!refundMethod) { toast.error('اختر طريقة الاسترداد'); return; }
    if (!isAdmin) { toast.error('ليست لديك صلاحية المرتجعات'); return; }
    if (submittingRef.current) return;
    submittingRef.current = true;
    try {
      const reg = localStorage.getItem('pos_register_id');
      const res = await returnsAPI.create({
        invoice_number: saleData.invoice_number, items, reason: reason.trim(),
        refund_method: refundMethod, register_id: reg ? parseInt(reg) : null,
      });
      toast.success(`تم إصدار الإشعار الدائن ${res.data.credit_note_number}`);
      setPrintDoc(res.data);
      const fresh = await returnsAPI.getForInvoice(saleData.invoice_number);
      setSaleData(fresh.data);
      setQty({});
      setReason('');
      loadRecent();
      search();
    } catch (err) {
      toast.error(apiError(err, 'خطأ في تنفيذ المرتجع'));
    } finally {
      submittingRef.current = false;
    }
  };

  const input = 'px-3 py-2 rounded-lg border border-gray-300 focus:ring-2 focus:ring-bayan-green outline-none text-sm';

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-800">المرتجعات</h1>
        <p className="text-gray-500 mt-1">ابحث عن الفاتورة، اختر الأصناف المرتجعة، وأصدر إشعاراً دائناً</p>
      </div>

      {!saleData && (
        <>
          {/* Finder */}
          <form
            onSubmit={(e) => { e.preventDefault(); search(); }}
            className="bg-white rounded-xl border shadow-sm p-4 grid grid-cols-2 md:grid-cols-4 gap-3"
          >
            <input className={`${input} text-left`} dir="ltr" placeholder="رقم الفاتورة أو رمز العملية"
              value={filters.q} onChange={(e) => setF('q', e.target.value)} />
            <input className={input} placeholder="اسم العميل أو جواله"
              value={filters.customer} onChange={(e) => setF('customer', e.target.value)} />
            <div className="flex items-center gap-1 md:col-span-2">
              <input type="date" className={`${input} flex-1`} value={filters.date_from} onChange={(e) => setF('date_from', e.target.value)} />
              <span className="text-gray-400 text-xs">إلى</span>
              <input type="date" className={`${input} flex-1`} value={filters.date_to} onChange={(e) => setF('date_to', e.target.value)} />
            </div>
            <div className="flex items-center gap-1">
              <input type="number" className={`${input} w-full`} placeholder="من مبلغ" value={filters.amount_min} onChange={(e) => setF('amount_min', e.target.value)} />
              <input type="number" className={`${input} w-full`} placeholder="إلى مبلغ" value={filters.amount_max} onChange={(e) => setF('amount_max', e.target.value)} />
            </div>
            <select className={input} value={filters.method} onChange={(e) => setF('method', e.target.value)}>
              <option value="">كل طرق الدفع</option>
              <option value="cash">نقدي</option>
              <option value="card">شبكة</option>
              <option value="transfer">تحويل</option>
            </select>
            <div className="md:col-span-2 flex gap-2 justify-end">
              <button type="button" onClick={() => { setFilters(EMPTY); search(EMPTY); }}
                className="px-4 py-2 rounded-lg bg-gray-100 hover:bg-gray-200 text-gray-700 text-sm">مسح</button>
              <button type="submit" className="flex items-center gap-2 bg-bayan-green hover:bg-bayan-dark text-white px-6 py-2 rounded-lg text-sm">
                <HiOutlineSearch /> {searching ? 'جاري البحث...' : 'بحث'}
              </button>
            </div>
          </form>

          {/* Results */}
          <div className="bg-white rounded-xl border shadow-sm overflow-hidden">
            <div className="px-4 py-3 bg-gray-50 border-b text-sm text-gray-600">
              {results.count} فاتورة {results.count > results.rows.length && `(يُعرض أحدث ${results.rows.length})`}
            </div>
            <table className="w-full text-sm text-right">
              <thead>
                <tr className="text-gray-500 border-b">
                  <th className="px-4 py-2 font-medium">رقم الفاتورة</th>
                  <th className="px-4 py-2 font-medium">التاريخ</th>
                  <th className="px-4 py-2 font-medium">العميل</th>
                  <th className="px-4 py-2 font-medium">الدفع</th>
                  <th className="px-4 py-2 font-medium">الإجمالي</th>
                  <th className="px-4 py-2 font-medium">المُرتجع</th>
                  <th className="px-4 py-2"></th>
                </tr>
              </thead>
              <tbody>
                {results.rows.map((r) => {
                  const fully = r.returned_total >= r.total - 0.001;
                  return (
                    <tr key={r.id} className="border-b last:border-0 hover:bg-gray-50 cursor-pointer" onClick={() => openInvoice(r.invoice_number)}>
                      <td className="px-4 py-2 font-medium" dir="ltr">{r.invoice_number}</td>
                      <td className="px-4 py-2 text-gray-600">{fmtDateTime(r.issued_at)}</td>
                      <td className="px-4 py-2 text-gray-600">
                        {r.customer_name || '—'}
                        {r.customer_phone && <span className="text-xs text-gray-400 block" dir="ltr">{r.customer_phone}</span>}
                      </td>
                      <td className="px-4 py-2 text-gray-600">{r.methods.map((m) => METHOD_AR[m]).join(' + ')}</td>
                      <td className="px-4 py-2 font-medium">{r.total.toFixed(2)}</td>
                      <td className={`px-4 py-2 ${r.returned_total > 0 ? 'text-red-600' : 'text-gray-400'}`}>
                        {r.returned_total > 0 ? (fully ? 'مرتجع بالكامل' : r.returned_total.toFixed(2)) : '—'}
                      </td>
                      <td className="px-4 py-2 text-bayan-green">{fully ? '' : 'اختيار ←'}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
            {results.rows.length === 0 && <p className="p-6 text-center text-gray-400">لا توجد فواتير مطابقة</p>}
          </div>
        </>
      )}

      {/* Selected invoice */}
      {saleData && (
        <div className="bg-white rounded-xl border shadow-sm overflow-hidden">
          <div className="px-4 py-3 bg-gray-50 border-b flex items-center justify-between">
            <div className="flex items-center gap-3">
              <button onClick={() => setSaleData(null)} className="p-1 rounded hover:bg-gray-200" title="رجوع للقائمة"><HiOutlineArrowRight /></button>
              <span className="font-bold text-gray-800">فاتورة <span dir="ltr">{saleData.invoice_number}</span></span>
              {saleData.customer_name && <span className="text-sm text-gray-500">· {saleData.customer_name}</span>}
            </div>
            <span className="text-gray-500 text-sm">
              {fmtDateTime(saleData.issued_at)} — الإجمالي: {saleData.total.toFixed(2)} ر.س — الدفع: {METHOD_AR[saleData.payment_method] || saleData.payment_method}
            </span>
          </div>

          <div className="p-4 overflow-x-auto">
            <table className="w-full text-sm text-right">
              <thead>
                <tr className="text-gray-500 border-b">
                  <th className="py-2 font-medium">المنتج</th>
                  <th className="py-2 font-medium">السعر</th>
                  <th className="py-2 font-medium">المباع</th>
                  <th className="py-2 font-medium">المُرتجع سابقاً</th>
                  <th className="py-2 font-medium">المتبقي</th>
                  <th className="py-2 font-medium">كمية الإرجاع</th>
                </tr>
              </thead>
              <tbody>
                {saleData.items.map((it) => (
                  <tr key={it.product_id} className="border-b last:border-0">
                    <td className="py-2 text-gray-800">{it.product_name}</td>
                    <td className="py-2">{it.price.toFixed(2)}</td>
                    <td className="py-2">{it.sold}</td>
                    <td className="py-2">{it.returned}</td>
                    <td className="py-2 font-medium">{it.remaining}</td>
                    <td className="py-2">
                      <input type="number" min={0} step="any" max={it.remaining}
                        value={qty[it.product_id] || ''} disabled={it.remaining === 0}
                        onChange={(e) => setItemQty(it.product_id, e.target.value, it.remaining)}
                        className="w-20 px-2 py-1 rounded border border-gray-300 outline-none text-center disabled:bg-gray-100" />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="p-4 border-t space-y-3">
            <textarea value={reason} onChange={(e) => setReason(e.target.value)} rows={2}
              placeholder="سبب الإرجاع (مطلوب — يظهر على الإشعار الدائن)"
              className="w-full px-3 py-2 rounded-lg border border-gray-300 focus:ring-2 focus:ring-bayan-green outline-none text-right" />
            <div className="flex items-center gap-3 flex-wrap">
              <span className="text-sm text-gray-600">طريقة الاسترداد:</span>
              {saleData.refund_methods.map((m) => (
                <label key={m} className={`px-3 py-1.5 rounded-lg border-2 cursor-pointer text-sm ${refundMethod === m ? 'border-bayan-green bg-bayan-light text-bayan-green' : 'border-gray-200 text-gray-600'}`}>
                  <input type="radio" className="hidden" checked={refundMethod === m} onChange={() => setRefundMethod(m)} />
                  {METHOD_AR[m]}
                </label>
              ))}
              <span className="text-xs text-gray-400">نقداً، أو بإحدى طرق دفع الفاتورة الأصلية</span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-lg font-bold text-gray-800">قيمة الاسترداد: {refundTotal.toFixed(2)} ر.س</span>
              <button onClick={submit}
                disabled={refundTotal <= 0 || !isAdmin || !reason.trim() || !refundMethod}
                title={!isAdmin ? 'ليست لديك صلاحية المرتجعات' : ''}
                className="flex items-center gap-2 bg-bayan-green hover:bg-bayan-dark disabled:opacity-40 disabled:cursor-not-allowed text-white px-6 py-2 rounded-lg transition-all">
                <HiOutlineReceiptRefund /> إصدار إشعار دائن
              </button>
            </div>
            {!isAdmin && <p className="text-xs text-amber-600 text-left">ليست لديك صلاحية المرتجعات.</p>}
          </div>
        </div>
      )}

      {/* Recent credit notes */}
      <div className="bg-white rounded-xl border shadow-sm overflow-hidden">
        <div className="px-4 py-3 bg-gray-50 border-b font-bold text-gray-800">آخر الإشعارات الدائنة</div>
        {recent.length === 0 ? (
          <p className="p-4 text-gray-400 text-sm">لا توجد مرتجعات بعد</p>
        ) : (
          <div className="divide-y">
            {recent.map((r) => (
              <div key={r.id} className="px-4 py-3 flex items-center justify-between text-sm">
                <div className="text-gray-800">
                  <span dir="ltr">{r.credit_note_number}</span>
                  <span className="text-gray-400"> — فاتورة <span dir="ltr">{r.original_invoice_number}</span></span>
                  <span className="text-gray-400 text-xs mr-2">{fmtDateTime(r.issued_at)}</span>
                </div>
                <div className="flex items-center gap-4">
                  <span className="text-gray-500">{METHOD_AR[r.refund_method] || ''}</span>
                  <span className="font-medium text-red-600">-{r.total.toFixed(2)} ر.س</span>
                  <button onClick={() => setPrintDoc(r)} className="text-gray-500 hover:text-bayan-green" title="عرض وطباعة ومشاركة">
                    <HiOutlinePrinter className="text-lg" />
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {printDoc && <DocumentModal type="credit_note" doc={printDoc} onClose={() => setPrintDoc(null)} />}
    </div>
  );
}
