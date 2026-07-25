"""Web admin panel routelari.

Ko'rinish huquqlari:
  super_admin / hokimiyat_vakili  -> barcha mahallalar, foydalanuvchilar, sozlamalar
  rais                            -> o'z mahallasi: barcha muammolar, hisobot, mas'ullar ro'yxati
  soha mas'ullari (inspektor, elektr, gaz, suv, ...) -> faqat o'z kategoriyasidagi muammolar
"""
from datetime import timedelta

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from pathlib import Path

import config
from database import (
    Issue, IssueHistory, Mahalla, MessageLog, SessionLocal, User,
    add_history, hash_password, new_link_code, now_tk, verify_password,
)
from roles import (
    CATEGORIES, CLOSED_STATUSES, CREATABLE_BY, GLOBAL_ROLES, MSG_TYPES,
    OPEN_STATUSES, ROLE_LABELS, ROLE_RAIS, SECTOR_ROLES, SEVERITY,
    STATUS_HAL_QILINDI, STATUS_JARAYONDA, STATUS_LABELS, STATUS_RAD_ETILDI,
    STATUS_TASDIQLANGAN, STATUS_YOPILDI, responsible_role,
)
from web.auth import (
    SESSION_COOKIE, create_session_token, get_current_user, login_redirect,
)

router = APIRouter()
templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))

# Shablonlarda ishlatiladigan global lug'atlar
templates.env.globals.update(
    ROLE_LABELS=ROLE_LABELS,
    STATUS_LABELS=STATUS_LABELS,
    CATEGORIES=CATEGORIES,
    SEVERITY=SEVERITY,
    MSG_TYPES=MSG_TYPES,
    GLOBAL_ROLES=GLOBAL_ROLES,
    ROLE_RAIS=ROLE_RAIS,
)


def render(request: Request, name: str, user, **ctx):
    return templates.TemplateResponse(
        request, name, {"user": user, **ctx}
    )


def scoped_issues_query(db, user):
    """Foydalanuvchi maqomiga mos muammolar so'rovi."""
    q = db.query(Issue)
    if user.role in GLOBAL_ROLES:
        return q
    if user.role == ROLE_RAIS:
        return q.filter(Issue.mahalla_id == user.mahalla_id)
    # Soha mas'uli: o'z mahallasi + o'z maqomiga tayinlangan
    return q.filter(Issue.mahalla_id == user.mahalla_id,
                    Issue.assigned_role == user.role)


# ============================================================
# LOGIN / LOGOUT
# ============================================================

@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    if get_current_user(request):
        return RedirectResponse("/", status_code=302)
    return render(request, "login.html", None, error=None)


@router.post("/login")
async def login_submit(request: Request, username: str = Form(...), password: str = Form(...)):
    with SessionLocal() as db:
        user = db.query(User).filter(User.username == username.strip()).first()
        if not user or not user.is_active or not verify_password(password, user.password_hash):
            return render(request, "login.html", None,
                          error="Login yoki parol noto'g'ri.")
    resp = RedirectResponse("/", status_code=302)
    resp.set_cookie(SESSION_COOKIE, create_session_token(user.id),
                    max_age=7 * 24 * 3600, httponly=True, samesite="lax")
    return resp


@router.get("/logout")
async def logout():
    resp = RedirectResponse("/login", status_code=302)
    resp.delete_cookie(SESSION_COOKIE)
    return resp


# ============================================================
# BOSH SAHIFA (DASHBOARD)
# ============================================================

@router.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    user = get_current_user(request)
    if not user:
        return login_redirect()

    with SessionLocal() as db:
        q = scoped_issues_query(db, user)
        week_ago = now_tk() - timedelta(days=7)

        stats = {
            "open": q.filter(Issue.status.in_(OPEN_STATUSES)).count(),
            "in_progress": q.filter(Issue.status == STATUS_JARAYONDA).count(),
            "resolved_week": q.filter(Issue.status.in_([STATUS_YOPILDI, STATUS_HAL_QILINDI]),
                                      Issue.updated_at >= week_ago).count(),
            "total": q.count(),
            "urgent": q.filter(Issue.severity == "favqulodda",
                               Issue.status.in_(OPEN_STATUSES)).count(),
        }

        # Kategoriya kesimi (ochiq muammolar) — diagramma uchun
        cat_stats = []
        max_c = 1
        for key, info in CATEGORIES.items():
            c = q.filter(Issue.category == key, Issue.status.in_(OPEN_STATUSES)).count()
            if c:
                cat_stats.append({"key": key, "label": info["label"],
                                  "emoji": info["emoji"], "count": c})
                max_c = max(max_c, c)
        for c in cat_stats:
            c["pct"] = int(c["count"] / max_c * 100)
        cat_stats.sort(key=lambda x: -x["count"])

        recent = (q.order_by(Issue.created_at.desc()).limit(8).all())
        # Mahalla nomlarini oldindan yuklash
        mahalla_names = {m.id: m.name for m in db.query(Mahalla).all()}

        # Haftalik xabar oqimi statistikasi (reklama/spam ni ham ko'rsatish)
        lq = db.query(MessageLog).filter(MessageLog.created_at >= week_ago)
        if user.role not in GLOBAL_ROLES and user.mahalla_id:
            lq = lq.filter(MessageLog.mahalla_id == user.mahalla_id)
        msg_stats = {}
        for row in lq.all():
            msg_stats[row.msg_type] = msg_stats.get(row.msg_type, 0) + 1

    return render(request, "dashboard.html", user,
                  stats=stats, cat_stats=cat_stats, recent=recent,
                  mahalla_names=mahalla_names, msg_stats=msg_stats)


# ============================================================
# MUAMMOLAR
# ============================================================

@router.get("/issues", response_class=HTMLResponse)
async def issues_list(request: Request, status: str = "", category: str = "",
                      mahalla: str = ""):
    user = get_current_user(request)
    if not user:
        return login_redirect()

    with SessionLocal() as db:
        q = scoped_issues_query(db, user)
        if status == "ochiq":
            q = q.filter(Issue.status.in_(OPEN_STATUSES))
        elif status == "yopiq":
            q = q.filter(Issue.status.in_(CLOSED_STATUSES))
        elif status:
            q = q.filter(Issue.status == status)
        if category:
            q = q.filter(Issue.category == category)
        if mahalla and user.role in GLOBAL_ROLES:
            q = q.filter(Issue.mahalla_id == int(mahalla))

        issues = q.order_by(Issue.created_at.desc()).limit(200).all()
        mahalla_names = {m.id: m.name for m in db.query(Mahalla).all()}
        mahallas = db.query(Mahalla).order_by(Mahalla.name).all() \
            if user.role in GLOBAL_ROLES else []

    return render(request, "issues.html", user,
                  issues=issues, mahalla_names=mahalla_names, mahallas=mahallas,
                  f_status=status, f_category=category, f_mahalla=mahalla)


@router.get("/issues/{issue_id}", response_class=HTMLResponse)
async def issue_detail(request: Request, issue_id: int):
    user = get_current_user(request)
    if not user:
        return login_redirect()

    with SessionLocal() as db:
        issue = db.get(Issue, issue_id)
        if not issue:
            return RedirectResponse("/issues", status_code=302)
        # Huquq: ko'rish
        if user.role not in GLOBAL_ROLES:
            if issue.mahalla_id != user.mahalla_id:
                return RedirectResponse("/issues", status_code=302)
            if user.role in SECTOR_ROLES and issue.assigned_role != user.role:
                return RedirectResponse("/issues", status_code=302)

        history = (db.query(IssueHistory)
                   .filter(IssueHistory.issue_id == issue_id)
                   .order_by(IssueHistory.created_at).all())
        mahalla = db.get(Mahalla, issue.mahalla_id)
        assigned = db.get(User, issue.assigned_user_id) if issue.assigned_user_id else None
        # Tayinlash uchun nomzodlar (rais/global uchun)
        candidates = []
        if user.role in GLOBAL_ROLES or user.role == ROLE_RAIS:
            candidates = (db.query(User)
                          .filter(User.mahalla_id == issue.mahalla_id,
                                  User.is_active == True)  # noqa: E712
                          .all())

    can_manage = (user.role in GLOBAL_ROLES
                  or (user.mahalla_id == issue.mahalla_id
                      and user.role in (ROLE_RAIS, issue.assigned_role)))

    return render(request, "issue_detail.html", user,
                  issue=issue, history=history, mahalla=mahalla,
                  assigned=assigned, candidates=candidates, can_manage=can_manage)


@router.post("/issues/{issue_id}/status")
async def issue_set_status(request: Request, issue_id: int,
                           new_status: str = Form(...)):
    user = get_current_user(request)
    if not user:
        return login_redirect()
    valid = {STATUS_TASDIQLANGAN, STATUS_JARAYONDA, STATUS_HAL_QILINDI,
             STATUS_YOPILDI, STATUS_RAD_ETILDI}
    with SessionLocal() as db:
        issue = db.get(Issue, issue_id)
        if issue and new_status in valid:
            allowed = (user.role in GLOBAL_ROLES
                       or (user.mahalla_id == issue.mahalla_id
                           and user.role in (ROLE_RAIS, issue.assigned_role)))
            if allowed:
                issue.status = new_status
                if new_status in (STATUS_YOPILDI, STATUS_HAL_QILINDI, STATUS_RAD_ETILDI):
                    issue.resolved_at = now_tk()
                add_history(db, issue.id,
                            f"Holat panel orqali o'zgartirildi: {STATUS_LABELS.get(new_status)}",
                            f"{user.full_name} ({ROLE_LABELS.get(user.role)})")
                db.commit()
    return RedirectResponse(f"/issues/{issue_id}", status_code=302)


@router.post("/issues/{issue_id}/assign")
async def issue_assign(request: Request, issue_id: int, user_id: int = Form(...)):
    user = get_current_user(request)
    if not user:
        return login_redirect()
    with SessionLocal() as db:
        issue = db.get(Issue, issue_id)
        target = db.get(User, user_id)
        if issue and target and (user.role in GLOBAL_ROLES
                                 or (user.role == ROLE_RAIS
                                     and user.mahalla_id == issue.mahalla_id)):
            issue.assigned_user_id = target.id
            issue.assigned_role = target.role
            if issue.status == "yangi":
                issue.status = STATUS_TASDIQLANGAN
            add_history(db, issue.id,
                        f"Mas'ul tayinlandi: {target.full_name} "
                        f"({ROLE_LABELS.get(target.role)})",
                        f"{user.full_name}")
            db.commit()
    return RedirectResponse(f"/issues/{issue_id}", status_code=302)


# ============================================================
# FOYDALANUVCHILAR (MAQOMLAR)
# ============================================================

@router.get("/users", response_class=HTMLResponse)
async def users_list(request: Request):
    user = get_current_user(request)
    if not user:
        return login_redirect()
    if user.role not in GLOBAL_ROLES and user.role != ROLE_RAIS:
        return RedirectResponse("/", status_code=302)

    with SessionLocal() as db:
        q = db.query(User)
        if user.role == ROLE_RAIS:
            q = q.filter(User.mahalla_id == user.mahalla_id)
        users = q.order_by(User.role, User.full_name).all()
        mahalla_names = {m.id: m.name for m in db.query(Mahalla).all()}
        mahallas = db.query(Mahalla).order_by(Mahalla.name).all()

    creatable = CREATABLE_BY.get(user.role, [])
    return render(request, "users.html", user,
                  users=users, mahalla_names=mahalla_names,
                  mahallas=mahallas, creatable=creatable,
                  can_create=bool(creatable))


@router.post("/users/create")
async def user_create(request: Request,
                      full_name: str = Form(...), phone: str = Form(""),
                      role: str = Form(...), mahalla_id: str = Form(""),
                      username: str = Form(...), password: str = Form(...)):
    user = get_current_user(request)
    if not user:
        return login_redirect()
    creatable = CREATABLE_BY.get(user.role, [])
    if role not in creatable:
        return RedirectResponse("/users", status_code=302)

    with SessionLocal() as db:
        if db.query(User).filter(User.username == username.strip()).first():
            return RedirectResponse("/users?err=login_band", status_code=302)
        m_id = int(mahalla_id) if mahalla_id and role not in GLOBAL_ROLES else None
        new_user = User(
            full_name=full_name.strip(),
            phone=phone.strip(),
            role=role,
            mahalla_id=m_id,
            username=username.strip(),
            password_hash=hash_password(password),
            link_code=new_link_code(),
        )
        db.add(new_user)
        db.commit()
    return RedirectResponse("/users", status_code=302)


@router.post("/users/{user_id}/toggle")
async def user_toggle(request: Request, user_id: int):
    user = get_current_user(request)
    if not user or user.role not in GLOBAL_ROLES:
        return login_redirect()
    with SessionLocal() as db:
        target = db.get(User, user_id)
        if target and target.role != "super_admin":
            target.is_active = not target.is_active
            db.commit()
    return RedirectResponse("/users", status_code=302)


@router.post("/users/{user_id}/newcode")
async def user_new_code(request: Request, user_id: int):
    """Yangi Telegram ulanish kodi berish (eski ulanish uziladi)."""
    user = get_current_user(request)
    if not user:
        return login_redirect()
    if user.role not in GLOBAL_ROLES and user.role != ROLE_RAIS:
        return RedirectResponse("/users", status_code=302)
    with SessionLocal() as db:
        target = db.get(User, user_id)
        if target:
            if user.role == ROLE_RAIS and target.mahalla_id != user.mahalla_id:
                return RedirectResponse("/users", status_code=302)
            target.link_code = new_link_code()
            target.tg_id = None
            db.commit()
    return RedirectResponse("/users", status_code=302)


@router.post("/users/{user_id}/password")
async def user_reset_password(request: Request, user_id: int,
                              new_password: str = Form(...)):
    user = get_current_user(request)
    if not user or user.role not in GLOBAL_ROLES:
        return login_redirect()
    with SessionLocal() as db:
        target = db.get(User, user_id)
        if target and len(new_password) >= 6:
            target.password_hash = hash_password(new_password)
            db.commit()
    return RedirectResponse("/users", status_code=302)


# ============================================================
# MAHALLALAR
# ============================================================

@router.get("/mahallas", response_class=HTMLResponse)
async def mahallas_list(request: Request):
    user = get_current_user(request)
    if not user:
        return login_redirect()
    if user.role not in GLOBAL_ROLES:
        return RedirectResponse("/", status_code=302)
    with SessionLocal() as db:
        mahallas = db.query(Mahalla).order_by(Mahalla.name).all()
        counts = {}
        for m in mahallas:
            counts[m.id] = {
                "users": db.query(User).filter(User.mahalla_id == m.id).count(),
                "open": db.query(Issue).filter(Issue.mahalla_id == m.id,
                                               Issue.status.in_(OPEN_STATUSES)).count(),
            }
    return render(request, "mahallas.html", user, mahallas=mahallas, counts=counts)


@router.post("/mahallas/create")
async def mahalla_create(request: Request, name: str = Form(...),
                         district: str = Form(""), chat_id: str = Form("")):
    user = get_current_user(request)
    if not user or user.role not in GLOBAL_ROLES:
        return login_redirect()
    with SessionLocal() as db:
        db.add(Mahalla(name=name.strip(), district=district.strip(),
                       chat_id=chat_id.strip() or None))
        db.commit()
    return RedirectResponse("/mahallas", status_code=302)


@router.post("/mahallas/{mahalla_id}/update")
async def mahalla_update(request: Request, mahalla_id: int,
                         chat_id: str = Form("")):
    user = get_current_user(request)
    if not user or user.role not in GLOBAL_ROLES:
        return login_redirect()
    with SessionLocal() as db:
        m = db.get(Mahalla, mahalla_id)
        if m:
            m.chat_id = chat_id.strip() or None
            db.commit()
    return RedirectResponse("/mahallas", status_code=302)


@router.post("/mahallas/{mahalla_id}/toggle")
async def mahalla_toggle(request: Request, mahalla_id: int):
    user = get_current_user(request)
    if not user or user.role not in GLOBAL_ROLES:
        return login_redirect()
    with SessionLocal() as db:
        m = db.get(Mahalla, mahalla_id)
        if m:
            m.is_active = not m.is_active
            db.commit()
    return RedirectResponse("/mahallas", status_code=302)


# ============================================================
# HISOBOTLAR (TAHLIL)
# ============================================================

@router.get("/reports", response_class=HTMLResponse)
async def reports(request: Request, days: int = 30):
    user = get_current_user(request)
    if not user:
        return login_redirect()

    days = max(7, min(days, 365))
    since = now_tk() - timedelta(days=days)

    with SessionLocal() as db:
        iq = scoped_issues_query(db, user).filter(Issue.created_at >= since)

        # Kategoriya kesimi
        cat_rows = []
        max_c = 1
        for key, info in CATEGORIES.items():
            total = iq.filter(Issue.category == key).count()
            solved = iq.filter(Issue.category == key,
                               Issue.status.in_([STATUS_YOPILDI, STATUS_HAL_QILINDI])).count()
            if total:
                cat_rows.append({"label": info["label"], "emoji": info["emoji"],
                                 "total": total, "solved": solved})
                max_c = max(max_c, total)
        for r in cat_rows:
            r["pct"] = int(r["total"] / max_c * 100)
            r["solve_pct"] = int(r["solved"] / r["total"] * 100) if r["total"] else 0
        cat_rows.sort(key=lambda x: -x["total"])

        # Xabar turlari (reklama, spam, e'lonlar oqimi)
        lq = db.query(MessageLog).filter(MessageLog.created_at >= since)
        if user.role not in GLOBAL_ROLES and user.mahalla_id:
            lq = lq.filter(MessageLog.mahalla_id == user.mahalla_id)
        type_rows = {}
        for row in lq.all():
            type_rows[row.msg_type] = type_rows.get(row.msg_type, 0) + 1

        # Eng ko'p qayta ochilgan (muammoli) topshiriqlar
        problem_issues = (scoped_issues_query(db, user)
                          .filter(Issue.reopen_count > 0)
                          .order_by(Issue.reopen_count.desc()).limit(10).all())

        # O'rtacha hal qilish vaqti (soatlarda)
        solved_issues = iq.filter(Issue.resolved_at.isnot(None)).all()
        if solved_issues:
            total_h = sum(
                (i.resolved_at - i.created_at).total_seconds() / 3600
                for i in solved_issues
            )
            avg_hours = round(total_h / len(solved_issues), 1)
        else:
            avg_hours = None

        mahalla_names = {m.id: m.name for m in db.query(Mahalla).all()}
        total_new = iq.count()

    return render(request, "reports.html", user,
                  days=days, cat_rows=cat_rows, type_rows=type_rows,
                  problem_issues=problem_issues, avg_hours=avg_hours,
                  mahalla_names=mahalla_names, total_new=total_new)
