import toast from 'react-hot-toast';
import { proofsAPI, apiError } from '../services/api';

const MAX = 5 * 1024 * 1024;
const OK = ['image/jpeg', 'image/png', 'image/webp', 'application/pdf'];

/** Upload a transfer proof; returns {id, original_name, ...} or null. */
export async function uploadProof(file) {
  if (!file) return null;
  if (file.size > MAX) { toast.error('حجم الملف أكبر من 5 ميجابايت'); return null; }
  if (file.type && !OK.includes(file.type)) { toast.error('صورة (JPG/PNG/WEBP) أو PDF فقط'); return null; }
  try {
    toast.loading('جاري رفع الإثبات...');
    const { data } = await proofsAPI.upload(file);
    toast.dismiss();
    toast.success('تم رفع إثبات التحويل');
    return data;
  } catch (err) {
    toast.dismiss();
    toast.error(apiError(err, 'تعذّر رفع الملف'));
    return null;
  }
}

/** Open a stored proof in a new tab (fetched with the session — never a public link). */
export async function openProof(id) {
  const win = window.open('', '_blank');
  try {
    const { data } = await proofsAPI.file(id);
    const url = URL.createObjectURL(data);
    if (win) win.location.href = url; else window.open(url, '_blank');
    setTimeout(() => URL.revokeObjectURL(url), 60000);
  } catch (err) {
    if (win) win.close();
    toast.error(apiError(err, 'تعذّر فتح الإثبات'));
  }
}
