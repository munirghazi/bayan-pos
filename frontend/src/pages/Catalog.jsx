import { useState } from 'react';
import { HiOutlineCube, HiOutlineArchive } from 'react-icons/hi';
import { PageHeader, Tabs } from '../components/ui';
import { getCapabilities } from '../utils/posSettings';
import Products from './Products';
import Consignment from './Consignment';

// Unified "Products & Consignment" screen. Consignment is an admin + sales-enabled area,
// so it only appears as a tab for those tenants; otherwise this is just the products screen.
export default function Catalog() {
  const user = JSON.parse(localStorage.getItem('user') || '{}');
  const caps = getCapabilities();
  const showConsign = user.role === 'admin' && caps.sales_enabled;
  const [tab, setTab] = useState('products');

  if (!showConsign) {
    return (
      <div className="space-y-5">
        <PageHeader title="المنتجات" icon={<HiOutlineCube />} />
        <Products embedded />
      </div>
    );
  }

  return (
    <div className="space-y-5">
      <PageHeader title="المنتجات والأمانات" icon={<HiOutlineCube />} />
      <Tabs value={tab} onChange={setTab} tabs={[
        { value: 'products', label: 'المنتجات', icon: <HiOutlineCube /> },
        { value: 'consignment', label: 'الأمانات', icon: <HiOutlineArchive /> },
      ]} />
      {tab === 'products' ? <Products embedded /> : <Consignment embedded />}
    </div>
  );
}
