import asyncio
import json
import os
from datetime import datetime, timedelta
from threading import Thread
from http.server import HTTPServer, BaseHTTPRequestHandler
from telegram import Update, ChatPermissions
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

TOKEN = "8924072551:AAF5hfJNcEA4eRxbcM9sa3nt3-SXgZacmCY"
ADMIN_ID = 8561804900  # ваш ID

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
                await update.message.reply_text(f"Не найден @{username}.")
            except:
                pass
            return None
    return None

async def delete_after(message, delay: int = 40):
    await asyncio.sleep(delay)
    try:
        await message.delete()
    except:
        pass

async def send_log(context: ContextTypes.DEFAULT_TYPE, text: str):
    await context.bot.send_message(chat_id=ADMIN_ID, text=text, parse_mode="Markdown")

async def warn_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("Нет прав.")
        return
    if not update.message.reply_to_message:
        await update.message.reply_text("Ответьте на сообщение пользователя.")
        return
    user = update.message.reply_to_message.from_user
    user_id = user.id
    mention = f"[{user.first_name}](tg://user?id={user_id})"
    chat_id = str(update.effective_chat.id)
    warnings = load_warnings()
    if chat_id not in warnings:
        warnings[chat_id] = {}
    current = warnings[chat_id].get(str(user_id), 0)
    new_count = current + 1
    warnings[chat_id][str(user_id)] = new_count
    save_warnings(warnings)

    if new_count == 1:
        text = f"⚠️ Предупреждение 1/3 для {mention}\nСледующее предупреждение → мут 30 минут."
        await update.message.reply_text(text, parse_mode="Markdown")
        await send_log(context, f"Предупреждение 1/3 для {mention} в чате {update.effective_chat.title}")
    elif new_count == 2:
        # мут 30 мин
        until = datetime.utcnow() + timedelta(minutes=30)
        await context.bot.restrict_chat_member(update.effective_chat.id, user_id,
            ChatPermissions(can_send_messages=False), until_date=until)
        text = f"⚠️ Предупреждение 2/3 для {mention}\nВыдан мут на 30 минут. Следующее предупреждение → мут 2 часа."
        await update.message.reply_text(text, parse_mode="Markdown")
        await send_log(context, f"Предупреждение 2/3 + мут 30 мин для {mention} в чате {update.effective_chat.title}")
    else:
        # мут 2 часа
        until = datetime.utcnow() + timedelta(hours=2)
        await context.bot.restrict_chat_member(update.effective_chat.id, user_id,
            ChatPermissions(can_send_messages=False), until_date=until)
        text = f"⚠️⚠️⚠️ Третье предупреждение для {mention}\nВыдан мут на 2 часа."
        await update.message.reply_text(text, parse_mode="Markdown")
        await send_log(context, f"Третье предупреждение + мут 2 часа для {mention} в чате {update.effective_chat.title}")
        warnings[chat_id][str(user_id)] = 0
        save_warnings(warnings)

async def reset_warns(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("Нет прав.")
        return
    target = None
    if len(context.args) > 0:
        target = context.args[0]
    user_id = await resolve_user_id(update, context, target)
    if not user_id:
        await update.message.reply_text("Укажите пользователя (ответом или @username).")
        return
    chat_id = update.effective_chat.id
    try:
        await context.bot.restrict_chat_member(chat_id, user_id, ChatPermissions(can_send_messages=True))
    except:
        pass
    warnings = load_warnings()
    chat_id_str = str(chat_id)
    if chat_id_str in warnings and str(user_id) in warnings[chat_id_str]:
        del warnings[chat_id_str][str(user_id)]
        save_warnings(warnings)
        await update.message.reply_text("✅ Предупреждения сброшены, мут снят.")
    else:
        await update.message.reply_text("✅ Мут снят (предупреждений не было).")

async def handle_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if not text.startswith(('.мут', '.размут', '.бан', '.разбан', '.пред', '.сброс', '.снять_пред')):
        return
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("Нет прав.")
        return
    success = False
    try:
        if text.startswith('.пред'):
            await warn_command(update, context)
            success = True
        elif text.startswith(('.сброс', '.снять_пред')):
            parts = text.split()
            if len(parts) > 1:
                context.args = parts[1:]
            else:
                context.args = []
            await reset_warns(update, context)
            success = True
        elif text.startswith(('.мут', '/mute')):
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
                await update.message.reply_text(f"Ошибка: {dur_text}")
                return
            until = datetime.utcnow() + delta
            await context.bot.restrict_chat_member(update.effective_chat.id, uid,
                ChatPermissions(can_send_messages=False), until_date=until)
            await update.message.reply_text(f"🔇 Пользователь замучен на {dur_text}")
            success = True
        elif text.startswith(('.размут', '/unmute')):
            parts = text.split()
            uid = await resolve_user_id(update, context, parts[1] if len(parts)>1 else None)
            if not uid: return
            await context.bot.restrict_chat_member(update.effective_chat.id, uid,
                ChatPermissions(can_send_messages=True))
            await update.message.reply_text("🔊 Пользователь размучен")
            success = True
        elif text.startswith(('.бан', '/ban')):
            parts = text.split()
            uid = await resolve_user_id(update, context, parts[1] if len(parts)>1 else None)
            if not uid: return
            await context.bot.ban_chat_member(update.effective_chat.id, uid, revoke_messages=True)
            await update.message.reply_text("🔨 Пользователь забанен навсегда")
            success = True
        elif text.startswith(('.разбан', '/unban')):
            parts = text.split()
            uid = await resolve_user_id(update, context, parts[1] if len(parts)>1 else None)
            if not uid: return
            await context.bot.unban_chat_member(update.effective_chat.id, uid)
            await update.message.reply_text("🟢 Пользователь разбанен")
            success = True
    except Exception as e:
        await update.message.reply_text(f"Ошибка: {e}")
    if success:
        try:
            await update.message.delete()
        except:
            pass

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("Нет прав.\nПо вопросам: @ваш_username")
        return
    await update.message.reply_text(
        "Бот-администратор.\nКоманды: .мут, .размут, .бан, .разбан, .пред, .сброс"
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
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_command))
    print("Бот запущен.")
    app.run_polling()

if __name__ == "__main__":
    main()
