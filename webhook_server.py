from flask import Flask
import asyncio
import bot  # твой bot.py

app = Flask(__name__)

@app.route("/")
def home():
    return "Bot is running!"

@app.route("/webhook", methods=["POST"])
def webhook():
    return "ok", 200

# Запуск бота через asyncio
async def start_bot():
    await bot.main()  # запускаем main() из bot.py

if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.create_task(start_bot())
    import os
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))

