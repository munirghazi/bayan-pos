/**
 * طباعة الإيصال بطريقة موثوقة على طابعة حرارية 80مم (Epson TM-m30II)
 * يأخذ محتوى HTML من ref ويطبعه في نافذة منفصلة مع انتظار التحميل.
 * العرض مضبوط على 72مم (منطقة الطباعة الفعلية لورق 80مم) مع قطع تلقائي سليم.
 */
export function printReceipt(receiptRef) {
  if (!receiptRef?.current) return;

  const content = receiptRef.current.innerHTML;

  const printWindow = window.open('', '_blank', 'width=360,height=640');
  if (!printWindow) {
    alert('الرجاء السماح بالنوافذ المنبثقة لطباعة الإيصال');
    return;
  }

  printWindow.document.write(`
    <!DOCTYPE html>
    <html lang="ar" dir="rtl">
      <head>
        <meta charset="UTF-8">
        <title>إيصال - جمعية بيان</title>
        <link rel="preconnect" href="https://fonts.googleapis.com">
        <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
        <link href="https://fonts.googleapis.com/css2?family=Cairo:wght@400;600;700&display=swap" rel="stylesheet">
        <style>
          /* ورق حراري 80مم: منطقة الطباعة 72مم، بلا هوامش، قطع تلقائي */
          @page {
            size: 80mm auto;
            margin: 0;
          }
          * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
          }
          html, body {
            width: 80mm;
          }
          body {
            font-family: 'Cairo', 'Segoe UI', Tahoma, sans-serif;
            direction: rtl;
            padding: 0;
            color: #000;
            background: #fff;
            -webkit-print-color-adjust: exact;
            print-color-adjust: exact;
          }
          .receipt-content {
            width: 72mm;
            max-width: 72mm;
            margin: 0 auto;
            background: #fff;
            padding: 2mm 1.5mm 4mm;
            font-size: 12px;
            line-height: 1.35;
          }
          /* الصور (الشعار ورمز QR) لا تتجاوز عرض الورق */
          img {
            max-width: 100%;
            height: auto;
          }
          table {
            width: 100%;
            border-collapse: collapse;
            table-layout: fixed;
          }
          th, td {
            padding: 2px 3px;
            text-align: right;
            word-wrap: break-word;
            overflow-wrap: break-word;
          }
          th {
            border-bottom: 1px solid #000;
          }
          td {
            border-bottom: 1px solid #ddd;
          }
          .text-center { text-align: center; }
          .text-left { text-align: left; }
          .font-bold { font-weight: 700; }
          .font-medium { font-weight: 600; }
          .text-lg { font-size: 15px; }
          .text-base { font-size: 13px; }
          .text-sm { font-size: 12px; }
          .text-xs { font-size: 10px; }
          .text-gray-400 { color: #555; }
          .text-gray-500 { color: #444; }
          .text-gray-600 { color: #333; }
          .text-gray-800 { color: #000; }
          .border-b { border-bottom: 1px solid #ccc; }
          .border-b-2 { border-bottom: 1px dashed #000; }
          .border-t-2 { border-top: 1px dashed #000; }
          .border-dashed { border-style: dashed; }
          .border-gray-200 { border-color: #ccc; }
          .border-gray-300 { border-color: #bbb; }
          .border-gray-400 { border-color: #999; }
          .pb-4 { padding-bottom: 10px; }
          .pt-3 { padding-top: 8px; }
          .pt-4 { padding-top: 10px; }
          .mt-1 { margin-top: 3px; }
          .mt-6 { margin-top: 14px; }
          .mb-3 { margin-bottom: 8px; }
          .mb-4 { margin-bottom: 10px; }
          .py-1 { padding-top: 3px; padding-bottom: 3px; }
          .space-y-2 > * + * { margin-top: 6px; }
          .flex { display: flex; }
          .justify-between { justify-content: space-between; }
          .items-center { align-items: center; }
          svg { vertical-align: middle; display: inline-block; fill: #000; max-width: 100%; }
          svg path { fill: #000; }
          @media print {
            svg { fill: #000; }
            svg path { fill: #000; }
            body { padding: 0; }
            .receipt-content { width: 72mm; max-width: 72mm; }
          }
        </style>
      </head>
      <body>
        <div class="receipt-content">
          ${content}
        </div>
      </body>
    </html>
  `);

  printWindow.document.close();

  // انتظر حتى تحميل الخطوط والمحتوى ثم اطبع
  printWindow.onload = () => {
    setTimeout(() => {
      printWindow.focus();
      printWindow.print();
      // أغلق النافذة بعد الطباعة أو الإلغاء
      printWindow.onafterprint = () => {
        printWindow.close();
      };
    }, 500);
  };
}
