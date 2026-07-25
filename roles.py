"""Maqomlar (rollar), muammo kategoriyalari va statuslar tizimi.

Bu fayl — loyihaning "konstitutsiyasi": qaysi maqom nima ko'radi,
qaysi kategoriya kimga tegishli — hammasi shu yerda belgilanadi.
"""

# ============================================================
# MAQOMLAR (ROLLAR)
# ============================================================

ROLE_SUPER_ADMIN = "super_admin"
ROLE_HOKIMIYAT = "hokimiyat_vakili"
ROLE_RAIS = "rais"
ROLE_INSPEKTOR = "inspektor"
ROLE_ELEKTR = "elektr_masul"
ROLE_GAZ = "gaz_masul"
ROLE_SUV = "suv_masul"
ROLE_IJTIMOIY = "ijtimoiy_masul"
ROLE_OBODON = "obodonlashtirish_masul"

ROLE_LABELS = {
    ROLE_SUPER_ADMIN: "Super Admin",
    ROLE_HOKIMIYAT: "Hokimiyat vakili",
    ROLE_RAIS: "Mahalla raisi",
    ROLE_INSPEKTOR: "Profilaktika inspektori",
    ROLE_ELEKTR: "Elektr tarmog'i mas'uli",
    ROLE_GAZ: "Gaz ta'minoti mas'uli",
    ROLE_SUV: "Suv ta'minoti mas'uli",
    ROLE_IJTIMOIY: "Ijtimoiy masalalar mas'uli",
    ROLE_OBODON: "Obodonlashtirish mas'uli",
}

# Barcha mahallalarni ko'ra oladigan maqomlar
GLOBAL_ROLES = {ROLE_SUPER_ADMIN, ROLE_HOKIMIYAT}

# O'z mahallasidagi BARCHA muammolarni ko'radigan va boshqaradigan maqomlar
MAHALLA_MANAGER_ROLES = {ROLE_RAIS}

# Faqat o'ziga biriktirilgan kategoriya muammolarini ko'radigan maqomlar
SECTOR_ROLES = {
    ROLE_INSPEKTOR, ROLE_ELEKTR, ROLE_GAZ,
    ROLE_SUV, ROLE_IJTIMOIY, ROLE_OBODON,
}

# Web panelga kira oladigan maqomlar (hammasi kiradi, ko'rinishi cheklanadi)
PANEL_ROLES = set(ROLE_LABELS.keys())

# Foydalanuvchi yarata oladigan maqomlar:
# Super admin -> hammani; Hokimiyat vakili -> mahalla darajasidagilarni
CREATABLE_BY = {
    ROLE_SUPER_ADMIN: [r for r in ROLE_LABELS if r != ROLE_SUPER_ADMIN],
    ROLE_HOKIMIYAT: [ROLE_RAIS, ROLE_INSPEKTOR, ROLE_ELEKTR, ROLE_GAZ,
                     ROLE_SUV, ROLE_IJTIMOIY, ROLE_OBODON],
}

# ============================================================
# MUAMMO KATEGORIYALARI va ULARNING MAS'ULLARI
# ============================================================
# AI har bir xabarni shu kategoriyalardan biriga ajratadi.
# Har bir kategoriya -> asosiy mas'ul maqom.
# Agar mahallada shu maqomdagi xodim bo'lmasa -> rais oladi (fallback).

CATEGORIES = {
    "elektr": {
        "label": "Elektr / Yoritish",
        "emoji": "⚡",
        "role": ROLE_ELEKTR,
        "desc": "Svet o'chishi, kuchlanish pasayishi, ko'cha chiroqlari, sim uzilishi",
    },
    "gaz": {
        "label": "Gaz ta'minoti",
        "emoji": "🔥",
        "role": ROLE_GAZ,
        "desc": "Gaz bosimi, gaz yo'qligi, gaz hidi (favqulodda!), quvur nosozligi",
    },
    "suv": {
        "label": "Suv / Kanalizatsiya",
        "emoji": "💧",
        "role": ROLE_SUV,
        "desc": "Ichimlik suvi, quvur yorilishi, kanalizatsiya tiqilishi, oqava",
    },
    "chiqindi": {
        "label": "Chiqindi / Tozalik",
        "emoji": "🗑",
        "role": ROLE_OBODON,
        "desc": "Axlat olib ketilmasligi, noqonuniy chiqindixona, ifloslik",
    },
    "yol": {
        "label": "Yo'l / Infratuzilma",
        "emoji": "🛣",
        "role": ROLE_OBODON,
        "desc": "Yo'l chuqurlari, trotuar, bolalar maydonchasi, daraxtlar, ariq",
    },
    "huquq": {
        "label": "Huquq-tartibot",
        "emoji": "🚔",
        "role": ROLE_INSPEKTOR,
        "desc": "Bezorilik, shovqin, shubhali holat, noqonuniy savdo, janjal",
    },
    "ijtimoiy": {
        "label": "Ijtimoiy masalalar",
        "emoji": "🤝",
        "role": ROLE_IJTIMOIY,
        "desc": "Kam ta'minlangan oila, yolg'iz keksa, nogironlik, ishsizlik, yordam so'rovi",
    },
    "boshqa": {
        "label": "Boshqa muammo",
        "emoji": "📌",
        "role": ROLE_RAIS,
        "desc": "Yuqoridagilarga kirmaydigan mahalla muammolari",
    },
}

# AI xabar turlari (muammo bo'lmaganlari faqat statistikaga yoziladi)
MSG_TYPES = {
    "muammo": "Muammo / Shikoyat",
    "elon": "E'lon / Tadbir",
    "reklama": "Reklama / Xizmat taklifi",
    "savol": "Savol",
    "minnatdorchilik": "Minnatdorchilik",
    "oddiy_suhbat": "Oddiy suhbat",
    "spam": "Spam / Asossiz",
}

# Jiddiylik darajalari
SEVERITY = {
    "past": {"label": "Past", "emoji": "🟢"},
    "orta": {"label": "O'rta", "emoji": "🟡"},
    "yuqori": {"label": "Yuqori", "emoji": "🟠"},
    "favqulodda": {"label": "FAVQULODDA", "emoji": "🔴"},
}

# ============================================================
# MUAMMO STATUSLARI
# ============================================================

STATUS_YANGI = "yangi"                # AI aniqladi, aholi tasdig'i kutilmoqda
STATUS_TASDIQLANGAN = "tasdiqlangan"  # Tasdiqlandi, mas'ulga yuborildi
STATUS_JARAYONDA = "jarayonda"        # Mas'ul ish boshladi
STATUS_HAL_QILINDI = "hal_qilindi"    # Mas'ul hal qildi, xalq tekshiruvi ketmoqda
STATUS_YOPILDI = "yopildi"            # Aholi tasdiqladi — yakuniy
STATUS_RAD_ETILDI = "rad_etildi"      # Asossiz deb topildi

STATUS_LABELS = {
    STATUS_YANGI: "🆕 Yangi",
    STATUS_TASDIQLANGAN: "📨 Mas'ulga yuborildi",
    STATUS_JARAYONDA: "⏳ Jarayonda",
    STATUS_HAL_QILINDI: "✅ Hal qilindi (tekshiruvda)",
    STATUS_YOPILDI: "✔️ Yopildi",
    STATUS_RAD_ETILDI: "❌ Asossiz",
}

OPEN_STATUSES = [STATUS_YANGI, STATUS_TASDIQLANGAN, STATUS_JARAYONDA, STATUS_HAL_QILINDI]
CLOSED_STATUSES = [STATUS_YOPILDI, STATUS_RAD_ETILDI]


def category_info(key: str) -> dict:
    """Kategoriya ma'lumotini xavfsiz olish."""
    return CATEGORIES.get(key, CATEGORIES["boshqa"])


def responsible_role(category_key: str) -> str:
    """Kategoriya uchun mas'ul maqomni qaytaradi."""
    return category_info(category_key)["role"]
