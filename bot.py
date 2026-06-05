import asyncio
from datetime import datetime, timedelta
from threading import Thread
from http.server import HTTPServer, BaseHTTPRequestHandler
from telegram import Update, ChatPermissions
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

TOKEN = "8924072551:AAF5hfJNcEA4eRxbcM9sa3nt3-SXgZacmCY"
ADMIN_ID = 8561804900  # ваш Telegram ID

# --- Парсинг времени (русские и английские суффиксы) ---
def parse_duration(duration_str: str):
    if not duration_str:
        return None, "Не указана длительность."
    s = duration_str.lower().strip()
    if any(s.endswith(x) for x in ('h', 'ч', 'час', 'часа', 'часов')):
        val = int(''.join(filter(str.isdigit, s)))
        return timedelta(hours=val), f"{val} час(ов)"
    if any(s.endswith(x) for x in ('m', 'мин', 'минута', 'минуты', 'минут')):
        val = int(''.join(filter(str.isdigit, s)))
        return timedelta(minutes=val), f"{val} минут"
    if any(s.endswith(x) for x in ('s', 'сек', 'секунда', 'секунды', 'секунд')):
        val = int(''.join(filter(str.isdigit, s)))
        return timedelta(seconds=val), f"{val} секунд"
    if any(s.endswith(x) for x in ('d', 'д', 'дн', 'дня', 'дней')):
        val = int(''.join(filter(str.isdigit, s)))
        return timedelta(days=val), f"{val} день(дней)"
    if any(s.endswith(x) for x in ('w', 'нед', 'неделя', 'недели', 'недель')):
        val = int(''.join(filter(str.isdigit, s)))
        return timedelta(weeks=val), f"{val} неделя(ь)"
    return None, "Используйте: 30м, 2ч, 1д, 1нед"

# --- Получение ID пользователя (реплай, @username, прямой ID) ---
async def resolve_user_id(update: Update, context: ContextTypes.DEFAULT_TYPE, target: str = None):
    if update.message.reply_to_message:
        return update.message.reply_to_message.from_user.id
    if target:
        target = target.strip()
        if target.isdigit():
            return int(target)
        if target.startswith('@'):
            username = target[1:]
            try:
                admins = await context.bot.get_chat_administrators(update.effective_chat.id)
                for admin in admins:
                    if admin.user.username and admin.user.username.lower() == username.lower():
                        return admin.user.id
                await update.message.reply_text(f"❌ Не найден @{username} (только среди админов).")
            except Exception as e:
                await update.message.reply_text(f"Ошибка поиска: {e}")
            return None
    return None

# --- Обработчик всех команд с точкой или слешем ---
async def handle_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("⛔ Нет прав.")
        return
    text = update.message.text.strip()
    if not text:
        return

    # ----- МУТ -----
    if text.startswith(('.мут', '/mute')):
        parts = text.split()
        if len(parts) == 1:
            uid = await resolve_user_id(update, context)
            if not uid: return
            dur = "1h"
        elif len(parts) == 2:
            if any(parts[1].endswith(x) for x in ('h','m','s','d','w','ч','мин','сек','д','нед')):
                uid = await resolve_user_id(update, context)
                if not uid: return
                dur = parts[1]
            else:
                uid = await resolve_user_id(update, context, parts[1])
                if not uid: return
                dur = "1h"
        else:
            uid = await resolve_user_id(update, context, parts[1])
            if not uid: return
            dur = parts[2]
        delta, dur_text = parse_duration(dur)
        if delta is None:
            await update.message.reply_text(f"❌ {dur_text}")
            return
        until = datetime.utcnow() + delta
        try:
            await context.bot.restrict_chat_member(
                update.effective_chat.id, uid,
                ChatPermissions(can_send_messages=False),
                until_date=until
            )
            await update.message.reply_text(f"🔇 Пользователь замучен на {dur_text}")
        except Exception as e:
            await update.message.reply_text(f"Ошибка: {e}")

    # ----- РАЗМУТ -----
    elif text.startswith(('.размут', '/unmute')):
        parts = text.split()
        uid = await resolve_user_id(update, context, parts[1] if len(parts)>1 else None)
        if not uid: return
        try:
            await context.bot.restrict_chat_member(
                update.effective_chat.id, uid,
                ChatPermissions(can_send_messages=True)
            )
            await update.message.reply_text("🔊 Пользователь размучен")
        except Exception as e:
            await update.message.reply_text(f"Ошибка: {e}")

    # ----- БАН (навсегда) -----
    elif text.startswith(('.бан', '/ban')):
        parts = text.split()
        uid = await resolve_user_id(update, context, parts[1] if len(parts)>1 else None)
        if not uid: return
        try:
            await context.bot.ban_chat_member(update.effective_chat.id, uid, revoke_messages=True)
            await update.message.reply_text("🔨 Пользователь забанен навсегда")
        except Exception as e:
            await update.message.reply_text(f"Ошибка: {e}")

    # ----- РАЗБАН -----
    elif text.startswith(('.разбан', '/unban')):
        parts = text.split()
        uid = await resolve_user_id(update, context, parts[1] if len(parts)>1 else None)
        if not uid: return
        try:
            await context.bot.unban_chat_member(update.effective_chat.id, uid)
            await update.message.reply_text("🟢 Пользователь разбанен (может зайти по ссылке)")
        except Exception as e:
            await update.message.reply_text(f"Ошибка: {e}")

# --- Команда /start ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("⛔ Нет прав.")
        return
    await update.message.reply_text(
        "✅ Бот-администратор.\n\n"
        "Команды (с точкой или /):\n"
        "• .мут 1мин   (ответьте на сообщение)\n"
        "• .мут @username 2ч\n"
        "• .размут @username\n"
        "• .бан @username\n"
        "• .разбан @username\n\n"
        "Поддерживается: 1мин, 2ч, 3д, 1нед, 30сек"
    )

# --- Веб-сервер для Render (чтобы не падал по портам) ---
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

# --- Запуск ---
def main():
    Thread(target=run_webserver, daemon=True).start()
    app = Application.builder().token(TOKEN).build()
    # Сброс вебхука при старте
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(app.bot.delete_webhook(drop_pending_updates=True))
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_command))
    print("✅ Бот успешно запущен. Команды: .мут 1мин (ответом), .размут, .бан, .разбан")
    app.run_polling()

if __name__ == "__main__":
    main()
