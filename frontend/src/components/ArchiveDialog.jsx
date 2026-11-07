// Delete / archive with explicit consequences (tester: a product with invoices and
// stock was deleted with no warning and its stock disappeared).
// The server decides: permanent delete only without history; otherwise archive
// (hidden, kept, restorable); archive refused while stock is on hand / POs are open.
import { useEffect, useState } from 'react';
import toast from 'react-hot-toast';
import { HiOutlineArchive, HiOutlineTrash, HiOutlineExclamation } from 'react-icons/hi';
import { apiError } from '../services/api';
import { Button, Modal, Spinner } from './ui';

export default function ArchiveDialog({ title, name, loadUsage, onArchive, onDelete, onClose, onDone, noun = 'المنتج' }) {
  const [u, setU] = useState(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    loadUsage().then((r) => setU(r.data)).catch((e) => { toast.error(apiError(e, 'تعذّر التحقق')); onClose(); });
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const run = async (fn, okMsg) => {
    setBusy(true);
    try { const r = await fn(); toast.success(r?.data?.message || okMsg); onDone(); }
    catch (e) { toast.error(apiError(e, 'تعذّر التنفيذ')); } finally { setBusy(false); }
  };

  return (
    <Modal title={title} size="md" onClose={onClose}
      footer={!u ? null : (
        <>
          <Button variant="secondary" onClick={onClose}>إلغاء</Button>
          {u.deletable ? (
            <Button variant="danger" loading={busy} icon={<HiOutlineTrash />} onClick={() => run(onDelete, 'تم الحذف')}>حذف نهائي</Button>
          ) : u.archivable ? (
            <Button loading={busy} icon={<HiOutlineArchive />} onClick={() => run(onArchive, 'تمت الأرشفة')}>أرشفة</Button>
          ) : null}
        </>
      )}>
      {!u ? <div className="py-8 flex justify-center text-gray-400"><Spinner size={28} /></div> : (
        <div className="space-y-3 text-sm leading-7">
          <p className="font-semibold text-gray-800">«{name}»</p>
          {u.deletable ? (
            <p className="text-gray-600">لا توجد لهذا {noun} أي حركات أو رصيد، لذا يمكن حذفه نهائياً. <b>لا يمكن التراجع.</b></p>
          ) : (
            <>
              <div className="rounded-lg bg-gray-50 border p-3">
                <p className="text-gray-500 text-xs mb-1">لا يمكن حذفه لأن له سجلاً:</p>
                <p className="text-gray-800">{u.summary}</p>
              </div>
              {u.archivable ? (
                <p className="text-gray-600">
                  <b>الأرشفة</b> تخفيه من القوائم ونقطة البيع، مع بقاء كل فواتيره وحركاته كما هي في التقارير.
                  يمكن استعادته في أي وقت من «عرض المؤرشفة».
                </p>
              ) : (
                <div className="flex gap-2 rounded-lg bg-amber-50 border border-amber-200 text-amber-900 p-3">
                  <HiOutlineExclamation className="text-lg shrink-0 mt-1" />
                  <div>
                    <p className="font-semibold">لا يمكن أرشفته الآن:</p>
                    {u.archive_blockers.map((b) => <p key={b}>• {b}</p>)}
                  </div>
                </div>
              )}
            </>
          )}
        </div>
      )}
    </Modal>
  );
}
