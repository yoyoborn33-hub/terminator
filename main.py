import asyncio
import logging
import random
import os
import sys
import string
import json
import io
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
MAX_WORDS = 50000 # Лимит слов. 50к слов займут ~50-100МБ RAM, что безопасно для Free тарифа.

if not TOKEN:
    print("ОШИБКА: Токен не найден! Установите переменную окружения BOT_TOKEN.")
    if not TOKEN:
        sys.exit(1)

logging.basicConfig(level=logging.INFO)
bot = Bot(token=TOKEN)
dp = Dispatcher()

# --- ЛОГИКА "МОЗГА" ---
markov_chain = defaultdict(list)
START_WORD = "___START___"
END_WORD = "___END___"
message_counter = 0 
SILENT_MODE = False # Режим шпиона (по умолчанию выключен)

def load_brain():
    """Загружает базу знаний из файла"""
    global markov_chain
    try:
        if os.path.exists(DB_FILE):
            with open(DB_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
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

def clean_brain():
    """Очищает память, если она переполнена"""
    global markov_chain
    if len(markov_chain) > MAX_WORDS:
        print(f"🧹 Очистка памяти! Было слов: {len(markov_chain)}")
        # Удаляем 20% случайных слов, чтобы освободить место для новых
        # Превращаем ключи в список, чтобы выбрать случайные
        keys = list(markov_chain.keys())
        # Не удаляем спец. слова
        if START_WORD in keys: keys.remove(START_WORD)
        
        # Выбираем жертв
        keys_to_remove = random.sample(keys, int(len(keys) * 0.2))
        
        for key in keys_to_remove:
            del markov_chain[key]
            
        print(f"✨ Память очищена. Стало слов: {len(markov_chain)}")

def train_brain(text):
    """Обучает бота"""
    global message_counter
    # Очистка текста
    text = text.translate(str.maketrans('', '', string.punctuation.replace('-', '')))
    words = text.split()
    
    if len(words) < 2:
        return

    # Обучение
    markov_chain[START_WORD].append(words[0])

    for i in range(len(words) - 1):
        markov_chain[words[i]].append(words[i + 1])
    
    markov_chain[words[-1]].append(END_WORD)

    # Сохраняем каждые 50 новых фраз
    message_counter += 1
    if message_counter >= 50:
        clean_brain() # Проверяем, не пора ли почистить
        save_brain()
        message_counter = 0

def generate_sentence(seed_word=None):
    """Генерирует предложение"""
    if not markov_chain.get(START_WORD):
        return "Я еще слишком мало знаю..."

    current_word = None

    if seed_word:
        if seed_word in markov_chain:
            current_word = seed_word
        elif seed_word.capitalize() in markov_chain:
            current_word = seed_word.capitalize()
        elif seed_word.lower() in markov_chain:
            current_word = seed_word.lower()
    
    if not current_word:
        current_word = random.choice(markov_chain[START_WORD])

    sentence = [current_word]
    if seed_word and current_word == seed_word:
        sentence[0] = sentence[0].capitalize()

    for _ in range(50):
        next_words = markov_chain.get(current_word)
        if not next_words: break
        next_word = random.choice(next_words)
        if next_word == END_WORD: break
        sentence.append(next_word)
        current_word = next_word

    return " ".join(sentence)

# --- ХЕНДЛЕРЫ ---

@dp.message(Command("start"))
async def cmd_start(message: Message):
    await message.answer("Я бот-шпион. Добавь меня в чат, дай права админа и отключи Privacy Mode в BotFather.")

@dp.message(Command("silent"))
async def cmd_silent(message: Message):
    """Включает/выключает режим молчания (только учится)"""
    global SILENT_MODE
    # Разрешаем менять режим только админу бота (тебе)
    if message.from_user.username == ADMIN_USERNAME:
        SILENT_MODE = not SILENT_MODE
        status = "ВКЛЮЧЕН 🤫 (Я молчу и запоминаю)" if SILENT_MODE else "ВЫКЛЮЧЕН 🗣 (Я говорю)"
        await message.answer(f"Режим шпиона {status}")
    else:
        await message.answer("Не трогай мои настройки!")

@dp.message(Command("stats"))
async def cmd_stats(message: Message):
    words_count = len(markov_chain)
    pairs_count = sum(len(v) for v in markov_chain.values())
    mode_text = "Тихий (Шпион)" if SILENT_MODE else "Активный (Болтун)"
    # Добавили инфо о лимите
    limit_percent = round((words_count / MAX_WORDS) * 100, 1)
    await message.answer(f"🧠 <b>Мозг:</b>\nСлов: {words_count} / {MAX_WORDS} ({limit_percent}%)\nСвязей: {pairs_count}\nРежим: {mode_text}", parse_mode="HTML")

@dp.message(Command("reset"))
async def cmd_reset(message: Message):
    if message.from_user.username == ADMIN_USERNAME:
        global markov_chain
        markov_chain = defaultdict(list)
        save_brain()
        await message.answer("🤯 Память стерта.")
    else:
        await message.answer("Доступ запрещен.")

@dp.message(Command("ban"))
async def cmd_ban(message: Message):
    if not message.reply_to_message:
        await message.reply("Пиши в ответ на сообщение.")
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

# Обработка файлов .txt (для быстрого обучения)
@dp.message(F.document)
async def handle_files(message: Message):
    if message.from_user.username != ADMIN_USERNAME:
        return

    # Проверяем, что это текстовый файл
    if message.document.mime_type == "text/plain" or message.document.file_name.endswith(".txt"):
        try:
            msg = await message.answer("📥 Читаю файл... Это может занять время.")
            file_id = message.document.file_id
            file_info = await bot.get_file(file_id)
            
            # Скачиваем в память
            downloaded_file = await bot.download_file(file_info.file_path)
            content = downloaded_file.read().decode('utf-8', errors='ignore')
            
            # Обучаем построчно
            lines = content.split('\n')
            count = 0
            for line in lines:
                if line.strip():
                    train_brain(line)
                    count += 1
            
            save_brain()
            await msg.edit_text(f"✅ Файл прочитан! Изучено {count} новых фраз.")
        except Exception as e:
            await message.reply(f"Ошибка чтения файла: {e}")

@dp.message(F.text)
async def chat_handler(message: Message):
    if message.text.startswith("/"):
        return

    try:
        # 1. Обучение (работает ВСЕГДА, даже в тихом режиме)
        train_brain(message.text)

        # Если включен Тихий режим - выходим, не отвечая
        if SILENT_MODE:
            return

        # 2. Логика ответа
        should_reply = False
        is_question = message.text.strip().endswith("?")
        
        if message.chat.type == 'private':
            should_reply = True
        elif f"@{bot.id}" in message.text or (message.reply_to_message and message.reply_to_message.from_user.id == bot.id):
            should_reply = True
        elif is_question and random.random() < 0.50:
            should_reply = True 
        elif random.random() < 0.07:
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
    load_brain()
    await bot.delete_webhook(drop_pending_updates=True)
    try:
        await asyncio.gather(dp.start_polling(bot), start_server())
    finally:
        save_brain()

if __name__ == "__main__":
    asyncio.run(main())
