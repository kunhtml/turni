import os
import time
import random
import threading
from datetime import datetime

def log(message: str):
    """Log a message with a timestamp to the terminal."""
    print(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {message}")

def random_wait(min_seconds=2, max_seconds=4):
    """Wait for a random amount of time to appear more human-like"""
    import random
    wait_time = random.uniform(min_seconds, max_seconds)
    time.sleep(wait_time)

from turnitin_auth import navigate_to_quick_submit, get_session_page

from turnitin_auth import navigate_to_quick_submit

def submit_document(page, file_path, chat_id, timestamp, bot, processing_messages):
    """Handle document submission process - Optimized version"""
    worker_name = threading.current_thread().name
    
    # Ensure we have a live session page (recover if previous viewer popup was closed)
    try:
        if page is None or (hasattr(page, 'is_closed') and page.is_closed()):
            log(f"[{worker_name}] [{worker_name}] Session page is closed or None; reacquiring and navigating to Quick Submit...")
            page = get_session_page()
            try:
                navigate_to_quick_submit()
            except Exception as nav_err:
                log(f"[{worker_name}] [{worker_name}] navigate_to_quick_submit error during recovery: {nav_err}")
            try:
                page.wait_for_load_state('domcontentloaded', timeout=30000)
                page.wait_for_load_state('networkidle', timeout=30000)
            except Exception:
                pass
    except Exception as recover_err:
        log(f"[{worker_name}] [{worker_name}] Recovery check failed (continuing): {recover_err}")

    # Wait for page to load
    try:
        page.wait_for_load_state('domcontentloaded', timeout=30000)  # Wait for DOM only
    except Exception as wait_error:
        log(f"[{worker_name}] [{worker_name}] Wait for load state timeout (continuing anyway): {wait_error}")
    random_wait(2, 3)
    
    # Click Submit button with multiple selectors
    log(f"[{worker_name}] [{worker_name}] Clicking Submit button...")

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
            log(f"[{worker_name}] Trying Submit button selector: {selector}")
            page.wait_for_selector(selector, timeout=15000)
            page.click(selector)
            log(f"[{worker_name}] Submit button clicked successfully with selector: {selector}")
            submit_clicked = True
            break
        except Exception as selector_error:
            log(f"[{worker_name}] Submit selector {selector} failed: {selector_error}")
            continue

    if not submit_clicked:
        raise Exception("Could not find Submit button with any selector")

    random_wait(2, 3)

    # Configure submission settings (simplified)
    log(f"[{worker_name}] Configuring submission settings...")
    try:
        page.wait_for_load_state('domcontentloaded', timeout=30000)  # Wait for DOM only
    except Exception as wait_error:
        log(f"[{worker_name}] Wait for load state timeout (continuing anyway): {wait_error}")
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
                    log(f"[{worker_name}] Checked: {option['name']}")
            except Exception as checkbox_error:
                log(f"[{worker_name}] Error with checkbox {option['name']}: {checkbox_error}")

        # Ensure Army Institute checkbox is NOT checked
        try:
            army_checkbox = page.locator('input[name="compare_to_database"][value="100"]')
            if army_checkbox.count() > 0 and army_checkbox.is_checked():
                army_checkbox.uncheck()
                log(f"[{worker_name}] Unchecked: Army Institute checkbox")
        except Exception as army_error:
            log(f"[{worker_name}] Error with Army Institute checkbox: {army_error}")

        # Set repository option to "no repository" (value="0")
        try:
            repository_select = page.locator('select[name="submit_papers_to"]')
            if repository_select.count() > 0:
                repository_select.select_option("0")  # "no repository"
                log(f"[{worker_name}] Selected: no repository option")
        except Exception as repo_error:
            log(f"[{worker_name}] Error setting repository option: {repo_error}")

        log(f"[{worker_name}] All submission settings configured successfully")
    except Exception as e:
        log(f"[{worker_name}] Error configuring settings: {e}")

    # Click Submit/Continue to proceed with multiple selectors and fallbacks
    log(f"[{worker_name}] Clicking Submit/Continue to proceed...")

    proceed_selectors = [
        # Common explicit submit buttons
        'input[type="submit"][value="Submit"]',
        'input[name="submit"][type="submit"]',
        'input[class="submit"]',
        'input[type="submit"]',
        'input[value="Submit"]',
        # Variants observed as site changes
        'button:has-text("Submit")',
        'button:has-text("Continue")',
        'button:has-text("Next")',
        'input[value="Continue"]',
        'input[value="Next"]',
        '#confirm',                     # Modal-style confirm id
        'input#confirm',
        'button#confirm',
        '.continue.modal-button'
    ]

    proceed_clicked = False
    for selector in proceed_selectors:
        try:
            log(f"[{worker_name}] Trying proceed selector: {selector}")
            page.wait_for_selector(selector, timeout=30000)
            loc = page.locator(selector)
            if loc.count() > 1:
                log(f"[{worker_name}] {selector} resolved to {loc.count()} elements, clicking the first visible one")
                loc = loc.first
            # If the element is disabled, attempt to enable by checking any required checkboxes
            try:
                disabled_attr = loc.get_attribute('disabled')
                if disabled_attr is not None:
                    log(f"[{worker_name}] Proceed element appears disabled; attempting to enable prerequisites...")
                    # Try to check any visible agreement/confirm checkboxes around
                    for cb in [
                        'input[type="checkbox"][name*="agree"]',
                        'input[type="checkbox"][name*="confirm"]',
                        'input[type="checkbox"]'
                    ]:
                        try:
                            cbloc = page.locator(cb)
                            if cbloc.count() > 0:
                                # Click all visible unchecked checkboxes (up to 3)
                                max_to_check = min(3, cbloc.count())
                                for i in range(max_to_check):
                                    elem = cbloc.nth(i)
                                    try:
                                        if elem.is_visible():
                                            elem.check()
                                					# tiny wait
                                            time.sleep(0.2)
                                    except Exception:
                                        continue
                        except Exception:
                            pass
                    # Re-evaluate disabled state after attempts
                    try:
                        disabled_attr2 = loc.get_attribute('disabled')
                        if disabled_attr2 is not None:
                            log(f"[{worker_name}] Proceed element still disabled; will attempt click anyway")
                    except Exception:
                        pass
            except Exception:
                pass

            loc.click()
            log(f"[{worker_name}] Proceed clicked successfully with selector: {selector}")
            proceed_clicked = True
            break
        except Exception as selector_error:
            log(f"[{worker_name}] Proceed selector {selector} failed: {selector_error}")
            continue

    # Heuristic fallback: try any submit/continue buttons present
    if not proceed_clicked:
        try:
            generic = page.locator('input[type="submit"], button[type="submit"], button:has-text("Submit"), button:has-text("Continue")')
            count = generic.count()
            log(f"[{worker_name}] Fallback: found {count} generic submit/continue buttons")
            if count > 0:
                generic.first.click()
                proceed_clicked = True
                log(f"[{worker_name}] Fallback proceed click succeeded")
        except Exception as generic_err:
            log(f"[{worker_name}] Fallback proceed click failed: {generic_err}")

    if not proceed_clicked:
        raise Exception("Could not find Submit/Continue proceed button with any selector")

    random_wait(2, 3)

    # Fill submission details
    log(f"[{worker_name}] Filling submission details...")
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
    log(f"[{worker_name}] Form filled - Author: Bot Checker, Title: {submission_title}")

    # Upload file with improved error handling
    log(f"[{worker_name}] Uploading file from path: {file_path}")
    msg = bot.send_message(chat_id, "📎 Uploading document...")
    processing_messages.append(msg.message_id)

    # Click file chooser button or directly upload
    try:
        # Try clicking choose file button first
        page.wait_for_selector("#choose-file-btn", timeout=15000)
        page.click("#choose-file-btn")
        random_wait(1, 2)
    except Exception as btn_error:
        log(f"[{worker_name}] Choose file button click failed: {btn_error}")

    # Upload file directly to input element
    try:
        page.locator("#selected-file").set_input_files(file_path)
        log(f"[{worker_name}] File selected successfully")
        random_wait(2, 3)
    except Exception as upload_error:
        log(f"[{worker_name}] File upload error: {upload_error}")
        raise Exception(f"Could not upload file: {upload_error}")

    # Click Upload button with multiple selectors
    log(f"[{worker_name}] Clicking Upload button...")

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
            log(f"[{worker_name}] Trying Upload button selector: {selector}")
            page.wait_for_selector(selector, timeout=15000)
            page.click(selector)
            log(f"[{worker_name}] Upload button clicked successfully with selector: {selector}")
            upload_clicked = True
            break
        except Exception as selector_error:
            log(f"[{worker_name}] Upload selector {selector} failed: {selector_error}")
            continue

    if not upload_clicked:
        raise Exception("Could not find Upload button with any selector")
    
    # Wait for processing and metadata extraction
    log(f"[{worker_name}] Waiting for processing and confirmation banner...")
    msg = bot.send_message(chat_id, "📊 Processing document...")
    processing_messages.append(msg.message_id)

    # Wait for "Please confirm that this is the file you would like to submit..." banner
    # For large files (>30MB), we need to wait for processing states instead of fixed timeout
    file_size_mb = os.path.getsize(file_path) / (1024 * 1024)
    if file_size_mb > 30:
        log(f"[{worker_name}] Large file detected ({file_size_mb:.2f} MB), will wait for processing states...")
    else:
        log(f"[{worker_name}] Normal file ({file_size_mb:.2f} MB), waiting for confirmation...")
    
    # Wait for processing to start
    banner_appeared = False
    processing_detected = False
    
    # Step 1: Wait for processing state to appear
    try:
        page.wait_for_selector('.state-processing, #submission-preview-processing', timeout=30000)
        log(f"[{worker_name}] File processing started...")
        processing_detected = True
    except Exception as proc_err:
        log(f"[{worker_name}] Processing state not detected: {proc_err}")
    
    # Step 2: For large files, wait for "still-processing" message
    if file_size_mb > 30 or processing_detected:
        try:
            # Wait for "still-processing" message to appear (indicates long processing)
            page.wait_for_selector('.state-still-processing', timeout=60000)
            log(f"[{worker_name}] Long processing message appeared - file is being processed in background")
            # For very large files, the confirm button may be available even during processing
            time.sleep(5)
        except Exception:
            log(f"[{worker_name}] No long-processing message (file may have processed quickly)")
    
    # Step 3: Wait for confirm button to exist and become enabled
    try:
        page.wait_for_selector('#confirm-btn', state='attached', timeout=300000)  # 5 minutes max
        log(f"[{worker_name}] Confirm button detected")
        banner_appeared = True
    except Exception as banner_error:
        log(f"[{worker_name}] Confirm button wait failed: {banner_error}")
        # Try alternative indicators
        for alt_selector in [
            '.state-confirm',
            '#submission-metadata-title',
            '[class*="submission-metadata"]'
        ]:
            try:
                page.wait_for_selector(alt_selector, timeout=30000)
                log(f"[{worker_name}] Alternative confirmation element found: {alt_selector}")
                banner_appeared = True
                break
            except Exception:
                continue
    
    if not banner_appeared:
        log(f"[{worker_name}] ⚠️ Warning: No confirmation elements detected, will attempt to proceed anyway")

    # Wait for confirm button to be enabled (not disabled)
    log(f"[{worker_name}] Waiting for confirm button to be enabled...")
    confirm_button_enabled = False
    for attempt in range(90):  # Try for up to 90 seconds (increased from 60)
        try:
            confirm_btn = page.locator('#confirm-btn')
            if confirm_btn.count() > 0:
                is_disabled = confirm_btn.get_attribute('disabled')
                if is_disabled is None:  # Not disabled
                    confirm_button_enabled = True
                    log(f"[{worker_name}] Confirm button is now enabled")
                    break
            time.sleep(1)
        except Exception:
            time.sleep(1)
            continue

    if not confirm_button_enabled:
        log(f"[{worker_name}] Warning: Confirm button may still be disabled after 90s wait, attempting to proceed...")

    # Extract metadata with comprehensive error handling
    # Wait a bit longer for metadata to populate after confirm button appears
    time.sleep(2)
    
    try:
        # Get submission title
        try:
            actual_submission_title = page.locator("#submission-metadata-title").inner_text(timeout=10000)
            if not actual_submission_title or actual_submission_title.strip() == "":
                actual_submission_title = submission_title
        except Exception as title_err:
            log(f"[{worker_name}] Could not extract title: {title_err}")
            actual_submission_title = submission_title

        # Get page count with retry
        page_count = "Unknown"
        for retry in range(3):
            try:
                page_count = page.locator("#submission-metadata-pagecount").inner_text(timeout=5000)
                if page_count and page_count.strip():
                    page_count = page_count.strip()
                    break
            except Exception:
                if retry < 2:
                    time.sleep(1)
                    continue
                page_count = "Unknown"

        # Get word count with retry
        word_count = "Unknown"
        for retry in range(3):
            try:
                word_count = page.locator("#submission-metadata-wordcount").inner_text(timeout=5000)
                if word_count and word_count.strip():
                    word_count = word_count.strip()
                    break
            except Exception:
                if retry < 2:
                    time.sleep(1)
                    continue
                word_count = "Unknown"

        # Get character count with retry
        character_count = "Unknown"
        for retry in range(3):
            try:
                character_count = page.locator("#submission-metadata-charactercount").inner_text(timeout=5000)
                if character_count and character_count.strip():
                    character_count = character_count.strip()
                    break
            except Exception:
                if retry < 2:
                    time.sleep(1)
                    continue
                character_count = "Unknown"

        # Get file size
        try:
            file_size = page.locator("#submission-metadata-filesize").inner_text(timeout=5000)
            file_size = file_size.strip() if file_size else "Unknown"
        except Exception:
            file_size = "Unknown"

        # Get submission date and ID
        try:
            submission_date = page.locator("#submission-metadata-date").inner_text(timeout=5000)
            submission_date = submission_date.strip() if submission_date else "Unknown"
        except Exception:
            submission_date = "Unknown"

        try:
            submission_id = page.locator("#submission-metadata-oid").inner_text(timeout=5000)
            submission_id = submission_id.strip() if submission_id else "Unknown"
        except:
            submission_id = "Unknown"
        
        log(f"[{worker_name}] Submission metadata - Title: {actual_submission_title}, Pages: {page_count}, Words: {word_count}, Characters: {character_count}")
        log(f"[{worker_name}] Submission details - Date: {submission_date}, ID: {submission_id}")

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
        log(f"[{worker_name}] Submission details stored: {submission_details}")
        
    except Exception as metadata_error:
        log(f"[{worker_name}] Could not extract metadata: {metadata_error}")
        actual_submission_title = submission_title
        # Send generic verification message
        verify_msg = bot.send_message(chat_id, "✅ <b>Document Verified</b>\n\n🚀 Submitting to Turnitin...")
        processing_messages.append(verify_msg.message_id)

    # Click Confirm button with multiple selectors
    log(f"[{worker_name}] Clicking Confirm button...")

    confirm_selectors = [
        '#confirm-btn',                         # ID selector from HTML
        'button:has-text("Confirm")',          # Text-based selector
        '.btn-primary:has-text("Confirm")',    # Class + text selector
        'button[data-loading-text="Confirming..."]'  # Data attribute selector
    ]

    confirm_clicked = False
    for selector in confirm_selectors:
        try:
            log(f"[{worker_name}] Trying Confirm button selector: {selector}")
            page.wait_for_selector(selector, timeout=15000)
            page.click(selector)
            log(f"[{worker_name}] Confirm button clicked successfully with selector: {selector}")
            confirm_clicked = True
            break
        except Exception as selector_error:
            log(f"[{worker_name}] Confirm selector {selector} failed: {selector_error}")
            continue

    if not confirm_clicked:
        raise Exception("Could not find Confirm button with any selector")

    # Wait for digital receipt confirmation message
    log(f"[{worker_name}] Waiting for submission confirmation message...")
    msg = bot.send_message(chat_id, "⏳ Document submitted, waiting for confirmation...")
    processing_messages.append(msg.message_id)
    
    # Check for "Congratulations - your submission is complete!" message
    confirmation_found = False
    max_check_attempts = 30  # Up to 30 seconds of checking
    check_interval = 1  # Check every 1 second
    
    for attempt in range(max_check_attempts):
        try:
            # Look for the congratulations message
            confirmation_element = page.query_selector('span.text-default-color')
            if confirmation_element:
                confirmation_text = confirmation_element.inner_text().strip()
                if "Congratulations" in confirmation_text and "submission is complete" in confirmation_text:
                    log(f"[{worker_name}] ✅ Found confirmation message: {confirmation_text}")
                    confirmation_found = True
                    break
        except Exception as check_error:
            pass
        
        if not confirmation_found:
            time.sleep(check_interval)
            if (attempt + 1) % 10 == 0:  # Log every 10 attempts
                log(f"[{worker_name}] Still waiting for confirmation... (attempt {attempt + 1}/{max_check_attempts})")
    
    if not confirmation_found:
        log(f"[{worker_name}] ⚠️ Warning: Could not find confirmation message, but continuing...")
    
    # Navigate to Quick Submit page immediately after confirmation
    log(f"[{worker_name}] Navigating to Quick Submit page...")
    try:
        navigate_to_quick_submit()
        log(f"[{worker_name}] ✅ Quick Submit page loaded successfully")
    except Exception as quick_submit_err:
        log(f"[{worker_name}] Error navigating to Quick Submit: {quick_submit_err}")
        raise
    
    # Wait for Quick Submit page to fully load
    try:
        page.wait_for_load_state('domcontentloaded', timeout=30000)
        page.wait_for_load_state('networkidle', timeout=30000)
        log(f"[{worker_name}] Quick Submit page fully loaded, ready to search for submission")
    except Exception as load_err:
        log(f"[{worker_name}] Quick Submit page load warning: {load_err}")
    
    # Small buffer before returning to allow page to stabilize
    page.wait_for_timeout(2000)  # 2 seconds buffer

    return actual_submission_title
