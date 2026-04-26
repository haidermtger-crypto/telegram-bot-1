import telebot
from telebot import types
import time
import os
import psycopg2
from psycopg2 import pool

# ====== TOKEN ======
TOKEN = os.getenv("BOT_TOKEN")

OWNER_ID = 653170487
CHANNEL = "@mu_un1"

bot = telebot.TeleBot(TOKEN, parse_mode="HTML")

# ====== DATABASE (POOL) ======
DATABASE_URL = os.getenv("DATABASE_URL")

db_pool = psycopg2.pool.SimpleConnectionPool(
    1, 20,
    DATABASE_URL
)

def get_conn():
    return db_pool.getconn()

def put_conn(conn):
    db_pool.putconn(conn)

# ====== INIT TABLES ======
conn = get_conn()
cur = conn.cursor()

cur.execute("""
CREATE TABLE IF NOT EXISTS leaders(
    user_id BIGINT PRIMARY KEY
)
""")

cur.execute("""
CREATE TABLE IF NOT EXISTS players(
    user_id BIGINT PRIMARY KEY,
    name TEXT,
    link TEXT UNIQUE,
    serial TEXT UNIQUE,
    status TEXT DEFAULT 'pending',
    screen_file_id TEXT
)
""")

conn.commit()
put_conn(conn)

# ====== ADD OWNER ======
conn = get_conn()
cur = conn.cursor()

cur.execute(
    "INSERT INTO leaders(user_id) VALUES(%s) ON CONFLICT DO NOTHING",
    (OWNER_ID,)
)

conn.commit()
put_conn(conn)

steps = {}
cache = {}

# ====== FUNCTIONS ======
def is_leader(uid):
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("SELECT 1 FROM leaders WHERE user_id=%s", (uid,))
    res = cur.fetchone()

    put_conn(conn)
    return res is not None


def subscribed(uid):
    if is_leader(uid):
        return True
    try:
        member = bot.get_chat_member(CHANNEL, uid)
        return member.status in ["member", "administrator", "creator"]
    except:
        return False


def user_menu():
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.row("📝 تسجيل", "📊 عدد اللاعبين")
    kb.row("ℹ️ معلومات", "📞 تواصل")
    return kb


def admin_menu():
    kb = user_menu()
    kb.row("📥 الطلبات", "🔍 بحث لاعب")
    kb.row("📢 إعلان")
    kb.row("➕ إضافة قائد", "➖ حذف قائد")
    return kb


def send_home(uid):
    if is_leader(uid):
        bot.send_message(uid, "👑 لوحة القائد", reply_markup=admin_menu())
    else:
        bot.send_message(uid, "أهلاً بك", reply_markup=user_menu())

# ====== START ======
@bot.message_handler(commands=["start"])
def start(msg):
    uid = msg.chat.id
    steps.pop(uid, None)
    cache.pop(uid, None)

    if not subscribed(uid):
        kb = types.InlineKeyboardMarkup()
        kb.add(types.InlineKeyboardButton(
            "اشترك بالقناة",
            url="https://t.me/mu_un1"
        ))
        bot.send_message(uid, "يجب الاشتراك بالقناة ثم أرسل /start", reply_markup=kb)
        return

    send_home(uid)

# ====== REGISTER ======
@bot.message_handler(func=lambda m: m.text == "📝 تسجيل")
def register(m):
    uid = m.chat.id

    if not subscribed(uid):
        start(m)
        return

    conn = get_conn()
    cur = conn.cursor()

    cur.execute("SELECT 1 FROM players WHERE user_id=%s", (uid,))
    exists = cur.fetchone()

    put_conn(conn)

    if exists:
        bot.send_message(uid, "أنت مسجل مسبقاً")
        return

    steps[uid] = "name"
    bot.send_message(uid, "ارسل اسمك")

# ====== COUNT ======
@bot.message_handler(func=lambda m: m.text == "📊 عدد اللاعبين")
def count_users(m):
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("SELECT COUNT(*) FROM players WHERE status='accepted'")
    n = cur.fetchone()[0]

    put_conn(conn)

    bot.send_message(m.chat.id, f"عدد اللاعبين: {n}")

# ====== REQUESTS ======
@bot.message_handler(func=lambda m: m.text == "📥 الطلبات")
def requests_btn(m):
    if not is_leader(m.chat.id):
        return

    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""
        SELECT user_id,name,link,serial,screen_file_id
        FROM players
        WHERE status='pending'
    """)
    rows = cur.fetchall()

    put_conn(conn)

    if not rows:
        bot.send_message(m.chat.id, "لا توجد طلبات")
        return

    for uid, name, link, serial, screen in rows:
        kb = types.InlineKeyboardMarkup()
        kb.row(
            types.InlineKeyboardButton("✅ قبول", callback_data=f"acc:{uid}"),
            types.InlineKeyboardButton("❌ رفض", callback_data=f"rej:{uid}")
        )

        txt = f"""الاسم: {name}
الرابط: {link}
التسلسلي: {serial}
ID: {uid}"""

        if screen:
            bot.send_photo(m.chat.id, screen, caption=txt, reply_markup=kb)
        else:
            bot.send_message(m.chat.id, txt, reply_markup=kb)

# ====== CALLBACK ======
@bot.callback_query_handler(func=lambda c: True)
def callback(c):
    if not is_leader(c.message.chat.id):
        return

    action, uid = c.data.split(":")
    uid = int(uid)

    conn = get_conn()
    cur = conn.cursor()

    if action == "acc":
        cur.execute("UPDATE players SET status='accepted' WHERE user_id=%s", (uid,))
        bot.send_message(uid, "تم قبول طلبك ✅")

    elif action == "rej":
        cur.execute("DELETE FROM players WHERE user_id=%s", (uid,))
        bot.send_message(uid, "تم رفض طلبك ❌")

    conn.commit()
    put_conn(conn)

    bot.answer_callback_query(c.id, "تم")

# ====== STEPS ======
@bot.message_handler(content_types=["text", "photo"])
def all_messages(m):
    uid = m.chat.id
    step = steps.get(uid)

    if not step:
        return

    if m.content_type == "text":
        txt = m.text.strip()

        if step == "name":
            cache[uid] = {"name": txt}
            steps[uid] = "link"
            bot.send_message(uid, "ارسل رابط الفيس")
            return

        if step == "link":
            cache[uid]["link"] = txt
            steps[uid] = "serial"
            bot.send_message(uid, "ارسل الرقم التسلسلي")
            return

        if step == "serial":
            cache[uid]["serial"] = txt
            steps[uid] = "screen"
            bot.send_message(uid, "ارسل سكرين الرقم التسلسلي")
            return

    if m.content_type == "photo" and step == "screen":
        file_id = m.photo[-1].file_id

        conn = get_conn()
        cur = conn.cursor()

        cur.execute("""
            INSERT INTO players(user_id,name,link,serial,status,screen_file_id)
            VALUES(%s,%s,%s,%s,%s,%s)
            ON CONFLICT (user_id) DO NOTHING
        """, (
            uid,
            cache[uid]["name"],
            cache[uid]["link"],
            cache[uid]["serial"],
            "pending",
            file_id
        ))

        conn.commit()
        put_conn(conn)

        steps.pop(uid, None)
        cache.pop(uid, None)

        bot.send_message(uid, "تم إرسال طلبك للمراجعة ✅")

# ====== RUN ======
while True:
    try:
        bot.infinity_polling(skip_pending=True)
    except:
        time.sleep(5)
