# LiveStatusChecker.py

from bs4 import BeautifulSoup
import re
import sys
import pprint
import time
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import TimeoutException
from webdriver_manager.chrome import ChromeDriverManager

driver = None

def setup_driver(headless=True):
    """
    Initializes a headless Chrome WebDriver instance if one is not already running.
    """
    global driver
    if driver is None:
        print(f"[LiveStatusChecker] Initializing Selenium WebDriver (headless={headless})...")
        options = Options()
        if headless:
            options.add_argument('--head')
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument('--disable-gpu')
        options.add_argument('--window-size=1920,1080')
        options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36")
        
        try:
            # Hide verbose logs from webdriver-manager in the console
            options.add_experimental_option('excludeSwitches', ['enable-logging'])
            service = Service(ChromeDriverManager().install())
            driver = webdriver.Chrome(service=service, options=options)
        except Exception as e:
            print(f"[LiveStatusChecker] FATAL: Could not initialize WebDriver. Live checking will be disabled. Error: {e}")
            driver = None
    return driver

def shutdown_driver():
    """
    Properly closes the WebDriver to free up resources.
    This is registered with `atexit` in Main.py to run on app shutdown.
    """
    global driver
    if driver:
        driver.quit()
        driver = None

def get_live_section_status(course_code, headless=True):
    """
    Scrapes the UoGuelph course search page for live section availability.
    It uses Selenium to handle the JavaScript-driven page and mimics user interaction.
    """
    local_driver = setup_driver(headless=headless)
    if not local_driver:
        return None, "Selenium WebDriver is not available. Cannot perform live check."

    if not course_code:
        return None, "Course code cannot be empty."

    search_url = f"https://colleague-ss.uoguelph.ca/Student/Courses/Search?keyword={course_code}"
    section_statuses = {}
    
    try:
        local_driver.get(search_url)

        # Wait for the main course results container to appear, confirming the page has loaded.
        WebDriverWait(local_driver, 15).until(
            EC.presence_of_element_located((By.ID, "course-resultul"))
        )
        
        # Handle cases where the course code is invalid or not offered.
        if "No results found for your search" in local_driver.page_source:
             return None, f"The course '{course_code}' was not found. It may not be offered or the code is incorrect."

        # First, check if the section content is already visible to avoid unnecessary clicks.
        try:
            content_selector = "li.search-nestedaccordionitem"
            WebDriverWait(local_driver, 2).until(
                EC.visibility_of_element_located((By.CSS_SELECTOR, content_selector))
            )
        except TimeoutException:
            # If the content isn't visible, we need to click the "View Available Sections" button.
            button_selector = "#course-resultul .esg-collapsible-group__toggle"
            
            view_sections_button = WebDriverWait(local_driver, 10).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, button_selector))
            )
            # Scroll to the button to ensure it's in the viewport and clickable.
            local_driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", view_sections_button)
            time.sleep(0.3)
            local_driver.execute_script("arguments[0].click();", view_sections_button)

            # After the click, we must wait for the section content to load and become visible.
            WebDriverWait(local_driver, 20).until(
                EC.visibility_of_element_located((By.CSS_SELECTOR, content_selector))
            )

    except TimeoutException:
        return None, f"A timeout occurred while trying to load section details for '{course_code}'. The website may be slow or its structure has changed."
    except Exception as e:
        return None, f"An unexpected error occurred during page navigation: {e}"

    # Now that the page is fully rendered, parse the HTML.
    soup = BeautifulSoup(local_driver.page_source, 'html.parser')
    
    # Iterate through each term (e.g., "Fall 2025", "Winter 2026") on the page.
    term_headers = soup.select("h4")
    for term_header in term_headers:
        term_name = term_header.get_text(strip=True)
        # Skip any headers that aren't valid term names.
        if term_name not in ["Fall 2025", "Winter 2026", "Summer 2025"]:
            continue
        
        # Find the list of sections associated with the current term.
        section_list_ul = term_header.find_next_sibling('ul')
        if not section_list_ul:
            continue
            
        section_lis = section_list_ul.select('li.search-nestedaccordionitem')
        if not section_lis:
            continue
        
        # Extract the status from each section within the term.
        for section_li in section_lis:
            section_id_tag = section_li.find('a', class_='search-sectiondetailslink')
            if not section_id_tag or not section_id_tag.text.strip():
                continue
            section_id = section_id_tag.text.strip()
            
            table = section_li.find('table', class_='search-sectiontable')
            if not table: continue
            
            headers = [th.get_text(strip=True) for th in table.select('thead > tr > th')]
            data_cells = table.select('tbody > tr:first-child > td')
            if not headers or not data_cells: continue
            
            status_idx, status_type = -1, None
            if 'Seats' in headers:
                status_idx, status_type = headers.index('Seats'), 'Seats'
            elif 'Waitlisted' in headers:
                status_idx, status_type = headers.index('Waitlisted'), 'Waitlisted'

            if status_idx != -1 and status_idx < len(data_cells):
                status_cell = data_cells[status_idx]
                
                # The status cell contains multiple spans; find the one that is currently visible.
                spans = status_cell.find_all('span', class_='search-seatsavailabletext')
                status_value = "N/A"
                for span in spans:
                    # A visible span does not have 'display: none' in its style attribute.
                    if 'style' not in span.attrs or 'display: none' not in span['style']:
                        status_value = span.get_text(strip=True)
                        break
                
                # Categorize the section status based on the parsed value.
                if status_type == 'Seats':
                    parts = [p.strip() for p in status_value.split('/')]
                    try:
                        available_seats = int(parts[0])
                        status = "available" if available_seats > 0 else "full"
                        section_statuses[section_id] = {"status": status, "details": status_value, "term": term_name}
                    except (ValueError, IndexError):
                        section_statuses[section_id] = {"status": "unknown", "details": status_value, "term": term_name}
                elif status_type == 'Waitlisted':
                    section_statuses[section_id] = {"status": "waitlisted", "details": status_value, "term": term_name}
    
    if not section_statuses:
        return None, f"Could not parse status for any section of {course_code}. The page structure may have changed."

    return section_statuses, None

# This block allows the script to be run directly from the command line for testing purposes.
if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: python LiveStatusChecker.py <COURSE_CODE> [--no-headless]")
        print("Example (headless): python LiveStatusChecker.py \"CIS*2750\"")
        print("Example (visible browser):  python LiveStatusChecker.py \"CIS*2750\" --no-headless")
        sys.exit(1)

    course_to_check = sys.argv[1]
    # Check for the optional flag to run with a visible browser for debugging.
    run_headless = "--no-headless" not in sys.argv
    
    print(f"Checking live status for: {course_to_check}...")
    try:
        statuses, error_msg = get_live_section_status(course_to_check, headless=run_headless)

        if error_msg:
            print(f"\n--- ERROR ---")
            print(error_msg)
        else:
            print(f"\n--- SUCCESS ---")
            print(f"Found status for {len(statuses)} sections:")
            pprint.pprint(statuses)
    finally:
        # Ensure the browser instance is closed after the script finishes.
        shutdown_driver()