// Units of measure — card per measurement type, in plain words (tester: too many
// similar terms). "Category / reference / factor" become "measurement type /
// base unit / equals N base units".
import { useState, useEffect } from 'react';
import { uomAPI, apiError } from '../services/api';
import toast from 'react-hot-toast';
import { HiOutlineScale, HiOutlinePlus, HiOutlineTrash, HiOutlineInformationCircle } from 'react-icons/hi';
import { Button, Input } from '../components/ui';
import { can } from '../utils/perms';

export default function UnitsOfMeasure() {
  const [categories, setCategories] = useState([]);
  const [units, setUnits] = useState([]);
  const [newCat, setNewCat] = useState({ name: '', fractions: false, base: '' });
  const [drafts, setDrafts] = useState({});           // per category: { name, factor }
  const editable = can('products');

  useEffect(() => { load(); }, []);

  const load = async () => {
    try {
      const [c, u] = await Promise.all([uomAPI.categories(), uomAPI.units()]);
      setCategories(c.data);
      setUnits(u.data);
    } catch (err) { toast.error(apiError(err, 'خطأ في التحميل')); }
  };

  const addCategory = async () => {
    if (!newCat.name.trim()) return toast.error('أدخل اسم نوع القياس (مثال: طول)');
    if (!newCat.base.trim()) return toast.error('أدخل الوحدة الأساسية (مثال: متر)');
    try {
      const r = await uomAPI.createCategory({ name: newCat.name.trim(), decimal_places: newCat.fractions ? 3 : 0 });
      await uomAPI.createUnit({ category_id: r.data.id, name: newCat.base.trim(), factor: 1, is_reference: true });
      setNewCat({ name: '', fractions: false, base: '' });
      toast.success('تمت إضافة نوع القياس ووحدته الأساسية');
      load();
    } catch (err) { toast.error(apiError(err, 'تعذّرت الإضافة')); }
  };

  const removeCategory = async (c) => {
    if (!confirm(`إيقاف نوع القياس «${c.name}» ووحداته؟ المنتجات المرتبطة به لا تتأثر.`)) return;
    try { await uomAPI.deleteCategory(c.id); toast.success('تم الإيقاف'); load(); }
    catch (err) { toast.error(apiError(err, 'تعذّر الإيقاف')); }
  };

  const addUnit = async (c, base) => {
    const d = drafts[c.id] || {};
    if (!(d.name || '').trim()) return toast.error('أدخل اسم الوحدة (مثال: كرتون)');
    const factor = parseFloat(d.factor);
    if (!base) {
      try {
        await uomAPI.createUnit({ category_id: c.id, name: d.name.trim(), factor: 1, is_reference: true });
        setDrafts({ ...drafts, [c.id]: {} }); toast.success('تمت إضافة الوحدة الأساسية'); load();
      } catch (err) { toast.error(apiError(err, 'تعذّرت الإضافة')); }
      return;
    }
    if (!(factor > 0)) return toast.error(`كم ${base.name} في هذه الوحدة؟ أدخل رقماً أكبر من صفر`);
    try {
      await uomAPI.createUnit({ category_id: c.id, name: d.name.trim(), factor, is_reference: false });
      setDrafts({ ...drafts, [c.id]: {} });
      toast.success(`تمت إضافة «${d.name.trim()}» = ${factor} ${base.name}`);
      load();
    } catch (err) { toast.error(apiError(err, 'تعذّرت الإضافة')); }
  };

  const removeUnit = async (u) => {
    if (!confirm(`حذف الوحدة «${u.name}»؟`)) return;
    try { await uomAPI.deleteUnit(u.id); load(); }
    catch (err) { toast.error(apiError(err, 'تعذّر الحذف')); }
  };

  const fmt = (n) => (Number.isInteger(n) ? String(n) : String(+Number(n).toFixed(3)));

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-800 flex items-center gap-2">
          <HiOutlineScale className="text-bayan-green" /> وحدات القياس
        </h1>
        <p className="text-gray-500 mt-1">القائمة الموحّدة التي تختار منها وحدة كل منتج.</p>
      </div>

      <div className="flex gap-3 bg-blue-50 border border-blue-100 text-blue-900 rounded-xl p-4 text-sm leading-7">
        <HiOutlineInformationCircle className="text-xl shrink-0 mt-1" />
        <div>
          <p><b>نوع القياس</b>: هل يُعدّ المنتج (عدد) أم يُوزن (وزن) أم يُكال (حجم).</p>
          <p><b>الوحدة الأساسية</b>: أصغر وحدة يُحسب بها المخزون — مثل الحبة أو الجرام.</p>
          <p><b>الوحدات الأخرى</b> تُعرَّف بعدد الوحدات الأساسية فيها — مثل: الكرتون = 24 حبة. التحويل يتم تلقائياً عند الشراء والبيع.</p>
        </div>
      </div>

      <div className="grid gap-5 md:grid-cols-2 xl:grid-cols-3">
        {categories.map((c) => {
          const list = units.filter((u) => u.category_id === c.id).sort((a, b) => (b.is_reference - a.is_reference) || a.factor - b.factor);
          const base = list.find((u) => u.is_reference);
          const d = drafts[c.id] || {};
          return (
            <div key={c.id} className="bg-white rounded-2xl border shadow-sm flex flex-col">
              <div className="px-4 py-3 border-b flex items-center justify-between">
                <div>
                  <h2 className="font-bold text-gray-800 text-lg">{c.name}</h2>
                  <p className="text-xs text-gray-500">{c.decimal_places > 0 ? 'يقبل كسوراً (مثل 1.5)' : 'أعداد صحيحة فقط'}</p>
                </div>
                {editable && <button onClick={() => removeCategory(c)} className="text-gray-300 hover:text-red-500 p-1" title="إيقاف"><HiOutlineTrash /></button>}
              </div>
              <ul className="divide-y flex-1">
                {list.length === 0 && <li className="px-4 py-3 text-sm text-gray-400">لا توجد وحدات بعد</li>}
                {list.map((u) => (
                  <li key={u.id} className="px-4 py-2.5 flex items-center justify-between">
                    <span className="text-gray-800">
                      <b>{u.name}</b>
                      {u.is_reference
                        ? <span className="mr-2 text-xs bg-emerald-100 text-emerald-700 px-2 py-0.5 rounded-full">الوحدة الأساسية</span>
                        : base && <span className="text-gray-500 text-sm"> = {fmt(u.factor)} {base.name}</span>}
                    </span>
                    {editable && !u.is_reference && (
                      <button onClick={() => removeUnit(u)} className="text-gray-300 hover:text-red-500 p-1" title="حذف"><HiOutlineTrash /></button>
                    )}
                  </li>
                ))}
              </ul>
              {editable && (
                <div className="p-3 border-t bg-gray-50 rounded-b-2xl">
                  <div className="flex items-center gap-2 text-sm">
                    <Input value={d.name || ''} placeholder={base ? 'وحدة جديدة (مثال: كرتون)' : 'الوحدة الأساسية (مثال: حبة)'}
                      className="!min-h-[40px] flex-1" onChange={(e) => setDrafts({ ...drafts, [c.id]: { ...d, name: e.target.value } })} />
                    {base && (
                      <>
                        <span className="text-gray-500">=</span>
                        <Input type="number" min="0" step="any" dir="ltr" value={d.factor || ''} placeholder="24" className="!min-h-[40px] !w-20 text-center"
                          onChange={(e) => setDrafts({ ...drafts, [c.id]: { ...d, factor: e.target.value } })} />
                        <span className="text-gray-500 whitespace-nowrap">{base.name}</span>
                      </>
                    )}
                    <Button size="sm" className="!min-h-[40px]" onClick={() => addUnit(c, base)} icon={<HiOutlinePlus />} aria-label="إضافة" />
                  </div>
                </div>
              )}
            </div>
          );
        })}

        {editable && (
          <div className="rounded-2xl border-2 border-dashed border-gray-300 p-4 space-y-3">
            <h2 className="font-bold text-gray-700">نوع قياس جديد</h2>
            <Input value={newCat.name} placeholder="الاسم (مثال: طول)" onChange={(e) => setNewCat({ ...newCat, name: e.target.value })} />
            <Input value={newCat.base} placeholder="وحدته الأساسية (مثال: متر)" onChange={(e) => setNewCat({ ...newCat, base: e.target.value })} />
            <label className="flex items-center gap-2 text-sm text-gray-700 cursor-pointer">
              <input type="checkbox" className="w-5 h-5" checked={newCat.fractions} onChange={(e) => setNewCat({ ...newCat, fractions: e.target.checked })} />
              يقبل كسوراً (مثل 1.5 متر)
            </label>
            <Button onClick={addCategory} icon={<HiOutlinePlus />}>إضافة</Button>
          </div>
        )}
      </div>
    </div>
  );
}
