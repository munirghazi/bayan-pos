import html2canvas from 'html2canvas';
import jsPDF from 'jspdf';
import { senderName } from './generatePDF';
import { fmtDateTime as fmtDT } from './datetime';

/*
 * A4 report PDF for any report screen.
 *
 *   downloadReportPDF({
 *     title: 'تقرير المبيعات',
 *     subtitle: 'من 2026/11/01 إلى 2026/11/08',
 *     meta: [['الفرع', 'الرئيسي'], ...],                 // optional label/value lines
 *     summary: [{ label: 'إجمالي المبيعات', value: '1,250.00' }, ...],
 *     sections: [{ title: 'الفواتير', columns: [{ label: 'رقم', key: 'n', align: 'left' }, ...], rows: [...],
 *                  footer: ['', 'الإجمالي', '1,250.00'] }],
 *     filename: 'تقرير_المبيعات_2026-11-08',
 *   })
 *
 * Arabic is rendered by the browser itself (html2canvas), so shaping and
 * right-to-left order are always correct. Pages are laid out row by row:
 * a row never splits across two pages and each table repeats its header.
 */

const PAGE_W = 794;   // A4 width in CSS px (96 dpi)
const PAGE_H = 1123;  // A4 height
const PAD = 40;

const esc = (v) => String(v ?? '').replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));

function cellValue(row, col) {
  if (typeof col.value === 'function') return col.value(row);
  return row[col.key];
}

function newPage(host) {
  const page = document.createElement('div');
  page.style.cssText = `width:${PAGE_W}px;height:${PAGE_H}px;padding:${PAD}px ${PAD}px ${PAD + 24}px;box-sizing:border-box;`
    + 'background:#fff;color:#111827;direction:rtl;font-family:Cairo,Tahoma,Arial,sans-serif;font-size:12px;'
    + 'position:relative;overflow:hidden;';
  const body = document.createElement('div');
  page.appendChild(body);
  host.appendChild(page);
  return { page, body };
}

const usable = () => PAGE_H - PAD * 2 - 24;

function headerHTML(def) {
  const org = esc(def.org || senderName() || '');
  const meta = (def.meta || []).map(([k, v]) =>
    `<span style="margin-left:16px"><b>${esc(k)}:</b> ${esc(v)}</span>`).join('');
  return `
    <div style="display:flex;justify-content:space-between;align-items:flex-start;border-bottom:2px solid #1f3f8a;padding-bottom:8px;margin-bottom:10px">
      <div>
        <div style="font-size:18px;font-weight:700;color:#1f3f8a">${esc(def.title)}</div>
        ${def.subtitle ? `<div style="color:#4b5563;margin-top:2px">${esc(def.subtitle)}</div>` : ''}
        ${meta ? `<div style="color:#374151;margin-top:4px">${meta}</div>` : ''}
      </div>
      <div style="text-align:left;font-weight:700;font-size:14px">${org}</div>
    </div>`;
}

function summaryHTML(summary) {
  if (!summary || !summary.length) return '';
  const cells = summary.map((s) => `
    <div style="border:1px solid #e5e7eb;border-radius:6px;padding:6px 8px;background:#f9fafb">
      <div style="color:#6b7280;font-size:10.5px">${esc(s.label)}</div>
      <div style="font-weight:700;font-size:13.5px;${s.color ? `color:${s.color}` : ''}" dir="auto">${esc(s.value)}</div>
    </div>`).join('');
  return `<div style="display:grid;grid-template-columns:repeat(4,1fr);gap:6px;margin-bottom:12px">${cells}</div>`;
}

function tableShell(section, cont) {
  const t = document.createElement('div');
  t.style.marginBottom = '12px';
  const head = section.columns.map((c) =>
    `<th style="text-align:${c.align === 'left' ? 'left' : 'right'};padding:5px 6px;background:#eef2ff;border-bottom:1px solid #c7d2fe;font-weight:700;font-size:11px;white-space:nowrap">${esc(c.label)}</th>`).join('');
  t.innerHTML = `
    <div style="font-weight:700;font-size:13px;margin:4px 0 6px">${esc(section.title)}${cont ? ' <span style="color:#6b7280;font-weight:400;font-size:11px">(تابع)</span>' : ''}</div>
    <table style="width:100%;border-collapse:collapse"><thead><tr>${head}</tr></thead><tbody></tbody></table>`;
  return { wrap: t, tbody: t.querySelector('tbody') };
}

function rowEl(section, row, i, isFooter) {
  const tr = document.createElement('tr');
  const vals = isFooter ? row : section.columns.map((c) => cellValue(row, c));
  tr.innerHTML = section.columns.map((c, k) => {
    const v = vals[k];
    return `<td style="text-align:${c.align === 'left' ? 'left' : 'right'};padding:4px 6px;border-bottom:1px solid #f1f5f9;`
      + `${isFooter ? 'font-weight:700;background:#f8fafc;border-top:1px solid #cbd5e1;' : (i % 2 ? 'background:#fcfcfd;' : '')}`
      + `font-size:11px;vertical-align:top" ${c.align === 'left' ? 'dir="ltr"' : 'dir="auto"'}>${esc(v)}</td>`;
  }).join('');
  return tr;
}

function layout(def, host) {
  const pages = [];
  let cur = newPage(host);
  pages.push(cur);
  const fits = () => cur.body.scrollHeight <= usable();
  const nextPage = () => { cur = newPage(host); pages.push(cur); };

  const block = document.createElement('div');
  block.innerHTML = headerHTML(def) + summaryHTML(def.summary);
  cur.body.appendChild(block);

  for (const section of def.sections || []) {
    if (!section.rows || !section.rows.length) {
      if (section.emptyText) {
        const p = document.createElement('div');
        p.innerHTML = `<div style="font-weight:700;font-size:13px;margin:4px 0">${esc(section.title)}</div><div style="color:#6b7280;margin-bottom:12px">${esc(section.emptyText)}</div>`;
        cur.body.appendChild(p);
        if (!fits()) { cur.body.removeChild(p); nextPage(); cur.body.appendChild(p); }
      }
      continue;
    }
    let t = tableShell(section, false);
    cur.body.appendChild(t.wrap);
    if (!fits() || cur.body.scrollHeight > usable() - 40) {   // keep a title with at least one row
      cur.body.removeChild(t.wrap); nextPage(); t = tableShell(section, false); cur.body.appendChild(t.wrap);
    }
    const all = section.rows.map((r, i) => [r, i, false]);
    if (section.footer) all.push([section.footer, all.length, true]);
    for (const [r, i, isFooter] of all) {
      const tr = rowEl(section, r, i, isFooter);
      t.tbody.appendChild(tr);
      if (!fits()) {
        t.tbody.removeChild(tr);
        nextPage();
        t = tableShell(section, true);
        cur.body.appendChild(t.wrap);
        t.tbody.appendChild(tr);
      }
    }
  }

  if (def.notes) {
    const n = document.createElement('div');
    n.style.cssText = 'color:#374151;margin-top:6px;white-space:pre-wrap';
    n.textContent = def.notes;
    cur.body.appendChild(n);
    if (!fits()) { cur.body.removeChild(n); nextPage(); cur.body.appendChild(n); }
  }

  const stamp = fmtDT(new Date());
  pages.forEach((p, i) => {
    const f = document.createElement('div');
    f.style.cssText = `position:absolute;left:${PAD}px;right:${PAD}px;bottom:${PAD - 14}px;display:flex;justify-content:space-between;color:#9ca3af;font-size:10px;border-top:1px solid #e5e7eb;padding-top:4px`;
    f.innerHTML = `<span>${esc(def.title)} · طُبع ${esc(stamp)}</span><span>صفحة ${i + 1} من ${pages.length}</span>`;
    p.page.appendChild(f);
  });
  return pages;
}

export async function buildReportPDF(def) {
  const host = document.createElement('div');
  host.style.cssText = `position:fixed;left:-10000px;top:0;width:${PAGE_W}px;z-index:-1;`;
  document.body.appendChild(host);
  try {
    if (document.fonts && document.fonts.ready) await document.fonts.ready;
    const pages = layout(def, host);
    const pdf = new jsPDF({ orientation: 'portrait', unit: 'mm', format: 'a4' });
    for (let i = 0; i < pages.length; i++) {
      const canvas = await html2canvas(pages[i].page, { scale: 2, backgroundColor: '#ffffff', logging: false });
      if (i > 0) pdf.addPage();
      pdf.addImage(canvas.toDataURL('image/jpeg', 0.92), 'JPEG', 0, 0, 210, 297);
    }
    return pdf;
  } finally {
    document.body.removeChild(host);
  }
}

export async function downloadReportPDF(def) {
  const pdf = await buildReportPDF(def);
  const name = (def.filename || def.title || 'report').replace(/[\\/:*?"<>|]+/g, '_');
  pdf.save(`${name}.pdf`);
}

// \u2066…\u2069 keeps numbers, dates and signs in left-to-right order inside Arabic text.
export const ltr = (v) => `\u2066${v}\u2069`;
export const neg = (n) => (Number(n || 0) ? ltr(`-${money(n)}`) : money(0));
export const money = (n) => Number(n || 0).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
export const methodLabel = (m) => ({ cash: 'نقدي', card: 'شبكة', transfer: 'تحويل', mixed: 'متعدد', other: 'أخرى' }[m] || m || '—');
export { fmtDateTime } from './datetime';
