import os, json, asyncio, threading, datetime, requests, re
from pathlib import Path
from flask import Flask, request
import pytz
from bs4 import BeautifulSoup
from fpdf import FPDF
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes, MessageHandler, filters
from telegram.constants import ParseMode
from apscheduler.schedulers.background import BackgroundScheduler

# ===== AAPKA SETTING =====
BOT_TOKEN = os.getenv("BOT_TOKEN","").strip()
CHANNEL_ID = "@AllGovernmentExamAlerts"
CHANNEL_LINK = "https://t.me/AllGovernmentExamAlerts"
GROUP_ID = os.getenv("GROUP_ID","").strip()

POST_MODE = os.getenv("POST_MODE","both") # both / bot_only / channel_only
FORCE_JOIN = True # True = Channel join karna padega
IST = pytz.timezone('Asia/Kolkata')

PERSIST_DIR = Path("/data") if Path("/data").exists() else Path(".")
SUBS_FILE = PERSIST_DIR / "subs.json"
SEEN_FILE = PERSIST_DIR / "seen_jobs.json"

def load_json(p,d):
    if p.exists():
        try: return json.loads(p.read_text(encoding="utf-8"))
        except: return d
    return d
def save_json(p,d): p.write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")

loop = asyncio.new_event_loop()
def start_loop():
    asyncio.set_event_loop(loop)
    loop.run_forever()
threading.Thread(target=start_loop, daemon=True).start()
application = Application.builder().token(BOT_TOKEN).build()

# ===== ALL EXAMS OFFICIAL SOURCES - 30+ =====
SOURCES = [
    {"name": "UPSC", "url": "https://upsc.gov.in/whats-new", "type": "upsc"},
    {"name": "SSC", "url": "https://ssc.gov.in/", "type": "ssc"},
    {"name": "RRB Railway", "url": "https://www.rrbcdg.gov.in/", "type": "railway"},
    {"name": "IBPS Bank", "url": "https://www.ibps.in/", "type": "banking"},
    {"name": "SBI Bank", "url": "https://bank.sbi/careers", "type": "banking"},
    {"name": "Indian Army", "url": "https://joinindianarmy.nic.in/", "type": "defence"},
    {"name": "CSBC Bihar Police", "url": "https://csbc.bih.nic.in/", "type": "police"},
    {"name": "BPSC Bihar", "url": "https://bpsc.bih.nic.in/", "type": "bpsc"},
    {"name": "BSSC Bihar", "url": "https://bssc.bihar.gov.in/", "type": "bihar"},
    {"name": "UPPSC", "url": "https://uppsc.up.nic.in/", "type": "state_psc"},
    {"name": "CTET", "url": "https://ctet.nic.in/", "type": "teaching"},
    {"name": "KVS", "url": "https://kvsangathan.nic.in/", "type": "teaching"},
]

# ===== FORCE JOIN CHECK =====
async def is_joined(user_id, bot):
    try:
        m = await bot.get_chat_member(chat_id=CHANNEL_ID, user_id=user_id)
        return m.status in ["member","administrator","creator"]
    except: return False

async def force_join_message(update: Update):
    kb = [[InlineKeyboardButton("📢 Channel Join Karo - @AllGovernmentExamAlerts", url=CHANNEL_LINK)],
          [InlineKeyboardButton("✅ Join Karke Aaya - Check Karo", callback_data="check_join")]]
    await update.message.reply_text(f"⚠️ **Channel Join Karo Boss!**\n\nAapne {CHANNEL_ID} join nahi kiya! Bot use karne ke liye pehle join karo fir ✅ dabao!", reply_markup=InlineKeyboardMarkup(kb), parse_mode=ParseMode.MARKDOWN)

# ===== ANALYSIS + PDF =====
def analyze_job(title):
    t=title.lower()
    qual="Graduation"; 
    if "10th" in t or "matric" in t: qual="10th Pass"
    elif "12th" in t: qual="12th Pass"
    elif "iti" in t: qual="ITI Pass"
    age="18-28 Years"; 
    if "police" in t: age="18-25 (Bihar Police), 18-28 (SSC GD)"
    elif "upsc" in t: age="21-32 Years"
    sel="Written + Physical/Interview"
    if "police" in t: sel="Written > Physical (Running, High Jump) > Medical > Merit"
    elif "cgl" in t: sel="Tier-1 > Tier-2 > Tier-3 > DV"
    elif "railway" in t: sel="CBT > PET > Document Verification"
    return {"qual":qual,"age":age,"selection":sel,"salary":"Rs. 21,700 - 1,42,400 + DA, HRA"}

def create_pdf(title, url, analysis):
    path=f"/tmp/{re.sub(r'[^a-zA-Z0-9]','_',title)[:25]}.pdf"
    pdf=FPDF(); pdf.add_page()
    pdf.set_font("Arial","B",16); pdf.cell(0,10,"Sarkari Exam Alert - Full Analysis",align="C",new_x="LMARGIN",new_y="NEXT")
    pdf.set_font("Arial","",11); pdf.multi_cell(0,7,f"Post: {title}\nOfficial: {url}\nDate: {datetime.datetime.now(IST).strftime('%d-%m-%Y %H:%M')}\n\nQualification: {analysis['qual']}\nAge: {analysis['age']}\nSelection: {analysis['selection']}\nSalary: {analysis['salary']}\n\nNote: Final details official PDF me dekho.\n@AllGovernmentExamAlerts | @SarkariExamAlertIndiaBot")
    pdf.output(path); return path

async def check_and_post():
    seen=load_json(SEEN_FILE,[]); subs=load_json(SUBS_FILE,[])
    for src in SOURCES:
        try:
            r=requests.get(src['url'], headers={"User-Agent":"Mozilla/5.0"}, timeout=15)
            soup=BeautifulSoup(r.text,'lxml')
            links=soup.find_all('a', string=re.compile(r'(Notice|Advt|Vacancy|Recruitment|Result|Admit|Corrigendum)', re.I))
            for a in links[:4]:
                title=a.get_text(strip=True); href=a.get('href')
                if not href: continue
                if not href.startswith('http'): href=src['url'].rstrip('/')+'/'+href.lstrip('/')
                if href in seen: continue
                analysis=analyze_job(title); pdf_path=create_pdf(title, href, analysis)
                caption=f"🚨 **NEW {src['type'].upper()} ALERT!**\n\n📌 **{title}**\n🏢 **{src['name']}**\n\n📊 **Full Details:**\n🎓 **Qualification:** {analysis['qual']}\n🎂 **Age:** {analysis['age']}\n📝 **Selection:** {analysis['selection']}\n💰 **Salary:** {analysis['salary']}\n\n📥 **Niche 2 PDF hai:**\n1. Official Notification (Link)\n2. Analysis PDF (Bot banayega)\n\n⏰ {datetime.datetime.now(IST).strftime('%d-%m-%Y %I:%M %p')}"
                kb=[[InlineKeyboardButton("📄 Official PDF - Official Site", url=href)],
                    [InlineKeyboardButton("🔍 Full Syllabus + Details", callback_data=f"detail_{src['type']}")]]
                if POST_MODE in ["both","channel_only"]:
                    try:
                        with open(pdf_path,"rb") as f:
                            await application.bot.send_document(chat_id=CHANNEL_ID, document=f, caption=caption, reply_markup=InlineKeyboardMarkup(kb), parse_mode=ParseMode.MARKDOWN)
                    except: 
                        try: await application.bot.send_message(chat_id=CHANNEL_ID, text=caption, reply_markup=InlineKeyboardMarkup(kb), parse_mode=ParseMode.MARKDOWN)
                        except: pass
                if POST_MODE in ["both","bot_only"]:
                    for uid in subs[-50:]:
                        try: await application.bot.send_message(chat_id=uid, text=caption, reply_markup=InlineKeyboardMarkup(kb), parse_mode=ParseMode.MARKDOWN)
                        except: pass
                seen.append(href); save_json(SEEN_FILE,seen)
        except Exception as e: print(f"Fail {src['name']} {e}")

# ===== COLOURFUL BUTTON - PATLIPUTRA JAISA =====
def main_keyboard():
    kb=[
        [KeyboardButton("🔍 Search Job by City/Name")],
        [KeyboardButton("🎓 Check Your Result"), KeyboardButton("❓ How to Apply")],
        [KeyboardButton("🏆 Latest Vacancy 2026")],
        [KeyboardButton("📄 Download Admit Card")],
        [KeyboardButton("📥 Download Full Notification PDF")],
        [KeyboardButton("🔔 Subscribe to Daily Alert")],
        [KeyboardButton("🆕 Published Today Papers/Jobs")],
        [KeyboardButton("🧮 Age / Eligibility Calculator")],
        [KeyboardButton("📤 Share Sarkari Bot"), KeyboardButton("💬 Help & Support")],
    ]
    return ReplyKeyboardMarkup(kb, resize_keyboard=True)

async def start(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if FORCE_JOIN and not await is_joined(update.effective_user.id, ctx.bot):
        await force_join_message(update); return
    txt=f"👋 **Hello, {update.effective_user.first_name}!**\n\n**Welcome to Sarkari Exam Alert India Bot!**\n\nYe bot aapko **All Govt Exam, Vacancy, Admit Card, Result, Answer Key, Syllabus** ka turant alert dega.\n\nJaise hi koi notification ayega - Turant Analysis karke PDF + Full Details yahan aur {CHANNEL_ID} pe aa jayega.\n\n👇 **Select an option below to get started!**"
    await update.message.reply_text(txt, reply_markup=main_keyboard(), parse_mode=ParseMode.MARKDOWN)

async def handle_text(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    if FORCE_JOIN and not await is_joined(update.effective_user.id, ctx.bot):
        await force_join_message(update); return
    t=update.message.text
    if "Search Job" in t:
        kb=[[InlineKeyboardButton("🔥 SSC", callback_data="cat_SSC"), InlineKeyboardButton("🚂 Railway", callback_data="cat_Railway")],
            [InlineKeyboardButton("🎓 UPSC", callback_data="cat_UPSC"), InlineKeyboardButton("🏦 Banking", callback_data="cat_Banking")],
            [InlineKeyboardButton("👮 Bihar Police", callback_data="cat_Police"), InlineKeyboardButton("📚 Teaching", callback_data="cat_Teaching")],
            [InlineKeyboardButton("🏛️ BPSC/BSSC", callback_data="cat_BPSC")]]
        await update.message.reply_text("🏆 **Category chuno - All Details ke saath:**", reply_markup=InlineKeyboardMarkup(kb))
    elif "Latest Vacancy" in t or "Published Today" in t:
        await update.message.reply_text("🔍 Abhi live check kar raha hu... 5 sec ruko!"); await check_and_post()
        await update.message.reply_text(f"✅ Check ho gaya! Naya job {CHANNEL_ID} pe post ho gaya. Wahan jao!")
    elif "Admit Card" in t:
        kb=[[InlineKeyboardButton("🎫 SSC Admit Card", url="https://ssc.gov.in"), InlineKeyboardButton("🎫 Railway Admit Card", url="https://rrbcdg.gov.in")],
            [InlineKeyboardButton("🎫 Bihar Police Admit Card", url="https://csbc.bih.nic.in")]]
        await update.message.reply_text("📄 **All Admit Card Official Links - Colourful:**", reply_markup=InlineKeyboardMarkup(kb))
    elif "Notification PDF" in t:
        await update.message.reply_text("📥 **Official + Analysis PDF kaise milega?**\n\nHar job ke saath 2 button ayega:\n1. 📄 Official PDF (Official Site)\n2. 📊 Full Analysis PDF (Qualification, Age, Salary, Selection, Syllabus)\n\nYehi legal tarika hai!", parse_mode=ParseMode.MARKDOWN)
    elif "Subscribe" in t:
        subs=load_json(SUBS_FILE,[]); uid=update.effective_user.id
        if uid not in subs: subs.append(uid); save_json(SUBS_FILE,subs)
        await update.message.reply_text("🔔 **Subscribed!**\n\nAb har naya Vacancy, Admit Card, Result ka turant DM + Channel pe alert ayega!\n\nMode: Both Bot & Channel")
    elif "Result" in t:
        kb=[[InlineKeyboardButton("🏆 SSC Result", url="https://ssc.gov.in"), InlineKeyboardButton("🏆 Railway Result", url="https://rrbcdg.gov.in")],
            [InlineKeyboardButton("🏆 BPSC Result", url="https://bpsc.bih.nic.in")]]
        await update.message.reply_text("🎓 **All Result Links:**", reply_markup=InlineKeyboardMarkup(kb))
    else:
        await update.message.reply_text("👇 Menu se chuno Boss:", reply_markup=main_keyboard())

async def handle_cb(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    q=update.callback_query; await q.answer(); data=q.data
    if data=="check_join":
        if await is_joined(q.from_user.id, ctx.bot):
            await q.message.delete(); await q.message.reply_text("✅ **Join Ho Gaya! Ab full access!**", reply_markup=main_keyboard(), parse_mode=ParseMode.MARKDOWN)
        else: await q.answer("❌ Abhi join nahi kiya! Pehle join karo!", show_alert=True)
        return
    if data.startswith("cat_"):
        cat=data.replace("cat_",""); await q.message.reply_text(f"🏆 **{cat} ke All Jobs:**\n\n📊 Analysis: Qualification, Age, Salary, Selection sab PDF me\n\nNiche official link hai:", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton(f"📄 {cat} Official + Analysis PDF", url="https://ssc.gov.in")]]), parse_mode=ParseMode.MARKDOWN)
    if data.startswith("detail_"):
        await q.message.reply_text("📊 **Full Details + Syllabus:**\n\n🎓 Qualification, 🎂 Age, 📝 Selection, 💰 Salary, 📚 Syllabus - sab Analysis PDF me de diya gaya hai! Official site pe jao!", parse_mode=ParseMode.MARKDOWN)

application.add_handler(CommandHandler("start", start))
application.add_handler(CallbackQueryHandler(handle_cb))
application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

flask_app=Flask(__name__)
@flask_app.route('/')
def home(): return "SarkariExamAlertIndiaBot - All Exam Live"
@flask_app.route('/webhook', methods=['POST'])
def webhook():
    try:
        data=request.get_json(force=True); update=Update.de_json(data, application.bot)
        asyncio.run_coroutine_threadsafe(application.process_update(update), loop)
    except Exception as e: print(e)
    return "ok"

async def init_bot():
    await application.initialize(); await application.start()
    hn=os.getenv("RENDER_EXTERNAL_HOSTNAME")
    if hn:
        url=f"https://{hn}/webhook"; await application.bot.delete_webhook(drop_pending_updates=True); await application.bot.set_webhook(url=url)
        print(f"Webhook {url}")
asyncio.run_coroutine_threadsafe(init_bot(), loop)

scheduler=BackgroundScheduler(timezone=IST)
scheduler.add_job(lambda: asyncio.run_coroutine_threadsafe(check_and_post(), loop), 'interval', minutes=5, id='all_exam_checker')
scheduler.start()
asyncio.run_coroutine_threadsafe(check_and_post(), loop)

if __name__=='__main__': flask_app.run(host="0.0.0.0", port=int(os.environ.get("PORT",10000)))