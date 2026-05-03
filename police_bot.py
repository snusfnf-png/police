"""
🚔 POLICE GAME BOT
Переменные окружения Railway:
  BOT_TOKEN    — токен от @BotFather
  BOT_USERNAME — username бота без @
"""

import asyncio, random, json, os, sys, sqlite3
from datetime import datetime, timedelta, timezone, date
from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    Message, CallbackQuery,
    InlineKeyboardMarkup, InlineKeyboardButton,
)
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties

# ══════════════════════════════════════════
#  КОНФИГУРАЦИЯ
# ══════════════════════════════════════════
BOT_TOKEN    = os.environ.get("BOT_TOKEN", "")
BOT_USERNAME = os.environ.get("BOT_USERNAME", "")
ADMIN_USERNAME = "tntks"   # без @

if not BOT_TOKEN:
    print("❌ BOT_TOKEN не задан!"); sys.exit(1)

DATA_FILE = "players.json"
MSK = timezone(timedelta(hours=3))

def msk_now() -> datetime:
    return datetime.now(MSK)

def now_str() -> str:
    return msk_now().strftime("%H:%M")

def today_str() -> str:
    return msk_now().strftime("%Y-%m-%d")

# ══════════════════════════════════════════
#  БД (JSON)
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
        d = today_str()
        data[key] = {
            "username": username, "xp": 0, "coins": 0,
            "catches": 0, "pursuits": 0, "pursuits_success": 0,
            "cuffs": 0, "operations": 0,
            "last_pursuit": 0, "last_cuff": 0, "last_patrol": 0,
            "last_raid": 0, "last_fine": 0, "last_bribe": 0,
            "last_operation": 0, "last_radar_income": 0,
            "has_radar": False, "radar_count": 0,
            "items": {}, "joined": d,
        }
        # статистика по дням
        stats = load_stats()
        stats[d] = stats.get(d, 0) + 1
        save_stats(stats)
    p = data[key]
    for f in ["operations","last_operation","items","has_radar","radar_count",
              "last_radar_income","joined"]:
        if f not in p:
            if f == "items": p[f] = {}
            elif f in ("has_radar",): p[f] = False
            elif f == "joined": p[f] = today_str()
            else: p[f] = 0
    if username:
        p["username"] = username
    return p

STATS_FILE = "daily_stats.json"

def load_stats() -> dict:
    if os.path.exists(STATS_FILE):
        with open(STATS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_stats(s: dict):
    with open(STATS_FILE, "w", encoding="utf-8") as f:
        json.dump(s, f, ensure_ascii=False, indent=2)

# ══════════════════════════════════════════
#  РАНГИ
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

CMD_RANK_REQUIRED = {
    "ticket": 0, "bribe": 0, "patrol": 0,
    "arrest": 3, "pursuit": 3,
    "raid": 6, "operation": 8, "radar": 11,
}
CMD_RANK_NAMES = {
    "arrest":    "🟡 Старший сержант (900 XP)",
    "pursuit":   "🟡 Старший сержант (900 XP)",
    "raid":      "⭐ Капитан (3300 XP)",
    "operation": "💫 Подполковник (6200 XP)",
    "radar":     "🏆 Генерал полиции (15000 XP)",
}

def get_rank(xp: int) -> dict:
    r = RANKS[0]
    for rank in RANKS:
        if xp >= rank["min_xp"]: r = rank
    return r

def next_rank(xp: int):
    for rank in RANKS:
        if xp < rank["min_xp"]: return rank
    return None

def get_rank_idx(xp: int) -> int:
    return get_rank(xp)["idx"]

def check_rank_access(player: dict, cmd: str) -> bool:
    return get_rank_idx(player.get("xp", 0)) >= CMD_RANK_REQUIRED.get(cmd, 0)

# ══════════════════════════════════════════
#  КУЛДАУНЫ
# ══════════════════════════════════════════
COOLDOWNS = {
    "pursuit": 7200, "arrest": 5400, "patrol": 3600,
    "raid": 10800, "ticket": 1800, "bribe": 1800, "operation": 14400,
}

def check_cooldown(p: dict, action: str) -> int:
    now = int(msk_now().timestamp())
    return max(0, COOLDOWNS.get(action, 60) - (now - p.get(f"last_{action}", 0)))

def set_cooldown(p: dict, action: str):
    p[f"last_{action}"] = int(msk_now().timestamp())

def fmt_time(s: int) -> str:
    h, r = divmod(s, 3600); m, s = divmod(r, 60)
    if h > 0: return f"{h} ч {m} мин" if m else f"{h} ч"
    if m > 0: return f"{m} мин {s} сек" if s else f"{m} мин"
    return f"{s} сек"

def end_time_str(mn: int, mx: int) -> str:
    return (msk_now() + timedelta(minutes=random.randint(mn, mx))).strftime("%H:%M")

def mention(msg: Message) -> str:
    u = msg.from_user
    return f"@{u.username}" if u.username else f"[{u.first_name}](tg://user?id={u.id})"

def mention_name(msg: Message) -> str:
    return msg.from_user.first_name

def add_xp_coins(p: dict, xp: int, coins: int):
    p["xp"]    = p.get("xp", 0) + xp
    p["coins"] = p.get("coins", 0) + coins

def rank_up_msg(xp_before: int, xp_after: int) -> str:
    if get_rank(xp_before)["name"] != get_rank(xp_after)["name"]:
        return f"\n\n🎉 *НОВОЕ ЗВАНИЕ: {get_rank(xp_after)['name']}!* 🎉"
    return ""

def use_badge(p: dict) -> int:
    if p["items"].get("badge", 0) > 0:
        p["items"]["badge"] -= 1
        if not p["items"]["badge"]: del p["items"]["badge"]
        return 25
    return 0

def use_radio(p: dict, base: int) -> int:
    if p["items"].get("radio", 0) > 0:
        p["items"]["radio"] -= 1
        if not p["items"]["radio"]: del p["items"]["radio"]
        return min(90, base + 20)
    return base

def use_vest(p: dict, pen: int) -> tuple:
    if pen < 0 and p["items"].get("vest", 0) > 0:
        p["items"]["vest"] -= 1
        if not p["items"]["vest"]: del p["items"]["vest"]
        return 0, "\n🦺 *Бронежилет поглотил штраф!*"
    return pen, ""

def is_admin(msg: Message) -> bool:
    u = msg.from_user
    return (u.username or "").lower() == ADMIN_USERNAME.lower()

# ══════════════════════════════════════════
#  МАГАЗИН
# ══════════════════════════════════════════
SHOP_ITEMS = {
    "coffee":    {"name": "☕ Кофе бодрости",    "desc": "Снижает КД следующей команды на 30 мин",            "price": 80,  "emoji": "☕"},
    "badge":     {"name": "🏅 Нагрудный знак",   "desc": "Даёт +25 XP бонуса к следующей операции",          "price": 120, "emoji": "🏅"},
    "vest":      {"name": "🦺 Бронежилет",        "desc": "Защищает от штрафа монет при провале (1 раз)",     "price": 200, "emoji": "🦺"},
    "radio":     {"name": "📻 Рация спецсвязи",  "desc": "Повышает шанс успеха погони/задержания на 20%",    "price": 250, "emoji": "📻"},
    "informant": {"name": "🕵️ Информатор",       "desc": "Удваивает монеты со следующего рейда/операции",    "price": 350, "emoji": "🕵️"},
    "stars":     {"name": "⭐ Звёздный аванс",   "desc": "Немедленно даёт +150 XP",                          "price": 500, "emoji": "⭐"},
}

# ══════════════════════════════════════════
#  СЦЕНАРИИ
# ══════════════════════════════════════════
PATROL_EVENTS = [
    ("🔍 Заметил угнанный автомобиль — вызвал эвакуатор.", 18, 12, True),
    ("🤝 Помог найти потерявшегося ребёнка.", 15, 10, True),
    ("🚯 Задержал хулигана у школы.", 20, 14, True),
    ("☕ Спокойная смена. Кофе, квартал, тишина.", 8, 6, False),
    ("📢 Разогнал шумную компанию у подъезда.", 14, 9, True),
    ("🚘 Остановил пьяного водителя. Задержан.", 25, 18, True),
    ("👀 Засёк карманника в толпе!", 28, 20, True),
    ("🌧️ Дождливая смена. Помог аварийной машине.", 12, 8, False),
    ("🏪 Предотвратил ограбление магазина.", 22, 15, True),
    ("📦 Остановил фургон с краденым грузом.", 30, 22, True),
]

FINE_SCENARIOS = [
    ("🚦 Проехал на красный — штраф выписан!", 10, 22),
    ("📱 Телефон за рулём — протокол составлен.", 9, 20),
    ("🚗 Парковка в запрещённом месте.", 8, 25),
    ("🏎️ Превышение на 40 км/ч.", 12, 28),
    ("🍺 Пьяный водитель — задержан!", 15, 35),
    ("🔦 Езда без фар ночью.", 7, 18),
    ("🏍️ Мотоциклист без прав.", 14, 30),
    ("🚛 Грузовик в жилой зоне.", 11, 24),
]

PURSUIT_SUCCESS = [
    ("🚗 Прижат к забору во дворах!", 55, 38),
    ("🏃 Настиг у входа в метро!", 60, 42),
    ("🚁 Вертолёт отследил маршрут!", 70, 50),
    ("💨 Манёвр — преступник в кювете!", 50, 35),
    ("🛑 Шипы спустили шины!", 48, 32),
    ("🌉 На мосту перекрыли путь!", 65, 45),
    ("📡 Видеонаблюдение — перехвачен!", 58, 40),
    ("🤝 Коллеги взяли в кольцо!", 75, 55),
    ("🚔 Таран бампером — заглох!", 68, 48),
]

PURSUIT_FAIL = [
    "🚗💥 ДТП на перекрёстке — красный светофор.",
    "⛽ Закончилось топливо!",
    "🛞 Лопнуло колесо на 130 км/ч.",
    "📻 Рация сломалась.",
    "🌫️ Густой туман — снизил скорость.",
    "🚧 Объезд завёл в тупик.",
    "🌧️ Ливень — потерял из виду.",
    "📱 Навигатор завёл не туда.",
    "🏗️ Поднятый мост.",
    "🚑 Уступил дорогу скорой.",
]

CUFF_SUCCESS = [
    ("🏃 Ждал за углом — сам выбежал!", 75, 50),
    ("🎭 Маскировка сработала!", 70, 46),
    ("🐕‍🦺 Рекс взял след!", 85, 58),
    ("📷 Камеры — взяли у дома!", 68, 44),
    ("🤝 Агент передал точку!", 80, 55),
    ("🚔 Три машины — сдался сам!", 90, 62),
    ("🕵️ Информатор — взяли за столом!", 88, 60),
]

CUFF_FAIL = [
    ("😤 Опытный боец — вырвался.", -8),
    ("🚪 Чёрный ход — ушёл.", 0),
    ("🤦 Перепутал адрес!", -12),
    ("📵 Связь пропала.", 0),
    ("🌑 Затаился в темноте.", 0),
    ("🎭 Переоделся — потеряли.", 0),
]

RAID_EVENTS = [
    ("🏭 Подпольный склад — контрабанда изъята!", 140, 95, True),
    ("🎰 Накрыли казино! 15 задержанных.", 120, 85, True),
    ("💊 Ликвидирована точка сбыта.", 160, 110, True),
    ("🔫 Нелегальное оружие изъято.", 150, 100, True),
    ("🚫 Ложная информация — рейд провалился.", 15, 8, False),
    ("🏠 Явочная квартира — нашли компромат!", 160, 115, True),
    ("💻 Накрыли хакерскую группу.", 170, 120, True),
]

OPERATION_SUCCESS = [
    ("🕵️ Синдикат уничтожен! 30 задержанных.", 280, 200),
    ("💣 Предотвращён теракт без жертв.", 320, 240),
    ("🌍 Международная операция с Интерполом!", 300, 220),
    ("💰 Активы клана заморожены. Лидер задержан.", 290, 210),
    ("🔒 Сеть торговли людьми ликвидирована.", 350, 260),
]

OPERATION_FAIL = [
    ("🕵️ Крот предупредил преступников.", -30),
    ("📡 Глушилки заблокировали связь.", -10),
    ("🌧️ Буря помешала высадке.", 0),
]

# ══════════════════════════════════════════
#  РП КОМАНДЫ
# ══════════════════════════════════════════
RP_COMMANDS = {
    "надеть_наручники": [
        "🔒 *{a}* надел наручники на *{b}*. Сопротивление бесполезно!",
        "⛓️ *{a}* защёлкнул наручники на запястьях *{b}*. Не дёргайся!",
    ],
    "снять_наручники": [
        "🔓 *{a}* снял наручники с *{b}*. Ты свободен, но под наблюдением.",
    ],
    "обыск": [
        "🔍 *{a}* проводит досмотр *{b}*. Руки за голову!",
        "👀 *{a}* обыскивает *{b}*... найдено кое-что подозрительное.",
        "🕵️ *{a}* тщательно обыскал *{b}*. Карманы пусты — подозрительно.",
    ],
    "тайзер": [
        "⚡ *{a}* применил тайзер против *{b}*! Тот без сил рухнул на землю.",
        "🌩️ *{a}* оглушил *{b}* электрошокером. Лежать, не вставать!",
    ],
    "розыск": [
        "📋 *{a}* объявил *{b}* в федеральный розыск. Никуда не денешься!",
        "🚨 *{a}* внёс *{b}* в базу разыскиваемых. Добро пожаловать в систему.",
    ],
    "снять_розыск": [
        "✅ *{a}* снял *{b}* с розыска. Считай, повезло.",
    ],
    "арест": [
        "🚔 *{a}* арестовал *{b}*. Ты имеешь право хранить молчание!",
        "⚖️ *{a}* произвёл официальный арест *{b}*. Документы уже оформляются.",
    ],
    "отпустить": [
        "🕊️ *{a}* отпустил *{b}* под подписку о невыезде.",
        "🚪 *{a}* выпустил *{b}* из-под стражи. Пока свободен.",
    ],
    "допрос": [
        "🎤 *{a}* начал допрос *{b}*. Где был в пятницу вечером?",
        "🪑 *{a}* усадил *{b}* напротив и включил лампу. Говори!",
    ],
    "конвоировать": [
        "🚶 *{a}* конвоирует *{b}* в участок. Шаг в сторону — сочтём за побег.",
    ],
    "взять_под_стражу": [
        "🛡️ *{a}* взял *{b}* под стражу. Теперь никуда не денется.",
    ],
    "проверить_документы": [
        "🪪 *{a}* попросил *{b}* предъявить документы. Паспорт, пожалуйста.",
        "📄 *{a}* проверяет документы *{b}*... всё чисто. Пока.",
    ],
    "штраф": [
        "📝 *{a}* выписал *{b}* штраф на 5000 рублей. Квитанция на руки.",
    ],
    "предупреждение": [
        "⚠️ *{a}* сделал официальное предупреждение *{b}*. Следующий раз — арест.",
    ],
    "прикрыть": [
        "🛡️ *{a}* прикрыл *{b}* собственным телом. Напарник — это святое!",
    ],
    "надеть_наколенники": [
        "🦵 *{a}* уложил *{b}* на колени. На землю, быстро!",
    ],
    "конфисковать": [
        "🗄️ *{a}* конфисковал имущество *{b}*. Это теперь улика.",
    ],
    "пробить_по_базе": [
        "💻 *{a}* пробил *{b}* по базе данных. Результат... интересный.",
        "🖥️ *{a}* запустил проверку *{b}* по всем базам. Ждём результата.",
    ],
    "передать_дело": [
        "📁 *{a}* передал дело *{b}* в следственный комитет.",
    ],
    "засада": [
        "🌑 *{a}* устроил засаду на *{b}*. Тот даже не почувствовал.",
    ],
    "слежка": [
        "👁️ *{a}* ведёт скрытое наблюдение за *{b}*. Час, второй, третий...",
    ],
    "эскорт": [
        "🚗 *{a}* взял *{b}* на эскорт. С мигалками и почётом.",
    ],
    "высадить": [
        "🚪 *{a}* высадил *{b}* из машины прямо у участка.",
    ],
    "прижать_к_стене": [
        "🧱 *{a}* прижал *{b}* к стене. Не рыпайся!",
    ],
    "дать_показания": [
        "📜 *{a}* вынудил *{b}* дать показания. Запротоколировано.",
    ],
    "сопроводить": [
        "🤝 *{a}* вежливо сопроводил *{b}* до выхода из здания.",
    ],
    "медосмотр": [
        "🏥 *{a}* отправил *{b}* на принудительный медосмотр.",
    ],
    "принять_сторону": [
        "⚖️ *{a}* официально встал на сторону *{b}* в этом споре.",
    ],
}

# ══════════════════════════════════════════
#  FSM для рассылки и действий с юзером
# ══════════════════════════════════════════
class BroadcastForm(StatesGroup):
    waiting_for_text     = State()
    waiting_for_media    = State()
    waiting_for_btn_text = State()
    waiting_for_btn_url  = State()

class UserActionForm(StatesGroup):
    waiting_for_uid    = State()
    waiting_for_amount = State()
    current_action     = State()

# ══════════════════════════════════════════
#  БОТ
# ══════════════════════════════════════════
bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.MARKDOWN))
dp  = Dispatcher(storage=MemoryStorage())

# ══════════════════════════════════════════
#  GUARD
# ══════════════════════════════════════════
async def guard(msg: Message, p: dict, cmd: str) -> bool:
    if not check_rank_access(p, cmd):
        req = CMD_RANK_NAMES.get(cmd, "более высокого ранга")
        await msg.answer(f"🔒 *Команда недоступна!*\n\nТребуется: *{req}*\nПрогресс: /rank")
        return False
    cd = check_cooldown(p, cmd)
    if cd > 0:
        ready = (msk_now() + timedelta(seconds=cd)).strftime("%H:%M")
        await msg.answer(f"⏳ *Перезарядка*\nОсталось: *{fmt_time(cd)}*\nДоступно в: `{ready}` МСК")
        return False
    return True

# ══════════════════════════════════════════
#  /start
# ══════════════════════════════════════════
@dp.message(CommandStart())
async def cmd_start(msg: Message):
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="➕ Добавить бота в чат",
                             url=f"https://t.me/{BOT_USERNAME}?startgroup=true",
                             style="success")
    ]])
    await msg.answer(
        "🚔 *POLICE GAME BOT* 🚔\n\n"
        "Добро пожаловать в полицейскую академию!\n\n"
        "Ты — офицер полиции. Тебя ждут патрули, штрафы, погони, "
        "рейды и элитные операции. Карьерный путь — от Новобранца "
        "до Генерала полиции.\n\n"
        "🔒 Новые команды открываются с ростом звания\n\n"
        "📋 /help — все команды",
        reply_markup=kb
    )

# ══════════════════════════════════════════
#  /help
# ══════════════════════════════════════════
@dp.message(Command("help"))
async def cmd_help(msg: Message):
    await msg.answer(
        "📋 *КОМАНДЫ POLICE GAME BOT*\n\n"
        "━━━━━ 🟢 ВСЕМ ━━━━━\n"
        "/ticket — 📄 Штраф нарушителю | КД 30 мин\n"
        "/bribe — 💰 Рисковая взятка | КД 30 мин\n"
        "/patrol — 👮 Патруль | КД 1 час\n\n"
        "━━━━━ 🟡 СТ. СЕРЖАНТ (900 XP) ━━━━━\n"
        "/pursuit — 🚗 Погоня | КД 2 часа\n"
        "/arrest — 🔒 Задержание | КД 1.5 часа\n\n"
        "━━━━━ ⭐ КАПИТАН (3300 XP) ━━━━━\n"
        "/raid — 🏭 Рейд | КД 3 часа\n\n"
        "━━━━━ 💫 ПОДПОЛКОВНИК (6200 XP) ━━━━━\n"
        "/operation — 🕵️ Элитная операция | КД 4 часа\n\n"
        "━━━━━ 🏆 ГЕНЕРАЛ ПОЛИЦИИ (15000 XP) ━━━━━\n"
        "/radar — 📡 Камера контроля скорости\n\n"
        "━━━━━ 📊 ПРОФИЛЬ ━━━━━\n"
        "/pass — 🪪 Мой профиль\n"
        "/top — 🏆 Топ офицеров\n"
        "/rank — ⭐ Список рангов\n"
        "/shop — 🛒 Магазин\n"
        "/inventory — 🎒 Инвентарь\n"
        "/buy <предмет> — купить\n\n"
        "━━━━━ 🎭 РП КОМАНДЫ (в чате) ━━━━━\n"
        "Ответьте на сообщение и напишите *без* /:\n"
        "надеть\\_наручники, обыск, тайзер, розыск,\n"
        "арест, допрос, конвоировать, слежка и др.\n"
        "_Полный список: /rp\\_help_"
    )

# ══════════════════════════════════════════
#  /rp_help
# ══════════════════════════════════════════
@dp.message(Command("rp_help"))
async def cmd_rp_help(msg: Message):
    cmds = "\n".join(f"• {c}" for c in RP_COMMANDS)
    await msg.answer(
        f"🎭 *РП КОМАНДЫ*\n\n"
        f"Ответьте на сообщение участника и напишите команду *без* /:\n\n"
        f"{cmds}"
    )

# ══════════════════════════════════════════
#  РП ОБРАБОТЧИК
# ══════════════════════════════════════════
@dp.message(F.text.regexp(r"^(" + "|".join(RP_COMMANDS.keys()) + r")$", flags=2))
async def cmd_rp(msg: Message):
    cmd_raw = msg.text.strip().lower()
    templates = RP_COMMANDS.get(cmd_raw)
    if not templates:
        return

    a = mention_name(msg)

    if msg.reply_to_message:
        b = msg.reply_to_message.from_user.first_name
    else:
        await msg.answer("💬 _Ответьте на сообщение участника чтобы применить команду._")
        return

    text = random.choice(templates).format(a=a, b=b)
    await msg.answer(text)

# ══════════════════════════════════════════
#  /ticket (бывший /fine)
# ══════════════════════════════════════════
@dp.message(Command("ticket"))
async def cmd_ticket(msg: Message):
    data = load_data(); p = get_player(data, msg.from_user.id, msg.from_user.username or "")
    if not await guard(msg, p, "ticket"): return
    set_cooldown(p, "ticket")
    scenario, xp, coins = random.choice(FINE_SCENARIOS)
    bonus = use_badge(p); xp_b = p.get("xp", 0)
    add_xp_coins(p, xp + bonus, coins)
    text = (f"📄 *ШТРАФ*\n\n👮 {mention(msg)} в `{now_str()}` МСК\n\n"
            f"📖 {scenario}\n\n✅ *Протокол оформлен*\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"⚡ Опыт: +{xp}{f' +{bonus}🏅' if bonus else ''} XP\n💰 Монеты: +{coins}\n")
    text += rank_up_msg(xp_b, p["xp"]); save_data(data)
    await msg.answer(text)

# ══════════════════════════════════════════
#  /bribe
# ══════════════════════════════════════════
@dp.message(Command("bribe"))
async def cmd_bribe(msg: Message):
    data = load_data(); p = get_player(data, msg.from_user.id, msg.from_user.username or "")
    if not await guard(msg, p, "bribe"): return
    set_cooldown(p, "bribe"); roll = random.randint(1, 100)
    if roll <= 40:
        xp, coins = 15, random.randint(45, 90); add_xp_coins(p, xp, coins)
        text = (f"💰 *ПРОШЛО ЧИСТО!*\n\n🤫 {mention(msg)} принял «благодарность»...\n"
                f"━━━━━━━━━━━━━━━━━━\n⚡ Опыт: +{xp} XP\n💰 Монеты: +{coins}\n")
    elif roll <= 70:
        add_xp_coins(p, 5, 0)
        text = (f"🤷 *НИЧЕГО НЕ ВЫШЛО*\n\n😤 {mention(msg)} попытался, но задержанный не согласился.\n"
                f"━━━━━━━━━━━━━━━━━━\n⚡ Опыт: +5 XP\n")
    else:
        pen = -random.randint(25, 60); pen, shield = use_vest(p, pen)
        if pen < 0: p["coins"] = max(0, p.get("coins", 0) + pen)
        text = (f"🚨 *ПОПАЛСЯ!*\n\n😱 {mention(msg)} замечен!\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"{'💸 Штраф: ' + str(pen) + ' монет' if pen < 0 else '💸 Монеты: 0 (бронежилет)'}\n{shield}")
    save_data(data); await msg.answer(text)

# ══════════════════════════════════════════
#  /patrol
# ══════════════════════════════════════════
@dp.message(Command("patrol"))
async def cmd_patrol(msg: Message):
    data = load_data(); p = get_player(data, msg.from_user.id, msg.from_user.username or "")
    if not await guard(msg, p, "patrol"): return
    set_cooldown(p, "patrol"); scenario, xp, coins, ok = random.choice(PATROL_EVENTS)
    bonus = use_badge(p); xp_b = p.get("xp", 0); add_xp_coins(p, xp + bonus, coins)
    icon = "✅" if ok else "😴"
    text = (f"👮 *ПАТРУЛЬ*\n\n{mention(msg)} вышел в `{now_str()}` МСК\n\n"
            f"📖 {scenario}\n\n{icon} *Смена завершена*\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"⚡ Опыт: +{xp}{f' +{bonus}🏅' if bonus else ''} XP\n💰 Монеты: +{coins}\n")
    text += rank_up_msg(xp_b, p["xp"]); save_data(data); await msg.answer(text)

# ══════════════════════════════════════════
#  /pursuit
# ══════════════════════════════════════════
@dp.message(Command("pursuit"))
async def cmd_pursuit(msg: Message):
    data = load_data(); p = get_player(data, msg.from_user.id, msg.from_user.username or "")
    if not await guard(msg, p, "pursuit"): return
    start = now_str(); set_cooldown(p, "pursuit"); p["pursuits"] = p.get("pursuits", 0) + 1
    chance = use_radio(p, 55); ok = random.randint(1, 100) <= chance
    end = end_time_str(8, 55)
    if ok:
        scenario, xp, coins = random.choice(PURSUIT_SUCCESS)
        p["pursuits_success"] = p.get("pursuits_success", 0) + 1; p["catches"] = p.get("catches", 0) + 1
        bonus = use_badge(p); xp_b = p.get("xp", 0); add_xp_coins(p, xp + bonus, coins)
        text = (f"🚨 *ПОГОНЯ!*\n\n👮 {mention(msg)} выехал!\n\n"
                f"🕐 Выехал — `{start}` МСК\n✅ Поймал — `{end}` МСК\n\n"
                f"📖 {scenario}\n\n🎯 *ЗАДЕРЖАН!*\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"⚡ Опыт: +{xp}{f' +{bonus}🏅' if bonus else ''} XP\n💰 Монеты: +{coins}\n")
        text += rank_up_msg(xp_b, p["xp"])
    else:
        reason = random.choice(PURSUIT_FAIL); xp_b = p.get("xp", 0); add_xp_coins(p, 8, 0)
        text = (f"🚨 *ПОГОНЯ!*\n\n👮 {mention(msg)} выехал!\n\n"
                f"🕐 Выехал — `{start}` МСК\n❌ Потерял — `{end}` МСК\n\n"
                f"📖 {reason}\n\n😤 *УШЁЛ*\n"
                f"━━━━━━━━━━━━━━━━━━\n⚡ Опыт: +8 XP\n")
    save_data(data); await msg.answer(text)

# ══════════════════════════════════════════
#  /arrest (бывший /cuff)
# ══════════════════════════════════════════
@dp.message(Command("arrest"))
async def cmd_arrest(msg: Message):
    data = load_data(); p = get_player(data, msg.from_user.id, msg.from_user.username or "")
    if not await guard(msg, p, "arrest"): return
    set_cooldown(p, "arrest"); p["cuffs"] = p.get("cuffs", 0) + 1
    chance = use_radio(p, 60); ok = random.randint(1, 100) <= chance
    if ok:
        scenario, xp, coins = random.choice(CUFF_SUCCESS); p["catches"] = p.get("catches", 0) + 1
        bonus = use_badge(p); xp_b = p.get("xp", 0); add_xp_coins(p, xp + bonus, coins)
        text = (f"🔒 *ЗАДЕРЖАНИЕ!*\n\n👮 {mention(msg)} вышел в `{now_str()}` МСК\n\n"
                f"📖 {scenario}\n\n✅ *В НАРУЧНИКАХ!*\n"
                f"━━━━━━━━━━━━━━━━━━\n"
                f"⚡ Опыт: +{xp}{f' +{bonus}🏅' if bonus else ''} XP\n💰 Монеты: +{coins}\n")
        text += rank_up_msg(xp_b, p["xp"])
    else:
        scenario, pen = random.choice(CUFF_FAIL); pen, shield = use_vest(p, pen)
        xp_b = p.get("xp", 0); add_xp_coins(p, 10, 0)
        if pen < 0: p["coins"] = max(0, p.get("coins", 0) + pen)
        text = (f"🔒 *ЗАДЕРЖАНИЕ!*\n\n👮 {mention(msg)} вышел в `{now_str()}` МСК\n\n"
                f"📖 {scenario}\n\n❌ *УСКОЛЬЗНУЛ*\n"
                f"━━━━━━━━━━━━━━━━━━\n⚡ Опыт: +10 XP\n")
        if pen < 0: text += f"💸 Монеты: {pen}\n"
        text += shield
    save_data(data); await msg.answer(text)

# ══════════════════════════════════════════
#  /raid
# ══════════════════════════════════════════
@dp.message(Command("raid"))
async def cmd_raid(msg: Message):
    data = load_data(); p = get_player(data, msg.from_user.id, msg.from_user.username or "")
    if not await guard(msg, p, "raid"): return
    set_cooldown(p, "raid"); scenario, xp, coins, ok = random.choice(RAID_EVENTS)
    inf = ""
    if ok and p["items"].get("informant", 0) > 0:
        coins *= 2; p["items"]["informant"] -= 1
        if not p["items"]["informant"]: del p["items"]["informant"]
        inf = "\n🕵️ *Информатор удвоил монеты!*"
    bonus = use_badge(p) if ok else 0; xp_b = p.get("xp", 0); add_xp_coins(p, xp + bonus, coins)
    icon = "🎯" if ok else "😤"
    text = (f"🏭 *РЕЙД!*\n\n🚔 {mention(msg)} в `{now_str()}` МСК\n\n"
            f"📖 {scenario}\n\n{icon} *{'Успешно' if ok else 'Провалился'}*\n"
            f"━━━━━━━━━━━━━━━━━━\n"
            f"⚡ Опыт: +{xp}{f' +{bonus}🏅' if bonus else ''} XP\n💰 Монеты: +{coins}{inf}\n")
    text += rank_up_msg(xp_b, p["xp"]); save_data(data); await msg.answer(text)

# ══════════════════════════════════════════
#  /operation
# ══════════════════════════════════════════
@dp.message(Command("operation"))
async def cmd_operation(msg: Message):
    data = load_data(); p = get_player(data, msg.from_user.id, msg.from_user.username or "")
    if not await guard(msg, p, "operation"): return
    set_cooldown(p, "operation"); p["operations"] = p.get("operations", 0) + 1
    ok = random.randint(1, 100) <= 65
    if ok:
        scenario, xp, coins = random.choice(OPERATION_SUCCESS)
        inf = ""
        if p["items"].get("informant", 0) > 0:
            coins = int(coins * 1.5); p["items"]["informant"] -= 1
            if not p["items"]["informant"]: del p["items"]["informant"]
            inf = "\n🕵️ *Информатор +50% монет!*"
        xp_b = p.get("xp", 0); add_xp_coins(p, xp, coins); p["catches"] = p.get("catches", 0) + 5
        text = (f"🕵️ *ЭЛИТНАЯ ОПЕРАЦИЯ*\n\n🚔 {mention(msg)} в `{now_str()}` МСК\n\n"
                f"📖 {scenario}\n\n✅ *УСПЕХ!*\n"
                f"━━━━━━━━━━━━━━━━━━\n⚡ Опыт: +{xp} XP\n💰 Монеты: +{coins}{inf}\n")
        text += rank_up_msg(xp_b, p["xp"])
    else:
        scenario, pen = random.choice(OPERATION_FAIL); xp_b = p.get("xp", 0); add_xp_coins(p, 20, 0)
        if pen < 0: p["coins"] = max(0, p.get("coins", 0) + pen)
        text = (f"🕵️ *ЭЛИТНАЯ ОПЕРАЦИЯ*\n\n🚔 {mention(msg)} в `{now_str()}` МСК\n\n"
                f"📖 {scenario}\n\n❌ *ПРОВАЛ*\n"
                f"━━━━━━━━━━━━━━━━━━\n⚡ Опыт: +20 XP\n")
        if pen < 0: text += f"💸 Монеты: {pen}\n"
    save_data(data); await msg.answer(text)

# ══════════════════════════════════════════
#  /radar — Камера (Генерал полиции)
# ══════════════════════════════════════════
@dp.message(Command("radar"))
async def cmd_radar(msg: Message):
    data = load_data(); p = get_player(data, msg.from_user.id, msg.from_user.username or "")
    if not await guard(msg, p, "radar"): return
    count = p.get("radar_count", 0)
    if count == 0:
        # первая бесплатно
        p["has_radar"] = True; p["radar_count"] = 1
        p["last_radar_income"] = int(msk_now().timestamp())
        save_data(data)
        await msg.answer(
            "📡 *КАМЕРА УСТАНОВЛЕНА!*\n\n"
            "✅ Камера контроля скорости выставлена.\n"
            "💰 Каждые 24 часа вам будет начисляться *+15 монет* автоматически.\n\n"
            "💡 Вторую камеру можно установить за 1000 монет: `/radar`"
        )
    elif count == 1:
        if p.get("coins", 0) < 1000:
            await msg.answer(f"💸 *Вторая камера стоит 1000 монет.*\nУ вас: {p.get('coins',0)} 💰")
            return
        p["coins"] -= 1000; p["has_radar"] = True; p["radar_count"] = 2
        save_data(data)
        await msg.answer(
            "📡 *ВТОРАЯ КАМЕРА УСТАНОВЛЕНА!*\n\n"
            "✅ Теперь у вас 2 камеры.\n"
            "💰 Ежедневный доход: *+30 монет*\n\n"
            "💸 Потрачено: 1000 монет"
        )
    else:
        await msg.answer("📡 У вас уже максимальное количество камер (2).\n💰 Ежедневный доход: *+30 монет*")

# ══════════════════════════════════════════
#  /shop, /buy, /inventory
# ══════════════════════════════════════════
@dp.message(Command("shop"))
async def cmd_shop(msg: Message):
    text = "🛒 *МАГАЗИН ПОЛИЦЕЙСКОГО*\n\n"
    for key, item in SHOP_ITEMS.items():
        text += f"{item['emoji']} *{item['name']}*\n   💰 {item['price']} монет\n   📝 {item['desc']}\n   → `/buy {key}`\n\n"
    text += "💡 _Предметы одноразовые, применяются автоматически._"
    await msg.answer(text)

@dp.message(Command("buy"))
async def cmd_buy(msg: Message):
    data = load_data(); p = get_player(data, msg.from_user.id, msg.from_user.username or "")
    args = msg.text.split()
    if len(args) < 2:
        await msg.answer("❓ `/buy <предмет>` | Список: /shop"); return
    key = args[1].lower()
    if key not in SHOP_ITEMS:
        await msg.answer(f"❌ Предмет `{key}` не найден. /shop"); return
    item = SHOP_ITEMS[key]
    if key == "stars":
        if p.get("coins", 0) < item["price"]:
            await msg.answer(f"💸 Нужно {item['price']} 💰, у вас {p.get('coins',0)}"); return
        p["coins"] -= item["price"]; xp_b = p.get("xp", 0); p["xp"] = xp_b + 150
        save_data(data)
        await msg.answer(f"✅ *Звёздный аванс!*\n⚡ +150 XP немедленно!\n💰 Осталось: {p['coins']}{rank_up_msg(xp_b, p['xp'])}")
        return
    if key == "coffee":
        if p.get("coins", 0) < item["price"]:
            await msg.answer(f"💸 Нужно {item['price']} 💰"); return
        cmds = ["pursuit","arrest","raid","operation","patrol","ticket","bribe"]
        best = max(cmds, key=lambda c: check_cooldown(p, c))
        if check_cooldown(p, best) == 0:
            await msg.answer("☕ Все команды уже готовы!"); return
        p[f"last_{best}"] = p.get(f"last_{best}", 0) - 1800; p["coins"] -= item["price"]
        save_data(data)
        await msg.answer(f"☕ *Кофе!* КД `/{best}` снижен на 30 мин.\nОсталось: {fmt_time(check_cooldown(p, best))}"); return
    if p.get("coins", 0) < item["price"]:
        await msg.answer(f"💸 Нужно {item['price']} 💰, у вас {p.get('coins',0)}"); return
    p["coins"] -= item["price"]; p["items"][key] = p["items"].get(key, 0) + 1
    save_data(data)
    await msg.answer(f"✅ *{item['emoji']} {item['name']}*\n📝 {item['desc']}\n💰 Осталось: {p['coins']}")

@dp.message(Command("inventory"))
async def cmd_inventory(msg: Message):
    data = load_data(); p = get_player(data, msg.from_user.id, msg.from_user.username or "")
    items = {k: v for k, v in p.get("items", {}).items() if v > 0}
    if not items:
        await msg.answer("🎒 *Инвентарь пуст*\n\n/shop"); return
    text = "🎒 *МОЙ ИНВЕНТАРЬ*\n\n"
    for k, v in items.items():
        it = SHOP_ITEMS.get(k)
        if it: text += f"{it['emoji']} {it['name']} — x{v}\n"
    await msg.answer(text)

# ══════════════════════════════════════════
#  /pass (бывший /profile)
# ══════════════════════════════════════════
@dp.message(Command("pass"))
async def cmd_pass(msg: Message):
    data = load_data(); p = get_player(data, msg.from_user.id, msg.from_user.username or "")
    xp = p.get("xp", 0); coins = p.get("coins", 0)
    rank = get_rank(xp); nxt = next_rank(xp)
    if nxt:
        needed = nxt["min_xp"] - rank["min_xp"]; cur = xp - rank["min_xp"]
        pct = min(cur / needed, 1.0); filled = int(pct * 10)
        bar = f"{'█'*filled}{'░'*(10-filled)} {int(pct*100)}%"
        prog = f"⬆️ До *{nxt['name']}*: *{nxt['min_xp']-xp} XP*\n`{bar}`"
    else:
        prog = "🏆 *Максимальный ранг!*"
    radar_info = ""
    if p.get("radar_count", 0) > 0:
        radar_info = f"\n📡 Камер: {p['radar_count']} | Доход: +{p['radar_count']*15} монет/день"
    await msg.answer(
        f"🪪 *ЛИЧНОЕ ДЕЛО ОФИЦЕРА*\n\n"
        f"👤 {msg.from_user.first_name}\n"
        f"🎖️ {rank['name']}\n\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"⚡ Опыт: *{xp} XP*\n"
        f"💰 Монеты: *{coins}*{radar_info}\n\n"
        f"{prog}\n\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"📊 *СТАТИСТИКА*\n"
        f"🚗 Погонь: {p.get('pursuits',0)} (успех: {p.get('pursuits_success',0)})\n"
        f"🔒 Задержаний: {p.get('cuffs',0)}\n"
        f"🕵️ Операций: {p.get('operations',0)}\n"
        f"🎯 Поймано: {p.get('catches',0)}\n"
    )

# ══════════════════════════════════════════
#  /top
# ══════════════════════════════════════════
@dp.message(Command("top"))
async def cmd_top(msg: Message):
    data = load_data()
    if not data:
        await msg.answer("📊 Никто ещё не играл!"); return
    pl = sorted(data.items(), key=lambda x: x[1].get("xp", 0), reverse=True)
    medals = ["🥇","🥈","🥉"]
    text = "🏆 *ТОП ОФИЦЕРОВ*\n\n"
    for i, (uid, p) in enumerate(pl[:10]):
        m = medals[i] if i < 3 else f"{i+1}."
        name = p.get("username") or f"Офицер{uid[-4:]}"
        rank = get_rank(p.get("xp", 0))
        text += f"{m} @{name} — {rank['emoji']} {p.get('xp',0)} XP | 🎯 {p.get('catches',0)}\n"
    await msg.answer(text)

# ══════════════════════════════════════════
#  /rank
# ══════════════════════════════════════════
@dp.message(Command("rank"))
async def cmd_rank(msg: Message):
    data = load_data(); p = get_player(data, msg.from_user.id, msg.from_user.username or "")
    cur = get_rank(p.get("xp", 0))
    unlocks = {
        "🟡 Старший сержант": " 🔓 _погоня, задержание_",
        "⭐ Капитан":         " 🔓 _рейд_",
        "💫 Подполковник":    " 🔓 _элитные операции_",
        "🏆 Генерал полиции": " 🔓 _камера радара_",
    }
    text = "⭐ *СИСТЕМА РАНГОВ*\n\n"
    for r in RANKS:
        me = " ✅ *← ВЫ*" if r["name"] == cur["name"] else ""
        ul = unlocks.get(r["name"], "")
        text += f"{r['emoji']} {r['name']} — {r['min_xp']} XP{me}{ul}\n"
    await msg.answer(text)

# ══════════════════════════════════════════
#  ЕЖЕДНЕВНЫЙ РАДАР (фоновая задача)
# ══════════════════════════════════════════
async def radar_income_task():
    while True:
        await asyncio.sleep(3600)  # проверяем каждый час
        data = load_data()
        now_ts = int(msk_now().timestamp())
        changed = False
        for uid, p in data.items():
            if p.get("has_radar") and p.get("radar_count", 0) > 0:
                last = p.get("last_radar_income", 0)
                if now_ts - last >= 86400:  # 24 часа
                    income = p["radar_count"] * 15
                    p["coins"] = p.get("coins", 0) + income
                    p["last_radar_income"] = now_ts
                    changed = True
                    try:
                        await bot.send_message(
                            int(uid),
                            f"📡 *Доход с камеры!*\n\n"
                            f"💰 Начислено: +{income} монет\n"
                            f"_(камер: {p['radar_count']})_"
                        )
                    except Exception:
                        pass
        if changed:
            save_data(data)

# ══════════════════════════════════════════
#  АДМИН ПАНЕЛЬ
# ══════════════════════════════════════════
def admin_menu_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📨 Рассылка",         callback_data="admin_broadcast")],
        [InlineKeyboardButton(text="📊 Статистика",       callback_data="admin_stats")],
        [InlineKeyboardButton(text="👤 Действие с юзером",callback_data="admin_user")],
    ])

def admin_stats_text() -> str:
    data  = load_data()
    stats = load_stats()
    total = len(data)

    # последние 30 дней
    days_text = ""
    today = msk_now().date()
    for i in range(29, -1, -1):
        d = (today - timedelta(days=i)).strftime("%Y-%m-%d")
        count = stats.get(d, 0)
        if count > 0 or i < 7:
            label = (today - timedelta(days=i)).strftime("%d.%m")
            bar = "▓" * min(count, 20)
            days_text += f"`{label}` {bar} {count}\n"

    return (
        f"📊 *СТАТИСТИКА БОТА*\n\n"
        f"👥 Всего пользователей: *{total}*\n\n"
        f"📅 *Новые за 30 дней:*\n{days_text or 'Нет данных'}"
    )

@dp.message(Command("admin"))
async def cmd_admin(msg: Message):
    if not is_admin(msg):
        return  # молчим
    await msg.answer("🔐 *ПАНЕЛЬ АДМИНИСТРАТОРА*", reply_markup=admin_menu_kb())

@dp.callback_query(F.data == "admin_panel")
async def cb_admin_panel(cb: CallbackQuery, state: FSMContext):
    if not is_admin(cb.message) and (cb.from_user.username or "").lower() != ADMIN_USERNAME.lower():
        return await cb.answer()
    await state.clear()
    await cb.message.edit_text("🔐 *ПАНЕЛЬ АДМИНИСТРАТОРА*", reply_markup=admin_menu_kb())
    await cb.answer()

# ── Статистика ──────────────────────────
@dp.callback_query(F.data == "admin_stats")
async def cb_admin_stats(cb: CallbackQuery):
    if (cb.from_user.username or "").lower() != ADMIN_USERNAME.lower():
        return await cb.answer()
    text = admin_stats_text()
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="◁ Назад", callback_data="admin_panel")
    ]])
    await cb.message.edit_text(text, reply_markup=kb)
    await cb.answer()

# ── Действие с юзером ──────────────────
def user_action_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💰 Выдать монеты",    callback_data="ua_coins")],
        [InlineKeyboardButton(text="⚡ Выдать опыт",      callback_data="ua_xp")],
        [InlineKeyboardButton(text="🎁 Выдать предмет",   callback_data="ua_item")],
        [InlineKeyboardButton(text="◁ Назад",             callback_data="admin_panel")],
    ])

@dp.callback_query(F.data == "admin_user")
async def cb_admin_user(cb: CallbackQuery, state: FSMContext):
    if (cb.from_user.username or "").lower() != ADMIN_USERNAME.lower():
        return await cb.answer()
    await cb.message.edit_text("👤 *ДЕЙСТВИЕ С ЮЗЕРОМ*\nВыберите действие:", reply_markup=user_action_kb())
    await cb.answer()

@dp.callback_query(F.data.in_({"ua_coins", "ua_xp", "ua_item"}))
async def cb_ua_select(cb: CallbackQuery, state: FSMContext):
    if (cb.from_user.username or "").lower() != ADMIN_USERNAME.lower():
        return await cb.answer()
    action_map = {"ua_coins": "coins", "ua_xp": "xp", "ua_item": "item"}
    action = action_map[cb.data]
    await state.update_data(ua_action=action)
    await state.set_state(UserActionForm.waiting_for_uid)
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="◁ Отмена", callback_data="admin_panel")]])
    await cb.message.edit_text(f"👤 Введите *Telegram ID* пользователя:", reply_markup=kb)
    await cb.answer()

@dp.message(UserActionForm.waiting_for_uid)
async def ua_receive_uid(msg: Message, state: FSMContext):
    if (msg.from_user.username or "").lower() != ADMIN_USERNAME.lower(): return
    uid_str = msg.text.strip()
    if not uid_str.isdigit():
        await msg.answer("❌ ID должен быть числом. Введите снова:"); return
    await state.update_data(ua_uid=uid_str)
    data_s = await state.get_data()
    action = data_s.get("ua_action")

    if action == "item":
        items_list = "\n".join(f"`{k}` — {v['name']}" for k, v in SHOP_ITEMS.items())
        await state.set_state(UserActionForm.waiting_for_amount)
        await msg.answer(f"🎁 Введите *ключ предмета*:\n\n{items_list}")
    else:
        label = "монет" if action == "coins" else "XP"
        await state.set_state(UserActionForm.waiting_for_amount)
        await msg.answer(f"💡 Введите количество *{label}* для выдачи:")

@dp.message(UserActionForm.waiting_for_amount)
async def ua_receive_amount(msg: Message, state: FSMContext):
    if (msg.from_user.username or "").lower() != ADMIN_USERNAME.lower(): return
    data_s = await state.get_data()
    action = data_s.get("ua_action"); uid_str = data_s.get("ua_uid")
    value  = msg.text.strip()
    db     = load_data()
    p      = get_player(db, int(uid_str))

    if action == "coins":
        if not value.lstrip("-").isdigit():
            await msg.answer("❌ Введите число"); return
        p["coins"] = max(0, p.get("coins", 0) + int(value))
        result = f"💰 Выдано *{value}* монет юзеру `{uid_str}`"
    elif action == "xp":
        if not value.lstrip("-").isdigit():
            await msg.answer("❌ Введите число"); return
        xp_b = p.get("xp", 0); p["xp"] = max(0, xp_b + int(value))
        result = f"⚡ Выдано *{value}* XP юзеру `{uid_str}`{rank_up_msg(xp_b, p['xp'])}"
    elif action == "item":
        if value not in SHOP_ITEMS:
            await msg.answer(f"❌ Предмет `{value}` не найден"); return
        p["items"][value] = p["items"].get(value, 0) + 1
        it = SHOP_ITEMS[value]
        result = f"🎁 Выдан *{it['name']}* юзеру `{uid_str}`"
    else:
        result = "❓ Неизвестное действие"

    save_data(db); await state.clear()
    await msg.answer(f"✅ {result}", reply_markup=admin_menu_kb())

# ══════════════════════════════════════════
#  РАССЫЛКА (FSM)
# ══════════════════════════════════════════
def get_all_users(data: dict) -> list[int]:
    return [int(uid) for uid in data.keys()]

def build_reply_markup(btn_text, btn_url):
    if not btn_text or not btn_url: return None
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text=btn_text, url=btn_url)
    ]])

@dp.callback_query(F.data == "admin_broadcast")
async def cb_admin_broadcast(cb: CallbackQuery, state: FSMContext):
    if (cb.from_user.username or "").lower() != ADMIN_USERNAME.lower():
        return await cb.answer()
    await state.set_state(BroadcastForm.waiting_for_text)
    await cb.message.edit_text(
        "📨 *Шаг 1: Отправьте текст сообщения для рассылки:*",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="◁ Отмена", callback_data="admin_panel")
        ]])
    )
    await cb.answer()

@dp.message(BroadcastForm.waiting_for_text)
async def bc_receive_text(msg: Message, state: FSMContext):
    if (msg.from_user.username or "").lower() != ADMIN_USERNAME.lower(): return
    await state.update_data(bc_text=msg.text or msg.caption, bc_entities=msg.entities or msg.caption_entities)
    await state.set_state(BroadcastForm.waiting_for_media)
    await msg.answer(
        "📨 *Шаг 2: Отправьте медиа (фото/видео/GIF) или пропустите:*",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="⏩ Пропустить", callback_data="bc_skip_media")],
            [InlineKeyboardButton(text="◁ Отмена",       callback_data="admin_panel")],
        ])
    )

@dp.message(BroadcastForm.waiting_for_media, F.photo | F.video | F.animation)
async def bc_receive_media(msg: Message, state: FSMContext):
    if (msg.from_user.username or "").lower() != ADMIN_USERNAME.lower(): return
    if msg.photo:       await state.update_data(bc_photo=msg.photo[-1].file_id, bc_video=None, bc_animation=None)
    elif msg.video:     await state.update_data(bc_photo=None, bc_video=msg.video.file_id, bc_animation=None)
    elif msg.animation: await state.update_data(bc_photo=None, bc_video=None, bc_animation=msg.animation.file_id)
    await _bc_ask_button(msg.chat.id, state)

@dp.callback_query(F.data == "bc_skip_media", BroadcastForm.waiting_for_media)
async def bc_skip_media(cb: CallbackQuery, state: FSMContext):
    await state.update_data(bc_photo=None, bc_video=None, bc_animation=None)
    await _bc_ask_button(cb.message.chat.id, state); await cb.answer()

async def _bc_ask_button(chat_id: int, state: FSMContext):
    await state.set_state(BroadcastForm.waiting_for_btn_text)
    await bot.send_message(chat_id, "📨 *Шаг 3: Добавить кнопку со ссылкой?*",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="➕ Добавить кнопку", callback_data="bc_add_button")],
            [InlineKeyboardButton(text="⏩ Без кнопки",      callback_data="bc_skip_button")],
            [InlineKeyboardButton(text="◁ Отмена",           callback_data="admin_panel")],
        ])
    )

@dp.callback_query(F.data == "bc_add_button", BroadcastForm.waiting_for_btn_text)
async def bc_add_button(cb: CallbackQuery, state: FSMContext):
    await bot.send_message(cb.message.chat.id, "📨 *Шаг 4: Введите текст кнопки:*",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="◁ Отмена", callback_data="admin_panel")]]))
    await cb.answer()

@dp.message(BroadcastForm.waiting_for_btn_text)
async def bc_receive_btn_text(msg: Message, state: FSMContext):
    if (msg.from_user.username or "").lower() != ADMIN_USERNAME.lower(): return
    await state.update_data(bc_btn_text=msg.text)
    await state.set_state(BroadcastForm.waiting_for_btn_url)
    await msg.answer("📨 *Шаг 5: Введите URL для кнопки:*",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="◁ Отмена", callback_data="admin_panel")]]))

@dp.message(BroadcastForm.waiting_for_btn_url)
async def bc_receive_btn_url(msg: Message, state: FSMContext):
    if (msg.from_user.username or "").lower() != ADMIN_USERNAME.lower(): return
    await state.update_data(bc_btn_url=msg.text)
    await _bc_show_preview(msg.chat.id, state)

@dp.callback_query(F.data == "bc_skip_button", BroadcastForm.waiting_for_btn_text)
async def bc_skip_button(cb: CallbackQuery, state: FSMContext):
    await state.update_data(bc_btn_text=None, bc_btn_url=None)
    await _bc_show_preview(cb.message.chat.id, state); await cb.answer()

async def _bc_show_preview(chat_id: int, state: FSMContext):
    d = await state.get_data()
    bc_text = d.get("bc_text"); bc_photo = d.get("bc_photo")
    bc_video = d.get("bc_video"); bc_animation = d.get("bc_animation")
    btn_text = d.get("bc_btn_text"); btn_url = d.get("bc_btn_url")
    rm = build_reply_markup(btn_text, btn_url)
    await bot.send_message(chat_id, "👁 *Предпросмотр рассылки:*")
    if bc_photo:          await bot.send_photo(chat_id, bc_photo, caption=bc_text, reply_markup=rm, parse_mode=None)
    elif bc_video:        await bot.send_video(chat_id, bc_video, caption=bc_text, reply_markup=rm, parse_mode=None)
    elif bc_animation:    await bot.send_animation(chat_id, bc_animation, caption=bc_text, reply_markup=rm, parse_mode=None)
    else:                 await bot.send_message(chat_id, bc_text, reply_markup=rm, parse_mode=None)
    await bot.send_message(chat_id, "❓ *Отправить рассылку?*",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="✔️ Отправить", callback_data="bc_confirm"),
            InlineKeyboardButton(text="✖️ Отмена",    callback_data="bc_cancel_preview"),
        ]])
    )

@dp.callback_query(F.data == "bc_confirm")
async def bc_confirm(cb: CallbackQuery, state: FSMContext):
    if (cb.from_user.username or "").lower() != ADMIN_USERNAME.lower():
        return await cb.answer()
    d = await state.get_data(); await state.clear()
    bc_text = d.get("bc_text"); bc_photo = d.get("bc_photo")
    bc_video = d.get("bc_video"); bc_animation = d.get("bc_animation")
    btn_text = d.get("bc_btn_text"); btn_url = d.get("bc_btn_url")
    rm = build_reply_markup(btn_text, btn_url)
    db = load_data(); users = get_all_users(db)
    success = failed = 0
    status = await cb.message.answer("📤 *Рассылка начата...*")
    for uid in users:
        try:
            if bc_photo:       await bot.send_photo(uid, bc_photo, caption=bc_text, reply_markup=rm, parse_mode=None)
            elif bc_video:     await bot.send_video(uid, bc_video, caption=bc_text, reply_markup=rm, parse_mode=None)
            elif bc_animation: await bot.send_animation(uid, bc_animation, caption=bc_text, reply_markup=rm, parse_mode=None)
            else:              await bot.send_message(uid, bc_text, reply_markup=rm, parse_mode=None)
            success += 1
        except Exception: failed += 1
        await asyncio.sleep(0.05)
    await status.edit_text(
        f"✅ *Рассылка завершена*\n\n✅ Успешно: *{success}*\n❌ Ошибок: *{failed}*",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="◁ Назад", callback_data="admin_panel")]])
    )
    await cb.answer()

@dp.callback_query(F.data == "bc_cancel_preview")
async def bc_cancel_preview(cb: CallbackQuery, state: FSMContext):
    await state.clear()
    await cb.message.answer("❌ Рассылка отменена.", reply_markup=admin_menu_kb()); await cb.answer()

# ══════════════════════════════════════════
#  ЗАПУСК
# ══════════════════════════════════════════
async def main():
    print("🚔 Police Game Bot запущен!")
    asyncio.create_task(radar_income_task())
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
