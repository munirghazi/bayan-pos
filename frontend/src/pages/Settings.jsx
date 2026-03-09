import { useState, useEffect } from 'react';
import { authAPI } from '../services/api';
import { getZATCASettings, saveZATCASettings } from '../utils/zatca';
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
} from 'react-icons/hi';

export default function Settings() {
  const [users, setUsers] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [editingUser, setEditingUser] = useState(null);
  const [activeSection, setActiveSection] = useState('profile');

  const [form, setForm] = useState({
    username: '',
    password: '',
    full_name: '',
    role: 'cashier',
  });

  // Company profile & ZATCA settings combined
  const [profileForm, setProfileForm] = useState(getZATCASettings());

  const currentUser = JSON.parse(localStorage.getItem('user') || '{}');

  useEffect(() => {
    loadUsers();
  }, []);

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

    if (editingUser) {
      try {
        const data = {
          full_name: form.full_name,
          role: form.role,
        };
        if (form.password) {
          data.password = form.password;
        }
        await authAPI.updateUser(editingUser.id, data);
        toast.success('تم تحديث المستخدم');
        resetForm();
        loadUsers();
      } catch (err) {
        toast.error(err.response?.data?.detail || 'خطأ في التحديث');
      }
    } else {
      if (!form.username || !form.password || !form.full_name) {
        toast.error('الرجاء تعبئة جميع الحقول المطلوبة');
        return;
      }
      try {
        await authAPI.createUser(form);
        toast.success('تم إضافة المستخدم');
        resetForm();
        loadUsers();
      } catch (err) {
        toast.error(err.response?.data?.detail || 'خطأ في الإضافة');
      }
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
    });
    setShowForm(true);
  };

  const resetForm = () => {
    setForm({ username: '', password: '', full_name: '', role: 'cashier' });
    setEditingUser(null);
    setShowForm(false);
  };

  const handleSaveProfile = () => {
    if (!profileForm.vatNumber || profileForm.vatNumber.length !== 15) {
      toast.error('الرقم الضريبي يجب أن يكون 15 رقم');
      return;
    }
    saveZATCASettings(profileForm);
    toast.success('تم حفظ بيانات الجمعية والإعدادات الضريبية');
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
      <div className="flex bg-gray-100 rounded-lg p-1 w-fit">
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

              {/* Static info */}
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">الموقع الإلكتروني</label>
                <a
                  href="https://www.bayanmakkah.org.sa/"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="block px-4 py-3 rounded-lg border border-gray-200 bg-gray-50 text-bayan-green hover:underline"
                >
                  www.bayanmakkah.org.sa
                </a>
              </div>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">المدينة</label>
                <p className="px-4 py-3 rounded-lg border border-gray-200 bg-gray-50 text-gray-800">مكة المكرمة</p>
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-2">الدولة</label>
                <p className="px-4 py-3 rounded-lg border border-gray-200 bg-gray-50 text-gray-800">المملكة العربية السعودية</p>
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
