import asyncio
from datetime import datetime, timedelta
from threading import Thread
from http.server import HTTPServer, BaseHTTPRequestHandler
from telegram import Update, ChatPermissions
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

TOKEN = "8045822374:AAFPvLyjwCdPndVDomcN_plp-_mhxkHgIww"   # только токен, ADMIN_ID не нужен

# --- Проверка, является ли пользователь админом чата ---
async def is_chat_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    try:
        member = await context.bot.get_chat_member(chat_id, user_id)
        return member.status in ('administrator', 'creator')
    except:
        return False

# --- Парсинг длительности (русские и английские суффиксы) ---
def parse_duration(duration_str: str):
    if not duration_str:
        return None, "Не указана длительность."
    duration_str = duration_str.lower().strip()
    # Часы
    if any(duration_str.endswith(s) for s in ('h', 'ч', 'час', 'часа', 'часов')):
        val = int(''.join(filter(str.isdigit, duration_str)))
        return timedelta(hours=val), f"{val} час(ов)"
    # Минуты
    if any(duration_str.endswith(s) for s in ('m', 'мин', 'минута', 'минуты', 'минут')):
        val = int(''.join(filter(str.isdigit, duration_str)))
        return timedelta(minutes=val), f"{val} минут"
    # Секунды
    if any(duration_str.endswith(s) for s in ('s', 'сек', 'секунда', 'секунды', 'секунд')):
        val = int(''.join(filter(str.isdigit, duration_str)))
        return timedelta(seconds=val), f"{val} секунд"
    # Дни
    if any(duration_str.endswith(s) for s in ('d', 'д', 'дн', 'дня', 'дней')):
        val = int(''.join(filter(str.isdigit, duration_str)))
        return timedelta(days=val), f"{val} день(дней)"
    # Недели
    if any(duration_str.endswith(s) for s in ('w', 'нед', 'неделя', 'недели', 'недель')):
        val = int(''.join(filter(str.isdigit, duration_str)))
        return timedelta(weeks=val), f"{val} неделя(ь)"
    return None, "Используйте: 30m (мин), 2h (ч), 1d (д), 1w (нед). Пример: .мут 1мин"

# --- Получение user_id из реплая, @username или ID ---
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
                # Ищем среди администраторов (проще, чем среди всех участников)
                chat = update.effective_chat
                admins = await context.bot.get_chat_administrators(chat.id)
                for admin in admins:
                    if admin.user.username and admin.user.username.lower() == username.lower():
                        return admin.user.id
                await update.message.reply_text(f"❌ Не найден @{username}. Попросите пользователя написать в чат или используйте ID.")
                return None
            except Exception as e:
                await update.message.reply_text(f"Ошибка поиска: {e}")
                return None
    return None

# --- Обработчик команд ---
async def handle_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Проверяем, админ ли отправитель
    if not await is_chat_admin(update, context):
        await update.message.reply_text("⛔ Только администраторы чата могут использовать команды.")
        return

    text = update.message.text.strip()

    # ========== МУТ ==========
    if text.startswith(('.мут', '/mute')):
        parts = text.split()
        if len(parts) == 1:
            user_id = await resolve_user_id(update, context)
            if not user_id: return
            duration = "1h"
        elif len(parts) == 2:
            if any(parts[1].endswith(suf) for suf in ('h','m','s','d','w','ч','мин','сек','д','нед')):
                user_id = await resolve_user_id(update, context)
                if not user_id: return
                duration = parts[1]
            else:
                user_id = await resolve_user_id(update, context, parts[1])
                if not user_id: return
                duration = "1h"
        else:
            user_id = await resolve_user_id(update, context, parts[1])
            if not user_id: return
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

    # ========== РАЗМУТ ==========
    elif text.startswith(('.размут', '/unmute')):
        parts = text.split()
        user_id = await resolve_user_id(update, context, parts[1] if len(parts) > 1 else None)
        if not user_id: return
        try:
            await context.bot.restrict_chat_member(
                update.effective_chat.id, user_id,
                ChatPermissions(can_send_messages=True)
            )
            await update.message.reply_text("🔊 Пользователь размучен")
        except Exception as e:
            await update.message.reply_text(f"Ошибка: {e}")

    # ========== БАН (навсегда) ==========
    elif text.startswith(('.бан', '/ban')):
        parts = text.split()
        user_id = await resolve_user_id(update, context, parts[1] if len(parts) > 1 else None)
        if not user_id: return
        try:
            await context.bot.ban_chat_member(update.effective_chat.id, user_id, revoke_messages=True)
            await update.message.reply_text("🔨 Пользователь забанен навсегда")
        except Exception as e:
            await update.message.reply_text(f"Ошибка: {e}")

    # ========== РАЗБАН ==========
    elif text.startswith(('.разбан', '/unban')):
        parts = text.split()
        user_id = await resolve_user_id(update, context, parts[1] if len(parts) > 1 else None)
        if not user_id: return
        try:
            await context.bot.unban_chat_member(update.effective_chat.id, user_id)
            await update.message.reply_text("🟢 Пользователь разбанен (может зайти по ссылке)")
        except Exception as e:
            await update.message.reply_text(f"Ошибка: {e}")

# --- /start ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_chat_admin(update, context):
        await update.message.reply_text("⛔ Только администраторы чата могут использовать бота.")
        return
    await update.message.reply_text(
        "✅ Бот-администратор.\n\n"
        "Команды (с точкой или слешем):\n"
        "• .мут [@username/ID] [время]  — время: 1m (1мин), 2h (2ч), 1d (1д), 1w (1нед)\n"
        "• .размут [@username/ID]       — по реплаю или @\n"
        "• .бан [@username/ID]          — навсегда\n"
        "• .разбан [@username/ID]\n"
        "Примеры: .мут 1мин, .мут @user 2ч, ответом .мут 30сек"
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

def main():
    Thread(target=run_webserver, daemon=True).start()
    app = Application.builder().token(TOKEN).build()
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(app.bot.delete_webhook(drop_pending_updates=True))
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_command))
    print("✅ Бот запущен (команды доступны всем администраторам чата)")
    app.run_polling()

if __name__ == "__main__":
    main()
