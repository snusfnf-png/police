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
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command, CommandStart
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties

# ══════════════════════════════════════════
#  КОНФИГУРАЦИЯ
# ══════════════════════════════════════════
BOT_TOKEN    = os.environ.get("BOT_TOKEN", "")
BOT_USERNAME = os.environ.get("BOT_USERNAME", "")

if not BOT_TOKEN:
    print("❌ Ошибка: переменная BOT_TOKEN не задана!")
    sys.exit(1)

DATA_FILE = "players.json"

# ══════════════════════════════════════════
#  СИСТЕМА РАНГОВ (idx — индекс для проверки доступа)
# ══════════════════════════════════════════
RANKS = [
    {"name": "🪪 Новобранец",        "min_xp": 0,      "emoji": "🪪",  "idx": 0},
    {"name": "👮 Рядовой",            "min_xp": 200,    "emoji": "👮",  "idx": 1},
    {"name": "🔵 Сержант",           "min_xp": 500,    "emoji": "🔵",  "idx": 2},
    {"name": "🟡 Старший сержант",   "min_xp": 900,    "emoji": "🟡",  "idx": 3},
    {"name": "🔴 Лейтенант",         "min_xp": 1500,   "emoji": "🔴",  "idx": 4},
    {"name": "🟠 Старший лейтенант", "min_xp": 2300,   "emoji": "🟠",  "idx": 5},
    {"name": "⭐ Капитан",           "min_xp": 3300,   "emoji": "⭐",  "idx": 6},
    {"name": "🌟 Майор",             "min_xp": 4600,   "emoji": "🌟",  "idx": 7},
    {"name": "💫 Подполковник",      "min_xp": 6200,   "emoji": "💫",  "idx": 8},
    {"name": "🏅 Полковник",         "min_xp": 8200,   "emoji": "🏅",  "idx": 9},
    {"name": "🎖️ Генерал-майор",    "min_xp": 11000,  "emoji": "🎖️", "idx": 10},
    {"name": "🏆 Генерал полиции",   "min_xp": 15000,  "emoji": "🏆",  "idx": 11},
]

# Минимальный idx ранга для команды
CMD_RANK_REQUIRED = {
    "fine":      0,
    "bribe":     0,
    "patrol":    0,
    "cuff":      3,  # Старший сержант
    "pursuit":   3,  # Старший сержант
    "raid":      6,  # Капитан
    "operation": 8,  # Подполковник
}
CMD_RANK_NAMES = {
    "cuff":      "🟡 Старший сержант (900 XP)",
    "pursuit":   "🟡 Старший сержант (900 XP)",
    "raid":      "⭐ Капитан (3300 XP)",
    "operation": "💫 Подполковник (6200 XP)",
}

def get_rank(xp: int) -> dict:
    r = RANKS[0]
    for rank in RANKS:
        if xp >= rank["min_xp"]:
            r = rank
    return r

def next_rank(xp: int):
    for rank in RANKS:
        if xp < rank["min_xp"]:
            return rank
    return None

def get_rank_idx(xp: int) -> int:
    return get_rank(xp)["idx"]

def check_rank_access(player: dict, cmd: str) -> bool:
    return get_rank_idx(player.get("xp", 0)) >= CMD_RANK_REQUIRED.get(cmd, 0)

# ══════════════════════════════════════════
#  КУЛДАУНЫ (секунды)
# ══════════════════════════════════════════
COOLDOWNS = {
    "pursuit":   7200,   # 2 часа
    "cuff":      5400,   # 1.5 часа
    "patrol":    3600,   # 1 час
    "raid":      10800,  # 3 часа
    "fine":      1800,   # 30 минут
    "bribe":     1800,   # 30 минут
    "operation": 14400,  # 4 часа
}

# ══════════════════════════════════════════
#  БД
# ══════════════════════════════════════════
def load_data() -> dict:
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_data(data: dict):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def get_player(data: dict, uid: int, username: str = "") -> dict:
    key = str(uid)
    if key not in data:
        data[key] = {
            "username": username, "xp": 0, "coins": 0,
            "catches": 0, "pursuits": 0, "pursuits_success": 0,
            "cuffs": 0, "operations": 0,
            "last_pursuit": 0, "last_cuff": 0, "last_patrol": 0,
            "last_raid": 0, "last_fine": 0, "last_bribe": 0, "last_operation": 0,
            "items": {},
        }
    p = data[key]
    for f in ["operations", "last_operation", "items"]:
        if f not in p:
            p[f] = {} if f == "items" else 0
    if username:
        p["username"] = username
    return p

# ══════════════════════════════════════════
#  УТИЛИТЫ
# ══════════════════════════════════════════
def check_cooldown(player: dict, action: str) -> int:
    now  = int(datetime.now().timestamp())
    last = player.get(f"last_{action}", 0)
    cd   = COOLDOWNS.get(action, 60)
    return max(0, cd - (now - last))

def set_cooldown(player: dict, action: str):
    player[f"last_{action}"] = int(datetime.now().timestamp())

def fmt_time(s: int) -> str:
    h, r = divmod(s, 3600)
    m, s = divmod(r, 60)
    if h > 0:
        return f"{h} ч {m} мин" if m else f"{h} ч"
    if m > 0:
        return f"{m} мин {s} сек" if s else f"{m} мин"
    return f"{s} сек"

def now_str() -> str:
    return datetime.now().strftime("%H:%M")

def end_time_str(min_offset: int, max_offset: int) -> str:
    """Генерирует время окончания операции (через min–max минут от сейчас, но всегда позже начала)"""
    offset = random.randint(min_offset, max_offset)
    return (datetime.now() + timedelta(minutes=offset)).strftime("%H:%M")

def mention(msg: Message) -> str:
    u = msg.from_user
    return f"@{u.username}" if u.username else f"[{u.first_name}](tg://user?id={u.id})"

def add_xp_coins(p: dict, xp: int, coins: int):
    p["xp"]    = p.get("xp", 0)    + xp
    p["coins"] = p.get("coins", 0) + coins

def rank_up_msg(xp_before: int, xp_after: int) -> str:
    if get_rank(xp_before)["name"] != get_rank(xp_after)["name"]:
        return f"\n\n🎉 *НОВОЕ ЗВАНИЕ: {get_rank(xp_after)['name']}!* 🎉"
    return ""

def use_badge(p: dict) -> int:
    """Применяет нагрудный знак, возвращает бонус XP"""
    if p["items"].get("badge", 0) > 0:
        p["items"]["badge"] -= 1
        if p["items"]["badge"] == 0:
            del p["items"]["badge"]
        return 25
    return 0

def use_radio(p: dict, base: int) -> int:
    """Применяет рацию, возвращает новый шанс успеха"""
    if p["items"].get("radio", 0) > 0:
        p["items"]["radio"] -= 1
        if p["items"]["radio"] == 0:
            del p["items"]["radio"]
        return min(90, base + 20)
    return base

def use_vest(p: dict, penalty: int) -> tuple[int, str]:
    """Применяет бронежилет при штрафе. Возвращает (новый_штраф, заметка)"""
    if penalty < 0 and p["items"].get("vest", 0) > 0:
        p["items"]["vest"] -= 1
        if p["items"]["vest"] == 0:
            del p["items"]["vest"]
        return 0, "\n🦺 *Бронежилет поглотил штраф!*"
    return penalty, ""

# ══════════════════════════════════════════
#  МАГАЗИН
# ══════════════════════════════════════════
SHOP_ITEMS = {
    "coffee": {
        "name": "☕ Кофе бодрости",
        "desc": "Снижает КД следующей команды на 30 минут",
        "price": 80, "emoji": "☕",
    },
    "badge": {
        "name": "🏅 Нагрудный знак",
        "desc": "Даёт +25 XP бонуса к следующей операции",
        "price": 120, "emoji": "🏅",
    },
    "vest": {
        "name": "🦺 Бронежилет",
        "desc": "Защищает от штрафа монет при провале (1 раз)",
        "price": 200, "emoji": "🦺",
    },
    "radio": {
        "name": "📻 Рация спецсвязи",
        "desc": "Повышает шанс успеха следующей погони/задержания на 20%",
        "price": 250, "emoji": "📻",
    },
    "informant": {
        "name": "🕵️ Информатор",
        "desc": "Удваивает монеты со следующего рейда/операции",
        "price": 350, "emoji": "🕵️",
    },
    "stars": {
        "name": "⭐ Звёздный аванс",
        "desc": "Немедленно даёт +150 XP",
        "price": 500, "emoji": "⭐",
    },
}

# ══════════════════════════════════════════
#  СЦЕНАРИИ
# ══════════════════════════════════════════
PATROL_EVENTS = [
    ("🔍 Заметил угнанный автомобиль — вызвал эвакуатор, преступника разыскивают.", 18, 12, True),
    ("🤝 Помог найти потерявшегося ребёнка. Репутация офицера растёт!", 15, 10, True),
    ("🚯 Задержал хулигана с баллончиком краски у школы.", 20, 14, True),
    ("☕ Спокойная смена. Кофе, квартал, тишина.", 8, 6, False),
    ("📢 Разогнал шумную компанию у подъезда. Жители благодарны!", 14, 9, True),
    ("🚘 Остановил пьяного водителя. Задержан до вытрезвления.", 25, 18, True),
    ("👀 Засёк карманника в толпе и задержал на месте!", 28, 20, True),
    ("🌧️ Дождливая смена. Помог аварийной машине добраться до заправки.", 12, 8, False),
    ("🐕 Поймал сбежавшую опасную собаку — хозяин благодарен.", 10, 7, False),
    ("🔦 Обнаружил открытый люк и оградил его. Предотвратил несчастный случай.", 12, 9, True),
    ("🏪 Предотвратил мелкое ограбление магазина — преступник убежал, но товар цел.", 22, 15, True),
    ("📦 Остановил подозрительный фургон — оказался с краденым грузом.", 30, 22, True),
]

FINE_SCENARIOS = [
    ("🚦 Проехал на красный — штраф выписан!", 10, 22),
    ("📱 Телефон за рулём — протокол составлен.", 9, 20),
    ("🚗 Парковка в запрещённом месте — эвакуатор.", 8, 25),
    ("🏎️ Превышение на 40 км/ч — штраф и предупреждение.", 12, 28),
    ("🍺 Пьяный водитель — протокол и задержание!", 15, 35),
    ("🔦 Езда без фар ночью — штраф и нотация.", 7, 18),
    ("🚲 Велосипедист на проезжей части без шлема.", 6, 14),
    ("🚛 Грузовик в жилой зоне не в то время.", 11, 24),
    ("🏍️ Мотоциклист без прав — задержан!", 14, 30),
    ("🐾 Выгул собаки без намордника в общественном месте.", 5, 12),
]

PURSUIT_SUCCESS = [
    ("🚗 Преступник пытался уйти через дворы — прижат к забору!", 55, 38),
    ("🏃 Пешая погоня — настиг у входа в метро!", 60, 42),
    ("🚁 Вертолёт отследил маршрут — машина остановлена!", 70, 50),
    ("💨 Крутой манёвр — преступник в кювете. Задержан!", 50, 35),
    ("🛑 Шипы на дороге спустили шины — никуда не ушёл!", 48, 32),
    ("🌉 На мосту перекрыли путь — деваться некуда!", 65, 45),
    ("📡 Видеонаблюдение установило маршрут — перехвачен!", 58, 40),
    ("🤝 Коллеги из соседнего района взяли в кольцо!", 75, 55),
    ("🚔 Таран бампером — автомобиль заглох на перекрёстке!", 68, 48),
    ("🎯 Снайпер выбил колесо — машина остановилась сама.", 72, 52),
]

PURSUIT_FAIL = [
    "🚗💥 ДТП на перекрёстке — красный светофор в самый неподходящий момент.",
    "⛽ Закончилось топливо! Кто последний раз заправлял машину?!",
    "🛞 Лопнуло колесо на скорости 130 км/ч.",
    "📻 Рация сломалась — потерял координацию с коллегами.",
    "🌫️ Густой туман — пришлось снизить скорость, преступник ушёл.",
    "🚧 Строительный объезд завёл в тупик.",
    "🐕 Стая собак на дороге — пришлось экстренно тормозить.",
    "🚌 Автобус перекрыл перекрёсток в нужный момент.",
    "🌧️ Ливень — потерял машину из виду.",
    "📱 Навигатор завёл не туда — классика!",
    "🏗️ Поднятый мост. Пока ждал — преступник давно исчез.",
    "😴 Напарник задремал и пропустил поворот. Опоздали.",
    "🚑 Перекрыл дорогу скорой помощи — пришлось уступить.",
]

CUFF_SUCCESS = [
    ("🏃 Преступник выбежал из подъезда — офицер уже ждал за углом!", 75, 50),
    ("🎭 Маскировка под гражданского сработала — сам подошёл!", 70, 46),
    ("🐕‍🦺 Служебная собака Рекс взяла след и загнала в угол!", 85, 58),
    ("📷 Слежка через камеры — взяли прямо у его дома!", 68, 44),
    ("🤝 Агент под прикрытием передал точное местоположение!", 80, 55),
    ("🏙️ Засада в переулке — не догадывался, что его ждут!", 72, 48),
    ("🚔 Три машины перекрыли все выходы. Сдался без сопротивления!", 90, 62),
    ("🎯 Снайперское наблюдение + штурм — задержан за 30 секунд!", 95, 65),
    ("🕵️ Информатор сдал точку — взяли прямо за столом!", 88, 60),
    ("🔐 Вскрыли дверь и накрыли спящим. Даже не проснулся!", 78, 52),
]

CUFF_FAIL = [
    ("😤 Оказался опытным бойцом и вырвался.", -8),
    ("🚪 Выбил дверь — чёрный ход. Ушёл через дворы.", 0),
    ("🤦 Перепутал адрес! Задержали не того человека.", -12),
    ("📵 Связь с группой захвата пропала в нужный момент.", 0),
    ("🌑 Затаился в темноте склада — найти не удалось.", 0),
    ("🏃💨 Опытный бегун — просто не успели.", 0),
    ("🔑 Дверь бронированная — инструментов не хватило.", 0),
    ("🎭 Преступник переоделся — потеряли из виду на рынке.", 0),
]

RAID_EVENTS = [
    ("🏭 Рейд на подпольный склад! Контрабанда изъята на крупную сумму.", 140, 95, True),
    ("🎰 Накрыли подпольное казино! 15 задержанных.", 120, 85, True),
    ("💊 Ликвидирована точка сбыта запрещённых веществ.", 160, 110, True),
    ("🔫 Изъяли нелегальное оружие у группировки.", 150, 100, True),
    ("📦 Поддельный товар изъят, владелец задержан.", 110, 75, True),
    ("🚫 Рейд не принёс результата — информация ложная.", 15, 8, False),
    ("🏠 Обыск в явочной квартире — компромат на преступную сеть!", 160, 115, True),
    ("💻 Накрыли хакерскую группу. Серверы изъяты.", 170, 120, True),
    ("🚢 Рейд на порт — нелегальный груз задержан.", 155, 108, True),
    ("🔥 Ликвидирован цех по производству поддельных документов.", 145, 98, True),
]

OPERATION_SUCCESS = [
    ("🕵️ Преступный синдикат уничтожен после многомесячной разработки! 30 задержанных.", 280, 200),
    ("💣 Предотвращён крупный теракт. Группа нейтрализована без жертв.", 320, 240),
    ("🌍 Международная операция совместно с Интерполом завершилась успехом!", 300, 220),
    ("💰 Заморожены активы клана на 10 млн. Лидер задержан.", 290, 210),
    ("🔒 Ликвидирована сеть торговли людьми. 50 человек освобождены.", 350, 260),
    ("🏦 Предотвращено ограбление банка — все члены группы задержаны.", 310, 230),
]

OPERATION_FAIL = [
    ("🕵️ Крот в ведомстве — преступники предупреждены заранее. Операция провалена.", -30),
    ("📡 Глушилки заблокировали связь в критический момент.", -10),
    ("🚁 Вертолёт поддержки опоздал. Отступили без потерь, но без результата.", 0),
    ("🌧️ Буря помешала высадке группы. Операция перенесена.", 0),
]

# ══════════════════════════════════════════
#  БОТ
# ══════════════════════════════════════════
bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.MARKDOWN))
dp  = Dispatcher()

# ══════════════════════════════════════════
#  GUARD: проверка ранга и КД
# ══════════════════════════════════════════
async def guard(msg: Message, player: dict, cmd: str) -> bool:
    if not check_rank_access(player, cmd):
        req = CMD_RANK_NAMES.get(cmd, "более высокого ранга")
        await msg.answer(
            f"🔒 *Команда недоступна!*\n\n"
            f"Требуется звание: *{req}*\n"
            f"Твой прогресс: /rank"
        )
        return False
    cd = check_cooldown(player, cmd)
    if cd > 0:
        ready = (datetime.now() + timedelta(seconds=cd)).strftime("%H:%M")
        await msg.answer(
            f"⏳ *Команда на перезарядке*\n"
            f"Осталось: *{fmt_time(cd)}*\n"
            f"Доступно в: `{ready}`"
        )
        return False
    return True

# ══════════════════════════════════════════
#  КОМАНДЫ
# ══════════════════════════════════════════
@dp.message(CommandStart())
async def cmd_start(msg: Message):
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(
            text="➕ Добавить бота в чат",
            url=f"https://t.me/{BOT_USERNAME}?startgroup=true",
            style="success"
        )
    ]])
    await msg.answer(
        "🚔 *POLICE GAME BOT* 🚔\n\n"
        "Добро пожаловать в полицейскую академию!\n\n"
        "Ты — офицер полиции. Тебя ждут патрули, штрафы, погони, "
        "рейды и элитные операции. Карьерный путь — от Новобранца "
        "до Генерала полиции.\n\n"
        "⚡ 12 рангов | 💰 Экономика | 🛒 Магазин\n"
        "🔒 Новые команды открываются с ростом звания\n\n"
        "📋 /help — все команды\n"
        "🪪 Начни с /fine или /patrol",
        reply_markup=kb
    )


@dp.message(Command("help"))
async def cmd_help(msg: Message):
    await msg.answer(
        "📋 *КОМАНДЫ POLICE GAME BOT*\n\n"
        "━━━━━ 🟢 ДОСТУПНО ВСЕМ ━━━━━\n"
        "/fine — 📄 Выписать штраф\n"
        "_КД: 30 мин_\n\n"
        "/bribe — 💰 Рисковая «благодарность»\n"
        "_КД: 30 мин | Можно потерять монеты!_\n\n"
        "/patrol — 👮 Патруль района\n"
        "_КД: 1 час_\n\n"
        "━━━━━ 🟡 СТ. СЕРЖАНТ (900 XP) ━━━━━\n"
        "/pursuit — 🚗 Погоня\n"
        "_КД: 2 часа_\n\n"
        "/cuff — 🔒 Задержание\n"
        "_КД: 1.5 часа_\n\n"
        "━━━━━ ⭐ КАПИТАН (3300 XP) ━━━━━\n"
        "/raid — 🏭 Рейд\n"
        "_КД: 3 часа_\n\n"
        "━━━━━ 💫 ПОДПОЛКОВНИК (6200 XP) ━━━━━\n"
        "/operation — 🕵️ Элитная операция\n"
        "_КД: 4 часа_\n\n"
        "━━━━━ 📊 ПРОЧЕЕ ━━━━━\n"
        "/profile — 🪪 Профиль\n"
        "/top — 🏆 Топ офицеров\n"
        "/rank — ⭐ Список рангов\n"
        "/shop — 🛒 Магазин\n"
        "/inventory — 🎒 Инвентарь\n"
        "/buy <предмет> — купить из магазина\n"
    )


@dp.message(Command("patrol"))
async def cmd_patrol(msg: Message):
    data = load_data()
    p    = get_player(data, msg.from_user.id, msg.from_user.username or "")
    if not await guard(msg, p, "patrol"):
        return

    set_cooldown(p, "patrol")
    scenario, xp, coins, success = random.choice(PATROL_EVENTS)
    bonus_xp  = use_badge(p)
    xp_before = p.get("xp", 0)
    add_xp_coins(p, xp + bonus_xp, coins)

    icon = "✅" if success else "😴"
    text = (
        f"👮 *ПАТРУЛЬ*\n\n"
        f"{mention(msg)} вышел на маршрут в `{now_str()}`\n\n"
        f"📖 {scenario}\n\n"
        f"{icon} *Смена завершена*\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"⚡ Опыт: +{xp}{f' +{bonus_xp}🏅' if bonus_xp else ''} XP\n"
        f"💰 Монеты: +{coins}\n"
    )
    text += rank_up_msg(xp_before, p["xp"])
    save_data(data)
    await msg.answer(text)


@dp.message(Command("fine"))
async def cmd_fine(msg: Message):
    data = load_data()
    p    = get_player(data, msg.from_user.id, msg.from_user.username or "")
    if not await guard(msg, p, "fine"):
        return

    set_cooldown(p, "fine")
    scenario, xp, coins = random.choice(FINE_SCENARIOS)
    bonus_xp  = use_badge(p)
    xp_before = p.get("xp", 0)
    add_xp_coins(p, xp + bonus_xp, coins)

    text = (
        f"📄 *ШТРАФ*\n\n"
        f"👮 {mention(msg)} в `{now_str()}`\n\n"
        f"📖 {scenario}\n\n"
        f"✅ *Протокол оформлен*\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"⚡ Опыт: +{xp}{f' +{bonus_xp}🏅' if bonus_xp else ''} XP\n"
        f"💰 Монеты: +{coins}\n"
    )
    text += rank_up_msg(xp_before, p["xp"])
    save_data(data)
    await msg.answer(text)


@dp.message(Command("bribe"))
async def cmd_bribe(msg: Message):
    data = load_data()
    p    = get_player(data, msg.from_user.id, msg.from_user.username or "")
    if not await guard(msg, p, "bribe"):
        return

    set_cooldown(p, "bribe")
    roll = random.randint(1, 100)

    if roll <= 40:
        xp, coins = 15, random.randint(45, 90)
        add_xp_coins(p, xp, coins)
        text = (
            f"💰 *ПРОШЛО ЧИСТО!*\n\n"
            f"🤫 {mention(msg)} принял «благодарность»...\n"
            f"Никто ничего не видел.\n\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"⚡ Опыт: +{xp} XP\n"
            f"💰 Монеты: +{coins}\n"
        )
    elif roll <= 70:
        add_xp_coins(p, 5, 0)
        text = (
            f"🤷 *НИЧЕГО НЕ ВЫШЛО*\n\n"
            f"😤 {mention(msg)} попытался получить «благодарность»,\n"
            f"но задержанный оказался принципиальным!\n\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"⚡ Опыт: +5 XP\n"
        )
    else:
        penalty = -random.randint(25, 60)
        penalty, shield = use_vest(p, penalty)
        if penalty < 0:
            p["coins"] = max(0, p.get("coins", 0) + penalty)
        text = (
            f"🚨 *ПОПАЛСЯ!*\n\n"
            f"😱 {mention(msg)} замечен при получении взятки!\n"
            f"Служба безопасности всё видела...\n\n"
            f"━━━━━━━━━━━━━━━━━━\n"
        )
        text += f"💸 Штраф: {penalty} монет\n" if penalty < 0 else "💸 Монеты: 0 (бронежилет спас)\n"
        text += shield

    save_data(data)
    await msg.answer(text)


@dp.message(Command("pursuit"))
async def cmd_pursuit(msg: Message):
    data = load_data()
    p    = get_player(data, msg.from_user.id, msg.from_user.username or "")
    if not await guard(msg, p, "pursuit"):
        return

    start = now_str()
    set_cooldown(p, "pursuit")
    p["pursuits"] = p.get("pursuits", 0) + 1

    chance     = use_radio(p, 55)
    is_success = random.randint(1, 100) <= chance
    end        = end_time_str(8, 55)  # всегда >= 8 минут после старта

    if is_success:
        scenario, xp, coins = random.choice(PURSUIT_SUCCESS)
        p["pursuits_success"] = p.get("pursuits_success", 0) + 1
        p["catches"]          = p.get("catches", 0) + 1
        bonus_xp  = use_badge(p)
        xp_before = p.get("xp", 0)
        add_xp_coins(p, xp + bonus_xp, coins)

        text = (
            f"🚨 *ПОГОНЯ!*\n\n"
            f"👮 {mention(msg)} выехал на вызов!\n\n"
            f"🕐 Выехал — `{start}`\n"
            f"✅ Поймал — `{end}`\n\n"
            f"📖 {scenario}\n\n"
            f"🎯 *ПРЕСТУПНИК ЗАДЕРЖАН!*\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"⚡ Опыт: +{xp}{f' +{bonus_xp}🏅' if bonus_xp else ''} XP\n"
            f"💰 Монеты: +{coins}\n"
        )
        text += rank_up_msg(xp_before, p["xp"])
    else:
        reason    = random.choice(PURSUIT_FAIL)
        xp_before = p.get("xp", 0)
        add_xp_coins(p, 8, 0)

        text = (
            f"🚨 *ПОГОНЯ!*\n\n"
            f"👮 {mention(msg)} выехал на вызов!\n\n"
            f"🕐 Выехал — `{start}`\n"
            f"❌ Потерял — `{end}`\n\n"
            f"📖 {reason}\n\n"
            f"😤 *ПРЕСТУПНИК УШЁЛ*\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"⚡ Опыт: +8 XP (за попытку)\n"
        )

    save_data(data)
    await msg.answer(text)


@dp.message(Command("cuff"))
async def cmd_cuff(msg: Message):
    data = load_data()
    p    = get_player(data, msg.from_user.id, msg.from_user.username or "")
    if not await guard(msg, p, "cuff"):
        return

    set_cooldown(p, "cuff")
    p["cuffs"] = p.get("cuffs", 0) + 1

    chance     = use_radio(p, 60)
    is_success = random.randint(1, 100) <= chance

    if is_success:
        scenario, xp, coins = random.choice(CUFF_SUCCESS)
        p["catches"] = p.get("catches", 0) + 1
        bonus_xp     = use_badge(p)
        xp_before    = p.get("xp", 0)
        add_xp_coins(p, xp + bonus_xp, coins)

        text = (
            f"🔒 *ЗАДЕРЖАНИЕ!*\n\n"
            f"👮 {mention(msg)} вышел на операцию в `{now_str()}`\n\n"
            f"📖 {scenario}\n\n"
            f"✅ *ПРЕСТУПНИК В НАРУЧНИКАХ!*\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"⚡ Опыт: +{xp}{f' +{bonus_xp}🏅' if bonus_xp else ''} XP\n"
            f"💰 Монеты: +{coins}\n"
        )
        text += rank_up_msg(xp_before, p["xp"])
    else:
        scenario, coin_pen = random.choice(CUFF_FAIL)
        coin_pen, shield   = use_vest(p, coin_pen)
        xp_before          = p.get("xp", 0)
        add_xp_coins(p, 10, 0)
        if coin_pen < 0:
            p["coins"] = max(0, p.get("coins", 0) + coin_pen)

        text = (
            f"🔒 *ЗАДЕРЖАНИЕ!*\n\n"
            f"👮 {mention(msg)} вышел на операцию в `{now_str()}`\n\n"
            f"📖 {scenario}\n\n"
            f"❌ *ПРЕСТУПНИК УСКОЛЬЗНУЛ*\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"⚡ Опыт: +10 XP\n"
        )
        if coin_pen < 0:
            text += f"💸 Монеты: {coin_pen}\n"
        text += shield

    save_data(data)
    await msg.answer(text)


@dp.message(Command("raid"))
async def cmd_raid(msg: Message):
    data = load_data()
    p    = get_player(data, msg.from_user.id, msg.from_user.username or "")
    if not await guard(msg, p, "raid"):
        return

    set_cooldown(p, "raid")
    scenario, xp, coins, success = random.choice(RAID_EVENTS)

    inf_note = ""
    if success and p["items"].get("informant", 0) > 0:
        coins *= 2
        p["items"]["informant"] -= 1
        if p["items"]["informant"] == 0:
            del p["items"]["informant"]
        inf_note = "\n🕵️ *Информатор удвоил монеты!*"

    bonus_xp  = use_badge(p) if success else 0
    xp_before = p.get("xp", 0)
    add_xp_coins(p, xp + bonus_xp, coins)

    icon = "🎯" if success else "😤"
    text = (
        f"🏭 *РЕЙД!*\n\n"
        f"🚔 {mention(msg)} возглавил операцию в `{now_str()}`\n\n"
        f"📖 {scenario}\n\n"
        f"{icon} *Рейд {'успешен' if success else 'провалился'}*\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"⚡ Опыт: +{xp}{f' +{bonus_xp}🏅' if bonus_xp else ''} XP\n"
        f"💰 Монеты: +{coins}{inf_note}\n"
    )
    text += rank_up_msg(xp_before, p["xp"])
    save_data(data)
    await msg.answer(text)


@dp.message(Command("operation"))
async def cmd_operation(msg: Message):
    data = load_data()
    p    = get_player(data, msg.from_user.id, msg.from_user.username or "")
    if not await guard(msg, p, "operation"):
        return

    set_cooldown(p, "operation")
    p["operations"] = p.get("operations", 0) + 1
    is_success = random.randint(1, 100) <= 65

    if is_success:
        scenario, xp, coins = random.choice(OPERATION_SUCCESS)
        inf_note = ""
        if p["items"].get("informant", 0) > 0:
            coins = int(coins * 1.5)
            p["items"]["informant"] -= 1
            if p["items"]["informant"] == 0:
                del p["items"]["informant"]
            inf_note = "\n🕵️ *Информатор дал +50% монет!*"

        xp_before = p.get("xp", 0)
        add_xp_coins(p, xp, coins)
        p["catches"] = p.get("catches", 0) + 5

        text = (
            f"🕵️ *ЭЛИТНАЯ ОПЕРАЦИЯ*\n\n"
            f"🚔 {mention(msg)} возглавил спецгруппу в `{now_str()}`\n\n"
            f"📖 {scenario}\n\n"
            f"✅ *ОПЕРАЦИЯ УСПЕШНА!*\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"⚡ Опыт: +{xp} XP\n"
            f"💰 Монеты: +{coins}{inf_note}\n"
        )
        text += rank_up_msg(xp_before, p["xp"])
    else:
        scenario, coin_pen = random.choice(OPERATION_FAIL)
        xp_before = p.get("xp", 0)
        add_xp_coins(p, 20, 0)
        if coin_pen < 0:
            p["coins"] = max(0, p.get("coins", 0) + coin_pen)

        text = (
            f"🕵️ *ЭЛИТНАЯ ОПЕРАЦИЯ*\n\n"
            f"🚔 {mention(msg)} возглавил спецгруппу в `{now_str()}`\n\n"
            f"📖 {scenario}\n\n"
            f"❌ *ОПЕРАЦИЯ ПРОВАЛЕНА*\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"⚡ Опыт: +20 XP\n"
        )
        if coin_pen < 0:
            text += f"💸 Монеты: {coin_pen}\n"

    save_data(data)
    await msg.answer(text)


@dp.message(Command("shop"))
async def cmd_shop(msg: Message):
    text = "🛒 *МАГАЗИН ПОЛИЦЕЙСКОГО*\n\n"
    for key, item in SHOP_ITEMS.items():
        text += (
            f"{item['emoji']} *{item['name']}*\n"
            f"   💰 {item['price']} монет\n"
            f"   📝 {item['desc']}\n"
            f"   → `/buy {key}`\n\n"
        )
    text += "💡 _Предметы одноразовые, применяются автоматически._"
    await msg.answer(text)


@dp.message(Command("buy"))
async def cmd_buy(msg: Message):
    data = load_data()
    p    = get_player(data, msg.from_user.id, msg.from_user.username or "")

    args = msg.text.split()
    if len(args) < 2:
        await msg.answer("❓ Укажи предмет: `/buy <название>`\nСписок: /shop")
        return

    key = args[1].lower()
    if key not in SHOP_ITEMS:
        await msg.answer(f"❌ Предмет `{key}` не найден. Смотри /shop")
        return

    item = SHOP_ITEMS[key]

    # Особый случай: звёздный аванс применяется сразу
    if key == "stars":
        if p.get("coins", 0) < item["price"]:
            await msg.answer(f"💸 Нужно {item['price']} 💰, у тебя {p.get('coins',0)} 💰")
            return
        p["coins"] -= item["price"]
        xp_before = p.get("xp", 0)
        p["xp"] = xp_before + 150
        save_data(data)
        text = (
            f"✅ *Куплено: ⭐ Звёздный аванс*\n\n"
            f"⚡ Получено: +150 XP немедленно!\n"
            f"💰 Осталось монет: {p['coins']}\n"
        )
        text += rank_up_msg(xp_before, p["xp"])
        await msg.answer(text)
        return

    # Кофе: снижает КД одной команды
    if key == "coffee":
        if p.get("coins", 0) < item["price"]:
            await msg.answer(f"💸 Нужно {item['price']} 💰, у тебя {p.get('coins',0)} 💰")
            return
        # Найдём команду с наибольшим КД
        cmds = ["pursuit", "cuff", "raid", "operation", "patrol", "fine", "bribe"]
        best_cmd = max(cmds, key=lambda c: check_cooldown(p, c))
        cd_before = check_cooldown(p, best_cmd)
        if cd_before == 0:
            await msg.answer("☕ Все команды уже готовы — кофе не нужен!")
            return
        reduction = 1800  # 30 минут
        new_last   = p.get(f"last_{best_cmd}", 0) - reduction
        p[f"last_{best_cmd}"] = new_last
        p["coins"] -= item["price"]
        cd_after = check_cooldown(p, best_cmd)
        save_data(data)
        await msg.answer(
            f"☕ *Кофе выпит!*\n\n"
            f"КД команды `/{best_cmd}` снижен на 30 минут.\n"
            f"Осталось ждать: *{fmt_time(cd_after)}*\n"
            f"💰 Осталось монет: {p['coins']}"
        )
        return

    # Обычная покупка
    if p.get("coins", 0) < item["price"]:
        need = item["price"] - p.get("coins", 0)
        await msg.answer(
            f"💸 *Недостаточно монет!*\n\n"
            f"Нужно: {item['price']} 💰\n"
            f"У тебя: {p.get('coins',0)} 💰\n"
            f"Не хватает: {need} 💰"
        )
        return

    p["coins"] -= item["price"]
    p["items"][key] = p["items"].get(key, 0) + 1
    save_data(data)
    await msg.answer(
        f"✅ *Куплено: {item['emoji']} {item['name']}*\n\n"
        f"📝 {item['desc']}\n\n"
        f"💰 Осталось монет: {p['coins']}"
    )


@dp.message(Command("inventory"))
async def cmd_inventory(msg: Message):
    data  = load_data()
    p     = get_player(data, msg.from_user.id, msg.from_user.username or "")
    items = {k: v for k, v in p.get("items", {}).items() if v > 0}

    if not items:
        await msg.answer("🎒 *Инвентарь пуст*\n\nКупи что-нибудь в /shop!")
        return

    text = "🎒 *МОЙ ИНВЕНТАРЬ*\n\n"
    for key, qty in items.items():
        item = SHOP_ITEMS.get(key)
        if item:
            text += f"{item['emoji']} {item['name']} — x{qty}\n"
    text += "\n_Предметы применяются автоматически при следующей операции._"
    await msg.answer(text)


@dp.message(Command("profile"))
async def cmd_profile(msg: Message):
    data = load_data()
    p    = get_player(data, msg.from_user.id, msg.from_user.username or "")

    xp    = p.get("xp", 0)
    coins = p.get("coins", 0)
    rank  = get_rank(xp)
    nxt   = next_rank(xp)

    if nxt:
        needed  = nxt["min_xp"] - rank["min_xp"]
        current = xp - rank["min_xp"]
        pct     = min(current / needed, 1.0)
        filled  = int(pct * 10)
        bar     = f"{'█' * filled}{'░' * (10 - filled)} {int(pct*100)}%"
        prog    = f"⬆️ До *{nxt['name']}*: *{nxt['min_xp'] - xp} XP*\n`{bar}`"
    else:
        prog = "🏆 *Максимальный ранг достигнут!*"

    await msg.answer(
        f"🪪 *ЛИЧНОЕ ДЕЛО ОФИЦЕРА*\n\n"
        f"👤 {msg.from_user.first_name}\n"
        f"🎖️ Звание: {rank['name']}\n\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"⚡ Опыт: *{xp} XP*\n"
        f"💰 Монеты: *{coins}*\n\n"
        f"{prog}\n\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"📊 *СТАТИСТИКА*\n"
        f"🚗 Погонь: {p.get('pursuits',0)} (успешных: {p.get('pursuits_success',0)})\n"
        f"🔒 Задержаний: {p.get('cuffs',0)}\n"
        f"🕵️ Элитных операций: {p.get('operations',0)}\n"
        f"🎯 Всего поймано: {p.get('catches',0)}\n"
    )


@dp.message(Command("top"))
async def cmd_top(msg: Message):
    data = load_data()
    if not data:
        await msg.answer("📊 Пока никто не играл!")
        return

    players = sorted(data.items(), key=lambda x: x[1].get("xp", 0), reverse=True)
    medals  = ["🥇", "🥈", "🥉"]
    text    = "🏆 *ТОП ОФИЦЕРОВ*\n\n"
    for i, (uid, pl) in enumerate(players[:10]):
        med  = medals[i] if i < 3 else f"{i+1}."
        name = pl.get("username") or f"Офицер{uid[-4:]}"
        rank = get_rank(pl.get("xp", 0))
        text += f"{med} @{name} — {rank['emoji']} {pl.get('xp',0)} XP | 🎯 {pl.get('catches',0)}\n"
    await msg.answer(text)


@dp.message(Command("rank"))
async def cmd_rank(msg: Message):
    data = load_data()
    p    = get_player(data, msg.from_user.id, msg.from_user.username or "")
    cur  = get_rank(p.get("xp", 0))

    text = "⭐ *СИСТЕМА РАНГОВ*\n\n"
    for r in RANKS:
        me      = " ✅ *← ВЫ*" if r["name"] == cur["name"] else ""
        unlocks = {
            "🟡 Старший сержант": " 🔓 _погоня, задержание_",
            "⭐ Капитан":         " 🔓 _рейд_",
            "💫 Подполковник":    " 🔓 _элитные операции_",
        }.get(r["name"], "")
        text += f"{r['emoji']} {r['name']} — {r['min_xp']} XP{me}{unlocks}\n"
    text += "\n💡 _Чем выше ранг — тем мощнее задания._"
    await msg.answer(text)


# ══════════════════════════════════════════
#  ЗАПУСК
# ══════════════════════════════════════════
async def main():
    print("🚔 Police Game Bot запущен!")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
