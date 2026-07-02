# Overtime Interpretation

## Trigger Summary

Ordinary Hours are defined as:

- 38 Hours per week, which can be averaged over 1,2,3 or 4 weeks (22.1)
- Up to 20 days worked in a 28 day work cycle or (22.1a)
- Up to 19 days worked, with one day as ADO in a 28 day work cycle (22.1b)
- Eight hours on a day shift or 10 hours on a night shift.  (22.1c)
- For Day workers only, hours worked between 6AM to 6PM Monday to Friday (22.2a)
- For Shiftworkers, Ordinary hours may be worked outside 6AM to 6PM Monday to Friday (22.2b)
- Hours which are displayed on a roster (22.6a)

### Overtime Rules:

- Overtime is payable where an employee is required to be on duty during a meal break, until the meal break is taken  (24.1b)
- An employee recalled to work for overtime, will be entitled to receive a minimum of four hours worked ( 25.1e)
- For full time employees, any hours worked during a sleepover will be paid at overtime rates (22.9gi)

### Additional Guidelines  (supplied by the user)

Any hours which are not ordinary hours, are to be considered overtime

# Overtime Interpretation

## Clause Applicability Matrix

| Trigger | FT | PT | Casual | Day Worker | Shiftworker |
|----------|----|----|---------|------------|-------------|
| Weekly hours exceeded | ✓ | ✓ | ✓ | ✓ | ✓ |
| Daily hours exceeded | ✓ | ✓ | ✓ | ✓ | ✓ |
| Outside ordinary spread | ✓ | ✓ | ✓ | ✓ | ✗ |
| Outside rostered hours | ✓ | ✓ | ✗ | ✓ | ✓ |
| Missed meal break | ✓ | ✓ | ✓ | ✓ | ✓ |
| Recall to work | ✓ | ✓ | ✓ | ✓ | ✓ |

## When does overtime occur?

T*his is when an employee is entitled to receive overtime  - when does overtime trigger*

- For all employees, Any hours worked in excess of 76 hours in a pay period (22.1 - assuming that employees work a standard 14 day work week)
- For all employees, any days worked in excess of 20 days in a 28 day work cycle (22.1a), or where in excess of 19 hours in a 28 day work cycle are worked, with 1 day being an ADO (22.1b)
- For all permanent employees, working a day shift, any hours worked in excess of 8 on a day (22.1c)
- For all permanent employees, working a night shift, any hours worked in excess of 10 hours in a day (22.1c)
- For any casual employees, any hours in excess of 10 in a day (25.1.c)
- For day workers (not shift workers), any hours worked outside 6AM to 6PM, or on the weekend (22.2)
- For permanent (Full Time & Part Time) employees, hours work outside the specified roster (22.6a)
- For all employees, any hours worked beyond 5 hours, where employees are unable to take their break due to having to work (24.1b)
- For all employees, any hours (with a mininum of four) where the employee is recalled to work (25.1e)

Any hours which are not overtime, are to be considered as ordinary hours, with the following minimum hours:

- For Full Time employees, a minimum of four hours (22.7a)
- For Part Time and casual employees, a minimum of two hours (22.7b)

## What happens when overtime occurs?

*Once an employee has determined to recieve overtime, this is what happens* 

- For Full Time & Part Time employees,  the first two hours on Monday to Friday is paid at 150% , any subsequent hours are paid at 200% (25.1aiA, 25.1biA)
- For Part Time employees working in excess of 10 hours a day on a Saturday  the first two hours is paid at 150% , any subsequent hours are paid at 200% (25.1aiA, 25.1biA)
- For Full Time & Part time employees (except for working in excess of 10 hours), any overtime on a Saturday or Sunday is paid at 200% (25.1a1B, 25.1biB)
- For Full Time & Part time employees, any overtime on public holidays is paid at 250% (25aiC, 25biC)
- For casual employees working in excess of 10 hours in a day, overtime on Monday to Saturday is paid at 187.5% of the hourly rate for the first two hours, then 250% for subsequent hours. (25.1ci)
- For casual employees working in excess of 10 hours in a day,  overtime on Sunday is paid at 250% of the hourly rate (25.1ci)
- For casual employees working in excess of 10 hours in a day,  overtime on Sunday a public holiday is paid at 312.5% of the hourly rate. (25.1ci)
- For casual employees receiving overtime for other reasons, overtime on Monday to Friday is paid at 187.5% of the hourly rate for the first two hours, then 250% for subsequent hours. (25.1ci)
- For casual employees receiving overtime for other reasons, overtime on Saturday or Sunday is paid at 250% of the hourly rate (25.1cii)
- For casual employees receiving overtime for other reasons,  overtime on a public holiday is paid at 312.5% of the hourly rate. (25.1cii)

## Additional Consequences

- Any Full Time or Part time employees who works overtime without 10 consecutive hours break will be paid 200% until they have had a 10 hour break (25.1(d) )
- Any employee who works beyond one hour or their shift, or works one hour overtime will be supplied with a meal allowance of $16.62, and an additional $14.98 where the overtime exceeds for hours (15.4).  THis is not applicable where the employee is supplied with a meal, or could return home for a meal
- Employees may elect to take   Time off instead of payment for overtime (25.2)

## Edge Cases and Implementation Issues

### Additional Considerations:

Part time employees may agree not to receive overtime for working outside the specified roster time (25.1(b)iii)

## Required Data

Required for initial calculation: *These are the fields that will be used in the initial calculation* 

- Hours worked for each employee, including start and finish time
- Employee Type  - is the employee Full Time, Part time, or Casual
- Employee type  - is the employee a shift worker, or a day worker

Required for subsequent calculation: *These are fields that can be included in subsequent calcuations*  

- Rostered time for each employee, including start and finish time
- Break Rules - have employees work in excess of five hours
- is the shift a sleepover shift
- Is the shift a recall shift?

## Assumptions and Exclusions

### Required Business Assumptions & Initial Ruleset

Implemented Assumptions: *These assumptions are implemented in the current calculation* 

- Are weekly hours averaged over 1,2,3,or 4 weeks - Assumed to be two weeks
- What is considered a night shift (assumed to be any shifts worked past 6pm)
- No employees agree to talk time off, rather than overtime

Scenarios Excluded: *These are scenarios which are assumed not to occur* 

- Do employees receive an ADO (assumed to be no)
- Do employees work outside rostered time (assumed to be no)
- Do part time employees agree to work outside rostered time (assumed to be no)
- Do employees ever miss their break  (assumed to be no)
- Are employees working sleepovers (assumed to be no)
- Are employees recalled to work (assumed to be no)