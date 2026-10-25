#!/bin/bash
set -e

echo "[*] Copying updated backend files into nextup_backend container..."
mkdir -p /home/rathinam/nextup-deploy/backend/tasks/migrations
mv /home/rathinam/nextup-deploy/backend/tasks/0003_task_is_gm_own_task.py /home/rathinam/nextup-deploy/backend/tasks/migrations/0003_task_is_gm_own_task.py 2>/dev/null || true

docker cp /home/rathinam/nextup-deploy/backend/tasks/models.py nextup_backend:/app/tasks/models.py
docker cp /home/rathinam/nextup-deploy/backend/tasks/serializers.py nextup_backend:/app/tasks/serializers.py
docker cp /home/rathinam/nextup-deploy/backend/tasks/views.py nextup_backend:/app/tasks/views.py
docker cp /home/rathinam/nextup-deploy/backend/tasks/services.py nextup_backend:/app/tasks/services.py
docker cp /home/rathinam/nextup-deploy/backend/tasks/migrations/0003_task_is_gm_own_task.py nextup_backend:/app/tasks/migrations/0003_task_is_gm_own_task.py

echo "[*] Running migrations in nextup_backend..."
docker exec nextup_backend python manage.py migrate

echo "[*] Ensuring GM department exists and flagging GM tasks..."
docker exec nextup_backend python -c "
import os, django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'task_tracker.settings')
django.setup()
from tasks.models import Department, Task
d, created = Department.objects.get_or_create(code='GM', defaults={'name': 'General Management', 'description': 'Executive management and institutional leadership.'})
print('GM Dept exists:', d.name, '(created:', created, ')')
cnt = Task.objects.filter(assigned_to__role__in=['GENERAL_MANAGER', 'SUPER_ADMIN']).update(is_gm_own_task=True)
print('Existing GM tasks flagged as is_gm_own_task=True:', cnt)
"

echo "[*] Restarting nextup_backend container..."
docker restart nextup_backend

echo "[*] Backend update complete!"
