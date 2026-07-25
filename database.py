"""Ma'lumotlar bazasi: modellar va sessiya boshqaruvi (SQLAlchemy 2.0)."""
import hashlib
import hmac
import secrets
from datetime import datetime, timedelta

from sqlalchemy import (
    Boolean, Column, DateTime, Float, ForeignKey, Integer,
    String, Text, create_engine,
)
from sqlalchemy.orm import declarative_base, relationship, sessionmaker

import config

Base = declarative_base()

engine_kwargs = {"pool_pre_ping": True}
if config.DATABASE_URL.startswith("sqlite"):
    engine_kwargs["connect_args"] = {"check_same_thread": False}

engine = create_engine(config.DATABASE_URL, **engine_kwargs)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def now_tk() -> datetime:
    """Toshkent vaqti (UTC+5)."""
    return datetime.utcnow() + timedelta(hours=config.TZ_OFFSET_HOURS)


# ============================================================
# MODELLAR
# ============================================================

class Mahalla(Base):
    __tablename__ = "mahallas"

    id = Column(Integer, primary_key=True)
    name = Column(String(200), nullable=False)
    district = Column(String(200), default="")          # Tuman / shahar
    chat_id = Column(String(50), unique=True, nullable=True)  # Telegram guruh ID
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=now_tk)

    users = relationship("User", back_populates="mahalla")
    issues = relationship("Issue", back_populates="mahalla")


class User(Base):
    """Panel foydalanuvchisi = mas'ul shaxs (maqom egasi)."""
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    full_name = Column(String(200), nullable=False)
    phone = Column(String(30), default="")
    role = Column(String(50), nullable=False)           # roles.py dagi maqomlar
    mahalla_id = Column(Integer, ForeignKey("mahallas.id"), nullable=True)  # global maqomlarda bo'sh

    # Web panelga kirish
    username = Column(String(100), unique=True, nullable=False)
    password_hash = Column(String(300), nullable=False)

    # Telegram bog'lash: mas'ul botga /ulanish KOD yuboradi
    tg_id = Column(String(50), unique=True, nullable=True)
    link_code = Column(String(20), unique=True, nullable=True)

    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=now_tk)

    mahalla = relationship("Mahalla", back_populates="users")


class Issue(Base):
    """Muammo / topshiriq."""
    __tablename__ = "issues"

    id = Column(Integer, primary_key=True)
    mahalla_id = Column(Integer, ForeignKey("mahallas.id"), nullable=False)

    category = Column(String(50), default="boshqa")
    severity = Column(String(20), default="orta")
    summary = Column(String(500), default="")           # AI qisqacha bayoni
    original_text = Column(Text, default="")            # Asl xabar (panelda ko'rinadi)
    location_hint = Column(String(300), default="")     # AI ajratgan manzil ("X ko'cha")

    status = Column(String(30), default="yangi")
    assigned_role = Column(String(50), default="")
    assigned_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)

    # Telegram bog'lamalari
    author_tg_id = Column(String(50), default="")       # Hisobotlarda ko'rsatilmaydi (maxfiylik)
    group_message_id = Column(Integer, nullable=True)   # Asl xabar ID
    bot_message_id = Column(Integer, nullable=True)     # Bot tasdiqlash xabari ID
    verify_message_id = Column(Integer, nullable=True)  # "Hal bo'ldimi?" xabari ID

    confirm_count = Column(Integer, default=0)
    reopen_count = Column(Integer, default=0)

    created_at = Column(DateTime, default=now_tk)
    updated_at = Column(DateTime, default=now_tk, onupdate=now_tk)
    resolved_at = Column(DateTime, nullable=True)

    mahalla = relationship("Mahalla", back_populates="issues")
    assigned_user = relationship("User", foreign_keys=[assigned_user_id])
    votes = relationship("Vote", back_populates="issue", cascade="all, delete-orphan")
    history = relationship("IssueHistory", back_populates="issue",
                           cascade="all, delete-orphan", order_by="IssueHistory.created_at")


class Vote(Base):
    """Aholi ovozlari: tasdiqlash yoki hal bo'lganini tekshirish."""
    __tablename__ = "votes"

    id = Column(Integer, primary_key=True)
    issue_id = Column(Integer, ForeignKey("issues.id"), nullable=False)
    tg_user_id = Column(String(50), nullable=False)
    kind = Column(String(20), nullable=False)   # confirm | verify_ok | verify_no
    created_at = Column(DateTime, default=now_tk)

    issue = relationship("Issue", back_populates="votes")


class IssueHistory(Base):
    """Muammo bo'yicha barcha harakatlar jurnali (audit)."""
    __tablename__ = "issue_history"

    id = Column(Integer, primary_key=True)
    issue_id = Column(Integer, ForeignKey("issues.id"), nullable=False)
    action = Column(String(300), nullable=False)
    actor = Column(String(200), default="Tizim")
    created_at = Column(DateTime, default=now_tk)

    issue = relationship("Issue", back_populates="history")


class MessageLog(Base):
    """Har bir tahlil qilingan xabar statistikasi (haftalik hisobot uchun).

    Maxfiylik: matnning faqat AI bayoni saqlanadi, muallif ismi hisobotlarga chiqmaydi.
    """
    __tablename__ = "message_logs"

    id = Column(Integer, primary_key=True)
    mahalla_id = Column(Integer, ForeignKey("mahallas.id"), nullable=False)
    msg_type = Column(String(30), default="oddiy_suhbat")
    category = Column(String(50), default="")
    summary = Column(String(300), default="")
    confidence = Column(Float, default=0.0)
    created_at = Column(DateTime, default=now_tk)


class Setting(Base):
    """Kalit-qiymat sozlamalar (masalan, oxirgi haftalik hisobot belgisi)."""
    __tablename__ = "settings"

    key = Column(String(100), primary_key=True)
    value = Column(String(500), default="")


# ============================================================
# PAROL XESHLASH (tashqi kutubxonasiz, PBKDF2)
# ============================================================

def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 200_000)
    return f"{salt}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        salt, digest_hex = stored.split("$", 1)
    except ValueError:
        return False
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 200_000)
    return hmac.compare_digest(digest.hex(), digest_hex)


def new_link_code() -> str:
    """Telegram ulanish kodi: 8 belgili, chalkashmas harflar."""
    alphabet = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
    return "".join(secrets.choice(alphabet) for _ in range(8))


# ============================================================
# BOSHLANG'ICH SOZLASH
# ============================================================

def init_db():
    """Jadvallarni yaratish va Super Adminni ta'minlash."""
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        admin = db.query(User).filter(User.role == "super_admin").first()
        if not admin:
            admin = User(
                full_name="Super Administrator",
                role="super_admin",
                username=config.ADMIN_USERNAME,
                password_hash=hash_password(config.ADMIN_PASSWORD),
                link_code=new_link_code(),
            )
            db.add(admin)
            db.commit()


def get_setting(db, key: str, default: str = "") -> str:
    row = db.get(Setting, key)
    return row.value if row else default


def set_setting(db, key: str, value: str):
    row = db.get(Setting, key)
    if row:
        row.value = value
    else:
        db.add(Setting(key=key, value=value))
    db.commit()


def add_history(db, issue_id: int, action: str, actor: str = "Tizim"):
    db.add(IssueHistory(issue_id=issue_id, action=action, actor=actor))
