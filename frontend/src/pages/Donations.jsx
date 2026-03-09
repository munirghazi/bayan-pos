import { useState, useEffect, useRef } from 'react';
import { donationsAPI } from '../services/api';
import Receipt from '../components/Receipt';
import { SarIcon } from '../components/SarIcon';
import { printReceipt } from '../utils/printReceipt';
import { downloadPDF, shareViaWhatsApp, shareViaEmail } from '../utils/generatePDF';
import toast from 'react-hot-toast';
import {
  HiOutlineHeart,
  HiOutlinePlus,
  HiOutlineTrash,
  HiOutlinePrinter,
  HiOutlineCash,
  HiOutlineCreditCard,
  HiOutlineDeviceMobile,
  HiOutlineDocumentDownload,
  HiOutlineMail,
} from 'react-icons/hi';

const WhatsAppIcon = () => (
  <svg viewBox="0 0 24 24" fill="currentColor" className="w-4 h-4">
    <path d="M17.472 14.382c-.297-.149-1.758-.867-2.03-.967-.273-.099-.471-.148-.67.15-.197.297-.767.966-.94 1.164-.173.199-.347.223-.644.075-.297-.15-1.255-.463-2.39-1.475-.883-.788-1.48-1.761-1.653-2.059-.173-.297-.018-.458.13-.606.134-.133.298-.347.446-.52.149-.174.198-.298.298-.497.099-.198.05-.371-.025-.52-.075-.149-.669-1.612-.916-2.207-.242-.579-.487-.5-.669-.51-.173-.008-.371-.01-.57-.01-.198 0-.52.074-.792.372-.272.297-1.04 1.016-1.04 2.479 0 1.462 1.065 2.875 1.213 3.074.149.198 2.096 3.2 5.077 4.487.709.306 1.262.489 1.694.625.712.227 1.36.195 1.871.118.571-.085 1.758-.719 2.006-1.413.248-.694.248-1.289.173-1.413-.074-.124-.272-.198-.57-.347m-5.421 7.403h-.004a9.87 9.87 0 01-5.031-1.378l-.361-.214-3.741.982.998-3.648-.235-.374a9.86 9.86 0 01-1.51-5.26c.001-5.45 4.436-9.884 9.888-9.884 2.64 0 5.122 1.03 6.988 2.898a9.825 9.825 0 012.893 6.994c-.003 5.45-4.437 9.884-9.885 9.884m8.413-18.297A11.815 11.815 0 0012.05 0C5.495 0 .16 5.335.157 11.892c0 2.096.547 4.142 1.588 5.945L.057 24l6.305-1.654a11.882 11.882 0 005.683 1.448h.005c6.554 0 11.89-5.335 11.893-11.893a11.821 11.821 0 00-3.48-8.413z" />
  </svg>
);

const paymentMethodAr = { cash: 'نقدي', card: 'شبكة', transfer: 'تحويل' };

export default function Donations() {
  const [donations, setDonations] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [showReceipt, setShowReceipt] = useState(false);
  const [selectedDonation, setSelectedDonation] = useState(null);
  const receiptRef = useRef(null);

  const [form, setForm] = useState({
    donor_name: '',
    amount: '',
    note: '',
    payment_method: 'cash',
  });

  useEffect(() => {
    loadDonations();
  }, []);

  const loadDonations = async () => {
    try {
      const res = await donationsAPI.getAll();
      setDonations(res.data);
    } catch (err) {
      toast.error('خطأ في تحميل التبرعات');
    } finally {
      setLoading(false);
    }
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    const amount = parseFloat(form.amount);
    if (!amount || amount <= 0) {
      toast.error('الرجاء إدخال مبلغ صحيح');
      return;
    }

    try {
      const res = await donationsAPI.create({
        donor_name: form.donor_name || null,
        amount,
        note: form.note || null,
        payment_method: form.payment_method,
      });

      setSelectedDonation(res.data);
      setShowForm(false);
      setShowReceipt(true);
      setForm({ donor_name: '', amount: '', note: '', payment_method: 'cash' });
      loadDonations();
      toast.success('تم تسجيل التبرع - جزاكم الله خيراً');
    } catch (err) {
      toast.error(err.response?.data?.detail || 'خطأ في تسجيل التبرع');
    }
  };

  const handleDelete = async (id) => {
    if (!confirm('هل أنت متأكد من حذف هذا التبرع؟')) return;
    try {
      await donationsAPI.delete(id);
      toast.success('تم حذف التبرع');
      loadDonations();
    } catch (err) {
      toast.error('خطأ في حذف التبرع');
    }
  };

  const handlePrint = () => {
    printReceipt(receiptRef);
  };

  const getFilename = () => selectedDonation ? `إيصال_تبرع_${selectedDonation.id}` : 'إيصال_تبرع';

  const handleDownloadPDF = async () => {
    if (!receiptRef.current) return;
    try {
      toast.loading('جاري إنشاء PDF...');
      await downloadPDF(receiptRef.current, getFilename());
      toast.dismiss();
      toast.success('تم تحميل PDF');
    } catch (err) {
      toast.dismiss();
      toast.error('خطأ في إنشاء PDF');
    }
  };

  const handleShareWhatsApp = async () => {
    if (!receiptRef.current) return;
    try {
      toast.loading('جاري إنشاء PDF...');
      await shareViaWhatsApp(receiptRef.current, getFilename());
      toast.dismiss();
    } catch (err) {
      toast.dismiss();
      toast.error('خطأ في المشاركة');
    }
  };

  const handleShareEmail = async () => {
    if (!receiptRef.current) return;
    try {
      toast.loading('جاري إنشاء PDF...');
      await shareViaEmail(receiptRef.current, getFilename());
      toast.dismiss();
    } catch (err) {
      toast.dismiss();
      toast.error('خطأ في المشاركة');
    }
  };

  const totalDonations = donations.reduce((sum, d) => sum + d.amount, 0);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-bayan-green"></div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-800">التبرعات</h1>
          <p className="text-gray-500 mt-1">
            الإجمالي: <span className="font-bold text-purple-600">{totalDonations.toFixed(2)} <SarIcon size={14} /></span>
            {' '} ({donations.length} تبرع)
          </p>
        </div>
        <button
          onClick={() => setShowForm(true)}
          className="flex items-center gap-2 bg-purple-600 hover:bg-purple-700 text-white px-6 py-2 rounded-lg transition-all"
        >
          <HiOutlinePlus />
          تسجيل تبرع
        </button>
      </div>

      {/* Donations Table */}
      <div className="bg-white rounded-xl shadow-sm border overflow-hidden">
        <table className="w-full">
          <thead className="bg-gray-50">
            <tr>
              <th className="text-right px-6 py-3 text-sm font-medium text-gray-500">#</th>
              <th className="text-right px-6 py-3 text-sm font-medium text-gray-500">المتبرع</th>
              <th className="text-right px-6 py-3 text-sm font-medium text-gray-500">المبلغ</th>
              <th className="text-right px-6 py-3 text-sm font-medium text-gray-500">طريقة الدفع</th>
              <th className="text-right px-6 py-3 text-sm font-medium text-gray-500">ملاحظة</th>
              <th className="text-right px-6 py-3 text-sm font-medium text-gray-500">التاريخ</th>
              <th className="text-right px-6 py-3 text-sm font-medium text-gray-500">الموظف</th>
              <th className="px-6 py-3"></th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-100">
            {donations.map((donation) => (
              <tr key={donation.id} className="hover:bg-gray-50">
                <td className="px-6 py-4 text-sm text-gray-600">{donation.id}</td>
                <td className="px-6 py-4">
                  <span className="font-medium text-gray-800">
                    {donation.donor_name || 'متبرع مجهول'}
                  </span>
                </td>
                <td className="px-6 py-4">
                  <span className="font-bold text-purple-600">{donation.amount.toFixed(2)} <SarIcon size={13} /></span>
                </td>
                <td className="px-6 py-4 text-sm text-gray-600">
                  {paymentMethodAr[donation.payment_method]}
                </td>
                <td className="px-6 py-4 text-sm text-gray-600">{donation.note || '-'}</td>
                <td className="px-6 py-4 text-sm text-gray-600">
                  {new Date(donation.created_at).toLocaleDateString('ar-SA')}
                </td>
                <td className="px-6 py-4 text-sm text-gray-600">{donation.user_name}</td>
                <td className="px-6 py-4">
                  <div className="flex gap-2">
                    <button
                      onClick={() => { setSelectedDonation(donation); setShowReceipt(true); }}
                      className="p-2 text-bayan-green hover:bg-bayan-light rounded-lg transition-all"
                      title="طباعة إيصال"
                    >
                      <HiOutlinePrinter />
                    </button>
                    <button
                      onClick={() => handleDelete(donation.id)}
                      className="p-2 text-red-600 hover:bg-red-50 rounded-lg transition-all"
                      title="حذف"
                    >
                      <HiOutlineTrash />
                    </button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>

        {donations.length === 0 && (
          <div className="text-center py-16 text-gray-400">
            <HiOutlineHeart className="text-6xl mx-auto mb-4" />
            <p className="text-lg">لا توجد تبرعات بعد</p>
          </div>
        )}
      </div>

      {/* Donation Form Modal */}
      {showForm && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-2xl w-full max-w-md p-6">
            <h2 className="text-xl font-bold text-gray-800 mb-4 flex items-center gap-2">
              <HiOutlineHeart className="text-purple-600" />
              تسجيل تبرع جديد
            </h2>

            <form onSubmit={handleSubmit} className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">مبلغ التبرع (<SarIcon size={12} />) *</label>
                <input
                  type="number"
                  step="0.01"
                  value={form.amount}
                  onChange={(e) => setForm({ ...form, amount: e.target.value })}
                  className="w-full px-4 py-3 rounded-lg border border-gray-300 focus:ring-2 focus:ring-purple-500 outline-none text-center text-xl"
                  placeholder="0.00"
                  autoFocus
                />
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">اسم المتبرع (اختياري)</label>
                <input
                  type="text"
                  value={form.donor_name}
                  onChange={(e) => setForm({ ...form, donor_name: e.target.value })}
                  className="w-full px-4 py-2 rounded-lg border border-gray-300 focus:ring-2 focus:ring-purple-500 outline-none"
                  placeholder="اسم المتبرع"
                />
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">ملاحظة (اختياري)</label>
                <input
                  type="text"
                  value={form.note}
                  onChange={(e) => setForm({ ...form, note: e.target.value })}
                  className="w-full px-4 py-2 rounded-lg border border-gray-300 focus:ring-2 focus:ring-purple-500 outline-none"
                  placeholder="ملاحظة"
                />
              </div>

              <div className="grid grid-cols-3 gap-2">
                {[
                  { key: 'cash', icon: HiOutlineCash, label: 'نقدي' },
                  { key: 'card', icon: HiOutlineCreditCard, label: 'شبكة' },
                  { key: 'transfer', icon: HiOutlineDeviceMobile, label: 'تحويل' },
                ].map(({ key, icon: Icon, label }) => (
                  <button
                    key={key}
                    type="button"
                    onClick={() => setForm({ ...form, payment_method: key })}
                    className={`flex flex-col items-center gap-1 py-2 rounded-lg border-2 transition-all text-sm ${
                      form.payment_method === key
                        ? 'border-purple-500 bg-purple-50 text-purple-700'
                        : 'border-gray-200 text-gray-500 hover:border-gray-300'
                    }`}
                  >
                    <Icon className="text-lg" />
                    {label}
                  </button>
                ))}
              </div>

              <div className="flex gap-3 pt-2">
                <button
                  type="submit"
                  className="flex-1 bg-purple-600 hover:bg-purple-700 text-white font-bold py-3 rounded-xl transition-all"
                >
                  تسجيل التبرع
                </button>
                <button
                  type="button"
                  onClick={() => setShowForm(false)}
                  className="px-6 py-3 bg-gray-100 hover:bg-gray-200 text-gray-700 rounded-xl transition-all"
                >
                  إلغاء
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Receipt Modal */}
      {showReceipt && selectedDonation && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-2xl w-full max-w-md max-h-[90vh] overflow-auto">
            <div ref={receiptRef}>
              <Receipt type="donation" donation={selectedDonation} />
            </div>
            <div className="p-4 border-t space-y-3">
              {/* Primary actions */}
              <div className="flex gap-3">
                <button
                  onClick={handlePrint}
                  className="flex-1 flex items-center justify-center gap-2 bg-bayan-green hover:bg-bayan-dark text-white font-bold py-3 rounded-xl transition-all"
                >
                  <HiOutlinePrinter />
                  طباعة
                </button>
                <button
                  onClick={handleDownloadPDF}
                  className="flex-1 flex items-center justify-center gap-2 bg-blue-600 hover:bg-blue-700 text-white font-bold py-3 rounded-xl transition-all"
                >
                  <HiOutlineDocumentDownload />
                  تحميل PDF
                </button>
              </div>
              {/* Share actions */}
              <div className="flex gap-3">
                <button
                  onClick={handleShareWhatsApp}
                  className="flex-1 flex items-center justify-center gap-2 bg-green-500 hover:bg-green-600 text-white font-medium py-2.5 rounded-xl transition-all"
                >
                  <WhatsAppIcon />
                  واتساب
                </button>
                <button
                  onClick={handleShareEmail}
                  className="flex-1 flex items-center justify-center gap-2 bg-orange-500 hover:bg-orange-600 text-white font-medium py-2.5 rounded-xl transition-all"
                >
                  <HiOutlineMail className="text-xl" />
                  إيميل
                </button>
                <button
                  onClick={() => { setShowReceipt(false); setSelectedDonation(null); }}
                  className="px-6 py-2.5 bg-gray-100 hover:bg-gray-200 text-gray-700 rounded-xl transition-all"
                >
                  إغلاق
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
