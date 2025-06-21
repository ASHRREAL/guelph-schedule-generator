from flask import Flask, render_template, request, jsonify
import json
import time  # Import the time module
from CourseUtil import ScheduleItem, CourseSection, CoursePlanner
from sortingMethods import filterByEarliestAtSchool, filterByLatestAtSchool, filterByTotalMinTimeBetweenClasses
from functools import lru_cache
import gc  # For garbage collection

app = Flask(__name__)

# Add configuration for better performance
app.config['JSON_SORT_KEYS'] = False
app.config['JSONIFY_PRETTYPRINT_REGULAR'] = False

import re

# Cache for loaded course data to improve performance
course_data_cache = {}

error_codes = ["No_Course_Entered", "Course_Not_Available", "Invalid_Times", "None", "No_Combinations"]


@lru_cache(maxsize=3)  # Cache up to 3 semester files
def load_course_data(json_file):
    """Load and cache course data from JSON file"""
    try:
        with open(json_file, 'r') as file:
            return json.load(file)
    except FileNotFoundError:
        return None


def get_cached_course_data(semester):
    """Get course data with caching"""
    json_file_map = {
        "Summer 2025": 'S25.json',
        "Fall 2025": 'F25.json',
        "Winter 2026": 'W26.json'
    }
    
    if semester not in json_file_map:
        return None
    
    json_file = json_file_map[semester]
    
    # Use cached version if available
    if json_file in course_data_cache:
        return course_data_cache[json_file]
      # Load and cache the data
    data = load_course_data(json_file)
    if data:
        course_data_cache[json_file] = data
    
        return data


def get_course_data_for_semester(semester):
    """Get course data for a specific semester (wrapper for caching)"""
    return get_cached_course_data(semester)


# Function to correct course code formatting
def correct_course_codes(course_codes):
    # Regular expression to match course codes missing the '*'
    corrected_codes = []

    for code in course_codes:
        # If the code doesn't already contain a '*', fix it
        if '*' not in code:
            # Use regex to separate the letters and numbers, and insert '*'
            corrected_code = re.sub(r'([A-Za-z]+)(\d+)', r'\1*\2', code)
            corrected_codes.append(corrected_code)
        else:
            corrected_codes.append(code)

    return corrected_codes


def convert_time_to_minutes(time_str):
    """Convert time string (HH:MM) to minutes since midnight"""
    if not time_str:
        return None
    try:
        hours, minutes = map(int, time_str.split(':'))
        return hours * 60 + minutes
    except (ValueError, AttributeError):
        return None


def calculate_comprehensive_schedule_score(combination):
    """Calculate a comprehensive score for a schedule combination"""
    dateToIndexMap = {"M": 0, "T": 1, "W": 2, "Th": 3, "F": 4, "Sa": 5}
    week = [[], [], [], [], [], []]  # Create an empty list for each day (M-S)
    
    # Build weekly schedule
    for course in combination:
        for schedule_item in [course.lecture, course.seminar, course.lab]:
            if schedule_item is not None:
                for day in schedule_item.days:
                    week[dateToIndexMap[day]].append((schedule_item.start, schedule_item.finish))
    
    # Sort each day by start time
    for w in range(len(week)):
        week[w] = sorted(week[w], key=lambda x: x[0])
    
    score = 0
    gap_penalties = 0
    back_to_back_penalties = 0
    long_day_penalties = 0
    days_on_campus = 0
    
    for day_schedule in week:
        if not day_schedule:
            continue
            
        days_on_campus += 1
        
        # Calculate daily metrics
        day_start = day_schedule[0][0]
        day_end = day_schedule[-1][1]
        day_length = day_end - day_start
        
        # Penalty for very long days (over 8 hours = 480 minutes)
        if day_length > 480:
            long_day_penalties += (day_length - 480) * 0.1
        
        # Analyze gaps between classes
        for i in range(1, len(day_schedule)):
            gap = day_schedule[i][0] - day_schedule[i-1][1]
            
            if gap == 0:
                # Back-to-back classes - moderate penalty
                back_to_back_penalties += 20
            elif gap < 0:
                # Overlapping classes - should not happen but heavy penalty
                gap_penalties += 100
            elif gap < 15:
                # Very short gap - difficult to move between classes
                gap_penalties += 30
            elif gap < 30:
                # Short gap - some penalty
                gap_penalties += 10
            elif 30 <= gap <= 120:
                # Good gap - reward this
                score += 20 + (10 * (1 - abs(gap - 60) / 60))  # Best at 60 minutes
            elif gap <= 180:
                # Long gap - minor penalty
                gap_penalties += 5
            else:
                # Very long gap - more penalty
                gap_penalties += gap * 0.1
    
    # Bonus for fewer days on campus (more concentrated schedule)
    if days_on_campus <= 3:
        score += 50
    elif days_on_campus == 4:
        score += 25
    
    # Calculate final score
    final_score = score - gap_penalties - back_to_back_penalties - long_day_penalties
    
    return final_score, {
        'base_score': score,
        'gap_penalties': gap_penalties,
        'back_to_back_penalties': back_to_back_penalties,
        'long_day_penalties': long_day_penalties,
        'days_on_campus': days_on_campus
    }

def calculate_gap_score(total_gap):
    """Calculate gap distribution score (higher is better) - Legacy function"""
    # Ideal gap range is 30-90 minutes
    ideal_min = 30
    ideal_max = 90
    optimal_gap = 60
    
    if ideal_min <= total_gap <= ideal_max:
        # Within ideal range - score based on proximity to optimal
        proximity_to_optimal = abs(total_gap - optimal_gap)
        return 100 - proximity_to_optimal
    elif total_gap < ideal_min:
        # Too little gap time - penalize heavily
        return max(0, 30 - (ideal_min - total_gap))
    else:
        # Too much gap time - penalize moderately
        excess = total_gap - ideal_max
        return max(0, 50 - (excess * 0.5))


def section_meets_time_constraints(section, course_code, course_time_constraints):
    """Check if a course section meets the course-specific time constraints"""
    if course_code not in course_time_constraints:
        return True

    constraints = course_time_constraints[course_code]
    earliest_minutes = convert_time_to_minutes(constraints.get('earliest'))
    latest_minutes = convert_time_to_minutes(constraints.get('latest'))

    # If no constraints are set, allow the section
    if earliest_minutes is None and latest_minutes is None:
        return True

    # Check all time components of the section
    for time_component in [section.lecture, section.seminar, section.lab]:
        if time_component is None:
            continue

        start_minutes = time_component.start
        end_minutes = time_component.finish

        # Check if section times fall within constraints
        if earliest_minutes is not None and start_minutes < earliest_minutes:
            return False
        if latest_minutes is not None and end_minutes > latest_minutes:
            return False

    return True


@app.route('/', methods=['GET', 'POST'])
def schedule():
    if request.method == 'POST':
        error_code = "None"

        # Record the start time
        start_time = time.time()

        # Get the course codes and correct the format
        course_codes = ''.join(request.form.getlist('courses[]')[0].split()).upper().split(',')
        print("Received Course Codes")
        print(course_codes)

        course_codes = [code for code in course_codes if code]  # Remove empty strings
        course_codes = correct_course_codes(course_codes)  # Correct the course code format

        print("Filtered Course Codes")
        print(course_codes)

        # If no course codes were entered, trigger an error
        if len(course_codes) == 0:
            print("No Courses Entered")
            error_code = "No_Course_Entered"
            return render_template('error.html', error_code=error_code)

        # Get earliest and latest times
        earliest = request.form.get('earliest', None)
        latest = request.form.get('latest', None)
        
        # Get course-specific time constraints
        course_time_constraints_str = request.form.get('course_time_constraints', '{}')
        try:
            course_time_constraints = json.loads(course_time_constraints_str) if course_time_constraints_str else {}
        except json.JSONDecodeError:
            course_time_constraints = {}

        print("Entered Times:")
        print(earliest, latest)
        print("Course-specific time constraints:")
        print(course_time_constraints)

        if earliest:
            earliestAtSchool = int(earliest.split(":")[0]) * 60 + int(earliest.split(":")[1])
        else:
            earliestAtSchool = 0  # Default: 12:00 AM

        if latest:
            latestAtSchool = int(latest.split(":")[0]) * 60 + int(latest.split(":")[1])
        else:
            latestAtSchool = 0  # Default: 12:00 AM (Midnight)

        # Check if times are valid
        if earliestAtSchool > latestAtSchool:
            error_code = "Invalid_Times"
            print("User entered invalid times")
            return render_template('error.html', error_code=error_code)        # Load the correct file based on the selected semester
        semester = request.form.get('semester')
        
        # Use cached data loading
        data = get_cached_course_data(semester)
        if data is None:
            error_code = "Invalid_Semester"
            return render_template('error.html', error_code=error_code)
        
        print(f"Reading {semester} Courses (cached: {semester in course_data_cache})")

        # Rest of your code to process the course schedule
        allCourseData = []

        # Initialize a list to store invalid course codes
        invalid_courses = []

        # Check if courses are available in the data
        for course_code in course_codes:
            if course_code in data:
                course_info = data[course_code]
                allCourseData.append([])
                cData = course_info.get("Sections", [])

                for sec in cData:
                    try:
                        lectureTime = ScheduleItem("Lecture", sec["LEC"]["start"], sec["LEC"]["end"],
                                                   sec["LEC"]["date"])
                    except KeyError:
                        lectureTime = None
                    try:
                        semTime = ScheduleItem("Seminar", sec["SEM"]["start"], sec["SEM"]["end"], sec["SEM"]["date"])
                    except KeyError:
                        semTime = None
                    try:
                        labTime = ScheduleItem("Lab", sec["LAB"]["start"], sec["LAB"]["end"], sec["LAB"]["date"])
                    except KeyError:
                        labTime = None

                    newSection = CourseSection(sec["id"], lectureTime, semTime, labTime)
                    
                    # Apply course-specific time constraints
                    if section_meets_time_constraints(newSection, course_code, course_time_constraints):
                        allCourseData[-1].append(newSection)
            else:
                invalid_courses.append(course_code)        # If there are invalid courses, trigger an error
        if invalid_courses:
            print("Invalid Course Codes")
            print(invalid_courses)
            error_code = "Course_Not_Available"
            return render_template('error.html', error_code=error_code, invalid_courses=invalid_courses)

        comb = CoursePlanner(allCourseData)
        validCombination = comb.nonOverlapped()

        if len(validCombination) == 0:
            print("Could not find any valid combinations")
            error_code = "No_Combinations"
            return render_template('error.html', error_code=error_code)

        validCombination = filterByEarliestAtSchool(validCombination, earliestAtSchool)
        validCombination = filterByLatestAtSchool(validCombination, latestAtSchool)

        validCombination, sortedTimeIndices1, times1 = filterByTotalMinTimeBetweenClasses(validCombination)

        print("Post Processed Valid Combinations:")
        print(len(validCombination))        # Get max results and sort preference from form
        max_results = int(request.form.get('max_results', 500))  # Increased default
        max_results = min(max_results, 5000)  # Cap at 5000 for performance
        sort_preference = request.form.get('sort_preference', 'smart_gaps')  # Changed default to smart_gaps
        
        print(f"Sort preference: {sort_preference}")
        
        # Apply sorting based on preference
        if sort_preference == 'smart_gaps' or sort_preference == 'minimal_gaps':
            # Use comprehensive schedule scoring (new default)
            comprehensive_scores = []
            for i in range(len(sortedTimeIndices1)):
                idx = sortedTimeIndices1[i]
                combination = validCombination[idx]
                
                # Calculate comprehensive score
                comp_score, metrics = calculate_comprehensive_schedule_score(combination)
                comprehensive_scores.append((comp_score, idx, times1[idx], metrics))
            
            # Sort by comprehensive score (highest score first)
            comprehensive_scores.sort(key=lambda x: x[0], reverse=True)
            
            # Create final sorted indices and times
            final_indices = [item[1] for item in comprehensive_scores[:max_results]]
            final_times = [item[2] for item in comprehensive_scores[:max_results]]
            
            # Add scoring details for debugging (optional)
            if len(comprehensive_scores) > 0:
                best_score = comprehensive_scores[0]
                print(f"Best schedule score: {best_score[0]:.1f}")
                print(f"Metrics: {best_score[3]}")
            
        elif sort_preference == 'best_gaps':
            # Legacy gap scoring for backward compatibility
            gap_scores = []
            for i in range(len(sortedTimeIndices1)):
                idx = sortedTimeIndices1[i]
                gap_time = times1[idx]
                score = calculate_gap_score(gap_time)
                gap_scores.append((score, idx, gap_time))
              # Sort by gap score (highest score first)
            gap_scores.sort(key=lambda x: x[0], reverse=True)
            
            # Create final sorted indices and times
            final_indices = [item[1] for item in gap_scores[:max_results]]
            final_times = [item[2] for item in gap_scores[:max_results]]
            
        elif sort_preference == 'fewer_days':
            # Sort by fewer days on campus
            day_scores = []
            for i in range(len(sortedTimeIndices1)):
                idx = sortedTimeIndices1[i]
                combination = validCombination[idx]
                
                # Count unique days
                days_used = set()
                for course in combination:
                    for schedule_item in [course.lecture, course.seminar, course.lab]:
                        if schedule_item:
                            days_used.update(schedule_item.days)
                
                # Score: fewer days is better, but also consider gap quality
                days_count = len(days_used)
                gap_time = times1[idx]
                
                # Primary score: fewer days (negative because we want fewer days first)
                # Secondary score: better gaps
                score = (-days_count * 1000) + calculate_gap_score(gap_time)
                day_scores.append((score, idx, times1[idx]))
            
            # Sort by score (higher is better)
            day_scores.sort(key=lambda x: x[0], reverse=True)
            final_indices = [item[1] for item in day_scores[:max_results]]
            final_times = [item[2] for item in day_scores[:max_results]]
            
        elif sort_preference == 'early_start':
            # Sort by earliest start time
            early_scores = []
            for i in range(len(sortedTimeIndices1)):
                idx = sortedTimeIndices1[i]
                combination = validCombination[idx]
                
                # Find earliest start time across all courses in combination
                earliest_start = float('inf')
                for course in combination:
                    for schedule_item in [course.lecture, course.seminar, course.lab]:
                        if schedule_item:
                            earliest_start = min(earliest_start, schedule_item.start)
                
                early_scores.append((earliest_start, idx, times1[idx]))
            
            # Sort by earliest start time
            early_scores.sort(key=lambda x: x[0])
            final_indices = [item[1] for item in early_scores[:max_results]]
            final_times = [item[2] for item in early_scores[:max_results]]
            
        elif sort_preference == 'late_start':
            # Sort by latest start time
            late_scores = []
            for i in range(len(sortedTimeIndices1)):
                idx = sortedTimeIndices1[i]
                combination = validCombination[idx]
                
                # Find latest start time across all courses in combination
                latest_start = 0
                for course in combination:
                    for schedule_item in [course.lecture, course.seminar, course.lab]:
                        if schedule_item:
                            latest_start = max(latest_start, schedule_item.start)
                
                late_scores.append((latest_start, idx, times1[idx]))
            
            # Sort by latest start time (descending)
            late_scores.sort(key=lambda x: x[0], reverse=True)
            final_indices = [item[1] for item in late_scores[:max_results]]
            final_times = [item[2] for item in late_scores[:max_results]]
            
        elif sort_preference == 'compact':
            # Sort by most compact schedule (shortest time span)
            compact_scores = []
            for i in range(len(sortedTimeIndices1)):
                idx = sortedTimeIndices1[i]
                combination = validCombination[idx]
                
                # Calculate total time span for the combination
                earliest_start = float('inf')
                latest_end = 0
                for course in combination:
                    for schedule_item in [course.lecture, course.seminar, course.lab]:
                        if schedule_item:
                            earliest_start = min(earliest_start, schedule_item.start)
                            latest_end = max(latest_end, schedule_item.finish)
                
                time_span = latest_end - earliest_start if earliest_start != float('inf') else 0
                compact_scores.append((time_span, idx, times1[idx]))
              # Sort by time span (ascending - smaller span is more compact)
            compact_scores.sort(key=lambda x: x[0])
            final_indices = [item[1] for item in compact_scores[:max_results]]
            final_times = [item[2] for item in compact_scores[:max_results]]
            
        else:
            # Default: use smart gaps (comprehensive scoring)
            comprehensive_scores = []
            for i in range(len(sortedTimeIndices1)):
                idx = sortedTimeIndices1[i]
                combination = validCombination[idx]
                
                # Calculate comprehensive score
                comp_score, metrics = calculate_comprehensive_schedule_score(combination)
                comprehensive_scores.append((comp_score, idx, times1[idx], metrics))
            
            # Sort by comprehensive score (highest score first)
            comprehensive_scores.sort(key=lambda x: x[0], reverse=True)
            
            # Create final sorted indices and times
            final_indices = [item[1] for item in comprehensive_scores[:max_results]]
            final_times = [item[2] for item in comprehensive_scores[:max_results]]
        
        # Create combinations using the sorted indices
        combinations = []
        for i, idx in enumerate(final_indices):
            combination = {
                "total_time": final_times[i],
                "courses": validCombination[idx]
            }
            combinations.append(combination)
        
        # Clear large variables to free memory
        del validCombination
        del comb
        gc.collect()  # Force garbage collection        # Record the end time
        end_time = time.time()
        elapsed_time = end_time - start_time

        return render_template('result.html', combinations=combinations, earliestAtSchool=earliestAtSchool,
                               latestAtSchool=latestAtSchool, elapsed_time=elapsed_time,
                               total_possible=len(sortedTimeIndices1))

    return render_template('index.html')


# API endpoints for frontend functionality

@app.route('/api/search-courses')
def api_search_courses():
    """Search for courses by query string"""
    query = request.args.get('q', '').strip()
    semester = request.args.get('semester', 'Summer 2025')
    
    if len(query) < 2:
        return jsonify([])
    
    # Get course data for the semester
    course_data = get_course_data_for_semester(semester)
    if not course_data:
        return jsonify([])
    
    # Search through courses
    results = []
    seen_codes = set()
    query_upper = query.upper()
    query_lower = query.lower()
    
    for course_code, course_info in course_data.items():
        if course_code in seen_codes:
            continue
            
        # Check if query matches course code
        code_match = query_upper in course_code
          # Check if query matches course title or description
        title_match = False
        description_match = False
        title = "Course"
        description = ""
        credits = ""
        
        # Extract course information from the main course object
        if 'Title' in course_info:
            title = course_info['Title']
            title_match = query_lower in title.lower()
        
        if 'Description' in course_info:
            description = course_info['Description']
            description_match = query_lower in description.lower()
            
        # Extract credits from title (format: "COURSE*1234 Course Name (X.X Credits)")
        if title and "(" in title and "Credits)" in title:
            try:
                credits_part = title.split("(")[1].split(" Credits)")[0]
                credits = credits_part + " Credits"
            except (IndexError, AttributeError):
                credits = ""
        
        # Include if any match is found
        if code_match or title_match or description_match:
            seen_codes.add(course_code)
            
            # Count sections
            section_count = len(course_info.get('Sections', []))
            
            results.append({
                'code': course_code,
                'title': title,
                'description': description[:100] + "..." if len(description) > 100 else description,
                'credits': credits,
                'sections': section_count
            })
    
    # Sort by relevance (exact code match first, then title match, then description match)
    def sort_key(x):
        code_exact = x['code'] == query_upper
        code_starts = x['code'].startswith(query_upper)
        title_starts = x['title'].lower().startswith(query_lower)
        return (not code_exact, not code_starts, not title_starts, x['code'])
    
    results.sort(key=sort_key)
    
    # Limit results to prevent overwhelming the UI
    return jsonify(results[:15])


@app.route('/api/semester-info')
def api_semester_info():
    """Get information about a semester"""
    semester = request.args.get('semester', 'Summer 2025')
    
    course_data = get_course_data_for_semester(semester)
    if not course_data:
        return jsonify({'error': 'Semester data not found'})
    
    # Calculate statistics
    total_courses = len(course_data)
    total_sections = sum(len(course_info.get('Sections', [])) for course_info in course_data.values())
    
    # Count unique departments
    departments = set()
    for course_code in course_data.keys():
        if '*' in course_code:
            dept = course_code.split('*')[0]
            departments.add(dept)
    
    return jsonify({
        'semester': semester,
        'total_courses': total_courses,
        'total_sections': total_sections,
        'department_count': len(departments)
    })


def get_course_data_for_semester(semester):
    """Helper function to get course data for a specific semester"""
    # Map semester to JSON file
    json_file_map = {
        "Summer 2025": 'S25.json',
        "Fall 2025": 'F25.json',
        "Winter 2026": 'W26.json'
    }
    
    json_file = json_file_map.get(semester)
    if not json_file:
        return None
    
    try:
        with open(json_file, 'r') as file:
            data = json.load(file)
            return data
    except FileNotFoundError:
        print(f"Warning: {json_file} not found for semester {semester}")
        return None


if __name__ == '__main__':
    app.run(debug=True)













#
# from flask import Flask, render_template
#
# import M68k_Tutorial.routes
# from CoursePlaner.routes import course_planer_bp
# from M68k_Tutorial.routes import m68k_bp
#
# app = Flask(__name__)
#
# # Register the blueprint
# app.register_blueprint(course_planer_bp)
#
# # Register the blueprint
# app.register_blueprint(M68k_Tutorial.routes.m68k_bp)
#
# @app.route('/')
# def landing_page():
#     return render_template('landing_page.html')
#
# if __name__ == '__main__':
#     app.run(debug=False)

#
#
#
#
#
#
#
# from flask import Flask, render_template, Blueprint, request
# import json
# import time
# import re
# from CourseUtil import ScheduleItem, CourseSection, CoursePlanner
# from sortingMethods import filterByEarliestAtSchool, filterByLatestAtSchool, filterByTotalMinTimeBetweenClasses
#
#
# # Course Planner Blueprint
# course_planer_bp = Blueprint('course_planer', __name__, template_folder='templates', static_folder='static')
#
# error_codes = ["No_Course_Entered", "Course_Not_Available", "Invalid_Times", "None", "No_Combinations"]
#
# def correct_course_codes(course_codes):
#     corrected_codes = []
#     for code in course_codes:
#         if '*' not in code:
#             corrected_code = re.sub(r'([A-Za-z]+)(\d+)', r'\1*\2', code)
#             corrected_codes.append(corrected_code)
#         else:
#             corrected_codes.append(code)
#     return corrected_codes
#
# @course_planer_bp.route('/course-planner', methods=['GET', 'POST'])
# def schedule():
#     if request.method == 'POST':
#         error_code = "None"
#         start_time = time.time()
#
#         # Get the course codes and correct the format
#         course_codes = ''.join(request.form.getlist('courses[]')[0].split()).upper().split(',')
#         print("Received Course Codes:", course_codes)
#
#         course_codes = [code for code in course_codes if code]
#         course_codes = correct_course_codes(course_codes)
#
#         if not course_codes:
#             error_code = "No_Course_Entered"
#             return render_template('error.html', error_code=error_code)
#
#         earliest = request.form.get('earliest', None)
#         latest = request.form.get('latest', None)
#         if earliest:
#             earliestAtSchool = int(earliest.split(":")[0]) * 60 + int(earliest.split(":")[1])
#         else:
#             earliestAtSchool = 0
#
#         if latest:
#             latestAtSchool = int(latest.split(":")[0]) * 60 + int(latest.split(":")[1])
#         else:
#             latestAtSchool = 0
#
#         if earliestAtSchool > latestAtSchool:
#             error_code = "Invalid_Times"
#             return render_template('error.html', error_code=error_code)
#
#         semester = request.form.get('semester')
#         if semester == "Fall 2024":
#             json_file = 'CoursePlaner/outputF24.json'
#         elif semester == "Winter 2025":
#             json_file = 'CoursePlaner/outputW25NoProfNoRooms.json'
#         else:
#             error_code = "Invalid_Semester"
#             return render_template('error.html', error_code=error_code)
#
#         try:
#             with open(json_file, 'r') as file:
#                 data = json.load(file)
#         except FileNotFoundError:
#             error_code = "File_Not_Found"
#             return render_template('error.html', error_code=error_code)
#
#         allCourseData = []
#         invalid_courses = []
#         for course_code in course_codes:
#             if course_code in data:
#                 course_info = data[course_code]
#                 allCourseData.append([])
#                 cData = course_info.get("Sections", [])
#                 for sec in cData:
#                     try:
#                         lectureTime = ScheduleItem("Lecture", sec["LEC"]["start"], sec["LEC"]["end"],
#                                                    sec["LEC"]["date"])
#                     except KeyError:
#                         lectureTime = None
#                     try:
#                         semTime = ScheduleItem("Seminar", sec["SEM"]["start"], sec["SEM"]["end"], sec["SEM"]["date"])
#                     except KeyError:
#                         semTime = None
#                     try:
#                         labTime = ScheduleItem("Lab", sec["LAB"]["start"], sec["LAB"]["end"], sec["LAB"]["date"])
#                     except KeyError:
#                         labTime = None
#
#                     newSection = CourseSection(sec["id"], lectureTime, semTime, labTime)
#                     allCourseData[-1].append(newSection)
#             else:
#                 invalid_courses.append(course_code)
#
#         if invalid_courses:
#             error_code = "Course_Not_Available"
#             return render_template('error.html', error_code=error_code, invalid_courses=invalid_courses)
#
#         comb = CoursePlanner(allCourseData)
#         validCombination = comb.nonOverlapped()
#
#         if not validCombination:
#             error_code = "No_Combinations"
#             return render_template('error.html', error_code=error_code)
#
#         validCombination = filterByEarliestAtSchool(validCombination, earliestAtSchool)
#         validCombination = filterByLatestAtSchool(validCombination, latestAtSchool)
#         validCombination, sortedTimeIndices1, times1 = filterByTotalMinTimeBetweenClasses(validCombination)
#
#         combinations = []
#         for i in sortedTimeIndices1:
#             combination = {"total_time": times1[i], "courses": validCombination[i]}
#             combinations.append(combination)
#
#         end_time = time.time()
#         elapsed_time = end_time - start_time
#
#         return render_template(
#             'result.html',
#             combinations=combinations,
#             earliestAtSchool=earliestAtSchool,
#             latestAtSchool=latestAtSchool,
#             elapsed_time=elapsed_time,
#             total_possible=len(comb.combinations),
#         )
#
#     return render_template('index.html')
#
#
# # Main Flask App
# app = Flask(__name__)
#
# app.register_blueprint(course_planer_bp)
#
# @app.route('/')
# def landing_page():
#     return render_template('index.html')
#
# if __name__ == '__main__':
#     app.run(debug=True)





