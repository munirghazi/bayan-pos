/**
 * ZATCA Simplified Tax Invoice - QR Code Generator
 * Based on ZATCA E-Invoicing TLV (Tag-Length-Value) specification
 * 
 * Tags:
 *   1 = Seller Name (اسم البائع)
 *   2 = VAT Registration Number (الرقم الضريبي)
 *   3 = Invoice Date/Time (تاريخ ووقت الفاتورة) - ISO 8601
 *   4 = Invoice Total with VAT (إجمالي الفاتورة شامل الضريبة)
 *   5 = VAT Amount (مبلغ الضريبة)
 */

/**
 * Encode a single TLV (Tag-Length-Value) entry
 */
function encodeTLV(tag, value) {
  const encoder = new TextEncoder();
  const valueBytes = encoder.encode(String(value));
  const tlv = new Uint8Array(2 + valueBytes.length);
  tlv[0] = tag;
  tlv[1] = valueBytes.length;
  tlv.set(valueBytes, 2);
  return tlv;
}

/**
 * Concatenate multiple Uint8Array buffers
 */
function concatBuffers(...buffers) {
  const totalLength = buffers.reduce((sum, buf) => sum + buf.length, 0);
  const result = new Uint8Array(totalLength);
  let offset = 0;
  for (const buf of buffers) {
    result.set(buf, offset);
    offset += buf.length;
  }
  return result;
}

/**
 * Convert Uint8Array to base64 string (browser-safe)
 */
function toBase64(bytes) {
  let binary = '';
  for (let i = 0; i < bytes.length; i++) {
    binary += String.fromCharCode(bytes[i]);
  }
  return btoa(binary);
}

/**
 * Generate ZATCA-compliant QR code data (base64 TLV string)
 * 
 * @param {Object} params
 * @param {string} params.sellerName - اسم البائع
 * @param {string} params.vatNumber - الرقم الضريبي
 * @param {string} params.timestamp - تاريخ ووقت الفاتورة (ISO 8601)
 * @param {number} params.totalWithVat - إجمالي الفاتورة شامل الضريبة
 * @param {number} params.vatAmount - مبلغ الضريبة
 * @returns {string} Base64 encoded TLV string for QR code
 */
export function generateZATCAQR({
  sellerName,
  vatNumber,
  timestamp,
  totalWithVat,
  vatAmount,
}) {
  const tlv1 = encodeTLV(1, sellerName);
  const tlv2 = encodeTLV(2, vatNumber);
  const tlv3 = encodeTLV(3, timestamp);
  const tlv4 = encodeTLV(4, Number(totalWithVat).toFixed(2));
  const tlv5 = encodeTLV(5, Number(vatAmount).toFixed(2));

  const allTLV = concatBuffers(tlv1, tlv2, tlv3, tlv4, tlv5);
  return toBase64(allTLV);
}

/**
 * Default store/charity settings for ZATCA
 */
export const ZATCA_DEFAULTS = {
  sellerName: 'جمعية بيان بمكة المكرمة',
  vatNumber: '300000000000003', // Placeholder - update in Settings
  vatRate: 0.15, // 15% VAT
};

/**
 * Get ZATCA settings from localStorage or use defaults
 */
export function getZATCASettings() {
  try {
    const saved = localStorage.getItem('zatca_settings');
    if (saved) {
      return { ...ZATCA_DEFAULTS, ...JSON.parse(saved) };
    }
  } catch (e) {}
  return { ...ZATCA_DEFAULTS };
}

/**
 * Save ZATCA settings to localStorage
 */
export function saveZATCASettings(settings) {
  localStorage.setItem('zatca_settings', JSON.stringify(settings));
}

/**
 * Calculate VAT breakdown for a list of items
 * Supports tax-exempt items (is_tax_exempt flag)
 * 
 * @param {Array} items - Array of {price, quantity, is_tax_exempt}
 * @param {number} vatRate - VAT rate (default 0.15)
 * @returns {{ taxableTotal: number, exemptTotal: number, vatAmount: number, totalBeforeVat: number, totalWithVat: number }}
 */
export function calculateItemsVAT(items, vatRate = 0.15) {
  let taxableTotal = 0;
  let exemptTotal = 0;

  for (const item of items) {
    const lineTotal = item.price * item.quantity;
    if (item.is_tax_exempt) {
      exemptTotal += lineTotal;
    } else {
      taxableTotal += lineTotal;
    }
  }

  // Taxable items: price is assumed to be VAT-inclusive
  const taxableBeforeVat = taxableTotal / (1 + vatRate);
  const vatAmount = taxableTotal - taxableBeforeVat;
  const totalBeforeVat = taxableBeforeVat + exemptTotal;
  const totalWithVat = taxableTotal + exemptTotal;

  return {
    taxableTotal: Math.round(taxableTotal * 100) / 100,
    exemptTotal: Math.round(exemptTotal * 100) / 100,
    vatAmount: Math.round(vatAmount * 100) / 100,
    totalBeforeVat: Math.round(totalBeforeVat * 100) / 100,
    totalWithVat: Math.round(totalWithVat * 100) / 100,
  };
}

/**
 * Calculate VAT for a single amount (backwards compat)
 * @param {number} totalWithVat - Total including VAT
 * @param {number} vatRate - VAT rate (default 0.15)
 * @returns {{ totalBeforeVat: number, vatAmount: number }}
 */
export function calculateVAT(totalWithVat, vatRate = 0.15) {
  const totalBeforeVat = totalWithVat / (1 + vatRate);
  const vatAmount = totalWithVat - totalBeforeVat;
  return {
    totalBeforeVat: Math.round(totalBeforeVat * 100) / 100,
    vatAmount: Math.round(vatAmount * 100) / 100,
  };
}
