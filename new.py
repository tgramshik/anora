import os
import logging
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
import aiohttp
import json
from datetime import datetime
from typing import List

# Настройка логгера
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", 
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Конфигурация
TELEGRAM_BOT_TOKEN = "7944300293:AAFFihKDZB6QncG4liJEFMzWG-hJ8astL4o"
GROQ_API_KEY = "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"
HUGGINGFACE_API_TOKEN = "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"
ADMIN_ID = 556828139
DATA_FILE = "user_data.json"

# Загрузка данных пользователей
try:
    with open(DATA_FILE, "r", encoding='utf-8') as f:
        user_data = json.load(f)
except (FileNotFoundError, json.JSONDecodeError):
    user_data = {}

# Глобальная статистика
global_stats = {"total_users": len(user_data), "daily_messages": {}}
user_sessions = {}

def save_user_data():
    with open(DATA_FILE, "w", encoding='utf-8') as f:
        json.dump(user_data, f, ensure_ascii=False, indent=2)

def add_message_to_session(user_id: int, role: str, content: str):
    if user_id not in user_sessions:
        user_sessions[user_id] = []
        if str(user_id) not in user_data:
            global_stats["total_users"] += 1
    
    user_sessions[user_id].append({"role": role, "content": content})
    user_sessions[user_id] = user_sessions[user_id][-7:]
    
    current_day = datetime.now().strftime('%Y-%m-%d')
    global_stats["daily_messages"][current_day] = global_stats["daily_messages"].get(current_day, 0) + 1

async def query_groq(user_id: int, prompt: str, model: str = "llama-3.3-70b-versatile") -> str:
    add_message_to_session(user_id, "user", prompt)
    
    user_id_str = str(user_id)
    user_info = user_data.get(user_id_str, {})
    
    # Формируем системный промпт
    system_prompt = user_info.get('system_prompt') or \
        f"Ты — {user_info.get('name', 'Ассистент')}, " \
        f"{user_info.get('personality', 'нейтральный')} ассистент. " \
        f"Предпочтения: {user_info.get('preferences', 'отсутствуют')}."
    
    messages = [{"role": "system", "content": system_prompt}] + user_sessions[user_id]
    
    async with aiohttp.ClientSession() as session:
        async with session.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"},
            json={
                "model": model,
                "messages": messages,
                "temperature": 0.7,
                "max_tokens": 500
            }
        ) as response:
            if response.status != 200:
                error = await response.text()
                raise Exception(f"API Error {response.status}: {error}")
            
            data = await response.json()
            reply = data['choices'][0]['message']['content']
            add_message_to_session(user_id, "assistant", reply)
            return reply

async def generate_image(prompt: str) -> bytes:
    async with aiohttp.ClientSession() as session:
        async with session.post(
            "https://api-inference.huggingface.co/models/stabilityai/stable-diffusion-xl-base-1.0",
            headers={"Authorization": f"Bearer {HUGGINGFACE_API_TOKEN}"},
            json={"inputs": prompt}
        ) as response:
            return await response.read() if response.status == 200 else None

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [["Дружелюбная", "Пошлая", "Нейтральная"]]
    await update.message.reply_text(
        "👋 Привет! Я Анора - твой персональный ИИ-ассистент.\n\n"
        "📌 Используй кнопки ниже для выбора стиля общения или команды:\n"
        "/setup - Настройка профиля\n"
        "/system - Кастомизация поведения\n"
        "/image - Генерация изображений\n",
        reply_markup=ReplyKeyboardMarkup(keyboard, one_time_keyboard=True)
    )

async def setup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args: List[str] = context.args
    user_id = str(update.message.from_user.id)
    
    if len(args) < 4:
        await update.message.reply_text("❌ Формат: /setup Имя Возраст Характер Ваши предпочтения")
        return
    
    try:
        age = int(args[1])
    except ValueError:
        await update.message.reply_text("⚠️ Возраст должен быть числом!")
        return
    
    user_data[user_id] = {
        "name": args[0],
        "age": age,
        "personality": args[2],
        "preferences": " ".join(args[3:])
    }
    
    save_user_data()
    await update.message.reply_text(
        f"✅ Профиль обновлен!\n"
        f"▫️ Имя: {args[0]}\n"
        f"▫️ Возраст: {age}\n"
        f"▫️ Характер: {args[2]}\n"
        f"▫️ Предпочтения: {' '.join(args[3:])}"
    )

async def system_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.message.from_user.id)
    args: List[str] = context.args
    
    if not args:
        current = user_data.get(user_id, {}).get('system_prompt', 'Используются настройки профиля')
        await update.message.reply_text(f"⚙️ Текущий системный промпт:\n{current}")
        return
    
    if args[0].lower() == "reset":
        user_data[user_id].pop('system_prompt', None)
        save_user_data()
        await update.message.reply_text("♻️ Промпт сброшен до значений профиля")
    else:
        user_data.setdefault(user_id, {})['system_prompt'] = " ".join(args)
        save_user_data()
        await update.message.reply_text("✅ Системный промпт успешно обновлен!")

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text
    user_id = update.message.from_user.id
    
    if text in ["Дружелюбная", "Пошлая", "Нейтральная"]:
        style_map = {
            "Дружелюбная": "дружелюбный тон, эмоциональные ответы",
            "Пошлая": "игривый стиль с элементами флирта",
            "Нейтральная": "формальные и сдержанные ответы"
        }
        add_message_to_session(user_id, "system", f"Стиль общения: {style_map[text]}")
        await update.message.reply_text(f"🎭 Установлен стиль: {text}")
    elif text.startswith("/image"):
        prompt = text[6:].strip()
        if not prompt:
            await update.message.reply_text("📷 Укажите описание изображения после команды")
            return
        
        await update.message.reply_text("🖌 Генерирую изображение...")
        image = await generate_image(prompt)
        await update.message.reply_photo(image if image else "❌ Ошибка генерации")
    else:
        response = await query_groq(user_id, text)
        await update.message.reply_text(response)

async def show_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.from_user.id == ADMIN_ID:
        stats = [
            f"👥 Пользователей: {global_stats['total_users']}",
            f"📨 Сообщений сегодня: {global_stats['daily_messages'].get(datetime.now().strftime('%Y-%m-%d'), 0)}"
        ]
        await update.message.reply_text("\n".join(stats))
    else:
        await update.message.reply_text("⛔ Доступ запрещен")

def main():
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    
    handlers = [
        CommandHandler('start', start),
        CommandHandler('setup', setup),
        CommandHandler('system', system_prompt),
        CommandHandler('stats', show_stats),
        MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message)
    ]
    
    for handler in handlers:
        app.add_handler(handler)
    
    app.run_polling()

if __name__ == '__main__':
    main()
