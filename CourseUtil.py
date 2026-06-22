import itertools

class ScheduleItem:
    """
    Object to store information for a schedule item (Lecture, Seminar, or Lab)
    """

    def __init__(self, item_type, start, finish, days):
        self.item_type = item_type  
        self.start = start
        self.finish = finish
        self.days = days

    def __str__(self):
        return f"{self.item_type}: {self.days} from {self.start} to {self.finish}"

    def overlaps_with(self, other):
        """Check if this schedule item overlaps with another"""

        common_days = set(self.days) & set(other.days)
        if not common_days:
            return False

        return not (self.finish <= other.start or other.finish <= self.start)

    def fits_time_constraints(self, earliest=0, latest=1440):
        """Check if this item fits within time constraints"""
        if earliest == 0 and latest == 0: 
            return True
        effective_latest = latest if latest > 0 else 1440 

        return self.start >= earliest and self.finish <= effective_latest

class CourseSection:
    """
    Object to store information for a course section.
    Lecture, seminar, or lab attributes can be a single ScheduleItem or a list of ScheduleItems.
    """

    def __init__(self, courseCode, lecture=None, seminar=None, lab=None):
        self.courseCode = courseCode
        self.lecture = lecture    
        self.seminar = seminar    
        self.lab = lab            
        self._schedule_items = None
        self._conflict_cache = {}

    def get_schedule_items(self):
        """Get all non-None schedule items for this section, handling lists."""
        if self._schedule_items is None:
            items_to_process = [self.lecture, self.seminar, self.lab]
            self._schedule_items = []
            for item_or_list in items_to_process:
                if item_or_list is not None:
                    if isinstance(item_or_list, list):
                        self._schedule_items.extend(item_or_list) 
                    else: 
                        self._schedule_items.append(item_or_list)
        return self._schedule_items

    def conflicts_with(self, other):
        """Check if this section conflicts with another section"""

        if not self.get_schedule_items() or not other.get_schedule_items():
            return False

        cache_key = (id(self), id(other))
        if cache_key in self._conflict_cache:
            return self._conflict_cache[cache_key]

        for item1 in self.get_schedule_items():
            for item2 in other.get_schedule_items():
                if item1.overlaps_with(item2):
                    self._conflict_cache[cache_key] = True
                    return True

        self._conflict_cache[cache_key] = False
        return False

    def fits_time_constraints(self, earliest=0, latest=1440):
        """Check if all schedule items fit within time constraints"""
        if not self.get_schedule_items(): 
            return True
        return all(item.fits_time_constraints(earliest, latest) for item in self.get_schedule_items())

    def __str__(self):
        result = f"Course Code: {self.courseCode}\n"

        def format_item(item_or_list, item_type_name="Item"):
            res_str = ""
            if item_or_list is not None:
                if isinstance(item_or_list, list):
                    for i, item in enumerate(item_or_list):

                        display_type = item.item_type if hasattr(item, 'item_type') else item_type_name
                        res_str += f"  {display_type} ({i+1}): Days {item.days} Start {item.start} Finish {item.finish}\n"
                else: 
                    display_type = item_or_list.item_type if hasattr(item_or_list, 'item_type') else item_type_name
                    res_str += f"  {display_type}: Days {item_or_list.days} Start {item_or_list.start} Finish {item_or_list.finish}\n"
            return res_str

        result += format_item(self.lecture, "Lecture")
        result += format_item(self.seminar, "Seminar")
        result += format_item(self.lab, "Lab")
        return result.strip()

class CoursePlanner:
    def __init__(self, courses):
        self.courses = courses
        self._conflict_matrix = None
        self._section_map = None

    def _build_conflict_matrix(self):
        """Pre-compute conflict matrix for all sections across all courses."""
        if self._conflict_matrix is not None:
            return

        sections = []
        section_course_map = []
        for ci, course_sections in enumerate(self.courses):
            for section in course_sections:
                sections.append(section)
                section_course_map.append(ci)

        n = len(sections)
        self._conflict_matrix = [set() for _ in range(n)]
        self._section_map = (sections, section_course_map)

        for i in range(n):
            for j in range(i + 1, n):
                if section_course_map[i] == section_course_map[j]:
                    continue
                if sections[i].conflicts_with(sections[j]):
                    self._conflict_matrix[i].add(j)
                    self._conflict_matrix[j].add(i)

    def nonOverlapped(self):
        """Use pre-computed conflict matrix for fast combination checking."""
        self._build_conflict_matrix()
        sections, section_course_map = self._section_map
        conflict_matrix = self._conflict_matrix

        course_section_indices = []
        idx = 0
        for course_sections in self.courses:
            indices = list(range(idx, idx + len(course_sections)))
            course_section_indices.append(indices)
            idx += len(course_sections)

        total_combinations = 1
        for ci in range(len(self.courses)):
            total_combinations *= len(course_section_indices[ci])

        if total_combinations == 0:
            print("No combinations possible as at least one course has no available sections.")
            return []

        print(f"Checking {total_combinations:,} total combinations in CoursePlanner...")

        validCombinations = []
        combination_count = 0

        for combo_indices in itertools.product(*course_section_indices):
            combination_count += 1

            if combination_count % 100000 == 0 and combination_count > 0:
                print(f"Processed {combination_count:,}/{total_combinations:,} combinations in planner...")

            valid = True
            for i in range(len(combo_indices)):
                for j in range(i + 1, len(combo_indices)):
                    if combo_indices[j] in conflict_matrix[combo_indices[i]]:
                        valid = False
                        break
                if not valid:
                    break

            if valid:
                combo_sections = tuple(sections[idx] for idx in combo_indices)
                validCombinations.append(combo_sections)

            if len(validCombinations) >= 1500000:
                print(f"Reached combination limit ({len(validCombinations):,}). Stopping early.")
                break

        print(f"Planner found {len(validCombinations):,} valid (non-overlapping) combinations out of {combination_count:,} checked.")
        return validCombinations

    def print_all_schedules(self):

        if self.combinations is None: 
            self.generate_combinations() 
            print(f"Total potential combinations before filtering: {len(self.combinations):,}")

        filtered_combinations = self.nonOverlapped() 

        for idx, combination in enumerate(filtered_combinations):
            if idx >= 10: 
                print(f"... and {len(filtered_combinations) - 10} more schedules.")
                break
            print(f"\n\nSchedule for Combination {idx + 1}:")
            self.print_schedule(combination)

        print(f"\nTotal non-overlapping schedules: {len(filtered_combinations):,}")

    def print_schedule(self, combination): 
        for course_section in combination: 
            print(course_section) 