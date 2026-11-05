// All documents carry issued_at in UTC; always DISPLAY in Riyadh time,
// whatever the device's own time zone is set to.
const TZ = 'Asia/Riyadh';

function toDate(v) {
  if (!v) return null;
  if (v instanceof Date) return v;
  let s = String(v);
  // a naive timestamp from an older API response is UTC
  if (!/[zZ]|[+-]\d\d:?\d\d$/.test(s)) s += 'Z';
  const d = new Date(s);
  return Number.isNaN(d.getTime()) ? null : d;
}

export function fmtDateTime(v) {
  const d = toDate(v);
  return d ? d.toLocaleString('ar-SA', { timeZone: TZ }) : '';
}

export function fmtTime(v) {
  const d = toDate(v);
  return d ? d.toLocaleTimeString('ar-SA', { timeZone: TZ, hour: '2-digit', minute: '2-digit' }) : '';
}

export function fmtDate(v) {
  const d = toDate(v);
  return d ? d.toLocaleDateString('ar-SA', { timeZone: TZ }) : '';
}
