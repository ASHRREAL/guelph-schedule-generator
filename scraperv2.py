#!/usr/bin/env python3
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
        elif not is_pm and hour == 12: # 12 AM is midnight
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
    
    # Handle common multi-character days first
    days_str = days_str.replace("Mon", "M").replace("Tue", "T").replace("Wed", "W")
    days_str = days_str.replace("Thur", "Th").replace("Thu", "Th").replace("Thurs", "Th")
    days_str = days_str.replace("Fri", "F").replace("Sat", "Sa").replace("Sun", "Su")

    parsed_days = []
    
    # Try splitting by common delimiters like '/' or space if they exist
    if '/' in days_str:
        parts = days_str.split('/')
    elif ' ' in days_str:
        parts = days_str.split(' ')
    else: # Assume concatenated if no clear delimiter
        temp_parts = []
        i = 0
        while i < len(days_str):
            if days_str[i:i+2] == "Th":
                temp_parts.append("Th")
                i += 2
            elif days_str[i] in day_mappings:
                temp_parts.append(days_str[i])
                i += 1
            else: # Skip unrecognized char
                i += 1
        parts = temp_parts

    for part in parts:
        clean_part = part.strip()
        if clean_part in day_mappings:
            parsed_days.append(day_mappings[clean_part])
        elif clean_part: # If part is not empty and not in mappings, add as is (or log warning)
            # print(f"Warning: Unrecognized day part '{clean_part}' in '{days_str}'")
            parsed_days.append(clean_part) # Or decide to ignore

    # Remove duplicates while preserving order
    ordered_unique_days = []
    for day in parsed_days:
        if day not in ordered_unique_days:
            ordered_unique_days.append(day)
            
    return ordered_unique_days


def parse_course_header(course_str):
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
                
    course_code_num = match.group(1)
    title_credits = match.group(2).strip()
    
    credits_start = title_credits.rfind('(')
    if credits_start == -1 or not title_credits.endswith('Credits)'):
        title = title_credits
        credits = "0.5" 
    else:
        title = title_credits[:credits_start].strip()
        credits_str = title_credits[credits_start+1:-1] 
        credits_match = re.search(r'\d+\.?\d*', credits_str)
        credits = credits_match.group() if credits_match else "0.5"
    
    return {
        'subcode': subcode,
        'course_code': course_code_num,
        'title': title,
        'credits': credits,
        'full_title': course_str
    }

def click_collapsible_buttons(driver):
    try:
        buttons = WebDriverWait(driver, 10).until(
            EC.presence_of_all_elements_located((By.CLASS_NAME, "esg-collapsible-group__toggle"))
        )
        for index in range(len(buttons)):
            # Re-fetch buttons in each iteration to handle potential DOM changes
            current_buttons = driver.find_elements(By.CLASS_NAME, "esg-collapsible-group__toggle")
            if index >= len(current_buttons): break # Stop if index out of bounds
            button = current_buttons[index]
            try:
                # Check if already expanded (aria-expanded="true")
                if button.get_attribute("aria-expanded") == "true":
                    continue 

                driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", button)
                time.sleep(0.1) # Brief pause for scrolling
                # Use JavaScript click as it's more reliable
                driver.execute_script("arguments[0].click();", button)
                time.sleep(0.3) # Wait for content to expand
            except Exception as e:
                # Fallback if other methods fail
                try:
                    button.click()
                    time.sleep(0.3)
                except Exception as e_click:
                    print(f"  Error clicking button {index + 1}: {e_click}")
    except Exception as e:
        print(f"Error finding/clicking collapsible buttons: {str(e)}")


def click_next_page(driver, current_page):
    try:
        next_button = WebDriverWait(driver, 15).until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, "#course-results-next-page:not([disabled])"))
        )
        driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", next_button)
        driver.execute_script("arguments[0].click();", next_button)
        
        WebDriverWait(driver, 30).until(
            EC.invisibility_of_element_located((By.CSS_SELECTOR, ".esg-spinner"))
        )
        # Wait for the presence of course results, and also that the current page number in URL updates or content changes.
        # This is a bit tricky if page number isn't in URL. A more robust wait might be needed.
        WebDriverWait(driver, 30).until(
            lambda d: d.find_element(By.ID, "course-resultul") and \
                      len(d.find_elements(By.CSS_SELECTOR, "#course-resultul li")) > 0
        )
        return True
    except TimeoutException:
        print("Timeout waiting for next page to load or next button disappeared.")
        return False
    except Exception as e:
        print(f"Failed to navigate to next page: {str(e)}")
        return False

def extract_course_details(course_element):
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
            "Title": parsed_header['full_title'], "Description": "", "Offering": "",
            "Restriction": "", "Department": "", "Requisites": "None",
            "Locations": "Guelph", "Offered": "", "Sections": []
        }
        
        try:
            section_details_container = course_element.find_element(By.TAG_NAME, "section")
            
            try:
                desc_div = section_details_container.find_element(By.CSS_SELECTOR, "div.search-coursedescription")
                course_data["Description"] = desc_div.text.strip()
            except NoSuchElementException: pass
            
            try:
                # More robust extraction of key-value pairs from course details section
                potential_detail_divs = section_details_container.find_elements(By.XPATH, "./div[string-length(normalize-space(.)) > 0]")
                # Iterate through pairs of divs if structure is consistent (label div, value div)
                # This needs to be adapted based on the actual HTML structure of these details
                # For now, let's assume a less strict parsing
                all_text_content = section_details_container.text.split('\n')
                for line in all_text_content:
                    if ':' in line:
                        key, value = line.split(':', 1)
                        key = key.strip().lower()
                        value = value.strip()
                        if 'requisites' in key: course_data["Requisites"] = value
                        elif 'location' in key: course_data["Locations"] = value
                        elif 'offered' in key: course_data["Offered"] = value
                        elif 'department' in key: course_data["Department"] = value
                        elif 'offering information' in key: course_data["Offering"] = value # Example
                        elif 'restrictions' in key: course_data["Restriction"] = value # Example
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
    sections_by_term = {
        'Summer 2025': [], 'Fall 2025': [], 'Winter 2026': []
    }
    
    try:
        collapsible_group = course_element.find_element(By.CSS_SELECTOR, ".esg-collapsible-group")
        
        term_headers = collapsible_group.find_elements(By.TAG_NAME, "h4")
        
        for term_header_element in term_headers:
            try:
                term_name = term_header_element.text.strip()
                if term_name not in sections_by_term: # Skip if term not recognized
                    continue

                # Find the UL that is the next sibling of this H4
                ul_element = term_header_element.find_element(By.XPATH, "./following-sibling::ul[1]")
                section_li_elements = ul_element.find_elements(By.TAG_NAME, "li")
                
                for section_li in section_li_elements:
                    section_data_dict = extract_single_section(section_li, term_name)
                    if section_data_dict:
                        sections_by_term[term_name].append(section_data_dict)
                            
            except (NoSuchElementException, StaleElementReferenceException) as e:
                # print(f"  Skipping term header due to: {e}")
                continue
                
    except (NoSuchElementException, StaleElementReferenceException) as e:
        # print(f"  No collapsible group found for sections: {e}")
        pass
    
    return sections_by_term

def extract_single_section(section_li, term_name):
    try:
        section_id = ""
        try:
            # Prioritize the link with section details
            link_element = section_li.find_element(By.CSS_SELECTOR, "a.search-sectiondetailslink")
            section_id = link_element.text.strip()
        except NoSuchElementException:
            # Fallback if the specific class isn't found
            try:
                # Look for any link that seems to contain a section ID pattern
                all_links = section_li.find_elements(By.TAG_NAME, "a")
                for link in all_links:
                    text = link.text.strip()
                    if re.match(r'^[A-Z]{2,4}\*\d{4}\*\w+$', text):
                        section_id = text
                        break
                if not section_id: # If no link matched, try to get from text
                    text_content = section_li.text
                    section_pattern = re.search(r'([A-Z]{2,4}\*\d{4}\*\w+)', text_content)
                    if section_pattern:
                        section_id = section_pattern.group(1)
            except NoSuchElementException:
                 pass # Will be caught by "if not section_id"
        
        if not section_id:
            # print(f"Warning: Could not find section ID in list item: {section_li.text[:100]}")
            return None
            
        # Initialize meetings as a dictionary where keys are 'LEC', 'LAB', 'SEM'
        # and values are LISTS of meeting details.
        meetings_data = {"LEC": [], "LAB": [], "SEM": []} 
        
        try:
            # Find all rows representing meetings for this section
            meeting_rows = section_li.find_elements(By.CSS_SELECTOR, "tr.search-sectionrow")
            for row in meeting_rows:
                try:
                    # Time, Days
                    time_td = row.find_element(By.CSS_SELECTOR, "td.search-sectiondaystime")
                    days_str = ""
                    start_time_str = ""
                    end_time_str = ""
                    try: days_str = time_td.find_element(By.CSS_SELECTOR, "span[id*='-meeting-days-']").text.strip()
                    except NoSuchElementException: pass
                    try: start_time_str = time_td.find_element(By.CSS_SELECTOR, "span[id*='-start-']").text.strip()
                    except NoSuchElementException: pass
                    try: end_time_str = time_td.find_element(By.CSS_SELECTOR, "span[id*='-end-']").text.strip()
                    except NoSuchElementException: pass

                    # Location, Method
                    loc_td = row.find_element(By.CSS_SELECTOR, "td.search-sectionlocations")
                    method_str = ""
                    location_str = ""
                    
                    try: method_str = loc_td.find_element(By.CSS_SELECTOR, "span[id*='-meeting-instructional-method-']").text.strip().upper()
                    except NoSuchElementException: # Fallback for method if specific span not found
                        all_spans_in_loc = loc_td.find_elements(By.TAG_NAME, "span")
                        for span in all_spans_in_loc:
                            text = span.text.strip().upper()
                            if text in ['LEC', 'SEM', 'LAB', 'EXAM', 'TUTORIAL', 'DISTANCE EDUCATION']: # Added TUTORIAL
                                method_str = text
                                break
                    
                    try: location_str = loc_td.find_element(By.CSS_SELECTOR, "span[id*='-meeting-location-']").text.strip()
                    except NoSuchElementException: # Fallback for location
                        # Try to construct location from other spans if primary not found
                        all_spans_in_loc = loc_td.find_elements(By.TAG_NAME, "span")
                        temp_loc_parts = []
                        for span in all_spans_in_loc:
                            text = span.text.strip()
                            # Avoid picking up method string or known non-location parts
                            if text and text.upper() not in ['LEC', 'SEM', 'LAB', 'EXAM', 'TUTORIAL', 'DISTANCE EDUCATION']:
                                temp_loc_parts.append(text)
                        location_str = ", ".join(temp_loc_parts)
                    
                    meeting_detail = {}
                    if method_str in ['LEC', 'LAB', 'SEM']: # Only process known types
                        if method_str == 'DISTANCE EDUCATION' or not days_str and not start_time_str: # Handle DE or TBD times
                            meeting_detail = {
                                "start": 0, "end": 0, "date": [], "location": location_str or "Online"
                            }
                        else:
                            meeting_detail = {
                                "start": time_to_minutes(start_time_str),
                                "end": time_to_minutes(end_time_str),
                                "date": parse_days(days_str),
                                "location": location_str
                            }
                        
                        # Append to the list for this meeting type
                        if method_str in meetings_data:
                             meetings_data[method_str].append(meeting_detail)
                        # else: # Handle new/unexpected meeting types if needed
                        #     meetings_data[method_str] = [meeting_detail]


                except (NoSuchElementException, StaleElementReferenceException) as e_row:
                    # print(f"    Skipping a meeting row due to: {e_row}")
                    continue
        
        except (NoSuchElementException, StaleElementReferenceException) as e_meetings:
            # print(f"  No meeting rows found or error: {e_meetings}")
            pass
        
        # Construct the final section dictionary, only including types that have meetings
        final_section_data = {"id": section_id}
        for type_key, meeting_list in meetings_data.items():
            if meeting_list: # Only add if there are actual meetings for this type
                # For compatibility with your existing JSON structure, if there's only one meeting
                # for a type, you might want to store it directly, not as a list.
                # However, to correctly handle multiple labs/lecs, storing as a list is better.
                # Your downstream code (Main.py) will need to be adapted if it expects a single object.
                # **For now, I will assume your Main.py will be adapted to handle a list of meetings per type.**
                # If your Main.py strictly expects ONE entry per LEC/LAB/SEM, this needs adjustment.
                # Example: if len(meeting_list) == 1: final_section_data[type_key] = meeting_list[0]
                #          else: final_section_data[type_key] = meeting_list # or handle error/choice
                #
                # **Decision: For now, I'll keep the output as a list for each type to correctly capture multiple labs.**
                # **This means `CourseUtil.py` and `Main.py` might need changes if they expect a single dict for LEC/LAB/SEM.**
                #
                # **If you want to maintain the old single-entry structure and just pick the first one (losing data for multiple labs):**
                # final_section_data[type_key] = meeting_list[0]
                #
                # **To ensure all data is captured, let's keep it as a list, and you can adapt downstream:**
                # This part is tricky if the target JSON format MUST be a single object for LEC/LAB/SEM.
                # For example, your target format is "LEC": {details}, "LAB": {details}
                # If there are two labs, L1 and L2, how should they be represented?
                # Option 1: "LAB": [L1, L2] (This is what the code below does, requires downstream changes)
                # Option 2: "LAB1": L1, "LAB2": L2 (More complex to generate unique keys)
                # Option 3: Only take the first one: "LAB": L1 (Loses data)

                # Let's assume your final format allows a LIST of meetings for each type.
                # If not, this is where you'd have to decide how to represent multiple labs.
                # For now, if there's a single meeting, store it as an object for backward compatibility
                # if there are multiple, store as a list. This is a common pattern but might be inconsistent.
                # A more consistent approach is to ALWAYS store as a list.
                
                # --> CONSISTENT APPROACH: ALWAYS STORE AS A LIST <--
                final_section_data[type_key] = meeting_list
        
        # Only return if there's more than just the ID (i.e., some meeting data was found)
        return final_section_data if len(final_section_data) > 1 else None
    
    except Exception as e:
        print(f"Warning: Critical error extracting single section: {section_li.text[:100]} - Error: {str(e)}")
        return None

def scrape_all_courses(driver, max_pages=None):
    all_courses_by_term = {
        'Summer 2025': {}, 'Fall 2025': {}, 'Winter 2026': {}
    }
    current_page = 1
    
    driver.get("https://colleague-ss.uoguelph.ca/Student/Courses/Search")
    
    while True:
        if max_pages and current_page > max_pages:
            break
            
        print(f"\nProcessing PAGE {current_page}")
        
        try:
            click_collapsible_buttons(driver) # Crucial to expand sections before parsing
            
            course_list_ul = WebDriverWait(driver, 30).until(
                EC.presence_of_element_located((By.ID, "course-resultul"))
            )
            course_li_elements = course_list_ul.find_elements(By.TAG_NAME, "li")
            
            print(f"Found {len(course_li_elements)} course elements on page {current_page}")
            
            for idx in range(len(course_li_elements)):
                try:
                    # Re-find the course list and the specific element for this iteration
                    # This helps with stale element references if the DOM updates subtly
                    current_course_list_ul = driver.find_element(By.ID, "course-resultul")
                    current_course_li_elements = current_course_list_ul.find_elements(By.TAG_NAME, "li")

                    if idx >= len(current_course_li_elements): # Safety check
                        print(f"  Index {idx} out of bounds for current course elements ({len(current_course_li_elements)}). Skipping.")
                        break 
                    
                    course_element_to_process = current_course_li_elements[idx]
                    
                    # Scroll the specific course element into view before processing
                    # driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", course_element_to_process)
                    # time.sleep(0.1) # Brief pause for scrolling
                    
                    result = extract_course_details(course_element_to_process)
                    if result:
                        course_key, course_data_from_extraction = result
                        
                        sections_by_term_from_extraction = course_data_from_extraction["Sections"]
                        
                        for term_name, sections_list_for_term in sections_by_term_from_extraction.items():
                            if sections_list_for_term: 
                                term_specific_course_data = {
                                    "Title": course_data_from_extraction["Title"],
                                    "Description": course_data_from_extraction["Description"],
                                    "Offering": course_data_from_extraction["Offering"],
                                    "Restriction": course_data_from_extraction["Restriction"],
                                    "Department": course_data_from_extraction["Department"],
                                    "Requisites": course_data_from_extraction["Requisites"],
                                    "Locations": course_data_from_extraction["Locations"],
                                    "Offered": course_data_from_extraction["Offered"],
                                    "Sections": sections_list_for_term 
                                }
                                # Ensure the course key exists for this term before adding/updating
                                if course_key not in all_courses_by_term[term_name]:
                                    all_courses_by_term[term_name][course_key] = term_specific_course_data
                                else: # Merge if already exists (e.g. from previous runs)
                                    all_courses_by_term[term_name][course_key].update(term_specific_course_data)

                        total_parsed_sections = sum(len(s_list) for s_list in sections_by_term_from_extraction.values())
                        print(f"  Processed: {course_key} ({total_parsed_sections} sections found across its terms)")
                        
                except StaleElementReferenceException:
                    print(f"  Stale element reference for course {idx+1} on page {current_page}. Re-fetching page elements.")
                    # Potentially break and re-process page or just skip this course item.
                    # For now, we'll continue to the next item in the (potentially stale) list.
                    # A more robust solution might re-fetch the entire `course_li_elements` list here.
                    break # Break from inner loop, will refetch courses on next outer loop pass
                except Exception as e_course:
                    print(f"  Error processing course {idx+1} on page {current_page}: {str(e_course)}")
                    continue
            
            save_progress(all_courses_by_term, current_page)
            
            try:
                # Check if next button exists and is clickable
                WebDriverWait(driver, 5).until(
                     EC.presence_of_element_located((By.CSS_SELECTOR, "#course-results-next-page:not([disabled])"))
                )
                if click_next_page(driver, current_page):
                    current_page += 1
                    time.sleep(1) # Give page a moment to settle
                else:
                    print("click_next_page returned False or failed.")
                    break
            except (NoSuchElementException, TimeoutException):
                print("No 'Next Page' button found or it's disabled. End of results.")
                break
                
        except Exception as e_page:
            print(f"Critical error on page {current_page}: {str(e_page)}")
            save_progress(all_courses_by_term, current_page) # Save before exiting
            break # Exit outer while loop
    
    return all_courses_by_term


def save_progress(courses_data_by_term, page_num):
    for term_name, term_courses_dict in courses_data_by_term.items():
        if term_courses_dict: 
            term_filename_map = {
                'Summer 2025': 'S25', # Shortened for flask app
                'Fall 2025': 'F25', 
                'Winter 2026': 'W26'
            }
            
            # Use the flask app's naming convention for final output
            if term_name in term_filename_map:
                filename = f"{term_filename_map[term_name]}.json" 
            else: # Fallback if term name not in map
                filename = f"output_{term_name.replace(' ', '')}_page{page_num}.json"

            try:
                with open(filename, 'w', encoding='utf-8') as f:
                    json.dump(term_courses_dict, f, indent=4, ensure_ascii=False)
                print(f"  Progress saved: {len(term_courses_dict)} courses for {term_name} to {filename} (after page {page_num})")
            except Exception as e:
                print(f"  Error saving progress for {term_name} to {filename}: {e}")


def load_existing_progress():
    all_courses_by_term = {
        'Summer 2025': {}, 'Fall 2025': {}, 'Winter 2026': {}
    }
    
    term_filename_map = {
        'Summer 2025': 'S25.json', # Match final filenames
        'Fall 2025': 'F25.json', 
        'Winter 2026': 'W26.json'
    }
    
    for term_name, filename in term_filename_map.items():
        try:
            with open(filename, 'r', encoding='utf-8') as f:
                data = json.load(f)
                all_courses_by_term[term_name] = data
                print(f"Loaded existing data: {len(data)} courses from {filename}")
        except FileNotFoundError:
            print(f"No existing file found: {filename}. Starting fresh for this term.")
        except json.JSONDecodeError:
            print(f"Error decoding JSON from {filename}. File might be corrupted. Starting fresh for this term.")
    
    return all_courses_by_term

def main():
    options = Options()
    options.add_argument('--disable-blink-features=AutomationControlled')
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option('useAutomationExtension', False)
    # options.add_argument('--headless') # Enable for production
    options.add_argument('--no-sandbox')
    options.add_argument('--disable-dev-shm-usage')
    options.add_argument('--disable-extensions')
    options.add_argument('--disable-gpu')
    options.add_argument('--window-size=1920,1080')
    options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/90.0.4430.212 Safari/537.36")

    
    service = Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)
    
    # Apply stealth measures
    driver.execute_cdp_cmd('Network.setUserAgentOverride', {"userAgent": 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/94.0.4606.81 Safari/537.36'})
    driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")

    try:
        print("Starting FINAL PRODUCTION course scraping...")
        
        courses_data_by_term = load_existing_progress()
        
        updated_courses_from_scrape = scrape_all_courses(driver, max_pages=None) 
        
        # Merge newly scraped data with any loaded existing data
        # This ensures that if the scrape is partial, existing complete data isn't overwritten by partial.
        # However, for a full production run, `updated_courses_from_scrape` should be the most complete.
        # A more robust merge might be needed if resuming partial scrapes, but for a full run,
        # it's often simpler to just use the new scrape's result.
        # For safety, let's update:
        for term_name in courses_data_by_term:
            if term_name in updated_courses_from_scrape and updated_courses_from_scrape[term_name]:
                 # Careful merge: update existing entries, add new ones.
                for course_key, new_course_val in updated_courses_from_scrape[term_name].items():
                    courses_data_by_term[term_name][course_key] = new_course_val # Overwrite with latest scrape data
        
        # Save final files (using the names S25.json, F25.json, W26.json)
        final_filenames_map = {
            'Summer 2025': 'S25.json',
            'Fall 2025': 'F25.json', 
            'Winter 2026': 'W26.json'
        }
        for term_name, term_courses_dict in courses_data_by_term.items():
            if term_name in final_filenames_map:
                filename_to_save = final_filenames_map[term_name]
                if term_courses_dict: # Only save if there's data
                    with open(filename_to_save, 'w', encoding='utf-8') as f:
                        json.dump(term_courses_dict, f, indent=4, ensure_ascii=False)
                    print(f"FINAL SAVE: Saved {len(term_courses_dict)} courses for {term_name} to {filename_to_save}")
                else:
                    print(f"No courses data found for {term_name} to save to {filename_to_save}.")
            else:
                print(f"Warning: Term name '{term_name}' not in final_filenames_map. Not saved.")
        
    except Exception as e:
        print(f"Main error: {str(e)}")
        import traceback
        traceback.print_exc()
    finally:
        print("Quitting driver.")
        driver.quit()

if __name__ == "__main__":
    main()