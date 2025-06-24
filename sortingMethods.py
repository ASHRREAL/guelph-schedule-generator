def filterByEarliestAtSchool(schedule, startTime):

    if startTime == 0:
        return schedule

    dateToIndexMap = {"M": 0, "T": 1, "W": 2, "Th": 3, "F": 4, "Sa": 5}
    validCombinations = []

    for possibleCombination in schedule: 
        week = [[], [], [], [], [], []]  
        isValidCombination = True 

        for course_section in possibleCombination: 

            for schedule_item in course_section.get_schedule_items(): 
                if schedule_item is not None:

                    if schedule_item.start < startTime:
                        isValidCombination = False
                        break 

                    for day in schedule_item.days:
                        if day in dateToIndexMap:
                             week[dateToIndexMap[day]].append((schedule_item.start, schedule_item.finish))
            if not isValidCombination:
                break 

        if not isValidCombination: 
            continue

        isTrulyValid = True
        for w_idx in range(len(week)):
            if week[w_idx]:
                week[w_idx] = sorted(week[w_idx], key=lambda x: x[0]) 
                if week[w_idx][0][0] < startTime:
                    isTrulyValid = False
                    break

        if isTrulyValid:
            validCombinations.append(possibleCombination)

    return validCombinations

def filterByLatestAtSchool(schedule, endTime):

    if endTime == 0:
        return schedule

    dateToIndexMap = {"M": 0, "T": 1, "W": 2, "Th": 3, "F": 4, "Sa": 5}
    validCombinations = [] 

    for possibleCombination in schedule:
        week = [[], [], [], [], [], []]
        max_end_time_for_combination = 0
        has_classes = False

        for course_section in possibleCombination:
            for schedule_item in course_section.get_schedule_items():
                if schedule_item is not None:
                    has_classes = True
                    max_end_time_for_combination = max(max_end_time_for_combination, schedule_item.finish)

                    for day in schedule_item.days:
                        if day in dateToIndexMap:
                            week[dateToIndexMap[day]].append((schedule_item.start, schedule_item.finish))

        if not has_classes: 
            validCombinations.append(possibleCombination)
            continue

        isTrulyValid = True
        for w_idx in range(len(week)):
            if week[w_idx]:
                week[w_idx] = sorted(week[w_idx], key=lambda x: x[1], reverse=True) 
                if week[w_idx][0][1] > endTime: 
                    isTrulyValid = False
                    break

        if isTrulyValid:
            validCombinations.append(possibleCombination)

    return validCombinations

def filterBySpecificDayOff(schedule, daysOff): 
    if not daysOff:
        return schedule

    validCombinations = []
    days_off_set = set(daysOff)

    for possibleCombination in schedule:
        hasClassOnDayOff = False
        for course_section in possibleCombination:
            for schedule_item in course_section.get_schedule_items():
                if schedule_item is not None:

                    if not set(schedule_item.days).isdisjoint(days_off_set):
                        hasClassOnDayOff = True
                        break 
            if hasClassOnDayOff:
                break 

        if not hasClassOnDayOff:
            validCombinations.append(possibleCombination)

    return validCombinations

def filterByAmountOfDaysOff(schedule, numberOfDaysOff):
    if numberOfDaysOff is None or numberOfDaysOff < 0: 
        return schedule

    validCombinations = []
    all_possible_week_days = {"M", "T", "W", "Th", "F"} 

    for possibleCombination in schedule:
        days_on_campus = set()
        for course_section in possibleCombination:
            for schedule_item in course_section.get_schedule_items():
                if schedule_item is not None:
                    days_on_campus.update(d for d in schedule_item.days if d in all_possible_week_days)

        actual_days_off = len(all_possible_week_days - days_on_campus)

        if actual_days_off >= numberOfDaysOff:
            validCombinations.append(possibleCombination)

    return validCombinations

def filterByTotalMinTimeBetweenClasses(schedule):
    """Calculates total gap time for each schedule combination."""
    if not schedule:
        return [], [], [] 

    dateToIndexMap = {"M": 0, "T": 1, "W": 2, "Th": 3, "F": 4, "Sa": 5}
    gap_times_list = [] 

    for i in range(len(schedule)):
        possibleCombination = schedule[i]
        week_schedule = [[] for _ in range(6)]  

        for course_section in possibleCombination:
            for schedule_item in course_section.get_schedule_items():
                if schedule_item is not None:
                    for day_char in schedule_item.days:
                        if day_char in dateToIndexMap:
                            day_idx = dateToIndexMap[day_char]
                            week_schedule[day_idx].append((schedule_item.start, schedule_item.finish))

        total_gap_for_combination = 0
        for daily_meetings in week_schedule:
            if len(daily_meetings) > 1:
                daily_meetings.sort(key=lambda x: x[0])  
                for j in range(len(daily_meetings) - 1):
                    gap = daily_meetings[j+1][0] - daily_meetings[j][1] 
                    if gap > 0: 
                        total_gap_for_combination += gap

        gap_times_list.append(total_gap_for_combination)

    sorted_indices_by_gap = sorted(range(len(gap_times_list)), key=gap_times_list.__getitem__)

    return schedule, sorted_indices_by_gap, gap_times_list

def filterByAvgStartTime(schedule, sortByLatest=False):

    if not schedule:
        return [], [], []

    dateToIndexMap = {"M": 0, "T": 1, "W": 2, "Th": 3, "F": 4, "Sa": 5}
    avg_start_times = []

    for possibleCombination in schedule:
        week_first_class_starts = [[] for _ in range(6)]

        for course_section in possibleCombination:
            for schedule_item in course_section.get_schedule_items():
                if schedule_item is not None:
                    for day_char in schedule_item.days:
                        if day_char in dateToIndexMap:

                            week_first_class_starts[dateToIndexMap[day_char]].append(schedule_item.start)

        sum_of_daily_first_starts = 0
        days_on_campus_count = 0

        for daily_starts in week_first_class_starts:
            if daily_starts: 
                days_on_campus_count += 1
                sum_of_daily_first_starts += min(daily_starts) 

        if days_on_campus_count > 0:
            avg_start_times.append(sum_of_daily_first_starts / days_on_campus_count)
        else:
            avg_start_times.append(float('inf') if not sortByLatest else float('-inf')) 

    sorted_indices = sorted(range(len(avg_start_times)), key=avg_start_times.__getitem__)

    if sortByLatest: 
        sorted_indices.reverse()

    return schedule, sorted_indices, avg_start_times