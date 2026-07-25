"""Telegram bot handlerlari.

Oqim:
  1. Guruh xabari -> oldindan filtr -> Gemini tahlil -> MessageLog
  2. "muammo" bo'lsa -> Issue (yangi) -> guruhda tasdiqlash tugmasi
  3. N ta tasdiq (yoki favqulodda) -> mas'ullarga shaxsiy topshiriq
  4. Mas'ul tugmalari: Qabul qildim / Hal qilindi / Asossiz
  5. "Hal qilindi" -> guruhda xalq tekshiruvi (👍/👎)
  6. 👎 ko'p bo'lsa -> muammo qayta ochiladi
"""
import logging

from aiogram import Bot, F, Router
from aiogram.filters import Command, CommandStart
from aiogram.types import (
    CallbackQuery, ChatMemberUpdated, InlineKeyboardButton,
    InlineKeyboardMarkup, Message,
)

import ai
import config
from database import (
    Issue, Mahalla, MessageLog, SessionLocal, User, Vote,
    add_history, now_tk,
)
from roles import (
    CATEGORIES, GLOBAL_ROLES, ROLE_LABELS, ROLE_RAIS, SEVERITY,
    STATUS_HAL_QILINDI, STATUS_JARAYONDA, STATUS_LABELS, STATUS_RAD_ETILDI,
    STATUS_TASDIQLANGAN, STATUS_YANGI, STATUS_YOPILDI,
    OPEN_STATUSES, category_info, responsible_role,
)

log = logging.getLogger("bot")
router = Router()


# ============================================================
# YORDAMCHI FUNKSIYALAR
# ============================================================

def issue_card(issue: Issue, with_text: bool = False) -> str:
    """Muammo kartochkasi matni (HTML)."""
    cat = category_info(issue.category)
    sev = SEVERITY.get(issue.severity, SEVERITY["orta"])
    lines = [
        f"{cat['emoji']} <b>Muammo #{issue.id}</b> — {cat['label']}",
        f"Jiddiylik: {sev['emoji']} {sev['label']}",
        f"📝 {issue.summary or 'Bayon yo`q'}",
    ]
    if issue.location_hint:
        lines.append(f"📍 Manzil: {issue.location_hint}")
    lines.append(f"Holat: {STATUS_LABELS.get(issue.status, issue.status)}")
    if with_text and issue.original_text:
        lines.append(f"\n💬 <i>Asl xabar:</i> {issue.original_text[:400]}")
    return "\n".join(lines)


def official_kb(issue_id: int) -> InlineKeyboardMarkup:
    """Mas'ul uchun boshqaruv tugmalari."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⏳ Qabul qildim, jarayonda",
                              callback_data=f"st:{issue_id}:{STATUS_JARAYONDA}")],
        [InlineKeyboardButton(text="✅ Hal qilindi",
                              callback_data=f"st:{issue_id}:{STATUS_HAL_QILINDI}")],
        [InlineKeyboardButton(text="❌ Asossiz murojaat",
                              callback_data=f"st:{issue_id}:{STATUS_RAD_ETILDI}")],
    ])


async def safe_send(bot: Bot, chat_id, text: str, **kwargs):
    """Xabar yuborish — xato bo'lsa bot yiqilmaydi (masalan, mas'ul botni bloklagan)."""
    try:
        return await bot.send_message(chat_id, text, **kwargs)
    except Exception as e:
        log.warning("Yuborilmadi chat_id=%s: %s", chat_id, e)
        return None


def find_officials(db, mahalla_id: int, role: str) -> list[User]:
    """Mahallada berilgan maqomdagi, Telegramga ulangan faol mas'ullar."""
    return (
        db.query(User)
        .filter(User.mahalla_id == mahalla_id, User.role == role,
                User.is_active == True, User.tg_id.isnot(None))  # noqa: E712
        .all()
    )


async def activate_issue(bot: Bot, db, issue: Issue):
    """Muammo tasdiqlandi: mas'ullarga topshiriq yuborish."""
    issue.status = STATUS_TASDIQLANGAN
    role = responsible_role(issue.category)
    issue.assigned_role = role

    officials = find_officials(db, issue.mahalla_id, role)
    raislar = find_officials(db, issue.mahalla_id, ROLE_RAIS)

    # Fallback: soha mas'uli yo'q bo'lsa — rais mas'ul bo'ladi
    if not officials:
        officials = raislar
        issue.assigned_role = ROLE_RAIS if raislar else role

    if officials:
        issue.assigned_user_id = officials[0].id

    add_history(db, issue.id,
                f"Tasdiqlandi. Mas'ul maqom: {ROLE_LABELS.get(issue.assigned_role, issue.assigned_role)}")
    db.commit()

    text = ("📬 <b>Sizga yangi topshiriq!</b>\n\n" + issue_card(issue, with_text=True)
            + "\n\n👇 Holatni tugmalar orqali yangilang. "
              "Batafsil: web-panelning «Muammolar» bo'limida.")

    notified = set()
    for u in officials:
        if u.tg_id and u.tg_id not in notified:
            await safe_send(bot, u.tg_id, text, reply_markup=official_kb(issue.id))
            notified.add(u.tg_id)
    # Rais har doim xabardor (agar o'zi mas'ul bo'lmasa — nusxa oladi)
    for r in raislar:
        if r.tg_id and r.tg_id not in notified:
            await safe_send(
                bot, r.tg_id,
                "ℹ️ <b>Mahallangizda yangi muammo ro'yxatga olindi</b>\n\n"
                + issue_card(issue),
            )
            notified.add(r.tg_id)

    # Guruhdagi tasdiqlash xabarini yangilash
    if issue.mahalla.chat_id and issue.bot_message_id:
        try:
            await bot.edit_message_text(
                chat_id=issue.mahalla.chat_id,
                message_id=issue.bot_message_id,
                text=(f"{category_info(issue.category)['emoji']} <b>Muammo #{issue.id} "
                      f"ro'yxatga olindi</b> va mas'ulga yuborildi.\n"
                      f"📝 {issue.summary}\n"
                      f"Holat: {STATUS_LABELS[STATUS_TASDIQLANGAN]}"),
            )
        except Exception:
            pass


# ============================================================
# GURUH XABARLARINI TAHLIL QILISH (asosiy oqim)
# ============================================================

@router.message(F.chat.type.in_({"group", "supergroup"}), F.text, ~F.text.startswith("/"))
async def on_group_message(message: Message, bot: Bot):
    text = (message.text or "").strip()
    if not text or message.from_user.is_bot:
        return

    with SessionLocal() as db:
        mahalla = (db.query(Mahalla)
                   .filter(Mahalla.chat_id == str(message.chat.id),
                           Mahalla.is_active == True)  # noqa: E712
                   .first())
        if not mahalla:
            return  # Ro'yxatdan o'tmagan guruh — jim turamiz

        if not ai.needs_ai(text):
            return  # Arzon filtr: oddiy qisqa gap

        result = await ai.classify_message(text)
        if not result:
            return

        # Statistika jurnali (haftalik hisobot uchun) — har doim yoziladi
        db.add(MessageLog(
            mahalla_id=mahalla.id,
            msg_type=result["turi"],
            category=result["kategoriya"] if result["turi"] == "muammo" else "",
            summary=result["qisqacha"][:290],
            confidence=result["ishonch"],
        ))
        db.commit()

        # Faqat ishonchli MUAMMO topshiriqqa aylanadi.
        # Reklama, spam, e'lon, oddiy suhbat — faqat statistikada qoladi.
        if result["turi"] != "muammo" or result["ishonch"] < config.MIN_CONFIDENCE:
            return

        # Deduplikatsiya: shu mahallada, shu kategoriyada ochiq muammo bormi?
        dup = (db.query(Issue)
               .filter(Issue.mahalla_id == mahalla.id,
                       Issue.category == result["kategoriya"],
                       Issue.status.in_([STATUS_YANGI, STATUS_TASDIQLANGAN, STATUS_JARAYONDA]))
               .order_by(Issue.created_at.desc())
               .first())
        if dup:
            # Yangi muammo ochmaymiz — mavjudiga "ovoz" sifatida qo'shamiz
            already = (db.query(Vote)
                       .filter(Vote.issue_id == dup.id,
                               Vote.tg_user_id == str(message.from_user.id),
                               Vote.kind == "confirm").first())
            if not already:
                db.add(Vote(issue_id=dup.id, tg_user_id=str(message.from_user.id), kind="confirm"))
                dup.confirm_count += 1
                add_history(db, dup.id, "Yana bir fuqaro shu muammoni ko'tardi (avto-birlashtirildi)")
                db.commit()
                if dup.status == STATUS_YANGI and dup.confirm_count >= config.CONFIRM_THRESHOLD:
                    await activate_issue(bot, db, dup)
            return

        # Yangi muammo yaratish
        issue = Issue(
            mahalla_id=mahalla.id,
            category=result["kategoriya"],
            severity=result["jiddiylik"],
            summary=result["qisqacha"],
            original_text=text[:1500],
            location_hint=result["manzil"],
            author_tg_id=str(message.from_user.id),
            group_message_id=message.message_id,
            status=STATUS_YANGI,
        )
        db.add(issue)
        db.commit()
        add_history(db, issue.id, "AI tomonidan aniqlandi")
        db.commit()

        cat = category_info(issue.category)

        # FAVQULODDA holat — tasdiq kutmasdan darhol mas'ullarga
        if issue.severity == "favqulodda":
            m = await safe_send(
                bot, message.chat.id,
                f"🔴 <b>FAVQULODDA HOLAT ANIQLANDI!</b>\n"
                f"{cat['emoji']} {issue.summary}\n"
                f"Mas'ullarga zudlik bilan xabar yuborildi. Muammo #{issue.id}",
                reply_to_message_id=message.message_id,
            )
            if m:
                issue.bot_message_id = m.message_id
                db.commit()
            await activate_issue(bot, db, issue)
            return

        # Oddiy holat — guruhda tasdiqlash so'raladi (yolg'on signalga qarshi)
        kb = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(
                text=f"👍 Tasdiqlayman (0/{config.CONFIRM_THRESHOLD})",
                callback_data=f"cf:{issue.id}",
            )
        ]])
        m = await safe_send(
            bot, message.chat.id,
            f"{cat['emoji']} <b>Muammo aniqladim:</b> {issue.summary}\n\n"
            f"Bu haqiqiy muammo bo'lsa, {config.CONFIRM_THRESHOLD} kishi tasdiqlashi bilan "
            f"mas'ullarga rasmiy topshiriq yuboraman. (#{issue.id})",
            reply_to_message_id=message.message_id,
            reply_markup=kb,
        )
        if m:
            issue.bot_message_id = m.message_id
            db.commit()


# ============================================================
# TASDIQLASH (aholi 👍 bosadi)
# ============================================================

@router.callback_query(F.data.startswith("cf:"))
async def on_confirm(cb: CallbackQuery, bot: Bot):
    issue_id = int(cb.data.split(":")[1])
    with SessionLocal() as db:
        issue = db.get(Issue, issue_id)
        if not issue or issue.status != STATUS_YANGI:
            await cb.answer("Bu muammo allaqachon ko'rib chiqilgan.", show_alert=False)
            return
        uid = str(cb.from_user.id)
        exists = (db.query(Vote)
                  .filter(Vote.issue_id == issue_id, Vote.tg_user_id == uid,
                          Vote.kind == "confirm").first())
        if exists:
            await cb.answer("Siz allaqachon tasdiqlagansiz 👍")
            return
        db.add(Vote(issue_id=issue_id, tg_user_id=uid, kind="confirm"))
        issue.confirm_count += 1
        db.commit()

        if issue.confirm_count >= config.CONFIRM_THRESHOLD:
            await cb.answer("Tasdiqlandi! Mas'ullarga yuborilmoqda ✅")
            await activate_issue(bot, db, issue)
        else:
            await cb.answer("Ovozingiz qabul qilindi 👍")
            try:
                kb = InlineKeyboardMarkup(inline_keyboard=[[
                    InlineKeyboardButton(
                        text=f"👍 Tasdiqlayman ({issue.confirm_count}/{config.CONFIRM_THRESHOLD})",
                        callback_data=f"cf:{issue.id}",
                    )
                ]])
                await cb.message.edit_reply_markup(reply_markup=kb)
            except Exception:
                pass


# ============================================================
# MAS'UL STATUS O'ZGARTIRADI (shaxsiy chatdagi tugmalar)
# ============================================================

@router.callback_query(F.data.startswith("st:"))
async def on_status_change(cb: CallbackQuery, bot: Bot):
    _, issue_id, new_status = cb.data.split(":")
    issue_id = int(issue_id)

    with SessionLocal() as db:
        issue = db.get(Issue, issue_id)
        if not issue:
            await cb.answer("Muammo topilmadi.", show_alert=True)
            return

        user = (db.query(User)
                .filter(User.tg_id == str(cb.from_user.id), User.is_active == True)  # noqa: E712
                .first())
        if not user:
            await cb.answer("Siz tizimga ulanmagansiz. /ulanish KOD yuboring.", show_alert=True)
            return

        # Huquq tekshiruvi: global maqom, o'z mahalla raisi yoki tayinlangan maqom
        allowed = (
            user.role in GLOBAL_ROLES
            or (user.mahalla_id == issue.mahalla_id
                and user.role in (ROLE_RAIS, issue.assigned_role))
        )
        if not allowed:
            await cb.answer("Bu muammo sizning vakolatingizda emas.", show_alert=True)
            return

        if issue.status in (STATUS_YOPILDI, STATUS_RAD_ETILDI):
            await cb.answer("Muammo allaqachon yakunlangan.", show_alert=True)
            return

        issue.status = new_status
        issue.assigned_user_id = user.id
        actor = f"{user.full_name} ({ROLE_LABELS.get(user.role, user.role)})"

        if new_status == STATUS_JARAYONDA:
            add_history(db, issue.id, "Mas'ul ishni qabul qildi", actor)
            db.commit()
            await cb.answer("Qabul qilindi. Omad! ⏳")
            if issue.mahalla.chat_id:
                await safe_send(
                    bot, issue.mahalla.chat_id,
                    f"⏳ <b>Muammo #{issue.id}</b> bo'yicha mas'ul ishni boshladi.\n"
                    f"📝 {issue.summary}",
                )

        elif new_status == STATUS_RAD_ETILDI:
            add_history(db, issue.id, "Asossiz deb topildi", actor)
            issue.resolved_at = now_tk()
            db.commit()
            await cb.answer("Asossiz deb belgilandi ❌")
            if issue.mahalla.chat_id:
                await safe_send(
                    bot, issue.mahalla.chat_id,
                    f"❌ <b>Muammo #{issue.id}</b> mas'ul tomonidan asossiz deb topildi.\n"
                    f"📝 {issue.summary}\n"
                    f"<i>Rozimasligingiz bo'lsa, raisga murojaat qiling.</i>",
                )

        elif new_status == STATUS_HAL_QILINDI:
            add_history(db, issue.id, "Mas'ul 'hal qilindi' deb belgiladi", actor)
            issue.resolved_at = now_tk()
            db.commit()
            await cb.answer("Ajoyib! Endi aholi tasdig'i so'raladi ✅")
            # XALQ TEKSHIRUVI — ishonch mexanizmi
            if issue.mahalla.chat_id:
                kb = InlineKeyboardMarkup(inline_keyboard=[[
                    InlineKeyboardButton(text="👍 Ha, hal bo'ldi",
                                         callback_data=f"vf:{issue.id}:ok"),
                    InlineKeyboardButton(text="👎 Yo'q, hal bo'lmadi",
                                         callback_data=f"vf:{issue.id}:no"),
                ]])
                m = await safe_send(
                    bot, issue.mahalla.chat_id,
                    f"✅ <b>Muammo #{issue.id} hal qilindi deb belgilandi.</b>\n"
                    f"📝 {issue.summary}\n\n"
                    f"Hurmatli aholi, rostdan hal bo'ldimi? Fikringiz muhim! 👇",
                    reply_markup=kb,
                )
                if m:
                    issue.verify_message_id = m.message_id
                    db.commit()

        # Mas'ulning shaxsiy xabaridagi tugmalarni yangilash
        try:
            await cb.message.edit_text(
                issue_card(issue, with_text=True),
                reply_markup=None if new_status != STATUS_JARAYONDA else official_kb(issue.id),
            )
        except Exception:
            pass


# ============================================================
# XALQ TEKSHIRUVI (hal bo'ldimi? 👍/👎)
# ============================================================

@router.callback_query(F.data.startswith("vf:"))
async def on_verify(cb: CallbackQuery, bot: Bot):
    _, issue_id, vote = cb.data.split(":")
    issue_id = int(issue_id)
    kind = "verify_ok" if vote == "ok" else "verify_no"

    with SessionLocal() as db:
        issue = db.get(Issue, issue_id)
        if not issue or issue.status != STATUS_HAL_QILINDI:
            await cb.answer("Ovoz berish yakunlangan.")
            return
        uid = str(cb.from_user.id)
        exists = (db.query(Vote)
                  .filter(Vote.issue_id == issue_id, Vote.tg_user_id == uid,
                          Vote.kind.in_(["verify_ok", "verify_no"])).first())
        if exists:
            await cb.answer("Siz allaqachon ovoz bergansiz.")
            return
        db.add(Vote(issue_id=issue_id, tg_user_id=uid, kind=kind))
        db.commit()

        ok = db.query(Vote).filter(Vote.issue_id == issue_id, Vote.kind == "verify_ok").count()
        no = db.query(Vote).filter(Vote.issue_id == issue_id, Vote.kind == "verify_no").count()

        if no >= config.VERIFY_THRESHOLD:
            # Aholi rad etdi — muammo QAYTA OCHILADI va eskalatsiya
            issue.status = STATUS_TASDIQLANGAN
            issue.reopen_count += 1
            issue.resolved_at = None
            add_history(db, issue.id, f"Aholi rad etdi ({no} ovoz) — muammo qayta ochildi")
            db.commit()
            await cb.answer("Ovozingiz qabul qilindi.")
            if issue.mahalla.chat_id and issue.verify_message_id:
                try:
                    await bot.edit_message_text(
                        chat_id=issue.mahalla.chat_id,
                        message_id=issue.verify_message_id,
                        text=(f"🔁 <b>Muammo #{issue.id} aholi fikriga ko'ra hal bo'lmagan.</b>\n"
                              f"📝 {issue.summary}\n"
                              f"Mas'ulga qayta yuborildi. Nazorat davom etadi."),
                    )
                except Exception:
                    pass
            # Mas'ul va raisga qayta xabar
            for u in find_officials(db, issue.mahalla_id, issue.assigned_role) + \
                     find_officials(db, issue.mahalla_id, ROLE_RAIS):
                if u.tg_id:
                    await safe_send(
                        bot, u.tg_id,
                        f"⚠️ <b>Diqqat!</b> Muammo #{issue.id} aholi tomonidan "
                        f"<b>hal bo'lmagan</b> deb baholandi va qayta ochildi.\n\n"
                        + issue_card(issue),
                        reply_markup=official_kb(issue.id),
                    )
        elif ok >= config.VERIFY_THRESHOLD:
            issue.status = STATUS_YOPILDI
            add_history(db, issue.id, f"Aholi tasdiqladi ({ok} ovoz) — muammo yopildi")
            db.commit()
            await cb.answer("Rahmat! Muammo yopildi ✔️")
            if issue.mahalla.chat_id and issue.verify_message_id:
                try:
                    await bot.edit_message_text(
                        chat_id=issue.mahalla.chat_id,
                        message_id=issue.verify_message_id,
                        text=(f"✔️ <b>Muammo #{issue.id} to'liq hal qilindi!</b>\n"
                              f"📝 {issue.summary}\n"
                              f"Barcha ishtirokchilarga rahmat! 🙌"),
                    )
                except Exception:
                    pass
        else:
            await cb.answer("Ovozingiz qabul qilindi 🙏")


# ============================================================
# SHAXSIY CHAT BUYRUQLARI
# ============================================================

@router.message(CommandStart(), F.chat.type == "private")
async def cmd_start(message: Message):
    with SessionLocal() as db:
        user = db.query(User).filter(User.tg_id == str(message.from_user.id)).first()
    if user:
        await message.answer(
            f"Assalomu alaykum, <b>{user.full_name}</b>!\n"
            f"Maqomingiz: <b>{ROLE_LABELS.get(user.role, user.role)}</b>\n\n"
            "Buyruqlar:\n"
            "/muammolar — sizga tegishli ochiq muammolar\n"
            "/hisobot — mahalla bo'yicha qisqa statistika\n"
            "/yordam — qo'llanma"
        )
    else:
        await message.answer(
            "Assalomu alaykum! Men <b>Mahalla AI</b> yordamchisiman. 🏘\n\n"
            "🔹 <b>Mas'ul shaxs bo'lsangiz:</b> panel administratoridan olgan kodingizni "
            "quyidagicha yuboring:\n<code>/ulanish KOD</code>\n\n"
            "🔹 <b>Aholi bo'lsangiz:</b> muammo yoki murojaatingizni shu yerga yozishingiz "
            "mumkin — u <b>anonim</b> tarzda mahalla raisiga yetkaziladi. Buning uchun "
            "avval mahalla guruhida faol bo'ling yoki murojaatda mahallangiz nomini yozing."
        )


@router.message(Command("yordam"), F.chat.type == "private")
async def cmd_help(message: Message):
    await message.answer(
        "<b>Qo'llanma</b>\n\n"
        "👥 <b>Guruhda:</b> men suhbatni kuzatib, muammolarni aniqlayman. "
        "Muammo topsam, tasdiqlash tugmasini chiqaraman — 👍 bosing.\n\n"
        "👤 <b>Mas'ullar uchun:</b>\n"
        "/ulanish KOD — hisobingizni bog'lash\n"
        "/muammolar — ochiq topshiriqlaringiz\n"
        "/hisobot — statistika\n\n"
        "🌐 To'liq boshqaruv web-panelda amalga oshiriladi."
    )


@router.message(Command("ulanish"), F.chat.type == "private")
async def cmd_link(message: Message):
    parts = (message.text or "").split(maxsplit=1)
    if len(parts) < 2:
        await message.answer("Kod yuboring: <code>/ulanish KOD</code>")
        return
    code = parts[1].strip().upper()
    with SessionLocal() as db:
        user = db.query(User).filter(User.link_code == code, User.is_active == True).first()  # noqa: E712
        if not user:
            await message.answer("❌ Kod noto'g'ri yoki eskirgan. Administratordan yangi kod so'rang.")
            return
        # Bitta Telegram akkaunt bitta hisobga
        taken = db.query(User).filter(User.tg_id == str(message.from_user.id)).first()
        if taken and taken.id != user.id:
            await message.answer("❌ Bu Telegram akkaunt boshqa hisobga ulangan.")
            return
        user.tg_id = str(message.from_user.id)
        user.link_code = None  # kod bir martalik
        db.commit()
        await message.answer(
            f"✅ Muvaffaqiyatli ulandingiz!\n"
            f"👤 {user.full_name}\n"
            f"🎖 Maqom: <b>{ROLE_LABELS.get(user.role, user.role)}</b>\n\n"
            f"Endi sizga tegishli muammolar shu yerga keladi. /muammolar buyrug'ini sinab ko'ring."
        )


@router.message(Command("muammolar"), F.chat.type == "private")
async def cmd_issues(message: Message):
    with SessionLocal() as db:
        user = (db.query(User)
                .filter(User.tg_id == str(message.from_user.id), User.is_active == True)  # noqa: E712
                .first())
        if not user:
            await message.answer("Avval ulaning: <code>/ulanish KOD</code>")
            return

        q = db.query(Issue).filter(Issue.status.in_(OPEN_STATUSES))
        if user.role in GLOBAL_ROLES:
            pass  # hammasi
        elif user.role == ROLE_RAIS:
            q = q.filter(Issue.mahalla_id == user.mahalla_id)
        else:
            q = q.filter(Issue.mahalla_id == user.mahalla_id,
                         Issue.assigned_role == user.role)
        issues = q.order_by(Issue.created_at.desc()).limit(10).all()

        if not issues:
            await message.answer("🎉 Ochiq muammolar yo'q. Barakalla!")
            return
        await message.answer(f"📋 Ochiq muammolar: <b>{len(issues)}</b> ta (oxirgi 10 tasi)")
        for issue in issues:
            await message.answer(issue_card(issue), reply_markup=official_kb(issue.id))


@router.message(Command("hisobot"), F.chat.type == "private")
async def cmd_stats(message: Message):
    with SessionLocal() as db:
        user = (db.query(User)
                .filter(User.tg_id == str(message.from_user.id), User.is_active == True)  # noqa: E712
                .first())
        if not user:
            await message.answer("Avval ulaning: <code>/ulanish KOD</code>")
            return
        q = db.query(Issue)
        if user.role not in GLOBAL_ROLES:
            q = q.filter(Issue.mahalla_id == user.mahalla_id)
        total = q.count()
        yopildi = q.filter(Issue.status == STATUS_YOPILDI).count()
        ochiq = q.filter(Issue.status.in_(OPEN_STATUSES)).count()
        lines = [
            "📊 <b>Qisqa statistika</b>",
            f"Jami muammolar: {total}",
            f"Hal qilingan: {yopildi} ✔️",
            f"Ochiq: {ochiq} ⏳",
            "",
            "Kategoriyalar bo'yicha ochiq:",
        ]
        for key, info in CATEGORIES.items():
            c = q.filter(Issue.category == key, Issue.status.in_(OPEN_STATUSES)).count()
            if c:
                lines.append(f"{info['emoji']} {info['label']}: {c}")
        await message.answer("\n".join(lines))


@router.message(Command("chatid"))
async def cmd_chatid(message: Message):
    """Guruh ID sini olish — panelda mahallani bog'lash uchun kerak."""
    await message.answer(
        f"🆔 Ushbu chat ID: <code>{message.chat.id}</code>\n"
        "Web-panel → Mahallalar bo'limida shu ID ni kiriting."
    )


# ============================================================
# AHOLIDAN SHAXSIY (ANONIM) MUROJAAT
# ============================================================

@router.message(F.chat.type == "private", F.text, ~F.text.startswith("/"))
async def private_appeal(message: Message, bot: Bot):
    """Ulanmagan foydalanuvchi shaxsiy yozsa — anonim murojaat sifatida qabul qilinadi."""
    with SessionLocal() as db:
        user = db.query(User).filter(User.tg_id == str(message.from_user.id)).first()
        if user:
            await message.answer(
                "Buyruqlardan foydalaning: /muammolar, /hisobot, /yordam.\n"
                "To'liq boshqaruv — web-panelda."
            )
            return

        text = message.text.strip()
        if len(text) < 15:
            await message.answer(
                "Murojaatingizni batafsilroq yozing (kamida 15 belgi). "
                "Qaysi mahalla, qaysi ko'cha va muammo nimadaligini ko'rsating."
            )
            return

        result = await ai.classify_message(text)
        if not result or result["turi"] in ("spam", "oddiy_suhbat"):
            await message.answer(
                "Murojaatingiz mazmunini aniqlay olmadim. Iltimos, muammoni aniq yozing: "
                "qaysi mahalla, qaysi manzil va nima muammo."
            )
            return

        # Mahallani aniqlash: matnda mahalla nomi bormi?
        mahallas = db.query(Mahalla).filter(Mahalla.is_active == True).all()  # noqa: E712
        target = None
        low = text.lower()
        for m in mahallas:
            if m.name and m.name.lower() in low:
                target = m
                break
        if not target:
            if len(mahallas) == 1:
                target = mahallas[0]
            else:
                names = "\n".join(f"• {m.name}" for m in mahallas[:30]) or "— hali yo'q —"
                await message.answer(
                    "Qaysi mahallaga tegishli ekanini aniqlay olmadim. "
                    "Murojaat matnida mahalla nomini yozing.\n\n"
                    f"Ro'yxatdagi mahallalar:\n{names}"
                )
                return

        issue = Issue(
            mahalla_id=target.id,
            category=result["kategoriya"],
            severity=result["jiddiylik"],
            summary=result["qisqacha"],
            original_text=text[:1500] + "\n\n[Manba: shaxsiy/anonim murojaat]",
            location_hint=result["manzil"],
            author_tg_id=str(message.from_user.id),
            status=STATUS_YANGI,
            confirm_count=config.CONFIRM_THRESHOLD,  # shaxsiy murojaat tasdiq talab qilmaydi
        )
        db.add(issue)
        db.commit()
        add_history(db, issue.id, "Anonim shaxsiy murojaat orqali kelib tushdi")
        db.commit()
        await activate_issue(bot, db, issue)
        await message.answer(
            f"✅ Murojaatingiz qabul qilindi va <b>anonim</b> tarzda mas'ullarga yuborildi.\n"
            f"Raqami: <b>#{issue.id}</b>. Holatini bilish uchun keyinroq shu raqamni yozing."
        )


# ============================================================
# BOT GURUHGA QO'SHILGANDA
# ============================================================

@router.my_chat_member()
async def on_bot_added(event: ChatMemberUpdated, bot: Bot):
    if event.chat.type not in ("group", "supergroup"):
        return
    new = event.new_chat_member
    if new.status in ("member", "administrator"):
        await safe_send(
            bot, event.chat.id,
            "Assalomu alaykum! Men <b>Mahalla AI</b> yordamchisiman. 🏘\n\n"
            "Men bu guruhda aholi ko'targan muammolarni aniqlab, mas'ullarga "
            "yetkazaman va hal bo'lishini nazorat qilaman.\n\n"
            "⚠️ <b>Ma'lumot:</b> guruhdagi ochiq xabarlar muammolarni aniqlash maqsadida "
            "avtomatik tahlil qilinadi. Hisobotlarda ismlar ko'rsatilmaydi.\n\n"
            f"🆔 Guruh ID: <code>{event.chat.id}</code> — administrator ushbu ID ni "
            "web-panelda mahallaga bog'lashi kerak.\n"
            "Guruh ID ni qayta olish: /chatid"
        )
