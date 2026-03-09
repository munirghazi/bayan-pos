import { useState, useEffect } from 'react';
import { reportsAPI } from '../services/api';
import { SarIcon } from '../components/SarIcon';
import {
  HiOutlineCash,
  HiOutlineShoppingCart,
  HiOutlineHeart,
  HiOutlineExclamation,
} from 'react-icons/hi';
import toast from 'react-hot-toast';

function StatCard({ icon: Icon, label, value, subValue, color }) {
  const colors = {
    green: 'bg-emerald-50 text-emerald-700 border-emerald-200',
    blue: 'bg-blue-50 text-blue-700 border-blue-200',
    purple: 'bg-purple-50 text-purple-700 border-purple-200',
    orange: 'bg-orange-50 text-orange-700 border-orange-200',
  };

  const iconColors = {
    green: 'bg-emerald-100 text-emerald-600',
    blue: 'bg-blue-100 text-blue-600',
    purple: 'bg-purple-100 text-purple-600',
    orange: 'bg-orange-100 text-orange-600',
  };

  return (
    <div className={`rounded-xl border p-6 ${colors[color]}`}>
      <div className="flex items-center justify-between">
        <div>
          <p className="text-sm font-medium opacity-75">{label}</p>
          <p className="text-2xl font-bold mt-1">{value}</p>
          {subValue && <p className="text-xs mt-1 opacity-60">{subValue}</p>}
        </div>
        <div className={`w-12 h-12 rounded-xl flex items-center justify-center ${iconColors[color]}`}>
          <Icon className="text-2xl" />
        </div>
      </div>
    </div>
  );
}

export default function Dashboard() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadDashboard();
  }, []);

  const loadDashboard = async () => {
    try {
      const res = await reportsAPI.getDashboard();
      setData(res.data);
    } catch (err) {
      toast.error('خطأ في تحميل البيانات');
    } finally {
      setLoading(false);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-bayan-green"></div>
      </div>
    );
  }

  if (!data) return null;

  const paymentMethodAr = { cash: 'نقدي', card: 'شبكة', transfer: 'تحويل' };

  const sarSuffix = (amount) => (
    <>{amount.toFixed(2)} <SarIcon size={16} /></>
  );

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-gray-800">لوحة التحكم</h1>
        <p className="text-gray-500 mt-1">ملخص اليوم - {new Date().toLocaleDateString('ar-SA')}</p>
      </div>

      {/* Stats Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard
          icon={HiOutlineCash}
          label="مبيعات اليوم"
          value={sarSuffix(data.today.sales_total)}
          subValue={`${data.today.sales_count} عملية`}
          color="green"
        />
        <StatCard
          icon={HiOutlineHeart}
          label="تبرعات اليوم"
          value={sarSuffix(data.today.donations_total)}
          subValue={`${data.today.donations_count} تبرع`}
          color="purple"
        />
        <StatCard
          icon={HiOutlineShoppingCart}
          label="إجمالي المبيعات"
          value={sarSuffix(data.all_time.sales_total)}
          subValue={`${data.all_time.sales_count} عملية`}
          color="blue"
        />
        <StatCard
          icon={HiOutlineHeart}
          label="إجمالي التبرعات"
          value={sarSuffix(data.all_time.donations_total)}
          subValue={`${data.all_time.donations_count} تبرع`}
          color="orange"
        />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Recent Sales */}
        <div className="bg-white rounded-xl shadow-sm border p-6">
          <h2 className="text-lg font-bold text-gray-800 mb-4">آخر المبيعات</h2>
          {data.recent_sales.length === 0 ? (
            <p className="text-gray-400 text-center py-8">لا توجد مبيعات بعد</p>
          ) : (
            <div className="space-y-3">
              {data.recent_sales.map((sale) => (
                <div key={sale.id} className="flex items-center justify-between p-3 bg-gray-50 rounded-lg">
                  <div>
                    <p className="font-medium text-gray-700">فاتورة #{sale.id}</p>
                    <p className="text-xs text-gray-500">
                      {sale.user_name} • {paymentMethodAr[sale.payment_method]}
                    </p>
                  </div>
                  <div className="text-left">
                    <p className="font-bold text-bayan-green">{sale.total.toFixed(2)} <SarIcon size={13} /></p>
                    <p className="text-xs text-gray-400">
                      {new Date(sale.created_at).toLocaleTimeString('ar-SA', { hour: '2-digit', minute: '2-digit' })}
                    </p>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Recent Donations */}
        <div className="bg-white rounded-xl shadow-sm border p-6">
          <h2 className="text-lg font-bold text-gray-800 mb-4">آخر التبرعات</h2>
          {data.recent_donations.length === 0 ? (
            <p className="text-gray-400 text-center py-8">لا توجد تبرعات بعد</p>
          ) : (
            <div className="space-y-3">
              {data.recent_donations.map((donation) => (
                <div key={donation.id} className="flex items-center justify-between p-3 bg-gray-50 rounded-lg">
                  <div>
                    <p className="font-medium text-gray-700">
                      {donation.donor_name || 'متبرع مجهول'}
                    </p>
                    <p className="text-xs text-gray-500">تبرع #{donation.id}</p>
                  </div>
                  <div className="text-left">
                    <p className="font-bold text-purple-600">{donation.amount.toFixed(2)} <SarIcon size={13} /></p>
                    <p className="text-xs text-gray-400">
                      {new Date(donation.created_at).toLocaleTimeString('ar-SA', { hour: '2-digit', minute: '2-digit' })}
                    </p>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Low Stock Alert */}
      {data.low_stock.length > 0 && (
        <div className="bg-orange-50 border border-orange-200 rounded-xl p-6">
          <div className="flex items-center gap-2 mb-3">
            <HiOutlineExclamation className="text-2xl text-orange-600" />
            <h2 className="text-lg font-bold text-orange-700">تنبيه: مخزون منخفض</h2>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
            {data.low_stock.map((product) => (
              <div key={product.id} className="flex items-center justify-between p-3 bg-white rounded-lg">
                <span className="font-medium text-gray-700">{product.name}</span>
                <span className="bg-orange-100 text-orange-700 px-3 py-1 rounded-full text-sm font-bold">
                  {product.stock} متبقي
                </span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
