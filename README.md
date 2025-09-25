# Guelph Schedule Generatorguelph-schedule-generator

=========================

A small Python utility to scrape University of Guelph course section availability and generate schedules.

A small Python utility to scrape University of Guelph course section availability and generate schedules.

## Files of interest

Overview

- `Main.py` - main entrypoint for the application.--------

- `LiveStatusChecker.py` - uses Selenium to perform a live availability check of course sections on the U of Guelph site.- `Main.py` - main entrypoint for the application.

- `scraperv2.py`, `CourseUtil.py`, `sortingMethods.py` - supporting scripts used by the project.- `LiveStatusChecker.py` - uses Selenium to perform a live availability check of course sections on the U of Guelph site.

- `*.json` - sample semester/course data files.- `scraperv2.py`, `CourseUtil.py`, `sortingMethods.py` - supporting scripts used by the project.

- `*.json` - sample semester/course data files.

## Requirements

Requirements

- Python 3.11+ (tested with Python 3.13)------------

- Google Chrome installed- Python 3.11+ (project used with Python 3.13 in development)

- pip

## Python packages- Google Chrome installed on the machine



Install the required packages (recommended inside a virtual environment):Python packages

---------------

```powershellInstall required packages (preferably in a virtual environment):

python -m pip install -r requirements.txt

``````powershell

python -m pip install -r requirements.txt

If you don't have a `requirements.txt`, at minimum install:```



```powershellIf you don't have a `requirements.txt`, install the main packages used here:

python -m pip install selenium beautifulsoup4 webdriver-manager

``````powershell

python -m pip install selenium beautifulsoup4 webdriver-manager

## Usage```



Run the live status checker directly for a quick test:Usage

-----

```powershellRun the live status checker directly for testing:

# Headless by default

python LiveStatusChecker.py "CIS*2750" "Fall 2025"```powershell

# Headless by default

# Visible browser for debuggingpython LiveStatusChecker.py "CIS*2750" "Fall 2025"

python LiveStatusChecker.py "CIS*2750" "Fall 2025" --no-headless

```# Visible browser for debugging

python LiveStatusChecker.py "CIS*2750" "Fall 2025" --no-headless

When calling from `Main.py` or other modules, pass the course code and semester string to `get_live_section_status(course_code, semester, headless=True)`.```



## Notes on term filteringNotes about the term filter behavior

-----------------------------------

`LiveStatusChecker.py` attempts to open the on-page Filters panel and click the Terms filter option matching the semester string you provide (for example "Fall 2025"). If it can't find or click the filter, the script will still parse the page but results may include sections from more than one term.`LiveStatusChecker.py` attempts to open the on-page Filters panel and click the Terms filter option matching the semester string you provide (for example "Fall 2025"). This helps ensure the scraper only sees sections for the selected term. The implementation tries several strategies:



## Troubleshooting- Click a known "Filter Results" toggle (if present) to expose filter options.

- Search for a label or element containing the semester text and click it (or its associated input).

- Ensure Chrome is installed and up-to-date.

- If Selenium cannot start, check that `webdriver-manager` can download drivers (network restrictions may block it).Edge cases

----------

## License- If the site structure changes, the filter-clicking logic may fail and the script will still try to parse the page; you may get results for multiple terms.

- If you see incorrect term results, try running with `--no-headless` to observe the site and adjust selectors.

MIT

Troubleshooting
---------------
- Ensure Chrome is installed and up-to-date.
- For verbose webdriver-manager logs, remove the experimental option added in `LiveStatusChecker.py`.
- If Selenium cannot start, check that `webdriver-manager` can download drivers (network restrictions may block it).

License
-------
MIT
