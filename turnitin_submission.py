import os
import time
import random
from datetime import datetime

def log(message: str):
    """Log a message with a timestamp to the terminal."""
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {message}")

def random_wait(min_seconds=2, max_seconds=4):
    """Wait for a random amount of time to appear more human-like"""
    import random
    wait_time = random.uniform(min_seconds, max_seconds)
    time.sleep(wait_time)

from turnitin_auth import navigate_to_quick_submit

from turnitin_auth import navigate_to_quick_submit

def submit_document(page, file_path, chat_id, timestamp, bot, processing_messages):
    """Handle document submission process - Optimized version"""
    
    # Wait for page to load
    try:
        page.wait_for_load_state('domcontentloaded', timeout=30000)  # Wait for DOM only
    except Exception as wait_error:
        log(f"Wait for load state timeout (continuing anyway): {wait_error}")
    random_wait(2, 3)
    
    # Click Submit button with multiple selectors
    log("Clicking Submit button...")

    submit_selectors = [
        'a.matte_button.submit_paper_button',    # Current working selector
        'a.submit_paper_button',                 # Class-based fallback
        'a:has-text("Submit")',                  # Text-based selector
        '[href*="t_custom_search"]',             # Href-based selector
        '.matte_button:has-text("Submit")'       # Combined selector
    ]

    submit_clicked = False
    for selector in submit_selectors:
        try:
            log(f"Trying Submit button selector: {selector}")
            page.wait_for_selector(selector, timeout=15000)
            page.click(selector)
            log(f"Submit button clicked successfully with selector: {selector}")
            submit_clicked = True
            break
        except Exception as selector_error:
            log(f"Submit selector {selector} failed: {selector_error}")
            continue

    if not submit_clicked:
        raise Exception("Could not find Submit button with any selector")

    random_wait(2, 3)

    # Configure submission settings (simplified)
    log("Configuring submission settings...")
    try:
        page.wait_for_load_state('domcontentloaded', timeout=30000)  # Wait for DOM only
    except Exception as wait_error:
        log(f"Wait for load state timeout (continuing anyway): {wait_error}")
    random_wait(2, 3)
    
    # Configure search options and repository settings
    try:
        # Check all search options EXCEPT Army Institute
        search_options = [
            {'selector': 'input[name="compare_to_database"][value="0"]', 'name': 'Search the internet'},
            {'selector': 'input[name="compare_to_database"][value="1"]', 'name': 'Search student papers'},
            {'selector': 'input[name="compare_to_database"][value="14,32,36,917"]', 'name': 'Search periodicals, journals, & publications'}
        ]

        for option in search_options:
            try:
                checkbox = page.locator(option['selector'])
                if checkbox.count() > 0 and not checkbox.is_checked():
                    checkbox.check()
                    log(f"Checked: {option['name']}")
            except Exception as checkbox_error:
                log(f"Error with checkbox {option['name']}: {checkbox_error}")

        # Ensure Army Institute checkbox is NOT checked
        try:
            army_checkbox = page.locator('input[name="compare_to_database"][value="100"]')
            if army_checkbox.count() > 0 and army_checkbox.is_checked():
                army_checkbox.uncheck()
                log("Unchecked: Army Institute checkbox")
        except Exception as army_error:
            log(f"Error with Army Institute checkbox: {army_error}")

        # Set repository option to "no repository" (value="0")
        try:
            repository_select = page.locator('select[name="submit_papers_to"]')
            if repository_select.count() > 0:
                repository_select.select_option("0")  # "no repository"
                log("Selected: no repository option")
        except Exception as repo_error:
            log(f"Error setting repository option: {repo_error}")

        log("All submission settings configured successfully")
    except Exception as e:
        log(f"Error configuring settings: {e}")

    # Click Submit to proceed with multiple selectors
    log("Clicking Submit to proceed...")

    proceed_selectors = [
        'input[type="submit"][value="Submit"]',     # Exact match from HTML
        'input[name="submit"][type="submit"]',      # Name + type selector
        'input[class="submit"]',                    # Class-based selector
        'input[type="submit"]',                     # Type-only fallback
        'input[value="Submit"]'                     # Value-only fallback
    ]

    proceed_clicked = False
    for selector in proceed_selectors:
        try:
            log(f"Trying Submit proceed selector: {selector}")
            page.wait_for_selector(selector, timeout=15000)
            page.click(selector)
            log(f"Submit proceed clicked successfully with selector: {selector}")
            proceed_clicked = True
            break
        except Exception as selector_error:
            log(f"Submit proceed selector {selector} failed: {selector_error}")
            continue

    if not proceed_clicked:
        raise Exception("Could not find Submit proceed button with any selector")

    random_wait(2, 3)

    # Fill submission details
    log("Filling submission details...")
    page.wait_for_selector('#author_first', timeout=15000)

    # Fill names as requested: "Bot" and "Checker"
    page.fill('#author_first', "Bot")
    page.fill('#author_last', "Checker")

    # Create submission title with date/time and unique ID (max 14 characters)
    # Generate unique short title format: DDHHMMXXXXX (11 chars)
    now = datetime.now()
    day = now.strftime("%d")
    hour = now.strftime("%H")
    minute = now.strftime("%M")
    unique_id = str(random.randint(100, 999))  # 3-digit random number

    submission_title = f"{day}{hour}{minute}{unique_id}"  # Max 11 characters

    page.fill('#title', submission_title)
    log(f"Form filled - Author: Bot Checker, Title: {submission_title}")

    # Upload file with improved error handling
    log(f"Uploading file from path: {file_path}")
    msg = bot.send_message(chat_id, "📎 Uploading document...")
    processing_messages.append(msg.message_id)

    # Click file chooser button or directly upload
    try:
        # Try clicking choose file button first
        page.wait_for_selector("#choose-file-btn", timeout=15000)
        page.click("#choose-file-btn")
        random_wait(1, 2)
    except Exception as btn_error:
        log(f"Choose file button click failed: {btn_error}")

    # Upload file directly to input element
    try:
        page.locator("#selected-file").set_input_files(file_path)
        log("File selected successfully")
        random_wait(2, 3)
    except Exception as upload_error:
        log(f"File upload error: {upload_error}")
        raise Exception(f"Could not upload file: {upload_error}")

    # Click Upload button with multiple selectors
    log("Clicking Upload button...")

    upload_selectors = [
        '#upload-btn',                          # ID selector from HTML
        'button[name="submit_button"]',         # Name selector from HTML
        'button:has-text("Upload")',           # Text-based selector
        '.btn-primary:has-text("Upload")',     # Class + text selector
        'button[type="submit"]'                # Type fallback
    ]

    upload_clicked = False
    for selector in upload_selectors:
        try:
            log(f"Trying Upload button selector: {selector}")
            page.wait_for_selector(selector, timeout=15000)
            page.click(selector)
            log(f"Upload button clicked successfully with selector: {selector}")
            upload_clicked = True
            break
        except Exception as selector_error:
            log(f"Upload selector {selector} failed: {selector_error}")
            continue

    if not upload_clicked:
        raise Exception("Could not find Upload button with any selector")
    
    # Wait for processing and metadata extraction
    log("Waiting for processing and confirmation banner...")
    msg = bot.send_message(chat_id, "📊 Processing document...")
    processing_messages.append(msg.message_id)

    # Wait for "Please confirm that this is the file you would like to submit..." banner
    # For large files (>30MB), processing can take 2-3 minutes
    file_size_mb = os.path.getsize(file_path) / (1024 * 1024)
    if file_size_mb > 30:
        wait_timeout = 180000  # 3 minutes for large files
        log(f"Large file detected ({file_size_mb:.2f} MB), using extended timeout: {wait_timeout/1000}s")
    else:
        wait_timeout = 90000  # 90 seconds for normal files
    
    try:
        # Wait for state-confirm to be visible (not just present)
        page.wait_for_selector('.state-confirm', state='visible', timeout=wait_timeout)
        log("Confirmation banner appeared")
    except Exception as banner_error:
        log(f"Banner wait failed: {banner_error}")
        # Try alternative: wait for confirm button instead
        try:
            page.wait_for_selector('#confirm-btn', state='visible', timeout=30000)
            log("Confirm button appeared (alternative check)")
        except Exception as btn_error:
            log(f"Confirm button wait also failed: {btn_error}")

    # Wait for confirm button to be enabled (not disabled)
    log("Waiting for confirm button to be enabled...")
    confirm_button_enabled = False
    for attempt in range(60):  # Try for up to 60 seconds (increased from 30)
        try:
            confirm_btn = page.locator('#confirm-btn')
            if confirm_btn.count() > 0:
                is_disabled = confirm_btn.get_attribute('disabled')
                if is_disabled is None:  # Not disabled
                    confirm_button_enabled = True
                    log("Confirm button is now enabled")
                    break
            time.sleep(1)
        except Exception:
            time.sleep(1)
            continue

    if not confirm_button_enabled:
        log("Warning: Confirm button may still be disabled, but continuing...")

    # Extract metadata with comprehensive error handling
    try:
        # Get submission title
        try:
            actual_submission_title = page.locator("#submission-metadata-title").inner_text(timeout=10000)
            if not actual_submission_title or actual_submission_title.strip() == "":
                actual_submission_title = submission_title
        except:
            actual_submission_title = submission_title

        # Get page count
        try:
            page_count = page.locator("#submission-metadata-pagecount").inner_text(timeout=5000)
            page_count = page_count.strip() if page_count else "Unknown"
        except:
            page_count = "Unknown"

        # Get word count
        try:
            word_count = page.locator("#submission-metadata-wordcount").inner_text(timeout=5000)
            word_count = word_count.strip() if word_count else "Unknown"
        except:
            word_count = "Unknown"

        # Get character count (new)
        try:
            character_count = page.locator("#submission-metadata-charactercount").inner_text(timeout=5000)
            character_count = character_count.strip() if character_count else "Unknown"
        except:
            character_count = "Unknown"

        # Get file size (additional info)
        try:
            file_size = page.locator("#submission-metadata-filesize").inner_text(timeout=5000)
            file_size = file_size.strip() if file_size else "Unknown"
        except:
            file_size = "Unknown"

        # Get submission date and ID (for future use and user confirmation)
        try:
            submission_date = page.locator("#submission-metadata-date").inner_text(timeout=5000)
            submission_date = submission_date.strip() if submission_date else "Unknown"
        except:
            submission_date = "Unknown"

        try:
            submission_id = page.locator("#submission-metadata-oid").inner_text(timeout=5000)
            submission_id = submission_id.strip() if submission_id else "Unknown"
        except:
            submission_id = "Unknown"
        
        log(f"Submission metadata - Title: {actual_submission_title}, Pages: {page_count}, Words: {word_count}, Characters: {character_count}")
        log(f"Submission details - Date: {submission_date}, ID: {submission_id}")

        # Send comprehensive metadata to user
        import html

        # Escape all values for HTML
        title_safe = html.escape(str(actual_submission_title))
        page_count_safe = html.escape(str(page_count))
        word_count_safe = html.escape(str(word_count))
        character_count_safe = html.escape(str(character_count))
        file_size_safe = html.escape(str(file_size))
        submission_date_safe = html.escape(str(submission_date))
        submission_id_safe = html.escape(str(submission_id))

        # Create comprehensive verification message with submission details
        verification_msg = f"""✅ <b>Document Verified & Ready</b>

📋 <b>Title:</b> {title_safe}
📄 <b>File Size:</b> {file_size_safe}
📃 <b>Pages:</b> {page_count_safe}
📝 <b>Words:</b> {word_count_safe}
📊 <b>Characters:</b> {character_count_safe}

📅 <b>Submission Date:</b> {submission_date_safe}
🆔 <b>Submission ID:</b> {submission_id_safe}

🚀 Submitting to Turnitin..."""

        verify_msg = bot.send_message(chat_id, verification_msg)
        processing_messages.append(verify_msg.message_id)

        # Store submission details for potential future use
        submission_details = {
            'title': actual_submission_title,
            'date': submission_date,
            'id': submission_id,
            'file_size': file_size,
            'pages': page_count,
            'words': word_count,
            'characters': character_count
        }
        log(f"Submission details stored: {submission_details}")
        
    except Exception as metadata_error:
        log(f"Could not extract metadata: {metadata_error}")
        actual_submission_title = submission_title
        # Send generic verification message
        verify_msg = bot.send_message(chat_id, "✅ <b>Document Verified</b>\n\n🚀 Submitting to Turnitin...")
        processing_messages.append(verify_msg.message_id)

    # Click Confirm button with multiple selectors
    log("Clicking Confirm button...")

    confirm_selectors = [
        '#confirm-btn',                         # ID selector from HTML
        'button:has-text("Confirm")',          # Text-based selector
        '.btn-primary:has-text("Confirm")',    # Class + text selector
        'button[data-loading-text="Confirming..."]'  # Data attribute selector
    ]

    confirm_clicked = False
    for selector in confirm_selectors:
        try:
            log(f"Trying Confirm button selector: {selector}")
            page.wait_for_selector(selector, timeout=15000)
            page.click(selector)
            log(f"Confirm button clicked successfully with selector: {selector}")
            confirm_clicked = True
            break
        except Exception as selector_error:
            log(f"Confirm selector {selector} failed: {selector_error}")
            continue

    if not confirm_clicked:
        raise Exception("Could not find Confirm button with any selector")

    # Wait for processing
    log("Waiting for processing...")
    msg = bot.send_message(chat_id, "⏳ Document submitted, processing...")
    processing_messages.append(msg.message_id)
    page.wait_for_timeout(60000)  # 60 seconds

    # Click close/inbox button with multiple selectors
    log("Going to assignment inbox...")

    close_selectors = [
        '#close-btn',                               # ID selector from HTML
        'button:has-text("Go to assignment inbox")', # Text-based selector
        '.btn-primary.state-digital-receipt',       # Class-based selector
        'button[class*="state-digital-receipt"]'    # Partial class match
    ]

    close_clicked = False
    for selector in close_selectors:
        try:
            log(f"Trying Close button selector: {selector}")
            page.wait_for_selector(selector, timeout=15000)
            page.click(selector)
            log(f"Close button clicked successfully with selector: {selector}")
            close_clicked = True
            break
        except Exception as selector_error:
            log(f"Close selector {selector} failed: {selector_error}")
            continue

    if not close_clicked:
        raise Exception("Could not find Close button with any selector")
    
    # Wait before searching for submission
    log("Waiting before searching for submission...")
    page.wait_for_timeout(30000)  # 30 seconds

    return actual_submission_title