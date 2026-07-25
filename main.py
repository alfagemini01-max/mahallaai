"""Mahalla AI Bot — asosiy kirish nuqtasi.

Bitta FastAPI ilova ikkita vazifani bajaradi:
  1. Telegram bot webhook'i  (POST /webhook/<maxfiy>)
  2. Web admin panel         (/, /login, /issues, ...)

Ishga tushirish (lokal):   uvicorn main:app --reload
Render startCommand:       uvicorn main:app --host 0.0.0.0 --port $PORT
"""
import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.types import Update
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

import config
from bot.handlers import router as bot_router
from bot.weekly import weekly_scheduler
from database import init_db
from web.routes import router as web_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
log = logging.getLogger("main")

# ---------- Telegram bot ----------
bot: Bot | None = None
dp = Dispatcher()
dp.include_router(bot_router)

if config.BOT_TOKEN:
    bot = Bot(token=config.BOT_TOKEN,
              default=DefaultBotProperties(parse_mode="HTML"))
else:
    log.warning("BOT_TOKEN kiritilmagan — bot ishlamaydi, faqat panel ochiladi.")

_bg_tasks: list[asyncio.Task] = []


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 1) Baza va super admin
    init_db()
    log.info("Baza tayyor. Super admin: %s", config.ADMIN_USERNAME)

    if bot:
        # 2) Webhook yoki polling
        if config.BASE_URL:
            url = f"{config.BASE_URL}/webhook/{config.WEBHOOK_SECRET}"
            try:
                await bot.set_webhook(
                    url,
                    allowed_updates=["message", "callback_query", "my_chat_member"],
                    drop_pending_updates=True,
                )
                log.info("Webhook o'rnatildi: %s", url)
            except Exception as e:
                log.error("Webhook o'rnatilmadi: %s", e)
        else:
            # Lokal rejim: BASE_URL yo'q — long polling
            log.info("BASE_URL yo'q — polling rejimida ishga tushmoqda (lokal rejim)")
            await bot.delete_webhook(drop_pending_updates=True)
            _bg_tasks.append(asyncio.create_task(dp.start_polling(bot, handle_signals=False)))

        # 3) Haftalik hisobot fon vazifasi
        _bg_tasks.append(asyncio.create_task(weekly_scheduler(bot)))

    yield

    for t in _bg_tasks:
        t.cancel()
    if bot:
        await bot.session.close()


app = FastAPI(title="Mahalla AI", lifespan=lifespan)

app.mount("/static", StaticFiles(directory=str(Path(__file__).parent / "static")),
          name="static")
app.include_router(web_router)


@app.post("/webhook/{secret}")
async def telegram_webhook(secret: str, request: Request):
    """Telegramdan keladigan yangilanishlar."""
    if secret != config.WEBHOOK_SECRET or not bot:
        return JSONResponse({"ok": False}, status_code=403)
    try:
        data = await request.json()
        update = Update.model_validate(data, context={"bot": bot})
        await dp.feed_update(bot, update)
    except Exception as e:
        log.error("Webhook xatosi: %s", e)
    return {"ok": True}


@app.get("/health")
async def health():
    """Render health-check uchun."""
    return {"status": "ok"}
