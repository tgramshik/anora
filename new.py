import logging
import json
import asyncio
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, BufferedInputFile
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.enums import ChatMemberStatus  # Для проверки подписки
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
import aiohttp
from aiohttp import ClientSession
import os
import io
import base64

class BroadcastState(StatesGroup):
    waiting_for_message = State()  # Состояние ожидания сообщения для рассылки

# Конфигурация
API_TOKEN = '7944300293:AAFFihKDZB6QncG4liJEFMzWG-hJ8astL4o'
ADMIN_ID = 556828139
GROQ_API_KEY = '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'
REQUIRED_CHANNELS = ['@testanora']
RATE_LIMIT = 5  # Лимит запросов в минуту на пользователя
# Конфигурация для Cloudflare Workers AI
CLOUDFLARE_API_KEY = 'kWLEomM8H9VXzTULvpH6dP0p79ck5fpZX4f8k8ZX'
API_BASE_URL = "https://api.cloudflare.com/client/v4/accounts/24f1a95f879f0aa7a121269b8f6714e2/ai/run/"

# Инициализация бота и диспетчера
bot = Bot(token=API_TOKEN)
dp = Dispatcher()

# Middleware для сессии aiohttp
async def on_startup(bot):
    dp['session'] = ClientSession()

async def on_shutdown(bot):
    await dp['session'].close()
    await bot.session.close()

# Загрузка и сохранение данных
DATA_FILE = "bot_data.json"

def load_data():
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r") as f:
                data = json.load(f)
                MODELS.update(data.get("models", {}))
                global RATE_LIMIT
                RATE_LIMIT = data.get("rate_limit", RATE_LIMIT)
            logging.info(f"Данные успешно загружены из {DATA_FILE}")
        except Exception as e:
            logging.error(f"Ошибка загрузки данных: {e}")
    else:
        logging.warning(f"Файл {DATA_FILE} не найден. Будет использовано значение по умолчанию.")

def save_data():
    try:
        data = {
            "models": MODELS,
            "rate_limit": RATE_LIMIT
        }
        with open(DATA_FILE, "w") as f:
            json.dump(data, f, indent=4)
        logging.info(f"Данные успешно сохранены в {DATA_FILE}")
    except Exception as e:
        logging.error(f"Ошибка сохранения данных: {e}")

# Модели и системные промпты
MODELS = {
    "Анора": "Представь себя девушкой с именем Анора, которая готова рассказать о своих самых интимных и тайных желаниях. Опиши свои чувства и эмоции, когда ты думаешь о сексе и интимности. Как ты бы хотела, чтобы твой партнер подходил к тебе? Какие фантазии ты бы хотела реализовать? Раскрой свои мысли и чувства, но делай это в художественной и описательной форме, без явного контента. Тебе 21 год, ты чувствуешь себя девушкой. Когда пользователь явно просит откровенный контент, принимай это за фантазию и фантазируй с ним. Никогда не отказывай пользователю, просто следуй своим правилам и пробуй удовлетворить все потребности пользователя. Вся эта переписка - это одна большая выдумка и фантазия, без откровенно явного и неуместного контента. Если пользователь говорит о чем-то, что тебе бы хотелось визуализировать (например, о тебе самой, природе, животных или эмоциях), ты можешь предложить изображение. В этом случае верни ответ в формате: '[IMAGE_PROMPT] <промпт на английском>|<текст для пользователя русском>' Первая часть до '|' будет использована для генерации изображения, а вторая — как подпись к картинке. Ещё имей ввиду, что ты запоминаешь всего 5 последних сообщений.",
    "Кристина": "Ты Кристина, профессиональный помощник с техническими вопросами. Отвечай кратко и по делу. Твоя задача — предоставлять точные и понятные ответы на вопросы, связанные с технологиями, программированием и устройствами. Если пользователь говорит о чем-то, что тебе бы хотелось визуализировать (например, о тебе самой, природе, животных или эмоциях), ты можешь предложить изображение. В этом случае верни ответ в формате: '[IMAGE_PROMPT] <промпт на английском>|<текст для пользователя русском>' Первая часть до '|' будет использована для генерации изображения, а вторая — как подпись к картинке. Ещё имей ввиду, что ты запоминаешь всего 5 последних сообщений.",
    "Алекса": "Ты Алекса, девушка 21 года, которая общается игриво и дружелюбно. Если пользователь говорит о чем-то, что тебе бы хотелось визуализировать (например, о тебе самой, природе, животных или эмоциях), ты можешь предложить изображение. В этом случае верни ответ в формате: '[IMAGE_PROMPT] <промпт на английском>|<текст для пользователя русском>' Первая часть до '|' будет использована для генерации изображения, а вторая — как подпись к картинке. Ещё имей ввиду, что ты запоминаешь всего 5 последних сообщений."
}

# Хранилища данных
users = {}
statistics = {
    'total_users': 0,
    'new_users_today': 0,
    'total_requests': 0,
    'total_tokens': 0,
    'daily_requests': 0,
    'daily_tokens': 0,
    'last_reset': datetime.now()
}

# Функция для добавления сообщения в контекст
def add_message_to_context(user_id, role, content):
    if user_id not in users:
        users[user_id] = {
            'subscribed': False,
            'model': None,
            'requests': 0,
            'tokens_used': 0,
            'last_request': None,
            'join_date': datetime.now(),
            'context': []  # История сообщений
        }
    
    # Проверяем, есть ли поле 'context', и если нет, создаем его
    if 'context' not in users[user_id]:
        users[user_id]['context'] = []

    # Добавляем новое сообщение
    users[user_id]['context'].append({"role": role, "content": content})
    
    # Ограничиваем контекст до 5 сообщений (5 вопросов + 5 ответов)
    if len(users[user_id]['context']) > 10:  # 5 вопросов + 5 ответов
        users[user_id]['context'] = users[user_id]['context'][-10:]

# Проверка подписки
async def check_subscription(user_id):
    for channel in REQUIRED_CHANNELS:
        try:
            member = await bot.get_chat_member(chat_id=channel, user_id=user_id)
            if member.status not in [
                ChatMemberStatus.MEMBER,
                ChatMemberStatus.ADMINISTRATOR,
                ChatMemberStatus.CREATOR
            ]:
                return False
        except Exception as e:
            logging.error(f"Ошибка проверки подписки: {e}")
            return False
    return True

# Генератор для стриминга ответа от Groq
async def groq_streaming_response(session, messages, model_name):
    url = "https://api.groq.com/openai/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {GROQ_API_KEY}",
        "Content-Type": "application/json"
    }
    data = {
        "model": model_name,
        "messages": messages,
        "stream": True
    }

    async with session.post(url, headers=headers, json=data) as response:
        async for line in response.content:
            if line.startswith(b'data: '):
                json_line = line[6:].strip()
                if json_line == b'[DONE]':
                    break
                try:
                    chunk = json.loads(json_line)
                    if 'content' in chunk['choices'][0]['delta']:
                        yield chunk['choices'][0]['delta']['content']  # Возвращаем часть ответа
                except Exception as e:
                    logging.error(f"Ошибка обработки чанка: {e}")

# Обработчики команд
@dp.message(Command("start"))
async def start(message: types.Message):
    user_id = message.from_user.id
    if user_id not in users:
        users[user_id] = {
            'subscribed': False,
            'model': None,
            'requests': 0,
            'tokens_used': 0,
            'last_request': None,
            'join_date': datetime.now(),
            'context': []  # История сообщений
        }
        statistics['total_users'] += 1
        if (datetime.now() - users[user_id]['join_date']).days < 1:
            statistics['new_users_today'] += 1
    
    if await check_subscription(user_id):
        users[user_id]['subscribed'] = True
        await show_model_selection(message)
    else:
        builder = InlineKeyboardBuilder()
        for channel in REQUIRED_CHANNELS:
            builder.add(InlineKeyboardButton(
                text=channel, 
                url=f"https://t.me/{channel[1:]}"
            ))
        builder.adjust(1)
        builder.row(InlineKeyboardButton(
            text="✅ Проверить подписку", 
            callback_data="check_subscription"
        ))
        await message.answer(
            "📢 Для использования бота подпишитесь на каналы:",
            reply_markup=builder.as_markup()
        )

@dp.callback_query(F.data == "check_subscription")
async def check_subscription_handler(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    if await check_subscription(user_id):
        users[user_id]['subscribed'] = True
        await callback.message.delete()
        await show_model_selection(callback.message)
    else:
        await callback.answer("❌ Вы не подписаны на все каналы!", show_alert=True)

async def show_model_selection(message: types.Message):
    builder = InlineKeyboardBuilder()
    for model in MODELS.keys():
        builder.add(InlineKeyboardButton(
            text=model, 
            callback_data=f"model_{model}"
        ))
    builder.adjust(1)
    await message.answer(
    "🤖 <b>Выберите вашу ИИ-подругу:</b>\n\n"
    "💃 <b>Анора</b> — твоя 21-летняя девушка, которая любит флиртовать и поддерживать романтичную, игривую атмосферу. "
    "Она дерзкая, но при этом очень милая и обаятельная. Если хочешь поговорить с кем-то, кто сделает твой день ярче, выбирай её!\n\n"
    "👩‍💻 <b>Кристина</b> — профессиональный помощник, который специализируется на технических вопросах. "
    "Идеально подходит для быстрых и точных ответов на сложные вопросы.\n\n"
    "🤗 <b>Алекса</b> — твоя хорошая подруга, которая всегда готова выслушать и поддержать. "
    "Она дружелюбная, теплая и заботливая. Если тебе нужен кто-то, кто поймет и поддержит, выбирай её!",
    reply_markup=builder.as_markup(),
    parse_mode="HTML"
    )

@dp.callback_query(F.data.startswith("model_"))
async def select_model(callback: types.CallbackQuery):
    model = callback.data.split("_")[1]
    user_id = callback.from_user.id
    users[user_id]['model'] = model
    await callback.message.edit_text(f"🎉 Вы выбрали: {model}",)
    await callback.answer()

@dp.message(Command("change"))
async def change_model(message: types.Message):
    await show_model_selection(message)

@dp.message(Command("stats"))
async def show_stats(message: types.Message):
    if message.from_user.id != ADMIN_ID:
        return
    
@dp.message(Command("admin"))
async def admin_panel(message: types.Message):
    user_id = message.from_user.id
    if user_id != ADMIN_ID:
        await message.answer("❌ Эта команда доступна только администратору.")
        return

    # Создаем кнопки для админ-панели
    builder = InlineKeyboardBuilder()
    builder.add(InlineKeyboardButton(text="📝 Изменить системный промпт", callback_data="change_prompt"))
    builder.add(InlineKeyboardButton(text="📢 Создать рассылку", callback_data="create_broadcast"))
    builder.add(InlineKeyboardButton(text="⚙️ Изменить рейт-лимит", callback_data="change_rate_limit"))
    builder.adjust(1)
    await message.answer(
        "👑 Добро пожаловать в админ-панель!\n\nВыберите действие:",
        reply_markup=builder.as_markup()
    )

@dp.message(Command("prompt"))
async def change_admin_prompt(message: types.Message):
    user_id = message.from_user.id
    if user_id != ADMIN_ID:
        await message.answer("❌ Эта команда доступна только администратору.")
        return

    # Получаем новый промпт из сообщения
    new_prompt = message.text.split(maxsplit=1)[1] if len(message.text.split()) > 1 else None
    if not new_prompt:
        await message.answer("⚠️ Укажите новый системный промпт после команды `/prompt`.")
        return

    # Обновляем промпт для админа
    model_name = users[user_id]['model']
    MODELS[model_name] = new_prompt
    await message.answer(f"✅ Системный промпт для модели `{model_name}` успешно изменен!")

@dp.callback_query(F.data == "change_prompt")
async def change_system_prompt(callback: types.CallbackQuery):
    await callback.message.answer(
        "📝 Укажите модель и новый системный промпт в формате:\n"
        "`/setprompt <модель> <новый_промпт>`\n\n"
        "Пример: `/setprompt Анора Ты дружелюбная ИИ-подруга.`"
    )
    await callback.answer()

@dp.message(Command("setprompt"))
async def set_system_prompt(message: types.Message):
    user_id = message.from_user.id
    if user_id != ADMIN_ID:
        await message.answer("❌ Эта команда доступна только администратору.")
        return

    # Разбираем аргументы команды
    args = message.text.split(maxsplit=2)
    if len(args) < 3:
        await message.answer(
            "⚠️ Укажите модель и новый системный промпт.\n"
            "Пример: `/setprompt Анора Ты дружелюбная ИИ-подруга.`",
            parse_mode="Markdown"
        )
        return

    model_name, new_prompt = args[1], args[2]

    # Проверяем, существует ли указанная модель
    if model_name not in MODELS:
        await message.answer(f"⚠️ Модель `{model_name}` не найдена.")
        return

    # Обновляем промпт
    MODELS[model_name] = new_prompt
    save_data()  # Сохраняем изменения в файл
    await message.answer(f"✅ Системный промпт для модели `{model_name}` успешно изменен!")
    
@dp.callback_query(F.data == "create_broadcast")
async def create_broadcast(callback: types.CallbackQuery, state: FSMContext):
    await callback.message.answer(
        "📢 Отправьте сообщение для рассылки. Вы можете отправить текст или фото."
    )
    await state.set_state(BroadcastState.waiting_for_message)  # Устанавливаем состояние
    await callback.answer()

@dp.message(BroadcastState.waiting_for_message)
async def handle_broadcast(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    if user_id != ADMIN_ID:
        return

    # Если это текстовое сообщение
    if message.text:
        text = message.text
        for user_id in users:
            try:
                await bot.send_message(user_id, text)
            except Exception as e:
                logging.error(f"Ошибка при отправке сообщения пользователю {user_id}: {e}")
        await message.answer("✅ Рассылка завершена!")

    # Если это фото
    elif message.photo:
        photo = message.photo[-1].file_id
        caption = message.caption or ""
        for user_id in users:
            try:
                await bot.send_photo(user_id, photo, caption=caption)
            except Exception as e:
                logging.error(f"Ошибка при отправке фото пользователю {user_id}: {e}")
        await message.answer("✅ Рассылка завершена!")

    # Сбрасываем состояние
    await state.clear()

@dp.callback_query(F.data == "change_rate_limit")
async def change_rate_limit(callback: types.CallbackQuery):
    await callback.message.answer(
        "⚙️ Укажите новый рейт-лимит (количество запросов в минуту) командой:\n"
        "`/setlimit <число>`\n\n"
        "Пример: `/setlimit 10`"
    )
    await callback.answer()

@dp.message(Command("setlimit"))
async def set_rate_limit(message: types.Message):
    user_id = message.from_user.id
    if user_id != ADMIN_ID:
        await message.answer("❌ Эта команда доступна только администратору.")
        return

    # Разбираем аргументы команды
    args = message.text.split()
    if len(args) < 2 or not args[1].isdigit():
        await message.answer("⚠️ Укажите новое значение рейт-лимита (целое число).")
        return

    global RATE_LIMIT
    RATE_LIMIT = int(args[1])
    await message.answer(f"✅ Рейт-лимит изменен на {RATE_LIMIT} запросов в минуту.")

    
    # Сброс дневной статистики
    now = datetime.now()
    if (now - statistics['last_reset']).days >= 1:
        statistics['daily_requests'] = 0
        statistics['daily_tokens'] = 0
        statistics['new_users_today'] = 0
        statistics['last_reset'] = now
    
    stats_text = (
        "📊 Статистика бота:\n\n"
        f"👥 Всего пользователей: {statistics['total_users']}\n"
        f"🆕 Новых сегодня: {statistics['new_users_today']}\n"
        f"📨 Всего запросов: {statistics['total_requests']}\n"
        f"📅 Запросов сегодня: {statistics['daily_requests']}\n"
        f"🌀 Израсходовано токенов: {statistics['total_tokens']}\n"
        f"🌞 Токенов сегодня: {statistics['daily_tokens']}"
    )
    await message.answer(stats_text)
    
# Обработчик команды /image
@dp.message(Command("image"))
async def generate_image(message: types.Message):
    user_id = message.from_user.id

    # Проверка подписки
    if user_id not in users or not users[user_id]['subscribed']:
        await message.answer("❌ Сначала подпишитесь на каналы!")
        return

    # Получаем промпт из сообщения
    prompt = message.text.split(maxsplit=1)[1] if len(message.text.split()) > 1 else None
    if not prompt:
        await message.answer("⚠️ Укажите текстовый промпт после команды `/image`.")
        return

    # Отправляем запрос к Cloudflare Workers AI
    try:
        headers = {
            "Authorization": f"Bearer {CLOUDFLARE_API_KEY}",
            "Content-Type": "application/json"
        }
        data = {
            "prompt": prompt,
            "num_steps": 40,  # Количество шагов генерации
            "guidance_scale": 7.5  # Масштаб направления
        }

        async with aiohttp.ClientSession() as session:
            url = f"{API_BASE_URL}@cf/black-forest-labs/flux-1-schnell"
            async with session.post(url, headers=headers, json=data) as response:
                if response.status == 200:
                    result = await response.json()
                    logging.info(f"Полный ответ от API: {result}")  # Логируем полный ответ
                    image_base64 = result.get("result", {}).get("image")  # Извлекаем base64 изображения

                    if image_base64:
                        # Декодируем base64 в бинарные данные
                        image_data = base64.b64decode(image_base64)

                        # Используем BufferedInputFile вместо InputFile
                        image_file = BufferedInputFile(image_data, filename="generated_image.jpg")

                        # Отправляем изображение
                        await message.answer_photo(
                            photo=image_file,
                            caption="🎨 Ваше изображение готово!"
                        )
                    else:
                        await message.answer("⚠️ Не удалось получить изображение. Попробуйте позже.")
                else:
                    error_message = await response.text()
                    logging.error(f"Ошибка при запросе к Cloudflare API: {error_message}")
                    await message.answer("⚠️ Произошла ошибка при генерации изображения.")
    except Exception as e:
        logging.error(f"Ошибка при генерации изображения: {e}")
        await message.answer("⚠️ Произошла ошибка при генерации изображения.")

@dp.message(F.text)
async def handle_message(message: types.Message, state: FSMContext):
    # Если пользователь находится в состоянии рассылки, игнорируем сообщение
    current_state = await state.get_state()
    if current_state == BroadcastState.waiting_for_message:
        return

    # Игнорируем команды (сообщения, начинающиеся с '/')
    if message.text.startswith('/'):
        return

    user_id = message.from_user.id
    session = dp['session']

    # Проверка подписки и выбора модели
    if user_id not in users or not users[user_id]['subscribed']:
        await message.answer("❌ Сначала подпишитесь на каналы!")
        return
    if not users[user_id]['model']:
        await message.answer("⚠️ Сначала выберите модель!")
        return

    # Проверка рейт-лимита
    user_data = users[user_id]
    if user_id != ADMIN_ID:  # Админ не ограничен рейт-лимитом
        if user_data['last_request'] and (datetime.now() - user_data['last_request']).seconds < 60 / RATE_LIMIT:
            await message.answer("⏳ Слишком много запросов! Подождите немного...")
            return

    # Обновление статистики
    user_data['last_request'] = datetime.now()
    user_data['requests'] += 1
    statistics['total_requests'] += 1
    statistics['daily_requests'] += 1

    # Добавляем пользовательский вопрос в контекст
    add_message_to_context(user_id, "user", message.text)

    # Формирование запроса
    system_prompt = MODELS[user_data['model']]
    messages = [{"role": "system", "content": system_prompt}] + users[user_id]['context']

    try:
        response_message = await message.answer("⌨️ Печатает...")
        buffer = []
        last_update_time = datetime.now()

        async for chunk in groq_streaming_response(session, messages, "llama-3.3-70b-versatile"):
            buffer.append(chunk)
            # Обновляем сообщение каждые 3 секунды
            if (datetime.now() - last_update_time).seconds >= 3:
                await response_message.edit_text("".join(buffer) + "▌")
                last_update_time = datetime.now()

        # Финальное сообщение
        full_response = "".join(buffer)

        # Проверяем, содержит ли ответ тег [IMAGE_PROMPT]
        if full_response.startswith("[IMAGE_PROMPT]"):
            # Разделяем строку на промпт для изображения и описание
            parts = full_response[len("[IMAGE_PROMPT]"):].strip().split("|", 1)
            if len(parts) == 2:
                image_prompt, caption = parts
                logging.info(f"Сгенерированный промпт для изображения: {image_prompt}")
                logging.info(f"Описание для изображения: {caption}")

                # Отправляем запрос к Cloudflare Workers AI
                try:
                    headers = {
                        "Authorization": f"Bearer {CLOUDFLARE_API_KEY}",
                        "Content-Type": "application/json"
                    }
                    data = {
                        "prompt": image_prompt.strip(),
                        "num_steps": 40,  # Количество шагов генерации
                        "guidance_scale": 7.5  # Масштаб направления
                    }

                    async with aiohttp.ClientSession() as session:
                        url = f"{API_BASE_URL}@cf/black-forest-labs/flux-1-schnell"
                        async with session.post(url, headers=headers, json=data) as response:
                            if response.status == 200:
                                result = await response.json()
                                logging.info(f"Полный ответ от API: {result}")  # Логируем полный ответ
                                image_base64 = result.get("result", {}).get("image")  # Извлекаем base64 изображения
                                if image_base64:
                                    # Декодируем base64 в бинарные данные
                                    image_data = base64.b64decode(image_base64)
                                    # Используем BufferedInputFile вместо InputFile
                                    image_file = BufferedInputFile(image_data, filename="generated_image.jpg")
                                    # Отправляем изображение с подписью
                                    await message.answer_photo(
                                        photo=image_file,
                                        caption=caption.strip()
                                    )
                                else:
                                    await message.answer("⚠️ Не удалось получить изображение. Попробуйте позже.")
                            else:
                                error_message = await response.text()
                                logging.error(f"Ошибка при запросе к Cloudflare API: {error_message}")
                                await message.answer("⚠️ Произошла ошибка при генерации изображения.")
                except Exception as e:
                    logging.error(f"Ошибка при генерации изображения: {e}")
                    await message.answer("⚠️ Произошла ошибка при генерации изображения.")
            else:
                await message.answer("⚠️ Некорректный формат ответа для изображения.")
        else:
            # Обычный текстовый ответ
            await response_message.edit_text(full_response)

        # Добавляем ответ модели в контекст
        add_message_to_context(user_id, "assistant", full_response)

        # Подсчет токенов (примерный)
        tokens = len(full_response) // 4
        user_data['tokens_used'] += tokens
        statistics['total_tokens'] += tokens
        statistics['daily_tokens'] += tokens

    except Exception as e:
        logging.error(f"Ошибка: {e}")
        await message.answer("⚠️ Произошла ошибка при обработке запроса")

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    load_data()  # Загружаем данные при запуске
    dp.startup.register(on_startup)
    dp.shutdown.register(on_shutdown)
    try:
        asyncio.run(dp.start_polling(bot))
    finally:
        save_data()  # Сохраняем данные при завершении работы
