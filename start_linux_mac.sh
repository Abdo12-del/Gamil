#!/usr/bin/env bash
set -e

echo "================================================================"
echo "  ☁️  Gamil CloudPool v2.0 — تشغيل المنصة الموحدة بضغطة واحدة"
echo "================================================================"

if [ ! -d ".venv" ]; then
    echo "[1/3] جاري إنشاء البيئة الافتراضية (.venv)..."
    python3 -m venv .venv
fi

source .venv/bin/activate
echo "[2/3] جاري تثبيت/تحديث المتطلبات..."
pip install --quiet -r requirements.txt

echo "[3/3] جاري تشغيل خادم Gamil CloudPool على الرابط http://127.0.0.1:8000 ..."
python3 run.py
