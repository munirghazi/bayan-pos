import { useState, useEffect } from 'react';
import { uomAPI, apiError } from '../services/api';
import toast from 'react-hot-toast';
import { HiOutlineScale, HiOutlinePlus, HiOutlineTrash } from 'react-icons/hi';

export default function UnitsOfMeasure() {
  const [categories, setCategories] = useState([]);
  const [units, setUnits] = useState([]);
  const [selectedCat, setSelectedCat] = useState(null);
  const [newCat, setNewCat] = useState({ name: '', decimal_places: 3 });
  const [newUnit, setNewUnit] = useState({ name: '', factor: '', is_reference: false });

  useEffect(() => { load(); }, []);

  const load = async () => {
    try {
      const [c, u] = await Promise.all([uomAPI.categories(), uomAPI.units()]);
      setCategories(c.data);
      setUnits(u.data);
      if (!selectedCat && c.data.length) setSelectedCat(c.data[0].id);
    } catch (err) { toast.error(apiError(err, 'خطأ في التحميل')); }
  };

  const addCategory = async () => {
    if (!newCat.name.trim()) { toast.error('أدخل اسم الفئة'); return; }
    try {
      const r = await uomAPI.createCategory({ name: newCat.name.trim(), decimal_places: parseInt(newCat.decimal_places) || 0 });
      setNewCat({ name: '', decimal_places: 3 });
      setSelectedCat(r.data.id);
      load();
    } catch (err) { toast.error(apiError(err, 'خطأ')); }
  };

  const removeCategory = async (id) => {
    if (!confirm('تعطيل هذه الفئة؟')) return;
    try { await uomAPI.deleteCategory(id); if (selectedCat === id) setSelectedCat(null); load(); }
    catch (err) { toast.error(apiError(err, 'خطأ')); }
  };

  const addUnit = async () => {
    if (!selectedCat) { toast.error('اختر فئة أولاً'); return; }
    if (!newUnit.name.trim() || !newUnit.factor) { toast.error('أدخل اسم الوحدة والمعامل'); return; }
    try {
      await uomAPI.createUnit({
        category_id: selectedCat, name: newUnit.name.trim(),
        factor: parseFloat(newUnit.factor), is_reference: newUnit.is_reference,
      });
      setNewUnit({ name: '', factor: '', is_reference: false });
      load();
    } catch (err) { toast.error(apiError(err, 'خطأ')); }
  };

  const removeUnit = async (id) => {
    try { await uomAPI.deleteUnit(id); load(); }
    catch (err) { toast.error(apiError(err, 'خطأ')); }
  };

  const catUnits = units.filter((u) => u.category_id === selectedCat);
  const cat = categories.find((c) => c.id === selectedCat);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-800 flex items-center gap-2">
          <HiOutlineScale className="text-bayan-green" /> وحدات القياس
        </h1>
        <p className="text-gray-500 mt-1">الفئات ووحداتها. التحويل مسموح داخل الفئة الواحدة فقط. المعامل = عدد الوحدات المرجعية في هذه الوحدة.</p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Categories */}
        <div className="bg-white rounded-xl border shadow-sm overflow-hidden">
          <div className="px-4 py-3 bg-gray-50 border-b font-bold text-gray-800">الفئات</div>
          <div className="divide-y">
            {categories.map((c) => (
              <div key={c.id}
                onClick={() => setSelectedCat(c.id)}
                className={`px-4 py-3 flex items-center justify-between cursor-pointer hover:bg-gray-50 ${selectedCat === c.id ? 'bg-emerald-50' : ''}`}>
                <span className="text-gray-800">{c.name}</span>
                <div className="flex items-center gap-3">
                  <span className="text-xs text-gray-400">{c.decimal_places} خانة عشرية</span>
                  <button onClick={(e) => { e.stopPropagation(); removeCategory(c.id); }} className="text-red-400 hover:text-red-600"><HiOutlineTrash /></button>
                </div>
              </div>
            ))}
          </div>
          <div className="p-4 border-t flex gap-2">
            <input value={newCat.name} onChange={(e) => setNewCat({ ...newCat, name: e.target.value })}
              placeholder="اسم الفئة" className="flex-1 px-3 py-2 rounded-lg border border-gray-300 outline-none text-right text-sm" />
            <input type="number" value={newCat.decimal_places} onChange={(e) => setNewCat({ ...newCat, decimal_places: e.target.value })}
              className="w-20 px-2 py-2 rounded-lg border border-gray-300 outline-none text-sm" title="خانات عشرية" min="0" max="3" />
            <button onClick={addCategory} className="flex items-center gap-1 bg-bayan-green hover:bg-bayan-dark text-white px-4 py-2 rounded-lg text-sm"><HiOutlinePlus /> فئة</button>
          </div>
        </div>

        {/* Units of the selected category */}
        <div className="bg-white rounded-xl border shadow-sm overflow-hidden">
          <div className="px-4 py-3 bg-gray-50 border-b font-bold text-gray-800">
            {cat ? `وحدات فئة: ${cat.name}` : 'اختر فئة'}
          </div>
          {cat && (
            <>
              <div className="divide-y">
                {catUnits.length === 0 && <p className="p-4 text-gray-400 text-sm">لا توجد وحدات</p>}
                {catUnits.map((u) => (
                  <div key={u.id} className="px-4 py-3 flex items-center justify-between text-sm">
                    <span className="text-gray-800">
                      {u.name}
                      {u.is_reference && <span className="mr-2 text-xs bg-emerald-100 text-emerald-700 px-2 py-0.5 rounded-full">مرجعية</span>}
                    </span>
                    <div className="flex items-center gap-3">
                      <span className="text-gray-500">معامل: {u.factor}</span>
                      <button onClick={() => removeUnit(u.id)} className="text-red-400 hover:text-red-600"><HiOutlineTrash /></button>
                    </div>
                  </div>
                ))}
              </div>
              <div className="p-4 border-t space-y-2">
                <div className="flex gap-2">
                  <input value={newUnit.name} onChange={(e) => setNewUnit({ ...newUnit, name: e.target.value })}
                    placeholder="اسم الوحدة" className="flex-1 px-3 py-2 rounded-lg border border-gray-300 outline-none text-right text-sm" />
                  <input type="number" step="any" value={newUnit.factor} onChange={(e) => setNewUnit({ ...newUnit, factor: e.target.value })}
                    placeholder="المعامل" className="w-28 px-3 py-2 rounded-lg border border-gray-300 outline-none text-sm" dir="ltr" />
                </div>
                <div className="flex items-center justify-between">
                  <label className="flex items-center gap-2 text-sm text-gray-600">
                    <input type="checkbox" checked={newUnit.is_reference} onChange={(e) => setNewUnit({ ...newUnit, is_reference: e.target.checked })} />
                    وحدة مرجعية (معامل 1)
                  </label>
                  <button onClick={addUnit} className="flex items-center gap-1 bg-bayan-green hover:bg-bayan-dark text-white px-4 py-2 rounded-lg text-sm"><HiOutlinePlus /> وحدة</button>
                </div>
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
