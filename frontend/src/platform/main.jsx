// Platform console entry (platform.html). Hash routes so the page works the
// same behind Caddy and in the Vite dev server.
import React from 'react';
import ReactDOM from 'react-dom/client';
import { HashRouter, Navigate, Route, Routes } from 'react-router-dom';
import { Toaster } from 'react-hot-toast';
import '../index.css';
import Login from './Login';
import Layout from './Layout';
import Tenants from './Tenants';
import NewTenant from './NewTenant';
import TenantPage from './TenantPage';
import Audit from './Audit';

ReactDOM.createRoot(document.getElementById('root')).render(
  <React.StrictMode>
    <HashRouter>
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route element={<Layout />}>
          <Route path="/tenants" element={<Tenants />} />
          <Route path="/tenants/new" element={<NewTenant />} />
          <Route path="/tenants/:id" element={<TenantPage />} />
          <Route path="/audit" element={<Audit />} />
        </Route>
        <Route path="*" element={<Navigate to="/tenants" replace />} />
      </Routes>
    </HashRouter>
    <Toaster position="top-center" toastOptions={{ style: { fontFamily: 'Cairo, sans-serif' } }} />
  </React.StrictMode>,
);
