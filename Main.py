from flask import Flask, render_template, request, jsonify
import json
import time
import re
from CourseUtil import ScheduleItem, CourseSection, CoursePlanner

from LiveStatusChecker import get_live_section_status, shutdown_driver
import atexit
import traceback

from sortingMethods import (
    filterByEarliestAtSchool, filterByLatestAtSchool,
    filterByTotalMinTimeBetweenClasses, filterByAvgStartTime,
    filterBySpecificDayOff, filterByAmountOfDaysOff
)
from functools import lru_cache
import gc

app = Flask(__name__)
app.config['JSON_SORT_KEYS'] = False
app.config['JSONIFY_PRETTYPRINT_REGULAR'] = False

# This ensures that when the Flask app is closed (e.g., with Ctrl+C),
# the WebDriver process is properly terminated to prevent memory leaks.
atexit.register(shutdown_driver)

course_data_cache = {}

error_messages = {
    "No_Course_Entered": "Please select at least one course.",
    "Course_Not_Available": "One or more selected courses are not available for the chosen semester.",
    "Invalid_Times": "The 'Earliest Start Time' cannot be after the 'Latest End Time'.",
    "No_Combinations": "No schedules match your selected courses and constraints.",
    "No_Combinations_For_Course": "A selected course has no sections that meet all specified time criteria. Please adjust constraints for this course or global times.",
    "No_Combinations_Query_Too_Strict": "No schedules found. Your time or course-specific constraints might be too strict.",
    "Invalid_Semester": "The selected semester data is not available."
}

MAX_SCHEDULES_TO_DISPLAY = 500

@lru_cache(maxsize=3)
def load_course_data(json_file):
    try:
        with open(json_file, 'r', encoding='utf-8') as file:
            return json.load(file)
    except FileNotFoundError:
        print(f"Error: Data file {json_file} not found.")
        return None
    except json.JSONDecodeError:
        print(f"Error: Could not decode JSON from {json_file}.")
        return None

def get_cached_course_data(semester):
    json_file_map = {
        "Summer 2025": 'S25.json',
        "Fall 2025": 'F25.json',
        "Winter 2026": 'W26.json'
    }
    if semester not in json_file_map:
        return None
    json_file = json_file_map[semester]
    if json_file not in course_data_cache:
        data = load_course_data(json_file)
        if data:
            course_data_cache[json_file] = data
        else:
            return None
    return course_data_cache.get(json_file)

def correct_course_codes(course_codes):
    corrected_codes = []
    for code in course_codes:
        code = code.strip().upper()
        if not code: continue
        if '*' not in code:
            corrected_code = re.sub(r'([A-Z]+)(\d+)', r'\1*\2', code)
            corrected_codes.append(corrected_code)
        else:
            corrected_codes.append(code)
    return corrected_codes

def convert_time_to_minutes(time_str):
    if not time_str: return None
    try:
        hours, minutes = map(int, time_str.split(':'))
        return hours * 60 + minutes
    except (ValueError, AttributeError):
        return None

def calculate_cm_schedule_score(combination):
    dateToIndexMap = {"M": 0, "T": 1, "W": 2, "Th": 3, "F": 4, "Sa": 5}
    week = [[] for _ in range(6)]

    for course_section in combination:
        for schedule_item in course_section.get_schedule_items():
            if schedule_item is not None:
                for day in schedule_item.days:
                    if day in dateToIndexMap:
                        week[dateToIndexMap[day]].append((schedule_item.start, schedule_item.finish))

    for w_idx in range(len(week)):
        week[w_idx] = sorted(week[w_idx], key=lambda x: x[0])

    score = 0
    gap_penalties = 0
    back_to_back_penalties = 0
    long_day_penalties = 0
    days_on_campus = 0

    for day_schedule in week:
        if not day_schedule: continue
        days_on_campus += 1
        day_start_time, day_end_time = day_schedule[0][0], day_schedule[-1][1]
        day_duration = day_end_time - day_start_time

        if day_duration > 8 * 60:
            long_day_penalties += (day_duration - 8 * 60) * 0.1

        for i in range(len(day_schedule) - 1):
            current_class_end = day_schedule[i][1]
            next_class_start = day_schedule[i+1][0]
            gap = next_class_start - current_class_end

            if gap == 0:
                back_to_back_penalties += 20
            elif gap < 0:
                gap_penalties += 100
            elif gap < 15:
                gap_penalties += 30
            elif gap < 30:
                gap_penalties += 10
            elif 30 <= gap <= 120:
                score += 20 + (10 * (1 - abs(gap - 60) / 60))
            elif gap <= 180:
                gap_penalties += 5
            else:
                gap_penalties += gap * 0.1

    if days_on_campus <= 3: score += 50
    elif days_on_campus == 4: score += 25

    final_score = score - gap_penalties - back_to_back_penalties - long_day_penalties
    return final_score, {
        'base_score': score,
        'gap_penalties': gap_penalties,
        'back_to_back_penalties': back_to_back_penalties,
        'long_day_penalties': long_day_penalties,
        'days_on_campus': days_on_campus
    }

def calculate_gap_score(total_gap_minutes):
    if total_gap_minutes < 60 : return 100 - total_gap_minutes
    elif total_gap_minutes < 240: return 80 - (total_gap_minutes - 60) * 0.1
    else: return max(0, 40 - (total_gap_minutes - 240) * 0.2)

def section_meets_time_constraints(section, course_code, course_time_constraints):
    if course_code not in course_time_constraints: return True

    constraints = course_time_constraints[course_code]
    earliest_minutes = convert_time_to_minutes(constraints.get('earliest'))
    latest_minutes = convert_time_to_minutes(constraints.get('latest'))

    if earliest_minutes is None and latest_minutes is None: return True
    return section.fits_time_constraints(earliest_minutes or 0, latest_minutes or 0)

def _handle_error(error_code_key, status_code=400, **kwargs):
    message = error_messages.get(error_code_key, "An unknown error occurred.")
    if "problematic_course" in kwargs:
        message = f"One or more courses cannot be scheduled: {kwargs['problematic_course']}. Please check constraints or course availability."
        if error_code_key == "No_Combinations_For_Course":
             message = f"For course(s) {kwargs['problematic_course']}: No sections meet all specified time criteria. Please adjust constraints for these courses or global times."
    elif "invalid_courses" in kwargs:
        message = f"Courses not found or not available in {kwargs.get('semester', 'selected semester')}: {', '.join(kwargs['invalid_courses'])}. Please check course codes and semester selection."

    print(f"Error handled: {error_code_key} - {message} (Status: {status_code})")
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify({'error': error_code_key, 'message': message}), status_code
    return render_template('error.html', error_code=error_code_key, message=message, **kwargs)

@app.route('/', methods=['GET', 'POST'])
def schedule():
    if request.method == 'POST':
        request_start_time = time.time()

        course_codes_str = request.form.getlist('courses[]')[0]
        raw_course_codes = [code.strip() for code in course_codes_str.split(',') if code.strip()]
        course_codes = correct_course_codes(raw_course_codes)

        if not course_codes:
            return _handle_error("No_Course_Entered")

        earliest_str = request.form.get('earliest')
        latest_str = request.form.get('latest')

        course_time_constraints_str = request.form.get('course_time_constraints', '{}')
        course_section_filter_str = request.form.get('course_section_filter', '{}')
        try:
            course_section_filter = json.loads(course_section_filter_str) if course_section_filter_str else {}
        except json.JSONDecodeError:
            print("Warning: Could not parse course_section_filter JSON. Defaulting to empty.")
            course_section_filter = {}
        try:
            course_time_constraints = json.loads(course_time_constraints_str) if course_time_constraints_str else {}
        except json.JSONDecodeError:
            print("Warning: Could not parse course_time_constraints JSON. Defaulting to empty.")
            course_time_constraints = {}

        earliestAtSchool = convert_time_to_minutes(earliest_str) or 0
        latestAtSchool = convert_time_to_minutes(latest_str) or 0

        if earliestAtSchool > 0 and latestAtSchool > 0 and earliestAtSchool >= latestAtSchool :
             return _handle_error("Invalid_Times")

        semester = request.form.get('semester')
        data = get_cached_course_data(semester)
        if data is None:
            return _handle_error("Invalid_Semester", problematic_semester=semester)

        print(f"\n--- New Request ---")
        print(f"Semester: {semester}, Courses: {course_codes}")
        print(f"Global Times: Earliest={earliestAtSchool}, Latest={latestAtSchool}")
        print(f"Course Specific Times: {course_time_constraints}")

        allCourseData_for_planner = []
        problematic_course_details = []

        for course_code in course_codes:
            if course_code not in data:
                problematic_course_details.append(f"{course_code} (Not found in {semester} data)")
                continue

            course_info_json = data[course_code]
            sections_json_list = course_info_json.get("Sections", [])
            current_course_valid_sections = []

            if not sections_json_list:
                problematic_course_details.append(f"{course_code} (No sections listed in data)")
                continue

            for sec_json in sections_json_list:
                if course_code in course_section_filter and sec_json['id'] not in course_section_filter[course_code]:
                    continue
                def process_meeting_data(meeting_data_json, item_type_str):
                    if not meeting_data_json: return None
                    items = []
                    if isinstance(meeting_data_json, list):
                        for item_json in meeting_data_json:
                            if "start" in item_json and "end" in item_json and "date" in item_json:
                                items.append(ScheduleItem(item_type_str, item_json["start"], item_json["end"], item_json["date"]))
                    elif isinstance(meeting_data_json, dict):
                        if "start" in meeting_data_json and "end" in meeting_data_json and "date" in meeting_data_json:
                            items.append(ScheduleItem(item_type_str, meeting_data_json["start"], meeting_data_json["end"], meeting_data_json["date"]))
                    if not items: return None
                    return items[0] if len(items) == 1 else items

                lectureComponent = process_meeting_data(sec_json.get("LEC"), "Lecture")
                seminarComponent = process_meeting_data(sec_json.get("SEM"), "Seminar")
                labComponent = process_meeting_data(sec_json.get("LAB"), "Lab")

                newSection = CourseSection(sec_json["id"], lectureComponent, seminarComponent, labComponent)

                if not section_meets_time_constraints(newSection, course_code, course_time_constraints):
                    continue
                if not newSection.fits_time_constraints(earliestAtSchool, latestAtSchool):
                    continue
                current_course_valid_sections.append(newSection)

            if not current_course_valid_sections:
                problematic_course_details.append(f"{course_code} (No sections meet time criteria)")
            else:
                allCourseData_for_planner.append(current_course_valid_sections)

        if problematic_course_details:
            return _handle_error("No_Combinations_For_Course", problematic_course=", ".join(problematic_course_details))

        if not allCourseData_for_planner and course_codes:
            print("WARNING: Reached 'if not allCourseData_for_planner and course_codes' unexpectedly. Problematic courses should have been caught.")
            return _handle_error("No_Combinations_Query_Too_Strict")

        if not allCourseData_for_planner and not course_codes:
             return _handle_error("No_Course_Entered")

        planner = CoursePlanner(allCourseData_for_planner)
        est_combinations = 1
        for sections_list in allCourseData_for_planner: est_combinations *= len(sections_list)
        print(f"Estimated combinations before planner: {est_combinations:,}")
        if est_combinations == 0:
             return _handle_error("No_Combinations_Query_Too_Strict")

        validCombinations = planner.nonOverlapped()
        print(f"Planner nonOverlapped returned: {len(validCombinations)} combinations")

        days_off_request = request.form.getlist('days_off[]')
        if days_off_request:
            validCombinations = filterBySpecificDayOff(validCombinations, days_off_request)
            print(f"After 'Specific Day Off' ({days_off_request}) filter: {len(validCombinations)}")
            if not validCombinations: return _handle_error("No_Combinations_Query_Too_Strict")

        num_days_off_request_str = request.form.get('num_days_off')
        if num_days_off_request_str:
            try:
                num_days_off = int(num_days_off_request_str)
                if num_days_off >= 0:
                    validCombinations = filterByAmountOfDaysOff(validCombinations, num_days_off)
                    print(f"After 'Amount of Days Off' ({num_days_off}) filter: {len(validCombinations)}")
                    if not validCombinations: return _handle_error("No_Combinations_Query_Too_Strict")
            except ValueError:
                print(f"Warning: Invalid value for num_days_off: {num_days_off_request_str}")

        if earliestAtSchool > 0:
            validCombinations = filterByEarliestAtSchool(validCombinations, earliestAtSchool)
            print(f"After global earliest time filter ({earliestAtSchool}): {len(validCombinations)}")

        if latestAtSchool > 0:
            validCombinations = filterByLatestAtSchool(validCombinations, latestAtSchool)
            print(f"After global latest time filter ({latestAtSchool}): {len(validCombinations)}")

        if not validCombinations:
             return _handle_error("No_Combinations_Query_Too_Strict")

        _, sorted_gap_indices, gap_times_list = filterByTotalMinTimeBetweenClasses(validCombinations)
        print(f"Gap calculation done. {len(validCombinations)} combinations remain for sorting.")

        if not validCombinations :
             return _handle_error("No_Combinations_Query_Too_Strict")

        sort_preference = request.form.get('sort_preference', 'smart_gaps')
        print(f"Sorting preference: {sort_preference}")

        scored_schedules = []

        for i in range(len(validCombinations)):
            combo = validCombinations[i]
            gap_time = gap_times_list[i] if i < len(gap_times_list) else 0

            if sort_preference == 'smart_gaps':
                comp_score, metrics = calculate_cm_schedule_score(combo)
                scored_schedules.append((comp_score, i, gap_time, metrics))
            elif sort_preference == 'minimal_gaps':
                scored_schedules.append((-gap_time, i, gap_time))
            elif sort_preference == 'best_gaps':
                score = calculate_gap_score(gap_time)
                scored_schedules.append((score, i, gap_time))
            elif sort_preference == 'fewer_days':
                days_used_count = 0
                if combo:
                    days_present = set()
                    for course_sec in combo:
                        for sch_item in course_sec.get_schedule_items():
                            days_present.update(sch_item.days)
                    days_used_count = len(days_present)
                smart_s, _ = calculate_cm_schedule_score(combo)
                scored_schedules.append(((-days_used_count * 10000) + smart_s, i, gap_time, {'days_on_campus': days_used_count}))
            elif sort_preference == 'early_start':
                min_start_time = float('inf')
                if combo:
                    for course_sec in combo:
                        for sch_item in course_sec.get_schedule_items():
                            min_start_time = min(min_start_time, sch_item.start)
                scored_schedules.append((min_start_time if min_start_time != float('inf') else 9999, i, gap_time))
            elif sort_preference == 'late_start':
                overall_latest_first_class_start = 0
                if combo:
                    daily_first_starts = []
                    temp_week = [[] for _ in range(6)]; dateToIndexMap = {"M":0,"T":1,"W":2,"Th":3,"F":4,"Sa":5}
                    for cs in combo:
                        for si in cs.get_schedule_items():
                            for day_char in si.days:
                                if day_char in dateToIndexMap: temp_week[dateToIndexMap[day_char]].append(si.start)
                    for day_starts in temp_week:
                        if day_starts: daily_first_starts.append(min(day_starts))
                    if daily_first_starts: overall_latest_first_class_start = min(daily_first_starts)
                scored_schedules.append((overall_latest_first_class_start, i, gap_time))
            elif sort_preference == 'compact':
                total_daily_span = 0; days_active = 0
                if combo:
                    temp_week_spans = [[] for _ in range(6)]; dateToIndexMap = {"M":0,"T":1,"W":2,"Th":3,"F":4,"Sa":5}
                    for cs in combo:
                        for si in cs.get_schedule_items():
                            for day_char in si.days:
                                if day_char in dateToIndexMap: temp_week_spans[dateToIndexMap[day_char]].append((si.start, si.finish))
                    for day_meetings in temp_week_spans:
                        if day_meetings:
                            days_active+=1; min_s = min(m[0] for m in day_meetings); max_e = max(m[1] for m in day_meetings)
                            total_daily_span += (max_e - min_s)
                score = total_daily_span + gap_time * 0.1
                scored_schedules.append((score, i, gap_time))
            else:
                comp_score, metrics = calculate_cm_schedule_score(combo)
                scored_schedules.append((comp_score, i, gap_time, metrics))

        if sort_preference in ['early_start', 'compact', 'minimal_gaps']:
            scored_schedules.sort(key=lambda x: x[0])
        else:
            scored_schedules.sort(key=lambda x: x[0], reverse=True)

        if not scored_schedules:
            return _handle_error("No_Combinations_Query_Too_Strict")

        total_found_before_cap = len(scored_schedules)
        combinations_for_response = []

        # Limit the number of schedules to process for the response
        for i, scored_item in enumerate(scored_schedules):
            if i >= MAX_SCHEDULES_TO_DISPLAY:
                print(f"Limiting display to {MAX_SCHEDULES_TO_DISPLAY} schedules out of {total_found_before_cap} found.")
                break
            
            original_combo_idx = scored_item[1]
            original_combo = validCombinations[original_combo_idx]
            time_metric = scored_item[2]

            rank = len(combinations_for_response) + 1
            response_item = {
                "rank": rank, "total_gap_time": time_metric,
                "courses": original_combo
            }
            if sort_preference == 'smart_gaps' and len(scored_item) > 3:
                response_item['smart_score_details'] = scored_item[3]
                response_item['smart_score'] = scored_item[0]
            elif sort_preference == 'fewer_days' and len(scored_item) > 3:
                 response_item['days_on_campus'] = scored_item[3].get('days_on_campus')
            combinations_for_response.append(response_item)

        del validCombinations, planner, allCourseData_for_planner, scored_schedules, gap_times_list, sorted_gap_indices
        gc.collect()

        request_end_time = time.time()
        elapsed_time = request_end_time - request_start_time
        print(f"Total request processing time: {elapsed_time:.2f} seconds.")

        if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or \
           request.headers.get('Accept') == 'application/json':
            response_data_list_for_json = []
            for combo_obj_for_resp in combinations_for_response: # This is now the limited list
                combo_data_for_json = {
                    'rank': combo_obj_for_resp['rank'],
                    'total_gap_time': combo_obj_for_resp['total_gap_time'],
                    'courses': []
                }
                if 'smart_score' in combo_obj_for_resp:
                    combo_data_for_json['smart_score'] = round(combo_obj_for_resp['smart_score'],1)
                if 'smart_score_details' in combo_obj_for_resp:
                    combo_data_for_json['smart_score_details'] = combo_obj_for_resp['smart_score_details']
                if 'days_on_campus' in combo_obj_for_resp:
                    combo_data_for_json['days_on_campus'] = combo_obj_for_resp['days_on_campus']

                for course_section_obj in combo_obj_for_resp['courses']:
                    course_item_data_for_json = {'section_id': course_section_obj.courseCode}
                    def add_serialized_meetings_to_dict(target_dict, meeting_attr_val, meeting_key_str, meeting_type_str_val):
                        if meeting_attr_val is None: return
                        if isinstance(meeting_attr_val, list):
                            serialized_list = []
                            for sch_item in meeting_attr_val:
                                serialized_list.append({
                                    'type': meeting_type_str_val, 'start': sch_item.start,
                                    'finish': sch_item.finish, 'days': sch_item.days,
                                    'location': getattr(sch_item, 'location', 'N/A')
                                })
                            if serialized_list: target_dict[meeting_key_str] = serialized_list
                        else:
                            target_dict[meeting_key_str] = {
                                'type': meeting_type_str_val, 'start': meeting_attr_val.start,
                                'finish': meeting_attr_val.finish, 'days': meeting_attr_val.days,
                                'location': getattr(meeting_attr_val, 'location', 'N/A')
                            }

                    add_serialized_meetings_to_dict(course_item_data_for_json, course_section_obj.lecture, "LEC", "Lecture")
                    add_serialized_meetings_to_dict(course_item_data_for_json, course_section_obj.seminar, "SEM", "Seminar")
                    add_serialized_meetings_to_dict(course_item_data_for_json, course_section_obj.lab, "LAB", "Lab")

                    combo_data_for_json['courses'].append(course_item_data_for_json)
                response_data_list_for_json.append(combo_data_for_json)

            return jsonify({
                'combinations': response_data_list_for_json,
                'stats': {
                    'total_found_before_cap': total_found_before_cap, # Total found
                    'total_displayed': len(combinations_for_response), # Actual number sent
                    'processing_time': round(elapsed_time, 2),
                    'earliest_time_applied': earliestAtSchool if earliestAtSchool > 0 else "Any",
                    'latest_time_applied': latestAtSchool if latestAtSchool > 0 else "Any",
                    'sort_preference': sort_preference
                }
            })

        return render_template('result.html',
                               combinations=combinations_for_response, # Limited list
                               earliestAtSchool=earliestAtSchool,
                               latestAtSchool=latestAtSchool,
                               elapsed_time=round(elapsed_time,2),
                               total_possible=total_found_before_cap, # Total found
                               num_displayed=len(combinations_for_response), # Actual number sent
                               sort_preference=sort_preference)

    gc.collect()
    return render_template('index.html')

@app.route('/api/search-courses')
def api_search_courses():
    query = request.args.get('q', '').strip()
    semester = request.args.get('semester', 'Summer 2025')

    if len(query) < 2: return jsonify([])

    course_data = get_cached_course_data(semester)
    if not course_data: return jsonify([])

    query_upper = query.upper()
    query_lower = query.lower()
    
    # Normalize query for matching, e.g., CIS1500 -> CIS*1500
    normalized_query = query_upper
    if '*' not in normalized_query and re.match(r'^[A-Z]+\d+', normalized_query):
        normalized_query = re.sub(r'([A-Z]+)(\d+)', r'\1*\2', normalized_query)
    
    # Create a version of the query with no spaces or stars for Levenshtein distance calculation
    query_for_levenshtein = re.sub(r'[\s\*]', '', query_upper)

    final_results = {}
    for course_code, course_info in course_data.items():
        title = course_info.get('Title', "Unknown Course Title")
        
        # Normalize course_code for Levenshtein matching
        course_code_for_levenshtein = re.sub(r'[\s\*]', '', course_code)
        
        # Calculate match score
        match_score = 0
        
        # 1. Levenshtein Distance (for typos in course code)
        distance = levenshtein_distance(query_for_levenshtein, course_code_for_levenshtein)
        
        if distance <= 2: # Only consider courses with a small number of typos
            # Higher score for lower distance
            match_score = max(match_score, 85 - (distance * 15))

        # 2. Exact/Prefix Match (override Levenshtein score if better)
        if course_code == normalized_query:
            match_score = 100
        elif course_code.startswith(normalized_query):
            match_score = max(match_score, 95)
        elif course_code.startswith(query_upper):
             match_score = max(match_score, 90)

        # 3. Title Match
        if query_lower in title.lower():
            if title.lower().startswith(query_lower):
                match_score = max(match_score, 65)
            else:
                match_score = max(match_score, 50)

        # Add course to results if it has a reasonable score
        if match_score > 40:
            # If course already in results, only update if the new score is higher
            if course_code not in final_results or match_score > final_results[course_code]['match_score']:
                credits_str = ""
                if title and "(" in title and "Credit" in title:
                    credits_match_re = re.search(r'\(([\d\.]+\s*Credits?)\)', title, re.IGNORECASE)
                    if credits_match_re: credits_str = credits_match_re.group(1)

                final_results[course_code] = {
                    'code': course_code,
                    'title': title,
                    'description': course_info.get('Description', "")[:120] + "...",
                    'credits': credits_str,
                    'sections_count': len(course_info.get('Sections', [])),
                    'match_score': match_score
                }

    # Sort results by score (descending)
    sorted_results = sorted(final_results.values(), key=lambda x: x['match_score'], reverse=True)
    
    # Clean up before sending
    for r_item in sorted_results:
        del r_item['match_score']

    return jsonify(sorted_results[:15])

@app.route('/api/course-sections')
def api_course_sections():
    course_code = request.args.get('course_code', '').strip().upper()
    semester = request.args.get('semester', 'Summer 2025')

    if not course_code:
        return jsonify({'error': 'Course code is required.'}), 400

    course_data = get_cached_course_data(semester)
    if not course_data or course_code not in course_data:
        return jsonify({'error': 'Course not found in the selected semester.'}), 404

    sections = course_data[course_code].get('Sections', [])
    return jsonify(sections)

@app.route('/api/live-status')
def api_live_status():
    course_code = request.args.get('course_code')
    if not course_code:
        return jsonify({'error': 'course_code is required'}), 400
    
    try:
        status_data, error = get_live_section_status(course_code)
        
        if error:
            return jsonify({'error': 'Failed to fetch live status', 'details': error}), 500
        
        return jsonify(status_data)

    except Exception as e:
        # This catches any unhandled exception (a CRASH) from the scraper
        print(f"!!! CRITICAL ERROR in /api/live-status for course '{course_code}': {e}")
        traceback.print_exc()
        return jsonify({
            'error': 'A critical server error occurred during the live check.',
            'details': 'The server was unable to complete the request. Please check the server logs for more information.'
        }), 500

@app.route('/api/semester-info')
def api_semester_info():
    semester = request.args.get('semester', 'Summer 2025')
    course_data = get_cached_course_data(semester)
    if not course_data: return jsonify({'error': 'Semester data not found'}), 404

    total_courses = len(course_data)
    total_sections = sum(len(c_info.get('Sections', [])) for c_info in course_data.values())
    departments = set()
    for course_code_key in course_data:
        if '*' in course_code_key: departments.add(course_code_key.split('*')[0])
        else:
            match = re.match(r'([A-Z]+)', course_code_key)
            if match: departments.add(match.group(1))

    return jsonify({
        'semester': semester, 'total_courses': total_courses,
        'total_sections': total_sections, 'department_count': len(departments)
    })

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)