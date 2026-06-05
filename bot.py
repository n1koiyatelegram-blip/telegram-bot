import os
from datetime import datetime, timedelta
from telegram import Update, ChatPermissions
from telegram.ext import Application, CommandHandler, ContextTypes
from threading import Thread
from http.server import HTTPServer, BaseHTTPRequestHandler

TOKEN = "8045822374:AAF_n01BMHRuFHSgpPQlf6cfCvyxd5ITuIw"
ADMIN_ID = 8561804900

# --- Код бота (баны, муты) ---
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
        await update.message.reply_text("ID числом")
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

# --- Веб-сервер для Render (чтобы он не ругался на отсутствие порта) ---
class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"OK")

def run_http_server():
    server = HTTPServer(('0.0.0.0', 10000), Handler)
    server.serve_forever()

# --- Запуск ---
def main():
    # Запускаем веб-сервер в отдельном потоке
    Thread(target=run_http_server, daemon=True).start()
    # Запускаем бота
    app = Application.builder().token(TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("ban", ban))
    app.add_handler(CommandHandler("unban", unban))
    app.add_handler(CommandHandler("mute", mute))
    app.add_handler(CommandHandler("unmute", unmute))
    print("✅ Бот запущен (бан, разбан, мут, размут)")
    app.run_polling()

if __name__ == "__main__":
    main()
