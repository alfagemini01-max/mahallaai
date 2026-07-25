"""Web panel autentifikatsiyasi: imzolangan cookie-sessiya (tashqi kutubxonasiz)."""
import hashlib
import hmac
import time

from fastapi import Request
from fastapi.responses import RedirectResponse

import config
from database import SessionLocal, User

SESSION_COOKIE = "mahalla_session"
SESSION_MAX_AGE = 7 * 24 * 3600  # 1 hafta


def _sign(payload: str) -> str:
    return hmac.new(config.SECRET_KEY.encode(), payload.encode(), hashlib.sha256).hexdigest()


def create_session_token(user_id: int) -> str:
    payload = f"{user_id}.{int(time.time())}"
    return f"{payload}.{_sign(payload)}"


def parse_session_token(token: str) -> int | None:
    try:
        user_id, ts, sig = token.split(".")
        payload = f"{user_id}.{ts}"
        if not hmac.compare_digest(sig, _sign(payload)):
            return None
        if time.time() - int(ts) > SESSION_MAX_AGE:
            return None
        return int(user_id)
    except (ValueError, AttributeError):
        return None


def get_current_user(request: Request) -> User | None:
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        return None
    user_id = parse_session_token(token)
    if not user_id:
        return None
    with SessionLocal() as db:
        user = db.get(User, user_id)
        if user and user.is_active:
            return user
    return None


def login_redirect() -> RedirectResponse:
    return RedirectResponse("/login", status_code=302)
