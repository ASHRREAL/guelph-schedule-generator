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
        self.combinations = self.generate_combinations()

    def generate_combinations(self):
        return list(itertools.product(*self.courses))

    def nonOverlapped(self):
        dateToIndexMap = {"M": 0, "T": 1, "W": 2, "Th": 3, "F": 4, "Sa": 5}

        validCombinations = []

        # Locate One Of The Possible Options
        for possibleCombination in self.combinations:
            week = [[], [], [], [], [], []]  # Create an empty list for each day (M-F)

            for course in possibleCombination:
                for schedule_item in [course.lecture, course.seminar, course.lab]:
                    if schedule_item is not None:
                        for day in schedule_item.days:
                            week[dateToIndexMap[day]].append((schedule_item.start, schedule_item.finish))

            isValid = True
            for w in range(len(week)):
                # sort low to high based on the start times
                week[w] = sorted(week[w], key=lambda x: x[0])

                for c in range(1, len(week[w])):
                    if week[w][c - 1][1] >= week[w][c][0]:  # Check if finish time overlaps with next start
                        isValid = False
                        break

                if not isValid:
                    break

            if isValid:
                # print("Found Valid Combination!")
                validCombinations.append(possibleCombination)

        print(f"Valid: {len(validCombinations)} Total: {len(self.combinations)}")

        return validCombinations

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
