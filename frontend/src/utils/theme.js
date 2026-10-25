// White-label theming applied at runtime via CSS variables.
// Colors (Phase 1) + font family and UI radius (Phase 1b). Tailwind brand
// colors, the base font, and the border-radius scale all read these vars,
// so existing components re-theme without markup changes.

const KEY = 'tenant_theme';
const COLOR_VARS = ['--brand-primary-rgb', '--brand-dark-rgb', '--brand-light-rgb', '--brand-accent-rgb'];
const RADIUS_VARS = ['--radius', '--radius-md', '--radius-lg', '--radius-xl', '--radius-2xl'];

// ---- curated, Arabic-first web fonts (self-host later for PDPL hardening) ----
export const FONT_OPTIONS = [
  'Cairo', 'Tajawal', 'Almarai', 'IBM Plex Sans Arabic',
  'Noto Kufi Arabic', 'Changa', 'El Messiri', 'Readex Pro',
];
const FONT_SPECS = {
  // Cairo is already loaded in index.html -> no dynamic load needed
  'Tajawal': 'Tajawal:wght@300;400;500;700;800',
  'Almarai': 'Almarai:wght@300;400;700;800',
  'IBM Plex Sans Arabic': 'IBM+Plex+Sans+Arabic:wght@300;400;500;600;700',
  'Noto Kufi Arabic': 'Noto+Kufi+Arabic:wght@300;400;500;700',
  'Changa': 'Changa:wght@300;400;500;700',
  'El Messiri': 'El+Messiri:wght@400;500;600;700',
  'Readex Pro': 'Readex+Pro:wght@300;400;500;600;700',
};

export const RADIUS_OPTIONS = [
  { value: 'default', label: 'افتراضي' },
  { value: 'sharp', label: 'حاد' },
  { value: 'rounded', label: 'دائري' },
];
const RADII = {
  sharp:   { '--radius': '0.125rem', '--radius-md': '0.125rem', '--radius-lg': '0.1875rem', '--radius-xl': '0.25rem', '--radius-2xl': '0.375rem' },
  rounded: { '--radius': '0.375rem', '--radius-md': '0.5rem',   '--radius-lg': '0.75rem',   '--radius-xl': '1rem',    '--radius-2xl': '1.25rem' },
};

// ---------- colors ----------
function hexToRgb(hex) {
  if (!hex) return null;
  const h = String(hex).trim().replace('#', '');
  const n = h.length === 3 ? h.split('').map((x) => x + x).join('') : h;
  if (!/^[0-9a-fA-F]{6}$/.test(n)) return null;
  return [parseInt(n.slice(0, 2), 16), parseInt(n.slice(2, 4), 16), parseInt(n.slice(4, 6), 16)];
}
const triplet = (rgb) => `${rgb[0]} ${rgb[1]} ${rgb[2]}`;
const darken = (rgb, f = 0.82) => rgb.map((x) => Math.round(x * f));
const tint = (rgb, t = 0.88) => rgb.map((x) => Math.round(x * (1 - t) + 255 * t));

// ---------- font loading ----------
function loadFont(name) {
  const spec = FONT_SPECS[name];
  if (!spec) return; // Cairo (default) or unknown -> nothing to load
  const id = 'font-' + name.replace(/\s+/g, '-');
  if (document.getElementById(id)) return;
  const link = document.createElement('link');
  link.id = id; link.rel = 'stylesheet';
  link.href = `https://fonts.googleapis.com/css2?family=${spec}&display=swap`;
  document.head.appendChild(link);
}

function setFavicon(url) {
  if (!url) return;
  let link = document.querySelector("link[rel~='icon']");
  if (!link) { link = document.createElement('link'); link.rel = 'icon'; document.head.appendChild(link); }
  link.href = url;
}

function applyRadius(scale) {
  const root = document.documentElement.style;
  RADIUS_VARS.forEach((v) => root.removeProperty(v));      // reset -> fallback = default
  const set = RADII[scale];
  if (set) Object.entries(set).forEach(([k, v]) => root.setProperty(k, v));
}

export function applyTheme(s = {}) {
  const root = document.documentElement.style;
  const p = hexToRgb(s.primary_color);
  if (p) {
    root.setProperty('--brand-primary-rgb', triplet(p));
    root.setProperty('--brand-dark-rgb', triplet(darken(p)));
    root.setProperty('--brand-light-rgb', triplet(tint(p)));
  }
  const a = hexToRgb(s.accent_color);
  if (a) root.setProperty('--brand-accent-rgb', triplet(a));

  if (s.font_family) { loadFont(s.font_family); root.setProperty('--brand-font', `'${s.font_family}'`); }
  if (s.ui_radius) applyRadius(s.ui_radius);

  if (s.favicon_url) setFavicon(s.favicon_url);
  const name = s.brand_name || s.name;
  if (name) document.title = name;
}

export function storeTheme(s = {}) {
  try {
    localStorage.setItem(KEY, JSON.stringify({
      primary_color: s.primary_color || null,
      accent_color: s.accent_color || null,
      favicon_url: s.favicon_url || null,
      brand_name: s.brand_name || null,
      font_family: s.font_family || null,
      ui_radius: s.ui_radius || null,
    }));
  } catch (e) {}
}

export function loadStoredTheme() {
  try {
    const t = JSON.parse(localStorage.getItem(KEY) || 'null');
    if (t) applyTheme(t);
  } catch (e) {}
}

export function clearTheme() {
  localStorage.removeItem(KEY);
  const root = document.documentElement.style;
  [...COLOR_VARS, ...RADIUS_VARS, '--brand-font'].forEach((v) => root.removeProperty(v));
  document.title = 'سهل';
}
