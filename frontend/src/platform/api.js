// Platform console API client. Session = httpOnly cookie set by the server.
// Every request carries X-Platform-Request: the server refuses state-changing
// calls without it (CSRF guard; the tenant app shares the parent domain).
import axios from 'axios';

const api = axios.create({
  baseURL: '/api/platform',
  withCredentials: true,
  headers: { 'X-Platform-Request': '1' },
});

api.interceptors.response.use(
  (r) => r,
  (error) => {
    const url = error.config?.url || '';
    if (error.response?.status === 401 && !url.startsWith('/auth/')) {
      sessionStorage.setItem('platform_expired', '1');
      window.location.hash = '#/login';
    }
    return Promise.reject(error);
  },
);

export const errMsg = (e, fallback = 'حدث خطأ') => {
  const d = e?.response?.data?.detail;
  if (typeof d === 'string') return d;
  if (Array.isArray(d)) return d.map((x) => x.msg).join('، ');
  return fallback;
};

export const platformAPI = {
  login: (username, password) => api.post('/auth/login', { username, password }),
  mfa: (mfa_token, code) => api.post('/auth/mfa', { mfa_token, code }),
  logout: () => api.post('/auth/logout'),
  me: () => api.get('/auth/me'),
  changePassword: (data) => api.post('/auth/change-password', data),

  meta: () => api.get('/meta'),
  tenants: () => api.get('/tenants'),
  createTenant: (data) => api.post('/tenants', data),
  tenant: (id) => api.get(`/tenants/${id}`),
  updateIdentity: (id, data) => api.put(`/tenants/${id}/identity`, data),
  updateCapabilities: (id, data) => api.put(`/tenants/${id}/capabilities`, data),
  suspend: (id, reason) => api.post(`/tenants/${id}/suspend`, { reason }),
  activate: (id) => api.post(`/tenants/${id}/activate`),
  resetPassword: (id, uid) => api.post(`/tenants/${id}/users/${uid}/reset-password`),
  deleteTenant: (id, confirm_slug) => api.delete(`/tenants/${id}`, { data: { confirm_slug } }),
  activity: (id) => api.get(`/tenants/${id}/activity`),
  audit: (params) => api.get('/audit', { params }),
};
