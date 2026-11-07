import { useState, useEffect, useRef, useMemo } from 'react';
import { can } from '../utils/perms';
import { productsAPI, suppliersAPI, uomAPI, apiError } from '../services/api';
import { Button, EmptyState, Field, Input, Select, MoneyInput, SwitchRow } from '../components/ui';

import PrintLabelsModal from '../components/PrintLabelsModal';
import ArchiveDialog from '../components/ArchiveDialog';
import { SarIcon } from '../components/SarIcon';
import toast from 'react-hot-toast';
import {
  HiOutlinePlus,
  HiOutlinePencil,
  HiOutlineTrash,
  HiOutlinePhotograph,
  HiOutlineTag,
  HiOutlinePrinter,
} from 'react-icons/hi';

const FIELD_CLS = 'w-full min-h-[48px] px-4 rounded-xl border border-gray-300 bg-white text-base outline-none focus:border-bayan-green focus:ring-2 focus:ring-bayan-green/30';

export default function Products({ embedded = false }) {
  const [products, setProducts] = useState([]);
  const [categories, setCategories] = useState([]);
  const [suppliers, setSuppliers] = useState([]);
  const [units, setUnits] = useState([]);
  const [uomCategories, setUomCategories] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showForm, setShowForm] = useState(false);
  const [showCategoryForm, setShowCategoryForm] = useState(false);
  const [editingProduct, setEditingProduct] = useState(null);
  const [categoryName, setCategoryName] = useState('');
  const [editingCategory, setEditingCategory] = useState(null);
  const submittingRef = useRef(false);  // prevents duplicate submits
  const [showArchived, setShowArchived] = useState(false);

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
    uom_category_id: '',
    uom_id: '',
    purchase_uom_id: '',
    sales_uom_id: '',
    image_url: '',
    is_tax_exempt: false,
    is_kit: false,
    components: [],
  });

  const user = JSON.parse(localStorage.getItem('user') || '{}');

  useEffect(() => {
    loadData();
    suppliersAPI.getAll().then((r) => setSuppliers(r.data)).catch(() => {});
    uomAPI.units().then((r) => setUnits(r.data)).catch(() => {});
    uomAPI.categories().then((r) => setUomCategories(r.data)).catch(() => {});
  }, []);

  const loadData = async () => {
    try {
      const [prodRes, catRes] = await Promise.all([
        can('products') ? productsAPI.getAllAdmin(true) : productsAPI.getAll(),
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
        is_kit: form.is_kit,
        components: form.is_kit
          ? form.components
              .filter((c) => c.product_id && parseFloat(c.quantity) > 0)
              .map((c) => ({ product_id: parseInt(c.product_id), quantity: parseFloat(c.quantity) }))
          : null,
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

  const [printItems, setPrintItems] = useState(null);
  const [quickSupplier, setQuickSupplier] = useState(null);
  // Enter = next field (tester: Enter saved and closed the form). Ctrl+Enter saves.
  // a new product starts on the basic counting unit ("حبة"), so purchase / sale units are usable at once
  useEffect(() => {
    if (!showForm || editingProduct || form.uom_id || !units.length) return;
    const countCat = uomCategories.find((c) => c.name === 'عدد') || uomCategories[0];
    const base = units.find((u) => countCat && u.category_id === countCat.id && u.is_reference);
    if (base) setForm((f) => ({ ...f, uom_id: String(base.id), uom_category_id: String(base.category_id) }));
  }, [showForm, editingProduct, units, uomCategories]); // eslint-disable-line react-hooks/exhaustive-deps

  const unitHint = (id) => {
    if (!id || !form.uom_id) return undefined;
    const u = units.find((x) => String(x.id) === String(id));
    const base = units.find((x) => String(x.id) === String(form.uom_id));
    if (!u || !base || !u.factor || !base.factor) return undefined;
    const n = u.factor / base.factor;
    return `${u.name} = ${+n.toFixed(3)} ${base.name}`;
  };
  const enterToNext = (e) => {
    if (e.key !== 'Enter' || e.target.tagName === 'TEXTAREA' || e.target.tagName === 'BUTTON') return;
    if (e.ctrlKey || e.metaKey) { e.preventDefault(); e.currentTarget.requestSubmit(); return; }   // Ctrl+Enter saves
    if (e.target.dataset?.enter === 'own') return;           // field handles Enter itself
    e.preventDefault();
    const fields = Array.from(e.currentTarget.querySelectorAll('input, select, textarea, button[type=submit]'))
      .filter((el) => !el.disabled && el.type !== 'file' && el.type !== 'hidden' && el.offsetParent !== null);
    const i = fields.indexOf(e.target);
    const next = fields[i + 1];
    if (next) { next.focus(); if (next.select && next.tagName === 'INPUT') next.select(); }
  };
  const saveQuickSupplier = async () => {
    const name = (quickSupplier?.name || '').trim();
    if (!name) { toast.error('أدخل اسم المورّد'); return; }
    try {
      const { data } = await suppliersAPI.create({ name });
      setSuppliers((list) => [...list, data]);
      setForm((f) => ({ ...f, default_supplier_id: String(data.id) }));
      setQuickSupplier(null);
      toast.success(`تمت إضافة المورّد «${name}» واختياره`);
    } catch (e) { toast.error(apiError(e, 'تعذّرت إضافة المورّد')); }
  };

  const visibleProducts = useMemo(() => products.filter((p) => (showArchived ? !p.is_active : p.is_active !== false)), [products, showArchived]);
  const archivedCount = useMemo(() => products.filter((p) => p.is_active === false).length, [products]);
  const groupedProducts = useMemo(() => {
    const map = {};
    visibleProducts.forEach((pr) => {
      const key = pr.category?.name || 'بدون تصنيف';
      (map[key] = map[key] || []).push(pr);
    });
    return Object.entries(map).sort((a, b) => {
      if (a[0] === 'بدون تصنيف') return 1;
      if (b[0] === 'بدون تصنيف') return -1;
      return a[0].localeCompare(b[0], 'ar');
    });
  }, [visibleProducts]);

  const printLabels = async (ids) => {
    try {
      const { data } = await productsAPI.ensureBarcodes(ids);
      if (!data.length) { toast.error('لا أصناف للطباعة'); return; }
      setPrintItems(data.map((d) => ({ name: d.name, barcode: d.barcode, price: d.price, qty: 1 })));
    } catch (e) { toast.error(apiError(e, 'تعذّر تجهيز الباركود')); }
  };

  // delete / archive goes through a dialog that shows the consequences
  const [archiving, setArchiving] = useState(null);
  const handleDelete = (id) => setArchiving(products.find((p) => p.id === id) || null);
  const restore = async (p) => {
    try { await productsAPI.restore(p.id); toast.success(`تمت استعادة «${p.name}»`); loadData(); }
    catch (e) { toast.error(apiError(e, 'تعذّرت الاستعادة')); }
  };

  const handleEdit = (product) => {
    setEditingProduct(product);
    setForm({
      name: product.name,
      price: Number(product.price).toFixed(2),
      category_id: product.category_id?.toString() || '',
      stock: product.stock.toString(),
      barcode: product.barcode || '',
      cost_price: product.cost_price != null ? Number(product.cost_price).toFixed(2) : '',
      unit: product.unit || '',
      reorder_level: product.reorder_level != null ? product.reorder_level.toString() : '',
      default_supplier_id: product.default_supplier_id?.toString() || '',
      uom_category_id: (() => { const u = units.find((x) => x.id === product.uom_id); return u ? u.category_id.toString() : ''; })(),
      uom_id: product.uom_id?.toString() || '',
      purchase_uom_id: product.purchase_uom_id?.toString() || '',
      sales_uom_id: product.sales_uom_id?.toString() || '',
      image_url: product.image_url || '',
      is_tax_exempt: product.is_tax_exempt || false,
      is_kit: product.is_kit || false,
      components: (product.components || []).map((c) => ({
        product_id: c.product_id.toString(), quantity: c.quantity.toString(),
      })),
    });
    setShowForm(true);
  };

  const resetForm = () => {
    setForm({ name: '', price: '', category_id: '', stock: '', barcode: '', cost_price: '', unit: '', reorder_level: '', default_supplier_id: '', uom_category_id: '', uom_id: '', purchase_uom_id: '', sales_uom_id: '', image_url: '', is_tax_exempt: false, is_kit: false, components: [] });
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
    return (
      <div className="flex items-center justify-center h-full">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-bayan-green"></div>
      </div>
    );
  }

  const catUnits = form.uom_category_id
    ? units.filter((u) => u.category_id === parseInt(form.uom_category_id))
    : [];

  return (
    <div className="space-y-5">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          {!embedded && <h1 className="text-2xl font-bold text-gray-800">إدارة المنتجات</h1>}
          <p className="text-gray-500 mt-1 flex items-center gap-3">
            {showArchived ? `${visibleProducts.length} منتج مؤرشف` : `${visibleProducts.length} منتج`}
            {can('products') && (archivedCount > 0 || showArchived) && (
              <button onClick={() => setShowArchived(!showArchived)} className="text-sm text-bayan-green hover:underline">
                {showArchived ? '← العودة للمنتجات النشطة' : `عرض المؤرشفة (${archivedCount})`}
              </button>
            )}
          </p>
        </div>
        {can('products') && (
          <div className="flex gap-3">
            <Button variant="secondary" icon={<HiOutlinePrinter />} onClick={() => printLabels(visibleProducts.map((p) => p.id))}>طباعة ملصقات</Button>
            <Button variant="secondary" icon={<HiOutlineTag />} onClick={() => { setShowCategoryForm(true); setEditingCategory(null); setCategoryName(''); }}>التصنيفات</Button>
            <Button variant="primary" icon={<HiOutlinePlus />} onClick={() => { resetForm(); setShowForm(true); }}>إضافة منتج</Button>
          </div>
        )}
      </div>

      {/* Products Grid */}
      {groupedProducts.map(([cat, items]) => (
        <div key={cat} className="space-y-3">
          <div className="flex items-center gap-3">
            <h3 className="text-xl font-extrabold text-gray-800 whitespace-nowrap">{cat}</h3>
            <span className="text-sm font-medium text-bayan-green bg-bayan-light px-2.5 py-0.5 rounded-full">{items.length}</span>
            <div className="flex-1 h-px bg-gray-200" />
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
            {items.map((product) => (
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
                  المخزون: {product.is_kit ? (product.available_stock ?? 0) : product.stock}
                  {product.is_low_stock && (
                    <span className="mr-2 text-xs bg-red-100 text-red-700 px-2 py-0.5 rounded-full">منخفض</span>
                  )}
                </span>
                {can('products') && (
                  <div className="flex gap-2">
                    <button
                      onClick={() => printLabels([product.id])}
                      className="p-2 text-gray-600 hover:bg-gray-100 rounded-lg transition-all"
                      title="طباعة ملصق باركود"
                    >
                      <HiOutlinePrinter />
                    </button>
                    <button
                      onClick={() => handleEdit(product)}
                      className="p-2 text-blue-600 hover:bg-blue-50 rounded-lg transition-all"
                    >
                      <HiOutlinePencil />
                    </button>
                    {product.is_active === false ? (
                      <button onClick={() => restore(product)} className="px-3 py-1.5 text-sm text-bayan-green hover:bg-bayan-light/40 rounded-lg" title="استعادة">
                        استعادة
                      </button>
                    ) : (
                      <button
                        onClick={() => handleDelete(product.id)}
                        className="p-2 text-red-600 hover:bg-red-50 rounded-lg transition-all"
                        title="حذف أو أرشفة"
                      >
                        <HiOutlineTrash />
                      </button>
                    )}
                  </div>
                )}
              </div>
            </div>
          </div>
            ))}
          </div>
        </div>
      ))}

      {visibleProducts.length === 0 && !showArchived && (
        <EmptyState icon={<HiOutlinePhotograph />} title="لا توجد منتجات بعد"
          subtitle="اضغط على «إضافة منتج» للبدء"
          action={can('products') ? <Button icon={<HiOutlinePlus />} onClick={() => { resetForm(); setShowForm(true); }}>إضافة منتج</Button> : null} />
      )}

      {archiving && (
        <ArchiveDialog title="حذف أو أرشفة منتج" name={archiving.name}
          loadUsage={() => productsAPI.usage(archiving.id)}
          onArchive={() => productsAPI.archive(archiving.id)}
          onDelete={() => productsAPI.delete(archiving.id)}
          onClose={() => setArchiving(null)}
          onDone={() => { setArchiving(null); loadData(); }} />
      )}

      {/* Product Form Modal */}
      {printItems && (
        <PrintLabelsModal items={printItems} onClose={() => setPrintItems(null)} />
      )}
      {showForm && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-2 sm:p-4">
          <form onSubmit={handleSubmit} onKeyDown={enterToNext}
            className="bg-white rounded-2xl w-full max-w-6xl max-h-[96vh] flex flex-col shadow-xl">
            <div className="flex items-center justify-between px-5 py-3 border-b">
              <h2 className="text-lg font-bold text-gray-800">{editingProduct ? `تعديل: ${editingProduct.name}` : 'إضافة منتج جديد'}</h2>
              <button type="button" onClick={resetForm} className="text-gray-400 hover:text-gray-700 text-2xl leading-none px-2" aria-label="إغلاق">×</button>
            </div>

            <div className="overflow-auto px-5 py-4">
              <div className="grid md:grid-cols-2 xl:grid-cols-3 gap-5">
                {/* 1 — basics */}
                <section className="space-y-3">
                  <h3 className="text-xs font-bold text-gray-500">الأساسيات</h3>
                  <Field label="اسم المنتج *">
                    <Input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder="مثال: ماء 330 مل" autoFocus />
                  </Field>
                  <Field label="التصنيف">
                    <Select value={form.category_id} onChange={(e) => setForm({ ...form, category_id: e.target.value })}>
                      <option value="">بدون تصنيف</option>
                      {categories.map((cat) => <option key={cat.id} value={cat.id}>{cat.name}</option>)}
                    </Select>
                  </Field>
                  <Field label="الباركود" hint="يُولَّد تلقائياً عند طباعة الملصقات إن تُرك فارغاً">
                    <Input dir="ltr" value={form.barcode} onChange={(e) => setForm({ ...form, barcode: e.target.value })} />
                  </Field>
                  <Field label="صورة المنتج (اختياري)">
                    <div className="flex items-center gap-3">
                      {form.image_url
                        ? <img src={form.image_url} alt="" className="w-14 h-14 object-cover rounded-lg border" />
                        : <div className="w-14 h-14 rounded-lg bg-gray-100 flex items-center justify-center text-2xl text-gray-300">📦</div>}
                      <input type="file" accept="image/png,image/jpeg,image/webp,image/gif" onChange={handleImageUpload} className="flex-1 text-sm" />
                    </div>
                  </Field>
                </section>

                {/* 2 — price & tax */}
                <section className="space-y-3">
                  <h3 className="text-xs font-bold text-gray-500">السعر والضريبة</h3>
                  <div className="grid grid-cols-2 gap-3">
                    <Field label={<>سعر البيع (<SarIcon size={12} />) *</>} hint="شامل الضريبة">
                      <MoneyInput value={form.price} onChange={(v) => setForm({ ...form, price: v })} className={FIELD_CLS} />
                    </Field>
                    <Field label="سعر التكلفة" hint="للتقارير فقط">
                      <MoneyInput value={form.cost_price} onChange={(v) => setForm({ ...form, cost_price: v })} className={FIELD_CLS} />
                    </Field>
                  </div>
                  {parseFloat(form.price) > 0 && parseFloat(form.cost_price) > 0 && (
                    <p className="text-xs text-gray-500">هامش الربح: {(parseFloat(form.price) - parseFloat(form.cost_price)).toFixed(2)} ({Math.round((1 - parseFloat(form.cost_price) / parseFloat(form.price)) * 100)}٪)</p>
                  )}
                  <SwitchRow tone="orange" checked={form.is_tax_exempt} onChange={(v) => setForm({ ...form, is_tax_exempt: v })}
                    title="معفى من ضريبة القيمة المضافة" hint="لا تُحسب عليه ضريبة 15٪ (مثل بعض السلع الأساسية المعفاة نظاماً)" />
                  <SwitchRow checked={form.is_kit} onChange={(v) => setForm({ ...form, is_kit: v, components: v && form.components.length === 0 ? [{ product_id: '', quantity: '1' }] : form.components })}
                    title="منتج مُجمّع (سلة / حقيبة)" hint="يتكوّن من منتجات أخرى ويُخصم مخزونها عند البيع. أضف المكوّنات أسفل النموذج." />
                </section>

                {/* 3 — stock, unit, supplier */}
                <section className="space-y-3">
                  <h3 className="text-xs font-bold text-gray-500">المخزون والوحدة والمورّد</h3>
                  <div className="rounded-xl border border-gray-200 p-3 space-y-3">
                    <p className="text-xs text-gray-500">الوحدات والتعبئة — من القائمة الموحّدة في «وحدات القياس»</p>
                    <Field label="الوحدة الأساسية (يُحسب بها المخزون)">
                      <Select value={form.uom_id}
                        onChange={(e) => {
                          const u = units.find((x) => String(x.id) === e.target.value);
                          setForm({ ...form, uom_id: e.target.value, uom_category_id: u ? String(u.category_id) : '', purchase_uom_id: '', sales_uom_id: '' });
                        }}>
                        <option value="">— اختر —</option>
                        {uomCategories.map((c) => (
                          <optgroup key={c.id} label={c.name}>
                            {units.filter((u) => u.category_id === c.id).map((u) => <option key={u.id} value={u.id}>{u.name}</option>)}
                          </optgroup>
                        ))}
                      </Select>
                    </Field>
                    <div className="grid grid-cols-2 gap-3">
                      <Field label="وحدة الشراء" hint={unitHint(form.purchase_uom_id)}>
                        <Select value={form.purchase_uom_id} disabled={!form.uom_id} onChange={(e) => setForm({ ...form, purchase_uom_id: e.target.value })}>
                          <option value="">نفس الأساسية</option>
                          {catUnits.map((u) => <option key={u.id} value={u.id}>{u.name}</option>)}
                        </Select>
                      </Field>
                      <Field label="وحدة البيع" hint={unitHint(form.sales_uom_id)}>
                        <Select value={form.sales_uom_id} disabled={!form.uom_id} onChange={(e) => setForm({ ...form, sales_uom_id: e.target.value })}>
                          <option value="">نفس الأساسية</option>
                          {catUnits.map((u) => <option key={u.id} value={u.id}>{u.name}</option>)}
                        </Select>
                      </Field>
                    </div>
                    {form.uom_id && catUnits.length < 2 && (
                      <p className="text-xs text-amber-700">لا توجد وحدات تعبئة لهذا النوع بعد (مثل الكرتون) — أضفها من «وحدات القياس».</p>
                    )}
                    <p className="text-xs text-gray-400">مثال: الأساسية «حبة»، الشراء «كرتون» (= 24 حبة)، البيع «حبة». يتحوّل المخزون تلقائياً.</p>
                  </div>
                  <div className="grid grid-cols-2 gap-3">
                    <Field label={editingProduct ? 'الكمية الحالية' : 'الكمية الافتتاحية'} hint={form.is_kit ? 'تُحسب من المكوّنات' : editingProduct ? 'للتعديل استخدم «حركة المخزون»' : undefined}>
                      <Input type="number" min="0" step="any" value={form.is_kit ? '' : form.stock} disabled={form.is_kit || !!editingProduct}
                        onChange={(e) => setForm({ ...form, stock: e.target.value })} placeholder={form.is_kit ? 'تلقائي' : '0'} />
                    </Field>
                    <Field label="حد إعادة الطلب" hint="تنبيه عند انخفاض الكمية">
                      <Input type="number" min="0" step="any" value={form.reorder_level} onChange={(e) => setForm({ ...form, reorder_level: e.target.value })} placeholder="0" />
                    </Field>
                  </div>
                  <Field label="المورّد الافتراضي">
                    <div className="flex gap-2">
                      <Select value={form.default_supplier_id} onChange={(e) => setForm({ ...form, default_supplier_id: e.target.value })}>
                        <option value="">بدون</option>
                        {suppliers.map((sup) => <option key={sup.id} value={sup.id}>{sup.name}{sup.is_compliant ? '' : ' (غير معتمد)'}</option>)}
                      </Select>
                      {can('suppliers') && (
                        <Button type="button" variant="secondary" size="sm" className="!min-h-[48px] whitespace-nowrap" onClick={() => setQuickSupplier({ name: '' })}>+ مورّد</Button>
                      )}
                    </div>
                  </Field>
                  {quickSupplier && (
                    <div className="rounded-xl border border-bayan-green/40 bg-bayan-light/20 p-3 space-y-2">
                      <p className="text-sm font-medium text-gray-700">مورّد جديد</p>
                      <Input value={quickSupplier.name} autoFocus placeholder="اسم المورّد"
                        onChange={(e) => setQuickSupplier({ name: e.target.value })}
                        data-enter="own" onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); e.stopPropagation(); saveQuickSupplier(); } }} />
                      <p className="text-xs text-gray-500">تُستكمل مستنداته لاحقاً من شاشة «الموردون» قبل إصدار أوامر شراء له.</p>
                      <div className="flex gap-2">
                        <Button type="button" size="sm" onClick={saveQuickSupplier}>إضافة واختيار</Button>
                        <Button type="button" size="sm" variant="ghost" onClick={() => setQuickSupplier(null)}>إلغاء</Button>
                      </div>
                    </div>
                  )}
                </section>
              </div>

              {form.is_kit && (
                <div className="mt-5 rounded-xl border border-gray-200 p-4 space-y-2">
                  <p className="text-sm font-bold text-gray-700">مكوّنات المنتج المجمّع</p>
                  {form.components.map((c, i) => (
                    <div key={i} className="flex gap-2 items-center">
                      <Select value={c.product_id} className="flex-1"
                        onChange={(e) => setForm({ ...form, components: form.components.map((x, idx) => (idx === i ? { ...x, product_id: e.target.value } : x)) })}>
                        <option value="">اختر منتجاً…</option>
                        {products.filter((pr) => pr.is_active !== false && !pr.is_kit && (!editingProduct || pr.id !== editingProduct.id)).map((pr) => <option key={pr.id} value={pr.id}>{pr.name}</option>)}
                      </Select>
                      <Input type="number" step="any" min="0" value={c.quantity} placeholder="الكمية" className="!w-28 text-center"
                        onChange={(e) => setForm({ ...form, components: form.components.map((x, idx) => (idx === i ? { ...x, quantity: e.target.value } : x)) })} />
                      <button type="button" onClick={() => setForm({ ...form, components: form.components.filter((_, idx) => idx !== i) })}
                        className="text-red-400 hover:text-red-600 px-2 text-2xl leading-none" aria-label="حذف">×</button>
                    </div>
                  ))}
                  <button type="button" onClick={() => setForm({ ...form, components: [...form.components, { product_id: '', quantity: '1' }] })}
                    className="text-sm text-bayan-green hover:underline">+ إضافة مكوّن</button>
                </div>
              )}
            </div>

            <div className="flex gap-3 px-5 py-3 border-t bg-gray-50 rounded-b-2xl">
              <Button type="submit" className="flex-1 sm:flex-none sm:px-10" title="أو Ctrl+Enter">{editingProduct ? 'حفظ التعديلات' : 'إضافة المنتج'}</Button>
              <span className="hidden sm:flex items-center text-xs text-gray-400">Enter للانتقال للحقل التالي · Ctrl+Enter للحفظ</span>
              <Button type="button" variant="secondary" onClick={resetForm}>إلغاء</Button>
            </div>
          </form>
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
