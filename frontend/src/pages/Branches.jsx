import { useState, useEffect, useRef } from 'react';
import { locationsAPI, registersAPI } from '../services/api';
import toast from 'react-hot-toast';
import {
  HiOutlineOfficeBuilding,
  HiOutlinePlus,
  HiOutlinePencil,
  HiOutlineTrash,
  HiOutlineDesktopComputer,
} from 'react-icons/hi';

export default function Branches() {
  const [locations, setLocations] = useState([]);
  const [registers, setRegisters] = useState([]);
  const [loading, setLoading] = useState(true);
  const [newBranch, setNewBranch] = useState('');
  const [newRegister, setNewRegister] = useState({}); // { [locationId]: name }
  const submittingRef = useRef(false);

  useEffect(() => { loadData(); }, []);

  const loadData = async () => {
    try {
      const [locRes, regRes] = await Promise.all([
        locationsAPI.getAll(),
        registersAPI.getAll(),
      ]);
      setLocations(locRes.data);
      setRegisters(regRes.data);
    } catch (err) {
      toast.error('خطأ في تحميل البيانات');
    } finally {
      setLoading(false);
    }
  };

  const addBranch = async () => {
    if (!newBranch.trim()) return;
    if (submittingRef.current) return;
    submittingRef.current = true;
    try {
      await locationsAPI.create({ name: newBranch.trim() });
      toast.success('تم إضافة الفرع');
      setNewBranch('');
      loadData();
    } catch (err) {
      toast.error(err.response?.data?.detail || 'خطأ في إضافة الفرع');
    } finally {
      submittingRef.current = false;
    }
  };

  const renameBranch = async (loc) => {
    const name = prompt('اسم الفرع الجديد:', loc.name);
    if (!name || !name.trim()) return;
    try {
      await locationsAPI.update(loc.id, { name: name.trim() });
      toast.success('تم تحديث الفرع');
      loadData();
    } catch (err) {
      toast.error('خطأ في التحديث');
    }
  };

  const deactivateBranch = async (loc) => {
    if (!confirm(`تعطيل الفرع "${loc.name}" وجميع صناديقه؟`)) return;
    try {
      await locationsAPI.delete(loc.id);
      toast.success('تم تعطيل الفرع');
      loadData();
    } catch (err) {
      toast.error('خطأ في التعطيل');
    }
  };

  const addRegister = async (locationId) => {
    const name = (newRegister[locationId] || '').trim();
    if (!name) return;
    if (submittingRef.current) return;
    submittingRef.current = true;
    try {
      await registersAPI.create({ name, location_id: locationId });
      toast.success('تم إضافة الصندوق');
      setNewRegister((prev) => ({ ...prev, [locationId]: '' }));
      loadData();
    } catch (err) {
      toast.error(err.response?.data?.detail || 'خطأ في إضافة الصندوق');
    } finally {
      submittingRef.current = false;
    }
  };

  const renameRegister = async (reg) => {
    const name = prompt('اسم الصندوق الجديد:', reg.name);
    if (!name || !name.trim()) return;
    try {
      await registersAPI.update(reg.id, { name: name.trim() });
      toast.success('تم تحديث الصندوق');
      loadData();
    } catch (err) {
      toast.error('خطأ في التحديث');
    }
  };

  const deactivateRegister = async (reg) => {
    if (!confirm(`تعطيل الصندوق "${reg.name}"؟`)) return;
    try {
      await registersAPI.delete(reg.id);
      toast.success('تم تعطيل الصندوق');
      loadData();
    } catch (err) {
      toast.error('خطأ في التعطيل');
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
          <h1 className="text-2xl font-bold text-gray-800">الفروع والصناديق</h1>
          <p className="text-gray-500 mt-1">{locations.length} فرع</p>
        </div>
      </div>

      {/* Add branch */}
      <div className="bg-white rounded-xl border shadow-sm p-4 flex gap-3">
        <input
          type="text"
          value={newBranch}
          onChange={(e) => setNewBranch(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && addBranch()}
          placeholder="اسم فرع جديد"
          className="flex-1 px-4 py-2 rounded-lg border border-gray-300 focus:ring-2 focus:ring-bayan-green outline-none text-right"
        />
        <button
          onClick={addBranch}
          className="flex items-center gap-2 bg-bayan-green hover:bg-bayan-dark text-white px-6 py-2 rounded-lg transition-all"
        >
          <HiOutlinePlus /> إضافة فرع
        </button>
      </div>

      {/* Branches list */}
      <div className="space-y-4">
        {locations.map((loc) => {
          const locRegisters = registers.filter((r) => r.location_id === loc.id);
          return (
            <div key={loc.id} className="bg-white rounded-xl border shadow-sm overflow-hidden">
              <div className="flex items-center justify-between p-4 bg-gray-50 border-b">
                <div className="flex items-center gap-2 font-bold text-gray-800">
                  <HiOutlineOfficeBuilding className="text-bayan-green text-xl" />
                  {loc.name}
                </div>
                <div className="flex items-center gap-2">
                  <button onClick={() => renameBranch(loc)} className="text-blue-500 hover:text-blue-700 p-1">
                    <HiOutlinePencil />
                  </button>
                  <button onClick={() => deactivateBranch(loc)} className="text-red-500 hover:text-red-700 p-1">
                    <HiOutlineTrash />
                  </button>
                </div>
              </div>

              <div className="p-4 space-y-2">
                {locRegisters.length === 0 && (
                  <p className="text-gray-400 text-sm">لا توجد صناديق في هذا الفرع</p>
                )}
                {locRegisters.map((reg) => (
                  <div key={reg.id} className="flex items-center justify-between px-3 py-2 rounded-lg bg-gray-50">
                    <div className="flex items-center gap-2 text-gray-700">
                      <HiOutlineDesktopComputer className="text-gray-400" />
                      {reg.name}
                    </div>
                    <div className="flex items-center gap-2">
                      <button onClick={() => renameRegister(reg)} className="text-blue-500 hover:text-blue-700 p-1">
                        <HiOutlinePencil />
                      </button>
                      <button onClick={() => deactivateRegister(reg)} className="text-red-500 hover:text-red-700 p-1">
                        <HiOutlineTrash />
                      </button>
                    </div>
                  </div>
                ))}

                {/* Add register to this branch */}
                <div className="flex gap-2 pt-2">
                  <input
                    type="text"
                    value={newRegister[loc.id] || ''}
                    onChange={(e) => setNewRegister((prev) => ({ ...prev, [loc.id]: e.target.value }))}
                    onKeyDown={(e) => e.key === 'Enter' && addRegister(loc.id)}
                    placeholder="اسم صندوق جديد"
                    className="flex-1 px-3 py-2 rounded-lg border border-gray-300 focus:ring-2 focus:ring-bayan-green outline-none text-right text-sm"
                  />
                  <button
                    onClick={() => addRegister(loc.id)}
                    className="flex items-center gap-1 bg-gray-100 hover:bg-gray-200 text-gray-700 px-4 py-2 rounded-lg text-sm transition-all"
                  >
                    <HiOutlinePlus /> صندوق
                  </button>
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
