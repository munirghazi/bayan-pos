import { useState, useEffect, useRef } from 'react';
import { returnsAPI, apiError } from '../services/api';
import toast from 'react-hot-toast';
import { HiOutlineReceiptRefund, HiOutlineSearch } from 'react-icons/hi';

export default function Returns() {
  const currentUser = JSON.parse(localStorage.getItem('user') || '{}');
  const isAdmin = currentUser.role === 'admin';
  const [saleId, setSaleId] = useState('');
  const [saleData, setSaleData] = useState(null); // { sale_id, total, items:[...] }
  const [qty, setQty] = useState({}); // product_id -> quantity
  const [reason, setReason] = useState('');
  const [recent, setRecent] = useState([]);
  const submittingRef = useRef(false);

  useEffect(() => { loadRecent(); }, []);

  const loadRecent = async () => {
    try {
      const res = await returnsAPI.getAll();
      setRecent(res.data);
    } catch (err) {}
  };

  const lookup = async () => {
    const id = parseInt(saleId);
    if (!id) { toast.error('أدخل رقم الفاتورة'); return; }
    try {
      const res = await returnsAPI.getForSale(id);
      setSaleData(res.data);
      setQty({});
      setReason('');
    } catch (err) {
      setSaleData(null);
      toast.error(apiError(err, 'تعذّر العثور على الفاتورة'));
    }
  };

  const setItemQty = (pid, val, max) => {
    let n = parseInt(val);
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
    if (submittingRef.current) return;
    submittingRef.current = true;
    try {
      if (!isAdmin) { toast.error('تنفيذ المرتجعات يتطلب صلاحية مدير'); return; }
      const res = await returnsAPI.create({
        sale_id: saleData.sale_id, items, reason: reason.trim() || null,
      });
      toast.success(`تم إنشاء إشعار دائن رقم ${res.data.credit_note_number} — استرداد ${res.data.total.toFixed(2)} ر.س`);
      const fresh = await returnsAPI.getForSale(saleData.sale_id);
      setSaleData(fresh.data);
      setQty({});
      setReason('');
      loadRecent();
    } catch (err) {
      toast.error(apiError(err, 'خطأ في تنفيذ المرتجع'));
    } finally {
      submittingRef.current = false;
    }
  };

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-800">المرتجعات</h1>
        <p className="text-gray-500 mt-1">إرجاع أصناف من فاتورة وإصدار إشعار دائن</p>
      </div>

      {/* Lookup */}
      <div className="bg-white rounded-xl border shadow-sm p-4 flex gap-3">
        <input
          type="number"
          value={saleId}
          onChange={(e) => setSaleId(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && lookup()}
          placeholder="رقم الفاتورة"
          className="flex-1 px-4 py-2 rounded-lg border border-gray-300 focus:ring-2 focus:ring-bayan-green outline-none text-right"
        />
        <button
          onClick={lookup}
          className="flex items-center gap-2 bg-bayan-green hover:bg-bayan-dark text-white px-6 py-2 rounded-lg transition-all"
        >
          <HiOutlineSearch /> بحث
        </button>
      </div>

      {/* Sale items */}
      {saleData && (
        <div className="bg-white rounded-xl border shadow-sm overflow-hidden">
          <div className="px-4 py-3 bg-gray-50 border-b flex items-center justify-between">
            <span className="font-bold text-gray-800">فاتورة رقم {saleData.sale_id}</span>
            <span className="text-gray-500 text-sm">الإجمالي الأصلي: {saleData.total.toFixed(2)} ر.س</span>
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
                      <input
                        type="number"
                        min={0}
                        max={it.remaining}
                        value={qty[it.product_id] || ''}
                        disabled={it.remaining === 0}
                        onChange={(e) => setItemQty(it.product_id, e.target.value, it.remaining)}
                        className="w-20 px-2 py-1 rounded border border-gray-300 outline-none text-center disabled:bg-gray-100"
                      />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div className="p-4 border-t space-y-3">
            <textarea
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              placeholder="سبب الإرجاع (اختياري)"
              rows={2}
              className="w-full px-3 py-2 rounded-lg border border-gray-300 focus:ring-2 focus:ring-bayan-green outline-none text-right"
            />
            <div className="flex items-center justify-between">
              <span className="text-lg font-bold text-gray-800">قيمة الاسترداد: {refundTotal.toFixed(2)} ر.س</span>
              <button
                onClick={submit}
                disabled={refundTotal <= 0 || !isAdmin}
                title={!isAdmin ? 'المرتجعات تتطلب صلاحية مدير' : ''}
                className="flex items-center gap-2 bg-bayan-green hover:bg-bayan-dark disabled:opacity-40 disabled:cursor-not-allowed text-white px-6 py-2 rounded-lg transition-all"
              >
                <HiOutlineReceiptRefund /> تنفيذ المرتجع
              </button>
            </div>
            {!isAdmin && (
              <p className="text-xs text-amber-600 text-left">تنفيذ المرتجعات يتطلب صلاحية مدير.</p>
            )}
          </div>
        </div>
      )}

      {/* Recent credit notes */}
      <div className="bg-white rounded-xl border shadow-sm overflow-hidden">
        <div className="px-4 py-3 bg-gray-50 border-b font-bold text-gray-800">آخر المرتجعات</div>
        {recent.length === 0 ? (
          <p className="p-4 text-gray-400 text-sm">لا توجد مرتجعات بعد</p>
        ) : (
          <div className="divide-y">
            {recent.map((r) => (
              <div key={r.id} className="px-4 py-3 flex items-center justify-between text-sm">
                <div className="text-gray-800">
                  إشعار دائن #{r.credit_note_number}
                  <span className="text-gray-400"> — فاتورة {r.sale_id}</span>
                </div>
                <div className="flex items-center gap-4">
                  <span className="text-gray-500">{r.items.length} صنف</span>
                  <span className="font-medium text-red-600">-{r.total.toFixed(2)} ر.س</span>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
