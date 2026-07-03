import os
import sqlite3
import logging
from datetime import datetime, timedelta
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

# ===== SETUP =====
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Environment variables
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
RAILWAY_URL = os.getenv("RAILWAY_PUBLIC_DOMAIN", "")
PORT = int(os.getenv("PORT", 8080))

# Database path (Railway persistent storage)
DB_PATH = "/data/memories.db"

# ===== DATABASE FUNCTIONS =====
def init_db():
    """Create database table if it doesn't exist"""
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute('''CREATE TABLE IF NOT EXISTS memories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER,
            user_id INTEGER,
            username TEXT,
            message TEXT,
            saved_date TEXT,
            original_date TEXT
        )''')
        conn.commit()
        conn.close()
        logger.info("✅ Database initialized successfully!")
        return True
    except Exception as e:
        logger.error(f"❌ Database init error: {e}")
        return False

def save_memory(chat_id, user_id, username, message):
    """Save a message to the database"""
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        now = datetime.now().isoformat()
        c.execute(
            "INSERT INTO memories (chat_id, user_id, username, message, saved_date, original_date) VALUES (?,?,?,?,?,?)",
            (chat_id, user_id, username, message, now, now)
        )
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        logger.error(f"❌ Save error: {e}")
        return False

def get_year_ago_memories(chat_id):
    """Get memories from exactly 1 year ago"""
    try:
        year_ago = (datetime.now() - timedelta(days=365)).strftime("%Y-%m-%d")
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute(
            "SELECT username, message, saved_date FROM memories WHERE chat_id=? AND date(saved_date)=?",
            (chat_id, year_ago)
        )
        results = c.fetchall()
        conn.close()
        return results
    except Exception as e:
        logger.error(f"❌ Get memories error: {e}")
        return []

def get_random_memory(chat_id):
    """Get a random memory from the chat"""
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute(
            "SELECT username, message, saved_date FROM memories WHERE chat_id=? ORDER BY RANDOM() LIMIT 1",
            (chat_id,)
        )
        result = c.fetchone()
        conn.close()
        return result
    except Exception as e:
        logger.error(f"❌ Random memory error: {e}")
        return None

def get_top_users(chat_id):
    """Get top 5 users with most saved memories"""
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute(
            "SELECT username, COUNT(*) as count FROM memories WHERE chat_id=? GROUP BY username ORDER BY count DESC LIMIT 5",
            (chat_id,)
        )
        results = c.fetchall()
        conn.close()
        return results
    except Exception as e:
        logger.error(f"❌ Stats error: {e}")
        return []

def get_all_chats():
    """Get all unique chat IDs that have memories"""
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute("SELECT DISTINCT chat_id FROM memories")
        results = [row[0] for row in c.fetchall()]
        conn.close()
        return results
    except Exception as e:
        logger.error(f"❌ Get chats error: {e}")
        return []

# ===== BOT COMMANDS =====
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/start command"""
    welcome = """
🧠 *Welcome to DejaVu Bot!*

I save your favorite messages and remind you of them exactly 1 year later!

*Commands:*
/save - Reply to a message with /save to store it
/random - Get a random memory from this chat
/stats - See who has the most saved messages
/help - Show this message

*Quick Save:* Click the 📌 button below any message!
"""
    keyboard = [[InlineKeyboardButton("📌 Save this message", callback_data="save_prompt")]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(welcome, parse_mode='Markdown', reply_markup=reply_markup)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/help command"""
    help_text = """
📖 *How to use DejaVu Bot:*

1️⃣ *Save a message:*
   - Reply to any message with `/save`
   - OR click the 📌 button that appears below messages

2️⃣ *View memories:*
   - `/random` - See a random saved memory
   - `/stats` - See who saves the most

3️⃣ *Daily Throwbacks:*
   - Every day at 9 AM, I'll send memories from exactly 1 year ago!

*Pro Tip:* Add me to group chats to save group memories!
"""
    await update.message.reply_text(help_text, parse_mode='Markdown')

async def save_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /save command (reply to a message)"""
    if not update.message.reply_to_message:
        await update.message.reply_text(
            "❗ Please reply to a message you want to save!\n\n"
            "Example: Reply to a message and type /save"
        )
        return
    
    replied_msg = update.message.reply_to_message
    chat_id = update.effective_chat.id
    user_id = replied_msg.from_user.id
    username = replied_msg.from_user.username or replied_msg.from_user.first_name
    text = replied_msg.text or replied_msg.caption or "[Media/File]"
    
    if save_memory(chat_id, user_id, username, text):
        keyboard = [
            [InlineKeyboardButton("📖 View Random", callback_data="view_random")],
            [InlineKeyboardButton("📊 View Stats", callback_data="view_stats")]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            f"✅ *Saved!* 💾\n\n📝 *Preview:* {text[:100]}...",
            parse_mode='Markdown',
            reply_markup=reply_markup
        )
    else:
        await update.message.reply_text("❌ Failed to save. Please try again.")

async def random_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/random command - show a random memory"""
    chat_id = update.effective_chat.id
    result = get_random_memory(chat_id)
    
    if result:
        username, message, date = result
        if len(message) > 200:
            message = message[:200] + "..."
        await update.message.reply_text(
            f"🎲 *Random Memory:*\n\n👤 @{username}\n💬 {message}\n\n📅 {date[:10]}",
            parse_mode='Markdown'
        )
    else:
        await update.message.reply_text("😕 No memories saved yet! Use /save to start saving messages.")

async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """/stats command - show top users"""
    chat_id = update.effective_chat.id
    results = get_top_users(chat_id)
    
    if results:
        msg = "🏆 *Top Memory Contributors:*\n\n"
        emojis = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣"]
        for i, (user, count) in enumerate(results[:5]):
            if user:
                msg += f"{emojis[i]} @{user}: {count} memories\n"
            else:
                msg += f"{emojis[i]} User: {count} memories\n"
        
        total = sum(count for _, count in results)
        msg += f"\n📊 *Total memories:* {total}"
        
        keyboard = [[InlineKeyboardButton("🎲 Get Random Memory", callback_data="view_random")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(msg, parse_mode='Markdown', reply_markup=reply_markup)
    else:
        await update.message.reply_text("No memories yet! Start saving with /save")

# ===== INLINE BUTTON HANDLERS =====
async def button_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle inline button presses"""
    query = update.callback_query
    await query.answer()
    
    if query.data == "save_prompt":
        await query.message.reply_text("💡 Reply to any message with `/save` to store it!")
    
    elif query.data == "view_random":
        chat_id = query.message.chat_id
        result = get_random_memory(chat_id)
        if result:
            username, message, date = result
            if len(message) > 200:
                message = message[:200] + "..."
            await query.message.reply_text(
                f"🎲 *Random Memory:*\n\n👤 @{username}\n💬 {message}\n\n📅 {date[:10]}",
                parse_mode='Markdown'
            )
        else:
            await query.message.reply_text("No memories yet! Use /save to start.")
    
    elif query.data == "view_stats":
        chat_id = query.message.chat_id
        results = get_top_users(chat_id)
        if results:
            msg = "🏆 *Top Contributors:*\n\n"
            emojis = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣"]
            for i, (user, count) in enumerate(results[:5]):
                msg += f"{emojis[i]} @{user}: {count}\n"
            await query.message.reply_text(msg, parse_mode='Markdown')
        else:
            await query.message.reply_text("No stats yet!")

# ===== DAILY THROWBACK SCHEDULER =====
def send_daily_throwbacks(application):
    """Send memories from exactly 1 year ago to all chats"""
    logger.info("🔄 Running daily throwback check...")
    chats = get_all_chats()
    
    if not chats:
        logger.info("No chats with memories found.")
        return
    
    for chat_id in chats:
        try:
            memories = get_year_ago_memories(chat_id)
            for username, message, date in memories:
                text = f"📅 *On this day 1 year ago...*\n\n👤 @{username}\n💬 {message}"
                application.bot.send_message(chat_id=chat_id, text=text, parse_mode='Markdown')
            if memories:
                logger.info(f"✅ Sent {len(memories)} throwbacks to chat {chat_id}")
        except Exception as e:
            logger.error(f"❌ Error sending throwbacks to {chat_id}: {e}")

def start_scheduler(application):
    """Start the daily scheduler"""
    scheduler = BackgroundScheduler()
    scheduler.add_job(
        lambda: send_daily_throwbacks(application),
        trigger=CronTrigger(hour=9, minute=0),
        id="daily_throwback",
        replace_existing=True
    )
    scheduler.start()
    logger.info("⏰ Scheduler started! Daily throwbacks at 9:00 AM")

# ===== MAIN FUNCTION =====
def main():
    """Start the bot"""
    # Check token
    if not TOKEN:
        logger.error("❌ TELEGRAM_BOT_TOKEN not set!")
        logger.error("Please add it in Railway Variables")
        return
    
    # Initialize database
    if not init_db():
        logger.error("❌ Failed to initialize database. Check volume mount at /data")
        return
    
    # Create application
    application = Application.builder().token(TOKEN).build()
    
    # Add command handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("save", save_command))
    application.add_handler(CommandHandler("random", random_command))
    application.add_handler(CommandHandler("stats", stats_command))
    
    # Add callback handler for buttons
    application.add_handler(CallbackQueryHandler(button_callback))
    
    # Start scheduler
    start_scheduler(application)
    
    # Start the bot
    logger.info("🤖 Bot is starting...")
    
    if RAILWAY_URL:
        # Webhook mode (Railway)
        webhook_path = f"/{TOKEN}"
        full_webhook_url = f"https://{RAILWAY_URL}{webhook_path}"
        logger.info(f"🌐 Setting webhook: {full_webhook_url}")
        
        # Remove old webhook first
        application.bot.delete_webhook()
        
        # Set new webhook
        application.run_webhook(
            listen="0.0.0.0",
            port=PORT,
            url_path=webhook_path,
            webhook_url=full_webhook_url
        )
    else:
        # Polling mode (local development)
        logger.info("📡 Running in polling mode")
        application.run_polling(allowed_updates=["message", "callback_query"])

if __name__ == "__main__":
    main()
