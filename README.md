# 🏘 Mahalla AI Bot

Mahalla Telegram guruhlarini sun'iy intellekt (Google Gemini) yordamida kuzatib, aholi muammolarini avtomatik aniqlaydigan, mas'ullarga yetkazadigan va hal bo'lishini nazorat qiladigan tizim.

**Tarkibi:** Telegram bot + Web boshqaruv paneli (bitta ilova sifatida ishlaydi).

---

## Imkoniyatlar

- 🤖 Guruh xabarlarini AI tahlili: muammo / reklama / spam / e'lon / savol / oddiy suhbatni ajratadi
- 🚫 Reklama, spam va asossiz murojaatlar topshiriqqa aylanmaydi — faqat statistikada hisoblanadi
- 👍 Yolg'on signalga qarshi: muammo mas'ulga ketishidan oldin aholidan 2 ta tasdiq so'raladi (favqulodda holatlar darhol yuboriladi)
- 📬 Kategoriyaga qarab avtomatik yo'naltirish: elektr → elektr mas'uli, gaz → gaz mas'uli va h.k. (mas'ul bo'lmasa — raisga)
- ✅ "Hal qilindi"dan keyin **xalq tekshiruvi**: aholi 👍/👎 orqali baholaydi, rad etilsa muammo qayta ochiladi
- 📊 Har yakshanba 19:00 da haftalik AI hisobot: guruhga qisqa, raisga batafsil
- 🌐 Web panel: dashboard, muammolar boshqaruvi, mas'ullar (maqomlar), mahallalar, tahlil
- 🔒 Maxfiylik: hisobotlarda muallif ismlari ko'rsatilmaydi; aholi shaxsiy (anonim) murojaat ham yubora oladi

## Maqomlar tizimi

| Maqom | Ko'rish doirasi | Vakolatlar |
|---|---|---|
| **Super Admin** | Barcha mahallalar | Hamma narsa: mahalla, maqom yaratish, parollar |
| **Hokimiyat vakili** | Barcha mahallalar | Mahalla darajasidagi maqomlarni yaratish, barcha muammolar |
| **Mahalla raisi** | O'z mahallasi | Barcha muammolar, mas'ul tayinlash, ulanish kodlari |
| **Profilaktika inspektori** | O'z mahallasi | Huquq-tartibot muammolari |
| **Elektr mas'uli** | O'z mahallasi | Elektr/yoritish muammolari |
| **Gaz mas'uli** | O'z mahallasi | Gaz muammolari |
| **Suv mas'uli** | O'z mahallasi | Suv/kanalizatsiya muammolari |
| **Ijtimoiy mas'ul** | O'z mahallasi | Ijtimoiy masalalar |
| **Obodonlashtirish mas'uli** | O'z mahallasi | Chiqindi, yo'l, infratuzilma |

---

## 1-QADAM. Telegram bot yaratish

1. Telegramda [@BotFather](https://t.me/BotFather) ga kiring
2. `/newbot` → bot nomi → bot username (masalan, `MahallaAI_bot`)
3. Berilgan **tokenni** saqlab qo'ying (`123456:AAA...` ko'rinishida)
4. **⚠️ ENG MUHIM QADAM:** botga guruh xabarlarini o'qish ruxsatini bering:
   - BotFather'da: `/setprivacy` → botingizni tanlang → **Disable**
   - Aks holda bot guruhda faqat buyruqlarni ko'radi va suhbatni tahlil qila olmaydi!
   - (Muqobil: botni guruhda administrator qilsangiz ham xabarlarni ko'radi)

## 2-QADAM. Gemini API kaliti olish

1. https://aistudio.google.com/apikey saytiga kiring (Google hisob kerak)
2. **Create API key** tugmasini bosing
3. `AIzaSy...` bilan boshlanadigan kalitni saqlab qo'ying
4. Bepul tarif kuniga yetarli so'rovlar beradi (kichik mahallalar uchun bemalol yetadi)

## 3-QADAM. GitHub'ga joylash

```bash
cd mahalla-ai-bot
git init
git add .
git commit -m "Mahalla AI bot"
git branch -M main
git remote add origin https://github.com/SIZNING_LOGIN/mahalla-ai-bot.git
git push -u origin main
```

## 4-QADAM. Render'da ishga tushirish

1. https://render.com da ro'yxatdan o'ting (GitHub bilan kirish qulay)
2. **New → Web Service** → GitHub repozitoriyingizni tanlang
3. Sozlamalar (render.yaml bo'lgani uchun ko'pi avtomatik to'ladi):
   - **Runtime:** Python
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `uvicorn main:app --host 0.0.0.0 --port $PORT`
4. **Environment Variables** bo'limida kiriting:

| O'zgaruvchi | Qiymat |
|---|---|
| `BOT_TOKEN` | BotFather'dan olingan token |
| `GEMINI_API_KEY` | Gemini kaliti |
| `ADMIN_USERNAME` | super admin logini (masalan `admin`) |
| `ADMIN_PASSWORD` | **kuchli parol o'ylab toping!** |
| `SECRET_KEY` | istalgan uzun tasodifiy satr |
| `WEBHOOK_SECRET` | istalgan tasodifiy so'z |

5. **Create Web Service** — bir necha daqiqada sayt ochiladi:
   `https://mahalla-ai-bot.onrender.com` (webhook avtomatik o'rnatiladi)

> **💾 Ma'lumotlar bazasi haqida:** standart holatda SQLite ishlatiladi. Render bepul tarifida disk **vaqtinchalik** — har deploy'da ma'lumotlar o'chadi. Doimiy saqlash uchun: Render'da **New → PostgreSQL** yarating va uning `Internal Database URL` qiymatini `DATABASE_URL` o'zgaruvchisiga kiriting. Kod hech qanday o'zgarishsiz Postgres bilan ishlaydi.

> **😴 Uxlash haqida:** Render bepul tarifida 15 daqiqa harakatsizlikdan keyin xizmat uxlaydi va birinchi so'rovda 30-50 soniyada uyg'onadi. Webhook kelganda avtomatik uyg'onadi, lekin kechikish bo'lishi mumkin. Jiddiy foydalanish uchun pullik tarif tavsiya etiladi.

## 5-QADAM. Tizimni sozlash

1. **Panelga kiring:** `https://SIZNING-APP.onrender.com` → super admin login/parol
2. **Mahalla qo'shing:** «Mahallalar» → nomi, tumani (guruh ID keyinroq)
3. **Botni guruhga qo'shing:** mahalla Telegram guruhiga botni qo'shing — u guruh ID sini yozib chiqaradi (yoki guruhda `/chatid` yozing)
4. **Guruhni bog'lang:** panelda «Mahallalar» → guruh ID maydoniga `-100...` ni kiritib 💾 bosing
5. **Mas'ullarni yarating:** «Mas'ullar» → F.I.Sh., maqom, mahalla, login, parol
6. **Mas'ullarni Telegramga ulang:** jadvalda har bir mas'ulning **ulanish kodi** ko'rinadi. Mas'ul botga shaxsiy yozadi: `/ulanish KOD` — shundan keyin topshiriqlar unga shaxsiy xabarda keladi
7. Tayyor! Guruhda kimdir «3 kundan beri svet yo'q» deb yozsa — bot muammoni aniqlab jarayonni boshlaydi.

## Lokal ishga tushirish (test uchun)

```bash
pip install -r requirements.txt
cp .env.example .env    # va qiymatlarni to'ldiring
uvicorn main:app --reload
```

`BASE_URL` bo'sh bo'lsa bot **polling** rejimida ishlaydi (webhook shart emas) — lokal test uchun qulay. Panel: http://localhost:8000

## Bot buyruqlari

| Buyruq | Kim uchun | Vazifasi |
|---|---|---|
| `/start` | Hamma | Tanishuv |
| `/ulanish KOD` | Mas'ullar | Telegram hisobini panelga bog'lash |
| `/muammolar` | Mas'ullar | Ochiq topshiriqlar (tugmalar bilan) |
| `/hisobot` | Mas'ullar | Qisqa statistika |
| `/chatid` | Guruhda | Guruh ID sini olish |
| `/yordam` | Hamma | Qo'llanma |

Aholi botga **shaxsiy** yozsa — murojaat anonim tarzda qabul qilinib, mas'ullarga yuboriladi.

## Texnik tuzilishi

```
main.py            — FastAPI: webhook + panel + fon vazifalari
config.py          — sozlamalar (env)
roles.py           — maqomlar, kategoriyalar, statuslar "konstitutsiyasi"
database.py        — SQLAlchemy modellari (SQLite/PostgreSQL)
ai.py              — Gemini: xabar tasnifi + haftalik hisobot
bot/handlers.py    — bot mantig'i (tahlil, tasdiqlash, statuslar, tekshiruv)
bot/weekly.py      — haftalik hisobot scheduler
web/routes.py      — panel sahifalari va amallar
web/templates/     — HTML shablonlar (o'zbek tilida)
static/style.css   — dizayn
```
