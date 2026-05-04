"""
🚔 POLICE GAME BOT
Переменные окружения:
  BOT_TOKEN    — токен от @BotFather
  BOT_USERNAME — username бота без @
"""

import asyncio, random, json, os, sys, re
from datetime import datetime, timedelta, timezone
from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.enums import ParseMode
from aiogram.client.default import DefaultBotProperties

# ══════════════════════════════════════════
#  КОНФИГ
# ══════════════════════════════════════════
BOT_TOKEN      = os.environ.get("BOT_TOKEN", "")
BOT_USERNAME   = os.environ.get("BOT_USERNAME", "")
ADMIN_USERNAME = "tntks"

if not BOT_TOKEN:
    print("❌ BOT_TOKEN не задан!"); sys.exit(1)

DATA_FILE  = "players.json"
STATS_FILE = "daily_stats.json"
MSK        = timezone(timedelta(hours=3))

def msk_now():
    return datetime.now(MSK)

def now_str():
    return msk_now().strftime("%H:%M")

# ══════════════════════════════════════════
#  РАНГИ
# ══════════════════════════════════════════
RANKS = [
    {"name": "Новобранец",        "min_xp": 0,      "emoji": "🪪",  "idx": 0},
    {"name": "Рядовой",           "min_xp": 200,    "emoji": "👮",  "idx": 1},
    {"name": "Сержант",           "min_xp": 500,    "emoji": "🔵",  "idx": 2},
    {"name": "Старший сержант",   "min_xp": 900,    "emoji": "🟡",  "idx": 3},
    {"name": "Лейтенант",         "min_xp": 1500,   "emoji": "🔴",  "idx": 4},
    {"name": "Старший лейтенант", "min_xp": 2300,   "emoji": "🟠",  "idx": 5},
    {"name": "Капитан",           "min_xp": 3300,   "emoji": "⭐",  "idx": 6},
    {"name": "Майор",             "min_xp": 4600,   "emoji": "🌟",  "idx": 7},
    {"name": "Подполковник",      "min_xp": 6200,   "emoji": "💫",  "idx": 8},
    {"name": "Полковник",         "min_xp": 8200,   "emoji": "🏅",  "idx": 9},
    {"name": "Генерал-майор",     "min_xp": 11000,  "emoji": "🎖",  "idx": 10},
    {"name": "Генерал полиции",   "min_xp": 15000,  "emoji": "🏆",  "idx": 11},
]

CMD_MIN_RANK = {
    "ticket": 0, "bribe": 0, "patrol": 0,
    "arrest": 3, "pursuit": 3,
    "raid": 6,
    "operation": 8,
    "radar": 11,
}
CMD_RANK_LABEL = {
    "arrest":    "🟡 Старший сержант (900 XP)",
    "pursuit":   "🟡 Старший сержант (900 XP)",
    "raid":      "⭐ Капитан (3300 XP)",
    "operation": "💫 Подполковник (6200 XP)",
    "radar":     "🏆 Генерал полиции (15000 XP)",
}

def get_rank(xp):
    r = RANKS[0]
    for rank in RANKS:
        if xp >= rank["min_xp"]: r = rank
    return r

def next_rank(xp):
    for rank in RANKS:
        if xp < rank["min_xp"]: return rank
    return None

def rank_line(r): return r["emoji"] + " " + r["name"]

def has_rank(player, cmd):
    return get_rank(player.get("xp", 0))["idx"] >= CMD_MIN_RANK.get(cmd, 0)

def rank_up_note(xp_before, xp_after):
    rb = get_rank(xp_before); ra = get_rank(xp_after)
    if rb["name"] != ra["name"]:
        return "\n\nНОВОЕ ЗВАНИЕ: " + ra["emoji"] + " " + ra["name"] + "!"
    return ""

# ══════════════════════════════════════════
#  КУЛДАУНЫ (секунды)
# ══════════════════════════════════════════
COOLDOWNS = {
    "ticket": 1800, "bribe": 1800, "patrol": 3600,
    "pursuit": 7200, "arrest": 5400,
    "raid": 10800, "operation": 14400,
}

def cd_left(player, action):
    now  = int(msk_now().timestamp())
    last = player.get("last_" + action, 0)
    return max(0, COOLDOWNS.get(action, 60) - (now - last))

def set_cd(player, action):
    player["last_" + action] = int(msk_now().timestamp())

def fmt_cd(s):
    h, r = divmod(s, 3600); m, s = divmod(r, 60)
    if h: return f"{h} ч {m} мин" if m else f"{h} ч"
    if m: return f"{m} мин {s} сек" if s else f"{m} мин"
    return f"{s} сек"

def end_time(mn, mx):
    return (msk_now() + timedelta(minutes=random.randint(mn, mx))).strftime("%H:%M")

# ══════════════════════════════════════════
#  БАЗА ДАННЫХ
# ══════════════════════════════════════════
def load_db():
    if os.path.exists(DATA_FILE):
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_db(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

def load_stats():
    if os.path.exists(STATS_FILE):
        with open(STATS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_stats(s):
    with open(STATS_FILE, "w", encoding="utf-8") as f:
        json.dump(s, f, ensure_ascii=False, indent=2)

def get_player(data, uid, username=""):
    key = str(uid)
    if key not in data:
        joined = msk_now().strftime("%Y-%m-%d %H:%M:%S")
        data[key] = {
            "username": username, "xp": 0, "coins": 0,
            "catches": 0, "pursuits": 0, "pursuits_ok": 0, "cuffs": 0, "ops": 0,
            "last_ticket": 0, "last_bribe": 0, "last_patrol": 0,
            "last_pursuit": 0, "last_arrest": 0,
            "last_raid": 0, "last_operation": 0, "last_radar_income": 0,
            "radar_count": 0, "items": {}, "joined": joined,
        }
        stats = load_stats()
        day = msk_now().strftime("%Y-%m-%d")
        stats[day] = stats.get(day, 0) + 1
        save_stats(stats)
    p = data[key]
    for field, default in [("items", {}), ("radar_count", 0), ("last_radar_income", 0),
                            ("ops", 0), ("last_operation", 0), ("joined", "—")]:
        if field not in p:
            p[field] = default
    if username: p["username"] = username
    return p

def give(player, xp, coins):
    player["xp"]    = player.get("xp", 0)    + xp
    player["coins"] = player.get("coins", 0) + coins

def mention(msg):
    u = msg.from_user
    return "@" + u.username if u.username else u.first_name

def is_admin(msg):
    return (msg.from_user.username or "").lower() == ADMIN_USERNAME.lower()

def cb_is_admin(cb):
    return (cb.from_user.username or "").lower() == ADMIN_USERNAME.lower()

# ══════════════════════════════════════════
#  ПРЕДМЕТЫ МАГАЗИНА
# ══════════════════════════════════════════
SHOP = {
    "coffee":    {"name": "Кофе бодрости",   "desc": "Снижает КД следующей команды на 30 мин",        "price": 80,  "emoji": "☕"},
    "badge":     {"name": "Нагрудный знак",  "desc": "Даёт +25 XP бонуса к следующей операции",       "price": 120, "emoji": "🏅"},
    "vest":      {"name": "Бронежилет",      "desc": "Защищает от штрафа монет при провале (1 раз)",  "price": 200, "emoji": "🦺"},
    "radio":     {"name": "Рация спецсвязи", "desc": "Повышает шанс успеха погони/задержания +20%",   "price": 250, "emoji": "📻"},
    "informant": {"name": "Информатор",      "desc": "Удваивает монеты со следующего рейда/операции", "price": 350, "emoji": "🕵️"},
    "stars":     {"name": "Звёздный аванс",  "desc": "Немедленно даёт +150 XP",                       "price": 500, "emoji": "⭐"},
}

def use_badge(p):
    if p["items"].get("badge", 0) > 0:
        p["items"]["badge"] -= 1
        if not p["items"]["badge"]: del p["items"]["badge"]
        return 25
    return 0

def use_radio(p, base):
    if p["items"].get("radio", 0) > 0:
        p["items"]["radio"] -= 1
        if not p["items"]["radio"]: del p["items"]["radio"]
        return min(90, base + 20)
    return base

def use_vest(p, pen):
    if pen < 0 and p["items"].get("vest", 0) > 0:
        p["items"]["vest"] -= 1
        if not p["items"]["vest"]: del p["items"]["vest"]
        return 0, "\nБронежилет поглотил штраф!"
    return pen, ""

# ══════════════════════════════════════════
#  СЦЕНАРИИ
# ══════════════════════════════════════════
PATROL_EVT = [
    ("Заметил угнанный автомобиль — вызвал эвакуатор.", 18, 12),
    ("Помог найти потерявшегося ребёнка. Репутация растёт!", 15, 10),
    ("Задержал хулигана с баллончиком краски у школы.", 20, 14),
    ("Спокойная смена. Кофе, квартал, тишина.", 8, 6),
    ("Разогнал шумную компанию у подъезда.", 14, 9),
    ("Остановил пьяного водителя. Задержан.", 25, 18),
    ("Засёк карманника в толпе и задержал!", 28, 20),
    ("Остановил подозрительный фургон — краденый груз.", 30, 22),
    ("Предотвратил ограбление магазина.", 22, 15),
    ("Поймал сбежавшую опасную собаку.", 10, 7),
]

TICKET_EVT = [
    ("Проехал на красный — штраф выписан!", 10, 22),
    ("Телефон за рулём — протокол составлен.", 9, 20),
    ("Парковка в запрещённом месте — эвакуатор.", 8, 25),
    ("Превышение на 40 км/ч — штраф.", 12, 28),
    ("Пьяный водитель — протокол и задержание!", 15, 35),
    ("Езда без фар ночью — штраф.", 7, 18),
    ("Мотоциклист без прав — задержан!", 14, 30),
    ("Грузовик в жилой зоне не в то время.", 11, 24),
]

PURSUIT_OK = [
    ("Прижат к забору во дворах!", 55, 38),
    ("Настиг у входа в метро!", 60, 42),
    ("Вертолёт отследил маршрут — остановлен!", 70, 50),
    ("Крутой манёвр — преступник в кювете!", 50, 35),
    ("Шипы спустили шины — никуда не ушёл!", 48, 32),
    ("На мосту перекрыли путь — деваться некуда!", 65, 45),
    ("Видеонаблюдение помогло перехватить!", 58, 40),
    ("Коллеги взяли в кольцо!", 75, 55),
    ("Таран бампером — автомобиль заглох!", 68, 48),
]

PURSUIT_FAIL = [
    "ДТП на перекрёстке — красный светофор.",
    "Закончилось топливо!",
    "Лопнуло колесо на 130 км/ч.",
    "Рация сломалась.",
    "Густой туман — снизил скорость, преступник ушёл.",
    "Объезд завёл в тупик.",
    "Ливень — потерял из виду.",
    "Навигатор завёл не туда.",
    "Поднятый мост.",
    "Уступил дорогу скорой помощи.",
]

ARREST_OK = [
    ("Ждал за углом — сам выбежал!", 75, 50),
    ("Маскировка сработала — сам подошёл!", 70, 46),
    ("Служебная собака Рекс взял след!", 85, 58),
    ("Камеры помогли — взяли у дома!", 68, 44),
    ("Агент под прикрытием передал точку!", 80, 55),
    ("Три машины перекрыли все выходы. Сдался.", 90, 62),
    ("Информатор сдал точку — взяли за столом!", 88, 60),
]

ARREST_FAIL = [
    ("Опытный боец — вырвался.", -8),
    ("Чёрный ход — ушёл через дворы.", 0),
    ("Перепутал адрес!", -12),
    ("Связь пропала в нужный момент.", 0),
    ("Затаился в темноте склада.", 0),
    ("Переоделся — потеряли на рынке.", 0),
]

RAID_EVT = [
    ("Подпольный склад — контрабанда изъята!", 140, 95, True),
    ("Накрыли казино! 15 задержанных.", 120, 85, True),
    ("Ликвидирована точка сбыта.", 160, 110, True),
    ("Нелегальное оружие изъято.", 150, 100, True),
    ("Ложная информация — рейд провалился.", 15, 8, False),
    ("Явочная квартира — нашли компромат!", 160, 115, True),
    ("Накрыли хакерскую группу.", 170, 120, True),
    ("Цех поддельных документов ликвидирован.", 145, 98, True),
]

OPERATION_OK = [
    ("Синдикат уничтожен! 30 задержанных.", 280, 200),
    ("Предотвращён теракт без жертв.", 320, 240),
    ("Международная операция с Интерполом!", 300, 220),
    ("Активы клана заморожены. Лидер задержан.", 290, 210),
    ("Сеть торговли людьми ликвидирована.", 350, 260),
]

OPERATION_FAIL = [
    ("Крот предупредил преступников.", -30),
    ("Глушилки заблокировали связь.", -10),
    ("Буря помешала высадке.", 0),
]

# ══════════════════════════════════════════
#  РП КОМАНДЫ
# ══════════════════════════════════════════
RP = {
    "надеть наручники":    ["🔒 {a} надел наручники на {b}. Сопротивление бесполезно!", "⛓ {a} защёлкнул наручники на {b}. Не дёргайся!"],
    "снять наручники":     ["🔓 {a} снял наручники с {b}. Свободен, но под наблюдением."],
    "обыск":               ["🔍 {a} проводит досмотр {b}. Руки за голову!", "👁 {a} обыскал {b}. Карманы пусты — подозрительно."],
    "тайзер":              ["⚡ {a} применил тайзер на {b}! Тот рухнул без сил.", "🌩 {a} оглушил {b} электрошокером. Лежать!"],
    "розыск":              ["📋 {a} объявил {b} в розыск. Никуда не денешься!", "🚨 {a} внёс {b} в базу разыскиваемых."],
    "снять розыск":        ["✅ {a} снял {b} с розыска. Считай, повезло."],
    "арест":               ["🚔 {a} арестовал {b}. Имеешь право хранить молчание!", "⚖ {a} произвёл официальный арест {b}."],
    "отпустить":           ["🕊 {a} отпустил {b} под подписку о невыезде.", "🚪 {a} выпустил {b} из-под стражи."],
    "допрос":              ["🎤 {a} начал допрос {b}. Где был в пятницу вечером?", "💡 {a} усадил {b} напротив и включил лампу. Говори!"],
    "конвоировать":        ["🚶 {a} конвоирует {b} в участок. Шаг в сторону — побег."],
    "взять под стражу":    ["🛡 {a} взял {b} под стражу."],
    "проверить документы": ["🪪 {a} проверяет документы {b}... всё чисто. Пока.", "📄 {a} попросил {b} предъявить документы."],
    "штраф":               ["📝 {a} выписал {b} штраф на 5000 рублей."],
    "предупреждение":      ["⚠ {a} сделал официальное предупреждение {b}. Следующий раз — арест."],
    "прикрыть":            ["🛡 {a} прикрыл {b} собственным телом. Напарник — это святое!"],
    "надеть наколенники":  ["🦵 {a} уложил {b} на колени. На землю, быстро!"],
    "конфисковать":        ["🗄 {a} конфисковал имущество {b}. Это теперь улика."],
    "пробить по базе":     ["💻 {a} пробил {b} по базе данных. Результат... интересный.", "🖥 {a} запустил проверку {b} по всем базам."],
    "передать дело":       ["📁 {a} передал дело {b} в следственный комитет."],
    "засада":              ["🌑 {a} устроил засаду на {b}. Тот и не почувствовал."],
    "слежка":              ["👁 {a} ведёт скрытое наблюдение за {b}. Час, второй..."],
    "высадить":            ["🚪 {a} высадил {b} из машины прямо у участка."],
    "прижать к стене":     ["🧱 {a} прижал {b} к стене. Не рыпайся!"],
    "дать показания":      ["📜 {a} вынудил {b} дать показания. Запротоколировано."],
    "сопроводить":         ["🤝 {a} вежливо сопроводил {b} до выхода."],
    "медосмотр":           ["🏥 {a} отправил {b} на принудительный медосмотр."],
    "принять сторону":     ["⚖ {a} официально встал на сторону {b} в споре."],
}

# ══════════════════════════════════════════
#  FSM
# ══════════════════════════════════════════
class BC(StatesGroup):
    text  = State()
    media = State()
    btn_t = State()
    btn_u = State()

class UA(StatesGroup):
    uid    = State()
    amount = State()

# ══════════════════════════════════════════
#  BOT + DISPATCHER
# ══════════════════════════════════════════
bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.MARKDOWN))
dp  = Dispatcher(storage=MemoryStorage())

# ══════════════════════════════════════════
#  GUARD
# ══════════════════════════════════════════
async def guard(msg, player, cmd):
    if not has_rank(player, cmd):
        req = CMD_RANK_LABEL.get(cmd, "более высокого ранга")
        await msg.answer("Команда недоступна!\n\nТребуется: " + req)
        return False
    cd = cd_left(player, cmd)
    if cd > 0:
        ready = (msk_now() + timedelta(seconds=cd)).strftime("%H:%M")
        await msg.answer("Перезарядка: " + fmt_cd(cd) + "\nДоступно в: " + ready + " МСК")
        return False
    return True

# ══════════════════════════════════════════
#  /start
# ══════════════════════════════════════════
@dp.message(CommandStart())
async def cmd_start(msg: Message):
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(
            text="➕ Добавить бота в чат",
            url="https://t.me/" + BOT_USERNAME + "?startgroup=true"
        )
    ]])
    await msg.answer(
        "🚔 POLICE GAME BOT 🚔\n\n"
        "Добро пожаловать в полицейскую академию!\n\n"
        "Ты — офицер полиции. Тебя ждут патрули, штрафы, погони, "
        "рейды и элитные операции. Карьерный путь — от Новобранца "
        "до Генерала полиции.\n\n"
        "🔒 Новые команды открываются с ростом звания\n\n"
        "📋 /help — все команды",
        parse_mode=None,
        reply_markup=kb
    )

# ══════════════════════════════════════════
#  /help
# ══════════════════════════════════════════
@dp.message(Command("help"))
async def cmd_help(msg: Message):
    await msg.answer(
        "КОМАНДЫ POLICE GAME BOT\n\n"
        "ВСЕМ:\n"
        "/ticket — Штраф нарушителю, КД 30 мин\n"
        "/bribe  — Рисковая взятка, КД 30 мин\n"
        "/patrol — Патруль, КД 1 час\n\n"
        "СТАРШИЙ СЕРЖАНТ (900 XP):\n"
        "/pursuit — Погоня, КД 2 часа\n"
        "/arrest  — Задержание, КД 1.5 часа\n\n"
        "КАПИТАН (3300 XP):\n"
        "/raid — Рейд, КД 3 часа\n\n"
        "ПОДПОЛКОВНИК (6200 XP):\n"
        "/operation — Элитная операция, КД 4 часа\n\n"
        "ГЕНЕРАЛ ПОЛИЦИИ (15000 XP):\n"
        "/radar — Камера контроля скорости\n\n"
        "ПРОФИЛЬ:\n"
        "/pass      — Мой профиль\n"
        "/top       — Топ офицеров\n"
        "/rank      — Список рангов\n"
        "/shop      — Магазин\n"
        "/inventory — Инвентарь\n"
        "/buy предмет — купить\n\n"
        "РП КОМАНДЫ:\n"
        "Ответьте на сообщение и напишите без /\n"
        "Полный список: /rphelp",
        parse_mode=None
    )

# ══════════════════════════════════════════
#  /rphelp
# ══════════════════════════════════════════
@dp.message(Command("rphelp", "rp_help"))
async def cmd_rphelp(msg: Message):
    text = "РП КОМАНДЫ\n\n" + "\n".join("• " + k for k in RP.keys())
    await msg.answer(text, parse_mode=None)

# ══════════════════════════════════════════
#  /rank
# ══════════════════════════════════════════
@dp.message(Command("rank"))
async def cmd_rank(msg: Message):
    data = load_db()
    p = get_player(data, msg.from_user.id, msg.from_user.username or "")
    cur = get_rank(p.get("xp", 0))
    unlocks = {
        "Старший сержант":   " | погоня, задержание",
        "Капитан":           " | рейд",
        "Подполковник":      " | элитные операции",
        "Генерал полиции":   " | камера радара",
    }
    lines = ["СИСТЕМА РАНГОВ\n"]
    for r in RANKS:
        me = " << ВЫ" if r["name"] == cur["name"] else ""
        ul = unlocks.get(r["name"], "")
        lines.append(r["emoji"] + " " + r["name"] + " — " + str(r["min_xp"]) + " XP" + me + ul)
    await msg.answer("\n".join(lines), parse_mode=None)

# ══════════════════════════════════════════
#  /ticket
# ══════════════════════════════════════════
@dp.message(Command("ticket"))
async def cmd_ticket(msg: Message):
    data = load_db()
    p = get_player(data, msg.from_user.id, msg.from_user.username or "")
    if not await guard(msg, p, "ticket"): return
    set_cd(p, "ticket")
    scenario, xp, coins = random.choice(TICKET_EVT)
    bonus = use_badge(p); xp_b = p.get("xp", 0)
    give(p, xp + bonus, coins)
    text = (
        "📄 ШТРАФ\n\n"
        + mention(msg) + " в " + now_str() + " МСК\n\n"
        + scenario + "\n\n"
        + "Протокол оформлен\n"
        + "━━━━━━━━━━━━━━━\n"
        + "Опыт: +" + str(xp) + (" +" + str(bonus) + " (знак)" if bonus else "") + " XP\n"
        + "Монеты: +" + str(coins)
        + rank_up_note(xp_b, p["xp"])
    )
    save_db(data)
    await msg.answer(text, parse_mode=None)

# ══════════════════════════════════════════
#  /bribe
# ══════════════════════════════════════════
@dp.message(Command("bribe"))
async def cmd_bribe(msg: Message):
    data = load_db()
    p = get_player(data, msg.from_user.id, msg.from_user.username or "")
    if not await guard(msg, p, "bribe"): return
    set_cd(p, "bribe")
    roll = random.randint(1, 100)
    if roll <= 40:
        xp, coins = 15, random.randint(45, 90)
        give(p, xp, coins)
        text = "💰 ПРОШЛО ЧИСТО!\n\n" + mention(msg) + " принял «благодарность»...\n━━━━━━━━━━━━━━━\nОпыт: +" + str(xp) + " XP\nМонеты: +" + str(coins)
    elif roll <= 70:
        give(p, 5, 0)
        text = "🤷 НИЧЕГО НЕ ВЫШЛО\n\nЗадержанный оказался принципиальным!\n━━━━━━━━━━━━━━━\nОпыт: +5 XP"
    else:
        pen = -random.randint(25, 60)
        pen, shield = use_vest(p, pen)
        if pen < 0: p["coins"] = max(0, p.get("coins", 0) + pen)
        text = "🚨 ПОПАЛСЯ!\n\nСлужба безопасности всё видела...\n━━━━━━━━━━━━━━━\n" + ("Штраф: " + str(pen) + " монет" if pen < 0 else "Монеты: 0 (бронежилет спас)") + shield
    save_db(data)
    await msg.answer(text, parse_mode=None)

# ══════════════════════════════════════════
#  /patrol
# ══════════════════════════════════════════
@dp.message(Command("patrol"))
async def cmd_patrol(msg: Message):
    data = load_db()
    p = get_player(data, msg.from_user.id, msg.from_user.username or "")
    if not await guard(msg, p, "patrol"): return
    set_cd(p, "patrol")
    scenario, xp, coins = random.choice(PATROL_EVT)
    bonus = use_badge(p); xp_b = p.get("xp", 0)
    give(p, xp + bonus, coins)
    text = (
        "👮 ПАТРУЛЬ\n\n"
        + mention(msg) + " вышел в " + now_str() + " МСК\n\n"
        + scenario + "\n\n"
        + "Смена завершена\n"
        + "━━━━━━━━━━━━━━━\n"
        + "Опыт: +" + str(xp) + (" +" + str(bonus) + " (знак)" if bonus else "") + " XP\n"
        + "Монеты: +" + str(coins)
        + rank_up_note(xp_b, p["xp"])
    )
    save_db(data)
    await msg.answer(text, parse_mode=None)

# ══════════════════════════════════════════
#  /pursuit
# ══════════════════════════════════════════
@dp.message(Command("pursuit"))
async def cmd_pursuit(msg: Message):
    data = load_db()
    p = get_player(data, msg.from_user.id, msg.from_user.username or "")
    if not await guard(msg, p, "pursuit"): return
    start = now_str()
    set_cd(p, "pursuit")
    p["pursuits"] = p.get("pursuits", 0) + 1
    chance = use_radio(p, 55)
    ok = random.randint(1, 100) <= chance
    finish = end_time(8, 55)
    if ok:
        scenario, xp, coins = random.choice(PURSUIT_OK)
        p["pursuits_ok"] = p.get("pursuits_ok", 0) + 1
        p["catches"]     = p.get("catches", 0) + 1
        bonus = use_badge(p); xp_b = p.get("xp", 0)
        give(p, xp + bonus, coins)
        text = (
            "🚨 ПОГОНЯ!\n\n"
            + mention(msg) + " выехал на вызов!\n\n"
            + "Выехал — " + start + " МСК\n"
            + "Поймал — " + finish + " МСК\n\n"
            + scenario + "\n\n"
            + "ПРЕСТУПНИК ЗАДЕРЖАН!\n"
            + "━━━━━━━━━━━━━━━\n"
            + "Опыт: +" + str(xp) + (" +" + str(bonus) + " (знак)" if bonus else "") + " XP\n"
            + "Монеты: +" + str(coins)
            + rank_up_note(xp_b, p["xp"])
        )
    else:
        reason = random.choice(PURSUIT_FAIL)
        xp_b = p.get("xp", 0)
        give(p, 8, 0)
        text = (
            "🚨 ПОГОНЯ!\n\n"
            + mention(msg) + " выехал на вызов!\n\n"
            + "Выехал — " + start + " МСК\n"
            + "Потерял — " + finish + " МСК\n\n"
            + reason + "\n\n"
            + "ПРЕСТУПНИК УШЁЛ\n"
            + "━━━━━━━━━━━━━━━\n"
            + "Опыт: +8 XP (за попытку)"
        )
    save_db(data)
    await msg.answer(text, parse_mode=None)

# ══════════════════════════════════════════
#  /arrest
# ══════════════════════════════════════════
@dp.message(Command("arrest"))
async def cmd_arrest(msg: Message):
    data = load_db()
    p = get_player(data, msg.from_user.id, msg.from_user.username or "")
    if not await guard(msg, p, "arrest"): return
    set_cd(p, "arrest")
    p["cuffs"] = p.get("cuffs", 0) + 1
    chance = use_radio(p, 60)
    ok = random.randint(1, 100) <= chance
    if ok:
        scenario, xp, coins = random.choice(ARREST_OK)
        p["catches"] = p.get("catches", 0) + 1
        bonus = use_badge(p); xp_b = p.get("xp", 0)
        give(p, xp + bonus, coins)
        text = (
            "🔒 ЗАДЕРЖАНИЕ!\n\n"
            + mention(msg) + " вышел в " + now_str() + " МСК\n\n"
            + scenario + "\n\n"
            + "ПРЕСТУПНИК В НАРУЧНИКАХ!\n"
            + "━━━━━━━━━━━━━━━\n"
            + "Опыт: +" + str(xp) + (" +" + str(bonus) + " (знак)" if bonus else "") + " XP\n"
            + "Монеты: +" + str(coins)
            + rank_up_note(xp_b, p["xp"])
        )
    else:
        scenario, pen = random.choice(ARREST_FAIL)
        pen, shield = use_vest(p, pen)
        xp_b = p.get("xp", 0)
        give(p, 10, 0)
        if pen < 0: p["coins"] = max(0, p.get("coins", 0) + pen)
        text = (
            "🔒 ЗАДЕРЖАНИЕ!\n\n"
            + mention(msg) + " вышел в " + now_str() + " МСК\n\n"
            + scenario + "\n\n"
            + "ПРЕСТУПНИК УСКОЛЬЗНУЛ\n"
            + "━━━━━━━━━━━━━━━\n"
            + "Опыт: +10 XP"
            + ("\nМонеты: " + str(pen) if pen < 0 else "")
            + shield
        )
    save_db(data)
    await msg.answer(text, parse_mode=None)

# ══════════════════════════════════════════
#  /raid
# ══════════════════════════════════════════
@dp.message(Command("raid"))
async def cmd_raid(msg: Message):
    data = load_db()
    p = get_player(data, msg.from_user.id, msg.from_user.username or "")
    if not await guard(msg, p, "raid"): return
    set_cd(p, "raid")
    scenario, xp, coins, ok = random.choice(RAID_EVT)
    inf = ""
    if ok and p["items"].get("informant", 0) > 0:
        coins *= 2
        p["items"]["informant"] -= 1
        if not p["items"]["informant"]: del p["items"]["informant"]
        inf = "\nИнформатор удвоил монеты!"
    bonus = use_badge(p) if ok else 0
    xp_b = p.get("xp", 0)
    give(p, xp + bonus, coins)
    text = (
        "🏭 РЕЙД!\n\n"
        + mention(msg) + " в " + now_str() + " МСК\n\n"
        + scenario + "\n\n"
        + ("УСПЕШНО" if ok else "ПРОВАЛ") + "\n"
        + "━━━━━━━━━━━━━━━\n"
        + "Опыт: +" + str(xp) + (" +" + str(bonus) + " (знак)" if bonus else "") + " XP\n"
        + "Монеты: +" + str(coins) + inf
        + rank_up_note(xp_b, p["xp"])
    )
    save_db(data)
    await msg.answer(text, parse_mode=None)

# ══════════════════════════════════════════
#  /operation
# ══════════════════════════════════════════
@dp.message(Command("operation"))
async def cmd_operation(msg: Message):
    data = load_db()
    p = get_player(data, msg.from_user.id, msg.from_user.username or "")
    if not await guard(msg, p, "operation"): return
    set_cd(p, "operation")
    p["ops"] = p.get("ops", 0) + 1
    ok = random.randint(1, 100) <= 65
    if ok:
        scenario, xp, coins = random.choice(OPERATION_OK)
        inf = ""
        if p["items"].get("informant", 0) > 0:
            coins = int(coins * 1.5)
            p["items"]["informant"] -= 1
            if not p["items"]["informant"]: del p["items"]["informant"]
            inf = "\nИнформатор +50% монет!"
        xp_b = p.get("xp", 0)
        give(p, xp, coins)
        p["catches"] = p.get("catches", 0) + 5
        text = (
            "🕵️ ЭЛИТНАЯ ОПЕРАЦИЯ\n\n"
            + mention(msg) + " в " + now_str() + " МСК\n\n"
            + scenario + "\n\n"
            + "ОПЕРАЦИЯ УСПЕШНА!\n"
            + "━━━━━━━━━━━━━━━\n"
            + "Опыт: +" + str(xp) + " XP\n"
            + "Монеты: +" + str(coins) + inf
            + rank_up_note(xp_b, p["xp"])
        )
    else:
        scenario, pen = random.choice(OPERATION_FAIL)
        xp_b = p.get("xp", 0)
        give(p, 20, 0)
        if pen < 0: p["coins"] = max(0, p.get("coins", 0) + pen)
        text = (
            "🕵️ ЭЛИТНАЯ ОПЕРАЦИЯ\n\n"
            + mention(msg) + " в " + now_str() + " МСК\n\n"
            + scenario + "\n\n"
            + "ОПЕРАЦИЯ ПРОВАЛЕНА\n"
            + "━━━━━━━━━━━━━━━\n"
            + "Опыт: +20 XP"
            + ("\nМонеты: " + str(pen) if pen < 0 else "")
        )
    save_db(data)
    await msg.answer(text, parse_mode=None)

# ══════════════════════════════════════════
#  /radar
# ══════════════════════════════════════════
@dp.message(Command("radar"))
async def cmd_radar(msg: Message):
    data = load_db()
    p = get_player(data, msg.from_user.id, msg.from_user.username or "")
    if not await guard(msg, p, "radar"): return
    count = p.get("radar_count", 0)
    if count == 0:
        p["radar_count"] = 1
        p["last_radar_income"] = int(msk_now().timestamp())
        save_db(data)
        await msg.answer("📡 КАМЕРА УСТАНОВЛЕНА!\n\nКамера контроля скорости выставлена.\nКаждые 24 часа: +15 монет автоматически.\n\nВторую камеру можно поставить за 1000 монет.", parse_mode=None)
    elif count == 1:
        if p.get("coins", 0) < 1000:
            await msg.answer("Вторая камера стоит 1000 монет.\nУ вас: " + str(p.get("coins", 0)), parse_mode=None)
            return
        p["coins"] -= 1000
        p["radar_count"] = 2
        save_db(data)
        await msg.answer("📡 ВТОРАЯ КАМЕРА УСТАНОВЛЕНА!\n\nТеперь у вас 2 камеры.\nЕжедневный доход: +30 монет\n\nПотрачено: 1000 монет", parse_mode=None)
    else:
        await msg.answer("📡 У вас максимум камер (2).\nЕжедневный доход: +30 монет", parse_mode=None)

# ══════════════════════════════════════════
#  /shop
# ══════════════════════════════════════════
@dp.message(Command("shop"))
async def cmd_shop(msg: Message):
    lines = ["🛒 МАГАЗИН ПОЛИЦЕЙСКОГО\n"]
    for key, item in SHOP.items():
        lines.append(
            item["emoji"] + " " + item["name"] + "\n"
            "   💰 " + str(item["price"]) + " монет\n"
            "   " + item["desc"] + "\n"
            "   /buy " + key + "\n"
        )
    lines.append("Предметы одноразовые, применяются автоматически.")
    await msg.answer("\n".join(lines), parse_mode=None)

# ══════════════════════════════════════════
#  /buy
# ══════════════════════════════════════════
@dp.message(Command("buy"))
async def cmd_buy(msg: Message):
    data = load_db()
    p = get_player(data, msg.from_user.id, msg.from_user.username or "")
    args = msg.text.split()
    if len(args) < 2:
        await msg.answer("Укажи предмет: /buy предмет\nСписок: /shop", parse_mode=None)
        return
    key = args[1].lower()
    if key not in SHOP:
        await msg.answer("Предмет " + key + " не найден. /shop", parse_mode=None)
        return
    item = SHOP[key]
    if key == "stars":
        if p.get("coins", 0) < item["price"]:
            await msg.answer("Нужно " + str(item["price"]) + " монет, у вас " + str(p.get("coins", 0)), parse_mode=None)
            return
        p["coins"] -= item["price"]
        xp_b = p.get("xp", 0)
        give(p, 150, 0)
        save_db(data)
        await msg.answer("Куплено: " + item["emoji"] + " " + item["name"] + "\n+150 XP немедленно!\nОсталось монет: " + str(p["coins"]) + rank_up_note(xp_b, p["xp"]), parse_mode=None)
        return
    if key == "coffee":
        if p.get("coins", 0) < item["price"]:
            await msg.answer("Нужно " + str(item["price"]) + " монет", parse_mode=None)
            return
        cmds = ["pursuit","arrest","raid","operation","patrol","ticket","bribe"]
        best = max(cmds, key=lambda c: cd_left(p, c))
        if cd_left(p, best) == 0:
            await msg.answer("Все команды уже готовы — кофе не нужен!", parse_mode=None)
            return
        p["last_" + best] = p.get("last_" + best, 0) - 1800
        p["coins"] -= item["price"]
        save_db(data)
        await msg.answer("Куплено: ☕ " + item["name"] + "\nКД /" + best + " снижен на 30 мин.\nОсталось: " + fmt_cd(cd_left(p, best)), parse_mode=None)
        return
    if p.get("coins", 0) < item["price"]:
        await msg.answer("Нужно " + str(item["price"]) + " монет, у вас " + str(p.get("coins", 0)), parse_mode=None)
        return
    p["coins"] -= item["price"]
    p["items"][key] = p["items"].get(key, 0) + 1
    save_db(data)
    await msg.answer("Куплено: " + item["emoji"] + " " + item["name"] + "\n" + item["desc"] + "\nОсталось монет: " + str(p["coins"]), parse_mode=None)

# ══════════════════════════════════════════
#  /inventory
# ══════════════════════════════════════════
@dp.message(Command("inventory"))
async def cmd_inventory(msg: Message):
    data = load_db()
    p = get_player(data, msg.from_user.id, msg.from_user.username or "")
    items = {k: v for k, v in p.get("items", {}).items() if v > 0}
    if not items:
        await msg.answer("🎒 Инвентарь пуст\n\n/shop", parse_mode=None)
        return
    lines = ["🎒 МОЙ ИНВЕНТАРЬ\n"]
    for k, v in items.items():
        it = SHOP.get(k)
        if it: lines.append(it["emoji"] + " " + it["name"] + " — x" + str(v))
    lines.append("\nПредметы применяются автоматически.")
    await msg.answer("\n".join(lines), parse_mode=None)

# ══════════════════════════════════════════
#  /pass
# ══════════════════════════════════════════
@dp.message(Command("pass"))
async def cmd_pass(msg: Message):
    data = load_db()
    p = get_player(data, msg.from_user.id, msg.from_user.username or "")
    xp = p.get("xp", 0); coins = p.get("coins", 0)
    rank = get_rank(xp); nxt = next_rank(xp)
    if nxt:
        needed = nxt["min_xp"] - rank["min_xp"]
        cur_xp = xp - rank["min_xp"]
        pct    = min(cur_xp / needed, 1.0)
        filled = int(pct * 10)
        bar    = "█" * filled + "░" * (10 - filled) + " " + str(int(pct * 100)) + "%"
        prog   = "До " + nxt["emoji"] + " " + nxt["name"] + ": " + str(nxt["min_xp"] - xp) + " XP\n" + bar
    else:
        prog = "Максимальный ранг достигнут!"
    radar = ""
    if p.get("radar_count", 0) > 0:
        radar = "\nКамер: " + str(p["radar_count"]) + " | Доход: +" + str(p["radar_count"] * 15) + " монет/день"
    await msg.answer(
        "ЛИЧНОЕ ДЕЛО ОФИЦЕРА\n\n"
        "Имя: " + msg.from_user.first_name + "\n"
        "Звание: " + rank["emoji"] + " " + rank["name"] + "\n\n"
        "━━━━━━━━━━━━━━━\n"
        "Опыт: " + str(xp) + " XP\n"
        "Монеты: " + str(coins) + radar + "\n\n"
        + prog + "\n\n"
        "━━━━━━━━━━━━━━━\n"
        "СТАТИСТИКА\n"
        "Погонь: " + str(p.get("pursuits", 0)) + " (успех: " + str(p.get("pursuits_ok", 0)) + ")\n"
        "Задержаний: " + str(p.get("cuffs", 0)) + "\n"
        "Операций: " + str(p.get("ops", 0)) + "\n"
        "Поймано: " + str(p.get("catches", 0)),
        parse_mode=None
    )

# ══════════════════════════════════════════
#  /top
# ══════════════════════════════════════════
@dp.message(Command("top"))
async def cmd_top(msg: Message):
    data = load_db()
    if not data:
        await msg.answer("Никто ещё не играл!", parse_mode=None)
        return
    pl = sorted(data.items(), key=lambda x: x[1].get("xp", 0), reverse=True)
    medals = ["🥇", "🥈", "🥉"]
    lines = ["🏆 ТОП ОФИЦЕРОВ\n"]
    for i, (uid, pl_data) in enumerate(pl[:10]):
        m    = medals[i] if i < 3 else str(i + 1) + "."
        name = pl_data.get("username") or "Офицер" + uid[-4:]
        rank = get_rank(pl_data.get("xp", 0))
        lines.append(m + " @" + name + " — " + rank["emoji"] + " " + rank["name"] + " | " + str(pl_data.get("xp", 0)) + " XP | поймано: " + str(pl_data.get("catches", 0)))
    await msg.answer("\n".join(lines), parse_mode=None)

# ══════════════════════════════════════════
#  РП ОБРАБОТЧИК
# ══════════════════════════════════════════
@dp.message(F.text.func(lambda t: t is not None and t.strip().lower() in RP))
async def cmd_rp(msg: Message):
    key = msg.text.strip().lower()
    templates = RP.get(key)
    if not templates: return
    a = msg.from_user.first_name
    if not msg.reply_to_message:
        await msg.answer("Ответьте на сообщение участника.", parse_mode=None)
        return
    b = msg.reply_to_message.from_user.first_name
    await msg.answer(random.choice(templates).format(a=a, b=b), parse_mode=None)

# ══════════════════════════════════════════
#  РАДАР — фоновая задача
# ══════════════════════════════════════════
async def radar_task():
    while True:
        await asyncio.sleep(3600)
        data = load_db(); now_ts = int(msk_now().timestamp()); changed = False
        for uid, p in data.items():
            if p.get("radar_count", 0) > 0:
                if now_ts - p.get("last_radar_income", 0) >= 86400:
                    income = p["radar_count"] * 15
                    p["coins"] = p.get("coins", 0) + income
                    p["last_radar_income"] = now_ts
                    changed = True
                    try:
                        await bot.send_message(int(uid), "📡 Доход с камеры!\n\n+" + str(income) + " монет (камер: " + str(p["radar_count"]) + ")", parse_mode=None)
                    except Exception: pass
        if changed: save_db(data)

# ══════════════════════════════════════════
#  АДМИН ПАНЕЛЬ
# ══════════════════════════════════════════
def admin_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📨 Рассылка",          callback_data="adm_bc")],
        [InlineKeyboardButton(text="📊 Статистика",        callback_data="adm_stats")],
        [InlineKeyboardButton(text="👤 Действие с юзером", callback_data="adm_user")],
        [InlineKeyboardButton(text="👥 Все пользователи",  callback_data="adm_users_xp_desc")],
    ])

def users_filter_kb(cur):
    opts = [
        ("🆕 Сначала новые",  "adm_users_new"),
        ("🕰 Сначала старые", "adm_users_old"),
        ("⬆️ Больше опыта",  "adm_users_xp_desc"),
        ("⬇️ Меньше опыта",  "adm_users_xp_asc"),
        ("💰 Больше монет",  "adm_users_coins_desc"),
        ("💸 Меньше монет",  "adm_users_coins_asc"),
    ]
    rows = [[InlineKeyboardButton(text=label + (" ✅" if cb == cur else ""), callback_data=cb)] for label, cb in opts]
    rows.append([InlineKeyboardButton(text="◁ Назад", callback_data="adm_panel")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def build_users_page(sort_key):
    data = load_db()
    players = list(data.items())
    if sort_key == "adm_users_new":
        players.sort(key=lambda x: x[1].get("joined", "0000"), reverse=True)
    elif sort_key == "adm_users_old":
        players.sort(key=lambda x: x[1].get("joined", "9999"))
    elif sort_key == "adm_users_xp_desc":
        players.sort(key=lambda x: x[1].get("xp", 0), reverse=True)
    elif sort_key == "adm_users_xp_asc":
        players.sort(key=lambda x: x[1].get("xp", 0))
    elif sort_key == "adm_users_coins_desc":
        players.sort(key=lambda x: x[1].get("coins", 0), reverse=True)
    elif sort_key == "adm_users_coins_asc":
        players.sort(key=lambda x: x[1].get("coins", 0))
    if not players: return "Нет пользователей"
    lines = ["ПОЛЬЗОВАТЕЛИ: " + str(len(players)) + "\n"]
    for i, (uid, p) in enumerate(players[:40], 1):
        name   = p.get("username", "")
        uname  = "@" + name if name else "нет username"
        joined = p.get("joined", "—")
        xp     = p.get("xp", 0)
        coins  = p.get("coins", 0)
        rank   = get_rank(xp)
        lines.append(
            str(i) + ". " + rank["emoji"] + " " + uname + "\n"
            "   ID: " + uid + "\n"
            "   Зашёл: " + joined + "\n"
            "   Опыт: " + str(xp) + " XP | Монеты: " + str(coins) + "\n"
        )
    if len(players) > 40:
        lines.append("...и ещё " + str(len(players) - 40) + " пользователей")
    return "\n".join(lines)

def stats_text():
    data  = load_db(); stats = load_stats()
    total = len(data)
    today = msk_now().date()
    lines = ["СТАТИСТИКА БОТА\n", "Всего пользователей: " + str(total) + "\n", "Новые за 30 дней:\n"]
    for i in range(29, -1, -1):
        d     = (today - timedelta(days=i)).strftime("%Y-%m-%d")
        count = stats.get(d, 0)
        if count > 0 or i < 7:
            label = (today - timedelta(days=i)).strftime("%d.%m")
            lines.append(label + " — " + str(count) + " чел.")
    return "\n".join(lines)

@dp.message(Command("admin"))
async def cmd_admin(msg: Message):
    if not is_admin(msg): return
    await msg.answer("ПАНЕЛЬ АДМИНИСТРАТОРА", reply_markup=admin_kb(), parse_mode=None)

@dp.callback_query(F.data == "adm_panel")
async def cb_adm_panel(cb: CallbackQuery, state: FSMContext):
    if not cb_is_admin(cb): return await cb.answer()
    await state.clear()
    await cb.message.edit_text("ПАНЕЛЬ АДМИНИСТРАТОРА", reply_markup=admin_kb())
    await cb.answer()

@dp.callback_query(F.data == "adm_stats")
async def cb_adm_stats(cb: CallbackQuery):
    if not cb_is_admin(cb): return await cb.answer()
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="◁ Назад", callback_data="adm_panel")]])
    await cb.message.edit_text(stats_text(), reply_markup=kb, parse_mode=None)
    await cb.answer()

USERS_KEYS = {"adm_users_new","adm_users_old","adm_users_xp_desc","adm_users_xp_asc","adm_users_coins_desc","adm_users_coins_asc"}

@dp.callback_query(F.data.in_(USERS_KEYS))
async def cb_adm_users(cb: CallbackQuery):
    if not cb_is_admin(cb): return await cb.answer()
    text = build_users_page(cb.data)
    try:
        await cb.message.edit_text(text, reply_markup=users_filter_kb(cb.data), parse_mode=None)
    except Exception:
        await cb.message.answer(text, reply_markup=users_filter_kb(cb.data), parse_mode=None)
    await cb.answer()

# ── Действие с юзером ──
def user_action_kb():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💰 Выдать монеты",  callback_data="ua_coins")],
        [InlineKeyboardButton(text="⚡ Выдать опыт",    callback_data="ua_xp")],
        [InlineKeyboardButton(text="🎁 Выдать предмет", callback_data="ua_item")],
        [InlineKeyboardButton(text="◁ Назад",           callback_data="adm_panel")],
    ])

@dp.callback_query(F.data == "adm_user")
async def cb_adm_user(cb: CallbackQuery):
    if not cb_is_admin(cb): return await cb.answer()
    await cb.message.edit_text("Действие с юзером:", reply_markup=user_action_kb(), parse_mode=None)
    await cb.answer()

@dp.callback_query(F.data.in_({"ua_coins","ua_xp","ua_item"}))
async def cb_ua_select(cb: CallbackQuery, state: FSMContext):
    if not cb_is_admin(cb): return await cb.answer()
    await state.update_data(ua_action=cb.data)
    await state.set_state(UA.uid)
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="◁ Отмена", callback_data="adm_panel")]])
    await cb.message.edit_text("Введите Telegram ID пользователя:", reply_markup=kb, parse_mode=None)
    await cb.answer()

@dp.message(UA.uid)
async def ua_uid(msg: Message, state: FSMContext):
    if not is_admin(msg): return
    if not msg.text.strip().isdigit():
        await msg.answer("ID должен быть числом. Введите снова:", parse_mode=None); return
    await state.update_data(ua_uid=msg.text.strip())
    d = await state.get_data()
    action = d.get("ua_action")
    if action == "ua_item":
        items_list = "\n".join(k + " — " + v["name"] for k, v in SHOP.items())
        await msg.answer("Введите ключ предмета:\n\n" + items_list, parse_mode=None)
    else:
        label = "монет" if action == "ua_coins" else "XP"
        await msg.answer("Введите количество " + label + ":", parse_mode=None)
    await state.set_state(UA.amount)

@dp.message(UA.amount)
async def ua_amount(msg: Message, state: FSMContext):
    if not is_admin(msg): return
    d = await state.get_data()
    action = d.get("ua_action"); uid_str = d.get("ua_uid")
    value  = msg.text.strip()
    db     = load_db()
    p      = get_player(db, int(uid_str))
    if action == "ua_coins":
        if not value.lstrip("-").isdigit():
            await msg.answer("Введите число", parse_mode=None); return
        p["coins"] = max(0, p.get("coins", 0) + int(value))
        result = "Выдано " + value + " монет юзеру " + uid_str
    elif action == "ua_xp":
        if not value.lstrip("-").isdigit():
            await msg.answer("Введите число", parse_mode=None); return
        xp_b = p.get("xp", 0); p["xp"] = max(0, xp_b + int(value))
        result = "Выдано " + value + " XP юзеру " + uid_str + rank_up_note(xp_b, p["xp"])
    elif action == "ua_item":
        if value not in SHOP:
            await msg.answer("Предмет " + value + " не найден", parse_mode=None); return
        p["items"][value] = p["items"].get(value, 0) + 1
        result = "Выдан " + SHOP[value]["name"] + " юзеру " + uid_str
    else:
        result = "Неизвестное действие"
    save_db(db); await state.clear()
    await msg.answer("✅ " + result, reply_markup=admin_kb(), parse_mode=None)

# ── Рассылка ──
@dp.callback_query(F.data == "adm_bc")
async def cb_adm_bc(cb: CallbackQuery, state: FSMContext):
    if not cb_is_admin(cb): return await cb.answer()
    await state.set_state(BC.text)
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="◁ Отмена", callback_data="adm_panel")]])
    await cb.message.edit_text("Шаг 1: Отправьте текст рассылки:", reply_markup=kb, parse_mode=None)
    await cb.answer()

@dp.message(BC.text)
async def bc_text(msg: Message, state: FSMContext):
    if not is_admin(msg): return
    await state.update_data(bc_text=msg.text or msg.caption)
    await state.set_state(BC.media)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⏩ Пропустить", callback_data="bc_skip_media")],
        [InlineKeyboardButton(text="◁ Отмена",      callback_data="adm_panel")],
    ])
    await msg.answer("Шаг 2: Отправьте медиа или пропустите:", reply_markup=kb, parse_mode=None)

@dp.message(BC.media, F.photo | F.video | F.animation)
async def bc_media(msg: Message, state: FSMContext):
    if not is_admin(msg): return
    if msg.photo:          await state.update_data(bc_photo=msg.photo[-1].file_id, bc_video=None, bc_anim=None)
    elif msg.video:        await state.update_data(bc_photo=None, bc_video=msg.video.file_id, bc_anim=None)
    elif msg.animation:    await state.update_data(bc_photo=None, bc_video=None, bc_anim=msg.animation.file_id)
    await bc_ask_btn(msg.chat.id, state)

@dp.callback_query(F.data == "bc_skip_media", BC.media)
async def bc_skip_media(cb: CallbackQuery, state: FSMContext):
    await state.update_data(bc_photo=None, bc_video=None, bc_anim=None)
    await bc_ask_btn(cb.message.chat.id, state); await cb.answer()

async def bc_ask_btn(chat_id, state):
    await state.set_state(BC.btn_t)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Добавить кнопку", callback_data="bc_add_btn")],
        [InlineKeyboardButton(text="⏩ Без кнопки",      callback_data="bc_skip_btn")],
        [InlineKeyboardButton(text="◁ Отмена",           callback_data="adm_panel")],
    ])
    await bot.send_message(chat_id, "Шаг 3: Добавить кнопку?", reply_markup=kb, parse_mode=None)

@dp.callback_query(F.data == "bc_add_btn", BC.btn_t)
async def bc_add_btn(cb: CallbackQuery):
    await bot.send_message(cb.message.chat.id, "Введите текст кнопки:", parse_mode=None); await cb.answer()

@dp.message(BC.btn_t)
async def bc_btn_t(msg: Message, state: FSMContext):
    if not is_admin(msg): return
    await state.update_data(bc_btn_t=msg.text)
    await state.set_state(BC.btn_u)
    await msg.answer("Введите URL кнопки:", parse_mode=None)

@dp.message(BC.btn_u)
async def bc_btn_u(msg: Message, state: FSMContext):
    if not is_admin(msg): return
    await state.update_data(bc_btn_u=msg.text)
    await bc_preview(msg.chat.id, state)

@dp.callback_query(F.data == "bc_skip_btn", BC.btn_t)
async def bc_skip_btn(cb: CallbackQuery, state: FSMContext):
    await state.update_data(bc_btn_t=None, bc_btn_u=None)
    await bc_preview(cb.message.chat.id, state); await cb.answer()

async def bc_preview(chat_id, state):
    d = await state.get_data()
    txt = d.get("bc_text"); photo = d.get("bc_photo"); video = d.get("bc_video"); anim = d.get("bc_anim")
    bt = d.get("bc_btn_t"); bu = d.get("bc_btn_u")
    rm = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=bt, url=bu)]]) if bt and bu else None
    await bot.send_message(chat_id, "Предпросмотр:", parse_mode=None)
    if photo:       await bot.send_photo(chat_id, photo, caption=txt, reply_markup=rm, parse_mode=None)
    elif video:     await bot.send_video(chat_id, video, caption=txt, reply_markup=rm, parse_mode=None)
    elif anim:      await bot.send_animation(chat_id, anim, caption=txt, reply_markup=rm, parse_mode=None)
    else:           await bot.send_message(chat_id, txt, reply_markup=rm, parse_mode=None)
    kb = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="✔️ Отправить", callback_data="bc_confirm"),
        InlineKeyboardButton(text="✖️ Отмена",    callback_data="bc_cancel"),
    ]])
    await bot.send_message(chat_id, "Отправить рассылку?", reply_markup=kb, parse_mode=None)

@dp.callback_query(F.data == "bc_confirm")
async def bc_confirm(cb: CallbackQuery, state: FSMContext):
    if not cb_is_admin(cb): return await cb.answer()
    d = await state.get_data(); await state.clear()
    txt = d.get("bc_text"); photo = d.get("bc_photo"); video = d.get("bc_video"); anim = d.get("bc_anim")
    bt = d.get("bc_btn_t"); bu = d.get("bc_btn_u")
    rm = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=bt, url=bu)]]) if bt and bu else None
    db = load_db(); users = [int(uid) for uid in db.keys()]
    ok = fail = 0
    status = await cb.message.answer("Рассылка начата...", parse_mode=None)
    for uid in users:
        try:
            if photo:      await bot.send_photo(uid, photo, caption=txt, reply_markup=rm, parse_mode=None)
            elif video:    await bot.send_video(uid, video, caption=txt, reply_markup=rm, parse_mode=None)
            elif anim:     await bot.send_animation(uid, anim, caption=txt, reply_markup=rm, parse_mode=None)
            else:          await bot.send_message(uid, txt, reply_markup=rm, parse_mode=None)
            ok += 1
        except Exception: fail += 1
        await asyncio.sleep(0.05)
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="◁ Назад", callback_data="adm_panel")]])
    await status.edit_text("Рассылка завершена\n\nУспешно: " + str(ok) + "\nОшибок: " + str(fail), reply_markup=kb, parse_mode=None)
    await cb.answer()

@dp.callback_query(F.data == "bc_cancel")
async def bc_cancel(cb: CallbackQuery, state: FSMContext):
    await state.clear()
    await cb.message.answer("Рассылка отменена.", reply_markup=admin_kb(), parse_mode=None); await cb.answer()

# ══════════════════════════════════════════
#  ЗАПУСК
# ══════════════════════════════════════════
async def main():
    print("🚔 Police Bot запущен!")
    asyncio.create_task(radar_task())
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
