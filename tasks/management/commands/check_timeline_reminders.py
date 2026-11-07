import logging
from django.core.management.base import BaseCommand
from tasks.services import check_and_dispatch_all_timeline_reminders

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Scans all active tasks with deadlines, calculates relative timelines, and dispatches automated reminder emails (Monday to Saturday, silenced on Sunday).'

    def add_arguments(self, parser):
        parser.add_argument(
            '--force',
            action='store_true',
            help='Force timeline check even if today is Sunday (holiday).',
        )

    def handle(self, *args, **options):
        force = options.get('force', False)
        self.stdout.write(self.style.NOTICE("[TIMELINE] Starting task timeline deadline scanner (Active: Mon-Sat, Sunday Holiday)..."))
        
        try:
            results = check_and_dispatch_all_timeline_reminders(force=force)
            if results.get('holiday_notice'):
                self.stdout.write(self.style.WARNING(f"[HOLIDAY] {results['holiday_notice']}"))
                return
            
            self.stdout.write(self.style.SUCCESS(
                f"[OK] Timeline scan finished successfully!\n"
                f"   - Active tasks inspected: {results['tasks_checked']}\n"
                f"   - Reminder emails sent:   {results['emails_dispatched']}"
            ))
            
            for item in results.get('items', []):
                self.stdout.write(
                    f"   * Task #{item['task_id']} '{item['title']}' -> "
                    f"Timeline: {item['timeline_text']} (Assigned: {item['assignee_email']})"
                )
        except Exception as e:
            self.stderr.write(self.style.ERROR(f"[ERROR] Error during timeline scan: {str(e)}"))
            logger.exception("Timeline scan command failed")
