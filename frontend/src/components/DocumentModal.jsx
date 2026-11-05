import { useEffect, useRef, useState } from 'react';
import toast from 'react-hot-toast';
import { HiOutlinePrinter, HiOutlineDocumentDownload, HiOutlineMail, HiOutlinePaperClip } from 'react-icons/hi';
import Receipt from './Receipt';
import { printReceipt } from '../utils/printReceipt';
import { downloadPDF, shareViaWhatsApp, shareViaEmail, pdfToBase64, senderName } from '../utils/generatePDF';
import { deliveryAPI, apiError } from '../services/api';
import { openProof } from '../utils/proofs';

const WhatsAppIcon = () => (
  <svg viewBox="0 0 24 24" fill="currentColor" className="w-5 h-5">
    <path d="M17.472 14.382c-.297-.149-1.758-.867-2.03-.967-.273-.099-.471-.148-.67.15-.197.297-.767.966-.94 1.164-.173.199-.347.223-.644.075-.297-.15-1.255-.463-2.39-1.475-.883-.788-1.48-1.761-1.653-2.059-.173-.297-.018-.458.13-.606.134-.133.298-.347.446-.52.149-.174.198-.298.298-.497.099-.198.05-.371-.025-.52-.075-.149-.669-1.612-.916-2.207-.242-.579-.487-.5-.669-.51-.173-.008-.371-.01-.57-.01-.198 0-.52.074-.792.372-.272.297-1.04 1.016-1.04 2.479 0 1.462 1.065 2.875 1.213 3.074.149.198 2.096 3.2 5.077 4.487.709.306 1.262.489 1.694.625.712.227 1.36.195 1.871.118.571-.085 1.758-.719 2.006-1.413.248-.694.248-1.289.173-1.413-.074-.124-.272-.198-.57-.347m-5.421 7.403h-.004a9.87 9.87 0 01-5.031-1.378l-.361-.214-3.741.982.998-3.648-.235-.374a9.86 9.86 0 01-1.51-5.26c.001-5.45 4.436-9.884 9.888-9.884 2.64 0 5.122 1.03 6.988 2.898a9.825 9.825 0 012.893 6.994c-.003 5.45-4.437 9.884-9.885 9.884m8.413-18.297A11.815 11.815 0 0012.05 0C5.495 0 .16 5.335.157 11.892c0 2.096.547 4.142 1.588 5.945L.057 24l6.305-1.654a11.882 11.882 0 005.683 1.448h.005c6.554 0 11.89-5.335 11.893-11.893a11.821 11.821 0 00-3.48-8.413z" />
  </svg>
);

const TITLES = { sale: 'فاتورة', credit_note: 'إشعار_دائن', donation: 'إيصال_تبرع' };

function docNumber(type, doc) {
  if (!doc) return '';
  if (type === 'sale') return doc.invoice_number;
  if (type === 'credit_note') return doc.credit_note_number;
  return doc.receipt_number;
}

/**
 * One window for every issued document — invoice, credit note, donation receipt —
 * so they all offer the same actions: print, PDF, WhatsApp, email (+ transfer proof).
 */
export default function DocumentModal({ type = 'sale', doc, onClose, phone = '', email = '' }) {
  const ref = useRef(null);
  const [emailServer, setEmailServer] = useState(false);
  useEffect(() => {
    deliveryAPI.status().then(({ data }) => setEmailServer(!!data.email_enabled)).catch(() => {});
  }, []);
  if (!doc) return null;

  const number = docNumber(type, doc);
  const filename = `${TITLES[type]}_${number}`;
  const proofIds = type === 'sale'
    ? (doc.payments || []).map((p) => p.proof_id).filter(Boolean)
    : (doc.proof_id ? [doc.proof_id] : []);

  const run = async (label, fn) => {
    if (!ref.current) return;
    try {
      toast.loading(label);
      await fn();
      toast.dismiss();
    } catch (err) {
      toast.dismiss();
      toast.error(apiError(err, 'تعذّرت العملية'));
    }
  };

  const onPDF = () => run('جاري إنشاء PDF...', async () => {
    await downloadPDF(ref.current, filename);
    toast.success('تم تحميل PDF');
  });

  const onWhatsApp = () => run('جاري تجهيز المستند...', async () => {
    const intl = (phone || '').replace(/\D/g, '');
    await shareViaWhatsApp(ref.current, filename, intl, `${filename.replace(/_/g, ' ')} — ${senderName()}\nالملف المرفق بصيغة PDF.`);
    toast.success('تم تحميل PDF — أرفقه في محادثة واتساب');
  });

  const onEmail = async () => {
    if (!emailServer) {
      await run('جاري تجهيز المستند...', () => shareViaEmail(ref.current, filename, email));
      return;
    }
    const to = window.prompt('البريد الإلكتروني:', email || '');
    if (!to) return;
    await run('جاري الإرسال...', async () => {
      const pdf_base64 = await pdfToBase64(ref.current, filename);
      await deliveryAPI.sendEmail({ to, filename: `${filename}.pdf`, pdf_base64,
        subject: `${filename.replace(/_/g, ' ')} — ${senderName()}` });
      toast.success('تم الإرسال بالبريد');
    });
  };

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
      <div className="bg-white rounded-2xl w-full max-w-md max-h-[92vh] flex flex-col">
        <div className="overflow-auto flex-1">
          <div ref={ref}>
            <Receipt
              type={type}
              sale={type === 'sale' ? doc : null}
              creditNote={type === 'credit_note' ? doc : null}
              donation={type === 'donation' ? doc : null}
            />
          </div>
        </div>
        <div className="p-4 border-t no-print space-y-3">
          <div className="flex gap-3">
            <button onClick={() => printReceipt(ref)}
              className="flex-1 flex items-center justify-center gap-2 bg-bayan-green hover:bg-bayan-dark text-white font-bold py-3 rounded-xl transition-all">
              <HiOutlinePrinter /> طباعة
            </button>
            <button onClick={onPDF}
              className="flex-1 flex items-center justify-center gap-2 bg-blue-600 hover:bg-blue-700 text-white font-bold py-3 rounded-xl transition-all">
              <HiOutlineDocumentDownload /> PDF
            </button>
          </div>
          <div className="flex gap-3">
            <button onClick={onWhatsApp}
              className="flex-1 flex items-center justify-center gap-2 bg-green-500 hover:bg-green-600 text-white font-medium py-2.5 rounded-xl transition-all">
              <WhatsAppIcon /> واتساب
            </button>
            <button onClick={onEmail}
              className="flex-1 flex items-center justify-center gap-2 bg-orange-500 hover:bg-orange-600 text-white font-medium py-2.5 rounded-xl transition-all">
              <HiOutlineMail className="text-xl" /> إيميل
            </button>
            <button onClick={onClose}
              className="px-6 py-2.5 bg-gray-100 hover:bg-gray-200 text-gray-700 rounded-xl transition-all">
              إغلاق
            </button>
          </div>
          {proofIds.length > 0 && (
            <div className="flex flex-wrap gap-2">
              {proofIds.map((id, i) => (
                <button key={id} onClick={() => openProof(id)}
                  className="flex items-center gap-1 text-sm text-bayan-green hover:underline">
                  <HiOutlinePaperClip /> إثبات التحويل{proofIds.length > 1 ? ` ${i + 1}` : ''}
                </button>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
