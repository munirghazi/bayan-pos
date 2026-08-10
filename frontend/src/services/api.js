import axios from 'axios';

const API_BASE = '/api';

const api = axios.create({
  baseURL: API_BASE,
  withCredentials: true, // send the httpOnly session cookie
});

// Handle 401 responses
api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      localStorage.removeItem('token');
      localStorage.removeItem('user');
      localStorage.removeItem('tenant_name');
      localStorage.removeItem('tenant_slug');
      localStorage.removeItem('tenant_logo');
      if (window.location.pathname !== '/login') {
        window.location.href = '/login';
      }
    }
    return Promise.reject(error);
  }
);

// ===================== Auth =====================
export const authAPI = {
  login: (username, password, tenant) => api.post('/auth/login', { username, password, tenant }),
  logout: () => api.post('/auth/logout'),
  getMe: () => api.get('/auth/me'),
  getUsers: () => api.get('/auth/users'),
  createUser: (data) => api.post('/auth/users', data),
  updateUser: (id, data) => api.put(`/auth/users/${id}`, data),
  deleteUser: (id) => api.delete(`/auth/users/${id}`),
};

// ===================== Products =====================
export const productsAPI = {
  getAll: () => api.get('/products/'),
  getAllAdmin: () => api.get('/products/all'),
  get: (id) => api.get(`/products/${id}`),
  create: (data) => api.post('/products/', data),
  update: (id, data) => api.put(`/products/${id}`, data),
  delete: (id) => api.delete(`/products/${id}`),
  uploadImage: (file) => {
    const formData = new FormData();
    formData.append('file', file);
    return api.post('/products/upload-image', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    });
  },
  updateStock: (id, quantity) => api.put(`/products/${id}/stock?quantity=${quantity}`),
  getCategories: () => api.get('/products/categories'),
  createCategory: (data) => api.post('/products/categories', data),
  updateCategory: (id, data) => api.put(`/products/categories/${id}`, data),
  deleteCategory: (id) => api.delete(`/products/categories/${id}`),
};

// ===================== Sales =====================
export const salesAPI = {
  create: (data) => api.post('/sales/', data),
  getAll: (skip = 0, limit = 50) => api.get(`/sales/?skip=${skip}&limit=${limit}`),
  get: (id) => api.get(`/sales/${id}`),
};

// ===================== Donations =====================
export const donationsAPI = {
  create: (data) => api.post('/donations/', data),
  getAll: (skip = 0, limit = 50) => api.get(`/donations/?skip=${skip}&limit=${limit}`),
  get: (id) => api.get(`/donations/${id}`),
  delete: (id) => api.delete(`/donations/${id}`),
};

// ===================== Reports =====================
export const reportsAPI = {
  getDashboard: () => api.get('/reports/dashboard'),
  getSalesReport: (startDate, endDate) => {
    const params = new URLSearchParams();
    if (startDate) params.append('start_date', startDate);
    if (endDate) params.append('end_date', endDate);
    return api.get(`/reports/sales-report?${params}`);
  },
  getDonationsReport: (startDate, endDate) => {
    const params = new URLSearchParams();
    if (startDate) params.append('start_date', startDate);
    if (endDate) params.append('end_date', endDate);
    return api.get(`/reports/donations-report?${params}`);
  },
};

// ===================== Settings =====================
export const settingsAPI = {
  getTenant: () => api.get('/settings/tenant'),
  updateTenant: (data) => api.put('/settings/tenant', data),
  uploadLogo: (file) => {
    const formData = new FormData();
    formData.append('file', file);
    return api.post('/settings/upload-logo', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    });
  },
  getLogo: () => api.get('/settings/logo'),
};

// ===================== Locations & Registers =====================
export const locationsAPI = {
  getAll: () => api.get('/locations/'),
  create: (data) => api.post('/locations/', data),
  update: (id, data) => api.put(`/locations/${id}`, data),
  delete: (id) => api.delete(`/locations/${id}`),
};

export const registersAPI = {
  getAll: (locationId) => api.get('/registers/' + (locationId ? `?location_id=${locationId}` : '')),
  create: (data) => api.post('/registers/', data),
  update: (id, data) => api.put(`/registers/${id}`, data),
  delete: (id) => api.delete(`/registers/${id}`),
};

export const customersAPI = {
  getAll: (q) => api.get('/customers/' + (q ? `?q=${encodeURIComponent(q)}` : '')),
  get: (id) => api.get(`/customers/${id}`),
  create: (data) => api.post('/customers/', data),
  update: (id, data) => api.put(`/customers/${id}`, data),
  delete: (id) => api.delete(`/customers/${id}`),
};

// Extracts a human-readable message from an axios error:
// - string detail (our HTTPException messages)
// - list detail (FastAPI 422 validation) -> joined field messages
// - no response (dropped connection / server down) -> clear connectivity message
export const returnsAPI = {
  getForSale: (saleId) => api.get(`/returns/sale/${saleId}`),
  getAll: () => api.get('/returns/'),
  get: (id) => api.get(`/returns/${id}`),
  create: (data) => api.post('/returns/', data),
};

export const deliveryAPI = {
  status: () => api.get('/delivery/status'),
  sendEmail: (data) => api.post('/delivery/email', data),
};

export function apiError(err, fallback = 'حدث خطأ') {
  if (err && err.response) {
    const d = err.response.data && err.response.data.detail;
    if (typeof d === 'string' && d) return d;
    if (Array.isArray(d) && d.length) {
      return d.map((x) => (x && x.msg) ? x.msg : (typeof x === 'string' ? x : JSON.stringify(x))).join('، ');
    }
    return `${fallback} (${err.response.status})`;
  }
  return 'تعذّر الاتصال بالخادم، تأكد من تشغيله وأعد المحاولة';
}

export default api;
