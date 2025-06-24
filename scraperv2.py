#!/usr/bin/env python3
"""
FINAL PRODUCTION University of Guelph Course Scraper
Generates complete datasets for Summer 2025, Fall 2025, Winter 2026.
Automated version with robust waits and processing.
"""

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import NoSuchElementException, TimeoutException, StaleElementReferenceException
from webdriver_manager.chrome import ChromeDriverManager
import json
import time
import re

# --- Constants for Debugging (Typically off for production) ---
DEBUG_COURSE_CODE_SUBSTRING = "" # Set to a course for specific tracing if needed
# These are effectively off for a normal automated run
TARGET_START_PAGE = 1
OBSERVE_AND_PAUSE_ON_PAGE = None 
MAX_PAGES_TO_SCRAPE_IN_DEBUG_MODE = None 

def time_to_minutes(time_str):
    if not time_str or time_str.strip() == '': return 0
    time_str = time_str.strip().upper()
    if ':' not in time_str: return 0
    try:
        if 'AM' in time_str or 'PM' in time_str:
            time_part = time_str.replace('AM', '').replace('PM', '').strip()
            is_pm = 'PM' in time_str
        else: time_part = time_str; is_pm = False
        hour, minute = map(int, time_part.split(':'))
        if is_pm and hour != 12: hour += 12
        elif not is_pm and hour == 12: hour = 0 
        return hour * 60 + minute
    except (ValueError, IndexError): print(f"Warning: Could not parse time '{time_str}'"); return 0

def parse_days(days_str):
    if not days_str or days_str.strip() == '': return []
    days_str = days_str.strip()
    day_mappings = {'M':'M','Mo':'M','Mon':'M','T':'T','Tu':'T','Tue':'T','Tues':'T','W':'W','We':'W','Wed':'W','Th':'Th','R':'Th','Thu':'Th','Thur':'Th','Thurs':'Th','F':'F','Fr':'F','Fri':'F','S':'Sa','Sa':'Sa','Sat':'Sa','Su':'Su','Sun':'Su'}
    parsed_days = []
    if '/' in days_str:
        parts = days_str.split('/')
        for part in parts:
            part = part.strip()
            parsed_days.append(day_mappings.get(part, part if part else None))
        return list(dict.fromkeys(filter(None, parsed_days))) if parsed_days else []
    if ' ' in days_str:
        parts = days_str.split()
        for part in parts:
            part = part.strip()
            parsed_days.append(day_mappings.get(part, part if part else None))
        return list(dict.fromkeys(filter(None, parsed_days))) if parsed_days else []
    i = 0; temp_concatenated_days = []
    current_str = days_str
    while i < len(current_str):
        found_match = False
        if i + 1 < len(current_str):
            two_char_day = current_str[i:i+2]
            if two_char_day in day_mappings:
                temp_concatenated_days.append(day_mappings[two_char_day])
                i += 2
                found_match = True
        if not found_match and current_str[i] in day_mappings:
            temp_concatenated_days.append(day_mappings[current_str[i]])
            i += 1
            found_match = True
        if not found_match: 
            remaining_part = current_str[i:].strip()
            if remaining_part:
                temp_concatenated_days.append(remaining_part)
            break 
    if temp_concatenated_days:
        return list(dict.fromkeys(temp_concatenated_days))
    return [days_str] if days_str else []

def parse_course_header(course_str):
    is_debug_course = DEBUG_COURSE_CODE_SUBSTRING and DEBUG_COURSE_CODE_SUBSTRING in course_str
    try:
        if not course_str or course_str.strip() == '': return None
        course_str_stripped = course_str.strip()
        if '*' not in course_str_stripped: return None
        subcode, rest = course_str_stripped.split('*', 1); subcode = subcode.strip(); rest = rest.strip()
        match = re.match(r'(\d{4})\s*([^a-zA-Z0-9\s]*)\s*(.+)', rest) 
        if not match: match = re.match(r'(\d{4})\s*(.*)', rest)
        if not match: match = re.match(r'(\d{4})(.*)', rest)
        if not match: print(f"Warning: Could not parse course code from '{rest}' (original: '{course_str_stripped}')"); return None
        course_code = match.group(1).strip()
        title_credits_parts = []
        for i in range(2, match.lastindex + 1): 
            if match.group(i):
                title_credits_parts.append(match.group(i).strip())
        title_credits = " ".join(filter(None, title_credits_parts)).strip()
        title = title_credits; credits_val = "0.5" 
        credits_pattern_match = re.search(r'\(([\d\.]+)\s*(?:Credit|Credits)?\)$', title_credits, re.IGNORECASE)
        if credits_pattern_match:
            title = title_credits[:credits_pattern_match.start()].strip()
            credits_val = credits_pattern_match.group(1)
        else: 
            credits_simple_match = re.search(r'\(([\d\.]+)\)$', title_credits)
            if credits_simple_match:
                title = title_credits[:credits_simple_match.start()].strip()
                credits_val = credits_simple_match.group(1)
        parsed_data = {'subcode': subcode, 'course_code': course_code, 'title': title, 'credits': credits_val, 'full_title': course_str}
        return parsed_data
    except Exception as e: print(f"Error parsing course header '{course_str}': {e}"); return None

def click_collapsible_buttons(driver):
    # Reduced verbosity for production, but essential logic remains
    buttons_clicked_count = 0
    try:
        WebDriverWait(driver, 10).until(EC.presence_of_element_located((By.CLASS_NAME, "esg-collapsible-group__toggle")))
        buttons = driver.find_elements(By.CLASS_NAME, "esg-collapsible-group__toggle")
        if not buttons : return

        for i, button_to_click in enumerate(buttons):
            try:
                driver.execute_script("arguments[0].scrollIntoViewIfNeeded(true);", button_to_click); time.sleep(0.1) # Shortened sleep
                if not button_to_click.is_displayed() or not button_to_click.is_enabled(): continue
                is_expanded = button_to_click.get_attribute("aria-expanded")
                if is_expanded == "false":
                    WebDriverWait(driver, 5).until(EC.element_to_be_clickable(button_to_click)) # Shorter wait
                    button_to_click.click(); buttons_clicked_count += 1
                    time.sleep(0.3) # Shortened sleep
                elif is_expanded != "true": # Handle missing or unexpected aria-expanded
                    WebDriverWait(driver, 5).until(EC.element_to_be_clickable(button_to_click))
                    button_to_click.click(); buttons_clicked_count += 1
                    time.sleep(0.3)
            except StaleElementReferenceException: pass # Silently skip stale buttons in prod
            except TimeoutException: pass # Silently skip non-clickable buttons in prod
            except Exception: # Other click issues, try JS
                try:
                    driver.execute_script("arguments[0].click();", button_to_click); buttons_clicked_count += 1
                    time.sleep(0.3)
                except Exception: pass # JS click also failed
        # print(f"DEBUG_CLICK: Clicked {buttons_clicked_count} collapsible buttons.") # Optional: re-enable if needed
    except TimeoutException: pass # No buttons found
    except Exception: pass # General error

def click_next_page(driver, current_page_for_log):
    try:
        next_button = WebDriverWait(driver, 15).until(EC.element_to_be_clickable((By.CSS_SELECTOR, "#course-results-next-page:not([disabled])")))
        driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", next_button); time.sleep(0.2)
        driver.execute_script("arguments[0].click();", next_button)
        WebDriverWait(driver, 30).until(EC.invisibility_of_element_located((By.CSS_SELECTOR, ".esg-spinner")))
        WebDriverWait(driver, 30).until(EC.presence_of_element_located((By.CSS_SELECTOR, "#course-resultul li")))
        return True
    except TimeoutException: print(f"Timeout next page (from p{current_page_for_log}). Last page?"); return False
    except Exception as e: print(f"Failed next page (from p{current_page_for_log}): {str(e)}"); return False

def extract_course_details(course_element, current_page_num_for_debug=0):
    course_element_text_for_debug = course_element.text 
    is_debug_course = DEBUG_COURSE_CODE_SUBSTRING and DEBUG_COURSE_CODE_SUBSTRING in course_element_text_for_debug
    general_debug_for_later_pages = not DEBUG_COURSE_CODE_SUBSTRING and current_page_num_for_debug > 0 and OBSERVE_AND_PAUSE_ON_PAGE # only if observing
    
    if is_debug_course or general_debug_for_later_pages: 
        print(f"DEBUG_TRACE (Page {current_page_num_for_debug}) [extract_course_details]: Element text (first 200): {course_element_text_for_debug[:200].replace(chr(10), ' ')}")
    try:
        h3_text = None
        try: h3 = course_element.find_element(By.TAG_NAME, "h3"); h3_text = h3.text.strip()
        except NoSuchElementException:
            try: span_element = course_element.find_element(By.CSS_SELECTOR, "span[id*='course-']"); h3_text = span_element.text.strip()
            except NoSuchElementException:
                all_text_lines = course_element_text_for_debug.split('\n')
                if all_text_lines and re.match(r'^[A-Z]{2,5}\*\d{4}', all_text_lines[0].strip()): h3_text = all_text_lines[0].strip()
        
        if not h3_text: 
            if is_debug_course or general_debug_for_later_pages: print(f"DEBUG_TRACE (Page {current_page_num_for_debug}) ... No h3_text found. Returning None.")
            print(f"Warning: No course title. Text: {course_element_text_for_debug[:100].replace(chr(10), ' ')}"); return None
        
        parsed_header = parse_course_header(h3_text)
        if not parsed_header: 
            if is_debug_course or general_debug_for_later_pages: print(f"DEBUG_TRACE (Page {current_page_num_for_debug}) ... parsed_header is None for h3_text '{h3_text}'. Returning None.")
            return None
        
        course_key = f"{parsed_header['subcode']}*{parsed_header['course_code']}"
        course_data = {"Title": parsed_header['full_title'], "Description": "", "Offering": "","Restriction": "", "Department": "", "Requisites": "None","Locations": "Guelph", "Offered": "", "Sections": []}
        
        try:
            section_tag = course_element.find_element(By.TAG_NAME, "section")
            try: desc_div = section_tag.find_element(By.CSS_SELECTOR, "div.search-coursedescription"); course_data["Description"] = desc_div.text.strip()
            except NoSuchElementException: pass
            info_items = section_tag.find_elements(By.XPATH, ".//div[contains(@class, 'search-coursedetails-left') or contains(@class, 'search-coursedetails-right')]/strong/parent::div")
            for item_div in info_items:
                try:
                    strong_tag = item_div.find_element(By.TAG_NAME, "strong")
                    label_text = strong_tag.text.strip().lower()
                    value_text = item_div.text.replace(strong_tag.text, "").strip() 
                    if not value_text:
                        try: value_sibling_div = item_div.find_element(By.XPATH, "./following-sibling::div[1]"); value_text = value_sibling_div.text.strip()
                        except NoSuchElementException: pass 
                    if not value_text: continue
                    if 'requisite' in label_text: course_data["Requisites"] = value_text
                    elif 'location' in label_text: course_data["Locations"] = value_text
                    elif 'offered' in label_text and 'also offered as' not in label_text: course_data["Offered"] = value_text
                    elif 'department' in label_text: course_data["Department"] = value_text
                    elif 'also offered as' in label_text or ('offering' in label_text and 'also' in label_text): course_data["Offering"] = value_text
                    elif 'restriction' in label_text: course_data["Restriction"] = value_text
                except (NoSuchElementException, StaleElementReferenceException): continue
        except NoSuchElementException: pass
        
        course_data["Sections"] = extract_sections_by_term_correct(course_element, current_page_num_for_debug) 
        return course_key, course_data
    except Exception as e: 
        if is_debug_course or general_debug_for_later_pages: print(f"DEBUG_TRACE (Page {current_page_num_for_debug}) ... Major exception in extract_course_details: {e}")
        print(f"Error extracting course details: {e}"); return None

def extract_sections_by_term_correct(course_element, current_page_num_for_debug=0):
    is_debug_course_context = DEBUG_COURSE_CODE_SUBSTRING and DEBUG_COURSE_CODE_SUBSTRING in course_element.text
    general_debug_for_later_pages = not DEBUG_COURSE_CODE_SUBSTRING and current_page_num_for_debug > 0 and OBSERVE_AND_PAUSE_ON_PAGE
    sections_by_term = { 'Summer 2025': [], 'Fall 2025': [], 'Winter 2026': [] }
    try:
        sections_container = course_element.find_element(By.CSS_SELECTOR, ".esg-collapsible-group")
        term_headers = sections_container.find_elements(By.TAG_NAME, "h4") 
        for term_header_element in term_headers:
            term_name = term_header_element.text.strip()
            if term_name not in sections_by_term: continue 
            try:
                ul_element = term_header_element.find_element(By.XPATH, "./following-sibling::ul[1]")
                section_li_elements = ul_element.find_elements(By.TAG_NAME, "li") 
                for section_li in section_li_elements:
                    single_section_data = extract_single_section(section_li, term_name, current_page_num_for_debug) 
                    if single_section_data: sections_by_term[term_name].append(single_section_data)
            except NoSuchElementException: pass
            except StaleElementReferenceException: pass
    except NoSuchElementException: pass
    except StaleElementReferenceException: pass
    return sections_by_term

def extract_single_section(section_li, term_name, current_page_num_for_debug=0):
    section_li_text_for_debug = section_li.text
    is_debug_course_context = DEBUG_COURSE_CODE_SUBSTRING and DEBUG_COURSE_CODE_SUBSTRING in section_li_text_for_debug
    general_debug_for_later_pages = not DEBUG_COURSE_CODE_SUBSTRING and current_page_num_for_debug > 0 and OBSERVE_AND_PAUSE_ON_PAGE
    section_id_text = "unknown_section" 
    try:
        section_id = ""
        try: 
            section_id_link = section_li.find_element(By.CSS_SELECTOR, "a.search-sectiondetailslink")
            section_id = section_id_link.text.strip() if section_id_link.text else ""
            if section_id: section_id_text = section_id
        except NoSuchElementException:
            try: 
                section_id_link = section_li.find_element(By.CSS_SELECTOR, "a[href*='section']")
                section_id = section_id_link.text.strip() if section_id_link.text else ""
                if section_id: section_id_text = section_id
            except NoSuchElementException: pass
        if not section_id: 
            section_pattern = re.search(r'([A-Z]{2,5}\*\d{4}\*[\w-]+)', section_li_text_for_debug) 
            if section_pattern:
                section_id = section_pattern.group(1) 
                section_id_text = section_id
            else:
                first_line = section_li_text_for_debug.split('\n')[0].strip()
                if re.match(r'^[A-Z]{2,5}\*\d{4}', first_line): 
                    section_id = first_line 
                    section_id_text = section_id
                else: return None
        if not section_id: return None
        section_data = {"id": section_id}; meetings = {} 
        try:
            rows = section_li.find_elements(By.CSS_SELECTOR, "tr.search-sectionrow")
            for row_idx, row in enumerate(rows):
                try:
                    time_td = row.find_element(By.CSS_SELECTOR, "td.search-sectiondaystime")
                    days_elems = time_td.find_elements(By.CSS_SELECTOR, "span[id*='-meeting-days-']")
                    start_elems = time_td.find_elements(By.CSS_SELECTOR, "span[id*='-start-']")
                    end_elems = time_td.find_elements(By.CSS_SELECTOR, "span[id*='-end-']")
                    days_str = days_elems[0].text.strip() if days_elems and days_elems[0].text.strip() else ""
                    start_time = start_elems[0].text.strip() if start_elems and start_elems[0].text.strip() else ""
                    end_time = end_elems[0].text.strip() if end_elems and end_elems[0].text.strip() else ""
                    loc_td = row.find_element(By.CSS_SELECTOR, "td.search-sectionlocations"); method = ""
                    method_elems = loc_td.find_elements(By.CSS_SELECTOR, "span[id*='-meeting-instructional-method-']")
                    if method_elems and method_elems[0].text.strip(): method = method_elems[0].text.strip().upper()
                    else: 
                        all_spans_in_loc = loc_td.find_elements(By.TAG_NAME, "span")
                        for span in all_spans_in_loc:
                            text = span.text.strip().upper()
                            if text in ['LEC','SEM','LAB','EXAM','TUT','FLD','CLIN','PRA','WKS','STU','IND','RES','DISTANCE EDUCATION','DE']:
                                method = 'DISTANCE EDUCATION' if text in ['DISTANCE EDUCATION','DE'] else text; break 
                    location = ""; location_elems = loc_td.find_elements(By.CSS_SELECTOR, "span[id*='-meeting-location-']")
                    if location_elems and location_elems[0].text.strip(): location = location_elems[0].text.strip()
                    all_loc_span_texts = [s.text.strip() for s in loc_td.find_elements(By.TAG_NAME, "span") if s.text.strip()]
                    additional_loc_parts = []; known_loc_texts = {location, method} 
                    for text_part in all_loc_span_texts:
                        if text_part not in known_loc_texts and text_part.upper() not in ['LEC','SEM','LAB','EXAM','TUT','DISTANCE EDUCATION','DE']:
                            additional_loc_parts.append(text_part)
                    if additional_loc_parts: location = ", ".join(filter(None, [location] + additional_loc_parts))
                    elif not location and method != 'DISTANCE EDUCATION': 
                        td_text_content = loc_td.text.strip()
                        if method and method in td_text_content: td_text_content = td_text_content.replace(method, "").strip()
                        if td_text_content: location = td_text_content.strip(', ')
                    current_meeting_detail = None
                    if method: 
                        if method == 'DISTANCE EDUCATION': current_meeting_detail = {"start":0,"end":0,"date":[],"location":location if location else "ONLINE"}
                        elif days_str or start_time or end_time or location: 
                            current_meeting_detail = {"start":time_to_minutes(start_time),"end":time_to_minutes(end_time),"date":parse_days(days_str),"location":location}
                        if current_meeting_detail:
                            if method not in meetings: meetings[method] = current_meeting_detail
                            else:
                                if not isinstance(meetings[method], list): meetings[method] = [meetings[method]]
                                meetings[method].append(current_meeting_detail)
                except (NoSuchElementException, StaleElementReferenceException): pass
        except (NoSuchElementException, StaleElementReferenceException): pass
        if meetings: section_data.update(meetings); return section_data
        else: return None
    except Exception as e:
        print(f"Warning: Major error extracting section '{section_id_text}': {str(e)}"); return None

def scrape_all_courses(driver, start_page=1, max_pages_to_process=None, observe_and_pause_on_page=None):
    all_courses_by_term = { 'Summer 2025': {}, 'Fall 2025': {}, 'Winter 2026': {} }
    current_actual_page_num = 1
    driver.get("https://colleague-ss.uoguelph.ca/Student/Courses/Search")
    try: WebDriverWait(driver, 20).until(EC.presence_of_element_located((By.ID, "course-resultul")))
    except TimeoutException: print("Initial course search page did not load."); return all_courses_by_term 
    
    is_interactive_debug = observe_and_pause_on_page is not None
    
    if start_page > 1 : 
        print(f"Navigating to specified start page {start_page}...")
        for i in range(start_page - 1):
            if is_interactive_debug: print(f"  Advancing from page {current_actual_page_num} to {current_actual_page_num + 1}")
            if not click_next_page(driver, current_actual_page_num): print(f"Failed to reach page {start_page}. Stopping."); return all_courses_by_term 
            current_actual_page_num += 1
            if is_interactive_debug: print(f"  Successfully advanced to page {current_actual_page_num}. Pausing after next click...")
            time.sleep(5) # <<< 5 second sleep after next page click
        print(f"Reached target start page: {current_actual_page_num}.")
    
    page_being_processed_in_loop = current_actual_page_num
    
    while True:
        if max_pages_to_process and page_being_processed_in_loop > max_pages_to_process:
            print(f"Reached max_pages_to_process {max_pages_to_process}. Stopping."); break
        
        print(f"\n--- Processing PAGE {page_being_processed_in_loop} ---")
        
        if is_interactive_debug and page_being_processed_in_loop == observe_and_pause_on_page:
            print(f"DEBUG: Paused on page {observe_and_pause_on_page}. Browser is visible. Inspect. Press Enter to scrape this page...")
            input()
        
        try:
            WebDriverWait(driver, 30).until(EC.presence_of_element_located((By.ID, "course-resultul")))
            if not is_interactive_debug: print(f"Expanding sections on page {page_being_processed_in_loop}...")
            click_collapsible_buttons(driver) 
            
            if not is_interactive_debug: print(f"Waiting for page elements to settle after expansions on page {page_being_processed_in_loop}...")
            WebDriverWait(driver, 20).until(EC.invisibility_of_element_located((By.CSS_SELECTOR, ".esg-spinner"))) 
            time.sleep(1.5) 
            
            initial_course_elements_on_page = WebDriverWait(driver, 20).until(
                EC.presence_of_all_elements_located((By.CSS_SELECTOR, "#course-resultul > li"))
            )
            num_courses_to_process_this_page = len(initial_course_elements_on_page)
            print(f"Found {num_courses_to_process_this_page} course containers on page {page_being_processed_in_loop}.")

            if not initial_course_elements_on_page:
                print(f"No courses found on page {page_being_processed_in_loop} after expansions.");
                if page_being_processed_in_loop > 1: break 
                else: break
            
            processed_count_this_page = 0
            for i in range(num_courses_to_process_this_page):
                is_curr_debug_course = DEBUG_COURSE_CODE_SUBSTRING and DEBUG_COURSE_CODE_SUBSTRING in initial_course_elements_on_page[i].text # Approx check
                try:
                    current_view_course_elements = driver.find_elements(By.CSS_SELECTOR, "#course-resultul > li")
                    if i >= len(current_view_course_elements):
                        print(f"  Index {i} is now OOB (list size {len(current_view_course_elements)}). DOM changed. Stopping for this page.")
                        break 
                    course_element = current_view_course_elements[i]
                    driver.execute_script("arguments[0].scrollIntoView({block: 'center', behavior: 'auto'});", course_element); 
                    time.sleep(0.2) # Short pause for scroll
                    
                    result = extract_course_details(course_element, page_being_processed_in_loop if is_interactive_debug else 0)

                    if result:
                        course_key, course_data_extracted = result
                        processed_count_this_page +=1
                        sections_by_term = course_data_extracted["Sections"]; num_sections = 0
                        for term_name, sections_list in sections_by_term.items():
                            if sections_list: 
                                if term_name not in all_courses_by_term: all_courses_by_term[term_name] = {}
                                term_data = {k:v for k,v in course_data_extracted.items() if k!="Sections"}
                                term_data["Sections"] = sections_list
                                all_courses_by_term[term_name][course_key] = term_data
                                num_sections += len(sections_list)
                        if num_sections > 0 : print(f"  Processed: {course_key} ({num_sections} sections)")
                        else: print(f"  Processed: {course_key} (0 sections for target terms)") # Still print if processed
                    elif is_curr_debug_course: 
                        print(f"DEBUG_TRACE ... extract_course_details returned None for '{DEBUG_COURSE_CODE_SUBSTRING}'.")
                except StaleElementReferenceException: 
                    print(f"  StaleElement for course index {i}. Skipping."); 
                    continue 
                except Exception as e_course: 
                    print(f"  Error processing course index {i}: {str(e_course)}")
            
            print(f"Finished processing attempts for {processed_count_this_page}/{num_courses_to_process_this_page} courses on page {page_being_processed_in_loop}.")
            save_progress(all_courses_by_term, page_being_processed_in_loop)
            
            if max_pages_to_process and page_being_processed_in_loop >= max_pages_to_process:
                 print(f"Reached max_pages_to_process {max_pages_to_process}. Stopping."); break
            
            print(f"Attempting to navigate to next page from page {page_being_processed_in_loop}.")
            try:
                WebDriverWait(driver, 7).until(EC.presence_of_element_located((By.CSS_SELECTOR, "#course-results-next-page:not([disabled])")))
                if click_next_page(driver, page_being_processed_in_loop): 
                    page_being_processed_in_loop += 1
                    print(f"Successfully navigated to page {page_being_processed_in_loop}. Pausing for 5 seconds...")
                    time.sleep(5) # <<< 5 second sleep after next page click
                else: 
                    print("click_next_page returned False. Assuming end of results."); break
            except TimeoutException: 
                print("No active 'next page' button found. Assuming end of results."); break
        
        except TimeoutException as e_page_timeout: 
            print(f"Page {page_being_processed_in_loop}: Timed out waiting for elements: {str(e_page_timeout)}. Assuming end or loading issue."); break
        except Exception as e_page: 
            print(f"Page {page_being_processed_in_loop}: Critical error: {str(e_page)}"); break
    
    return all_courses_by_term

def save_progress(courses_data_by_term, page_num):
    is_debug_run = TARGET_START_PAGE > 1 or OBSERVE_AND_PAUSE_ON_PAGE is not None or MAX_PAGES_TO_SCRAPE_IN_DEBUG_MODE is not None
    filename_suffix = f"_debug_page{page_num}" if is_debug_run else "_final" # Production saves as _final
    for term_name, term_courses in courses_data_by_term.items():
        if term_courses: 
            term_map = {'Summer 2025':'Summer2025','Fall 2025':'Fall2025','Winter 2026':'Winter2026'}
            if term_name in term_map:
                base_filename = f"output{term_map[term_name]}"
                filename = f"{base_filename}{filename_suffix}.json"
                try:
                    with open(filename, 'w', encoding='utf-8') as f: json.dump(term_courses, f, indent=4, ensure_ascii=False)
                    print(f"  Progress saved to {filename}")
                except IOError as e: print(f"  Error saving to {filename}: {e}")

def main():
    options = Options()
    options.add_argument('--disable-blink-features=AutomationControlled')
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option('useAutomationExtension', False)
    
    is_visual_debug_run = OBSERVE_AND_PAUSE_ON_PAGE is not None or TARGET_START_PAGE > 1
    if is_visual_debug_run:
        print("INFO: Running in VISIBLE browser mode for targeted debugging.")
    else:
        options.add_argument('--headless')
        print("INFO: Running in HEADLESS mode for full scrape.")

    options.add_argument('--no-sandbox'); options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--disable-extensions'); options.add_argument('--disable-gpu')
    options.add_argument('--window-size=1920,1080') 
    options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36")
    options.add_argument("--lang=en-US")
    driver = None 
    try:
        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=options)
        driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})") 
        
        is_full_production_run = TARGET_START_PAGE == 1 and OBSERVE_AND_PAUSE_ON_PAGE is None and MAX_PAGES_TO_SCRAPE_IN_DEBUG_MODE is None
        
        if not is_full_production_run:
            print(f"--- STARTING DEBUG RUN ---")
            print(f"Target Start Page: {TARGET_START_PAGE}, Observe Page: {OBSERVE_AND_PAUSE_ON_PAGE}, Max Pages: {MAX_PAGES_TO_SCRAPE_IN_DEBUG_MODE}")
        else:
            print("--- STARTING FINAL PRODUCTION SCRAPE (AUTOMATED) ---")
        if DEBUG_COURSE_CODE_SUBSTRING: print(f"Specific course debug tracing FOR: {DEBUG_COURSE_CODE_SUBSTRING}")

        final_scraped_data = scrape_all_courses(driver, start_page=TARGET_START_PAGE, 
                                                max_pages_to_process=MAX_PAGES_TO_SCRAPE_IN_DEBUG_MODE, 
                                                observe_and_pause_on_page=OBSERVE_AND_PAUSE_ON_PAGE) 
        
        print("\n--- FINALIZING DATA ---")
        final_save_suffix = "_final_debugrun" if not is_full_production_run else "_final"
        for term_name, term_courses in final_scraped_data.items():
            if term_courses or term_name in ['Summer 2025', 'Fall 2025', 'Winter 2026']: 
                base_name_map = {'Summer 2025':'Summer2025','Fall 2025':'Fall2025','Winter 2026':'Winter2026'}
                if term_name in base_name_map:
                    filename = f"output{base_name_map[term_name]}{final_save_suffix}.json"
                    with open(filename, 'w', encoding='utf-8') as f: json.dump(term_courses, f, indent=4, ensure_ascii=False)
                    print(f"Final save: {len(term_courses)} courses to {filename}")
        
        print("--- SCRAPING PROCESS COMPLETED ---")
        if is_visual_debug_run:
            input("DEBUG: Browser still open (if not headless). Press Enter in console to close browser...")
            
    except Exception as e: 
        print(f"MAIN SCRIPT ERROR: {str(e)}")
        import traceback
        traceback.print_exc()
    finally:
        if driver: 
            print("Closing browser...")
            driver.quit()
        print("Browser closed.")

if __name__ == "__main__":
    main()