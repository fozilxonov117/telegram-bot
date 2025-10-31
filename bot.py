import telebot
import gspread
from datetime import datetime
from oauth2client.service_account import ServiceAccountCredentials
from telebot import types
import json
import os
from datetime import datetime, timedelta, timezone


# === 🔐 1. TOKENLAR VA KALITLARNI ENVIRONMENT'DAN OLYAPMIZ ===
BOT_TOKEN = os.environ.get("BOT_TOKEN")  # Render environment'dan olinadi
GOOGLE_CREDS = os.environ.get("GOOGLE_CREDS")  # service_account.json matni

if not BOT_TOKEN or not GOOGLE_CREDS:
    print("❌ Xato: BOT_TOKEN yoki GOOGLE_CREDS topilmadi. Render environment'ni tekshiring.")
    exit()

# === 🔐 2. Google Sheets ulanmasi (Render uchun mos shakl) ===
SCOPE = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
creds_dict = json.loads(GOOGLE_CREDS)
CREDS = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, SCOPE)
client = gspread.authorize(CREDS)
sheet = client.open("Tikuvchilar Hisoboti").worksheet("Kunlik hisobot")

# === 3. Ma'lumotlar bazasi ===
EMPLOYEES = {
    "1656876161": "Ziyoda",
    "7643816702": "Muhayyo",
    "6158665118": "Nigina",
    "1355803384": "Durdona",
    "836724731": "Zoirxon",
    "5857129558": "Usmon",
}

TIKUVCHI_PRICES = {
    "nimcha": 16000,
    "chok": 5000,
    "averlok fut/walvar": 4000,
    "pol-zamok": 3000,
    "rashma": 700,
    "kant": 1000
}

QADOQ_PRICES = {
    "dvoyka": 1500,
    "troyka": 2000,
    "troyka-sintifon": 2500
}

STATE = {}
bot = telebot.TeleBot(BOT_TOKEN)

# === 4. Klaviaturalar ===
def role_keyboard():
    kb = types.InlineKeyboardMarkup()
    kb.add(
        types.InlineKeyboardButton("🧵 Tikuvchi", callback_data="role:tikuvchi"),
        types.InlineKeyboardButton("📦 Qadoqlovchi", callback_data="role:qadoqlovchi")
    )
    return kb

def type_keyboard(role):
    kb = types.InlineKeyboardMarkup()
    items = TIKUVCHI_PRICES if role == "tikuvchi" else QADOQ_PRICES
    for k in items.keys():
        kb.add(types.InlineKeyboardButton(k, callback_data=f"type:{k}"))
    kb.add(types.InlineKeyboardButton("🔙 Rolga qaytish", callback_data="back:role"))
    return kb

def confirm_keyboard():
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("✅ To‘g‘ri", callback_data="confirm:yes"),
           types.InlineKeyboardButton("❌ Bekor qilish", callback_data="confirm:no"))
    kb.add(types.InlineKeyboardButton("🔙 Kiyim turiga qaytish", callback_data="back:type"))
    return kb

def reset_state(uid):
    STATE[uid] = {"stage": "role", "role": None, "type": None, "count": None, "price": None}

# === 5. Google Sheets yordamchi funksiyalar ===
def can_submit_today(uid):
    today = datetime.now().strftime("%Y-%m-%d")
    records = sheet.get_all_records()
    return sum(1 for r in records if str(r.get("Telegram ID")) == uid and str(r.get("Sana")) == today) < 2


def append_row(uid, name, role, product, count, price):
    # 🕒 Toshkent vaqti (UTC+5)
    tashkent_tz = timezone(timedelta(hours=5))
    today = datetime.now(tashkent_tz).strftime("%Y-%m-%d")
    time_now = datetime.now(tashkent_tz).strftime("%H:%M:%S")

    total = count * price
    row = [today, name, uid, role.capitalize(), product, count, price, total, time_now]
    sheet.append_row(row)


# === 6. Bot komandalar va handlerlar ===
@bot.message_handler(commands=['start'])
def start(msg):
    uid = str(msg.chat.id)
    if uid not in EMPLOYEES:
        bot.send_message(uid, "⚠️ Siz ro‘yxatda yo‘qsiz. Admin bilan bog‘laning.")
        return
    reset_state(uid)
    bot.send_message(uid, "👋 Salom! Rolingizni tanlang:", reply_markup=types.ReplyKeyboardRemove())
    bot.send_message(uid, "Tanlang:", reply_markup=role_keyboard())

@bot.callback_query_handler(func=lambda c: c.data.startswith("role:"))
def choose_role(call):
    uid = str(call.message.chat.id)
    role = call.data.split(":")[1]
    STATE[uid] = {"stage": "type", "role": role, "type": None, "count": None, "price": None}
    bot.edit_message_text(f"🔽 {role.capitalize()} uchun kiyim turini tanlang:",
                          call.message.chat.id, call.message.id, reply_markup=type_keyboard(role))

@bot.callback_query_handler(func=lambda c: c.data.startswith("type:"))
def choose_type(call):
    uid = str(call.message.chat.id)
    role = STATE[uid]["role"]
    product = call.data.split(":")[1]
    price = (TIKUVCHI_PRICES if role == "tikuvchi" else QADOQ_PRICES)[product]
    STATE[uid].update({"type": product, "price": price, "stage": "count"})
    kb = types.InlineKeyboardMarkup()
    kb.add(types.InlineKeyboardButton("🔙 Orqaga", callback_data="back:type"))
    bot.edit_message_text(
        f"✍️ {product} uchun nechta dona kiriting.\n💵 1 dona: {price:,} so‘m",
        call.message.chat.id, call.message.id, reply_markup=kb
    )

@bot.callback_query_handler(func=lambda c: c.data.startswith("back:"))
def go_back(call):
    uid = str(call.message.chat.id)
    action = call.data.split(":")[1]
    if action == "role":
        reset_state(uid)
        bot.edit_message_text("Rolni qaytadan tanlang:", call.message.chat.id,
                              call.message.id, reply_markup=role_keyboard())
    elif action == "type":
        role = STATE[uid]["role"]
        STATE[uid].update({"stage": "type", "type": None})
        bot.edit_message_text(f"{role.capitalize()} uchun kiyim turini tanlang:",
                              call.message.chat.id, call.message.id, reply_markup=type_keyboard(role))

@bot.callback_query_handler(func=lambda c: c.data.startswith("confirm:"))
def confirm(call):
    uid = str(call.message.chat.id)
    ans = call.data.split(":")[1]
    st = STATE[uid]
    if ans == "no":
        st["count"] = None
        bot.edit_message_text(f"❌ Bekor qilindi. {st['type']} uchun sonni qayta kiriting.",
                              call.message.chat.id, call.message.id)
        return
    if not can_submit_today(uid):
        bot.edit_message_text("⚠️ Bugun 2 ta hisobot topshirdingiz.", call.message.chat.id, call.message.id)
        reset_state(uid)
        return
    name = EMPLOYEES[uid]
    append_row(uid, name, st["role"], st["type"], st["count"], st["price"])
    total = st["count"] * st["price"]
    bot.edit_message_text(
        f"✅ Qabul qilindi!\n👤 {name}\n🧩 Rol: {st['role'].capitalize()}\n"
        f"👕 Tur: {st['type']}\n🔢 Soni: {st['count']}\n💵 Jami: {total:,} so‘m",
        call.message.chat.id, call.message.id)
    reset_state(uid)

@bot.message_handler(func=lambda m: m.text.isdigit())
def input_count(msg):
    uid = str(msg.chat.id)
    if uid not in EMPLOYEES or uid not in STATE:
        bot.send_message(uid, "⚠️ Avval /start bosing.")
        return
    st = STATE[uid]
    if st.get("stage") != "count":
        bot.send_message(uid, "Avval kiyim turini tanlang.")
        return
    count = int(msg.text)
    st["count"] = count
    total = count * st["price"]
    text = (f"🔎 Tekshiruv:\nRol: {st['role'].capitalize()}\nKiyim turi: {st['type']}\n"
            f"Soni: {count}\n1 dona: {st['price']:,} so‘m\nJami: {total:,} so‘m\nTasdiqlaysizmi?")
    bot.send_message(uid, text, reply_markup=confirm_keyboard())

@bot.message_handler(func=lambda m: True)
def fallback(msg):
    bot.send_message(msg.chat.id, "ℹ️ Avval /start yuboring.")

print("🤖 Bot Render.com’da ishga tushdi...")
bot.infinity_polling(timeout=10, long_polling_timeout=5)
