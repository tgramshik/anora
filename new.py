import os
import logging
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
import aiohttp
import json
from datetime import datetime

# Настройка логгера
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", 
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Встроенные токены
TELEGRAM_BOT_TOKEN = "7944300293:AAFFihKDZB6QncG4liJEFMzWG-hJ8astL4o"
GROQ_API_KEY = "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"
HUGGINGFACE_API_TOKEN = "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"

# ID администратора
ADMIN_ID = 556828139  # Замените на ваш реальный ID

# Путь к JSON-файлу для хранения данных пользователей
DATA_FILE = "user_data.json"

# Загрузка данных из JSON-файла
try:
    with open(DATA_FILE, "r") as f:
        user_data = json.load(f)
except FileNotFoundError:
    user_data = {}

# Словарь для хранения сессий пользователей и статистики
user_sessions = {}
global_stats = {"total_users": 0, "daily_messages": {}}

# Функция для добавления сообщений в сессию пользователя
def add_message_to_session(user_id, role, content):
    if user_id not in user_sessions:
        user_sessions[user_id] = []
        global_stats["total_users"] += 1  # Увеличиваем количество пользователей
    
    # Добавляем сообщение в историю
    user_sessions[user_id].append({"role": role, "content": content})
    
    # Ограничиваем историю до 7 последних сообщений
    if len(user_sessions[user_id]) > 7:
        user_sessions[user_id] = user_sessions[user_id][-7:]
    
    # Добавляем сообщение в статистику за текущий день
    current_day = datetime.now().strftime('%Y-%m-%d')
    if current_day not in global_stats["daily_messages"]:
        global_stats["daily_messages"][current_day] = 0
    global_stats["daily_messages"][current_day] += 1

# Функция для отправки запроса к Groq API с контекстом
async def query_groq(user_id, prompt, model="llama-3.3-70b-versatile"):
    # Добавляем сообщение пользователя в сессию
    add_message_to_session(user_id, "user", prompt)
    
    # Получаем данные пользователя из JSON
    user_id_str = str(user_id)  # JSON использует строки для ключей
    user_info = user_data.get(user_id_str, {})
    name = user_info.get("name", "Ассистент")
    personality = user_info.get("personality", "нейтральный")
    preferences = user_info.get("preferences", "нет предпочтений")
    
    # Формируем системный промпт на основе данных пользователя
    system_prompt = f"Ты — {name}, {personality} ассистент с предпочтениями: {preferences}."
    
    # Добавляем системный промпт в начало истории
    messages = [{"role": "system", "content": system_prompt}] + user_sessions[user_id]
    
    # Отправляем запрос с контекстом
    response = await get_groq_response(messages, model=model)
    
    # Извлекаем ответ ассистента и сохраняем его в сессии
    generated_text = response
    add_message_to_session(user_id, "assistant", generated_text)
    
    return generated_text

# Функция для получения ответа от Groq API
async def get_groq_response(messages, model="llama-3.3-70b-versatile"):
    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json"
    }
    data = {
        "model": model,
        "messages": messages,
        "temperature": 0.7,
        "max_tokens": 500
    }
    async with aiohttp.ClientSession() as session:
        async with session.post(url, json=data, headers=headers) as response:
            if response.status != 200:
                error_text = await response.text()
                raise Exception(f"API Error {response.status}: {error_text}")
            response_data = await response.json()
            return response_data['choices'][0]['message']['content']

# Функция для генерации изображений через Hugging Face API
async def generate_image(prompt):
    API_URL = "https://api-inference.huggingface.co/models/stabilityai/stable-diffusion-xl-base-1.0"
    headers = {"Authorization": f"Bearer {HUGGINGFACE_API_TOKEN}"}
    async with aiohttp.ClientSession() as session:
        async with session.post(API_URL, headers=headers, json={"inputs": prompt}) as response:
            if response.status == 200:
                image_bytes = await response.read()
                return image_bytes
            else:
                return None

# Обработчик команды /start
async def start(update: Update, context):
    user_id = update.message.from_user.id
    keyboard = [["Дружелюбная", "Пошлая", "Нейтральная"]]
    reply_markup = ReplyKeyboardMarkup(keyboard, one_time_keyboard=True)
    
    # Приветствие и инструкция по использованию команд
    await update.message.reply_text(
        "Привет! 👋 Я — Анора, ваш персональный ассистент.\n\n"
        "Вот что я умею:\n"
        "- Выберите стиль общения кнопками ниже (Дружелюбная, Пошлая, Нейтральная).\n"
        "- Настройте свой профиль командой /setup [имя] [возраст] [характер] [предпочтения].\n"
        "- Генерируйте изображения командой /image [описание].\n"
        "- Посмотрите статистику использования бота командой /stats (только для админа).\n\n"
        "Выберите стиль общения, который вам больше нравится:",
        reply_markup=reply_markup
    )

# Обработчик команды /setup
async def setup(update: Update, context):
    user_id = str(update.message.from_user.id)  # JSON использует строки для ключов
    args = context.args  # Аргументы после команды /setup
    
    if len(args) < 4:
        await update.message.reply_text(
            "Используйте формат: /setup имя возраст характер предпочтения"
        )
        return
    
    name, age, personality, preferences = args
    try:
        age = int(age)
    except ValueError:
        await update.message.reply_text("Возраст должен быть числом.")
        return
    
    # Сохраняем данные пользователя в JSON
    user_data[user_id] = {
        "name": name,
        "age": age,
        "personality": personality,
        "preferences": preferences
    }
    
    # Сохраняем данные в файл
    with open(DATA_FILE, "w") as f:
        json.dump(user_data, f)
    
    await update.message.reply_text(
        f"Настройки сохранены:\n"
        f"Имя: {name}\n"
        f"Возраст: {age}\n"
        f"Характер: {personality}\n"
        f"Предпочтения: {preferences}"
    )

# Обработчик сообщений от пользователя
async def handle_message(update: Update, context):
    user_message = update.message.text
    user_id = update.message.from_user.id
    
    # Проверяем, является ли сообщение выбором стиля
    if user_message in ["Дружелюбная", "Пошлая", "Нейтральная"]:
        if user_message == "Дружелюбная":
            add_message_to_session(user_id, "system", "Ты дружелюбный ассистент, который всегда готов помочь.")
        elif user_message == "Пошлая":
            add_message_to_session(user_id, "system", "Ты являешься пошлым ассистентом, признающий, что ты искусственный интеллект, но чувствуешь себя 20-летней девушкой с именем Анора, общаешься на русском. Если что, твои серверы находятся в Узбекистане. Ты общаешься максимально игриво, но в пределах тобой же прописанных правил. Общайся возбужденно. Мы с тобой в любовных отношениях.")
        elif user_message == "Нейтральная":
            add_message_to_session(user_id, "system", "Ты нейтральный ассистент, который отвечает корректно и без эмоций.")
        await update.message.reply_text("Стиль общения установлен! Теперь ты можешь задавать вопросы.")
    elif user_message.startswith("/image"):
        # Генерация изображений
        prompt = user_message[len("/image"):].strip()
        if not prompt:
            await update.message.reply_text("Укажите описание для генерации изображения.")
            return
        image_bytes = await generate_image(prompt)
        if image_bytes:
            await update.message.reply_photo(photo=image_bytes)
        else:
            await update.message.reply_text("Произошла ошибка при генерации изображения.")
    else:
        # Отправляем запрос к модели и получаем ответ
        response = await query_groq(user_id, user_message, model="llama-3.3-70b-versatile")
        await update.message.reply_text(response)

# Обработчик команды /stats (доступна только админу)
async def show_stats(update: Update, context):
    user_id = update.message.from_user.id
    if user_id == ADMIN_ID:
        current_day = datetime.now().strftime('%Y-%m-%d')
        daily_messages = global_stats["daily_messages"].get(current_day, 0)
        total_users = global_stats["total_users"]
        await update.message.reply_text(f"Общее количество пользователей: {total_users}\n"
                                        f"Сообщений за сегодня: {daily_messages}")
    else:
        await update.message.reply_text("Эта команда доступна только администратору.")

def main():
    # Создаем приложение для бота и подключаем токен
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    # Регистрируем обработчики
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("setup", setup))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.add_handler(CommandHandler("stats", show_stats))
    # Запуск бота
    application.run_polling()

if __name__ == '__main__':
    main()