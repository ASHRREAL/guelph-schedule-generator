from typing import List, Tuple
import time


def optimized_filter_by_total_min_time_between_classes(schedules: List[Tuple]) -> Tuple[List[Tuple], List[int], List[int]]:
    """
    Optimized version of filterByTotalMinTimeBetweenClasses that processes schedules more efficiently
    """
    if not schedules:
        return schedules, [], []
    
    date_to_index_map = {"M": 0, "T": 1, "W": 2, "Th": 3, "F": 4, "Sa": 5}
    times = []

    # Process all schedules in a single pass
    for schedule in schedules:
        # Initialize week structure
        week = [[] for _ in range(6)]  # M-Sa
        
        # Collect all time blocks for the week
        for course in schedule:
            for schedule_item in [course.lecture, course.seminar, course.lab]:
                if schedule_item is not None:
                    for day in schedule_item.days:
                        day_index = date_to_index_map[day]
                        week[day_index].append((schedule_item.start, schedule_item.finish))
        
        # Calculate total gap time for this schedule
        total_gap_time = 0
        for day_schedule in week:
            if day_schedule:
                # Sort by start time
                day_schedule.sort(key=lambda x: x[0])
                
                # Calculate gaps between consecutive classes
                for i in range(1, len(day_schedule)):
                    gap = day_schedule[i][0] - day_schedule[i-1][1]
                    total_gap_time += gap
        
        times.append(total_gap_time)

    # Create sorted indices based on gap times (ascending order - less gap time is better)
    sorted_time_indices = sorted(range(len(times)), key=times.__getitem__)

    return schedules, sorted_time_indices, times


def calculate_schedule_metrics(schedule: Tuple) -> dict:
    """
    Calculate various metrics for a schedule for better sorting and display
    """
    date_to_index_map = {"M": 0, "T": 1, "W": 2, "Th": 3, "F": 4, "Sa": 5}
    
    # Initialize tracking variables
    week = [[] for _ in range(6)]
    total_credits = 0
    course_count = len(schedule)
    
    # Collect all schedule items
    for course in schedule:
        for schedule_item in [course.lecture, course.seminar, course.lab]:
            if schedule_item is not None:
                for day in schedule_item.days:
                    day_index = date_to_index_map[day]
                    week[day_index].append((schedule_item.start, schedule_item.finish))
    
    # Calculate metrics
    days_on_campus = sum(1 for day in week if day)
    total_gap_time = 0
    earliest_start = float('inf')
    latest_end = 0
    total_class_time = 0
    
    for day_schedule in week:
        if day_schedule:
            day_schedule.sort(key=lambda x: x[0])
            
            # Track earliest and latest times
            earliest_start = min(earliest_start, day_schedule[0][0])
            latest_end = max(latest_end, day_schedule[-1][1])
            
            # Calculate total class time for the day
            day_class_time = sum(end - start for start, end in day_schedule)
            total_class_time += day_class_time
            
            # Calculate gaps between classes
            for i in range(1, len(day_schedule)):
                gap = day_schedule[i][0] - day_schedule[i-1][1]
                total_gap_time += gap
    
    # Calculate average start time
    total_start_time = 0
    for day_schedule in week:
        if day_schedule:
            total_start_time += day_schedule[0][0]
    avg_start_time = total_start_time / days_on_campus if days_on_campus > 0 else 0
    
    return {
        'total_gap_time': total_gap_time,
        'days_on_campus': days_on_campus,
        'earliest_start': earliest_start if earliest_start != float('inf') else 0,
        'latest_end': latest_end,
        'total_class_time': total_class_time,
        'avg_start_time': avg_start_time,
        'course_count': course_count,
        'campus_span': latest_end - earliest_start if earliest_start != float('inf') else 0
    }


def sort_schedules_by_preference(schedules: List[Tuple], preference: str = 'minimal_gaps') -> Tuple[List[Tuple], List[int], List[float]]:
    """
    Sort schedules by different preferences
    
    Args:
        schedules: List of schedule tuples
        preference: Sorting preference ('minimal_gaps', 'fewer_days', 'early_start', 'late_start', 'compact')
    
    Returns:
        Tuple of (schedules, sorted_indices, preference_values)
    """
    if not schedules:
        return schedules, [], []
    
    print(f"Calculating metrics for {len(schedules)} schedules...")
    start_time = time.time()
    
    # Calculate metrics for all schedules
    schedule_metrics = [calculate_schedule_metrics(schedule) for schedule in schedules]
    
    # Extract values based on preference
    if preference == 'minimal_gaps':
        values = [metrics['total_gap_time'] for metrics in schedule_metrics]
        reverse = False  # Lower gap time is better
    elif preference == 'fewer_days':
        values = [metrics['days_on_campus'] for metrics in schedule_metrics]
        reverse = False  # Fewer days is better
    elif preference == 'early_start':
        values = [metrics['avg_start_time'] for metrics in schedule_metrics]
        reverse = False  # Earlier start is better
    elif preference == 'late_start':
        values = [metrics['avg_start_time'] for metrics in schedule_metrics]
        reverse = True   # Later start is better
    elif preference == 'compact':
        values = [metrics['campus_span'] for metrics in schedule_metrics]
        reverse = False  # Shorter span is better
    else:
        # Default to minimal gaps
        values = [metrics['total_gap_time'] for metrics in schedule_metrics]
        reverse = False
    
    # Create sorted indices
    sorted_indices = sorted(range(len(values)), key=values.__getitem__, reverse=reverse)
    
    end_time = time.time()
    print(f"Metrics calculation completed in {end_time - start_time:.2f} seconds")
    
    return schedules, sorted_indices, values


def batch_process_combinations(schedules: List[Tuple], batch_size: int = 1000) -> Tuple[List[Tuple], List[int], List[int]]:
    """
    Process large numbers of schedules in batches to improve memory efficiency
    """
    if len(schedules) <= batch_size:
        return optimized_filter_by_total_min_time_between_classes(schedules)
    
    print(f"Processing {len(schedules)} schedules in batches of {batch_size}...")
    
    all_times = []
    batch_count = (len(schedules) + batch_size - 1) // batch_size
    
    for i in range(0, len(schedules), batch_size):
        batch = schedules[i:i + batch_size]
        print(f"Processing batch {i // batch_size + 1}/{batch_count}")
        
        _, _, times = optimized_filter_by_total_min_time_between_classes(batch)
        all_times.extend(times)
    
    # Create sorted indices for all schedules
    sorted_indices = sorted(range(len(all_times)), key=all_times.__getitem__)
    
    return schedules, sorted_indices, all_times
