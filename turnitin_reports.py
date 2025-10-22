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

            # Try to extract assignment ID from current URL or use default
            try:
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

            page.goto(inbox_url, timeout=30000)
            page.wait_for_load_state('networkidle', timeout=20000)
            log("Navigated to assignment inbox")
        else:
            log("Already on inbox page")

    except Exception as nav_error:
        log(f"Error ensuring inbox page: {nav_error}")

    # Sort by Paper ID (click 2 times to get newest first)
    try:
        log(f"[{worker_name}] Sorting submissions by Paper ID (newest first)...")        # Wait for table to be fully loaded
        page.wait_for_selector('th[title*="Turnitin paper id"]', timeout=10000)
        page.wait_for_load_state('networkidle', timeout=10000)
        random_wait(1, 2)
        
        # Click 1st time - sort ascending
        paper_id_header = page.locator('th[title*="Turnitin paper id"]')
        paper_id_header.click()
        log(f"[{worker_name}] Clicked Paper ID header (1st time)")
        
        # Wait for page to reload after sort
        page.wait_for_load_state('networkidle', timeout=10000)
        random_wait(2, 3)
        
        # Click 2nd time - sort descending (newest first)
        paper_id_header.click()
        log(f"[{worker_name}] Clicked Paper ID header (2nd time - sorted by newest)")
        
        # Wait for page to reload after sort
        page.wait_for_load_state('networkidle', timeout=10000)
        random_wait(2, 3)
        
        log(f"[{worker_name}] Successfully sorted submissions by newest Paper ID")
    except Exception as sort_error:
        log(f"[{worker_name}] Warning: Could not sort by Paper ID: {sort_error}")
        log("Continuing with default sort order...")

    # Wait and check for submission with similarity score
    max_attempts = 30  # Wait up to 30 attempts (about 5 minutes)

    for attempt in range(max_attempts):
        try:
            log(f"[{worker_name}] Attempt {attempt + 1}/{max_attempts} - Checking for submission with similarity score...")

            # Refresh page to get latest data
            page.reload()
            page.wait_for_load_state('networkidle', timeout=30000)
            random_wait(2, 3)

            # Look for submission rows in the inbox table
            submission_rows = page.locator('tr.student--1').all()
            log(f"[{worker_name}] Found {len(submission_rows)} submission rows in inbox")

            for row in submission_rows:
                try:
                    # Check if this row contains our submission by title or paper ID
                    # Use .last to get the Paper ID link (not the icon link)
                    title_element = row.locator('.ibox_title a').last
                    paper_id_element = row.locator('.pid')

                    if title_element.count() > 0:
                        row_title = title_element.inner_text().strip()
                        log(f"[{worker_name}] Checking row with title: {row_title}")

                        # Match by exact title match (strict comparison)
                        title_match = (row_title.strip() == submission_title.strip())

                        if title_match:
                            log(f"[{worker_name}] Found matching title: {row_title}")

                            # Check if similarity score is available (percentage link exists)
                            similarity_link = row.locator('span.or_full_version a')
                            if similarity_link.count() > 0 and similarity_link.is_visible():
                                similarity_text = similarity_link.locator('.or-percentage').inner_text().strip()
                                log(f"Found similarity score: {similarity_text}")

                                # Send update to user
                                try:
                                    bot.send_message(
                                        chat_id,
                                        f"📊 <b>Report Ready!</b>\n\n"
                                        f"📋 <b>Title:</b> {row_title}\n"
                                        f"🎯 <b>Similarity:</b> {similarity_text}\n\n"
                                        f"⬇️ Downloading reports..."
                                    )
                                except Exception as msg_error:
                                    log(f"Error sending similarity message: {msg_error}")

                                # Click the similarity link to open reports page
                                with page.expect_popup() as page1_info:
                                    similarity_link.click()

                                page1 = page1_info.value
                                random_wait(2, 3)
                                log(f"[{worker_name}] Successfully opened reports page for submission: {row_title}")
                                return page1
                            else:
                                log(f"[{worker_name}] Submission found but similarity score not yet available: {row_title}")

                except Exception as row_error:
                    log(f"Error checking row: {row_error}")
                    continue

            # If not found, wait and try again
            if attempt < max_attempts - 1:
                log(f"[{worker_name}] Submission not ready yet, waiting 10 seconds before next attempt...")
                page.wait_for_timeout(10000)  # Wait 10 seconds

        except Exception as attempt_error:
            log(f"[{worker_name}] Error in attempt {attempt + 1}: {attempt_error}")
            if attempt < max_attempts - 1:
                page.wait_for_timeout(10000)  # Wait 10 seconds
                continue

    # If we get here, submission was not found after all attempts
    log(f"[{worker_name}] Could not find submission with similarity score after maximum attempts")
    show_retry_option(chat_id, submission_title, bot, processing_messages)
    return None

def download_reports_with_retry(page1, chat_id, timestamp, bot, processing_messages):
    """Download reports - Optimized version"""
    
    # Ensure downloads folder exists
    downloads_dir = "downloads"
    os.makedirs(downloads_dir, exist_ok=True)

    # Wait for page to load with longer timeout
    try:
        page1.wait_for_load_state('networkidle', timeout=60000)  # Increased from 30 to 60 seconds
        msg = bot.send_message(chat_id, "📊 Processing complete. Downloading reports...")
        processing_messages.append(msg.message_id)
    except Exception as load_error:
        log(f"Page load timeout, continuing anyway: {load_error}")
        msg = bot.send_message(chat_id, "📊 Attempting to download reports...")
        processing_messages.append(msg.message_id)

    # Wait for reports to be ready
    log("Waiting 60 seconds for reports...")
    page1.wait_for_timeout(60000)

    # Check AI Writing score for document validation
    ai_score_valid = check_ai_writing_score(page1, chat_id, bot, processing_messages)
    if not ai_score_valid:
        # AI score indicates document error, but still try to download similarity report
        log("AI Writing score indicates document error, downloading similarity report only")

    # Check if reports are available
    if not check_reports_availability(page1):
        log("Reports not ready")
        show_retry_option(chat_id, "download_retry", bot, processing_messages)
        return None, None

    # Download reports (conditionally based on AI score validation)
    sim_filename = download_similarity_report(page1, chat_id, timestamp, downloads_dir)

    # Only download AI report if AI score is valid
    ai_filename = None
    if ai_score_valid:
        ai_filename = download_ai_report(page1, chat_id, timestamp, downloads_dir)
    else:
        log("Skipping AI Writing Report download due to invalid AI score")

    if sim_filename or ai_filename:
        log(f"Reports downloaded - Similarity: {bool(sim_filename)}, AI: {bool(ai_filename)}")
        return sim_filename, ai_filename
    else:
        show_retry_option(chat_id, "download_retry", bot, processing_messages)
        return None, None

def check_ai_writing_score(page1, chat_id, bot, processing_messages):
    """Check AI Writing score to validate document processing"""
    try:
        log("Checking AI Writing score for document validation...")

        # Look for AI Writing tab badge with score
        ai_score_selectors = [
            '.ai-writing-badge .label',                    # Class-based selector
            'tii-sws-tab-button:has-text("AI Writing") .label', # Tab-specific selector
            'tdl-badge .label'                             # Generic badge label
        ]

        ai_score_text = None
        for selector in ai_score_selectors:
            try:
                score_element = page1.locator(selector).last  # Get last match (AI Writing badge)
                if score_element.count() > 0:
                    ai_score_text = score_element.inner_text().strip()
                    log(f"Found AI score with selector '{selector}': {ai_score_text}")
                    break
            except Exception:
                continue

        if ai_score_text:
            # Check if AI score is valid (contains %) or indicates error
            if '%' in ai_score_text and ai_score_text != '--%':
                log(f"Valid AI Writing score found: {ai_score_text}")
                try:
                    bot.send_message(
                        chat_id,
                        f"🤖 <b>AI Writing Analysis:</b> {ai_score_text}\n\n📊 Proceeding with report downloads..."
                    )
                except Exception:
                    pass
                return True
            else:
                log(f"Invalid AI Writing score detected: {ai_score_text}")
                try:
                    bot.send_message(
                        chat_id,
                        f"⚠️ <b>Document Processing Error</b>\n\n"
                        f"🤖 <b>AI Writing Score:</b> {ai_score_text}\n\n"
                        f"❌ This indicates an issue with document processing.\n"
                        f"📊 Downloading similarity report only..."
                    )
                except Exception:
                    pass
                return False
        else:
            log("Could not find AI Writing score, assuming valid")
            return True

    except Exception as e:
        log(f"Error checking AI Writing score: {e}")
        return True  # Default to valid if check fails

def check_reports_availability(page1):
    """Check if reports are available - Simplified"""
    try:
        current_url = page1.url
        log(f"Checking reports on: {current_url}")

        # Use only working selector from logs
        page1.wait_for_selector('tii-sws-download-btn-mfe', timeout=10000)
        button = page1.locator('tii-sws-download-btn-mfe')

        if button.count() > 0 and button.first.is_visible():
            log("Download button found - reports available")
            return True
        else:
            log("Download button not visible")
            return False

    except Exception as e:
        log(f"Reports not available: {e}")
        return False

def download_similarity_report(page1, chat_id, timestamp, downloads_dir):
    """Download similarity report - Updated for new UI"""
    log("Downloading Similarity Report...")

    try:
        # Click download button with multiple selectors
        download_btn_selectors = [
            'tii-sws-download-btn-mfe',           # Main element
            'button[data-px="DownloadMenuClicked"]', # Data attribute selector
            'button[aria-label="Download"]'        # Aria label selector
        ]

        download_clicked = False
        for selector in download_btn_selectors:
            try:
                page1.click(selector)
                log(f"Download button clicked with selector: {selector}")
                download_clicked = True
                break
            except Exception:
                continue

        if not download_clicked:
            raise Exception("Could not click download button")

        random_wait(1, 2)
        
        # Wait for download menu/dialog to appear
        try:
            page1.wait_for_selector('dialog.popover-wrapper.open, .download-menu, [role="menu"]', timeout=5000)
            log("Download menu appeared")
        except:
            log("Download menu selector not found, continuing...")

        # Click Similarity Report option with improved selectors
        similarity_selectors = [
            'button[data-px="SimReportDownloadClicked"]',  # Specific data attribute
            'button:has-text("Similarity Report")',        # Text-based selector
            'li.download-menu-item button:first-child',    # Position-based selector
            'button[type="button"]:has-text("Similarity Report")' # Combined selector
        ]

        similarity_clicked = False
        for selector in similarity_selectors:
            try:
                # Wait for selector
                page1.wait_for_selector(selector, timeout=10000, state='attached')
                
                # Try to click with multiple methods
                with page1.expect_download(timeout=60000) as download_info:
                    try:
                        # Method 1: Normal click
                        page1.click(selector, timeout=5000)
                    except:
                        try:
                            # Method 2: Force click
                            page1.click(selector, force=True, timeout=5000)
                        except:
                            # Method 3: JavaScript click
                            page1.evaluate(f'document.querySelector(\'{selector}\').click()')
                            time.sleep(1)

                download_sim = download_info.value
                sim_filename = os.path.join(downloads_dir, f"{chat_id}_{timestamp}_similarity.pdf")
                download_sim.save_as(sim_filename)
                log(f"Saved Similarity Report as {sim_filename}")
                similarity_clicked = True
                return sim_filename

            except Exception as selector_error:
                log(f"Similarity report selector {selector} failed: {selector_error}")
                continue

        if not similarity_clicked:
            raise Exception("Could not download similarity report")

        return sim_filename
        
    except Exception as e:
        log(f"Error downloading Similarity Report: {e}")
        return None

def download_ai_report(page1, chat_id, timestamp, downloads_dir):
    """Download AI report - Updated for new UI"""
    log("Downloading AI Writing Report...")

    try:
        random_wait(1, 2)

        # Click download button again with multiple selectors
        download_btn_selectors = [
            'tii-sws-download-btn-mfe',           # Main element
            'button[data-px="DownloadMenuClicked"]', # Data attribute selector
            'button[aria-label="Download"]'        # Aria label selector
        ]

        download_clicked = False
        for selector in download_btn_selectors:
            try:
                page1.click(selector)
                log(f"Download button clicked with selector: {selector}")
                download_clicked = True
                break
            except Exception:
                continue

        if not download_clicked:
            raise Exception("Could not click download button for AI report")

        random_wait(1, 2)

        # Click AI Writing Report option with improved selectors
        ai_report_selectors = [
            'button[data-px="AIWritingReportDownload"]',  # Specific data attribute
            'button:has-text("AI Writing Report")',       # Text-based selector
            'li.download-menu-item:nth-child(2) button',  # Position-based (2nd item)
            'button[type="button"]:has-text("AI Writing Report")' # Combined selector
        ]

        ai_clicked = False
        for selector in ai_report_selectors:
            try:
                page1.wait_for_selector(selector, timeout=10000)
                with page1.expect_download(timeout=60000) as download_info:
                    page1.click(selector)

                download_ai = download_info.value
                ai_filename = os.path.join(downloads_dir, f"{chat_id}_{timestamp}_ai.pdf")
                download_ai.save_as(ai_filename)
                log(f"Saved AI Writing Report as {ai_filename}")
                ai_clicked = True
                return ai_filename

            except Exception as selector_error:
                log(f"AI report selector {selector} failed: {selector_error}")
                continue

        if not ai_clicked:
            raise Exception("Could not download AI report")

        return ai_filename

    except Exception as e:
        log(f"Could not download AI Writing Report: {e}")
        return None

def show_retry_option(chat_id, retry_type, bot, processing_messages):
    """Show simple retry option without complex countdown"""
    
    # Clean up processing messages
    for message_id in processing_messages:
        try:
            bot.delete_message(chat_id, message_id)
        except:
            pass
    
    if retry_type == "download_retry":
        message = ("⚠️ <b>Reports Not Ready Yet</b>\n\n"
                  "Your document was submitted but reports are still being generated. "
                  "Please wait a few minutes and try submitting again.\n\n"
                  "💡 <b>Tip:</b> Larger documents take longer to process.")
    else:
        message = ("⚠️ <b>Document Not Found</b>\n\n"
                  "Your document was submitted but hasn't appeared in the list yet. "
                  "Please wait a few minutes and try submitting again.\n\n"
                  "💡 <b>Tip:</b> Processing can take 2-5 minutes.")
    
    bot.send_message(chat_id, message)

def send_reports_to_user(chat_id, sim_filename, ai_filename, bot, processing_messages, original_filename=None):
    """Send downloaded reports to Telegram user"""
    
    # Clean up processing messages
    for message_id in processing_messages:
        try:
            bot.delete_message(chat_id, message_id)
        except:
            pass

    # Upload reports to Google Drive and send links
    from google_drive_uploader import upload_file_to_drive
    
    drive_links = []
    
    if sim_filename and os.path.exists(sim_filename):
        log("Uploading Similarity Report to Google Drive...")
        try:
            bot.send_message(chat_id, "☁️ Uploading Similarity Report to Google Drive...")
            result = upload_file_to_drive(sim_filename, f"Similarity_Report_{chat_id}.pdf")
            if result:
                drive_links.append({
                    'type': 'Similarity',
                    'view_link': result['view_link'],
                    'download_link': result['download_link']
                })
                log("Similarity Report uploaded successfully")
            else:
                bot.send_message(chat_id, "⚠️ Failed to upload Similarity Report to Drive")
        except Exception as upload_error:
            log(f"Error uploading Similarity Report to Drive: {upload_error}")
            bot.send_message(chat_id, f"⚠️ Error uploading Similarity Report: {upload_error}")

    if ai_filename and os.path.exists(ai_filename):
        log("Uploading AI Writing Report to Google Drive...")
        try:
            bot.send_message(chat_id, "☁️ Uploading AI Writing Report to Google Drive...")
            result = upload_file_to_drive(ai_filename, f"AI_Report_{chat_id}.pdf")
            if result:
                drive_links.append({
                    'type': 'AI Writing',
                    'view_link': result['view_link'],
                    'download_link': result['download_link']
                })
                log("AI Writing Report uploaded successfully")
            else:
                bot.send_message(chat_id, "⚠️ Failed to upload AI Writing Report to Drive")
        except Exception as upload_error:
            log(f"Error uploading AI Writing Report to Drive: {upload_error}")
            bot.send_message(chat_id, f"⚠️ Error uploading AI Writing Report: {upload_error}")
    
    # Send Google Drive links
    if drive_links:
        links_message = "✅ <b>Reports Ready!</b>\n\n"
        
        # Add original filename if provided
        if original_filename:
            links_message += f"📁 <b>File:</b> {original_filename}\n\n"
        
        links_message += "📊 <b>Download Links:</b>\n\n"
        
        for link_info in drive_links:
            links_message += f"<b>📄 {link_info['type']} Report:</b>\n"
            links_message += f"🔗 <a href='{link_info['view_link']}'>View Online</a>\n"
            links_message += f"⬇️ <a href='{link_info['download_link']}'>Download</a>\n\n"
        
        links_message += "💡 <b>Note:</b> Links will expire after 24 hours. Download now!"
        bot.send_message(chat_id, links_message, disable_web_page_preview=True)

    # Return submission info
    submission_info = {
        'submission_title': None,
        'similarity_score': None,
        'ai_score': None,
        'submission_date': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        'reports_available': len(drive_links) > 0
    }
    
    return submission_info

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