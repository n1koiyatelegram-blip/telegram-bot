import asyncio
import json
import os
import re
from datetime import datetime, timedelta
from threading import Thread
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse

from telegram import Update, ChatPermissions
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# ===== КОНФИГУРАЦИЯ =====
TOKEN = "8924072551:AAF5hfJNcEA4eRxbcM9sa3nt3-SXgZacmCY"
ADMIN_ID = 8561804900  # ваш Telegram ID

WARN_FILE = "warnings.json"
USER_CACHE_FILE = "user_cache.json"

ALLOWED_DOMAINS = ['t.me', 'telegram.me']
BLOCK_SHORT_LINKS = True
SHORT_LINK_DOMAINS = ['bit.ly', 'goo.gl', 'tinyurl.com', 'clck.ru', 'shorturl.at']

# ===== КЭШ ПОЛЬЗОВАТЕЛЕЙ =====
def load_user_cache():
    if os.path.exists(USER_CACHE_FILE):
        with open(USER_CACHE_FILE, "r") as f:
            return json.load(f)
    return {}

def save_user_cache(cache):
    with open(USER_CACHE_FILE, "w") as f:
        json.dump(cache, f, indent=2)

def update_user_cache(username, user_id):
    if not username:
        return
    cache = load_user_cache()
    cache[username.lower()] = user_id
    save_user_cache(cache)

# ===== ПРЕДУПРЕЖДЕНИЯ =====
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
    if update.message and update.message.reply_to_message:
        user = update.message.reply_to_message.from_user
        if user.username:
            update_user_cache(user.username, user.id)
        return user.id
    if target:
        target = target.strip()
        if target.isdigit():
            return int(target)
        if target.startswith('@'):
            username = target[1:].lower()
            cache = load_user_cache()
            if username in cache:
                return cache[username]
            try:
                admins = await context.bot.get_chat_administrators(update.effective_chat.id)
                for admin in admins:
                    if admin.user.username and admin.user.username.lower() == username:
                        update_user_cache(admin.user.username, admin.user.id)
                        return admin.user.id
            except Exception:
                pass
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=f"```\n❌ Не найден @{target}. Убедитесь, что пользователь писал сообщения в чате, или используйте ID.\n```",
                parse_mode="Markdown"
            )
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
        msg = await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=msg_text,
            parse_mode="Markdown"
        )
        asyncio.create_task(delete_after(msg))
        user = await context.bot.get_chat(user_id)
        username = f"@{user.username}" if user.username else str(user_id)
        await send_log(context,
            f"✅ *Мут*\nЧат: {update.effective_chat.title}\nПользователь: {username}\nДлительность: {dur_text}\nВремя: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        )
        return True
    except Exception as e:
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=f"```\n❌ Ошибка при муте: {e}\n```",
            parse_mode="Markdown"
        )
        return False

async def warn_user_by_id(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int, reason: str = ""):
    chat_id = update.effective_chat.id
    warnings = load_warnings()
    chat_id_str = str(chat_id)
    if chat_id_str not in warnings:
        warnings[chat_id_str] = {}
    current = warnings[chat_id_str].get(str(user_id), 0)
    new_count = current + 1
    warnings[chat_id_str][str(user_id)] = new_count
    save_warnings(warnings)

    try:
        user = await context.bot.get_chat(user_id)
        if user.username:
            user_display = f"@{user.username}"
        else:
            user_display = user.first_name
    except:
        user_display = str(user_id)

    if new_count == 1:
        text = (
            f"```\n⚠️ ПРЕДУПРЕЖДЕНИЕ 1/3 для {user_display}\n"
            f"Следующее предупреждение повлечёт мут на 30 минут.\n{reason}\n```"
        )
        await context.bot.send_message(chat_id=chat_id, text=text, parse_mode="Markdown")
        await send_log(context, f"⚠️ Предупреждение 1/3 для {user_display} (причина: {reason})")
    elif new_count == 2:
        until = datetime.utcnow() + timedelta(minutes=30)
        try:
            await context.bot.restrict_chat_member(
                chat_id, user_id,
                ChatPermissions(can_send_messages=False),
                until_date=until
            )
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"```\n⚠️ ПРЕДУПРЕЖДЕНИЕ 2/3 для {user_display}\n🔇 Пользователь замучен на 30 минут.\n```",
                parse_mode="Markdown"
            )
        except Exception as e:
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"```\n❌ Ошибка при муте: {e}\n```",
                parse_mode="Markdown"
            )
        await send_log(context, f"⚠️ Предупреждение 2/3 + мут 30 мин для {user_display}")
    else:
        until = datetime.utcnow() + timedelta(hours=2)
        try:
            await context.bot.restrict_chat_member(
                chat_id, user_id,
                ChatPermissions(can_send_messages=False),
                until_date=until
            )
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"```\n⚠️⚠️⚠️ ТРЕТЬЕ ПРЕДУПРЕЖДЕНИЕ для {user_display}\n🔇 Пользователь замучен на 2 часа.\n```",
                parse_mode="Markdown"
            )
        except Exception as e:
            await context.bot.send_message(
                chat_id=chat_id,
                text=f"```\n❌ Ошибка при муте: {e}\n```",
                parse_mode="Markdown"
            )
        warnings[chat_id_str][str(user_id)] = 0
        save_warnings(warnings)
        await send_log(context, f"⚠️ Третье предупреждение + мут 2 часа для {user_display}")

def extract_domain(url: str) -> str:
    parsed = urlparse(url)
    domain = parsed.netloc or parsed.path
    domain = domain.replace('www.', '').lower()
    return domain

async def handle_spam_links(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not update.message or not update.message.text:
        return
    if update.effective_user.id == ADMIN_ID:
        return
    text = update.message.text
    url_pattern = re.compile(r'https?://\S+|www\.\S+')
    urls = url_pattern.findall(text)
    if not urls:
        return
    spam = False
    for url in urls:
        domain = extract_domain(url)
        if BLOCK_SHORT_LINKS and domain in SHORT_LINK_DOMAINS:
            spam = True
            break
        if domain not in ALLOWED_DOMAINS:
            spam = True
            break
    if spam:
        await warn_user_by_id(update, context, update.effective_user.id, reason="Спам-ссылка (запрещённый домен)")
        try:
            await update.message.delete()
        except Exception as e:
            await send_log(context, f"Не удалось удалить сообщение: {e}")

# ===== ОСНОВНЫЕ КОМАНДЫ =====
async def warn_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="```\n⛔ Нет прав.\n```",
            parse_mode="Markdown"
        )
        return
    if not update.message.reply_to_message:
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="```\n❌ Ответьте на сообщение пользователя.\n```",
            parse_mode="Markdown"
        )
        return
    user_id = update.message.reply_to_message.from_user.id
    user = update.message.reply_to_message.from_user
    if user.username:
        update_user_cache(user.username, user_id)
    if user.username:
        user_display = f"@{user.username}"
    else:
        user_display = user.first_name
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
            f"```\n⚠️ ПРЕДУПРЕЖДЕНИЕ 1/3 для {user_display}\n"
            "Следующее предупреждение повлечёт мут на 30 минут.\n"
            "```"
        )
        await context.bot.send_message(chat_id=update.effective_chat.id, text=text, parse_mode="Markdown")
        await send_log(context, f"⚠️ Предупреждение 1/3 для {user_display}")
    elif new_count == 2:
        await apply_mute(update, context, user_id, timedelta(minutes=30),
                         f"⚠️ ПРЕДУПРЕЖДЕНИЕ 2/3 для {user_display}")
        text = f"```\n⚠️⚠️ Для {user_display} при следующем предупреждении будет выдан мут на 2 часа.\n```"
        await context.bot.send_message(chat_id=update.effective_chat.id, text=text, parse_mode="Markdown")
        await send_log(context, f"⚠️ Предупреждение 2/3 + мут 30 мин для {user_display}")
    else:
        await apply_mute(update, context, user_id, timedelta(hours=2),
                         f"⚠️⚠️⚠️ ТРЕТЬЕ ПРЕДУПРЕЖДЕНИЕ для {user_display}")
        warnings[chat_id][str(user_id)] = 0
        save_warnings(warnings)
        await send_log(context, f"⚠️ Третье предупреждение + мут 2 часа для {user_display}")

async def reset_warns(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="```\n⛔ Нет прав.\n```",
            parse_mode="Markdown"
        )
        return
    target = None
    if len(context.args) > 0:
        target = context.args[0]
    user_id = await resolve_user_id(update, context, target)
    if not user_id:
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
    user = await context.bot.get_chat(user_id)
    user_display = f"@{user.username}" if user.username else str(user_id)
    if chat_id_str in warnings and str(user_id) in warnings[chat_id_str]:
        del warnings[chat_id_str][str(user_id)]
        save_warnings(warnings)
        await context.bot.send_message(
            chat_id=chat_id,
            text="```\n✅ Предупреждения сброшены, мут снят.\n```",
            parse_mode="Markdown"
        )
        await send_log(context, f"🔄 Сброс предупреждений и снятие мута для {user_display}")
    else:
        await context.bot.send_message(
            chat_id=chat_id,
            text="```\n✅ Мут снят (предупреждений не было).\n```",
            parse_mode="Markdown"
        )
        await send_log(context, f"🔄 Снятие мута для {user_display}")

async def handle_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    if not text.startswith(('.мут', '.размут', '.бан', '.разбан', '.пред', '.сброс', '.снять_пред')):
        return
    if update.effective_user.id != ADMIN_ID:
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="```\n⛔ Нет прав.\n```",
            parse_mode="Markdown"
        )
        return
    success = False
    try:
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
                await context.bot.send_message(
                    chat_id=update.effective_chat.id,
                    text=f"```\n❌ {dur_text}\n```",
                    parse_mode="Markdown"
                )
                return
            until = datetime.utcnow() + delta
            await context.bot.restrict_chat_member(
                update.effective_chat.id, uid,
                ChatPermissions(can_send_messages=False),
                until_date=until
            )
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=f"```\n🔇 Пользователь замучен на {dur_text}\n```",
                parse_mode="Markdown"
            )
            user = await context.bot.get_chat(uid)
            username = f"@{user.username}" if user.username else str(uid)
            await send_log(context, f"🔨 Мут для {username} на {dur_text} в чате {update.effective_chat.title}")
            success = True
        elif text.startswith(('.размут', '/unmute')):
            parts = text.split()
            uid = await resolve_user_id(update, context, parts[1] if len(parts)>1 else None)
            if not uid: return
            await context.bot.restrict_chat_member(
                update.effective_chat.id, uid,
                ChatPermissions(can_send_messages=True)
            )
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="```\n🔊 Пользователь размучен\n```",
                parse_mode="Markdown"
            )
            user = await context.bot.get_chat(uid)
            username = f"@{user.username}" if user.username else str(uid)
            await send_log(context, f"🔊 Снятие мута с {username} в чате {update.effective_chat.title}")
            success = True
        elif text.startswith(('.бан', '/ban')):
            parts = text.split()
            uid = await resolve_user_id(update, context, parts[1] if len(parts)>1 else None)
            if not uid: return
            await context.bot.ban_chat_member(update.effective_chat.id, uid, revoke_messages=True)
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="```\n🔨 Пользователь забанен навсегда\n```",
                parse_mode="Markdown"
            )
            user = await context.bot.get_chat(uid)
            username = f"@{user.username}" if user.username else str(uid)
            await send_log(context, f"🔨 Бан {username} в чате {update.effective_chat.title}")
            success = True
        elif text.startswith(('.разбан', '/unban')):
            parts = text.split()
            uid = await resolve_user_id(update, context, parts[1] if len(parts)>1 else None)
            if not uid: return
            await context.bot.unban_chat_member(update.effective_chat.id, uid)
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="```\n🟢 Пользователь разбанен\n```",
                parse_mode="Markdown"
            )
            user = await context.bot.get_chat(uid)
            username = f"@{user.username}" if user.username else str(uid)
            await send_log(context, f"🟢 Разбан {username} в чате {update.effective_chat.title}")
            success = True
        elif text.startswith('.пред'):
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
    except Exception as e:
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=f"```\n❌ Ошибка: {e}\n```",
            parse_mode="Markdown"
        )
    if success:
        try:
            await update.message.delete()
        except Exception:
            pass

async def update_cache(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message and update.message.from_user and update.message.from_user.username:
        update_user_cache(update.message.from_user.username, update.message.from_user.id)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID:
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text="```\n⛔ Нет прав.\n\nПо вопросам: [Мой Telegram](https://t.me/ваш_username)\n```",
            parse_mode="Markdown"
        )
        return
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text="```\n"
        "✅ БОТ-АДМИНИСТРАТОР\n\n"
        "Команды (с точкой):\n"
        "• .мут 1мин (ответом или @username)\n"
        "• .мут @username 2ч\n"
        "• .размут @username\n"
        "• .бан @username\n"
        "• .разбан @username\n"
        "• .пред (ответом) — предупреждения\n"
        "• .сброс / .снять_пред — сброс и снятие мута\n\n"
        "СИСТЕМА ПРЕДУПРЕЖДЕНИЙ:\n"
        "1-е — уведомление\n"
        "2-е — мут 30 мин\n"
        "3-е — мут 2 часа + сброс\n\n"
        "ЗАЩИТА ОТ СПАМ-ССЫЛОК:\n"
        "Сообщения со ссылками на запрещённые домены удаляются, отправитель получает предупреждение.\n"
        "```\n\n"
        "[Мой Telegram](https://t.me/ваш_username)",
        parse_mode="Markdown"
    )

# ===== ВЕБ-СЕРВЕР =====
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
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, update_cache), group=0)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_spam_links), group=1)
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_command), group=2)
    print("✅ Бот запущен с исправленной обработкой Markdown.")
    app.run_polling()

if __name__ == "__main__":
    main()
