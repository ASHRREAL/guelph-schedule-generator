def filterByEarliestAtSchool(schedule, startTime):
    # If the user does not want to filter by this
    if startTime == 0:
        return schedule

    dateToIndexMap = {"M": 0, "T": 1, "W": 2, "Th": 3, "F": 4, "Sa": 5}

    validCombinations = []

    # Locate One Of The Possible Options
    for possibleCombination in schedule:
        week = [[], [], [], [], [], []]  # Create an empty list for each day (M-S)

        for course in possibleCombination:
            for schedule_item in [course.lecture, course.seminar, course.lab]:
                if schedule_item is not None:
                    for day in schedule_item.days:
                        week[dateToIndexMap[day]].append((schedule_item.start, schedule_item.finish))

        isValid = True
        for w in range(len(week)):
            # sort low to high based on the start times
            week[w] = sorted(week[w], key=lambda x: x[0])

            if week[w] and week[w][0][0] < startTime:
                isValid = False
                break

        if isValid:
            validCombinations.append(possibleCombination)

    # print(f"After: {len(validCombinations)} Before: {len(schedule)}")

    return validCombinations


def filterByLatestAtSchool(schedule, endTime):
    # If the user does not want to filter by this
    if endTime == 0:
        return schedule

    dateToIndexMap = {"M": 0, "T": 1, "W": 2, "Th": 3, "F": 4, "Sa": 5}

    # Use tiered filtering approach: prioritize combinations that fit within constraints,
    # but don't completely eliminate options if user is too restrictive
    perfect_combinations = []  # Combinations that fit exactly within time constraints
    acceptable_combinations = []  # Combinations that fit within a small buffer
    fallback_combinations = []  # Combinations that fit within a larger buffer

    # Debug: Track what's being filtered out
    filtered_out_count = 0
    sample_violations = []

    # Locate One Of The Possible Options
    for possibleCombination in schedule:
        week = [[], [], [], [], [], []]  # Create an empty list for each day (M-S)

        for course in possibleCombination:
            for schedule_item in [course.lecture, course.seminar, course.lab]:
                if schedule_item is not None:
                    for day in schedule_item.days:
                        week[dateToIndexMap[day]].append((schedule_item.start, schedule_item.finish))

        # Find the latest end time for this combination
        latest_end_time = 0
        for w in range(len(week)):
            week[w] = sorted(week[w], key=lambda x: x[0])
            if week[w]:
                latest_end_time = max(latest_end_time, week[w][-1][-1])

        # Categorize combinations based on how well they fit time constraints
        if latest_end_time <= endTime:
            # Perfect fit - ends exactly on time or earlier
            perfect_combinations.append(possibleCombination)
        elif latest_end_time <= endTime + 30:
            # Acceptable - ends within 30 minutes of preferred time
            acceptable_combinations.append(possibleCombination)
        elif latest_end_time <= endTime + 60:
            # Fallback - ends within 60 minutes of preferred time
            fallback_combinations.append(possibleCombination)
        else:
            # Too late - track for debugging
            filtered_out_count += 1
            if len(sample_violations) < 5:
                sample_violations.append({
                    'latest_end': latest_end_time,
                    'limit': endTime,
                    'latest_end_hours': f"{latest_end_time // 60}:{latest_end_time % 60:02d}",
                    'limit_hours': f"{endTime // 60}:{endTime % 60:02d}"
                })

    # Return combinations in order of preference: perfect first, then acceptable, then fallback
    if perfect_combinations:
        validCombinations = perfect_combinations
        print(f"Latest time filter: Found {len(perfect_combinations)} combinations ending by {endTime // 60}:{endTime % 60:02d}")
    elif acceptable_combinations:
        validCombinations = acceptable_combinations
        print(f"Latest time filter: Found {len(acceptable_combinations)} combinations ending within 30 min of {endTime // 60}:{endTime % 60:02d}")
    elif fallback_combinations:
        validCombinations = fallback_combinations
        print(f"Latest time filter: Found {len(fallback_combinations)} combinations ending within 60 min of {endTime // 60}:{endTime % 60:02d}")
    else:
        # If nothing fits even with 60-minute buffer, return a subset of original combinations
        # This prevents the system from returning zero results
        validCombinations = schedule[:min(1000, len(schedule))]
        print(f"Latest time filter: Time constraints too strict, showing best {len(validCombinations)} combinations")

    # Debug output for rejected combinations
    if filtered_out_count > 0:
        print(f"Latest time filter removed {filtered_out_count} combinations that end too late")
        if sample_violations:
            print("Sample violations (past 60-minute buffer):")
            for violation in sample_violations:
                print(f"  - Class ends at {violation['latest_end_hours']}, limit is {endTime // 60}:{endTime % 60:02d}")

    return validCombinations


def filterBySpecificDayOff(schedule, daysOff):
    pass


def filterByAmountOfDaysOff(schedule, numberOfDaysOff):
    pass


def filterByTotalMinTimeBetweenClasses(schedule):
    """Optimized gap calculation with caching"""
    if not schedule:
        return schedule, [], []
    
    dateToIndexMap = {"M": 0, "T": 1, "W": 2, "Th": 3, "F": 4, "Sa": 5}
    times = []
    
    print(f"Calculating gaps for {len(schedule)} combinations...")

    # Process in batches for progress indication
    batch_size = 1000
    for batch_start in range(0, len(schedule), batch_size):
        batch_end = min(batch_start + batch_size, len(schedule))
        
        for i in range(batch_start, batch_end):
            possibleCombination = schedule[i]
            week = [[] for _ in range(6)]  # M-Sa
            
            # Build schedule for this combination
            for course in possibleCombination:
                for schedule_item in [course.lecture, course.seminar, course.lab]:
                    if schedule_item is not None:
                        for day in schedule_item.days:
                            day_idx = dateToIndexMap[day]
                            week[day_idx].append((schedule_item.start, schedule_item.finish))
            
            # Calculate total gap time
            total_gap = 0
            for day_schedule in week:
                if len(day_schedule) > 1:
                    day_schedule.sort(key=lambda x: x[0])  # Sort by start time
                    for j in range(1, len(day_schedule)):
                        gap = day_schedule[j][0] - day_schedule[j-1][1]
                        total_gap += max(0, gap)  # Only count positive gaps
            
            times.append(total_gap)
        
        # Progress indicator
        if batch_end % 5000 == 0 or batch_end == len(schedule):
            print(f"Processed {batch_end}/{len(schedule)} combinations...")

    # Sort indices by gap time (minimal gaps first)
    sortedTimeIndices = sorted(range(len(times)), key=times.__getitem__)
    
    return schedule, sortedTimeIndices, times


def filterByAvgStartTime(schedule, sortByLatest=False):
    dateToIndexMap = {"M": 0, "T": 1, "W": 2, "Th": 3, "F": 4, "Sa": 5}

    times = []

    # Locate One Of The Possible Options
    for possibleCombination in schedule:
        week = [[], [], [], [], [], []]  # Create an empty list for each day (M-S)

        for course in possibleCombination:
            for schedule_item in [course.lecture, course.seminar, course.lab]:
                if schedule_item is not None:
                    for day in schedule_item.days:
                        week[dateToIndexMap[day]].append((schedule_item.start, schedule_item.finish))

        t = 0
        daysOnCampus = 0

        for w in range(len(week)):
            # sort low to high based on the start times
            week[w] = sorted(week[w], key=lambda x: x[0])

            if week[w]:
                daysOnCampus += 1
                t += week[w][0][0]

        times.append(t / daysOnCampus)

    # Yoinked from https://stackoverflow.com/a/6423325/11521629
    # Better than using np since there is no dependency

    sortedTimeIndices = sorted(range(len(times)), key=times.__getitem__)

    # reverse to show the latest classes
    if sortByLatest:
        sortedTimeIndices.reverse()

    # print(f"After: {len(validCombinations)} Before: {len(schedule)}")

    return schedule, sortedTimeIndices, times
