// Barcode label engine.
// - Zebra path: render each label to a canvas (Arabic name + Code128 barcode + price),
//   convert to a monochrome ZPL ^GFA graphic, and send to the printer via Zebra Browser Print.
//   This prints Arabic correctly (Zebra fonts can't) and keeps the barcode crisp at the label DPI.
// - Sheet path: HTML print window (JsBarcode) for normal/sheet printers.

const SETTINGS_KEY = 'label_settings';
const BP_BASE = 'http://localhost:9100';   // Zebra Browser Print local service (dev/http)
const JSBARCODE_CDN = 'https://cdnjs.cloudflare.com/ajax/libs/jsbarcode/3.11.6/JsBarcode.all.min.js';

export function getLabelSettings() {
  const d = { mode: 'zebra', width_mm: 38, height_mm: 29, dpi: 203, name: true, price: true };
  try { return { ...d, ...(JSON.parse(localStorage.getItem(SETTINGS_KEY) || '{}')) }; }
  catch (e) { return d; }
}
export function saveLabelSettings(s) {
  try { localStorage.setItem(SETTINGS_KEY, JSON.stringify(s)); } catch (e) {}
}

let _jsbarcodePromise = null;
function loadJsBarcode() {
  if (window.JsBarcode) return Promise.resolve();
  if (_jsbarcodePromise) return _jsbarcodePromise;
  _jsbarcodePromise = new Promise((resolve, reject) => {
    const sc = document.createElement('script');
    sc.src = JSBARCODE_CDN; sc.onload = () => resolve(); sc.onerror = () => reject(new Error('jsbarcode load failed'));
    document.head.appendChild(sc);
  });
  return _jsbarcodePromise;
}

// ---- render one label onto a canvas at the target dot size ----
function renderLabelCanvas(item, s) {
  const dotsPerMm = s.dpi / 25.4;
  const W = Math.round(s.width_mm * dotsPerMm);
  const H = Math.round(s.height_mm * dotsPerMm);
  const c = document.createElement('canvas');
  c.width = W; c.height = H;
  const ctx = c.getContext('2d');
  ctx.fillStyle = '#fff'; ctx.fillRect(0, 0, W, H);
  ctx.fillStyle = '#000'; ctx.textAlign = 'center';

  let y = Math.round(H * 0.06);
  if (s.name && item.name) {
    const fs = Math.max(14, Math.round(H * 0.16));
    ctx.font = `bold ${fs}px Arial, "Segoe UI", sans-serif`;
    ctx.textBaseline = 'top';
    // truncate to fit width
    let name = String(item.name);
    while (ctx.measureText(name).width > W - 8 && name.length > 3) name = name.slice(0, -2);
    ctx.fillText(name, W / 2, y);
    y += fs + 4;
  }
  // barcode via JsBarcode onto a temp canvas, then draw scaled
  const bcCanvas = document.createElement('canvas');
  try {
    window.JsBarcode(bcCanvas, String(item.barcode || ''), {
      format: 'CODE128', displayValue: true, fontSize: Math.max(12, Math.round(H * 0.11)),
      height: Math.round(H * 0.42), margin: 0, width: 2,
    });
  } catch (e) { /* invalid barcode */ }
  const availW = W - 8;
  const bcH = Math.round(H * 0.5);
  const bcW = Math.min(availW, bcCanvas.width);
  const bx = Math.round((W - bcW) / 2);
  if (bcCanvas.width) ctx.drawImage(bcCanvas, bx, y, bcW, bcH);
  y += bcH + 2;

  if (s.price && item.price != null && item.price !== '') {
    const fs = Math.max(13, Math.round(H * 0.14));
    ctx.font = `bold ${fs}px Arial, sans-serif`;
    ctx.textBaseline = 'top';
    ctx.fillText(Number(item.price).toFixed(2) + ' SAR', W / 2, Math.min(y, H - fs - 2));
  }
  return c;
}

// ---- canvas -> ZPL ^GFA (monochrome) ----
function canvasToZPL(canvas, qty) {
  const W = canvas.width, H = canvas.height;
  const ctx = canvas.getContext('2d');
  const data = ctx.getImageData(0, 0, W, H).data;
  const bytesPerRow = Math.ceil(W / 8);
  const total = bytesPerRow * H;
  let hex = '';
  for (let row = 0; row < H; row++) {
    for (let b = 0; b < bytesPerRow; b++) {
      let byte = 0;
      for (let bit = 0; bit < 8; bit++) {
        const x = b * 8 + bit;
        let dark = 0;
        if (x < W) {
          const idx = (row * W + x) * 4;
          const lum = (data[idx] + data[idx + 1] + data[idx + 2]) / 3;
          const alpha = data[idx + 3];
          dark = (alpha > 128 && lum < 128) ? 1 : 0;   // black pixel
        }
        byte = (byte << 1) | dark;
      }
      hex += byte.toString(16).padStart(2, '0').toUpperCase();
    }
  }
  const q = Math.max(1, parseInt(qty || 1));
  return `^XA\n^CI28\n^PW${W}\n^LL${H}\n^FO0,0^GFA,${total},${total},${bytesPerRow},${hex}^FS\n^PQ${q}\n^XZ\n`;
}

// ---- Zebra Browser Print transport ----
async function zebraDefaultDevice() {
  const r = await fetch(`${BP_BASE}/default?type=printer`);
  if (!r.ok) throw new Error('no default printer');
  return await r.json();
}
async function zebraWrite(device, data) {
  const r = await fetch(`${BP_BASE}/write`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ device, data }),
  });
  if (!r.ok) throw new Error('write failed');
}

// items: [{ name, barcode, price, qty }]
export async function printZebra(items, settings) {
  const s = settings || getLabelSettings();
  await loadJsBarcode();
  const zplParts = items
    .filter((it) => it && it.barcode)
    .map((it) => canvasToZPL(renderLabelCanvas(it, s), it.qty || 1));
  const zpl = zplParts.join('');
  if (!zpl) throw new Error('no labels');
  const device = await zebraDefaultDevice();
  await zebraWrite(device, zpl);
}

// Build ZPL and download it as a .zpl file (fallback when Browser Print isn't available)
export async function downloadZpl(items, settings) {
  const s = settings || getLabelSettings();
  await loadJsBarcode();
  const zpl = items.filter((it) => it && it.barcode)
    .map((it) => canvasToZPL(renderLabelCanvas(it, s), it.qty || 1)).join('');
  const blob = new Blob([zpl], { type: 'application/octet-stream' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a'); a.href = url; a.download = 'labels.zpl'; a.click();
  URL.revokeObjectURL(url);
}

// Sheet / normal-printer HTML print (respects qty by repeating labels)
export function printSheet(items, settings) {
  const s = settings || getLabelSettings();
  const list = [];
  (items || []).filter((it) => it && it.barcode).forEach((it) => {
    const n = Math.max(1, parseInt(it.qty || 1));
    for (let i = 0; i < n; i++) list.push(it);
  });
  if (list.length === 0) return;
  const w = window.open('', '_blank', 'width=820,height=640');
  if (!w) { alert('اسمح بالنوافذ المنبثقة لطباعة الملصقات'); return; }
  const esc = (t) => String(t == null ? '' : t).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  const labels = list.map((it, i) =>
    '<div class="label" style="width:' + s.width_mm + 'mm;height:' + s.height_mm + 'mm">' +
      (s.name ? '<div class="name">' + esc(it.name) + '</div>' : '') +
      '<svg class="bc" id="bc' + i + '"></svg>' +
      (s.price && it.price != null && it.price !== '' ? '<div class="price">' + Number(it.price).toFixed(2) + ' ر.س</div>' : '') +
    '</div>').join('');
  const scriptTag = '<scr' + 'ipt src="' + JSBARCODE_CDN + '"></scr' + 'ipt>';
  const render = list.map((it, i) => "try{JsBarcode('#bc" + i + "'," + JSON.stringify(String(it.barcode)) + ",{format:'CODE128',height:34,fontSize:11,margin:2});}catch(e){}").join('');
  const doc = '<!DOCTYPE html><html dir="rtl"><head><meta charset="utf-8"><title>ملصقات</title>' + scriptTag +
    '<style>body{font-family:Arial,sans-serif;margin:0;padding:4px}.label{display:inline-flex;flex-direction:column;justify-content:center;align-items:center;border:1px solid #ddd;border-radius:4px;padding:3px;margin:2px;box-sizing:border-box;overflow:hidden}.name{font-size:11px;font-weight:bold;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:100%}.price{font-size:11px}.bc{max-width:100%}@media print{.label{page-break-inside:avoid}}</style></head><body>' +
    labels + '<scr' + 'ipt>window.onload=function(){' + render + 'setTimeout(function(){window.print();},400);};</scr' + 'ipt></body></html>';
  w.document.open(); w.document.write(doc); w.document.close();
}
