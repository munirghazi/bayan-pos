import { useState } from 'react';
import { NavLink, useNavigate } from 'react-router-dom';
import Logo from './Logo';
import { clearTheme } from '../utils/theme';
import { getPOSSettings, getCapabilities } from '../utils/posSettings';
import {
  HiOutlineViewGrid,
  HiOutlineShoppingCart,
  HiOutlineCube,
  HiOutlineHeart,
  HiOutlineChartBar,
  HiOutlineReceiptRefund,
  HiOutlineCog,
  HiOutlineShieldCheck,
  HiOutlineOfficeBuilding,
  HiOutlineTruck,
  HiOutlineScale,
  HiOutlineArchive,
  HiOutlineClipboardList,
  HiOutlineCalculator,
  HiOutlineLogout,
  HiOutlineMenu,
} from 'react-icons/hi';

const menuItems = [
  { path: '/', icon: HiOutlineViewGrid, label: 'لوحة التحكم' },
  { path: '/pos', icon: HiOutlineShoppingCart, label: 'نقطة البيع' },
  { path: '/products', icon: HiOutlineCube, label: 'المنتجات والأمانات' },
  { path: '/donations', icon: HiOutlineHeart, label: 'التبرعات' },
  { path: '/returns', icon: HiOutlineReceiptRefund, label: 'المرتجعات' },
  { path: '/reports', icon: HiOutlineChartBar, label: 'التقارير' },
  { path: '/branches', icon: HiOutlineOfficeBuilding, label: 'الفروع والصناديق' },
  { path: '/register-closing', icon: HiOutlineCalculator, label: 'إغلاق الصندوق' },
  { path: '/suppliers', icon: HiOutlineTruck, label: 'الموردون' },
  { path: '/uom', icon: HiOutlineScale, label: 'وحدات القياس' },
  { path: '/inventory', icon: HiOutlineArchive, label: 'حركة المخزون' },
  { path: '/purchase-orders', icon: HiOutlineClipboardList, label: 'أوامر الشراء' },
  { path: '/settings', icon: HiOutlineCog, label: 'الإعدادات' },
  { path: '/privacy', icon: HiOutlineShieldCheck, label: 'الخصوصية' },
];

export default function Sidebar() {
  const navigate = useNavigate();
  const user = JSON.parse(localStorage.getItem('user') || '{}');
  const posSettings = getPOSSettings();
  const caps = getCapabilities();
  const tenantName = localStorage.getItem('tenant_name') || 'نظام نقاط البيع';
  const tenantLogo = localStorage.getItem('tenant_logo') || '';
  const showPoweredBy = localStorage.getItem('show_powered_by') !== '0';

  // Collapsed (icon-only) rail — persisted so it survives navigation/remounts.
  const [collapsed, setCollapsed] = useState(
    () => localStorage.getItem('sidebar_collapsed') === '1'
  );
  const toggle = () =>
    setCollapsed((v) => {
      const nv = !v;
      try { localStorage.setItem('sidebar_collapsed', nv ? '1' : '0'); } catch (e) {}
      return nv;
    });

  const handleLogout = () => {
    localStorage.removeItem('token');
    localStorage.removeItem('user');
    localStorage.removeItem('tenant_name');
    localStorage.removeItem('tenant_slug');
    localStorage.removeItem('tenant_logo');
    clearTheme();
    navigate('/login');
  };

  let filteredMenu = user.role === 'admin'
    ? menuItems
    : menuItems.filter(item => !['/settings', '/privacy', '/branches', '/suppliers', '/uom', '/inventory', '/purchase-orders'].includes(item.path));

  if (!posSettings.showDonation) {
    filteredMenu = filteredMenu.filter(item => item.path !== '/donations');
  }

  // Phase 3: hide sections this tenant's mode doesn't use
  const capHidden = [];
  if (!caps.sales_enabled) capHidden.push('/pos', '/register-closing');
  if (!caps.donations_enabled) capHidden.push('/donations');
  if (!caps.purchasing_enabled) capHidden.push('/suppliers', '/purchase-orders');
  if (!caps.inventory_enabled) capHidden.push('/inventory', '/uom');
  filteredMenu = filteredMenu.filter(item => !capHidden.includes(item.path));

  return (
    <aside
      className={`${collapsed ? 'w-16' : 'w-64'} bg-bayan-dark h-full flex flex-col shadow-xl transition-[width] duration-200 ease-in-out`}
    >
      {/* Collapse toggle */}
      <button
        onClick={toggle}
        title={collapsed ? 'توسيع القائمة' : 'طيّ القائمة'}
        aria-label={collapsed ? 'توسيع القائمة' : 'طيّ القائمة'}
        className="m-2 p-2 rounded-lg text-indigo-200 hover:bg-bayan-green/50 hover:text-white transition-all self-start"
      >
        <HiOutlineMenu className="text-xl" />
      </button>

      {/* Logo / Header */}
      <div className={`${collapsed ? 'px-2 pb-3' : 'px-6 pb-6'} border-b border-bayan-green/30 text-center`}>
        {tenantLogo ? (
          <img
            src={tenantLogo}
            alt="شعار الجمعية"
            className={`${collapsed ? 'h-10 w-10' : 'h-14'} mx-auto mb-2 object-contain bg-white rounded-lg p-1`}
          />
        ) : (
          <div className={`mx-auto mb-2 ${collapsed ? 'w-10 h-10' : 'w-14 h-14'} bg-white rounded-xl flex items-center justify-center`}>
            <Logo size={collapsed ? 30 : 44} />
          </div>
        )}
        {!collapsed && (
          <>
            <h1 className="text-xl font-bold text-white">{tenantName}</h1>
            {showPoweredBy && (
              <div className="flex items-center justify-center gap-1.5 mt-1">
                <Logo size={16} />
                <p className="text-indigo-300 text-sm">سهل</p>
              </div>
            )}
          </>
        )}
      </div>

      {/* Navigation */}
      <nav className={`flex-1 ${collapsed ? 'p-2' : 'p-4'} space-y-1 overflow-auto`}>
        {filteredMenu.map((item) => (
          <NavLink
            key={item.path}
            to={item.path}
            end={item.path === '/'}
            title={item.label}
            className={({ isActive }) =>
              `flex items-center ${collapsed ? 'justify-center px-0' : 'gap-3 px-4'} py-3 rounded-lg transition-all duration-200 ${
                isActive
                  ? 'bg-bayan-green text-white shadow-lg'
                  : 'text-indigo-200 hover:bg-bayan-green/50 hover:text-white'
              }`
            }
          >
            <item.icon className="text-xl flex-shrink-0" />
            {!collapsed && <span className="font-medium">{item.label}</span>}
          </NavLink>
        ))}
      </nav>

      {/* User info + Logout */}
      <div className={`${collapsed ? 'p-2' : 'p-4'} border-t border-bayan-green/30`}>
        {!collapsed && (
          <div className="flex items-center gap-3 px-4 py-2 mb-2">
            <div className="w-8 h-8 bg-bayan-green rounded-full flex items-center justify-center text-white text-sm font-bold flex-shrink-0">
              {user.full_name?.charAt(0) || '؟'}
            </div>
            <div>
              <p className="text-white text-sm font-medium">{user.full_name || 'مستخدم'}</p>
              <p className="text-indigo-400 text-xs">
                {user.role === 'admin' ? 'مدير' : 'كاشير'}
              </p>
            </div>
          </div>
        )}
        <button
          onClick={handleLogout}
          title="تسجيل الخروج"
          className={`flex items-center ${collapsed ? 'justify-center px-0' : 'gap-3 px-4'} py-3 rounded-lg text-red-300 hover:bg-red-900/30 hover:text-red-200 transition-all w-full`}
        >
          <HiOutlineLogout className="text-xl flex-shrink-0" />
          {!collapsed && <span className="font-medium">تسجيل الخروج</span>}
        </button>
      </div>
    </aside>
  );
}
