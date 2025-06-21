import itertools
from typing import List, Generator, Tuple, Optional, Dict
import time


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

    def overlaps_with(self, other: 'ScheduleItem') -> bool:
        """Check if this schedule item overlaps with another"""
        # Check if they share any common days
        common_days = set(self.days) & set(other.days)
        if not common_days:
            return False
        
        # Check time overlap for common days
        return not (self.finish <= other.start or other.finish <= self.start)

    def fits_time_constraints(self, earliest: int = 0, latest: int = 1440) -> bool:
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

    def get_schedule_items(self) -> List[ScheduleItem]:
        """Get all non-None schedule items for this section"""
        if self._schedule_items is None:
            self._schedule_items = [item for item in [self.lecture, self.seminar, self.lab] if item is not None]
        return self._schedule_items

    def conflicts_with(self, other: 'CourseSection') -> bool:
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

    def fits_time_constraints(self, earliest: int = 0, latest: int = 1440) -> bool:
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


class OptimizedCoursePlanner:
    """
    Optimized course planner that uses generators and early pruning
    """
    
    def __init__(self, courses: List[List[CourseSection]], earliest: int = 0, latest: int = 1440):
        self.courses = courses
        self.earliest = earliest
        self.latest = latest
        self.filtered_courses = self._filter_courses_by_time()
        self.total_combinations = self._calculate_total_combinations()
        
        # Performance tracking
        self.combinations_checked = 0
        self.valid_combinations_found = 0
        self.early_pruned = 0

    def _filter_courses_by_time(self) -> List[List[CourseSection]]:
        """Pre-filter course sections by time constraints"""
        filtered = []
        for course_sections in self.courses:
            valid_sections = [
                section for section in course_sections 
                if section.fits_time_constraints(self.earliest, self.latest)
            ]
            if not valid_sections:
                # If no sections fit time constraints, keep original to show error
                filtered.append(course_sections)
            else:
                filtered.append(valid_sections)
        return filtered

    def _calculate_total_combinations(self) -> int:
        """Calculate total possible combinations after time filtering"""
        total = 1
        for course_sections in self.filtered_courses:
            total *= len(course_sections)
        return total

    def generate_valid_combinations(self, max_combinations: int = 10000) -> Generator[Tuple[CourseSection, ...], None, None]:
        """
        Generate valid combinations using a generator approach with early pruning
        """
        def is_valid_partial_combination(partial_combination: List[CourseSection]) -> bool:
            """Check if a partial combination is valid (no conflicts)"""
            for i in range(len(partial_combination)):
                for j in range(i + 1, len(partial_combination)):
                    if partial_combination[i].conflicts_with(partial_combination[j]):
                        return False
            return True

        def backtrack(course_index: int, current_combination: List[CourseSection]):
            """Recursive backtracking with early pruning"""
            self.combinations_checked += 1
            
            if course_index == len(self.filtered_courses):
                # We have a complete combination
                self.valid_combinations_found += 1
                yield tuple(current_combination)
                return

            # Try each section for the current course
            for section in self.filtered_courses[course_index]:
                # Create new combination with this section
                new_combination = current_combination + [section]
                
                # Early pruning: check if this partial combination is valid
                if is_valid_partial_combination(new_combination):
                    # Recursively try next course
                    yield from backtrack(course_index + 1, new_combination)
                else:
                    self.early_pruned += 1

                # Stop if we've found enough combinations
                if self.valid_combinations_found >= max_combinations:
                    return

        yield from backtrack(0, [])

    def get_valid_combinations(self, max_combinations: int = 10000) -> List[Tuple[CourseSection, ...]]:
        """Get all valid combinations up to the maximum limit"""
        start_time = time.time()
        
        valid_combinations = list(self.generate_valid_combinations(max_combinations))
        
        end_time = time.time()
        elapsed_time = end_time - start_time
        
        print(f"Optimization Results:")
        print(f"  Time taken: {elapsed_time:.2f} seconds")
        print(f"  Combinations checked: {self.combinations_checked:,}")
        print(f"  Valid combinations found: {self.valid_combinations_found:,}")
        print(f"  Early pruned: {self.early_pruned:,}")
        print(f"  Total possible (after time filter): {self.total_combinations:,}")
        print(f"  Efficiency: {(self.early_pruned / max(self.combinations_checked, 1)) * 100:.1f}% pruned")
        
        return valid_combinations

    def nonOverlapped(self, max_combinations: int = 10000) -> List[Tuple[CourseSection, ...]]:
        """
        Legacy method for compatibility - returns valid combinations
        """
        return self.get_valid_combinations(max_combinations)


class CourseSearchIndex:
    """
    Indexed search for course suggestions
    """
    
    def __init__(self, course_data: Dict):
        self.course_data = course_data
        self.title_index = {}
        self.code_index = {}
        self._build_indexes()

    def _build_indexes(self):
        """Build search indexes for faster lookups"""
        for course_code, course_info in self.course_data.items():
            # Index by course code parts
            code_parts = course_code.replace('*', ' ').split()
            for part in code_parts:
                if part not in self.code_index:
                    self.code_index[part] = []
                self.code_index[part].append(course_code)

            # Index by title words
            title = course_info.get('Title', '').upper()
            title_words = title.split()
            for word in title_words:
                if len(word) >= 3:  # Only index words with 3+ characters
                    if word not in self.title_index:
                        self.title_index[word] = []
                    self.title_index[word].append(course_code)

    def search(self, query: str, limit: int = 10) -> List[Dict]:
        """Search for courses matching the query"""
        query = query.upper().strip()
        if len(query) < 2:
            return []

        matches = set()
        
        # Direct course code match
        if query in self.course_data:
            matches.add(query)
        
        # Partial course code matches
        for code_part, courses in self.code_index.items():
            if query in code_part:
                matches.update(courses)
        
        # Title word matches
        for word, courses in self.title_index.items():
            if query in word:
                matches.update(courses)

        # Convert to list with course info
        results = []
        for course_code in list(matches)[:limit]:
            course_info = self.course_data[course_code]
            results.append({
                'code': course_code,
                'title': course_info.get('Title', ''),
                'description': course_info.get('Description', '')[:100] + '...' if len(course_info.get('Description', '')) > 100 else course_info.get('Description', ''),
                'sections': len(course_info.get('Sections', []))
            })

        return results


# Global search indexes cache
search_indexes = {}

def get_course_search_index(semester: str, course_data: Dict) -> CourseSearchIndex:
    """Get or create a search index for the given semester"""
    if semester not in search_indexes:
        search_indexes[semester] = CourseSearchIndex(course_data)
    return search_indexes[semester]
