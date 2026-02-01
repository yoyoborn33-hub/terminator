import asyncio
import logging
import random
import os
import sys
from collections import defaultdict
from aiohttp import web

from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import Message
from aiogram.enums import ChatMemberStatus

# --- КОНФИГУРАЦИЯ ---
# БЕЗОПАСНОСТЬ: Токен теперь берется ТОЛЬКО из переменных окружения.
# Если ты запускаешь бота на компьютере, тебе нужно либо создать .env файл,
# либо временно вписать токен ниже, но НЕ ЗАБУДЬ УДАЛИТЬ перед загрузкой на GitHub!
TOKEN = os.getenv("BOT_TOKEN")

# Простая проверка, чтобы бот не падал с непонятной ошибкой, если токена нет
if not TOKEN:
    print("ОШИБКА: Токен не найден! Установите переменную окружения BOT_TOKEN.")
    # Для локального теста (на своем ПК) можешь раскомментировать строку ниже и вставить токен.
    # TOKEN = "ТВОЙ_ТОКЕН_ЗДЕСЬ" 
    
    # Если токен всё еще пустой, останавливаем программу
    if not TOKEN:
        sys.exit(1)

# Настройка логирования
logging.basicConfig(level=logging.INFO)

# Инициализация бота и диспетчера
bot = Bot(token=TOKEN)
dp = Dispatcher()

# --- ЛОГИКА "МОЗГА" (ЦЕПИ МАРКОВА) ---
markov_chain = defaultdict(list)
START_WORD = "___START___"
END_WORD = "___END___"

def train_brain(text):
    """Обучает бота новым словам из сообщения"""
    words = text.split()
    if len(words) < 2:
        return

    # Добавляем стартовую связь
    markov_chain[START_WORD].append(words[0])

    # Связываем слова друг с другом
    for i in range(len(words) - 1):
        markov_chain[words[i]].append(words[i + 1])
    
    # Добавляем конечную связь
    markov_chain[words[-1]].append(END_WORD)

def generate_sentence():
    """Генерирует предложение на основе изученного"""
    if not markov_chain.get(START_WORD):
        return "Я еще слишком мало знаю..."

    word = random.choice(markov_chain[START_WORD])
    sentence = [word]

    # Генерируем цепочку (максимум 30 слов)
    for _ in range(30):
        next_words = markov_chain.get(word)
        if not next_words:
            break
        
        word = random.choice(next_words)
        if word == END_WORD:
            break
        sentence.append(word)

    return " ".join(sentence)

# --- ХЕНДЛЕРЫ (КОМАНДЫ) ---

@dp.message(Command("start"))
async def cmd_start(message: Message):
    await message.answer("Привет! Я учусь говорить как вы, а еще могу банить плохих парней. Просто добавь меня в чат и дай права админа.")

@dp.message(Command("ban"))
async def cmd_ban(message: Message):
    """Команда /ban (работает только в ответ на сообщение)"""
    if not message.reply_to_message:
        await message.reply("Эту команду нужно писать в ответ на сообщение нарушителя.")
        return

    # Проверка прав администратора у того, кто вызывает команду
    user_status = await bot.get_chat_member(message.chat.id, message.from_user.id)
    if user_status.status not in [ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.CREATOR]:
        await message.reply("У тебя нет прав админа, чтобы банить людей!")
        return

    # Проверка прав бота
    bot_status = await bot.get_chat_member(message.chat.id, bot.id)
    if not bot_status.can_restrict_members and bot_status.status != ChatMemberStatus.ADMINISTRATOR:
        await message.reply("Дайте мне права администратора (банить пользователей), чтобы я мог это сделать.")
        return

    try:
        user_to_ban = message.reply_to_message.from_user
        await bot.ban_chat_member(message.chat.id, user_to_ban.id)
        await message.answer(f"Пользователь {user_to_ban.full_name} был забанен! 🔨")
    except Exception as e:
        await message.reply(f"Не удалось забанить: {e}")

# --- ОБРАБОТКА ОБЫЧНЫХ СООБЩЕНИЙ (ОБУЧЕНИЕ) ---
@dp.message(F.text)
async def chat_handler(message: Message):
    # Не учиться на командах
    if message.text.startswith("/"):
        return

    # 1. Обучение
    train_brain(message.text)

    # 2. Ответ бота
    should_reply = False
    
    if message.chat.type == 'private':
        should_reply = True
    elif f"@{bot.id}" in message.text or (message.reply_to_message and message.reply_to_message.from_user.id == bot.id):
        should_reply = True
    elif random.random() < 0.10: # 10% шанс ответить
        should_reply = True

    if should_reply:
        text = generate_sentence()
        await message.reply(text)

# --- ВЕБ-СЕРВЕР (Для работы 24/7 на Render) ---
async def handle(request):
    return web.Response(text="I am alive")

async def start_server():
    app = web.Application()
    app.router.add_get('/', handle)
    port = int(os.environ.get("PORT", 8080))
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "0.0.0.0", port)
    await site.start()

# --- ЗАПУСК ---
async def main():
    print("Бот запущен...")
    # Удаляем вебхуки и запускаем всё вместе
    await bot.delete_webhook(drop_pending_updates=True)
    
    await asyncio.gather(
        dp.start_polling(bot),
        start_server()
    )

if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())
