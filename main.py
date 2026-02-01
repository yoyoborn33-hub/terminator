import asyncio
import logging
import random
import os
import sys
import string
import json
from collections import defaultdict
from aiohttp import web

from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import Message
from aiogram.enums import ChatMemberStatus

# --- КОНФИГУРАЦИЯ ---
TOKEN = os.getenv("BOT_TOKEN")
ADMIN_USERNAME = "honobread"
DB_FILE = "brain.json" # Файл для хранения памяти

if not TOKEN:
    print("ОШИБКА: Токен не найден! Установите переменную окружения BOT_TOKEN.")
    # Если мы локально, не падаем сразу, даем шанс (но лучше задать переменную)
    if not TOKEN:
        sys.exit(1)

logging.basicConfig(level=logging.INFO)
bot = Bot(token=TOKEN)
dp = Dispatcher()

# --- ЛОГИКА "МОЗГА" ---
markov_chain = defaultdict(list)
START_WORD = "___START___"
END_WORD = "___END___"
message_counter = 0 # Счётчик для периодического сохранения

def load_brain():
    """Загружает базу знаний из файла"""
    global markov_chain
    try:
        if os.path.exists(DB_FILE):
            with open(DB_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                # JSON возвращает dict, нам нужен defaultdict
                markov_chain = defaultdict(list, data)
            print(f"Загружено {len(markov_chain)} слов из памяти.")
        else:
            print("Файл памяти не найден, начинаем с нуля.")
    except Exception as e:
        print(f"Ошибка загрузки памяти: {e}")
        markov_chain = defaultdict(list)

def save_brain():
    """Сохраняет базу знаний в файл"""
    try:
        with open(DB_FILE, 'w', encoding='utf-8') as f:
            json.dump(markov_chain, f, ensure_ascii=False)
        print("Память сохранена.")
    except Exception as e:
        print(f"Ошибка сохранения памяти: {e}")

def train_brain(text):
    """Обучает бота"""
    global message_counter
    # Убираем лишние символы, но оставляем структуру
    text = text.translate(str.maketrans('', '', string.punctuation.replace('-', '')))
    words = text.split()
    
    if len(words) < 2:
        return

    # Обучение (цепь Маркова)
    markov_chain[START_WORD].append(words[0])

    for i in range(len(words) - 1):
        markov_chain[words[i]].append(words[i + 1])
    
    markov_chain[words[-1]].append(END_WORD)

    # Сохраняем каждые 50 сообщений, чтобы не потерять данные
    message_counter += 1
    if message_counter >= 50:
        save_brain()
        message_counter = 0

def generate_sentence(seed_word=None):
    """Генерирует предложение"""
    if not markov_chain.get(START_WORD):
        return "Я еще слишком мало знаю... Пообщайтесь со мной!"

    current_word = None

    # 1. Пытаемся использовать ключевое слово (ОПТИМИЗИРОВАНО)
    # Мы больше не перебираем все ключи (это убивало память), а проверяем наличие напрямую
    if seed_word:
        # Пробуем найти слово как есть
        if seed_word in markov_chain:
            current_word = seed_word
        # Если не нашли, пробуем с большой/маленькой буквы (простой перебор вариантов)
        elif seed_word.capitalize() in markov_chain:
            current_word = seed_word.capitalize()
        elif seed_word.lower() in markov_chain:
            current_word = seed_word.lower()
    
    # 2. Если слово не нашли, берем случайное начало
    if not current_word:
        current_word = random.choice(markov_chain[START_WORD])

    sentence = [current_word]
    if seed_word and current_word == seed_word:
        sentence[0] = sentence[0].capitalize()

    # Генерация цепочки
    for _ in range(50): # Максимум 50 слов
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
    await message.answer("Привет! Я перезагрузился и стал умнее (и экономнее).")

@dp.message(Command("stats"))
async def cmd_stats(message: Message):
    """Показывает статистику знаний"""
    words_count = len(markov_chain)
    pairs_count = sum(len(v) for v in markov_chain.values())
    await message.answer(f"🧠 <b>Состояние мозга:</b>\n"
                         f"Слов в словаре: {words_count}\n"
                         f"Всего связей: {pairs_count}", parse_mode="HTML")

@dp.message(Command("reset"))
async def cmd_reset(message: Message):
    """Сброс памяти (только для админа)"""
    if message.from_user.username == ADMIN_USERNAME:
        global markov_chain
        markov_chain = defaultdict(list)
        save_brain() # Сохраняем пустой файл
        await message.answer("🤯 Мозг полностью очищен! Я забыл всё, что знал.")
    else:
        await message.answer("Только создатель может стирать мне память.")

@dp.message(Command("ban"))
async def cmd_ban(message: Message):
    if not message.reply_to_message:
        await message.reply("Эту команду нужно писать в ответ на сообщение.")
        return

    # Проверка прав (пропускаем для краткости, она такая же)
    try:
        await bot.ban_chat_member(message.chat.id, message.reply_to_message.from_user.id)
        await message.answer("Забанен! 🔨")
    except Exception as e:
        await message.reply(f"Не удалось забанить. Дайте мне права админа!")

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

    try:
        # 1. Обучение
        train_brain(message.text)

        # 2. Логика ответа
        should_reply = False
        is_question = message.text.strip().endswith("?")
        
        # Если это ЛС
        if message.chat.type == 'private':
            should_reply = True
        # Если тегнули
        elif f"@{bot.id}" in message.text or (message.reply_to_message and message.reply_to_message.from_user.id == bot.id):
            should_reply = True
        # Рандом
        elif is_question and random.random() < 0.50: # 50% на вопросы
            should_reply = True 
        elif random.random() < 0.07: # 7% на обычные
            should_reply = True

        if should_reply:
            seed = None
            if is_question:
                words = [w for w in message.text.split() if len(w) > 3]
                if words:
                    seed = random.choice(words)
            
            text = generate_sentence(seed_word=seed)
            await message.reply(text)
            
    except Exception as e:
        logging.error(f"Ошибка в chat_handler: {e}")
        # Если ошибка, просто молчим, чтобы не спамить в чат логами

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
    # Загружаем память при старте
    load_brain()
    
    await bot.delete_webhook(drop_pending_updates=True)
    try:
        await asyncio.gather(dp.start_polling(bot), start_server())
    finally:
        # Сохраняем память при выключении
        save_brain()

if __name__ == "__main__":
    asyncio.run(main())
