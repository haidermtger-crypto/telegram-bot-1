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

# ===== DB =====
conn = get_conn()
cur = conn.cursor()

cur.execute("CREATE TABLE IF NOT EXISTS leaders(user_id BIGINT PRIMARY KEY)")
cur.execute("""
CREATE TABLE IF NOT EXISTS players(
    user_id BIGINT PRIMARY KEY,
    name TEXT,
    link TEXT,
    serial TEXT,
    status TEXT DEFAULT 'pending',
    screen_file_id TEXT
)
""")

conn.commit()
put_conn(conn)

conn = get_conn()
cur = conn.cursor()
cur.execute("INSERT INTO leaders(user_id) VALUES(%s) ON CONFLICT DO NOTHING",(OWNER_ID,))
conn.commit()
put_conn(conn)

steps = {}
cache = {}

# ===== FUNCTIONS =====
def is_leader(uid):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM leaders WHERE user_id=%s",(uid,))
    r = cur.fetchone()
    put_conn(conn)
    return r is not None

def subscribed(uid):
    if is_leader(uid): return True
    try:
        m = bot.get_chat_member(CHANNEL, uid)
        return m.status in ["member","administrator","creator"]
    except:
        return False

def valid_facebook(link):
    return re.match(r"(https?://)?(www\.)?(facebook\.com|fb\.com)/", link)

def user_menu():
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.row("📝 تسجيل","📊 عدد اللاعبين")
    kb.row("ℹ️ معلومات","📞 تواصل")
    kb.row("🔍 بحث لاعب")
    return kb

def admin_menu():
    kb = user_menu()
    kb.row("📥 الطلبات","📢 إعلان")
    kb.row("➕ إضافة قائد","➖ حذف قائد")
    return kb

def send_home(uid):
    if is_leader(uid):
        bot.send_message(uid,"👑 لوحة القائد",reply_markup=admin_menu())
    else:
        bot.send_message(uid,"أهلاً بك",reply_markup=user_menu())

# ===== START =====
@bot.message_handler(commands=["start"])
def start(m):
    uid = m.chat.id
    steps.pop(uid,None)
    cache.pop(uid,None)

    if not subscribed(uid):
        kb = types.InlineKeyboardMarkup()
        kb.add(types.InlineKeyboardButton("اشترك",url="https://t.me/mu_un1"))
        bot.send_message(uid,"اشترك بالقناة ثم /start",reply_markup=kb)
        return

    send_home(uid)

# ===== معلومات =====
@bot.message_handler(func=lambda m: m.text=="ℹ️ معلومات")
def info(m):
    bot.send_message(m.chat.id,
"""اهلا وسهلا 
هذا ال بوت خاص ببيانات لاعبين الاتحاد العراقي يرجى ارسال 
اسمك 
رابط صفحتك على فيس بوك 
الرقم التسلسلي 
سكرين للرقم التسلسلي 

بعدها سيصل طلبك للقاده للمراجعه 

تنويه 
متاح تغير معلوماتك بالفترة من 1 الى 5 من كل شهر 

تحياتنا لكم 
الاتحاد العراقي للكلانات""")

# ===== تواصل =====
@bot.message_handler(func=lambda m: m.text=="📞 تواصل")
def contact(m):
    bot.send_message(m.chat.id,"📬 تواصل: @haider_awwd")

# ===== تسجيل =====
@bot.message_handler(func=lambda m: m.text=="📝 تسجيل")
def reg(m):
    uid = m.chat.id

    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT status FROM players WHERE user_id=%s",(uid,))
    row = cur.fetchone()
    put_conn(conn)

    if row:
        day = datetime.now().day
        if day < 1 or day > 5:
            bot.send_message(uid,"❌ لا يمكنك التعديل الآن")
            return

    steps[uid]="name"
    bot.send_message(uid,"ارسل اسمك")

# ===== عدد =====
@bot.message_handler(func=lambda m: m.text=="📊 عدد اللاعبين")
def count(m):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM players WHERE status='accepted'")
    n = cur.fetchone()[0]
    put_conn(conn)
    bot.send_message(m.chat.id,f"📊 عدد اللاعبين: {n}")

# ===== طلبات =====
@bot.message_handler(func=lambda m: m.text=="📥 الطلبات")
def requests(m):
    if not is_leader(m.chat.id): return

    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT user_id,name,link,serial,screen_file_id FROM players WHERE status='pending'")
    rows = cur.fetchall()
    put_conn(conn)

    if not rows:
        bot.send_message(m.chat.id,"📭 لا توجد طلبات للمراجعة")
        return

    for uid,name,link,serial,screen in rows:
        kb = types.InlineKeyboardMarkup()
        kb.row(
            types.InlineKeyboardButton("✅ قبول",callback_data=f"acc:{uid}"),
            types.InlineKeyboardButton("❌ رفض",callback_data=f"rej:{uid}")
        )

        txt=f"{name}\n{link}\n{serial}\nID:{uid}"

        if screen:
            bot.send_photo(m.chat.id,screen,caption=txt,reply_markup=kb)
        else:
            bot.send_message(m.chat.id,txt,reply_markup=kb)

# ===== CALLBACK (FIXED) =====
@bot.callback_query_handler(func=lambda c: True)
def callback(c):
    if not is_leader(c.message.chat.id):
        return

    conn = get_conn()
    cur = conn.cursor()

    action, uid = c.data.split(":")
    uid = int(uid)

    old_text = c.message.caption if c.message.caption else c.message.text

    if action=="acc":
        cur.execute("UPDATE players SET status='accepted' WHERE user_id=%s",(uid,))
        conn.commit()

        bot.send_message(uid,"🎉 تم قبول طلبك بنجاح")

        new_text = old_text + "\n\n✅ تمت الموافقة"

    elif action=="rej":
        cur.execute("DELETE FROM players WHERE user_id=%s",(uid,))
        conn.commit()

        bot.send_message(uid,"❌ تم رفض طلبك، تأكد من صحة معلوماتك")

        new_text = old_text + "\n\n❌ تم الرفض"

    try:
        if c.message.photo:
            bot.edit_message_caption(
                caption=new_text,
                chat_id=c.message.chat.id,
                message_id=c.message.message_id,
                reply_markup=None
            )
        else:
            bot.edit_message_text(
                text=new_text,
                chat_id=c.message.chat.id,
                message_id=c.message.message_id,
                reply_markup=None
            )
    except:
        pass

    bot.answer_callback_query(c.id,"تم")
    put_conn(conn)

# ===== RUN =====
while True:
    try:
        bot.infinity_polling(skip_pending=True)
    except:
        time.sleep(5)
