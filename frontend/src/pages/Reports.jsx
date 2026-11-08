import { useState, useEffect, useRef } from 'react';
import { reportsAPI, salesAPI, returnsAPI, donationsAPI, apiError } from '../services/api';
import { getCapabilities } from '../utils/posSettings';
import { fmtDateTime } from '../utils/datetime';
import { openProof } from '../utils/proofs';
import { SarIcon, SAR_TEXT } from '../components/SarIcon';
import DocumentModal from '../components/DocumentModal';
import { printReceipt } from '../utils/printReceipt';
import { generatePDFBlob, downloadPDF } from '../utils/generatePDF';
import { downloadReportPDF, money, neg, ltr } from '../utils/reportPDF';
import toast from 'react-hot-toast';
import {
  HiOutlineChartBar,
  HiOutlineDocumentDownload,
  HiOutlineCalendar,
  HiOutlineChevronDown,
  HiOutlineChevronUp,
  HiOutlinePrinter,
  HiOutlineMail,
  HiOutlineChatAlt2,
  HiOutlineDownload,
} from 'react-icons/hi';

const paymentMethodAr = { cash: 'نقدي', card: 'شبكة', transfer: 'تحويل', mixed: 'متعدد' };
const riyadhToday = () => new Date().toLocaleDateString('en-CA', { timeZone: 'Asia/Riyadh' });

export default function Reports() {
  const caps = getCapabilities();
  const donationsOn = !!caps.donations_enabled;
  const salesOn = caps.sales_enabled !== false;
  const [activeTab, setActiveTab] = useState(salesOn || !donationsOn ? 'sales' : 'donations');
  const [startDate, setStartDate] = useState('');
  const [endDate, setEndDate] = useState('');
  const [salesData, setSalesData] = useState(null);
  const [donationsData, setDonationsData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [expandedSale, setExpandedSale] = useState(null);

  // Reprint state
  const [showReceipt, setShowReceipt] = useState(false);
  const [selectedSale, setSelectedSale] = useState(null);
  const [selectedDonation, setSelectedDonation] = useState(null);
  const receiptRef = useRef(null);

  useEffect(() => {
    // Default: today
    const today = riyadhToday();
    setStartDate(today);
    setEndDate(today);
  }, []);

  useEffect(() => {
    if (startDate && endDate) {
      loadReport();
    }
  }, [activeTab, startDate, endDate]);

  const loadReport = async () => {
    setLoading(true);
    try {
      if (activeTab === 'sales') {
        const res = await reportsAPI.getSalesReport(startDate, endDate);
        setSalesData(res.data);
      } else if (donationsOn) {
        const res = await reportsAPI.getDonationsReport(startDate, endDate);
        setDonationsData(res.data);
      }
    } catch (err) {
      toast.error('خطأ في تحميل التقرير');
    } finally {
      setLoading(false);
    }
  };

  const exportCSV = () => {
    let csv = '';
    let filename = '';

    if (activeTab === 'sales' && salesData) {
      csv = '\uFEFF'; // BOM for Arabic
      csv += `رقم الفاتورة,العميل,المنتجات,غير شامل الضريبة (${SAR_TEXT}),الضريبة (${SAR_TEXT}),الإجمالي (${SAR_TEXT}),طريقة الدفع,عدد المنتجات,الموظف,التاريخ\n`;
      salesData.sales.forEach((s) => {
        // Escape product summary for CSV (replace commas with semicolons)
        const productsSafe = (s.products_summary || '').replace(/,/g, '؛');
        csv += `${s.invoice_number},"${(s.customer_name || '').replace(/"/g, "'")}","${productsSafe}",${s.subtotal},${s.vat_amount},${s.total},${paymentMethodAr[s.payment_method]},${s.items_count},${s.user_name},"${fmtDateTime(s.issued_at)}"\n`;
      });

      // Add detailed items section
      csv += '\n\n--- تفاصيل المبيعات ---\n';
      csv += `رقم الفاتورة,اسم المنتج,الكمية,سعر الوحدة (${SAR_TEXT}),المجموع الفرعي (${SAR_TEXT})\n`;
      salesData.sales.forEach((s) => {
        if (s.items) {
          s.items.forEach((item) => {
            csv += `${s.invoice_number},${item.product_name},${item.quantity},${item.price},${item.subtotal}\n`;
          });
        }
      });

      if (salesData.credit_notes?.length) {
        csv += '\n\n--- الإشعارات الدائنة ---\n';
        csv += `رقم الإشعار,الفاتورة الأصلية,الضريبة (${SAR_TEXT}),المبلغ (${SAR_TEXT}),السبب,التاريخ\n`;
        salesData.credit_notes.forEach((r) => {
          csv += `${r.credit_note_number},${r.original_invoice_number},${r.vat_amount},${r.total},"${(r.reason || '').replace(/"/g, "'")}","${fmtDateTime(r.issued_at)}"\n`;
        });
      }
      const sm = salesData.summary;
      csv += `\n\nإجمالي المبيعات,${sm.total}\nضريبة المبيعات,${sm.vat_total}\nالإشعارات الدائنة,${sm.credit_notes_total}\nضريبة الإشعارات الدائنة,${sm.credit_notes_vat}\nصافي المبيعات,${sm.net_total}\nصافي الضريبة,${sm.net_vat}\n`;
      filename = `تقرير_المبيعات_${startDate}_${endDate}.csv`;
    } else if (donationsData) {
      csv = '\uFEFF';
      csv += `رقم الإيصال,المبلغ (${SAR_TEXT}),المتبرع,طريقة الدفع,الحالة,ملاحظة,الموظف,التاريخ\n`;
      donationsData.donations.forEach((d) => {
        const st = d.status === 'void' ? `ملغى: ${d.void_reason || ''}` : 'صادر';
        csv += `${d.receipt_number},${d.amount},${d.donor_name || 'مجهول'},${paymentMethodAr[d.payment_method]},"${st}",${d.note || '-'},${d.user_name},"${fmtDateTime(d.issued_at)}"\n`;
      });
      filename = `تقرير_التبرعات_${startDate}_${endDate}.csv`;
    }

    const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
    const link = document.createElement('a');
    link.href = URL.createObjectURL(blob);
    link.download = filename;
    link.click();
  };

  const [pdfBusy, setPdfBusy] = useState(false);
  const exportPDF = async () => {
    const period = startDate === endDate ? `يوم ${ltr(startDate)}` : `من ${ltr(startDate)} إلى ${ltr(endDate)}`;
    let def = null;
    if (activeTab === 'sales' && salesData) {
      const sm = salesData.summary;
      def = {
        title: 'تقرير المبيعات', subtitle: period,
        summary: [
          { label: 'إجمالي المبيعات', value: money(sm.total) },
          { label: 'عدد العمليات', value: sm.count },
          { label: 'نقدي', value: money(sm.cash_total) },
          { label: 'شبكة + تحويل', value: money((sm.card_total || 0) + (sm.transfer_total || 0)) },
          { label: 'ضريبة المبيعات', value: money(sm.vat_total) },
          { label: `الإشعارات الدائنة (${sm.credit_notes_count})`, value: neg(sm.credit_notes_total), color: '#dc2626' },
          { label: 'صافي المبيعات', value: money(sm.net_total) },
          { label: 'صافي الضريبة المستحقة', value: money(sm.net_vat) },
        ],
        sections: [
          {
            title: `الفواتير (${salesData.sales.length})`, emptyText: 'لا توجد مبيعات في هذه الفترة',
            columns: [
              { label: 'رقم الفاتورة', key: 'invoice_number', align: 'left' },
              { label: 'العميل', value: (r) => r.customer_name || '—' },
              { label: 'المنتجات', key: 'products_summary' },
              { label: 'الضريبة', value: (r) => money(r.vat_amount), align: 'left' },
              { label: 'المجموع', value: (r) => money(r.total), align: 'left' },
              { label: 'الدفع', value: (r) => paymentMethodAr[r.payment_method] || r.payment_method },
              { label: 'الموظف', key: 'user_name' },
              { label: 'التاريخ', value: (r) => fmtDateTime(r.issued_at) },
            ],
            rows: salesData.sales,
            footer: ['', '', 'الإجمالي', money(sm.vat_total), money(sm.total), '', '', ''],
          },
          {
            title: `الإشعارات الدائنة (${(salesData.credit_notes || []).length})`,
            columns: [
              { label: 'رقم الإشعار', key: 'credit_note_number', align: 'left' },
              { label: 'الفاتورة الأصلية', key: 'original_invoice_number', align: 'left' },
              { label: 'العميل', value: (r) => r.customer_name || '—' },
              { label: 'المبلغ المسترد', value: (r) => money(r.total), align: 'left' },
              { label: 'طريقة الاسترداد', value: (r) => paymentMethodAr[r.refund_method] || r.refund_method || '—' },
              { label: 'السبب', value: (r) => r.reason || '—' },
              { label: 'التاريخ', value: (r) => fmtDateTime(r.issued_at) },
            ],
            rows: salesData.credit_notes || [],
          },
        ],
        filename: `تقرير_المبيعات_${startDate}_${endDate}`,
      };
    } else if (activeTab === 'donations' && donationsData) {
      const sm = donationsData.summary;
      def = {
        title: 'تقرير التبرعات', subtitle: period,
        summary: [
          { label: 'إجمالي التبرعات', value: money(sm.total) },
          { label: 'عدد التبرعات', value: sm.count },
          { label: 'إيصالات ملغاة', value: sm.void_count },
          { label: 'شبكة + تحويل', value: money((sm.card_total || 0) + (sm.transfer_total || 0)) },
        ],
        sections: [{
          title: `الإيصالات (${donationsData.donations.length})`, emptyText: 'لا توجد تبرعات في هذه الفترة',
          columns: [
            { label: 'رقم الإيصال', key: 'receipt_number', align: 'left' },
            { label: 'المتبرع', value: (r) => r.donor_name || 'مجهول' },
            { label: 'المبلغ', value: (r) => money(r.amount), align: 'left' },
            { label: 'طريقة الدفع', value: (r) => paymentMethodAr[r.payment_method] || r.payment_method },
            { label: 'الحالة', value: (r) => (r.status === 'void' ? `ملغى: ${r.void_reason || ''}` : 'صادر') },
            { label: 'الموظف', key: 'user_name' },
            { label: 'التاريخ', value: (r) => fmtDateTime(r.issued_at) },
          ],
          rows: donationsData.donations,
        }],
        filename: `تقرير_التبرعات_${startDate}_${endDate}`,
      };
    }
    if (!def) return;
    setPdfBusy(true);
    try { await downloadReportPDF(def); } catch (e) { toast.error('تعذّر إنشاء ملف PDF'); } finally { setPdfBusy(false); }
  };

  const toggleExpandSale = (saleId) => {
    setExpandedSale(expandedSale === saleId ? null : saleId);
  };

  // ========== Reprint functions ==========

  // Reprints load the full stored document, so the copy is identical to the original.
  const handleReprintSale = async (sale, e) => {
    e.stopPropagation(); // Don't toggle expand
    try {
      const { data } = await salesAPI.get(sale.id);
      setSelectedSale(data);
      setSelectedDonation(null);
      setShowReceipt(true);
    } catch (err) {
      toast.error(apiError(err, 'تعذّر تحميل الفاتورة'));
    }
  };

  const handleReprintDonation = async (donation) => {
    try {
      const { data } = await donationsAPI.get(donation.id);
      setSelectedDonation(data);
      setSelectedSale(null);
      setShowReceipt(true);
    } catch (err) {
      toast.error(apiError(err, 'تعذّر تحميل الإيصال'));
    }
  };

  const [selectedCN, setSelectedCN] = useState(null);
  const openCreditNote = async (id) => {
    try {
      const { data } = await returnsAPI.get(id);
      setSelectedCN(data); setSelectedSale(null); setSelectedDonation(null); setShowReceipt(true);
    } catch (err) { toast.error(apiError(err, 'تعذّر تحميل الإشعار')); }
  };
  const openSaleById = async (saleId) => {
    try {
      const { data } = await salesAPI.get(saleId);
      setSelectedSale(data); setSelectedCN(null); setSelectedDonation(null); setShowReceipt(true);
    } catch (err) { toast.error(apiError(err, 'تعذّر تحميل الفاتورة')); }
  };

  const closeReceipt = () => {
    setShowReceipt(false);
    setSelectedSale(null);
    setSelectedDonation(null);
    setSelectedCN(null);
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-800">التقارير</h1>
          <p className="text-gray-500 mt-1">عرض وتصدير تقارير المبيعات والتبرعات</p>
        </div>
        <div className="flex gap-2">
          <button
            onClick={exportPDF} disabled={pdfBusy || loading}
            className="flex items-center gap-2 bg-red-600 hover:bg-red-700 disabled:opacity-60 text-white px-5 py-2 rounded-lg transition-all"
          >
            <HiOutlineDocumentDownload />
            {pdfBusy ? 'جاري الإنشاء…' : 'تصدير PDF'}
          </button>
          <button
            onClick={exportCSV}
            className="flex items-center gap-2 bg-bayan-green hover:bg-bayan-dark text-white px-5 py-2 rounded-lg transition-all"
          >
            <HiOutlineDocumentDownload />
            تصدير CSV
          </button>
        </div>
      </div>

      {/* Tabs + Filters */}
      <div className="bg-white rounded-xl shadow-sm border p-4">
        <div className="flex flex-wrap items-center gap-4">
          {/* Tabs */}
          <div className="flex bg-gray-100 rounded-lg p-1">
            {salesOn && <button
              onClick={() => setActiveTab('sales')}
              className={`px-6 py-2 rounded-lg font-medium transition-all ${
                activeTab === 'sales'
                  ? 'bg-bayan-green text-white shadow'
                  : 'text-gray-600 hover:text-gray-800'
              }`}
            >
              المبيعات
            </button>}
            {donationsOn && <button
              onClick={() => setActiveTab('donations')}
              className={`px-6 py-2 rounded-lg font-medium transition-all ${
                activeTab === 'donations'
                  ? 'bg-purple-600 text-white shadow'
                  : 'text-gray-600 hover:text-gray-800'
              }`}
            >
              التبرعات
            </button>}
          </div>

          {/* Date filters */}
          <div className="flex items-center gap-2 mr-auto">
            <HiOutlineCalendar className="text-gray-400" />
            <input
              type="date"
              value={startDate}
              onChange={(e) => setStartDate(e.target.value)}
              className="px-3 py-2 rounded-lg border border-gray-300 text-sm focus:ring-2 focus:ring-bayan-green outline-none"
            />
            <span className="text-gray-400">إلى</span>
            <input
              type="date"
              value={endDate}
              onChange={(e) => setEndDate(e.target.value)}
              className="px-3 py-2 rounded-lg border border-gray-300 text-sm focus:ring-2 focus:ring-bayan-green outline-none"
            />
          </div>
        </div>
      </div>

      {loading && (
        <div className="flex items-center justify-center py-12">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-bayan-green"></div>
        </div>
      )}

      {/* Sales Report */}
      {!loading && activeTab === 'sales' && salesData && (
        <>
          {/* Summary */}
          <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
            <div className="bg-white rounded-xl border p-4">
              <p className="text-sm text-gray-500">إجمالي المبيعات</p>
              <p className="text-2xl font-bold text-bayan-green">{salesData.summary.total.toFixed(2)} <SarIcon size={18} /></p>
            </div>
            <div className="bg-white rounded-xl border p-4">
              <p className="text-sm text-gray-500">عدد العمليات</p>
              <p className="text-2xl font-bold text-gray-800">{salesData.summary.count}</p>
            </div>
            <div className="bg-white rounded-xl border p-4">
              <p className="text-sm text-gray-500">نقدي</p>
              <p className="text-2xl font-bold text-emerald-600">{salesData.summary.cash_total.toFixed(2)} <SarIcon size={18} /></p>
            </div>
            <div className="bg-white rounded-xl border p-4">
              <p className="text-sm text-gray-500">شبكة + تحويل</p>
              <p className="text-2xl font-bold text-blue-600">
                {(salesData.summary.card_total + salesData.summary.transfer_total).toFixed(2)} <SarIcon size={18} />
              </p>
            </div>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
            <div className="bg-white rounded-xl border p-4">
              <p className="text-sm text-gray-500">ضريبة القيمة المضافة على المبيعات</p>
              <p className="text-xl font-bold text-gray-800">{salesData.summary.vat_total.toFixed(2)} <SarIcon size={16} /></p>
            </div>
            <div className="bg-white rounded-xl border p-4">
              <p className="text-sm text-gray-500">الإشعارات الدائنة ({salesData.summary.credit_notes_count})</p>
              <p className="text-xl font-bold text-red-600">-{salesData.summary.credit_notes_total.toFixed(2)} <SarIcon size={16} /></p>
              <p className="text-xs text-gray-400">منها ضريبة {salesData.summary.credit_notes_vat.toFixed(2)}</p>
            </div>
            <div className="bg-white rounded-xl border p-4">
              <p className="text-sm text-gray-500">صافي المبيعات</p>
              <p className="text-xl font-bold text-bayan-green">{salesData.summary.net_total.toFixed(2)} <SarIcon size={16} /></p>
            </div>
            <div className="bg-white rounded-xl border p-4">
              <p className="text-sm text-gray-500">صافي الضريبة المستحقة</p>
              <p className="text-xl font-bold text-gray-800">{salesData.summary.net_vat.toFixed(2)} <SarIcon size={16} /></p>
            </div>
          </div>

          {/* Sales table with expandable product details */}
          <div className="bg-white rounded-xl shadow-sm border overflow-hidden">
            <table className="w-full">
              <thead className="bg-gray-50">
                <tr>
                  <th className="text-right px-6 py-3 text-sm font-medium text-gray-500">رقم الفاتورة</th>
                  <th className="text-right px-4 py-3 text-sm font-medium text-gray-500">العميل</th>
                  <th className="text-right px-6 py-3 text-sm font-medium text-gray-500">المنتجات</th>
                  <th className="text-right px-6 py-3 text-sm font-medium text-gray-500">المجموع</th>
                  <th className="text-right px-6 py-3 text-sm font-medium text-gray-500">طريقة الدفع</th>
                  <th className="text-right px-6 py-3 text-sm font-medium text-gray-500">الموظف</th>
                  <th className="text-right px-6 py-3 text-sm font-medium text-gray-500">التاريخ</th>
                  <th className="px-6 py-3 text-sm font-medium text-gray-500">إعادة طباعة</th>
                  <th className="px-6 py-3 w-10"></th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {salesData.sales.map((sale) => (
                  <>
                    <tr key={sale.id} className="hover:bg-gray-50 cursor-pointer" onClick={() => toggleExpandSale(sale.id)}>
                      <td className="px-6 py-4 text-sm text-gray-600" dir="ltr">{sale.invoice_number}</td>
                      <td className="px-4 py-4 text-sm text-gray-700">
                        {sale.customer_name || <span className="text-gray-300">—</span>}
                        {sale.customer_phone && <div className="text-xs text-gray-400" dir="ltr">{sale.customer_phone}</div>}
                      </td>
                      <td className="px-6 py-4 text-sm text-gray-700 max-w-xs">
                        <div className="truncate" title={sale.products_summary}>
                          {sale.products_summary || `${sale.items_count} منتجات`}
                        </div>
                      </td>
                      <td className="px-6 py-4 font-bold text-bayan-green">{sale.total.toFixed(2)} <SarIcon size={13} /></td>
                      <td className="px-6 py-4 text-sm text-gray-600">{paymentMethodAr[sale.payment_method]}</td>
                      <td className="px-6 py-4 text-sm text-gray-600">{sale.user_name}</td>
                      <td className="px-6 py-4 text-sm text-gray-600">
                        {fmtDateTime(sale.issued_at)}
                      </td>
                      <td className="px-6 py-4 text-center">
                        <button
                          onClick={(e) => handleReprintSale(sale, e)}
                          className="p-2 text-bayan-green hover:bg-bayan-light rounded-lg transition-all"
                          title="إعادة طباعة الفاتورة"
                        >
                          <HiOutlinePrinter className="text-lg" />
                        </button>
                      </td>
                      <td className="px-6 py-4">
                        {expandedSale === sale.id ? (
                          <HiOutlineChevronUp className="text-gray-400" />
                        ) : (
                          <HiOutlineChevronDown className="text-gray-400" />
                        )}
                      </td>
                    </tr>
                    {/* Expanded details row */}
                    {expandedSale === sale.id && sale.items && (
                      <tr key={`${sale.id}-details`}>
                        <td colSpan="9" className="px-6 py-3 bg-gray-50">
                          <div className="mr-8">
                            <table className="w-full text-sm">
                              <thead>
                                <tr className="text-gray-500 border-b border-gray-200">
                                  <th className="text-right py-2 font-medium">المنتج</th>
                                  <th className="text-center py-2 font-medium">الكمية</th>
                                  <th className="text-center py-2 font-medium">سعر الوحدة</th>
                                  <th className="text-left py-2 font-medium">المجموع الفرعي</th>
                                </tr>
                              </thead>
                              <tbody>
                                {sale.items.map((item, idx) => (
                                  <tr key={idx} className="border-b border-gray-100">
                                    <td className="py-2 text-gray-700 font-medium">{item.product_name}</td>
                                    <td className="text-center py-2 text-gray-600">{item.quantity}</td>
                                    <td className="text-center py-2 text-gray-600">{item.price.toFixed(2)} <SarIcon size={11} /></td>
                                    <td className="text-left py-2 font-bold text-bayan-green">{item.subtotal.toFixed(2)} <SarIcon size={11} /></td>
                                  </tr>
                                ))}
                              </tbody>
                            </table>
                            <div className="flex flex-wrap gap-4 mt-2 text-xs text-gray-600">
                              {(sale.payments || []).map((p, i) => (
                                <span key={i}>
                                  {paymentMethodAr[p.method]}: {p.amount.toFixed(2)}
                                  {p.card_ref && <span dir="ltr"> ({p.card_ref})</span>}
                                  {p.proof_id && (
                                    <button onClick={(e) => { e.stopPropagation(); openProof(p.proof_id); }}
                                      className="mr-1 text-bayan-green hover:underline">📎 الإثبات</button>
                                  )}
                                </span>
                              ))}
                              {sale.change_given > 0 && <span>الباقي: {sale.change_given.toFixed(2)}</span>}
                            </div>
                          </div>
                        </td>
                      </tr>
                    )}
                  </>
                ))}
              </tbody>
            </table>
            {salesData.sales.length === 0 && (
              <p className="text-center py-12 text-gray-400">لا توجد مبيعات في هذه الفترة</p>
            )}
          </div>

          {/* Credit notes: each opens, and so does its original invoice */}
          {salesData.credit_notes?.length > 0 && (
            <div className="bg-white rounded-xl shadow-sm border overflow-hidden">
              <div className="px-6 py-3 border-b font-bold text-gray-800">الإشعارات الدائنة ({salesData.credit_notes.length})</div>
              <div className="overflow-x-auto">
                <table className="w-full">
                  <thead className="bg-gray-50">
                    <tr>
                      <th className="text-right px-6 py-3 text-sm font-medium text-gray-500">رقم الإشعار</th>
                      <th className="text-right px-4 py-3 text-sm font-medium text-gray-500">الفاتورة الأصلية</th>
                      <th className="text-right px-4 py-3 text-sm font-medium text-gray-500">العميل</th>
                      <th className="text-right px-4 py-3 text-sm font-medium text-gray-500">المبلغ المسترد</th>
                      <th className="text-right px-4 py-3 text-sm font-medium text-gray-500">طريقة الاسترداد</th>
                      <th className="text-right px-4 py-3 text-sm font-medium text-gray-500">السبب</th>
                      <th className="text-right px-4 py-3 text-sm font-medium text-gray-500">التاريخ</th>
                      <th className="px-4 py-3 text-sm font-medium text-gray-500">عرض</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-100">
                    {salesData.credit_notes.map((cn) => (
                      <tr key={cn.id} className="hover:bg-gray-50">
                        <td className="px-6 py-3 text-sm text-gray-700" dir="ltr">
                          <button onClick={() => openCreditNote(cn.id)} className="text-red-600 hover:underline font-medium">{cn.credit_note_number}</button>
                        </td>
                        <td className="px-4 py-3 text-sm" dir="ltr">
                          {cn.sale_id
                            ? <button onClick={() => openSaleById(cn.sale_id)} className="text-bayan-green hover:underline">{cn.original_invoice_number}</button>
                            : cn.original_invoice_number}
                        </td>
                        <td className="px-4 py-3 text-sm text-gray-700">{cn.customer_name || <span className="text-gray-300">—</span>}</td>
                        <td className="px-4 py-3 font-bold text-red-600">-{cn.total.toFixed(2)} <SarIcon size={13} /></td>
                        <td className="px-4 py-3 text-sm text-gray-600">{paymentMethodAr[cn.refund_method] || '—'}</td>
                        <td className="px-4 py-3 text-sm text-gray-600 max-w-xs truncate" title={cn.reason || ''}>{cn.reason || '—'}</td>
                        <td className="px-4 py-3 text-sm text-gray-600">{fmtDateTime(cn.issued_at)}</td>
                        <td className="px-4 py-3 text-center">
                          <button onClick={() => openCreditNote(cn.id)} className="p-2 text-red-600 hover:bg-red-50 rounded-lg" title="عرض / طباعة الإشعار">
                            <HiOutlinePrinter className="text-lg" />
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </>
      )}

      {/* Donations Report */}
      {!loading && donationsOn && activeTab === 'donations' && donationsData && (
        <>
          {/* Summary */}
          <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
            <div className="bg-white rounded-xl border p-4">
              <p className="text-sm text-gray-500">إجمالي التبرعات</p>
              <p className="text-2xl font-bold text-purple-600">{donationsData.summary.total.toFixed(2)} <SarIcon size={18} /></p>
            </div>
            <div className="bg-white rounded-xl border p-4">
              <p className="text-sm text-gray-500">عدد التبرعات</p>
              <p className="text-2xl font-bold text-gray-800">{donationsData.summary.count}</p>
            </div>
            <div className="bg-white rounded-xl border p-4">
              <p className="text-sm text-gray-500">إيصالات ملغاة</p>
              <p className="text-2xl font-bold text-red-600">{donationsData.summary.void_count}</p>
            </div>
            <div className="bg-white rounded-xl border p-4">
              <p className="text-sm text-gray-500">شبكة + تحويل</p>
              <p className="text-2xl font-bold text-blue-600">
                {(donationsData.summary.card_total + donationsData.summary.transfer_total).toFixed(2)} <SarIcon size={18} />
              </p>
            </div>
          </div>

          {/* Donations table */}
          <div className="bg-white rounded-xl shadow-sm border overflow-hidden">
            <table className="w-full">
              <thead className="bg-gray-50">
                <tr>
                  <th className="text-right px-6 py-3 text-sm font-medium text-gray-500">رقم الإيصال</th>
                  <th className="text-right px-6 py-3 text-sm font-medium text-gray-500">المتبرع</th>
                  <th className="text-right px-6 py-3 text-sm font-medium text-gray-500">المبلغ</th>
                  <th className="text-right px-6 py-3 text-sm font-medium text-gray-500">طريقة الدفع</th>
                  <th className="text-right px-6 py-3 text-sm font-medium text-gray-500">ملاحظة</th>
                  <th className="text-right px-6 py-3 text-sm font-medium text-gray-500">الموظف</th>
                  <th className="text-right px-6 py-3 text-sm font-medium text-gray-500">التاريخ</th>
                  <th className="px-6 py-3 text-sm font-medium text-gray-500">إعادة طباعة</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-100">
                {donationsData.donations.map((d) => (
                  <tr key={d.id} className={`hover:bg-gray-50 ${d.status === 'void' ? 'opacity-60' : ''}`}>
                    <td className="px-6 py-4 text-sm text-gray-600">
                      <span dir="ltr">{d.receipt_number}</span>
                      {d.status === 'void' && (
                        <span className="mr-2 text-xs text-red-600 font-bold" title={d.void_reason || ''}>ملغى</span>
                      )}
                    </td>
                    <td className="px-6 py-4 font-medium">{d.donor_name || 'مجهول'}</td>
                    <td className="px-6 py-4 font-bold text-purple-600">{d.amount.toFixed(2)} <SarIcon size={13} /></td>
                    <td className="px-6 py-4 text-sm text-gray-600">{paymentMethodAr[d.payment_method]}</td>
                    <td className="px-6 py-4 text-sm text-gray-600">{d.note || '-'}</td>
                    <td className="px-6 py-4 text-sm text-gray-600">{d.user_name}</td>
                    <td className="px-6 py-4 text-sm text-gray-600">
                      {fmtDateTime(d.issued_at)}
                    </td>
                    <td className="px-6 py-4 text-center">
                      <button
                        onClick={() => handleReprintDonation(d)}
                        className="p-2 text-purple-600 hover:bg-purple-50 rounded-lg transition-all"
                        title="إعادة طباعة إيصال التبرع"
                      >
                        <HiOutlinePrinter className="text-lg" />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {donationsData.donations.length === 0 && (
              <p className="text-center py-12 text-gray-400">لا توجد تبرعات في هذه الفترة</p>
            )}
          </div>
        </>
      )}

      {/* ========== Reprint: same document window as everywhere ========== */}
      {showReceipt && (selectedSale || selectedDonation || selectedCN) && (
        <DocumentModal
          type={selectedDonation ? 'donation' : selectedCN ? 'credit_note' : 'sale'}
          doc={selectedDonation || selectedCN || selectedSale}
          phone={(selectedSale || selectedCN)?.customer_phone || ''}
          onClose={closeReceipt}
        />
      )}
    </div>
  );
}
