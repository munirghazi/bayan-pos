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
