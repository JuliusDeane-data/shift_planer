# shift_planer/forms.py

from django import forms
from django.core.exceptions import ValidationError
from shift_planer.models import ShiftAssignment, Employee, Ward, Shift, Absence, EmployeeAvailability, Qualification, ProfessionalProfile
import datetime
from django.db.models import Q # For complex queries

class ShiftAssignmentForm(forms.ModelForm):
    # Form fields for planning a whole shift
    # No direct 'employee'-field anymore, instead multiple selection for roles

    ward = forms.ModelChoiceField(
        queryset=Ward.objects.all().order_by('name'),
        label="Station",
        empty_label="--- Station auswählen ---",
        widget=forms.Select(attrs={'class': 'mt-1 block w-full pl-3 pr-10 py-2 text-base border-gray-300 focus:outline-none focus:ring-blue-500 focus:border-blue-500 sm:text-sm rounded-md shadow-sm'})
    )
    
    date = forms.DateField(
        label="Datum",
        widget=forms.DateInput(attrs={'type': 'date', 'class': 'mt-1 block w-full pl-3 pr-3 py-2 text-base border-gray-300 focus:outline-none focus:ring-blue-500 focus:border-blue-500 sm:text-sm rounded-md shadow-sm'}),
        initial=datetime.date.today
    )

    shift = forms.ModelChoiceField(
        queryset=Shift.objects.all().order_by('start_time'),
        label="Schicht",
        empty_label="--- Schicht auswählen ---",
        widget=forms.Select(attrs={'class': 'mt-1 block w-full pl-3 pr-10 py-2 text-base border-gray-300 focus:outline-none focus:ring-blue-500 focus:border-blue-500 sm:text-sm rounded-md shadow-sm'})
    )

    # Korrigiert: widget zu CheckboxSelectMultiple geändert
    professional_nurses = forms.ModelMultipleChoiceField(
        queryset=Employee.objects.filter(professional_profile__counts_towards_staff_ratio=True).distinct().order_by('last_name', 'first_name'),
        label="Pflegefachkräfte",
        required=False,
        widget=forms.CheckboxSelectMultiple(attrs={'class': 'h-4 w-4 text-blue-600 focus:ring-blue-500 border-gray-300 rounded'})
    )

    # Korrigiert: widget zu CheckboxSelectMultiple geändert
    nursing_assistants = forms.ModelMultipleChoiceField(
        queryset=Employee.objects.filter(professional_profile__counts_towards_staff_ratio=False).distinct().order_by('last_name', 'first_name'),
        label="Pflegehelfer",
        required=False,
        widget=forms.CheckboxSelectMultiple(attrs={'class': 'h-4 w-4 text-blue-600 focus:ring-blue-500 border-gray-300 rounded'})
    )

    status = forms.ChoiceField(
        choices=ShiftAssignment.STATUS_CHOICES, # Choices from your model
        label="Status",
        widget=forms.Select(attrs={'class': 'mt-1 block w-full pl-3 pr-10 py-2 text-base border-gray-300 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500 sm:text-sm rounded-md shadow-sm'})
    )

    class Meta:
        model = ShiftAssignment
        fields = ['ward', 'date', 'shift', 'professional_nurses', 'nursing_assistants', 'status'] 


    def __init__(self, *args, **kwargs):
        # Das 'request'-Objekt aus kwargs entfernen, bevor es an super().__init__ übergeben wird.
        self.request = kwargs.pop('request', None) 

        initial_date = kwargs.pop('initial_date', None)
        initial_ward = kwargs.pop('initial_ward', None)
        initial_shift = kwargs.pop('initial_shift', None)
        
        if 'initial' not in kwargs:
            kwargs['initial'] = {}
        kwargs['initial'].setdefault('status', 'PLANNED')


        super().__init__(*args, **kwargs)

        if initial_date:
            self.fields['date'].initial = initial_date
            # self.fields['date'].widget.attrs['disabled'] = True # Entfernt, da wir hidden input verwenden
        
        if initial_ward:
            self.fields['ward'].initial = initial_ward
            # self.fields['ward'].widget.attrs['disabled'] = True # Entfernt, da wir hidden input verwenden

        # Nur wenn eine initial_shift übergeben wird, das Feld deaktivieren
        if initial_shift:
            self.fields['shift'].initial = initial_shift
            # self.fields['shift'].widget.attrs['disabled'] = True # Entfernt, da wir hidden input verwenden
        else:
            # Wenn keine initial_shift, sicherstellen, dass das Feld aktiviert ist (Standardverhalten)
            # und dass es als 'required' markiert ist, damit der Benutzer es auswählen muss.
            self.fields['shift'].required = True


        if 'professional_nurses' in self.initial:
            self.fields['professional_nurses'].initial = self.initial['professional_nurses']
        if 'nursing_assistants' in self.initial:
            self.fields['nursing_assistants'].initial = self.initial['nursing_assistants']

        if self.initial.get('ward') and self.initial.get('date') and self.initial.get('shift'):
            existing_assignments_for_shift = ShiftAssignment.objects.filter(
                ward=self.initial['ward'],
                date=self.initial['date'],
                shift=self.initial['shift']
            ).first()

            if existing_assignments_for_shift:
                self.fields['status'].initial = existing_assignments_for_shift.status
            else:
                self.fields['status'].initial = 'PLANNED'


    def clean(self):
        cleaned_data = super().clean()

        # Versuche, ward, date und shift immer aus den rohen POST-Daten zu holen,
        # da sie als versteckte Felder gesendet werden könnten, auch wenn sie deaktiviert sind.
        ward_pk_from_post = self.data.get('ward')
        date_str_from_post = self.data.get('date')
        shift_pk_from_post = self.data.get('shift')

        ward = None
        date = None
        shift = None

        try:
            if ward_pk_from_post:
                ward = Ward.objects.get(pk=ward_pk_from_post)
            if date_str_from_post:
                date = datetime.date.fromisoformat(date_str_from_post)
            # Nur versuchen, die Schicht zu bekommen, wenn ein Wert vorhanden ist
            if shift_pk_from_post:
                shift = Shift.objects.get(pk=shift_pk_from_post)
            elif self.cleaned_data.get('shift'): # Falls das Feld sichtbar war und ausgewählt wurde
                shift = self.cleaned_data.get('shift')
        except (ValueError, Ward.DoesNotExist, Shift.DoesNotExist) as e:
            # Dies fängt ungültige PKs oder Datumsformate aus versteckten Feldern ab
            # Oder wenn die Schicht nicht gefunden wurde.
            raise ValidationError(f"Fehler bei der Verarbeitung von Station, Datum oder Schicht: {e}. Bitte versuchen Sie es erneut.")

        # Überprüfe, ob die notwendigen Objekte vorhanden sind.
        if not all([ward, date]):
            errors = []
            if not ward: errors.append("Station")
            if not date: errors.append("Datum")
            raise ValidationError(f"{', '.join(errors)} muss ausgewählt werden.")
        
        # separate validation for shift, as it might be selected in the form
        if not shift:
             raise ValidationError("Schicht muss ausgewählt werden.")


        # Stelle sicher, dass diese gültigen Objekte in cleaned_data gesetzt werden,
        # damit form_valid sie verwenden kann und andere clean-Methoden darauf zugreifen können.
        cleaned_data['ward'] = ward
        cleaned_data['date'] = date
        cleaned_data['shift'] = shift
        
        professional_nurses = cleaned_data.get('professional_nurses', [])
        nursing_assistants = cleaned_data.get('nursing_assistants', [])
        status = cleaned_data.get('status') 

        critical_quals_in_db = Qualification.objects.filter(is_critical=True)
        shift_requires_critical_qual = shift.required_qualifications.filter(is_critical=True).exists()

        all_selected_employees = list(professional_nurses) + list(nursing_assistants)

        selected_employee_ids = [emp.id for emp in all_selected_employees]
        employees_data = Employee.objects.filter(id__in=selected_employee_ids).select_related('professional_profile').prefetch_related('qualifications', 'allowed_shifts')
        employees_map = {emp.id: emp for emp in employees_data}

        # --- Einzelne Mitarbeiterprüfungen (blockierende Fehler) ---
        for employee in all_selected_employees:
            emp_obj = employees_map.get(employee.id)
            if not emp_obj: continue

            # 1. Check Employee's Allowed Shifts
            if shift and not emp_obj.allowed_shifts.filter(pk=shift.pk).exists() and emp_obj.allowed_shifts.exists():
                raise ValidationError(
                    f"{emp_obj.first_name} {emp_obj.last_name} ist nicht für die Schicht '{shift.get_name_display()}' eingetragen."
                )

            # 2. Check for Employee Absence
            if Absence.objects.filter(
                employee=emp_obj,
                start_date__lte=date,
                end_date__gte=date,
                approved=True
            ).exists():
                raise ValidationError(
                    f"{emp_obj.first_name} {emp_obj.last_name} ist am {date} abwesend (Urlaub/Krankheit)."
                )

            # 3. Check for Employee Availability
            availability = EmployeeAvailability.objects.filter(employee=emp_obj, date=date).first()
            if availability and not availability.is_available:
                raise ValidationError(
                    f"{emp_obj.first_name} {emp_obj.last_name} ist am {date} nicht verfügbar."
                )

            # 4. Überlappende Schichten (am selben Tag, aber andere Schicht)
            overlapping_assignments = ShiftAssignment.objects.filter(
                employee=emp_obj,
                date=date
            )
            if self.initial.get('shift'):
                 overlapping_assignments = overlapping_assignments.exclude(
                     shift=self.initial['shift']
                 )

            if overlapping_assignments.exists():
                for existing_assignment in overlapping_assignments:
                    current_shift_start_dt = datetime.datetime.combine(date, shift.start_time)
                    current_shift_end_dt = datetime.datetime.combine(date, shift.end_time)

                    if shift.end_time < shift.start_time:
                        current_shift_end_dt += datetime.timedelta(days=1)

                    existing_shift_start_dt = datetime.datetime.combine(existing_assignment.date, existing_assignment.shift.start_time)
                    existing_shift_end_dt = datetime.datetime.combine(existing_assignment.date, existing_assignment.shift.end_time)
                    
                    if existing_assignment.shift.end_time < existing_assignment.shift.start_time:
                        existing_shift_end_dt += datetime.timedelta(days=1) 

                    if (current_shift_start_dt < existing_shift_end_dt and 
                        existing_shift_start_dt < current_shift_end_dt):
                        raise ValidationError(
                            f"{emp_obj.first_name} {emp_obj.last_name} ist bereits am {date} von "
                            f"'{existing_assignment.shift.get_name_display()}' ({existing_assignment.shift.start_time.strftime('%H:%M')}-{existing_assignment.shift.end_time.strftime('%H:%M')}) eingetragen. "
                            f"Ein Mitarbeiter kann nicht zu mehreren überlappenden Schichten zugewiesen werden."
                        )
            
            # 5. Eindeutigkeitsprüfung für (Mitarbeiter, Schicht, Datum) über alle Stationen
            conflicting_exact_match_assignments = ShiftAssignment.objects.filter(
                employee=emp_obj,
                shift=shift,
                date=date
            )
            
            if self.initial.get('ward') and self.initial.get('date') and self.initial.get('shift'):
                conflicting_exact_match_assignments = conflicting_exact_match_assignments.exclude(
                    ward=self.initial['ward'],
                    date=self.initial['date'],
                    shift=self.initial['shift']
                )
            
            if conflicting_exact_match_assignments.exists():
                conflict_assignment = conflicting_exact_match_assignments.first()
                raise ValidationError(
                    f"{emp_obj.first_name} {emp_obj.last_name} ist bereits für die Schicht '{shift.get_name_display()}' am {date} auf "
                    f"Station '{conflict_assignment.ward.name}' eingetragen. Ein Mitarbeiter kann nicht zweimal zur gleichen Schicht an einem Tag eingetragen werden (auch nicht auf verschiedenen Stationen)."
                )


        # --- Collective Shift-Level Checks (non-blocking warnings) ---
        staff_counting_towards_ratio = 0
        critical_qual_found_in_selection = False
        
        for employee in all_selected_employees:
            emp_obj = employees_map.get(employee.id)
            if not emp_obj: continue

            if hasattr(emp_obj, 'professional_profile') and emp_obj.professional_profile and emp_obj.professional_profile.counts_towards_staff_ratio:
                staff_counting_towards_ratio += 1
            
            if shift_requires_critical_qual:
                employee_has_critical_qual = any(q_db.pk in emp_obj.qualifications.values_list('pk', flat=True) for q_db in critical_quals_in_db)
                if employee_has_critical_qual:
                    critical_qual_found_in_selection = True

        # Rule 6: Critical Qualification (WARNING)
        if shift_requires_critical_qual and ward.current_patients > 0 and not critical_qual_found_in_selection:
            self.add_error(None, 
                f"WARNUNG: Es fehlt noch ein Mitarbeiter mit kritischer Qualifikation für die Schicht '{shift.get_name_display()}' auf Station '{ward.name}'.")

        # Rule 7: Patient-Staff Ratio (WARNING)
        if ward.current_patients > 0:
            required_staff_for_patients = (ward.current_patients + 2) // 3
            
            min_staff_for_shift_type = 0
            if shift.name == 'EARLY':
                min_staff_for_shift_type = ward.min_staff_early_shift
            elif shift.name == 'LATE':
                min_staff_for_shift_type = ward.min_staff_late_shift
            elif shift.name == 'NIGHT':
                min_staff_for_shift_type = ward.min_staff_night_shift
            
            total_min_required_professionals = max(required_staff_for_patients, min_staff_for_shift_type)

            if staff_counting_towards_ratio < total_min_required_professionals:
                self.add_error(None, 
                    f"WARNUNG: Nicht genügend Pflegefachkräfte für die Schicht '{shift.get_name_display()}' auf Station '{ward.name}'. "
                    f"Benötigt: mindestens {total_min_required_professionals} Pflegefachkräfte. Aktuell: {staff_counting_towards_ratio}.")
        
        cleaned_data['status'] = status
        return cleaned_data


class EmployeeProfileForm(forms.ModelForm):
    """
    Formular zum Erstellen und Bearbeiten von Mitarbeiterprofilen.
    Enthält alle Felder des Employee-Modells.
    """
    professional_profile = forms.ModelChoiceField(
        queryset=ProfessionalProfile.objects.all().order_by('name'),
        label="Berufsprofil",
        empty_label="--- Berufsprofil auswählen ---",
        widget=forms.Select(attrs={'class': 'mt-1 block w-full pl-3 pr-10 py-2 text-base border-gray-300 focus:outline-none focus:ring-blue-500 focus:border-blue-500 sm:text-sm rounded-md shadow-sm'})
    )

    qualifications = forms.ModelMultipleChoiceField(
        queryset=Qualification.objects.all().order_by('name'),
        label="Qualifikationen",
        required=False,
        widget=forms.SelectMultiple(attrs={'class': 'mt-1 block w-full pl-3 pr-10 py-2 text-base border-gray-300 focus:outline-none focus:ring-blue-500 focus:border-blue-500 sm:text-sm rounded-md shadow-sm h-48'})
    )

    allowed_shifts = forms.ModelMultipleChoiceField(
        queryset=Shift.objects.all().order_by('start_time'),
        label="Erlaubte Schichten",
        required=False,
        widget=forms.SelectMultiple(attrs={'class': 'mt-1 block w-full pl-3 pr-10 py-2 text-base border-gray-300 focus:outline-none focus:ring-blue-500 focus:border-blue-500 sm:text-sm rounded-md shadow-sm h-48'})
    )

    class Meta:
        model = Employee
        fields = [
            'first_name', 'last_name', 'professional_profile', 'employee_number', 
            'phone', 'email', 'available_hours_per_week', 
            'qualifications', 'allowed_shifts'
        ]
        widgets = {
            'first_name': forms.TextInput(attrs={'class': 'mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-blue-500 focus:ring-blue-500 sm:text-sm'}),
            'last_name': forms.TextInput(attrs={'class': 'mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-blue-500 focus:ring-blue-500 sm:text-sm'}),
            'employee_number': forms.TextInput(attrs={'class': 'mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-blue-500 focus:ring-blue-500 sm:text-sm'}),
            'phone': forms.TextInput(attrs={'class': 'mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-blue-500 focus:ring-blue-500 sm:text-sm'}),
            'email': forms.EmailInput(attrs={'class': 'mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-blue-500 focus:ring-blue-500 sm:text-sm'}),
            'available_hours_per_week': forms.NumberInput(attrs={'class': 'mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-blue-500 focus:ring-blue-500 sm:text-sm'}),
        }


class EmployeeAvailabilityForm(forms.ModelForm):
    """
    Formular zum Erstellen/Bearbeiten der Verfügbarkeit eines Mitarbeiters für ein bestimmtes Datum.
    """
    date = forms.DateField(
        label="Datum",
        widget=forms.DateInput(attrs={'type': 'date', 'class': 'mt-1 block w-full pl-3 pr-3 py-2 text-base border-gray-300 focus:outline-none focus:ring-blue-500 focus:border-blue-500 sm:text-sm rounded-md shadow-sm'}),
    )
    is_available = forms.BooleanField(
        label="Verfügbar",
        required=False, # Allow to be unchecked for 'not available'
        widget=forms.CheckboxInput(attrs={'class': 'h-4 w-4 text-blue-600 focus:ring-blue-500 border-gray-300 rounded'})
    )

    class Meta:
        model = EmployeeAvailability
        fields = ['date', 'is_available']


class AbsenceForm(forms.ModelForm):
    """
    Formular zum Erstellen/Bearbeiten von Abwesenheiten eines Mitarbeiters.
    """
    start_date = forms.DateField(
        label="Startdatum",
        widget=forms.DateInput(attrs={'type': 'date', 'class': 'mt-1 block w-full pl-3 pr-3 py-2 text-base border-gray-300 focus:outline-none focus:ring-blue-500 focus:border-blue-500 sm:text-sm rounded-md shadow-sm'}),
    )
    end_date = forms.DateField(
        label="Enddatum",
        widget=forms.DateInput(attrs={'type': 'date', 'class': 'mt-1 block w-full pl-3 pr-3 py-2 text-base border-gray-300 focus:outline-none focus:ring-blue-500 focus:border-blue-500 sm:text-sm rounded-md shadow-sm'}),
    )
    type = forms.ChoiceField( # Feldname zu 'type' geändert
        choices=Absence.ABSENCE_TYPES_CHOICES, # Choices zu 'Absence.ABSENCE_TYPES' geändert
        label="Abwesenheitstyp",
        widget=forms.Select(attrs={'class': 'mt-1 block w-full pl-3 pr-10 py-2 text-base border-gray-300 focus:outline-none focus:ring-blue-500 focus:border-blue-500 sm:text-sm rounded-md shadow-sm'})
    )
    approved = forms.BooleanField(
        label="Genehmigt",
        required=False,
        widget=forms.CheckboxInput(attrs={'class': 'h-4 w-4 text-blue-600 focus:ring-blue-500 border-gray-300 rounded'})
    )

    class Meta:
        model = Absence
        fields = ['start_date', 'end_date', 'type', 'approved'] # Feld 'absence_type' zu 'type' geändert

    def clean(self):
        cleaned_data = super().clean()
        start_date = cleaned_data.get('start_date')
        end_date = cleaned_data.get('end_date')

        if start_date and end_date and end_date < start_date:
            raise ValidationError("Enddatum darf nicht vor dem Startdatum liegen.")
        return cleaned_data

class AutomaticScheduleForm(forms.Form):
    """
    Formular zur Konfiguration der automatischen Dienstplanerstellung.
    """
    ward = forms.ModelChoiceField(
        queryset=Ward.objects.all().order_by('name'),
        label="Station",
        empty_label="--- Station auswählen ---",
        widget=forms.Select(attrs={'class': 'mt-1 block w-full pl-3 pr-10 py-2 text-base border-gray-300 focus:outline-none focus:ring-blue-500 focus:border-blue-500 sm:text-sm rounded-md shadow-sm'})
    )

    year = forms.IntegerField(
        label="Jahr",
        initial=datetime.date.today().year,
        widget=forms.NumberInput(attrs={'class': 'mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-blue-500 focus:ring-blue-500 sm:text-sm'})
    )

    month = forms.ChoiceField(
        label="Monat",
        choices=[(i, datetime.date(2000, i, 1).strftime('%B')) for i in range(1, 13)],
        initial=datetime.date.today().month,
        widget=forms.Select(attrs={'class': 'mt-1 block w-full pl-3 pr-10 py-2 text-base border-gray-300 focus:outline-none focus:ring-blue-500 focus:border-blue-500 sm:text-sm rounded-md shadow-sm'})
    )

    min_rest_hours = forms.DecimalField(
        label="Mindestruhezeit zwischen Schichten (Stunden)",
        min_value=0,
        decimal_places=1,
        initial=11.0,
        widget=forms.NumberInput(attrs={'class': 'mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-blue-500 focus:ring-blue-500 sm:text-sm'})
    )

    max_consecutive_shifts = forms.IntegerField(
        label="Maximale aufeinanderfolgende Arbeitstage",
        min_value=1,
        initial=6,
        widget=forms.NumberInput(attrs={'class': 'mt-1 block w-full rounded-md border-gray-300 shadow-sm focus:border-blue-500 focus:ring-blue-500 sm:text-sm'})
    )

    overwrite_existing = forms.BooleanField(
        label="Bestehende Zuweisungen überschreiben?",
        required=False,
        initial=False,
        widget=forms.CheckboxInput(attrs={'class': 'focus:ring-blue-500 h-4 w-4 text-blue-600 border-gray-300 rounded'})
    )