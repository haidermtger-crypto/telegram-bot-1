import telebot
from telebot import types
import time
import os
import psycopg2
import re

TOKEN = os.getenv("BOT_TOKEN")
OWNER_ID = 653170487
CHANNEL = "@mu_un1"

bot = telebot.TeleBot(TOKEN, parse_mode="HTML")
DATABASE_URL = os.getenv("DATABASE_URL")

conn = psycopg2.connect(DATABASE_URL)
cur = conn.cursor()

# ====== TABLES ======
cur.execute("""
CREATE TABLE IF NOT EXISTS leaders(
    user_id BIGINT PRIMARY KEY
)
""")

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

cur.execute("INSERT INTO leaders(user_id) VALUES(%s) ON CONFLICT DO NOTHING", (OWNER_ID,))
conn.commit()

steps = {}
cache = {}

# ====== FUNCTIONS ======
def is_leader(uid):
    cur.execute("SELECT 1 FROM leaders WHERE user_id=%s", (uid,))
    return cur.fetchone() is not None

def subscribed(uid):
    if is_leader(uid):
        return True
    try:
        member = bot.get_chat_member(CHANNEL, uid)
        return member.status in ["member", "administrator", "creator"]
    except:
        return False

def is_facebook_link(link):
    return bool(re.search(r"(facebook\.com|fb\.com)", link.lower()))

# ====== MENUS ======
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
        bot.send_message(uid, "اشترك بالقناة أولاً")
        return

    send_home(uid)

# ====== REGISTER ======
@bot.message_handler(func=lambda m: m.text == "📝 تسجيل")
def register(m):
    uid = m.chat.id

    cur.execute("SELECT 1 FROM players WHERE user_id=%s", (uid,))
    if cur.fetchone():
        bot.send_message(uid, "أنت مسجل مسبقاً")
        return

    steps[uid] = "name"
    bot.send_message(uid, "ارسل اسمك")

# ====== COUNT ======
@bot.message_handler(func=lambda m: m.text == "📊 عدد اللاعبين")
def count_users(m):
    cur.execute("SELECT COUNT(*) FROM players WHERE status='accepted'")
    n = cur.fetchone()[0]
    bot.send_message(m.chat.id, f"📊 عدد اللاعبين: {n}")

# ====== INFO ======
@bot.message_handler(func=lambda m: m.text == "ℹ️ معلومات")
def info(m):
    txt = """اهلا وسهلا 👋

هذا البوت خاص ببيانات لاعبين الاتحاد العراقي

يرجى ارسال:
- اسمك
- رابط صفحتك على فيس بوك
- الرقم التسلسلي
- سكرين للرقم التسلسلي

بعدها سيصل طلبك للقادة للمراجعة ✅

تنويه ⚠️
متاح تغير معلوماتك من 1 إلى 5 من كل شهر

تحياتنا ❤️
الاتحاد العراقي للكلانات"""
    bot.send_message(m.chat.id, txt)

# ====== CONTACT ======
@bot.message_handler(func=lambda m: m.text == "📞 تواصل")
def contact(m):
    bot.send_message(m.chat.id, "📬 تواصل: @haider_awwd")

# ====== REQUESTS ======
@bot.message_handler(func=lambda m: m.text == "📥 الطلبات")
def requests_btn(m):
    if not is_leader(m.chat.id):
        return

    cur.execute("SELECT * FROM players WHERE status='pending'")
    rows = cur.fetchall()

    if not rows:
        bot.send_message(m.chat.id, "📭 لا توجد طلبات للمراجعة")
        return

    for row in rows:
        uid, name, link, serial, status, screen = row

        kb = types.InlineKeyboardMarkup()
        kb.row(
            types.InlineKeyboardButton("✅ قبول", callback_data=f"acc:{uid}"),
            types.InlineKeyboardButton("❌ رفض", callback_data=f"rej:{uid}")
        )

        txt = f"{name}\n{link}\n{serial}\nID:{uid}"

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

    if action == "acc":
        cur.execute("UPDATE players SET status='accepted' WHERE user_id=%s", (uid,))
        conn.commit()

        bot.send_message(uid, "🎉 تم قبول طلبك بنجاح")
        bot.send_message(c.message.chat.id, "✅ تم القبول")

    elif action == "rej":
        cur.execute("DELETE FROM players WHERE user_id=%s", (uid,))
        conn.commit()

        bot.send_message(uid, "❌ تم رفض طلبك، تأكد من صحة معلوماتك وأعد المحاولة")
        bot.send_message(c.message.chat.id, "❌ تم الرفض")

# ====== SEARCH ======
@bot.message_handler(func=lambda m: m.text == "🔍 بحث لاعب")
def search(m):
    if not is_leader(m.chat.id):
        return

    steps[m.chat.id] = "search"
    bot.send_message(m.chat.id, "ارسل الاسم أو الرابط")

# ====== BROADCAST ======
@bot.message_handler(func=lambda m: m.text == "📢 إعلان")
def broadcast(m):
    if not is_leader(m.chat.id):
        return

    steps[m.chat.id] = "broadcast"
    bot.send_message(m.chat.id, "ارسل نص الإعلان")

# ====== ADD LEADER ======
@bot.message_handler(func=lambda m: m.text == "➕ إضافة قائد")
def add_leader(m):
    if m.chat.id != OWNER_ID:
        return

    steps[m.chat.id] = "add_leader"
    bot.send_message(m.chat.id, "ارسل ايدي الشخص")

# ====== DELETE LEADER ======
@bot.message_handler(func=lambda m: m.text == "➖ حذف قائد")
def del_leader(m):
    if m.chat.id != OWNER_ID:
        return

    steps[m.chat.id] = "del_leader"
    bot.send_message(m.chat.id, "ارسل ايدي الشخص")

# ====== STEPS ======
@bot.message_handler(content_types=["text", "photo"])
def all_messages(m):
    uid = m.chat.id
    step = steps.get(uid)

    if not step:
        return

    if step == "search":
        cur.execute("SELECT * FROM players WHERE name ILIKE %s OR link ILIKE %s",
                    (f"%{m.text}%", f"%{m.text}%"))
        res = cur.fetchone()

        if res:
            bot.send_message(uid, f"{res[1]}\n{res[2]}\n{res[3]}")
        else:
            bot.send_message(uid, "❌ ماكو نتيجة")

        steps.pop(uid)
        return

    if step == "broadcast":
        cur.execute("SELECT user_id FROM players WHERE status='accepted'")
        users = cur.fetchall()

        for u in users:
            try:
                bot.send_message(u[0], f"📢 إعلان:\n{m.text}")
            except:
                pass

        bot.send_message(uid, "✅ تم إرسال الإعلان")
        steps.pop(uid)
        return

    if step == "add_leader":
        cur.execute("INSERT INTO leaders(user_id) VALUES(%s) ON CONFLICT DO NOTHING", (m.text,))
        conn.commit()
        bot.send_message(uid, "✅ تم إضافة قائد")
        steps.pop(uid)
        return

    if step == "del_leader":
        cur.execute("DELETE FROM leaders WHERE user_id=%s", (m.text,))
        conn.commit()
        bot.send_message(uid, "❌ تم حذف قائد")
        steps.pop(uid)
        return

    # التسجيل
    if step == "name":
        cache[uid] = {"name": m.text}
        steps[uid] = "link"
        bot.send_message(uid, "ارسل رابط الفيس")
        return

    if step == "link":
        if not is_facebook_link(m.text):
            bot.send_message(uid, "❌ هذا ليس رابط فيس بوك")
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

    if step == "screen" and m.content_type == "photo":
        file_id = m.photo[-1].file_id

        cur.execute("""
        INSERT INTO players(user_id,name,link,serial,status,screen_file_id)
        VALUES(%s,%s,%s,%s,%s,%s)
        """, (
            uid,
            cache[uid]["name"],
            cache[uid]["link"],
            cache[uid]["serial"],
            "pending",
            file_id
        ))

        conn.commit()

        bot.send_message(uid, "✅ تم إرسال طلبك للمراجعة بنجاح")

        steps.pop(uid)
        cache.pop(uid)

# ====== RUN ======
while True:
    try:
        bot.infinity_polling(skip_pending=True)
    except:
        time.sleep(5)
