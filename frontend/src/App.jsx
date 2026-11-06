import { useEffect, useState } from 'react';
import { BrowserRouter, Routes, Route, Navigate, Outlet, useLocation } from 'react-router-dom';
import { HiOutlineMenu } from 'react-icons/hi';
import { canOpen, homePath } from './utils/perms';
import { Toaster } from 'react-hot-toast';
import Sidebar from './components/Sidebar';
import { authAPI, settingsAPI } from './services/api';
import { applyTheme, storeTheme } from './utils/theme';
import { saveCapabilities, getCapabilities } from './utils/posSettings';
import { syncZATCAFromTenant } from './utils/zatca';
import Login from './pages/Login';
import ChangePassword from './pages/ChangePassword';
import Dashboard from './pages/Dashboard';
import POS from './pages/POS';
import Products from './pages/Products';
import Catalog from './pages/Catalog';
import Donations from './pages/Donations';
import Reports from './pages/Reports';
import Settings from './pages/Settings';
import Privacy from './pages/Privacy';
import Consignment from './pages/Consignment';
import Branches from './pages/Branches';
import RegisterClosing from './pages/RegisterClosing';
import Returns from './pages/Returns';
import Suppliers from './pages/Suppliers';
import UnitsOfMeasure from './pages/UnitsOfMeasure';
import Inventory from './pages/Inventory';
import PurchaseOrders from './pages/PurchaseOrders';

function ProtectedLayout() {
  const token = localStorage.getItem('token');
  const [capsVersion, setCapsVersion] = useState(0);
  const [menuOpen, setMenuOpen] = useState(false);          // phone / tablet drawer
  const location = useLocation();
  useEffect(() => { setMenuOpen(false); }, [location.pathname]);
  useEffect(() => {
    if (!token) return;
    // refresh the user (role + permissions) so the menu matches what the server allows
    authAPI.getMe()
      .then((r) => { localStorage.setItem('user', JSON.stringify(r.data)); setCapsVersion((v) => v + 1); })
      .catch(() => {});
    authAPI.getCapabilities()
      .then((r) => { saveCapabilities(r.data); setCapsVersion((v) => v + 1); })
      .catch(() => {});
    settingsAPI.getTenant()
      .then((r) => { syncZATCAFromTenant(r.data); applyTheme(r.data); storeTheme(r.data); })
      .catch(() => {});
  }, [token]);
  if (!token) return <Navigate to="/login" replace />;

  // Force a password change before the app is usable when the account is flagged.
  const user = JSON.parse(localStorage.getItem('user') || '{}');
  if (user.must_change_password) return <Navigate to="/change-password" replace />;

  const tenantName = localStorage.getItem('tenant_name') || '';
  return (
    <div className="flex h-[100dvh] overflow-hidden bg-gray-50">
      <Sidebar key={capsVersion} mobileOpen={menuOpen} onClose={() => setMenuOpen(false)} />
      <div className="flex-1 min-w-0 flex flex-col">
        {/* phone / tablet: the menu is a drawer opened from this bar */}
        <div className="lg:hidden flex items-center gap-3 px-3 h-12 bg-bayan-dark text-white shrink-0">
          <button onClick={() => setMenuOpen(true)} aria-label="القائمة" className="p-2 -m-1 rounded-lg hover:bg-white/10">
            <HiOutlineMenu className="text-2xl" />
          </button>
          <span className="font-bold truncate">{tenantName}</span>
        </div>
        <main className="app-main flex-1 p-6 overflow-auto">
          <Outlet />
        </main>
      </div>
    </div>
  );
}

// A page the user has no permission for is unreachable, even by URL.
function RequirePerm({ path, children }) {
  return canOpen(path) ? children : <Navigate to={homePath()} replace />;
}

function Home() {
  return canOpen('/') ? <Dashboard /> : <Navigate to={homePath()} replace />;
}

// A page whose feature is switched off for this tenant is unreachable, even by URL.
function RequireCap({ flag, children }) {
  return getCapabilities()[flag] ? children : <Navigate to="/" replace />;
}

// Reads the token when the route renders (not when the app first loads), so the
// redirect right after login sees the fresh token instead of looping to a blank page.
function ChangePasswordRoute() {
  return localStorage.getItem('token') ? <ChangePassword /> : <Navigate to="/login" replace />;
}

function PublicRoute({ children }) {
  const token = localStorage.getItem('token');
  if (token) return <Navigate to={homePath()} replace />;
  return children;
}

export default function App() {
  return (
    <BrowserRouter>
      <Toaster
        position="top-center"
        toastOptions={{
          duration: 3000,
          style: {
            fontFamily: 'Cairo, sans-serif',
            direction: 'rtl',
          },
        }}
      />
      <Routes>
        <Route
          path="/login"
          element={
            <PublicRoute>
              <Login />
            </PublicRoute>
          }
        />
        <Route
          path="/change-password"
          element={<ChangePasswordRoute />}
        />
        <Route element={<ProtectedLayout />}>
          <Route path="/" element={<Home />} />
          <Route path="/pos" element={<RequirePerm path="/pos"><POS /></RequirePerm>} />
          <Route path="/products" element={<RequirePerm path="/products"><Catalog /></RequirePerm>} />
          <Route path="/donations" element={<RequireCap flag="donations_enabled"><RequirePerm path="/donations"><Donations /></RequirePerm></RequireCap>} />
          <Route path="/reports" element={<RequirePerm path="/reports"><Reports /></RequirePerm>} />
          <Route path="/branches" element={<RequirePerm path="/branches"><Branches /></RequirePerm>} />
          <Route path="/register-closing" element={<RequirePerm path="/register-closing"><RegisterClosing /></RequirePerm>} />
          <Route path="/returns" element={<RequirePerm path="/returns"><Returns /></RequirePerm>} />
          <Route path="/suppliers" element={<RequirePerm path="/suppliers"><Suppliers /></RequirePerm>} />
          <Route path="/uom" element={<RequirePerm path="/uom"><UnitsOfMeasure /></RequirePerm>} />
          <Route path="/inventory" element={<RequirePerm path="/inventory"><Inventory /></RequirePerm>} />
          <Route path="/purchase-orders" element={<RequirePerm path="/purchase-orders"><PurchaseOrders /></RequirePerm>} />
          <Route path="/settings" element={<RequirePerm path="/settings"><Settings /></RequirePerm>} />
          <Route path="/privacy" element={<RequirePerm path="/privacy"><Privacy /></RequirePerm>} />
          <Route path="/consignment" element={<RequirePerm path="/consignment"><Catalog /></RequirePerm>} />
        </Route>
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  );
}
