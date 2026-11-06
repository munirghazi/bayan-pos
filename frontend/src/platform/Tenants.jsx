import { useEffect, useMemo, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import toast from 'react-hot-toast';
import { HiOutlinePlus, HiOutlineSearch, HiOutlineExclamation } from 'react-icons/hi';
import { Badge, Button, Card, Input, PageHeader, Spinner } from '../components/ui';
import { platformAPI, errMsg } from './api';
import { fmt, VERIFICATION } from './labels';

export default function Tenants() {
  const [rows, setRows] = useState(null);
  const [q, setQ] = useState('');
  const [status, setStatus] = useState('all');
  const navigate = useNavigate();

  useEffect(() => {
    platformAPI.tenants().then((r) => setRows(r.data)).catch((e) => toast.error(errMsg(e)));
  }, []);

  const shown = useMemo(() => (rows || []).filter((t) => {
    if (status === 'active' && !t.is_active) return false;
    if (status === 'suspended' && t.is_active) return false;
    const s = q.trim().toLowerCase();
    return !s || [t.slug, t.name, t.name_en, t.vat_number, t.cr_number, t.license_number, t.unified_number]
      .some((v) => (v || '').toLowerCase().includes(s));
  }), [rows, q, status]);

  const totals = useMemo(() => (rows || []).reduce((a, t) => ({
    tenants: a.tenants + 1, active: a.active + (t.is_active ? 1 : 0),
    documents: a.documents + t.stats.documents, users: a.users + t.stats.users,
  }), { tenants: 0, active: 0, documents: 0, users: 0 }), [rows]);

  return (
    <div>
      <PageHeader title="المنشآت" subtitle="كل المنشآت على المنصة مع أعداد السجلات"
        actions={<Button icon={<HiOutlinePlus />} onClick={() => navigate('/tenants/new')}>منشأة جديدة</Button>} />

      {rows && (
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 mb-5">
          {[['المنشآت', totals.tenants], ['الفعّالة', totals.active], ['المستخدمون', totals.users], ['المستندات الصادرة', totals.documents]]
            .map(([l, v]) => (
              <Card key={l} className="!p-4"><div className="text-xs text-slate-500">{l}</div><div className="text-2xl font-bold text-slate-800 mt-1">{v}</div></Card>
            ))}
        </div>
      )}

      <Card padded={false}>
        <div className="p-4 flex flex-wrap gap-3 items-center border-b border-slate-100">
          <div className="relative flex-1 min-w-[220px]">
            <HiOutlineSearch className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400" />
            <Input className="pr-9 !min-h-[42px]" placeholder="بحث بالاسم أو المعرّف أو رقم السجل أو الرقم الضريبي" value={q} onChange={(e) => setQ(e.target.value)} />
          </div>
          <div className="inline-flex p-1 bg-slate-100 rounded-xl text-sm">
            {[['all', 'الكل'], ['active', 'فعّالة'], ['suspended', 'موقوفة']].map(([v, l]) => (
              <button key={v} onClick={() => setStatus(v)}
                className={`px-3 py-1.5 rounded-lg ${status === v ? 'bg-white shadow text-slate-900' : 'text-slate-500'}`}>{l}</button>
            ))}
          </div>
        </div>

        {!rows ? (
          <div className="p-10 flex justify-center text-slate-400"><Spinner size={28} /></div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-slate-50 text-slate-500 text-xs">
                <tr>
                  <th className="text-right font-medium px-4 py-3">المنشأة</th>
                  <th className="text-right font-medium px-3 py-3">النوع</th>
                  <th className="text-right font-medium px-3 py-3">الحالة</th>
                  <th className="text-center font-medium px-3 py-3">المستخدمون</th>
                  <th className="text-center font-medium px-3 py-3">الفروع</th>
                  <th className="text-center font-medium px-3 py-3">الفواتير</th>
                  <th className="text-center font-medium px-3 py-3">إشعارات دائنة</th>
                  <th className="text-center font-medium px-3 py-3">التبرعات</th>
                  <th className="text-right font-medium px-3 py-3">آخر نشاط</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {shown.map((t) => (
                  <tr key={t.id} className="hover:bg-slate-50 cursor-pointer" onClick={() => navigate(`/tenants/${t.id}`)}>
                    <td className="px-4 py-3">
                      <Link to={`/tenants/${t.id}`} className="font-semibold text-slate-800 hover:underline" onClick={(e) => e.stopPropagation()}>{t.name}</Link>
                      <div className="text-xs text-slate-400 font-mono" dir="ltr">{t.slug}</div>
                    </td>
                    <td className="px-3 py-3 text-slate-600">{t.entity_type_label}</td>
                    <td className="px-3 py-3">
                      <div className="flex flex-wrap gap-1">
                        {t.is_active ? <Badge tone="green">فعّالة</Badge> : <Badge tone="red">موقوفة</Badge>}
                        {t.verification_status !== 'verified' && <Badge tone="amber">{VERIFICATION[t.verification_status]}</Badge>}
                        {t.missing.length > 0 && <Badge tone="amber"><HiOutlineExclamation />ناقص: {t.missing.join('، ')}</Badge>}
                      </div>
                    </td>
                    <td className="px-3 py-3 text-center">{t.stats.users}</td>
                    <td className="px-3 py-3 text-center">{t.stats.branches}</td>
                    <td className="px-3 py-3 text-center">{t.stats.sales}</td>
                    <td className="px-3 py-3 text-center">{t.stats.credit_notes}</td>
                    <td className="px-3 py-3 text-center">{t.donations_effective ? t.stats.donations : <span className="text-slate-300">—</span>}</td>
                    <td className="px-3 py-3 text-slate-500 whitespace-nowrap">{fmt(t.stats.last_activity_at)}</td>
                  </tr>
                ))}
                {shown.length === 0 && (
                  <tr><td colSpan={9} className="text-center text-slate-400 py-10">لا توجد نتائج</td></tr>
                )}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
  );
}
