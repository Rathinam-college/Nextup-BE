import logging
from django.core.management.base import BaseCommand
from tasks.services import check_and_dispatch_all_timeline_reminders

logger = logging.getLogger(__name__)

class Command(BaseCommand):
    help = 'Scans all active tasks with deadlines, calculates relative timelines, and dispatches automated reminder emails.'

    def handle(self, *args, **options):
        self.stdout.write(self.style.NOTICE("[TIMELINE] Starting task timeline deadline scanner..."))
        
        try:
            results = check_and_dispatch_all_timeline_reminders()
            
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
