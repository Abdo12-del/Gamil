#!/usr/bin/env python3
"""
Gamil CloudPool — المشغّل الموحد الجاهز (Standalone Launcher)
يشغّل قاعدة البيانات، محرك التوسع التلقائي الخلفي، والواجهة الرسومية الموحدة بضغطة واحدة.
"""

import argparse
import os
import sys
import threading
import time
import webbrowser

import uvicorn

from backend.database import init_db


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Gamil CloudPool — منصة التخزين السحابي الموحد والتوسع التلقائي الخلفي"
    )
    parser.add_argument("--host", default="0.0.0.0", help="عنوان الاستضافة (الافتراضي: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=8000, help="رقم المنفذ (الافتراضي: 8000)")
    parser.add_argument(
        "--no-browser",
        action="store_true",
        help="عدم فتح المتصفح تلقائيًا عند بدء التشغيل",
    )
    args = parser.parse_args()

    os.makedirs("storage_nodes", exist_ok=True)
    init_db()

    url = f"http://127.0.0.1:{args.port}"
    print("=" * 68)
    print("☁️  Gamil CloudPool v2.0 — Unified Storage & Background Auto-Scaler")
    print(f"🚀 الواجهة الموحدة جاهزة على الرابط: {url}")
    print("=" * 68)

    if not args.no_browser and os.environ.get("DISPLAY"):
        def _open() -> None:
            time.sleep(1.2)
            try:
                webbrowser.open(url)
            except Exception:
                pass

        threading.Thread(target=_open, daemon=True).start()

    uvicorn.run("backend.main:app", host=args.host, port=args.port, reload=False)


if __name__ == "__main__":
    main()
