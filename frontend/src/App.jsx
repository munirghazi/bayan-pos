import { useEffect, useState } from 'react';
import { BrowserRouter, Routes, Route, Navigate, Outlet } from 'react-router-dom';
import { Toaster } from 'react-hot-toast';
import Sidebar from './components/Sidebar';
import { authAPI, settingsAPI } from './services/api';
import { applyTheme, storeTheme } from './utils/theme';
import { saveCapabilities } from './utils/posSettings';
import { syncZATCAFromTenant } from './utils/zatca';
import Login from './pages/Login';
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
  useEffect(() => {
    if (!token) return;
    authAPI.getCapabilities()
      .then((r) => { saveCapabilities(r.data); setCapsVersion((v) => v + 1); })
      .catch(() => {});
    settingsAPI.getTenant()
      .then((r) => { syncZATCAFromTenant(r.data); applyTheme(r.data); storeTheme(r.data); })
      .catch(() => {});
  }, [token]);
  if (!token) return <Navigate to="/login" replace />;

  return (
    <div className="flex h-[100dvh] overflow-hidden bg-gray-50">
      <Sidebar key={capsVersion} />
      <main className="app-main flex-1 p-6 overflow-auto">
        <Outlet />
      </main>
    </div>
  );
}

function PublicRoute({ children }) {
  const token = localStorage.getItem('token');
  if (token) return <Navigate to="/" replace />;
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
        <Route element={<ProtectedLayout />}>
          <Route path="/" element={<Dashboard />} />
          <Route path="/pos" element={<POS />} />
          <Route path="/products" element={<Catalog />} />
          <Route path="/donations" element={<Donations />} />
          <Route path="/reports" element={<Reports />} />
          <Route path="/branches" element={<Branches />} />
          <Route path="/register-closing" element={<RegisterClosing />} />
          <Route path="/returns" element={<Returns />} />
          <Route path="/suppliers" element={<Suppliers />} />
          <Route path="/uom" element={<UnitsOfMeasure />} />
          <Route path="/inventory" element={<Inventory />} />
          <Route path="/purchase-orders" element={<PurchaseOrders />} />
          <Route path="/settings" element={<Settings />} />
          <Route path="/privacy" element={<Privacy />} />
          <Route path="/consignment" element={<Catalog />} />
        </Route>
        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  );
}
