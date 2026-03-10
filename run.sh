#!/usr/bin/env bash

echo
echo "============================================"
echo "   نظام نقاط البيع - جمعية بيان بمكة المكرمة"
echo "============================================"
echo

PROJECT_ROOT="$(cd "$(dirname "$0")" && pwd)"

# Check if frontend is built
if [ ! -f "$PROJECT_ROOT/frontend/dist/index.html" ]; then
    echo "⚠️ الواجهة غير مبنية. جاري البناء..."
    cd "$PROJECT_ROOT/frontend" || exit

    npm run build
    if [ $? -ne 0 ]; then
        echo "❌ فشل بناء الواجهة. الرجاء تشغيل install.sh أولاً"
        exit 1
    fi
fi

echo "✅ جاري تشغيل الخادم..."
echo
echo "============================================"
echo "   النظام يعمل على: http://localhost:8000"
echo "============================================"
echo
echo "   بيانات الدخول:"
echo "   المدير:  admin / admin123"
echo "   الكاشير: cashier / cashier123"
echo
echo "   لإيقاف النظام: اضغط Ctrl+C"
echo "============================================"
echo

# Open browser automatically (Linux)
if command -v xdg-open > /dev/null; then
    xdg-open "http://localhost:8000" >/dev/null 2>&1 &
fi

# Start backend
cd "$PROJECT_ROOT/backend" || exit
python3 -m uvicorn main:app --host 0.0.0.0 --port 8000
