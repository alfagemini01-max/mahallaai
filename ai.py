"""Google Gemini AI integratsiyasi.

Ikki vazifa:
1. classify_message  — guruh xabarini tahlil qilib, turi/kategoriyasi/jiddiyligini aniqlash
2. weekly_report     — haftalik yozishmalar asosida tahliliy hisobot yaratish

Gemini REST API to'g'ridan-to'g'ri httpx orqali chaqiriladi (qo'shimcha SDK talab qilmaydi).
"""
import json
import logging

import httpx

import config
from roles import CATEGORIES

log = logging.getLogger("ai")

GEMINI_URL = (
    "https://generativelanguage.googleapis.com/v1beta/models/"
    "{model}:generateContent?key={key}"
)

# Oldindan filtrlash uchun kalit so'zlar: bularsiz ham LLM chaqirilmaydi
# (xarajatni kamaytiradi). Ro'yxatda so'z uchrasa YOKI xabar uzun bo'lsa — LLM ga boradi.
_HINT_WORDS = (
    "svet", "свет", "chiroq", "elektr", "электр", "tok ", "gaz", "газ",
    "suv", "сув", "вода", "kanaliz", "канализ", "quvur", "труб",
    "axlat", "chiqindi", "мусор", "yo'l", "yol", "yul", "дорог", "chuqur",
    "muammo", "муаммо", "проблем", "shikoyat", "шикоят", "yordam", "ёрдам",
    "помощ", "o'chib", "ochib", "uchib", "yo'q", "yoq", "нет", "ishlamay",
    "buzil", "бузил", "yoril", "tiqil", "hid", "ҳид", "запах", "shovqin",
    "шовқин", "janjal", "bezori", "жанжал", "kerak", "керак", "iltimos",
    "илтимос", "qachon", "качон", "nega", "нега", "почему",
)


def needs_ai(text: str) -> bool:
    """Arzon oldindan filtr: aniq muammo belgisi bo'lmagan qisqa gaplar tashlanadi."""
    if len(text) < config.MIN_TEXT_LEN:
        return False
    low = text.lower()
    if any(w in low for w in _HINT_WORDS):
        return True
    # Uzunroq xabarlar baribir tekshiriladi (reklama/e'lon statistikasi uchun)
    return len(text) >= 60


def _category_docs() -> str:
    lines = []
    for key, info in CATEGORIES.items():
        lines.append(f'- "{key}": {info["label"]} — {info["desc"]}')
    return "\n".join(lines)


CLASSIFY_PROMPT = """Sen O'zbekiston mahalla Telegram guruhi xabarlarini tahlil qiluvchi tizimsan.
Xabarlar o'zbek (lotin/kirill), rus tilida, sheva va imlo xatolari bilan bo'lishi mumkin.

Xabarni tahlil qilib FAQAT quyidagi JSON formatida javob ber (boshqa hech narsa yozma):

{{
  "turi": "muammo | elon | reklama | savol | minnatdorchilik | oddiy_suhbat | spam",
  "kategoriya": "elektr | gaz | suv | chiqindi | yol | huquq | ijtimoiy | boshqa",
  "jiddiylik": "past | orta | yuqori | favqulodda",
  "qisqacha": "muammoning 1 jumlalik neytral bayoni (o'zbek lotin yozuvida)",
  "manzil": "xabarda aytilgan ko'cha/uy/joy nomi, bo'lmasa bo'sh qator",
  "ishonch": 0.0
}}

Qoidalar:
- "turi" = "muammo" FAQAT aholi real muammo/shikoyat/nosozlik haqida yozganda.
- Reklama, xizmat taklifi ("santexnik xizmati", "sotiladi") = "reklama".
- To'y/hashar/yig'ilish e'loni = "elon".
- Salomlashish, hazil, stiker-javob, umumiy gap = "oddiy_suhbat".
- Ma'nosiz, haqoratli, takroriy, asossiz xabar = "spam".
- "jiddiylik" = "favqulodda" FAQAT hayotga xavf bo'lsa: gaz hidi, ochiq elektr simi,
  suv toshqini, yong'in, zo'ravonlik.
- "ishonch" — tahlilingga ishonch darajasi (0.0 dan 1.0 gacha).
- Eski voqea eslash, boshqa hudud haqida gap, hazil ohangi bo'lsa — ishonchni pasaytir.

Kategoriyalar:
{categories}

Xabar:
\"\"\"{text}\"\"\"
"""


async def _call_gemini(prompt: str, json_mode: bool = True, temperature: float = 0.1) -> str | None:
    """Gemini API ga so'rov. Xato bo'lsa None qaytaradi (bot yiqilmasligi kerak)."""
    if not config.GEMINI_API_KEY:
        log.warning("GEMINI_API_KEY kiritilmagan — AI tahlil o'chirilgan")
        return None
    url = GEMINI_URL.format(model=config.GEMINI_MODEL, key=config.GEMINI_API_KEY)
    body = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": temperature, "maxOutputTokens": 2048},
    }
    if json_mode:
        body["generationConfig"]["responseMimeType"] = "application/json"
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            r = await client.post(url, json=body)
            r.raise_for_status()
            data = r.json()
            return data["candidates"][0]["content"]["parts"][0]["text"]
    except Exception as e:  # tarmoq, kvota, parsing — hammasi yumshoq o'tadi
        log.error("Gemini xatosi: %s", e)
        return None


async def classify_message(text: str) -> dict | None:
    """Xabarni tasniflash. Natija: dict yoki None (AI ishlamasa)."""
    prompt = CLASSIFY_PROMPT.format(categories=_category_docs(), text=text[:2000])
    raw = await _call_gemini(prompt, json_mode=True)
    if not raw:
        return None
    try:
        raw = raw.strip().removeprefix("```json").removeprefix("```").removesuffix("```")
        data = json.loads(raw)
    except json.JSONDecodeError:
        log.error("Gemini JSON emas: %s", raw[:200])
        return None

    # Qiymatlarni xavfsiz normallashtirish
    turi = str(data.get("turi", "oddiy_suhbat")).lower()
    kategoriya = str(data.get("kategoriya", "boshqa")).lower()
    if kategoriya not in CATEGORIES:
        kategoriya = "boshqa"
    jiddiylik = str(data.get("jiddiylik", "orta")).lower()
    if jiddiylik not in ("past", "orta", "yuqori", "favqulodda"):
        jiddiylik = "orta"
    try:
        ishonch = float(data.get("ishonch", 0))
    except (TypeError, ValueError):
        ishonch = 0.0

    return {
        "turi": turi,
        "kategoriya": kategoriya,
        "jiddiylik": jiddiylik,
        "qisqacha": str(data.get("qisqacha", ""))[:450],
        "manzil": str(data.get("manzil", ""))[:250],
        "ishonch": max(0.0, min(1.0, ishonch)),
    }


WEEKLY_PROMPT = """Sen mahalla raisining tahlilchi yordamchisisan. Quyida mahalla Telegram
guruhining bir haftalik statistikasi va muammolari berilgan. Shu asosda o'zbek tilida
(lotin yozuvi) qisqa tahliliy hisobot yoz.

Hisobot tuzilishi (Telegram uchun, HTML teglarsiz, emoji bilan, 250 so'zdan oshmasin):
1. Umumiy holat (2-3 jumla)
2. Asosiy muammo yo'nalishlari — qaysi soha "oqsayapti"
3. Hal qilingan ishlar (ijobiy ohangda)
4. Raisga aniq tavsiyalar (2-3 ta, amaliy)

Neytral, hurmatli va konstruktiv ohangda yoz. Hech qanday shaxs ismini tilga olma.

MA'LUMOTLAR:
{data}
"""


async def weekly_report(stats_text: str) -> str | None:
    """Haftalik tahliliy hisobot matnini yaratish."""
    prompt = WEEKLY_PROMPT.format(data=stats_text[:6000])
    return await _call_gemini(prompt, json_mode=False, temperature=0.4)
