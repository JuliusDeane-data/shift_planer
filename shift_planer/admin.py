# shift_planer/admin.py

from django.contrib import admin
from .models import (
    ProfessionalProfile, Qualification, Employee,
    Ward, Shift, ShiftAssignment, EmployeeAvailability, Absence
)

# Register ProfessionalProfile
@admin.register(ProfessionalProfile)
class ProfessionalProfileAdmin(admin.ModelAdmin):
    list_display = ('name', 'counts_towards_staff_ratio', 'description')
    search_fields = ('name',)
    list_filter = ('counts_towards_staff_ratio',)

# Register Qualification
@admin.register(Qualification)
class QualificationAdmin(admin.ModelAdmin):
    list_display = ('name', 'is_critical', 'description')
    search_fields = ('name',)
    list_filter = ('is_critical',)
    # 'counts_towards_staff_ratio' was removed from here as it's now in ProfessionalProfile

# Register Employee
@admin.register(Employee)
class EmployeeAdmin(admin.ModelAdmin):
    list_display = ('first_name', 'last_name', 'professional_profile', 'employee_number', 'phone', 'email', 'available_hours_per_week')
    list_filter = ('professional_profile', 'qualifications', 'allowed_shifts')
    search_fields = ('first_name', 'last_name', 'employee_number', 'email')
    filter_horizontal = ('qualifications', 'allowed_shifts') # For many-to-many fields
    
    # You might want to define custom forms for EmployeeAdmin if you want to filter
    # the choices for qualifications or allowed_shifts based on professional_profile.
    # For now, we'll keep it simple to fix the immediate error.


# Register Ward
@admin.register(Ward)
class WardAdmin(admin.ModelAdmin):
    list_display = ('name', 'slug', 'current_patients', 'min_staff_early_shift', 'min_staff_late_shift', 'min_staff_night_shift')
    search_fields = ('name',)
    prepopulated_fields = {'slug': ('name',)} # Automatically generate slug from name

# Register Shift
@admin.register(Shift)
class ShiftAdmin(admin.ModelAdmin):
    list_display = ('get_name_display', 'start_time', 'end_time')
    list_filter = ('name',)
    search_fields = ('name',)
    filter_horizontal = ('required_qualifications',)

# Register ShiftAssignment
@admin.register(ShiftAssignment)
class ShiftAssignmentAdmin(admin.ModelAdmin):
    list_display = ('date', 'ward', 'shift', 'employee', 'status')
    list_filter = ('date', 'ward', 'shift', 'status')
    search_fields = ('employee__first_name', 'employee__last_name', 'ward__name', 'shift__name')
    date_hierarchy = 'date' # Adds a date-based navigation

# Register EmployeeAvailability
@admin.register(EmployeeAvailability)
class EmployeeAvailabilityAdmin(admin.ModelAdmin):
    list_display = ('employee', 'date', 'is_available', 'preferred_shift')
    list_filter = ('is_available', 'date', 'preferred_shift')
    search_fields = ('employee__first_name', 'employee__last_name')
    date_hierarchy = 'date'

# Register Absence
@admin.register(Absence)
class AbsenceAdmin(admin.ModelAdmin):
    list_display = ('employee', 'start_date', 'end_date', 'type', 'approved') # Corrected 'absence_type' to 'type'
    list_filter = ('type', 'approved') # Corrected 'absence_type' to 'type'
    search_fields = ('employee__first_name', 'employee__last_name', 'notes')
    date_hierarchy = 'start_date'

