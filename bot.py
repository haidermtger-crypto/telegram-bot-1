import telebot
from telebot import types
import time
import os
import psycopg2
from psycopg2 import pool
from datetime import datetime
import re

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
        return member.status in ["member","administrator","creator"]
    except:
        return False

def valid_facebook(link):
    return "facebook.com" in link or "fb.com" in link

def can_edit():
    d = datetime.now().day
    return 1 <= d <= 5

def user_menu():
    kb = types.ReplyKeyboardMarkup(resize_keyboard=True)
    kb.row("📝 تسجيل", "📊 عدد اللاعبين")
    kb.row("ℹ️ معلومات", "📞 تواصل")
    kb.row("🔄 تغيير التسلسلي")
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

# ===== START =====
@bot.message_handler(commands=["start"])
def start(m):
    if not subscribed(m.chat.id):
        bot.send_message(m.chat.id,"اشترك بالقناة ثم ارسل /start")
        return
    send_home(m.chat.id)

# ===== INFO =====
@bot.message_handler(func=lambda m: "معلومات" in m.text)
def info(m):
    bot.send_message(m.chat.id, """اهلا وسهلا 
هذا ال بوت خاص بييانات لاعبين الاتحاد العراقي يرجى ارسال 
اسمك 
رابط صفحتك على فيس بوك 
الرقم التسلسلي 
سكرين للرقم التسلسلي 
بعدها سيصب طلبك للقاده للمراجعه 

تنويه 
متاح تغير معلوماتك بالفنره من 1/5 من كل شهر 
تحياتنا لكم 
الاتحاد العراقي للكلانات""")

# ===== CONTACT =====
@bot.message_handler(func=lambda m: "تواصل" in m.text)
def contact(m):
    bot.send_message(m.chat.id, "📩 تواصل: @haider_awwd")

# ===== COUNT =====
@bot.message_handler(func=lambda m: "عدد اللاعبين" in m.text)
def count_users(m):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM players WHERE status='accepted'")
    n = cur.fetchone()[0]
    put_conn(conn)
    bot.send_message(m.chat.id, f"📊 عدد اللاعبين: {n}")

# ===== REGISTER =====
@bot.message_handler(func=lambda m: "تسجيل" in m.text)
def register(m):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT 1 FROM players WHERE user_id=%s",(m.chat.id,))
    if cur.fetchone():
        bot.send_message(m.chat.id,"أنت مسجل مسبقاً")
        return
    put_conn(conn)

    steps[m.chat.id] = "name"
    bot.send_message(m.chat.id,"ارسل اسمك")

# ===== REQUESTS =====
@bot.message_handler(func=lambda m: m.text and "الطلبات" in m.text)
def requests_btn(m):
    if not is_leader(m.chat.id):
        return

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

# ===== CALLBACK =====
@bot.callback_query_handler(func=lambda c: True)
def cb(c):
    if not is_leader(c.message.chat.id):
        return

    action,uid = c.data.split(":")
    uid=int(uid)

    conn=get_conn()
    cur=conn.cursor()

    if action=="acc":
        cur.execute("UPDATE players SET status='accepted' WHERE user_id=%s",(uid,))
        bot.send_message(uid,"تم القبول ✅")

    if action=="rej":
        cur.execute("DELETE FROM players WHERE user_id=%s",(uid,))
        bot.send_message(uid,"تم الرفض ❌")

    conn.commit()
    put_conn(conn)

# ===== SEARCH =====
@bot.message_handler(func=lambda m: "بحث لاعب" in m.text)
def search(m):
    steps[m.chat.id]="search"
    bot.send_message(m.chat.id,"ارسل الاسم او الرابط")

# ===== ANNOUNCE =====
@bot.message_handler(func=lambda m: "إعلان" in m.text)
def announce(m):
    if not is_leader(m.chat.id):
        return
    steps[m.chat.id]="announce"
    bot.send_message(m.chat.id,"ارسل نص الاعلان")

# ===== ADD LEADER =====
@bot.message_handler(func=lambda m: "إضافة قائد" in m.text)
def add_leader(m):
    if m.chat.id!=OWNER_ID:
        return
    steps[m.chat.id]="add_leader"
    bot.send_message(m.chat.id,"ارسل ايدي")

@bot.message_handler(func=lambda m: "حذف قائد" in m.text)
def del_leader(m):
    if m.chat.id!=OWNER_ID:
        return
    steps[m.chat.id]="del_leader"
    bot.send_message(m.chat.id,"ارسل ايدي")

# ===== CHANGE SERIAL =====
@bot.message_handler(func=lambda m: "تغيير التسلسلي" in m.text)
def change_serial(m):
    if not can_edit():
        bot.send_message(m.chat.id,"❌ التعديل متاح فقط من 1 الى 5")
        return
    steps[m.chat.id]="change_serial"
    bot.send_message(m.chat.id,"ارسل الرقم الجديد")

# ===== ALL STEPS =====
@bot.message_handler(content_types=["text","photo"])
def steps_handler(m):
    uid=m.chat.id
    step=steps.get(uid)

    if not step:
        return

    if step=="name":
        cache[uid]={"name":m.text}
        steps[uid]="link"
        bot.send_message(uid,"ارسل رابط الفيس")
        return

    if step=="link":
        if not valid_facebook(m.text):
            bot.send_message(uid,"❌ هذا ليس رابط فيس بوك")
            return
        cache[uid]["link"]=m.text
        steps[uid]="serial"
        bot.send_message(uid,"ارسل التسلسلي")
        return

    if step=="serial":
        cache[uid]["serial"]=m.text
        steps[uid]="screen"
        bot.send_message(uid,"ارسل صورة")
        return

    if step=="screen" and m.photo:
        conn=get_conn()
        cur=conn.cursor()

        cur.execute("""
        INSERT INTO players(user_id,name,link,serial,status,screen_file_id)
        VALUES(%s,%s,%s,%s,%s,%s)
        """,(uid,cache[uid]["name"],cache[uid]["link"],cache[uid]["serial"],"pending",m.photo[-1].file_id))

        conn.commit()
        put_conn(conn)

        bot.send_message(uid,"تم ارسال الطلب ✅")
        steps.pop(uid)
        cache.pop(uid)
        return

    if step=="search":
        conn=get_conn()
        cur=conn.cursor()

        cur.execute("SELECT name,link,serial FROM players WHERE name ILIKE %s OR link ILIKE %s",('%'+m.text+'%','%'+m.text+'%'))
        rows=cur.fetchall()
        put_conn(conn)

        if not rows:
            bot.send_message(uid,"لا يوجد")
        else:
            for r in rows:
                bot.send_message(uid,f"{r[0]}\n{r[1]}\n{r[2]}")
        steps.pop(uid)
        return

    if step=="announce":
        conn=get_conn()
        cur=conn.cursor()
        cur.execute("SELECT user_id FROM players")
        users=cur.fetchall()
        put_conn(conn)

        for u in users:
            try:
                bot.send_message(u[0],f"📢 {m.text}")
            except:
                pass

        bot.send_message(uid,"تم الارسال ✅")
        steps.pop(uid)
        return

    if step=="add_leader":
        conn=get_conn()
        cur=conn.cursor()
        cur.execute("INSERT INTO leaders(user_id) VALUES(%s) ON CONFLICT DO NOTHING",(int(m.text),))
        conn.commit()
        put_conn(conn)
        bot.send_message(uid,"تم اضافة قائد ✅")
        steps.pop(uid)
        return

    if step=="del_leader":
        conn=get_conn()
        cur=conn.cursor()
        cur.execute("DELETE FROM leaders WHERE user_id=%s",(int(m.text),))
        conn.commit()
        put_conn(conn)
        bot.send_message(uid,"تم الحذف ❌")
        steps.pop(uid)
        return

    if step=="change_serial":
        conn=get_conn()
        cur=conn.cursor()
        cur.execute("UPDATE players SET serial=%s WHERE user_id=%s",(m.text,uid))
        conn.commit()
        put_conn(conn)
        bot.send_message(uid,"تم التعديل ✅")
        steps.pop(uid)
        return

# ===== RUN =====
while True:
    try:
        bot.infinity_polling(skip_pending=True)
    except:
        time.sleep(5)
