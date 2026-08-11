import { useState, useEffect, useRef } from 'react';
import { suppliersAPI, apiError } from '../services/api';
import toast from 'react-hot-toast';
import {
  HiOutlineTruck, HiOutlinePlus, HiOutlineTrash, HiOutlineCheckCircle,
  HiOutlineExclamationCircle, HiOutlineUpload, HiOutlineDocumentText,
} from 'react-icons/hi';

const DOC_TYPES = [
  { key: 'cr', label: 'السجل التجاري' },
  { key: 'vat', label: 'الشهادة الضريبية' },
  { key: 'national_address', label: 'العنوان الوطني' },
];

export default function Suppliers() {
  const [suppliers, setSuppliers] = useState([]);
  const [newSupplier, setNewSupplier] = useState({ name: '', iban: '', payment_terms: '' });
  const [selected, setSelected] = useState(null); // detail w/ compliance
  const [docForms, setDocForms] = useState({});   // doc_type -> { number, expiry_date }
  const submittingRef = useRef(false);

  useEffect(() => { load(); }, []);

  const load = async () => {
    try {
      const res = await suppliersAPI.getAll();
      setSuppliers(res.data);
    } catch (err) { toast.error(apiError(err, 'خطأ في التحميل')); }
  };

  const selectSupplier = async (id) => {
    try {
      const res = await suppliersAPI.get(id);
      setSelected(res.data);
      const forms = {};
      res.data.compliance.documents.forEach((d) => {
        forms[d.doc_type] = { number: d.number || '', expiry_date: d.expiry_date || '' };
      });
      setDocForms(forms);
    } catch (err) { toast.error(apiError(err, 'خطأ')); }
  };

  const refreshSelected = (detail) => {
    setSelected(detail);
    const forms = {};
    detail.compliance.documents.forEach((d) => {
      forms[d.doc_type] = { number: d.number || '', expiry_date: d.expiry_date || '' };
    });
    setDocForms(forms);
    load(); // update list badges
  };

  const createSupplier = async () => {
    if (!newSupplier.name.trim()) { toast.error('أدخل اسم المورّد'); return; }
    if (submittingRef.current) return;
    submittingRef.current = true;
    try {
      const res = await suppliersAPI.create({
        name: newSupplier.name.trim(),
        iban: newSupplier.iban.trim() || null,
        payment_terms: newSupplier.payment_terms.trim() || null,
      });
      toast.success('تم إضافة المورّد');
      setNewSupplier({ name: '', iban: '', payment_terms: '' });
      await load();
      refreshSelected(res.data);
    } catch (err) {
      toast.error(apiError(err, 'خطأ في الإضافة'));
    } finally { submittingRef.current = false; }
  };

  const deactivate = async (id) => {
    if (!confirm('تعطيل هذا المورّد؟')) return;
    try {
      await suppliersAPI.delete(id);
      if (selected && selected.id === id) setSelected(null);
      load();
    } catch (err) { toast.error(apiError(err, 'خطأ')); }
  };

  const saveDoc = async (docType) => {
    const form = docForms[docType] || {};
    try {
      const res = await suppliersAPI.upsertDoc(selected.id, {
        doc_type: docType,
        number: form.number || null,
        expiry_date: form.expiry_date || null,
      });
      toast.success('تم حفظ بيانات المستند (بانتظار التحقّق)');
      refreshSelected(res.data);
    } catch (err) { toast.error(apiError(err, 'خطأ في الحفظ')); }
  };

  const uploadDoc = async (docType, file) => {
    if (!file) return;
    try {
      const res = await suppliersAPI.uploadDoc(selected.id, docType, file);
      toast.success('تم رفع الملف (بانتظار التحقّق)');
      refreshSelected(res.data);
    } catch (err) { toast.error(apiError(err, 'خطأ في الرفع')); }
  };

  const verifyDoc = async (docType) => {
    try {
      const res = await suppliersAPI.verifyDoc(selected.id, docType);
      toast.success('تم التحقّق من المستند');
      refreshSelected(res.data);
    } catch (err) { toast.error(apiError(err, 'خطأ')); }
  };

  const docStatus = (d) => {
    if (!d.present) return { text: 'غير مرفوع', cls: 'bg-gray-100 text-gray-500' };
    if (d.expired) return { text: 'منتهي', cls: 'bg-red-100 text-red-700' };
    if (!d.is_verified) return { text: 'بانتظار التحقّق', cls: 'bg-yellow-100 text-yellow-700' };
    if (d.expiring_soon) return { text: 'قارب على الانتهاء', cls: 'bg-orange-100 text-orange-700' };
    return { text: 'موثّق', cls: 'bg-green-100 text-green-700' };
  };

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-800 flex items-center gap-2">
          <HiOutlineTruck className="text-bayan-green" /> الموردون
        </h1>
        <p className="text-gray-500 mt-1">إدارة الموردين والتحقّق من المستندات (السجل التجاري، الضريبة، العنوان الوطني)</p>
      </div>

      {/* Add supplier */}
      <div className="bg-white rounded-xl border shadow-sm p-4 grid grid-cols-1 md:grid-cols-4 gap-3">
        <input value={newSupplier.name} onChange={(e) => setNewSupplier({ ...newSupplier, name: e.target.value })}
          placeholder="اسم المورّد" className="px-4 py-2 rounded-lg border border-gray-300 focus:ring-2 focus:ring-bayan-green outline-none text-right" />
        <input value={newSupplier.iban} onChange={(e) => setNewSupplier({ ...newSupplier, iban: e.target.value })}
          placeholder="الآيبان (اختياري)" dir="ltr" className="px-4 py-2 rounded-lg border border-gray-300 focus:ring-2 focus:ring-bayan-green outline-none" />
        <input value={newSupplier.payment_terms} onChange={(e) => setNewSupplier({ ...newSupplier, payment_terms: e.target.value })}
          placeholder="شروط الدفع (اختياري)" className="px-4 py-2 rounded-lg border border-gray-300 focus:ring-2 focus:ring-bayan-green outline-none text-right" />
        <button onClick={createSupplier}
          className="flex items-center justify-center gap-2 bg-bayan-green hover:bg-bayan-dark text-white px-6 py-2 rounded-lg transition-all">
          <HiOutlinePlus /> إضافة
        </button>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Supplier list */}
        <div className="bg-white rounded-xl border shadow-sm overflow-hidden">
          <div className="px-4 py-3 bg-gray-50 border-b font-bold text-gray-800">القائمة ({suppliers.length})</div>
          {suppliers.length === 0 ? (
            <p className="p-4 text-gray-400 text-sm">لا يوجد موردون</p>
          ) : (
            <div className="divide-y">
              {suppliers.map((s) => (
                <div key={s.id}
                  onClick={() => selectSupplier(s.id)}
                  className={`px-4 py-3 flex items-center justify-between cursor-pointer hover:bg-gray-50 ${selected && selected.id === s.id ? 'bg-emerald-50' : ''}`}>
                  <div className="flex items-center gap-2">
                    {s.is_compliant
                      ? <HiOutlineCheckCircle className="text-green-600 text-xl" />
                      : <HiOutlineExclamationCircle className="text-red-500 text-xl" />}
                    <span className="text-gray-800">{s.name}</span>
                  </div>
                  <div className="flex items-center gap-3">
                    <span className={`text-xs px-2 py-0.5 rounded-full ${s.is_compliant ? 'bg-green-100 text-green-700' : 'bg-red-100 text-red-700'}`}>
                      {s.is_compliant ? 'متوافق' : 'غير متوافق'}
                    </span>
                    <button onClick={(e) => { e.stopPropagation(); deactivate(s.id); }} className="text-red-400 hover:text-red-600">
                      <HiOutlineTrash />
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Documents panel */}
        <div className="bg-white rounded-xl border shadow-sm overflow-hidden">
          <div className="px-4 py-3 bg-gray-50 border-b font-bold text-gray-800">
            {selected ? `مستندات: ${selected.name}` : 'اختر مورّداً لإدارة مستنداته'}
          </div>
          {selected && (
            <div className="p-4 space-y-4">
              {selected.compliance.documents.map((d) => {
                const st = docStatus(d);
                const form = docForms[d.doc_type] || { number: '', expiry_date: '' };
                return (
                  <div key={d.doc_type} className="rounded-lg border p-3 space-y-3">
                    <div className="flex items-center justify-between">
                      <span className="font-medium text-gray-800">{d.label}</span>
                      <span className={`text-xs px-2 py-0.5 rounded-full ${st.cls}`}>{st.text}</span>
                    </div>
                    <div className="grid grid-cols-2 gap-2">
                      <input value={form.number}
                        onChange={(e) => setDocForms({ ...docForms, [d.doc_type]: { ...form, number: e.target.value } })}
                        placeholder="رقم المستند" className="px-3 py-2 rounded border border-gray-300 outline-none text-sm text-right" />
                      <input type="date" value={form.expiry_date || ''}
                        onChange={(e) => setDocForms({ ...docForms, [d.doc_type]: { ...form, expiry_date: e.target.value } })}
                        className="px-3 py-2 rounded border border-gray-300 outline-none text-sm" dir="ltr" />
                    </div>
                    <div className="flex flex-wrap items-center gap-2">
                      <button onClick={() => saveDoc(d.doc_type)}
                        className="bg-gray-100 hover:bg-gray-200 text-gray-700 px-3 py-1.5 rounded text-sm">حفظ البيانات</button>
                      <label className="flex items-center gap-1 bg-gray-100 hover:bg-gray-200 text-gray-700 px-3 py-1.5 rounded text-sm cursor-pointer">
                        <HiOutlineUpload /> رفع ملف
                        <input type="file" accept=".pdf,.jpg,.jpeg,.png,.webp" className="hidden"
                          onChange={(e) => uploadDoc(d.doc_type, e.target.files[0])} />
                      </label>
                      {d.file_url && (
                        <a href={d.file_url} target="_blank" rel="noopener noreferrer"
                          className="flex items-center gap-1 text-blue-600 hover:underline text-sm">
                          <HiOutlineDocumentText /> عرض الملف
                        </a>
                      )}
                      {d.present && !d.is_verified && (
                        <button onClick={() => verifyDoc(d.doc_type)}
                          className="bg-green-600 hover:bg-green-700 text-white px-3 py-1.5 rounded text-sm mr-auto">تحقّق</button>
                      )}
                    </div>
                  </div>
                );
              })}

              <div className={`rounded-lg p-3 text-sm font-medium ${selected.compliance.is_compliant ? 'bg-green-50 text-green-700' : 'bg-red-50 text-red-700'}`}>
                {selected.compliance.is_compliant
                  ? '✓ هذا المورّد متوافق ويمكن إصدار أوامر شراء له'
                  : '✗ هذا المورّد غير متوافق — لا يمكن إصدار أوامر شراء حتى تكتمل المستندات وتُوثّق'}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
