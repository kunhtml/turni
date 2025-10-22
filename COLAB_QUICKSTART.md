# 🚀 Chạy Turnitin Bot trên Google Colab - Hướng Dẫn Nhanh

## 📱 Yêu Cầu

1. **Google Account** - Có sẵn
2. **Telegram Bot Token** - Lấy từ @BotFather
3. **Admin ID** - Lấy từ lệnh `/id` trên Telegram
4. **Turnitin Email & Password** - Của bạn

## ⚡ Quick Start (5 phút)

### Bước 1: Mở Google Colab
```
https://colab.research.google.com/
```

### Bước 2: Tạo Notebook Mới
- Click **File** → **New Notebook**

### Bước 3: Copy & Paste Code

Copy toàn bộ code dưới đây vào cell đầu tiên và **Shift + Enter**:

```python
# ============================================
# TURNITIN BOT - SETUP
# ============================================

import os

# Clone repo
!git clone https://github.com/your-repo/turnitin_bot-main.git
%cd turnitin_bot-main

# Install
!pip install -q playwright pyTelegramBotAPI python-dotenv python-telegram-bot requests gdown google-auth google-auth-oauthlib google-auth-httplib2 google-api-python-client pytz
!playwright install chromium

# Create folders
os.makedirs('uploads', exist_ok=True)
os.makedirs('downloads', exist_ok=True)
os.makedirs('cookies', exist_ok=True)

print("✅ Setup hoàn tất!")
```

### Bước 4: Tạo .env File

Tạo cell mới, copy code này:

```python
# Tạo .env với thông tin của bạn
env = """TELEGRAM_BOT_TOKEN=YOUR_TOKEN_HERE
ADMIN_TELEGRAM_ID=YOUR_ID_HERE
TURNITIN_EMAIL=email@example.com
TURNITIN_PASSWORD=password_here"""

with open('.env', 'w') as f:
    f.write(env)

print("✅ .env đã tạo")
print("⚠️  Thay thế YOUR_TOKEN_HERE, YOUR_ID_HERE, etc.")
```

### Bước 5: Chạy Bot

Tạo cell mới:

```python
!python main.py
```

Press **Shift + Enter** - Bot bắt đầu chạy! 🎉

## 📋 Chi Tiết Từng Bước

### Lấy Telegram Bot Token
1. Chat với @BotFather trên Telegram
2. Gửi `/newbot`
3. Tạo bot và lấy token
4. Copy token vào .env

### Lấy Admin ID
1. Chat với bot của bạn
2. Gửi `/id`
3. Bot trả về Telegram ID
4. Copy ID vào .env

### Lấy Turnitin Email & Password
- Dùng email đã đăng ký Turnitin
- Dùng mật khẩu Turnitin của bạn

## ⏱️ Quản Lý Thời Gian

Google Colab sẽ disconnect nếu:
- Quá 30 phút không hoạt động (free tier)
- Hoặc người dùng đóng tab

### Giải Pháp 1: Ngrok (Recommend)

```python
# Cài ngrok
!pip install pyngrok -q

# Copy auth token từ https://dashboard.ngrok.com/
from pyngrok import ngrok
ngrok.set_auth_token("YOUR_NGROK_TOKEN")

# Expose bot
public_url = ngrok.connect(8000)
print(f"Bot URL: {public_url}")
```

### Giải Pháp 2: Keep-Alive Script

```python
import time
import threading

def keep_alive():
    while True:
        time.sleep(3600)  # Mỗi 1 giờ
        print(f"✅ Bot vẫn chạy...")

# Chạy background
threading.Thread(target=keep_alive, daemon=True).start()

# Sau đó chạy bot
!python main.py
```

## 📊 Kiểm Tra Trạng Thái

Chạy trong cell riêng (không dừng bot):

```python
import json
import os

print("📊 STATUS CHECK")
print("=" * 50)

# Users
if os.path.exists('subscriptions.json'):
    with open('subscriptions.json') as f:
        users = json.load(f)
    print(f"👥 Users: {len(users)}")

# Pending requests
if os.path.exists('pending_requests.json'):
    with open('pending_requests.json') as f:
        reqs = json.load(f)
    print(f"📋 Pending: {len(reqs)}")

# History
if os.path.exists('submission_history.json'):
    with open('submission_history.json') as f:
        hist = json.load(f)
    total = sum(len(h) for h in hist.values())
    print(f"📝 Submissions: {total}")
```

## 🔧 Lệnh Hữu Ích

```python
# Xem file
!ls -la

# Xem nội dung .env
!cat .env

# Xem logs (nếu lưu)
!tail -100 bot.log

# Kiểm tra memory
!free -h

# Kill process (nếu cần)
!pkill -f python
```

## ⚠️ Lưu Ý Quan Trọng

1. **Lần đầu chạy sẽ mất 5-10 phút** vì cài dependencies
2. **Sau lần đầu chỉ mất 2-3 phút** để khởi động
3. **Dữ liệu subscriptions.json sẽ mất** khi Colab disconnect
   - Dùng Google Drive để backup: `!cp subscriptions.json /content/drive/My\ Drive/`
4. **Bot sẽ bị disconnect** sau 30 phút không hoạt động (free tier)
5. **Playwright cần thời gian** để khởi động browser lần đầu

## 💾 Backup to Google Drive

```python
from google.colab import drive

# Mount
drive.mount('/content/drive')

# Backup
!cp subscriptions.json /content/drive/My\ Drive/turnitin_subscriptions.json
!cp pending_requests.json /content/drive/My\ Drive/turnitin_pending.json
!cp submission_history.json /content/drive/My\ Drive/turnitin_history.json

print("✅ Backup complete!")
```

## 🆘 Troubleshooting

| Vấn đề | Giải Pháp |
|--------|----------|
| Bot crash ngay | Check .env values, verify token |
| Playwright fail | Run `!playwright install chromium` again |
| Disconnect sau 30 phút | Dùng ngrok hoặc Colab Pro |
| Memory full | Restart kernel, check file sizes |
| Import error | `!pip install --upgrade package-name` |

## 📞 Support

- **Error:** Xem logs để debug
- **Playwright:** `!playwright install chromium`
- **Memory:** Click **Runtime** → **Restart runtime**

---

**Happy coding! 🎉**

Nếu có lỗi, check file `COLAB_SETUP.md` để hướng dẫn chi tiết hơn.
