"""
TURNITIN BOT - GOOGLE COLAB LAUNCHER
Copy this entire script into a Google Colab cell and run it
"""

# ============================================
# CELL 1: Clone and Install
# ============================================

import os
import subprocess
import sys

print("=" * 70)
print("TURNITIN BOT - GOOGLE COLAB SETUP")
print("=" * 70)

# Clone repository
print("\n[1/4] Cloning repository...")
if not os.path.exists('turnitin_bot-main'):
    !git clone https://github.com/your-username/turnitin_bot-main.git
    
%cd turnitin_bot-main

# Install dependencies
print("[2/4] Installing dependencies...")
!pip install -q playwright pyTelegramBotAPI python-dotenv python-telegram-bot requests gdown google-auth google-auth-oauthlib google-auth-httplib2 google-api-python-client pytz

print("[3/4] Installing Playwright browsers...")
!playwright install chromium

print("[4/4] Creating directories...")
import os
os.makedirs('uploads', exist_ok=True)
os.makedirs('downloads', exist_ok=True)
os.makedirs('cookies', exist_ok=True)

print("\n✅ Setup complete!")
print("=" * 70)

# ============================================
# CELL 2: Configure .env
# ============================================

print("\n📝 CONFIGURING BOT")
print("=" * 70)

# Read or create .env
env_template = """TELEGRAM_BOT_TOKEN=YOUR_TELEGRAM_BOT_TOKEN
ADMIN_TELEGRAM_ID=YOUR_ADMIN_TELEGRAM_ID
TURNITIN_EMAIL=your_turnitin_email@example.com
TURNITIN_PASSWORD=your_turnitin_password
WEBSHARE_API_TOKEN="""

if os.path.exists('.env'):
    print("\n✅ .env file exists")
    with open('.env', 'r') as f:
        print("\nCurrent .env content:")
        print(f.read())
else:
    print("\n⚠️  Creating new .env file...")
    with open('.env', 'w') as f:
        f.write(env_template)
    print("✅ .env created with template")

print("\n" + "=" * 70)
print("❗ IMPORTANT: Edit .env file with your credentials:")
print("   1. Get TELEGRAM_BOT_TOKEN from @BotFather")
print("   2. Get ADMIN_TELEGRAM_ID from /id command")
print("   3. Enter Turnitin email and password")
print("=" * 70)

# ============================================
# CELL 3: Authenticate with Google Drive (Optional)
# ============================================

print("\n🔐 GOOGLE AUTHENTICATION")
print("=" * 70)

try:
    from google.colab import auth
    print("Authenticating with Google Drive...")
    auth.authenticate_user()
    print("✅ Google authentication successful")
    
    from google.colab import drive
    drive.mount('/content/drive')
    print("✅ Google Drive mounted at /content/drive")
except Exception as e:
    print(f"⚠️  Google Drive auth skipped: {e}")

print("=" * 70)

# ============================================
# CELL 4: Run the Bot
# ============================================

print("\n🚀 STARTING BOT")
print("=" * 70)
print("The bot is now running in this cell")
print("Messages will appear below as they're processed")
print("To stop the bot, press the ⏹️ button above or Ctrl+C")
print("=" * 70)
print()

try:
    !python main.py
except KeyboardInterrupt:
    print("\n\n⏹️  Bot stopped by user")
except Exception as e:
    print(f"\n❌ Bot error: {e}")

# ============================================
# CELL 5: Monitor Status (Run separately)
# ============================================

"""
Run this cell to check bot status without stopping it

import json
import os
from datetime import datetime

print("📊 BOT STATUS CHECK")
print("=" * 70)
print(f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
print()

# Check subscriptions
if os.path.exists('subscriptions.json'):
    with open('subscriptions.json', 'r') as f:
        subs = json.load(f)
    print(f"✅ Total users: {len(subs)}")
    for user_id, data in subs.items():
        print(f"   - User {user_id}: {data.get('type', 'unknown')} plan")

# Check pending requests
if os.path.exists('pending_requests.json'):
    with open('pending_requests.json', 'r') as f:
        reqs = json.load(f)
    print(f"📋 Pending requests: {len(reqs)}")

# Check submission history
if os.path.exists('submission_history.json'):
    with open('submission_history.json', 'r') as f:
        history = json.load(f)
    total_subs = sum(len(subs) for subs in history.values())
    print(f"📝 Total submissions: {total_subs}")

print("=" * 70)
"""
