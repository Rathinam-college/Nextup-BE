from django.apps import AppConfig
import os
import sys


class TasksConfig(AppConfig):
    name = 'tasks'

    def ready(self):
        # Prevent starting twice during development autoreload or in migration commands
        if 'runserver' in sys.argv and os.environ.get('RUN_MAIN') != 'true':
            return
        if any(cmd in sys.argv for cmd in ['makemigrations', 'migrate', 'collectstatic', 'test']):
            return

        try:
            from .scheduler import start_india_work_hours_scheduler
            start_india_work_hours_scheduler()
        except Exception as e:
            print(f"[TasksConfig] Could not start scheduler: {e}")
