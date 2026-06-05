import asyncio
import json
import os
from datetime import datetime, timedelta
from threading import Thread
from http.server import HTTPServer, BaseHTTPRequestHandler
from telegram import Update, ChatPermissions
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

TOKEN = "8924072551:AAF5hfJNcEA4eRxbcM9sa3nt3-SXgZacmCY"
ADMIN_ID = 8561804900

WARN_FILE = "warnings.json"

def load_warnings():
    if os.path.exists(WARN_FILE):
        with open(WARN_FILE, "r") as f:
            return json.load(f)
    return {}

def save_warnings(warnings):
    with open(WARN_FILE, "w") as f:
        json.dump(warnings, f, indent=2)

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

async def apply_mute(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int, duration: timedelta, reason: str):
    until = datetime.utcnow() + duration
    try:
        await context.bot.restrict_chat_member(
            update.effective_chat.id, user_id,
            ChatPermissions(can_send_messages=False),
            until_date=until
        )
        minutes = int(duration.total_seconds() // 60)
        if minutes == 30:
            dur_text = "30 минут"
        elif minutes == 120:
            dur_text = "2 часа"
        else:
            dur_text = f"{minutes} минут"
        await update.message.reply_text(f"{reason} 🔇 Пользователь замучен на {dur_text}.")
        return True
    except Exception as e:
        await update.message.reply_text(f"Ошибка при муте: {e}")
        return False

async def warn_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("⛔ Нет прав.")
        return
    if not update.message.reply_to_message:
        await update.message.reply_text("❌ Ответьте на сообщение пользователя, которому хотите выдать предупреждение.")
        return
    user_id = update.message.reply_to_message.from_user.id
    chat_id = str(update.effective_chat.id)

    warnings = load_warnings()
    if chat_id not in warnings:
        warnings[chat_id] = {}
    current = warnings[chat_id].get(str(user_id), 0)
    new_count = current + 1
    warnings[chat_id][str(user_id)] = new_count
    save_warnings(warnings)

    if new_count == 1:
        await update.message.reply_text(
            "⚠️ Предупреждение 1/3.\n"
            "Следующее предупреждение повлечёт мут на 30 минут."
        )
    elif new_count == 2:
        await apply_mute(update, context, user_id, timedelta(minutes=30),
                         "⚠️ Предупреждение 2/3.")
        await update.message.reply_text(
            "⚠️⚠️ При следующем (третьем) предупреждении будет выдан мут на 2 часа."
        )
    else:  # new_count >= 3
        await apply_mute(update, context, user_id, timedelta(hours=2),
                         "⚠️⚠️⚠️ Третье предупреждение.")
        # Сбрасываем счётчик после третьего предупреждения
        warnings[chat_id][str(user_id)] = 0
        save_warnings(warnings)

async def reset_warns(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("⛔ Нет прав.")
        return
    target = None
    if len(context.args) > 0:
        target = context.args[0]
    user_id = await resolve_user_id(update, context, target)
    if not user_id:
        await update.message.reply_text("❌ Укажите пользователя (ответом на сообщение или @username/ID).")
        return
    chat_id = str(update.effective_chat.id)
    warnings = load_warnings()
    if chat_id in warnings and str(user_id) in warnings[chat_id]:
        del warnings[chat_id][str(user_id)]
        save_warnings(warnings)
        await update.message.reply_text("✅ Предупреждения для пользователя сброшены.")
    else:
        await update.message.reply_text("❌ У пользователя нет предупреждений.")

async def handle_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("⛔ Нет прав.")
        return
    text = update.message.text.strip()
    if not text:
        return

    # Обработка .пред и .сброс через единый обработчик
    if text.startswith(('.пред', '/пред')):
        await warn_command(update, context)
        return
    if text.startswith(('.сброс', '.снять_пред', '/сброс', '/снять_пред')):
        await reset_warns(update, context)
        return

    # Мут
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

    # Размут
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

    # Бан
    elif text.startswith(('.бан', '/ban')):
        parts = text.split()
        uid = await resolve_user_id(update, context, parts[1] if len(parts)>1 else None)
        if not uid: return
        try:
            await context.bot.ban_chat_member(update.effective_chat.id, uid, revoke_messages=True)
            await update.message.reply_text("🔨 Пользователь забанен навсегда")
        except Exception as e:
            await update.message.reply_text(f"Ошибка: {e}")

    # Разбан
    elif text.startswith(('.разбан', '/unban')):
        parts = text.split()
        uid = await resolve_user_id(update, context, parts[1] if len(parts)>1 else None)
        if not uid: return
        try:
            await context.bot.unban_chat_member(update.effective_chat.id, uid)
            await update.message.reply_text("🟢 Пользователь разбанен (может зайти по ссылке)")
        except Exception as e:
            await update.message.reply_text(f"Ошибка: {e}")

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
        "• .разбан @username\n"
        "• .пред        (ответьте на сообщение) — система предупреждений\n"
        "• .сброс или .снять_пред @username — сбросить предупреждения\n\n"
        "Система предупреждений:\n"
        "1-е — только уведомление\n"
        "2-е — мут 30 мин\n"
        "3-е — мут 2 часа, счётчик сбрасывается\n\n"
        "Форматы времени: 1мин, 2ч, 3д, 1нед, 30сек"
    )

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
    # Все текстовые сообщения обрабатываются handle_command (включая .пред, .сброс, .мут и т.д.)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_command))
    print("✅ Бот запущен с системой предупреждений (только точка и слеш для /start)")
    app.run_polling()

if __name__ == "__main__":
    main()
