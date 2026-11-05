import { useEffect, useMemo, useRef, useState } from 'react';
import toast from 'react-hot-toast';
import {
  HiOutlineCash, HiOutlineCreditCard, HiOutlineDeviceMobile, HiOutlineTrash,
  HiOutlinePaperClip, HiOutlineCheckCircle, HiOutlineClock,
} from 'react-icons/hi';
import { SarIcon } from './SarIcon';
import { uploadProof, openProof } from '../utils/proofs';

export const METHOD_META = {
  cash: { label: 'نقدي', icon: HiOutlineCash },
  card: { label: 'شبكة', icon: HiOutlineCreditCard },
  transfer: { label: 'تحويل بنكي', icon: HiOutlineDeviceMobile },
};

const r2 = (n) => Math.round((Number(n) || 0) * 100) / 100;
let seq = 0;
const newLine = (method, amount) => ({ key: ++seq, method, amount: amount > 0 ? amount.toFixed(2) : '', card_ref: '', proof: null });

/**
 * Split payment for one invoice.
 * Rules (same as the server): only CASH may exceed what is left (change comes
 * from cash); card and transfer must not exceed it; card needs the terminal
 * transaction code; transfer needs its proof — or the sale is saved as a draft.
 */
export default function PaymentModal({ total, methods, initialMethod, requireProof = true,
  busy = false, onIssue, onDraft, onClose, title = 'الدفع' }) {
  const [lines, setLines] = useState(() => [newLine(initialMethod || methods[0], total)]);
  const fileRefs = useRef({});

  const calc = useMemo(() => {
    const amt = (l) => r2(parseFloat(l.amount));
    const cash = r2(lines.filter((l) => l.method === 'cash').reduce((s, l) => s + amt(l), 0));
    const nonCash = r2(lines.filter((l) => l.method !== 'cash').reduce((s, l) => s + amt(l), 0));
    const paid = r2(cash + nonCash);
    const remaining = r2(Math.max(total - paid, 0));
    const change = r2(Math.max(paid - total, 0));
    const errors = [];
    if (lines.some((l) => !(amt(l) > 0))) errors.push('أدخل مبلغ كل طريقة دفع');
    if (nonCash > total + 0.001) errors.push('الشبكة والتحويل لا يتجاوزان المتبقي — الزيادة نقداً فقط');
    if (lines.some((l) => l.method === 'card' && !l.card_ref.trim())) errors.push('أدخل رمز عملية الشبكة');
    if (cash > 0 && nonCash >= total) errors.push('لا حاجة للنقد — المبلغ مغطى');
    const missingProof = requireProof && lines.some((l) => l.method === 'transfer' && !l.proof);
    return { paid, remaining, change, errors, missingProof, cash };
  }, [lines, total, requireProof]);

  const canIssue = calc.remaining === 0 && calc.errors.length === 0 && !calc.missingProof;
  const canDraft = calc.remaining === 0 && calc.errors.length === 0 && calc.missingProof;

  const add = (method) => setLines((ls) => [...ls, newLine(method, calc.remaining)]);
  const update = (key, patch) => setLines((ls) => ls.map((l) => (l.key === key ? { ...l, ...patch } : l)));
  // Removing a tender gives what it covered to the first empty line (or the only line left).
  const remove = (key) => setLines((ls) => {
    if (ls.length <= 1) return ls;
    const rest = ls.filter((l) => l.key !== key);
    const covered = r2(rest.reduce((s, l) => s + (parseFloat(l.amount) || 0), 0));
    const left = r2(Math.max(total - covered, 0));
    if (left > 0) {
      const i = rest.findIndex((l) => !(parseFloat(l.amount) > 0));
      const j = i >= 0 ? i : (rest.length === 1 ? 0 : -1);
      if (j >= 0) rest[j] = { ...rest[j], amount: (r2(parseFloat(rest[j].amount) || 0) + left).toFixed(2) };
    }
    return rest;
  });

  const attach = async (key, file) => {
    const p = await uploadProof(file);
    if (p) update(key, { proof: { id: p.id, name: p.original_name || 'إثبات' } });
  };

  const payload = () => lines.map((l) => ({
    method: l.method,
    amount: r2(parseFloat(l.amount)),
    card_ref: l.method === 'card' ? l.card_ref.trim() : null,
    proof_id: l.method === 'transfer' && l.proof ? l.proof.id : null,
  }));

  useEffect(() => {
    const onKey = (e) => {
      if (e.key === 'Escape') onClose();
      if (e.key === 'Enter' && canIssue && !busy && e.target.tagName !== 'BUTTON') onIssue(payload());
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  });

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
      <div className="bg-white rounded-2xl w-full max-w-lg max-h-[92vh] flex flex-col">
        <div className="p-5 border-b flex items-center justify-between">
          <h2 className="text-xl font-bold text-gray-800">{title}</h2>
          <span className="text-2xl font-bold text-bayan-green">{total.toFixed(2)} <SarIcon size={18} /></span>
        </div>

        <div className="p-5 space-y-3 overflow-auto flex-1">
          {lines.map((l) => {
            const M = METHOD_META[l.method];
            return (
              <div key={l.key} className="border rounded-xl p-3 space-y-2">
                <div className="flex items-center gap-2">
                  <M.icon className="text-xl text-gray-500" />
                  <span className="font-medium text-gray-700 w-24">{M.label}</span>
                  <input
                    type="number" step="0.01" min="0" autoFocus={lines.length === 1}
                    value={l.amount}
                    onChange={(e) => update(l.key, { amount: e.target.value })}
                    placeholder={l.method === 'cash' ? 'المبلغ المستلم' : 'المبلغ'}
                    className="flex-1 px-3 py-2 rounded-lg border border-gray-300 focus:ring-2 focus:ring-bayan-green outline-none text-center text-lg"
                  />
                  {lines.length > 1 && (
                    <button onClick={() => remove(l.key)} className="p-2 text-red-500 hover:bg-red-50 rounded-lg" title="حذف">
                      <HiOutlineTrash />
                    </button>
                  )}
                </div>
                {l.method === 'card' && (
                  <input
                    type="text" dir="ltr" value={l.card_ref}
                    onChange={(e) => update(l.key, { card_ref: e.target.value })}
                    placeholder="رمز العملية (من جهاز الشبكة) *"
                    className="w-full px-3 py-2 rounded-lg border border-gray-300 focus:ring-2 focus:ring-bayan-green outline-none text-center"
                  />
                )}
                {l.method === 'transfer' && (
                  <div className="flex items-center gap-2">
                    {l.proof ? (
                      <>
                        <HiOutlineCheckCircle className="text-green-600 text-xl" />
                        <button onClick={() => openProof(l.proof.id)} className="text-sm text-green-700 hover:underline truncate">
                          {l.proof.name}
                        </button>
                        <button onClick={() => update(l.key, { proof: null })} className="text-xs text-gray-400 hover:text-red-500 mr-auto">تغيير</button>
                      </>
                    ) : (
                      <>
                        <button
                          onClick={() => fileRefs.current[l.key]?.click()}
                          className="flex items-center gap-2 px-3 py-2 rounded-lg border-2 border-dashed border-amber-400 text-amber-700 hover:bg-amber-50 text-sm"
                        >
                          <HiOutlinePaperClip /> إرفاق إثبات التحويل {requireProof ? '*' : '(اختياري)'}
                        </button>
                        <span className="text-xs text-gray-400">صورة أو PDF حتى 5MB</span>
                      </>
                    )}
                    <input
                      ref={(el) => { fileRefs.current[l.key] = el; }}
                      type="file" accept="image/jpeg,image/png,image/webp,application/pdf" className="hidden"
                      onChange={(e) => { attach(l.key, e.target.files?.[0]); e.target.value = ''; }}
                    />
                  </div>
                )}
              </div>
            );
          })}

          {/* add another tender */}
          <div className="flex gap-2">
            {methods.map((m) => {
              const M = METHOD_META[m];
              return (
                <button key={m} onClick={() => add(m)}
                  className="flex-1 flex items-center justify-center gap-1 py-2 rounded-lg border border-gray-200 text-gray-600 hover:border-bayan-green hover:text-bayan-green text-sm">
                  + <M.icon /> {M.label}
                </button>
              );
            })}
          </div>

          <div className="bg-gray-50 rounded-xl p-3 space-y-1 text-sm">
            <div className="flex justify-between"><span>المدفوع</span><span>{calc.paid.toFixed(2)}</span></div>
            <div className={`flex justify-between font-bold ${calc.remaining > 0 ? 'text-red-600' : 'text-gray-700'}`}>
              <span>المتبقي</span><span>{calc.remaining.toFixed(2)}</span>
            </div>
            {calc.change > 0 && (
              <div className="flex justify-between font-bold text-emerald-600 text-lg">
                <span>الباقي للعميل</span><span>{calc.change.toFixed(2)} <SarIcon size={14} /></span>
              </div>
            )}
          </div>

          {calc.errors.length > 0 && (
            <ul className="text-xs text-red-600 space-y-0.5">{calc.errors.map((e) => <li key={e}>• {e}</li>)}</ul>
          )}
          {canDraft && (
            <div className="text-xs text-amber-800 bg-amber-50 border border-amber-200 rounded-lg p-3 leading-relaxed">
              لم يُرفق إثبات التحويل. يمكن حفظ العملية <b>كمسودة بلا رقم فاتورة</b> مع حجز الأصناف، ثم إصدارها عند إرفاق الإثبات.
              <br />
              <b>تنبيه:</b> إذا استلم العميل البضاعة يجب إصدار الفاتورة الآن. المسودة لمن تبقى بضاعته في المحل حتى تأكيد التحويل، وتُلغى تلقائياً بنهاية اليوم.
            </div>
          )}
        </div>

        <div className="p-4 border-t flex gap-3">
          <button
            onClick={() => onIssue(payload())}
            disabled={!canIssue || busy}
            className="flex-1 bg-bayan-green hover:bg-bayan-dark text-white font-bold py-3 rounded-xl transition-all disabled:opacity-40 disabled:cursor-not-allowed"
          >
            {busy ? 'جاري الإصدار...' : 'إصدار الفاتورة'}
          </button>
          {canDraft && onDraft && (
            <button
              onClick={() => onDraft(payload())}
              disabled={busy}
              className="flex items-center gap-1 px-4 py-3 bg-amber-500 hover:bg-amber-600 text-white rounded-xl font-medium disabled:opacity-40"
            >
              <HiOutlineClock /> حفظ كمسودة
            </button>
          )}
          <button onClick={onClose} className="px-5 py-3 bg-gray-100 hover:bg-gray-200 text-gray-700 rounded-xl">إلغاء</button>
        </div>
      </div>
    </div>
  );
}
