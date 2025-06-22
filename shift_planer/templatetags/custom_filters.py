# shift_planer/templatetags/custom_filters.py

from django import template
from itertools import groupby

register = template.Library()

@register.filter(name='get_item')
def get_item(dictionary, key):
    """
    Allows dictionary access in templates.
    Usage: {{ dict|get_item:key }}
    
    This version is more robust for chaining, returning an empty dict
    if the input dictionary is None or not a dictionary.
    """
    # Überprüfen, ob 'dictionary' tatsächlich ein Dictionary ist.
    # Wenn nicht, gib ein leeres Dictionary zurück, um weitere Fehler zu vermeiden.
    if isinstance(dictionary, dict):
        # Gib den Wert für den Schlüssel zurück, oder ein leeres Dictionary, wenn der Schlüssel nicht gefunden wird.
        # Dies verhindert, dass der nachfolgende .get()-Aufruf fehlschlägt, wenn das Ergebnis None ist.
        return dictionary.get(key, {}) 
    return {} # Wenn das anfängliche 'dictionary', das dem Filter übergeben wurde, None oder kein Dict ist, gib ein leeres Dict zurück

@register.filter(name='group_by_shift')
def group_by_shift(assignments):
    """
    Groups a list of ShiftAssignment objects by their shift.
    Returns a list of objects, each with 'shift' and 'assignments' attributes.
    """
    grouped_data = []
    # Sort assignments by shift (assuming shift objects are comparable or have a consistent ID/name)
    # Important: Ensure assignments are sorted by shift first for groupby to work correctly
    # Filter out None assignments, just in case
    assignments = [a for a in assignments if a is not None]
    if not assignments:
        return []

    assignments_sorted = sorted(assignments, key=lambda x: x.shift.pk) 
    
    for shift_obj, group in groupby(assignments_sorted, key=lambda x: x.shift):
        grouped_data.append({
            'id': shift_obj.id, # Add shift ID for URL reversing
            'get_name_display': shift_obj.get_name_display, # For displaying shift name
            'start_time': shift_obj.start_time,
            'end_time': shift_obj.end_time,
            'assignments': list(group)
        })
    # Sort the grouped data by shift start time for consistent display
    return sorted(grouped_data, key=lambda x: x['start_time'])

@register.filter(name='has_conflict_status')
def has_conflict_status(assignments):
    """
    Checks if any assignment in a list has the 'KONFLIKT' status.
    Usage: {% if shift_obj.assignments|has_conflict_status %}
    """
    if not assignments: # Handle empty or None list
        return False
    for assignment in assignments:
        if assignment and assignment.status == 'CONFLICT': # Check if assignment is not None too
            return True
    return False

@register.filter(name='has_conflict_in_assignments')
def has_conflict_in_assignments(assignments):
    """
    Checks if any assignment in the given list has the status 'KONFLIKT'.
    This filter is used on the list of assignments for a specific shift.
    Usage: {{ shift_details.assignments|has_conflict_in_assignments }}
    """
    if not assignments:
        return False
    for assignment in assignments:
        if assignment and assignment.status == 'CONFLICT':
            return True
    return False
