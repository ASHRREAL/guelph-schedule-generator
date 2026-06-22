from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import NoSuchElementException, TimeoutException, StaleElementReferenceException
from bs4 import BeautifulSoup
import json
import time
import re

# --- Constants ---
DEBUG_COURSE_CODE_SUBSTRING = ""
TARGET_START_PAGE = 1
OBSERVE_AND_PAUSE_ON_PAGE = None
MAX_PAGES_TO_SCRAPE_IN_DEBUG_MODE = None
SAVE_EVERY_N_PAGES = 5  # Save progress every N pages instead of every page

def time_to_minutes(time_str):
    if not time_str or time_str.strip() == '':
        return 0
    time_str = time_str.strip().upper()
    if ':' not in time_str:
        return 0
    try:
        if 'AM' in time_str or 'PM' in time_str:
            time_part = time_str.replace('AM', '').replace('PM', '').strip()
            is_pm = 'PM' in time_str
        else:
            time_part = time_str
            is_pm = False
        hour, minute = map(int, time_part.split(':'))
        if is_pm and hour != 12:
            hour += 12
        elif not is_pm and hour == 12:
            hour = 0
        return hour * 60 + minute
    except (ValueError, IndexError):
        print(f"Warning: Could not parse time '{time_str}'")
        return 0

def parse_days(days_str):
    if not days_str or days_str.strip() == '':
        return []
    days_str = days_str.strip()
    day_mappings = {
        'M': 'M', 'Mo': 'M', 'Mon': 'M',
        'T': 'T', 'Tu': 'T', 'Tue': 'T', 'Tues': 'T',
        'W': 'W', 'We': 'W', 'Wed': 'W',
        'Th': 'Th', 'R': 'Th', 'Thu': 'Th', 'Thur': 'Th', 'Thurs': 'Th',
        'F': 'F', 'Fr': 'F', 'Fri': 'F',
        'S': 'Sa', 'Sa': 'Sa', 'Sat': 'Sa',
        'Su': 'Su', 'Sun': 'Su'
    }
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
    i = 0
    temp_concatenated_days = []
    current_str = days_str
    while i < len(current_str):
        found_match = False
        if i + 1 < len(current_str):
            two_char_day = current_str[i:i + 2]
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
        if not course_str or course_str.strip() == '':
            return None
        course_str_stripped = course_str.strip()
        if '*' not in course_str_stripped:
            return None
        subcode, rest = course_str_stripped.split('*', 1)
        subcode = subcode.strip()
        rest = rest.strip()
        match = re.match(r'(\d{4})\s*([^a-zA-Z0-9\s]*)\s*(.+)', rest)
        if not match:
            match = re.match(r'(\d{4})\s*(.*)', rest)
        if not match:
            match = re.match(r'(\d{4})(.*)', rest)
        if not match:
            print(f"Warning: Could not parse course code from '{rest}' (original: '{course_str_stripped}')")
            return None
        course_code = match.group(1).strip()
        title_credits_parts = []
        for i in range(2, match.lastindex + 1):
            if match.group(i):
                title_credits_parts.append(match.group(i).strip())
        title_credits = " ".join(filter(None, title_credits_parts)).strip()
        title = title_credits
        credits_val = "0.5"
        credits_pattern_match = re.search(r'\(([\d\.]+)\s*(?:Credit|Credits)?\)$', title_credits, re.IGNORECASE)
        if credits_pattern_match:
            title = title_credits[:credits_pattern_match.start()].strip()
            credits_val = credits_pattern_match.group(1)
        else:
            credits_simple_match = re.search(r'\(([\d\.]+)\)$', title_credits)
            if credits_simple_match:
                title = title_credits[:credits_simple_match.start()].strip()
                credits_val = credits_simple_match.group(1)
        return {
            'subcode': subcode, 'course_code': course_code,
            'title': title, 'credits': credits_val, 'full_title': course_str
        }
    except Exception as e:
        print(f"Error parsing course header '{course_str}': {e}")
        return None

def click_collapsible_buttons(driver):
    """Click all collapsed accordion buttons to expand course sections."""
    try:
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CLASS_NAME, "esg-collapsible-group__toggle"))
        )
        buttons = driver.find_elements(By.CLASS_NAME, "esg-collapsible-group__toggle")
        if not buttons:
            return

        for button in buttons:
            try:
                driver.execute_script("arguments[0].scrollIntoViewIfNeeded(true);", button)
                if not button.is_displayed() or not button.is_enabled():
                    continue
                is_expanded = button.get_attribute("aria-expanded")
                if is_expanded == "false":
                    driver.execute_script("arguments[0].click();", button)
                elif is_expanded != "true":
                    driver.execute_script("arguments[0].click();", button)
            except StaleElementReferenceException:
                pass
            except Exception:
                pass
    except TimeoutException:
        pass
    except Exception:
        pass

def click_next_page(driver, current_page_for_log):
    """Click 'Next Page' button and wait for NEW content to actually load."""
    try:
        next_button = WebDriverWait(driver, 15).until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, "#course-results-next-page:not([disabled])"))
        )

        # Grab a reference to the first course <li> BEFORE clicking next
        old_items = driver.find_elements(By.CSS_SELECTOR, "#course-resultul > li")
        old_first = old_items[0] if old_items else None

        driver.execute_script("arguments[0].click();", next_button)

        # Wait for spinner to appear and then disappear (confirming AJAX round-trip)
        try:
            WebDriverWait(driver, 5).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, ".esg-spinner"))
            )
        except TimeoutException:
            pass  # Spinner might not appear if page loads instantly

        WebDriverWait(driver, 15).until(
            EC.invisibility_of_element_located((By.CSS_SELECTOR, ".esg-spinner"))
        )

        # Wait for the OLD course item to become stale (DOM replaced)
        if old_first:
            try:
                WebDriverWait(driver, 15).until(
                    EC.staleness_of(old_first)
                )
            except TimeoutException:
                pass

        # Wait for new course items to appear
        WebDriverWait(driver, 15).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "#course-resultul li"))
        )
        return True
    except TimeoutException:
        print(f"Timeout next page (from p{current_page_for_log}). Last page?")
        return False
    except Exception as e:
        print(f"Failed next page (from p{current_page_for_log}): {str(e)}")
        return False


# --- BeautifulSoup-based extraction functions ---

def extract_course_details_bs(course_tag):
    """Extract course details from a BeautifulSoup <li> tag."""
    try:
        # Find course title from <h3> or <span>
        h3_text = None
        h3 = course_tag.find('h3')
        if h3:
            h3_text = h3.get_text(strip=True)
        else:
            span = course_tag.select_one("span[id*='course-']")
            if span:
                h3_text = span.get_text(strip=True)
            else:
                text_lines = course_tag.get_text().split('\n')
                if text_lines and re.match(r'^[A-Z]{2,5}\*\d{4}', text_lines[0].strip()):
                    h3_text = text_lines[0].strip()

        if not h3_text:
            print(f"Warning: No course title found. Text: {course_tag.get_text()[:100]}")
            return None

        parsed_header = parse_course_header(h3_text)
        if not parsed_header:
            return None

        course_key = f"{parsed_header['subcode']}*{parsed_header['course_code']}"
        course_data = {
            "Title": parsed_header['full_title'],
            "Description": "",
            "Offering": "",
            "Restriction": "",
            "Department": "",
            "Requisites": "None",
            "Locations": "Guelph",
            "Offered": "",
            "Sections": []
        }

        # Extract metadata from <section> tag
        section_tag = course_tag.find('section')
        if section_tag:
            desc_div = section_tag.select_one("div.search-coursedescription")
            if desc_div:
                for br in desc_div.find_all('br'):
                    br.replace_with('\n')
                course_data["Description"] = desc_div.get_text().strip()

            for item_div in section_tag.select("div[class*='search-coursedetails-left'], div[class*='search-coursedetails-right']"):
                strong_tag = item_div.find('strong')
                if not strong_tag:
                    continue
                label_text = strong_tag.get_text(strip=True).lower()
                value_text = item_div.get_text().replace(strong_tag.get_text(), "").strip()
                if not value_text:
                    sibling = item_div.find_next_sibling('div')
                    if sibling:
                        value_text = sibling.get_text(strip=True)
                if not value_text:
                    continue
                if 'requisite' in label_text:
                    course_data["Requisites"] = value_text
                elif 'location' in label_text:
                    course_data["Locations"] = value_text
                elif 'offered' in label_text and 'also offered as' not in label_text:
                    course_data["Offered"] = value_text
                elif 'department' in label_text:
                    course_data["Department"] = value_text
                elif 'also offered as' in label_text or ('offering' in label_text and 'also' in label_text):
                    course_data["Offering"] = value_text
                elif 'restriction' in label_text:
                    course_data["Restriction"] = value_text

        course_data["Sections"] = extract_sections_by_term_bs(course_tag)
        return course_key, course_data
    except Exception as e:
        print(f"Error extracting course details: {e}")
        return None


def extract_sections_by_term_bs(course_tag):
    """Extract sections organized by term from a BeautifulSoup course tag."""
    sections_by_term = {'Summer 2026': [], 'Fall 2026': [], 'Winter 2027': []}
    try:
        sections_container = course_tag.select_one(".esg-collapsible-group")
        if not sections_container:
            return sections_by_term

        for h4 in sections_container.find_all('h4'):
            term_name = h4.get_text(strip=True)
            if term_name not in sections_by_term:
                continue
            ul = h4.find_next_sibling('ul')
            if not ul:
                continue
            for section_li in ul.find_all('li'):
                section_data = extract_single_section_bs(section_li, term_name)
                if section_data:
                    sections_by_term[term_name].append(section_data)
    except Exception:
        pass
    return sections_by_term


def extract_single_section_bs(section_li, term_name):
    """Extract a single section's data from a BeautifulSoup <li> tag."""
    section_text = section_li.get_text()
    section_id = ""
    section_id_text = "unknown_section"

    # Find section ID
    id_link = section_li.select_one("a.search-sectiondetailslink")
    if id_link and id_link.get_text(strip=True):
        section_id = id_link.get_text(strip=True)
        section_id_text = section_id
    else:
        id_link = section_li.select_one("a[href*='section']")
        if id_link and id_link.get_text(strip=True):
            section_id = id_link.get_text(strip=True)
            section_id_text = section_id
        else:
            pattern = re.search(r'([A-Z]{2,5}\*\d{4}\*[\w-]+)', section_text)
            if pattern:
                section_id = pattern.group(1)
                section_id_text = section_id
            else:
                first_line = section_text.split('\n')[0].strip()
                if re.match(r'^[A-Z]{2,5}\*\d{4}', first_line):
                    section_id = first_line
                    section_id_text = section_id
                else:
                    return None

    if not section_id:
        return None

    section_data = {"id": section_id}
    meetings = {}

    rows = section_li.select("tr.search-sectionrow")
    for row in rows:
        try:
            time_td = row.select_one("td.search-sectiondaystime")
            if not time_td:
                continue

            days_elems = time_td.select("span[id*='-meeting-days-']")
            start_elems = time_td.select("span[id*='-start-']")
            end_elems = time_td.select("span[id*='-end-']")

            days_str = days_elems[0].get_text(strip=True) if days_elems and days_elems[0].get_text(strip=True) else ""
            start_time = start_elems[0].get_text(strip=True) if start_elems and start_elems[0].get_text(strip=True) else ""
            end_time = end_elems[0].get_text(strip=True) if end_elems and end_elems[0].get_text(strip=True) else ""

            loc_td = row.select_one("td.search-sectionlocations")
            if not loc_td:
                continue

            method = ""
            method_elems = loc_td.select("span[id*='-meeting-instructional-method-']")
            if method_elems and method_elems[0].get_text(strip=True):
                method = method_elems[0].get_text(strip=True).upper()
            else:
                valid_methods = {'LEC', 'SEM', 'LAB', 'EXAM', 'TUT', 'FLD', 'CLIN', 'PRA', 'WKS', 'STU', 'IND', 'RES', 'DISTANCE EDUCATION', 'DE'}
                for span in loc_td.find_all('span'):
                    text = span.get_text(strip=True).upper()
                    if text in valid_methods:
                        method = 'DISTANCE EDUCATION' if text in ('DISTANCE EDUCATION', 'DE') else text
                        break

            location = ""
            location_elems = loc_td.select("span[id*='-meeting-location-']")
            if location_elems and location_elems[0].get_text(strip=True):
                location = location_elems[0].get_text(strip=True)

            all_loc_span_texts = [s.get_text(strip=True) for s in loc_td.find_all('span') if s.get_text(strip=True)]
            additional_loc_parts = []
            known_loc_texts = {location, method}
            excluded_texts = {'LEC', 'SEM', 'LAB', 'EXAM', 'TUT', 'FLD', 'CLIN', 'PRA', 'WKS', 'STU', 'IND', 'RES', 'DISTANCE EDUCATION', 'DE', 'TBD'}
            for text_part in all_loc_span_texts:
                if text_part not in known_loc_texts and text_part.upper() not in excluded_texts:
                    additional_loc_parts.append(text_part)
            if additional_loc_parts:
                location = ", ".join(filter(None, [location] + additional_loc_parts))
            elif not location and method != 'DISTANCE EDUCATION':
                td_text_content = loc_td.get_text(strip=True)
                if method and method in td_text_content:
                    td_text_content = td_text_content.replace(method, "").strip()
                if td_text_content:
                    location = td_text_content.strip(', ')

            current_meeting_detail = None
            if method:
                if method == 'DISTANCE EDUCATION':
                    current_meeting_detail = {
                        "start": 0, "end": 0, "date": [],
                        "location": location if location else "ONLINE"
                    }
                elif days_str or start_time or end_time or location:
                    current_meeting_detail = {
                        "start": time_to_minutes(start_time),
                        "end": time_to_minutes(end_time),
                        "date": parse_days(days_str),
                        "location": location
                    }
                if current_meeting_detail:
                    if method not in meetings:
                        meetings[method] = current_meeting_detail
                    else:
                        if not isinstance(meetings[method], list):
                            meetings[method] = [meetings[method]]
                        meetings[method].append(current_meeting_detail)
        except Exception:
            pass

    if meetings:
        section_data.update(meetings)
        return section_data
    return None


# --- Main scraping loop ---

def scrape_all_courses(driver, start_page=1, max_pages_to_process=None, observe_and_pause_on_page=None):
    all_courses_by_term = {'Summer 2026': {}, 'Fall 2026': {}, 'Winter 2027': {}}
    current_actual_page_num = 1

    driver.get("https://colleague-ss.uoguelph.ca/Student/Courses/Search")
    try:
        WebDriverWait(driver, 20).until(EC.presence_of_element_located((By.ID, "course-resultul")))
    except TimeoutException:
        print("Initial course search page did not load.")
        return all_courses_by_term

    is_interactive_debug = observe_and_pause_on_page is not None

    if start_page > 1:
        print(f"Navigating to specified start page {start_page}...")
        for i in range(start_page - 1):
            if not click_next_page(driver, current_actual_page_num):
                print(f"Failed to reach page {start_page}. Stopping.")
                return all_courses_by_term
            current_actual_page_num += 1
        print(f"Reached target start page: {current_actual_page_num}.")

    page_being_processed_in_loop = current_actual_page_num

    while True:
        if max_pages_to_process and page_being_processed_in_loop > max_pages_to_process:
            print(f"Reached max_pages_to_process {max_pages_to_process}. Stopping.")
            break

        print(f"\n--- Processing PAGE {page_being_processed_in_loop} ---")

        if is_interactive_debug and page_being_processed_in_loop == observe_and_pause_on_page:
            print(f"DEBUG: Paused on page {observe_and_pause_on_page}. Press Enter to scrape this page...")
            input()

        try:
            WebDriverWait(driver, 15).until(EC.presence_of_element_located((By.ID, "course-resultul")))

            # Let the page fully settle before interacting with it
            time.sleep(3)

            # Expand all collapsible sections
            print(f"Expanding sections on page {page_being_processed_in_loop}...")
            click_collapsible_buttons(driver)

            # Wait for all AJAX section loads to complete
            time.sleep(2)
            try:
                WebDriverWait(driver, 15).until(
                    EC.invisibility_of_element_located((By.CSS_SELECTOR, ".esg-spinner"))
                )
            except TimeoutException:
                pass
            time.sleep(1)

            # Get the full page HTML once and parse with BeautifulSoup
            soup = BeautifulSoup(driver.page_source, 'html.parser')
            course_items = soup.select("#course-resultul > li")
            num_courses = len(course_items)
            print(f"Found {num_courses} course containers on page {page_being_processed_in_loop}.")

            if not course_items:
                print(f"No courses found on page {page_being_processed_in_loop}.")
                break

            processed_count = 0
            for i, course_li in enumerate(course_items):
                try:
                    result = extract_course_details_bs(course_li)
                    if result:
                        course_key, course_data_extracted = result
                        processed_count += 1
                        sections_by_term = course_data_extracted["Sections"]
                        num_sections = 0
                        for term_name, sections_list in sections_by_term.items():
                            if sections_list:
                                if term_name not in all_courses_by_term:
                                    all_courses_by_term[term_name] = {}
                                term_data = {k: v for k, v in course_data_extracted.items() if k != "Sections"}
                                term_data["Sections"] = sections_list
                                all_courses_by_term[term_name][course_key] = term_data
                                num_sections += len(sections_list)
                        if num_sections > 0:
                            print(f"  Processed: {course_key} ({num_sections} sections)")
                        else:
                            print(f"  Processed: {course_key} (0 sections for target terms)")
                except Exception as e:
                    print(f"  Error processing course index {i}: {e}")

            print(f"Finished processing {processed_count}/{num_courses} courses on page {page_being_processed_in_loop}.")

            # Save progress every N pages (and on max pages / last page)
            if page_being_processed_in_loop % SAVE_EVERY_N_PAGES == 0:
                save_progress(all_courses_by_term, page_being_processed_in_loop)
            elif max_pages_to_process and page_being_processed_in_loop >= max_pages_to_process:
                save_progress(all_courses_by_term, page_being_processed_in_loop)

            if max_pages_to_process and page_being_processed_in_loop >= max_pages_to_process:
                print(f"Reached max_pages_to_process {max_pages_to_process}. Stopping.")
                break

            # Navigate to next page
            print(f"Navigating to next page from page {page_being_processed_in_loop}.")
            try:
                WebDriverWait(driver, 7).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "#course-results-next-page:not([disabled])"))
                )
                if click_next_page(driver, page_being_processed_in_loop):
                    page_being_processed_in_loop += 1
                    print(f"Successfully navigated to page {page_being_processed_in_loop}.")
                else:
                    print("click_next_page returned False. Assuming end of results.")
                    save_progress(all_courses_by_term, page_being_processed_in_loop)
                    break
            except TimeoutException:
                print("No active 'next page' button found. Assuming end of results.")
                save_progress(all_courses_by_term, page_being_processed_in_loop)
                break

        except TimeoutException as e:
            print(f"Page {page_being_processed_in_loop}: Timed out waiting for elements: {e}. Assuming end.")
            save_progress(all_courses_by_term, page_being_processed_in_loop)
            break
        except Exception as e:
            print(f"Page {page_being_processed_in_loop}: Critical error: {e}")
            save_progress(all_courses_by_term, page_being_processed_in_loop)
            break

    return all_courses_by_term


def save_progress(courses_data_by_term, page_num):
    is_debug_run = TARGET_START_PAGE > 1 or OBSERVE_AND_PAUSE_ON_PAGE is not None or MAX_PAGES_TO_SCRAPE_IN_DEBUG_MODE is not None
    filename_suffix = f"_debug_page{page_num}" if is_debug_run else "_final"
    for term_name, term_courses in courses_data_by_term.items():
        if term_courses:
            term_map = {'Summer 2026': 'Summer2026', 'Fall 2026': 'Fall2026', 'Winter 2027': 'Winter2027'}
            if term_name in term_map:
                base_filename = f"output{term_map[term_name]}"
                filename = f"{base_filename}{filename_suffix}.json"
                try:
                    with open(filename, 'w', encoding='utf-8') as f:
                        json.dump(term_courses, f, indent=4, ensure_ascii=False)
                    print(f"  Progress saved to {filename}")
                except IOError as e:
                    print(f"  Error saving to {filename}: {e}")


def main():
    options = Options()
    options.add_argument('--disable-blink-features=AutomationControlled')
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option('useAutomationExtension', False)

    is_visual_debug_run = OBSERVE_AND_PAUSE_ON_PAGE is not None or TARGET_START_PAGE > 1
    if is_visual_debug_run:
        print("INFO: Running in VISIBLE browser mode for targeted debugging.")
    else:
        options.add_argument('--head=new')
        print("INFO: Running in HEADLESS mode for full scrape.")

    # Performance-optimized browser flags
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--disable-extensions')
    options.add_argument('--disable-gpu')
    options.add_argument('--window-size=1920,1080')
    options.add_argument('--disable-background-networking')
    options.add_argument('--disable-sync')
    options.add_argument('--disable-default-apps')
    options.add_argument('--disable-translate')
    options.add_argument('--disable-web-security')
    options.add_argument('--disable-features=TranslateUI')
    options.add_argument('--metrics-recording-only')
    options.add_argument('--mute-audio')
    options.add_argument('--no-first-run')
    options.add_argument('--safebrowsing-disable-auto-update')
    options.add_argument('--blink-settings=imagesEnabled=false')
    options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36")
    options.add_argument("--lang=en-US")

    # Reduce logging
    options.add_argument('--log-level=3')
    options.add_argument('--silent')

    driver = None
    try:
        options.binary_location = '/usr/bin/chromium'
        driver = webdriver.Chrome(options=options)
        driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")

        is_full_production_run = TARGET_START_PAGE == 1 and OBSERVE_AND_PAUSE_ON_PAGE is None and MAX_PAGES_TO_SCRAPE_IN_DEBUG_MODE is None

        if not is_full_production_run:
            print(f"--- STARTING DEBUG RUN ---")
            print(f"Target Start Page: {TARGET_START_PAGE}, Observe Page: {OBSERVE_AND_PAUSE_ON_PAGE}, Max Pages: {MAX_PAGES_TO_SCRAPE_IN_DEBUG_MODE}")
        else:
            print("--- STARTING FINAL PRODUCTION SCRAPE (AUTOMATED) ---")
        if DEBUG_COURSE_CODE_SUBSTRING:
            print(f"Specific course debug tracing FOR: {DEBUG_COURSE_CODE_SUBSTRING}")

        final_scraped_data = scrape_all_courses(
            driver, start_page=TARGET_START_PAGE,
            max_pages_to_process=MAX_PAGES_TO_SCRAPE_IN_DEBUG_MODE,
            observe_and_pause_on_page=OBSERVE_AND_PAUSE_ON_PAGE
        )

        print("\n--- FINALIZING DATA ---")
        final_save_suffix = "_final_debugrun" if not is_full_production_run else "_final"
        for term_name, term_courses in final_scraped_data.items():
            if term_courses or term_name in ['Summer 2026', 'Fall 2026', 'Winter 2027']:
                base_name_map = {'Summer 2026': 'Summer2026', 'Fall 2026': 'Fall2026', 'Winter 2027': 'Winter2027'}
                if term_name in base_name_map:
                    filename = f"output{base_name_map[term_name]}{final_save_suffix}.json"
                    with open(filename, 'w', encoding='utf-8') as f:
                        json.dump(term_courses, f, indent=4, ensure_ascii=False)
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
