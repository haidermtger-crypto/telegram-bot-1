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

# ===== ADD OWNER =====
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

# ===== MENUS =====
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

# ===== INFO =====
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

# ===== CONTACT =====
@bot.message_handler(func=lambda m: m.text=="📞 تواصل")
def contact(m):
    bot.send_message(m.chat.id,"📬 تواصل: @haider_awwd")

# ===== REGISTER =====
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

# ===== COUNT =====
@bot.message_handler(func=lambda m: m.text=="📊 عدد اللاعبين")
def count(m):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM players WHERE status='accepted'")
    n = cur.fetchone()[0]
    put_conn(conn)
    bot.send_message(m.chat.id,f"📊 عدد اللاعبين: {n}")

# ===== REQUESTS =====
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

# ===== CALLBACK =====
@bot.callback_query_handler(func=lambda c: True)
def callback(c):
    if not is_leader(c.message.chat.id):
        return

    conn = get_conn()
    cur = conn.cursor()

    action, uid = c.data.split(":")
    uid = int(uid)

    if action=="acc":
        cur.execute("UPDATE players SET status='accepted' WHERE user_id=%s",(uid,))
        conn.commit()

        bot.send_message(uid,"🎉 تم قبول طلبك بنجاح")

        bot.edit_message_caption(
            chat_id=c.message.chat.id,
            message_id=c.message.message_id,
            caption=c.message.caption + "\n\n✅ تم القبول",
            reply_markup=None
        )

        bot.answer_callback_query(c.id,"تم القبول ✅")

    elif action=="rej":
        cur.execute("DELETE FROM players WHERE user_id=%s",(uid,))
        conn.commit()

        bot.send_message(uid,"❌ تم رفض طلبك، تأكد من صحة معلوماتك")

        bot.edit_message_caption(
            chat_id=c.message.chat.id,
            message_id=c.message.message_id,
            caption=c.message.caption + "\n\n❌ تم الرفض",
            reply_markup=None
        )

        bot.answer_callback_query(c.id,"تم الرفض ❌")

    put_conn(conn)

# ===== ADD LEADER =====
@bot.message_handler(func=lambda m: m.text=="➕ إضافة قائد")
def add_leader(m):
    if not is_leader(m.chat.id): return
    steps[m.chat.id] = "add_leader"
    bot.send_message(m.chat.id,"ارسل ايدي الشخص")

# ===== REMOVE LEADER =====
@bot.message_handler(func=lambda m: m.text=="➖ حذف قائد")
def remove_leader(m):
    if not is_leader(m.chat.id): return
    steps[m.chat.id] = "remove_leader"
    bot.send_message(m.chat.id,"ارسل الايدي")

# ===== BROADCAST =====
@bot.message_handler(func=lambda m: m.text=="📢 إعلان")
def ad(m):
    if not is_leader(m.chat.id): return
    steps[m.chat.id]="broadcast"
    bot.send_message(m.chat.id,"ارسل نص الاعلان")

# ===== SEARCH =====
@bot.message_handler(func=lambda m: m.text=="🔍 بحث لاعب")
def search(m):
    steps[m.chat.id]="search"
    bot.send_message(m.chat.id,"ارسل الاسم او الرابط")

# ===== ALL =====
@bot.message_handler(content_types=["text","photo"])
def all(m):
    uid = m.chat.id
    step = steps.get(uid)

    if not step: return

    # ADD LEADER
    if step=="add_leader":
        try:
            new_id=int(m.text)
            conn=get_conn()
            cur=conn.cursor()
            cur.execute("INSERT INTO leaders(user_id) VALUES(%s) ON CONFLICT DO NOTHING",(new_id,))
            conn.commit()
            put_conn(conn)
            bot.send_message(uid,"✅ تم إضافة قائد")
        except:
            bot.send_message(uid,"❌ خطأ")
        steps.pop(uid)
        return

    # REMOVE LEADER
    if step=="remove_leader":
        try:
            del_id=int(m.text)
            conn=get_conn()
            cur=conn.cursor()
            cur.execute("DELETE FROM leaders WHERE user_id=%s",(del_id,))
            conn.commit()
            put_conn(conn)
            bot.send_message(uid,"✅ تم حذف قائد")
        except:
            bot.send_message(uid,"❌ خطأ")
        steps.pop(uid)
        return

    # BROADCAST
    if step=="broadcast":
        conn=get_conn()
        cur=conn.cursor()
        cur.execute("SELECT user_id FROM players WHERE status='accepted'")
        users=cur.fetchall()
        put_conn(conn)

        for u in users:
            try: bot.send_message(u[0],m.text)
            except: pass

        bot.send_message(uid,"✅ تم الإرسال")
        steps.pop(uid)
        return

    # SEARCH
    if step=="search":
        conn=get_conn()
        cur=conn.cursor()
        cur.execute("""
        SELECT name,link,serial,screen_file_id 
        FROM players 
        WHERE name ILIKE %s OR link ILIKE %s
        """,('%'+m.text+'%','%'+m.text+'%'))
        results=cur.fetchall()
        put_conn(conn)

        if not results:
            bot.send_message(uid,"❌ لا يوجد")
        else:
            for name,link,serial,screen in results:
                txt=f"👤 {name}\n🔗 {link}\n🔢 {serial}"
                if screen:
                    bot.send_photo(uid,screen,caption=txt)
                else:
                    bot.send_message(uid,txt)

        steps.pop(uid)
        return

    # REGISTER
    if m.content_type=="text":
        if step=="name":
            cache[uid]={"name":m.text}
            steps[uid]="link"
            bot.send_message(uid,"ارسل رابط الفيس")
            return

        if step=="link":
            if not valid_facebook(m.text):
                bot.send_message(uid,"❌ رابط غير صالح")
                return
            cache[uid]["link"]=m.text
            steps[uid]="serial"
            bot.send_message(uid,"ارسل الرقم التسلسلي")
            return

        if step=="serial":
            cache[uid]["serial"]=m.text
            steps[uid]="screen"
            bot.send_message(uid,"ارسل سكرين")
            return

    if m.content_type=="photo" and step=="screen":
        file_id=m.photo[-1].file_id

        conn=get_conn()
        cur=conn.cursor()
        cur.execute("""
        INSERT INTO players(user_id,name,link,serial,status,screen_file_id)
        VALUES(%s,%s,%s,%s,'pending',%s)
        ON CONFLICT (user_id)
        DO UPDATE SET name=EXCLUDED.name,link=EXCLUDED.link,serial=EXCLUDED.serial,screen_file_id=EXCLUDED.screen_file_id,status='pending'
        """,(uid,cache[uid]["name"],cache[uid]["link"],cache[uid]["serial"],file_id))

        conn.commit()
        put_conn(conn)

        bot.send_message(uid,"📩 تم إرسال طلبك للمراجعة")
        steps.pop(uid)
        cache.pop(uid)

# ===== RUN =====
while True:
    try:
        bot.infinity_polling(skip_pending=True)
    except:
        time.sleep(5)
