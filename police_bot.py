"""
🚔 POLICE GAME BOT — Игровой Telegram-бот
Токен и username берутся из переменных окружения Railway:
  BOT_TOKEN    — токен от @BotFather
  BOT_USERNAME — username бота без @
"""

import asyncio
import random
import json
import os
import sys
from datetime import datetime
from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command, CommandStart
from aiogram.types import (
    Message, CallbackQuery,
    InlineKeyboardMarkup, InlineKeyboardButton,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties

# ══════════════════════════════════════════
#  КОНФИГУРАЦИЯ — берём из переменных окружения
# ══════════════════════════════════════════
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
BOT_USERNAME = os.environ.get("BOT_USERNAME", "")

if not BOT_TOKEN:
    print("❌ Ошибка: переменная BOT_TOKEN не задана!")
    sys.exit(1)

if not BOT_USERNAME:
    print("⚠️  Предупреждение: переменная BOT_USERNAME не задана. Кнопка добавления в чат не будет работать.")

DATA_FILE = "players.json"

# ══════════════════════════════════════════
#  СИСТЕМА РАНГОВ
# ══════════════════════════════════════════
RANKS = [
    {"name": "🪪 Новобранец",          "min_xp": 0,     "emoji": "🪪"},
    {"name": "👮 Рядовой",              "min_xp": 100,   "emoji": "👮"},
    {"name": "🔵 Сержант",             "min_xp": 300,   "emoji": "🔵"},
    {"name": "🟡 Старший сержант",     "min_xp": 600,   "emoji": "🟡"},
    {"name": "🔴 Лейтенант",           "min_xp": 1000,  "emoji": "🔴"},
    {"name": "🟠 Старший лейтенант",   "min_xp": 1500,  "emoji": "🟠"},
    {"name": "⭐ Капитан",             "min_xp": 2200,  "emoji": "⭐"},
    {"name": "🌟 Майор",               "min_xp": 3000,  "emoji": "🌟"},
    {"name": "💫 Подполковник",        "min_xp": 4200,  "emoji": "💫"},
    {"name": "🏅 Полковник",           "min_xp": 5500,  "emoji": "🏅"},
    {"name": "🎖️ Генерал-майор",      "min_xp": 7500,  "emoji": "🎖️"},
    {"name": "🏆 Генерал полиции",     "min_xp": 10000, "emoji": "🏆"},
]

def get_rank(xp: int) -> dict:
    rank = RANKS[0]
    for r in RANKS:
        if xp >= r["min_xp"]:
            rank = r
    return rank

def next_rank(xp: int) -> dict | None:
    for r in RANKS:
        if xp < r["min_xp"]:
            return r
    return None

# ══════════════════════════════════════════
#  БАЗА ДАННЫХ (JSON-файл)
# ══════════════════════════════════════════
def load_data() -> dict:
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_data(data: dict):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def get_player(data: dict, user_id: int, username: str = "") -> dict:
    uid = str(user_id)
    if uid not in data:
        data[uid] = {
            "username": username,
            "xp": 0,
            "coins": 0,
            "catches": 0,
            "pursuits": 0,
            "pursuits_success": 0,
            "cuffs": 0,
            "last_pursuit": 0,
            "last_cuff": 0,
            "last_patrol": 0,
            "last_raid": 0,
            "last_fine": 0,
            "last_bribe": 0,
        }
    if username:
        data[uid]["username"] = username
    return data[uid]

# ══════════════════════════════════════════
#  УТИЛИТЫ
# ══════════════════════════════════════════
COOLDOWNS = {
    "pursuit": 120,    # 2 минуты
    "cuff":    180,    # 3 минуты
    "patrol":  90,     # 1.5 минуты
    "raid":    300,    # 5 минут
    "fine":    60,     # 1 минута
    "bribe":   240,    # 4 минуты
}

def check_cooldown(player: dict, action: str) -> int:
    """Возвращает оставшееся время КД в секундах, 0 если КД прошёл"""
    now = int(datetime.now().timestamp())
    last = player.get(f"last_{action}", 0)
    cd = COOLDOWNS.get(action, 60)
    elapsed = now - last
    if elapsed < cd:
        return cd - elapsed
    return 0

def set_cooldown(player: dict, action: str):
    player[f"last_{action}"] = int(datetime.now().timestamp())

def fmt_time(seconds: int) -> str:
    m, s = divmod(seconds, 60)
    if m > 0:
        return f"{m} мин {s} сек"
    return f"{s} сек"

def now_str() -> str:
    return datetime.now().strftime("%H:%M")

def mention(message: Message) -> str:
    u = message.from_user
    if u.username:
        return f"@{u.username}"
    return f"[{u.first_name}](tg://user?id={u.id})"

# ══════════════════════════════════════════
#  СЦЕНАРИИ ПОГОНИ (/pursuit)
# ══════════════════════════════════════════
PURSUIT_SUCCESS = [
    ("🚗 Преступник попытался уйти через дворы, но был прижат к забору!", 40, 25),
    ("🏃 Пешая погоня завершилась — офицер догнал его у магазина!", 45, 30),
    ("🚁 Вертолёт полиции отследил маршрут и машина была остановлена!", 50, 35),
    ("💨 Крутой манёвр, и преступник влетел в кювет. Задержан!", 35, 20),
    ("🛑 Спустил шины шипами — никуда не ушёл!", 30, 18),
    ("🌉 На мосту преступнику перекрыли путь. Деваться некуда!", 55, 40),
    ("📡 Видеонаблюдение помогло установить маршрут и перехватить!", 42, 28),
]

PURSUIT_FAIL = [
    "🚗💥 Попал в ДТП на перекрёстке — виноват красный светофор.",
    "⛽ Закончилось топливо в самый неподходящий момент!",
    "🛞 Лопнуло колесо на скорости 120 км/ч.",
    "📻 Рация вышла из строя, потерял координацию с коллегами.",
    "🌫️ Густой туман — пришлось снизить скорость, преступник ушёл.",
    "🚧 Строительный объезд завёл в тупик.",
    "🐕 На дорогу выбежала собака, пришлось тормозить.",
    "🚌 Автобус перекрыл перекрёсток в самый нужный момент.",
    "🌧️ Сильный дождь — потерял машину из виду.",
    "📱 Навигатор завёл не туда — классика!",
]

# ══════════════════════════════════════════
#  СЦЕНАРИИ ЗАДЕРЖАНИЯ (/cuff)
# ══════════════════════════════════════════
CUFF_SUCCESS = [
    ("🏃 Преступник выбежал из подъезда, но офицер уже ждал за углом и мгновенно скрутил его!", 60, 40),
    ("🎭 Маскировка под гражданского сработала — преступник сам подошёл к офицеру!", 55, 35),
    ("🐕‍🦺 Служебная собака Рекс взяла след и загнала подозреваемого в угол!", 70, 45),
    ("📷 Слежка через камеры позволила взять преступника прямо у его дома!", 50, 30),
    ("🤝 Агент под прикрытием передал точное местоположение. Захват прошёл чисто!", 65, 42),
    ("🏙️ Засада в переулке — преступник и не подозревал, что его уже ждут!", 58, 38),
    ("🚔 Три машины перекрыли все выходы. Сдался без сопротивления!", 75, 50),
]

CUFF_FAIL = [
    ("😤 Преступник оказался опытным бойцом и вырвался. Придётся попробовать ещё раз.",   -5),
    ("🚪 Выбил дверь, а там черный ход. Ушёл через соседние дворы.",                       0),
    ("🤦 Перепутал адрес! Задержали не того человека. Пришлось отпустить.",                -10),
    ("📵 Связь с группой захвата пропала в самый ответственный момент.",                    0),
    ("🌑 Преступник затаился в темноте склада, найти не удалось.",                          0),
    ("🏃💨 Опытный бегун — офицер просто не успел за ним.",                                 0),
]

# ══════════════════════════════════════════
#  СЦЕНАРИИ ПАТРУЛЯ (/patrol)
# ══════════════════════════════════════════
PATROL_EVENTS = [
    ("🔍 Патруль обнаружил подозрительный автомобиль — оказался в угоне. +опыт!", 20, 12, True),
    ("🤝 Помог гражданину с заблудившимся ребёнком. Репутация растёт!", 15, 8, True),
    ("🎫 Выписал штраф за нарушение ПДД. Пополнение казны!", 10, 15, True),
    ("🚯 Задержал хулигана, разрисовавшего стену. Малолетний вандал.", 18, 10, True),
    ("☕ Спокойная смена. Выпил кофе, обошёл квартал. Ничего особенного.", 5, 5, False),
    ("📢 Разогнал шумную компанию у подъезда. Жители благодарны!", 12, 7, True),
    ("🚘 Остановил пьяного водителя. Задержан до вытрезвления.", 25, 18, True),
    ("👀 Засёк карманника в толпе и задержал на месте!", 30, 20, True),
]

# ══════════════════════════════════════════
#  СЦЕНАРИИ РЕЙДА (/raid)
# ══════════════════════════════════════════
RAID_EVENTS = [
    ("🏭 Рейд на подпольный склад! Изъяты контрабандные товары на крупную сумму.", 120, 80, True),
    ("🎰 Накрыли подпольное казино! 15 задержанных.", 100, 70, True),
    ("💊 Ликвидирована точка сбыта запрещённых веществ.", 150, 90, True),
    ("🔫 Изъяли нелегальное оружие у группировки.", 130, 85, True),
    ("📦 Рейд по складам. Поддельный товар изъят, владелец задержан.", 90, 60, True),
    ("🚫 Рейд не принёс результата — информация оказалась ложной.", 10, 5, False),
    ("🏠 Обыск в явочной квартире — нашли компромат на преступную сеть!", 140, 95, True),
]

# ══════════════════════════════════════════
#  БОТ И ДИСПЕТЧЕР
# ══════════════════════════════════════════
bot = Bot(
    token=BOT_TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.MARKDOWN)
)
dp = Dispatcher()

# ══════════════════════════════════════════
#  /start
# ══════════════════════════════════════════
@dp.message(CommandStart())
async def cmd_start(message: Message):
    # Кнопка "Добавить бота в чат" — зелёная (style=success), Bot API 9.4
    keyboard = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(
            text="➕ Добавить бота в чат",
            url=f"https://t.me/{BOT_USERNAME}?startgroup=true",
            style="success"   # ← зелёный цвет (Bot API 9.4)
        )
    ]])

    text = (
        "🚔 *POLICE GAME BOT* 🚔\n\n"
        "Добро пожаловать в полицейскую академию!\n\n"
        "Ты — офицер полиции. Тебя ждут погони, рейды, задержания и продвижение по карьерной лестнице.\n\n"
        "⚡ *Что умеет этот бот:*\n"
        "• Случайные исходы операций с реалистичными историями\n"
        "• Система рангов: от Новобранца до Генерала полиции\n"
        "• Экономика: монеты, опыт, штрафы и взятки\n"
        "• Работает в группах — соревнуйтесь с друзьями!\n\n"
        "📋 Напишите /help чтобы увидеть все команды\n\n"
        "👇 *Добавь бота в свой чат и начни игру вместе с друзьями!*"
    )
    await message.answer(text, reply_markup=keyboard)

# ══════════════════════════════════════════
#  /help
# ══════════════════════════════════════════
@dp.message(Command("help"))
async def cmd_help(message: Message):
    text = (
        "📋 *Список команд Police Game Bot*\n\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        "🚔 *ОПЕРАТИВНЫЕ КОМАНДЫ*\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        "/pursuit — 🚗 Начать погоню за преступником\n"
        "_КД: 2 минуты | Награда: опыт + монеты_\n\n"
        "/cuff — 🔒 Задержать преступника\n"
        "_КД: 3 минуты | Награда: опыт + монеты_\n\n"
        "/patrol — 👮 Выйти на патруль\n"
        "_КД: 1.5 минуты | Награда: опыт + монеты_\n\n"
        "/raid — 🏭 Провести рейд\n"
        "_КД: 5 минут | Большая награда!_\n\n"
        "/fine — 📄 Выписать штраф нарушителю\n"
        "_КД: 1 минута | Быстрые монеты_\n\n"
        "/bribe — 💰 Проверить подозреваемого на взятку\n"
        "_КД: 4 минуты | Рисково, но выгодно_\n\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        "📊 *ПРОФИЛЬ И СТАТИСТИКА*\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        "/profile — 🪪 Ваш профиль офицера\n"
        "/top — 🏆 Топ офицеров чата\n"
        "/rank — ⭐ Все ранги и требования\n\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        "ℹ️ *ПРОЧЕЕ*\n"
        "━━━━━━━━━━━━━━━━━━━━━\n"
        "/start — 🚔 Приветствие бота\n"
        "/help — 📋 Это сообщение\n\n"
        "💡 *Совет:* Используйте все команды регулярно — "
        "каждая даёт опыт и монеты для продвижения по рангу!"
    )
    await message.answer(text)

# ══════════════════════════════════════════
#  /pursuit — ПОГОНЯ
# ══════════════════════════════════════════
@dp.message(Command("pursuit"))
async def cmd_pursuit(message: Message):
    data = load_data()
    uid = message.from_user.id
    player = get_player(data, uid, message.from_user.username or "")

    cd = check_cooldown(player, "pursuit")
    if cd > 0:
        await message.answer(
            f"⏳ *Машина ещё не готова к выезду!*\n"
            f"Ждите ещё: *{fmt_time(cd)}*",
            parse_mode="Markdown"
        )
        return

    start_time = now_str()
    player["pursuits"] = player.get("pursuits", 0) + 1
    set_cooldown(player, "pursuit")

    success_chance = 55  # 55% успех
    is_success = random.randint(1, 100) <= success_chance

    if is_success:
        scenario, xp, coins = random.choice(PURSUIT_SUCCESS)
        end_time = f"{datetime.now().hour:02d}:{random.randint(1,9):02d}"
        player["pursuits_success"] = player.get("pursuits_success", 0) + 1
        player["xp"] = player.get("xp", 0) + xp
        player["coins"] = player.get("coins", 0) + coins
        player["catches"] = player.get("catches", 0) + 1

        rank_before = get_rank(player["xp"] - xp)
        rank_after = get_rank(player["xp"])
        rank_up = rank_before["name"] != rank_after["name"]

        text = (
            f"🚨 *ПОГОНЯ!*\n\n"
            f"👮 {mention(message)} выехал на вызов!\n\n"
            f"🕐 Выехал — `{start_time}`\n"
            f"✅ Поймал — `{end_time}`\n\n"
            f"📖 {scenario}\n\n"
            f"🎯 *Результат: ПРЕСТУПНИК ЗАДЕРЖАН!*\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"⚡ Опыт: +{xp} XP\n"
            f"💰 Монеты: +{coins}\n"
        )
        if rank_up:
            text += f"\n🎉 *НОВЫЙ РАНГ: {rank_after['name']}!*"
    else:
        reason = random.choice(PURSUIT_FAIL)
        end_time = f"{datetime.now().hour:02d}:{random.randint(10,59):02d}"
        xp_consolation = 5
        player["xp"] = player.get("xp", 0) + xp_consolation

        text = (
            f"🚨 *ПОГОНЯ!*\n\n"
            f"👮 {mention(message)} выехал на вызов!\n\n"
            f"🕐 Выехал — `{start_time}`\n"
            f"❌ Потерял — `{end_time}`\n\n"
            f"📖 {reason}\n\n"
            f"😤 *Результат: ПРЕСТУПНИК УШЁЛ*\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"⚡ Опыт: +{xp_consolation} XP (за попытку)\n"
        )

    save_data(data)
    await message.answer(text, parse_mode="Markdown")

# ══════════════════════════════════════════
#  /cuff — ЗАДЕРЖАНИЕ
# ══════════════════════════════════════════
@dp.message(Command("cuff"))
async def cmd_cuff(message: Message):
    data = load_data()
    uid = message.from_user.id
    player = get_player(data, uid, message.from_user.username or "")

    cd = check_cooldown(player, "cuff")
    if cd > 0:
        await message.answer(
            f"⏳ *Спецснаряжение перезаряжается!*\n"
            f"Ждите ещё: *{fmt_time(cd)}*"
        )
        return

    set_cooldown(player, "cuff")
    player["cuffs"] = player.get("cuffs", 0) + 1

    success_chance = 60
    is_success = random.randint(1, 100) <= success_chance

    if is_success:
        scenario, xp, coins = random.choice(CUFF_SUCCESS)
        player["catches"] = player.get("catches", 0) + 1
        player["xp"] = player.get("xp", 0) + xp
        player["coins"] = player.get("coins", 0) + coins

        rank_before = get_rank(player["xp"] - xp)
        rank_after = get_rank(player["xp"])
        rank_up = rank_before["name"] != rank_after["name"]

        text = (
            f"🔒 *ЗАДЕРЖАНИЕ!*\n\n"
            f"👮 {mention(message)} вышел на операцию...\n\n"
            f"📖 {scenario}\n\n"
            f"✅ *ПРЕСТУПНИК В НАРУЧНИКАХ!*\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"⚡ Опыт: +{xp} XP\n"
            f"💰 Монеты: +{coins}\n"
        )
        if rank_up:
            text += f"\n🎉 *НОВЫЙ РАНГ: {rank_after['name']}!*"
    else:
        scenario, coin_penalty = random.choice(CUFF_FAIL)
        xp_consolation = 8
        player["xp"] = player.get("xp", 0) + xp_consolation
        player["coins"] = max(0, player.get("coins", 0) + coin_penalty)

        text = (
            f"🔒 *ЗАДЕРЖАНИЕ!*\n\n"
            f"👮 {mention(message)} вышел на операцию...\n\n"
            f"📖 {scenario}\n\n"
            f"❌ *ПРЕСТУПНИК УСКОЛЬЗНУЛ*\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"⚡ Опыт: +{xp_consolation} XP\n"
        )
        if coin_penalty < 0:
            text += f"💸 Монеты: {coin_penalty} (штраф за провал)\n"

    save_data(data)
    await message.answer(text, parse_mode="Markdown")

# ══════════════════════════════════════════
#  /patrol — ПАТРУЛЬ
# ══════════════════════════════════════════
@dp.message(Command("patrol"))
async def cmd_patrol(message: Message):
    data = load_data()
    uid = message.from_user.id
    player = get_player(data, uid, message.from_user.username or "")

    cd = check_cooldown(player, "patrol")
    if cd > 0:
        await message.answer(f"⏳ *На отдыхе после патруля!*\nЖдите ещё: *{fmt_time(cd)}*")
        return

    set_cooldown(player, "patrol")
    scenario, xp, coins, success = random.choice(PATROL_EVENTS)
    player["xp"] = player.get("xp", 0) + xp
    player["coins"] = player.get("coins", 0) + coins

    icon = "✅" if success else "😴"
    text = (
        f"👮 *ПАТРУЛЬ*\n\n"
        f"{mention(message)} вышел на маршрут в `{now_str()}`\n\n"
        f"📖 {scenario}\n\n"
        f"{icon} *Смена завершена*\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"⚡ Опыт: +{xp} XP\n"
        f"💰 Монеты: +{coins}\n"
    )
    save_data(data)
    await message.answer(text, parse_mode="Markdown")

# ══════════════════════════════════════════
#  /raid — РЕЙД
# ══════════════════════════════════════════
@dp.message(Command("raid"))
async def cmd_raid(message: Message):
    data = load_data()
    uid = message.from_user.id
    player = get_player(data, uid, message.from_user.username or "")

    cd = check_cooldown(player, "raid")
    if cd > 0:
        await message.answer(f"⏳ *Группа захвата ещё не готова!*\nЖдите ещё: *{fmt_time(cd)}*")
        return

    set_cooldown(player, "raid")
    scenario, xp, coins, success = random.choice(RAID_EVENTS)
    player["xp"] = player.get("xp", 0) + xp
    player["coins"] = player.get("coins", 0) + coins

    icon = "🎯" if success else "😤"
    text = (
        f"🏭 *РЕЙД!*\n\n"
        f"🚔 {mention(message)} возглавил операцию в `{now_str()}`\n\n"
        f"📖 {scenario}\n\n"
        f"{icon} *Рейд {'завершён успешно' if success else 'провалился'}*\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"⚡ Опыт: +{xp} XP\n"
        f"💰 Монеты: +{coins}\n"
    )

    rank_before = get_rank(player["xp"] - xp)
    rank_after = get_rank(player["xp"])
    if rank_before["name"] != rank_after["name"]:
        text += f"\n🎉 *НОВЫЙ РАНГ: {rank_after['name']}!*"

    save_data(data)
    await message.answer(text, parse_mode="Markdown")

# ══════════════════════════════════════════
#  /fine — ШТРАФ
# ══════════════════════════════════════════
FINE_SCENARIOS = [
    ("🚦 Остановил водителя, проехавшего на красный. Штраф выписан!", 8, 20),
    ("📱 Водитель разговаривал по телефону за рулём. Протокол составлен.", 7, 18),
    ("🚗 Парковка в запрещённом месте. Эвакуатор вызван, штраф выписан!", 6, 22),
    ("🏎️ Превышение скорости на 40 км/ч. Лишение прав предложено!", 10, 25),
    ("🍺 Водитель в нетрезвом виде. Протокол и задержание!", 12, 30),
    ("🔦 Езда без фар в тёмное время суток. Предупреждение и штраф.", 5, 15),
]

@dp.message(Command("fine"))
async def cmd_fine(message: Message):
    data = load_data()
    uid = message.from_user.id
    player = get_player(data, uid, message.from_user.username or "")

    cd = check_cooldown(player, "fine")
    if cd > 0:
        await message.answer(f"⏳ *Бланки протоколов закончились!*\nЖдите ещё: *{fmt_time(cd)}*")
        return

    set_cooldown(player, "fine")
    scenario, xp, coins = random.choice(FINE_SCENARIOS)
    player["xp"] = player.get("xp", 0) + xp
    player["coins"] = player.get("coins", 0) + coins

    text = (
        f"📄 *ШТРАФ*\n\n"
        f"👮 {mention(message)} в `{now_str()}`\n\n"
        f"📖 {scenario}\n\n"
        f"✅ *Протокол оформлен*\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"⚡ Опыт: +{xp} XP\n"
        f"💰 Монеты: +{coins}\n"
    )
    save_data(data)
    await message.answer(text, parse_mode="Markdown")

# ══════════════════════════════════════════
#  /bribe — ВЗЯТКА (рисковая операция)
# ══════════════════════════════════════════
@dp.message(Command("bribe"))
async def cmd_bribe(message: Message):
    data = load_data()
    uid = message.from_user.id
    player = get_player(data, uid, message.from_user.username or "")

    cd = check_cooldown(player, "bribe")
    if cd > 0:
        await message.answer(f"⏳ *Служба безопасности следит!*\nЖдите ещё: *{fmt_time(cd)}*")
        return

    set_cooldown(player, "bribe")
    roll = random.randint(1, 100)

    if roll <= 40:   # 40% — большой куш
        xp, coins = 15, random.randint(40, 80)
        text = (
            f"💰 *УСПЕШНАЯ ОПЕРАЦИЯ!*\n\n"
            f"🤫 {mention(message)} принял «благодарность» от задержанного...\n"
            f"Никто ничего не видел.\n\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"⚡ Опыт: +{xp} XP\n"
            f"💰 Монеты: +{coins}\n"
        )
    elif roll <= 70:   # 30% — ничего
        xp = 5
        text = (
            f"🤷 *НИЧЕГО НЕ ВЫШЛО*\n\n"
            f"😤 {mention(message)} попытался получить «благодарность»,\n"
            f"но задержанный оказался принципиальным!\n\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"⚡ Опыт: +{xp} XP\n"
        )
        player["xp"] = player.get("xp", 0) + xp
        save_data(data)
        await message.answer(text, parse_mode="Markdown")
        return
    else:   # 30% — провал, штраф
        penalty = random.randint(20, 50)
        player["coins"] = max(0, player.get("coins", 0) - penalty)
        text = (
            f"🚨 *ПОПАЛСЯ!*\n\n"
            f"😱 {mention(message)} был замечен при получении взятки!\n"
            f"Служба собственной безопасности всё видела...\n\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"💸 Штраф: -{penalty} монет\n"
        )
        save_data(data)
        await message.answer(text, parse_mode="Markdown")
        return

    player["xp"] = player.get("xp", 0) + xp
    player["coins"] = player.get("coins", 0) + coins
    save_data(data)
    await message.answer(text, parse_mode="Markdown")

# ══════════════════════════════════════════
#  /profile — ПРОФИЛЬ
# ══════════════════════════════════════════
@dp.message(Command("profile"))
async def cmd_profile(message: Message):
    data = load_data()
    uid = message.from_user.id
    player = get_player(data, uid, message.from_user.username or "")

    xp = player.get("xp", 0)
    coins = player.get("coins", 0)
    rank = get_rank(xp)
    nxt = next_rank(xp)

    name = message.from_user.first_name
    catches = player.get("catches", 0)
    pursuits = player.get("pursuits", 0)
    pursuits_ok = player.get("pursuits_success", 0)
    cuffs = player.get("cuffs", 0)

    progress_bar = ""
    if nxt:
        needed = nxt["min_xp"] - rank["min_xp"]
        current = xp - rank["min_xp"]
        pct = min(current / needed, 1.0)
        filled = int(pct * 10)
        progress_bar = f"{'█' * filled}{'░' * (10 - filled)} {int(pct*100)}%"
        xp_to_next = nxt["min_xp"] - xp
        next_info = f"⬆️ До следующего ранга: *{xp_to_next} XP*\n{progress_bar}"
    else:
        next_info = "🏆 *Максимальный ранг достигнут!*"

    text = (
        f"🪪 *ЛИЧНОЕ ДЕЛО ОФИЦЕРА*\n\n"
        f"👤 Имя: {name}\n"
        f"🎖️ Звание: {rank['name']}\n\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"⚡ Опыт (XP): *{xp}*\n"
        f"💰 Монеты: *{coins}*\n\n"
        f"{next_info}\n\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"📊 *СТАТИСТИКА*\n"
        f"🚗 Погонь: {pursuits} (успешных: {pursuits_ok})\n"
        f"🔒 Задержаний: {cuffs}\n"
        f"🎯 Всего пойманных: {catches}\n"
    )
    await message.answer(text, parse_mode="Markdown")

# ══════════════════════════════════════════
#  /top — ТОП ИГРОКОВ
# ══════════════════════════════════════════
@dp.message(Command("top"))
async def cmd_top(message: Message):
    data = load_data()
    if not data:
        await message.answer("📊 Пока никто не играл в этом чате!")
        return

    players = [(uid, p) for uid, p in data.items()]
    players.sort(key=lambda x: x[1].get("xp", 0), reverse=True)

    text = "🏆 *ТОП ОФИЦЕРОВ*\n\n"
    medals = ["🥇", "🥈", "🥉"]
    for i, (uid, p) in enumerate(players[:10]):
        medal = medals[i] if i < 3 else f"{i+1}."
        name = p.get("username") or f"Офицер {uid[-4:]}"
        rank = get_rank(p.get("xp", 0))
        xp = p.get("xp", 0)
        catches = p.get("catches", 0)
        text += f"{medal} @{name} — {rank['emoji']} {xp} XP | 🎯 {catches}\n"

    await message.answer(text, parse_mode="Markdown")

# ══════════════════════════════════════════
#  /rank — СПИСОК РАНГОВ
# ══════════════════════════════════════════
@dp.message(Command("rank"))
async def cmd_rank(message: Message):
    data = load_data()
    uid = message.from_user.id
    player = get_player(data, uid, message.from_user.username or "")
    current_rank = get_rank(player.get("xp", 0))

    text = "⭐ *СИСТЕМА РАНГОВ POLICE GAME*\n\n"
    for r in RANKS:
        marker = " ← *ВЫ ЗДЕСЬ*" if r["name"] == current_rank["name"] else ""
        text += f"{r['emoji']} {r['name']} — от {r['min_xp']} XP{marker}\n"

    text += "\n💡 _Каждая операция даёт опыт. Чем сложнее — тем больше!_"
    await message.answer(text, parse_mode="Markdown")

# ══════════════════════════════════════════
#  ЗАПУСК
# ══════════════════════════════════════════
async def main():
    print("🚔 Police Game Bot запущен!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
