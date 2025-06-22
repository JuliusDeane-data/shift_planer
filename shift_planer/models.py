# shift_planer/models.py

from django.db import models
from django.utils.text import slugify

# Neues Modell für Berufsprofile (z.B. Pflegefachkraft, Pflegehelfer, Reinigungskraft)
class ProfessionalProfile(models.Model):
    name = models.CharField(max_length=100, unique=True, verbose_name="Professional Profile Name")
    description = models.TextField(blank=True, verbose_name="Description")
    # Gibt an, ob dieses Berufsprofil zum Mindestpersonalbestand zählt (z.B. Pflegefachkraft)
    counts_towards_staff_ratio = models.BooleanField(default=False, verbose_name="Counts towards Staff Ratio")

    class Meta:
        verbose_name = "Professional Profile"
        verbose_name_plural = "Professional Profiles"
        ordering = ['name']

    def __str__(self):
        return self.name

# Modell für Qualifikationen (z.B. Beatmungsschein, Praxisanleiter)
class Qualification(models.Model):
    name = models.CharField(max_length=100, unique=True, verbose_name="Qualification Name")
    description = models.TextField(blank=True, verbose_name="Description")
    # Gibt an, ob diese Qualifikation für bestimmte Aufgaben kritisch ist (z.B. Beatmungsschein)
    is_critical = models.BooleanField(default=False, verbose_name="Is Critical (e.g., Ventilation Certificate)") 
    # Removed: counts_towards_staff_ratio (moved to ProfessionalProfile)

    class Meta:
        verbose_name = "Qualification"
        verbose_name_plural = "Qualifications"
        ordering = ['name']

    def __str__(self):
        return self.name

# Modell für Mitarbeiter
class Employee(models.Model):
    first_name = models.CharField(max_length=50, verbose_name="First Name")
    last_name = models.CharField(max_length=50, verbose_name="Last Name")
    
    # Verknüpfung zum primären Berufsprofil des Mitarbeiters (z.B. Pflegefachkraft, Pflegehelfer)
    professional_profile = models.ForeignKey(ProfessionalProfile, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Professional Profile")

    employee_number = models.CharField(max_length=20, unique=True, blank=True, null=True, verbose_name="Employee Number")
    phone = models.CharField(max_length=20, blank=True, verbose_name="Phone Number")
    email = models.EmailField(blank=True, verbose_name="Email") 
    
    # Qualifikationen des Mitarbeiters (Viele-zu-Viele-Beziehung) - für zusätzliche Zertifikate
    qualifications = models.ManyToManyField(Qualification, blank=True, verbose_name="Qualifications")

    available_hours_per_week = models.DecimalField(
        max_digits=4, decimal_places=2, default=40.00,
        verbose_name="Available Hours per Week"
    )
    
    # Schichten, die ein Mitarbeiter generell arbeiten darf
    allowed_shifts = models.ManyToManyField('Shift', blank=True, related_name='allowed_employees', verbose_name="Allowed Shifts")

    class Meta:
        verbose_name = "Employee"
        verbose_name_plural = "Employees"
        ordering = ['last_name', 'first_name']

    def __str__(self):
        return f"{self.first_name} {self.last_name}" if self.first_name or self.last_name else "Unknown Employee"


# Modell für Stationen/Abteilungen
class Ward(models.Model):
    name = models.CharField(max_length=100, unique=True, verbose_name="Ward Name")
    slug = models.SlugField(max_length=100, unique=True, blank=True, verbose_name="URL Slug")
    description = models.TextField(blank=True, verbose_name="Description")
    
    min_staff_early_shift = models.IntegerField(default=1, verbose_name="Min. Staff Early Shift")
    min_staff_late_shift = models.IntegerField(default=1, verbose_name="Min. Staff Late Shift")
    min_staff_night_shift = models.IntegerField(default=1, verbose_name="Min. Staff Night Shift")

    current_patients = models.IntegerField(default=0, verbose_name="Current Number of Patients")

    class Meta:
        verbose_name = "Ward"
        verbose_name_plural = "Wards"
        ordering = ['name']

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = slugify(self.name)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.name if self.name else "Unnamed Ward"


# Modell für Schichttypen (z.B. Früh, Spät, Nacht)
class Shift(models.Model):
    SHIFT_TYPES = [
        ('EARLY', 'Early Shift'),
        ('LATE', 'Late Shift'),
        ('NIGHT', 'Night Shift'),
        ('OTHER', 'Other Shift'),
    ]
    
    name = models.CharField(max_length=50, choices=SHIFT_TYPES, unique=True, verbose_name="Shift Type")
    start_time = models.TimeField(verbose_name="Start Time")
    end_time = models.TimeField(verbose_name="End Time")
    
    # Qualifikationen, die für diese Schicht benötigt werden
    required_qualifications = models.ManyToManyField(Qualification, blank=True, verbose_name="Required Qualifications")

    class Meta:
        verbose_name = "Shift"
        verbose_name_plural = "Shifts"
        ordering = ['start_time']

    def __str__(self):
        return f"{self.get_name_display()} ({self.start_time.strftime('%H:%M')}-{self.end_time.strftime('%H:%M')})"

# Modell für einen einzelnen Eintrag im Schichtplan
class ShiftAssignment(models.Model):
    date = models.DateField(verbose_name="Date")
    shift = models.ForeignKey(Shift, on_delete=models.CASCADE, verbose_name="Shift")
    ward = models.ForeignKey(Ward, on_delete=models.CASCADE, verbose_name="Ward")
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, verbose_name="Employee")
    
    STATUS_CHOICES = [
        ('PLANNED', 'Planned'),
        ('CONFIRMED', 'Confirmed'),
        ('CONFLICT', 'Conflict'),
        ('UNASSIGNED', 'Unassigned / Open'),
    ]
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='UNASSIGNED', verbose_name="Status")

    class Meta:
        verbose_name = "Shift Assignment"
        verbose_name_plural = "Shift Assignments"
        unique_together = ('date', 'shift', 'employee')
        ordering = ['date', 'ward', 'shift__start_time']

    def __str__(self):
        return f"{self.date.strftime('%Y-%m-%d')} - {self.ward.name} - {self.shift.name} ({self.employee.first_name} {self.employee.last_name})"

# Modell für die Verfügbarkeit/Wunschdienste der Mitarbeiter
class EmployeeAvailability(models.Model):
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, verbose_name="Employee")
    date = models.DateField(verbose_name="Date")
    is_available = models.BooleanField(default=True, verbose_name="Is Available")
    preferred_shift = models.ForeignKey(Shift, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="Preferred Shift")
    notes = models.TextField(blank=True, verbose_name="Notes")

    class Meta:
        verbose_name = "Employee Availability"
        verbose_name_plural = "Employee Availabilities"
        unique_together = ('employee', 'date')
        ordering = ['date', 'employee']

    def __str__(self):
        status = "Available" if self.is_available else "Not Available"
        if self.preferred_shift:
            return f"{self.employee} on {self.date} - {status} (Preference: {self.preferred_shift.name})"
        return f"{self.employee} on {self.date} - {status}"

# Modell für Abwesenheiten (Urlaub, Krankheit etc.)
class Absence(models.Model):
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, verbose_name="Employee")
    start_date = models.DateField(verbose_name="Start Date")
    end_date = models.DateField(verbose_name="End Date")
    ABSENCE_TYPES_CHOICES = [
        ('VACATION', 'Vacation'),
        ('SICKNESS', 'Sickness'),
        ('TRAINING', 'Training'),
        ('OTHER', 'Other'),
    ]
    # Temporarily set null=True to allow migration to pass if existing data has nulls
    type = models.CharField(max_length=20, choices=ABSENCE_TYPES_CHOICES, verbose_name="Absence Type", null=True, default='OTHER')
    approved = models.BooleanField(default=False, verbose_name="Approved")
    notes = models.TextField(blank=True, verbose_name="Notes")

    class Meta:
        verbose_name = "Absence"
        verbose_name_plural = "Absences"
        ordering = ['start_date', 'employee']

    def __str__(self):
        return f"{self.employee} - {self.type} from {self.start_date} to {self.end_date}"
