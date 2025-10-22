import os
import json
import time
import threading
import queue
import signal
import sys
import re
import gdown
from datetime import datetime, timedelta
from dotenv import load_dotenv
import telebot
from telebot import types
from turnitin_processor import process_turnitin, shutdown_browser_session

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
MAX_WORKERS = 3  # 3 workers with sequential login to avoid concurrent login issues
MIN_QUEUE_SIZE_FOR_SCALING = 2  # Start additional workers when queue has 2+ items

# Login synchronization - ensures workers login one at a time
login_lock = threading.Lock()
worker_login_events = {}  # Track when each worker completes login

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
    """Worker thread to process documents from queue"""
    log(f"Worker {worker_id} started")
    
    # Wait for previous worker to complete login before starting
    if worker_id > 1:
        previous_worker = worker_id - 1
        if previous_worker in worker_login_events:
            log(f"[Worker-{worker_id}] Waiting for Worker-{previous_worker} to complete login...")
            worker_login_events[previous_worker].wait(timeout=120)  # Wait max 2 minutes
            log(f"[Worker-{worker_id}] Worker-{previous_worker} login completed, proceeding...")
        time.sleep(5)  # Additional 5s delay between workers
    
    # Create login event for this worker
    worker_login_events[worker_id] = threading.Event()
    
    # Pre-login to Turnitin when worker starts - don't wait for first document
    log(f"[Worker-{worker_id}] Initializing browser and logging in...")
    try:
        with login_lock:  # Acquire lock to ensure sequential login
            from turnitin_auth import get_or_create_browser_session, check_and_perform_login
            
            # Initialize browser session for this worker thread
            page = get_or_create_browser_session()
            
            # Now try login
            login_success = check_and_perform_login()
            if login_success:
                log(f"[Worker-{worker_id}] ✅ Pre-login successful - ready to process documents")
            else:
                log(f"[Worker-{worker_id}] ⚠️ Pre-login failed, will retry on first document")
    except Exception as login_error:
        log(f"[Worker-{worker_id}] Pre-login error: {login_error} - will retry on first document")
    finally:
        # Signal that this worker has completed login attempt
        worker_login_events[worker_id].set()
    
    while True:
        try:
            queue_item = processing_queue.get()
            
            if queue_item is None:  # Shutdown signal
                log(f"Worker {worker_id} shutting down")
                break
            
            # If there are multiple items in queue, add delay to prevent server overload
            queue_size = processing_queue.qsize()
            if queue_size >= 2:
                delay_seconds = 5 * (worker_id - 1)  # Worker 1: 0s, Worker 2: 5s, Worker 3: 10s
                if delay_seconds > 0:
                    log(f"Worker {worker_id} waiting {delay_seconds}s to prevent server overload (queue size: {queue_size})...")
                    time.sleep(delay_seconds)
            
            log(f"Worker {worker_id} processing document for user {queue_item['user_id']}")
            
            try:
                bot.send_message(
                    queue_item['user_id'], 
                    f"📄 Your document is now being processed by Worker {worker_id}..."
                )
            except Exception as msg_error:
                log(f"Error sending processing message: {msg_error}")
            
            # Process the document
            try:
                # Update queue item status
                queue_item['status'] = 'processing'
                queue_item['started_time'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                queue_item['worker_id'] = worker_id

                # Pass the bot instance to the processor
                submission_info = process_turnitin(queue_item['file_path'], queue_item['user_id'], bot)
                log(f"Worker {worker_id} successfully processed document for user {queue_item['user_id']}")

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
    """Start all 3 document processing worker threads"""
    global worker_threads
    
    # Start 3 workers initially - they will wait for tasks in queue
    for worker_id in range(1, MAX_WORKERS + 1):
        worker = threading.Thread(
            target=process_documents_worker, 
            args=(worker_id,),
            daemon=True,
            name=f"Worker-{worker_id}"
        )
        worker.start()
        worker_threads.append(worker)
        log(f"Worker {worker_id} started")
        
        # Stagger startup by 2 seconds to avoid simultaneous initialization
        if worker_id < MAX_WORKERS:
            time.sleep(2)

def create_main_menu():
    """Create main menu keyboard"""
    markup = types.InlineKeyboardMarkup(row_width=2)
    
    markup.add(
        types.InlineKeyboardButton(" Document Based", callback_data="document_plans")
    )
    markup.add(
        types.InlineKeyboardButton("📊 My Subscription", callback_data="my_subscription"),
        types.InlineKeyboardButton("📜 My History", callback_data="my_history")
    )
    markup.add(
        types.InlineKeyboardButton("ℹ️ Help", callback_data="help")
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
        
        # All 3 workers are running from startup, no need to scale
        # scale_workers()
        
        # Notify user
        if queue_position == 1:
            queue_message = "📄 <b>Document queued for processing</b>\n\n🚀 Your document will be processed next."
        else:
            estimated_wait = (queue_position - 1) * 3
            queue_message = f"📄 <b>Document queued for processing</b>\n\n📊 Position: <b>{queue_position}</b>\n⏳ Estimated wait: <b>{estimated_wait} minutes</b>"
        
        bot.send_message(message.chat.id, queue_message)
        log(f"Added Google Drive document to queue for user {message.chat.id}. Queue size: {queue_position}")
        
    except Exception as e:
        bot.reply_to(message, f"❌ Failed to process Google Drive link: {e}")
        log(f"Error handling Google Drive link: {e}")

def process_user_document(message):
    """Process uploaded document through Turnitin"""
    try:
        log(f"Received document from user {message.chat.id}: {message.document.file_name}")
        
        # Check file size (Telegram limit: 20 MB for bot uploads)
        MAX_FILE_SIZE = 20 * 1024 * 1024  # 20 MB in bytes
        file_size = message.document.file_size
        
        if file_size > MAX_FILE_SIZE:
            size_mb = file_size / (1024 * 1024)
            bot.reply_to(
                message, 
                f"❌ <b>File Too Large</b>\n\n"
                f"📁 Your file: <b>{size_mb:.2f} MB</b>\n"
                f"📊 Maximum allowed: <b>20 MB</b>\n\n"
                f"💡 Please compress your document or split it into smaller files."
            )
            log(f"File rejected: {file_size / (1024 * 1024):.2f} MB (exceeds 20 MB limit)")
            return
        
        # Download file
        file_info = bot.get_file(message.document.file_id)
        if not file_info:
            bot.reply_to(message, "❌ Failed to get file information. Please try again.")
            return
            
        downloaded_file = bot.download_file(file_info.file_path)
        if not downloaded_file:
            bot.reply_to(message, "❌ Failed to download file. Please try again.")
            return
        
        # Save file
        original_filename = message.document.file_name or "document"
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        new_filename = f"{message.chat.id}_{timestamp}_{original_filename}"
        
        upload_dir = "uploads"
        os.makedirs(upload_dir, exist_ok=True)
        file_path = os.path.join(upload_dir, new_filename)
        
        with open(file_path, 'wb') as f:
            f.write(downloaded_file)
        
        log(f"Saved document to {file_path}")
        
        # Add to processing queue
        queue_item = {
            'user_id': message.chat.id,
            'file_path': file_path,
            'original_filename': original_filename,
            'added_time': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            'status': 'queued'
        }
        
        processing_queue.put(queue_item)
        
        # All 3 workers are running from startup, no need to scale
        # scale_workers()
        
        queue_position = processing_queue.qsize()
        
        # Notify user
        if queue_position == 1:
            queue_message = "📄 <b>Document queued for processing</b>\n\n🚀 Your document will be processed next."
        else:
            estimated_wait = (queue_position - 1) * 3  # 3 minutes per document (more realistic)
            queue_message = f"📄 <b>Document queued for processing</b>\n\n📊 Position: <b>{queue_position}</b>\n⏳ Estimated wait: <b>{estimated_wait} minutes</b>\n\n💡 You will receive updates as your document progresses."

        bot.send_message(message.chat.id, queue_message)
        log(f"Added document '{original_filename}' to queue for user {message.chat.id}. Queue size: {queue_position}, Position: {queue_position}")
        
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
        if sub_type == "monthly":
            end_date = datetime.fromisoformat(user_info["end_date"]).strftime("%Y-%m-%d")
            welcome_text = f"<b>Welcome back!</b>\n\nYour monthly subscription is active until: <b>{end_date}</b>\n\nSend me a document to get Turnitin reports!"
        else:
            docs_remaining = user_info["documents_remaining"]
            welcome_text = f"<b>Welcome back!</b>\n\nYou have <b>{docs_remaining}</b> document(s) remaining.\n\nSend me a document to get Turnitin reports!"
        
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
• Upload file directly (max 20 MB)
• Send Google Drive link (max 100 MB)

<b>Example Google Drive link:</b>
https://drive.google.com/file/d/YOUR_FILE_ID/view

💡 Make sure file sharing is set to "Anyone with the link"!"""
    
    bot.send_message(request_data["user_id"], user_message)
    bot.reply_to(message, f"✅ Subscription approved for user {request_data['user_id']}")

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

@bot.message_handler(func=lambda message: message.text and 'drive.google.com' in message.text)
def handle_google_drive_link(message):
    """Handle Google Drive links"""
    user_id = message.from_user.id
    
    log(f"DEBUG: Google Drive link received from user {user_id}")
    
    # Admin has unlimited access
    if user_id in ADMIN_TELEGRAM_IDS:
        process_google_drive_link(message, message.text.strip())
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
    
    # Process the Google Drive link
    process_google_drive_link(message, message.text.strip())

@bot.message_handler(content_types=['document'])
def handle_document(message):
    """Handle document uploads"""
    user_id = message.from_user.id
    
    log(f"DEBUG: Document received from user {user_id}")
    
    # Admin has unlimited access
    if user_id in ADMIN_TELEGRAM_IDS:
        process_user_document(message)
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
        
        remaining = user_data["documents_remaining"]
        bot.reply_to(message, f"📄 Processing document... ({remaining} documents remaining)")
    else:
        bot.reply_to(message, "📄 Processing your document...")
    
    # Process the document
    process_user_document(message)

if __name__ == "__main__":
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
