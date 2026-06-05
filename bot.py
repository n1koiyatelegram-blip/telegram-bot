import asyncio
import json
import os
from datetime import datetime, timedelta
from threading import Thread
from http.server import HTTPServer, BaseHTTPRequestHandler
from telegram import Update, ChatPermissions
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

TOKEN = "8924072551:AAF5hfJNcEA4eRxbcM9sa3nt3-SXgZacmCY"
ADMIN_ID = 8561804900  # ваш Telegram ID

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
    # ... (без изменений, как в предыдущем коде)
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
                msg = await update.message.reply_text(f"```\n❌ Не найден @{username}.\n```", parse_mode="Markdown")
                asyncio.create_task(delete_after(msg))
            except Exception as e:
                msg = await update.message.reply_text(f"```\n❌ Ошибка поиска: {e}\n```", parse_mode="Markdown")
                asyncio.create_task(delete_after(msg))
            return None
    return None

async def delete_after(message, delay: int = 40):
    await asyncio.sleep(delay)
    try:
        await message.delete()
    except:
        pass

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
        msg_text = f"```\n{reason}\n🔇 Пользователь замучен на {dur_text}.\n```"
        msg = await update.message.reply_text(msg_text, parse_mode="Markdown")
        asyncio.create_task(delete_after(msg))
        return True
    except Exception as e:
        msg = await update.message.reply_text(f"```\n❌ Ошибка при муте: {e}\n```", parse_mode="Markdown")
        asyncio.create_task(delete_after(msg))
        return False

async def warn_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        msg = await update.message.reply_text("```\n⛔ Нет прав.\n```", parse_mode="Markdown")
        asyncio.create_task(delete_after(msg))
        return
    if not update.message.reply_to_message:
        msg = await update.message.reply_text("```\n❌ Ответьте на сообщение пользователя.\n```", parse_mode="Markdown")
        asyncio.create_task(delete_after(msg))
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
        text = (
            "```\n"
            "⚠️ ПРЕДУПРЕЖДЕНИЕ 1/3\n"
            "Следующее предупреждение повлечёт мут на 30 минут.\n"
            "```"
        )
        msg = await update.message.reply_text(text, parse_mode="Markdown")
        asyncio.create_task(delete_after(msg))
    elif new_count == 2:
        await apply_mute(update, context, user_id, timedelta(minutes=30),
                         "⚠️ ПРЕДУПРЕЖДЕНИЕ 2/3")
        text = (
            "```\n"
            "⚠️⚠️ При следующем (третьем) предупреждении будет выдан мут на 2 часа.\n"
            "```"
        )
        msg = await update.message.reply_text(text, parse_mode="Markdown")
        asyncio.create_task(delete_after(msg))
    else:  # new_count >= 3
        await apply_mute(update, context, user_id, timedelta(hours=2),
                         "⚠️⚠️⚠️ ТРЕТЬЕ ПРЕДУПРЕЖДЕНИЕ")
        warnings[chat_id][str(user_id)] = 0
        save_warnings(warnings)

async def reset_warns(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        msg = await update.message.reply_text("```\n⛔ Нет прав.\n```", parse_mode="Markdown")
        asyncio.create_task(delete_after(msg))
        return
    target = None
    if len(context.args) > 0:
        target = context.args[0]
    user_id = await resolve_user_id(update, context, target)
    if not user_id:
        msg = await update.message.reply_text("```\n❌ Укажите пользователя (ответом или @username/ID).\n```", parse_mode="Markdown")
        asyncio.create_task(delete_after(msg))
        return
    chat_id = update.effective_chat.id
    try:
        await context.bot.restrict_chat_member(
            chat_id, user_id,
            ChatPermissions(can_send_messages=True)
        )
    except Exception:
        pass
    warnings = load_warnings()
    chat_id_str = str(chat_id)
    if chat_id_str in warnings and str(user_id) in warnings[chat_id_str]:
        del warnings[chat_id_str][str(user_id)]
        save_warnings(warnings)
        msg = await update.message.reply_text("```\n✅ Предупреждения сброшены, мут снят.\n```", parse_mode="Markdown")
    else:
        msg = await update.message.reply_text("```\n✅ Мут снят (предупреждений не было).\n```", parse_mode="Markdown")
    asyncio.create_task(delete_after(msg))

async def handle_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if not text.startswith(('.мут', '.размут', '.бан', '.разбан', '.пред', '.сброс', '.снять_пред')):
        return

    if update.effective_user.id != ADMIN_ID:
        msg = await update.message.reply_text("```\n⛔ Нет прав.\n```", parse_mode="Markdown")
        asyncio.create_task(delete_after(msg))
        return

    # Удаляем сообщение пользователя с командой (если есть права)
    try:
        await update.message.delete()
    except Exception:
        pass  # если нет прав на удаление — просто игнорируем

    # Обработка команд (код тот же, что и раньше)
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
            msg = await update.message.reply_text(f"```\n❌ {dur_text}\n```", parse_mode="Markdown")
            asyncio.create_task(delete_after(msg))
            return
        until = datetime.utcnow() + delta
        try:
            await context.bot.restrict_chat_member(
                update.effective_chat.id, uid,
                ChatPermissions(can_send_messages=False),
                until_date=until
            )
            msg = await update.message.reply_text(f"```\n🔇 Пользователь замучен на {dur_text}\n```", parse_mode="Markdown")
            asyncio.create_task(delete_after(msg))
        except Exception as e:
            msg = await update.message.reply_text(f"```\n❌ Ошибка: {e}\n```", parse_mode="Markdown")
            asyncio.create_task(delete_after(msg))

    elif text.startswith(('.размут', '/unmute')):
        parts = text.split()
        uid = await resolve_user_id(update, context, parts[1] if len(parts)>1 else None)
        if not uid: return
        try:
            await context.bot.restrict_chat_member(
                update.effective_chat.id, uid,
                ChatPermissions(can_send_messages=True)
            )
            msg = await update.message.reply_text("```\n🔊 Пользователь размучен\n```", parse_mode="Markdown")
            asyncio.create_task(delete_after(msg))
        except Exception as e:
            msg = await update.message.reply_text(f"```\n❌ Ошибка: {e}\n```", parse_mode="Markdown")
            asyncio.create_task(delete_after(msg))

    elif text.startswith(('.бан', '/ban')):
        parts = text.split()
        uid = await resolve_user_id(update, context, parts[1] if len(parts)>1 else None)
        if not uid: return
        try:
            await context.bot.ban_chat_member(update.effective_chat.id, uid, revoke_messages=True)
            msg = await update.message.reply_text("```\n🔨 Пользователь забанен навсегда\n```", parse_mode="Markdown")
            asyncio.create_task(delete_after(msg))
        except Exception as e:
            msg = await update.message.reply_text(f"```\n❌ Ошибка: {e}\n```", parse_mode="Markdown")
            asyncio.create_task(delete_after(msg))

    elif text.startswith(('.разбан', '/unban')):
        parts = text.split()
        uid = await resolve_user_id(update, context, parts[1] if len(parts)>1 else None)
        if not uid: return
        try:
            await context.bot.unban_chat_member(update.effective_chat.id, uid)
            msg = await update.message.reply_text("```\n🟢 Пользователь разбанен\n```", parse_mode="Markdown")
            asyncio.create_task(delete_after(msg))
        except Exception as e:
            msg = await update.message.reply_text(f"```\n❌ Ошибка: {e}\n```", parse_mode="Markdown")
            asyncio.create_task(delete_after(msg))

    elif text.startswith('.пред'):
        await warn_command(update, context)

    elif text.startswith(('.сброс', '.снять_пред')):
        parts = text.split()
        if len(parts) > 1:
            context.args = parts[1:]
        else:
            context.args = []
        await reset_warns(update, context)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        msg = await update.message.reply_text(
            "```\n"
            "⛔ Нет прав.\n\n"
            "По вопросам: [Мой Telegram](https://t.me/ваш_username)\n"
            "```",
            parse_mode="Markdown"
        )
        asyncio.create_task(delete_after(msg))
        return
    msg = await update.message.reply_text(
        "```\n"
        "✅ БОТ-АДМИНИСТРАТОР\n\n"
        "Команды (с точкой):\n"
        "• .мут 1мин (ответом)\n"
        "• .размут (ответом)\n"
        "• .бан (ответом)\n"
        "• .разбан (ответом)\n"
        "• .пред (ответом) — предупреждения\n"
        "• .сброс / .снять_пред — сброс и снятие мута\n\n"
        "СИСТЕМА ПРЕДУПРЕЖДЕНИЙ:\n"
        "1-е — уведомление\n"
        "2-е — мут 30 мин\n"
        "3-е — мут 2 часа + сброс\n\n"
        "Сообщения бота удаляются через 40 сек.\n"
        "```\n\n"
        "[Мой Telegram](https://t.me/ваш_username)",
        parse_mode="Markdown"
    )
    asyncio.create_task(delete_after(msg))

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
    print("✅ Бот запущен. Сообщения с командами удаляются.")
    app.run_polling()

if __name__ == "__main__":
    main()
