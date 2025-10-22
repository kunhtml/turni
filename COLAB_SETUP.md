# Turnitin Bot on Google Colab - Setup Guide

## 📋 Prerequisites

- Google Account
- Google Colab Access (https://colab.research.google.com/)
- Telegram Bot Token (from @BotFather)
- Admin Telegram ID
- Turnitin Email & Password

## 🚀 Step-by-Step Setup

### Step 1: Clone Repository to Colab

```python
!git clone https://github.com/your-username/turnitin_bot-main.git
%cd turnitin_bot-main
```

### Step 2: Install Dependencies

```python
!pip install -q playwright pyTelegramBotAPI python-dotenv python-telegram-bot requests gdown google-auth google-auth-oauthlib google-auth-httplib2 google-api-python-client pytz
!playwright install chromium
```

### Step 3: Create .env File

```python
from google.colab import files
import os

# Create .env file with your configuration
env_content = """TELEGRAM_BOT_TOKEN=YOUR_BOT_TOKEN
ADMIN_TELEGRAM_ID=YOUR_ADMIN_ID
TURNITIN_EMAIL=your_turnitin_email@example.com
TURNITIN_PASSWORD=your_turnitin_password
WEBSHARE_API_TOKEN="""

with open('.env', 'w') as f:
    f.write(env_content)

print("✅ .env file created")
print("\n⚠️  Edit the values above with your actual credentials:")
print("   - TELEGRAM_BOT_TOKEN")
print("   - ADMIN_TELEGRAM_ID")
print("   - TURNITIN_EMAIL")
print("   - TURNITIN_PASSWORD")
```

### Step 4: Create Google Drive Auth (Optional but Recommended)

```python
from google.colab import auth
from google.auth.transport.requests import Request

# Authenticate with Google Drive
auth.authenticate_user()
print("✅ Google authentication successful")
```

### Step 5: Create Persistent Storage Directories

```python
import os

# Create necessary directories
os.makedirs('uploads', exist_ok=True)
os.makedirs('downloads', exist_ok=True)
os.makedirs('cookies', exist_ok=True)

print("✅ Directories created")
```

### Step 6: Run the Bot

```python
# First, update .env with your credentials before running this cell

import subprocess
import threading
import time

# Run the bot in background
!python main.py
```

### Step 7: Keep Bot Running (Optional)

To prevent Colab from disconnecting, you can use ngrok or keep the cell running:

```python
# Option 1: Simple keep-alive
import time
try:
    while True:
        time.sleep(60)
        print(f"Bot running at {time.strftime('%Y-%m-%d %H:%M:%S')}")
except KeyboardInterrupt:
    print("\n⏹️  Bot stopped")
```

## 🔧 Alternative: Upload ZIP File

If you want to upload your entire bot folder:

```python
from google.colab import files
import zipfile
import os

# Step 1: Upload your bot ZIP file
uploaded = files.upload()

# Step 2: Extract it
for filename in uploaded.keys():
    zipfile.ZipFile(filename).extractall()
    print(f"✅ Extracted: {filename}")

# Step 3: Navigate to folder
import os
folders = [f for f in os.listdir('.') if os.path.isdir(f)]
bot_folder = [f for f in folders if 'bot' in f.lower()][0]
%cd {bot_folder}

# Step 4: Install requirements
!pip install -q -r requirements.txt
!playwright install chromium
```

## 📝 Complete Notebook Code

Here's a complete working notebook you can copy-paste:

```python
# ============================================
# TURNITIN BOT - GOOGLE COLAB SETUP
# ============================================

# 1. Clone repository
!git clone https://github.com/your-username/turnitin_bot-main.git
%cd turnitin_bot-main

# 2. Install dependencies
print("📦 Installing dependencies...")
!pip install -q playwright pyTelegramBotAPI python-dotenv python-telegram-bot requests gdown google-auth google-auth-oauthlib google-auth-httplib2 google-api-python-client pytz
!playwright install chromium
print("✅ Dependencies installed")

# 3. Create .env file
print("\n📝 Creating .env file...")
env_content = """TELEGRAM_BOT_TOKEN=YOUR_TELEGRAM_BOT_TOKEN
ADMIN_TELEGRAM_ID=YOUR_ADMIN_ID
TURNITIN_EMAIL=your_email@example.com
TURNITIN_PASSWORD=your_password"""

with open('.env', 'w') as f:
    f.write(env_content)

print("⚠️  IMPORTANT: Edit .env values before running the bot!")
print("   Replace: YOUR_TELEGRAM_BOT_TOKEN, YOUR_ADMIN_ID, etc.")

# 4. Create directories
import os
os.makedirs('uploads', exist_ok=True)
os.makedirs('downloads', exist_ok=True)
os.makedirs('cookies', exist_ok=True)
print("\n✅ Directories created")

# 5. Run the bot
print("\n🚀 Starting bot...")
!python main.py
```

## ⚠️ Important Notes for Colab

1. **Timeout Issues:**
   - Colab disconnects after 30 mins of inactivity
   - Use ngrok or keep-alive scripts to maintain connection

2. **File Storage:**
   - `/content/` - Temporary storage (cleared after session)
   - Use Google Drive for persistent storage

3. **Clipboard Access:**
   - Colab can't access system clipboard
   - Edit .env manually in Colab editor

4. **Performance:**
   - Free tier: Limited resources
   - Pro tier: More stable and faster

## 🔗 Google Drive Integration

To use Google Drive with Colab:

```python
from google.colab import auth
import gspread

# Authenticate
auth.authenticate_user()

# Now your bot can access Google Drive for report uploads
```

## 📊 Monitor Bot Activity

```python
import os
import json
from datetime import datetime

# Check subscription status
if os.path.exists('subscriptions.json'):
    with open('subscriptions.json', 'r') as f:
        subs = json.load(f)
    print(f"📊 Total users: {len(subs)}")
    for user_id, data in subs.items():
        print(f"  - User {user_id}: {data.get('type', 'unknown')} plan")

# Check pending requests
if os.path.exists('pending_requests.json'):
    with open('pending_requests.json', 'r') as f:
        requests = json.load(f)
    print(f"📋 Pending requests: {len(requests)}")
```

## 🛠️ Troubleshooting

| Issue | Solution |
|-------|----------|
| Bot disconnects | Use ngrok or Pro Colab |
| Playwright fails | Run `!playwright install chromium` again |
| .env not found | Verify file is in root directory with `!ls -la` |
| Port conflict | Change port in config or use ngrok |
| Memory full | Restart kernel and check file sizes |

## 💡 Pro Tips

1. **Use Google Drive for persistent storage:**
   ```python
   from google.colab import drive
   drive.mount('/content/drive')
   ```

2. **Run in background with nohup:**
   ```python
   !nohup python main.py > bot.log 2>&1 &
   ```

3. **Monitor logs:**
   ```python
   !tail -f bot.log
   ```

4. **Check resources:**
   ```python
   !nvidia-smi  # GPU info
   !free -h     # Memory info
   ```

---

**Happy coding! 🎉**
