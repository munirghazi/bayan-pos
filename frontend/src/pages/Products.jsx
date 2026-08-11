import { useState, useEffect, useRef } from 'react';
import { productsAPI, suppliersAPI, uomAPI, apiError } from '../services/api';
import { SarIcon } from '../components/SarIcon';
import toast from 'react-hot-toast';
import {
  HiOutlinePlus,
  HiOutlinePencil,
  HiOutlineTrash,
  HiOutlinePhotograph,
  HiOutlineTag,
} from 'react-icons/hi';

export default function Products() {
  const [products, setProducts] = useState([]);
  const [categories, setCategories] = useState([]);
  const [suppliers, setSuppliers] = useState([]);
  const [units, setUnits] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [showCategoryForm, setShowCategoryForm] = useState(false);
  const [editingProduct, setEditingProduct] = useState(null);
  const [categoryName, setCategoryName] = useState('');
  const [editingCategory, setEditingCategory] = useState(null);
  const submittingRef = useRef(false);  // prevents duplicate submits

  const [form, setForm] = useState({
    name: '',
    price: '',
    category_id: '',
    stock: '',
    barcode: '',
    cost_price: '',
    unit: '',
    reorder_level: '',
    default_supplier_id: '',
    uom_id: '',
    purchase_uom_id: '',
    sales_uom_id: '',
    image_url: '',
    is_tax_exempt: false,
  });

  const user = JSON.parse(localStorage.getItem('user') || '{}');

  useEffect(() => {
    loadData();
    suppliersAPI.getAll().then((r) => setSuppliers(r.data)).catch(() => {});
    uomAPI.units().then((r) => setUnits(r.data)).catch(() => {});
  }, []);

  const loadData = async () => {
    try {
      const [prodRes, catRes] = await Promise.all([
        user.role === 'admin' ? productsAPI.getAllAdmin() : productsAPI.getAll(),
        productsAPI.getCategories(),
      ]);
      setProducts(prodRes.data);
      setCategories(catRes.data);
    } catch (err) {
      toast.error('خطأ في تحميل البيانات');
    } finally {
      setLoading(false);
    }
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!form.name || !form.price) {
      toast.error('الرجاء إدخال اسم المنتج والسعر');
      return;
    }
    if (submittingRef.current) return;
    submittingRef.current = true;

    try {
      const data = {
        name: form.name,
        price: parseFloat(form.price),
        category_id: form.category_id ? parseInt(form.category_id) : null,
        stock: parseFloat(form.stock) || 0,
        barcode: form.barcode || null,
        cost_price: parseFloat(form.cost_price) || 0,
        unit: form.unit || null,
        reorder_level: parseFloat(form.reorder_level) || 0,
        default_supplier_id: form.default_supplier_id ? parseInt(form.default_supplier_id) : null,
        uom_id: form.uom_id ? parseInt(form.uom_id) : null,
        purchase_uom_id: form.purchase_uom_id ? parseInt(form.purchase_uom_id) : null,
        sales_uom_id: form.sales_uom_id ? parseInt(form.sales_uom_id) : null,
        image_url: form.image_url || null,
        is_tax_exempt: form.is_tax_exempt,
      };

      if (editingProduct) {
        await productsAPI.update(editingProduct.id, data);
        toast.success('تم تحديث المنتج');
      } else {
        await productsAPI.create(data);
        toast.success('تم إضافة المنتج');
      }

      resetForm();
      loadData();
    } catch (err) {
      toast.error(apiError(err, 'خطأ في حفظ المنتج'));
    } finally {
      submittingRef.current = false;
    }
  };

  const handleDelete = async (id) => {
    if (!confirm('هل أنت متأكد من حذف هذا المنتج؟')) return;
    try {
      await productsAPI.delete(id);
      toast.success('تم حذف المنتج');
      loadData();
    } catch (err) {
      toast.error('خطأ في حذف المنتج');
    }
  };

  const handleEdit = (product) => {
    setEditingProduct(product);
    setForm({
      name: product.name,
      price: product.price.toString(),
      category_id: product.category_id?.toString() || '',
      stock: product.stock.toString(),
      barcode: product.barcode || '',
      cost_price: product.cost_price != null ? product.cost_price.toString() : '',
      unit: product.unit || '',
      reorder_level: product.reorder_level != null ? product.reorder_level.toString() : '',
      default_supplier_id: product.default_supplier_id?.toString() || '',
      uom_id: product.uom_id?.toString() || '',
      purchase_uom_id: product.purchase_uom_id?.toString() || '',
      sales_uom_id: product.sales_uom_id?.toString() || '',
      image_url: product.image_url || '',
      is_tax_exempt: product.is_tax_exempt || false,
    });
    setShowForm(true);
  };

  const resetForm = () => {
    setForm({ name: '', price: '', category_id: '', stock: '', barcode: '', cost_price: '', unit: '', reorder_level: '', default_supplier_id: '', uom_id: '', purchase_uom_id: '', sales_uom_id: '', image_url: '', is_tax_exempt: false });
    setEditingProduct(null);
    setShowForm(false);
  };

  const handleImageUpload = async (e) => {
    const file = e.target.files[0];
    if (!file) return;
    try {
      const res = await productsAPI.uploadImage(file);
      setForm({ ...form, image_url: res.data.url });
      toast.success('تم رفع الصورة');
    } catch (err) {
      toast.error('خطأ في رفع الصورة');
    }
  };

  const handleCategorySubmit = async () => {
    if (!categoryName.trim()) return;
    if (submittingRef.current) return;
    submittingRef.current = true;
    try {
      if (editingCategory) {
        await productsAPI.updateCategory(editingCategory.id, { name: categoryName });
        toast.success('تم تحديث التصنيف');
      } else {
        await productsAPI.createCategory({ name: categoryName });
        toast.success('تم إضافة التصنيف');
      }
      setCategoryName('');
      setEditingCategory(null);
      setShowCategoryForm(false);
      loadData();
    } catch (err) {
      toast.error('خطأ في حفظ التصنيف');
    } finally {
      submittingRef.current = false;
    }
  };

  const handleDeleteCategory = async (id) => {
    if (!confirm('هل أنت متأكد من حذف هذا التصنيف؟')) return;
    try {
      await productsAPI.deleteCategory(id);
      toast.success('تم حذف التصنيف');
      loadData();
    } catch (err) {
      toast.error('خطأ في حذف التصنيف');
    }
  };

  if (loading) {
    const baseUom = units.find((u) => u.id === parseInt(form.uom_id));
  const sameCatUnits = baseUom ? units.filter((u) => u.category_id === baseUom.category_id) : [];

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
          <h1 className="text-2xl font-bold text-gray-800">إدارة المنتجات</h1>
          <p className="text-gray-500 mt-1">{products.length} منتج</p>
        </div>
        {user.role === 'admin' && (
          <div className="flex gap-3">
            <button
              onClick={() => { setShowCategoryForm(true); setEditingCategory(null); setCategoryName(''); }}
              className="flex items-center gap-2 bg-gray-100 hover:bg-gray-200 text-gray-700 px-4 py-2 rounded-lg transition-all"
            >
              <HiOutlineTag />
              التصنيفات
            </button>
            <button
              onClick={() => { resetForm(); setShowForm(true); }}
              className="flex items-center gap-2 bg-bayan-green hover:bg-bayan-dark text-white px-6 py-2 rounded-lg transition-all"
            >
              <HiOutlinePlus />
              إضافة منتج
            </button>
          </div>
        )}
      </div>

      {/* Products Grid */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-4">
        {products.map((product) => (
          <div
            key={product.id}
            className={`bg-white rounded-xl border shadow-sm overflow-hidden ${
              !product.is_active ? 'opacity-50' : ''
            }`}
          >
            {product.image_url ? (
              <img
                src={product.image_url}
                alt={product.name}
                className="w-full h-40 object-cover"
              />
            ) : (
              <div className="w-full h-40 bg-gray-100 flex items-center justify-center">
                <HiOutlinePhotograph className="text-4xl text-gray-300" />
              </div>
            )}
            <div className="p-4">
              <div className="flex items-start justify-between">
                <div>
                  <h3 className="font-bold text-gray-800">{product.name}</h3>
                  <div className="flex flex-wrap gap-1 mt-1">
                    {product.category && (
                      <span className="text-xs bg-bayan-light text-bayan-green px-2 py-0.5 rounded-full">
                        {product.category.name}
                      </span>
                    )}
                    {product.is_tax_exempt && (
                      <span className="text-xs bg-orange-100 text-orange-700 px-2 py-0.5 rounded-full">
                        معفى من الضريبة
                      </span>
                    )}
                  </div>
                </div>
                <p className="font-bold text-bayan-green text-lg">{product.price.toFixed(2)} <SarIcon size={15} /></p>
              </div>
              <div className="flex items-center justify-between mt-3">
                <span className={`text-sm ${product.is_low_stock ? 'text-red-500 font-bold' : 'text-gray-500'}`}>
                  المخزون: {product.stock}
                  {product.is_low_stock && (
                    <span className="mr-2 text-xs bg-red-100 text-red-700 px-2 py-0.5 rounded-full">منخفض</span>
                  )}
                </span>
                {user.role === 'admin' && (
                  <div className="flex gap-2">
                    <button
                      onClick={() => handleEdit(product)}
                      className="p-2 text-blue-600 hover:bg-blue-50 rounded-lg transition-all"
                    >
                      <HiOutlinePencil />
                    </button>
                    <button
                      onClick={() => handleDelete(product.id)}
                      className="p-2 text-red-600 hover:bg-red-50 rounded-lg transition-all"
                    >
                      <HiOutlineTrash />
                    </button>
                  </div>
                )}
              </div>
            </div>
          </div>
        ))}
      </div>

      {products.length === 0 && (
        <div className="text-center py-16 text-gray-400">
          <HiOutlinePhotograph className="text-6xl mx-auto mb-4" />
          <p className="text-lg">لا توجد منتجات بعد</p>
          <p className="text-sm mt-1">اضغط على "إضافة منتج" للبدء</p>
        </div>
      )}

      {/* Product Form Modal */}
      {showForm && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-2xl w-full max-w-lg p-6 max-h-[90vh] overflow-auto">
            <h2 className="text-xl font-bold text-gray-800 mb-4">
              {editingProduct ? 'تعديل المنتج' : 'إضافة منتج جديد'}
            </h2>

            <form onSubmit={handleSubmit} className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">اسم المنتج *</label>
                <input
                  type="text"
                  value={form.name}
                  onChange={(e) => setForm({ ...form, name: e.target.value })}
                  className="w-full px-4 py-2 rounded-lg border border-gray-300 focus:ring-2 focus:ring-bayan-green outline-none"
                  placeholder="اسم المنتج"
                />
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">السعر (<SarIcon size={12} />) *</label>
                  <input
                    type="number"
                    step="0.01"
                    value={form.price}
                    onChange={(e) => setForm({ ...form, price: e.target.value })}
                    className="w-full px-4 py-2 rounded-lg border border-gray-300 focus:ring-2 focus:ring-bayan-green outline-none"
                    placeholder="0.00"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">الكمية</label>
                  <input
                    type="number"
                    value={form.stock}
                    onChange={(e) => setForm({ ...form, stock: e.target.value })}
                    className="w-full px-4 py-2 rounded-lg border border-gray-300 focus:ring-2 focus:ring-bayan-green outline-none"
                    placeholder="0"
                  />
                </div>
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">التصنيف</label>
                <select
                  value={form.category_id}
                  onChange={(e) => setForm({ ...form, category_id: e.target.value })}
                  className="w-full px-4 py-2 rounded-lg border border-gray-300 focus:ring-2 focus:ring-bayan-green outline-none"
                >
                  <option value="">بدون تصنيف</option>
                  {categories.map((cat) => (
                    <option key={cat.id} value={cat.id}>{cat.name}</option>
                  ))}
                </select>
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">سعر التكلفة</label>
                  <input type="number" step="0.01" value={form.cost_price}
                    onChange={(e) => setForm({ ...form, cost_price: e.target.value })}
                    className="w-full px-4 py-2 rounded-lg border border-gray-300 focus:ring-2 focus:ring-bayan-green outline-none" placeholder="0.00" />
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">الوحدة</label>
                  <input type="text" value={form.unit}
                    onChange={(e) => setForm({ ...form, unit: e.target.value })}
                    className="w-full px-4 py-2 rounded-lg border border-gray-300 focus:ring-2 focus:ring-bayan-green outline-none" placeholder="حبة / كرتون / كجم" />
                </div>
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">حد إعادة الطلب</label>
                  <input type="number" value={form.reorder_level}
                    onChange={(e) => setForm({ ...form, reorder_level: e.target.value })}
                    className="w-full px-4 py-2 rounded-lg border border-gray-300 focus:ring-2 focus:ring-bayan-green outline-none" placeholder="0" />
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">الباركود</label>
                  <input type="text" value={form.barcode}
                    onChange={(e) => setForm({ ...form, barcode: e.target.value })}
                    className="w-full px-4 py-2 rounded-lg border border-gray-300 focus:ring-2 focus:ring-bayan-green outline-none" dir="ltr" placeholder="—" />
                </div>
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">المورّد الافتراضي</label>
                <select value={form.default_supplier_id}
                  onChange={(e) => setForm({ ...form, default_supplier_id: e.target.value })}
                  className="w-full px-4 py-2 rounded-lg border border-gray-300 focus:ring-2 focus:ring-bayan-green outline-none">
                  <option value="">بدون</option>
                  {suppliers.map((sup) => (
                    <option key={sup.id} value={sup.id}>{sup.name}{sup.is_compliant ? '' : ' (غير متوافق)'}</option>
                  ))}
                </select>
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">وحدة القياس الأساسية (المخزون)</label>
                <select value={form.uom_id}
                  onChange={(e) => setForm({ ...form, uom_id: e.target.value, purchase_uom_id: '', sales_uom_id: '' })}
                  className="w-full px-4 py-2 rounded-lg border border-gray-300 focus:ring-2 focus:ring-bayan-green outline-none">
                  <option value="">بدون</option>
                  {units.map((u) => (<option key={u.id} value={u.id}>{u.name}</option>))}
                </select>
              </div>
              {form.uom_id && (
                <div className="grid grid-cols-2 gap-4">
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">وحدة الشراء</label>
                    <select value={form.purchase_uom_id}
                      onChange={(e) => setForm({ ...form, purchase_uom_id: e.target.value })}
                      className="w-full px-4 py-2 rounded-lg border border-gray-300 focus:ring-2 focus:ring-bayan-green outline-none">
                      <option value="">مثل الأساسية</option>
                      {sameCatUnits.map((u) => (<option key={u.id} value={u.id}>{u.name}</option>))}
                    </select>
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">وحدة البيع</label>
                    <select value={form.sales_uom_id}
                      onChange={(e) => setForm({ ...form, sales_uom_id: e.target.value })}
                      className="w-full px-4 py-2 rounded-lg border border-gray-300 focus:ring-2 focus:ring-bayan-green outline-none">
                      <option value="">مثل الأساسية</option>
                      {sameCatUnits.map((u) => (<option key={u.id} value={u.id}>{u.name}</option>))}
                    </select>
                  </div>
                </div>
              )}

              {/* Tax exempt toggle */}
              <div className="flex items-center gap-3 p-3 rounded-lg border border-gray-200 bg-gray-50">
                <label className="relative inline-flex items-center cursor-pointer">
                  <input
                    type="checkbox"
                    checked={form.is_tax_exempt}
                    onChange={(e) => setForm({ ...form, is_tax_exempt: e.target.checked })}
                    className="sr-only peer"
                  />
                  <div className="w-11 h-6 bg-gray-200 peer-focus:outline-none peer-focus:ring-2 peer-focus:ring-orange-300 rounded-full peer peer-checked:after:translate-x-full rtl:peer-checked:after:-translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:start-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-orange-500"></div>
                </label>
                <div>
                  <p className="text-sm font-medium text-gray-700">معفى من ضريبة القيمة المضافة</p>
                  <p className="text-xs text-gray-400">تفعيل هذا الخيار يعني أن المنتج لا تُحسب عليه ضريبة 15%</p>
                </div>
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">صورة المنتج</label>
                <div className="flex items-center gap-3">
                  <input
                    type="file"
                    accept="image/*"
                    onChange={handleImageUpload}
                    className="flex-1 text-sm"
                  />
                  {form.image_url && (
                    <img src={form.image_url} alt="preview" className="w-16 h-16 object-cover rounded-lg" />
                  )}
                </div>
                <p className="text-xs text-gray-400 mt-1">أو أدخل رابط الصورة مباشرة:</p>
                <input
                  type="text"
                  value={form.image_url}
                  onChange={(e) => setForm({ ...form, image_url: e.target.value })}
                  className="w-full px-4 py-2 rounded-lg border border-gray-300 focus:ring-2 focus:ring-bayan-green outline-none mt-1 text-sm"
                  placeholder="رابط الصورة"
                  dir="ltr"
                />
              </div>

              <div className="flex gap-3 pt-4">
                <button
                  type="submit"
                  className="flex-1 bg-bayan-green hover:bg-bayan-dark text-white font-bold py-3 rounded-xl transition-all"
                >
                  {editingProduct ? 'تحديث' : 'إضافة'}
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

      {/* Category Form Modal */}
      {showCategoryForm && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-2xl w-full max-w-md p-6">
            <h2 className="text-xl font-bold text-gray-800 mb-4">إدارة التصنيفات</h2>

            {/* Add category */}
            <div className="flex gap-2 mb-4">
              <input
                type="text"
                value={categoryName}
                onChange={(e) => setCategoryName(e.target.value)}
                className="flex-1 px-4 py-2 rounded-lg border border-gray-300 focus:ring-2 focus:ring-bayan-green outline-none"
                placeholder="اسم التصنيف"
              />
              <button
                onClick={handleCategorySubmit}
                className="bg-bayan-green hover:bg-bayan-dark text-white px-4 py-2 rounded-lg transition-all"
              >
                {editingCategory ? 'تحديث' : 'إضافة'}
              </button>
            </div>

            {/* Categories list */}
            <div className="space-y-2 max-h-64 overflow-auto">
              {categories.map((cat) => (
                <div key={cat.id} className="flex items-center justify-between p-3 bg-gray-50 rounded-lg">
                  <span className="font-medium">{cat.name}</span>
                  <div className="flex gap-2">
                    <button
                      onClick={() => { setEditingCategory(cat); setCategoryName(cat.name); }}
                      className="p-1 text-blue-600 hover:bg-blue-50 rounded"
                    >
                      <HiOutlinePencil />
                    </button>
                    <button
                      onClick={() => handleDeleteCategory(cat.id)}
                      className="p-1 text-red-600 hover:bg-red-50 rounded"
                    >
                      <HiOutlineTrash />
                    </button>
                  </div>
                </div>
              ))}
              {categories.length === 0 && (
                <p className="text-center text-gray-400 py-4">لا توجد تصنيفات</p>
              )}
            </div>

            <button
              onClick={() => { setShowCategoryForm(false); setEditingCategory(null); setCategoryName(''); }}
              className="w-full mt-4 py-2 bg-gray-100 hover:bg-gray-200 text-gray-700 rounded-xl transition-all"
            >
              إغلاق
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
