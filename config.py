"""Mahalla AI Bot - Konfiguratsiya.

Barcha sozlamalar muhit o'zgaruvchilari (Environment Variables) orqali olinadi.
Render.com da: Dashboard -> Environment bo'limida kiritiladi.
Lokal ishlatishda: .env faylidan (python-dotenv o'rnatilgan bo'lsa) yoki export orqali.
"""
import os
import secrets

# .env faylini yuklashga urinish (lokal ishlatish uchun, majburiy emas)
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# ========== ASOSIY SOZLAMALAR ==========

# Telegram bot tokeni (@BotFather dan olinadi)
BOT_TOKEN = os.getenv("BOT_TOKEN", "")

# Google Gemini API kaliti (https://aistudio.google.com/apikey dan olinadi)
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")

# Ma'lumotlar bazasi. Standart: SQLite (lokal fayl).
# Render'da doimiy saqlash uchun PostgreSQL tavsiya etiladi (README ga qarang).
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./mahalla.db")
if DATABASE_URL.startswith("postgres://"):
    # Render eski formatda beradi, SQLAlchemy yangi formatni talab qiladi
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

# Web panel sessiyalarini imzolash uchun maxfiy kalit.
# MUHIM: Production'da o'zingiz tasodifiy uzun qiymat kiriting!
SECRET_KEY = os.getenv("SECRET_KEY", secrets.token_hex(32))

# Birinchi ishga tushishda yaratiladigan Super Admin hisobi
ADMIN_USERNAME = os.getenv("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD", "admin12345")

# Sayt manzili. Render avtomatik RENDER_EXTERNAL_URL beradi.
BASE_URL = (os.getenv("BASE_URL") or os.getenv("RENDER_EXTERNAL_URL", "")).rstrip("/")

# Webhook yo'lini himoyalash uchun maxfiy so'z
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "mahalla-hook-2026")

# ========== BOT MANTIG'I SOZLAMALARI ==========

# Muammo rasmiy topshiriqqa aylanishi uchun nechta aholi tasdig'i kerak
CONFIRM_THRESHOLD = int(os.getenv("CONFIRM_THRESHOLD", "2"))

# "Hal qilindi"ni rad etish / tasdiqlash uchun ovozlar soni
VERIFY_THRESHOLD = int(os.getenv("VERIFY_THRESHOLD", "2"))

# AI ishonch darajasi shundan past bo'lsa, muammo yaratilmaydi (0..1)
MIN_CONFIDENCE = float(os.getenv("MIN_CONFIDENCE", "0.55"))

# Tahlil qilinadigan minimal xabar uzunligi (spam/qisqa gaplarni filtrlash)
MIN_TEXT_LEN = int(os.getenv("MIN_TEXT_LEN", "8"))

# Toshkent vaqti (UTC+5)
TZ_OFFSET_HOURS = 5

# Haftalik hisobot: yakshanba (0=Dushanba ... 6=Yakshanba), soat 19:00 (mahalliy)
WEEKLY_REPORT_WEEKDAY = int(os.getenv("WEEKLY_REPORT_WEEKDAY", "6"))
WEEKLY_REPORT_HOUR = int(os.getenv("WEEKLY_REPORT_HOUR", "19"))
