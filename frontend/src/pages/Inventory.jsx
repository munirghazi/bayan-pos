import { useState, useEffect } from 'react';
import { productsAPI, uomAPI, stockAPI, apiError } from '../services/api';
import toast from 'react-hot-toast';
import { HiOutlineArchive, HiOutlinePlusCircle, HiOutlineAdjustments } from 'react-icons/hi';

const TYPE_LABEL = { in: 'إدخال', out: 'إخراج', adjust: 'تسوية' };
const REF_LABEL = { sale: 'بيع', return: 'مرتجع', manual: 'إدخال يدوي', adjustment: 'جرد' };

export default function Inventory() {
  const [products, setProducts] = useState([]);
  const [units, setUnits] = useState([]);
  const [selectedId, setSelectedId] = useState('');
  const [movements, setMovements] = useState([]);
  const [inForm, setInForm] = useState({ quantity: '', uom_id: '', unit_cost: '', note: '' });
  const [adjForm, setAdjForm] = useState({ new_quantity: '', uom_id: '', note: '' });

  useEffect(() => { load(); }, []);

  const load = async () => {
    try {
      const [p, u] = await Promise.all([productsAPI.getAllAdmin(), uomAPI.units()]);
      setProducts(p.data.filter((x) => !x.is_kit));
      setUnits(u.data);
    } catch (err) { toast.error(apiError(err, 'خطأ في التحميل')); }
  };

  const selected = products.find((p) => p.id === parseInt(selectedId));

  // units in the same category as the selected product's base unit
  const productUnits = (() => {
    if (!selected || !selected.uom_id) return [];
    const base = units.find((u) => u.id === selected.uom_id);
    return base ? units.filter((u) => u.category_id === base.category_id) : [];
  })();

  useEffect(() => {
    if (!selectedId) { setMovements([]); return; }
    loadMovements();
    setInForm({ quantity: '', uom_id: '', unit_cost: '', note: '' });
    setAdjForm({ new_quantity: '', uom_id: '', note: '' });
  }, [selectedId]);

  const loadMovements = async () => {
    try {
      const r = await stockAPI.movements(selectedId);
      setMovements(r.data);
    } catch (err) { toast.error(apiError(err, 'خطأ')); }
  };

  const doStockIn = async () => {
    if (!inForm.quantity || parseFloat(inForm.quantity) <= 0) { toast.error('أدخل كمية صحيحة'); return; }
    try {
      await stockAPI.stockIn({
        product_id: parseInt(selectedId),
        quantity: parseFloat(inForm.quantity),
        uom_id: inForm.uom_id ? parseInt(inForm.uom_id) : null,
        unit_cost: inForm.unit_cost ? parseFloat(inForm.unit_cost) : null,
        note: inForm.note || null,
      });
      toast.success('تم إدخال المخزون');
      setInForm({ quantity: '', uom_id: '', unit_cost: '', note: '' });
      await load();
      loadMovements();
    } catch (err) { toast.error(apiError(err, 'خطأ في الإدخال')); }
  };

  const doAdjust = async () => {
    if (adjForm.new_quantity === '' || parseFloat(adjForm.new_quantity) < 0) { toast.error('أدخل كمية صحيحة'); return; }
    try {
      await stockAPI.adjust({
        product_id: parseInt(selectedId),
        new_quantity: parseFloat(adjForm.new_quantity),
        uom_id: adjForm.uom_id ? parseInt(adjForm.uom_id) : null,
        note: adjForm.note || null,
      });
      toast.success('تم تعديل المخزون');
      setAdjForm({ new_quantity: '', uom_id: '', note: '' });
      await load();
      loadMovements();
    } catch (err) { toast.error(apiError(err, 'خطأ في التسوية')); }
  };

  const unitOptions = (value, onChange) => (
    <select value={value} onChange={onChange}
      className="px-3 py-2 rounded-lg border border-gray-300 outline-none text-sm bg-white">
      <option value="">{selected?.uom_name || 'الوحدة الأساسية'}</option>
      {productUnits.map((u) => (<option key={u.id} value={u.id}>{u.name}</option>))}
    </select>
  );

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-800 flex items-center gap-2">
          <HiOutlineArchive className="text-bayan-green" /> حركة المخزون
        </h1>
        <p className="text-gray-500 mt-1">إدخال مخزون، تسوية جرد، وسجل كامل لحركات كل منتج</p>
      </div>

      <div className="bg-white rounded-xl border shadow-sm p-4">
        <label className="block text-sm font-medium text-gray-700 mb-1">المنتج</label>
        <select value={selectedId} onChange={(e) => setSelectedId(e.target.value)}
          className="w-full px-4 py-2 rounded-lg border border-gray-300 focus:ring-2 focus:ring-bayan-green outline-none">
          <option value="">اختر منتجاً…</option>
          {products.map((p) => (<option key={p.id} value={p.id}>{p.name}</option>))}
        </select>
        {selected && (
          <p className="mt-3 text-gray-700">
            الرصيد الحالي: <span className="font-bold">{selected.stock}</span> {selected.uom_name || ''}
          </p>
        )}
      </div>

      {selected && (
        <>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            {/* Stock in */}
            <div className="bg-white rounded-xl border shadow-sm p-4 space-y-3">
              <h2 className="font-bold text-gray-800 flex items-center gap-2"><HiOutlinePlusCircle className="text-bayan-green" /> إدخال مخزون</h2>
              <div className="flex gap-2">
                <input type="number" step="any" value={inForm.quantity}
                  onChange={(e) => setInForm({ ...inForm, quantity: e.target.value })}
                  placeholder="الكمية" className="flex-1 px-3 py-2 rounded-lg border border-gray-300 outline-none text-sm" />
                {selected.uom_id ? unitOptions(inForm.uom_id, (e) => setInForm({ ...inForm, uom_id: e.target.value })) : null}
              </div>
              <input type="number" step="any" value={inForm.unit_cost}
                onChange={(e) => setInForm({ ...inForm, unit_cost: e.target.value })}
                placeholder="تكلفة الوحدة (اختياري)" className="w-full px-3 py-2 rounded-lg border border-gray-300 outline-none text-sm" />
              <input value={inForm.note} onChange={(e) => setInForm({ ...inForm, note: e.target.value })}
                placeholder="ملاحظة (اختياري)" className="w-full px-3 py-2 rounded-lg border border-gray-300 outline-none text-sm text-right" />
              <button onClick={doStockIn} className="w-full bg-bayan-green hover:bg-bayan-dark text-white py-2 rounded-lg transition-all">إدخال</button>
            </div>

            {/* Adjust */}
            <div className="bg-white rounded-xl border shadow-sm p-4 space-y-3">
              <h2 className="font-bold text-gray-800 flex items-center gap-2"><HiOutlineAdjustments className="text-bayan-green" /> تسوية جرد</h2>
              <div className="flex gap-2">
                <input type="number" step="any" value={adjForm.new_quantity}
                  onChange={(e) => setAdjForm({ ...adjForm, new_quantity: e.target.value })}
                  placeholder="الرصيد الفعلي بعد الجرد" className="flex-1 px-3 py-2 rounded-lg border border-gray-300 outline-none text-sm" />
                {selected.uom_id ? unitOptions(adjForm.uom_id, (e) => setAdjForm({ ...adjForm, uom_id: e.target.value })) : null}
              </div>
              <input value={adjForm.note} onChange={(e) => setAdjForm({ ...adjForm, note: e.target.value })}
                placeholder="ملاحظة (اختياري)" className="w-full px-3 py-2 rounded-lg border border-gray-300 outline-none text-sm text-right" />
              <button onClick={doAdjust} className="w-full bg-amber-500 hover:bg-amber-600 text-white py-2 rounded-lg transition-all">تسوية</button>
            </div>
          </div>

          {/* Ledger */}
          <div className="bg-white rounded-xl border shadow-sm overflow-hidden">
            <div className="px-4 py-3 bg-gray-50 border-b font-bold text-gray-800">سجل الحركات</div>
            {movements.length === 0 ? (
              <p className="p-4 text-gray-400 text-sm">لا توجد حركات</p>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-sm text-right">
                  <thead>
                    <tr className="text-gray-500 border-b">
                      <th className="p-3 font-medium">النوع</th>
                      <th className="p-3 font-medium">الكمية</th>
                      <th className="p-3 font-medium">الرصيد بعدها</th>
                      <th className="p-3 font-medium">المرجع</th>
                      <th className="p-3 font-medium">ملاحظة</th>
                      <th className="p-3 font-medium">التاريخ</th>
                    </tr>
                  </thead>
                  <tbody>
                    {movements.map((m) => (
                      <tr key={m.id} className="border-b last:border-0">
                        <td className="p-3">{TYPE_LABEL[m.type] || m.type}</td>
                        <td className={`p-3 font-medium ${m.qty < 0 ? 'text-red-600' : 'text-green-600'}`}>
                          {m.qty > 0 ? '+' : ''}{m.qty}
                        </td>
                        <td className="p-3">{m.balance_after}</td>
                        <td className="p-3 text-gray-500">{REF_LABEL[m.ref_type] || m.ref_type || '—'}{m.ref_id ? ` #${m.ref_id}` : ''}</td>
                        <td className="p-3 text-gray-500">{m.note || '—'}</td>
                        <td className="p-3 text-gray-400">{new Date(m.created_at).toLocaleString('ar-EG')}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </>
      )}
    </div>
  );
}
