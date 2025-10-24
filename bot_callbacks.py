import time
from datetime import datetime
from telebot import types

def register_callback_handlers(bot, ADMIN_TELEGRAM_ID, MONTHLY_PLANS, DOCUMENT_PLANS, BANK_DETAILS,
                              load_pending_requests, save_pending_requests, load_subscriptions, 
                              save_subscriptions, is_user_subscribed, get_user_subscription_info,
                              create_main_menu, create_monthly_plans_menu, create_document_plans_menu,
                              create_admin_menu, processing_queue, log, get_user_submission_history):
    """Register all callback query handlers"""
    
    @bot.callback_query_handler(func=lambda call: True)
    def callback_query(call):
        """Handle callback queries"""
        user_id = call.from_user.id
        
        # Admin callbacks
        if user_id == ADMIN_TELEGRAM_ID:
            handle_admin_callbacks(call, bot, ADMIN_TELEGRAM_ID, load_subscriptions, 
                                 load_pending_requests, processing_queue, create_admin_menu, log, get_user_submission_history)
            return
        
        # User callbacks
        if call.data == "monthly_plans":
            bot.edit_message_text(
                "<b>Monthly Subscription Plans</b>\n\nChoose your plan:",
                call.message.chat.id,
                call.message.message_id,
                reply_markup=create_monthly_plans_menu()
            )
        
        elif call.data == "document_plans":
            bot.edit_message_text(
                "<b>Document-Based Plans</b>\n\nChoose your plan:",
                call.message.chat.id,
                call.message.message_id,
                reply_markup=create_document_plans_menu()
            )
        
        elif call.data == "my_subscription":
            show_user_subscription(call, bot, is_user_subscribed, get_user_subscription_info, 
                                 create_main_menu)
        
        elif call.data == "my_history":
            show_user_history(call, bot, get_user_subscription_history, create_main_menu)
        
        elif call.data == "check_id":
            show_user_id(call, bot, create_main_menu)
        
        elif call.data == "help":
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
• Or send a Google Drive link up to 100MB
    Hoặc gửi link Google Drive tối đa 100MB
• The bot generates: Similarity + AI Writing (if available)
    Hệ thống tạo: Similarity + AI Writing (nếu khả dụng)

<b>3) Supported formats / Định dạng hỗ trợ</b>
• PDF, DOC, DOCX, TXT, RTF, ODT, HTML

<b>4) Support / Liên hệ hỗ trợ</b>
• WhatsApp: +94702947854
"""
            
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton("⬅️ Back", callback_data="back_to_main"))
            
            bot.edit_message_text(
                help_text,
                call.message.chat.id,
                call.message.message_id,
                reply_markup=markup
            )
        
        elif call.data == "back_to_main":
            welcome_text = """🤖 <b>Turnitin Report Bot</b>

💳 <b>Choose your subscription plan:</b>"""
            
            bot.edit_message_text(
                welcome_text,
                call.message.chat.id,
                call.message.message_id,
                reply_markup=create_main_menu()
            )
        
        elif call.data.startswith("request_monthly_"):
            plan_id = call.data.replace("request_monthly_", "")
            handle_monthly_request(call, plan_id, bot, ADMIN_TELEGRAM_ID, MONTHLY_PLANS, BANK_DETAILS,
                                 load_pending_requests, save_pending_requests)
        
        elif call.data.startswith("request_document_"):
            plan_id = call.data.replace("request_document_", "")
            handle_document_request(call, plan_id, bot, ADMIN_TELEGRAM_ID, DOCUMENT_PLANS, BANK_DETAILS,
                                  load_pending_requests, save_pending_requests)

def show_user_id(call, bot, create_main_menu):
    """Show user their Telegram ID"""
    user_id = call.from_user.id
    username = call.from_user.username or "N/A"
    first_name = call.from_user.first_name or "N/A"
    
    id_text = f"""<b>Your Account Information</b>

<b>Telegram ID:</b> <code>{user_id}</code>
<b>Username:</b> @{username}
<b>Name:</b> {first_name}

💡 Share this ID with admins for account management."""
    
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("⬅️ Back", callback_data="back_to_main"))
    
    bot.edit_message_text(
        id_text,
        call.message.chat.id,
        call.message.message_id,
        reply_markup=markup
    )

def show_user_subscription(call, bot, is_user_subscribed, get_user_subscription_info, create_main_menu):
    """Show user's current subscription details"""
    user_id = call.from_user.id
    is_subscribed, sub_type = is_user_subscribed(user_id)
    
    if not is_subscribed:
        bot.edit_message_text(
            "❌ <b>No Active Subscription</b>\n\nYou don't have an active subscription. Please choose a plan:",
            call.message.chat.id,
            call.message.message_id,
            reply_markup=create_main_menu()
        )
        return
    
    user_info = get_user_subscription_info(user_id)
    
    if sub_type == "time":
        # Time-based subscription (unlimited uploads)
        start_date = datetime.fromisoformat(user_info["start_date"]).strftime("%d %b %Y")
        end_date = datetime.fromisoformat(user_info["end_date"]).strftime("%d %b %Y, %H:%M")
        duration_days = user_info.get("duration_days", "N/A")
        
        subscription_text = f"""✅ <b>Active Time-Based Subscription</b>

⏰ <b>Duration:</b> {duration_days} days
📅 <b>Start Date:</b> {start_date}
📆 <b>End Date:</b> {end_date}
💳 <b>Status:</b> Active
📤 <b>Uploads:</b> Unlimited

📄 Send me a document to get your Turnitin reports!"""
    
    elif sub_type == "monthly":
        # Monthly subscription
        end_date = datetime.fromisoformat(user_info["end_date"]).strftime("%Y-%m-%d")
        plan_name = user_info.get("plan_name", "Monthly")
        
        subscription_text = f"""✅ <b>Active Monthly Subscription</b>

📅 <b>Plan:</b> {plan_name}
📆 <b>End Date:</b> {end_date}
💳 <b>Status:</b> Active

📄 Send me a document to get your Turnitin reports!"""
    
    elif sub_type == "document":
        # Document-based subscription
        docs_remaining = user_info.get("documents_remaining", 0)
        docs_total = user_info.get("documents_total", docs_remaining)
        docs_used = docs_total - docs_remaining
        
        subscription_text = f"""✅ <b>Active Document Subscription</b>

📄 <b>Documents Remaining:</b> {docs_remaining}
📊 <b>Documents Used:</b> {docs_used}/{docs_total}
💳 <b>Status:</b> Active

📄 Send me a document to get your Turnitin reports!"""
    
    else:
        # Unknown subscription type (fallback)
        subscription_text = """✅ <b>Active Subscription</b>

💳 <b>Status:</b> Active

📄 Send me a document to get your Turnitin reports!"""
    
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("⬅️ Back", callback_data="back_to_main"))
    
    bot.edit_message_text(
        subscription_text,
        call.message.chat.id,
        call.message.message_id,
        reply_markup=markup
    )

def handle_monthly_request(call, plan_id, bot, ADMIN_TELEGRAM_ID, MONTHLY_PLANS, BANK_DETAILS,
                          load_pending_requests, save_pending_requests):
    """Handle monthly subscription request"""
    user_id = call.from_user.id
    plan_info = MONTHLY_PLANS[plan_id]
    
    # Save pending request
    pending_requests = load_pending_requests()
    request_id = f"{user_id}_{int(time.time())}"
    
    pending_requests[request_id] = {
        "user_id": user_id,
        "username": call.from_user.username or "No username",
        "first_name": call.from_user.first_name or "No name",
        "plan_type": "monthly",
        "plan_id": plan_id,
        "plan_name": plan_info["name"],
        "price": plan_info["price"],
        "duration": plan_info["duration"],
        "request_date": datetime.now().isoformat(),
        "status": "pending"
    }
    
    save_pending_requests(pending_requests)
    
    # Message to user
    user_message = f"""📋 <b>Subscription Request Submitted</b>

📅 <b>Plan:</b> {plan_info['name']}
💰 <b>Price:</b> Rs.{plan_info['price']}
🆔 <b>Your Telegram ID:</b> <code>{user_id}</code>

💳 <b>Payment Details:</b>
{BANK_DETAILS}

✅ Your request has been sent to admin for approval.
📧 You'll be notified once approved."""
    
    bot.edit_message_text(
        user_message,
        call.message.chat.id,
        call.message.message_id
    )
    
    # Notify admin
    admin_message = f"""📢 <b>New Subscription Request</b>

👤 <b>User:</b> {call.from_user.first_name} (@{call.from_user.username or 'No username'})
🆔 <b>Telegram ID:</b> {user_id}
📅 <b>Plan:</b> {plan_info['name']}
💰 <b>Price:</b> Rs.{plan_info['price']}
📝 <b>Request ID:</b> {request_id}

Use /approve {request_id} to approve this request."""
    
    bot.send_message(ADMIN_TELEGRAM_ID, admin_message)

def handle_document_request(call, plan_id, bot, ADMIN_TELEGRAM_ID, DOCUMENT_PLANS, BANK_DETAILS,
                           load_pending_requests, save_pending_requests):
    """Handle document-based subscription request"""
    user_id = call.from_user.id
    plan_info = DOCUMENT_PLANS[plan_id]
    
    # Save pending request
    pending_requests = load_pending_requests()
    request_id = f"{user_id}_{int(time.time())}"
    
    pending_requests[request_id] = {
        "user_id": user_id,
        "username": call.from_user.username or "No username",
        "first_name": call.from_user.first_name or "No name",
        "plan_type": "document",
        "plan_id": plan_id,
        "plan_name": plan_info["name"],
        "price": plan_info["price"],
        "documents": plan_info["documents"],
        "request_date": datetime.now().isoformat(),
        "status": "pending"
    }
    
    save_pending_requests(pending_requests)
    
    # Message to user
    user_message = f"""📋 <b>Subscription Request Submitted</b>

📄 <b>Plan:</b> {plan_info['name']}
💰 <b>Price:</b> Rs.{plan_info['price']}
🆔 <b>Your Telegram ID:</b> <code>{user_id}</code>

💳 <b>Payment Details:</b>
{BANK_DETAILS}

✅ Your request has been sent to admin for approval.
📧 You'll be notified once approved."""
    
    bot.edit_message_text(
        user_message,
        call.message.chat.id,
        call.message.message_id
    )
    
    # Notify admin
    admin_message = f"""📢 <b>New Document Subscription Request</b>

👤 <b>User:</b> {call.from_user.first_name} (@{call.from_user.username or 'No username'})
🆔 <b>Telegram ID:</b> {user_id}
📄 <b>Plan:</b> {plan_info['name']}
💰 <b>Price:</b> Rs.{plan_info['price']}
📝 <b>Request ID:</b> {request_id}

Use /approve {request_id} to approve this request."""
    
    bot.send_message(ADMIN_TELEGRAM_ID, admin_message)

def handle_admin_callbacks(call, bot, ADMIN_TELEGRAM_ID, load_subscriptions, 
                          load_pending_requests, processing_queue, create_admin_menu, log, get_user_submission_history):
    """Handle admin callback queries"""
    if call.data == "admin_view_subs":
        show_all_subscriptions(call, bot, load_subscriptions, create_admin_menu)
    elif call.data == "admin_pending":
        show_pending_requests(call, bot, load_pending_requests, create_admin_menu)
    elif call.data == "admin_edit":
        show_edit_subscription_menu(call, bot, create_admin_menu)
    elif call.data == "admin_history":
        show_admin_history_prompt(call, bot, create_admin_menu)
    elif call.data == "admin_stats":
        show_admin_stats(call, bot, load_subscriptions, load_pending_requests, 
                        processing_queue, create_admin_menu)
    elif call.data == "admin_queue":
        show_processing_queue(call, bot, processing_queue, create_admin_menu)
    elif call.data == "admin_bot_stats":
        show_bot_stats(call, bot, create_admin_menu)
    elif call.data == "back_to_admin":
        bot.edit_message_text(
            "<b>Admin Panel</b>\n\nWelcome admin! Choose an option:",
            call.message.chat.id,
            call.message.message_id,
            reply_markup=create_admin_menu()
        )

def show_all_subscriptions(call, bot, load_subscriptions, create_admin_menu):
    """Show all active subscriptions to admin with detailed statistics"""
    subscriptions = load_subscriptions()
    
    if not subscriptions:
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("⬅️ Back", callback_data="back_to_admin"))
        bot.edit_message_text(
            "📋 <b>No Active Subscriptions</b>",
            call.message.chat.id,
            call.message.message_id,
            reply_markup=markup
        )
        return
    
    # Count users by subscription type
    time_based_users = 0
    document_based_users = 0
    monthly_users = 0
    total_active = 0
    
    subscription_text = "👥 <b>Active Subscriptions Summary</b>\n\n"
    
    for user_id, user_data in subscriptions.items():
        is_active = False
        
        # Check time-based subscription
        if user_data.get("type") == "time" and "end_date" in user_data:
            end_date = datetime.fromisoformat(user_data["end_date"])
            if datetime.now() < end_date:
                time_based_users += 1
                is_active = True
        
        # Check monthly subscription
        elif "end_date" in user_data and user_data.get("type") != "time":
            end_date = datetime.fromisoformat(user_data["end_date"])
            if datetime.now() < end_date:
                monthly_users += 1
                is_active = True
        
        # Check document-based subscription
        if "documents_remaining" in user_data and user_data["documents_remaining"] > 0:
            if not is_active:  # Don't double count
                document_based_users += 1
                is_active = True
        
        if is_active:
            total_active += 1
    
    subscription_text += f"📊 <b>TỔNG SỐ NGƯỜI DÙNG ĐANG SỬ DỤNG:</b> <b>{total_active}</b>\n\n"
    subscription_text += f"⏰ Time-based (Theo thời gian): {time_based_users} người\n"
    subscription_text += f"📅 Monthly (Theo tháng): {monthly_users} người\n"
    subscription_text += f"📄 Document-based (Theo lượt): {document_based_users} người\n\n"
    subscription_text += "─────────────────────\n\n"
    subscription_text += "<b>Chi tiết người dùng:</b>\n\n"
    
    # List individual users
    for user_id, user_data in subscriptions.items():
        user_type = user_data.get("type", "unknown")
        
        if user_type == "time" and "end_date" in user_data:
            end_date = datetime.fromisoformat(user_data["end_date"])
            if datetime.now() < end_date:
                days_remaining = (end_date - datetime.now()).days
                subscription_text += f"🆔 <code>{user_id}</code>\n"
                subscription_text += f"📅 Time-based: {days_remaining} ngày còn lại\n"
                subscription_text += f"⏰ Hết hạn: {end_date.strftime('%d/%m/%Y %H:%M')}\n\n"
        
        elif "end_date" in user_data and user_type != "time":
            end_date = datetime.fromisoformat(user_data["end_date"])
            if datetime.now() < end_date:
                subscription_text += f"🆔 <code>{user_id}</code>\n"
                subscription_text += f"📅 {user_data.get('plan_name', 'Monthly')}\n"
                subscription_text += f"⏰ Hết hạn: {end_date.strftime('%d/%m/%Y')}\n\n"
        
        elif "documents_remaining" in user_data and user_data["documents_remaining"] > 0:
            subscription_text += f"🆔 <code>{user_id}</code>\n"
            subscription_text += f"📄 Docs: {user_data['documents_remaining']} lượt còn lại\n\n"
    
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("⬅️ Back", callback_data="back_to_admin"))
    
    bot.edit_message_text(
        subscription_text,
        call.message.chat.id,
        call.message.message_id,
        reply_markup=markup,
        parse_mode='HTML'
    )

def show_pending_requests(call, bot, load_pending_requests, create_admin_menu):
    """Show pending subscription requests to admin"""
    pending_requests = load_pending_requests()
    pending_only = {k: v for k, v in pending_requests.items() if v["status"] == "pending"}
    
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("⬅️ Back", callback_data="back_to_admin"))
    
    if not pending_only:
        bot.edit_message_text(
            "📋 <b>No Pending Requests</b>",
            call.message.chat.id,
            call.message.message_id,
            reply_markup=markup
        )
        return
    
    requests_text = "📋 <b>Pending Requests</b>\n\n"
    
    for request_id, request_data in pending_only.items():
        requests_text += f"🆔 {request_data['user_id']}\n"
        requests_text += f"👤 {request_data['first_name']}\n"
        requests_text += f"📅 {request_data['plan_name']}\n"
        requests_text += f"💰 Rs.{request_data['price']}\n"
        requests_text += f"📝 ID: {request_id}\n\n"
    
    requests_text += "\nUse /approve [request_id] to approve"
    
    bot.edit_message_text(
        requests_text,
        call.message.chat.id,
        call.message.message_id,
        reply_markup=markup
    )

def show_admin_stats(call, bot, load_subscriptions, load_pending_requests, 
                    processing_queue, create_admin_menu):
    """Show admin statistics"""
    subscriptions = load_subscriptions()
    pending_requests = load_pending_requests()
    
    active_monthly = 0
    active_document = 0
    total_pending = len([r for r in pending_requests.values() if r["status"] == "pending"])
    queue_size = processing_queue.qsize()
    
    for user_data in subscriptions.values():
        if "end_date" in user_data:
            end_date = datetime.fromisoformat(user_data["end_date"])
            if datetime.now() < end_date:
                active_monthly += 1
        
        if "documents_remaining" in user_data and user_data["documents_remaining"] > 0:
            active_document += 1
    
    stats_text = f"""📊 <b>Bot Statistics</b>

📅 <b>Active Monthly Subscriptions:</b> {active_monthly}
📄 <b>Active Document Subscriptions:</b> {active_document}
⏳ <b>Pending Requests:</b> {total_pending}
📄 <b>Processing Queue:</b> {queue_size} documents
👥 <b>Total Users in System:</b> {len(subscriptions)}

📈 <b>Generated:</b> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"""
    
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("⬅️ Back", callback_data="back_to_admin"))
    
    bot.edit_message_text(
        stats_text,
        call.message.chat.id,
        call.message.message_id,
        reply_markup=markup
    )

def show_processing_queue(call, bot, processing_queue, create_admin_menu):
    """Show current processing queue to admin"""
    import os
    queue_list = list(processing_queue.queue)
    
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("⬅️ Back", callback_data="back_to_admin"))
    
    if not queue_list:
        bot.edit_message_text(
            "📄 <b>Processing Queue</b>\n\nQueue is empty.",
            call.message.chat.id,
            call.message.message_id,
            reply_markup=markup
        )
        return
    
    queue_text = f"📄 <b>Processing Queue ({len(queue_list)} items)</b>\n\n"
    
    for i, item in enumerate(queue_list[:10]):  # Show first 10 items
        status = item.get('status', 'pending')
        queue_text += f"{i+1}. User ID: {item['user_id']}\n"
        queue_text += f"   File: {os.path.basename(item['file_path'])}\n"
        queue_text += f"   Status: {status}\n"
        queue_text += f"   Added: {item.get('added_time', 'Unknown')}\n\n"
    
    if len(queue_list) > 10:
        queue_text += f"... and {len(queue_list) - 10} more items"
    
    bot.edit_message_text(
        queue_text,
        call.message.chat.id,
        call.message.message_id,
        reply_markup=markup
    )

def show_bot_stats(call, bot, create_admin_menu):
    """Show optimized bot connection statistics"""
    try:
        bot_stats = bot.get_stats()
        
        stats_text = f"""🔧 <b>Bot Connection Statistics</b>

🌐 <b>Session Active:</b> {bot_stats['session_active']}
📈 <b>Total Requests:</b> {bot_stats['total_requests']}
📊 <b>Connection Pool:</b> Active
🔄 <b>Retry Strategy:</b> Enabled
⚡ <b>Rate Limiting:</b> Active

📈 <b>Generated:</b> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"""
        
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("⬅️ Back", callback_data="back_to_admin"))
        
        bot.edit_message_text(
            stats_text,
            call.message.chat.id,
            call.message.message_id,
            reply_markup=markup
        )
    except Exception as e:
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("⬅️ Back", callback_data="back_to_admin"))
        
        bot.edit_message_text(
            f"❌ <b>Error retrieving bot stats:</b>\n{str(e)}",
            call.message.chat.id,
            call.message.message_id,
            reply_markup=markup
        )

def show_edit_subscription_menu(call, bot, create_admin_menu):
    """Show edit subscription instructions to admin"""
    edit_text = """✏️ <b>Edit Subscription</b>

Để chỉnh sửa subscription cho người dùng, sử dụng các lệnh sau:

<b>1. Thêm số ngày sử dụng:</b>
<code>/active [user_id] [số_ngày]</code>
Ví dụ: <code>/active 123456789 30</code>
→ Thêm 30 ngày cho user

<b>2. Dừng subscription:</b>
<code>/stop [user_id]</code>
Ví dụ: <code>/stop 123456789</code>
→ Hủy subscription của user

<b>3. Kiểm tra thông tin user:</b>
<code>/check [user_id]</code>
Ví dụ: <code>/check 123456789</code>
→ Xem chi tiết subscription

<b>4. Xóa cooldown:</b>
<code>/clearcooldown [user_id]</code>
Ví dụ: <code>/clearcooldown 123456789</code>
→ Cho phép user gửi file ngay lập tức

<b>5. Xem lịch sử:</b>
<code>/viewhistory [user_id]</code>
Ví dụ: <code>/viewhistory 123456789</code>
→ Xem lịch sử submit của user"""
    
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("⬅️ Back", callback_data="back_to_admin"))
    
    bot.edit_message_text(
        edit_text,
        call.message.chat.id,
        call.message.message_id,
        reply_markup=markup,
        parse_mode='HTML'
    )

def show_user_history(call, bot, get_user_submission_history, create_main_menu):
    """Show user's submission history"""
    user_id = call.from_user.id
    history = get_user_submission_history(user_id, limit=10)
    
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("⬅️ Back", callback_data="back_to_main"))
    
    if not history:
        bot.edit_message_text(
            "📜 <b>Submission History</b>\n\n"
            "📭 No submissions yet.\n\n"
            "Upload your first document to get started!",
            call.message.chat.id,
            call.message.message_id,
            reply_markup=markup
        )
        return
    
    # Build history message
    history_text = "📜 <b>Your Recent Submissions</b>\n\n"
    
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
        history_text += f"   📋 Title: {submission_title}\n"
        history_text += f"   📅 Date: {formatted_date}\n"
        history_text += f"   ✅ Reports: Available\n\n"
    
    history_text += "💡 <b>Note:</b> Reports are deleted after sending. To get reports again, please re-upload the document."
    
    bot.edit_message_text(
        history_text,
        call.message.chat.id,
        call.message.message_id,
        reply_markup=markup
    )

def show_admin_history_prompt(call, bot, create_admin_menu):
    """Prompt admin to enter user ID to view history"""
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton("⬅️ Back", callback_data="back_to_admin"))
    
    bot.edit_message_text(
        "📜 <b>View User History</b>\n\n"
        "Please send the User ID to view their submission history.\n\n"
        "<b>Format:</b> /viewhistory [user_id]\n"
        "<b>Example:</b> /viewhistory 6072090845",
        call.message.chat.id,
        call.message.message_id,
        reply_markup=markup
    )