import logging
import json
import os
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.enums import ParseMode
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, LabeledPrice
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
import asyncio

# ========== КОНФИГУРАЦИЯ ==========
BOT_TOKEN = "8643149487:AAGAa3sV4gO55Z5kQXNajifRQH4d2Mhu4bE"
ADMIN_ID = 8423212939  # Ваш Telegram ID

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Используем FSM для хранения состояний
storage = MemoryStorage()
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=storage)

# Файл для хранения настроек
SETTINGS_FILE = "channel_settings.json"

# Состояния для FSM
class AddChannelStates(StatesGroup):
    waiting_for_channel_id = State()
    waiting_for_price = State()

# Загрузка настроек
def load_settings():
    if os.path.exists(SETTINGS_FILE):
        with open(SETTINGS_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return {}

def save_settings(settings):
    with open(SETTINGS_FILE, 'w', encoding='utf-8') as f:
        json.dump(settings, f, ensure_ascii=False, indent=2)

# Глобальные настройки
channel_settings = load_settings()
pending_requests = {}  # Временное хранилище заявок


# ========== АДМИН-ПАНЕЛЬ ==========
@dp.message(Command("admin"))
async def admin_panel(message: types.Message):
    """Админ панель - видна только админу"""
    if message.from_user.id != ADMIN_ID:
        await message.answer("⛔ У вас нет доступа к админ-панели")
        return
    
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📋 Список каналов", callback_data="admin_list_channels")],
            [InlineKeyboardButton(text="➕ Добавить канал", callback_data="admin_add_channel")],
            [InlineKeyboardButton(text="📊 Статистика", callback_data="admin_stats")]
        ]
    )
    
    await message.answer(
        "🔐 *Админ-панель*\n\n"
        "Выберите действие:",
        reply_markup=keyboard,
        parse_mode=ParseMode.MARKDOWN
    )


@dp.callback_query(F.data == "admin_list_channels")
async def list_channels(callback: types.CallbackQuery):
    """Список всех каналов"""
    await callback.answer()  # Сразу отвечаем, чтобы кнопка не "заедала"
    
    if callback.from_user.id != ADMIN_ID:
        await callback.message.answer("⛔ Нет доступа")
        return
    
    if not channel_settings:
        await callback.message.edit_text(
            "📭 *Список каналов пуст*\n\n"
            "Добавьте канал через меню ➕",
            parse_mode=ParseMode.MARKDOWN
        )
        return
    
    text = "📋 *Ваши каналы:*\n\n"
    buttons = []
    
    for channel_id, settings in channel_settings.items():
        check_type = "🔍 Человек" if settings['check_type'] == 'human' else f"⭐ Звезды ({settings.get('price', 1)}⭐)"
        status = "✅" if settings.get('active', True) else "❌"
        text += f"{status} Канал: `{channel_id}`\n"
        text += f"   Тип: {check_type}\n\n"
        
        # Добавляем кнопки для каждого канала
        buttons.append([
            InlineKeyboardButton(
                text=f"{'🔴 Выкл' if settings.get('active', True) else '🟢 Вкл'} {channel_id}",
                callback_data=f"toggle_{channel_id}"
            ),
            InlineKeyboardButton(
                text="🗑",
                callback_data=f"del_{channel_id}"
            )
        ])
    
    buttons.append([InlineKeyboardButton(text="◀️ Назад", callback_data="admin_back")])
    
    keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
    
    await callback.message.edit_text(text, reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN)


@dp.callback_query(F.data.startswith("toggle_"))
async def toggle_channel(callback: types.CallbackQuery):
    """Включить/выключить канал"""
    await callback.answer()
    
    if callback.from_user.id != ADMIN_ID:
        return
    
    channel_id = callback.data.replace("toggle_", "")
    
    if channel_id in channel_settings:
        channel_settings[channel_id]['active'] = not channel_settings[channel_id].get('active', True)
        save_settings(channel_settings)
        
        status = "включен" if channel_settings[channel_id]['active'] else "выключен"
        await callback.answer(f"Канал {status}", show_alert=True)
        
        # Обновляем список
        await list_channels(callback)


@dp.callback_query(F.data.startswith("del_"))
async def delete_channel(callback: types.CallbackQuery):
    """Удалить канал"""
    await callback.answer()
    
    if callback.from_user.id != ADMIN_ID:
        return
    
    channel_id = callback.data.replace("del_", "")
    
    if channel_id in channel_settings:
        del channel_settings[channel_id]
        save_settings(channel_settings)
        await callback.answer("Канал удален", show_alert=True)
        
        # Обновляем список
        await list_channels(callback)


@dp.callback_query(F.data == "admin_add_channel")
async def add_channel_start(callback: types.CallbackQuery, state: FSMContext):
    """Начало добавления канала"""
    await callback.answer()
    
    if callback.from_user.id != ADMIN_ID:
        return
    
    await callback.message.edit_text(
        "➕ *Добавление канала*\n\n"
        "Отправьте ID канала.\n"
        "Формат: `-100123456789`\n\n"
        "ID можно получить у @userinfobot, переслав любое сообщение из канала.\n\n"
        "❌ Для отмены отправьте /cancel",
        parse_mode=ParseMode.MARKDOWN
    )
    
    await state.set_state(AddChannelStates.waiting_for_channel_id)


@dp.message(Command("cancel"))
async def cancel_handler(message: types.Message, state: FSMContext):
    """Отмена операции"""
    await state.clear()
    await message.answer("❌ Операция отменена")


@dp.message(AddChannelStates.waiting_for_channel_id)
async def process_channel_id(message: types.Message, state: FSMContext):
    """Обработка введенного ID канала"""
    try:
        channel_id = int(message.text.strip())
        
        # Проверяем, не существует ли уже канал
        if str(channel_id) in channel_settings:
            await message.answer("❌ Этот канал уже добавлен!")
            await state.clear()
            return
        
        await state.update_data(channel_id=str(channel_id))
        
        # Спрашиваем тип проверки
        keyboard = InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="🔍 Проверка на человека", callback_data="type_human")],
                [InlineKeyboardButton(text="⭐ Оплата звездами", callback_data="type_stars")],
                [InlineKeyboardButton(text="❌ Отмена", callback_data="cancel_type")]
            ]
        )
        
        await message.answer(
            f"📌 *Канал:* `{channel_id}`\n\n"
            "Выберите тип проверки:",
            reply_markup=keyboard,
            parse_mode=ParseMode.MARKDOWN
        )
        
    except ValueError:
        await message.answer("❌ Неверный формат ID. Введите число.")


@dp.callback_query(F.data == "cancel_type")
async def cancel_type(callback: types.CallbackQuery, state: FSMContext):
    """Отмена выбора типа"""
    await callback.answer()
    await state.clear()
    await callback.message.edit_text("❌ Добавление канала отменено")


@dp.callback_query(F.data == "type_human")
async def set_human_type(callback: types.CallbackQuery, state: FSMContext):
    """Установка типа - человек"""
    await callback.answer()
    
    data = await state.get_data()
    channel_id = data.get('channel_id')
    
    channel_settings[channel_id] = {
        "check_type": "human",
        "active": True
    }
    save_settings(channel_settings)
    
    await callback.message.edit_text(
        f"✅ *Канал добавлен!*\n\n"
        f"📌 ID: `{channel_id}`\n"
        f"🔍 Тип: Проверка на человека\n\n"
        f"Теперь заявки в этот канал будут автоматически обрабатываться."
    )
    
    await state.clear()


@dp.callback_query(F.data == "type_stars")
async def set_stars_type(callback: types.CallbackQuery, state: FSMContext):
    """Установка типа - звезды"""
    await callback.answer()
    
    await callback.message.edit_text(
        "⭐ *Настройка оплаты*\n\n"
        "Введите количество звезд для оплаты (от 1 до 1000):\n\n"
        "❌ Для отмены отправьте /cancel"
    )
    
    await state.set_state(AddChannelStates.waiting_for_price)


@dp.message(AddChannelStates.waiting_for_price)
async def process_stars_price(message: types.Message, state: FSMContext):
    """Обработка цены в звездах"""
    try:
        price = int(message.text.strip())
        if price < 1 or price > 1000:
            await message.answer("❌ Цена должна быть от 1 до 1000 звезд")
            return
        
        data = await state.get_data()
        channel_id = data.get('channel_id')
        
        channel_settings[channel_id] = {
            "check_type": "stars",
            "price": price,
            "active": True
        }
        save_settings(channel_settings)
        
        await message.answer(
            f"✅ *Канал добавлен!*\n\n"
            f"📌 ID: `{channel_id}`\n"
            f"⭐ Тип: Оплата {price} звезд\n\n"
            f"Теперь заявки в этот канал будут требовать оплату."
        )
        
        await state.clear()
        
    except ValueError:
        await message.answer("❌ Введите число")


@dp.callback_query(F.data == "admin_stats")
async def show_stats(callback: types.CallbackQuery):
    """Статистика для админа"""
    await callback.answer()
    
    if callback.from_user.id != ADMIN_ID:
        return
    
    stats_text = f"📊 *Статистика*\n\n"
    stats_text += f"⏳ Ожидают проверки: {len(pending_requests)}\n"
    stats_text += f"📋 Настроено каналов: {len(channel_settings)}\n\n"
    
    for channel_id, settings in channel_settings.items():
        check_type = "🔍 Человек" if settings['check_type'] == 'human' else f"⭐ Звезды ({settings.get('price', 1)}⭐)"
        status = "✅" if settings.get('active', True) else "❌"
        stats_text += f"{status} Канал: `{channel_id}` - {check_type}\n"
    
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="◀️ Назад", callback_data="admin_back")]
        ]
    )
    
    await callback.message.edit_text(stats_text, reply_markup=keyboard, parse_mode=ParseMode.MARKDOWN)


@dp.callback_query(F.data == "admin_back")
async def back_to_admin(callback: types.CallbackQuery):
    """Возврат в админ-панель"""
    await callback.answer()
    await admin_panel(callback.message)


# ========== ОБРАБОТЧИК ЗАЯВОК ==========
@dp.chat_join_request()
async def handle_join_request(update: types.ChatJoinRequest):
    """Обработка заявок в канал"""
    chat_id = str(update.chat.id)
    user = update.from_user
    
    # Проверяем есть ли настройки для этого канала
    if chat_id not in channel_settings:
        logger.warning(f"Канал {chat_id} не настроен, пропускаем")
        return
    
    settings = channel_settings[chat_id]
    
    # Проверяем активен ли канал
    if not settings.get('active', True):
        logger.info(f"Канал {chat_id} неактивен, заявка игнорируется")
        return
    
    # Сохраняем заявку
    request_key = f"{chat_id}_{user.id}"
    pending_requests[request_key] = {
        "user": user,
        "chat_id": chat_id,
        "settings": settings,
        "message_id": None
    }
    
    if settings['check_type'] == 'human':
        # Проверка на человека
        await human_check(user, chat_id, request_key)
    else:
        # Оплата звездами
        await stars_payment(user, chat_id, request_key, settings)


async def human_check(user, chat_id, request_key):
    """Отправка проверки на человека"""
    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✅ Я человек", callback_data=f"verify_{request_key}")],
            [InlineKeyboardButton(text="❌ Отмена", callback_data=f"cancel_{request_key}")]
        ]
    )
    
    try:
        msg = await bot.send_message(
            chat_id=user.id,
            text=f"🔍 *Проверка перед вступлением*\n\n"
                 f"Привет, {user.full_name}!\n\n"
                 f"Вы подали заявку на вступление в канал.\n"
                 f"Пожалуйста, подтвердите что вы человек, нажав на кнопку ниже:",
            reply_markup=keyboard,
            parse_mode=ParseMode.MARKDOWN
        )
        
        # Сохраняем ID сообщения
        if request_key in pending_requests:
            pending_requests[request_key]["message_id"] = msg.message_id
            
    except Exception as e:
        logger.error(f"Ошибка при отправке сообщения {user.id}: {e}")


async def stars_payment(user, chat_id, request_key, settings):
    """Отправка счета на оплату звездами"""
    price = settings.get('price', 1)
    prices = [LabeledPrice(label="Доступ в канал", amount=price)]
    
    try:
        await bot.send_invoice(
            chat_id=user.id,
            title="⭐ Доступ в канал",
            description=f"Оплата {price} звездой для получения доступа.",
            payload=f"stars_{request_key}",
            provider_token="",
            currency="XTR",
            prices=prices,
            need_name=False,
            need_phone_number=False,
            need_email=False
        )
    except Exception as e:
        logger.error(f"Ошибка при отправке инвойса {user.id}: {e}")
        if request_key in pending_requests:
            del pending_requests[request_key]


@dp.callback_query(F.data.startswith("verify_"))
async def verify_human(callback: types.CallbackQuery):
    """Подтверждение проверки на человека"""
    await callback.answer()  # Сразу отвечаем, чтобы кнопка не заедала
    
    request_key = callback.data.replace("verify_", "")
    
    if request_key not in pending_requests:
        await callback.message.edit_text("❌ Заявка уже обработана")
        return
    
    request_data = pending_requests[request_key]
    user_id = request_data["user"].id
    chat_id = int(request_data["chat_id"])
    
    # Проверяем что кнопку нажал тот же пользователь
    if callback.from_user.id != user_id:
        await callback.answer("⛔ Эта кнопка не для вас!", show_alert=True)
        return
    
    try:
        await bot.approve_chat_join_request(
            chat_id=chat_id,
            user_id=user_id
        )
        
        await callback.message.edit_text(
            f"✅ *Проверка пройдена!*\n\n"
            f"Вы успешно добавлены в канал!\n\n"
            f"Добро пожаловать! 🎉",
            parse_mode=ParseMode.MARKDOWN
        )
        
        del pending_requests[request_key]
        
    except Exception as e:
        logger.error(f"Ошибка при добавлении: {e}")
        await callback.message.edit_text(f"❌ Ошибка: {str(e)}")


@dp.pre_checkout_query()
async def pre_checkout(pre_checkout_query: types.PreCheckoutQuery):
    """Подтверждение оплаты"""
    await pre_checkout_query.answer(ok=True)


@dp.message(F.successful_payment)
async def successful_payment(message: types.Message):
    """Успешная оплата звездами"""
    payload = message.successful_payment.invoice_payload
    request_key = payload.replace("stars_", "")
    
    if request_key not in pending_requests:
        await message.answer("❌ Заявка не найдена")
        return
    
    request_data = pending_requests[request_key]
    chat_id = int(request_data["chat_id"])
    user_id = message.from_user.id
    
    try:
        await bot.approve_chat_join_request(
            chat_id=chat_id,
            user_id=user_id
        )
        
        await message.answer(
            f"✅ *Оплата прошла успешно!*\n\n"
            f"Вы добавлены в канал!\n\n"
            f"Добро пожаловать! 🎉",
            parse_mode=ParseMode.MARKDOWN
        )
        
        del pending_requests[request_key]
        
    except Exception as e:
        logger.error(f"Ошибка: {e}")
        await message.answer(f"❌ Ошибка при добавлении: {str(e)}")


@dp.callback_query(F.data.startswith("cancel_"))
async def cancel_request(callback: types.CallbackQuery):
    """Отмена заявки"""
    await callback.answer()
    
    request_key = callback.data.replace("cancel_", "")
    
    if request_key not in pending_requests:
        await callback.message.edit_text("❌ Заявка уже обработана")
        return
    
    request_data = pending_requests[request_key]
    user_id = request_data["user"].id
    chat_id = int(request_data["chat_id"])
    
    # Проверяем что кнопку нажал тот же пользователь
    if callback.from_user.id != user_id:
        await callback.answer("⛔ Эта кнопка не для вас!", show_alert=True)
        return
    
    try:
        await bot.decline_chat_join_request(
            chat_id=chat_id,
            user_id=user_id
        )
        
        await callback.message.edit_text("❌ Заявка отклонена")
        del pending_requests[request_key]
        
    except Exception as e:
        logger.error(f"Ошибка: {e}")
        await callback.answer("Ошибка", show_alert=True)


@dp.message()
async def handle_unknown(message: types.Message):
    """Обработка неизвестных сообщений"""
    await message.answer(
        "🤖 Я бот для управления заявками в каналы\n\n"
        "Используйте /admin если вы администратор"
    )


async def main():
    """Запуск бота"""
    print("🤖 Бот-администратор запущен!")
    print(f"👤 Ваш ID: {ADMIN_ID}")
    print("📌 Используйте /admin для открытия админ-панели")
    print("=" * 50)
    
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
