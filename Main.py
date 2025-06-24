from flask import Flask, render_template, request, jsonify
import json
import time
import re
from CourseUtil import ScheduleItem, CourseSection, CoursePlanner
from sortingMethods import filterByEarliestAtSchool, filterByLatestAtSchool, filterByTotalMinTimeBetweenClasses
from functools import lru_cache
import gc

app = Flask(__name__)
app.config['JSON_SORT_KEYS'] = False
app.config['JSONIFY_PRETTYPRINT_REGULAR'] = False

course_data_cache = {}

error_messages = {
    "No_Course_Entered": "Please select at least one course.",
    "Course_Not_Available": "One or more selected courses are not available for the chosen semester.",
    "Invalid_Times": "The 'Earliest Start Time' cannot be after the 'Latest End Time'.",
    "No_Combinations": "No schedules match your selected courses and constraints.",
    "No_Combinations_For_Course": "A selected course has no sections that meet all time criteria. Cannot generate schedules.",
    "No_Combinations_Query_Too_Strict": "No schedules found. Your time or course-specific constraints might be too strict.",
    "Invalid_Semester": "The selected semester data is not available."
}

@lru_cache(maxsize=3)
def load_course_data(json_file):
    try:
        with open(json_file, 'r') as file:
            return json.load(file)
    except FileNotFoundError:
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
        if '*' not in code:
            corrected_code = re.sub(r'([A-Za-z]+)(\d+)', r'\1*\2', code)
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
    week = [[], [], [], [], [], []]
    for course in combination:
        for schedule_item in [course.lecture, course.seminar, course.lab]:
            if schedule_item is not None:
                for day in schedule_item.days:
                    week[dateToIndexMap[day]].append((schedule_item.start, schedule_item.finish))
    for w in range(len(week)):
        week[w] = sorted(week[w], key=lambda x: x[0])
    
    score = 0
    gap_penalties = 0
    back_to_back_penalties = 0
    long_day_penalties = 0
    days_on_campus = 0
    
    for day_schedule in week:
        if not day_schedule: continue
        days_on_campus += 1
        day_start, day_end = day_schedule[0][0], day_schedule[-1][1]
        day_length = day_end - day_start
        if day_length > 480: long_day_penalties += (day_length - 480) * 0.1
        
        for i in range(1, len(day_schedule)):
            gap = day_schedule[i][0] - day_schedule[i-1][1]
            if gap == 0: back_to_back_penalties += 20
            elif gap < 0: gap_penalties += 100 
            elif gap < 15: gap_penalties += 30
            elif gap < 30: gap_penalties += 10
            elif 30 <= gap <= 120: score += 20 + (10 * (1 - abs(gap - 60) / 60))
            elif gap <= 180: gap_penalties += 5
            else: gap_penalties += gap * 0.1
            
    if days_on_campus <= 3: score += 50
    elif days_on_campus == 4: score += 25
    final_score = score - gap_penalties - back_to_back_penalties - long_day_penalties
    return final_score, {'base_score': score, 'gap_penalties': gap_penalties, 'back_to_back_penalties': back_to_back_penalties, 'long_day_penalties': long_day_penalties, 'days_on_campus': days_on_campus}

def calculate_gap_score(total_gap):
    ideal_min, ideal_max, optimal_gap = 30, 90, 60
    if ideal_min <= total_gap <= ideal_max:
        return 100 - abs(total_gap - optimal_gap)
    elif total_gap < ideal_min:
        return max(0, 30 - (ideal_min - total_gap))
    else:
        return max(0, 50 - ((total_gap - ideal_max) * 0.5))

def section_meets_time_constraints(section, course_code, course_time_constraints):
    if course_code not in course_time_constraints: return True
    constraints = course_time_constraints[course_code]
    earliest_minutes = convert_time_to_minutes(constraints.get('earliest'))
    latest_minutes = convert_time_to_minutes(constraints.get('latest'))
    if earliest_minutes is None and latest_minutes is None: return True

    for time_component in [section.lecture, section.seminar, section.lab]:
        if time_component is None: continue
        if earliest_minutes is not None and time_component.start < earliest_minutes: return False
        if latest_minutes is not None and time_component.finish > latest_minutes: return False
    return True

def _handle_error(error_code_key, status_code=400, **kwargs):
    message = error_messages.get(error_code_key, "An unknown error occurred.")
    if "problematic_course" in kwargs:
        message = f"Course {kwargs['problematic_course']}: No sections meet time criteria. Cannot generate schedules."
    
    print(f"Error: {error_code_key} - {message}")
    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify({'error': error_code_key, 'message': message}), status_code
    return render_template('error.html', error_code=error_code_key, message=message, **kwargs)

@app.route('/', methods=['GET', 'POST'])
def schedule():
    if request.method == 'POST':
        start_time_req = time.time()

        course_codes_str = request.form.getlist('courses[]')[0]
        course_codes = [code.strip() for code in course_codes_str.upper().split(',') if code.strip()]
        course_codes = correct_course_codes(course_codes)

        if not course_codes:
            return _handle_error("No_Course_Entered")

        earliest_str = request.form.get('earliest')
        latest_str = request.form.get('latest')
        
        course_time_constraints_str = request.form.get('course_time_constraints', '{}')
        try:
            course_time_constraints = json.loads(course_time_constraints_str) if course_time_constraints_str else {}
        except json.JSONDecodeError:
            course_time_constraints = {}

        earliestAtSchool = convert_time_to_minutes(earliest_str) or 0
        latestAtSchool = convert_time_to_minutes(latest_str) or 0

        if earliestAtSchool > 0 and latestAtSchool > 0 and earliestAtSchool > latestAtSchool :
             return _handle_error("Invalid_Times")

        semester = request.form.get('semester')
        data = get_cached_course_data(semester)
        if data is None:
            return _handle_error("Invalid_Semester", problematic_semester=semester)
        
        print(f"Processing for semester: {semester}. Courses: {course_codes}")
        print(f"Global time constraints: Earliest={earliestAtSchool}, Latest={latestAtSchool}")
        print(f"Course-specific constraints: {course_time_constraints}")

        allCourseData = []
        invalid_courses = []

        global_prefilter_earliest = earliestAtSchool
        global_prefilter_latest = latestAtSchool
        if latestAtSchool > 0:
            global_prefilter_latest += 60
        elif latestAtSchool == 0:
            global_prefilter_latest = 1440
        
        print(f"Global pre-filtering window: Earliest={global_prefilter_earliest}, Latest={global_prefilter_latest}")

        for course_code in course_codes:
            if course_code not in data:
                invalid_courses.append(course_code)
                continue

            course_info = data[course_code]
            current_course_sections = []
            cData = course_info.get("Sections", [])

            for sec in cData:
                lectureTime, semTime, labTime = None, None, None
                try: lectureTime = ScheduleItem("Lecture", sec["LEC"]["start"], sec["LEC"]["end"], sec["LEC"]["date"])
                except KeyError: pass
                try: semTime = ScheduleItem("Seminar", sec["SEM"]["start"], sec["SEM"]["end"], sec["SEM"]["date"])
                except KeyError: pass
                try: labTime = ScheduleItem("Lab", sec["LAB"]["start"], sec["LAB"]["end"], sec["LAB"]["date"])
                except KeyError: pass
                
                newSection = CourseSection(sec["id"], lectureTime, semTime, labTime)

                if not section_meets_time_constraints(newSection, course_code, course_time_constraints):
                    continue
                
                section_passes_global_prefilter = True
                for item in newSection.get_schedule_items():
                    if global_prefilter_earliest > 0 and item.start < global_prefilter_earliest:
                        section_passes_global_prefilter = False
                        break
                    if item.finish > global_prefilter_latest:
                        section_passes_global_prefilter = False
                        break
                if not section_passes_global_prefilter:
                    continue
                
                current_course_sections.append(newSection)
            
            if not current_course_sections:
                print(f"CRITICAL: Course {course_code} has NO valid sections after pre-filtering. This will result in 0 combinations.")
                return _handle_error("No_Combinations_For_Course", problematic_course=course_code)

            allCourseData.append(current_course_sections)

        if invalid_courses:
            return _handle_error("Course_Not_Available", invalid_courses=invalid_courses)
        
        if latestAtSchool > 0:
            for course_sections_list in allCourseData:
                if course_sections_list:
                    def get_section_latest_end_time(section):
                        latest_end = 0
                        for item in section.get_schedule_items(): latest_end = max(latest_end, item.finish)
                        return latest_end
                    course_sections_list.sort(key=get_section_latest_end_time)

        comb = CoursePlanner(allCourseData)
        total_estimate = 1
        for course_list in allCourseData: total_estimate *= len(course_list)
        print(f"Estimated combinations for CoursePlanner: {total_estimate:,}")
        if total_estimate == 0:
             return _handle_error("No_Combinations_Query_Too_Strict")

        validCombination = comb.nonOverlapped()
        print(f"Combinations after nonOverlapped: {len(validCombination)}")

        if not validCombination:
             return _handle_error("No_Combinations_Query_Too_Strict")

        validCombination = filterByEarliestAtSchool(validCombination, earliestAtSchool)
        print(f"After earliest time filter: {len(validCombination)}")
        if not validCombination:
             return _handle_error("No_Combinations_Query_Too_Strict")
        
        validCombination = filterByLatestAtSchool(validCombination, latestAtSchool)
        print(f"After latest time filter: {len(validCombination)}")
        if not validCombination:
            if not filterByLatestAtSchool([], latestAtSchool):
                 return _handle_error("No_Combinations_Query_Too_Strict")

        if len(validCombination) > 7500:
            print(f"Limiting to first 7500 combinations for gap/score calculation performance")
            validCombination = validCombination[:7500]

        if not validCombination:
             return _handle_error("No_Combinations_Query_Too_Strict")

        validCombination, sortedTimeIndices1, times1 = filterByTotalMinTimeBetweenClasses(validCombination)
        print(f"After min time between classes: {len(validCombination)}")

        if not validCombination or not sortedTimeIndices1:
             return _handle_error("No_Combinations_Query_Too_Strict")
        
        max_results_cap = 7500
        sort_preference = request.form.get('sort_preference', 'smart_gaps')
        
        processing_limit = min(len(validCombination), max_results_cap)
        final_indices = []
        final_times = []
        
        indexed_combinations_with_gaps = []
        for i in range(len(sortedTimeIndices1)):
            original_idx = sortedTimeIndices1[i]
            if original_idx < len(validCombination) and original_idx < len(times1):
                 indexed_combinations_with_gaps.append(
                     (validCombination[original_idx], times1[original_idx], original_idx)
                 )
            else:
                print(f"Warning: Index out of bounds: original_idx={original_idx}, len(validCombination)={len(validCombination)}, len(times1)={len(times1)}")

        target_combinations_for_scoring = indexed_combinations_with_gaps[:processing_limit]
        scored_schedules = []

        if sort_preference == 'smart_gaps' or sort_preference == 'minimal_gaps':
            print(f"Calculating smart scores for {len(target_combinations_for_scoring)} combinations...")
            for i, (combo, gap_time, original_idx) in enumerate(target_combinations_for_scoring):
                comp_score, metrics = calculate_cm_schedule_score(combo)
                scored_schedules.append((comp_score, original_idx, gap_time, metrics))
                if i % 500 == 0 and i > 0: print(f"Scored {i}/{len(target_combinations_for_scoring)}...")
            scored_schedules.sort(key=lambda x: x[0], reverse=True)
            if scored_schedules:
                print(f"Best smart score: {scored_schedules[0][0]:.1f}, Metrics: {scored_schedules[0][3]}")

        elif sort_preference == 'best_gaps':
            for combo, gap_time, original_idx in target_combinations_for_scoring:
                score = calculate_gap_score(gap_time)
                scored_schedules.append((score, original_idx, gap_time))
            scored_schedules.sort(key=lambda x: x[0], reverse=True)

        elif sort_preference == 'fewer_days':
            for combo, gap_time, original_idx in target_combinations_for_scoring:
                days_used = set()
                for course in combo:
                    for item in [course.lecture, course.seminar, course.lab]:
                        if item: days_used.update(item.days)
                score = (-len(days_used) * 1000) + calculate_gap_score(gap_time)
                scored_schedules.append((score, original_idx, gap_time))
            scored_schedules.sort(key=lambda x: x[0], reverse=True)
        
        elif sort_preference == 'early_start':
            for combo, gap_time, original_idx in target_combinations_for_scoring:
                earliest_s = float('inf')
                for course in combo:
                    for item in [course.lecture, course.seminar, course.lab]:
                        if item: earliest_s = min(earliest_s, item.start)
                scored_schedules.append((earliest_s, original_idx, gap_time))
            scored_schedules.sort(key=lambda x: x[0])

        elif sort_preference == 'late_start':
            for combo, gap_time, original_idx in target_combinations_for_scoring:
                min_daily_start = float('inf')
                has_classes = False
                temp_week = [[] for _ in range(6)]
                dateToIndexMap = {"M": 0, "T": 1, "W": 2, "Th": 3, "F": 4, "Sa": 5}
                for course in combo:
                    for item in [course.lecture, course.seminar, course.lab]:
                        if item:
                            has_classes = True
                            for day_char in item.days:
                                temp_week[dateToIndexMap[day_char]].append(item.start)
                
                if not has_classes: min_daily_start = 0
                else:
                    actual_min_start = float('inf')
                    for day_sched_starts in temp_week:
                        if day_sched_starts:
                            actual_min_start = min(actual_min_start, min(day_sched_starts))
                    min_daily_start = actual_min_start if actual_min_start != float('inf') else 0

                scored_schedules.append((min_daily_start, original_idx, gap_time))
            scored_schedules.sort(key=lambda x: x[0], reverse=True)

        elif sort_preference == 'compact':
            for combo, gap_time, original_idx in target_combinations_for_scoring:
                earliest_s, latest_e = float('inf'), 0
                has_classes = False
                for course in combo:
                    for item in [course.lecture, course.seminar, course.lab]:
                        if item:
                            has_classes = True
                            earliest_s = min(earliest_s, item.start)
                            latest_e = max(latest_e, item.finish)
                time_span = (latest_e - earliest_s) if has_classes else float('inf')
                scored_schedules.append((time_span, original_idx, gap_time))
            scored_schedules.sort(key=lambda x: x[0])
        
        else:
            print(f"Unknown sort_preference '{sort_preference}', defaulting to smart_gaps.")
            for i, (combo, gap_time, original_idx) in enumerate(target_combinations_for_scoring):
                comp_score, metrics = calculate_cm_schedule_score(combo)
                scored_schedules.append((comp_score, original_idx, gap_time, metrics))
            scored_schedules.sort(key=lambda x: x[0], reverse=True)

        if not scored_schedules:
            return _handle_error("No_Combinations_Query_Too_Strict")

        final_indices = [item[1] for item in scored_schedules]
        final_times = [item[2] for item in scored_schedules]

        combinations_for_response = []
        for i, original_combo_idx in enumerate(final_indices):
            if original_combo_idx < len(validCombination):
                 combinations_for_response.append({
                    "rank": i + 1,
                    "total_time": final_times[i],
                    "courses": validCombination[original_combo_idx]
                })
            else:
                print(f"Warning: original_combo_idx {original_combo_idx} out of bounds for validCombination (len {len(validCombination)})")

        del validCombination, comb, allCourseData, indexed_combinations_with_gaps, target_combinations_for_scoring, scored_schedules
        gc.collect()

        end_time_req = time.time()
        elapsed_time = end_time_req - start_time_req
        
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest' or request.headers.get('Content-Type') == 'application/json':
            response_data_list = []
            for combo_obj in combinations_for_response:
                combo_data = {
                    'rank': combo_obj['rank'],
                    'total_time': combo_obj['total_time'],
                    'courses': []
                }
                for course_section in combo_obj['courses']:
                    course_item_data = {'section_id': course_section.courseCode}
                    if course_section.lecture: course_item_data['lecture'] = {'type': 'Lecture', 'start': course_section.lecture.start, 'finish': course_section.lecture.finish, 'days': course_section.lecture.days}
                    if course_section.seminar: course_item_data['seminar'] = {'type': 'Seminar', 'start': course_section.seminar.start, 'finish': course_section.seminar.finish, 'days': course_section.seminar.days}
                    if course_section.lab: course_item_data['lab'] = {'type': 'Lab', 'start': course_section.lab.start, 'finish': course_section.lab.finish, 'days': course_section.lab.days}
                    combo_data['courses'].append(course_item_data)
                response_data_list.append(combo_data)

            return jsonify({
                'combinations': response_data_list,
                'stats': {
                    'total_found': len(final_indices),
                    'processing_time': round(elapsed_time, 2),
                    'earliest_time_applied': earliestAtSchool,
                    'latest_time_applied': latestAtSchool
                }
            })
        
        return render_template('result.html', combinations=combinations_for_response, 
                               earliestAtSchool=earliestAtSchool, latestAtSchool=latestAtSchool, 
                               elapsed_time=elapsed_time, total_possible=len(final_indices))

    return render_template('index.html')

@app.route('/api/search-courses')
def api_search_courses():
    query = request.args.get('q', '').strip()
    semester = request.args.get('semester', 'Summer 2025')
    
    if len(query) < 2: return jsonify([])
    
    course_data = get_cached_course_data(semester)
    if not course_data: return jsonify([])
    
    results = []
    seen_codes = set()
    query_upper = query.upper()
    query_lower = query.lower()
    
    formatted_query = query_upper
    if '*' not in query_upper and re.match(r'^[A-Z]+\d+', query_upper):
        formatted_query = re.sub(r'([A-Z]+)(\d+)', r'\1*\2', query_upper)
    
    for course_code, course_info in course_data.items():
        if course_code in seen_codes: continue
            
        code_match, section_match, title_match, description_match = False, False, False, False
        code_without_star = course_code.replace('*', '')
        if (query_upper in course_code or formatted_query in course_code or 
            query_upper in code_without_star or course_code.startswith(query_upper) or
            course_code.startswith(formatted_query)):
            code_match = True
        
        sections = course_info.get('Sections', [])
        for section in sections:
            if query_upper in str(section.get('id', '')).upper():
                section_match = True; break
        
        title = course_info.get('Title', "Course")
        description = course_info.get('Description', "")
        credits = ""
        
        title_match = query_lower in title.lower()
        description_match = query_lower in description.lower()
            
        if title and "(" in title and "Credits)" in title:
            try: credits = title.split("(")[1].split(" Credits)")[0] + " Credits"
            except: pass
        
        if code_match or section_match or title_match or description_match:
            seen_codes.add(course_code)
            result = {'code': course_code, 'title': title, 
                      'description': description[:100] + ("..." if len(description) > 100 else ""),
                      'credits': credits, 'sections': len(sections), 'match_score': 0}
            
            if course_code.upper() == formatted_query: result['match_score'] = 100
            elif course_code.startswith(formatted_query) or course_code.startswith(query_upper): result['match_score'] = 90
            elif code_match: result['match_score'] = 80
            elif section_match: result['match_score'] = 70
            elif title.lower().startswith(query_lower): result['match_score'] = 60
            elif title_match: result['match_score'] = 50
            else: result['match_score'] = 40
            results.append(result)
    
    results.sort(key=lambda x: (-x['match_score'], x['code']))
    for r in results: del r['match_score']
    return jsonify(results[:15])

@app.route('/api/semester-info')
def api_semester_info():
    semester = request.args.get('semester', 'Summer 2025')
    course_data = get_cached_course_data(semester)
    if not course_data: return jsonify({'error': 'Semester data not found'}), 404
    
    total_courses = len(course_data)
    total_sections = sum(len(c.get('Sections', [])) for c in course_data.values())
    departments = set(cc.split('*')[0] for cc in course_data if '*' in cc)
    
    return jsonify({
        'semester': semester, 'total_courses': total_courses,
        'total_sections': total_sections, 'department_count': len(departments)
    })

if __name__ == '__main__':
    app.run(debug=True)