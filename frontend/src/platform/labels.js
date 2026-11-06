export const ACTIONS = {
  login: 'تسجيل دخول',
  login_failed: 'محاولة دخول فاشلة',
  login_locked: 'قفل الحساب مؤقتاً',
  logout: 'تسجيل خروج',
  mfa_enrolled: 'تفعيل التحقق الثنائي',
  mfa_reset: 'إعادة ضبط التحقق الثنائي (سطر الأوامر)',
  password_changed: 'تغيير كلمة مرور المشرف',
  admin_created: 'إنشاء مشرف منصة (سطر الأوامر)',
  admin_unlocked: 'فك قفل مشرف (سطر الأوامر)',
  admin_disabled: 'تعطيل مشرف (سطر الأوامر)',
  admin_enabled: 'تفعيل مشرف (سطر الأوامر)',
  admin_password_set: 'تعيين كلمة مرور مشرف (سطر الأوامر)',
  tenant_created: 'إنشاء منشأة',
  tenant_deleted: 'حذف منشأة',
  tenant_suspended: 'إيقاف منشأة',
  tenant_activated: 'تفعيل منشأة',
  identity_updated: 'تعديل الهوية',
  capabilities_updated: 'تعديل الصلاحيات',
  user_password_reset: 'إعادة تعيين كلمة مرور مستخدم',
};

export const FIELDS = {
  name: 'الاسم القانوني (عربي)', name_en: 'الاسم القانوني (إنجليزي)', entity_type: 'نوع المنشأة',
  unified_number: 'الرقم الموحد', cr_number: 'رقم السجل التجاري', license_number: 'رقم الترخيص',
  freelance_doc_number: 'رقم وثيقة العمل الحر', vat_enabled: 'مسجلة في الضريبة', vat_number: 'الرقم الضريبي',
  vat_rate: 'نسبة الضريبة', sales_enabled: 'البيع', donations_enabled: 'التبرعات',
  purchasing_enabled: 'المشتريات', inventory_enabled: 'المخزون', show_powered_by: 'عبارة «يعمل بواسطة»',
  verification_status: 'حالة التحقق',
  sales: 'البيع', donations: 'التبرعات', admin_username: 'مستخدم المدير', reason: 'السبب',
  stage: 'المرحلة', why: 'السبب', stats: 'الإحصاءات', role: 'الدور',
};

export const ENTITY = {
  nonprofit_association: 'جمعية أهلية', nonprofit_foundation: 'مؤسسة أهلية', endowment: 'وقف',
  cooperative: 'جمعية تعاونية', company: 'شركة', sole_establishment: 'مؤسسة فردية',
  online_store: 'متجر إلكتروني', freelancer: 'عمل حر', other: 'أخرى',
};
const VALUES = { ...ENTITY, password: 'كلمة المرور', totp: 'رمز التحقق', 'commercial type': 'نوع تجاري',
  admin: 'مدير', manager: 'مشرف', cashier: 'كاشير' };

export const VERIFICATION = { verified: 'موثّقة', pending: 'قيد المراجعة', limited: 'محدودة', rejected: 'مرفوضة' };
export const ROLES = { admin: 'مدير', manager: 'مشرف', cashier: 'كاشير' };

// Gregorian calendar + Latin digits, Riyadh time (operators compare these with logs).
const LOCALE = 'ar-SA-u-ca-gregory-nu-latn';
const RIYADH = { timeZone: 'Asia/Riyadh' };
export const fmt = (v, withTime = true) => {
  if (!v) return '—';
  let s = String(v);
  if (!/[zZ]|[+-]\d\d:?\d\d$/.test(s)) s += 'Z';          // naive timestamps are UTC
  const d = new Date(s);
  if (Number.isNaN(d.getTime())) return '—';
  const date = d.toLocaleDateString(LOCALE, { ...RIYADH, year: 'numeric', month: '2-digit', day: '2-digit' });
  if (!withTime) return date;
  return `${date} ${d.toLocaleTimeString(LOCALE, { ...RIYADH, hour: '2-digit', minute: '2-digit' })}`;
};

export const describeDetail = (detail) => {
  if (!detail) return '';
  const show = (x) => (x === true ? 'نعم' : x === false ? 'لا' : x === null || x === undefined || x === '' ? '—' : VALUES[x] ?? x);
  return Object.entries(detail).map(([k, v]) => {
    const label = FIELDS[k] || k;
    if (v && typeof v === 'object' && 'to' in v) return `${label}: ${show(v.from)} ← ${show(v.to)}`;
    if (k === 'stats' && v) return `المستندات: ${v.documents ?? 0} · المستخدمون: ${v.users ?? 0}`;
    if (v && typeof v === 'object') return `${label}: ${JSON.stringify(v)}`;
    return `${label}: ${show(v)}`;
  }).join(' · ');
};
