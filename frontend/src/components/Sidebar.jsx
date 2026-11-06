import { useState } from 'react';
import { NavLink, useNavigate } from 'react-router-dom';
import Logo from './Logo';
import { clearTheme } from '../utils/theme';
import { getPOSSettings, getCapabilities } from '../utils/posSettings';
import { canOpen } from '../utils/perms';
import { authAPI } from '../services/api';
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
  HiOutlineKey,
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

export default function Sidebar({ mobileOpen = false, onClose = () => {} }) {
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

  const handleLogout = async () => {
    try { await authAPI.logout(); } catch (e) { /* offline: still clear locally */ }
    localStorage.removeItem('token');
    localStorage.removeItem('user');
    localStorage.removeItem('tenant_name');
    localStorage.removeItem('tenant_slug');
    localStorage.removeItem('tenant_logo');
    clearTheme();
    navigate('/login');
  };

  let filteredMenu = menuItems.filter((item) => canOpen(item.path));

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

  // Phones / tablets (< lg): an off-canvas drawer, always full width labels.
  // Desktop: the normal rail, collapsible to icons.
  const rail = collapsed ? 'lg:w-16' : 'lg:w-64';
  const compact = collapsed && !mobileOpen;
  return (
    <>
    {mobileOpen && <div className="lg:hidden fixed inset-0 bg-black/40 z-40" onClick={onClose} />}
    <aside
      className={`${rail} w-72 bg-bayan-dark h-full flex flex-col shadow-xl transition-all duration-200 ease-in-out
        fixed inset-y-0 right-0 z-50 lg:static lg:z-auto lg:translate-x-0
        ${mobileOpen ? 'translate-x-0' : 'translate-x-full'}`}
    >
      {/* Collapse toggle (desktop) / close (drawer) */}
      <button
        onClick={() => (mobileOpen ? onClose() : toggle())}
        title={mobileOpen ? 'إغلاق القائمة' : compact ? 'توسيع القائمة' : 'طيّ القائمة'}
        aria-label={compact ? 'توسيع القائمة' : 'طيّ القائمة'}
        className="m-2 p-2 rounded-lg text-indigo-200 hover:bg-bayan-green/50 hover:text-white transition-all self-start"
      >
        <HiOutlineMenu className="text-xl" />
      </button>

      {/* Logo / Header */}
      <div className={`${compact ? 'px-2 pb-3' : 'px-6 pb-6 [@media(max-height:820px)]:pb-2'} border-b border-bayan-green/30 text-center`}>
        {tenantLogo ? (
          <img
            src={tenantLogo}
            alt="الشعار"
            className={`${compact ? 'h-10 w-10' : 'h-14 [@media(max-height:820px)]:h-9'} mx-auto mb-2 object-contain bg-white rounded-lg p-1`}
          />
        ) : (
          <div className={`mx-auto mb-2 ${compact ? 'w-10 h-10' : 'w-14 h-14'} bg-white rounded-xl flex items-center justify-center`}>
            <Logo size={compact ? 30 : 44} />
          </div>
        )}
        {!compact && (
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
      <nav className={`flex-1 ${compact ? 'p-2' : 'p-4 [@media(max-height:820px)]:py-2'} space-y-1 [@media(max-height:820px)]:space-y-0.5 overflow-y-auto sidebar-scroll`}>
        {filteredMenu.map((item) => (
          <NavLink
            key={item.path}
            to={item.path}
            end={item.path === '/'}
            title={item.label}
            className={({ isActive }) =>
              `flex items-center ${compact ? 'justify-center px-0' : 'gap-3 px-4'} py-3 [@media(max-height:820px)]:py-1.5 rounded-lg transition-all duration-200 ${
                isActive
                  ? 'bg-bayan-green text-white shadow-lg'
                  : 'text-indigo-200 hover:bg-bayan-green/50 hover:text-white'
              }`
            }
          >
            <item.icon className="text-xl flex-shrink-0" />
            {!compact && <span className="font-medium">{item.label}</span>}
          </NavLink>
        ))}
      </nav>

      {/* User info + password + logout — one compact row so the whole menu fits 1366×768 */}
      <div className={`${compact ? 'p-2 space-y-1' : 'p-3'} border-t border-bayan-green/30`}>
        <div className={`flex items-center ${compact ? 'flex-col gap-1' : 'gap-2'}`}>
          {!compact && (
            <>
              <div className="w-8 h-8 bg-bayan-green rounded-full flex items-center justify-center text-white text-sm font-bold flex-shrink-0">
                {user.full_name?.charAt(0) || '؟'}
              </div>
              <div className="flex-1 min-w-0">
                <p className="text-white text-sm font-medium truncate">{user.full_name || 'مستخدم'}</p>
                <p className="text-indigo-400 text-xs truncate">{user.role_label || (user.role === 'admin' ? 'مدير النظام' : 'مستخدم')}</p>
              </div>
            </>
          )}
          <NavLink
            to="/change-password"
            title="تغيير كلمة المرور"
            aria-label="تغيير كلمة المرور"
            className="p-2 rounded-lg text-indigo-200 hover:bg-bayan-green/50 hover:text-white transition-all"
          >
            <HiOutlineKey className="text-xl" />
          </NavLink>
          <button
            onClick={handleLogout}
            title="تسجيل الخروج"
            aria-label="تسجيل الخروج"
            className="p-2 rounded-lg text-red-300 hover:bg-red-900/30 hover:text-red-200 transition-all"
          >
            <HiOutlineLogout className="text-xl" />
          </button>
        </div>
      </div>
    </aside>
    </>
  );
}
