import html2canvas from 'html2canvas';
import jsPDF from 'jspdf';
import QRCode from 'qrcode';

/**
 * Generate a PDF from a DOM element (receipt)
 * @param {HTMLElement} element - The DOM element to convert to PDF
 * @param {string} filename - PDF filename (without extension)
 * @returns {Promise<Blob>} - The PDF blob
 */
export async function generatePDFBlob(element, filename = 'invoice') {
  // Create a clone to avoid modifying the original
  const canvas = await html2canvas(element, {
    scale: 2,
    useCORS: true,
    backgroundColor: '#ffffff',
    logging: false,
    // html2canvas rasterizes live <canvas> (e.g. the ZATCA QR) as blank.
    // Replace each cloned canvas with an <img> of the original's pixels.
    onclone: (clonedDoc) => {
      const origCanvases = element.querySelectorAll('canvas');
      const cloneCanvases = clonedDoc.querySelectorAll('canvas');
      cloneCanvases.forEach((cloneCanvas, i) => {
        const orig = origCanvases[i];
        if (!orig) return;
        try {
          const img = clonedDoc.createElement('img');
          img.src = orig.toDataURL('image/png');
          img.setAttribute('width', orig.width);
          img.setAttribute('height', orig.height);
          if (cloneCanvas.parentNode) cloneCanvas.parentNode.replaceChild(img, cloneCanvas);
        } catch (e) { /* ignore */ }
      });
    },
  });

  const imgData = canvas.toDataURL('image/png');
  const imgWidth = canvas.width;
  const imgHeight = canvas.height;

  // Calculate PDF dimensions (80mm thermal receipt width)
  const pdfWidth = 80; // mm
  const pdfHeight = (imgHeight * pdfWidth) / imgWidth;

  const pdf = new jsPDF({
    orientation: 'portrait',
    unit: 'mm',
    format: [pdfWidth, pdfHeight + 10],
  });

  pdf.addImage(imgData, 'PNG', 0, 5, pdfWidth, pdfHeight);

  // Stamp the ZATCA QR directly into the PDF at its on-screen position.
  // html2canvas is unreliable for the QR, so we draw it with jsPDF instead.
  try {
    const slot = element.querySelector('[data-qr-slot]');
    const qrValue = slot && slot.getAttribute('data-qr');
    if (slot && qrValue) {
      const qrUrl = await QRCode.toDataURL(qrValue, { margin: 1, width: 512 });
      const elRect = element.getBoundingClientRect();
      const r = slot.getBoundingClientRect();
      const scale = pdfWidth / elRect.width;           // mm per px
      const size = r.width * scale;
      const x = (r.left - elRect.left) * scale;
      const y = 5 + (r.top - elRect.top) * scale;
      pdf.addImage(qrUrl, 'PNG', x, y, size, size);
    }
  } catch (e) { /* QR overlay is best-effort */ }

  return pdf.output('blob');
}

/**
 * Generate and download PDF
 * @param {HTMLElement} element - The DOM element
 * @param {string} filename - Filename without extension
 */
export async function pdfToBase64(element, filename = 'invoice') {
  const blob = await generatePDFBlob(element, filename);
  return await new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onloadend = () => resolve(String(reader.result).split(',')[1]);
    reader.onerror = reject;
    reader.readAsDataURL(blob);
  });
}

export async function downloadPDF(element, filename = 'invoice') {
  const blob = await generatePDFBlob(element, filename);
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = `${filename}.pdf`;
  link.click();
  URL.revokeObjectURL(url);
}

/**
 * Share PDF via WhatsApp
 * Uses WhatsApp Web API - opens WhatsApp with a pre-filled message.
 * Since WhatsApp Web API doesn't support direct file upload via URL,
 * we download the PDF first, then open WhatsApp with a message.
 * 
 * @param {HTMLElement} element - The receipt DOM element
 * @param {string} filename - PDF filename
 * @param {string} phone - Phone number (optional, with country code e.g. 966XXXXXXXXX)
 * @param {string} message - Pre-filled message
 */
export async function shareViaWhatsApp(element, filename, phone = '', message = '') {
  // Download the PDF first
  await downloadPDF(element, filename);

  // Open WhatsApp with message
  const encodedMessage = encodeURIComponent(
    message || `إيصال من جمعية بيان بمكة المكرمة - ${filename}`
  );
  
  const whatsappUrl = phone
    ? `https://wa.me/${phone}?text=${encodedMessage}`
    : `https://wa.me/?text=${encodedMessage}`;
  
  window.open(whatsappUrl, '_blank');
}

/**
 * Share PDF via Email
 * Opens the default email client with the invoice details.
 * The PDF is downloaded separately since mailto: doesn't support attachments.
 * 
 * @param {HTMLElement} element - The receipt DOM element
 * @param {string} filename - PDF filename
 * @param {string} email - Recipient email (optional)
 * @param {string} subject - Email subject
 * @param {string} body - Email body
 */
export async function shareViaEmail(element, filename, email = '', subject = '', body = '') {
  // Download the PDF first
  await downloadPDF(element, filename);

  const defaultSubject = subject || `إيصال من جمعية بيان بمكة المكرمة - ${filename}`;
  const defaultBody = body || `السلام عليكم ورحمة الله وبركاته\n\nمرفق إيصال رقم ${filename}\n\nجزاكم الله خيراً\nجمعية بيان بمكة المكرمة`;

  const mailtoUrl = `mailto:${email}?subject=${encodeURIComponent(defaultSubject)}&body=${encodeURIComponent(defaultBody)}`;
  window.location.href = mailtoUrl;
}
