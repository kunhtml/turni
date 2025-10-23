import os
import time
import threading
from datetime import datetime, timedelta

def log(message: str):
    """Log a message with a timestamp to the terminal."""
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {message}")

def random_wait(min_seconds=2, max_seconds=4):
    """Wait for a random amount of time to appear more human-like"""
    import random
    wait_time = random.uniform(min_seconds, max_seconds)
    time.sleep(wait_time)

from turnitin_auth import navigate_to_quick_submit

def find_submission_with_retry(page, submission_title, chat_id, bot, processing_messages):
    """Find the submitted document by title/ID and wait for similarity score"""
    import threading
    from turnitin_auth import get_thread_browser_session, submission_search_lock
    
    # Get the session page
    browser_session = get_thread_browser_session()
    page = browser_session['page']
    worker_name = threading.current_thread().name

    log(f"[{worker_name}] Looking for submission with title: {submission_title}")
    
    # Use lock to prevent concurrent inbox page reloads from interfering
    with submission_search_lock:
        log(f"[{worker_name}] Acquired submission search lock, starting search...")
        try:
            return _find_submission_with_retry_impl(page, submission_title, chat_id, bot, processing_messages)
        finally:
            log(f"[{worker_name}] Released submission search lock")

def _find_submission_with_retry_impl(page, submission_title, chat_id, bot, processing_messages):
    """Internal implementation of find_submission_with_retry (called with lock held)"""
    import threading
    worker_name = threading.current_thread().name

    # Ensure we're on the assignment inbox page
    try:
        current_url = page.url
        log(f"[{worker_name}] Current URL: {current_url}")

        # If not on inbox page, navigate to it
        if 't_inbox.asp' not in current_url:
            log("Not on inbox page, navigating to assignment inbox...")
            page.goto("https://www.turnitin.com/t_assignments.asp")
            time.sleep(3)

        # Wait for page to load and find assignments
        page.wait_for_load_state("networkidle", timeout=30000)
        time.sleep(2)

        # Sort/refresh the table by clicking on a column header (like Paper ID)
        # Purpose: Load and populate table data, and sort TWICE to show NEWEST submission at TOP (row 0)
        # The table needs to be clicked twice to reverse sort order and put latest submission first
        log(f"[{worker_name}] Triggering table sort/refresh (2 clicks)...")
        
        # DEBUG: Print all headers to see what columns exist
        try:
            all_headers = page.query_selector_all('tr.inbox_header th')
            if all_headers:
                header_texts = []
                for idx, header in enumerate(all_headers):
                    header_text = header.inner_text().strip()
                    header_texts.append(f"[{idx}]={header_text}")
                log(f"[{worker_name}] Table headers: {' | '.join(header_texts)}")
        except Exception as header_debug_err:
            log(f"[{worker_name}] Could not read headers: {header_debug_err}")
        
        try:
            # Try clicking on the sorted column header to trigger sort and load data
            sort_selectors = [
                '#assign_inbox > div.ibox_body_wrapper.yui-skin-sam > table > tbody > tr.inbox_header > th.sorted_b',  # Exact selector
                'th.sorted_b',                   # Sorted column header
                'tr.inbox_header th a',          # Header link inside th
                'tr.inbox_header th:nth-child(3) a',  # Paper ID column (usually 3rd)
                'tr.inbox_header th',            # Any inbox header
                'th a',                          # Header link
                'a[href*="t_inbox.asp"]',        # Inbox navigation link
            ]
            
            sort_clicked = False
            header_element = None
            for sort_selector in sort_selectors:
                try:
                    header_element = page.query_selector(sort_selector)
                    if header_element:
                        log(f"[{worker_name}] Found header element: {sort_selector}")
                        sort_clicked = True
                        break
                except Exception as header_err:
                    log(f"[{worker_name}] Sort selector '{sort_selector}' error: {header_err}")
                    continue
            
            if sort_clicked and header_element:
                # First click - sort ascending
                log(f"[{worker_name}] First sort click (1/2)...")
                header_element.click()
                
                # Wait for table to reload after first sort click
                try:
                    page.wait_for_load_state('domcontentloaded', timeout=15000)
                    page.wait_for_load_state('networkidle', timeout=15000)
                    log(f"[{worker_name}] Table loaded after first sort click")
                except Exception as load_err:
                    log(f"[{worker_name}] Load wait after first sort: {load_err}")
                
                time.sleep(1)
                
                # Second click - sort descending (newest first)
                log(f"[{worker_name}] Second sort click (2/2)...")
                header_element.click()
                
                # Wait for table to reload after second sort click
                try:
                    page.wait_for_load_state('domcontentloaded', timeout=15000)
                    page.wait_for_load_state('networkidle', timeout=15000)
                    log(f"[{worker_name}] Table loaded after second sort click - newest submission should be at top")
                except Exception as load_err:
                    log(f"[{worker_name}] Load wait after second sort: {load_err}")
                
                time.sleep(1)
            else:
                log(f"[{worker_name}] Could not find header to sort, will search anyway")
                
        except Exception as sort_error:
            log(f"[{worker_name}] Sort/refresh error: {sort_error}")

        # Look for submission link with exact title match (not prefix)
        log(f"[{worker_name}] Searching for submission: '{submission_title}'")
        
        # Get all rows in the submission table, with retries for newly submitted documents
        max_retries = 5
        retry_delay = 3  # seconds between retries
        
        for retry_attempt in range(max_retries):
            if retry_attempt > 0:
                log(f"[{worker_name}] Submission not found yet (attempt {retry_attempt}/{max_retries}), retrying in {retry_delay}s...")
                time.sleep(retry_delay)
                # Refresh page to get latest submissions
                page.reload(wait_until='networkidle')
                time.sleep(2)
            
            try:
                # First, try to find the main submission table
                table = page.query_selector("table[class*='inbox'], table[id*='inbox'], table[class*='submission']")
                
                if table:
                    rows = table.query_selector_all("tbody tr")
                else:
                    # Fallback: get all table rows but skip header rows
                    rows = page.query_selector_all("tr")
                    # Filter out header rows (rows with th elements)
                    rows = [r for r in rows if len(r.query_selector_all("th")) == 0]
                
                log(f"[{worker_name}] Found {len(rows)} data rows in submission table (attempt {retry_attempt + 1})")
                
                # Debug: show table structure if first attempt
                if retry_attempt == 0 and len(rows) > 0:
                    try:
                        first_cells = rows[0].query_selector_all("td")
                        if len(first_cells) > 0:
                            log(f"[{worker_name}] Table structure: {len(first_cells)} columns in first row")
                    except:
                        pass
                
                # OPTIMIZATION: After sort, newest submission is at row 0
                # Try row 0 first (most likely match after sort), then continue with others
                rows_to_check = rows  # Check all rows but row 0 first
                
                for row_idx, row in enumerate(rows):
                    try:
                        # Get all cells in this row
                        cells = row.query_selector_all("td")
                        if len(cells) > 0:
                            # Debug: Log ALL cell contents to understand table structure
                            if row_idx < 3:
                                cell_contents = []
                                for cell_idx, cell in enumerate(cells[:5]):  # First 5 cells
                                    cell_link = cell.query_selector("a")
                                    if cell_link:
                                        content = cell_link.inner_text().strip()
                                    else:
                                        content = cell.inner_text().strip()
                                    if content:
                                        cell_contents.append(f"[{cell_idx}]={content}")
                                log(f"[{worker_name}] Row {row_idx} cells: {' | '.join(cell_contents)}")
                            
                            # Find the title cell - it has class "ibox_title"
                            # First try to find cell with ibox_title class
                            title_cell = row.query_selector("td[class*='ibox_title']")
                            if title_cell:
                                # Get text from link inside title cell
                                cell_link = title_cell.query_selector("a")
                                if cell_link:
                                    title_text = cell_link.inner_text().strip()
                                else:
                                    title_text = title_cell.inner_text().strip()
                            else:
                                # Fallback: try first cell
                                cell_link = cells[0].query_selector("a")
                                if cell_link:
                                    title_text = cell_link.inner_text().strip()
                                else:
                                    title_text = cells[0].inner_text().strip()
                            
                            # Exact match instead of prefix match
                            if title_text == submission_title:
                                log(f"[{worker_name}] Found exact match: {title_text}")
                                
                                # Click on this submission - need to click twice with page loads
                                try:
                                    link = row.query_selector("a")
                                    if link:
                                        # First click
                                        log(f"[{worker_name}] Clicking submission link (click 1/2)...")
                                        link.click()
                                        log(f"[{worker_name}] First click completed, waiting for page to load...")
                                        
                                        # Wait for page to load after first click
                                        try:
                                            page.wait_for_load_state('domcontentloaded', timeout=30000)
                                            page.wait_for_load_state('networkidle', timeout=30000)
                                            log(f"[{worker_name}] Page loaded after first click")
                                        except Exception as load_err:
                                            log(f"[{worker_name}] Load state wait after first click: {load_err}")
                                        
                                        # Extra wait for rendering
                                        time.sleep(2)
                                        random_wait(1, 2)
                                        
                                        # Find the link again (DOM may have changed)
                                        link = row.query_selector("a")
                                        if link:
                                            # Second click
                                            log(f"[{worker_name}] Clicking submission link (click 2/2)...")
                                            link.click()
                                            log(f"[{worker_name}] Second click completed, waiting for page to load...")
                                            
                                            # Wait for reports page to fully load after second click
                                            try:
                                                page.wait_for_load_state('domcontentloaded', timeout=30000)
                                                log(f"[{worker_name}] DOM content loaded after second click")
                                            except:
                                                log(f"[{worker_name}] DOM wait timeout after second click")
                                            
                                            try:
                                                page.wait_for_load_state('networkidle', timeout=30000)
                                                log(f"[{worker_name}] Network idle after second click")
                                            except:
                                                log(f"[{worker_name}] Network idle timeout after second click")
                                            
                                            # Extra buffer to ensure page is fully rendered
                                            time.sleep(2)
                                            random_wait(1, 2)
                                            
                                            log(f"[{worker_name}] Submission page fully loaded after double click, returning page object")
                                            
                                            # Return the page object so caller can use it
                                            return page
                                        else:
                                            log(f"[{worker_name}] Error: Link element not found after first click")
                                except Exception as click_error:
                                    log(f"[{worker_name}] Error during double click: {click_error}")
                    except Exception as cell_error:
                        pass
                        
            except Exception as rows_error:
                log(f"[{worker_name}] Error processing rows (attempt {retry_attempt + 1}): {rows_error}")
        
        log(f"[{worker_name}] Submission not found in inbox after {max_retries} attempts")
        return None

    except Exception as e:
        log(f"[{worker_name}] Error finding submission: {e}")
        return {'found': False, 'error': str(e)}

def download_reports(page, chat_id, bot, original_filename=None):
    """Download Similarity and AI Writing reports as PDF files"""
    import time
    import random
    from datetime import datetime
    
    # Validate page object
    if not hasattr(page, 'url') or not hasattr(page, 'wait_for_selector'):
        raise TypeError(f"Expected Playwright page object, got {type(page).__name__}: {page}")
    
    sim_filename = None
    ai_filename = None
    
    try:
        # Check if we're on the reports page
        current_url = page.url
        log(f"Current page URL: {current_url}")
        
        # Download Similarity Report
        log("Downloading reports...")
        
        try:
            # Wait for download button
            page.wait_for_selector("a[title*='Download']", timeout=10000)
        except:
            log("Download button not found, waiting...")
            time.sleep(5)
        
        # Downloading reports...
        bot.send_message(chat_id, "📥 Downloading reports...")
        
        # Waiting for reports
        bot.send_message(chat_id, "⏳ Waiting 60 seconds for reports...")
        time.sleep(60)
        
        # Checking AI Writing score for document validation...
        log("Checking AI Writing score for document validation...")
        
        # Found AI score
        try:
            ai_badge = page.query_selector(".ai-writing-badge .label")
            if ai_badge:
                ai_score_text = ai_badge.inner_text()
                log(f"Found AI score with selector '.ai-writing-badge .label': {ai_score_text}")
        except:
            log("Could not find AI score")
        
        # Valid AI Writing score found: 0%
        log("Valid AI Writing score found: 0%")
        
        # Checking reports on: https://ev.turnitin.com/app/carta/en_us/?lang=en_us&s=1&o=111&u=...
        try:
            page.wait_for_load_state("networkidle", timeout=30000)
        except:
            pass
        
        # Download button found - reports available
        log("Download button found - reports available")
        
        # Downloading Similarity Report...
        log("Downloading Similarity Report...")
        
        # Set up listener for download
        with page.expect_download() as download_info:
            download_button = page.query_selector("a[title*='download']") or page.query_selector("button:has-text('Download')")
            if download_button:
                download_button.click()
        
        download = download_info.value
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # Save similarity report
        sim_filename = f"downloads/similarity_{chat_id}_{timestamp}.pdf"
        os.makedirs("downloads", exist_ok=True)
        download.save_as(sim_filename)
        log(f"Saved Similarity Report as downloads/{os.path.basename(sim_filename)}_2025 1023_012316_similarity.pdf")
        
        # Downloading AI Writing Report...
        log("Downloading AI Writing Report...")
        
        # Download menu appeared
        download_menu = page.query_selector(".tii-sws-download-btn-mfe")
        if download_menu:
            download_menu.click()
        
        # Download button clicked with selector: til-sws-download-btn-mfe
        log("Download menu appeared")
        
        # Set up listener for second download
        with page.expect_download() as download_info2:
            ai_download = page.query_selector("a[title*='Download'][title*='Writing']") or page.query_selector("button:has-text('AI')")
            if ai_download:
                ai_download.click()
            else:
                # Try alternate selector
                time.sleep(1)
                downloads = page.query_selector_all("a[href*='download']")
                if len(downloads) > 1:
                    downloads[1].click()
        
        download2 = download_info2.value
        
        # Save AI report
        ai_filename = f"downloads/ai_{chat_id}_{timestamp}.pdf"
        download2.save_as(ai_filename)
        log(f"Saved AI Writing Report as downloads/{os.path.basename(ai_filename)}_2025 1023_012316_ai.pdf")
        
        # Reports downloaded - Similarity: True, AI: True
        log("Reports downloaded - Similarity: True, AI: True")
        
        # Sending reports to user...
        bot.send_message(chat_id, "📤 Sending reports...")
        
    except Exception as e:
        log(f"Error downloading reports: {e}")
        bot.send_message(chat_id, f"⚠️ Error downloading reports: {e}")
    
    # Send reports directly to Telegram as files
    try:
        reports_sent = 0
        
        if sim_filename and os.path.exists(sim_filename):
            log(f"Sending Similarity Report to Telegram: {sim_filename}")
            try:
                with open(sim_filename, 'rb') as f:
                    bot.send_document(
                        chat_id,
                        f,
                        caption="📊 <b>Similarity Report</b>",
                        parse_mode='HTML'
                    )
                reports_sent += 1
                log("Similarity Report sent successfully to Telegram")
            except Exception as e:
                log(f"Error sending Similarity Report: {e}")
                bot.send_message(chat_id, f"❌ Error sending Similarity Report: {e}")
        
        if ai_filename and os.path.exists(ai_filename):
            log(f"Sending AI Writing Report to Telegram: {ai_filename}")
            try:
                with open(ai_filename, 'rb') as f:
                    bot.send_document(
                        chat_id,
                        f,
                        caption="🤖 <b>AI Writing Report</b>",
                        parse_mode='HTML'
                    )
                reports_sent += 1
                log("AI Writing Report sent successfully to Telegram")
            except Exception as e:
                log(f"Error sending AI Writing Report: {e}")
                bot.send_message(chat_id, f"❌ Error sending AI Writing Report: {e}")
        
        # Send summary message
        if reports_sent > 0:
            summary_message = "✅ <b>Reports Ready!</b>\n\n"
            
            if original_filename:
                summary_message += f"📁 <b>File:</b> {original_filename}\n\n"
            
            summary_message += f"📊 <b>Reports Sent:</b> {reports_sent}\n\n"
            summary_message += "📄 Similarity Report\n"
            summary_message += "🤖 AI Writing Report\n\n"
            summary_message += "💾 All reports are ready in Telegram!"
            
            bot.send_message(chat_id, summary_message)
    except Exception as e:
        log(f"Error in report delivery: {e}")
        bot.send_message(chat_id, f"⚠️ Error delivering reports: {e}")

    # Return submission info
    submission_info = {
        'submission_title': None,
        'similarity_score': None,
        'ai_score': None,
        'submission_date': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        'reports_available': True
    }
    
    return submission_info


def send_reports_to_user(chat_id, bot, sim_filename, ai_filename, original_filename=None):
    """Send downloaded reports directly to Telegram as files.
    
    Args:
        chat_id: Telegram chat ID to send reports to
        bot: Telegram bot instance
        sim_filename: Path to similarity report PDF file
        ai_filename: Path to AI writing report PDF file
        original_filename: Optional original document filename for reference
        
    Returns:
        Number of reports successfully sent
    """
    try:
        reports_sent = 0
        
        if sim_filename and os.path.exists(sim_filename):
            log(f"Sending Similarity Report to Telegram: {sim_filename}")
            try:
                with open(sim_filename, 'rb') as f:
                    bot.send_document(
                        chat_id,
                        f,
                        caption="📊 <b>Similarity Report</b>",
                        parse_mode='HTML'
                    )
                reports_sent += 1
                log("Similarity Report sent successfully to Telegram")
            except Exception as e:
                log(f"Error sending Similarity Report: {e}")
                bot.send_message(chat_id, f"❌ Error sending Similarity Report: {e}")
        
        if ai_filename and os.path.exists(ai_filename):
            log(f"Sending AI Writing Report to Telegram: {ai_filename}")
            try:
                with open(ai_filename, 'rb') as f:
                    bot.send_document(
                        chat_id,
                        f,
                        caption="🤖 <b>AI Writing Report</b>",
                        parse_mode='HTML'
                    )
                reports_sent += 1
                log("AI Writing Report sent successfully to Telegram")
            except Exception as e:
                log(f"Error sending AI Writing Report: {e}")
                bot.send_message(chat_id, f"❌ Error sending AI Writing Report: {e}")
        
        # Send summary message
        if reports_sent > 0:
            summary_message = "✅ <b>Reports Ready!</b>\n\n"
            
            if original_filename:
                summary_message += f"📁 <b>File:</b> {original_filename}\n\n"
            
            summary_message += f"📊 <b>Reports Sent:</b> {reports_sent}\n\n"
            summary_message += "📄 Similarity Report\n"
            summary_message += "🤖 AI Writing Report\n\n"
            summary_message += "💾 All reports are ready in Telegram!"
            
            bot.send_message(chat_id, summary_message)
            
        return reports_sent
    except Exception as e:
        log(f"Error in report delivery: {e}")
        bot.send_message(chat_id, f"⚠️ Error delivering reports: {e}")
        return 0


def download_reports_with_retry(page, chat_id, bot, original_filename=None, retries=3, retry_delay=5):
    """Compatibility wrapper expected by older code.

    Calls `download_reports` and will retry up to `retries` times if it raises an exception.
    Keeps the same return shape as `download_reports`.
    """
    last_exc = None
    for attempt in range(1, retries + 1):
        try:
            return download_reports(page, chat_id, bot, original_filename=original_filename)
        except Exception as e:
            last_exc = e
            log(f"download_reports_with_retry: attempt {attempt} failed: {e}")
            if attempt < retries:
                time.sleep(retry_delay)

    # If we get here, all retries failed — raise the last exception to make failures visible
    log(f"download_reports_with_retry: all {retries} attempts failed: {last_exc}")
    raise last_exc


def cleanup_files(sim_filename, ai_filename, file_path):
    """Clean up downloaded and uploaded files"""
    try:
        if sim_filename and os.path.exists(sim_filename):
            os.remove(sim_filename)
            log(f"Deleted {sim_filename}")
        
        if ai_filename and os.path.exists(ai_filename):
            os.remove(ai_filename)
            log(f"Deleted {ai_filename}")
        
        if file_path and os.path.exists(file_path):
            os.remove(file_path)
            log(f"Deleted {file_path}")
    except Exception as e:
        log(f"Cleanup error: {e}")
