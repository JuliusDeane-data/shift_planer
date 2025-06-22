# shift_planer/urls.py

from django.urls import path
from .views import (
    EmployeeListView, HomeView, ShiftCalendarView, DailyShiftView, 
    ShiftAssignmentCreateView, ShiftAssignmentUpdateView, ShiftAssignmentDeleteView, 
    EmployeeUpdateView, EmployeeProfileOverview,
    EmployeeAvailabilityCreateView, EmployeeAvailabilityUpdateView, EmployeeAvailabilityDeleteView,
    AbsenceCreateView, AbsenceUpdateView, AbsenceDeleteView,
    # Importiere die ProfessionalProfile Views
    ProfessionalProfileListView, ProfessionalProfileCreateView,
    ProfessionalProfileUpdateView, ProfessionalProfileDeleteView,
    # Importiere die Qualification Views
    QualificationListView, QualificationCreateView,
    QualificationUpdateView, QualificationDeleteView,
    # Importiere die EmployeeCreateView und EmployeeDeleteView
    EmployeeCreateView, EmployeeDeleteView , AutomaticScheduleView
)

app_name = 'shift_planer' # Definiere einen Namespace für diese App-URLs

urlpatterns = [
    path('', HomeView.as_view(), name='home'),
    path('employees/', EmployeeListView.as_view(), name='employee_list'),
    
    # Employee Profile and related actions - EXPECTS 'pk'
    path('employees/add/', EmployeeCreateView.as_view(), name='employee_create'), # URL zum Hinzufügen von Mitarbeitern
    path('employees/<int:pk>/profile/', EmployeeProfileOverview.as_view(), name='employee_profile'),
    path('employees/<int:pk>/edit-profile/', EmployeeUpdateView.as_view(), name='employee_edit_profile'),
    path('employees/<int:pk>/delete/', EmployeeDeleteView.as_view(), name='employee_delete'), # NEU: URL zum Löschen von Mitarbeitern

    # Employee Availability URLs - EXPECTS 'employee_pk' in the URL pattern
    path('employees/<int:employee_pk>/availability/add/', EmployeeAvailabilityCreateView.as_view(), name='employee_availability_create'),
    path('availabilities/<int:pk>/edit/', EmployeeAvailabilityUpdateView.as_view(), name='employee_availability_update'),
    path('availabilities/<int:pk>/delete/', EmployeeAvailabilityDeleteView.as_view(), name='employee_availability_delete'),

    # Employee Absence URLs - EXPECTS 'employee_pk' in the URL pattern
    path('employees/<int:employee_pk>/absence/add/', AbsenceCreateView.as_view(), name='absence_create'),
    path('absences/<int:pk>/edit/', AbsenceUpdateView.as_view(), name='absence_update'),
    path('absences/<int:pk>/delete/', AbsenceDeleteView.as_view(), name='absence_delete'),

    # ProfessionalProfile Management URLs
    path('professional-profiles/', ProfessionalProfileListView.as_view(), name='professional_profile_list'),
    path('professional-profiles/add/', ProfessionalProfileCreateView.as_view(), name='professional_profile_create'),
    path('professional-profiles/<int:pk>/edit/', ProfessionalProfileUpdateView.as_view(), name='professional_profile_update'),
    path('professional-profiles/<int:pk>/delete/', ProfessionalProfileDeleteView.as_view(), name='professional_profile_delete'),

    # Qualification Management URLs
    path('qualifications/', QualificationListView.as_view(), name='qualification_list'),
    path('qualifications/add/', QualificationCreateView.as_view(), name='qualification_create'),
    path('qualifications/<int:pk>/edit/', QualificationUpdateView.as_view(), name='qualification_update'),
    path('qualifications/<int:pk>/delete/', QualificationDeleteView.as_view(), name='qualification_delete'),

    # Shift planning and management URLs (existing)
    path('ward/<slug:ward_name_slug>/<int:year>/<int:month>/', ShiftCalendarView.as_view(), name='shift_calendar'),
    path('ward/<slug:ward_name_slug>/<int:year>/<int:month>/<int:day>/daily/', DailyShiftView.as_view(), name='daily_shift_view'),
    path('ward/<slug:ward_name_slug>/<int:year>/<int:month>/<int:day>/shift/<int:shift_id>/plan/', ShiftAssignmentCreateView.as_view(), name='plan_shift'),
    path('ward/<slug:ward_name_slug>/<int:year>/<int:month>/<int:day>/plan/', ShiftAssignmentCreateView.as_view(), name='plan_shift_for_day'),
    path('plan/', ShiftAssignmentCreateView.as_view(), name='plan_shift_general'),
    path('ward/<slug:ward_name_slug>/<int:year>/<int:month>/<int:day>/shift/<int:shift_id>/edit/', ShiftAssignmentUpdateView.as_view(), name='edit_shift_plan'),
    path('ward/<slug:ward_name_slug>/<int:year>/<int:month>/<int:day>/shift/<int:shift_id>/delete/', ShiftAssignmentDeleteView.as_view(), name='delete_shift_plan'),

    # New: Automatic Schedule Generation Page
    path('generate-schedule/', AutomaticScheduleView.as_view(), name='generate_schedule_auto'),
]
