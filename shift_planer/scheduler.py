# shift_planer/scheduler.py

import datetime
import calendar
import random
from django.db import transaction
from django.db.models import Q
from shift_planer.models import ShiftAssignment, Employee, Ward, Shift, EmployeeAvailability, Absence, Qualification, ProfessionalProfile

class ShiftScheduler:
    def __init__(self, min_rest_hours, max_consecutive_shifts):
        self.MIN_REST_HOURS_BETWEEN_SHIFTS = float(min_rest_hours)
        self.MAX_CONSECUTIVE_SHIFTS = int(max_consecutive_shifts)
        # Dictionary to store logs/messages from the scheduling process
        self.log_messages = []

    def _log(self, message, level="INFO"):
        """Internal logging helper."""
        self.log_messages.append(f"[{level}] {message}")

    def get_logs(self):
        """Returns all collected log messages."""
        return self.log_messages

    def generate_schedule(self, year, month, ward_slug, overwrite=False):
        self.log_messages = [] # Reset logs for each run
        self._log(f"Starting schedule generation for {calendar.month_name[month]} {year} on Ward: {ward_slug}")

        try:
            ward = Ward.objects.get(slug=ward_slug)
        except Ward.DoesNotExist:
            self._log(f'Ward with slug "{ward_slug}" does not exist.', "ERROR")
            return {"success": False, "message": f'Station "{ward_slug}" existiert nicht.'}

        start_date = datetime.date(year, month, 1)
        end_date = datetime.date(year, month, calendar.monthrange(year, month)[1])

        # Check for existing assignments and handle overwrite
        existing_assignments_in_period = ShiftAssignment.objects.filter(
            ward=ward,
            date__gte=start_date,
            date__lte=end_date
        )

        if existing_assignments_in_period.exists():
            if overwrite:
                self._log(f"Overwriting {existing_assignments_in_period.count()} existing assignments for {ward.name} in {calendar.month_name[month]} {year}.", "WARNING")
                existing_assignments_in_period.delete()
            else:
                self._log(
                    f"Existing assignments found for {ward.name} in {calendar.month_name[month]} {year}. "
                    "Cannot generate schedule without --overwrite. Aborting.", "ERROR"
                )
                return {"success": False, "message": f"Bestehender Dienstplan für {calendar.month_name[month]} {year} auf {ward.name} gefunden. Bitte überschreiben Sie ihn oder wählen Sie einen anderen Monat/Station."}
        
        all_employees = Employee.objects.prefetch_related('qualifications', 'allowed_shifts', 'professional_profile').all()
        all_shifts = Shift.objects.all().order_by('start_time')
        
        critical_qual_ids = set(Qualification.objects.filter(is_critical=True).values_list('id', flat=True))

        generated_assignments_list = []
        
        employee_daily_assignments = {emp.id: {} for emp in all_employees}
        employee_monthly_shift_count = {emp.id: 0 for emp in all_employees}
        employee_consecutive_shifts = {emp.id: 0 for emp in all_employees}

        for day_num in range(1, end_date.day + 1):
            current_date = datetime.date(year, month, day_num)
            self._log(f"  Processing {current_date.strftime('%Y-%m-%d')}...")

            # Reset consecutive shifts if the previous day was not worked
            if day_num > 1:
                previous_date = current_date - datetime.timedelta(days=1)
                for emp in all_employees:
                    # Check if the employee was NOT assigned any shift on the previous day
                    # by querying the DB for actual assignments
                    was_assigned_prev_day = ShiftAssignment.objects.filter(
                        employee=emp, 
                        date=previous_date
                    ).exists()
                    if not was_assigned_prev_day:
                        employee_consecutive_shifts[emp.id] = 0 # Reset consecutive count

            absent_employees_ids = set(Absence.objects.filter(
                employee__in=all_employees,
                start_date__lte=current_date,
                end_date__gte=current_date,
                approved=True
            ).values_list('employee__id', flat=True))

            unavailable_employees_ids = set(EmployeeAvailability.objects.filter(
                employee__in=all_employees,
                date=current_date,
                is_available=False
            ).values_list('employee__id', flat=True))

            blocked_employees_ids = absent_employees_ids.union(unavailable_employees_ids)

            for shift in all_shifts:
                assigned_to_this_shift_today = []
                
                min_staff_for_shift_type = 0
                if shift.name == 'EARLY':
                    min_staff_for_shift_type = ward.min_staff_early_shift
                elif shift.name == 'LATE':
                    min_staff_for_shift_type = ward.min_staff_late_shift
                elif shift.name == 'NIGHT':
                    min_staff_for_shift_type = ward.min_staff_night_shift
                
                required_professionals_for_patients = 0
                if ward.current_patients > 0:
                    required_professionals_for_patients = (ward.current_patients + 2) // 3

                target_counting_staff = max(required_professionals_for_patients, min_staff_for_shift_type)
                
                current_counting_staff = 0
                critical_qual_assigned_to_shift = False
                
                shift_requires_critical_qual = shift.required_qualifications.filter(is_critical=True).exists()

                eligible_employees_for_shift = []
                for emp in all_employees:
                    if emp.id in blocked_employees_ids or shift not in emp.allowed_shifts.all():
                        continue

                    is_overlapping_with_other_shift_today = False
                    if current_date in employee_daily_assignments[emp.id]:
                        for existing_assignment_obj in employee_daily_assignments[emp.id][current_date].values():
                            current_shift_start_dt = datetime.datetime.combine(current_date, shift.start_time)
                            current_shift_end_dt = datetime.datetime.combine(current_date, shift.end_time)
                            if shift.end_time < shift.start_time:
                                current_shift_end_dt += datetime.timedelta(days=1)

                            existing_shift_start_dt = datetime.datetime.combine(existing_assignment_obj.date, existing_assignment_obj.shift.start_time)
                            existing_shift_end_dt = datetime.datetime.combine(existing_assignment_obj.date, existing_assignment_obj.shift.end_time)
                            if existing_assignment_obj.shift.end_time < existing_assignment_obj.shift.start_time:
                                existing_shift_end_dt += datetime.timedelta(days=1)

                            if (current_shift_start_dt < existing_shift_end_dt and 
                                existing_shift_start_dt < current_shift_end_dt):
                                is_overlapping_with_other_shift_today = True
                                break
                    if is_overlapping_with_other_shift_today:
                        self._log(f"    Skipping {emp.first_name} {emp.last_name} for {shift.name} on {current_date}: Overlaps with another shift today.", "WARNING")
                        continue

                    # Check minimum rest hours
                    last_assignment_query = ShiftAssignment.objects.filter(employee=emp, date__lt=current_date).order_by('-date', '-shift__end_time').first()
                    # Also check assignments already made *today* if they end before this shift starts (edge case for planning multiple shifts on one day)
                    if current_date in employee_daily_assignments[emp.id]:
                        for ass_on_day in employee_daily_assignments[emp.id][current_date].values():
                            # If this existing assignment on the same day ends *before* the current shift starts
                            if ass_on_day.shift.end_time < shift.start_time:
                                if last_assignment_query is None or ass_on_day.shift.end_time > last_assignment_query.shift.end_time: # Only if it's the latest ending shift
                                    last_assignment_query = ass_on_day

                    if last_assignment_query:
                        prev_end_dt = datetime.datetime.combine(last_assignment_query.date, last_assignment_query.shift.end_time)
                        if last_assignment_query.shift.end_time < last_assignment_query.shift.start_time:
                            prev_end_dt += datetime.timedelta(days=1)
                        
                        current_start_dt = datetime.datetime.combine(current_date, shift.start_time)
                        
                        rest_hours = (current_start_dt - prev_end_dt).total_seconds() / 3600
                        
                        if rest_hours < self.MIN_REST_HOURS_BETWEEN_SHIFTS:
                            self._log(f"    Skipping {emp.first_name} {emp.last_name} for {shift.name} on {current_date}: Not enough rest ({rest_hours:.1f}h).", "WARNING")
                            continue
                        
                        # Update consecutive count based on actual last shift and rest
                        if (current_date - last_assignment_query.date).days == 1 and rest_hours >= self.MIN_REST_HOURS_BETWEEN_SHIFTS:
                            employee_consecutive_shifts[emp.id] += 1
                        else:
                            employee_consecutive_shifts[emp.id] = 1
                    else:
                        employee_consecutive_shifts[emp.id] = 1

                    if employee_consecutive_shifts[emp.id] > self.MAX_CONSECUTIVE_SHIFTS:
                        self._log(f"    Skipping {emp.first_name} {emp.last_name} for {shift.name} on {current_date}: Max consecutive shifts reached ({self.MAX_CONSECUTIVE_SHIFTS}). Current: {employee_consecutive_shifts[emp.id]}", "WARNING")
                        continue

                    eligible_employees_for_shift.append(emp)

                eligible_employees_for_shift.sort(key=lambda emp: employee_monthly_shift_count[emp.id])
                random.shuffle(eligible_employees_for_shift)


                # --- Assignment Strategy ---
                if shift_requires_critical_qual and ward.current_patients > 0:
                    for emp in eligible_employees_for_shift:
                        emp_has_critical_qual = any(q_id in critical_qual_ids for q_id in emp.qualifications.values_list('id', flat=True))
                        
                        if emp_has_critical_qual:
                            if emp not in assigned_to_this_shift_today and not critical_qual_assigned_to_shift:
                                new_assignment = ShiftAssignment(employee=emp, shift=shift, ward=ward, date=current_date, status='PLANNED')
                                generated_assignments_list.append(new_assignment)
                                assigned_to_this_shift_today.append(emp)
                                
                                if current_date not in employee_daily_assignments[emp.id]:
                                    employee_daily_assignments[emp.id][current_date] = {}
                                employee_daily_assignments[emp.id][current_date][shift.id] = new_assignment

                                employee_monthly_shift_count[emp.id] += 1
                                critical_qual_assigned_to_shift = True
                                self._log(f"    Assigned {emp.first_name} {emp.last_name} (Critical) to {shift.name} on {current_date}.", "INFO")
                                break
                    if not critical_qual_assigned_to_shift and ward.current_patients > 0:
                        self._log(f"    WARNING: Critical qual missing for {shift.name} on {current_date} for Ward {ward.name}.", "WARNING")


                # Assign professional staff (counting towards ratio)
                remaining_eligible_professionals = [
                    emp for emp in eligible_employees_for_shift
                    if emp not in assigned_to_this_shift_today and \
                       emp.professional_profile and emp.professional_profile.counts_towards_staff_ratio
                ]
                remaining_eligible_professionals.sort(key=lambda emp: employee_monthly_shift_count[emp.id])

                current_counting_staff = len([
                    emp for emp in assigned_to_this_shift_today
                    if emp.professional_profile and emp.professional_profile.counts_towards_staff_ratio
                ])

                for emp in remaining_eligible_professionals:
                    if current_counting_staff < target_counting_staff:
                        new_assignment = ShiftAssignment(employee=emp, shift=shift, ward=ward, date=current_date, status='PLANNED')
                        generated_assignments_list.append(new_assignment)
                        assigned_to_this_shift_today.append(emp)
                        
                        if current_date not in employee_daily_assignments[emp.id]:
                            employee_daily_assignments[emp.id][current_date] = {}
                        employee_daily_assignments[emp.id][current_date][shift.id] = new_assignment

                        employee_monthly_shift_count[emp.id] += 1
                        current_counting_staff += 1
                        self._log(f"    Assigned {emp.first_name} {emp.last_name} (Professional) to {shift.name} on {current_date}.", "INFO")
                    else:
                        break
                
                if current_counting_staff < target_counting_staff:
                    self._log(f"    FAILED: Only {current_counting_staff}/{target_counting_staff} professional staff assigned for {shift.name} on {current_date}.", "ERROR")


                # Fill remaining slots up to min_staff_for_shift_type with any eligible staff (including helpers)
                total_assigned_to_shift = len(assigned_to_this_shift_today)
                
                remaining_eligible_any_staff = [
                    emp for emp in eligible_employees_for_shift
                    if emp not in assigned_to_this_shift_today
                ]
                remaining_eligible_any_staff.sort(key=lambda emp: employee_monthly_shift_count[emp.id])

                for emp in remaining_eligible_any_staff:
                    if total_assigned_to_shift < min_staff_for_shift_type:
                        new_assignment = ShiftAssignment(employee=emp, shift=shift, ward=ward, date=current_date, status='PLANNED')
                        generated_assignments_list.append(new_assignment)
                        assigned_to_this_shift_today.append(emp)
                        
                        if current_date not in employee_daily_assignments[emp.id]:
                            employee_daily_assignments[emp.id][current_date] = {}
                        employee_daily_assignments[emp.id][current_date][shift.id] = new_assignment

                        employee_monthly_shift_count[emp.id] += 1
                        total_assigned_to_shift += 1
                        self._log(f"    Assigned {emp.first_name} {emp.last_name} (Helper/Extra) to {shift.name} on {current_date}.", "INFO")
                    else:
                        break
                
                if len(assigned_to_this_shift_today) < min_staff_for_shift_type:
                    self._log(f"    FAILED: Only {len(assigned_to_this_shift_today)}/{min_staff_for_shift_type} total staff assigned for {shift.name} on {current_date}.", "ERROR")


        # Save all generated assignments in a single transaction
        try:
            with transaction.atomic():
                ShiftAssignment.objects.bulk_create(generated_assignments_list)
            self._log(f"Successfully generated {len(generated_assignments_list)} shift assignments for {ward.name} in {calendar.month_name[month]} {year}.", "SUCCESS")
        except Exception as e:
            self._log(f"Error saving assignments: {e}", "ERROR")
            return {"success": False, "message": f"Fehler beim Speichern der Zuweisungen: {e}"}

        # Re-run a detailed conflict check (optional, but good for reporting)
        self._log("\nRunning post-generation conflict check...", "INFO")
        newly_generated_and_existing_assignments = ShiftAssignment.objects.filter(
            ward=ward,
            date__gte=start_date,
            date__lte=end_date
        ).select_related('employee', 'shift').prefetch_related('employee__qualifications').order_by('date', 'shift__start_time')

        conflicts_found = self._check_for_conflicts(ward, start_date, end_date, newly_generated_and_existing_assignments)

        if conflicts_found:
            self._log("Schedule generated with conflicts. Please review in admin/UI.", "WARNING")
            return {"success": True, "message": "Dienstplan erstellt, aber mit Konflikten. Bitte überprüfen Sie die Details in der Tagesansicht."}
        else:
            self._log("No major conflicts detected in the generated schedule.", "SUCCESS")
            return {"success": True, "message": "Dienstplan erfolgreich generiert, keine Konflikte gefunden."}

    def _check_for_conflicts(self, ward, start_date, end_date, assignments_queryset=None):
        """
        Helper method to check for conflicts (e.g., overlapping shifts for same employee).
        This can be run after generation. It now updates the status of conflicting assignments.
        """
        conflicts_found = False
        
        if assignments_queryset is None:
            assignments_queryset = ShiftAssignment.objects.filter(
                ward=ward,
                date__gte=start_date,
                date__lte=end_date
            ).select_related('employee', 'shift', 'employee__professional_profile').prefetch_related('employee__qualifications').order_by('date', 'shift__start_time')

        assignments_to_update = {}

        assignments_by_employee_and_date = {}
        for assignment in assignments_queryset:
            assignments_by_employee_and_date.setdefault(assignment.employee.id, {}).setdefault(assignment.date, []).append(assignment)
        
        # 1. Check for Overlapping Shifts on the same day
        for emp_id, assignments_by_date in assignments_by_employee_and_date.items():
            employee_obj = Employee.objects.get(id=emp_id)
            for date, daily_assignments in assignments_by_date.items():
                daily_assignments.sort(key=lambda x: x.shift.start_time)
                
                for i in range(len(daily_assignments)):
                    for j in range(i + 1, len(daily_assignments)):
                        shift1_assignment = daily_assignments[i]
                        shift2_assignment = daily_assignments[j]
                        shift1 = shift1_assignment.shift
                        shift2 = shift2_assignment.shift
                        
                        shift1_start_dt = datetime.datetime.combine(date, shift1.start_time)
                        shift1_end_dt = datetime.datetime.combine(date, shift1.end_time)
                        if shift1.end_time < shift1.start_time:
                            shift1_end_dt += datetime.timedelta(days=1)

                        shift2_start_dt = datetime.datetime.combine(date, shift2.start_time)
                        shift2_end_dt = datetime.datetime.combine(date, shift2.end_time)
                        if shift2.end_time < shift2.start_time:
                            shift2_end_dt += datetime.timedelta(days=1)
                        
                        if (shift1_start_dt < shift2_end_dt and shift2_start_dt < shift1_end_dt):
                            self._log(
                                f"  CONFLICT (Overlap): {employee_obj.first_name} {employee_obj.last_name} assigned to overlapping shifts "
                                f"'{shift1.get_name_display()}' ({shift1.start_time.strftime('%H:%M')}-{shift1.end_time.strftime('%H:%M')}) and "
                                f"'{shift2.get_name_display()}' ({shift2.start_time.strftime('%H:%M')}-{shift2.end_time.strftime('%H:%M')}) on {date}.", "ERROR"
                            )
                            conflicts_found = True
                            assignments_to_update[shift1_assignment.pk] = 'CONFLICT'
                            assignments_to_update[shift2_assignment.pk] = 'CONFLICT'
        
        # 2. Check for Minimum Rest Hours and 3. Consecutive Shifts across days
        for emp_id, assignments_by_date in assignments_by_employee_and_date.items():
            employee_obj = Employee.objects.get(id=emp_id)
            
            employee_all_assignments_sorted = []
            for date in sorted(assignments_by_date.keys()):
                employee_all_assignments_sorted.extend(sorted(assignments_by_date[date], key=lambda x: x.shift.start_time))
            
            last_shift_end_datetime = None
            consecutive_count = 0
            
            for i, assignment in enumerate(employee_all_assignments_sorted):
                current_shift_start_datetime = datetime.datetime.combine(assignment.date, assignment.shift.start_time)
                current_shift_end_datetime = datetime.datetime.combine(assignment.date, assignment.shift.end_time)

                if assignment.shift.end_time < assignment.shift.start_time:
                     current_shift_end_datetime += datetime.timedelta(days=1)

                if last_shift_end_datetime:
                    time_since_last_shift = (current_shift_start_datetime - last_shift_end_datetime).total_seconds() / 3600
                    if time_since_last_shift < self.MIN_REST_HOURS_BETWEEN_SHIFTS:
                        self._log(
                            f"  CONFLICT (Rest): {employee_obj.first_name} {employee_obj.last_name} has insufficient rest "
                            f"({time_since_last_shift:.1f}h) between shift ending at {last_shift_end_datetime.time().strftime('%H:%M')} on {last_shift_end_datetime.date().strftime('%Y-%m-%d')} and "
                            f"shift '{assignment.shift.get_name_display()}' starting at {assignment.shift.start_time.strftime('%H:%M')} on {assignment.date.strftime('%Y-%m-%d')}.", "ERROR"
                        )
                        conflicts_found = True
                        assignments_to_update[assignment.pk] = 'CONFLICT'
                    
                if i > 0:
                    prev_assignment = employee_all_assignments_sorted[i-1]
                    prev_end_dt = datetime.datetime.combine(prev_assignment.date, prev_assignment.shift.end_time)
                    if prev_assignment.shift.end_time < prev_assignment.shift.start_time:
                        prev_end_dt += datetime.timedelta(days=1)

                    current_start_dt_for_consecutive_check = datetime.datetime.combine(assignment.date, assignment.shift.start_time)
                    
                    if (current_start_dt_for_consecutive_check - prev_end_dt).total_seconds() / 3600 >= self.MIN_REST_HOURS_BETWEEN_SHIFTS:
                        consecutive_count += 1
                    else:
                        consecutive_count = 1
                else:
                    consecutive_count = 1

                if consecutive_count > self.MAX_CONSECUTIVE_SHIFTS:
                    self._log(
                        f"  CONFLICT (Consecutive): {employee_obj.first_name} {employee_obj.last_name} works more than {self.MAX_CONSECUTIVE_SHIFTS} "
                        f"consecutive shifts, including shift '{assignment.shift.get_name_display()}' on {assignment.date}.", "ERROR"
                    )
                    conflicts_found = True
                    assignments_to_update[assignment.pk] = 'CONFLICT'
                
                last_shift_end_datetime = current_shift_end_datetime
        
        if assignments_to_update:
            self._log(f"  Updating status for {len(assignments_to_update)} conflicting assignments...", "WARNING")
            with transaction.atomic():
                for pk, status_val in assignments_to_update.items():
                    try:
                        assignment_to_update = ShiftAssignment.objects.get(pk=pk)
                        assignment_to_update.status = status_val
                        assignment_to_update.save(update_fields=['status'])
                        self._log(f"    Updated assignment {pk} to status '{assignment_to_update.status}'", "INFO")
                    except ShiftAssignment.DoesNotExist:
                        self._log(f"    Failed to find assignment {pk} for update.", "ERROR")

        return conflicts_found
