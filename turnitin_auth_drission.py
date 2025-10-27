import os
import time
import random
import json
import requests
import threading
from datetime import datetime
from dotenv import load_dotenv
from DrissionPage import ChromiumPage, ChromiumOptions
from DrissionPage.errors import ElementNotFoundError, PageDisconnectedError

# Load environment variables
load_dotenv()
TURNITIN_EMAIL = os.getenv("TURNITIN_EMAIL")
TURNITIN_PASSWORD = os.getenv("TURNITIN_PASSWORD")

# Chrome/Chromium executable path (for Windows Server without UI)
CHROME_PATH = os.getenv("CHROME_PATH", "")

# Webshare API configuration
WEBSHARE_API_TOKEN = os.getenv("WEBSHARE_API_TOKEN", "")

# Manual proxy configuration  
MANUAL_PROXY = os.getenv("MANUAL_PROXY", "")

# Thread-local storage for browser sessions (each worker thread gets its own session)
thread_local = threading.local()

# Thread-safety locks
browser_init_lock = threading.Lock()
submission_search_lock = threading.Lock()
login_lock = threading.Lock()
session_init_lock = threading.Lock()

# Rotating user agents for better success rate
USER_AGENTS = [
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:120.0) Gecko/20100101 Firefox/120.0'
]

def log(message: str):
    """Log a message with a timestamp to the terminal."""
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {message}")

def get_thread_browser_session():
    """Get or initialize thread-local browser session storage"""
    if not hasattr(thread_local, 'browser_session'):
        thread_local.browser_session = {
            'page': None,
            'logged_in': False,
            'last_activity': None,
            'current_proxy': None
        }
    return thread_local.browser_session

def random_wait(min_seconds=2, max_seconds=4):
    """Wait for a random amount of time to appear more human-like"""
    wait_time = random.uniform(min_seconds, max_seconds)
    time.sleep(wait_time)

def get_webshare_proxies():
    """Get a list of working proxies from Webshare API"""
    if not WEBSHARE_API_TOKEN:
        log("No Webshare API token configured, using direct connection")
        return []
    
    try:
        headers = {"Authorization": f"Token {WEBSHARE_API_TOKEN}"}
        
        response = requests.get(
            "https://proxy.webshare.io/api/v2/proxy/list/?mode=direct&page=1&page_size=20",
            headers=headers,
            timeout=30
        )
        
        if response.status_code == 200:
            proxy_data = response.json()
            proxies = proxy_data.get('results', [])
            
            if proxies:
                # Filter for valid proxies, prioritize US proxies
                us_proxies = [p for p in proxies if p.get('valid') and p.get('country_code') == 'US']
                other_proxies = [p for p in proxies if p.get('valid') and p.get('country_code') != 'US']
                
                # Return US proxies first, then others
                prioritized_proxies = us_proxies + other_proxies
                log(f"Successfully fetched {len(prioritized_proxies)} valid proxies from Webshare ({len(us_proxies)} US, {len(other_proxies)} other)")
                return prioritized_proxies
            else:
                log("No valid proxies found in Webshare response")
                return []
        else:
            log(f"Failed to fetch proxies from Webshare. Status code: {response.status_code}")
            return []
            
    except Exception as e:
        log(f"Error fetching Webshare proxies: {e}")
        return []

def test_proxy_connection(proxy_info, session=None):
    """Test if a proxy is working by making a request"""
    try:
        if session is None:
            session = requests.Session()
        
        proxy_url = f"http://{proxy_info['username']}:{proxy_info['password']}@{proxy_info['proxy_address']}:{proxy_info['port']}"
        proxies = {
            "http": proxy_url,
            "https": proxy_url
        }
        
        # Test with a simple request
        response = session.get(
            "https://www.turnitin.com",
            proxies=proxies,
            timeout=10,
            verify=False
        )
        
        if response.status_code == 200:
            log(f"✅ Proxy {proxy_info['proxy_address']}:{proxy_info['port']} is working")
            return True
        else:
            log(f"❌ Proxy {proxy_info['proxy_address']}:{proxy_info['port']} returned status {response.status_code}")
            return False
            
    except Exception as e:
        log(f"❌ Proxy {proxy_info['proxy_address']}:{proxy_info['port']} failed: {e}")
        return False

def get_working_proxy():
    """Get a working proxy from available sources"""
    # Try manual proxy first
    if MANUAL_PROXY:
        try:
            # Format: user:pass@host:port or host:port
            if '@' in MANUAL_PROXY:
                auth, address = MANUAL_PROXY.split('@')
                username, password = auth.split(':')
                host, port = address.split(':')
            else:
                username, password = '', ''
                host, port = MANUAL_PROXY.split(':')
            
            proxy_info = {
                'proxy_address': host,
                'port': port,
                'username': username,
                'password': password,
                'valid': True
            }
            
            log(f"Using manual proxy: {host}:{port}")
            return proxy_info
            
        except Exception as e:
            log(f"Error parsing manual proxy: {e}")
    
    # Try Webshare proxies
    proxies = get_webshare_proxies()
    
    if not proxies:
        log("No proxies available, using direct connection")
        return None
    
    # Test proxies and return the first working one
    for proxy in proxies:
        if test_proxy_connection(proxy):
            return proxy
    
    log("All proxies failed, using direct connection")
    return None

def get_or_create_browser_session():
    """Get or create browser session for current thread"""
    browser_session = get_thread_browser_session()
    
    # Check if we have a valid session
    if browser_session['page'] is not None:
        try:
            # Check session age and URL
            current_url = browser_session['page'].url
            
            if browser_session['last_activity']:
                session_age = datetime.now() - browser_session['last_activity']
                session_age_minutes = session_age.total_seconds() / 60
                
                # If session > 60 minutes old, refresh it
                if session_age_minutes > 60:
                    log(f"[{threading.current_thread().name}] Session is {session_age_minutes:.1f} minutes old (>60), refreshing...")
                    
                    # Delete cookies for fresh login
                    cookies_path = "cookies.json"
                    if os.path.exists(cookies_path):
                        os.remove(cookies_path)
                        log("🔄 Session refresh - deleted old cookies for fresh login")
                    
                    cleanup_browser_session()
                else:
                    browser_session['last_activity'] = datetime.now()
                    log(f"[{threading.current_thread().name}] Reusing existing browser session ({session_age_minutes:.1f} min old) - Current URL: {current_url}")
                    return browser_session['page']
            else:
                # No timestamp, update it and continue
                browser_session['last_activity'] = datetime.now()
                log(f"[{threading.current_thread().name}] Reusing existing browser session - Current URL: {current_url}")
                return browser_session['page']
        except Exception as e:
            log(f"[{threading.current_thread().name}] Existing session invalid: {e}, creating new session")
            cleanup_browser_session()
    
    # CRITICAL: Acquire session initialization lock
    log(f"[{threading.current_thread().name}] Waiting for session initialization lock...")
    with session_init_lock:
        log(f"[{threading.current_thread().name}] ✅ Acquired session initialization lock - starting browser setup...")
        
        try:
            # Create new session
            log(f"[{threading.current_thread().name}] Creating new browser session...")
            
            # Get proxy configuration
            proxy_info = get_working_proxy()
            
            # Configure ChromiumOptions with anti-detection
            options = ChromiumOptions()
            
            # Try to find Chrome executable
            # Priority 1: CHROME_PATH from .env (for Windows Server)
            # Priority 2: Standard Chrome locations
            chrome_paths = []
            
            if CHROME_PATH:
                chrome_paths.append(CHROME_PATH)
                log(f"🔍 Checking CHROME_PATH from .env: {CHROME_PATH}")
            
            # Add standard Chrome locations
            chrome_paths.extend([
                r"C:\Program Files\Google\Chrome\Application\chrome.exe",
                r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
                os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
                os.path.expandvars(r"%PROGRAMFILES%\Google\Chrome\Application\chrome.exe"),
                os.path.expandvars(r"%PROGRAMFILES(X86)%\Google\Chrome\Application\chrome.exe"),
                # Add Chromium portable path
                os.path.expanduser(r"~\.chromium\chrome-win\chrome.exe"),
            ])
            
            chrome_found = False
            for chrome_path in chrome_paths:
                if os.path.exists(chrome_path):
                    options.set_browser_path(chrome_path)
                    log(f"✅ Found Chrome at: {chrome_path}")
                    chrome_found = True
                    break
            
            if not chrome_found:
                log("❌ Chrome not found! Please install Chrome or run: .\\install_chromium.ps1")
                raise Exception("Chrome executable not found. Run install_chromium.ps1 to install.")
            
            # Anti-detection settings (DrissionPage has built-in anti-detection)
            options.headless(True)
            options.set_argument('--no-sandbox')
            options.set_argument('--disable-dev-shm-usage')
            options.set_argument('--disable-gpu')
            options.set_argument('--disable-extensions')
            options.set_argument('--no-first-run')
            options.set_argument('--disable-default-apps')
            
            # Set random user agent
            user_agent = random.choice(USER_AGENTS)
            options.set_user_agent(user_agent)
            
            # Configure proxy if available
            if proxy_info:
                proxy_server = f"{proxy_info['proxy_address']}:{proxy_info['port']}"
                if proxy_info['username'] and proxy_info['password']:
                    options.set_proxy(
                        proxy=f"http://{proxy_server}",
                        user=proxy_info['username'],
                        password=proxy_info['password']
                    )
                else:
                    options.set_proxy(proxy=f"http://{proxy_server}")
                
                browser_session['current_proxy'] = proxy_info
                log(f"Using proxy: {proxy_server}")
            else:
                log("No proxy configured, using direct connection")
            
            # Create ChromiumPage with anti-detection
            page = ChromiumPage(addr_or_opts=options)
            browser_session['page'] = page
            browser_session['last_activity'] = datetime.now()
            
            log(f"[{threading.current_thread().name}] ✅ Browser session created with DrissionPage anti-detection")
            
            # Load cookies if available
            cookies_path = "cookies.json"
            if os.path.exists(cookies_path):
                try:
                    with open(cookies_path, 'r', encoding='utf-8') as f:
                        cookie_data = json.load(f)
                        cookies = cookie_data.get('cookies', [])
                        
                        # Check if we have important session cookies
                        important_cookies = ['session-id', 't', 'apt.sid', 'cwr_s']
                        has_important = any(c['name'] in important_cookies for c in cookies)
                        
                        if cookies and has_important:
                            # Load cookies into page
                            for cookie in cookies:
                                try:
                                    page.set.cookies(cookie)
                                except:
                                    pass
                            log(f"Loaded {len(cookies)} saved cookies")
                        else:
                            log("Saved cookies don't contain session data, will perform fresh login")
                except Exception as e:
                    log(f"Could not load cookies: {e}, will perform fresh login")
            else:
                log("No saved cookies found, creating fresh session")
            
            # Check if we need to login
            if check_and_perform_login():
                browser_session['logged_in'] = True
                log(f"[{threading.current_thread().name}] ✅ Session initialization complete - releasing lock")
                return browser_session['page']
            else:
                raise Exception("Login failed")
                
        except Exception as e:
            log(f"[{threading.current_thread().name}] ❌ Error creating browser session: {e}")
            cleanup_browser_session()
            raise
            
        finally:
            log(f"[{threading.current_thread().name}] Released session initialization lock")

def check_and_perform_login():
    """Check if login is needed and perform if necessary"""
    browser_session = get_thread_browser_session()
    page = browser_session['page']
    
    # Notify main.py that login is starting
    try:
        import main
        with main.bot_is_logging_in_lock:
            main.bot_is_logging_in = True
        log(f"[{threading.current_thread().name}] 🔒 Login started - file uploads blocked")
    except Exception as flag_err:
        log(f"Could not set login flag: {flag_err}")
    
    # Acquire login lock
    log(f"[{threading.current_thread().name}] Waiting for login lock...")
    with login_lock:
        log(f"[{threading.current_thread().name}] Acquired login lock, starting login process...")
        
        try:
            # Navigate to Turnitin login page
            log("🌐 Navigating to Turnitin login page...")
            page.get("https://www.turnitin.com/login_page.asp?lang=en_us")
            time.sleep(3)
            
            # Save HTML for debugging
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            debug_html_path = f"debug_login_page_{timestamp}.html"
            try:
                with open(debug_html_path, 'w', encoding='utf-8') as f:
                    f.write(page.html)
                log(f"💾 Saved login page HTML to: {debug_html_path}")
            except Exception as save_err:
                log(f"Could not save debug HTML: {save_err}")
            
            # Check for blocking pages
            page_content = page.html.lower()
            page_title = page.title.lower() if page.title else ""
            
            if any(keyword in page_content for keyword in ['cloudflare', 'checking your browser', 'just a moment']):
                log("⚠️ Blocking detected: Cloudflare challenge")
                time.sleep(5)  # Wait for challenge
            elif 'captcha' in page_content or 'captcha' in page_title:
                log("⚠️ Blocking detected: CAPTCHA")
                time.sleep(5)
            elif 'access denied' in page_content or 'access denied' in page_title:
                log("⚠️ Blocking detected: Access denied")
            elif 'awswaf' in page_content or 'challenge' in page_content:
                log("⚠️ Blocking detected: AWS WAF challenge")
                time.sleep(5)
            
            log(f"📄 Page title: {page.title if page.title else '(empty)'}")
            
            # Check if already logged in
            if "inbox" in page.url.lower() or "home" in page.url.lower():
                log("✅ Already logged in!")
                # Clear login flag
                try:
                    with main.bot_is_logging_in_lock:
                        main.bot_is_logging_in = False
                except:
                    pass
                return True
            
            # Try multiple email field selectors
            email_selectors = [
                'input[name="email"]',
                'input[type="email"]',
                'input#email',
                'input[placeholder*="email" i]',
                'input[aria-label*="email" i]'
            ]
            
            email_input = None
            for selector in email_selectors:
                try:
                    email_input = page.ele(selector, timeout=5)
                    if email_input:
                        log(f"✅ Found email field with selector: {selector}")
                        break
                except:
                    continue
            
            if not email_input:
                log("❌ Could not find email input field with any selector")
                # Clear login flag before raising
                try:
                    with main.bot_is_logging_in_lock:
                        main.bot_is_logging_in = False
                except:
                    pass
                raise Exception("Email input field not found")
            
            # Enter email
            log(f"📧 Entering email: {TURNITIN_EMAIL}")
            email_input.clear()
            email_input.input(TURNITIN_EMAIL)
            random_wait(1, 2)
            
            # Find and enter password
            password_selectors = [
                'input[name="user_password"]',
                'input[type="password"]',
                'input#password',
                'input[aria-label*="password" i]'
            ]
            
            password_input = None
            for selector in password_selectors:
                try:
                    password_input = page.ele(selector, timeout=5)
                    if password_input:
                        log(f"✅ Found password field with selector: {selector}")
                        break
                except:
                    continue
            
            if not password_input:
                log("❌ Could not find password input field")
                # Clear login flag
                try:
                    with main.bot_is_logging_in_lock:
                        main.bot_is_logging_in = False
                except:
                    pass
                raise Exception("Password input field not found")
            
            log("🔑 Entering password...")
            password_input.clear()
            password_input.input(TURNITIN_PASSWORD)
            random_wait(1, 2)
            
            # Find and click login button
            login_button_selectors = [
                'button[type="submit"]',
                'input[type="submit"]',
                'button:has-text("Log in")',
                'button:has-text("Sign in")',
                'a:has-text("Log in")'
            ]
            
            login_button = None
            for selector in login_button_selectors:
                try:
                    login_button = page.ele(selector, timeout=5)
                    if login_button:
                        log(f"✅ Found login button with selector: {selector}")
                        break
                except:
                    continue
            
            if not login_button:
                log("❌ Could not find login button")
                # Clear login flag
                try:
                    with main.bot_is_logging_in_lock:
                        main.bot_is_logging_in = False
                except:
                    pass
                raise Exception("Login button not found")
            
            # Click login button
            log("🖱️ Clicking login button...")
            login_button.click()
            
            # Wait for redirect after login
            log("⏳ Waiting for login to complete...")
            time.sleep(5)
            
            # Check if login was successful
            current_url = page.url
            if "inbox" in current_url.lower() or "home" in current_url.lower():
                log("✅ Login successful!")
                save_cookies()
                # Clear login flag
                try:
                    with main.bot_is_logging_in_lock:
                        main.bot_is_logging_in = False
                except:
                    pass
                return True
            else:
                log(f"❌ Login may have failed. Current URL: {current_url}")
                # Clear login flag
                try:
                    with main.bot_is_logging_in_lock:
                        main.bot_is_logging_in = False
                except:
                    pass
                return False
                
        except Exception as e:
            log(f"❌ Login error: {e}")
            # Clear login flag on error
            try:
                with main.bot_is_logging_in_lock:
                    main.bot_is_logging_in = False
            except:
                pass
            raise

def navigate_to_quick_submit():
    """Navigate to quick submit page"""
    browser_session = get_thread_browser_session()
    page = browser_session['page']
    
    log("📍 Navigating to Quick Submit page...")
    page.get("https://www.turnitin.com/s_class_portfolio.asp?r=45.5179283141799")
    time.sleep(3)
    
    current_url = page.url
    if "class_portfolio" in current_url or "quick" in current_url.lower():
        log("✅ Successfully navigated to Quick Submit page")
        return True
    else:
        log(f"⚠️ May not be on Quick Submit page. Current URL: {current_url}")
        return False

def save_cookies():
    """Save cookies to file"""
    browser_session = get_thread_browser_session()
    page = browser_session['page']
    
    try:
        cookies = page.cookies(all_domains=True, all_info=True)
        
        cookie_data = {
            'cookies': cookies,
            'saved_at': datetime.now().isoformat()
        }
        
        with open('cookies.json', 'w', encoding='utf-8') as f:
            json.dump(cookie_data, f, indent=2)
        
        log(f"💾 Saved {len(cookies)} cookies to cookies.json")
        return True
    except Exception as e:
        log(f"Error saving cookies: {e}")
        return False

def cleanup_browser_session():
    """Clean up browser session for current thread"""
    browser_session = get_thread_browser_session()
    
    try:
        if browser_session['page']:
            browser_session['page'].quit()
    except Exception as e:
        log(f"[{threading.current_thread().name}] Error during cleanup: {e}")
    
    # Reset session
    browser_session['page'] = None
    browser_session['logged_in'] = False
    browser_session['last_activity'] = None
    browser_session['current_proxy'] = None

def get_session_page():
    """Get the current session page, creating if necessary"""
    return get_or_create_browser_session()
