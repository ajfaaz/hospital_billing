def performance_grade(compliance, escalations):
    """
    Returns a grade (A, B, C, D) based on SLA compliance % and number of escalations.
    """
    if compliance >= 90 and escalations == 0:
        return "A"
    elif compliance >= 80:
        return "B"
    elif compliance >= 70:
        return "C"
    else:
        return "D"