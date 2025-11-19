# bot_soundcloud_inline_final.py
import aiohttp
import asyncio
import tempfile
import os
import logging
from typing import Optional

from telegram import (
    InlineQueryResultArticle, InputTextMessageContent,
    InlineKeyboardButton, InlineKeyboardMarkup,
    InputMediaAudio, Update
)
from telegram.ext import (
    ApplicationBuilder, InlineQueryHandler,
    CallbackQueryHandler, ChosenInlineResultHandler,
    ContextTypes
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TOKEN = "8389019229:AAFUZMPRPlt5ZR1igMCqjLq9oc6G4zg6MnQ"
CLIENT_ID = "LMlJPYvzQSVyjYv7faMQl9W7OjTBCaq4"
OAUTH_TOKEN = "OAuth 2-308903-768145462-LvIvHQUlZ6RKsi"
SERVICE_CHAT = -1003363147744

track_cache = {}

class SoundCloudAPI:
    def __init__(self):
        self.headers = {}
        if OAUTH_TOKEN:
            self.headers["Authorization"] = OAUTH_TOKEN
        self.headers["User-Agent"] = "Mozilla/5.0"
        self.session: Optional[aiohttp.ClientSession] = None

    async def get_session(self):
        if not self.session:
            timeout = aiohttp.ClientTimeout(total=120)
            self.session = aiohttp.ClientSession(timeout=timeout, headers=self.headers)
        return self.session

    async def close_session(self):
        if self.session:
            await self.session.close()
            self.session = None

    async def sc_search_instant(self, query: str):
        session = await self.get_session()
        url = "https://api-v2.soundcloud.com/search/tracks"
        params = {"q": query, "client_id": CLIENT_ID, "limit": 10}
        try:
            async with session.get(url, params=params) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return data.get("collection", [])
                logger.warning("Search status %s", resp.status)
        except Exception:
            logger.exception("Search exception")
        return []

    async def sc_get_audio_url(self, track_id: str) -> Optional[str]:
        session = await self.get_session()
        info_url = f"https://api-v2.soundcloud.com/tracks/{track_id}"
        try:
            async with session.get(info_url, params={"client_id": CLIENT_ID}) as resp:
                if resp.status != 200:
                    logger.warning("Track info status %s", resp.status)
                    return None
                track = await resp.json()
            transcodings = track.get("media", {}).get("transcodings", [])
            for t in transcodings:
                proto = t.get("format", {}).get("protocol")
                if proto != "progressive":
                    continue
                async with session.get(t["url"], params={"client_id": CLIENT_ID}) as r2:
                    if r2.status == 200:
                        j = await r2.json()
                        return j.get("url")
                    else:
                        logger.debug("Transcode status %s", r2.status)
        except Exception:
            logger.exception("Get audio url exception")
        return None

    async def download_audio(self, audio_url: str, filename: str) -> bool:
        session = await self.get_session()
        try:
            async with session.get(audio_url, timeout=180) as resp:
                if resp.status == 200:
                    with open(filename, "wb") as f:
                        async for chunk in resp.content.iter_chunked(8192):
                            f.write(chunk)
                    return True
                else:
                    logger.warning("Download status %s", resp.status)
        except Exception:
            logger.exception("Download exception")
        return False

sc_api = SoundCloudAPI()

# ---------------- Inline search ----------------
async def inline_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = (update.inline_query.query or "").strip()
    if not query or len(query) < 2:
        return await update.inline_query.answer([])

    tracks = await sc_api.sc_search_instant(query)
    results = []

    for t in tracks[:8]:
        tid = str(t.get("id"))
        duration = (t.get("duration") or 0) // 1000
        m, s = divmod(duration, 60)
        artwork = t.get("artwork_url") or ""
        if artwork:
            artwork = artwork.replace("large", "t500x500")

        track_cache[tid] = {
            "title": t.get("title") or "Unknown",
            "performer": t.get("user", {}).get("username") or "Unknown",
            "duration": duration,
            "artwork": artwork
        }

        results.append(
            InlineQueryResultArticle(
                id=tid,
                title=(t.get("title") or "")[:64],
                description=f"{t.get('user', {}).get('username', '')} • {m}:{s:02d}",
                thumbnail_url=artwork or None,
                input_message_content=InputTextMessageContent("🎵 Загружаем трек..."),
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔄 Повторить", callback_data=f"dl:{tid}")]])
            )
        )

    await update.inline_query.answer(results, is_personal=True, cache_time=0)

# ---------------- Chosen Inline ----------------
async def chosen_inline_result_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    cir = update.chosen_inline_result
    tid = cir.result_id
    inline_message_id = cir.inline_message_id

    if not inline_message_id:
        return

    # Сразу редактируем выбранное inline-сообщение в чат
    asyncio.create_task(worker_download_and_edit_inline(tid, inline_message_id, context))

# ---------------- CallbackQuery ----------------
async def callback_query_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    data = q.data or ""
    if not data.startswith("dl:"):
        await q.answer()
        return

    tid = data.split(":", 1)[1]
    await q.answer("Перезапускаю загрузку…")
    inline_message_id = getattr(q, "inline_message_id", None)
    if inline_message_id:
        asyncio.create_task(worker_download_and_edit_inline(tid, inline_message_id, context))

# ---------------- Worker for inline messages ----------------
async def worker_download_and_edit_inline(track_id: str, inline_message_id: str, context: ContextTypes.DEFAULT_TYPE):
    logger.info("Worker start: %s", track_id)
    try:
        # Редактируем сообщение на "Скачиваем"
        await context.bot.edit_message_text(
            inline_message_id=inline_message_id,
            text="📥 Скачиваем аудио..."
        )

        audio_url = await sc_api.sc_get_audio_url(track_id)
        if not audio_url:
            await context.bot.edit_message_text(
                inline_message_id=inline_message_id,
                text="❌ Не удалось получить URL.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔄 Повторить", callback_data=f"dl:{track_id}")]])
            )
            return

        fd, tmpname = tempfile.mkstemp(suffix=".mp3")
        os.close(fd)
        ok = await sc_api.download_audio(audio_url, tmpname)
        if not ok:
            await context.bot.edit_message_text(
                inline_message_id=inline_message_id,
                text="❌ Ошибка при скачивании.",
                reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔄 Повторить", callback_data=f"dl:{track_id}")]])
            )
            return

        info = track_cache.get(track_id, {})
        title = info.get("title", "")[:64]
        performer = info.get("performer", "")[:64]
        duration = info.get("duration")

        with open(tmpname, "rb") as audio_file:
            # Отправляем в SERVICE_CHAT для получения file_id
            sent = await context.bot.send_audio(
                chat_id=SERVICE_CHAT,
                audio=audio_file,
                title=title,
                performer=performer,
                duration=duration
            )
            file_id = sent.audio.file_id
            try:
                await context.bot.delete_message(chat_id=SERVICE_CHAT, message_id=sent.message_id)
            except Exception:
                pass

            audio_file.seek(0)
            await context.bot.edit_message_media(
                inline_message_id=inline_message_id,
                media=InputMediaAudio(media=file_id, caption=title)
            )
    except Exception as e:
        logger.exception("Worker error: %s", e)
        await context.bot.edit_message_text(
            inline_message_id=inline_message_id,
            text="❌ Произошла ошибка.",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔄 Повторить", callback_data=f"dl:{track_id}")]])
        )
    finally:
        try:
            os.unlink(tmpname)
        except Exception:
            pass

# ---------------- Lifecycle ----------------
async def post_init(app):
    await sc_api.get_session()
    logger.info("Bot ready")

async def post_stop(app):
    await sc_api.close_session()
    logger.info("Bot stopped")

# ---------------- Main ----------------
def main():
    app = ApplicationBuilder().token(TOKEN).post_init(post_init).post_shutdown(post_stop).build()
    app.add_handler(InlineQueryHandler(inline_handler))
    app.add_handler(ChosenInlineResultHandler(chosen_inline_result_handler))
    app.add_handler(CallbackQueryHandler(callback_query_handler))
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
