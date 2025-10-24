import json
import os
from datetime import datetime, timedelta

COOLDOWN_FILE = "user_cooldowns.json"
COOLDOWN_DURATION_MINUTES = 8  # 8 phút

def load_cooldowns():
    """Load user cooldown data from file"""
    try:
        if os.path.exists(COOLDOWN_FILE):
            with open(COOLDOWN_FILE, "r") as f:
                return json.load(f)
        return {}
    except:
        return {}

def save_cooldowns(data):
    """Save user cooldown data to file"""
    with open(COOLDOWN_FILE, "w") as f:
        json.dump(data, f, indent=2)

def set_user_cooldown(user_id):
    """Set cooldown for a user after they upload a file"""
    cooldowns = load_cooldowns()
    user_id_str = str(user_id)
    
    # Set cooldown end time (current time + 10 minutes)
    cooldown_end = datetime.now() + timedelta(minutes=COOLDOWN_DURATION_MINUTES)
    
    cooldowns[user_id_str] = {
        "cooldown_end": cooldown_end.isoformat(),
        "last_upload": datetime.now().isoformat()
    }
    
    save_cooldowns(cooldowns)

def check_user_cooldown(user_id):
    """
    Check if user is in cooldown period
    
    Returns:
        tuple: (is_in_cooldown: bool, remaining_seconds: int, cooldown_end: datetime or None)
    """
    cooldowns = load_cooldowns()
    user_id_str = str(user_id)
    
    if user_id_str not in cooldowns:
        # No cooldown for this user
        return False, 0, None
    
    cooldown_data = cooldowns[user_id_str]
    cooldown_end = datetime.fromisoformat(cooldown_data["cooldown_end"])
    now = datetime.now()
    
    if now < cooldown_end:
        # User is still in cooldown
        remaining = cooldown_end - now
        remaining_seconds = int(remaining.total_seconds())
        return True, remaining_seconds, cooldown_end
    else:
        # Cooldown expired, clean up
        del cooldowns[user_id_str]
        save_cooldowns(cooldowns)
        return False, 0, None

def clear_user_cooldown(user_id):
    """Manually clear cooldown for a user (admin function)"""
    cooldowns = load_cooldowns()
    user_id_str = str(user_id)
    
    if user_id_str in cooldowns:
        del cooldowns[user_id_str]
        save_cooldowns(cooldowns)
        return True
    return False

def format_remaining_time(seconds):
    """Format remaining seconds into human-readable format"""
    if seconds < 60:
        return f"{seconds} giây"
    else:
        minutes = seconds // 60
        remaining_seconds = seconds % 60
        if remaining_seconds > 0:
            return f"{minutes} phút {remaining_seconds} giây"
        else:
            return f"{minutes} phút"

def get_cooldown_message(remaining_seconds, cooldown_end):
    """Generate user-friendly cooldown message in bilingual format"""
    formatted_time = format_remaining_time(remaining_seconds)
    cooldown_end_str = cooldown_end.strftime("%H:%M:%S")
    
    message = f"""🔒 <b>Upload Cooldown / Thời gian chờ</b>

⏳ <b>Please wait / Vui lòng đợi:</b> {formatted_time}
🕐 <b>Available at / Có thể gửi lại lúc:</b> {cooldown_end_str}

❓ <b>Why? / Tại sao?</b>
To prevent system overload, there is an 8-minute cooldown between uploads.
Để tránh quá tải hệ thống, có thời gian chờ 8 phút giữa các lần gửi file.

✅ You can upload again after the cooldown period.
✅ Bạn có thể gửi file mới sau khi hết thời gian chờ."""
    
    return message
