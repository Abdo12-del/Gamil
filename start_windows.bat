@echo off
chcp 65001 >nul
title Gamil CloudPool v2.0 - Unified Cloud Storage
echo ================================================================
echo   Gamil CloudPool v2.0 - تشغيل المنصة الموحدة بضغطة واحدة
echo ================================================================

if not exist ".venv" (
    echo [1/3] جاري تجهيز البيئة الافتراضية لأول مرة...
    python -m venv .venv
)

call .venv\Scripts\activate.bat
echo [2/3] جاري التحقق من المكتبات المطلوبة...
pip install --quiet -r requirements.txt

echo [3/3] جاري فتح الواجهة الرسومية وتشغيل المحرك...
start "" "http://127.0.0.1:8000"
python run.py --no-browser
pause
