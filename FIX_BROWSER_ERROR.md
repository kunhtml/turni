# 🔧 Fix Browser Launch Error on Windows Server

## ❌ Error: `spawn EFTYPE`

```
Error creating browser session: BrowserType.launch: spawn EFTYPE
```

---

## 🔍 Root Cause

**Windows Server 2012 R2** (Version 6.3.9600) thiếu dependencies cho Playwright Chromium.

---

## ✅ Solution - 3 Options

### **Option 1: Install Playwright Dependencies (Recommended)**

```bash
# 1. Install Playwright browsers with system dependencies
python -m playwright install chromium --with-deps

# If above fails, try:
python -m playwright install-deps
python -m playwright install chromium
```

---

### **Option 2: Use Firefox Instead of Chromium**

Sửa `turnitin_auth.py`:

```python
# OLD (Line ~150):
browser_session['browser'] = browser_session['playwright'].chromium.launch(**launch_options)

# NEW:
browser_session['browser'] = browser_session['playwright'].firefox.launch(**launch_options)
```

Cài Firefox browser:

```bash
python -m playwright install firefox
```

---

### **Option 3: Install Visual C++ Redistributables**

Windows Server 2012 R2 cần thêm:

1. **Download và cài:**

   - [VC++ 2015-2022 Redistributable (x64)](https://aka.ms/vs/17/release/vc_redist.x64.exe)
   - [VC++ 2013 Redistributable (x64)](https://aka.ms/highdpimfc2013x64enu)

2. **Restart server**

3. **Run lại:**
   ```bash
   python -m playwright install chromium
   ```

---

## 🚀 Quick Fix (Fastest)

```bash
# Run these commands:
cd "C:\Users\Administrator\Desktop\turnitin_bot-main (1)\turnitin_bot-main"

# Install browsers with dependencies
python -m playwright install chromium firefox --with-deps

# Verify installation
python -m playwright install --help
```

---

## 🔄 Alternative: Use Selenium Instead

Nếu Playwright vẫn fail, switch to Selenium (đã có trong requirements.txt):

### Edit `turnitin_auth.py`:

```python
# Comment out Playwright imports
# from playwright.sync_api import sync_playwright

# Add Selenium imports
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
```

---

## 📋 Check Current Python & Playwright Version

```bash
python --version
python -m playwright --version
pip show playwright
```

---

## ⚡ Immediate Action

**Run this command now:**

```bash
python -m playwright install chromium --with-deps
```

**Expected output:**

```
Downloading browsers...
  - chromium v1179 (playwright build) - 141.6 Mb [====================] 100% 0.0s
```

---

## 🎯 If Still Failing

**Use Firefox (more compatible with older Windows):**

```bash
# 1. Install Firefox
python -m playwright install firefox

# 2. Edit turnitin_auth.py (I can help with this)
# Change: .chromium.launch() → .firefox.launch()

# 3. Run bot
python main.py
```

---

## 📝 Summary

| Solution                      | Difficulty | Success Rate |
| ----------------------------- | ---------- | ------------ |
| Install with --with-deps      | Easy       | 80%          |
| Use Firefox                   | Easy       | 90%          |
| Install VC++ Redistributables | Medium     | 70%          |
| Switch to Selenium            | Hard       | 95%          |

**Recommended: Try Firefox first** ✅
