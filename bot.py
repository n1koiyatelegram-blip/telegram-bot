import asyncio
from datetime import datetime, timedelta
from threading import Thread
from http.server import HTTPServer, BaseHTTPRequestHandler
from telegram import Update, ChatPermissions
from telegram.ext import Application, CommandHandler, ContextTypes

TOKEN = "8045822374:AAFPvLyjwCdPndVDomcN_plp-_mhxkHgIww"
ADMIN_ID = 8561804900

# --- Команды ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    await update.message.reply_text("✅ Бот работает. Команды:\n/ban ID\n/unban ID\n/mute ID 1h\n/unmute ID")

async def ban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    if not context.args:
        await update.message.reply_text("/ban 123456789")
        return
    try:
        user_id = int(context.args[0])
    except:
        await update.message.reply_text("ID должен быть числом")
        return
    try:
        await context.bot.ban_chat_member(update.effective_chat.id, user_id)
        await update.message.reply_text(f"🔨 Пользователь {user_id} забанен")
    except Exception as e:
        await update.message.reply_text(f"Ошибка: {e}")

async def unban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    if not context.args:
        await update.message.reply_text("/unban 123456789")
        return
    try:
        user_id = int(context.args[0])
    except:
        await update.message.reply_text("ID числом")
        return
    try:
        await context.bot.unban_chat_member(update.effective_chat.id, user_id)
        await update.message.reply_text(f"🟢 Пользователь {user_id} разбанен")
    except Exception as e:
        await update.message.reply_text(f"Ошибка: {e}")

async def mute(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    if len(context.args) < 2:
        await update.message.reply_text("/mute 123456789 1h")
        return
    try:
        user_id = int(context.args[0])
    except:
        await update.message.reply_text("ID числом")
        return
    dur = context.args[1]
    if dur.endswith('h'):
        sec = int(dur[:-1]) * 3600
        text = f"{dur[:-1]} час(ов)"
    elif dur.endswith('m'):
        sec = int(dur[:-1]) * 60
        text = f"{dur[:-1]} минут"
    elif dur.endswith('s'):
        sec = int(dur[:-1])
        text = f"{dur[:-1]} секунд"
    else:
        await update.message.reply_text("Формат: 1h, 30m, 15s")
        return
    try:
        await context.bot.restrict_chat_member(
            update.effective_chat.id, user_id,
            ChatPermissions(can_send_messages=False),
            until_date=datetime.utcnow() + timedelta(seconds=sec)
        )
        await update.message.reply_text(f"🔇 Пользователь {user_id} замучен на {text}")
    except Exception as e:
        await update.message.reply_text(f"Ошибка: {e}")

async def unmute(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    if not context.args:
        await update.message.reply_text("/unmute 123456789")
        return
    try:
        user_id = int(context.args[0])
    except:
        await update.message.reply_text("ID числом")
        return
    try:
        await context.bot.restrict_chat_member(
            update.effective_chat.id, user_id,
            ChatPermissions(can_send_messages=True)
        )
        await update.message.reply_text(f"🔊 Пользователь {user_id} размучен")
    except Exception as e:
        await update.message.reply_text(f"Ошибка: {e}")

# --- Веб-сервер для Render (чтоб не ругался на порты) ---
class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"OK")
    def log_message(self, format, *args):
        pass  # заглушаем логи

def run_webserver():
    server = HTTPServer(('0.0.0.0', 10000), Handler)
    server.serve_forever()

# --- Запуск ---
def main():
    # Запускаем веб-сервер в фоновом потоке
    Thread(target=run_webserver, daemon=True).start()
    
    # Создаём приложение
    app = Application.builder().token(TOKEN).build()
    
    # Добавляем обработчики
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("ban", ban))
    app.add_handler(CommandHandler("unban", unban))
    app.add_handler(CommandHandler("mute", mute))
    app.add_handler(CommandHandler("unmute", unmute))
    
    # Убиваем все старые webhook и сессии (чтобы не было конфликта)
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(app.bot.delete_webhook(drop_pending_updates=True))
    
    print("✅ Бот запущен (бан, разбан, мут, размут)")
    # Запускаем polling (в этом же цикле)
    app.run_polling()

if __name__ == "__main__":
    main()
