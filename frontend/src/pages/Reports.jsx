import { useState, useEffect, useRef } from 'react';
import { reportsAPI } from '../services/api';
import { SarIcon, SAR_TEXT } from '../components/SarIcon';
import Receipt from '../components/Receipt';
import { printReceipt } from '../utils/printReceipt';
import { generatePDFBlob, downloadPDF } from '../utils/generatePDF';
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

const paymentMethodAr = { cash: 'نقدي', card: 'شبكة', transfer: 'تحويل' };

export default function Reports() {
  const [activeTab, setActiveTab] = useState('sales');
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
    const today = new Date().toISOString().split('T')[0];
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
      } else {
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
      csv += `رقم الفاتورة,المنتجات,المجموع (${SAR_TEXT}),طريقة الدفع,عدد المنتجات,الموظف,التاريخ\n`;
      salesData.sales.forEach((s) => {
        // Escape product summary for CSV (replace commas with semicolons)
        const productsSafe = (s.products_summary || '').replace(/,/g, '؛');
        csv += `${s.id},"${productsSafe}",${s.total},${paymentMethodAr[s.payment_method]},${s.items_count},${s.user_name},${new Date(s.created_at).toLocaleDateString('ar-SA')}\n`;
      });

      // Add detailed items section
      csv += '\n\n--- تفاصيل المبيعات ---\n';
      csv += `رقم الفاتورة,اسم المنتج,الكمية,سعر الوحدة (${SAR_TEXT}),المجموع الفرعي (${SAR_TEXT})\n`;
      salesData.sales.forEach((s) => {
        if (s.items) {
          s.items.forEach((item) => {
            csv += `${s.id},${item.product_name},${item.quantity},${item.price},${item.subtotal}\n`;
          });
        }
      });

      filename = `تقرير_المبيعات_${startDate}_${endDate}.csv`;
    } else if (donationsData) {
      csv = '\uFEFF';
      csv += `رقم التبرع,المبلغ (${SAR_TEXT}),المتبرع,طريقة الدفع,ملاحظة,الموظف,التاريخ\n`;
      donationsData.donations.forEach((d) => {
        csv += `${d.id},${d.amount},${d.donor_name || 'مجهول'},${paymentMethodAr[d.payment_method]},${d.note || '-'},${d.user_name},${new Date(d.created_at).toLocaleDateString('ar-SA')}\n`;
      });
      filename = `تقرير_التبرعات_${startDate}_${endDate}.csv`;
    }

    const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
    const link = document.createElement('a');
    link.href = URL.createObjectURL(blob);
    link.download = filename;
    link.click();
  };

  const toggleExpandSale = (saleId) => {
    setExpandedSale(expandedSale === saleId ? null : saleId);
  };

  // ========== Reprint functions ==========

  const handleReprintSale = (sale, e) => {
    e.stopPropagation(); // Don't toggle expand
    setSelectedSale(sale);
    setSelectedDonation(null);
    setShowReceipt(true);
  };

  const handleReprintDonation = (donation) => {
    setSelectedDonation(donation);
    setSelectedSale(null);
    setShowReceipt(true);
  };

  const handlePrint = () => {
    printReceipt(receiptRef);
  };

  const handleShare = async (method) => {
    if (!receiptRef.current) {
      toast.error('لا يوجد إيصال للمشاركة.');
      return;
    }

    const filename = selectedSale
      ? `فاتورة_رقم_${selectedSale.id}.pdf`
      : `إيصال_تبرع_رقم_${selectedDonation.id}.pdf`;
    const pdfBlob = await generatePDFBlob(receiptRef.current, filename);

    if (!pdfBlob) {
      toast.error('فشل في إنشاء ملف PDF.');
      return;
    }

    if (method === 'download') {
      const url = URL.createObjectURL(pdfBlob);
      const link = document.createElement('a');
      link.href = url;
      link.download = filename;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      URL.revokeObjectURL(url);
      toast.success('تم تحميل الفاتورة بنجاح');
      return;
    }

    const file = new File([pdfBlob], filename, { type: 'application/pdf' });

    if (navigator.share) {
      try {
        await navigator.share({
          files: [file],
          title: filename,
          text: 'إيصال من جمعية بيان بمكة المكرمة',
        });
        toast.success('تمت المشاركة بنجاح!');
      } catch (error) {
        console.error('Error sharing:', error);
        // Fallback
        fallbackShare(method, pdfBlob, filename);
      }
    } else {
      fallbackShare(method, pdfBlob, filename);
    }
  };

  const fallbackShare = (method, pdfBlob, filename) => {
    if (method === 'email') {
      // Download the PDF first, then open mailto
      const url = URL.createObjectURL(pdfBlob);
      const link = document.createElement('a');
      link.href = url;
      link.download = filename;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      URL.revokeObjectURL(url);
      const mailtoLink = `mailto:?subject=${encodeURIComponent(filename)}&body=${encodeURIComponent('مرفق إيصالك من جمعية بيان بمكة المكرمة. تم تحميل الملف، يرجى إرفاقه.')}`;
      window.open(mailtoLink, '_blank');
    } else if (method === 'whatsapp') {
      toast('الرجاء تحميل الملف ومشاركته يدوياً عبر واتساب.', { icon: 'ℹ️' });
      const url = URL.createObjectURL(pdfBlob);
      const link = document.createElement('a');
      link.href = url;
      link.download = filename;
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      URL.revokeObjectURL(url);
    } else {
      toast.error('المشاركة غير مدعومة في متصفحك.');
    }
  };

  const closeReceipt = () => {
    setShowReceipt(false);
    setSelectedSale(null);
    setSelectedDonation(null);
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-800">التقارير</h1>
          <p className="text-gray-500 mt-1">عرض وتصدير تقارير المبيعات والتبرعات</p>
        </div>
        <button
          onClick={exportCSV}
          className="flex items-center gap-2 bg-bayan-green hover:bg-bayan-dark text-white px-6 py-2 rounded-lg transition-all"
        >
          <HiOutlineDocumentDownload />
          تصدير CSV
        </button>
      </div>

      {/* Tabs + Filters */}
      <div className="bg-white rounded-xl shadow-sm border p-4">
        <div className="flex flex-wrap items-center gap-4">
          {/* Tabs */}
          <div className="flex bg-gray-100 rounded-lg p-1">
            <button
              onClick={() => setActiveTab('sales')}
              className={`px-6 py-2 rounded-lg font-medium transition-all ${
                activeTab === 'sales'
                  ? 'bg-bayan-green text-white shadow'
                  : 'text-gray-600 hover:text-gray-800'
              }`}
            >
              المبيعات
            </button>
            <button
              onClick={() => setActiveTab('donations')}
              className={`px-6 py-2 rounded-lg font-medium transition-all ${
                activeTab === 'donations'
                  ? 'bg-purple-600 text-white shadow'
                  : 'text-gray-600 hover:text-gray-800'
              }`}
            >
              التبرعات
            </button>
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

          {/* Sales table with expandable product details */}
          <div className="bg-white rounded-xl shadow-sm border overflow-hidden">
            <table className="w-full">
              <thead className="bg-gray-50">
                <tr>
                  <th className="text-right px-6 py-3 text-sm font-medium text-gray-500">#</th>
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
                      <td className="px-6 py-4 text-sm text-gray-600">{sale.id}</td>
                      <td className="px-6 py-4 text-sm text-gray-700 max-w-xs">
                        <div className="truncate" title={sale.products_summary}>
                          {sale.products_summary || `${sale.items_count} منتجات`}
                        </div>
                      </td>
                      <td className="px-6 py-4 font-bold text-bayan-green">{sale.total.toFixed(2)} <SarIcon size={13} /></td>
                      <td className="px-6 py-4 text-sm text-gray-600">{paymentMethodAr[sale.payment_method]}</td>
                      <td className="px-6 py-4 text-sm text-gray-600">{sale.user_name}</td>
                      <td className="px-6 py-4 text-sm text-gray-600">
                        {new Date(sale.created_at).toLocaleString('ar-SA')}
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
                        <td colSpan="8" className="px-6 py-3 bg-gray-50">
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
        </>
      )}

      {/* Donations Report */}
      {!loading && activeTab === 'donations' && donationsData && (
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
              <p className="text-sm text-gray-500">نقدي</p>
              <p className="text-2xl font-bold text-emerald-600">{donationsData.summary.cash_total.toFixed(2)} <SarIcon size={18} /></p>
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
                  <th className="text-right px-6 py-3 text-sm font-medium text-gray-500">#</th>
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
                  <tr key={d.id} className="hover:bg-gray-50">
                    <td className="px-6 py-4 text-sm text-gray-600">{d.id}</td>
                    <td className="px-6 py-4 font-medium">{d.donor_name || 'مجهول'}</td>
                    <td className="px-6 py-4 font-bold text-purple-600">{d.amount.toFixed(2)} <SarIcon size={13} /></td>
                    <td className="px-6 py-4 text-sm text-gray-600">{paymentMethodAr[d.payment_method]}</td>
                    <td className="px-6 py-4 text-sm text-gray-600">{d.note || '-'}</td>
                    <td className="px-6 py-4 text-sm text-gray-600">{d.user_name}</td>
                    <td className="px-6 py-4 text-sm text-gray-600">
                      {new Date(d.created_at).toLocaleString('ar-SA')}
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

      {/* ========== Reprint Receipt Modal ========== */}
      {showReceipt && (selectedSale || selectedDonation) && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-2xl w-full max-w-md max-h-[90vh] overflow-auto">
            {/* Receipt Preview */}
            <div ref={receiptRef}>
              <Receipt
                sale={selectedSale}
                type={selectedDonation ? 'donation' : 'sale'}
                donation={selectedDonation}
              />
            </div>

            {/* Action Buttons */}
            <div className="p-4 border-t space-y-3">
              {/* Row 1: Print + Download PDF */}
              <div className="flex gap-3">
                <button
                  onClick={handlePrint}
                  className="flex-1 flex items-center justify-center gap-2 bg-bayan-green hover:bg-bayan-dark text-white font-bold py-3 rounded-xl transition-all"
                >
                  <HiOutlinePrinter />
                  طباعة
                </button>
                <button
                  onClick={() => handleShare('download')}
                  className="flex-1 flex items-center justify-center gap-2 bg-gray-700 hover:bg-gray-800 text-white font-bold py-3 rounded-xl transition-all"
                >
                  <HiOutlineDownload />
                  تحميل PDF
                </button>
              </div>

              {/* Row 2: Email + WhatsApp */}
              <div className="flex gap-3">
                <button
                  onClick={() => handleShare('email')}
                  className="flex-1 flex items-center justify-center gap-2 bg-blue-500 hover:bg-blue-600 text-white font-bold py-3 rounded-xl transition-all"
                >
                  <HiOutlineMail />
                  إرسال بريد
                </button>
                <button
                  onClick={() => handleShare('whatsapp')}
                  className="flex-1 flex items-center justify-center gap-2 bg-green-500 hover:bg-green-600 text-white font-bold py-3 rounded-xl transition-all"
                >
                  <HiOutlineChatAlt2 />
                  واتساب
                </button>
              </div>

              {/* Row 3: Close */}
              <button
                onClick={closeReceipt}
                className="w-full py-3 bg-gray-100 hover:bg-gray-200 text-gray-700 rounded-xl transition-all font-medium"
              >
                إغلاق
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
