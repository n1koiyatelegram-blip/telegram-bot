import asyncio
from datetime import datetime, timedelta
from threading import Thread
from http.server import HTTPServer, BaseHTTPRequestHandler
from telegram import Update, ChatPermissions
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

TOKEN = "8045822374:AAFPvLyjwCdPndVDomcN_plp-_mhxkHgIww"
ADMIN_ID = 8561804900

# --- Вспомогательная функция парсинга длительности ---
def parse_duration(duration_str: str):
    """Возвращает (timedelta, человеко-читаемая строка) или (None, сообщение об ошибке)."""
    if not duration_str:
        return None, "Не указана длительность."
    duration_str = duration_str.lower().strip()
    # Поддерживаем: 1h, 30m, 15s, 2d, 1w
    if duration_str.endswith('h'):
        try:
            val = int(duration_str[:-1])
            return timedelta(hours=val), f"{val} час(ов)"
        except:
            return None, "Неверное число часов."
    elif duration_str.endswith('m'):
        try:
            val = int(duration_str[:-1])
            return timedelta(minutes=val), f"{val} минут"
        except:
            return None, "Неверное число минут."
    elif duration_str.endswith('s'):
        try:
            val = int(duration_str[:-1])
            return timedelta(seconds=val), f"{val} секунд"
        except:
            return None, "Неверное число секунд."
    elif duration_str.endswith('d'):
        try:
            val = int(duration_str[:-1])
            return timedelta(days=val), f"{val} день(дней)"
        except:
            return None, "Неверное число дней."
    elif duration_str.endswith('w'):
        try:
            val = int(duration_str[:-1])
            return timedelta(weeks=val), f"{val} неделя(ь)"
        except:
            return None, "Неверное число недель."
    else:
        return None, "Используйте: 30m, 2h, 15s, 1d, 1w"

# --- Вспомогательная функция для получения user_id из разных форматов ---
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
                chat = update.effective_chat
                admins = await context.bot.get_chat_administrators(chat.id)
                for admin in admins:
                    if admin.user.username and admin.user.username.lower() == username.lower():
                        return admin.user.id
                # Можно попробовать поискать среди всех участников? API не позволяет.
                await update.message.reply_text(f"❌ Не могу найти @{username}. Попросите пользователя написать сообщение в чат.")
                return None
            except Exception as e:
                await update.message.reply_text(f"Ошибка поиска: {e}")
                return None
    return None

# --- Обработчик команд ---
async def handle_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    text = update.message.text.strip()
    # ---- MUTE ----
    if text.startswith(('.мут', '/mute')):
        parts = text.split()
        # Определяем user_id и duration
        if len(parts) == 1:
            # Только команда: надеемся на реплай
            user_id = await resolve_user_id(update, context)
            if not user_id:
                await update.message.reply_text("❗ Ответьте на сообщение пользователя или укажите @username / ID.")
                return
            duration = "1h"
        elif len(parts) == 2:
            # .мут 1h  или  .мут @username
            if parts[1][-1] in ('h','m','s','d','w') and parts[1][:-1].isdigit():
                # Это длительность
                user_id = await resolve_user_id(update, context)
                if not user_id:
                    await update.message.reply_text("❗ Ответьте на сообщение пользователя или укажите @username.")
                    return
                duration = parts[1]
            else:
                # Это пользователь
                user_id = await resolve_user_id(update, context, parts[1])
                if not user_id:
                    return
                duration = "1h"
        else:  # >=3 частей: .мут @username 1h
            user_id = await resolve_user_id(update, context, parts[1])
            if not user_id:
                return
            duration = parts[2]
        delta, dur_text = parse_duration(duration)
        if delta is None:
            await update.message.reply_text(f"❌ {dur_text}")
            return
        until = datetime.utcnow() + delta
        try:
            await context.bot.restrict_chat_member(
                update.effective_chat.id, user_id,
                ChatPermissions(can_send_messages=False),
                until_date=until
            )
            await update.message.reply_text(f"🔇 Пользователь замучен на {dur_text}")
        except Exception as e:
            await update.message.reply_text(f"Ошибка: {e}")
    
    # ---- UNMUTE ----
    elif text.startswith(('.размут', '/unmute')):
        parts = text.split()
        user_id = await resolve_user_id(update, context, parts[1] if len(parts) > 1 else None)
        if not user_id:
            await update.message.reply_text("❗ Укажите пользователя: .размут @username или ответьте на его сообщение.")
            return
        try:
            await context.bot.restrict_chat_member(
                update.effective_chat.id, user_id,
                ChatPermissions(can_send_messages=True)
            )
            await update.message.reply_text("🔊 Пользователь размучен")
        except Exception as e:
            await update.message.reply_text(f"Ошибка: {e}")
    
    # ---- BAN (теперь с поддержкой временного бана) ----
    elif text.startswith(('.бан', '/ban')):
        parts = text.split()
        # Аналогично муту, но используем ban_chat_member с until_date
        if len(parts) == 1:
            user_id = await resolve_user_id(update, context)
            if not user_id:
                await update.message.reply_text("❗ Ответьте на сообщение или укажите @username / ID.")
                return
            delta = None  # навсегда
            dur_text = "навсегда"
        elif len(parts) == 2:
            if parts[1][-1] in ('h','m','s','d','w') and parts[1][:-1].isdigit():
                user_id = await resolve_user_id(update, context)
                if not user_id:
                    await update.message.reply_text("❗ Ответьте на сообщение или укажите @username.")
                    return
                duration = parts[1]
                delta, dur_text = parse_duration(duration)
                if delta is None:
                    await update.message.reply_text(f"❌ {dur_text}")
                    return
            else:
                user_id = await resolve_user_id(update, context, parts[1])
                if not user_id:
                    return
                delta = None
                dur_text = "навсегда"
        else:  # 3 части: .бан @username 1h
            user_id = await resolve_user_id(update, context, parts[1])
            if not user_id:
                return
            duration = parts[2]
            delta, dur_text = parse_duration(duration)
            if delta is None:
                await update.message.reply_text(f"❌ {dur_text}")
                return
        try:
            if delta:
                until = datetime.utcnow() + delta
                await context.bot.ban_chat_member(
                    update.effective_chat.id, user_id,
                    until_date=until,
                    revoke_messages=True
                )
                await update.message.reply_text(f"🔨 Пользователь забанен на {dur_text}")
            else:
                await context.bot.ban_chat_member(
                    update.effective_chat.id, user_id,
                    revoke_messages=True
                )
                await update.message.reply_text("🔨 Пользователь забанен навсегда")
        except Exception as e:
            await update.message.reply_text(f"Ошибка: {e}")
    
    # ---- UNBAN ----
    elif text.startswith(('.разбан', '/unban')):
        parts = text.split()
        user_id = await resolve_user_id(update, context, parts[1] if len(parts) > 1 else None)
        if not user_id:
            await update.message.reply_text("❗ Укажите пользователя: .разбан @username")
            return
        try:
            await context.bot.unban_chat_member(update.effective_chat.id, user_id)
            await update.message.reply_text("🟢 Пользователь разбанен (может зайти по ссылке)")
        except Exception as e:
            await update.message.reply_text(f"Ошибка: {e}")

# --- Команда start ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    await update.message.reply_text(
        "✅ Бот-администратор.\n\n"
        "Команды (с точкой или слешем):\n"
        "• .мут [@username/ID] [время]  — пример: .мут 30m, .мут @user 2h, ответом .мут 1d\n"
        "• .размут [@username/ID]       — по реплаю или @\n"
        "• .бан [@username/ID] [время]  — временный бан: .бан 30m, .бан @user 2d, без времени — навсегда\n"
        "• .разбан @username/ID\n"
        "Форматы времени: 30m, 2h, 15s, 1d, 1w"
    )

# --- Веб-сервер для Render ---
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
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(app.bot.delete_webhook(drop_pending_updates=True))
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_command))
    print("✅ Бот запущен (мут/бан по реплаю, юзернейму, ID, с поддержкой времени)")
    app.run_polling()

if __name__ == "__main__":
    main()
