# Overtime pseudocode

## Derived Fields

- `Worked_Hour_Units`
  - Split each shift into non-overlapping hour units using `Shift_Start` and `Shift_End`.
  - Preserve the calendar date and applicable day/week/fortnight/roster-cycle record for each hour unit.
  - If a shift crosses midnight, assign each hour unit to the calendar date on which it occurs.

- `Unallocated_Hours`
  - Initialise to all `Worked_Hour_Units`.
  - Reduce whenever an hour unit is assigned to `Overtime_Hours`.
  - An hour unit must not be assigned to overtime more than once.

- `Ordinary_Hours`
  - Set to the remaining `Unallocated_Hours` after all overtime rules have been applied.

- `Employee_Cohort`
  - Derive from:
    - `Employee Type - Full Time/PartTime/Casual`
    - `Shift_Worker_Status`
  - Classify an employee as a `Day_Worker` where `Shift_Worker_Status` indicates the employee is not a shift worker.

- `Daily_Worked_Hours`
  - Total worked hours for the relevant calendar date, including qualifying sleepover hours where required.

- `Weekly_Worked_Hours`
  - Total worked hours in the relevant week, including qualifying sleepover hours where required.

- `Fortnightly_Worked_Hours`
  - Total worked hours in the relevant fortnight, including qualifying sleepover hours where required.

- `Daily_Rostered_Ordinary_Hours`
  - Hours between `Roster_Start` and `Roster_End` for the relevant shift or work period.

- `Outside_Day_Worker_Span`
  - `TRUE` where an hour occurs:
    - before `06:00`; or
    - after `18:00`; or
    - on Saturday or Sunday,
  - and the employee is a `Day_Worker`.

- `Daily_Ordinary_Hours_Limit`
  - `8` hours where the shift is classified as a day shift.
  - `10` hours where the shift is classified as a night shift.

- `Ordinary_Hours_Model_Boundary`
  - The selected applicable boundary:
    - `38` hours per week; or
    - `76` hours per fortnight; or
    - `114` hours over 21 days; or
    - `152` hours over four weeks.

- `Roster_Cycle_Work_Day_Count`
  - Number of work days in the applicable 28-calendar-day roster cycle.

- `Outside_Ordinary_Hours_Boundary`
  - `TRUE` for hours exceeding the selected weekly, fortnightly, 21-day, four-week, roster-cycle, daily, or day-worker span boundary.
  - This field is a boundary indicator only and does not independently classify hours as overtime.

## Required additional inputs

- `Applicable_Ordinary_Hours_Model`
  - The selected ordinary-hours model for the employee or work arrangement.

- `Authorised_Work_Indicator`
  - Whether work was authorised for the full-time overtime rule.

- `Documented_Written_Part_Time_Variation_Indicator`
  - Whether a documented written variation exists under clause `10.3(c)`.

- `Agreed_Part_Time_Rostered_Hours`
  - The employee’s agreed rostered hours for each relevant day.

- `Shift_Type`
  - Whether each shift is a day shift or night shift for the 8-hour/10-hour daily boundary.

- `Roster_Cycle_Start`
  - Start date of the applicable 28-calendar-day roster cycle.

- `Roster_Cycle_Work_Day_Arrangement`
  - Whether the arrangement is:
    - no more than 20 work days; or
    - no more than 19 work days with the twentieth day as an accrued paid day off.

- `Qualifying_Sleepover_Indicator`
  - Whether the work period is an overnight required sleepover involving sleeping in while remaining on call for emergencies.

- `Sleepover_Start` and `Sleepover_End`
  - Required to verify that the sleepover span is between 8 and 10 hours.

- `Sleepover_Immediately_Before_or_After_Shift_Indicator`
  - Whether the sleepover is rostered immediately before or after the employee’s shift.

- `Sleepover_Continuity_Permitted_Indicator`
  - Whether clause `22.9(h)` permits continuity between the sleepover and the shift.

- `Full_Time_Daily_Hours_Comparator`
  - System-recorded full-time employee hours worked on the relevant day.
  - If no full-time employee exists, use `11` hours.

- `Permanent_Part_Time_Indicator`
  - Whether the part-time employee is permanent rather than casual.

- `Full_Time_or_Permanent_Part_Time_Unavailable_Indicator`
  - Whether full-time and permanent part-time employees were unavailable for the casual sleepover.

- `Casual_Exclusively_or_Almost_Exclusively_Sleepovers_Indicator`
  - Whether the casual employee is used exclusively or almost exclusively for sleepovers.

- `Broken_Shift_Agreement_Indicator`
  - Whether the broken shift was mutually agreed.

- `Non_Meal_Break_Hours`
  - Total non-meal break time in the broken shift.

- `Broken_Shift_Portion_Minimum_Engagement_Compliant_Indicator`
  - Whether each broken-shift portion satisfies the applicable minimum-engagement requirement.

- `Broken_Shift_Span_Hours`
  - Total span from the start of the first portion to the end of the last portion.

## Rule priority

Process rules in this order:

1. Qualifying sleepover rules.
2. Broken-shift validation and the 12-hour broken-shift boundary.
3. Day-worker span and shift-worker status.
4. Daily ordinary-hours boundaries.
5. Full-time daily authorised work outside rostered ordinary hours.
6. Part-time daily thresholds and agreed-rostered-hours threshold.
7. Casual daily threshold.
8. Part-time and casual weekly and fortnightly thresholds.
9. Selected ordinary-hours model and roster-cycle boundaries as boundary controls.
10. Assign all remaining `Unallocated_Hours` to `Ordinary_Hours`.

Where multiple rules identify the same worked hour:

- Assign the hour to `Overtime_Hours` once.
- Remove it from `Unallocated_Hours`.
- Do not create a second overtime allocation for the same hour.

## Pseudocode

- **Initialise hours**
  ```text
  Worked_Hour_Units = split each shift into non-overlapping hour units
  Unallocated_Hours = Worked_Hour_Units
  Overtime_Hours = empty
  Ordinary_Hours = empty
  ```

- **Select and record the ordinary-hours model**
  ```text
  IF Applicable_Ordinary_Hours_Model = "38 hours per week":
      Ordinary_Hours_Model_Boundary = 38 hours per week

  ELSE IF Applicable_Ordinary_Hours_Model = "76 hours per fortnight":
      Ordinary_Hours_Model_Boundary = 76 hours per fortnight

  ELSE IF Applicable_Ordinary_Hours_Model = "114 hours over 21 days":
      Ordinary_Hours_Model_Boundary = 114 hours over 21 days

  ELSE IF Applicable_Ordinary_Hours_Model = "152 hours over four weeks":
      Ordinary_Hours_Model_Boundary = 152 hours over four weeks

  ELSE:
      flag missing ordinary-hours model
  ```

  ```text
  // Clauses 22.1 and 25.1
  Calculate Outside_Ordinary_Hours_Boundary using the selected model.
  Do not classify an hour as overtime from this boundary alone.
  ```

- **Apply the 28-day roster-cycle boundary**
  ```text
  // Clauses 22.1(a) and 22.1(b)
  FOR each 28-calendar-day roster cycle:
      IF Roster_Cycle_Work_Day_Arrangement = "20 work days":
          ordinary roster-cycle arrangement = no more than 20 work days

      ELSE IF Roster_Cycle_Work_Day_Arrangement =
              "19 work days plus accrued paid day off":
          ordinary roster-cycle arrangement =
              no more than 19 work days plus twentieth day as accrued paid day off

      Mark work outside the selected arrangement as Outside_Ordinary_Hours_Boundary.
  ```

  ```text
  // Clauses 22.1(a), 22.1(b), 25.1
  Do not classify roster-cycle boundary hours as overtime unless a cohort-specific
  overtime trigger below also applies.
  ```

- **Apply the daily ordinary-hours limit**
  ```text
  // Clauses 22.1(c) and 25.1
  FOR each employee and calendar date:
      IF Shift_Type = "day shift":
          Daily_Ordinary_Hours_Limit = 8 hours
      ELSE IF Shift_Type = "night shift":
          Daily_Ordinary_Hours_Limit = 10 hours
      ELSE:
          flag missing shift type

      Mark hours after Daily_Ordinary_Hours_Limit as
      Outside_Ordinary_Hours_Boundary.
  ```

  ```text
  Do not classify hours after the daily limit as overtime from this boundary alone.
  Apply the employee’s applicable cohort-specific overtime trigger.
  ```

- **Identify day workers and shift workers**
  ```text
  // Clauses 22.2(a) and 22.2(b)
  IF Shift_Worker_Status = "shift worker":
      Employee_Cohort includes Shift_Worker
  ELSE:
      Employee_Cohort includes Day_Worker
  ```

  ```text
  // Clause 22.2(a)
  IF Employee_Cohort includes Day_Worker:
      Mark hours worked before 06:00, after 18:00, or on Saturday/Sunday as
      Outside_Day_Worker_Span.
  ```

  ```text
  // Clauses 22.2(a), 22.2(b)
  Do not use the day-worker span as a standalone overtime trigger.
  For a shift worker, do not apply a separate shift-worker span because the source
  does not specify one.
  ```

- **Full-time qualifying sleepover**
  ```text
  // Clauses 22.9, 22.9(a), 22.9(g)(i), 22.9(h)
  IF Employee Type - Full Time/PartTime/Casual = "full-time"
     AND Qualifying_Sleepover_Indicator = TRUE
     AND Sleepover_Start and Sleepover_End define an 8-to-10-hour overnight span
     AND Sleepover_Immediately_Before_or_After_Shift_Indicator = TRUE
     AND Sleepover_Continuity_Permitted_Indicator = TRUE:

      Move all qualifying sleepover hour units from Unallocated_Hours
      to Overtime_Hours.
  ```

- **Permanent part-time qualifying sleepover: daily comparator**
  ```text
  // Clause 22.9(g)(ii)
  IF Permanent_Part_Time_Indicator = TRUE
     AND Qualifying_Sleepover_Indicator = TRUE:

      Include all qualifying sleepover hours in Daily_Worked_Hours.

      IF Full_Time_Daily_Hours_Comparator exists:
          Daily_Sleepover_Comparator = Full_Time_Daily_Hours_Comparator
      ELSE:
          Daily_Sleepover_Comparator = 11 hours

      IF Daily_Worked_Hours > Daily_Sleepover_Comparator:
          Identify the portion of the relevant day's worked hours
          exceeding Daily_Sleepover_Comparator.

          Move only those identified hour units still in Unallocated_Hours
          to Overtime_Hours.
  ```

- **Permanent part-time qualifying sleepover: weekly and fortnightly thresholds**
  ```text
  // Clause 22.9(g)(ii)
  IF Permanent_Part_Time_Indicator = TRUE
     AND Qualifying_Sleepover_Indicator = TRUE:

      Include all qualifying sleepover hours in Weekly_Worked_Hours
      and Fortnightly_Worked_Hours.

      IF Weekly_Worked_Hours > 38 hours:
          Identify hours exceeding 38 hours in the relevant week.
          Move only those hour units still in Unallocated_Hours
          to Overtime_Hours.

      IF Fortnightly_Worked_Hours > 76 hours:
          Identify hours exceeding 76 hours in the relevant fortnight.
          Move only those hour units still in Unallocated_Hours
          to Overtime_Hours.
  ```

- **Casual qualifying sleepover**
  ```text
  // Clauses 22.9(g)(iii) and 22.9(k)
  IF Employee Type - Full Time/PartTime/Casual = "casual"
     AND Qualifying_Sleepover_Indicator = TRUE
     AND Full_Time_or_Permanent_Part_Time_Unavailable_Indicator = TRUE
     AND Casual_Exclusively_or_Almost_Exclusively_Sleepovers_Indicator = FALSE:

      Include all qualifying sleepover hours in Weekly_Worked_Hours
      and Fortnightly_Worked_Hours.

      IF Weekly_Worked_Hours > 38 hours:
          Identify hours exceeding 38 hours in the relevant week.
          Move only those hour units still in Unallocated_Hours
          to Overtime_Hours.

      IF Fortnightly_Worked_Hours > 76 hours:
          Identify hours exceeding 76 hours in the relevant fortnight.
          Move only those hour units still in Unallocated_Hours
          to Overtime_Hours.
  ```

  ```text
  IF Employee Type - Full Time/PartTime/Casual = "casual"
     AND Qualifying_Sleepover_Indicator = TRUE
     AND (
         Full_Time_or_Permanent_Part_Time_Unavailable_Indicator = FALSE
         OR Casual_Exclusively_or_Almost_Exclusively_Sleepovers_Indicator = TRUE
     ):
      flag sleepover as not permitted under the reviewed rule
  ```

- **Broken-shift validation**
  ```text
  // Clauses 22.8(a), 22.8(b), and 22.8(f)
  IF Employee Type - Full Time/PartTime/Casual is "casual"
     OR Employee Type - Full Time/PartTime/Casual is "part-time":

      IF Broken_Shift_Agreement_Indicator = TRUE
         AND Non_Meal_Break_Hours <= 4 hours
         AND Broken_Shift_Portion_Minimum_Engagement_Compliant_Indicator = TRUE
         AND Broken_Shift_Span_Hours <= 12 hours:

          record broken shift as valid

      ELSE:
          flag broken shift as not compliant with the reviewed conditions
  ```

- **Broken-shift span exceeding 12 hours**
  ```text
  // Clause 22.8(d)
  IF Broken_Shift_Span_Hours > 12 hours:
      mark hours beyond the 12-hour broken-shift span as
      Outside_Ordinary_Hours_Boundary

      // Clause 22.8(d) is not a standalone overtime-hours trigger.
      Do not move these hours to Overtime_Hours unless the employee's
      applicable overtime trigger below is also satisfied.
  ```

- **Full-time daily authorised work**
  ```text
  // Clause 25.1(a)(i)
  IF Employee Type - Full Time/PartTime/Casual = "full-time":

      FOR each calendar date:
          Identify authorised worked hour units performed in addition to
          the employee's rostered ordinary hours for that date.

          IF Authorised_Work_Indicator = TRUE:
              Move only those identified hour units still in Unallocated_Hours
              to Overtime_Hours.
  ```

- **Part-time weekly and fortnightly thresholds**
  ```text
  // Clause 25.1(b)(i)
  IF Employee Type - Full Time/PartTime/Casual = "part-time":

      IF Weekly_Worked_Hours > 38 hours:
          Identify hours exceeding 38 hours in the relevant week.
          Move only those hour units still in Unallocated_Hours
          to Overtime_Hours.

      IF Fortnightly_Worked_Hours > 76 hours:
          Identify hours exceeding 76 hours in the relevant fortnight.
          Move only those hour units still in Unallocated_Hours
          to Overtime_Hours.
  ```

- **Part-time daily threshold**
  ```text
  // Clause 25.1(b)(ii)
  IF Employee Type - Full Time/PartTime/Casual = "part-time":

      FOR each calendar date:
          IF Daily_Worked_Hours > 10 hours:
              Identify hours exceeding 10 hours on that date.
              Move only those hour units still in Unallocated_Hours
              to Overtime_Hours.
  ```

- **Part-time hours above agreed daily roster**
  ```text
  // Clauses 10.3(b), 10.3(c), and 25.1(b)(iii)
  IF Employee Type - Full Time/PartTime/Casual = "part-time":

      FOR each calendar date:
          Calculate hours worked above Agreed_Part_Time_Rostered_Hours.

          IF hours worked exceed agreed rostered hours
             AND Documented_Written_Part_Time_Variation_Indicator = FALSE:

              Move only the excess hour units still in Unallocated_Hours
              to Overtime_Hours.

          IF Documented_Written_Part_Time_Variation_Indicator = TRUE:
              do not create overtime under this agreed-rostered-hours rule
              for the varied hours.
  ```

  ```text
  // Clauses 10.3(b), 10.3(c), and 25.1(b)(iii)
  A roster or agreement change without documented written variation does not
  satisfy the exception.
  ```

- **Casual weekly and fortnightly thresholds**
  ```text
  // Clauses 10.4(a), 10.4(c), and 25.1(c)(i)
  IF Employee Type - Full Time/PartTime/Casual = "casual":

      IF Weekly_Worked_Hours > 38 hours:
          Identify hours exceeding 38 hours in the relevant week.
          Move only those hour units still in Unallocated_Hours
          to Overtime_Hours.

      IF Fortnightly_Worked_Hours > 76 hours:
          Identify hours exceeding 76 hours in the relevant fortnight.
          Move only those hour units still in Unallocated_Hours
          to Overtime_Hours.
  ```

- **Casual daily threshold**
  ```text
  // Clause 25.1(c)(ii)
  IF Employee Type - Full Time/PartTime/Casual = "casual":

      FOR each calendar date:
          IF Daily_Worked_Hours > 10 hours:
              Identify hours exceeding 10 hours on that date.
              Move only those hour units still in Unallocated_Hours
              to Overtime_Hours.
  ```

- **Final ordinary-hours allocation**
  ```text
  // Applies after all overtime triggers
  Ordinary_Hours = Unallocated_Hours
  Unallocated_Hours = empty
  ```

- **Output validation**
  ```text
  ASSERT every worked hour is in exactly one of:
      Overtime_Hours
      Ordinary_Hours

  ASSERT no hour unit appears more than once in Overtime_Hours
  ASSERT Unallocated_Hours is empty
  ```

## Conditions not considered by the pseudocode

- **Clause 22.1**
  - Business rule: the applicable ordinary-hours model may be 38 hours per week, 76 hours per fortnight, 114 hours over 21 days, or 152 hours over four weeks.
  - Reason not directly determined from available fields: the selected model is an employee or work-arrangement configuration not contained in the supplied fields.

- **Clauses 22.1(a) and 22.1(b)**
  - Business rule: the 28-calendar-day roster cycle may contain no more than 20 work days, or 19 work days plus an accrued paid day off on the twentieth day.
  - Reason not directly determined from available fields: the roster-cycle arrangement and accrued paid day off are not supplied.

- **Clause 25.1(a)(i)**
  - Business rule: full-time overtime requires authorised work in addition to rostered ordinary hours.
  - Reason not directly determined from available fields: authorisation is not represented by the supplied fields.

- **Clauses 10.3(b), 10.3(c), and 25.1(b)(iii)**
  - Business rule: part-time hours above agreed daily rostered hours are overtime unless a documented written variation exists.
  - Reason not directly determined from available fields: the documented written-variation status and agreed rostered hours are not fully represented by `Roster_Start` and `Roster_End`.

- **Clauses 22.9, 22.9(a), 22.9(g)(i), and 22.9(h)**
  - Business rule: a qualifying full-time sleepover must be an 8-to-10-hour overnight required sleepover, immediately before or after the shift, with continuity permitted where applicable.
  - Reason not directly determined from available fields: sleepover status, on-call emergency requirement, sleepover duration, and continuity permission are not supplied.

- **Clause 22.9(g)(ii)**
  - Business rule: permanent part-time sleepover overtime uses the full-time employee daily-hours comparator, or 11 hours if no full-time employee exists.
  - Reason not directly determined from available fields: the system-recorded full-time daily comparator and permanent part-time status are not supplied.

- **Clauses 22.9(g)(iii) and 22.9(k)**
  - Business rule: casual sleepovers are permitted only where full-time and permanent part-time employees are unavailable and not where the casual is used exclusively or almost exclusively for sleepovers.
  - Reason not directly determined from available fields: employee availability and the casual employee’s sleepover usage pattern are not supplied.

- **Clauses 22.8(a), 22.8(b), 22.8(d), and 22.8(f)**
  - Business rule: a mutually agreed broken shift requires non-meal breaks of no more than four hours, compliant minimum engagement for each portion, and a span of no more than 12 hours; work beyond 12 hours is subject to a payment consequence but is not independently an overtime trigger.
  - Reason not directly determined from available fields: broken-shift agreement, break classification, minimum-engagement compliance, and total broken-shift span are not supplied.

## Implementation notes

- The `Outside_Ordinary_Hours_Boundary` field must not independently create overtime because clauses `22.1`, `22.1(a)`, `22.1(b)`, `22.1(c)`, `22.2(a)`, and `25.1` require the applicable cohort-specific overtime trigger to be satisfied.
- `Shift_Worker_Status` should be used to identify shift workers. The source provides no separate shift-worker ordinary-hours span.
- `Public_Holiday_Indicator`, `Previous_Shift_End`, and `Shift_Day` do not create overtime under the reviewed rules and are not used as standalone triggers.
- The broken-shift rule must not classify hours beyond 12 hours as overtime solely because clause `22.8(d)` applies.
- Sleepover hours must be included in the relevant daily, weekly, and fortnightly totals before applying the sleepover-specific thresholds.
- Apply the relevant weekly and fortnightly thresholds to the same worked-hour population only once. When a daily and a weekly or fortnightly rule identifies the same hour, retain one overtime classification.
- Do not calculate overtime multipliers, double-time amounts, penalty amounts, allowances, or other payment outcomes.
