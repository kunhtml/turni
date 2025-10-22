import os
import json
from datetime import datetime
from dotenv import load_dotenv

def log(message: str):
    """Log a message with a timestamp to the terminal."""
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {message}")

# Import optimized modules
from turnitin_auth import get_session_page, navigate_to_quick_submit, cleanup_browser_session
from turnitin_submission import submit_document
from turnitin_reports import (
    find_submission_with_retry, 
    download_reports_with_retry
)

# Load environment variables
load_dotenv()

def process_turnitin(file_path: str, chat_id: int, bot):
    """
    Optimized Turnitin processing function:
    - Uses persistent browser session
    - Removes unnecessary debugging
    - Uses only working methods
    - Faster processing times
    """
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    processing_messages = []
    
    try:
        # Send initial message
        msg = bot.send_message(chat_id, "🚀 Starting Turnitin process...")
        processing_messages.append(msg.message_id)
        log("Starting Turnitin process...")

        # Verify file exists
        if not os.path.exists(file_path):
            raise Exception(f"File not found: {file_path}")
        
        # Get original filename
        original_filename = os.path.basename(file_path)
        log(f"File verified: {file_path} (Size: {os.path.getsize(file_path)} bytes)")

        # Get or create browser session (persistent)
        page = get_session_page()
        
        if page is None:
            raise Exception("Failed to create browser session")
        
        log(f"Browser session acquired, current URL: {page.url}")
        
        # Navigate to Quick Submit - page is already there from login
        log("Quick Submit page ready for submission")

        # Submit the document (pass the session page)
        log("Starting document submission...")
        from turnitin_auth import get_thread_browser_session
        browser_session = get_thread_browser_session()
        session_page = browser_session['page']
        
        if session_page is None:
            raise Exception("Session page is None - browser session not initialized properly")
        
        log(f"Session page verified, URL: {session_page.url}")
        actual_submission_title = submit_document(session_page, file_path, chat_id, timestamp, bot, processing_messages)

        # Find the submitted document
        log("Finding submitted document...")
        page1 = find_submission_with_retry(session_page, actual_submission_title, chat_id, bot, processing_messages)
        
        if page1 is None:
            log("Document not found, user will retry later")
            return  # Exit without closing browser

        # Download reports (handles downloading and sending to Telegram)
        log("Downloading reports...")
        try:
            submission_info = download_reports_with_retry(page1, chat_id, bot, original_filename)
        except TypeError as e:
            if "'dict' object has no attribute" in str(e) or "has no attribute 'url'" in str(e):
                log(f"Page object error: {e} - this means find_submission returned wrong type")
                bot.send_message(chat_id, "❌ Internal error: submission page error")
                return
            raise
        
        if not submission_info or not submission_info.get('reports_available'):
            log("Download failed, user will retry later")
            return  # Exit without closing browser

        # Reports are already sent by download_reports_with_retry
        # Clean up files
        try:
            if os.path.exists(f"downloads/similarity_{chat_id}_*.pdf"):
                for f in os.listdir("downloads"):
                    if f"similarity_{chat_id}" in f or f"ai_{chat_id}" in f:
                        os.remove(f"downloads/{f}")
                        log(f"Cleaned up {f}")
        except Exception as cleanup_err:
            log(f"Cleanup warning: {cleanup_err}")
        
        # Close only the submission page (page1), keep main session
        try:
            page1.close()
            log("Closed submission page, keeping main session active")
        except Exception as close_error:
            log(f"Error closing submission page: {close_error}")

        # Navigate to assignment inbox for next request
        try:
            from turnitin_auth import get_thread_browser_session
            browser_session = get_thread_browser_session()
            main_page = browser_session['page']

            # Extract assignment ID from current URL or use default
            try:
                current_url = main_page.url
                if 'aid=' in current_url:
                    aid_part = current_url.split('aid=')[1].split('&')[0]
                    inbox_url = f"https://www.turnitin.com/t_inbox.asp?lang=en_us&aid={aid_part}"
                    log(f"Using extracted assignment ID: {aid_part}")
                else:
                    inbox_url = "https://www.turnitin.com/t_inbox.asp?lang=en_us&aid=quicksubmit"
                    log("Using default assignment ID: quicksubmit")
            except Exception:
                inbox_url = "https://www.turnitin.com/t_inbox.asp?lang=en_us&aid=quicksubmit"
                log("Using fallback assignment ID: quicksubmit")

            # Navigate to assignment inbox for the next document
            main_page.goto(inbox_url, timeout=30000)
            main_page.wait_for_load_state('networkidle', timeout=20000)
            log("Navigated to assignment inbox for next request")

        except Exception as inbox_error:
            log(f"Error navigating to inbox: {inbox_error}")

        log("Turnitin process complete. Browser session maintained for next request.")
        
        # Return submission info with actual title
        return {
            'submission_title': actual_submission_title,
            'submission_date': submission_info.get('submission_date'),
            'reports_available': submission_info.get('reports_available', False)
        }

    except Exception as e:
        error_msg = f"An error occurred during Turnitin processing: {str(e)}"
        
        # Clean up processing messages
        for message_id in processing_messages:
            try:
                bot.delete_message(chat_id, message_id)
            except:
                pass
        
        bot.send_message(chat_id, f"❌ {error_msg}")
        log(f"ERROR: {error_msg}")
        
        # Clean up files
        try:
            if os.path.exists(file_path):
                os.remove(file_path)
                log(f"Cleaned up uploaded file")
        except Exception as cleanup_error:
            log(f"Cleanup error: {cleanup_error}")
        
        # On critical errors, reset browser session
        if "browser" in str(e).lower() or "page" in str(e).lower():
            log("Critical browser error detected, resetting session")
            cleanup_browser_session()

def shutdown_browser_session():
    """Shutdown browser session when bot stops"""
    log("Shutting down browser session...")
    cleanup_browser_session()
    log("Browser session closed")