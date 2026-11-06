// Per-user permissions (server-enforced; the UI only hides what can't be used).
// The logged-in user (with effective `permissions`) is kept in localStorage.user.

export function currentUser() {
  try { return JSON.parse(localStorage.getItem('user') || '{}'); } catch (e) { return {}; }
}

export function isAdmin() {
  return currentUser().role === 'admin';
}

/** true when the user has ANY of the given permission keys (admins: always). */
export function can(...keys) {
  const u = currentUser();
  if (u.role === 'admin') return true;
  const p = u.permissions || [];
  return keys.some((k) => p.includes(k));
}

// Which permission opens which page (admin-only pages use 'admin').
export const PAGE_PERMS = {
  '/': ['reports'],
  '/pos': ['sell', 'donate'],
  '/products': ['products', 'stock_adjust', 'sell', 'consignment'],
  '/consignment': ['consignment'],
  '/donations': ['donate', 'void_donations', 'reports'],
  '/returns': ['returns'],
  '/reports': ['reports'],
  '/branches': ['branches'],
  '/register-closing': ['register_close'],
  '/suppliers': ['suppliers', 'purchasing'],
  '/uom': ['products'],
  '/inventory': ['stock_adjust', 'receiving', 'products'],
  '/purchase-orders': ['purchasing', 'po_approve', 'receiving'],
  '/settings': ['admin'],
  '/privacy': ['admin'],
};

export function canOpen(path) {
  const need = PAGE_PERMS[path];
  if (!need) return true;
  if (need.includes('admin')) return isAdmin();
  return can(...need);
}

/** First page this user may open (the home page when they can't see reports). */
export function homePath() {
  for (const p of ['/', '/pos', '/products', '/inventory', '/purchase-orders', '/suppliers', '/returns', '/register-closing']) {
    if (canOpen(p)) return p;
  }
  return '/change-password';
}
