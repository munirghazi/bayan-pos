import { useState, useEffect } from 'react';
import { consignmentAPI, productsAPI, suppliersAPI, apiError } from '../services/api';
import { SarIcon } from '../components/SarIcon';
import toast from 'react-hot-toast';
import { HiOutlineArchive, HiOutlinePlus, HiOutlineTrash, HiOutlineDocumentText, HiOutlineCash, HiOutlinePrinter, HiOutlineCog } from 'react-icons/hi';
import PrintLabelsModal from '../components/PrintLabelsModal';
import { Button, EmptyState } from '../components/ui';


function groupByConsignor(items) {
  const map = {};
  (items || []).forEach((l) => {
    const key = l.consignor_name || 'بدون مودِع';
    (map[key] = map[key] || []).push(l);
  });
  return Object.entries(map).sort((a, b) => a[0].localeCompare(b[0], 'ar'));
}

export default function Consignment({ embedded = false }) {
  const [report, setReport] = useState([]);
  const [consignors, setConsignors] = useState([]);
  const [products, setProducts] = useState([]);
  const [suppliers, setSuppliers] = useState([]);
  const [showConsignor, setShowConsignor] = useState(false);
  const [showIntake, setShowIntake] = useState(false);
  const [statementFor, setStatementFor] = useState(null);
  const [printItems, setPrintItems] = useState(null);
  const [aging, setAging] = useState([]);
  const [stock, setStock] = useState([]);

  const load = () => {
    consignmentAPI.getReport().then(({ data }) => setReport(data)).catch(() => {});
    consignmentAPI.getConsignors().then(({ data }) => setConsignors(data)).catch(() => {});
    consignmentAPI.getAging().then(({ data }) => setAging(data)).catch(() => {});
    consignmentAPI.getStock().then(({ data }) => setStock(data)).catch(() => {});
  };

  const returnLot = async (lot) => {
    const input = window.prompt(`كمية الإرجاع للمودِع (المتاح: ${lot.qty_remaining})`, String(lot.qty_remaining));
    if (input == null) return;
    const qty = parseFloat(input);
    if (isNaN(qty) || qty <= 0) return;
    try {
      await consignmentAPI.returnItem({ consignment_item_id: lot.id, qty });
      toast.success('تم تسجيل الإرجاع');
      load();
    } catch (e) { toast.error(apiError(e, 'تعذر الإرجاع')); }
  };
  useEffect(() => {
    load();
    productsAPI.getAll().then(({ data }) => setProducts(data)).catch(() => {});
    suppliersAPI.getAll().then(({ data }) => setSuppliers(data)).catch(() => {});
  }, []);

  const balanceOf = (cid) => {
    const r = report.find((x) => x.consignor_id === cid);
    return r ? r.balance : 0;
  };

  return (
    <div className={embedded ? 'space-y-5' : 'max-w-5xl mx-auto space-y-6'}>
      <div className="flex items-center justify-between">
        {embedded ? <div /> : (
          <h1 className="text-2xl font-bold text-gray-800 flex items-center gap-2">
            <HiOutlineArchive className="text-bayan-green" /> الأمانات (Consignment)
          </h1>
        )}
        <div className="flex gap-2">
          <Button variant="secondary" size="sm" icon={<HiOutlinePlus />} onClick={() => setShowConsignor(true)}>مودِع جديد</Button>
          <Button variant="primary" size="sm" icon={<HiOutlineArchive />} onClick={() => setShowIntake(true)}>استلام أمانة</Button>
        </div>
      </div>

      {aging.length > 0 && (
        <div className="bg-amber-50 border border-amber-200 rounded-xl p-4">
          <p className="font-bold text-amber-800 mb-2">أصناف تجاوزت مدة الإرجاع ({aging.length})</p>
          <div className="space-y-1">
            {aging.map((a) => (
              <div key={a.id} className="flex items-center justify-between text-sm">
                <span className="text-amber-800">{a.product_name} — {a.consignor_name} · متبقٍ {a.qty_remaining} · {a.days_on_hand} يوم</span>
                <button onClick={() => returnLot(a)} className="text-xs bg-amber-100 hover:bg-amber-200 text-amber-700 px-2 py-1 rounded">إرجاع</button>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Summary report */}
      <div className="bg-white rounded-xl border p-6">
        <h2 className="font-bold text-gray-800 mb-3">ملخص المودِعين</h2>
        {report.length === 0 ? (
          <p className="text-gray-400 text-sm">لا يوجد مودِعون بعد.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-gray-500 border-b">
                  <th className="py-2 text-right">المودِع</th>
                  <th className="text-right">قيمة المخزون</th>
                  <th className="text-right">مستحق</th>
                  <th className="text-right">مدفوع</th>
                  <th className="text-right">الرصيد</th>
                  <th></th>
                </tr>
              </thead>
              <tbody>
                {report.map((r) => (
                  <tr key={r.consignor_id} className="border-b last:border-0">
                    <td className="py-2 font-medium text-gray-800">{r.name}</td>
                    <td>{r.on_hand_value.toFixed(2)}</td>
                    <td>{r.accrued.toFixed(2)}</td>
                    <td>{r.paid.toFixed(2)}</td>
                    <td className={r.balance > 0 ? 'font-bold text-amber-600' : 'text-gray-600'}>{r.balance.toFixed(2)}</td>
                    <td className="text-left">
                      <button onClick={() => setStatementFor(r.consignor_id)}
                        className="text-xs bg-slate-100 hover:bg-slate-200 text-slate-700 px-2 py-1 rounded inline-flex items-center gap-1">
                        <HiOutlineDocumentText /> كشف حساب
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Consigned items — grouped by provider, shown as cards (matches Products) */}
      {stock.length > 0 && groupByConsignor(stock).map(([provider, lots]) => (
        <div key={provider} className="space-y-3">
          <div className="flex items-center gap-3">
            <h3 className="text-xl font-extrabold text-gray-800 whitespace-nowrap">{provider}</h3>
            <span className="text-sm font-medium text-bayan-green bg-bayan-light px-2.5 py-0.5 rounded-full">{lots.length}</span>
            <div className="flex-1 h-px bg-gray-200" />
            <Button variant="secondary" size="sm" icon={<HiOutlinePrinter />}
              onClick={() => setPrintItems(lots.map((l) => ({ name: l.product_name, barcode: l.barcode, price: l.unit_price, qty: Math.max(1, Math.round(l.qty_remaining || 1)) })))}>
              طباعة ملصقات
            </Button>
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
            {lots.map((lot) => (
              <div key={lot.id} className="bg-white rounded-2xl border border-gray-100 shadow-card overflow-hidden">
                <div className="w-full h-32 bg-gray-50 flex items-center justify-center">
                  <HiOutlineArchive className="text-4xl text-gray-300" />
                </div>
                <div className="p-4">
                  <div className="flex items-start justify-between gap-2">
                    <div className="min-w-0">
                      <h4 className="font-bold text-gray-800 truncate">{lot.product_name}</h4>
                      <p className="text-xs text-gray-400 font-mono mt-0.5" dir="ltr">{lot.barcode}</p>
                    </div>
                    <p className="font-bold text-bayan-green text-lg whitespace-nowrap">{Number(lot.unit_price).toFixed(2)} <SarIcon size={15} /></p>
                  </div>
                  <div className="flex items-center justify-between mt-3">
                    <span className="text-sm text-gray-500">متبقٍ: <span className="font-bold text-gray-700">{lot.qty_remaining}</span></span>
                    <div className="flex items-center gap-1">
                      <button onClick={() => setPrintItems([{ name: lot.product_name, barcode: lot.barcode, price: lot.unit_price, qty: Math.max(1, Math.round(lot.qty_remaining || 1)) }])}
                        className="w-9 h-9 flex items-center justify-center text-gray-600 hover:bg-gray-100 rounded-lg" title="طباعة ملصق"><HiOutlinePrinter /></button>
                      <button onClick={() => returnLot(lot)}
                        className="text-xs bg-red-50 hover:bg-red-100 text-red-600 px-3 py-2 rounded-lg">إرجاع للمودِع</button>
                    </div>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      ))}

      {showConsignor && (
        <ConsignorModal suppliers={suppliers} onClose={() => setShowConsignor(false)}
          onSaved={() => { setShowConsignor(false); load(); }} />
      )}
      {showIntake && (
        <IntakeModal consignors={consignors} products={products}
          onClose={() => setShowIntake(false)} onSaved={() => { setShowIntake(false); load(); }}
          onPrint={(rows) => setPrintItems(rows)} />
      )}
      {statementFor && (
        <StatementModal consignorId={statementFor} onClose={() => setStatementFor(null)}
          onPaid={load} />
      )}
      {printItems && (
        <PrintLabelsModal items={printItems} onClose={() => setPrintItems(null)} />
      )}
    </div>
  );
}

function ConsignorModal({ suppliers, onClose, onSaved }) {
  const [form, setForm] = useState({ name: '', phone: '', email: '', supplier_id: '', default_commission_percent: '', return_period_days: '', payout_terms: '' });
  const save = async () => {
    if (!form.name.trim()) { toast.error('الاسم مطلوب'); return; }
    try {
      await consignmentAPI.createConsignor({
        name: form.name.trim(), phone: form.phone || null, email: form.email || null,
        supplier_id: form.supplier_id ? parseInt(form.supplier_id) : null,
        default_commission_percent: parseFloat(form.default_commission_percent || 0),
        return_period_days: form.return_period_days ? parseInt(form.return_period_days) : null,
        payout_terms: form.payout_terms || null,
      });
      toast.success('تم إضافة المودِع');
      onSaved();
    } catch (e) { toast.error(apiError(e, 'تعذر الحفظ')); }
  };
  return (
    <Modal title="مودِع جديد" onClose={onClose}>
      <Field label="الاسم" value={form.name} onChange={(v) => setForm({ ...form, name: v })} />
      <Field label="الجوال" value={form.phone} onChange={(v) => setForm({ ...form, phone: v })} ltr />
      <Field label="البريد" value={form.email} onChange={(v) => setForm({ ...form, email: v })} ltr />
      <div className="mt-3">
        <label className="text-sm text-gray-600">ربط بمورّد (اختياري)</label>
        <select value={form.supplier_id} onChange={(e) => setForm({ ...form, supplier_id: e.target.value })}
          className="w-full mt-1 px-3 py-2 rounded-lg border border-gray-300 outline-none focus:ring-2 focus:ring-bayan-green bg-white">
          <option value="">— بدون —</option>
          {suppliers.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
        </select>
      </div>
      <div className="grid grid-cols-2 gap-3">
        <Field label="عمولة المتجر الافتراضية %" value={form.default_commission_percent} onChange={(v) => setForm({ ...form, default_commission_percent: v })} ltr />
        <Field label="مدة الإرجاع (أيام)" value={form.return_period_days} onChange={(v) => setForm({ ...form, return_period_days: v })} ltr />
      </div>
      <Field label="شروط السداد (اختياري)" value={form.payout_terms} onChange={(v) => setForm({ ...form, payout_terms: v })} />
      <SaveRow onClose={onClose} onSave={save} />
    </Modal>
  );
}

function IntakeModal({ consignors, products, onClose, onSaved, onPrint }) {
  const [consignorId, setConsignorId] = useState('');
  const [lines, setLines] = useState([{ item_text: '', qty: '', unit_price: '', commission_percent: '', barcode: '' }]);
  const [result, setResult] = useState(null);
  const setLine = (i, f, v) => setLines(lines.map((l, idx) => idx === i ? { ...l, [f]: v } : l));
  const addLine = () => setLines([...lines, { item_text: '', qty: '', unit_price: '', commission_percent: '', barcode: '' }]);
  const rmLine = (i) => setLines(lines.filter((_, idx) => idx !== i));

  const save = async () => {
    if (!consignorId) { toast.error('اختر المودِع'); return; }
    const byName = {};
    products.forEach((pp) => { byName[(pp.name || '').trim()] = pp.id; });
    const chosen = lines.filter((l) => (l.item_text || '').trim() && l.qty);
    const meta = [];   // remember display name per line for the result panel
    const payloadLines = chosen.map((l) => {
      const text = l.item_text.trim();
      const pid = byName[text];
      meta.push({ name: text, price: parseFloat(l.unit_price || 0) });
      return {
        ...(pid ? { product_id: pid } : { item_name: text }),
        qty: parseFloat(l.qty),
        unit_price: parseFloat(l.unit_price || 0),
        commission_percent: l.commission_percent === '' ? null : parseFloat(l.commission_percent),
        barcode: l.barcode ? l.barcode.trim() : null,
      };
    });
    if (payloadLines.length === 0) { toast.error('أضف صنفاً واحداً على الأقل'); return; }
    try {
      const { data } = await consignmentAPI.createIntake({ consignor_id: parseInt(consignorId), lines: payloadLines });
      const rows = (data.items || []).map((it, idx) => ({
        name: meta[idx]?.name || '—', price: meta[idx]?.price, barcode: it.barcode,
      }));
      toast.success('تم استلام الأمانة');
      setResult(rows);
    } catch (e) { toast.error(apiError(e, 'تعذر الحفظ')); }
  };

  if (result) {
    return (
      <Modal title="تم الاستلام — الباركودات" wide onClose={() => { onSaved(); }}>
        <p className="text-sm text-gray-500 mb-3">اطبع هذه الباركودات وألصقها على الأصناف. يُمسح الباركود عند البيع في نقطة البيع.</p>
        <div className="divide-y border rounded-lg">
          {result.map((r, i) => (
            <div key={i} className="flex items-center justify-between p-3">
              <span className="font-medium text-gray-800 text-sm">{r.name}</span>
              <span className="font-mono text-sm bg-gray-100 px-3 py-1 rounded" dir="ltr">{r.barcode}</span>
            </div>
          ))}
        </div>
        <div className="flex gap-2 mt-4">
          <button onClick={() => onPrint(result.map((r) => ({ ...r, qty: 1 })))} className="flex-1 bg-gray-100 hover:bg-gray-200 text-gray-700 py-2 rounded-lg text-sm flex items-center justify-center gap-1"><HiOutlinePrinter /> طباعة الملصقات</button>
          <button onClick={() => { onSaved(); }} className="flex-1 bg-bayan-green hover:bg-bayan-dark text-white py-2 rounded-lg text-sm">تم</button>
        </div>
      </Modal>
    );
  }

  return (
    <Modal title="استلام أمانة" wide onClose={onClose}>
      <div>
        <label className="text-sm text-gray-600">المودِع</label>
        <select value={consignorId} onChange={(e) => setConsignorId(e.target.value)}
          className="w-full mt-1 px-3 py-2 rounded-lg border border-gray-300 outline-none focus:ring-2 focus:ring-bayan-green bg-white">
          <option value="">— اختر —</option>
          {consignors.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}
        </select>
      </div>
      <datalist id="consign-products">
        {products.map((p) => <option key={p.id} value={p.name} />)}
      </datalist>
      <p className="mt-3 text-xs text-gray-400">اختر منتجاً موجوداً لإعادة البيع، أو اكتب اسم صنف جديد للأمانات الفريدة (لن يظهر في كتالوج منتجاتك).</p>
      <div className="mt-4 space-y-2">
        <div className="grid grid-cols-12 gap-2 text-xs text-gray-500">
          <span className="col-span-4">الصنف</span><span className="col-span-1">الكمية</span>
          <span className="col-span-2">سعر البيع</span><span className="col-span-2">عمولة%</span>
          <span className="col-span-2">باركود</span><span></span>
        </div>
        {lines.map((l, i) => (
          <div key={i} className="grid grid-cols-12 gap-2 items-center">
            <input list="consign-products" value={l.item_text} onChange={(e) => setLine(i, 'item_text', e.target.value)}
              placeholder="اختر منتجاً أو اكتب اسم صنف"
              className="col-span-4 px-2 py-2 rounded-lg border border-gray-300 outline-none bg-white text-sm" />
            <input type="number" step="any" value={l.qty} onChange={(e) => setLine(i, 'qty', e.target.value)}
              className="col-span-1 px-1 py-2 rounded-lg border border-gray-300 text-center text-sm" />
            <input type="number" step="any" value={l.unit_price} onChange={(e) => setLine(i, 'unit_price', e.target.value)}
              className="col-span-2 px-2 py-2 rounded-lg border border-gray-300 text-center text-sm" />
            <input type="number" step="any" value={l.commission_percent} onChange={(e) => setLine(i, 'commission_percent', e.target.value)}
              placeholder="افتراضي"
              className="col-span-2 px-2 py-2 rounded-lg border border-gray-300 text-center text-sm" />
            <input type="text" dir="ltr" value={l.barcode} onChange={(e) => setLine(i, 'barcode', e.target.value)}
              placeholder="تلقائي"
              className="col-span-2 px-2 py-2 rounded-lg border border-gray-300 text-center text-sm" />
            <button onClick={() => rmLine(i)} className="col-span-1 text-red-400 hover:text-red-600 flex justify-center"><HiOutlineTrash /></button>
          </div>
        ))}
        <button onClick={addLine} className="text-sm text-bayan-green hover:text-bayan-dark flex items-center gap-1"><HiOutlinePlus /> إضافة صنف</button>
      </div>
      <SaveRow onClose={onClose} onSave={save} label="استلام" />
    </Modal>
  );
}

function StatementModal({ consignorId, onClose, onPaid }) {
  const [st, setSt] = useState(null);
  const [amount, setAmount] = useState('');
  const load = () => consignmentAPI.getStatement(consignorId).then(({ data }) => setSt(data)).catch(() => {});
  useEffect(() => { load(); }, [consignorId]);

  const payout = async () => {
    const a = parseFloat(amount);
    if (isNaN(a) || a <= 0) { toast.error('أدخل مبلغاً صحيحاً'); return; }
    try {
      await consignmentAPI.createPayout({ consignor_id: consignorId, amount: a });
      toast.success('تم تسجيل الدفعة');
      setAmount(''); load(); onPaid && onPaid();
    } catch (e) { toast.error(apiError(e, 'تعذر تسجيل الدفعة')); }
  };

  return (
    <Modal title="كشف حساب المودِع" wide onClose={onClose}>
      {!st ? <p className="text-gray-400 text-sm">جارٍ التحميل…</p> : (
        <>
          <div className="grid grid-cols-3 gap-3 text-center mb-4">
            <Stat label="مستحق" value={st.accrued} />
            <Stat label="مدفوع" value={st.paid} />
            <Stat label="الرصيد" value={st.balance} highlight />
          </div>
          <div className="max-h-56 overflow-auto border rounded-lg">
            <table className="w-full text-sm">
              <thead><tr className="text-gray-500 border-b sticky top-0 bg-white">
                <th className="py-2 text-right px-2">التاريخ</th><th className="text-right">النوع</th><th className="text-right px-2">المبلغ</th>
              </tr></thead>
              <tbody>
                {st.entries.map((e) => (
                  <tr key={e.id} className="border-b last:border-0">
                    <td className="py-2 px-2">{e.created_at ? new Date(e.created_at).toLocaleDateString('ar') : '—'}</td>
                    <td>{e.type === 'accrual' ? 'استحقاق بيع' : 'دفعة'}</td>
                    <td className={`px-2 ${e.amount < 0 ? 'text-red-600' : 'text-green-600'}`}>{e.amount.toFixed(2)}</td>
                  </tr>
                ))}
                {st.entries.length === 0 && <tr><td colSpan="3" className="text-center text-gray-400 py-4">لا حركات.</td></tr>}
              </tbody>
            </table>
          </div>
          <div className="flex items-end gap-2 mt-4 pt-3 border-t">
            <div className="flex-1">
              <label className="text-sm text-gray-600">تسجيل دفعة</label>
              <input type="number" step="any" value={amount} onChange={(e) => setAmount(e.target.value)}
                placeholder="المبلغ" dir="ltr"
                className="w-full mt-1 px-3 py-2 rounded-lg border border-gray-300 outline-none focus:ring-2 focus:ring-bayan-green text-right" />
            </div>
            <button onClick={payout} className="bg-bayan-green hover:bg-bayan-dark text-white px-5 py-2 rounded-lg flex items-center gap-1">
              <HiOutlineCash /> دفع
            </button>
          </div>
        </>
      )}
      <button onClick={onClose} className="mt-4 w-full bg-gray-100 hover:bg-gray-200 py-2 rounded-lg text-sm">إغلاق</button>
    </Modal>
  );
}



// ---- small shared UI ----
function Modal({ title, children, onClose, wide }) {
  return (
    <div className="fixed inset-0 bg-black/40 flex items-center justify-center p-4 z-40" onClick={onClose}>
      <div className={`bg-white rounded-2xl shadow-xl w-full ${wide ? 'max-w-xl' : 'max-w-md'} p-6 max-h-[85vh] overflow-auto`} onClick={(e) => e.stopPropagation()}>
        <h2 className="text-lg font-bold text-gray-800 mb-4">{title}</h2>
        {children}
      </div>
    </div>
  );
}
function Field({ label, value, onChange, ltr }) {
  return (
    <div className="mt-3">
      <label className="text-sm text-gray-600">{label}</label>
      <input value={value} onChange={(e) => onChange(e.target.value)} dir={ltr ? 'ltr' : undefined}
        className={`w-full mt-1 px-3 py-2 rounded-lg border border-gray-300 outline-none focus:ring-2 focus:ring-bayan-green ${ltr ? 'text-left' : ''}`} />
    </div>
  );
}
function SaveRow({ onClose, onSave, label }) {
  return (
    <div className="flex gap-2 mt-5">
      <button onClick={onSave} className="flex-1 bg-bayan-green hover:bg-bayan-dark text-white py-2 rounded-lg text-sm">{label || 'حفظ'}</button>
      <button onClick={onClose} className="px-5 py-2 bg-gray-100 hover:bg-gray-200 rounded-lg text-sm">إلغاء</button>
    </div>
  );
}
function Stat({ label, value, highlight }) {
  return (
    <div className={`rounded-lg p-3 ${highlight ? 'bg-bayan-light/40' : 'bg-gray-50'}`}>
      <p className="text-xs text-gray-500">{label}</p>
      <p className="font-bold text-gray-800 flex items-center justify-center gap-1">{value.toFixed(2)} <SarIcon className="w-3.5 h-3.5" /></p>
    </div>
  );
}
