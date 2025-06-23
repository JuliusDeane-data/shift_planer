# shift_planer/tests.py

from django.test import TestCase
from django.utils import timezone
from datetime import date, time, timedelta
import calendar

from shift_planer.models import (
    ProfessionalProfile, Qualification, Employee,
    Ward, Shift, ShiftAssignment, EmployeeAvailability, Absence
)
from shift_planer.scheduler import ShiftScheduler # Importiere den Scheduler

class ModelTests(TestCase):
    """
    Unit tests for the Shift Planner models.
    """

    def setUp(self):
        """
        Set up common data for tests.
        """
        # Create Professional Profiles
        self.prof_nurse = ProfessionalProfile.objects.create(
            name="Pflegefachkraft", description="Qualified nurse", counts_towards_staff_ratio=True
        )
        self.nursing_assistant = ProfessionalProfile.objects.create(
            name="Pflegehelfer", description="Nursing assistant", counts_towards_staff_ratio=False
        )

        # Create Qualifications
        self.qual_critical = Qualification.objects.create(
            name="Beatmungsschein", description="Ventilation certificate", is_critical=True
        )
        self.qual_praxis = Qualification.objects.create(
            name="Praxisanleiter", description="Practical instructor", is_critical=False
        )

        # Create Shifts
        self.shift_early = Shift.objects.create(
            name='EARLY', start_time=time(6, 0), end_time=time(14, 0)
        )
        self.shift_late = Shift.objects.create(
            name='LATE', start_time=time(14, 0), end_time=time(22, 0)
        )
        self.shift_night = Shift.objects.create(
            name='NIGHT', start_time=time(22, 0), end_time=time(6, 0)
        )
        self.shift_night.required_qualifications.add(self.qual_critical)

        # Create Wards
        self.ward_alpha = Ward.objects.create(
            name="Station Alpha",
            description="General Ward",
            min_staff_early_shift=3,
            min_staff_late_shift=3,
            min_staff_night_shift=2,
            current_patients=10
        )
        self.ward_beta = Ward.objects.create(
            name="Station Beta",
            description="Intensive Care Unit",
            min_staff_early_shift=2,
            min_staff_late_shift=2,
            min_staff_night_shift=1,
            current_patients=5
        )

        # Create Employees
        self.employee_anna = Employee.objects.create(
            first_name="Anna", last_name="Muster", professional_profile=self.prof_nurse,
            employee_number="EMP001", email="anna@example.com", available_hours_per_week=40
        )
        self.employee_anna.qualifications.add(self.qual_critical, self.qual_praxis)
        self.employee_anna.allowed_shifts.add(self.shift_early, self.shift_late, self.shift_night)

        self.employee_ben = Employee.objects.create(
            first_name="Ben", last_name="Schulz", professional_profile=self.prof_nurse,
            employee_number="EMP002", email="ben@example.com", available_hours_per_week=35
        )
        self.employee_ben.allowed_shifts.add(self.shift_early, self.shift_late) # No night shift allowed

        self.employee_clara = Employee.objects.create(
            first_name="Clara", last_name="Weber", professional_profile=self.nursing_assistant,
            employee_number="EMP003", email="clara@example.com", available_hours_per_week=30
        )
        self.employee_clara.allowed_shifts.add(self.shift_early, self.shift_late)

    def test_professional_profile_creation(self):
        """Test ProfessionalProfile model creation and __str__ method."""
        self.assertEqual(self.prof_nurse.name, "Pflegefachkraft")
        self.assertTrue(self.prof_nurse.counts_towards_staff_ratio)
        self.assertEqual(str(self.prof_nurse), "Pflegefachkraft")

    def test_qualification_creation(self):
        """Test Qualification model creation and __str__ method."""
        self.assertEqual(self.qual_critical.name, "Beatmungsschein")
        self.assertTrue(self.qual_critical.is_critical)
        self.assertEqual(str(self.qual_critical), "Beatmungsschein")

    def test_shift_creation(self):
        """Test Shift model creation and __str__ method."""
        self.assertEqual(self.shift_early.name, 'EARLY')
        self.assertEqual(self.shift_early.start_time, time(6, 0))
        self.assertEqual(str(self.shift_early), "Early Shift (06:00-14:00)")
        self.assertTrue(self.shift_night.required_qualifications.filter(name="Beatmungsschein").exists())

    def test_ward_creation(self):
        """Test Ward model creation and __str__ method and slug generation."""
        self.assertEqual(self.ward_alpha.name, "Station Alpha")
        self.assertEqual(self.ward_alpha.slug, "station-alpha")
        self.assertEqual(str(self.ward_alpha), "Station Alpha")
        self.assertEqual(self.ward_alpha.min_staff_night_shift, 2)

    def test_employee_creation(self):
        """Test Employee model creation and __str__ method."""
        self.assertEqual(self.employee_anna.first_name, "Anna")
        self.assertEqual(self.employee_anna.last_name, "Muster")
        self.assertEqual(str(self.employee_anna), "Anna Muster")
        self.assertEqual(self.employee_anna.professional_profile, self.prof_nurse)
        self.assertTrue(self.employee_anna.qualifications.filter(name="Beatmungsschein").exists())
        self.assertTrue(self.employee_anna.allowed_shifts.filter(name='NIGHT').exists())

    def test_shift_assignment_creation(self):
        """Test ShiftAssignment model creation and __str__ method."""
        assignment = ShiftAssignment.objects.create(
            employee=self.employee_anna,
            shift=self.shift_early,
            ward=self.ward_alpha,
            date=date(2025, 1, 1),
            status='PLANNED'
        )
        self.assertEqual(assignment.status, 'PLANNED')
        self.assertEqual(str(assignment), f"2025-01-01 - Station Alpha - EARLY (Anna Muster)")
        # Test unique_together constraint (should fail if trying to create same assignment again)
        with self.assertRaises(Exception): # Using generic Exception for simplicity, could be IntegrityError
            ShiftAssignment.objects.create(
                employee=self.employee_anna,
                shift=self.shift_early,
                ward=self.ward_alpha,
                date=date(2025, 1, 1),
                status='PLANNED'
            )

    def test_employee_availability_creation(self):
        """Test EmployeeAvailability model creation and __str__ method."""
        availability = EmployeeAvailability.objects.create(
            employee=self.employee_anna,
            date=date(2025, 1, 1),
            is_available=True,
            preferred_shift=self.shift_late
        )
        self.assertTrue(availability.is_available)
        self.assertEqual(availability.preferred_shift, self.shift_late)
        self.assertEqual(str(availability), f"Anna Muster on 2025-01-01 - Available (Preference: LATE)")

    def test_absence_creation(self):
        """Test Absence model creation and __str__ method."""
        absence = Absence.objects.create(
            employee=self.employee_anna,
            start_date=date(2025, 1, 10),
            end_date=date(2025, 1, 15),
            type='VACATION',
            approved=True
        )
        self.assertEqual(absence.type, 'VACATION')
        self.assertTrue(absence.approved)
        self.assertEqual(str(absence), f"Anna Muster - VACATION from 2025-01-10 to 2025-01-15")


class ShiftSchedulerTests(TestCase):
    """
    Unit tests for the ShiftScheduler logic.
    """

    def setUp(self):
        """
        Set up common data for scheduler tests.
        """
        self.prof_nurse = ProfessionalProfile.objects.create(
            name="Pflegefachkraft", description="Qualified nurse", counts_towards_staff_ratio=True
        )
        self.nursing_assistant = ProfessionalProfile.objects.create(
            name="Pflegehelfer", description="Nursing assistant", counts_towards_staff_ratio=False
        )

        self.qual_critical = Qualification.objects.create(
            name="Beatmungsschein", description="Ventilation certificate", is_critical=True
        )
        self.qual_praxis = Qualification.objects.create(
            name="Praxisanleiter", description="Practical instructor", is_critical=False
        )

        self.shift_early = Shift.objects.create(
            name='EARLY', start_time=time(6, 0), end_time=time(14, 0)
        )
        self.shift_late = Shift.objects.create(
            name='LATE', start_time=time(14, 0), end_time=time(22, 0)
        )
        self.shift_night = Shift.objects.create(
            name='NIGHT', start_time=time(22, 0), end_time=time(6, 0)
        )
        self.shift_night.required_qualifications.add(self.qual_critical)

        self.ward_alpha = Ward.objects.create(
            name="Station Alpha",
            description="General Ward",
            min_staff_early_shift=1, # Reduced for easier testing
            min_staff_late_shift=1,
            min_staff_night_shift=1,
            current_patients=5 # Min staff 2 for professionals (5+2)//3 = 2
        )

        self.employee_anna = Employee.objects.create(
            first_name="Anna", last_name="Muster", professional_profile=self.prof_nurse,
            employee_number="EMP001", email="anna@example.com", available_hours_per_week=40
        )
        self.employee_anna.qualifications.add(self.qual_critical)
        self.employee_anna.allowed_shifts.add(self.shift_early, self.shift_late, self.shift_night)

        self.employee_ben = Employee.objects.create(
            first_name="Ben", last_name="Schulz", professional_profile=self.prof_nurse,
            employee_number="EMP002", email="ben@example.com", available_hours_per_week=35
        )
        self.employee_ben.allowed_shifts.add(self.shift_early, self.shift_late, self.shift_night)

        self.employee_clara = Employee.objects.create(
            first_name="Clara", last_name="Weber", professional_profile=self.nursing_assistant,
            employee_number="EMP003", email="clara@example.com", available_hours_per_week=30
        )
        self.employee_clara.allowed_shifts.add(self.shift_early, self.shift_late)

        # Scheduler instance with default parameters
        self.scheduler = ShiftScheduler(min_rest_hours=11, max_consecutive_shifts=6)
        self.year = 2025
        self.month = 7 # July 2025

    def test_generate_schedule_success(self):
        """Test successful schedule generation for a month."""
        result = self.scheduler.generate_schedule(
            year=self.year, month=self.month, ward_slug=self.ward_alpha.slug, overwrite=True
        )
        self.assertTrue(result["success"])
        self.assertIn("Successfully generated", result["message"])
        
        # Check if assignments were created
        assignments_count = ShiftAssignment.objects.filter(
            ward=self.ward_alpha,
            date__year=self.year,
            date__month=self.month
        ).count()
        self.assertGreater(assignments_count, 0)
        
        # Check for expected number of professional nurses and critical qual
        # (This is a simplified check, detailed conflict check is separate)
        for day in range(1, calendar.monthrange(self.year, self.month)[1] + 1):
            current_date = date(self.year, self.month, day)
            for shift in [self.shift_early, self.shift_late, self.shift_night]:
                assignments = ShiftAssignment.objects.filter(
                    ward=self.ward_alpha, date=current_date, shift=shift
                )
                if shift == self.shift_night:
                    # Check if at least one critical qual is assigned to night shift
                    critical_assigned = any(
                        self.qual_critical in ass.employee.qualifications.all() for ass in assignments
                    )
                    self.assertTrue(critical_assigned or self.ward_alpha.current_patients == 0,
                                    f"Night shift on {current_date} has no critical qual employee")

    def test_generate_schedule_no_overwrite_existing(self):
        """Test that generation fails if existing assignments and no overwrite."""
        # Create a dummy assignment first
        ShiftAssignment.objects.create(
            employee=self.employee_anna,
            shift=self.shift_early,
            ward=self.ward_alpha,
            date=date(self.year, self.month, 1),
            status='PLANNED'
        )
        
        result = self.scheduler.generate_schedule(
            year=self.year, month=self.month, ward_slug=self.ward_alpha.slug, overwrite=False
        )
        self.assertFalse(result["success"])
        self.assertIn("Bestehender Dienstplan", result["message"])
        self.assertIn("[ERROR] Existing assignments found", self.scheduler.get_logs()[0])

    def test_generate_schedule_with_overwrite(self):
        """Test that generation overwrites existing assignments."""
        # Create a dummy assignment first
        ShiftAssignment.objects.create(
            employee=self.employee_anna,
            shift=self.shift_early,
            ward=self.ward_alpha,
            date=date(self.year, self.month, 1),
            status='PLANNED'
        )
        
        initial_count = ShiftAssignment.objects.filter(
            ward=self.ward_alpha, date__year=self.year, date__month=self.month
        ).count()
        self.assertGreater(initial_count, 0) # Ensure initial assignment exists

        result = self.scheduler.generate_schedule(
            year=self.year, month=self.month, ward_slug=self.ward_alpha.slug, overwrite=True
        )
        self.assertTrue(result["success"])
        self.assertIn("Successfully generated", result["message"])
        
        # Check if the old assignments were deleted and new ones created
        new_count = ShiftAssignment.objects.filter(
            ward=self.ward_alpha, date__year=self.year, date__month=self.month
        ).count()
        self.assertGreater(new_count, 0)
        # Note: We can't easily assert new_count != initial_count because the scheduler might generate the same count
        # or more/less depending on logic. The key is that it *ran* and saved new ones.
        self.assertIn("Overwriting", "\n".join(self.scheduler.get_logs()))


    def test_conflict_detection_overlapping_shifts(self):
        """Test detection of overlapping shifts for an employee on the same day."""
        target_date = date(self.year, self.month, 1)
        
        # Manually create two overlapping assignments for employee_anna
        ShiftAssignment.objects.create(
            employee=self.employee_anna, shift=self.shift_early, ward=self.ward_alpha, date=target_date, status='PLANNED'
        )
        ShiftAssignment.objects.create(
            employee=self.employee_anna, shift=self.shift_late, ward=self.ward_alpha, date=target_date, status='PLANNED'
        )
        
        # Run the scheduler with overwrite to trigger the internal conflict check
        result = self.scheduler.generate_schedule(
            year=self.year, month=self.month, ward_slug=self.ward_alpha.slug, overwrite=True
        )
        
        # Verify that conflicts were detected and assignments updated
        self.assertIn("aber mit Konflikten", result["message"])
        self.assertIn("CONFLICT", "\n".join(self.scheduler.get_logs()))
        
        anna_early_assignment = ShiftAssignment.objects.get(
            employee=self.employee_anna, shift=self.shift_early, date=target_date
        )
        anna_late_assignment = ShiftAssignment.objects.get(
            employee=self.employee_anna, shift=self.shift_late, date=target_date
        )
        self.assertEqual(anna_early_assignment.status, 'CONFLICT')
        self.assertEqual(anna_late_assignment.status, 'CONFLICT')

    def test_conflict_detection_insufficient_rest_hours(self):
        """Test detection of insufficient rest hours between shifts."""
        # Create a scenario where an employee works a late shift then an early shift with insufficient rest
        test_date = date(self.year, self.month, 5)
        
        # Shift ending at 22:00 on day D
        ShiftAssignment.objects.create(
            employee=self.employee_anna, shift=self.shift_late, ward=self.ward_alpha, date=test_date, status='PLANNED'
        )
        # Shift starting at 06:00 on day D+1 (8 hours rest, which is < 11 required)
        ShiftAssignment.objects.create(
            employee=self.employee_anna, shift=self.shift_early, ward=self.ward_alpha, date=test_date + timedelta(days=1), status='PLANNED'
        )
        
        result = self.scheduler.generate_schedule(
            year=self.year, month=self.month, ward_slug=self.ward_alpha.slug, overwrite=True
        )
        
        self.assertIn("aber mit Konflikten", result["message"])
        self.assertIn("CONFLICT (Rest)", "\n".join(self.scheduler.get_logs()))
        
        # Check if the second assignment's status is CONFLICT
        conflict_assignment = ShiftAssignment.objects.get(
            employee=self.employee_anna, shift=self.shift_early, date=test_date + timedelta(days=1)
        )
        self.assertEqual(conflict_assignment.status, 'CONFLICT')

    def test_conflict_detection_max_consecutive_shifts(self):
        """Test detection of exceeding maximum consecutive shifts."""
        # Set a very low max_consecutive_shifts for testing
        self.scheduler.MAX_CONSECUTIVE_SHIFTS = 2 
        
        # Assign Anna to shifts for 3 consecutive days
        ShiftAssignment.objects.create(employee=self.employee_anna, shift=self.shift_early, ward=self.ward_alpha, date=date(self.year, self.month, 1), status='PLANNED')
        ShiftAssignment.objects.create(employee=self.employee_anna, shift=self.shift_early, ward=self.ward_alpha, date=date(self.year, self.month, 2), status='PLANNED')
        ShiftAssignment.objects.create(employee=self.employee_anna, shift=self.shift_early, ward=self.ward_alpha, date=date(self.year, self.month, 3), status='PLANNED') # This one should cause conflict
        
        result = self.scheduler.generate_schedule(
            year=self.year, month=self.month, ward_slug=self.ward_alpha.slug, overwrite=True
        )
        
        self.assertIn("aber mit Konflikten", result["message"])
        self.assertIn("CONFLICT", "\n".join(self.scheduler.get_logs()))
        
        # Check if the third assignment's status is CONFLICT
        conflict_assignment = ShiftAssignment.objects.get(
            employee=self.employee_anna, shift=self.shift_early, date=date(self.year, self.month, 3)
        )
        self.assertEqual(conflict_assignment.status, 'CONFLICT')
    
    def test_employee_availability_respected(self):
        """Test that employees are not assigned if unavailable."""
        unavailable_date = date(self.year, self.month, 10)
        EmployeeAvailability.objects.create(
            employee=self.employee_anna, date=unavailable_date, is_available=False
        )

        result = self.scheduler.generate_schedule(
            year=self.year, month=self.month, ward_slug=self.ward_alpha.slug, overwrite=True
        )
        self.assertTrue(result["success"]) # Generation should still complete

        # Verify no assignments for Anna on the unavailable date
        assignments_for_anna = ShiftAssignment.objects.filter(
            employee=self.employee_anna, date=unavailable_date
        ).exists()
        self.assertFalse(assignments_for_anna, f"Anna was assigned on {unavailable_date} despite being unavailable.")
        self.assertIn(f"Skipping {self.employee_anna.first_name} {self.employee_anna.last_name} for {self.shift_early.name} on {unavailable_date}: Not available.", "\n".join(self.scheduler.get_logs()))


    def test_employee_absence_respected(self):
        """Test that employees are not assigned during absence."""
        absence_start = date(self.year, self.month, 15)
        absence_end = date(self.year, self.month, 17)
        Absence.objects.create(
            employee=self.employee_ben, start_date=absence_start, end_date=absence_end,
            type=Absence.SICK_LEAVE, approved=True
        )

        result = self.scheduler.generate_schedule(
            year=self.year, month=self.month, ward_slug=self.ward_alpha.slug, overwrite=True
        )
        self.assertTrue(result["success"])

        # Verify no assignments for Ben during his absence
        assignments_during_absence = ShiftAssignment.objects.filter(
            employee=self.employee_ben, date__gte=absence_start, date__lte=absence_end
        ).exists()
        self.assertFalse(assignments_during_absence, f"Ben was assigned during his absence.")
        self.assertIn(f"Skipping {self.employee_ben.first_name} {self.employee_ben.last_name} for {self.shift_early.name} on {absence_start}: Is absent.", "\n".join(self.scheduler.get_logs()))

    def test_qualification_matching_for_critical_shift(self):
        """Test that critical qualifications are respected for required shifts."""
        # Remove critical qual from Anna to ensure it gets picked from Ben if available
        self.employee_anna.qualifications.remove(self.qual_critical)
        
        # Ensure Ben has the critical qual
        self.employee_ben.qualifications.add(self.qual_critical)

        result = self.scheduler.generate_schedule(
            year=self.year, month=self.month, ward_slug=self.ward_alpha.slug, overwrite=True
        )
        self.assertTrue(result["success"])
        
        # Check if Ben (or another qualified employee if more exist) is assigned to night shifts
        # A simple check: At least one night shift should have a critical qual employee
        night_assignments = ShiftAssignment.objects.filter(
            ward=self.ward_alpha, shift=self.shift_night, date__year=self.year, date__month=self.month
        )
        
        found_qualified = False
        for assignment in night_assignments:
            if self.qual_critical in assignment.employee.qualifications.all():
                found_qualified = True
                break
        
        self.assertTrue(found_qualified, "No employee with critical qualification assigned to night shift.")
        
        # Re-add critical qual to Anna for other tests
        self.employee_anna.qualifications.add(self.qual_critical)

    def test_professional_staff_ratio_met(self):
        """Test that the minimum professional staff ratio is attempted to be met."""
        # For ward_alpha, current_patients=5, so required_professionals = (5+2)//3 = 2
        # min_staff_early_shift = 1, so target_counting_staff = max(2,1) = 2
        
        # We have Anna (Prof Nurse) and Ben (Prof Nurse)
        result = self.scheduler.generate_schedule(
            year=self.year, month=self.month, ward_slug=self.ward_alpha.slug, overwrite=True
        )
        self.assertTrue(result["success"])

        # Check a specific early shift day
        test_date = date(self.year, self.month, 1)
        assignments = ShiftAssignment.objects.filter(
            ward=self.ward_alpha, date=test_date, shift=self.shift_early
        )
        
        professional_staff_count = sum(
            1 for ass in assignments 
            if ass.employee.professional_profile and ass.employee.professional_profile.counts_towards_staff_ratio
        )
        
        # Assert that at least the minimum required professional staff are assigned
        self.assertGreaterEqual(professional_staff_count, 2, f"Expected at least 2 professional staff on {test_date} {self.shift_early.name}")
        self.assertIn("Assigned", "\n".join(self.scheduler.get_logs()))

    def test_no_professional_staff_assigned_warning(self):
        """Test warning when professional staff cannot be assigned."""
        # Make all professional nurses unavailable for a day
        test_date = date(self.year, self.month, 12)
        EmployeeAvailability.objects.create(employee=self.employee_anna, date=test_date, is_available=False)
        EmployeeAvailability.objects.create(employee=self.employee_ben, date=test_date, is_available=False)
        
        result = self.scheduler.generate_schedule(
            year=self.year, month=self.month, ward_slug=self.ward_alpha.slug, overwrite=True
        )
        self.assertTrue(result["success"]) # Generation still completes
        
        # Expect a warning for failing to meet professional staff quota
        self.assertIn("FAILED: Only 0/2 professional staff assigned for Early Shift", "\n".join(self.scheduler.get_logs()))
        self.assertIn("[ERROR]", "\n".join(self.scheduler.get_logs())) # FAILED is logged as ERROR
