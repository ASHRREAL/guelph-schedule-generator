import itertools


class ScheduleItem:
    """
    Object to store information for a schedule item (Lecture, Seminar, or Lab)
    """

    def __init__(self, item_type, start, finish, days):
        self.item_type = item_type  # Can be 'Lecture', 'Seminar', or 'Lab'
        self.start = start
        self.finish = finish
        self.days = days

    def __str__(self):
        return f"{self.item_type}: {self.days} from {self.start} to {self.finish}"

    def overlaps_with(self, other):
        """Check if this schedule item overlaps with another"""
        # Check if they share any common days
        common_days = set(self.days) & set(other.days)
        if not common_days:
            return False
        
        # Check time overlap for common days
        return not (self.finish <= other.start or other.finish <= self.start)

    def fits_time_constraints(self, earliest=0, latest=1440):
        """Check if this item fits within time constraints"""
        if earliest == 0 and latest == 0:
            return True
        if latest == 0:
            latest = 1440  # End of day
        return self.start >= earliest and self.finish <= latest


class CourseSection:
    """
    Object to store information for a course section
    """

    def __init__(self, courseCode, lecture=None, seminar=None, lab=None):
        self.courseCode = courseCode
        self.lecture = lecture
        self.seminar = seminar
        self.lab = lab
        self._schedule_items = None
        self._conflict_cache = {}

    def get_schedule_items(self):
        """Get all non-None schedule items for this section"""
        if self._schedule_items is None:
            self._schedule_items = [item for item in [self.lecture, self.seminar, self.lab] if item is not None]
        return self._schedule_items

    def conflicts_with(self, other):
        """Check if this section conflicts with another section"""
        cache_key = (id(self), id(other))
        if cache_key in self._conflict_cache:
            return self._conflict_cache[cache_key]
        
        # Check all combinations of schedule items between sections
        for item1 in self.get_schedule_items():
            for item2 in other.get_schedule_items():
                if item1.overlaps_with(item2):
                    self._conflict_cache[cache_key] = True
                    return True
        
        self._conflict_cache[cache_key] = False
        return False

    def fits_time_constraints(self, earliest=0, latest=1440):
        """Check if all schedule items fit within time constraints"""
        return all(item.fits_time_constraints(earliest, latest) for item in self.get_schedule_items())

    def __str__(self):
        result = f"Course Code: {self.courseCode}\n"
        if self.lecture:
            result += f"{self.lecture}\n"
        if self.seminar:
            result += f"{self.seminar}\n"
        if self.lab:
            result += f"{self.lab}\n"
        return result.strip()


class CoursePlanner:
    def __init__(self, courses):
        self.courses = courses
        self.combinations = None  # Generate lazily
        self._conflict_cache = {}

    def generate_combinations(self):
        """Generate combinations lazily to save memory"""
        if self.combinations is None:
            self.combinations = list(itertools.product(*self.courses))
        return self.combinations

    def nonOverlapped(self):
        """Optimized conflict detection using early termination and caching"""
        validCombinations = []
        
        # Pre-filter courses by time constraints if needed
        filtered_courses = []
        for course_sections in self.courses:
            # Keep all sections for now, could add pre-filtering here
            filtered_courses.append(course_sections)
        
        total_combinations = 1
        for course_sections in filtered_courses:
            total_combinations *= len(course_sections)
            
        print(f"Checking {total_combinations} total combinations...")
        
        # Use generator to avoid creating all combinations at once
        combination_count = 0
        for combination in itertools.product(*filtered_courses):
            combination_count += 1
            
            # Progress indicator for large numbers
            if combination_count % 10000 == 0:
                print(f"Processed {combination_count}/{total_combinations} combinations...")
            
            # Early termination: check conflicts as we build the combination
            if self._is_valid_combination_optimized(combination):
                validCombinations.append(combination)
                
            # Limit to prevent memory issues
            if len(validCombinations) >= 1000000:
    
                break

        print(f"Valid: {len(validCombinations)} Total Checked: {combination_count}")
        return validCombinations

    def _is_valid_combination_optimized(self, combination):
        """Optimized conflict checking with early termination"""
        # Use pairwise conflict checking instead of day-by-day checking
        for i in range(len(combination)):
            for j in range(i + 1, len(combination)):
                if self._sections_conflict(combination[i], combination[j]):
                    return False
        return True
    
    def _sections_conflict(self, section1, section2):
        """Check if two sections conflict using cached results"""
        # Create a cache key
        cache_key = (id(section1), id(section2))
        if cache_key in self._conflict_cache:
            return self._conflict_cache[cache_key]
        
        # Check for conflicts between all schedule items
        for item1 in section1.get_schedule_items():
            for item2 in section2.get_schedule_items():
                if self._items_overlap(item1, item2):
                    self._conflict_cache[cache_key] = True
                    return True
        
        self._conflict_cache[cache_key] = False
        return False
    
    def _items_overlap(self, item1, item2):
        """Fast overlap checking"""
        # Check if they share any common days
        if not (set(item1.days) & set(item2.days)):
            return False
        
        # Check time overlap
        return not (item1.finish <= item2.start or item2.finish <= item1.start)

    def print_all_schedules(self):
        combinations = self.nonOverlapped()
        for idx, combination in enumerate(combinations):
            print(f"\n\n\nSchedule for Combination {idx + 1}:")
            self.print_schedule(combination)

        print(f"\n\nAfter: {len(combinations)} Before: {len(self.combinations)}")

    def print_schedule(self, combination):
        for course in combination:
            if course.lecture:
                print(course.lecture)
            if course.seminar:
                print(course.seminar)
            if course.lab:
                print(course.lab)
