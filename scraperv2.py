"""
FINAL PRODUCTION University of Guelph Course Scraper
Generates complete datasets for Summer 2025, Fall 2025, Winter 2026
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

def time_to_minutes(time_str):
    """Convert time string like '8:30 AM' to minutes since midnight"""
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
    """Parse days string like 'M/W' or 'T Th' into array format"""
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

    if '/' in days_str:
        parts = days_str.split('/')
        result = []
        for part in parts:
            part = part.strip()
            if part in day_mappings:
                result.append(day_mappings[part])
        if result:
            return result

    if ' ' in days_str:
        parts = days_str.split()
        result = []
        for part in parts:
            if part in day_mappings:
                result.append(day_mappings[part])
        if result:
            return result

    result = []
    i = 0
    while i < len(days_str):
        if i < len(days_str) - 1 and days_str[i:i+2] in day_mappings:
            result.append(day_mappings[days_str[i:i+2]])
            i += 2
        elif days_str[i] in day_mappings:
            result.append(day_mappings[days_str[i]])
            i += 1
        else:
            i += 1

    return result if result else [days_str]

def parse_course_header(course_str):
    """Parse course header like 'ACCT*1220 Intro Financial Accounting (0.5 Credits)'"""
    try:
        if not course_str or course_str.strip() == '':
            return None

        course_str = course_str.strip()

        if '*' not in course_str:
            return None

        subcode, rest = course_str.split('*', 1)

        match = re.match(r'(\d{4})\s+(.+)', rest)
        if not match:

            match = re.match(r'(\d{4})(.+)', rest)
            if not match:
                print(f"Warning: Could not parse course code from '{rest}'")
                return None

        course_code = match.group(1)
        title_credits = match.group(2).strip()

        credits_start = title_credits.rfind('(')
        if credits_start == -1:

            title = title_credits
            credits = "0.5"  
        else:
            title = title_credits[:credits_start].strip()
            credits_str = title_credits[credits_start+1:-1]

            credits_match = re.search(r'\d+\.?\d*', credits_str)
            credits = credits_match.group() if credits_match else "0.5"

        return {
            'subcode': subcode,
            'course_code': course_code,
            'title': title,
            'credits': credits,
            'full_title': course_str
        }
    except Exception as e:
        print(f"Error parsing course header '{course_str}': {e}")
        return None

def click_collapsible_buttons(driver):
    """Click all collapsible buttons to expand course sections"""
    try:
        buttons = WebDriverWait(driver, 10).until(
            EC.presence_of_all_elements_located((By.CLASS_NAME, "esg-collapsible-group__toggle"))
        )
        for index, button in enumerate(buttons):
            try:
                driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", button)
                button.click()
                time.sleep(0.3)
            except Exception as e:
                driver.execute_script("arguments[0].click();", button)
    except Exception as e:
        print(f"Error clicking collapsible buttons: {str(e)}")

def click_next_page(driver, current_page):
    """Navigate to the next page of results"""
    try:
        next_button = WebDriverWait(driver, 15).until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, "#course-results-next-page:not([disabled])"))
        )
        driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", next_button)
        driver.execute_script("arguments[0].click();", next_button)

        WebDriverWait(driver, 30).until(
            EC.invisibility_of_element_located((By.CSS_SELECTOR, ".esg-spinner"))
        )
        WebDriverWait(driver, 30).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "#course-resultul li"))
        )
        return True
    except Exception as e:
        print(f"Failed to navigate to next page: {str(e)}")
        return False

def extract_course_details(course_element):
    """Extract course details and convert to target JSON format"""
    try:

        h3_text = None
        try:
            h3 = course_element.find_element(By.TAG_NAME, "h3")
            h3_text = h3.text
        except NoSuchElementException:

            try:
                span_element = course_element.find_element(By.CSS_SELECTOR, "span[id*='course-']")
                h3_text = span_element.text
            except NoSuchElementException:

                try:
                    all_text = course_element.text
                    course_pattern = re.search(r'([A-Z]{2,4})\*(\d{4})', all_text)
                    if course_pattern:
                        h3_text = all_text.split('\n')[0]  
                except:
                    pass

        if not h3_text:
            print("Warning: Could not find course title in element")
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

        try:
            section = course_element.find_element(By.TAG_NAME, "section")

            try:
                desc_div = section.find_element(By.CSS_SELECTOR, "div.search-coursedescription")
                course_data["Description"] = desc_div.text.strip()
            except NoSuchElementException:
                pass

            try:
                fr_divs = section.find_elements(By.XPATH, ".//div")
                for i in range(0, len(fr_divs)-1, 2):
                    try:
                        key = fr_divs[i].text.strip()
                        value = fr_divs[i+1].text.strip()

                        if 'requisites' in key.lower():
                            course_data["Requisites"] = value
                        elif 'location' in key.lower():
                            course_data["Locations"] = value
                        elif 'offered' in key.lower():
                            course_data["Offered"] = value
                        elif 'department' in key.lower():
                            course_data["Department"] = value
                        elif 'offering' in key.lower():
                            course_data["Offering"] = value
                        elif 'restriction' in key.lower():
                            course_data["Restriction"] = value
                    except (StaleElementReferenceException, NoSuchElementException):
                        continue
            except Exception:
                pass

        except NoSuchElementException:
            pass

        course_data["Sections"] = extract_sections_by_term_correct(course_element)

        return course_key, course_data

    except Exception as e:
        print(f"Error extracting course details: {e}")
        return None

def extract_sections_by_term_correct(course_element):
    """Extract section information organized by term using correct HTML structure"""
    sections_by_term = {
        'Summer 2025': [],
        'Fall 2025': [],
        'Winter 2026': []
    }

    try:
        sections_container = course_element.find_element(By.CSS_SELECTOR, ".esg-collapsible-group")

        term_headers = sections_container.find_elements(By.TAG_NAME, "h4")

        for term_header in term_headers:
            try:
                term_name = term_header.text.strip()

                try:
                    following_ul = term_header.find_element(By.XPATH, "./following-sibling::ul[1]")

                    section_items = following_ul.find_elements(By.TAG_NAME, "li")

                    for section_li in section_items:
                        section_data = extract_single_section(section_li, term_name)
                        if section_data and term_name in sections_by_term:
                            sections_by_term[term_name].append(section_data)

                except NoSuchElementException:
                    pass

            except (NoSuchElementException, StaleElementReferenceException) as e:
                continue

    except (NoSuchElementException, StaleElementReferenceException) as e:
        pass

    return sections_by_term

def extract_single_section(section_li, term_name):
    """Extract data for a single section, handling multiple meetings for the same type (e.g., multiple LABs)."""
    try:

        section_id = ""
        try:
            section_id_link = section_li.find_element(By.CSS_SELECTOR, "a.search-sectiondetailslink")

            section_id = section_id_link.text.strip() if section_id_link.text else ""
        except NoSuchElementException:
            try:
                section_id_link = section_li.find_element(By.CSS_SELECTOR, "a[href*='section']")
                section_id = section_id_link.text.strip() if section_id_link.text else ""
            except NoSuchElementException:
                pass

        if not section_id: 
            text_content = section_li.text
            section_pattern = re.search(r'([A-Z]{2,5}\*\d{4}\*\w+)', text_content) 
            if section_pattern:
                section_id = section_pattern.group(1)
            else:
                print(f"Warning: Could not find section ID in: {text_content[:100]}")
                return None

        if not section_id: 
            return None

        section_data = {"id": section_id}
        meetings = {} 

        try:
            rows = section_li.find_elements(By.CSS_SELECTOR, "tr.search-sectionrow")
            for row in rows:
                try:
                    time_td = row.find_element(By.CSS_SELECTOR, "td.search-sectiondaystime")
                    days_elems = time_td.find_elements(By.CSS_SELECTOR, "span[id*='-meeting-days-']")
                    start_elems = time_td.find_elements(By.CSS_SELECTOR, "span[id*='-start-']")
                    end_elems = time_td.find_elements(By.CSS_SELECTOR, "span[id*='-end-']")

                    days_str = days_elems[0].text.strip() if days_elems else ""
                    start_time = start_elems[0].text.strip() if start_elems else ""
                    end_time = end_elems[0].text.strip() if end_elems else ""

                    loc_td = row.find_element(By.CSS_SELECTOR, "td.search-sectionlocations")
                    method = ""
                    method_elems = loc_td.find_elements(By.CSS_SELECTOR, "span[id*='-meeting-instructional-method-']")
                    if method_elems and method_elems[0].text.strip():
                        method = method_elems[0].text.strip().upper()
                    else:
                        all_spans_in_loc = loc_td.find_elements(By.TAG_NAME, "span")
                        for span in all_spans_in_loc:
                            text = span.text.strip().upper()

                            if text in ['LEC', 'SEM', 'LAB', 'EXAM', 'TUT', 'FLD', 'CLIN', 'PRA', 'WKS', 'STU', 'IND', 'RES', 'DISTANCE EDUCATION']:
                                method = 'DISTANCE EDUCATION' if text == 'DISTANCE EDUCATION' else text
                                break 

                    location = ""
                    location_elems = loc_td.find_elements(By.CSS_SELECTOR, "span[id*='-meeting-location-']")
                    if location_elems and location_elems[0].text.strip():
                        location = location_elems[0].text.strip()

                    all_loc_texts = [s.text.strip() for s in loc_td.find_elements(By.TAG_NAME, "span")]
                    processed_texts_for_loc = set()
                    if method_elems and method_elems[0].text.strip(): processed_texts_for_loc.add(method_elems[0].text.strip())
                    if location_elems and location_elems[0].text.strip(): processed_texts_for_loc.add(location_elems[0].text.strip())

                    additional_loc_info = []
                    for text in all_loc_texts:
                        if text and text not in processed_texts_for_loc and text.upper() not in ['LEC', 'SEM', 'LAB', 'EXAM', 'TUT', 'DISTANCE EDUCATION']:
                            additional_loc_info.append(text)

                    if additional_loc_info:
                        full_location_str = ", ".join([loc for loc in [location] + additional_loc_info if loc])
                        location = full_location_str
                    elif not location and method != 'DISTANCE EDUCATION': 
                        td_text_content = loc_td.text.strip()

                        if method and method in td_text_content:
                            td_text_content = td_text_content.replace(method, "").strip()
                        if td_text_content:
                            location = td_text_content

                    if method:
                        current_meeting_detail = None 
                        if method == 'DISTANCE EDUCATION':
                            current_meeting_detail = {
                                "start": 0,
                                "end": 0,
                                "date": [],
                                "location": location if location else "ONLINE"
                            }
                        elif days_str or start_time or end_time: 
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

                except (NoSuchElementException, StaleElementReferenceException):

                    continue

        except (NoSuchElementException, StaleElementReferenceException):

            pass 

        if meetings:
            section_data.update(meetings)
            return section_data
        else:

            return None

    except Exception as e:
        print(f"Warning: Error extracting section details for section ID '{section_id if 'section_id' in locals() and section_id else 'unknown'}': {str(e)}")
        return None

def scrape_all_courses(driver, max_pages=None):
    """Scrape all courses from the website"""
    all_courses_by_term = {
        'Summer 2025': {},
        'Fall 2025': {},
        'Winter 2026': {}
    }
    current_page = 1

    driver.get("https://colleague-ss.uoguelph.ca/Student/Courses/Search")

    while True:
        if max_pages and current_page > max_pages:
            break

        print(f"\nProcessing PAGE {current_page}")

        try:
            click_collapsible_buttons(driver)

            course_list = WebDriverWait(driver, 30).until(
                EC.presence_of_element_located((By.ID, "course-resultul"))
            )
            courses = course_list.find_elements(By.TAG_NAME, "li")

            print(f"Found {len(courses)} courses on page {current_page}")

            for idx in range(len(courses)):
                try:

                    courses = driver.find_elements(By.CSS_SELECTOR, "#course-resultul li")
                    if idx >= len(courses):
                        break
                    course = courses[idx]

                    result = extract_course_details(course)
                    if result:
                        course_key, course_data = result

                        sections_by_term = course_data["Sections"]

                        for term_name, sections in sections_by_term.items():
                            if sections:  

                                term_course_data = {
                                    "Title": course_data["Title"],
                                    "Description": course_data["Description"],
                                    "Offering": course_data["Offering"],
                                    "Restriction": course_data["Restriction"],
                                    "Department": course_data["Department"],
                                    "Requisites": course_data["Requisites"],
                                    "Locations": course_data["Locations"],
                                    "Offered": course_data["Offered"],
                                    "Sections": sections  
                                }
                                all_courses_by_term[term_name][course_key] = term_course_data

                        total_sections = sum(len(sections) for sections in sections_by_term.values())
                        print(f"  Processed: {course_key} ({total_sections} sections across all terms)")

                except Exception as e:
                    print(f"  Error processing course {idx+1}: {str(e)}")
                    continue

            save_progress(all_courses_by_term, current_page)

            try:
                next_button = driver.find_element(By.CSS_SELECTOR, "#course-results-next-page:not([disabled])")
                if click_next_page(driver, current_page):
                    current_page += 1
                    time.sleep(2)
                else:
                    break
            except NoSuchElementException:
                print("No more pages available")
                break

        except Exception as e:
            print(f"Critical error on page {current_page}: {str(e)}")

            save_progress(all_courses_by_term, current_page)
            break

    return all_courses_by_term

def save_progress(courses_data_by_term, page_num):
    """Save progress to the same final files after each page"""
    for term_name, term_courses in courses_data_by_term.items():
        if term_courses:

            term_filename_map = {
                'Summer 2025': 'Summer2025_final',
                'Fall 2025': 'Fall2025_final', 
                'Winter 2026': 'Winter2026_final'
            }

            filename = f"output{term_filename_map[term_name]}.json"
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(term_courses, f, indent=4, ensure_ascii=False)

            print(f"  Progress saved: {len(term_courses)} courses to {filename} (after page {page_num})")

def load_existing_progress():
    """Load existing progress files if they exist"""
    all_courses_by_term = {
        'Summer 2025': {},
        'Fall 2025': {},
        'Winter 2026': {}
    }

    term_filename_map = {
        'Summer 2025': 'Summer2025_final',
        'Fall 2025': 'Fall2025_final', 
        'Winter 2026': 'Winter2026_final'
    }

    for term_name, filename_base in term_filename_map.items():
        filename = f"output{filename_base}.json"
        try:
            with open(filename, 'r', encoding='utf-8') as f:
                data = json.load(f)
                all_courses_by_term[term_name] = data
                print(f"Loaded existing data: {len(data)} courses from {filename}")
        except FileNotFoundError:
            print(f"No existing file found: {filename}")

    return all_courses_by_term

def main():
    """Main scraping function"""

    options = Options()
    options.add_argument('--disable-blink-features=AutomationControlled')
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option('useAutomationExtension', False)
    options.add_argument('--headless')  
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--disable-extensions')
    options.add_argument('--disable-gpu')
    options.add_argument('--window-size=1920,1080')

    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)

    try:
        print("Starting FINAL PRODUCTION course scraping...")
        print("This will generate complete datasets for all terms")

        courses_data_by_term = load_existing_progress()

        updated_courses = scrape_all_courses(driver, max_pages=None)  

        for term_name in courses_data_by_term:
            if term_name in updated_courses:
                courses_data_by_term[term_name].update(updated_courses[term_name])

        for term_name, term_courses in courses_data_by_term.items():
            if term_courses:

                term_filename_map = {
                    'Summer 2025': 'Summer2025_final',
                    'Fall 2025': 'Fall2025_final', 
                    'Winter 2026': 'Winter2026_final'
                }

                filename = f"output{term_filename_map[term_name]}.json"
                with open(filename, 'w', encoding='utf-8') as f:
                    json.dump(term_courses, f, indent=4, ensure_ascii=False)

                print(f"Saved {len(term_courses)} courses to {filename}")
            else:
                print(f"No courses found for {term_name}")

    except Exception as e:
        print(f"Main error: {str(e)}")
        import traceback
        traceback.print_exc()
    finally:
        driver.quit()

if __name__ == "__main__":
    main()