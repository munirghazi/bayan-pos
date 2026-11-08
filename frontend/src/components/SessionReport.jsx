import { useState } from 'react';
import toast from 'react-hot-toast';
import { HiOutlineDocumentDownload, HiOutlinePrinter } from 'react-icons/hi';
import { Modal, Button } from './ui';
import { SarIcon } from './SarIcon';
import { fmtDateTime } from '../utils/datetime';
import { buildReportPDF, downloadReportPDF, money, methodLabel, neg, ltr } from '../utils/reportPDF';

/*
 * One register session: everything sold, refunded and donated at this register
 * between two closings. `report` comes from /registers/{id}/sessions/current
 * (open session = X report) or /registers/{id}/sessions/{closingId} (Z report).
 */

export function sessionPdfDef(report) {
  const r = report;
  const sm = r.summary;
  const closed = r.status === 'closed';
  const title = closed ? 'تقرير جلسة الصندوق (Z)' : 'تقرير الجلسة الحالية (X) — غير مغلقة';
  const period = `من ${r.period_from ? fmtDateTime(r.period_from) : 'بداية التشغيل'} إلى ${fmtDateTime(r.period_to)}`;
  const meta = [
    ['الفرع', `${r.register.location_name || ''}${r.register.location_code ? ` (${r.register.location_code})` : ''}`],
    ['الصندوق', r.register.name],
  ];
  if (closed) meta.push(['أغلقه', r.closed_by || '—']);
  const summary = [
    { label: 'عدد الفواتير', value: sm.sales_count },
    { label: 'إجمالي المبيعات', value: money(sm.total_sales) },
    { label: 'نقدي', value: money(sm.by_method.cash) },
    { label: 'شبكة', value: money(sm.by_method.card) },
    { label: 'تحويل', value: money(sm.by_method.transfer) },
    { label: `إشعارات دائنة (${sm.credit_notes_count})`, value: neg(sm.credit_notes_total), color: '#dc2626' },
    { label: 'صافي المبيعات', value: money(sm.net_sales) },
    { label: 'ضريبة المبيعات', value: money(sm.vat) },
    { label: 'رصيد افتتاحي', value: money(sm.opening_float) },
    { label: 'مرتجعات نقدية', value: neg(sm.cash_refunds) },
    { label: 'النقد المتوقع', value: money(sm.expected_cash) },
  ];
  if (closed) {
    summary.push({ label: 'النقد المعدود', value: money(sm.counted_cash) });
    summary.push({ label: 'الفرق', value: ltr(`${sm.variance > 0 ? '+' : ''}${money(sm.variance)}`),
      color: sm.variance === 0 ? undefined : (sm.variance > 0 ? '#16a34a' : '#dc2626') });
  }
  if (sm.donations_count) summary.push({ label: `تبرعات (${sm.donations_count})`, value: money(sm.donations_total) });

  return {
    title, subtitle: period, meta, summary,
    sections: [
      {
        title: 'حسب الكاشير',
        columns: [
          { label: 'الكاشير', key: 'cashier' },
          { label: 'الفواتير', key: 'sales_count', align: 'left' },
          { label: 'نقدي', value: (x) => money(x.cash), align: 'left' },
          { label: 'شبكة', value: (x) => money(x.card), align: 'left' },
          { label: 'تحويل', value: (x) => money(x.transfer), align: 'left' },
          { label: 'الإجمالي', value: (x) => money(x.total), align: 'left' },
        ],
        rows: r.per_cashier,
      },
      {
        title: `الفواتير (${r.invoices.length})`, emptyText: 'لا توجد فواتير في هذه الجلسة',
        columns: [
          { label: 'رقم الفاتورة', key: 'invoice_number', align: 'left' },
          { label: 'الوقت', value: (x) => fmtDateTime(x.issued_at) },
          { label: 'العميل', value: (x) => x.customer_name || '—' },
          { label: 'الدفع', value: (x) => methodLabel(x.payment_method) },
          { label: 'الكاشير', key: 'cashier' },
          { label: 'المبلغ', value: (x) => money(x.total), align: 'left' },
        ],
        rows: r.invoices,
        footer: ['', '', '', '', 'الإجمالي', money(sm.total_sales)],
      },
      {
        title: `الإشعارات الدائنة (${r.credit_notes.length})`,
        columns: [
          { label: 'رقم الإشعار', key: 'credit_note_number', align: 'left' },
          { label: 'الفاتورة الأصلية', key: 'original_invoice_number', align: 'left' },
          { label: 'الاسترداد', value: (x) => methodLabel(x.refund_method) },
          { label: 'السبب', value: (x) => x.reason || '—' },
          { label: 'المبلغ', value: (x) => neg(x.total), align: 'left' },
        ],
        rows: r.credit_notes,
      },
      {
        title: `التبرعات (${r.donations.length})`,
        columns: [
          { label: 'رقم الإيصال', key: 'receipt_number', align: 'left' },
          { label: 'المتبرع', value: (x) => x.donor_name || 'مجهول' },
          { label: 'الدفع', value: (x) => methodLabel(x.payment_method) },
          { label: 'الحالة', value: (x) => (x.status === 'void' ? 'ملغى' : 'صادر') },
          { label: 'المبلغ', value: (x) => money(x.amount), align: 'left' },
        ],
        rows: r.donations,
      },
    ],
    notes: r.note ? `ملاحظة الإغلاق: ${r.note}` : null,
    filename: `جلسة_${r.register.name}_${(r.period_to || '').slice(0, 10)}`,
  };
}

export default function SessionReport({ report, onClose }) {
  const [busy, setBusy] = useState('');
  const r = report;
  const sm = r.summary;
  const closed = r.status === 'closed';

  const pdf = async () => {
    setBusy('pdf');
    try { await downloadReportPDF(sessionPdfDef(r)); } catch (e) { toast.error('تعذّر إنشاء ملف PDF'); } finally { setBusy(''); }
  };
  const print = async () => {
    setBusy('print');
    try {
      const doc = await buildReportPDF(sessionPdfDef(r));
      doc.autoPrint();
      window.open(doc.output('bloburl'), '_blank');
    } catch (e) { toast.error('تعذّرت الطباعة'); } finally { setBusy(''); }
  };

  const Stat = ({ label, value, tone }) => (
    <div className="rounded-lg bg-gray-50 p-2.5 text-center">
      <p className="text-[11px] text-gray-500">{label}</p>
      <p className={`font-bold ${tone || 'text-gray-800'}`}>{value}</p>
    </div>
  );

  return (
    <Modal size="xl" onClose={onClose}
      title={closed ? 'تقرير جلسة الصندوق (Z)' : 'تقرير الجلسة الحالية (X)'}
      footer={<>
        <Button variant="secondary" onClick={onClose}>إغلاق</Button>
        <Button variant="secondary" icon={<HiOutlinePrinter />} loading={busy === 'print'} onClick={print}>طباعة</Button>
        <Button icon={<HiOutlineDocumentDownload />} loading={busy === 'pdf'} onClick={pdf}>تصدير PDF</Button>
      </>}>
      <div className="space-y-4 text-sm">
        <div className="flex flex-wrap gap-x-6 gap-y-1 text-gray-600">
          <span><b>الصندوق:</b> {r.register.location_name} — {r.register.name}</span>
          <span><b>من:</b> {r.period_from ? fmtDateTime(r.period_from) : 'بداية التشغيل'}</span>
          <span><b>إلى:</b> {fmtDateTime(r.period_to)}</span>
          {closed && <span><b>أغلقه:</b> {r.closed_by}</span>}
          {!closed && <span className="text-amber-700 font-medium">الجلسة مفتوحة — هذا تقرير اطلاع ولا يُغلق الصندوق</span>}
        </div>

        <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
          <Stat label="عدد الفواتير" value={sm.sales_count} />
          <Stat label="إجمالي المبيعات" value={money(sm.total_sales)} />
          <Stat label="نقدي" value={money(sm.by_method.cash)} />
          <Stat label="شبكة + تحويل" value={money(sm.by_method.card + sm.by_method.transfer)} />
          <Stat label={`إشعارات دائنة (${sm.credit_notes_count})`} value={neg(sm.credit_notes_total)} tone="text-red-600" />
          <Stat label="صافي المبيعات" value={money(sm.net_sales)} />
          <Stat label="النقد المتوقع" value={money(sm.expected_cash)} />
          {closed
            ? <Stat label="الفرق" value={ltr(`${sm.variance > 0 ? '+' : ''}${money(sm.variance)}`)}
                tone={sm.variance === 0 ? 'text-gray-800' : (sm.variance > 0 ? 'text-green-600' : 'text-red-600')} />
            : <Stat label="تبرعات" value={money(sm.donations_total)} />}
        </div>

        {r.per_cashier.length > 0 && (
          <div>
            <h3 className="font-bold text-gray-800 mb-2">حسب الكاشير</h3>
            <div className="overflow-x-auto">
              <table className="w-full min-w-[480px]">
                <thead><tr className="text-gray-500 border-b text-right">
                  <th className="py-1.5">الكاشير</th><th>الفواتير</th><th>نقدي</th><th>شبكة</th><th>تحويل</th><th>الإجمالي</th>
                </tr></thead>
                <tbody>{r.per_cashier.map((c) => (
                  <tr key={c.cashier} className="border-b last:border-0">
                    <td className="py-1.5">{c.cashier}</td><td>{c.sales_count}</td><td>{money(c.cash)}</td>
                    <td>{money(c.card)}</td><td>{money(c.transfer)}</td><td className="font-bold">{money(c.total)}</td>
                  </tr>))}</tbody>
              </table>
            </div>
          </div>
        )}

        <div>
          <h3 className="font-bold text-gray-800 mb-2">الفواتير ({r.invoices.length})</h3>
          {r.invoices.length === 0 ? <p className="text-gray-400">لا توجد فواتير في هذه الجلسة.</p> : (
            <div className="overflow-x-auto max-h-72 overflow-y-auto border rounded-lg">
              <table className="w-full min-w-[560px]">
                <thead className="sticky top-0 bg-gray-50"><tr className="text-gray-500 text-right">
                  <th className="py-1.5 px-2">رقم الفاتورة</th><th>الوقت</th><th>العميل</th><th>الدفع</th><th>الكاشير</th><th className="px-2">المبلغ</th>
                </tr></thead>
                <tbody>{r.invoices.map((x) => (
                  <tr key={x.id} className="border-t">
                    <td className="py-1.5 px-2" dir="ltr">{x.invoice_number}</td>
                    <td>{fmtDateTime(x.issued_at)}</td><td>{x.customer_name || '—'}</td>
                    <td>{methodLabel(x.payment_method)}</td><td>{x.cashier}</td>
                    <td className="px-2 font-medium">{money(x.total)} <SarIcon size={12} /></td>
                  </tr>))}</tbody>
              </table>
            </div>
          )}
        </div>

        {r.credit_notes.length > 0 && (
          <div>
            <h3 className="font-bold text-gray-800 mb-2">الإشعارات الدائنة ({r.credit_notes.length})</h3>
            <table className="w-full">
              <tbody>{r.credit_notes.map((x) => (
                <tr key={x.id} className="border-b last:border-0">
                  <td className="py-1.5" dir="ltr">{x.credit_note_number}</td>
                  <td className="text-gray-500" dir="ltr">{x.original_invoice_number}</td>
                  <td>{methodLabel(x.refund_method)}</td><td>{x.reason || '—'}</td>
                  <td className="text-red-600 font-medium">{neg(x.total)}</td>
                </tr>))}</tbody>
            </table>
          </div>
        )}

        {r.donations.length > 0 && (
          <p className="text-gray-600">التبرعات في الجلسة: {sm.donations_count} إيصال بقيمة {money(sm.donations_total)} (تظهر كاملة في ملف PDF).</p>
        )}
        {r.note && <p className="text-gray-600"><b>ملاحظة الإغلاق:</b> {r.note}</p>}
      </div>
    </Modal>
  );
}
