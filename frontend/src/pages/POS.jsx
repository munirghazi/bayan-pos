import { useState, useEffect, useRef, useMemo } from 'react';
import { productsAPI, salesAPI, donationsAPI, registersAPI, customersAPI, apiError } from '../services/api';
import { COUNTRIES, flagOf, validateLocalPhone } from '../utils/countries';
import { deliveryAPI } from '../services/api';
import Receipt from '../components/Receipt';
import { SarIcon } from '../components/SarIcon';
import { printReceipt } from '../utils/printReceipt';
import { downloadPDF, shareViaWhatsApp, pdfToBase64 } from '../utils/generatePDF';
import { getPOSSettings } from '../utils/posSettings';
import toast from 'react-hot-toast';
import {
  HiOutlineSearch,
  HiOutlinePlus,
  HiOutlineMinus,
  HiOutlineTrash,
  HiOutlineCash,
  HiOutlineCreditCard,
  HiOutlineDeviceMobile,
  HiOutlineHeart,
  HiOutlinePrinter,
  HiOutlineDocumentDownload,
  HiOutlineMail,
} from 'react-icons/hi';

// WhatsApp icon
const WhatsAppIcon = () => (
  <svg viewBox="0 0 24 24" fill="currentColor" className="w-5 h-5">
    <path d="M17.472 14.382c-.297-.149-1.758-.867-2.03-.967-.273-.099-.471-.148-.67.15-.197.297-.767.966-.94 1.164-.173.199-.347.223-.644.075-.297-.15-1.255-.463-2.39-1.475-.883-.788-1.48-1.761-1.653-2.059-.173-.297-.018-.458.13-.606.134-.133.298-.347.446-.52.149-.174.198-.298.298-.497.099-.198.05-.371-.025-.52-.075-.149-.669-1.612-.916-2.207-.242-.579-.487-.5-.669-.51-.173-.008-.371-.01-.57-.01-.198 0-.52.074-.792.372-.272.297-1.04 1.016-1.04 2.479 0 1.462 1.065 2.875 1.213 3.074.149.198 2.096 3.2 5.077 4.487.709.306 1.262.489 1.694.625.712.227 1.36.195 1.871.118.571-.085 1.758-.719 2.006-1.413.248-.694.248-1.289.173-1.413-.074-.124-.272-.198-.57-.347m-5.421 7.403h-.004a9.87 9.87 0 01-5.031-1.378l-.361-.214-3.741.982.998-3.648-.235-.374a9.86 9.86 0 01-1.51-5.26c.001-5.45 4.436-9.884 9.888-9.884 2.64 0 5.122 1.03 6.988 2.898a9.825 9.825 0 012.893 6.994c-.003 5.45-4.437 9.884-9.885 9.884m8.413-18.297A11.815 11.815 0 0012.05 0C5.495 0 .16 5.335.157 11.892c0 2.096.547 4.142 1.588 5.945L.057 24l6.305-1.654a11.882 11.882 0 005.683 1.448h.005c6.554 0 11.89-5.335 11.893-11.893a11.821 11.821 0 00-3.48-8.413z" />
  </svg>
);

const ALL_PAYMENT_METHODS = [
  { key: 'cash', icon: HiOutlineCash, label: 'نقدي' },
  { key: 'card', icon: HiOutlineCreditCard, label: 'شبكة' },
  { key: 'transfer', icon: HiOutlineDeviceMobile, label: 'تحويل' },
];

export default function POS() {
  const [products, setProducts] = useState([]);
  const [cart, setCart] = useState([]);
  const [search, setSearch] = useState('');
  const [paymentMethod, setPaymentMethod] = useState('cash');
  const [cashReceived, setCashReceived] = useState('');
  const [cardRef, setCardRef] = useState('');
  const [loading, setLoading] = useState(false);
  const [lastSale, setLastSale] = useState(null);
  const [showReceipt, setShowReceipt] = useState(false);
  const [showDonation, setShowDonation] = useState(false);
  const [donationAmount, setDonationAmount] = useState('');
  const [donorName, setDonorName] = useState('');
  const [donationNote, setDonationNote] = useState('');
  const [donationCardRef, setDonationCardRef] = useState('');
  const [lastDonation, setLastDonation] = useState(null);
  const [showShareMenu, setShowShareMenu] = useState(false);
  const receiptRef = useRef(null);
  const checkoutRef = useRef(false);
  const [registers, setRegisters] = useState([]);
  const [registerId, setRegisterId] = useState(() => localStorage.getItem('pos_register_id') || '');
  const [selectedCustomer, setSelectedCustomer] = useState(null);
  const [customerQuery, setCustomerQuery] = useState('');
  const [customerResults, setCustomerResults] = useState([]);
  const [showNewCustomer, setShowNewCustomer] = useState(false);
  const [newCustomer, setNewCustomer] = useState({ name: '', phone: '' });
  const [countryIso, setCountryIso] = useState('SA');

  const posSettings = getPOSSettings();

  const enabledPaymentMethods = useMemo(() => {
    const methods = ALL_PAYMENT_METHODS.filter((m) => posSettings.paymentMethods[m.key]);
    return methods.length > 0 ? methods : ALL_PAYMENT_METHODS;
  }, [posSettings.paymentMethods]);

  useEffect(() => {
    loadProducts();
    loadRegisters();
  }, []);

  const loadRegisters = async () => {
    try {
      const res = await registersAPI.getAll();
      let regs = res.data;
      const u = JSON.parse(localStorage.getItem('user') || '{}');
      if (u.location_id) regs = regs.filter((r) => r.location_id === u.location_id);
      setRegisters(regs);
      setRegisterId((prev) => {
        if (prev && regs.some((r) => String(r.id) === String(prev))) return prev;
        const first = regs.length ? String(regs[0].id) : '';
        if (first) localStorage.setItem('pos_register_id', first);
        return first;
      });
    } catch (err) {}
  };

  const searchCustomers = async (q) => {
    setCustomerQuery(q);
    if (!q || q.length < 2) { setCustomerResults([]); return; }
    try { const res = await customersAPI.getAll(q); setCustomerResults(res.data); } catch (e) {}
  };
  const selectCustomer = (c) => { setSelectedCustomer(c); setCustomerQuery(''); setCustomerResults([]); setShowNewCustomer(false); };
  const createCustomer = async () => {
    if (!newCustomer.name.trim()) { toast.error('الرجاء إدخال اسم العميل'); return; }
    let phone = null;
    const local = (newCustomer.phone || '').replace(/\D/g, '').replace(/^0+/, '');
    if (local) {
      const country = COUNTRIES.find((c) => c.iso === countryIso) || COUNTRIES[0];
      if (!validateLocalPhone(countryIso, local)) { toast.error('رقم الجوال غير صحيح لهذا البلد'); return; }
      phone = `+${country.code}${local}`;
    }
    try { const res = await customersAPI.create({ name: newCustomer.name.trim(), phone }); selectCustomer(res.data); setNewCustomer({ name: '', phone: '' }); toast.success('تم إضافة العميل'); }
    catch (err) { toast.error(apiError(err, 'خطأ في إضافة العميل')); }
  };

  useEffect(() => {
    if (!posSettings.paymentMethods[paymentMethod]) {
      const first = enabledPaymentMethods[0];
      if (first) setPaymentMethod(first.key);
    }
  }, [posSettings.paymentMethods]);

  const loadProducts = async () => {
    try {
      const res = await productsAPI.getAll();
      setProducts(res.data);
    } catch (err) {
      toast.error('خطأ في تحميل المنتجات');
    }
  };

  const filteredProducts = products.filter((p) =>
    p.name.includes(search) && p.stock > 0
  );

  const addToCart = (product) => {
    const existing = cart.find((item) => item.product_id === product.id);
    if (existing) {
      if (existing.quantity >= product.stock) {
        toast.error('الكمية المطلوبة غير متوفرة');
        return;
      }
      setCart(cart.map((item) =>
        item.product_id === product.id
          ? { ...item, quantity: item.quantity + 1 }
          : item
      ));
    } else {
      setCart([...cart, {
        product_id: product.id,
        name: product.name,
        price: product.price,
        quantity: 1,
        max_stock: product.stock,
        image_url: product.image_url,
        is_tax_exempt: product.is_tax_exempt || false,
      }]);
    }
  };

  const updateQuantity = (productId, delta) => {
    setCart(cart.map((item) => {
      if (item.product_id === productId) {
        const newQty = item.quantity + delta;
        if (newQty <= 0) return null;
        if (newQty > item.max_stock) {
          toast.error('الكمية المطلوبة غير متوفرة');
          return item;
        }
        return { ...item, quantity: newQty };
      }
      return item;
    }).filter(Boolean));
  };

  const setQuantity = (productId, value) => {
    let q = parseFloat(value);
    if (isNaN(q) || q < 0) q = 0;
    setCart(cart.map((item) => {
      if (item.product_id !== productId) return item;
      if (q > item.max_stock) { toast.error('الكمية المطلوبة غير متوفرة'); return { ...item, quantity: item.max_stock }; }
      return { ...item, quantity: q };
    }));
  };

  const removeFromCart = (productId) => {
    setCart(cart.filter((item) => item.product_id !== productId));
  };

  const total = cart.reduce((sum, item) => sum + item.price * item.quantity, 0);
  const change = paymentMethod === 'cash' && cashReceived
    ? parseFloat(cashReceived) - total
    : 0;

  const handleCheckout = async () => {
    if (cart.length === 0) {
      toast.error('السلة فارغة');
      return;
    }

    if (paymentMethod === 'card' && !cardRef.trim()) {
      toast.error('الرجاء إدخال رمز العملية');
      return;
    }
    if (registers.length > 0 && !registerId) {
      toast.error('الرجاء اختيار الصندوق');
      return;
    }
    if (checkoutRef.current) return;
    checkoutRef.current = true;

    setLoading(true);
    try {
      const res = await salesAPI.create({
        items: cart.filter((item) => item.quantity > 0).map((item) => ({
          product_id: item.product_id,
          quantity: item.quantity,
        })),
        payment_method: paymentMethod,
        card_ref: paymentMethod === 'card' ? cardRef.trim() : null,
        register_id: registerId ? parseInt(registerId) : null,
        customer_id: selectedCustomer ? selectedCustomer.id : null,
      });

      setLastSale(res.data);
      setLastDonation(null);
      setShowReceipt(true);
      setCart([]);
      setCashReceived('');
      setCardRef('');
      setSelectedCustomer(null);
      loadProducts();
      toast.success('تمت عملية البيع بنجاح');
    } catch (err) {
      toast.error(apiError(err, 'خطأ في عملية البيع'));
    } finally {
      setLoading(false);
      checkoutRef.current = false;
    }
  };

  const handleDonation = async () => {
    const amount = parseFloat(donationAmount);
    if (!amount || amount <= 0) {
      toast.error('الرجاء إدخال مبلغ صحيح');
      return;
    }

    if (paymentMethod === 'card' && !donationCardRef.trim()) {
      toast.error('الرجاء إدخال رمز العملية');
      return;
    }

    setLoading(true);
    try {
      const res = await donationsAPI.create({
        donor_name: donorName || null,
        amount,
        note: donationNote || null,
        payment_method: paymentMethod,
        card_ref: paymentMethod === 'card' ? donationCardRef.trim() : null,
      });

      setLastDonation(res.data);
      setLastSale(null);
      setShowDonation(false);
      setShowReceipt(true);
      setDonationAmount('');
      setDonorName('');
      setDonationNote('');
      setDonationCardRef('');
      toast.success('تم تسجيل التبرع بنجاح - جزاكم الله خيراً');
    } catch (err) {
      toast.error(err.response?.data?.detail || 'خطأ في تسجيل التبرع');
    } finally {
      setLoading(false);
    }
  };

  const handlePrint = () => {
    printReceipt(receiptRef);
  };

  const getInvoiceFilename = () => {
    if (lastSale) return `فاتورة_${lastSale.id}`;
    if (lastDonation) return `إيصال_تبرع_${lastDonation.id}`;
    return 'إيصال';
  };

  const handleDownloadPDF = async () => {
    if (!receiptRef.current) return;
    try {
      toast.loading('جاري إنشاء PDF...');
      await downloadPDF(receiptRef.current, getInvoiceFilename());
      toast.dismiss();
      toast.success('تم تحميل PDF بنجاح');
    } catch (err) {
      toast.dismiss();
      toast.error('خطأ في إنشاء PDF');
    }
  };

  const handleShareWhatsApp = async () => {
    if (!receiptRef.current) return;
    try {
      toast.loading('جاري إنشاء PDF...');
      await shareViaWhatsApp(receiptRef.current, getInvoiceFilename());
      toast.dismiss();
    } catch (err) {
      toast.dismiss();
      toast.error('خطأ في المشاركة');
    }
  };

  const handleShareEmail = async () => {
    if (!receiptRef.current) return;
    const suggested = (selectedCustomer && selectedCustomer.email) || '';
    const to = window.prompt('البريد الإلكتروني للعميل:', suggested);
    if (!to) return;
    try {
      toast.loading('جاري إرسال الفاتورة...');
      const pdf_base64 = await pdfToBase64(receiptRef.current, getInvoiceFilename());
      await deliveryAPI.sendEmail({ to, filename: `${getInvoiceFilename()}.pdf`, pdf_base64, subject: 'فاتورتك' });
      toast.dismiss();
      toast.success('تم إرسال الفاتورة بالبريد');
    } catch (err) {
      toast.dismiss();
      toast.error(apiError(err, 'تعذّر إرسال البريد'));
    }
  };

  return (
    <div className="flex gap-4 h-[calc(100vh-2rem)]">
      {/* Products Grid */}
      <div className="flex-1 flex flex-col">
        {/* Search + Donation button */}
        <div className="flex gap-3 mb-4">
          <div className="flex-1 relative">
            <HiOutlineSearch className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 text-xl" />
            <input
              type="text"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="ابحث عن منتج..."
              className="w-full pr-10 pl-4 py-3 rounded-xl border border-gray-200 focus:ring-2 focus:ring-bayan-green focus:border-transparent outline-none"
            />
          </div>
          {posSettings.showDonation && (
            <button
              onClick={() => setShowDonation(true)}
              className="flex items-center gap-2 bg-purple-600 hover:bg-purple-700 text-white px-6 py-3 rounded-xl transition-all font-medium"
            >
              <HiOutlineHeart className="text-xl" />
              تبرع
            </button>
          )}
        </div>

        {/* Products */}
        <div className="flex-1 overflow-auto grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-3 content-start">
          {filteredProducts.map((product) => (
            <button
              key={product.id}
              onClick={() => addToCart(product)}
              className="bg-white rounded-xl border border-gray-200 p-3 hover:shadow-lg hover:border-bayan-green transition-all text-center group"
            >
              {product.image_url ? (
                <img
                  src={product.image_url}
                  alt={product.name}
                  className="w-full h-24 object-cover rounded-lg mb-2"
                />
              ) : (
                <div className="w-full h-24 bg-gray-100 rounded-lg mb-2 flex items-center justify-center">
                  <span className="text-3xl text-gray-300">📦</span>
                </div>
              )}
              <p className="font-medium text-gray-800 text-sm truncate">{product.name}</p>
              <p className="text-bayan-green font-bold mt-1">{product.price.toFixed(2)} <SarIcon size={14} /></p>
              <p className="text-xs text-gray-400 mt-1">المتبقي: {product.stock}</p>
            </button>
          ))}

          {filteredProducts.length === 0 && (
            <div className="col-span-full text-center py-16 text-gray-400">
              <p className="text-4xl mb-2">📦</p>
              <p>لا توجد منتجات</p>
            </div>
          )}
        </div>
      </div>

      {/* Cart / Checkout */}
      <div className="w-96 bg-white rounded-2xl shadow-lg border flex flex-col">
        <div className="p-4 border-b">
          <h2 className="text-lg font-bold text-gray-800">🛒 سلة المشتريات</h2>
        </div>

        {/* Cart Items */}
        <div className="flex-1 overflow-auto p-4 space-y-3">
          {cart.length === 0 ? (
            <div className="text-center py-12 text-gray-400">
              <p className="text-4xl mb-2">🛒</p>
              <p>السلة فارغة</p>
              <p className="text-xs mt-1">اضغط على منتج لإضافته</p>
            </div>
          ) : (
            cart.map((item) => (
              <div key={item.product_id} className="flex items-center gap-3 p-3 bg-gray-50 rounded-xl">
                <div className="flex-1">
                  <p className="font-medium text-sm text-gray-800">{item.name}</p>
                  <p className="text-xs text-gray-500">{item.price.toFixed(2)} <SarIcon size={11} /></p>
                </div>
                <div className="flex items-center gap-2">
                  <button
                    onClick={() => updateQuantity(item.product_id, -1)}
                    className="w-7 h-7 rounded-full bg-gray-200 hover:bg-gray-300 flex items-center justify-center transition-all"
                  >
                    <HiOutlineMinus className="text-xs" />
                  </button>
                  <input
                    type="number"
                    step="any"
                    min="0"
                    value={item.quantity}
                    onChange={(e) => setQuantity(item.product_id, e.target.value)}
                    className="w-14 text-center font-bold text-sm rounded border border-gray-200 py-1 outline-none focus:ring-1 focus:ring-bayan-green"
                  />
                  <button
                    onClick={() => updateQuantity(item.product_id, 1)}
                    className="w-7 h-7 rounded-full bg-bayan-green hover:bg-bayan-dark text-white flex items-center justify-center transition-all"
                  >
                    <HiOutlinePlus className="text-xs" />
                  </button>
                </div>
                <div className="text-left w-20">
                  <p className="font-bold text-sm text-bayan-green">
                    {(item.price * item.quantity).toFixed(2)}
                  </p>
                </div>
                <button
                  onClick={() => removeFromCart(item.product_id)}
                  className="text-red-400 hover:text-red-600 transition-all"
                >
                  <HiOutlineTrash />
                </button>
              </div>
            ))
          )}
        </div>

        {/* Checkout Area */}
        <div className="border-t p-4 space-y-3">
          {/* Customer (optional) */}
          <div>
            {selectedCustomer ? (
              <div className="flex items-center justify-between bg-emerald-50 border border-emerald-200 rounded-lg px-3 py-2">
                <div className="text-sm">
                  <span className="font-medium text-gray-800">{selectedCustomer.name}</span>
                  {selectedCustomer.phone && <span className="text-gray-500 mr-2">{selectedCustomer.phone}</span>}
                </div>
                <button onClick={() => setSelectedCustomer(null)} className="text-red-500 hover:text-red-700 text-xl leading-none">×</button>
              </div>
            ) : (
              <div className="relative">
                <div className="flex gap-2">
                  <input
                    type="text"
                    value={customerQuery}
                    onChange={(e) => searchCustomers(e.target.value)}
                    placeholder="العميل (اختياري): بحث بالاسم أو الجوال"
                    className="flex-1 px-3 py-2 rounded-lg border border-gray-300 focus:ring-2 focus:ring-bayan-green outline-none text-sm text-right"
                  />
                  <button
                    onClick={() => setShowNewCustomer((v) => !v)}
                    className="bg-gray-100 hover:bg-gray-200 text-gray-700 px-3 py-2 rounded-lg text-sm whitespace-nowrap"
                  >
                    + جديد
                  </button>
                </div>
                {customerResults.length > 0 && (
                  <div className="absolute z-10 mt-1 w-full bg-white border border-gray-200 rounded-lg shadow-lg max-h-40 overflow-auto">
                    {customerResults.map((c) => (
                      <button
                        key={c.id}
                        onClick={() => selectCustomer(c)}
                        className="block w-full text-right px-3 py-2 hover:bg-gray-50 text-sm"
                      >
                        {c.name}{c.phone ? ` — ${c.phone}` : ''}
                      </button>
                    ))}
                  </div>
                )}
                {showNewCustomer && (
                  <div className="mt-2 p-3 rounded-lg border border-gray-200 bg-gray-50 space-y-2">
                    <input
                      type="text"
                      value={newCustomer.name}
                      onChange={(e) => setNewCustomer({ ...newCustomer, name: e.target.value })}
                      placeholder="اسم العميل"
                      className="w-full px-3 py-2 rounded-lg border border-gray-300 outline-none text-sm text-right"
                    />
                    <div className="flex gap-2" dir="ltr">
                      <select
                        value={countryIso}
                        onChange={(e) => setCountryIso(e.target.value)}
                        className="px-2 py-2 rounded-lg border border-gray-300 outline-none text-sm bg-white"
                      >
                        {COUNTRIES.map((c) => (
                          <option key={c.iso} value={c.iso}>{flagOf(c.iso)} +{c.code}</option>
                        ))}
                      </select>
                      <input
                        type="tel"
                        value={newCustomer.phone}
                        onChange={(e) => setNewCustomer({ ...newCustomer, phone: e.target.value })}
                        placeholder="5XXXXXXXX (اختياري)"
                        className="flex-1 px-3 py-2 rounded-lg border border-gray-300 outline-none text-sm"
                      />
                    </div>
                    <button
                      onClick={createCustomer}
                      className="w-full bg-bayan-green hover:bg-bayan-dark text-white px-3 py-2 rounded-lg text-sm"
                    >
                      إضافة واختيار
                    </button>
                  </div>
                )}
              </div>
            )}
          </div>

          {/* Register picker */}
          {registers.length > 0 && (
            <div className="flex items-center gap-2">
              <label className="text-sm text-gray-600 whitespace-nowrap">الصندوق</label>
              <select
                value={registerId}
                onChange={(e) => { setRegisterId(e.target.value); localStorage.setItem('pos_register_id', e.target.value); }}
                className="flex-1 px-3 py-2 rounded-lg border border-gray-300 focus:ring-2 focus:ring-bayan-green outline-none text-sm"
              >
                {registers.map((r) => (
                  <option key={r.id} value={r.id}>
                    {r.location_name ? `${r.location_name} — ${r.name}` : r.name}
                  </option>
                ))}
              </select>
            </div>
          )}

          {/* Total */}
          <div className="flex justify-between items-center text-xl font-bold">
            <span className="text-gray-700">الإجمالي</span>
            <span className="text-bayan-green">{total.toFixed(2)} <SarIcon size={18} /></span>
          </div>

          {/* Payment Method */}
          <div className={`grid gap-2 ${enabledPaymentMethods.length === 1 ? 'grid-cols-1' : enabledPaymentMethods.length === 2 ? 'grid-cols-2' : 'grid-cols-3'}`}>
            {enabledPaymentMethods.map(({ key, icon: Icon, label }) => (
              <button
                key={key}
                onClick={() => setPaymentMethod(key)}
                className={`flex flex-col items-center gap-1 py-2 rounded-lg border-2 transition-all text-sm ${
                  paymentMethod === key
                    ? 'border-bayan-green bg-bayan-light text-bayan-green'
                    : 'border-gray-200 text-gray-500 hover:border-gray-300'
                }`}
              >
                <Icon className="text-lg" />
                {label}
              </button>
            ))}
          </div>

          {/* Cash input */}
          {paymentMethod === 'cash' && cart.length > 0 && (
            <div>
              <input
                type="number"
                value={cashReceived}
                onChange={(e) => setCashReceived(e.target.value)}
                placeholder="المبلغ المستلم"
                className="w-full px-4 py-2 rounded-lg border border-gray-300 focus:ring-2 focus:ring-bayan-green outline-none text-center text-lg"
              />
              {change > 0 && (
                <p className="text-center mt-2 text-lg font-bold text-emerald-600">
                  الباقي: {change.toFixed(2)} <SarIcon size={16} />
                </p>
              )}
            </div>
          )}

          {/* Card reference input */}
          {paymentMethod === 'card' && cart.length > 0 && (
            <div>
              <input
                type="text"
                value={cardRef}
                onChange={(e) => setCardRef(e.target.value)}
                placeholder="رمز العملية *"
                className="w-full px-4 py-2 rounded-lg border border-gray-300 focus:ring-2 focus:ring-bayan-green outline-none text-center text-lg"
                dir="ltr"
              />
            </div>
          )}

          {/* Checkout button */}
          <button
            onClick={handleCheckout}
            disabled={cart.length === 0 || loading}
            className="w-full bg-bayan-green hover:bg-bayan-dark text-white font-bold py-3 rounded-xl transition-all disabled:opacity-50 disabled:cursor-not-allowed text-lg"
          >
            {loading ? 'جاري المعالجة...' : 'إتمام البيع'}
          </button>
        </div>
      </div>

      {/* Donation Modal */}
      {showDonation && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-2xl w-full max-w-md p-6">
            <h2 className="text-xl font-bold text-gray-800 mb-4 flex items-center gap-2">
              <HiOutlineHeart className="text-purple-600" />
              تسجيل تبرع
            </h2>

            <div className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">مبلغ التبرع (<SarIcon size={12} />) *</label>
                <input
                  type="number"
                  value={donationAmount}
                  onChange={(e) => setDonationAmount(e.target.value)}
                  className="w-full px-4 py-3 rounded-lg border border-gray-300 focus:ring-2 focus:ring-purple-500 outline-none text-center text-xl"
                  placeholder="0.00"
                  autoFocus
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">اسم المتبرع (اختياري)</label>
                <input
                  type="text"
                  value={donorName}
                  onChange={(e) => setDonorName(e.target.value)}
                  className="w-full px-4 py-2 rounded-lg border border-gray-300 focus:ring-2 focus:ring-purple-500 outline-none"
                  placeholder="اسم المتبرع"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">ملاحظة (اختياري)</label>
                <input
                  type="text"
                  value={donationNote}
                  onChange={(e) => setDonationNote(e.target.value)}
                  className="w-full px-4 py-2 rounded-lg border border-gray-300 focus:ring-2 focus:ring-purple-500 outline-none"
                  placeholder="ملاحظة"
                />
              </div>

              {/* Payment method */}
              <div className={`grid gap-2 ${enabledPaymentMethods.length === 1 ? 'grid-cols-1' : enabledPaymentMethods.length === 2 ? 'grid-cols-2' : 'grid-cols-3'}`}>
                {enabledPaymentMethods.map(({ key, icon: Icon, label }) => (
                  <button
                    key={key}
                    onClick={() => setPaymentMethod(key)}
                    className={`flex flex-col items-center gap-1 py-2 rounded-lg border-2 transition-all text-sm ${
                      paymentMethod === key
                        ? 'border-purple-500 bg-purple-50 text-purple-700'
                        : 'border-gray-200 text-gray-500 hover:border-gray-300'
                    }`}
                  >
                    <Icon className="text-lg" />
                    {label}
                  </button>
                ))}
              </div>

              {/* Card reference for donation */}
              {paymentMethod === 'card' && (
                <div>
                  <input
                    type="text"
                    value={donationCardRef}
                    onChange={(e) => setDonationCardRef(e.target.value)}
                    placeholder="رمز العملية *"
                    className="w-full px-4 py-2 rounded-lg border border-gray-300 focus:ring-2 focus:ring-purple-500 outline-none text-center text-lg"
                    dir="ltr"
                  />
                </div>
              )}

              <div className="flex gap-3 mt-4">
                <button
                  onClick={handleDonation}
                  disabled={loading}
                  className="flex-1 bg-purple-600 hover:bg-purple-700 text-white font-bold py-3 rounded-xl transition-all disabled:opacity-50"
                >
                  {loading ? 'جاري التسجيل...' : 'تسجيل التبرع'}
                </button>
                <button
                  onClick={() => setShowDonation(false)}
                  className="px-6 py-3 bg-gray-100 hover:bg-gray-200 text-gray-700 rounded-xl transition-all"
                >
                  إلغاء
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Receipt Modal */}
      {showReceipt && (lastSale || lastDonation) && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-2xl w-full max-w-md max-h-[90vh] overflow-auto">
            <div ref={receiptRef}>
              <Receipt
                sale={lastSale}
                type={lastDonation ? 'donation' : 'sale'}
                donation={lastDonation}
              />
            </div>
            <div className="p-4 border-t no-print space-y-3">
              {/* Primary actions */}
              <div className="flex gap-3">
                <button
                  onClick={handlePrint}
                  className="flex-1 flex items-center justify-center gap-2 bg-bayan-green hover:bg-bayan-dark text-white font-bold py-3 rounded-xl transition-all"
                >
                  <HiOutlinePrinter />
                  طباعة
                </button>
                <button
                  onClick={handleDownloadPDF}
                  className="flex-1 flex items-center justify-center gap-2 bg-blue-600 hover:bg-blue-700 text-white font-bold py-3 rounded-xl transition-all"
                >
                  <HiOutlineDocumentDownload />
                  تحميل PDF
                </button>
              </div>

              {/* Share actions */}
              <div className="flex gap-3">
                <button
                  onClick={handleShareWhatsApp}
                  className="flex-1 flex items-center justify-center gap-2 bg-green-500 hover:bg-green-600 text-white font-medium py-2.5 rounded-xl transition-all"
                >
                  <WhatsAppIcon />
                  واتساب
                </button>
                <button
                  onClick={handleShareEmail}
                  className="flex-1 flex items-center justify-center gap-2 bg-orange-500 hover:bg-orange-600 text-white font-medium py-2.5 rounded-xl transition-all"
                >
                  <HiOutlineMail className="text-xl" />
                  إيميل
                </button>
                <button
                  onClick={() => {
                    setShowReceipt(false);
                    setLastSale(null);
                    setLastDonation(null);
                  }}
                  className="px-6 py-2.5 bg-gray-100 hover:bg-gray-200 text-gray-700 rounded-xl transition-all"
                >
                  إغلاق
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
