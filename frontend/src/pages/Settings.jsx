import { useState, useEffect, useRef } from 'react';
import { authAPI, settingsAPI, locationsAPI } from '../services/api';
import { getZATCASettings, saveZATCASettings } from '../utils/zatca';
import { getPOSSettings, savePOSSettings } from '../utils/posSettings';
import toast from 'react-hot-toast';
import {
  HiOutlineUsers,
  HiOutlinePlus,
  HiOutlinePencil,
  HiOutlineTrash,
  HiOutlineShieldCheck,
  HiOutlineDocumentText,
  HiOutlineSave,
  HiOutlineOfficeBuilding,
  HiOutlineCash,
  HiOutlineCreditCard,
  HiOutlineDeviceMobile,
  HiOutlineHeart,
  HiOutlinePhotograph,
  HiOutlineAdjustments,
} from 'react-icons/hi';

export default function Settings() {
  const [users, setUsers] = useState([]);
  const [locations, setLocations] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [editingUser, setEditingUser] = useState(null);
  const [activeSection, setActiveSection] = useState('profile');

  const [form, setForm] = useState({
    username: '',
    password: '',
    full_name: '',
    role: 'cashier',
    location_id: '',
  });

  // Company profile & ZATCA settings combined
  const [profileForm, setProfileForm] = useState({
    sellerName: '', vatNumber: '', vatRate: 0.15, website: '', city: '', country: '',
  });
  const savingProfileRef = useRef(false);

  // POS settings
  const [posSettings, setPosSettings] = useState(getPOSSettings());
  const [logoPreview, setLogoPreview] = useState('');
  const logoInputRef = useRef(null);
  const submittingRef = useRef(false);  // prevents duplicate submits

  const currentUser = JSON.parse(localStorage.getItem('user') || '{}');

  useEffect(() => {
    loadUsers();
    loadLogo();
    loadLocations();
    loadTenantSettings();
  }, []);

  const loadTenantSettings = async () => {
    try {
      const { data } = await settingsAPI.getTenant();
      const form = {
        sellerName: data.seller_name || '',
        vatNumber: data.vat_number || '',
        vatRate: (data.vat_rate ?? 15) / 100,
        website: data.website || '',
        city: data.city || '',
        country: data.country || '',
      };
      setProfileForm(form);
      // keep the receipt/ZATCA-QR cache in sync with THIS tenant
      saveZATCASettings({ sellerName: form.sellerName, vatNumber: form.vatNumber, vatRate: form.vatRate });
      localStorage.setItem('tenant_logo', data.logo_url || '');
    } catch (err) {}
  };

  const loadLocations = async () => {
    try {
      const res = await locationsAPI.getAll();
      setLocations(res.data);
    } catch (err) {}
  };

  const loadLogo = async () => {
    try {
      const res = await settingsAPI.getLogo();
      if (res.data.url) {
        setLogoPreview(res.data.url);
        setPosSettings((prev) => ({ ...prev, logoUrl: res.data.url }));
      }
    } catch (err) {}
  };

  const handleLogoUpload = async (e) => {
    const file = e.target.files[0];
    if (!file) return;
    try {
      const res = await settingsAPI.uploadLogo(file);
      const url = res.data.url;
      setLogoPreview(url);
      localStorage.setItem('tenant_logo', url);
      const updated = { ...posSettings, logoUrl: url };
      setPosSettings(updated);
      savePOSSettings(updated);
      toast.success('تم رفع الشعار بنجاح');
    } catch (err) {
      toast.error(err.response?.data?.detail || 'خطأ في رفع الشعار');
    }
  };

  const handleSavePOSSettings = () => {
    savePOSSettings(posSettings);
    toast.success('تم حفظ إعدادات نقطة البيع');
  };

  const loadUsers = async () => {
    try {
      const res = await authAPI.getUsers();
      setUsers(res.data);
    } catch (err) {
      toast.error('خطأ في تحميل المستخدمين');
    } finally {
      setLoading(false);
    }
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!editingUser && (!form.username || !form.password || !form.full_name)) {
      toast.error('الرجاء تعبئة جميع الحقول المطلوبة');
      return;
    }
    if (submittingRef.current) return;
    submittingRef.current = true;
    const locId = form.location_id ? parseInt(form.location_id) : null;
    try {
      if (editingUser) {
        const data = { full_name: form.full_name, role: form.role };
        if (form.password) data.password = form.password;
        if (locId !== null) data.location_id = locId;
        await authAPI.updateUser(editingUser.id, data);
        toast.success('تم تحديث المستخدم');
      } else {
        await authAPI.createUser({
          username: form.username, password: form.password,
          full_name: form.full_name, role: form.role, location_id: locId,
        });
        toast.success('تم إضافة المستخدم');
      }
      resetForm();
      loadUsers();
    } catch (err) {
      toast.error(err.response?.data?.detail || (editingUser ? 'خطأ في التحديث' : 'خطأ في الإضافة'));
    } finally {
      submittingRef.current = false;
    }
  };

  const handleDelete = async (id) => {
    if (!confirm('هل أنت متأكد من حذف هذا المستخدم؟')) return;
    try {
      await authAPI.deleteUser(id);
      toast.success('تم حذف المستخدم');
      loadUsers();
    } catch (err) {
      toast.error(err.response?.data?.detail || 'خطأ في الحذف');
    }
  };

  const handleToggleActive = async (user) => {
    try {
      await authAPI.updateUser(user.id, { is_active: !user.is_active });
      toast.success(user.is_active ? 'تم تعطيل الحساب' : 'تم تفعيل الحساب');
      loadUsers();
    } catch (err) {
      toast.error('خطأ في تحديث الحالة');
    }
  };

  const handleEdit = (user) => {
    setEditingUser(user);
    setForm({
      username: user.username,
      password: '',
      full_name: user.full_name,
      role: user.role,
      location_id: user.location_id ? String(user.location_id) : '',
    });
    setShowForm(true);
  };

  const resetForm = () => {
    setForm({ username: '', password: '', full_name: '', role: 'cashier', location_id: '' });
    setEditingUser(null);
    setShowForm(false);
  };

  const handleSaveProfile = async () => {
    if (!profileForm.vatNumber || profileForm.vatNumber.length !== 15) {
      toast.error('الرقم الضريبي يجب أن يكون 15 رقم');
      return;
    }
    if (savingProfileRef.current) return;
    savingProfileRef.current = true;
    try {
      await settingsAPI.updateTenant({
        seller_name: profileForm.sellerName,
        vat_number: profileForm.vatNumber,
        vat_rate: Math.round((profileForm.vatRate || 0) * 100),
        website: profileForm.website,
        city: profileForm.city,
        country: profileForm.country,
      });
      saveZATCASettings({ sellerName: profileForm.sellerName, vatNumber: profileForm.vatNumber, vatRate: profileForm.vatRate });
      toast.success('تم حفظ بيانات الجمعية');
    } catch (err) {
      toast.error(err.response?.data?.detail || 'خطأ في الحفظ');
    } finally {
      savingProfileRef.current = false;
    }
  };

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
          <h1 className="text-2xl font-bold text-gray-800">الإعدادات</h1>
          <p className="text-gray-500 mt-1">إدارة بيانات الجمعية والمستخدمين</p>
        </div>
        {activeSection === 'users' && (
          <button
            onClick={() => { resetForm(); setShowForm(true); }}
            className="flex items-center gap-2 bg-bayan-green hover:bg-bayan-dark text-white px-6 py-2 rounded-lg transition-all"
          >
            <HiOutlinePlus />
            إضافة مستخدم
          </button>
        )}
      </div>

      {/* Section Tabs */}
      <div className="flex bg-gray-100 rounded-lg p-1 w-fit flex-wrap gap-1">
        <button
          onClick={() => setActiveSection('profile')}
          className={`flex items-center gap-2 px-6 py-2 rounded-lg font-medium transition-all ${
            activeSection === 'profile'
              ? 'bg-bayan-green text-white shadow'
              : 'text-gray-600 hover:text-gray-800'
          }`}
        >
          <HiOutlineOfficeBuilding />
          بيانات الجمعية
        </button>
        <button
          onClick={() => setActiveSection('pos')}
          className={`flex items-center gap-2 px-6 py-2 rounded-lg font-medium transition-all ${
            activeSection === 'pos'
              ? 'bg-bayan-green text-white shadow'
              : 'text-gray-600 hover:text-gray-800'
          }`}
        >
          <HiOutlineAdjustments />
          إعدادات نقطة البيع
        </button>
        <button
          onClick={() => setActiveSection('users')}
          className={`flex items-center gap-2 px-6 py-2 rounded-lg font-medium transition-all ${
            activeSection === 'users'
              ? 'bg-bayan-green text-white shadow'
              : 'text-gray-600 hover:text-gray-800'
          }`}
        >
          <HiOutlineUsers />
          المستخدمين
        </button>
      </div>

      {/* ===== Company Profile & ZATCA Section ===== */}
      {activeSection === 'profile' && (
        <div className="space-y-6">
          {/* Company Info + VAT in one card */}
          <div className="bg-white rounded-xl border p-6 space-y-6">
            <div>
              <h2 className="text-lg font-bold text-gray-800 flex items-center gap-2">
                <HiOutlineOfficeBuilding className="text-bayan-green" />
                بيانات الجمعية والإعدادات الضريبية
              </h2>
              <p className="text-sm text-gray-500 mt-1">
                هذه البيانات تظهر في الفواتير وتُستخدم لإنشاء رمز QR المتوافق مع هيئة الزكاة والضريبة والجمارك (ZATCA)
              </p>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              {/* Seller Name */}
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  اسم الجمعية / البائع *
                </label>
                <input
                  type="text"
                  value={profileForm.sellerName}
                  onChange={(e) => setProfileForm({ ...profileForm, sellerName: e.target.value })}
                  className="w-full px-4 py-3 rounded-lg border border-gray-300 focus:ring-2 focus:ring-bayan-green outline-none"
                  placeholder="جمعية بيان بمكة المكرمة"
                />
              </div>

              {/* VAT Number */}
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  الرقم الضريبي (VAT Number) *
                </label>
                <input
                  type="text"
                  value={profileForm.vatNumber}
                  onChange={(e) => setProfileForm({ ...profileForm, vatNumber: e.target.value })}
                  className="w-full px-4 py-3 rounded-lg border border-gray-300 focus:ring-2 focus:ring-bayan-green outline-none font-mono"
                  placeholder="300000000000003"
                  dir="ltr"
                  maxLength={15}
                />
                <p className="text-xs text-gray-400 mt-1">الرقم الضريبي يتكون من 15 رقم ويبدأ وينتهي بـ 3</p>
              </div>

              {/* VAT Rate */}
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">
                  نسبة ضريبة القيمة المضافة (%)
                </label>
                <input
                  type="number"
                  step="0.01"
                  value={(profileForm.vatRate * 100).toFixed(0)}
                  onChange={(e) => setProfileForm({ ...profileForm, vatRate: parseFloat(e.target.value || 0) / 100 })}
                  className="w-full px-4 py-3 rounded-lg border border-gray-300 focus:ring-2 focus:ring-bayan-green outline-none"
                  placeholder="15"
                  dir="ltr"
                />
                <p className="text-xs text-gray-400 mt-1">النسبة الحالية في المملكة العربية السعودية 15%</p>
              </div>

              {/* Website */}
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">الموقع الإلكتروني</label>
                <input
                  type="text"
                  value={profileForm.website}
                  onChange={(e) => setProfileForm({ ...profileForm, website: e.target.value })}
                  className="w-full px-4 py-3 rounded-lg border border-gray-300 focus:ring-2 focus:ring-bayan-green outline-none"
                  placeholder="https://example.org.sa"
                  dir="ltr"
                />
              </div>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">المدينة</label>
                <input
                  type="text"
                  value={profileForm.city}
                  onChange={(e) => setProfileForm({ ...profileForm, city: e.target.value })}
                  className="w-full px-4 py-3 rounded-lg border border-gray-300 focus:ring-2 focus:ring-bayan-green outline-none"
                  placeholder="المدينة"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">الدولة</label>
                <input
                  type="text"
                  value={profileForm.country}
                  onChange={(e) => setProfileForm({ ...profileForm, country: e.target.value })}
                  className="w-full px-4 py-3 rounded-lg border border-gray-300 focus:ring-2 focus:ring-bayan-green outline-none"
                  placeholder="الدولة"
                />
              </div>
            </div>

            {/* Save button */}
            <div className="flex justify-end pt-2 border-t">
              <button
                onClick={handleSaveProfile}
                className="flex items-center gap-2 bg-bayan-green hover:bg-bayan-dark text-white px-8 py-3 rounded-xl transition-all font-bold"
              >
                <HiOutlineSave className="text-xl" />
                حفظ البيانات
              </button>
            </div>
          </div>

          {/* ZATCA Info box */}
          <div className="bg-blue-50 border border-blue-200 rounded-xl p-5">
            <h3 className="font-bold text-blue-800 text-sm mb-2 flex items-center gap-2">
              <HiOutlineDocumentText />
              معلومات عن الفاتورة الضريبية المبسطة (ZATCA)
            </h3>
            <ul className="text-sm text-blue-700 space-y-1 list-disc list-inside">
              <li>تتوافق مع متطلبات المرحلة الأولى من الفوترة الإلكترونية</li>
              <li>رمز QR يحتوي على: اسم البائع، الرقم الضريبي، التاريخ، الإجمالي، ومبلغ الضريبة</li>
              <li>المنتجات المعفاة من الضريبة لا تُحسب عليها ضريبة القيمة المضافة</li>
              <li>يمكن تعيين إعفاء المنتج من الضريبة من صفحة إدارة المنتجات</li>
            </ul>
          </div>
        </div>
      )}

      {/* ===== POS Settings Section ===== */}
      {activeSection === 'pos' && (
        <div className="space-y-6">
          {/* Logo Upload */}
          <div className="bg-white rounded-xl border p-6 space-y-4">
            <h2 className="text-lg font-bold text-gray-800 flex items-center gap-2">
              <HiOutlinePhotograph className="text-bayan-green" />
              شعار الجمعية
            </h2>
            <p className="text-sm text-gray-500">يظهر الشعار في صفحة الدخول والقائمة الجانبية والفواتير</p>

            <div className="flex items-center gap-6">
              {logoPreview ? (
                <img
                  src={logoPreview}
                  alt="شعار الجمعية"
                  className="w-24 h-24 object-contain rounded-xl border border-gray-200 bg-gray-50 p-1"
                />
              ) : (
                <div className="w-24 h-24 rounded-xl border-2 border-dashed border-gray-300 flex items-center justify-center text-gray-400">
                  <HiOutlinePhotograph className="text-3xl" />
                </div>
              )}
              <div>
                <input
                  ref={logoInputRef}
                  type="file"
                  accept="image/*"
                  onChange={handleLogoUpload}
                  className="hidden"
                />
                <button
                  onClick={() => logoInputRef.current?.click()}
                  className="flex items-center gap-2 bg-bayan-green hover:bg-bayan-dark text-white px-6 py-2 rounded-lg transition-all"
                >
                  <HiOutlinePhotograph />
                  {logoPreview ? 'تغيير الشعار' : 'رفع شعار'}
                </button>
                <p className="text-xs text-gray-400 mt-2">PNG, JPG, SVG - يفضل خلفية شفافة</p>
              </div>
            </div>
          </div>

          {/* Payment Methods */}
          <div className="bg-white rounded-xl border p-6 space-y-4">
            <h2 className="text-lg font-bold text-gray-800 flex items-center gap-2">
              <HiOutlineCash className="text-bayan-green" />
              طرق الدفع
            </h2>
            <p className="text-sm text-gray-500">اختر طرق الدفع المتاحة في نقطة البيع</p>

            <div className="space-y-3">
              {[
                { key: 'cash', icon: HiOutlineCash, label: 'نقدي', desc: 'الدفع النقدي' },
                { key: 'card', icon: HiOutlineCreditCard, label: 'شبكة', desc: 'الدفع عبر الشبكة (يطلب رمز العملية)' },
                { key: 'transfer', icon: HiOutlineDeviceMobile, label: 'تحويل', desc: 'التحويل البنكي' },
              ].map(({ key, icon: Icon, label, desc }) => (
                <label
                  key={key}
                  className={`flex items-center gap-4 p-4 rounded-xl border-2 cursor-pointer transition-all ${
                    posSettings.paymentMethods[key]
                      ? 'border-bayan-green bg-bayan-light/30'
                      : 'border-gray-200 bg-gray-50 opacity-60'
                  }`}
                >
                  <div className="relative">
                    <input
                      type="checkbox"
                      checked={posSettings.paymentMethods[key]}
                      onChange={(e) => {
                        const updated = {
                          ...posSettings,
                          paymentMethods: {
                            ...posSettings.paymentMethods,
                            [key]: e.target.checked,
                          },
                        };
                        const enabledCount = Object.values(updated.paymentMethods).filter(Boolean).length;
                        if (enabledCount === 0) {
                          toast.error('يجب تفعيل طريقة دفع واحدة على الأقل');
                          return;
                        }
                        setPosSettings(updated);
                      }}
                      className="w-5 h-5 text-bayan-green rounded focus:ring-bayan-green"
                    />
                  </div>
                  <Icon className="text-2xl text-gray-600" />
                  <div>
                    <p className="font-medium text-gray-800">{label}</p>
                    <p className="text-xs text-gray-500">{desc}</p>
                  </div>
                </label>
              ))}
            </div>
          </div>

          {/* Donation Toggle */}
          <div className="bg-white rounded-xl border p-6 space-y-4">
            <h2 className="text-lg font-bold text-gray-800 flex items-center gap-2">
              <HiOutlineHeart className="text-purple-600" />
              خيار التبرع
            </h2>
            <label className="flex items-center gap-4 p-4 rounded-xl border-2 cursor-pointer transition-all border-gray-200">
              <input
                type="checkbox"
                checked={posSettings.showDonation}
                onChange={(e) => setPosSettings({ ...posSettings, showDonation: e.target.checked })}
                className="w-5 h-5 text-purple-600 rounded focus:ring-purple-500"
              />
              <div>
                <p className="font-medium text-gray-800">إظهار زر التبرع في نقطة البيع</p>
                <p className="text-xs text-gray-500">عند التعطيل، لن يظهر زر التبرع في شاشة نقطة البيع</p>
              </div>
            </label>
          </div>

          {/* Save POS Settings */}
          <div className="flex justify-end">
            <button
              onClick={handleSavePOSSettings}
              className="flex items-center gap-2 bg-bayan-green hover:bg-bayan-dark text-white px-8 py-3 rounded-xl transition-all font-bold"
            >
              <HiOutlineSave className="text-xl" />
              حفظ إعدادات نقطة البيع
            </button>
          </div>
        </div>
      )}

      {/* ===== Users Section ===== */}
      {activeSection === 'users' && (
        <>
          {/* Users Grid */}
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {users.map((user) => (
              <div
                key={user.id}
                className={`bg-white rounded-xl border p-6 ${!user.is_active ? 'opacity-50' : ''}`}
              >
                <div className="flex items-center gap-4">
                  <div className="w-14 h-14 bg-bayan-light rounded-full flex items-center justify-center">
                    <span className="text-xl font-bold text-bayan-green">
                      {user.full_name?.charAt(0) || '؟'}
                    </span>
                  </div>
                  <div className="flex-1">
                    <h3 className="font-bold text-gray-800">{user.full_name}</h3>
                    <p className="text-sm text-gray-500">@{user.username}</p>
                    <span className={`inline-block mt-1 text-xs px-2 py-0.5 rounded-full ${
                      user.role === 'admin'
                        ? 'bg-purple-100 text-purple-700'
                        : 'bg-blue-100 text-blue-700'
                    }`}>
                      {user.role === 'admin' ? 'مدير' : 'كاشير'}
                    </span>
                  </div>
                </div>

                <div className="flex items-center justify-between mt-4 pt-4 border-t">
                  <span className={`text-sm ${user.is_active ? 'text-green-600' : 'text-red-600'}`}>
                    {user.is_active ? '● نشط' : '● معطل'}
                  </span>
                  {user.id !== currentUser.id && (
                    <div className="flex gap-2">
                      <button
                        onClick={() => handleToggleActive(user)}
                        className={`p-2 rounded-lg transition-all ${
                          user.is_active
                            ? 'text-orange-600 hover:bg-orange-50'
                            : 'text-green-600 hover:bg-green-50'
                        }`}
                        title={user.is_active ? 'تعطيل' : 'تفعيل'}
                      >
                        <HiOutlineShieldCheck />
                      </button>
                      <button
                        onClick={() => handleEdit(user)}
                        className="p-2 text-blue-600 hover:bg-blue-50 rounded-lg transition-all"
                        title="تعديل"
                      >
                        <HiOutlinePencil />
                      </button>
                      <button
                        onClick={() => handleDelete(user.id)}
                        className="p-2 text-red-600 hover:bg-red-50 rounded-lg transition-all"
                        title="حذف"
                      >
                        <HiOutlineTrash />
                      </button>
                    </div>
                  )}
                </div>
              </div>
            ))}
          </div>
        </>
      )}

      {/* User Form Modal */}
      {showForm && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-2xl w-full max-w-md p-6">
            <h2 className="text-xl font-bold text-gray-800 mb-4 flex items-center gap-2">
              <HiOutlineUsers className="text-bayan-green" />
              {editingUser ? 'تعديل المستخدم' : 'إضافة مستخدم جديد'}
            </h2>

            <form onSubmit={handleSubmit} className="space-y-4">
              {!editingUser && (
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">اسم المستخدم *</label>
                  <input
                    type="text"
                    value={form.username}
                    onChange={(e) => setForm({ ...form, username: e.target.value })}
                    className="w-full px-4 py-2 rounded-lg border border-gray-300 focus:ring-2 focus:ring-bayan-green outline-none"
                    placeholder="اسم المستخدم (بالإنجليزية)"
                    dir="ltr"
                  />
                </div>
              )}

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">الاسم الكامل *</label>
                <input
                  type="text"
                  value={form.full_name}
                  onChange={(e) => setForm({ ...form, full_name: e.target.value })}
                  className="w-full px-4 py-2 rounded-lg border border-gray-300 focus:ring-2 focus:ring-bayan-green outline-none"
                  placeholder="الاسم الكامل"
                />
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  كلمة المرور {editingUser ? '(اتركها فارغة إن لم ترد التغيير)' : '*'}
                </label>
                <input
                  type="password"
                  value={form.password}
                  onChange={(e) => setForm({ ...form, password: e.target.value })}
                  className="w-full px-4 py-2 rounded-lg border border-gray-300 focus:ring-2 focus:ring-bayan-green outline-none"
                  placeholder="كلمة المرور"
                />
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">الصلاحية</label>
                <select
                  value={form.role}
                  onChange={(e) => setForm({ ...form, role: e.target.value })}
                  className="w-full px-4 py-2 rounded-lg border border-gray-300 focus:ring-2 focus:ring-bayan-green outline-none"
                >
                  <option value="cashier">كاشير (متطوع)</option>
                  <option value="admin">مدير</option>
                </select>
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">الفرع</label>
                <select
                  value={form.location_id}
                  onChange={(e) => setForm({ ...form, location_id: e.target.value })}
                  className="w-full px-4 py-2 rounded-lg border border-gray-300 focus:ring-2 focus:ring-bayan-green outline-none"
                >
                  <option value="">— كل الفروع (مدير) —</option>
                  {locations.map((loc) => (
                    <option key={loc.id} value={loc.id}>{loc.name}</option>
                  ))}
                </select>
                <p className="text-xs text-gray-400 mt-1">الكاشير المُعيّن لفرع يبيع في صناديق فرعه فقط</p>
              </div>

              <div className="flex gap-3 pt-2">
                <button
                  type="submit"
                  className="flex-1 bg-bayan-green hover:bg-bayan-dark text-white font-bold py-3 rounded-xl transition-all"
                >
                  {editingUser ? 'تحديث' : 'إضافة'}
                </button>
                <button
                  type="button"
                  onClick={resetForm}
                  className="px-6 py-3 bg-gray-100 hover:bg-gray-200 text-gray-700 rounded-xl transition-all"
                >
                  إلغاء
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
