import { forwardRef, useEffect, useState } from 'react';
import QRCode from 'qrcode';
import { SarIcon } from './SarIcon';
import { getZATCASettings } from '../utils/zatca';
import { getPOSSettings } from '../utils/posSettings';
import { fmtDateTime } from '../utils/datetime';

const paymentMethodAr = {
  cash: 'نقدي',
  card: 'شبكة',
  transfer: 'تحويل بنكي',
};

const money = (v) => Number(v || 0).toFixed(2);

/**
 * Prints exactly what was ISSUED — every figure comes from the stored document
 * (number, VAT, seller identity, QR). Nothing tax-related is recomputed here,
 * so a reprint is identical to the original even after settings change.
 *
 *   type="sale"         sale        → فاتورة ضريبية مبسطة (or فاتورة if not VAT-registered)
 *   type="credit_note"  creditNote  → إشعار دائن, referencing the original invoice
 *   type="donation"     donation    → إيصال تبرع — never a tax invoice, never a QR
 */
const Receipt = forwardRef(({ sale, type = 'sale', donation = null, creditNote = null }, ref) => {
  const now = new Date();
  const branding = getZATCASettings();          // logo / footer / website only
  const posSettings = getPOSSettings();
  const logoUrl = posSettings.logoUrl;

  const doc = type === 'sale' ? sale : type === 'credit_note' ? creditNote : donation;
  const seller = (doc && doc.seller) || {};
  const isTax = type !== 'donation' && !!(doc && doc.is_tax_invoice);
  const qrData = isTax ? doc?.qr_data : null;

  const [qrImg, setQrImg] = useState('');
  useEffect(() => {
    if (!qrData) { setQrImg(''); return; }
    QRCode.toDataURL(qrData, { margin: 1, width: 320 })
      .then(setQrImg)
      .catch(() => setQrImg(''));
  }, [qrData]);

  if (!doc) return null;

  const title = type === 'donation'
    ? 'إيصال تبرع'
    : type === 'credit_note'
      ? (isTax ? 'إشعار دائن لفاتورة ضريبية مبسطة' : 'إشعار دائن')
      : (isTax ? 'فاتورة ضريبية مبسطة' : 'فاتورة');

  const lines = doc.items || [];
  const vatRates = [...new Set(lines.map((l) => Number(l.vat_rate || 0)).filter((r) => r > 0))];

  return (
    <div ref={ref} className="receipt-content bg-white p-6 max-w-sm mx-auto text-sm" dir="rtl" style={{ fontFamily: 'Cairo, sans-serif' }}>
      {/* Header — seller identity as stored on the document */}
      <div className="text-center border-b-2 border-dashed border-gray-400 pb-4 mb-4">
        {logoUrl && (
          <img
            src={logoUrl}
            alt="الشعار"
            style={{ maxHeight: '64px', maxWidth: '180px', margin: '0 auto 8px', objectFit: 'contain' }}
          />
        )}
        <h2 className="text-lg font-bold text-gray-800">{seller.name || '— يرجى ضبط بيانات الجهة في الإعدادات —'}</h2>
        {branding.website && <p className="text-gray-500 text-xs mt-1">{branding.website}</p>}
        {[seller.building_number, seller.street_name].filter(Boolean).length > 0 && (
          <p className="text-gray-500 text-xs mt-1">{[seller.building_number, seller.street_name].filter(Boolean).join(' ')}</p>
        )}
        {[seller.district, seller.city, seller.postal_code].filter(Boolean).length > 0 && (
          <p className="text-gray-500 text-xs">{[seller.district, seller.city, seller.postal_code].filter(Boolean).join('، ')}</p>
        )}
        {[seller.region, seller.country].filter(Boolean).length > 0 && (
          <p className="text-gray-500 text-xs">{[seller.region, seller.country].filter(Boolean).join('، ')}</p>
        )}
        {!seller.building_number && seller.national_address && (
          <p className="text-gray-500 text-xs">{seller.national_address}</p>
        )}
        {isTax && seller.vat_number && (
          <p className="text-gray-600 text-xs mt-1">الرقم الضريبي: <span dir="ltr">{seller.vat_number}</span></p>
        )}
        {type === 'donation' && seller.cr_number && (
          <p className="text-gray-500 text-xs mt-1">رقم الترخيص / السجل: {seller.cr_number}</p>
        )}
      </div>

      {/* Title */}
      <div className="text-center mb-3">
        <p className="text-base font-bold" style={type === 'donation' ? { color: '#1a7a4c' } : undefined}>{title}</p>
        {type === 'donation' && doc.status === 'void' && (
          <p className="text-red-600 font-bold text-sm mt-1 border-2 border-red-600 inline-block px-3 rounded">ملغى</p>
        )}
      </div>

      {/* ===== Sale / credit note ===== */}
      {type !== 'donation' && (
        <>
          <div className="text-xs text-gray-600 mb-3 space-y-0.5">
            <div className="flex justify-between">
              <span>{type === 'credit_note' ? 'رقم الإشعار' : 'رقم الفاتورة'}</span>
              <span dir="ltr" className="font-medium">{type === 'credit_note' ? doc.credit_note_number : doc.invoice_number}</span>
            </div>
            <div className="flex justify-between">
              <span>التاريخ والوقت</span>
              <span>{fmtDateTime(doc.issued_at || doc.created_at)}</span>
            </div>
            {type === 'credit_note' && (
              <>
                <div className="flex justify-between">
                  <span>الفاتورة الأصلية</span>
                  <span dir="ltr" className="font-medium">{doc.original_invoice_number}</span>
                </div>
                {doc.original_issued_at && (
                  <div className="flex justify-between">
                    <span>تاريخ الفاتورة الأصلية</span>
                    <span>{fmtDateTime(doc.original_issued_at)}</span>
                  </div>
                )}
                <div className="flex justify-between">
                  <span>سبب الإصدار</span>
                  <span>{doc.reason}</span>
                </div>
              </>
            )}
          </div>

          <table className="w-full text-xs mb-3">
            <thead>
              <tr className="border-b border-gray-300">
                <th className="text-right py-1">الصنف</th>
                <th className="text-center py-1">الكمية</th>
                <th className="text-center py-1">السعر</th>
                <th className="text-left py-1">المجموع</th>
              </tr>
            </thead>
            <tbody>
              {lines.map((item, idx) => (
                <tr key={idx} className="border-b border-gray-200">
                  <td className="py-1">
                    {item.product_name}
                    {isTax && item.is_tax_exempt && (
                      <span className="text-gray-400 mr-1" style={{ fontSize: '9px' }}>(معفى)</span>
                    )}
                  </td>
                  <td className="text-center py-1">{item.quantity}{item.uom_name ? ` ${item.uom_name}` : ''}</td>
                  <td className="text-center py-1">{money(item.price)}</td>
                  <td className="text-left py-1">{money(item.line_total ?? item.quantity * item.price)}</td>
                </tr>
              ))}
            </tbody>
          </table>

          <div className="border-t-2 border-dashed border-gray-400 pt-3 space-y-1">
            {isTax && (
              <>
                <div className="flex justify-between text-xs text-gray-600">
                  <span>الإجمالي غير شامل الضريبة</span>
                  <span>{money(doc.subtotal)} <SarIcon size={11} /></span>
                </div>
                {Number(doc.exempt_amount) > 0 && (
                  <div className="flex justify-between text-xs text-gray-500">
                    <span>منه أصناف معفاة</span>
                    <span>{money(doc.exempt_amount)} <SarIcon size={11} /></span>
                  </div>
                )}
                <div className="flex justify-between text-xs text-gray-600">
                  <span>ضريبة القيمة المضافة{vatRates.length === 1 ? ` (${vatRates[0]}%)` : ''}</span>
                  <span>{money(doc.vat_amount)} <SarIcon size={11} /></span>
                </div>
              </>
            )}
            <div className="flex justify-between font-bold text-base pt-1 border-t border-gray-200">
              <span>{type === 'credit_note' ? 'المبلغ المسترد' : isTax ? 'الإجمالي شامل الضريبة' : 'الإجمالي'}</span>
              <span>{money(doc.total)} <SarIcon size={14} /></span>
            </div>
            {type === 'sale' && (
              <>
                <div className="flex justify-between text-xs text-gray-500 mt-1">
                  <span>طريقة الدفع</span>
                  <span>{paymentMethodAr[doc.payment_method] || doc.payment_method}</span>
                </div>
                {doc.card_ref && (
                  <div className="flex justify-between text-xs text-gray-500">
                    <span>رمز العملية</span>
                    <span dir="ltr">{doc.card_ref}</span>
                  </div>
                )}
              </>
            )}
          </div>

          {qrData && (
            <div className="text-center mt-4 pt-3 border-t border-dashed border-gray-300">
              <div data-qr-slot data-qr={qrData} style={{ display: 'inline-block', background: '#fff', padding: '8px' }}>
                {qrImg && <img src={qrImg} alt="ZATCA QR" width={150} height={150} style={{ display: 'block' }} />}
              </div>
            </div>
          )}
        </>
      )}

      {/* ===== Donation receipt ===== */}
      {type === 'donation' && (
        <div className="space-y-2 text-sm">
          <div className="flex justify-between">
            <span className="text-gray-600">رقم الإيصال:</span>
            <span className="font-medium" dir="ltr">{doc.receipt_number}</span>
          </div>
          {doc.donor_name && (
            <div className="flex justify-between">
              <span className="text-gray-600">اسم المتبرع:</span>
              <span className="font-medium">{doc.donor_name}</span>
            </div>
          )}
          <div className="flex justify-between">
            <span className="text-gray-600">المبلغ:</span>
            <span className="font-bold text-lg">{money(doc.amount)} <SarIcon size={16} /></span>
          </div>
          <div className="flex justify-between">
            <span className="text-gray-600">طريقة الدفع:</span>
            <span>{paymentMethodAr[doc.payment_method] || doc.payment_method}</span>
          </div>
          {doc.card_ref && (
            <div className="flex justify-between">
              <span className="text-gray-600">رمز العملية:</span>
              <span dir="ltr">{doc.card_ref}</span>
            </div>
          )}
          {doc.note && (
            <div className="flex justify-between">
              <span className="text-gray-600">ملاحظة:</span>
              <span>{doc.note}</span>
            </div>
          )}
          <div className="flex justify-between text-xs text-gray-500">
            <span>التاريخ:</span>
            <span>{fmtDateTime(doc.issued_at || doc.created_at)}</span>
          </div>
          {doc.status === 'void' && doc.void_reason && (
            <div className="flex justify-between text-xs text-red-600">
              <span>سبب الإلغاء:</span>
              <span>{doc.void_reason}</span>
            </div>
          )}
          <p className="text-center text-xs text-gray-500 mt-3 pt-2 border-t border-dashed border-gray-300">
            هذا الإيصال ليس فاتورة ضريبية
          </p>
        </div>
      )}

      {/* Footer */}
      <div className="text-center mt-6 pt-4 border-t-2 border-dashed border-gray-400">
        <p className="text-xs text-gray-500">جزاكم الله خيراً</p>
        {branding.receiptFooter && (
          <p className="text-xs text-gray-500 mt-1 whitespace-pre-line">{branding.receiptFooter}</p>
        )}
        <p className="text-[10px] text-gray-400 mt-1">طُبع: {fmtDateTime(now)}</p>
        {branding.showPoweredBy !== false && (
          <p className="text-[10px] text-gray-300 mt-2">مشغّل بواسطة سهل</p>
        )}
      </div>
    </div>
  );
});

Receipt.displayName = 'Receipt';

export default Receipt;
