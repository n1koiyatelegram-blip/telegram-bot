import asyncio
from datetime import datetime, timedelta
from threading import Thread
from http.server import HTTPServer, BaseHTTPRequestHandler
from telegram import Update, ChatPermissions
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

TOKEN = "8045822374:AAFPvLyjwCdPndVDomcN_plp-_mhxkHgIww"
ADMIN_ID = 8561804900

# --- Вспомогательная функция для получения user_id из разных форматов ---
async def resolve_user_id(update: Update, context: ContextTypes.DEFAULT_TYPE, target: str = None):
    """Пытается получить user_id из: реплая, юзернейма, прямого ID."""
    # Если есть реплай (ответ на сообщение)
    if update.message.reply_to_message:
        return update.message.reply_to_message.from_user.id
    
    # Если передан target
    if target:
        target = target.strip()
        # Если это число — считаем ID
        if target.isdigit():
            return int(target)
        # Если это @username
        if target.startswith('@'):
            username = target[1:]
            try:
                # Пробуем найти участника по username (работает только если бот видит чат)
                chat = update.effective_chat
                admins = await context.bot.get_chat_administrators(chat.id)
                for admin in admins:
                    if admin.user.username and admin.user.username.lower() == username.lower():
                        return admin.user.id
                # Если не админ, можно попробовать других участников, но API не даёт список всех.
                # Простой вариант: попросить пользователя написать в чат, чтобы бот его запомнил.
                await update.message.reply_text(f"❌ Не могу найти @{username}. Попросите пользователя написать хоть одно сообщение в чат, затем повторите команду.")
                return None
            except Exception as e:
                await update.message.reply_text(f"Ошибка поиска: {e}")
                return None
    return None

# --- Обработчик команд с точкой и слешем (общий) ---
async def handle_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    
    text = update.message.text.strip()
    # Поддерживаем и /mute, и .мут
    if text.startswith(('.мут', '/mute')):
        parts = text.split()
        if len(parts) == 1:
            # Нет аргументов — пробуем реплай
            user_id = await resolve_user_id(update, context)
            if not user_id:
                await update.message.reply_text("❗ Укажите пользователя: .мут @username 1h или ответьте на сообщение и напишите .мут 1h")
                return
            duration = "1h"  # по умолчанию час
        elif len(parts) == 2:
            # Может быть .мут 1h (реплай) или .мут @username
            if parts[1][-1] in ('h','m','s') and parts[1][:-1].isdigit():
                # Это длительность
                user_id = await resolve_user_id(update, context)
                if not user_id:
                    await update.message.reply_text("❗ Ответьте на сообщение пользователя, чтобы замутить.")
                    return
                duration = parts[1]
            else:
                # Это юзернейм или ID
                user_id = await resolve_user_id(update, context, parts[1])
                if not user_id:
                    return
                duration = "1h"
        else:  # 3+ частей: .мут @username 1h
            user_id = await resolve_user_id(update, context, parts[1])
            if not user_id:
                return
            duration = parts[2]
        
        # Парсим длительность
        dur = duration
        if dur.endswith('h'):
            sec = int(dur[:-1]) * 3600
            text_dur = f"{dur[:-1]} час(ов)"
        elif dur.endswith('m'):
            sec = int(dur[:-1]) * 60
            text_dur = f"{dur[:-1]} минут"
        elif dur.endswith('s'):
            sec = int(dur[:-1])
            text_dur = f"{dur[:-1]} секунд"
        else:
            await update.message.reply_text("Неверный формат. Используйте: 1h, 30m, 15s")
            return
        
        try:
            await context.bot.restrict_chat_member(
                update.effective_chat.id, user_id,
                ChatPermissions(can_send_messages=False),
                until_date=datetime.utcnow() + timedelta(seconds=sec)
            )
            await update.message.reply_text(f"🔇 Пользователь замучен на {text_dur}")
        except Exception as e:
            await update.message.reply_text(f"Ошибка: {e}")
    
    elif text.startswith(('.размут', '/unmute')):
        parts = text.split()
        user_id = await resolve_user_id(update, context, parts[1] if len(parts)>1 else None)
        if not user_id:
            await update.message.reply_text("❗ Укажите пользователя: .размут @username или ответьте на его сообщение.")
            return
        try:
            await context.bot.restrict_chat_member(
                update.effective_chat.id, user_id,
                ChatPermissions(can_send_messages=True)
            )
            await update.message.reply_text(f"🔊 Пользователь размучен")
        except Exception as e:
            await update.message.reply_text(f"Ошибка: {e}")
    
    elif text.startswith(('.бан', '/ban')):
        parts = text.split()
        user_id = await resolve_user_id(update, context, parts[1] if len(parts)>1 else None)
        if not user_id:
            await update.message.reply_text("❗ Укажите пользователя: .бан @username или ответьте на его сообщение.")
            return
        try:
            await context.bot.ban_chat_member(update.effective_chat.id, user_id)
            await update.message.reply_text(f"🔨 Пользователь забанен")
        except Exception as e:
            await update.message.reply_text(f"Ошибка: {e}")
    
    elif text.startswith(('.разбан', '/unban')):
        parts = text.split()
        user_id = await resolve_user_id(update, context, parts[1] if len(parts)>1 else None)
        if not user_id:
            await update.message.reply_text("❗ Укажите пользователя: .разбан @username")
            return
        try:
            await context.bot.unban_chat_member(update.effective_chat.id, user_id)
            await update.message.reply_text(f"🟢 Пользователь разбанен (может зайти по ссылке)")
        except Exception as e:
            await update.message.reply_text(f"Ошибка: {e}")

# --- Команда /start (тоже обрабатывается) ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        return
    await update.message.reply_text(
        "✅ Бот-администратор.\n\n"
        "Команды (можно с точкой или слешем):\n"
        "• .мут 1h         — замутить пользователя, на чьё сообщение ответили\n"
        "• .мут @username 1h\n"
        "• .мут ID 1h\n"
        "• .размут (по реплаю или @username)\n"
        "• .бан (по реплаю или @username)\n"
        "• .разбан (по @username)\n"
        "Примеры: .мут 30m, .мут @durov 2h"
    )

# --- Веб-сервер для Render (чтобы не ругался на порты) ---
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
    
    # Убиваем старые webhook
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(app.bot.delete_webhook(drop_pending_updates=True))
    
    # Обработчики
    app.add_handler(CommandHandler("start", start))
    # Ловим все текстовые сообщения (кроме команд) и проверяем, не начинаются ли они с точки
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_command))
    
    print("✅ Бот запущен (мут/бан по реплаю, юзернейму, ID)")
    app.run_polling()

if __name__ == "__main__":
    main()
