# Guelph Schedule Generator

---
A small Python utility to scrape University of Guelph course section availability and generate schedules.

---
## Overview

- `Main.py` - main entrypoint for the application.--------

- `LiveStatusChecker.py` - uses Selenium to perform a live availability check of course sections on the U of Guelph site.- `Main.py` - main entrypoint for the application.

- `scraperv2.py`, `CourseUtil.py`, `sortingMethods.py` - supporting scripts used by the project.- `LiveStatusChecker.py` - uses Selenium to perform a live availability check of course sections on the U of Guelph site.

- `*.json` - sample semester/course data files.- `scraperv2.py`, `CourseUtil.py`, `sortingMethods.py` - supporting scripts used by the project.

- `*.json` - sample semester/course data files.
---
## Requirements

- Python 3.11+

- Google Chrome

- pip
---
## Python packages



Install the required packages


```

python -m pip install -r requirements.txt

```
Run the file

```
python main.py
```


---
