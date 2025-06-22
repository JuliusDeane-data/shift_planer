# shift_planer/views.py

from django.shortcuts import render, redirect, get_object_or_404
from django.views.generic import ListView, TemplateView, FormView, UpdateView, DeleteView, CreateView
from django.urls import reverse_lazy
from django.contrib import messages
from django.db import transaction

from shift_planer.models import Employee, Ward, Shift, ShiftAssignment, EmployeeAvailability, Absence, Qualification, ProfessionalProfile # ProfessionalProfile und Qualification hinzugefügt
import datetime
import calendar
from shift_planer.forms import ShiftAssignmentForm, EmployeeProfileForm, EmployeeAvailabilityForm, AbsenceForm, AutomaticScheduleForm
from .scheduler import ShiftScheduler  # Importiere den Scheduler

# Class-based view to display a list of all employees
class EmployeeListView(ListView):
    model = Employee
    template_name = 'shift_planer/employee_list.html'
    context_object_name = 'employees'

    def get_queryset(self):
        # Fetch related qualifications and allowed_shifts for efficiency
        return Employee.objects.prefetch_related('qualifications', 'allowed_shifts').all().order_by('last_name', 'first_name')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = 'Mitarbeiterliste'
        return context

# Home view for selecting ward and month/year for planning
class HomeView(TemplateView):
    template_name = 'shift_planer/home.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['wards'] = Ward.objects.all().order_by('name')
        
        today = datetime.date.today()
        context['current_year'] = today.year
        context['current_month'] = today.month
        context['months'] = [(i, datetime.date(2000, i, 1).strftime('%B')) for i in range(1, 13)]
        
        context['page_title'] = 'Schichtplanung Startseite'
        return context

    def post(self, request, *args, **kwargs):
        ward_id = request.POST.get('ward')
        year = request.POST.get('year')
        month = request.POST.get('month')

        if ward_id and year and month:
            try:
                ward = Ward.objects.get(id=ward_id)
                return redirect('shift_planer:shift_calendar', year=year, month=month, ward_name_slug=ward.slug)
            except Ward.DoesNotExist:
                pass
        
        return self.get(request, *args, **kwargs)


# View for displaying the shift calendar for a specific ward and month
class ShiftCalendarView(TemplateView):
    template_name = 'shift_planer/shift_calendar.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        year = self.kwargs['year']
        month = self.kwargs['month']
        ward_name_slug = self.kwargs['ward_name_slug']

        ward = get_object_or_404(Ward, slug=ward_name_slug)

        cal = calendar.Calendar()
        month_days = cal.itermonthdays2(year, month)

        calendar_data = []
        for day, weekday in month_days:
            if day != 0:
                calendar_data.append({
                    'day': day,
                    'date_obj': datetime.date(year, month, day),
                    'weekday': weekday,
                    'weekday_name': ['Mo', 'Di', 'Mi', 'Do', 'Fr', 'Sa', 'So'][weekday]
                })
        
        all_shifts = Shift.objects.all().order_by('start_time')

        start_date = datetime.date(year, month, 1)
        end_date = datetime.date(year, month, calendar.monthrange(year, month)[1])

        existing_assignments = ShiftAssignment.objects.filter(
            ward=ward,
            date__gte=start_date,
            date__lte=end_date
        ).select_related('employee', 'shift').order_by('date', 'shift__start_time', 'employee__last_name')

        assignments_by_day_shift = {}
        for assignment in existing_assignments:
            date_key = assignment.date
            shift_id_key = assignment.shift.id
            if date_key not in assignments_by_day_shift:
                assignments_by_day_shift[date_key] = {}
            if shift_id_key not in assignments_by_day_shift[date_key]:
                assignments_by_day_shift[date_key][shift_id_key] = []
            assignments_by_day_shift[date_key][shift_id_key].append(assignment)
        
        context.update({
            'page_title': f'Schichtplan für {ward.name} - {datetime.date(year, month, 1).strftime("%B %Y")}',
            'ward': ward,
            'ward_slug_for_urls': ward.slug,
            'year': year,
            'month': month,
            'calendar_data': calendar_data,
            'all_shifts': all_shifts,
            'assignments_by_day_shift': assignments_by_day_shift,
            # For navigation
            'prev_month': (month - 1) if month > 1 else 12,
            'prev_year': year if month > 1 else year - 1,
            'next_month': (month + 1) if month < 12 else 1,
            'next_year': year if month < 12 else year + 1,
        })
        return context

# View for displaying a daily shift overview for a specific ward and date
class DailyShiftView(TemplateView):
    template_name = 'shift_planer/daily_shift_view.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        year = self.kwargs['year']
        month = self.kwargs['month']
        day = self.kwargs['day']
        ward_name_slug = self.kwargs['ward_name_slug']

        ward = get_object_or_404(Ward, slug=ward_name_slug)

        try:
            selected_date = datetime.date(year, month, day)
        except ValueError:
            return redirect('shift_planer:home')

        # Order by shift start time, then employee for consistent display
        # NEU: prefetch_related professional_profile und shift__required_qualifications
        all_daily_assignments = ShiftAssignment.objects.filter(
            ward=ward,
            date=selected_date
        ).select_related('employee__professional_profile', 'shift').prefetch_related('shift__required_qualifications', 'employee__qualifications').order_by('shift__start_time', 'employee__last_name')


        all_shifts = Shift.objects.all().order_by('start_time')
        
        shifts_data = {}
        # Hol alle kritischen Qualifikationen aus der DB
        critical_qualifications_db = set(Qualification.objects.filter(is_critical=True).values_list('pk', flat=True))

        for shift in all_shifts:
            assignments_for_this_shift = [
                assignment for assignment in all_daily_assignments if assignment.shift == shift
            ]

            assigned_professional_nurses_count = 0
            assigned_total_staff_count = len(assignments_for_this_shift)
            is_critical_qual_needed = shift.required_qualifications.filter(is_critical=True).exists()
            is_critical_qual_met = False

            for assignment in assignments_for_this_shift:
                # Prüfe für Pflegefachkräfte (basierend auf professional_profile)
                if hasattr(assignment.employee, 'professional_profile') and assignment.employee.professional_profile and assignment.employee.professional_profile.counts_towards_staff_ratio:
                    assigned_professional_nurses_count += 1
                
                # Prüfe, ob die kritische Qualifikation erfüllt ist
                if is_critical_qual_needed:
                    employee_has_critical_qual = any(
                        q.pk in critical_qualifications_db for q in assignment.employee.qualifications.all()
                    )
                    if employee_has_critical_qual:
                        is_critical_qual_met = True
            
            # Berechne die benötigten Pflegefachkräfte basierend auf der Patientenzahl der Station und dem Schichttyp
            required_staff_for_patients = (ward.current_patients + 2) // 3 if ward.current_patients > 0 else 0
            
            min_staff_for_shift_type = 0
            if shift.name == 'EARLY':
                min_staff_for_shift_type = ward.min_staff_early_shift
            elif shift.name == 'LATE':
                min_staff_for_shift_type = ward.min_staff_late_shift
            elif shift.name == 'NIGHT':
                min_staff_for_shift_type = ward.min_staff_night_shift
            
            required_professional_nurses_count = max(required_staff_for_patients, min_staff_for_shift_type)

            shifts_data[shift.get_name_display()] = {
                'shift_pk': shift.pk,
                'shift_start_time': shift.start_time,
                'shift_end_time': shift.end_time,
                'assignments': assignments_for_this_shift,
                'assigned_professional_nurses_count': assigned_professional_nurses_count,
                'required_professional_nurses_count': required_professional_nurses_count,
                'assigned_total_staff_count': assigned_total_staff_count,
                'is_critical_qual_needed': is_critical_qual_needed,
                'is_critical_qual_met': is_critical_qual_met,
            }


        context.update({
            'page_title': f'Schichtplan für {ward.name} - {selected_date.strftime("%d.%m.%Y")}',
            'ward': ward,
            'selected_date': selected_date,
            'shifts_data': shifts_data, # Die neuen strukturierten Daten
            # For navigation back to month view
            'month_link_year': year,
            'month_link_month': month,
        })
        return context

# View for creating a Shift Assignment for multiple employees for a specific shift
class ShiftAssignmentCreateView(FormView):
    form_class = ShiftAssignmentForm
    template_name = 'shift_planer/shift_assignment_form.html'

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['request'] = self.request # Pass request to the form for messages and context.
        return kwargs

    def get_initial(self):
        initial = super().get_initial()
        ward_slug = self.kwargs.get('ward_name_slug')
        year = self.kwargs.get('year')
        month = self.kwargs.get('month')
        day = self.kwargs.get('day')
        shift_id = self.kwargs.get('shift_id')

        if ward_slug:
            initial['ward'] = get_object_or_404(Ward, slug=ward_slug)
        if year and month and day:
            try:
                initial['date'] = datetime.date(int(year), int(month), int(day))
            except ValueError:
                pass
        if shift_id:
            try:
                initial['shift'] = get_object_or_404(Shift, id=shift_id)
            except ValueError:
                pass
        return initial

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        ward_name_slug = self.kwargs.get('ward_name_slug')
        year = self.kwargs.get('year')
        month = self.kwargs.get('month')
        day = self.kwargs.get('day')
        shift_id = self.kwargs.get('shift_id')

        ward = None
        shift = None
        current_date = None # Initialize to None

        if ward_name_slug:
            ward = get_object_or_404(Ward, slug=ward_name_slug)
        if year and month and day:
            try:
                current_date = datetime.date(int(year), int(month), int(day))
            except ValueError:
                pass
        if shift_id:
            shift = get_object_or_404(Shift, id=shift_id)

        context['page_title'] = 'Schicht planen'
        context['ward'] = ward
        context['date'] = current_date # Ensure this is passed to context
        context['shift'] = shift
        
        # NEU: employee_display_data direkt in der View erstellen und an den Kontext übergeben
        employees_for_display = Employee.objects.prefetch_related('qualifications', 'allowed_shifts', 'professional_profile').all().order_by('last_name', 'first_name')
        employee_display_data = {}
        for emp in employees_for_display:
            # Stelle sicher, dass die Qualifikationen als Liste von Namen und nicht als Objekte übergeben werden
            qualifications_list = [q.name for q in emp.qualifications.all()]
            # Stelle sicher, dass die erlaubten Schichten als Liste von Namen übergeben werden
            allowed_shifts_list = [s.get_name_display() for s in emp.allowed_shifts.all()]

            employee_display_data[emp.pk] = {
                'first_name': emp.first_name,
                'last_name': emp.last_name,
                'professional_profile_name': emp.professional_profile.name if emp.professional_profile else '', # Neu
                'qualifications': qualifications_list,
                'allowed_shifts': allowed_shifts_list,
            }
        context['employee_display_data'] = employee_display_data

        if ward and year and month and day:
            context['back_to_day_url'] = reverse_lazy('shift_planer:daily_shift_view',
                                                kwargs={'ward_name_slug': ward.slug, 'year': year, 'month': month, 'day': day})
        if ward and year and month:
            context['back_to_month_url'] = reverse_lazy('shift_planer:shift_calendar', 
                                                kwargs={'ward_name_slug': ward.slug, 'year': year, 'month': month})
        return context

    def form_valid(self, form):
        # Retrieve ward, date, shift from cleaned_data (or request.POST/kwargs if disabled)
        ward = form.cleaned_data.get('ward') # Already a Ward object due to ModelChoiceField
        date = form.cleaned_data.get('date') # Already a Date object
        shift = form.cleaned_data.get('shift') # Already a Shift object

        professional_nurses = form.cleaned_data.get('professional_nurses')
        nursing_assistants = form.cleaned_data.get('nursing_assistants')

        all_selected_employees = list(professional_nurses) + list(nursing_assistants)

        with transaction.atomic():
            ShiftAssignment.objects.filter(
                ward=ward,
                date=date,
                shift=shift
            ).delete()
            
            new_assignments = []
            for employee in all_selected_employees:
                new_assignments.append(ShiftAssignment(
                    employee=employee,
                    shift=shift,
                    ward=ward,
                    date=date,
                    status=form.cleaned_data.get('status') # Use status from cleaned_data
                ))
            
            ShiftAssignment.objects.bulk_create(new_assignments)

        messages.success(self.request, f"Schicht für {ward.name} am {date.strftime('%d.%m.%Y')} - {shift.get_name_display()} erfolgreich geplant!")
        return redirect(self.get_success_url())

    def get_success_url(self):
        ward_slug = self.kwargs.get('ward_name_slug')
        year = self.kwargs.get('year')
        month = self.kwargs.get('month')
        day = self.kwargs.get('day')

        if ward_slug and year and month and day:
            return reverse_lazy('shift_planer:daily_shift_view', 
                                kwargs={'ward_name_slug': ward_slug, 'year': year, 'month': month, 'day': day})
        elif ward_slug and year and month:
            return reverse_lazy('shift_planer:shift_calendar', 
                                kwargs={'ward_name_slug': ward_slug, 'year': year, 'month': month})
        else:
            return reverse_lazy('shift_planer:home')

# View for updating a whole shift's assignments
class ShiftAssignmentUpdateView(FormView):
    form_class = ShiftAssignmentForm
    template_name = 'shift_planer/shift_assignment_form.html'

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['request'] = self.request # Pass request to the form
        return kwargs

    def get_initial(self):
        initial = super().get_initial()
        
        ward_slug = self.kwargs.get('ward_name_slug')
        year = self.kwargs.get('year')
        month = self.kwargs.get('month')
        day = self.kwargs.get('day')
        shift_id = self.kwargs.get('shift_id')

        ward = get_object_or_404(Ward, slug=ward_slug)
        date = datetime.date(year, month, day)
        shift = get_object_or_404(Shift, pk=shift_id)

        initial['ward'] = ward
        initial['date'] = date
        initial['shift'] = shift
        
        professional_nurse_pks = []
        nursing_assistant_pks = []
        
        existing_assignments = ShiftAssignment.objects.filter(
            ward=ward,
            date=date,
            shift=shift
        ).select_related('employee__professional_profile').prefetch_related('employee__qualifications') # NEU: prefetch_related professional_profile

        current_status = 'PLANNED'
        if existing_assignments.exists():
            current_status = existing_assignments.first().status

        initial['status'] = current_status

        for assignment in existing_assignments:
            # NEU: Prüfen auf professional_profile
            if hasattr(assignment.employee, 'professional_profile') and assignment.employee.professional_profile and assignment.employee.professional_profile.counts_towards_staff_ratio:
                professional_nurse_pks.append(assignment.employee.pk)
            else:
                nursing_assistant_pks.append(assignment.employee.pk)

        initial['professional_nurses'] = professional_nurse_pks
        initial['nursing_assistants'] = nursing_assistant_pks
        
        return initial

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        
        ward_slug = self.kwargs.get('ward_name_slug')
        year = self.kwargs.get('year')
        month = self.kwargs.get('month')
        day = self.kwargs.get('day')
        shift_id = self.kwargs.get('shift_id')

        ward = get_object_or_404(Ward, slug=ward_slug)
        date = datetime.date(year, month, day)
        shift = get_object_or_404(Shift, pk=shift_id)

        context['page_title'] = f"Schicht bearbeiten für {ward.name} am {date.strftime('%d.%m.%Y')} - {shift.get_name_display()}"
        context['ward'] = ward
        context['date'] = date
        context['shift'] = shift

        # NEU: employee_display_data direkt in der View erstellen und an den Kontext übergeben
        employees_for_display = Employee.objects.prefetch_related('qualifications', 'allowed_shifts', 'professional_profile').all().order_by('last_name', 'first_name')
        employee_display_data = {}
        for emp in employees_for_display:
            qualifications_list = [q.name for q in emp.qualifications.all()]
            allowed_shifts_list = [s.get_name_display() for s in emp.allowed_shifts.all()]
            
            employee_display_data[emp.pk] = {
                'first_name': emp.first_name,
                'last_name': emp.last_name,
                'professional_profile_name': emp.professional_profile.name if emp.professional_profile else '', # Neu
                'qualifications': qualifications_list,
                'allowed_shifts': allowed_shifts_list,
            }
        context['employee_display_data'] = employee_display_data

        context['back_to_day_url'] = reverse_lazy('shift_planer:daily_shift_view',
                                            kwargs={'ward_name_slug': ward.slug, 
                                                    'year': date.year, 
                                                    'month': date.month, 
                                                    'day': date.day})
        return context

    def form_valid(self, form):
        ward_pk = self.request.POST.get('ward')
        date_str = self.request.POST.get('date')
        shift_pk = self.request.POST.get('shift')
        status = form.cleaned_data.get('status')

        ward = get_object_or_404(Ward, pk=ward_pk)
        date = datetime.date.fromisoformat(date_str)
        shift = get_object_or_404(Shift, pk=shift_pk)

        professional_nurses = form.cleaned_data.get('professional_nurses')
        nursing_assistants = form.cleaned_data.get('nursing_assistants')

        all_selected_employees = list(professional_nurses) + list(nursing_assistants)

        with transaction.atomic():
            ShiftAssignment.objects.filter(
                ward=ward,
                date=date,
                shift=shift
            ).delete()
            
            new_assignments = []
            for employee in all_selected_employees:
                new_assignments.append(ShiftAssignment(
                    employee=employee,
                    shift=shift,
                    ward=ward,
                    date=date,
                    status=status
                ))
            
            ShiftAssignment.objects.bulk_create(new_assignments)

        messages.success(self.request, f"Schicht für {ward.name} am {date.strftime('%d.%m.%Y')} - {shift.get_name_display()} erfolgreich aktualisiert!")
        return redirect(self.get_success_url())

    def get_success_url(self):
        ward_slug = self.kwargs.get('ward_name_slug')
        year = self.kwargs.get('year')
        month = self.kwargs.get('month')
        day = self.kwargs.get('day')

        return reverse_lazy('shift_planer:daily_shift_view', 
                            kwargs={'ward_name_slug': ward_slug, 
                                    'year': year, 
                                    'month': month, 
                                    'day': day})


# View for deleting a whole shift's assignments
class ShiftAssignmentDeleteView(DeleteView):
    model = ShiftAssignment
    template_name = 'shift_planer/shift_assignment_confirm_delete.html'

    def get_object(self, queryset=None):
        ward_slug = self.kwargs.get('ward_name_slug')
        year = self.kwargs.get('year')
        month = self.kwargs.get('month')
        day = self.kwargs.get('day')
        shift_id = self.kwargs.get('shift_id')

        ward = get_object_or_404(Ward, slug=ward_slug)
        date = datetime.date(year, month, day)
        shift = get_object_or_404(Shift, pk=shift_id)

        return {
            'ward': ward,
            'date': date,
            'shift': shift,
            'assignments_count': ShiftAssignment.objects.filter(ward=ward, date=date, shift=shift).count()
        }

    def post(self, request, *args, **kwargs):
        obj_data = self.get_object()
        ward = obj_data['ward']
        date = obj_data['date']
        shift = obj_data['shift']

        with transaction.atomic():
            deleted_count, _ = ShiftAssignment.objects.filter(
                ward=ward,
                date=date,
                shift=shift
            ).delete()
        
        messages.success(self.request, f"{deleted_count} Zuweisungen für {ward.name} am {date.strftime('%d.%m.%Y')} - {shift.get_name_display()} erfolgreich gelöscht.")
        return redirect(self.get_success_url())

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        obj_data = self.get_object()
        context['page_title'] = f"Schichtplan löschen für {obj_data['ward'].name} am {obj_data['date'].strftime('%d.%m.%Y')} - {obj_data['shift'].get_name_display()}"
        context['ward'] = obj_data['ward']
        context['date'] = obj_data['date']
        context['shift'] = obj_data['shift']
        context['assignments_count'] = obj_data['assignments_count']
        return context

    def get_success_url(self):
        ward_slug = self.kwargs.get('ward_name_slug')
        year = self.kwargs.get('year')
        month = self.kwargs.get('month')
        day = self.kwargs.get('day')

        return reverse_lazy('shift_planer:daily_shift_view', 
                            kwargs={'ward_name_slug': ward_slug, 
                                    'year': year, 
                                    'month': month, 
                                    'day': day})


# View zum Bearbeiten eines bestehenden Mitarbeiters
class EmployeeUpdateView(UpdateView):
    model = Employee
    form_class = EmployeeProfileForm
    template_name = 'shift_planer/employee_profile_form.html'
    context_object_name = 'employee'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = f"Mitarbeiter bearbeiten: {self.object.first_name} {self.object.last_name}"
        context['back_to_employee_list_url'] = reverse_lazy('shift_planer:employee_list')
        return context

    def get_success_url(self):
        messages.success(self.request, f"Mitarbeiter {self.object.first_name} {self.object.last_name} erfolgreich aktualisiert.")
        return reverse_lazy('shift_planer:employee_list')


# View zum Hinzufügen eines neuen Mitarbeiters
class EmployeeCreateView(CreateView):
    model = Employee
    form_class = EmployeeProfileForm # Wiederverwendung des bestehenden Formulars
    template_name = 'shift_planer/employee_profile_form.html' # Wiederverwendung des bestehenden Templates
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = "Neuen Mitarbeiter hinzufügen"
        context['back_to_list_url'] = reverse_lazy('shift_planer:employee_list')
        return context

    def form_valid(self, form):
        messages.success(self.request, f"Mitarbeiter {form.instance.first_name} {form.instance.last_name} erfolgreich hinzugefügt.")
        return super().form_valid(form)

    def get_success_url(self):
        return reverse_lazy('shift_planer:employee_list')

# View zum Löschen eines Mitarbeiters
class EmployeeDeleteView(DeleteView):
    model = Employee
    template_name = 'shift_planer/confirm_delete.html' # Wiederverwendung des generischen Lösch-Templates
    context_object_name = 'employee' # Kann im Template mit 'object' oder 'employee' zugegriffen werden

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = "Mitarbeiter löschen"
        context['object_description'] = f"Mitarbeiter '{self.object.first_name} {self.object.last_name}'"
        context['back_to_list_url'] = reverse_lazy('shift_planer:employee_list') # Link zurück zur Mitarbeiterliste
        return context

    def form_valid(self, form):
        messages.success(self.request, f"Mitarbeiter '{self.object.first_name} {self.object.last_name}' erfolgreich gelöscht.")
        return super().form_valid(form)

    def get_success_url(self):
        return reverse_lazy('shift_planer:employee_list')


# New: Employee Profile View (Dashboard for Availability/Absence)
class EmployeeProfileOverview(TemplateView):
    template_name = 'shift_planer/employee_profile_overview.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        employee_id = self.kwargs['pk']
        employee = get_object_or_404(Employee, pk=employee_id)

        context['employee'] = employee
        context['page_title'] = f"Profil von {employee.first_name} {employee.last_name}"
        
        # Fetch current availabilities and absences for the employee
        context['availabilities'] = EmployeeAvailability.objects.filter(employee=employee).order_by('date')
        context['absences'] = Absence.objects.filter(employee=employee).order_by('start_date')

        context['back_to_employee_list_url'] = reverse_lazy('shift_planer:employee_list')
        return context


# New: Views for EmployeeAvailability
class EmployeeAvailabilityCreateView(CreateView):
    model = EmployeeAvailability
    form_class = EmployeeAvailabilityForm
    template_name = 'shift_planer/employee_availability_form.html'

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        # Pass an instance with the employee pre-filled. ModelForm uses this.
        kwargs['instance'] = EmployeeAvailability(employee_id=self.kwargs['employee_pk'])
        return kwargs

    def form_valid(self, form):
        # Ensure employee is set on the instance before saving
        form.instance.employee = get_object_or_404(Employee, pk=self.kwargs['employee_pk'])
        
        # Check for existing availability for the same employee and date before saving
        existing_availability = EmployeeAvailability.objects.filter(
            employee=form.instance.employee,
            date=form.instance.date
        ).first()

        if existing_availability:
            # If exists, update it instead of creating new
            existing_availability.is_available = form.cleaned_data['is_available']
            existing_availability.save(update_fields=['is_available'])
            messages.success(self.request, f"Verfügbarkeit für {form.instance.employee.first_name} {form.instance.employee.last_name} am {form.instance.date.strftime('%d.%m.%Y')} aktualisiert.")
            return redirect(self.get_success_url())
        else:
            # If not exists, create new
            messages.success(self.request, f"Verfügbarkeit für {form.instance.employee.first_name} {form.instance.employee.last_name} am {form.instance.date.strftime('%d.%m.%Y')} erstellt.")
            return super().form_valid(form) # Calls form.save() internally

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        employee = get_object_or_404(Employee, pk=self.kwargs['employee_pk'])
        context['employee'] = employee
        context['page_title'] = f"Verfügbarkeit hinzufügen für {employee.first_name} {employee.last_name}"
        # Korrigiert: Verwende kwargs={'pk': ...}
        context['back_to_profile_url'] = reverse_lazy('shift_planer:employee_profile', kwargs={'pk': employee.pk})
        return context

    def get_success_url(self):
        # Korrigiert: Verwende kwargs={'pk': ...}
        return reverse_lazy('shift_planer:employee_profile', kwargs={'pk': self.kwargs['employee_pk']})


class EmployeeAvailabilityUpdateView(UpdateView):
    model = EmployeeAvailability
    form_class = EmployeeAvailabilityForm
    template_name = 'shift_planer/employee_availability_form.html'
    context_object_name = 'availability'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        employee = self.get_object().employee
        context['employee'] = employee
        context['page_title'] = f"Verfügbarkeit bearbeiten für {employee.first_name} {employee.last_name}"
        # Korrigiert: Verwende kwargs={'pk': ...}
        context['back_to_profile_url'] = reverse_lazy('shift_planer:employee_profile', kwargs={'pk': employee.pk})
        return context

    def get_success_url(self):
        messages.success(self.request, f"Verfügbarkeit für {self.object.employee.first_name} {self.object.employee.last_name} am {self.object.date.strftime('%d.%m.%Y')} erfolgreich aktualisiert.")
        # Korrigiert: Verwende kwargs={'pk': ...}
        return reverse_lazy('shift_planer:employee_profile', kwargs={'pk': self.object.employee.pk})


class EmployeeAvailabilityDeleteView(DeleteView):
    model = EmployeeAvailability
    template_name = 'shift_planer/confirm_delete.html' # Generic confirmation template
    context_object_name = 'availability'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        employee = self.get_object().employee
        context['employee'] = employee
        context['page_title'] = "Verfügbarkeit löschen"
        context['object_description'] = f"Verfügbarkeit für {employee.first_name} {employee.last_name} am {self.object.date.strftime('%d.%m.%Y')} (Verfügbar: {'Ja' if self.object.is_available else 'Nein'})"
        # Korrigiert: Verwende kwargs={'pk': ...}
        context['back_to_profile_url'] = reverse_lazy('shift_planer:employee_profile', kwargs={'pk': employee.pk})
        return context

    def get_success_url(self):
        messages.success(self.request, "Verfügbarkeit erfolgreich gelöscht.")
        # Korrigiert: Verwende kwargs={'pk': ...}
        return reverse_lazy('shift_planer:employee_profile', kwargs={'pk': self.object.employee.pk})


# New: Views for Absence
class AbsenceCreateView(CreateView):
    model = Absence
    form_class = AbsenceForm
    template_name = 'shift_planer/absence_form.html'

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        # Pass an instance with the employee pre-filled. ModelForm uses this.
        kwargs['instance'] = Absence(employee_id=self.kwargs['employee_pk'])
        return kwargs

    def form_valid(self, form):
        # Ensure employee is set on the instance before saving
        form.instance.employee = get_object_or_404(Employee, pk=self.kwargs['employee_pk'])
        messages.success(self.request, f"Abwesenheit für {form.instance.employee.first_name} {form.instance.employee.last_name} ({form.instance.get_type_display()}) von {form.instance.start_date.strftime('%d.%m.%Y')} bis {form.instance.end_date.strftime('%d.%m.%Y')} erstellt.")
        return super().form_valid(form) # Calls form.save() internally

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        employee = get_object_or_404(Employee, pk=self.kwargs['employee_pk'])
        context['employee'] = employee
        context['page_title'] = f"Abwesenheit hinzufügen für {employee.first_name} {employee.last_name}"
        # Korrigiert: Verwende kwargs={'pk': ...}
        context['back_to_profile_url'] = reverse_lazy('shift_planer:employee_profile', kwargs={'pk': employee.pk})
        return context

    def get_success_url(self):
        # Korrigiert: Verwende kwargs={'pk': ...}
        return reverse_lazy('shift_planer:employee_profile', kwargs={'pk': self.kwargs['employee_pk']})


class AbsenceUpdateView(UpdateView):
    model = Absence
    form_class = AbsenceForm
    template_name = 'shift_planer/absence_form.html'
    context_object_name = 'absence'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        employee = self.get_object().employee
        context['employee'] = employee
        context['page_title'] = f"Abwesenheit bearbeiten für {employee.first_name} {employee.last_name}"
        # Korrigiert: Verwende kwargs={'pk': ...}
        context['back_to_profile_url'] = reverse_lazy('shift_planer:employee_profile', kwargs={'pk': employee.pk})
        return context

    def get_success_url(self):
        messages.success(self.request, f"Abwesenheit für {self.object.employee.first_name} {self.object.employee.last_name} erfolgreich aktualisiert.")
        # Korrigiert: Verwende kwargs={'pk': ...}
        return reverse_lazy('shift_planer:employee_profile', kwargs={'pk': self.object.employee.pk})


class AbsenceDeleteView(DeleteView):
    model = Absence
    template_name = 'shift_planer/confirm_delete.html' # Generic confirmation template
    context_object_name = 'absence'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        employee = self.get_object().employee
        context['employee'] = employee
        context['page_title'] = "Abwesenheit löschen"
        context['object_description'] = f"Abwesenheit für {employee.first_name} {employee.last_name} ({self.object.get_absence_type_display()}) von {self.object.start_date.strftime('%d.%m.%Y')} bis {self.object.end_date.strftime('%d.%m.%Y')}"
        # Korrigiert: Verwende kwargs={'pk': ...}
        context['back_to_profile_url'] = reverse_lazy('shift_planer:employee_profile', kwargs={'pk': employee.pk})
        return context

    def get_success_url(self):
        messages.success(self.request, "Abwesenheit erfolgreich gelöscht.")
        # Korrigiert: Verwende kwargs={'pk': ...}
        return reverse_lazy('shift_planer:employee_profile', kwargs={'pk': self.object.employee.pk})

# --- VIEWS FÜR PROFESSIONALPROFILE VERWALTUNG ---

# Liste aller Berufsprofile
class ProfessionalProfileListView(ListView):
    model = ProfessionalProfile
    template_name = 'shift_planer/professional_profile_list.html'
    context_object_name = 'professional_profiles'
    ordering = ['name']

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = 'Berufsprofile'
        return context

# Erstellen eines neuen Berufsprofils
class ProfessionalProfileCreateView(CreateView):
    model = ProfessionalProfile
    fields = ['name', 'description', 'counts_towards_staff_ratio'] # Felder, die im Formular angezeigt werden
    template_name = 'shift_planer/professional_profile_form.html'
    success_url = reverse_lazy('shift_planer:professional_profile_list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = 'Neues Berufsprofil erstellen'
        context['back_to_list_url'] = reverse_lazy('shift_planer:professional_profile_list')
        return context

    def form_valid(self, form):
        messages.success(self.request, f"Berufsprofil '{form.instance.name}' erfolgreich erstellt.")
        return super().form_valid(form)

# Bearbeiten eines bestehenden Berufsprofils
class ProfessionalProfileUpdateView(UpdateView):
    model = ProfessionalProfile
    fields = ['name', 'description', 'counts_towards_staff_ratio']
    template_name = 'shift_planer/professional_profile_form.html'
    context_object_name = 'professional_profile'
    success_url = reverse_lazy('shift_planer:professional_profile_list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = f"Berufsprofil bearbeiten: {self.object.name}"
        context['back_to_list_url'] = reverse_lazy('shift_planer:professional_profile_list')
        return context

    def form_valid(self, form):
        messages.success(self.request, f"Berufsprofil '{form.instance.name}' erfolgreich aktualisiert.")
        return super().form_valid(form)

# Löschen eines Berufsprofils
class ProfessionalProfileDeleteView(DeleteView):
    model = ProfessionalProfile
    template_name = 'shift_planer/confirm_delete.html' # Wiederverwendung des generischen Lösch-Templates
    context_object_name = 'professional_profile'
    success_url = reverse_lazy('shift_planer:professional_profile_list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = 'Berufsprofil löschen'
        context['object_description'] = f"Berufsprofil '{self.object.name}'"
        context['back_to_list_url'] = reverse_lazy('shift_planer:professional_profile_list')
        return context

    def form_valid(self, form):
        messages.success(self.request, f"Berufsprofil '{self.object.name}' erfolgreich gelöscht.")
        return super().form_valid(form)

# --- VIEWS FÜR QUALIFIKATIONSVERWALTUNG ---

# Liste aller Qualifikationen
class QualificationListView(ListView):
    model = Qualification
    template_name = 'shift_planer/qualification_list.html'
    context_object_name = 'qualifications'
    ordering = ['name']

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = 'Qualifikationen'
        return context

# Erstellen einer neuen Qualifikation
class QualificationCreateView(CreateView):
    model = Qualification
    fields = ['name', 'description', 'is_critical'] # Felder, die im Formular angezeigt werden
    template_name = 'shift_planer/qualification_form.html'
    success_url = reverse_lazy('shift_planer:qualification_list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = 'Neue Qualifikation erstellen'
        context['back_to_list_url'] = reverse_lazy('shift_planer:qualification_list')
        return context

    def form_valid(self, form):
        messages.success(self.request, f"Qualifikation '{form.instance.name}' erfolgreich erstellt.")
        return super().form_valid(form)

# Bearbeiten einer bestehenden Qualifikation
class QualificationUpdateView(UpdateView):
    model = Qualification
    fields = ['name', 'description', 'is_critical']
    template_name = 'shift_planer/qualification_form.html'
    context_object_name = 'qualification'
    success_url = reverse_lazy('shift_planer:qualification_list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = f"Qualifikation bearbeiten: {self.object.name}"
        context['back_to_list_url'] = reverse_lazy('shift_planer:qualification_list')
        return context

    def form_valid(self, form):
        messages.success(self.request, f"Qualifikation '{form.instance.name}' erfolgreich aktualisiert.")
        return super().form_valid(form)

# Löschen einer Qualifikation
class QualificationDeleteView(DeleteView):
    model = Qualification
    template_name = 'shift_planer/confirm_delete.html' # Wiederverwendung des generischen Lösch-Templates
    context_object_name = 'qualification'
    success_url = reverse_lazy('shift_planer:qualification_list')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = 'Qualifikation löschen'
        context['object_description'] = f"Qualifikation '{self.object.name}'"
        context['back_to_list_url'] = reverse_lazy('shift_planer:qualification_list')
        return context

    def form_valid(self, form):
        messages.success(self.request, f"Qualifikation '{self.object.name}' erfolgreich gelöscht.")
        return super().form_valid(form)

# New view for automatic schedule generation
class AutomaticScheduleView(FormView):
    template_name = 'shift_planer/automatic_schedule_form.html'
    form_class = AutomaticScheduleForm
    success_url = reverse_lazy('shift_planer:home') # Redirect after successful generation

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = "Automatische Dienstplanerstellung"
        return context

    def form_valid(self, form):
        ward = form.cleaned_data['ward']
        year = form.cleaned_data['year']
        month = int(form.cleaned_data['month'])

        min_rest_hours = form.cleaned_data['min_rest_hours']
        max_consecutive_shifts = form.cleaned_data['max_consecutive_shifts']
        overwrite_existing = form.cleaned_data['overwrite_existing']

        # Initialize the scheduler with parameters from the form
        scheduler = ShiftScheduler(min_rest_hours, max_consecutive_shifts)
        
        # Call the generate_schedule method
        result = scheduler.generate_schedule(
            year=year, 
            month=month, 
            ward_slug=ward.slug, 
            overwrite=overwrite_existing
        )

        # Add messages based on the scheduler's result
        if result["success"]:
            messages.success(self.request, result["message"])
            # Add detailed logs as info messages
            for log_msg in scheduler.get_logs():
                if "[ERROR]" in log_msg:
                    messages.error(self.request, log_msg)
                elif "[WARNING]" in log_msg:
                    messages.warning(self.request, log_msg)
                else:
                    messages.info(self.request, log_msg)
            
            # Redirect to the generated calendar view
            return redirect('shift_planer:shift_calendar', 
                            ward_name_slug=ward.slug, 
                            year=year, 
                            month=month)
        else:
            messages.error(self.request, result["message"])
            # Add detailed logs as error messages if generation failed
            for log_msg in scheduler.get_logs():
                messages.error(self.request, log_msg)
            return self.form_invalid(form) # Re-render the form with errors