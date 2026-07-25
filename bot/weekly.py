"""Haftalik AI tahliliy hisobot.

Har yakshanba soat 19:00 (Toshkent) da har bir mahalla uchun:
  - guruhga qisqa ommaviy hisobot
  - raisga batafsil shaxsiy hisobot
"""
import asyncio
import logging
from datetime import timedelta

from aiogram import Bot

import ai
import config
from database import (
    Issue, Mahalla, MessageLog, SessionLocal, User,
    get_setting, now_tk, set_setting,
)
from roles import (
    CATEGORIES, MSG_TYPES, OPEN_STATUSES, ROLE_RAIS,
    STATUS_YOPILDI, STATUS_HAL_QILINDI,
)

log = logging.getLogger("weekly")


def build_stats_text(db, mahalla: Mahalla) -> tuple[str, dict]:
    """Bir haftalik xom statistika matni (AI uchun) va raqamlar."""
    week_ago = now_tk() - timedelta(days=7)

    logs = (db.query(MessageLog)
            .filter(MessageLog.mahalla_id == mahalla.id,
                    MessageLog.created_at >= week_ago).all())
    issues = (db.query(Issue)
              .filter(Issue.mahalla_id == mahalla.id,
                      Issue.created_at >= week_ago).all())
    resolved = [i for i in issues
                if i.status in (STATUS_YOPILDI, STATUS_HAL_QILINDI)]
    still_open = (db.query(Issue)
                  .filter(Issue.mahalla_id == mahalla.id,
                          Issue.status.in_(OPEN_STATUSES)).all())

    type_counts = {}
    for l in logs:
        type_counts[l.msg_type] = type_counts.get(l.msg_type, 0) + 1
    cat_counts = {}
    for i in issues:
        cat_counts[i.category] = cat_counts.get(i.category, 0) + 1

    lines = [f"Mahalla: {mahalla.name}", "Davr: oxirgi 7 kun", ""]
    lines.append("Xabar turlari statistikasi:")
    for t, c in sorted(type_counts.items(), key=lambda x: -x[1]):
        lines.append(f"  {MSG_TYPES.get(t, t)}: {c} ta")
    lines.append("")
    lines.append(f"Yangi muammolar: {len(issues)} ta; shundan hal qilingan: {len(resolved)} ta")
    lines.append(f"Hozir ochiq turgan (barcha davrlardan): {len(still_open)} ta")
    lines.append("")
    lines.append("Muammolar kategoriyalar kesimida:")
    for k, c in sorted(cat_counts.items(), key=lambda x: -x[1]):
        lines.append(f"  {CATEGORIES.get(k, {}).get('label', k)}: {c} ta")
    lines.append("")
    lines.append("Ochiq muammolar bayonlari:")
    for i in still_open[:15]:
        lines.append(f"  - [{CATEGORIES.get(i.category, {}).get('label', i.category)}] {i.summary}")
    lines.append("")
    lines.append("Shu hafta hal qilinganlar:")
    for i in resolved[:10]:
        lines.append(f"  - {i.summary}")

    numbers = {
        "new": len(issues), "resolved": len(resolved),
        "open": len(still_open),
        "reklama": type_counts.get("reklama", 0),
        "spam": type_counts.get("spam", 0),
    }
    return "\n".join(lines), numbers


async def send_weekly_reports(bot: Bot):
    """Barcha faol mahallalar bo'yicha hisobot tarqatish."""
    with SessionLocal() as db:
        mahallas = db.query(Mahalla).filter(Mahalla.is_active == True).all()  # noqa: E712
        for m in mahallas:
            try:
                stats_text, nums = build_stats_text(db, m)
                report = await ai.weekly_report(stats_text)
                if not report:
                    report = (
                        f"📊 Haftalik hisobot — {m.name}\n"
                        f"Yangi muammolar: {nums['new']} ta\n"
                        f"Hal qilingan: {nums['resolved']} ta\n"
                        f"Ochiq: {nums['open']} ta"
                    )

                # 1) Guruhga qisqa ommaviy xulosa
                if m.chat_id:
                    public = (
                        f"📊 <b>{m.name} — haftalik hisobot</b>\n\n"
                        f"🆕 Yangi muammolar: <b>{nums['new']}</b> ta\n"
                        f"✔️ Hal qilingan: <b>{nums['resolved']}</b> ta\n"
                        f"⏳ Ochiq: <b>{nums['open']}</b> ta\n\n"
                        "Faolligingiz uchun rahmat! Muammolarni ko'rsangiz — "
                        "yozing, men mas'ullarga yetkazaman. 🤝"
                    )
                    try:
                        await bot.send_message(m.chat_id, public)
                    except Exception as e:
                        log.warning("Guruhga yuborilmadi %s: %s", m.name, e)

                # 2) Raisga batafsil AI tahlili
                raislar = (db.query(User)
                           .filter(User.mahalla_id == m.id, User.role == ROLE_RAIS,
                                   User.tg_id.isnot(None), User.is_active == True)  # noqa: E712
                           .all())
                for r in raislar:
                    try:
                        await bot.send_message(
                            r.tg_id,
                            f"📊 <b>Haftalik tahliliy hisobot</b>\n"
                            f"🏘 {m.name}\n\n{report}\n\n"
                            f"📎 Reklama xabarlari: {nums['reklama']} ta, "
                            f"spam: {nums['spam']} ta.\n"
                            f"Batafsil — web-panelning «Hisobotlar» bo'limida.",
                        )
                    except Exception as e:
                        log.warning("Raisga yuborilmadi: %s", e)
            except Exception as e:
                log.error("Hisobot xatosi (%s): %s", m.name, e)


async def weekly_scheduler(bot: Bot):
    """Fon vazifasi: har 20 daqiqada vaqtni tekshiradi.

    Yakshanba, belgilangan soatdan keyin, shu hafta uchun hali yuborilmagan
    bo'lsa — hisobotlarni tarqatadi. (Tashqi scheduler kutubxonasisiz —
    Render qayta ishga tushirilganda ham dublikat yubormaydi.)
    """
    while True:
        try:
            now = now_tk()
            week_key = now.strftime("%G-W%V")  # ISO hafta: 2026-W30
            if (now.weekday() == config.WEEKLY_REPORT_WEEKDAY
                    and now.hour >= config.WEEKLY_REPORT_HOUR):
                with SessionLocal() as db:
                    last = get_setting(db, "last_weekly_report", "")
                if last != week_key:
                    log.info("Haftalik hisobot boshlandi: %s", week_key)
                    await send_weekly_reports(bot)
                    with SessionLocal() as db:
                        set_setting(db, "last_weekly_report", week_key)
        except Exception as e:
            log.error("Scheduler xatosi: %s", e)
        await asyncio.sleep(1200)  # 20 daqiqa
