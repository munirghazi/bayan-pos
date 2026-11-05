import { useEffect, useRef, useState } from 'react';
import toast from 'react-hot-toast';
import { HiOutlineClock, HiOutlinePaperClip, HiOutlineX } from 'react-icons/hi';
import { draftsAPI, apiError } from '../services/api';
import { uploadProof } from '../utils/proofs';
import { fmtTime } from '../utils/datetime';
import { SarIcon } from './SarIcon';

const METHOD_AR = { cash: 'نقدي', card: 'شبكة', transfer: 'تحويل' };

/**
 * Open drafts (sale / donation waiting for a transfer proof).
 * "إرفاق الإثبات وإصدار" uploads the proof and issues the real document,
 * which only then gets its number. Drafts are cancelled automatically at day end.
 */
export default function DraftsModal({ onClose, onIssued, products = [] }) {
  const [rows, setRows] = useState([]);
  const [busy, setBusy] = useState(null);
  const fileRef = useRef(null);
  const target = useRef(null);

  const load = async () => {
    try { setRows((await draftsAPI.list()).data); } catch (e) { toast.error(apiError(e, 'تعذّر تحميل المسودات')); }
  };
  useEffect(() => { load(); }, []);

  const nameOf = (pid) => products.find((p) => p.id === pid)?.name || `#${pid}`;

  const pick = (d) => { target.current = d; fileRef.current?.click(); };

  const onFile = async (file) => {
    const d = target.current;
    if (!d || !file) return;
    const proof = await uploadProof(file);
    if (!proof) return;
    setBusy(d.id);
    try {
      let body;
      if (d.kind === 'sale') {
        let used = false;
        const payments = (d.payload.payments || []).map((p) => {
          if (p.method === 'transfer' && !p.proof_id && !used) { used = true; return { ...p, proof_id: proof.id }; }
          return p;
        });
        body = { payments };
      } else {
        body = { proof_id: proof.id };
      }
      const { data } = await draftsAPI.issue(d.id, body);
      toast.success(`تم الإصدار: ${data.draft.issued_ref}`);
      await load();
      onIssued?.(d.kind, d.kind === 'sale' ? data.sale : data.donation);
    } catch (e) {
      toast.error(apiError(e, 'تعذّر الإصدار'));
    } finally {
      setBusy(null);
    }
  };

  const cancel = async (d) => {
    const reason = window.prompt('سبب إلغاء المسودة (اختياري):', '');
    if (reason === null) return;
    try { await draftsAPI.cancel(d.id, reason); toast.success('أُلغيت المسودة وتحررت الأصناف'); load(); }
    catch (e) { toast.error(apiError(e, 'تعذّر الإلغاء')); }
  };

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
      <div className="bg-white rounded-2xl w-full max-w-2xl max-h-[90vh] flex flex-col">
        <div className="p-5 border-b flex items-center justify-between">
          <h2 className="text-xl font-bold text-gray-800 flex items-center gap-2">
            <HiOutlineClock className="text-amber-500" /> مسودات بانتظار إثبات التحويل
          </h2>
          <button onClick={onClose} className="p-2 hover:bg-gray-100 rounded-lg"><HiOutlineX /></button>
        </div>
        <div className="overflow-auto flex-1 divide-y">
          {rows.length === 0 && <p className="p-8 text-center text-gray-400">لا توجد مسودات مفتوحة</p>}
          {rows.map((d) => (
            <div key={d.id} className="p-4 flex items-center gap-4">
              <div className="flex-1 min-w-0">
                <p className="font-medium text-gray-800">
                  {d.kind === 'sale' ? 'بيع' : 'تبرع'} — {d.total.toFixed(2)} <SarIcon size={12} />
                  {d.customer_label && <span className="text-gray-500 text-sm"> · {d.customer_label}</span>}
                </p>
                <p className="text-xs text-gray-500 truncate">
                  {d.kind === 'sale'
                    ? (d.payload.items || []).map((i) => `${nameOf(i.product_id)} ×${i.quantity}`).join(' | ')
                    : (d.payload.note || '')}
                </p>
                <p className="text-xs text-gray-400">
                  {fmtTime(d.created_at)} · {d.user_name}
                  {d.kind === 'sale' && ' · ' + (d.payload.payments || []).map((p) => `${METHOD_AR[p.method]} ${Number(p.amount).toFixed(2)}`).join(' + ')}
                </p>
              </div>
              <button onClick={() => pick(d)} disabled={busy === d.id}
                className="flex items-center gap-1 px-3 py-2 bg-bayan-green hover:bg-bayan-dark text-white rounded-lg text-sm disabled:opacity-50">
                <HiOutlinePaperClip /> {busy === d.id ? 'جاري الإصدار...' : 'إرفاق الإثبات وإصدار'}
              </button>
              <button onClick={() => cancel(d)} className="px-3 py-2 text-red-600 hover:bg-red-50 rounded-lg text-sm">إلغاء</button>
            </div>
          ))}
        </div>
        <p className="p-3 text-xs text-gray-400 border-t">المسودة ليست فاتورة: لا رقم لها ولا تُخصم من المخزون، لكن أصنافها محجوزة. تُلغى تلقائياً بنهاية اليوم.</p>
        <input ref={fileRef} type="file" accept="image/jpeg,image/png,image/webp,application/pdf" className="hidden"
          onChange={(e) => { onFile(e.target.files?.[0]); e.target.value = ''; }} />
      </div>
    </div>
  );
}
