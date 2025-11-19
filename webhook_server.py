from flask import Flask, request
import telebot

TOKEN = "8389019229:AAFUZMPRPlt5ZR1igMCqjLq9oc6G4zg6MnQ"

bot = telebot.TeleBot(TOKEN)
app = Flask(__name__)

@app.route('/webhook', methods=['POST'])
def webhook():
    update = request.stream.read().decode("utf-8")
    bot.process_new_updates([telebot.types.Update.de_json(update)])
    return "ok", 200

@app.route('/')
def home():
    return "Bot is running!"

if __name__ == '__main__':
    bot.infinity_polling()
