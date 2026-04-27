import telebot
from telebot import types
import time
import os
import psycopg2
from psycopg2 import pool
import re
from datetime import datetime

TOKEN = os.getenv("BOT_TOKEN")
OWNER_ID = 653170487
CHANNEL = "@mu_un1"

bot = telebot.TeleBot(TOKEN, parse_mode="HTML")

DATABASE_URL = os.getenv("DATABASE_URL")

db_pool = psycopg2.pool.SimpleConnectionPool(1, 20, DATABASE_URL)

def get_conn():
    return db_pool.getconn()

def put_conn(conn):
    db_pool.putconn(conn)

# ===== DATABASE =====
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

# add owner
conn = get_conn()
cur = conn.cursor()
cur.execute("INSERT INTO leaders(user_id) VALUES(%s) ON CONFLICT DO NOTHING", (OWNER_ID,))
conn.commit()
put_conn(conn)

steps = {}
cache = {}

# ===== FUNCTIONS =====
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

def valid_facebook(link):
    return re.match(r"(https?://)?(www\.)?(facebook\.com|fb\.com)/", link)

def user_menu(uid):
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.row("📝 تسجيل", "📊 عدد اللاعبين")
    kb.row("ℹ️ معلومات", "📞 تواصل")

    # زر تغيير الرقم فقط من 1-5
    day = datetime.now().day
    if 1 <= day <= 5:
        kb.row("🔄 تغيير الرقم")

    return kb

def admin_menu(uid):
    kb = user_menu(uid)
    kb.row("📥 الطلبات", "🔍 بحث لاعب")
    kb.row("📢 إعلان")
    kb.row("➕ إضافة قائد", "➖ حذف قائد")
    return kb

def send_home(uid):
    if is_leader(uid):
        bot.send_message(uid, "👑 لوحة القائد", reply_markup=admin_menu(uid))
    else:
        bot.send_message(uid, "أهلاً بك", reply_markup=user_menu(uid))

# ===== START =====
@bot.message_handler(commands=["start"])
def start(msg):
    uid = msg.chat.id
    steps.pop(uid, None)
    cache.pop(uid, None)

    if not subscribed(uid):
        kb = types.InlineKeyboardMarkup()
        kb.add(types.InlineKeyboardButton("اشترك", url="https://t.me/mu_un1"))
        bot.send_message(uid, "اشترك ثم /start", reply_markup=kb)
        return

    send_home(uid)

# ===== REGISTER =====
@bot.message_handler(func=lambda m: m.text == "📝 تسجيل")
def register(m):
    uid = m.chat.id

    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM players WHERE user_id=%s", (uid,))
    if cur.fetchone():
        bot.send_message(uid, "أنت مسجل مسبقاً")
        put_conn(conn)
        return

    put_conn(conn)

    steps[uid] = "name"
    bot.send_message(uid, "ارسل اسمك")

# ===== SEARCH =====
@bot.message_handler(func=lambda m: m.text == "🔍 بحث لاعب")
def search(m):
    steps[m.chat.id] = "search"
    bot.send_message(m.chat.id, "ارسل الاسم او الرابط")

# ===== ANNOUNCE =====
@bot.message_handler(func=lambda m: m.text == "📢 إعلان")
def announce(m):
    if not is_leader(m.chat.id):
        return
    steps[m.chat.id] = "broadcast"
    bot.send_message(m.chat.id, "ارسل نص الإعلان")

# ===== CONTACT =====
@bot.message_handler(func=lambda m: m.text == "📞 تواصل")
def contact(m):
    bot.send_message(m.chat.id, "📩 تواصل: @haider_awwd")

# ===== ADD LEADER =====
@bot.message_handler(func=lambda m: m.text == "➕ إضافة قائد")
def add_leader(m):
    if m.chat.id != OWNER_ID:
        return
    steps[m.chat.id] = "add_leader"
    bot.send_message(m.chat.id, "ارسل ايدي الشخص")

# ===== DELETE LEADER =====
@bot.message_handler(func=lambda m: m.text == "➖ حذف قائد")
def del_leader(m):
    if m.chat.id != OWNER_ID:
        return
    steps[m.chat.id] = "del_leader"
    bot.send_message(m.chat.id, "ارسل ايدي الحذف")

# ===== CHANGE SERIAL =====
@bot.message_handler(func=lambda m: m.text == "🔄 تغيير الرقم")
def change_serial(m):
    uid = m.chat.id

    day = datetime.now().day
    if not (1 <= day <= 5):
        bot.send_message(uid, "❌ فقط من يوم 1 الى 5")
        return

    steps[uid] = "change_serial"
    bot.send_message(uid, "ارسل الرقم الجديد")

# ===== STEPS =====
@bot.message_handler(content_types=["text", "photo"])
def all(m):
    uid = m.chat.id
    step = steps.get(uid)

    if not step:
        return

    if step == "search":
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("""
        SELECT name,link,serial FROM players
        WHERE name ILIKE %s OR link ILIKE %s
        """, (f"%{m.text}%", f"%{m.text}%"))
        res = cur.fetchall()
        put_conn(conn)

        if not res:
            bot.send_message(uid, "ماكو نتائج")
        else:
            for r in res:
                bot.send_message(uid, f"{r[0]}\n{r[1]}\n{r[2]}")

        steps.pop(uid)
        return

    if step == "broadcast":
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("SELECT user_id FROM players WHERE status='accepted'")
        users = cur.fetchall()
        put_conn(conn)

        for u in users:
            try:
                bot.send_message(u[0], f"📢 {m.text}")
            except:
                pass

        bot.send_message(uid, "تم الإرسال ✅")
        steps.pop(uid)
        return

    if step == "add_leader":
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("INSERT INTO leaders(user_id) VALUES(%s) ON CONFLICT DO NOTHING", (int(m.text),))
        conn.commit()
        put_conn(conn)
        bot.send_message(uid, "تم إضافة قائد ✅")
        steps.pop(uid)
        return

    if step == "del_leader":
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("DELETE FROM leaders WHERE user_id=%s", (int(m.text),))
        conn.commit()
        put_conn(conn)
        bot.send_message(uid, "تم الحذف ❌")
        steps.pop(uid)
        return

    if step == "change_serial":
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("UPDATE players SET serial=%s WHERE user_id=%s", (m.text, uid))
        conn.commit()
        put_conn(conn)
        bot.send_message(uid, "تم التحديث ✅")
        steps.pop(uid)
        return

    # ===== REGISTER FLOW =====
    if m.content_type == "text":
        if step == "name":
            cache[uid] = {"name": m.text}
            steps[uid] = "link"
            bot.send_message(uid, "ارسل رابط الفيس")
            return

        if step == "link":
            if not valid_facebook(m.text):
                bot.send_message(uid, "❌ هذا ليس رابط فيسبوك")
                return

            cache[uid]["link"] = m.text
            steps[uid] = "serial"
            bot.send_message(uid, "ارسل الرقم التسلسلي")
            return

        if step == "serial":
            cache[uid]["serial"] = m.text
            steps[uid] = "screen"
            bot.send_message(uid, "ارسل سكرين")
            return

    if m.content_type == "photo" and step == "screen":
        file_id = m.photo[-1].file_id

        conn = get_conn()
        cur = conn.cursor()

        cur.execute("""
        INSERT INTO players(user_id,name,link,serial,status,screen_file_id)
        VALUES(%s,%s,%s,%s,'pending',%s)
        """, (
            uid,
            cache[uid]["name"],
            cache[uid]["link"],
            cache[uid]["serial"],
            file_id
        ))

        conn.commit()
        put_conn(conn)

        steps.pop(uid)
        cache.pop(uid)

        bot.send_message(uid, "تم إرسال الطلب ✅")

# ===== RUN =====
while True:
    try:
        bot.infinity_polling(skip_pending=True)
    except:
        time.sleep(5)
