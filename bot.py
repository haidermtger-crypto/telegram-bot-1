import telebot
from telebot import types
import time, os, re
import psycopg2
from psycopg2 import pool
from datetime import datetime

TOKEN = os.getenv("BOT_TOKEN")
OWNER_ID = 653170487
CHANNEL = "@mu_un1"

bot = telebot.TeleBot(TOKEN, parse_mode="HTML")

DATABASE_URL = os.getenv("DATABASE_URL")
db_pool = psycopg2.pool.SimpleConnectionPool(1, 20, DATABASE_URL)

def get_conn(): return db_pool.getconn()
def put_conn(conn): db_pool.putconn(conn)

# ===== DATABASE =====
conn = get_conn()
cur = conn.cursor()

cur.execute("""CREATE TABLE IF NOT EXISTS leaders(
user_id BIGINT PRIMARY KEY)""")

cur.execute("""CREATE TABLE IF NOT EXISTS players(
user_id BIGINT PRIMARY KEY,
name TEXT,
link TEXT,
serial TEXT,
status TEXT,
screen TEXT)""")

conn.commit()
put_conn(conn)

# add owner
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
    return r

def subscribed(uid):
    try:
        m = bot.get_chat_member(CHANNEL, uid)
        return m.status in ["member","administrator","creator"]
    except:
        return False

def is_facebook(link):
    return "facebook.com" in link.lower()

def allow_edit():
    day = datetime.now().day
    return 1 <= day <= 5

# ===== MENUS =====
def user_menu():
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.row("📝 تسجيل","📊 عدد اللاعبين")
    kb.row("ℹ️ معلومات","📞 تواصل")
    return kb

def admin_menu():
    kb = user_menu()
    kb.row("📥 الطلبات","🔍 بحث لاعب")
    kb.row("📢 إعلان")
    kb.row("➕ إضافة قائد","➖ حذف قائد")
    return kb

def home(uid):
    if is_leader(uid):
        bot.send_message(uid,"👑 لوحة القائد",reply_markup=admin_menu())
    else:
        bot.send_message(uid,"أهلاً بك",reply_markup=user_menu())

# ===== START =====
@bot.message_handler(commands=["start"])
def start(m):
    uid = m.chat.id
    steps.pop(uid,None)

    if not subscribed(uid):
        bot.send_message(uid,"اشترك بالقناة ثم /start")
        return

    home(uid)

# ===== INFO =====
@bot.message_handler(func=lambda m: m.text=="ℹ️ معلومات")
def info(m):
    bot.send_message(m.chat.id,
"""اهلا وسهلا 
هذا ال بوت خاص بييانات لاعبين الاتحاد العراقي يرجى ارسال 
اسمك 
رابط صفحتك على فيس بوك 
الرقم التسلسلي 
سكرين للرقم التسلسلي 

بعدها سيصل طلبك للقاده للمراجعه 

تنويه 
متاح تغير معلوماتك بالفترة من 1 إلى 5 من كل شهر 

تحياتنا لكم 
الاتحاد العراقي للكلانات""")

# ===== CONTACT =====
@bot.message_handler(func=lambda m: m.text=="📞 تواصل")
def contact(m):
    bot.send_message(m.chat.id,"📬 تواصل: @haider_awwd")

# ===== REGISTER =====
@bot.message_handler(func=lambda m: m.text=="📝 تسجيل")
def reg(m):
    uid = m.chat.id

    if not allow_edit():
        bot.send_message(uid,"❌ لا يمكنك التعديل الآن")
        return

    steps[uid]="name"
    bot.send_message(uid,"ارسل اسمك")

# ===== COUNT =====
@bot.message_handler(func=lambda m: m.text=="📊 عدد اللاعبين")
def count(m):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM players WHERE status='accepted'")
    n = cur.fetchone()[0]
    put_conn(conn)

    bot.send_message(m.chat.id,f"عدد اللاعبين: {n}")

# ===== SEARCH =====
@bot.message_handler(func=lambda m: m.text=="🔍 بحث لاعب")
def search_btn(m):
    if not is_leader(m.chat.id): return
    steps[m.chat.id]="search"
    bot.send_message(m.chat.id,"ارسل الاسم او الرابط")

# ===== REQUESTS =====
@bot.message_handler(func=lambda m: m.text=="📥 الطلبات")
def requests(m):
    if not is_leader(m.chat.id): return

    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT * FROM players WHERE status='pending'")
    rows = cur.fetchall()
    put_conn(conn)

    if not rows:
        bot.send_message(m.chat.id,"📭 لا توجد طلبات للمراجعة")
        return

    for r in rows:
        uid,name,link,serial,status,screen = r

        kb = types.InlineKeyboardMarkup()
        kb.row(
            types.InlineKeyboardButton("✅ قبول",callback_data=f"acc:{uid}"),
            types.InlineKeyboardButton("❌ رفض",callback_data=f"rej:{uid}")
        )

        txt=f"{name}\n{link}\n{serial}\nID:{uid}"

        bot.send_photo(m.chat.id,screen,caption=txt,reply_markup=kb)

# ===== CALLBACK =====
@bot.callback_query_handler(func=lambda c: True)
def call(c):
    if not is_leader(c.message.chat.id): return

    action,uid = c.data.split(":")
    uid=int(uid)

    conn = get_conn()
    cur = conn.cursor()

    if action=="acc":
        cur.execute("UPDATE players SET status='accepted' WHERE user_id=%s",(uid,))
        bot.send_message(uid,"✅ تم قبول طلبك بنجاح")
        bot.edit_message_caption("✅ تمت الموافقة",c.message.chat.id,c.message.message_id)

    if action=="rej":
        cur.execute("DELETE FROM players WHERE user_id=%s",(uid,))
        bot.send_message(uid,"❌ تم رفض طلبك تأكد من المعلومات")
        bot.edit_message_caption("❌ تم الرفض",c.message.chat.id,c.message.message_id)

    conn.commit()
    put_conn(conn)

# ===== ALL MESSAGES =====
@bot.message_handler(content_types=["text","photo"])
def all(m):
    uid = m.chat.id
    step = steps.get(uid)

    if not step: return

    if step=="search":
        conn = get_conn()
        cur = conn.cursor()

        cur.execute("""SELECT * FROM players 
        WHERE name ILIKE %s OR link ILIKE %s""",
        (f"%{m.text}%",f"%{m.text}%"))

        r = cur.fetchone()
        put_conn(conn)

        if not r:
            bot.send_message(uid,"❌ لا يوجد لاعب")
            return

        _,name,link,serial,_,screen = r

        bot.send_photo(uid,screen,
        caption=f"👤 {name}\n🔗 {link}\n🔢 {serial}")

        steps.pop(uid)
        return

    if m.content_type=="text":
        if step=="name":
            cache[uid]={"name":m.text}
            steps[uid]="link"
            bot.send_message(uid,"ارسل رابط الفيس")

        elif step=="link":
            if not is_facebook(m.text):
                bot.send_message(uid,"❌ هذا ليس رابط فيس بوك")
                return
            cache[uid]["link"]=m.text
            steps[uid]="serial"
            bot.send_message(uid,"ارسل الرقم التسلسلي")

        elif step=="serial":
            cache[uid]["serial"]=m.text
            steps[uid]="screen"
            bot.send_message(uid,"ارسل سكرين")

    elif m.content_type=="photo" and step=="screen":
        file_id = m.photo[-1].file_id

        conn = get_conn()
        cur = conn.cursor()

        cur.execute("""INSERT INTO players VALUES(%s,%s,%s,%s,%s,%s)
        ON CONFLICT (user_id) DO UPDATE SET
        name=EXCLUDED.name,
        link=EXCLUDED.link,
        serial=EXCLUDED.serial,
        status='pending',
        screen=EXCLUDED.screen""",
        (uid,cache[uid]["name"],cache[uid]["link"],
         cache[uid]["serial"],"pending",file_id))

        conn.commit()
        put_conn(conn)

        steps.pop(uid)
        cache.pop(uid)

        bot.send_message(uid,"📨 تم إرسال طلبك للمراجعة")

# ===== RUN =====
while True:
    try:
        bot.infinity_polling(skip_pending=True)
    except:
        time.sleep(5)
