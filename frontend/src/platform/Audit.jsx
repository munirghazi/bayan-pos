import { useEffect, useState } from 'react';
import toast from 'react-hot-toast';
import { Card, Field, Input, PageHeader, Select, Spinner } from '../components/ui';
import { platformAPI, errMsg } from './api';
import { ACTIONS } from './labels';
import { AuditList } from './TenantPage';

export default function Audit() {
  const [rows, setRows] = useState(null);
  const [action, setAction] = useState('');
  const [tenant, setTenant] = useState('');

  useEffect(() => {
    const h = setTimeout(() => {
      platformAPI.audit({ action: action || undefined, tenant: tenant.trim() || undefined, limit: 300 })
        .then((r) => setRows(r.data)).catch((e) => toast.error(errMsg(e)));
    }, 250);
    return () => clearTimeout(h);
  }, [action, tenant]);

  return (
    <div>
      <PageHeader title="سجل العمليات" subtitle="كل عملية على المنصة وكل محاولة دخول. السجل لا يُعدَّل ولا يُحذف." />
      <Card>
        <div className="grid sm:grid-cols-2 gap-3 mb-4 max-w-2xl">
          <Field label="العملية">
            <Select value={action} onChange={(e) => setAction(e.target.value)}>
              <option value="">الكل</option>
              {Object.entries(ACTIONS).map(([k, l]) => <option key={k} value={k}>{l}</option>)}
            </Select>
          </Field>
          <Field label="معرّف المنشأة"><Input dir="ltr" value={tenant} onChange={(e) => setTenant(e.target.value)} placeholder="bayan" /></Field>
        </div>
        {!rows ? <div className="p-10 flex justify-center text-slate-400"><Spinner size={28} /></div> : <AuditListWithTenant rows={rows} />}
      </Card>
    </div>
  );
}

function AuditListWithTenant({ rows }) {
  return <AuditList rows={rows.map((r) => ({ ...r, target: [r.tenant_slug, r.target].filter(Boolean).join(' · ') || null }))} />;
}
