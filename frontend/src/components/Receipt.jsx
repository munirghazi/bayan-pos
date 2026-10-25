import { forwardRef, useMemo, useEffect, useState } from 'react';
import QRCode from 'qrcode';
import { SarIcon } from './SarIcon';
import { generateZATCAQR, getZATCASettings, calculateItemsVAT, calculateVAT } from '../utils/zatca';
import { getPOSSettings } from '../utils/posSettings';

const paymentMethodAr = {
  cash: 'نقدي',
  card: 'شبكة',
  transfer: 'تحويل',
};

const Receipt = forwardRef(({ sale, type = 'sale', donation = null }, ref) => {
  const now = new Date();
  const zatca = getZATCASettings();
  const posSettings = getPOSSettings();
  const logoUrl = posSettings.logoUrl;

  // Calculate VAT with tax-exempt items support
  const vatInfo = useMemo(() => {
    if (type === 'sale' && sale && sale.items) {
      return calculateItemsVAT(sale.items, zatca.vatRate);
    }
    return null;
  }, [sale, type, zatca]);

  // Generate ZATCA QR code data
  const qrData = useMemo(() => {
    if (type === 'sale' && sale) {
      const totalWithVat = vatInfo ? vatInfo.totalWithVat : sale.total;
      const vatAmount = vatInfo ? vatInfo.vatAmount : 0;
      return generateZATCAQR({
        sellerName: zatca.sellerName,
        vatNumber: zatca.vatNumber,
        timestamp: sale.created_at || now.toISOString(),
        totalWithVat,
        vatAmount,
      });
    }
    if (type === 'donation' && donation) {
      return generateZATCAQR({
        sellerName: zatca.sellerName,
        vatNumber: zatca.vatNumber,
        timestamp: donation.created_at || now.toISOString(),
        totalWithVat: donation.amount,
        vatAmount: 0,
      });
    }
    return null;
  }, [sale, donation, type, zatca, vatInfo]);

  const [qrImg, setQrImg] = useState('');
  useEffect(() => {
    if (!qrData) { setQrImg(''); return; }
    QRCode.toDataURL(qrData, { margin: 1, width: 320 })
      .then(setQrImg)
      .catch(() => setQrImg(''));
  }, [qrData]);

  return (
    <div ref={ref} className="receipt-content bg-white p-6 max-w-sm mx-auto text-sm" dir="rtl" style={{ fontFamily: 'Cairo, sans-serif' }}>
      {/* Header */}
      <div className="text-center border-b-2 border-dashed border-gray-400 pb-4 mb-4">
        {logoUrl && (
          <img
            src={logoUrl}
            alt="شعار الجمعية"
            style={{ maxHeight: '64px', maxWidth: '180px', margin: '0 auto 8px', objectFit: 'contain' }}
          />
        )}
        <h2 className="text-lg font-bold text-gray-800">{zatca.sellerName || '— يرجى ضبط بيانات الجهة في الإعدادات —'}</h2>
        {zatca.website && (
          <p className="text-gray-500 text-xs mt-1">{zatca.website}</p>
        )}
        {[zatca.buildingNumber, zatca.streetName].filter(Boolean).length > 0 && (
          <p className="text-gray-500 text-xs mt-1">
            {[zatca.buildingNumber, zatca.streetName].filter(Boolean).join(' ')}
          </p>
        )}
        {[zatca.district, zatca.city, zatca.postalCode].filter(Boolean).length > 0 && (
          <p className="text-gray-500 text-xs">
            {[zatca.district, zatca.city, zatca.postalCode].filter(Boolean).join('، ')}
          </p>
        )}
        {[zatca.region, zatca.country].filter(Boolean).length > 0 && (
          <p className="text-gray-500 text-xs">
            {[zatca.region, zatca.country].filter(Boolean).join('، ')}
          </p>
        )}
        {!zatca.buildingNumber && zatca.nationalAddress && (
          <p className="text-gray-500 text-xs">{zatca.nationalAddress}</p>
        )}
        {zatca.vatNumber && (
          <p className="text-gray-500 text-xs mt-1">الرقم الضريبي: {zatca.vatNumber}</p>
        )}
      </div>

      {type === 'sale' && sale && (
        <>
          {/* Invoice label */}
          <div className="text-center mb-3">
            <p className="text-base font-bold text-gray-700">فاتورة ضريبية مبسطة</p>
          </div>

          {/* Sale info */}
          <div className="flex justify-between text-xs text-gray-500 mb-3">
            <span>فاتورة رقم: {sale.id}</span>
            <span>{new Date(sale.created_at).toLocaleString('ar-SA')}</span>
          </div>

          {/* Items */}
          <table className="w-full text-xs mb-3">
            <thead>
              <tr className="border-b border-gray-300">
                <th className="text-right py-1">المنتج</th>
                <th className="text-center py-1">الكمية</th>
                <th className="text-center py-1">السعر</th>
                <th className="text-left py-1">المجموع</th>
              </tr>
            </thead>
            <tbody>
              {sale.items?.map((item, idx) => (
                <tr key={idx} className="border-b border-gray-200">
                  <td className="py-1">
                    {item.product_name}
                    {item.is_tax_exempt && (
                      <span className="text-gray-400 mr-1" style={{ fontSize: '9px' }}>(معفى)</span>
                    )}
                  </td>
                  <td className="text-center py-1">{item.quantity}{item.uom_name ? ` ${item.uom_name}` : ''}</td>
                  <td className="text-center py-1">{item.price.toFixed(2)}</td>
                  <td className="text-left py-1">{(item.quantity * item.price).toFixed(2)}</td>
                </tr>
              ))}
            </tbody>
          </table>

          {/* VAT Breakdown + Total */}
          <div className="border-t-2 border-dashed border-gray-400 pt-3 space-y-1">
            {vatInfo && (
              <>
                <div className="flex justify-between text-xs text-gray-600">
                  <span>المجموع قبل الضريبة</span>
                  <span>{vatInfo.totalBeforeVat.toFixed(2)} <SarIcon size={11} /></span>
                </div>
                {vatInfo.exemptTotal > 0 && (
                  <div className="flex justify-between text-xs text-gray-500">
                    <span>منتجات معفاة من الضريبة</span>
                    <span>{vatInfo.exemptTotal.toFixed(2)} <SarIcon size={11} /></span>
                  </div>
                )}
                <div className="flex justify-between text-xs text-gray-600">
                  <span>ضريبة القيمة المضافة ({(zatca.vatRate * 100).toFixed(0)}%)</span>
                  <span>{vatInfo.vatAmount.toFixed(2)} <SarIcon size={11} /></span>
                </div>
              </>
            )}
            <div className="flex justify-between font-bold text-base pt-1 border-t border-gray-200">
              <span>الإجمالي شامل الضريبة</span>
              <span>{sale.total.toFixed(2)} <SarIcon size={14} /></span>
            </div>
            <div className="flex justify-between text-xs text-gray-500 mt-1">
              <span>طريقة الدفع</span>
              <span>{paymentMethodAr[sale.payment_method] || sale.payment_method}</span>
            </div>
            {sale.card_ref && (
              <div className="flex justify-between text-xs text-gray-500">
                <span>رمز العملية</span>
                <span dir="ltr">{sale.card_ref}</span>
              </div>
            )}
          </div>

          {/* ZATCA QR Code */}
          {qrData && (
            <div className="text-center mt-4 pt-3 border-t border-dashed border-gray-300">
              <div data-qr-slot data-qr={qrData} style={{ display: 'inline-block', background: '#fff', padding: '8px' }}>
                {qrImg && <img src={qrImg} alt="ZATCA QR" width={150} height={150} style={{ display: 'block' }} />}
              </div>
              <p className="text-xs text-gray-400 mt-1">رمز الفاتورة الضريبية (ZATCA)</p>
            </div>
          )}
        </>
      )}

      {type === 'donation' && donation && (
        <>
          <div className="text-center mb-4">
            <p className="text-lg font-bold" style={{ color: '#1a7a4c' }}>إيصال تبرع</p>
          </div>
          <div className="space-y-2 text-sm">
            <div className="flex justify-between">
              <span className="text-gray-600">رقم الإيصال:</span>
              <span className="font-medium">{donation.id}</span>
            </div>
            {donation.donor_name && (
              <div className="flex justify-between">
                <span className="text-gray-600">اسم المتبرع:</span>
                <span className="font-medium">{donation.donor_name}</span>
              </div>
            )}
            <div className="flex justify-between">
              <span className="text-gray-600">المبلغ:</span>
              <span className="font-bold text-lg">{donation.amount.toFixed(2)} <SarIcon size={16} /></span>
            </div>
            <div className="flex justify-between">
              <span className="text-gray-600">طريقة الدفع:</span>
              <span>{paymentMethodAr[donation.payment_method] || donation.payment_method}</span>
            </div>
            {donation.card_ref && (
              <div className="flex justify-between">
                <span className="text-gray-600">رمز العملية:</span>
                <span dir="ltr">{donation.card_ref}</span>
              </div>
            )}
            {donation.note && (
              <div className="flex justify-between">
                <span className="text-gray-600">ملاحظة:</span>
                <span>{donation.note}</span>
              </div>
            )}
            <div className="flex justify-between text-xs text-gray-500">
              <span>التاريخ:</span>
              <span>{new Date(donation.created_at).toLocaleString('ar-SA')}</span>
            </div>
          </div>

          {/* QR Code for donation */}
          {qrData && (
            <div className="text-center mt-4 pt-3 border-t border-dashed border-gray-300">
              <div data-qr-slot data-qr={qrData} style={{ display: 'inline-block', background: '#fff', padding: '8px' }}>
                {qrImg && <img src={qrImg} alt="ZATCA QR" width={120} height={120} style={{ display: 'block' }} />}
              </div>
            </div>
          )}
        </>
      )}

      {/* Footer */}
      <div className="text-center mt-6 pt-4 border-t-2 border-dashed border-gray-400">
        <p className="text-xs text-gray-500">جزاكم الله خيراً</p>
        {zatca.receiptFooter && (
          <p className="text-xs text-gray-500 mt-1 whitespace-pre-line">{zatca.receiptFooter}</p>
        )}
        <p className="text-xs text-gray-400 mt-1">{now.toLocaleString('ar-SA')}</p>
        {zatca.showPoweredBy !== false && (
          <p className="text-[10px] text-gray-300 mt-2">مشغّل بواسطة سهل</p>
        )}
      </div>
    </div>
  );
});

Receipt.displayName = 'Receipt';

export default Receipt;
