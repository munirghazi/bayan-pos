const POS_SETTINGS_KEY = 'pos_settings';

const DEFAULTS = {
  paymentMethods: { cash: true, card: true, transfer: true },
  showDonation: true,
  logoUrl: '',
};

export function getPOSSettings() {
  try {
    const saved = localStorage.getItem(POS_SETTINGS_KEY);
    if (saved) {
      const parsed = JSON.parse(saved);
      return {
        ...DEFAULTS,
        ...parsed,
        paymentMethods: { ...DEFAULTS.paymentMethods, ...parsed.paymentMethods },
      };
    }
  } catch (e) {}
  return { ...DEFAULTS };
}

export function savePOSSettings(settings) {
  localStorage.setItem(POS_SETTINGS_KEY, JSON.stringify(settings));
}


// ---- Phase 3: per-tenant capabilities (donation / trade / mixed) ----
const CAPS_KEY = 'tenant_caps';
const CAP_DEFAULTS = {
  business_type: 'mixed',
  sales_enabled: true,
  donations_enabled: true,
  purchasing_enabled: true,
  vat_enabled: true,
  inventory_enabled: true,
  verification_status: 'verified',
};

export function getCapabilities() {
  try {
    const saved = localStorage.getItem(CAPS_KEY);
    if (saved) return { ...CAP_DEFAULTS, ...JSON.parse(saved) };
  } catch (e) {}
  return { ...CAP_DEFAULTS };
}

export function saveCapabilities(caps) {
  localStorage.setItem(CAPS_KEY, JSON.stringify(caps || {}));
}
