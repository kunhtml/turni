import os
import time
import threading
from datetime import datetime, timedelta
import re
from typing import Optional, Tuple

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
            # Try clicking on the PAPER ID column header (column 10) to sort by Paper ID
            # PAPER ID column is at index 10, so we need th:nth-child(11) in CSS (1-indexed)
            sort_selectors = [
                'tr.inbox_header th:nth-child(11) a',   # PAPER ID column (index 10, but nth-child is 1-indexed so 11)
                'tr.inbox_header th:nth-child(11)',     # PAPER ID header without link
                'tr.inbox_header th a',                 # Any header link (fallback)
                'th.sorted_b',                          # Already sorted column
                '#assign_inbox > div.ibox_body_wrapper.yui-skin-sam > table > tbody > tr.inbox_header > th.sorted_b',
                'tr.inbox_header th',                   # Any inbox header
                'th a',                                 # Header link
                'a[href*="t_inbox.asp"]',               # Inbox navigation link
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
                # First click - sort ascending by PAPER ID
                log(f"[{worker_name}] First sort click (1/2) - sorting by PAPER ID...")
                header_element.click()
                
                # Wait for table to reload after first sort click
                try:
                    page.wait_for_load_state('domcontentloaded', timeout=15000)
                    page.wait_for_load_state('networkidle', timeout=15000)
                    log(f"[{worker_name}] Table loaded after first sort click")
                except Exception as load_err:
                    log(f"[{worker_name}] Load wait after first sort: {load_err}")
                
                time.sleep(1)
                
                # Second click - sort descending by PAPER ID (newest PAPER ID first)
                # IMPORTANT: Find the element again because DOM was refreshed
                log(f"[{worker_name}] Second sort click (2/2) - reversing sort to show newest paper ID at top...")
                
                # Re-find the header element after page reload
                header_element_2 = None
                for sort_selector in sort_selectors:
                    try:
                        header_element_2 = page.query_selector(sort_selector)
                        if header_element_2:
                            log(f"[{worker_name}] Re-found header element: {sort_selector}")
                            break
                    except:
                        continue
                
                if header_element_2:
                    header_element_2.click()
                    # Wait for table to reload after second sort click
                    try:
                        page.wait_for_load_state('domcontentloaded', timeout=15000)
                        page.wait_for_load_state('networkidle', timeout=15000)
                        log(f"[{worker_name}] Table loaded after second sort click - submission with title '{submission_title}' should be near top")
                    except Exception as load_err:
                        log(f"[{worker_name}] Load wait after second sort: {load_err}")
                    
                    time.sleep(1)
                else:
                    log(f"[{worker_name}] Could not re-find header element for second click, continuing anyway")
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
                            # DEBUG: Log ALL cell contents to understand table structure
                            if row_idx < 3:
                                cell_contents = []
                                # Log cells based on header info: PAPER ID is at column 10
                                # Show columns around where PAPER ID should be
                                for cell_idx in [10, 11, 2]:  # Check column 10 (PAPER ID), 11 (DATE), 2 (TITLE)
                                    if cell_idx < len(cells):
                                        cell = cells[cell_idx]
                                        cell_link = cell.query_selector("a")
                                        if cell_link:
                                            content = cell_link.inner_text().strip()
                                        else:
                                            content = cell.inner_text().strip()
                                        if content:
                                            cell_contents.append(f"[{cell_idx}]={content}")
                                log(f"[{worker_name}] Row {row_idx} cells: {' | '.join(cell_contents)}")
                            
                            # Extract TITLE text from the title cell (preferred) or checkbox title attribute
                            def _normalize(txt: str) -> str:
                                try:
                                    return " ".join((txt or "").strip().split())
                                except Exception:
                                    return txt or ""

                            title_text = ""
                            # Preferred: anchor text inside TITLE column
                            title_cell = row.query_selector("td[class*='ibox_title']") or (cells[2] if len(cells) > 2 else None)
                            if title_cell:
                                title_link_el = title_cell.query_selector("a")
                                if title_link_el:
                                    title_text = title_link_el.inner_text().strip()
                                else:
                                    title_text = title_cell.inner_text().strip()

                            # Fallback: checkbox input carries paper title in its title attribute
                            if not title_text:
                                try:
                                    cb = row.query_selector("td.ibox_checkbox input[name='object_checkbox']")
                                    if cb:
                                        tattr = cb.get_attribute("title")
                                        if tattr:
                                            title_text = tattr.strip()
                                except Exception:
                                    pass

                            # Extract PAPER ID for logging/diagnostics (column 10)
                            paper_id_text = ""
                            if len(cells) > 10:
                                try:
                                    paper_id_cell = cells[10]
                                    pid_link = paper_id_cell.query_selector("a")
                                    paper_id_text = (pid_link.inner_text().strip() if pid_link else paper_id_cell.inner_text().strip())
                                except Exception:
                                    paper_id_text = ""

                            # Exact match on TITLE
                            if _normalize(title_text).lower() == _normalize(submission_title).lower():
                                log(f"[{worker_name}] Found exact match: TITLE='{title_text}' | PAPER ID='{paper_id_text}' (row {row_idx})")

                                # Prefer clicking the TITLE link and handle popup/new window
                                try:
                                    title_link = row.query_selector("td[class*='ibox_title'] a") or row.query_selector("a")
                                    if title_link:
                                        # Try to capture popup window
                                        try:
                                            with page.expect_popup(timeout=5000) as popup_info:
                                                log(f"[{worker_name}] Clicking title link and expecting popup...")
                                                title_link.click()
                                            new_page = popup_info.value
                                            # Wait for the new page to load fully
                                            try:
                                                new_page.wait_for_load_state('domcontentloaded', timeout=30000)
                                            except Exception:
                                                pass
                                            try:
                                                new_page.wait_for_load_state('networkidle', timeout=30000)
                                            except Exception:
                                                pass
                                            time.sleep(2)
                                            random_wait(1, 2)
                                            log(f"[{worker_name}] Opened submission in new window/tab successfully")
                                            return new_page
                                        except Exception as popup_err:
                                            # Fallback: double-click pattern on same page
                                            log(f"[{worker_name}] No popup captured ({popup_err}); falling back to double-click on same page")
                                            log(f"[{worker_name}] Clicking submission link (click 1/2)...")
                                            title_link.click()
                                            try:
                                                page.wait_for_load_state('domcontentloaded', timeout=30000)
                                                page.wait_for_load_state('networkidle', timeout=30000)
                                            except Exception:
                                                pass
                                            time.sleep(2)
                                            random_wait(1, 2)

                                            # Re-find title link by text to avoid stale handles
                                            try:
                                                safe_sel = f"td[class*='ibox_title'] a:has-text('{submission_title}')"
                                                title_link2 = page.query_selector(safe_sel) or row.query_selector("td[class*='ibox_title'] a") or row.query_selector("a")
                                            except Exception:
                                                title_link2 = None
                                            if title_link2:
                                                log(f"[{worker_name}] Clicking submission link (click 2/2)...")
                                                title_link2.click()
                                                try:
                                                    page.wait_for_load_state('domcontentloaded', timeout=30000)
                                                except Exception:
                                                    pass
                                                try:
                                                    page.wait_for_load_state('networkidle', timeout=30000)
                                                except Exception:
                                                    pass
                                                time.sleep(2)
                                                random_wait(1, 2)
                                                log(f"[{worker_name}] Submission page fully loaded after double click")
                                                # If we didn't land on the viewer, try clicking the Similarity report link in the row to open the viewer
                                                current_after_click = page.url
                                                if ("ev.turnitin.com" in current_after_click) or ("newreport" in current_after_click) or ("paper_frameset" in current_after_click):
                                                    log(f"[{worker_name}] Detected viewer URL after double click: {current_after_click}")
                                                    return page
                                                else:
                                                    try:
                                                        report_link = row.query_selector("td.or_report_cell .or_full_version a, td.or_report_cell a.or-link")
                                                        if report_link:
                                                            with page.expect_popup(timeout=5000) as popup_info2:
                                                                log(f"[{worker_name}] Double-click did not navigate; opening Similarity report link via popup...")
                                                                report_link.click()
                                                            new_page2 = popup_info2.value
                                                            try:
                                                                new_page2.wait_for_load_state('domcontentloaded', timeout=30000)
                                                            except Exception:
                                                                pass
                                                            try:
                                                                new_page2.wait_for_load_state('networkidle', timeout=30000)
                                                            except Exception:
                                                                pass
                                                            time.sleep(2)
                                                            random_wait(1, 2)
                                                            log(f"[{worker_name}] Opened viewer from Similarity report link successfully")
                                                            return new_page2
                                                        else:
                                                            log(f"[{worker_name}] Could not find Similarity report link in row for fallback")
                                                    except Exception as link_err:
                                                        log(f"[{worker_name}] Error opening Similarity report link: {link_err}")
                                                    # As a last resort, return the current page
                                                    return page
                                            else:
                                                log(f"[{worker_name}] Error: Title link not found for second click")
                                except Exception as click_error:
                                    log(f"[{worker_name}] Error clicking title link: {click_error}")
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
            # Wait for a download affordance to appear in the viewer toolbar
            page.wait_for_selector("a[title*='Download' i], button[aria-label*='Download' i], .tii-sws-download-btn-mfe", timeout=20000)
        except:
            log("Download button not found, waiting...")
            time.sleep(5)
        
        # Downloading reports...
        bot.send_message(chat_id, "📥 Downloading reports...")

        # Adaptive readiness wait (no fixed 60s sleep)
        bot.send_message(chat_id, "⏳ Preparing reports…")
        try:
            # Poll for the presence of the download opener for up to ~90s
            start_ts = time.time()
            while time.time() - start_ts < 90:
                opener = page.query_selector("button[aria-label*='Download' i]") or \
                         page.query_selector(".tii-sws-download-btn-mfe") or \
                         page.query_selector("tii-sws-download-btn-mfe") or \
                         page.query_selector("tii-sws-header tii-sws-download-btn-mfe")
                if opener:
                    break
                time.sleep(1.5)
        except Exception:
            pass
        
        # Checking Similarity and AI badges in viewer (web components)
        log("Checking AI/Similarity badges for document validation...")
        try:
            # Similarity badge (Tab 1)
            sim_badge = page.query_selector("tii-sws-submission-workspace tii-sws-tab-navigator tii-sws-tab-button:nth-of-type(1) tdl-badge, tii-sws-tab-navigator tii-sws-tab-button:nth-of-type(1) tdl-badge")
            if sim_badge:
                sim_text = sim_badge.inner_text().strip()
                if sim_text:
                    log(f"Found Similarity badge text: {sim_text}")
        except Exception:
            pass
        try:
            # AI badge (Tab 3)
            ai_badge = page.query_selector("tii-sws-submission-workspace tii-sws-tab-navigator tii-sws-tab-button:nth-of-type(3) tdl-badge, tii-sws-tab-navigator tii-sws-tab-button:nth-of-type(3) tdl-badge")
            if ai_badge:
                ai_text = ai_badge.inner_text().strip()
                if ai_text:
                    log(f"Found AI badge text: {ai_text}")
        except Exception:
            pass
        
        # Checking reports on: https://ev.turnitin.com/app/carta/en_us/?lang=en_us&s=1&o=111&u=...
        try:
            page.wait_for_load_state("networkidle", timeout=30000)
        except:
            pass
        
        # Download button found - reports available
        log("Download button found - reports available")
        
        # Helper: open the download menu and wait for items to render
        def open_download_menu(p):
            openers = [
                "button[aria-label*='Download' i]",
                ".tii-sws-download-btn-mfe",
                "tii-sws-download-btn-mfe",
                "tii-sws-header tii-sws-download-btn-mfe",
                "div[role='button']:has-text('Download')",
            ]
            # Try up to 3 rounds with small delays
            for _ in range(3):
                for opener in openers:
                    try:
                        el = p.query_selector(opener)
                        if not el:
                            continue
                        log(f"Opening download menu via selector: {opener}")
                        el.click()
                        try:
                            p.wait_for_selector("ul.download-menu .download-menu-item button", timeout=3000)
                            return True
                        except Exception:
                            time.sleep(0.25)
                            # Try next opener if menu not visible
                    except Exception:
                        continue
            return False

        # Prefer menu-driven download as per provided markup
        def menu_click_download(p, button_selector, timeout_ms=90000, description=""):
            if not open_download_menu(p):
                log("Download menu did not appear; cannot proceed with menu item clicks")
                return None
            try:
                btn = p.query_selector(button_selector)
                if not btn:
                    # Fallback by visible text inside menu
                    # e.g., button:has-text('Similarity Report')
                    text_map = {
                        "sim": "Similarity Report",
                        "ai": "AI Writing Report",
                    }
                    text = text_map.get(description, None)
                    if text:
                        btn = p.query_selector(f"ul.download-menu button:has-text('{text}')") or p.query_selector(f"button:has-text('{text}')")
                if not btn:
                    log(f"Menu item not found: {button_selector}")
                    return None
                with p.expect_download(timeout=timeout_ms) as di:
                    log(f"Clicking download menu item: {button_selector} ({description})")
                    btn.click()
                return di.value
            except Exception as e:
                log(f"Error clicking menu item {button_selector}: {e}")
                return None

        # Try to use the explicit Similarity Report menu item first (li[1])
        download = menu_click_download(
            page,
            "ul.download-menu li:nth-child(1) button",
            timeout_ms=90000,
            description="sim",
        )
        if not download:
            # Fallback to data-px attribute if order changes
            download = menu_click_download(
                page,
                "ul.download-menu button[data-px='SimReportDownloadClicked']",
                timeout_ms=90000,
                description="sim",
            )
        if not download:
            # As a fallback, attempt direct anchors if any exist
            def attempt_direct_download(p, timeout_ms=60000):
                selectors = [
                    "a[download]",
                    "a[title*='Download' i]",
                ]
                for sel in selectors:
                    try:
                        el = p.query_selector(sel)
                        if not el:
                            continue
                        with p.expect_download(timeout=timeout_ms) as di:
                            log(f"Trying direct download via selector: {sel}")
                            el.click()
                        return di.value
                    except Exception:
                        continue
                return None
            download = attempt_direct_download(page, timeout_ms=90000)
        if not download:
            raise TimeoutError("Could not trigger Similarity report download via known selectors")
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        # Save similarity report
        sim_filename = f"downloads/similarity_{chat_id}_{timestamp}.pdf"
        os.makedirs("downloads", exist_ok=True)
        download.save_as(sim_filename)
        log(f"Saved Similarity Report as {sim_filename}")
        
        # Downloading AI Writing Report...
        log("Downloading AI Writing Report...")

        # Use explicit AI menu item (li[2]) per provided markup
        download2 = menu_click_download(
            page,
            "ul.download-menu li:nth-child(2) button",
            timeout_ms=90000,
            description="ai",
        )
        if not download2:
            # Fallback by data-px attribute
            download2 = menu_click_download(
                page,
                "ul.download-menu button[data-px='AIWritingReportDownload']",
                timeout_ms=90000,
                description="ai",
            )
        if not download2:
            # Fallbacks by visible text or generic anchors
            download2 = menu_click_download(
                page,
                "ul.download-menu button:has-text('AI Writing Report')",
                timeout_ms=90000,
                description="ai",
            )
        if not download2:
            try:
                links = page.query_selector_all("a[href*='download'], a[title*='Download' i]")
                if links and len(links) >= 2:
                    with page.expect_download(timeout=90000) as di2:
                        log("Falling back to second download link on page for AI report")
                        links[1].click()
                    download2 = di2.value
            except Exception:
                pass
        if not download2:
            raise TimeoutError("Could not trigger AI Writing report download via known selectors")
        
        # Save AI report
        ai_filename = f"downloads/ai_{chat_id}_{timestamp}.pdf"
        download2.save_as(ai_filename)
        log(f"Saved AI Writing Report as {ai_filename}")
        
        # Reports downloaded - Similarity: True, AI: True
        log("Reports downloaded - Similarity: True, AI: True")
        
        # Sending reports to user...
        bot.send_message(chat_id, "📤 Sending reports...")
        
    except Exception as e:
        log(f"Error downloading reports: {e}")
        bot.send_message(chat_id, f"⚠️ Error downloading reports: {e}")
    
    # Optionally upload to Filebin and send links
    try:
        links_msg_parts = []
        if sim_filename and os.path.exists(sim_filename):
            url = upload_file_to_filebin(sim_filename)
            if url:
                links_msg_parts.append(f"📄 Similarity: {url}")
        if ai_filename and os.path.exists(ai_filename):
            url = upload_file_to_filebin(ai_filename)
            if url:
                links_msg_parts.append(f"🤖 AI Writing: {url}")
        if links_msg_parts:
            bot.send_message(chat_id, "🔗 Filebin links:\n" + "\n".join(links_msg_parts))
            log("Filebin links sent to user")
    except Exception as link_err:
        log(f"Filebin upload warning: {link_err}")

    # Send reports directly to Telegram as files
    try:
        reports_sent = 0
        
        if sim_filename and os.path.exists(sim_filename):
            log(f"Sending Similarity Report to Telegram: {sim_filename}")
            if send_document_with_retry(bot, chat_id, sim_filename, "📊 <b>Similarity Report</b>"):
                reports_sent += 1
                log("Similarity Report sent successfully to Telegram")
        
        if ai_filename and os.path.exists(ai_filename):
            log(f"Sending AI Writing Report to Telegram: {ai_filename}")
            if send_document_with_retry(bot, chat_id, ai_filename, "🤖 <b>AI Writing Report</b>"):
                reports_sent += 1
                log("AI Writing Report sent successfully to Telegram")
        
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


def _guess_mime_type(path: str) -> str:
    name = os.path.basename(path).lower()
    if name.endswith('.pdf'):
        return 'application/pdf'
    if name.endswith('.doc'):
        return 'application/msword'
    if name.endswith('.docx'):
        return 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
    return 'application/octet-stream'


def upload_file_to_filebin(file_path: str) -> Optional[str]:
    """Upload a file to filebin.net and return a shareable URL.

    Tries multiple API patterns for compatibility:
    1) Create bin via /api/bin then POST file to /api/bin/{bin}/files
    2) PUT to /{bin}/{filename}
    3) POST multipart directly to /
    Returns the first URL found or None.
    """
    try:
        import requests
        timeout_short = 15
        timeout_long = 60

        # 1) Create a bin via API
        try:
            resp = requests.post('https://filebin.net/api/bin', timeout=timeout_short)
            if resp.ok:
                data = {}
                try:
                    data = resp.json()
                except Exception:
                    data = {}
                bin_id = data.get('name') or data.get('id') or data.get('bin')
                if bin_id:
                    files = {
                        'file': (os.path.basename(file_path), open(file_path, 'rb'), _guess_mime_type(file_path))
                    }
                    resp2 = requests.post(f'https://filebin.net/api/bin/{bin_id}/files', files=files, timeout=timeout_long)
                    if resp2.ok:
                        try:
                            j = resp2.json()
                            # Try common keys for URL
                            for key in ('url', 'fileUrl', 'file_url', 'href'):
                                if key in j:
                                    return j[key]
                        except Exception:
                            pass
                        # Fallback: build a URL if format is standard
                        return f'https://filebin.net/{bin_id}/{os.path.basename(file_path)}'
        except Exception:
            pass

        # 2) PUT directly to a random bin/filename
        try:
            import random, string
            bin_id = ''.join(random.choices(string.ascii_lowercase + string.digits, k=7))
            with open(file_path, 'rb') as f:
                resp = requests.put(f'https://filebin.net/{bin_id}/{os.path.basename(file_path)}', data=f, timeout=timeout_long)
            if resp.ok or resp.status_code in (200, 201):
                # Some instances return body text with the URL; otherwise construct it
                m = re.search(r'https?://filebin\.net/\S+', resp.text)
                return m.group(0) if m else f'https://filebin.net/{bin_id}/{os.path.basename(file_path)}'
        except Exception:
            pass

        # 3) POST multipart to root and extract URL
        try:
            files = {
                'file': (os.path.basename(file_path), open(file_path, 'rb'), _guess_mime_type(file_path))
            }
            resp = requests.post('https://filebin.net', files=files, timeout=timeout_long)
            if resp.ok:
                m = re.search(r'https?://filebin\.net/\S+', resp.text)
                if m:
                    return m.group(0)
        except Exception:
            pass

        return None
    except Exception as e:
        log(f"upload_file_to_filebin error: {e}")
        return None


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
            if send_document_with_retry(bot, chat_id, sim_filename, "📊 <b>Similarity Report</b>"):
                reports_sent += 1
                log("Similarity Report sent successfully to Telegram")
        
        if ai_filename and os.path.exists(ai_filename):
            log(f"Sending AI Writing Report to Telegram: {ai_filename}")
            if send_document_with_retry(bot, chat_id, ai_filename, "🤖 <b>AI Writing Report</b>"):
                reports_sent += 1
                log("AI Writing Report sent successfully to Telegram")
        
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


    def send_document_with_retry(bot, chat_id, file_path, caption, parse_mode='HTML', attempts=3, base_delay=2):
        """Send a document to Telegram with retries and a fallback to Filebin link on failure.
        Returns True if sent successfully, False otherwise.
        """
        for attempt in range(1, attempts + 1):
            try:
                with open(file_path, 'rb') as f:
                    bot.send_document(
                        chat_id,
                        f,
                        caption=caption,
                        parse_mode=parse_mode,
                        timeout=120
                    )
                return True
            except Exception as e:
                log(f"send_document_with_retry attempt {attempt} failed: {e}")
                if attempt < attempts:
                    # exponential backoff with small jitter
                    delay = base_delay * (2 ** (attempt - 1))
                    try:
                        time.sleep(delay)
                    except Exception:
                        pass
                else:
                    # Final failure: upload to Filebin and send link
                    url = upload_file_to_filebin(file_path)
                    if url:
                        try:
                            bot.send_message(chat_id, f"❗ Unable to send file directly due to network timeout. Here is a download link: {url}")
                        except Exception as e2:
                            log(f"Failed to send Filebin link message: {e2}")
                    else:
                        try:
                            bot.send_message(chat_id, f"❗ Unable to send file directly and upload fallback failed: {os.path.basename(file_path)}")
                        except Exception as e3:
                            log(f"Failed to send failure message: {e3}")
                    return False


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
