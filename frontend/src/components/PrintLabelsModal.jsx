import { useState } from 'react';
import toast from 'react-hot-toast';
import { HiOutlinePrinter, HiOutlineCog, HiOutlineTrash } from 'react-icons/hi';
import { getLabelSettings, saveLabelSettings, printZebra, downloadZpl, printSheet } from '../utils/labels';

// Shared barcode-label print dialog. items: [{ name, barcode, price, qty }]
export default function PrintLabelsModal({ items, onClose }) {
  const [rows, setRows] = useState(items.map((it) => ({ ...it, qty: it.qty || 1 })));
  const [s, setS] = useState(getLabelSettings());
  const [showSettings, setShowSettings] = useState(false);
  const [busy, setBusy] = useState(false);
  const setQty = (i, v) => setRows(rows.map((r, idx) => idx === i ? { ...r, qty: Math.max(1, parseInt(v || 1)) } : r));
  const removeRow = (i) => setRows(rows.filter((_, idx) => idx !== i));
  const setSetting = (f, v) => { const ns = { ...s, [f]: v }; setS(ns); saveLabelSettings(ns); };
  const totalLabels = rows.reduce((n, r) => n + (parseInt(r.qty) || 1), 0);

  const doZebra = async () => {
    if (busy || rows.length === 0) return; setBusy(true);
    try { await printZebra(rows, s); toast.success(`أُرسلت ${totalLabels} ملصقاً إلى الطابعة`); onClose(); }
    catch (e) { toast.error('تعذّر الاتصال بطابعة Zebra. تأكد من تشغيل Zebra Browser Print — أو نزّل ملف ZPL.'); }
    finally { setBusy(false); }
  };
  const doDownload = async () => { try { await downloadZpl(rows, s); } catch (e) { toast.error('تعذّر توليد ZPL'); } };

  return (
    <div className="fixed inset-0 bg-black/40 flex items-center justify-center p-4 z-50" onClick={onClose}>
      <div className="bg-white rounded-2xl shadow-xl w-full max-w-xl p-6 max-h-[85vh] overflow-auto" onClick={(e) => e.stopPropagation()}>
        <h2 className="text-lg font-bold text-gray-800 mb-4">طباعة ملصقات الباركود</h2>
        <div className="flex items-center justify-between mb-2">
          <p className="text-sm text-gray-500">إجمالي الملصقات: <span className="font-bold">{totalLabels}</span></p>
          <button onClick={() => setShowSettings(!showSettings)} className="text-xs text-gray-500 hover:text-gray-700 flex items-center gap-1"><HiOutlineCog /> إعدادات الطابعة</button>
        </div>

        {showSettings && (
          <div className="bg-gray-50 rounded-lg p-3 mb-3 grid grid-cols-2 gap-3 text-sm">
            <div>
              <label className="text-xs text-gray-600">نوع الطابعة</label>
              <select value={s.mode} onChange={(e) => setSetting('mode', e.target.value)} className="w-full mt-1 px-2 py-1.5 rounded border border-gray-300 bg-white">
                <option value="zebra">Zebra (Browser Print)</option>
                <option value="sheet">طابعة عادية / ورقة ملصقات</option>
              </select>
            </div>
            <div>
              <label className="text-xs text-gray-600">الدقة DPI</label>
              <select value={s.dpi} onChange={(e) => setSetting('dpi', parseInt(e.target.value))} className="w-full mt-1 px-2 py-1.5 rounded border border-gray-300 bg-white">
                <option value={203}>203 (GK420t)</option>
                <option value={300}>300</option>
              </select>
            </div>
            <div>
              <label className="text-xs text-gray-600">العرض (مم)</label>
              <input type="number" value={s.width_mm} onChange={(e) => setSetting('width_mm', parseFloat(e.target.value || 0))} className="w-full mt-1 px-2 py-1.5 rounded border border-gray-300" dir="ltr" />
            </div>
            <div>
              <label className="text-xs text-gray-600">الارتفاع (مم)</label>
              <input type="number" value={s.height_mm} onChange={(e) => setSetting('height_mm', parseFloat(e.target.value || 0))} className="w-full mt-1 px-2 py-1.5 rounded border border-gray-300" dir="ltr" />
            </div>
            <label className="flex items-center gap-2 text-xs text-gray-600"><input type="checkbox" checked={s.name} onChange={(e) => setSetting('name', e.target.checked)} /> إظهار الاسم</label>
            <label className="flex items-center gap-2 text-xs text-gray-600"><input type="checkbox" checked={s.price} onChange={(e) => setSetting('price', e.target.checked)} /> إظهار السعر</label>
          </div>
        )}

        <div className="max-h-64 overflow-auto divide-y border rounded-lg">
          {rows.length === 0 && <p className="text-center text-gray-400 text-sm py-4">لا أصناف للطباعة.</p>}
          {rows.map((r, i) => (
            <div key={i} className="flex items-center justify-between p-2.5 gap-2">
              <div className="min-w-0 flex-1">
                <p className="text-sm font-medium text-gray-800 truncate">{r.name}</p>
                <p className="text-xs text-gray-400 font-mono" dir="ltr">{r.barcode}</p>
              </div>
              <div className="flex items-center gap-2">
                <span className="text-xs text-gray-500">عدد</span>
                <input type="number" min="1" value={r.qty} onChange={(e) => setQty(i, e.target.value)} className="w-16 px-2 py-1 rounded border border-gray-300 text-center text-sm" dir="ltr" />
                <button onClick={() => removeRow(i)} className="text-red-400 hover:text-red-600"><HiOutlineTrash /></button>
              </div>
            </div>
          ))}
        </div>

        <div className="flex gap-2 mt-4">
          {s.mode === 'zebra' ? (
            <>
              <button onClick={doZebra} disabled={busy || rows.length === 0} className="flex-1 bg-bayan-green hover:bg-bayan-dark disabled:opacity-50 text-white py-2 rounded-lg text-sm flex items-center justify-center gap-1"><HiOutlinePrinter /> طباعة على Zebra</button>
              <button onClick={doDownload} className="px-4 py-2 bg-gray-100 hover:bg-gray-200 text-gray-700 rounded-lg text-sm">تنزيل ZPL</button>
            </>
          ) : (
            <button onClick={() => printSheet(rows, s)} disabled={rows.length === 0} className="flex-1 bg-bayan-green hover:bg-bayan-dark disabled:opacity-50 text-white py-2 rounded-lg text-sm flex items-center justify-center gap-1"><HiOutlinePrinter /> طباعة</button>
          )}
          <button onClick={onClose} className="px-5 py-2 bg-gray-100 hover:bg-gray-200 rounded-lg text-sm">إغلاق</button>
        </div>
      </div>
    </div>
  );
}
