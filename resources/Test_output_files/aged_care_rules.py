"""
Rule engine for Aged Care award pay calculations.

This module contains business rules and constants used in Aged Care award pay calculations.
"""

class AgedCareRules:
    """
    Business rules for Aged Care award pay calculations.
    """
    
    # Time rules for shift workers
    ORDINARY_HOURS_LIMIT_DAILY = 10  # Increased to 12 hours per day
    ORDINARY_HOURS_LIMIT_WEEKLY = 38  # Increased to 40 hours per week
    DEFAULT_BREAK = 1

    # Time rules for day workers
    DAY_WORKER_ORDINARY_HOURS_DAILY = 8 
    DAY_WORKER_ORDINARY_HOURS_WEEKLY = 38  # Increased to 40 hours per week
    
    # Part time overtime rules
    USE_CONTRACTED_HOURS_FOR_PT_OVERTIME = False  # If True, part-time employees get overtime after contracted hours
    
    # Contracted hours top-up rules
    PT_EMPLOYEES_ENTITLED_TO_CONTRACTED_TOPUP = True  # If True, part-time employees get top-up to contracted hours
    FT_EMPLOYEES_ENTITLED_TO_CONTRACTED_TOPUP = True  # If True, full-time employees get top-up to contracted hours
    
    # Rate multipliers
    STANDARD_OVERTIME_RATE = 1.5
    EXTENDED_OVERTIME_RATE = 2.0  # Used for extended overtime (keeping consistent with structure)
    SUNDAY_OVERTIME_RATE = 2.0  # Increased to 2.5x for weekends
    SATURDAY_OVERTIME_RATE = 2.0  # Increased to 2.5x for weekends
    EXTENDED_OVERTIME_DAYS = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday']
    SATURDAY_PENALTY_RATE = 0.25
    SUNDAY_PENALTY_RATE = 0.50
    
    # Span overtime settings
    APPLY_SPAN_OVERTIME = True  # Using span overtime for Aged Care
    SPAN_OVERTIME_HOUR = 18  # 6pm in 24-hour format
    
    # Gap penalty rule - specific to Aged Care award
    GAP_PENALTY_HOURS = 10  # Minimum hours required between shifts to avoid gap penalty
    GAP_PENALTY_RATE = 1.0  # 100% penalty rate when shifts are too close together
    
    # Unified penalties structure
    # Type can be "shift_based" (applies to entire shift based on start time) or "time_based" (applies to specific hours)
    PENALTIES = {
        'afternoon_shift_10': {
            'type': 'shift_based',
            'basis': 'start_time',  # Penalty applies based on shift start time
            'start': 10,   # 10am
            'end': 13,     # 1pm
            'rate': 0.10,  # 10% penalty
            'description': 'Morning Shift Penalty (10%)',
            'applies_to': ['shift']  # Only applies to shift workers
        },
        'afternoon_shift': {
            'type': 'shift_based',
            'basis': 'start_time',  # Penalty applies based on shift start time
            'start': 13,   # 1pm
            'end': 16,     # 4pm
            'rate': 0.125, # 12.5% penalty
            'description': 'Afternoon Shift Penalty (12.5%)',
            'applies_to': ['shift']  # Only applies to shift workers
        },
        'evening_shift': {
            'type': 'shift_based',
            'basis': 'start_time',  # Penalty applies based on shift start time
            'start': 16,   # 4pm
            'end': 24,     # Midnight
            'rate': 0.15,  # 15% penalty
            'description': 'Evening Shift Penalty (15%)',
            'applies_to': ['shift']  # Only applies to shift workers
        },
            'evening_shift_cont': {
            'type': 'shift_based',
            'basis': 'start_time',  # Penalty applies based on shift start time
            'start': 24,   # 4pm
            'end': 4,     # Midnight
            'rate': 0.15,  # 15% penalty
            'description': 'Evening Shift Penalty (15%)',
            'applies_to': ['shift']  # Only applies to shift workers
        },
                    'evening_shift_am': {
            'type': 'shift_based',
            'basis': 'start_time',  # Penalty applies based on shift start time
            'start': 4,   # 4pm
            'end': 6,     # Midnight
            'rate': 0.1,  # 15% penalty
            'description': 'Evening Shift Penalty (15%)',
            'applies_to': ['shift']  # Only applies to shift workers
        }
    }
    
    
    # Weekend rules by worker type
    WEEKEND_RULES = {
        'day': {
            'Saturday': {'is_overtime': True, 'rate': 2},  # All hours are overtime at 2.5x
            'Sunday': {'is_overtime': True, 'rate': 2}     # All hours are overtime at 2.5x
        },
        'shift': {
            'Saturday': {'penalty_rate': 0.5},  # Penalty rate for non-overtime hours
            'Sunday': {'penalty_rate': 0.75}     # Penalty rate for non-overtime hours
        }
    }
    
    # Two-tier overtime structure (not used in Aged Care)
    TWO_TIER_OVERTIME = False
    TWO_TIER_OVERTIME_THRESHOLD = 0  # Not applicable
