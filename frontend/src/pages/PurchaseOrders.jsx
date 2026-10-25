import { useState, useEffect } from 'react';
import { purchaseOrdersAPI, goodsReceiptsAPI, suppliersAPI, productsAPI, uomAPI, apiError } from '../services/api';
import toast from 'react-hot-toast';
import PrintLabelsModal from '../components/PrintLabelsModal';
import {
  HiOutlineClipboardList, HiOutlinePlus, HiOutlineTrash, HiOutlineX,
  HiOutlineCheckCircle, HiOutlineExclamationCircle,
  HiOutlinePrinter,
} from 'react-icons/hi';

const STATUS = {
  draft: { label: 'مسودّة', cls: 'bg-gray-100 text-gray-600' },
  submitted: { label: 'مُرسل', cls: 'bg-blue-100 text-blue-700' },
  approved: { label: 'معتمد', cls: 'bg-green-100 text-green-700' },
  cancelled: { label: 'ملغى', cls: 'bg-red-100 text-red-600' },
  received: { label: 'مُستلم', cls: 'bg-emerald-100 text-emerald-700' },
  closed: { label: 'مُغلق', cls: 'bg-gray-200 text-gray-700' },
};

const emptyLine = { product_id: '', quantity: '', uom_id: '', unit_cost: '' };

export default function PurchaseOrders() {
  const [orders, setOrders] = useState([]);
  const [suppliers, setSuppliers] = useState([]);
  const [products, setProducts] = useState([]);
  const [units, setUnits] = useState([]);
  const [creating, setCreating] = useState(false);
  const [form, setForm] = useState({ supplier_id: '', notes: '', lines: [{ ...emptyLine }] });
  const [expanded, setExpanded] = useState(null);
  const [receiveFor, setReceiveFor] = useState(null);
  const [printItems, setPrintItems] = useState(null);
  const [rcvLines, setRcvLines] = useState({});

  useEffect(() => { loadAll(); }, []);

  const loadAll = async () => {
    try {
      const [o, s, p, u] = await Promise.all([
        purchaseOrdersAPI.getAll(), suppliersAPI.getAll(),
        productsAPI.getAllAdmin(), uomAPI.units(),
      ]);
      setOrders(o.data);
      setSuppliers(s.data);
      setProducts(p.data);
      setUnits(u.data);
    } catch (err) { toast.error(apiError(err, 'خطأ في التحميل')); }
  };

  const unitsForProduct = (productId) => {
    const p = products.find((x) => x.id === parseInt(productId));
    if (!p || !p.uom_id) return [];
    const base = units.find((u) => u.id === p.uom_id);
    return base ? units.filter((u) => u.category_id === base.category_id) : [];
  };

  const setLine = (i, patch) => {
    const lines = form.lines.map((ln, idx) => (idx === i ? { ...ln, ...patch } : ln));
    setForm({ ...form, lines });
  };

  const onPickProduct = (i, productId) => {
    const p = products.find((x) => x.id === parseInt(productId));
    const defUom = p ? (p.purchase_uom_id || p.uom_id || '') : '';
    setLine(i, { product_id: productId, uom_id: defUom ? defUom.toString() : '', unit_cost: p && p.cost_price ? p.cost_price.toString() : '' });
  };

  const addLine = () => setForm({ ...form, lines: [...form.lines, { ...emptyLine }] });
  const removeLine = (i) => setForm({ ...form, lines: form.lines.filter((_, idx) => idx !== i) });

  const formTotal = form.lines.reduce(
    (sum, ln) => sum + (parseFloat(ln.quantity) || 0) * (parseFloat(ln.unit_cost) || 0), 0);

  const resetForm = () => { setForm({ supplier_id: '', notes: '', lines: [{ ...emptyLine }] }); setCreating(false); };

  const createPO = async () => {
    if (!form.supplier_id) { toast.error('اختر المورّد'); return; }
    const lines = form.lines
      .filter((ln) => ln.product_id && parseFloat(ln.quantity) > 0)
      .map((ln) => ({
        product_id: parseInt(ln.product_id),
        quantity: parseFloat(ln.quantity),
        uom_id: ln.uom_id ? parseInt(ln.uom_id) : null,
        unit_cost: parseFloat(ln.unit_cost) || 0,
      }));
    if (lines.length === 0) { toast.error('أضف بنداً واحداً على الأقل'); return; }
    try {
      await purchaseOrdersAPI.create({ supplier_id: parseInt(form.supplier_id), notes: form.notes || null, lines });
      toast.success('تم إنشاء أمر الشراء (مسودّة)');
      resetForm();
      loadAll();
    } catch (err) { toast.error(apiError(err, 'خطأ في الإنشاء')); }
  };

  const openReceive = (po) => {
    const init = {};
    po.lines.forEach((ln) => {
      const remaining = Number(ln.quantity) - Number(ln.received_qty || 0);
      init[ln.id] = { qty: '', cost: ln.unit_cost != null ? String(ln.unit_cost) : '', remaining };
    });
    setRcvLines(init);
    setReceiveFor(po.id);
  };

  const submitReceive = async (po) => {
    const lines = po.lines
      .filter((ln) => parseFloat(rcvLines[ln.id]?.qty) > 0)
      .map((ln) => ({
        po_line_id: ln.id,
        qty_received: parseFloat(rcvLines[ln.id].qty),
        unit_cost: rcvLines[ln.id].cost !== '' ? parseFloat(rcvLines[ln.id].cost) : null,
      }));
    if (lines.length === 0) { toast.error('أدخل كمية استلام واحدة على الأقل'); return; }
    try {
      await goodsReceiptsAPI.create({ po_id: po.id, lines });
      toast.success('تم استلام البضاعة وتحديث المخزون');
      // offer to print barcode labels for the received items
      const received = po.lines
        .filter((ln) => parseFloat(rcvLines[ln.id]?.qty) > 0)
        .map((ln) => ({ product_id: ln.product_id, name: ln.product_name, qty: Math.max(1, Math.round(parseFloat(rcvLines[ln.id].qty))) }));
      setReceiveFor(null);
      loadAll();
      try {
        const { data } = await productsAPI.ensureBarcodes(received.map((r) => r.product_id));
        const qById = {}; received.forEach((r) => { qById[r.product_id] = (qById[r.product_id] || 0) + r.qty; });
        setPrintItems(data.map((d) => ({ name: d.name, barcode: d.barcode, price: d.price, qty: qById[d.id] || 1 })));
      } catch (e) { /* printing is optional */ }
    } catch (err) { toast.error(apiError(err, 'خطأ في الاستلام')); }
  };

  const act = async (fn, id, okMsg) => {
    try { await fn(id); toast.success(okMsg); loadAll(); }
    catch (err) { toast.error(apiError(err, 'تعذّر تنفيذ العملية')); }
  };

  const selectedSupplier = suppliers.find((s) => s.id === parseInt(form.supplier_id));

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-800 flex items-center gap-2">
            <HiOutlineClipboardList className="text-bayan-green" /> أوامر الشراء
          </h1>
          <p className="text-gray-500 mt-1">لا يمكن إرسال أو اعتماد أمر شراء لمورّد غير متوافق المستندات</p>
        </div>
        <button onClick={() => setCreating(!creating)}
          className="flex items-center gap-2 bg-bayan-green hover:bg-bayan-dark text-white px-5 py-2 rounded-lg transition-all">
          {creating ? <HiOutlineX /> : <HiOutlinePlus />} {creating ? 'إلغاء' : 'أمر شراء جديد'}
        </button>
      </div>

      {/* Create form */}
      {creating && (
        <div className="bg-white rounded-xl border shadow-sm p-4 space-y-4">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">المورّد</label>
              <select value={form.supplier_id} onChange={(e) => setForm({ ...form, supplier_id: e.target.value })}
                className="w-full px-4 py-2 rounded-lg border border-gray-300 focus:ring-2 focus:ring-bayan-green outline-none">
                <option value="">اختر مورّداً…</option>
                {suppliers.map((s) => (
                  <option key={s.id} value={s.id}>{s.name}{s.is_compliant ? '' : ' (غير متوافق)'}</option>
                ))}
              </select>
              {selectedSupplier && !selectedSupplier.is_compliant && (
                <p className="text-xs text-red-600 mt-1 flex items-center gap-1">
                  <HiOutlineExclamationCircle /> هذا المورّد غير متوافق — يمكن حفظ المسودّة لكن لا يمكن إرسالها أو اعتمادها
                </p>
              )}
            </div>
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">ملاحظات</label>
              <input value={form.notes} onChange={(e) => setForm({ ...form, notes: e.target.value })}
                className="w-full px-4 py-2 rounded-lg border border-gray-300 focus:ring-2 focus:ring-bayan-green outline-none text-right" />
            </div>
          </div>

          {/* Lines */}
          <div className="space-y-2">
            <div className="grid grid-cols-12 gap-2 text-xs text-gray-500 px-1">
              <span className="col-span-5">المنتج</span><span className="col-span-2">الكمية</span>
              <span className="col-span-2">الوحدة</span><span className="col-span-2">التكلفة</span><span></span>
            </div>
            {form.lines.map((ln, i) => (
              <div key={i} className="grid grid-cols-12 gap-2 items-center">
                <select value={ln.product_id} onChange={(e) => onPickProduct(i, e.target.value)}
                  className="col-span-5 px-3 py-2 rounded-lg border border-gray-300 outline-none text-sm">
                  <option value="">اختر…</option>
                  {products.map((p) => (<option key={p.id} value={p.id}>{p.name}</option>))}
                </select>
                <input type="number" step="any" value={ln.quantity} onChange={(e) => setLine(i, { quantity: e.target.value })}
                  className="col-span-2 px-2 py-2 rounded-lg border border-gray-300 outline-none text-sm text-center" placeholder="0" />
                <select value={ln.uom_id} onChange={(e) => setLine(i, { uom_id: e.target.value })}
                  className="col-span-2 px-2 py-2 rounded-lg border border-gray-300 outline-none text-sm">
                  <option value="">—</option>
                  {unitsForProduct(ln.product_id).map((u) => (<option key={u.id} value={u.id}>{u.name}</option>))}
                </select>
                <input type="number" step="any" value={ln.unit_cost} onChange={(e) => setLine(i, { unit_cost: e.target.value })}
                  className="col-span-2 px-2 py-2 rounded-lg border border-gray-300 outline-none text-sm text-center" placeholder="0.00" />
                <button onClick={() => removeLine(i)} className="col-span-1 text-red-400 hover:text-red-600 flex justify-center"><HiOutlineTrash /></button>
              </div>
            ))}
            <button onClick={addLine} className="text-sm text-bayan-green hover:underline flex items-center gap-1"><HiOutlinePlus /> إضافة بند</button>
          </div>

          <div className="flex items-center justify-between pt-2 border-t">
            <span className="font-bold text-gray-800">الإجمالي: {formTotal.toFixed(2)} ر.س</span>
            <button onClick={createPO} className="bg-bayan-green hover:bg-bayan-dark text-white px-6 py-2 rounded-lg transition-all">حفظ كمسودّة</button>
          </div>
        </div>
      )}

      {/* PO list */}
      <div className="bg-white rounded-xl border shadow-sm overflow-hidden">
        <div className="px-4 py-3 bg-gray-50 border-b font-bold text-gray-800">أوامر الشراء ({orders.length})</div>
        {orders.length === 0 ? (
          <p className="p-4 text-gray-400 text-sm">لا توجد أوامر شراء</p>
        ) : (
          <div className="divide-y">
            {orders.map((po) => {
              const st = STATUS[po.status] || { label: po.status, cls: 'bg-gray-100 text-gray-600' };
              return (
                <div key={po.id}>
                  <div className="px-4 py-3 flex items-center justify-between hover:bg-gray-50 cursor-pointer"
                    onClick={() => setExpanded(expanded === po.id ? null : po.id)}>
                    <div className="flex items-center gap-2">
                      {po.supplier_compliant
                        ? <HiOutlineCheckCircle className="text-green-600" />
                        : <HiOutlineExclamationCircle className="text-red-500" />}
                      <span className="font-medium text-gray-800">أمر #{po.po_number}</span>
                      <span className="text-gray-500 text-sm">— {po.supplier_name}</span>
                    </div>
                    <div className="flex items-center gap-3">
                      <span className="text-gray-600 text-sm">{po.total.toFixed(2)} ر.س</span>
                      {(po.status === 'approved' || po.status === 'receiving') && (
                        <button onClick={(e) => { e.stopPropagation(); setExpanded(po.id); openReceive(po); }}
                          className="bg-bayan-green hover:bg-bayan-dark text-white px-3 py-1 rounded text-xs whitespace-nowrap">استلام</button>
                      )}
                      <span className={`text-xs px-2 py-0.5 rounded-full ${st.cls}`}>{st.label}</span>
                    </div>
                  </div>

                  {expanded === po.id && (
                    <div className="px-4 pb-4 bg-gray-50/50 overflow-x-auto">
                      <table className="w-full text-sm text-right mb-3 min-w-[520px]">
                        <thead>
                          <tr className="text-gray-500 border-b">
                            <th className="py-2 font-medium">المنتج</th><th className="py-2 font-medium">الكمية</th>
                            <th className="py-2 font-medium">الوحدة</th><th className="py-2 font-medium">التكلفة</th>
                            <th className="py-2 font-medium">الإجمالي</th>
                          </tr>
                        </thead>
                        <tbody>
                          {po.lines.map((ln) => (
                            <tr key={ln.id} className="border-b last:border-0">
                              <td className="py-2">{ln.product_name}</td>
                              <td className="py-2">{ln.quantity}</td>
                              <td className="py-2">{ln.uom_name || '—'}</td>
                              <td className="py-2">{Number(ln.unit_cost).toFixed(2)}</td>
                              <td className="py-2">{Number(ln.line_total).toFixed(2)}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                      {po.notes && <p className="text-sm text-gray-500 mb-3">ملاحظات: {po.notes}</p>}
                      <div className="flex flex-wrap gap-2">
                        {po.status === 'draft' && (
                          <>
                            <button onClick={() => act(purchaseOrdersAPI.submit, po.id, 'تم الإرسال')} className="bg-blue-600 hover:bg-blue-700 text-white px-4 py-1.5 rounded text-sm">إرسال</button>
                            <button onClick={() => act(purchaseOrdersAPI.approve, po.id, 'تم الاعتماد')} className="bg-green-600 hover:bg-green-700 text-white px-4 py-1.5 rounded text-sm">اعتماد</button>
                            <button onClick={() => act(purchaseOrdersAPI.delete, po.id, 'تم الحذف')} className="bg-red-100 hover:bg-red-200 text-red-700 px-4 py-1.5 rounded text-sm">حذف</button>
                          </>
                        )}
                        {po.status === 'submitted' && (
                          <>
                            <button onClick={() => act(purchaseOrdersAPI.approve, po.id, 'تم الاعتماد')} className="bg-green-600 hover:bg-green-700 text-white px-4 py-1.5 rounded text-sm">اعتماد</button>
                            <button onClick={() => act(purchaseOrdersAPI.cancel, po.id, 'تم الإلغاء')} className="bg-red-100 hover:bg-red-200 text-red-700 px-4 py-1.5 rounded text-sm">إلغاء</button>
                          </>
                        )}
                        {(po.status === 'approved' || po.status === 'receiving') && (
                          <button onClick={() => openReceive(po)}
                            className="bg-bayan-green hover:bg-bayan-dark text-white px-4 py-1.5 rounded text-sm">استلام بضاعة</button>
                        )}
                      </div>

                      {receiveFor === po.id && (
                        <div className="mt-3 border-t pt-3">
                          <h4 className="font-bold text-gray-800 mb-2">استلام بضاعة</h4>
                          <div className="overflow-x-auto">
                          <table className="w-full text-sm text-right mb-3 min-w-[560px]">
                            <thead>
                              <tr className="text-gray-500 border-b">
                                <th className="py-2 font-medium">المنتج</th><th className="py-2 font-medium">المطلوب</th>
                                <th className="py-2 font-medium">المستلم</th><th className="py-2 font-medium">المتبقي</th>
                                <th className="py-2 font-medium">كمية الاستلام</th><th className="py-2 font-medium">التكلفة</th>
                              </tr>
                            </thead>
                            <tbody>
                              {po.lines.map((ln) => {
                                const remaining = Number(ln.quantity) - Number(ln.received_qty || 0);
                                return (
                                  <tr key={ln.id} className="border-b last:border-0">
                                    <td className="py-2">{ln.product_name} {ln.uom_name ? `(${ln.uom_name})` : ''}</td>
                                    <td className="py-2">{ln.quantity}</td>
                                    <td className="py-2">{ln.received_qty || 0}</td>
                                    <td className="py-2 font-medium">{remaining}</td>
                                    <td className="py-2">
                                      <input type="number" step="any" min="0" max={remaining}
                                        value={rcvLines[ln.id]?.qty ?? ''}
                                        disabled={remaining <= 0}
                                        onChange={(e) => setRcvLines({ ...rcvLines, [ln.id]: { ...rcvLines[ln.id], qty: e.target.value } })}
                                        className="w-20 px-2 py-1 rounded border border-gray-300 outline-none text-center disabled:bg-gray-100" />
                                    </td>
                                    <td className="py-2">
                                      <input type="number" step="any"
                                        value={rcvLines[ln.id]?.cost ?? ''}
                                        onChange={(e) => setRcvLines({ ...rcvLines, [ln.id]: { ...rcvLines[ln.id], cost: e.target.value } })}
                                        className="w-24 px-2 py-1 rounded border border-gray-300 outline-none text-center" />
                                    </td>
                                  </tr>
                                );
                              })}
                            </tbody>
                          </table>
                          </div>
                          <div className="flex gap-2">
                            <button onClick={() => submitReceive(po)}
                              className="bg-bayan-green hover:bg-bayan-dark text-white px-6 py-2 rounded-lg text-sm">تأكيد الاستلام</button>
                            <button onClick={() => setReceiveFor(null)}
                              className="bg-gray-100 hover:bg-gray-200 text-gray-700 px-6 py-2 rounded-lg text-sm">إغلاق</button>
                          </div>
                        </div>
                      )}
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </div>
      {printItems && (
        <PrintLabelsModal items={printItems} onClose={() => setPrintItems(null)} />
      )}
    </div>
  );
}
