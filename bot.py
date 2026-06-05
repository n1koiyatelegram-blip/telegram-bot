import asyncio
from threading import Thread
from http.server import HTTPServer, BaseHTTPRequestHandler
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

TOKEN = "8045822374:AAGNjQ3gUDk6B5ZAwU8uHOlt2Ixx99LMnDI"
ADMIN_ID = 8561804900  # ваш ID

# Команда /test – отвечает в любом чате (даже без проверки админа)
async def test(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("✅ Бот работает и видит это сообщение!")

# Логируем все текстовые сообщения (для диагностики)
async def echo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    print(f"[LOG] Чат {update.effective_chat.id}, user {update.effective_user.id}, текст: {update.message.text}")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("⛔ Нет прав.")
        return
    await update.message.reply_text("Бот запущен. Попробуйте в группе /test")

# Веб-сервер для Render (без изменений)
class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"OK")
    def log_message(self, format, *args):
        pass

def run_webserver():
    server = HTTPServer(('0.0.0.0', 10000), Handler)
    server.serve_forever()

def main():
    Thread(target=run_webserver, daemon=True).start()
    app = Application.builder().token(TOKEN).build()
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(app.bot.delete_webhook(drop_pending_updates=True))
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("test", test))          # <- добавили
    app.add_handler(MessageHandler(filters.TEXT, echo))   # логируем всё
    print("✅ Бот в диагностическом режиме. Отправьте /test в группе.")
    app.run_polling()

if __name__ == "__main__":
    main()
