import { NavLink, useNavigate } from 'react-router-dom';
import { getPOSSettings } from '../utils/posSettings';
import {
  HiOutlineViewGrid,
  HiOutlineShoppingCart,
  HiOutlineCube,
  HiOutlineHeart,
  HiOutlineChartBar,
  HiOutlineCog,
  HiOutlineOfficeBuilding,
  HiOutlineLogout,
} from 'react-icons/hi';

const menuItems = [
  { path: '/', icon: HiOutlineViewGrid, label: 'لوحة التحكم' },
  { path: '/pos', icon: HiOutlineShoppingCart, label: 'نقطة البيع' },
  { path: '/products', icon: HiOutlineCube, label: 'المنتجات' },
  { path: '/donations', icon: HiOutlineHeart, label: 'التبرعات' },
  { path: '/reports', icon: HiOutlineChartBar, label: 'التقارير' },
  { path: '/branches', icon: HiOutlineOfficeBuilding, label: 'الفروع والصناديق' },
  { path: '/settings', icon: HiOutlineCog, label: 'الإعدادات' },
];

export default function Sidebar() {
  const navigate = useNavigate();
  const user = JSON.parse(localStorage.getItem('user') || '{}');
  const posSettings = getPOSSettings();
  const tenantName = localStorage.getItem('tenant_name') || 'نظام نقاط البيع';
  const tenantLogo = localStorage.getItem('tenant_logo') || '';

  const handleLogout = () => {
    localStorage.removeItem('token');
    localStorage.removeItem('user');
    localStorage.removeItem('tenant_name');
    localStorage.removeItem('tenant_slug');
    localStorage.removeItem('tenant_logo');
    navigate('/login');
  };

  let filteredMenu = user.role === 'admin'
    ? menuItems
    : menuItems.filter(item => !['/settings', '/branches'].includes(item.path));

  if (!posSettings.showDonation) {
    filteredMenu = filteredMenu.filter(item => item.path !== '/donations');
  }

  return (
    <aside className="w-64 bg-bayan-dark min-h-screen flex flex-col shadow-xl">
      {/* Logo / Header */}
      <div className="p-6 border-b border-bayan-green/30 text-center">
        {tenantLogo ? (
          <img
            src={tenantLogo}
            alt="شعار الجمعية"
            className="h-14 mx-auto mb-2 object-contain bg-white rounded-lg p-1"
          />
        ) : null}
        <h1 className="text-xl font-bold text-white">{tenantName}</h1>
        <p className="text-emerald-300 text-sm mt-1">نظام نقاط البيع</p>
      </div>

      {/* Navigation */}
      <nav className="flex-1 p-4 space-y-1">
        {filteredMenu.map((item) => (
          <NavLink
            key={item.path}
            to={item.path}
            end={item.path === '/'}
            className={({ isActive }) =>
              `flex items-center gap-3 px-4 py-3 rounded-lg transition-all duration-200 ${
                isActive
                  ? 'bg-bayan-green text-white shadow-lg'
                  : 'text-emerald-200 hover:bg-bayan-green/50 hover:text-white'
              }`
            }
          >
            <item.icon className="text-xl flex-shrink-0" />
            <span className="font-medium">{item.label}</span>
          </NavLink>
        ))}
      </nav>

      {/* User info + Logout */}
      <div className="p-4 border-t border-bayan-green/30">
        <div className="flex items-center gap-3 px-4 py-2 mb-2">
          <div className="w-8 h-8 bg-bayan-green rounded-full flex items-center justify-center text-white text-sm font-bold">
            {user.full_name?.charAt(0) || '؟'}
          </div>
          <div>
            <p className="text-white text-sm font-medium">{user.full_name || 'مستخدم'}</p>
            <p className="text-emerald-400 text-xs">
              {user.role === 'admin' ? 'مدير' : 'كاشير'}
            </p>
          </div>
        </div>
        <button
          onClick={handleLogout}
          className="flex items-center gap-3 px-4 py-3 rounded-lg text-red-300 hover:bg-red-900/30 hover:text-red-200 transition-all w-full"
        >
          <HiOutlineLogout className="text-xl" />
          <span className="font-medium">تسجيل الخروج</span>
        </button>
      </div>
    </aside>
  );
}
