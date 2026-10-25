// AlKashi UI kit — touch-first primitives. Colors follow the tenant theme
// (bayan-* Tailwind classes map to CSS variables), radii follow --radius-*.
import { HiOutlineX } from 'react-icons/hi';

const cx = (...a) => a.filter(Boolean).join(' ');

// ---------------- Button ----------------
const BTN_VARIANTS = {
  primary: 'bg-bayan-green text-white hover:bg-bayan-dark shadow-card',
  secondary: 'bg-gray-100 text-gray-700 hover:bg-gray-200',
  ghost: 'bg-transparent text-gray-600 hover:bg-gray-100',
  danger: 'bg-red-50 text-red-600 hover:bg-red-100',
  outline: 'bg-white text-gray-700 border border-gray-300 hover:bg-gray-50',
};
const BTN_SIZES = {
  sm: 'min-h-[40px] px-4 text-sm gap-1.5',
  md: 'min-h-[48px] px-5 text-base gap-2',       // touch default
  lg: 'min-h-[56px] px-7 text-lg gap-2.5',
};
export function Button({ variant = 'primary', size = 'md', className, icon, loading, children, disabled, ...rest }) {
  return (
    <button
      disabled={disabled || loading}
      className={cx('inline-flex items-center justify-center font-medium rounded-xl transition-all pressable disabled:opacity-50 disabled:pointer-events-none',
        BTN_VARIANTS[variant], BTN_SIZES[size], className)}
      {...rest}>
      {loading ? <Spinner size={size === 'lg' ? 22 : 18} className="text-current" /> : icon}
      {children}
    </button>
  );
}

// ---------------- IconButton (touch-sized) ----------------
export function IconButton({ className, tone = 'default', children, ...rest }) {
  const tones = {
    default: 'text-gray-600 hover:bg-gray-100',
    primary: 'text-bayan-green hover:bg-bayan-light/40',
    danger: 'text-red-600 hover:bg-red-50',
  };
  return (
    <button className={cx('inline-flex items-center justify-center w-11 h-11 rounded-xl transition-all pressable', tones[tone], className)} {...rest}>
      {children}
    </button>
  );
}

// ---------------- Card ----------------
export function Card({ className, children, padded = true, ...rest }) {
  return (
    <div className={cx('bg-white rounded-2xl border border-gray-100 shadow-card', padded && 'p-5', className)} {...rest}>
      {children}
    </div>
  );
}

// ---------------- Field / Input / Select / Textarea ----------------
const FIELD_BASE = 'w-full min-h-[48px] px-4 rounded-xl border border-gray-300 bg-white text-base outline-none focus:border-bayan-green focus:ring-2 focus:ring-bayan-green/30 transition-all placeholder:text-gray-400';
export function Field({ label, hint, error, children }) {
  return (
    <div className="space-y-1.5">
      {label && <label className="block text-sm font-medium text-gray-600">{label}</label>}
      {children}
      {error ? <p className="text-xs text-red-500">{error}</p> : hint ? <p className="text-xs text-gray-400">{hint}</p> : null}
    </div>
  );
}
export function Input({ className, ...rest }) { return <input className={cx(FIELD_BASE, className)} {...rest} />; }
export function Textarea({ className, ...rest }) { return <textarea className={cx(FIELD_BASE, 'py-3 min-h-[80px]', className)} {...rest} />; }
export function Select({ className, children, ...rest }) {
  return <select className={cx(FIELD_BASE, 'appearance-none bg-white pl-10', className)} {...rest}>{children}</select>;
}

// ---------------- Badge ----------------
const BADGE = {
  gray: 'bg-gray-100 text-gray-600', green: 'bg-emerald-100 text-emerald-700',
  amber: 'bg-amber-100 text-amber-700', red: 'bg-red-100 text-red-700',
  indigo: 'bg-bayan-light text-bayan-green', blue: 'bg-blue-100 text-blue-700',
};
export function Badge({ tone = 'gray', className, children }) {
  return <span className={cx('inline-flex items-center gap-1 text-xs font-medium px-2.5 py-1 rounded-full', BADGE[tone], className)}>{children}</span>;
}

// ---------------- Spinner ----------------
export function Spinner({ size = 20, className }) {
  return (
    <svg className={cx('animate-spin', className)} width={size} height={size} viewBox="0 0 24 24" fill="none">
      <circle cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="3" opacity="0.2" />
      <path d="M22 12a10 10 0 0 1-10 10" stroke="currentColor" strokeWidth="3" strokeLinecap="round" />
    </svg>
  );
}

// ---------------- PageHeader ----------------
export function PageHeader({ title, subtitle, actions, icon }) {
  return (
    <div className="flex flex-wrap items-center justify-between gap-3 mb-5">
      <div className="flex items-center gap-3">
        {icon && <div className="w-11 h-11 rounded-xl bg-bayan-light/50 text-bayan-green flex items-center justify-center text-2xl">{icon}</div>}
        <div>
          <h1 className="text-2xl font-bold text-gray-800">{title}</h1>
          {subtitle && <p className="text-gray-500 text-sm mt-0.5">{subtitle}</p>}
        </div>
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </div>
  );
}

// ---------------- EmptyState ----------------
export function EmptyState({ icon, title, subtitle, action }) {
  return (
    <div className="flex flex-col items-center justify-center text-center py-14 px-6">
      {icon && <div className="text-5xl text-gray-300 mb-3">{icon}</div>}
      <p className="text-gray-600 font-medium">{title}</p>
      {subtitle && <p className="text-gray-400 text-sm mt-1">{subtitle}</p>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  );
}

// ---------------- Modal ----------------
const MODAL_SIZES = { sm: 'max-w-md', md: 'max-w-lg', lg: 'max-w-2xl', xl: 'max-w-4xl' };
export function Modal({ title, size = 'md', onClose, children, footer }) {
  return (
    <div className="fixed inset-0 bg-black/40 backdrop-blur-sm flex items-end sm:items-center justify-center p-0 sm:p-4 z-50" onClick={onClose}>
      <div className={cx('bg-white w-full rounded-t-3xl sm:rounded-2xl shadow-xl flex flex-col max-h-[92vh] sm:max-h-[88vh]', MODAL_SIZES[size])}
        onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between px-5 sm:px-6 py-4 border-b border-gray-100">
          <h2 className="text-lg font-bold text-gray-800">{title}</h2>
          <IconButton onClick={onClose} aria-label="إغلاق"><HiOutlineX className="text-xl" /></IconButton>
        </div>
        <div className="px-5 sm:px-6 py-5 overflow-auto scroll-touch">{children}</div>
        {footer && <div className="px-5 sm:px-6 py-4 border-t border-gray-100 flex gap-2 justify-end">{footer}</div>}
      </div>
    </div>
  );
}


// ---------------- Tabs (segmented, touch-friendly) ----------------
export function Tabs({ value, onChange, tabs }) {
  return (
    <div className="inline-flex p-1 bg-gray-100 rounded-2xl gap-1">
      {tabs.map((t) => (
        <button key={t.value} onClick={() => onChange(t.value)}
          className={cx('inline-flex items-center gap-2 min-h-[44px] px-5 rounded-xl text-sm font-medium transition-all pressable',
            value === t.value ? 'bg-white text-bayan-green shadow-card' : 'text-gray-500 hover:text-gray-700')}>
          {t.icon}{t.label}
        </button>
      ))}
    </div>
  );
}
