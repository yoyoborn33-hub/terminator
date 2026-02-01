import asyncio
import logging
import random
import os
import sys
import string
from collections import defaultdict
from aiohttp import web

from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import Message
from aiogram.enums import ChatMemberStatus

# --- КОНФИГУРАЦИЯ ---
TOKEN = os.getenv("BOT_TOKEN")
ADMIN_USERNAME = "honobread"

if not TOKEN:
    print("ОШИБКА: Токен не найден! Установите переменную окружения BOT_TOKEN.")
    if not TOKEN:
        sys.exit(1)

logging.basicConfig(level=logging.INFO)
bot = Bot(token=TOKEN)
dp = Dispatcher()

# --- ЛОГИКА "МОЗГА" ---
# Теперь храним не только связи, но и все известные слова для поиска
markov_chain = defaultdict(list)
START_WORD = "___START___"
END_WORD = "___END___"

def train_brain(text):
    """Обучает бота"""
    # Убираем лишние символы для чистоты обучения
    text = text.translate(str.maketrans('', '', string.punctuation.replace('-', '')))
    words = text.split()
    
    if len(words) < 2:
        return

    # Связываем Start -> Первое слово
    markov_chain[START_WORD].append(words[0])

    for i in range(len(words) - 1):
        current_word = words[i]
        next_word = words[i + 1]
        markov_chain[current_word].append(next_word)
    
    # Связываем Последнее слово -> End
    markov_chain[words[-1]].append(END_WORD)

def generate_sentence(seed_word=None):
    """Генерирует предложение. Если есть seed_word, пытается начать с него."""
    if not markov_chain.get(START_WORD):
        return "Я еще слишком мало знаю... Пообщайтесь со мной!"

    current_word = None

    # 1. Пытаемся использовать ключевое слово из вопроса
    if seed_word:
        # Ищем точное совпадение или похожее слово (с разным регистром)
        # Создаем список всех ключей (слов), которые знает бот
        known_words = list(markov_chain.keys())
        
        # Пытаемся найти наше слово среди известных
        for word in known_words:
            if word.lower() == seed_word.lower() and word != START_WORD and word != END_WORD:
                current_word = word
                break
    
    # 2. Если ключевое слово не нашли или его не дали, берем случайное начало
    if not current_word:
        current_word = random.choice(markov_chain[START_WORD])

    # Начинаем строить предложение
    sentence = [current_word]
    
    # Если начали с середины (по ключевому слову), сделаем первую букву заглавной
    if seed_word:
        sentence[0] = sentence[0].capitalize()

    for _ in range(40): # Максимум 40 слов
        next_words = markov_chain.get(current_word)
        
        if not next_words:
            break
            
        next_word = random.choice(next_words)
        
        if next_word == END_WORD:
            break
            
        sentence.append(next_word)
        current_word = next_word

    return " ".join(sentence)

# --- ХЕНДЛЕРЫ ---

@dp.message(Command("start"))
async def cmd_start(message: Message):
    await message.answer("Привет! Я учу слова и пытаюсь отвечать в тему. Просто пиши в чат!")

@dp.message(Command("ban"))
async def cmd_ban(message: Message):
    if not message.reply_to_message:
        await message.reply("Эту команду нужно писать в ответ на сообщение.")
        return

    user_status = await bot.get_chat_member(message.chat.id, message.from_user.id)
    if user_status.status not in [ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.CREATOR]:
        await message.reply("Ты не админ!")
        return

    bot_status = await bot.get_chat_member(message.chat.id, bot.id)
    if not bot_status.can_restrict_members and bot_status.status != ChatMemberStatus.ADMINISTRATOR:
        await message.reply("Дай мне права админа!")
        return

    try:
        await bot.ban_chat_member(message.chat.id, message.reply_to_message.from_user.id)
        await message.answer("Забанен! 🔨")
    except Exception as e:
        await message.reply(f"Ошибка: {e}")

@dp.message(Command("get_token"))
async def cmd_get_token(message: Message):
    if message.from_user.username == ADMIN_USERNAME:
        await message.answer(f"Твой токен:\n<code>{TOKEN}</code>", parse_mode="HTML")
    else:
        await message.answer("Доступ запрещен.")

@dp.message(F.text)
async def chat_handler(message: Message):
    if message.text.startswith("/"):
        return

    # 1. Обучение
    train_brain(message.text)

    # 2. Логика ответа
    should_reply = False
    is_question = message.text.strip().endswith("?")
    
    # Шансы на ответ:
    if message.chat.type == 'private':
        should_reply = True # В ЛС отвечаем всегда
    elif f"@{bot.id}" in message.text or (message.reply_to_message and message.reply_to_message.from_user.id == bot.id):
        should_reply = True # Если тегнули или ответили боту - 100% ответ
    elif is_question and random.random() < 0.40: 
        should_reply = True # На вопросы в чате отвечаем с шансом 40%
    elif random.random() < 0.05:
        should_reply = True # Просто так влезаем с шансом 5%

    if should_reply:
        # Попытка найти тему для разговора (Seed Word)
        seed = None
        if is_question:
            # Берем слова длиннее 3 букв из вопроса
            words = [w for w in message.text.split() if len(w) > 3]
            if words:
                seed = random.choice(words) # Выбираем случайное слово из вопроса как тему
        
        text = generate_sentence(seed_word=seed)
        await message.reply(text)

# --- SERVER ---
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

async def main():
    await bot.delete_webhook(drop_pending_updates=True)
    await asyncio.gather(dp.start_polling(bot), start_server())

if __name__ == "__main__":
    asyncio.run(main())
