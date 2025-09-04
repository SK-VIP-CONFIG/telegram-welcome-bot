import os
from contextlib import asynccontextmanager
from datetime import datetime
from io import BytesIO

from fastapi import FastAPI, Request, Response
from http import HTTPStatus
from PIL import Image, ImageDraw, ImageFont
from telegram import Update
from telegram.ext import Application, MessageHandler, filters, ContextTypes

# --- ENV (set these in Render dashboard) ---
BOT_TOKEN = os.environ.get("TELEGRAM_TOKEN")
WEBHOOK_SECRET = os.environ.get("WEBHOOK_SECRET")
WEBHOOK_URL = os.environ.get("WEBHOOK_URL")

if not BOT_TOKEN:
    raise RuntimeError("TELEGRAM_TOKEN env var required")

# Build telegram application
app_bot = Application.builder().token(BOT_TOKEN).build()


def create_welcome_image(profile_img: Image.Image, username: str, fullname: str, join_date: str) -> Image.Image:
    W, H = 900, 360
    base = Image.new("RGB", (W, H), (245, 245, 245))
    profile = profile_img.resize((300, 300))
    base.paste(profile, (30, 30))

    draw = ImageDraw.Draw(base)
    font = ImageFont.load_default()
    draw.text((360, 60), f"Name: {fullname}", fill="black", font=font)
    draw.text((360, 110), f"Username: @{username}" if username and username != "N/A" else "Username: N/A", fill="black", font=font)
    draw.text((360, 160), f"Joined: {join_date}", fill="black", font=font)
    draw.text((360, 220), "Welcome to the group! 🎉", fill="black", font=font)
    return base


async def new_member_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.new_chat_members:
        return

    for member in update.message.new_chat_members:
        fullname = member.full_name
        username = member.username or "N/A"
        join_date = datetime.utcnow().strftime("%d-%m-%Y %H:%M UTC")

        try:
            photos = await context.bot.get_user_profile_photos(member.id, limit=1)
            if photos.total_count > 0:
                file = await context.bot.get_file(photos.photos[0][-1].file_id)
                bio = BytesIO()
                await file.download_to_memory(out=bio)
                bio.seek(0)
                profile_img = Image.open(bio).convert("RGB")
            else:
                profile_img = Image.new("RGB", (400, 400), (200, 200, 200))
        except Exception:
            profile_img = Image.new("RGB", (400, 400), (200, 200, 200))

        img = create_welcome_image(profile_img, username, fullname, join_date)
        out = BytesIO()
        out.name = "welcome.jpg"
        img.save(out, format="JPEG")
        out.seek(0)

        try:
            await context.bot.send_photo(chat_id=update.effective_chat.id, photo=out, caption=f"Welcome {fullname}! 🎉")
        except Exception as e:
            print("Send error:", e)


# Register handler
app_bot.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, new_member_handler))


# --- FastAPI integration with PTB ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    if not WEBHOOK_URL or not WEBHOOK_SECRET:
        raise RuntimeError("WEBHOOK_URL and WEBHOOK_SECRET must be set")
    await app_bot.bot.setWebhook(WEBHOOK_URL)
    await app_bot.start()
    print("Bot started and webhook set:", WEBHOOK_URL)
    try:
        yield
    finally:
        await app_bot.stop()
        print("Bot stopped.")


app = FastAPI(lifespan=lifespan)


@app.post("/webhook/{token}")
async def webhook(token: str, request: Request):
    if token != WEBHOOK_SECRET:
        return Response(status_code=HTTPStatus.FORBIDDEN)
    body = await request.json()
    update = Update.de_json(body, app_bot.bot)
    await app_bot.process_update(update)
    return Response(status_code=HTTPStatus.OK)
