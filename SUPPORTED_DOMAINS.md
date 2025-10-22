# 📍 Supported Domains & Endpoints

## Short Answer

**Không**, project **KHÔNG chỉ** chạy trên turnitin.com. Nó hỗ trợ **2 domain khác nhau**.

---

## Supported Domains

### 1. **Main Processor: turnitin.com** ✅

**File:** `turnitin_auth.py`, `turnitin_reports.py`, `turnitin_processor.py`

```python
# Hard-coded URLs pointing to turnitin.com
page.goto("https://www.turnitin.com/login_page.asp?lang=en_us")
inbox_url = "https://www.turnitin.com/t_inbox.asp?lang=en_us&aid=quicksubmit"
```

**Endpoints Used:**

- `https://www.turnitin.com/login_page.asp` - Login
- `https://www.turnitin.com/t_inbox.asp` - Assignment inbox
- `https://www.turnitin.com/t_custom_search` - (Quick Submit implied)

**Configuration:**

```python
TURNITIN_EMAIL = os.getenv("TURNITIN_EMAIL")
TURNITIN_PASSWORD = os.getenv("TURNITIN_PASSWORD")
```

---

### 2. **Alternative Processor: turnitright.com** ✅

**File:** `new_turnitin_processor.py`

```python
TURNITIN_BASE_URL = os.getenv("TURNITIN_BASE_URL", "https://www.turnitright.com")
```

**This is a CONFIGURABLE URL** - Can be any custom Turnitin endpoint!

**Supported Endpoints (from code):**

- `https://www.turnitright.com/login/` - Login page
- `https://www.turnitright.com/upload/` - Upload page
- `https://www.turnitright.com/my-files/` - File listing

**Configuration:**

```python
TURNITIN_USERNAME = os.getenv("TURNITIN_USERNAME")
TURNITIN_PASSWORD = os.getenv("TURNITIN_PASSWORD")
TURNITIN_BASE_URL = os.getenv("TURNITIN_BASE_URL", "https://www.turnitright.com")
```

---

## Detailed Domain Usage

### **turnitin.com (Standard)**

```
Login:    https://www.turnitin.com/login_page.asp?lang=en_us
Inbox:    https://www.turnitin.com/t_inbox.asp?lang=en_us&aid=quicksubmit
Submit:   https://www.turnitin.com/t_custom_search (implied via Quick Submit)
Reports:  Downloaded from turnitin.com
```

### **turnitright.com (Alternative)**

```
Login:    https://www.turnitright.com/login/
Upload:   https://www.turnitright.com/upload/
MyFiles:  https://www.turnitright.com/my-files/
Reports:  Downloaded from turnitright.com
```

---

## How to Switch Domains

### Option 1: Using `turnitin_auth.py` (Default)

This automatically uses `turnitin.com`:

```python
from turnitin_processor import process_turnitin
```

### Option 2: Using `new_turnitin_processor.py` (Configurable)

Set the `.env` file:

```bash
TURNITIN_BASE_URL=https://custom.domain.com
TURNITIN_USERNAME=your_username
TURNITIN_PASSWORD=your_password
```

Or hard-code:

```python
from new_turnitin_processor import process_turnitin
```

---

## Environment Variables Required

### For turnitin.com processor:

```env
TURNITIN_EMAIL=user@email.com
TURNITIN_PASSWORD=your_password
WEBSHARE_API_TOKEN=optional_proxy_token
```

### For turnitright.com processor:

```env
TURNITIN_BASE_URL=https://www.turnitright.com
TURNITIN_USERNAME=username
TURNITIN_PASSWORD=password
```

---

## Which Processor is Actually Used?

Looking at `main.py`:

```python
from turnitin_processor import process_turnitin, shutdown_browser_session
```

**Currently:** Uses `turnitin_auth.py` processor → `turnitin.com` only

**Available but not used:** `new_turnitin_processor.py` → supports `turnitright.com`

---

## Can You Use Other Domains?

### ✅ Yes - But requires code modification:

1. **For turnitright.com or similar:**

   - Edit `main.py` import:

   ```python
   # from turnitin_processor import process_turnitin
   from new_turnitin_processor import process_turnitin  # Switch
   ```

   - Set `.env`:

   ```
   TURNITIN_BASE_URL=https://your-domain.com
   ```

2. **For completely custom domain:**
   - Modify `turnitin_auth.py` to support configurable URLs
   - Replace hard-coded URLs with environment variables

---

## Summary Table

| Property       | turnitin.com       | turnitright.com             | Custom                |
| -------------- | ------------------ | --------------------------- | --------------------- |
| File           | `turnitin_auth.py` | `new_turnitin_processor.py` | Requires modification |
| Currently Used | ✅ YES             | ❌ NO (Available)           | ❌ NO                 |
| Configurable   | ❌ Hard-coded      | ✅ Via .env                 | ❌ Code change needed |
| Login Type     | Email + Password   | Username + Password         | Depends               |
| Flexibility    | Low                | Medium                      | High                  |

---

## Conclusion

**Direct Answer:** No, not just turnitin.com. The project supports:

1. ✅ **turnitin.com** - Default & currently used
2. ✅ **turnitright.com** - Alternative processor (not used by default)
3. ✅ **Custom domain** - Possible with code modification

**To use turnitright.com or custom domain:** Requires changing the import in `main.py` and setting environment variables.
