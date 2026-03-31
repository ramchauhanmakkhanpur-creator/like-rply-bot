import json
import os
import re
import random
import asyncio
from datetime import datetime

from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
from playwright.async_api import async_playwright, Browser

# ====================== CONFIGURATION ======================
TELEGRAM_BOT_TOKEN = '8525631445:AAHERO51zaOvRCbqsvpVi7S94HamddU6bfI'
ADMIN_ID = 8571870755

PLAYWRIGHT_HEADLESS = True  # सर्वर पर चला रहे हैं तो इसे True कर दें
PLAYWRIGHT_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/134.0.0.0 Safari/537.36"

CONFIG_FILE = 'config_bulk.json'

# ====================== RANDOM COMMENTS ======================
RANDOM_COMMENTS = [
    "❤️❤️❤️", "🔥🔥🔥", "Bhai kya scene hai 😍", "Too good yaar 🙌", "Ekdum mast 🔥", 
    "Bhai waah 😎", "Dil khush kar diya 💯", "Kya baat hai 👏👏", "Zabardast bhai 🙌🔥", 
    "Aag laga di yaar 🔥❤️", "Superb 😍😍", "Bilkul sahi hai bhai 💪", "Full support ❤️🔥", 
    "Mast content hai bhai 👌", "Ek number 🔥🔥", "Waah waah waah 🙌", "Bhut badiya yaar 😍", 
    "Lajawab 🔥💯", "Keep it up bhai 👏❤️", "Kya vibe hai yaar 😎🔥",
]

# ====================== GLOBAL ======================
browser: Browser = None
playwright_instance = None
running_users = {}
data_lock = asyncio.Lock() # 🟢 Race condition रोकने ��े लिए Lock

# ====================== DATA STORAGE ======================
user_configs = {}
user_states = {}

if os.path.exists(CONFIG_FILE):
    try:
        with open(CONFIG_FILE) as f:
            user_configs = json.load(f)
    except:
        user_configs = {}

# 🟢 Async File Saving (ताकि बॉट हैंग न हो और बैकग्राउंड में सेव होता रहे)
async def save_data():
    async with data_lock:
        await asyncio.to_thread(_write_json_sync)

def _write_json_sync():
    with open(CONFIG_FILE, 'w') as f:
        json.dump(user_configs, f, indent=4)

def clean_url(url):
    match = re.search(r'(https://www\.instagram\.com/(?:reel|p|tv)/[A-Za-z0-9_\-]+)', url)
    if match:
        result = match.group(1)
        if not result.endswith('/'):
            result += '/'
        return result
    if 'instagram.com' in url:
        result = url.split('?')[0]
        if not result.endswith('/'):
            result += '/'
        return result
    return None

# ====================== PLAYWRIGHT INIT ======================
async def init_playwright():
    global browser, playwright_instance
    if not playwright_instance:
        playwright_instance = await async_playwright().start()
        browser = await playwright_instance.chromium.launch(
            headless=PLAYWRIGHT_HEADLESS,
            args=['--disable-blink-features=AutomationControlled']
        )
        print("✅ Browser launched")

# ====================== BULK LOGIN FUNCTION ======================
async def process_bulk_logins(uid: str, bot, accounts_list: list):
    await bot.send_message(chat_id=int(uid), text=f"⚡ कुल {len(accounts_list)} अकाउंट्स फास्ट लॉगिन शुरू हो रहा है...\n(कृपया प्रतीक्षा करें...)")
    
    if uid not in user_configs:
        user_configs[uid] = {}
    if 'accounts' not in user_configs[uid]:
        user_configs[uid]['accounts'] = []

    success_count = 0
    fail_count = 0

    for acc in accounts_list:
        username, password = acc['username'], acc['password']
        
        # Agar account pehle se list me hai to skip karega
        already_exists = any(a['username'] == username for a in user_configs[uid]['accounts'])
        if already_exists:
            continue

        ctx = await browser.new_context(user_agent=PLAYWRIGHT_USER_AGENT)
        await ctx.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined});")
        page = await ctx.new_page()
        
        login_success = False
        try:
            print(f"🔄 Logging in: {username}")
            await page.goto('https://www.instagram.com/accounts/login/', timeout=40000)
            
            try:
                btn = await page.wait_for_selector('button:has-text("Allow all cookies")', timeout=1000)
                if btn: await btn.click()
            except: pass

            ufield = await page.wait_for_selector('input[name="username"], input[type="text"]', state='visible', timeout=8000)
            if ufield:
                await ufield.click()
                await ufield.type(username, delay=15) 

            pfield = await page.wait_for_selector('input[name="password"], input[type="password"]', state='visible', timeout=5000)
            if pfield:
                await pfield.click()
                await pfield.type(password, delay=15) 
            
            await page.keyboard.press('Enter')
            await asyncio.sleep(6) # Login process wait time

            current_url = page.url
            # 🟢 Checking if login failed (Wrong Pass/Blocked)
            if 'challenge' in current_url or 'checkpoint' in current_url or 'suspended' in current_url or 'login' in current_url:
                login_success = False
            else:
                login_success = True
            
            if login_success:
                storage_state = await ctx.storage_state()
                user_configs[uid]['accounts'].append({
                    'username': username,
                    'session': storage_state
                })
                await save_data() # Async save call
                success_count += 1
                print(f"✅ Login OK: {username}")
            else:
                fail_count += 1
                # 🟢 Notifying user about specific failed account and skipping
                await bot.send_message(chat_id=int(uid), text=f"❌ **लॉगिन विफल (Failed):** `{username}`\n⚠️ कारण: पासवर्ड/यूजरनेम गलत है या अकाउंट ब्लॉक है। (Skipping to next...)")
                print(f"❌ Login Failed: {username}")

        except Exception as e:
            fail_count += 1
            await bot.send_message(chat_id=int(uid), text=f"❌ **Error:** `{username}` को लॉगिन करते समय समस्या आई। (Skipping...)")
            print(f"Error login {username}: {e}")
        finally:
            await ctx.close()
            await asyncio.sleep(2) 

    total_accounts = len(user_configs[uid]['accounts'])
    
    await bot.send_message(
        chat_id=int(uid), 
        text=f"✅ **लॉगिन प्रक्रिया पूरी हो गई!**\n\n🟢 सफल (Success): {success_count}\n🔴 विफल (Failed): {fail_count}\n\n👥 **अब आपके पास कुल {total_accounts} अकाउंट्स हो गए हैं।**\n(बॉट अब इन सभी अकाउंट्स से रील्स पर काम करेगा!)",
        parse_mode='Markdown'
    )

# ====================== REEL ACTIONS ======================
async def perform_reel_actions(username: str, session_state: dict, reel_url: str) -> bool:
    ctx = await browser.new_context(storage_state=session_state, user_agent=PLAYWRIGHT_USER_AGENT)
    await ctx.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined});")
    page = await ctx.new_page()
    
    try:
        print(f"\n[{username}] 📱 Reel खोल रहे हैं...")
        await page.goto(reel_url, timeout=40000)
        await page.wait_for_load_state('domcontentloaded')
        
        print(f"[{username}] 👁️ Reel को 20 सेकंड Watch कर रहे हैं...")
        await asyncio.sleep(20) 
        
        print(f"[{username}] ❤️ Like कर रहे हैं...")
        try:
            like_btn = page.locator('svg[aria-label="Like"]').first
            unlike_btn = page.locator('svg[aria-label="Unlike"]').first
            if not await unlike_btn.is_visible(timeout=1000):
                if await like_btn.is_visible(timeout=1000):
                    await like_btn.click(force=True)
                else:
                    await page.keyboard.press('l')
        except: pass

        print(f"[{username}] 🔖 Save कर रहे हैं...")
        try:
            save_btn = page.locator('svg[aria-label="Save"]').first
            remove_btn = page.locator('svg[aria-label="Remove"]').first
            if not await remove_btn.is_visible(timeout=1000):
                if await save_btn.is_visible(timeout=1000):
                    await save_btn.click(force=True)
        except: pass

        print(f"[{username}] 💬 Comment Icon click कर रहे हैं...")
        try:
            comment_btn = page.locator('svg[aria-label="Comment"]').first
            if await comment_btn.is_visible(timeout=3000):
                await comment_btn.click()
        except: pass

        await asyncio.sleep(random.uniform(3.5, 4.5))
        comment_box = None
        selectors = [
            'textarea[aria-label*="Add a comment"]', 'textarea[placeholder*="Add a comment"]',
            'textarea[aria-label*="comment" i]', 'div[aria-label*="Add a comment"][role="textbox"]', 'form textarea'
        ]

        for sel in selectors:
            try:
                box = page.locator(sel).last
                if await box.is_visible(timeout=2000):
                    comment_box = box
                    break
            except: continue

        if not comment_box:
            try:
                fallback_loc = page.get_by_placeholder(re.compile(r'Add a comment', re.IGNORECASE)).last
                if await fallback_loc.is_visible(timeout=2000): comment_box = fallback_loc
            except: pass

        if comment_box:
            try:
                await comment_box.scroll_into_view_if_needed()
                await comment_box.hover()
                await comment_box.click(force=True, delay=200)
                await asyncio.sleep(random.uniform(1.5, 2.0))
                comment_text = random.choice(RANDOM_COMMENTS)
                print(f"[{username}] ⌨️ Type kar rahe hain: '{comment_text}'")
                await page.keyboard.type(comment_text, delay=random.uniform(30, 60))
                await asyncio.sleep(random.uniform(1, 1.5))
                await page.keyboard.press('Enter')
                print(f"[{username}] ✅ Comment post ho gaya (Single Time)!")
                await asyncio.sleep(random.uniform(2, 3))
            except Exception as e:
                print(f"[{username}] ❌ Comment typing error: {e}")
        else:
            print(f'[{username}] ❌ "Add a comment..." box nahi mila!')

        return True
    except Exception as e:
        print(f"❌ [{username}] Action failed: {e}")
        return False
    finally:
        await ctx.close()

# ====================== SMART BACKGROUND LOOP ======================
async def action_loop(bot):
    while True:
        try:
            for uid, is_running in list(running_users.items()):
                if not is_running: 
                    continue
                
                if uid not in user_configs:
                    running_users[uid] = False
                    continue

                posts = user_configs[uid].get('posts', [])
                accounts = user_configs[uid].get('accounts', []) 
                
                if 'history' not in user_configs[uid]:
                    user_configs[uid]['history'] = {}

                if not accounts: 
                    running_users[uid] = False
                    continue

                if not posts:
                    continue

                current_reel = posts[0] 

                if current_reel not in user_configs[uid]['history']:
                    user_configs[uid]['history'][current_reel] = []

                # Naye accounts jinki history nahi hai, wo automatically is pending me aa jayenge
                pending_accounts = [acc for acc in accounts if acc['username'] not in user_configs[uid]['history'][current_reel]]

                if not pending_accounts:
                    user_configs[uid]['posts'].pop(0) 
                    await save_data() # Async Save
                    
                    try:
                        await bot.send_message(
                            chat_id=int(uid),
                            text=f"🎉 **बधाई हो!** आपकी सभी लॉगिन ID से इस रील पर काम पूरा हो गया है:\n🔗 {current_reel}\n\nनई रील डालने के लिए ➕ **Add Reel** दबाएं।",
                            parse_mode='Markdown'
                        )
                    except: pass
                    continue 

                acc = pending_accounts[0]
                username = acc['username']
                session = acc['session']

                if len(user_configs[uid]['history'][current_reel]) == 0:
                    try:
                        await bot.send_message(chat_id=int(uid), text=f"🚀 रील प्रोसेस शुरू!\n🔗 {current_reel}\n\n⚡ Fast Mode: Like, Save, Single Comment (20s Watch)")
                    except: pass

                success = await perform_reel_actions(username, session, current_reel)
                
                user_configs[uid]['history'][current_reel].append(username)
                await save_data() # Async save after action

                if success:
                    try:
                        await bot.send_message(chat_id=int(uid), text=f"✅ अकाउंट: **{username}**\n⚡ काम हो गया (20s Watch, Like, Save, Single Comment)।", parse_mode='Markdown')
                    except: pass
                
                await asyncio.sleep(random.uniform(3, 5))

        except Exception as e:
            print(f"Loop error prevented: {e}")

        await asyncio.sleep(5)

# ====================== TELEGRAM HANDLERS ======================
async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = str(update.effective_user.id)
    if uid not in user_configs:
        user_configs[uid] = {'accounts': [], 'posts': [], 'history': {}}
        await save_data()
        
    await update.message.reply_text(
        "👋 **स्वागत है!**\n\nसबसे पहले अपना Email Verify करें। कृपया अपना **Email Address** टाइप करके भेजें:",
        parse_mode='Markdown'
    )
    user_states[uid] = 'waiting_email'

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = str(update.effective_user.id)
    
    if uid not in user_configs:
        user_configs[uid] = {'accounts': [], 'posts': [], 'history': {}}
        await save_data()

    state = user_states.get(uid)
    if not update.message or not update.message.text: return
    text = update.message.text.strip()

    if state == 'waiting_email':
        user_configs[uid]['email'] = text
        await save_data()
        msg = (
            "✅ Email Verify हो गया!\n\n"
            "अब अपने Instagram Accounts डालें। (आप कितने भी अकाउंट डाल सकते हैं)\n\n"
            "**इस फॉर्मेट में भेजें:**\n"
            "`username,password`\n"
            "`username2,password4`\n"
            "(हर अकाउंट नई लाइन में)"
        )
        await update.message.reply_text(msg, parse_mode='Markdown')
        user_states[uid] = 'waiting_bulk_accounts'
        return

    if state == 'waiting_bulk_accounts':
        lines = text.split('\n')
        acc_list = []
        for line in lines:
            if ',' in line or ':' in line:
                parts = line.replace(':', ',').split(',')
                if len(parts) >= 2:
                    acc_list.append({'username': parts[0].strip(), 'password': parts[1].strip()})
        
        if acc_list:
            user_states[uid] = None
            asyncio.create_task(process_bulk_logins(uid, context.bot, acc_list))
        else:
            await update.message.reply_text("❌ गलत फॉर्मेट! कृपया `username,password` के फॉर्मेट में भेजें।")
        return

    if state == 'waiting_reel':
        url = clean_url(text)
        if url:
            if 'posts' not in user_configs[uid]: user_configs[uid]['posts'] = []
            if 'history' not in user_configs[uid]: user_configs[uid]['history'] = {}

            if 'history' in user_configs[uid] and url in user_configs[uid]['history']:
                user_configs[uid]['history'][url] = []
                
            if url not in user_configs[uid]['posts']:
                user_configs[uid]['posts'].append(url)
                
            await save_data()
            running_users[uid] = True
            
            await update.message.reply_text("✅ Reel कतार (Queue) में जुड़ गई है!\n\n🔄 **बॉट ने ऑटोमैटिक काम शुरू कर दिया है!**", reply_markup=menu_keyboard, parse_mode='Markdown')
        else:
            await update.message.reply_text("❌ Invalid link! Instagram reel URL भेजें।")
        user_states[uid] = None
        return

    if state == 'waiting_delete':
        try:
            idx = int(text) - 1
            posts = user_configs[uid].get('posts', [])
            if 0 <= idx < len(posts):
                deleted_url = posts.pop(idx)
                await save_data()
                await update.message.reply_text(f"🗑️ रील सफलतापूर्वक हटा दी गई:\n{deleted_url}", reply_markup=menu_keyboard)
            else:
                await update.message.reply_text("❌ गलत नंबर।", reply_markup=menu_keyboard)
        except:
            await update.message.reply_text("❌ कृपया सही नंबर भेजें।", reply_markup=menu_keyboard)
        user_states[uid] = None
        return

    # ================== MAIN MENU COMMANDS ==================
    if text == "🚀 Start":
        accounts = user_configs.get(uid, {}).get('accounts', [])
        posts = user_configs.get(uid, {}).get('posts', [])
        
        if not accounts:
            return await update.message.reply_text("⚠️ आपके पास कोई लॉगिन अकाउंट नहीं है! पहले 🔑 **Add Accounts** दबाएं।")
        if not posts:
            return await update.message.reply_text("📭 कोई रील नहीं है! पहले ➕ **Add Reel** दबाएं।")
            
        running_users[uid] = True
        await update.message.reply_text(f"🚀 **बॉट शुरू हो गया!**\nTotal Accounts: {len(accounts)}\nTotal Reels Queue: {len(posts)}\n(बॉट लगातार काम कर रहा है)", reply_markup=menu_keyboard, parse_mode='Markdown')

    elif text == "🛑 Stop":
        running_users[uid] = False
        await update.message.reply_text("🛑 **बॉट रोक दिया गया है!**", reply_markup=menu_keyboard, parse_mode='Markdown')

    elif text == "🔑 Add Accounts":
        user_states[uid] = 'waiting_bulk_accounts'
        await update.message.reply_text("अकाउंट्स `username,password` की लिस्ट भेजें (पुरानी ID सुरक्षित रहेंगी):", parse_mode='Markdown')

    elif text == "➕ Add Reel":
        user_states[uid] = 'waiting_reel'
        await update.message.reply_text("📎 Instagram Reel का लिंक भेजें:", reply_markup=menu_keyboard)

    elif text == "🗑️ Delete Reel":
        posts = user_configs.get(uid, {}).get('posts', [])
        if not posts:
            return await update.message.reply_text("📭 डिलीट करने के लिए कोई रील नहीं है।", reply_markup=menu_keyboard)
        msg = "📋 **आपकी कतार (Queue) में मौजूद रील्स:**\n\n"
        for i, p in enumerate(posts, 1):
            short = p.replace('https://www.instagram.com/', '')
            msg += f"{i}. {short}\n"
        msg += "\n🗑️ जिस रील को हटाना है, उसका **नंबर** टाइप करके भेजें:"
        await update.message.reply_text(msg, reply_markup=menu_keyboard, parse_mode='Markdown')
        user_states[uid] = 'waiting_delete'

    elif text == "👥 Total Accounts":
        accounts = user_configs.get(uid, {}).get('accounts', [])
        if not accounts:
            return await update.message.reply_text("📭 अभी तक कोई अकाउंट नहीं जोड़ा गया है।", reply_markup=menu_keyboard)
        
        total = len(accounts)
        msg = f"👥 **कुल सेव किए गए अकाउंट्स: {total}**\n\n"
        
        usernames = [acc['username'] for acc in accounts]
        if total <= 100:
            msg += "📋 **अकाउंट्स की लिस्ट:**\n" + ", ".join(usernames)
        else:
            msg += f"📋 **लिस्ट (पहले 100 अकाउंट्स):**\n" + ", ".join(usernames[:100])
            msg += f"\n\n...और {total - 100} अन्य अकाउंट्स।"
            
        await update.message.reply_text(msg, reply_markup=menu_keyboard, parse_mode='Markdown')

    elif text == "📊 Status":
        accounts = len(user_configs.get(uid, {}).get('accounts', []))
        email = user_configs.get(uid, {}).get('email', 'Not Verified')
        await update.message.reply_text(f"📊 **स्टेटस:**\n\n📧 Email: {email}\n👥 Total Logged In IDs: {accounts}", reply_markup=menu_keyboard, parse_mode='Markdown')

    else:
        if state is None:
            await update.message.reply_text("नीचे दिए गए बटन का इस्तेमाल करें 👇", reply_markup=menu_keyboard)

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    print(f"Telegram Error: {context.error}")

menu_keyboard = ReplyKeyboardMarkup([
    ["🚀 Start", "🛑 Stop"],
    ["➕ Add Reel", "🗑️ Delete Reel"],
    ["🔑 Add Accounts", "👥 Total Accounts"],
    ["📊 Status"]
], resize_keyboard=True)

if __name__ == '__main__':
    app = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_error_handler(error_handler)

    async def post_init(application):
        await init_playwright()
        asyncio.create_task(action_loop(application.bot))

    app.post_init = post_init
    print("🚀 Bot Started Successfully!")
    app.run_polling()
