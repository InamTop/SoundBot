from flask import Flask
import threading
import asyncio
import os

# Импортируем твой бот
from bot import main as run_bot_main

app = Flask(__name__)

# Запуск бота в отдельном потоке (async polling)
def run_bot():
    asyncio.run(run_bot_main())

threading.Thread(target=run_bot, daemon=True).start()

@app.route("/")
def home():
    return "Bot is running!"

@app.route("/webhook", methods=["POST"])
def webhook():
    return "ok", 200
