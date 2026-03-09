@echo off
chcp 65001 >nul
title نظام نقاط البيع - جمعية بيان

echo.
echo ============================================
echo   نظام نقاط البيع - جمعية بيان بمكة المكرمة
echo ============================================
echo.

:: Check if frontend is built
if not exist "%~dp0frontend\dist\index.html" (
    echo ⚠️ الواجهة غير مبنية. جاري البناء...
    cd /d "%~dp0frontend"
    call npm run build
    if %errorlevel% neq 0 (
        echo ❌ فشل بناء الواجهة. الرجاء تشغيل install.bat أولاً
        pause
        exit /b 1
    )
)

echo ✅ جاري تشغيل الخادم...
echo.
echo ============================================
echo   النظام يعمل على: http://localhost:8000
echo ============================================
echo.
echo   بيانات الدخول:
echo   المدير:  admin / admin123
echo   الكاشير: cashier / cashier123
echo.
echo   لإيقاف النظام: اضغط Ctrl+C
echo ============================================
echo.

:: Open browser automatically
start "" "http://localhost:8000"

:: Start backend server (serves both API + frontend)
cd /d "%~dp0backend"
python -m uvicorn main:app --host 0.0.0.0 --port 8000

pause
