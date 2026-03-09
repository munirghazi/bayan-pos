/**
 * طباعة الإيصال بطريقة موثوقة
 * يأخذ محتوى HTML من ref ويطبعه في نافذة منفصلة مع انتظار التحميل
 */
export function printReceipt(receiptRef) {
  if (!receiptRef?.current) return;

  const content = receiptRef.current.innerHTML;

  const printWindow = window.open('', '_blank', 'width=400,height=600');
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
          * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
          }
          body {
            font-family: 'Cairo', 'Segoe UI', Tahoma, sans-serif;
            direction: rtl;
            padding: 10px;
            color: #333;
            -webkit-print-color-adjust: exact;
            print-color-adjust: exact;
          }
          .receipt-content {
            max-width: 350px;
            margin: 0 auto;
            background: white;
            padding: 15px;
            font-size: 13px;
          }
          table {
            width: 100%;
            border-collapse: collapse;
          }
          th, td {
            padding: 4px 6px;
            text-align: right;
          }
          th {
            border-bottom: 1px solid #ccc;
          }
          td {
            border-bottom: 1px solid #eee;
          }
          .text-center { text-align: center; }
          .text-left { text-align: left; }
          .font-bold { font-weight: bold; }
          .font-medium { font-weight: 500; }
          .text-lg { font-size: 16px; }
          .text-base { font-size: 14px; }
          .text-sm { font-size: 13px; }
          .text-xs { font-size: 11px; }
          .text-gray-400 { color: #9ca3af; }
          .text-gray-500 { color: #6b7280; }
          .text-gray-600 { color: #4b5563; }
          .text-gray-800 { color: #1f2937; }
          .border-b { border-bottom: 1px solid #e5e7eb; }
          .border-b-2 { border-bottom: 2px dashed #9ca3af; }
          .border-t-2 { border-top: 2px dashed #9ca3af; }
          .border-dashed { border-style: dashed; }
          .border-gray-200 { border-color: #e5e7eb; }
          .border-gray-300 { border-color: #d1d5db; }
          .border-gray-400 { border-color: #9ca3af; }
          .pb-4 { padding-bottom: 16px; }
          .pt-3 { padding-top: 12px; }
          .pt-4 { padding-top: 16px; }
          .mt-1 { margin-top: 4px; }
          .mt-6 { margin-top: 24px; }
          .mb-3 { margin-bottom: 12px; }
          .mb-4 { margin-bottom: 16px; }
          .py-1 { padding-top: 4px; padding-bottom: 4px; }
          .space-y-2 > * + * { margin-top: 8px; }
          .flex { display: flex; }
          .justify-between { justify-content: space-between; }
          .items-center { align-items: center; }
          svg { vertical-align: middle; display: inline-block; fill: currentColor; }
          svg path { fill: currentColor; }
          @media print {
            svg { vertical-align: middle; display: inline-block; fill: #000; }
            svg path { fill: #000; }
            body { padding: 0; }
            .receipt-content { max-width: 100%; }
          }
        </style>
      </head>
      <body>
        ${content}
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
      // fallback: أغلق بعد 3 ثوان إذا لم يتم التفاعل
      setTimeout(() => {
        if (!printWindow.closed) {
          // لا نغلق تلقائياً - نترك المستخدم يتحكم
        }
      }, 3000);
    }, 500);
  };
}
