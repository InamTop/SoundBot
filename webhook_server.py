from flask import Flask
import os
import asyncio
from bot import main as main_bot

app = Flask(__name__)

@app.route("/")
def home():
    return "Bot is running!"

@app.route("/webhook", methods=["POST"])
def webhook():
    return "ok", 200

# Запускаем бот асинхронно при старте сервера
async def start_bot():
    await main_bot()

if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.create_task(start_bot())
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
