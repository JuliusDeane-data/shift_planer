# shift_planer/management/commands/generate_schedule.py

from django.core.management.base import BaseCommand, CommandError
from shift_planer.models import Ward # Only Ward needed for lookup
from shift_planer.scheduler import ShiftScheduler # Import the new scheduler
import datetime
import calendar

# Define default constants for CLI, will be overridden by form if used via UI
DEFAULT_MIN_REST_HOURS_BETWEEN_SHIFTS = 11.0
DEFAULT_MAX_CONSECUTIVE_SHIFTS = 6

class Command(BaseCommand):
    help = 'Generates an automatic shift schedule for a given month and ward, with advanced constraints. Now uses ShiftScheduler.'

    def add_arguments(self, parser):
        parser.add_argument('year', type=int, help='Year for the schedule (e.g., 2025)')
        parser.add_argument('month', type=int, help='Month for the schedule (1-12)')
        parser.add_argument('ward_slug', type=str, help='Slug of the ward for which to generate the schedule (e.g., "station-1")')
        parser.add_argument('--overwrite', action='store_true', help='Overwrite existing assignments for the given month and ward.')
        parser.add_argument('--min-rest-hours', type=float, default=DEFAULT_MIN_REST_HOURS_BETWEEN_SHIFTS,
                            help=f'Minimum rest hours between shifts (default: {DEFAULT_MIN_REST_HOURS_BETWEEN_SHIFTS}).')
        parser.add_argument('--max-consecutive-shifts', type=int, default=DEFAULT_MAX_CONSECUTIVE_SHIFTS,
                            help=f'Maximum consecutive shifts allowed (default: {DEFAULT_MAX_CONSECUTIVE_SHIFTS}).')


    def handle(self, *args, **options):
        year = options['year']
        month = options['month']
        ward_slug = options['ward_slug']
        overwrite = options['overwrite']
        min_rest_hours = options['min_rest_hours']
        max_consecutive_shifts = options['max_consecutive_shifts']

        self.stdout.write(f"Attempting to generate schedule for {calendar.month_name[month]} {year} on Ward: {ward_slug}")
        self.stdout.write(f"Parameters: Min Rest Hours={min_rest_hours}, Max Consecutive Shifts={max_consecutive_shifts}")


        # Initialize the scheduler
        scheduler = ShiftScheduler(min_rest_hours, max_consecutive_shifts)

        # Call the generate_schedule method from the scheduler
        result = scheduler.generate_schedule(
            year=year, 
            month=month, 
            ward_slug=ward_slug, 
            overwrite=overwrite
        )

        # Print logs from the scheduler
        for msg in scheduler.get_logs():
            if "[ERROR]" in msg:
                self.stdout.write(self.style.ERROR(msg))
            elif "[WARNING]" in msg:
                self.stdout.write(self.style.WARNING(msg))
            else:
                self.stdout.write(self.style.SUCCESS(msg)) # Use SUCCESS for general info logs

        if result["success"]:
            self.stdout.write(self.style.SUCCESS(f"Schedule generation finished: {result['message']}"))
        else:
            raise CommandError(f"Schedule generation failed: {result['message']}")

