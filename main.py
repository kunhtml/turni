import os
import json
import time
import threading
import queue
import signal
import sys
import re
import gdown
import subprocess
from datetime import datetime, timedelta
from dotenv import load_dotenv
import telebot
from telebot import types
from turnitin_processor import process_turnitin, shutdown_browser_session
from rate_limiter import (
    check_user_cooldown, 
    set_user_cooldown, 
    get_cooldown_message,
    clear_user_cooldown
)

# Load environment variables
load_dotenv()
TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

# Parse admin IDs - supports multiple admins separated by comma
admin_ids_str = os.getenv("ADMIN_TELEGRAM_ID", "")
ADMIN_TELEGRAM_IDS = [int(id.strip()) for id in admin_ids_str.split(",") if id.strip()]
ADMIN_TELEGRAM_ID = ADMIN_TELEGRAM_IDS[0] if ADMIN_TELEGRAM_IDS else None  # Keep for backward compatibility

# Initialize standard bot
bot = telebot.TeleBot(TELEGRAM_TOKEN, parse_mode='HTML')

# Processing queue and worker threads
processing_queue = queue.Queue()
worker_threads = []
MAX_WORKERS = 1  # Maximum 1 concurrent worker
MIN_QUEUE_SIZE_FOR_SCALING = 2  # Start additional workers when queue has 2+ items

# Subscription plans
MONTHLY_PLANS = {
    "1_month": {"price": 1500, "duration": 30, "name": "1 Month"},
    "3_months": {"price": 4000, "duration": 90, "name": "3 Months"},
    "6_months": {"price": 6000, "duration": 180, "name": "6 Months"},
    "12_months": {"price": 8000, "duration": 365, "name": "12 Months"}
}

DOCUMENT_PLANS = {
    "1_doc": {"price": 150, "documents": 1, "name": "1 Document"},
    "5_docs": {"price": 800, "documents": 5, "name": "5 Documents"},
    "10_docs": {"price": 1000, "documents": 10, "name": "10 Documents"}
}

BANK_DETAILS = """🏦 Commercial Bank
📍 Kurunegala (016) - Suratissa Mawatha
💳 Account No: 8160103864
📌 Name: SMSS BANDARA
📝 Include your name in the bank description!

📱 Send payment slip via WhatsApp to: +94702947854"""

def log(message: str):
    """Log with timestamp"""
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {message}")

def try_git_pull_on_startup():
    """Attempt to update the repository by running 'git pull origin main'.
    This is best-effort and will not crash the bot if it fails (e.g., not a git repo)."""
    try:
        log("Attempting to update code from git (git pull origin main)...")
        result = subprocess.run(
            ["git", "--no-pager", "pull", "origin", "main"],
            capture_output=True,
            text=True,
            timeout=45,
            cwd=os.getcwd()
        )
        if result.returncode == 0:
            out = (result.stdout or "").strip()
            log(f"Git pull success. {out[:500]}")
        else:
            err = (result.stderr or "").strip()
            log(f"Git pull failed/skipped (code {result.returncode}). {err[:500]}")
    except Exception as e:
        log(f"Git pull not executed: {e}")

def signal_handler(sig, frame):
    """Handle shutdown signals"""
    log("Shutdown signal received...")
    shutdown_browser_session()
    processing_queue.put(None)
    sys.exit(0)

# Register signal handlers
signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)

def load_subscriptions():
    """Load subscription data from file"""
    try:
        if os.path.exists("subscriptions.json"):
            with open("subscriptions.json", "r") as f:
                return json.load(f)
        return {}
    except:
        return {}

def save_subscriptions(data):
    """Save subscription data to file"""
    with open("subscriptions.json", "w") as f:
        json.dump(data, f, indent=2)

def load_pending_requests():
    """Load pending subscription requests"""
    try:
        if os.path.exists("pending_requests.json"):
            with open("pending_requests.json", "r") as f:
                return json.load(f)
        return {}
    except:
        return {}

def save_pending_requests(data):
    """Save pending subscription requests"""
    with open("pending_requests.json", "w") as f:
        json.dump(data, f, indent=2)

def load_keys():
    """Load redeemable keys from file (keys.json)"""
    try:
        if os.path.exists("keys.json"):
            with open("keys.json", "r") as f:
                return json.load(f)
        return {}
    except:
        return {}

def save_keys(data):
    """Save redeemable keys to file (keys.json)"""
    with open("keys.json", "w") as f:
        json.dump(data, f, indent=2)

def load_submission_history():
    """Load submission history from file"""
    try:
        if os.path.exists("submission_history.json"):
            with open("submission_history.json", "r") as f:
                return json.load(f)
        return {}
    except:
        return {}

def save_submission_history(data):
    """Save submission history to file"""
    with open("submission_history.json", "w") as f:
        json.dump(data, f, indent=2)

def add_to_submission_history(user_id, submission_data):
    """Add a submission to user's history"""
    history = load_submission_history()
    user_id_str = str(user_id)
    
    if user_id_str not in history:
        history[user_id_str] = []
    
    # Add to beginning of list (newest first)
    history[user_id_str].insert(0, submission_data)
    
    # Keep only last 20 submissions per user
    if len(history[user_id_str]) > 20:
        history[user_id_str] = history[user_id_str][:20]
    
    save_submission_history(history)

def get_user_submission_history(user_id, limit=10):
    """Get user's submission history"""
    history = load_submission_history()
    user_id_str = str(user_id)
    
    if user_id_str not in history:
        return []
    
    return history[user_id_str][:limit]

def is_user_subscribed(user_id):
    """Check if user has active subscription"""
    subscriptions = load_subscriptions()
    user_id_str = str(user_id)
    
    if user_id_str not in subscriptions:
        return False, None
    
    user_data = subscriptions[user_id_str]
    
    # Check time-based subscription
    if user_data.get("type") == "time" and "end_date" in user_data:
        end_date = datetime.fromisoformat(user_data["end_date"])
        if datetime.now() < end_date:
            return True, "time"
    
    # Check monthly subscription
    if "end_date" in user_data:
        end_date = datetime.fromisoformat(user_data["end_date"])
        if datetime.now() < end_date:
            return True, "monthly"
    
    # Check document-based subscription
    if "documents_remaining" in user_data and user_data["documents_remaining"] > 0:
        return True, "document"
    
    return False, None

def get_user_subscription_info(user_id):
    """Get detailed subscription info for user"""
    subscriptions = load_subscriptions()
    user_id_str = str(user_id)
    
    if user_id_str not in subscriptions:
        return None
    
    return subscriptions[user_id_str]

def process_documents_worker(worker_id):
    """Worker thread to process documents from queue - SINGLE WORKER MODE (sequential processing)"""
    log(f"[Worker-{worker_id}] 🚀 Starting worker in SINGLE WORKER MODE")
    log(f"[Worker-{worker_id}] ℹ️  All documents will be processed sequentially, one at a time")
    
    # Pre-login to Turnitin when worker starts - don't wait for first document
    log(f"[Worker-{worker_id}] Initializing browser and logging in...")
    try:
        from turnitin_auth import get_or_create_browser_session
        
        # Initialize browser session for this worker thread (includes login)
        page = get_or_create_browser_session()
        
        if page:
            log(f"[Worker-{worker_id}] ✅ Pre-login successful - ready to process documents")
        else:
            log(f"[Worker-{worker_id}] ⚠️ Pre-login failed, will retry on first document")
    except Exception as login_error:
        log(f"[Worker-{worker_id}] Pre-login error: {login_error} - will retry on first document")
    
    while True:
        try:
            # Block and wait for next item in queue (FIFO - First In First Out)
            queue_item = processing_queue.get()
            
            if queue_item is None:  # Shutdown signal
                log(f"[Worker-{worker_id}] Shutdown signal received")
                break
            
            # Check queue size for information
            queue_size = processing_queue.qsize()
            if queue_size > 0:
                log(f"[Worker-{worker_id}] 📋 Queue status: Processing current document, {queue_size} document(s) waiting in queue")
            else:
                log(f"[Worker-{worker_id}] 📋 Queue status: Processing current document, no documents waiting")
            
            log(f"[Worker-{worker_id}] 📄 Starting to process document for user {queue_item['user_id']}")
            
            try:
                bot.send_message(
                    queue_item['user_id'], 
                    f"📄 <b>Your document is now being processed...</b>\n\n"
                    f"⏳ Please wait while we generate your reports."
                )
            except Exception as msg_error:
                log(f"[Worker-{worker_id}] Error sending processing message: {msg_error}")
            
            # Process the document (SEQUENTIAL - completes entire workflow before next document)
            try:
                # Update queue item status
                queue_item['status'] = 'processing'
                queue_item['started_time'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                queue_item['worker_id'] = worker_id

                # Pass the bot instance to the processor
                log(f"[Worker-{worker_id}] 🔄 Calling turnitin_processor...")
                submission_info = process_turnitin(queue_item['file_path'], queue_item['user_id'], bot)
                log(f"[Worker-{worker_id}] ✅ Successfully processed document for user {queue_item['user_id']}")

                # Update queue item status
                queue_item['status'] = 'completed'
                queue_item['completed_time'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                
                # Save to history if submission was successful
                if submission_info and submission_info.get('reports_available'):
                    history_item = {
                        'submission_title': submission_info.get('submission_title', 'Unknown'),
                        'original_filename': queue_item.get('original_filename', 'Unknown'),
                        'submission_date': submission_info.get('submission_date'),
                        'reports_available': True
                    }
                    add_to_submission_history(queue_item['user_id'], history_item)
                    log(f"Added submission to history for user {queue_item['user_id']}")

            except Exception as process_error:
                log(f"Worker {worker_id} error processing document: {process_error}")

                # Update queue item status
                queue_item['status'] = 'failed'
                queue_item['error'] = str(process_error)
                queue_item['failed_time'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

                try:
                    bot.send_message(
                        queue_item['user_id'],
                        f"❌ Error processing document: {str(process_error)}\n\nPlease try again or contact support."
                    )
                except:
                    pass
            
            processing_queue.task_done()
            
            # All 3 workers are running from startup, no need to scale
            # scale_workers()
            
        except Exception as worker_error:
            log(f"Worker {worker_id} thread error: {worker_error}")
            try:
                processing_queue.task_done()
            except:
                pass

def scale_workers():
    """Dynamically scale workers based on queue size"""
    global worker_threads
    
    queue_size = processing_queue.qsize()
    active_workers = sum(1 for t in worker_threads if t.is_alive())
    
    # Scale up: Start additional workers if queue has 2+ items and we have less than MAX_WORKERS
    if queue_size >= MIN_QUEUE_SIZE_FOR_SCALING and active_workers < MAX_WORKERS:
        workers_to_start = min(MAX_WORKERS - active_workers, queue_size)
        
        for i in range(workers_to_start):
            worker_id = len(worker_threads) + 1
            
            # Stagger worker startup to prevent simultaneous logins
            stagger_delay = 5 * i
            if stagger_delay > 0:
                log(f"Delaying Worker {worker_id} startup by {stagger_delay}s to prevent login overload...")
                time.sleep(stagger_delay)
            
            worker = threading.Thread(
                target=process_documents_worker, 
                args=(worker_id,),
                daemon=True,
                name=f"Worker-{worker_id}"
            )
            worker.start()
            worker_threads.append(worker)
            log(f"Started Worker {worker_id} (Queue size: {queue_size}, Active workers: {active_workers + i + 1})")

def start_processing_worker():
    """Start single document processing worker thread (SEQUENTIAL MODE)"""
    global worker_threads
    
    log("=" * 70)
    log("🚀 STARTING SINGLE WORKER MODE")
    log("=" * 70)
    log("ℹ️  Configuration: MAX_WORKERS = 1 (Sequential Processing)")
    log("ℹ️  Documents will be processed one at a time, from start to finish")
    log("ℹ️  Next document will only start after previous one completes")
    log("=" * 70)
    
    # Start single worker
    worker_id = 1
    log(f"\n📌 Initializing Worker {worker_id}...")
    
    worker = threading.Thread(
        target=process_documents_worker, 
        args=(worker_id,),
        daemon=True,
        name=f"Worker-{worker_id}"
    )
    worker.start()
    worker_threads.append(worker)
    
    log(f"✅ Worker {worker_id} thread created and started successfully")
    log(f"✅ Worker is now ready to process documents sequentially")
    log("=" * 70 + "\n")

def create_main_menu():
    """Create main menu keyboard"""
    markup = types.InlineKeyboardMarkup(row_width=2)
    
    markup.add(
        types.InlineKeyboardButton("📊 My Subscription", callback_data="my_subscription")
    )
    markup.add(
        types.InlineKeyboardButton("🆔 Check ID", callback_data="check_id"),
        types.InlineKeyboardButton("❓ Help / Trợ giúp", callback_data="help")
    )
    
    return markup

def create_monthly_plans_menu():
    """Create monthly plans menu"""
    markup = types.InlineKeyboardMarkup(row_width=2)
    
    for plan_id, plan_info in MONTHLY_PLANS.items():
        button_text = f"{plan_info['name']} - Rs.{plan_info['price']}"
        markup.add(types.InlineKeyboardButton(button_text, callback_data=f"request_monthly_{plan_id}"))
    
    markup.add(types.InlineKeyboardButton("⬅️ Back", callback_data="back_to_main"))
    return markup

def create_document_plans_menu():
    """Create document plans menu"""
    markup = types.InlineKeyboardMarkup(row_width=1)
    
    for plan_id, plan_info in DOCUMENT_PLANS.items():
        button_text = f"{plan_info['name']} - Rs.{plan_info['price']}"
        markup.add(types.InlineKeyboardButton(button_text, callback_data=f"request_document_{plan_id}"))
    
    markup.add(types.InlineKeyboardButton("⬅️ Back", callback_data="back_to_main"))
    return markup

def create_admin_menu():
    """Create admin menu"""
    markup = types.InlineKeyboardMarkup(row_width=2)
    
    markup.add(
        types.InlineKeyboardButton("👥 View Subscriptions", callback_data="admin_view_subs"),
        types.InlineKeyboardButton("📋 Pending Requests", callback_data="admin_pending")
    )
    markup.add(
        types.InlineKeyboardButton("✏️ Edit Subscription", callback_data="admin_edit"),
        types.InlineKeyboardButton("📊 Statistics", callback_data="admin_stats")
    )
    markup.add(
        types.InlineKeyboardButton("📄 Processing Queue", callback_data="admin_queue"),
        types.InlineKeyboardButton("📜 View History", callback_data="admin_history")
    )
    
    return markup

def extract_google_drive_file_id(url):
    """Extract file ID from Google Drive URL"""
    # Pattern 1: https://drive.google.com/file/d/FILE_ID/view
    match = re.search(r'/file/d/([a-zA-Z0-9_-]+)', url)
    if match:
        return match.group(1)
    
    # Pattern 2: https://drive.google.com/open?id=FILE_ID
    match = re.search(r'[?&]id=([a-zA-Z0-9_-]+)', url)
    if match:
        return match.group(1)
    
    # Pattern 3: https://drive.google.com/uc?id=FILE_ID
    match = re.search(r'uc\?id=([a-zA-Z0-9_-]+)', url)
    if match:
        return match.group(1)
    
    return None

def download_from_google_drive(file_id, output_path):
    """Download file from Google Drive using gdown"""
    try:
        url = f"https://drive.google.com/uc?id={file_id}"
        gdown.download(url, output_path, quiet=False)
        return True
    except Exception as e:
        log(f"Google Drive download error: {e}")
        return False

def process_google_drive_link(message, drive_url):
    """Process Google Drive link and download file"""
    try:
        # Extract file ID from URL
        file_id = extract_google_drive_file_id(drive_url)
        if not file_id:
            bot.reply_to(
                message,
                "❌ <b>Invalid Google Drive Link</b>\n\n"
                "💡 Please make sure:\n"
                "1. The link is a valid Google Drive file link\n"
                "2. The file sharing is set to 'Anyone with the link'\n\n"
                "<b>Example:</b>\n"
                "https://drive.google.com/file/d/FILE_ID/view"
            )
            return
        
        log(f"Extracted Google Drive file ID: {file_id}")
        
        # Notify user
        status_msg = bot.send_message(
            message.chat.id,
            "📥 <b>Downloading from Google Drive...</b>\n\n"
            "⏳ Please wait..."
        )
        
        # Prepare download path
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        upload_dir = "uploads"
        os.makedirs(upload_dir, exist_ok=True)
        temp_filename = f"{message.chat.id}_{timestamp}_gdrive_temp"
        file_path = os.path.join(upload_dir, temp_filename)
        
        # Download file
        success = download_from_google_drive(file_id, file_path)
        
        if not success or not os.path.exists(file_path):
            bot.edit_message_text(
                "❌ <b>Download Failed</b>\n\n"
                "💡 Please check:\n"
                "1. File sharing is set to 'Anyone with the link'\n"
                "2. The link is correct\n"
                "3. File is not too large (max 100 MB)",
                message.chat.id,
                status_msg.message_id
            )
            return
        
        # Check file size
        file_size = os.path.getsize(file_path)
        MAX_FILE_SIZE = 100 * 1024 * 1024  # 100 MB for Google Drive downloads
        
        if file_size > MAX_FILE_SIZE:
            os.remove(file_path)
            bot.edit_message_text(
                f"❌ <b>File Too Large</b>\n\n"
                f"📁 File size: <b>{file_size / (1024 * 1024):.2f} MB</b>\n"
                f"📊 Maximum allowed: <b>100 MB</b>",
                message.chat.id,
                status_msg.message_id
            )
            return
        
        # Detect file extension from downloaded file (gdown adds it automatically)
        original_filename = f"document_{timestamp}.docx"  # Default
        if os.path.exists(file_path):
            # Try to get actual filename
            for ext in ['.docx', '.doc', '.pdf', '.txt', '.pptx', '.xlsx']:
                if os.path.exists(file_path + ext):
                    file_path = file_path + ext
                    original_filename = f"document_{timestamp}{ext}"
                    break
        
        # Rename to proper filename
        new_filename = f"{message.chat.id}_{timestamp}_{original_filename}"
        new_file_path = os.path.join(upload_dir, new_filename)
        
        if file_path != new_file_path:
            os.rename(file_path, new_file_path)
            file_path = new_file_path
        
        log(f"Downloaded Google Drive file to {file_path} ({file_size / (1024 * 1024):.2f} MB)")
        
        # Update status
        bot.edit_message_text(
            "✅ <b>Download Complete!</b>\n\n"
            f"📁 Size: <b>{file_size / (1024 * 1024):.2f} MB</b>\n"
            "📋 Adding to processing queue...",
            message.chat.id,
            status_msg.message_id
        )
        
        # Add to processing queue
        queue_item = {
            'user_id': message.chat.id,
            'file_path': file_path,
            'original_filename': original_filename,
            'added_time': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            'status': 'queued'
        }
        
        processing_queue.put(queue_item)
        queue_position = processing_queue.qsize()
        
        # Notify user about queue status (SINGLE WORKER MODE - Sequential Processing)
        if queue_position == 1:
            queue_message = (
                "📄 <b>Document queued for processing</b>\n\n"
                "🚀 Your document will be processed next.\n"
                "⏳ Processing will complete from start to finish before any other document."
            )
        else:
            estimated_wait = (queue_position - 1) * 3
            queue_message = (
                f"📄 <b>Document queued for processing</b>\n\n"
                f"📊 Position in queue: <b>{queue_position}</b>\n"
                f"⏳ Estimated wait: <b>~{estimated_wait} minutes</b>\n\n"
                f"ℹ️ Each document is processed completely (submit + download reports) before the next one starts."
            )
        
        bot.send_message(message.chat.id, queue_message)
        log(f"Added Google Drive document to queue for user {message.chat.id}. Queue size: {queue_position}")
        
    except Exception as e:
        bot.reply_to(message, f"❌ Failed to process Google Drive link: {e}")
        log(f"Error handling Google Drive link: {e}")

def process_user_document(message):
    """Process uploaded document through Turnitin"""
    try:
        log(f"Received document from user {message.chat.id}: {message.document.file_name}")
        
        # Telegram bots can only receive files up to ~20 MB directly.
        # For larger files, instruct users to send a Google Drive link (supported up to 100 MB in this bot).
        DIRECT_UPLOAD_LIMIT = 20 * 1024 * 1024  # 20 MB in bytes
        file_size = message.document.file_size
        
        if file_size > DIRECT_UPLOAD_LIMIT:
            size_mb = file_size / (1024 * 1024)
            bot.reply_to(
                message, 
                f"❌ <b>File Too Large for Direct Upload</b>\n\n"
                f"📁 Your file: <b>{size_mb:.2f} MB</b>\n"
                f"📥 Direct upload limit (Telegram): <b>20 MB</b>\n\n"
                f"✅ For larger files (up to 100 MB), please send a <b>Google Drive link</b> instead."
            )
            log(f"Direct upload rejected: {size_mb:.2f} MB (exceeds Telegram 20 MB limit)")
            return
        
        # Download file from Telegram
        log("Requesting file info from Telegram API...")
        file_info = bot.get_file(message.document.file_id)
        if not file_info:
            bot.reply_to(message, "❌ Failed to get file information. Please try again.")
            log("Failed to get file information from Telegram API")
            return
        
        log(f"Downloading file from Telegram servers: path={getattr(file_info, 'file_path', 'N/A')}")
        downloaded_file = bot.download_file(file_info.file_path)
        if not downloaded_file:
            bot.reply_to(message, "❌ Failed to download file. Please try again.")
            log("Failed to download file bytes from Telegram servers")
            return
        
        # Save file locally
        original_filename = message.document.file_name or "document"
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        new_filename = f"{message.chat.id}_{timestamp}_{original_filename}"
        
        upload_dir = "uploads"
        os.makedirs(upload_dir, exist_ok=True)
        file_path = os.path.join(upload_dir, new_filename)
        
        with open(file_path, 'wb') as f:
            f.write(downloaded_file)
        
        log(f"Saved document to {file_path} ({os.path.getsize(file_path)} bytes)")
        
        # Send immediate acknowledgement to user
        size_mb = file_size / (1024 * 1024)
        receipt_message = (
            f"✅ <b>File Received!</b>\n\n"
            f"📁 <b>Filename:</b> {original_filename}\n"
            f"📊 <b>Size:</b> {size_mb:.2f} MB\n\n"
            f"⏳ <b>Please wait while we process your document...</b>\n\n"
            f"💡 <i>Larger files may take longer to process</i>"
        )
        bot.send_message(message.chat.id, receipt_message)
        log(f"Sent file receipt confirmation to user {message.chat.id}")
        
        # Add to processing queue
        queue_item = {
            'user_id': message.chat.id,
            'file_path': file_path,
            'original_filename': original_filename,
            'added_time': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            'status': 'queued'
        }
        
        processing_queue.put(queue_item)
        queue_position = processing_queue.qsize()
        log(f"Queued document for user {message.chat.id}. Queue size now: {queue_position}")
        
        # Notify user about queue status (SINGLE WORKER MODE - Sequential Processing)
        if queue_position == 1:
            queue_message = (
                "📄 <b>Document queued for processing</b>\n\n"
                "🚀 Your document will be processed next.\n"
                "⏳ Processing will complete from start to finish before any other document."
            )
        else:
            estimated_wait = max(1, (queue_position - 1) * 3)
            queue_message = (
                f"📄 <b>Document queued for processing</b>\n\n"
                f"📊 Position in queue: <b>{queue_position}</b>\n"
                f"⏳ Estimated wait: <b>~{estimated_wait} minutes</b>\n\n"
                f"ℹ️ Each document is processed completely (submit + download reports) before the next one starts."
            )
        bot.send_message(message.chat.id, queue_message)
        log(f"Notified user {message.chat.id} about queue position {queue_position}")
        
    except Exception as e:
        bot.reply_to(message, f"❌ Failed to process file: {e}")
        log(f"Error handling document: {e}")

# MESSAGE HANDLERS
@bot.message_handler(commands=['start'])
def send_welcome(message):
    """Handle /start command"""
    user_id = message.from_user.id
    
    # Admin gets admin panel
    if user_id in ADMIN_TELEGRAM_IDS:
        bot.send_message(
            user_id,
            "🛠️ <b>Admin Panel</b>\n\nWelcome admin! Choose an option:",
            reply_markup=create_admin_menu()
        )
        return
    
    # Check user subscription
    is_subscribed, sub_type = is_user_subscribed(user_id)
    
    if is_subscribed:
        user_info = get_user_subscription_info(user_id)
        
        if sub_type == "time":
            # Time-based subscription
            end_date = datetime.fromisoformat(user_info["end_date"]).strftime("%Y-%m-%d %H:%M")
            welcome_text = f"<b>Welcome back!</b>\n\nYour subscription is active until: <b>{end_date}</b>\n\n✅ Unlimited uploads!\n\nSend me a document to get Turnitin reports!"
        elif sub_type == "monthly":
            # Monthly subscription
            end_date = datetime.fromisoformat(user_info["end_date"]).strftime("%Y-%m-%d")
            welcome_text = f"<b>Welcome back!</b>\n\nYour monthly subscription is active until: <b>{end_date}</b>\n\nSend me a document to get Turnitin reports!"
        elif sub_type == "document":
            # Document-based subscription
            docs_remaining = user_info.get("documents_remaining", 0)
            welcome_text = f"<b>Welcome back!</b>\n\nYou have <b>{docs_remaining}</b> document(s) remaining.\n\nSend me a document to get Turnitin reports!"
        else:
            # Unknown subscription type (fallback)
            welcome_text = "<b>Welcome back!</b>\n\nYour subscription is active.\n\nSend me a document to get Turnitin reports!"
        
        bot.send_message(user_id, welcome_text)
    else:
        welcome_text = """<b>Welcome to Turnitin Report Bot!</b>

<b>What I can do:</b>
• Generate Turnitin Similarity Reports
• Generate AI Writing Reports
• Support multiple document formats

<b>Choose your subscription plan:</b>"""
        
        bot.send_message(
            user_id,
            welcome_text,
            reply_markup=create_main_menu()
        )

@bot.message_handler(commands=['approve'])
def approve_subscription(message):
    """Admin command to approve subscription requests"""
    if message.from_user.id not in ADMIN_TELEGRAM_IDS:
        return
    
    try:
        request_id = message.text.split(' ', 1)[1]
    except IndexError:
        bot.reply_to(message, "❌ Please provide request ID: /approve [request_id]")
        return
    
    pending_requests = load_pending_requests()
    
    if request_id not in pending_requests:
        bot.reply_to(message, "❌ Request ID not found")
        return
    
    request_data = pending_requests[request_id]
    
    if request_data["status"] != "pending":
        bot.reply_to(message, "❌ Request already processed")
        return
    
    # Approve the request
    subscriptions = load_subscriptions()
    user_id_str = str(request_data["user_id"])
    
    if request_data["plan_type"] == "monthly":
        start_date = datetime.now()
        end_date = start_date + timedelta(days=request_data["duration"])
        
        subscriptions[user_id_str] = {
            "plan_type": "monthly",
            "plan_name": request_data["plan_name"],
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "price": request_data["price"]
        }
    else:  # document subscription
        subscriptions[user_id_str] = {
            "plan_type": "document",
            "plan_name": request_data["plan_name"],
            "documents_total": request_data["documents"],
            "documents_remaining": request_data["documents"],
            "purchase_date": datetime.now().isoformat(),
            "price": request_data["price"]
        }
    
    # Update request status
    request_data["status"] = "approved"
    request_data["approved_date"] = datetime.now().isoformat()
    
    save_subscriptions(subscriptions)
    save_pending_requests(pending_requests)
    
    # Notify user
    user_message = f"""✅ <b>Subscription Approved!</b>

📅 <b>Plan:</b> {request_data['plan_name']}
💰 <b>Price:</b> Rs.{request_data['price']}

🎉 Your subscription is now active!

📄 <b>How to submit documents:</b>
• Upload file directly (max 20 MB via Telegram)
• Send Google Drive link (max 100 MB)

<b>Example Google Drive link:</b>
https://drive.google.com/file/d/YOUR_FILE_ID/view

💡 Make sure file sharing is set to "Anyone with the link"!"""
    
    bot.send_message(request_data["user_id"], user_message)
    bot.reply_to(message, f"✅ Subscription approved for user {request_data['user_id']}")

@bot.message_handler(commands=['add'])
def add_key_command(message):
    """Admin command to create/update a redeemable key: /add <key> <uses>"""
    if message.from_user.id not in ADMIN_TELEGRAM_IDS:
        return
    
    try:
        parts = message.text.split()
        _, key, uses_str = parts[0], parts[1], parts[2]
    except Exception:
        bot.reply_to(message, (
            "❌ Usage / Cách dùng: /add <key> <uses|số_lượt>\n\n"
            "Example / Ví dụ: /add VIPOCT 2\n"
            "→ Create key VIPOCT for 2 uses / Tạo key VIPOCT cho 2 lượt"
        ))
        return
    
    if not key or ' ' in key:
        bot.reply_to(message, "❌ Invalid key (no spaces) / Key không hợp lệ (không chứa khoảng trắng)")
        return
    
    try:
        uses = int(uses_str)
        if uses <= 0:
            raise ValueError()
    except ValueError:
        bot.reply_to(message, "❌ Uses must be a positive integer / Số lượt phải là số nguyên dương")
        return
    
    keys = load_keys()
    now = datetime.now().isoformat()
    
    # Behavior: upsert if key not redeemed; block if already redeemed
    if key in keys and keys[key].get('redeemed'):
        bot.reply_to(message, f"❌ Key '{key}' already redeemed; cannot update / đã được sử dụng, không thể cập nhật")
        return
    
    existed = key in keys
    keys[key] = {
        'uses': uses,
        'redeemed': False,
        'created_at': keys.get(key, {}).get('created_at', now) if existed else now,
        'created_by': keys.get(key, {}).get('created_by', message.from_user.id) if existed else message.from_user.id
    }
    save_keys(keys)
    
    if existed:
        bot.reply_to(message, f"✅ Updated key <b>{key}</b> → <b>{uses}</b> uses\n✅ Đã cập nhật key <b>{key}</b> → <b>{uses}</b> lượt", parse_mode='HTML')
    else:
        bot.reply_to(message, f"✅ Created key <b>{key}</b> with <b>{uses}</b> uses\n✅ Đã tạo key <b>{key}</b> với <b>{uses}</b> lượt", parse_mode='HTML')

@bot.message_handler(commands=['keys'])
def view_keys_command(message):
    """Admin command to view all active keys and redemption stats"""
    if message.from_user.id not in ADMIN_TELEGRAM_IDS:
        return
    
    keys = load_keys()
    
    if not keys:
        bot.reply_to(message, "📭 <b>No keys created yet</b>")
        return
    
    # Calculate stats
    total_keys = len(keys)
    active_keys = sum(1 for k in keys.values() if not k.get('redeemed', False))
    redeemed_keys = total_keys - active_keys
    total_uses = sum(int(k.get('uses', 0)) for k in keys.values())
    used_uses = sum(int(k.get('uses', 0)) for k in keys.values() if k.get('redeemed', False))
    available_uses = total_uses - used_uses
    
    # Build stats header
    stats_text = f"""🔑 <b>Key Management Statistics</b>

📊 <b>Summary / Tóm tắt:</b>
• <b>Total Keys:</b> {total_keys}
• <b>Active Keys (Chưa dùng):</b> {active_keys}
• <b>Redeemed Keys (Đã dùng):</b> {redeemed_keys}

📈 <b>Usage Stats / Thống kê sử dụng:</b>
• <b>Total Uses (Tổng lượt):</b> {total_uses}
• <b>Available Uses (Lượt khả dụng):</b> {available_uses}
• <b>Redeemed Uses (Lượt đã dùng):</b> {used_uses}

"""
    
    # Build key details table
    if active_keys > 0:
        stats_text += f"<b>📌 Active Keys (Tối đa 20)</b>\n"
        active_count = 0
        for key_name, key_info in sorted(keys.items()):
            if not key_info.get('redeemed', False) and active_count < 20:
                uses = int(key_info.get('uses', 0))
                created_at = key_info.get('created_at', 'Unknown')[:10]
                stats_text += f"• <code>{key_name}</code> → {uses} uses | Created: {created_at}\n"
                active_count += 1
        if active_count >= 20:
            stats_text += f"... and {active_keys - 20} more active keys\n"
    
    if redeemed_keys > 0:
        stats_text += f"\n<b>✅ Redeemed Keys (Tối đa 10)</b>\n"
        redeemed_count = 0
        for key_name, key_info in sorted(keys.items()):
            if key_info.get('redeemed', False) and redeemed_count < 10:
                uses = int(key_info.get('uses', 0))
                redeemed_by = key_info.get('redeemed_by', 'Unknown')
                redeemed_at = key_info.get('redeemed_at', 'Unknown')[:10]
                stats_text += f"• <code>{key_name}</code> → {uses} uses | By: {redeemed_by} | At: {redeemed_at}\n"
                redeemed_count += 1
        if redeemed_count >= 10:
            stats_text += f"... and {redeemed_keys - 10} more redeemed keys\n"
    
    bot.send_message(message.chat.id, stats_text)

@bot.message_handler(commands=['edit_subscription'])
def edit_subscription_command(message):
    """Admin command to edit subscription end date"""
    if message.from_user.id not in ADMIN_TELEGRAM_IDS:
        return
    
    try:
        parts = message.text.split(' ')
        user_id = parts[1]
        new_end_date = parts[2]  # Format: YYYY-MM-DD
    except IndexError:
        bot.reply_to(message, "❌ Usage: /edit_subscription [user_id] [YYYY-MM-DD]")
        return
    
    try:
        datetime.strptime(new_end_date, "%Y-%m-%d")
    except ValueError:
        bot.reply_to(message, "❌ Invalid date format. Use YYYY-MM-DD")
        return
    
    subscriptions = load_subscriptions()
    
    if user_id not in subscriptions:
        bot.reply_to(message, "❌ User not found in subscriptions")
        return
    
    # Update end date
    subscriptions[user_id]["end_date"] = f"{new_end_date}T23:59:59"
    save_subscriptions(subscriptions)
    
    bot.reply_to(message, f"✅ Updated subscription end date for user {user_id} to {new_end_date}")

@bot.message_handler(commands=['viewhistory'])
def view_history_command(message):
    """Admin command to view user submission history"""
    if message.from_user.id not in ADMIN_TELEGRAM_IDS:
        return
    
    try:
        user_id = int(message.text.split(' ')[1])
    except (IndexError, ValueError):
        bot.reply_to(message, "❌ Usage: /viewhistory [user_id]\n\nExample: /viewhistory 6072090845")
        return
    
    history = get_user_submission_history(user_id, limit=20)
    
    if not history:
        bot.reply_to(message, f"📜 <b>History for User {user_id}</b>\n\n📭 No submissions found.")
        return
    
    # Build history message
    history_text = f"📜 <b>History for User {user_id}</b>\n\n"
    
    for idx, item in enumerate(history, 1):
        submission_title = item.get('submission_title', 'Unknown')
        original_filename = item.get('original_filename', 'Unknown')
        submission_date = item.get('submission_date', 'Unknown')
        
        # Format date
        try:
            date_obj = datetime.strptime(submission_date, "%Y-%m-%d %H:%M:%S")
            formatted_date = date_obj.strftime("%d %b %Y, %I:%M %p")
        except:
            formatted_date = submission_date
        
        history_text += f"<b>{idx}. {original_filename}</b>\n"
        history_text += f"   📋 Paper ID: {submission_title}\n"
        history_text += f"   📅 Date: {formatted_date}\n\n"
    
    history_text += f"<b>Total:</b> {len(history)} submissions"
    
    bot.send_message(message.chat.id, history_text)

@bot.message_handler(commands=['key'])
def redeem_key_command(message):
    """User command to redeem a key: /key <key>
    Grants N document uses to the user's document-based subscription.
    """
    user_id = message.from_user.id
    try:
        parts = message.text.split()
        if len(parts) < 2:
            raise ValueError()
        key = parts[1].strip()
    except Exception:
        bot.reply_to(message, (
            "❌ Usage / Cách dùng: /key <key>\n\n"
            "Example / Ví dụ: /key VIPOCT\n"
            "→ Receive the number of uses provided by the key / Nhận số lượt đúng theo key"
        ))
        return
    
    keys = load_keys()
    if key not in keys:
        bot.reply_to(message, "❌ Key not found or invalid / Key không tồn tại hoặc sai")
        return
    
    key_info = keys[key]
    if key_info.get('redeemed'):
        bot.reply_to(message, "❌ Key already redeemed / Key đã được sử dụng")
        return
    
    uses = int(key_info.get('uses', 0))
    if uses <= 0:
        bot.reply_to(message, "❌ Invalid key (uses = 0) / Key không hợp lệ (số lượt = 0)")
        return
    
    # Mark key as redeemed
    key_info['redeemed'] = True
    key_info['redeemed_by'] = user_id
    key_info['redeemed_at'] = datetime.now().isoformat()
    save_keys(keys)
    
    # Grant document uses to user's subscription (document-based)
    subs = load_subscriptions()
    uid = str(user_id)
    now = datetime.now().isoformat()
    
    if uid not in subs:
        subs[uid] = {
            'type': 'document',
            'plan_name': 'Key Redeem',
            'documents_total': uses,
            'documents_remaining': uses,
            'start_date': now,
        }
    else:
        # If user already has document-based, add uses; otherwise create/augment doc counters
        user_sub = subs[uid]
        if user_sub.get('type') == 'document' or 'documents_remaining' in user_sub:
            user_sub['documents_total'] = int(user_sub.get('documents_total', 0)) + uses
            user_sub['documents_remaining'] = int(user_sub.get('documents_remaining', 0)) + uses
            user_sub['plan_name'] = user_sub.get('plan_name', 'Key Redeem')
        else:
            # User might have time/monthly; add document counters so is_user_subscribed can switch if time expires
            user_sub['documents_total'] = int(user_sub.get('documents_total', 0)) + uses
            user_sub['documents_remaining'] = int(user_sub.get('documents_remaining', 0)) + uses
            # Keep their original type; doc counters will be used when needed
    
    save_subscriptions(subs)
    
    # Confirm to user
    remaining = subs[str(user_id)].get('documents_remaining', uses)
    bot.reply_to(message, (
        "✅ <b>Key redeemed successfully!</b>\n"
        "✅ <b>Dùng key thành công!</b>\n\n"
        f"🎟️ Key: <code>{key}</code> → +<b>{uses}</b> uses / lượt\n"
        f"📊 Remaining: <b>{remaining}</b> / Còn lại: <b>{remaining}</b>\n\n"
        "📤 Send a document to start processing / Gửi tài liệu để bắt đầu xử lý."
    ), parse_mode='HTML')

@bot.message_handler(commands=['help'])
def help_command(message):
    """Show bilingual help like the Help button"""
    help_text = """❓ <b>Help / Hướng dẫn</b>

<b>1) Redeem Key / Sử dụng Key</b>
• When you have a key, use: /key YOURKEY
    Khi bạn có key, hãy dùng: <code>/key YOURKEY</code>
    Example / Ví dụ: <code>/key VIPOCT</code>
    → You will receive the same number of uses as the key provides
        Bạn sẽ nhận số lượt sử dụng tương ứng với key

<b>Notes / Lưu ý:</b>
• Each key can be redeemed once (one-time)
    Mỗi key chỉ dùng 1 lần
• After redeeming, check your status with /check
    Sau khi dùng key, có thể kiểm tra bằng <code>/check</code>

<b>2) Send documents / Gửi tài liệu</b>
• Direct upload up to 20MB (Telegram)
    Gửi file trực tiếp tối đa 20MB
 

<b>3) Supported formats / Định dạng hỗ trợ</b>
• PDF, DOC, DOCX, TXT, RTF, ODT, HTML
"""

    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("⬅️ Back", callback_data="back_to_main"))
    bot.send_message(message.chat.id, help_text, reply_markup=markup)

@bot.message_handler(commands=['id'])
def id_command(message):
    """Show user ID"""
    user_id = message.from_user.id
    username = message.from_user.username or "N/A"
    first_name = message.from_user.first_name or "N/A"
    
    info_text = f"""<b>Your Account Information:</b>

<b>Telegram ID:</b> <code>{user_id}</code>
<b>Username:</b> @{username}
<b>Name:</b> {first_name}

💡 Share this ID with admins for account management."""
    
    bot.send_message(user_id, info_text)

@bot.message_handler(commands=['active'])
def active_command(message):
    """Admin command to activate/create subscription for a user - time-based access"""
    if message.from_user.id not in ADMIN_TELEGRAM_IDS:
        return
    
    try:
        parts = message.text.split(' ')
        target_user_id = int(parts[1])
        days = int(parts[2])
    except (IndexError, ValueError):
        bot.reply_to(message, 
            "❌ Usage: /active <user_id> <số ngày>\n\n"
            "Example: /active 123456789 2\n"
            "(Kích hoạt 2 ngày cho user ID 123456789)")
        return
    
    if days <= 0:
        bot.reply_to(message, "❌ Số ngày phải lớn hơn 0")
        return
    
    subscriptions = load_subscriptions()
    user_id_str = str(target_user_id)
    
    # Calculate end date
    start_date = datetime.now()
    end_date = start_date + timedelta(days=days)
    
    # Create or update subscription (time-based, not document-based)
    subscriptions[user_id_str] = {
        "type": "time",
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "duration_days": days
    }
    
    action = "tạo" if user_id_str not in subscriptions else "gia hạn"
    
    save_subscriptions(subscriptions)
    
    # Format dates for display
    end_date_str = end_date.strftime("%d %b %Y, %H:%M:%S")
    
    # Notify admin
    admin_msg = f"""✅ <b>Subscription Activated</b>

<b>User ID:</b> {target_user_id}
<b>Action:</b> {action}
<b>Duration:</b> {days} ngày
<b>Valid Until:</b> {end_date_str}"""
    
    bot.reply_to(message, admin_msg)
    
    # Try to notify user
    try:
        user_msg = f"""🎉 <b>Your account has been activated!</b>

<b>Duration:</b> {days} ngày
<b>Valid Until:</b> {end_date_str}

✅ Unlimited document uploads!

Send me documents to get Turnitin reports!"""
        bot.send_message(target_user_id, user_msg)
    except:
        log(f"Could not notify user {target_user_id}")

@bot.message_handler(commands=['check'])
def check_command(message):
    """Check user subscription status"""
    user_id = message.from_user.id
    
    # Check if admin is checking someone else's info
    try:
        parts = message.text.split(' ')
        if len(parts) > 1 and user_id in ADMIN_TELEGRAM_IDS:
            # Admin checking another user
            target_user_id = int(parts[1])
        else:
            # User checking their own info
            target_user_id = user_id
    except (IndexError, ValueError):
        target_user_id = user_id
    
    subscriptions = load_subscriptions()
    user_id_str = str(target_user_id)
    
    if user_id_str not in subscriptions:
        if target_user_id == user_id:
            check_text = f"""❌ <b>No Active Subscription</b>

<b>Telegram ID:</b> <code>{target_user_id}</code>

You don't have an active subscription yet.
Contact admin to get started!"""
        else:
            check_text = f"""❌ <b>No Active Subscription</b>

<b>User ID:</b> {target_user_id}

This user doesn't have an active subscription."""
        bot.send_message(message.chat.id, check_text)
        return
    
    user_data = subscriptions[user_id_str]
    sub_type = user_data.get("type", "unknown")
    
    if sub_type == "time":
        # Time-based subscription
        start_date = user_data.get("start_date", "N/A")
        end_date = user_data.get("end_date", "N/A")
        
        # Format dates
        try:
            start_obj = datetime.fromisoformat(start_date)
            start_date_str = start_obj.strftime("%d %b %Y, %H:%M")
        except:
            start_date_str = start_date
        
        try:
            end_obj = datetime.fromisoformat(end_date)
            end_date_str = end_obj.strftime("%d %b %Y, %H:%M")
            # Calculate remaining time
            now = datetime.now()
            if end_obj > now:
                remaining = end_obj - now
                remaining_hours = int(remaining.total_seconds() / 3600)
                remaining_days = remaining_hours // 24
                remaining_hours = remaining_hours % 24
                time_remaining = f"{remaining_days}d {remaining_hours}h"
            else:
                time_remaining = "Hết hạn"
        except:
            end_date_str = end_date
            time_remaining = "Unknown"
        
        if target_user_id == user_id:
            check_text = f"""✅ <b>Your Subscription Status</b>

<b>Telegram ID:</b> <code>{target_user_id}</code>
<b>Plan Type:</b> Time-based
<b>Valid From:</b> {start_date_str}
<b>Valid Until:</b> {end_date_str}
<b>Time Remaining:</b> <b>{time_remaining}</b>

📤 Unlimited document uploads!"""
        else:
            check_text = f"""✅ <b>User Subscription Status</b>

<b>User ID:</b> {target_user_id}
<b>Plan Type:</b> Time-based
<b>Valid From:</b> {start_date_str}
<b>Valid Until:</b> {end_date_str}
<b>Time Remaining:</b> <b>{time_remaining}</b>"""
    
    elif sub_type == "document":
        documents_remaining = user_data.get("documents_remaining", 0)
        start_date = user_data.get("start_date", "N/A")
        end_date = user_data.get("end_date", "N/A")
        
        # Format dates
        try:
            start_obj = datetime.fromisoformat(start_date)
            start_date = start_obj.strftime("%d %b %Y")
        except:
            pass
        
        try:
            end_obj = datetime.fromisoformat(end_date)
            end_date = end_obj.strftime("%d %b %Y")
        except:
            pass
        
        if target_user_id == user_id:
            check_text = f"""✅ <b>Your Subscription Status</b>

<b>Telegram ID:</b> <code>{target_user_id}</code>
<b>Plan Type:</b> Document-based
<b>Documents Remaining:</b> <b>{documents_remaining}</b>
<b>Valid From:</b> {start_date}
<b>Valid Until:</b> {end_date}

📤 You can send {documents_remaining} more document(s) for processing."""
        else:
            check_text = f"""✅ <b>User Subscription Status</b>

<b>User ID:</b> {target_user_id}
<b>Plan Type:</b> Document-based
<b>Documents Remaining:</b> <b>{documents_remaining}</b>
<b>Valid From:</b> {start_date}
<b>Valid Until:</b> {end_date}"""
    
    elif sub_type == "monthly":
        end_date = user_data.get("end_date", "N/A")
        
        try:
            end_obj = datetime.fromisoformat(end_date)
            end_date = end_obj.strftime("%d %b %Y")
        except:
            pass
        
        if target_user_id == user_id:
            check_text = f"""✅ <b>Your Subscription Status</b>

<b>Telegram ID:</b> <code>{target_user_id}</code>
<b>Plan Type:</b> Monthly
<b>Valid Until:</b> {end_date}

📤 You have unlimited document processing!"""
        else:
            check_text = f"""✅ <b>User Subscription Status</b>

<b>User ID:</b> {target_user_id}
<b>Plan Type:</b> Monthly
<b>Valid Until:</b> {end_date}"""
    else:
        check_text = f"""⚠️ <b>Unknown Subscription</b>

<b>User ID:</b> {target_user_id}
<b>Status:</b> Unknown subscription type"""
    
    bot.send_message(message.chat.id, check_text)

@bot.message_handler(commands=['stop'])
def stop_subscription_command(message):
    """Admin command to stop/cancel user subscription"""
    if message.from_user.id not in ADMIN_TELEGRAM_IDS:
        return
    
    try:
        parts = message.text.split(' ')
        target_user_id = int(parts[1])
    except (IndexError, ValueError):
        bot.reply_to(message, 
            "❌ Usage: /stop <user_id>\n\n"
            "Example: /stop 123456789\n"
            "(Dừng gói cước cho user ID 123456789)")
        return
    
    subscriptions = load_subscriptions()
    user_id_str = str(target_user_id)
    
    if user_id_str not in subscriptions:
        bot.reply_to(message, f"❌ User {target_user_id} không có gói cước nào")
        return
    
    user_data = subscriptions[user_id_str]
    
    # Store old subscription info before deletion
    old_sub_type = user_data.get("type", "unknown")
    if old_sub_type == "time":
        old_sub_info = f"Time-based ({user_data.get('duration_days', '?')} days)"
    elif old_sub_type == "document":
        old_sub_info = f"Document-based ({user_data.get('documents_remaining', '?')} docs remaining)"
    else:
        old_sub_info = user_data.get("plan_name", "Unknown plan")
    
    # Delete subscription
    del subscriptions[user_id_str]
    save_subscriptions(subscriptions)
    
    # Notify admin
    admin_msg = f"""✅ <b>Subscription Stopped</b>

<b>User ID:</b> {target_user_id}
<b>Old Plan:</b> {old_sub_info}
<b>Status:</b> Đã hủy bỏ"""
    
    bot.reply_to(message, admin_msg)
    
    # Try to notify user
    try:
        user_msg = f"""⚠️ <b>Your subscription has been stopped</b>

Your access to document processing has been revoked.
Contact admin for more information."""
        bot.send_message(target_user_id, user_msg)
    except:
        log(f"Could not notify user {target_user_id}")
    
    log(f"Subscription stopped for user {target_user_id}. Old plan: {old_sub_info}")

@bot.message_handler(commands=['clearcooldown'])
def clear_cooldown_command(message):
    """Admin command to clear cooldown for a user"""
    if message.from_user.id not in ADMIN_TELEGRAM_IDS:
        return
    
    try:
        parts = message.text.split(' ')
        target_user_id = int(parts[1])
    except (IndexError, ValueError):
        bot.reply_to(message, 
            "❌ Usage: /clearcooldown <user_id>\n\n"
            "Example: /clearcooldown 123456789\n"
            "(Xóa cooldown cho user ID 123456789)")
        return
    
    if clear_user_cooldown(target_user_id):
        bot.reply_to(message, f"✅ Đã xóa cooldown cho user {target_user_id}")
        
        # Try to notify user
        try:
            bot.send_message(target_user_id, 
                "✅ <b>Cooldown Cleared / Đã xóa thời gian chờ</b>\n\n"
                "You can now upload documents immediately.\n"
                "Bạn có thể gửi file ngay bây giờ.")
        except:
            pass
    else:
        bot.reply_to(message, f"❌ User {target_user_id} không có cooldown")

@bot.message_handler(func=lambda message: message.text and 'drive.google.com' in message.text)
def handle_google_drive_link(message):
    """Handle Google Drive links"""
    user_id = message.from_user.id
    
    log(f"DEBUG: Google Drive link received from user {user_id}")
    
    # Admin has unlimited access and no cooldown
    if user_id in ADMIN_TELEGRAM_IDS:
        process_google_drive_link(message, message.text.strip())
        return
    
    # Check cooldown first
    is_in_cooldown, remaining_seconds, cooldown_end = check_user_cooldown(user_id)
    if is_in_cooldown:
        cooldown_msg = get_cooldown_message(remaining_seconds, cooldown_end)
        bot.reply_to(message, cooldown_msg)
        log(f"User {user_id} blocked by cooldown: {remaining_seconds}s remaining")
        return
    
    # Check subscription
    is_subscribed, sub_type = is_user_subscribed(user_id)
    
    if not is_subscribed:
        bot.reply_to(
            message,
            "<b>No Active Subscription</b>\n\nPlease purchase a subscription to use this service.",
            reply_markup=create_main_menu()
        )
        return
    
    # Handle document-based subscription limits only (time-based has unlimited)
    if sub_type == "document":
        subscriptions = load_subscriptions()
        user_data = subscriptions[str(user_id)]
        
        if user_data["documents_remaining"] <= 0:
            bot.reply_to(
                message,
                "<b>No Documents Remaining</b>\n\nYour document allowance has been used up. Please purchase a new plan.",
                reply_markup=create_main_menu()
            )
            return
        
        # Decrease document count
        user_data["documents_remaining"] -= 1
        save_subscriptions(subscriptions)
        
        remaining_msg = f"\n\n📊 <b>Remaining Documents:</b> {user_data['documents_remaining']}"
    else:
        remaining_msg = ""
    
    # Set cooldown for this user (8 minutes)
    set_user_cooldown(user_id)
    log(f"Set 8-minute cooldown for user {user_id}")
    
    # Process the Google Drive link
    process_google_drive_link(message, message.text.strip())

@bot.message_handler(content_types=['document'])
def handle_document(message):
    """Handle document uploads"""
    user_id = message.from_user.id
    
    log(f"DEBUG: Document received from user {user_id}")
    
    # Admin has unlimited access and no cooldown
    if user_id in ADMIN_TELEGRAM_IDS:
        log("User is admin - bypassing subscription check and cooldown")
        process_user_document(message)
        return
    
    # Check cooldown first
    is_in_cooldown, remaining_seconds, cooldown_end = check_user_cooldown(user_id)
    if is_in_cooldown:
        cooldown_msg = get_cooldown_message(remaining_seconds, cooldown_end)
        bot.reply_to(message, cooldown_msg)
        log(f"User {user_id} blocked by cooldown: {remaining_seconds}s remaining")
        return
    
    # Check subscription
    is_subscribed, sub_type = is_user_subscribed(user_id)
    log(f"Subscription check for user {user_id}: is_subscribed={is_subscribed}, type={sub_type}")
    
    if not is_subscribed:
        bot.reply_to(
            message,
            "<b>No Active Subscription</b>\n\nPlease purchase a subscription to use this service.",
            reply_markup=create_main_menu()
        )
        log(f"User {user_id} has no active subscription - rejected upload")
        return
    
    # Handle document-based subscription limits only (time-based has unlimited)
    if sub_type == "document":
        subscriptions = load_subscriptions()
        user_data = subscriptions[str(user_id)]
        
        if user_data["documents_remaining"] <= 0:
            bot.reply_to(
                message,
                "<b>No Documents Remaining</b>\n\nYour document allowance has been used up. Please purchase a new plan.",
                reply_markup=create_main_menu()
            )
            log(f"User {user_id} exceeded document quota")
            return
        
        # Decrease document count
        user_data["documents_remaining"] -= 1
        save_subscriptions(subscriptions)
        
        remaining = user_data["documents_remaining"]
        log(f"User {user_id} documents_remaining updated to {remaining} (document-based subscription)")
    else:
        log(f"User {user_id} time-based subscription - proceeding to process")
    
    # Set cooldown for this user (8 minutes)
    set_user_cooldown(user_id)
    log(f"Set 8-minute cooldown for user {user_id}")
    
    # Process the document
    process_user_document(message)

if __name__ == "__main__":
    # Update repository before starting the bot (best-effort)
    try_git_pull_on_startup()

    # Import and register callback handlers
    from bot_callbacks import register_callback_handlers
    register_callback_handlers(bot, ADMIN_TELEGRAM_ID, MONTHLY_PLANS, DOCUMENT_PLANS, BANK_DETAILS, 
                              load_pending_requests, save_pending_requests, load_subscriptions, 
                              save_subscriptions, is_user_subscribed, get_user_subscription_info,
                              create_main_menu, create_monthly_plans_menu, create_document_plans_menu,
                              create_admin_menu, processing_queue, log, get_user_submission_history)
    
    start_processing_worker()
    
    log("🤖 Turnitin bot starting...")
    
    try:
        bot.infinity_polling(
            timeout=60,
            long_polling_timeout=60,
            restart_on_change=False
        )
    except Exception as e:
        log(f"Polling error: {e}")
    finally:
        log("Bot shutting down...")
        shutdown_browser_session()
        
        # Signal all workers to stop
        for _ in worker_threads:
            processing_queue.put(None)
        
        # Wait for all workers to finish
        for worker in worker_threads:
            if worker.is_alive():
                worker.join(timeout=5)
        
        log("Bot shutdown complete")