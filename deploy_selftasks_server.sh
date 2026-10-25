#!/bin/bash
set -e

echo "[*] Copying SelfTask & SelfNote files into nextup_backend container..."
mkdir -p /home/rathinam/nextup-deploy/backend/tasks/migrations
cp /home/rathinam/nextup-deploy/backend/tasks/models.py /home/rathinam/nextup-deploy/backend/tasks/models.py
docker cp /home/rathinam/nextup-deploy/backend/tasks/models.py nextup_backend:/app/tasks/models.py
docker cp /home/rathinam/nextup-deploy/backend/tasks/serializers.py nextup_backend:/app/tasks/serializers.py
docker cp /home/rathinam/nextup-deploy/backend/tasks/views.py nextup_backend:/app/tasks/views.py
docker cp /home/rathinam/nextup-deploy/backend/tasks/urls.py nextup_backend:/app/tasks/urls.py
docker cp /home/rathinam/nextup-deploy/backend/tasks/migrations/0004_selfnote_selftask.py nextup_backend:/app/tasks/migrations/0004_selfnote_selftask.py

echo "[*] Running migration in nextup_backend..."
docker exec nextup_backend python manage.py migrate

echo "[*] Restarting nextup_backend container..."
docker restart nextup_backend

echo "[*] Production backend updated with SelfTask & SelfNote tables successfully!"
