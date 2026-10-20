#!/bin/sh
set -e

echo "============================================================"
echo " Starting Task Tracker Enterprise Backend..."
echo " Target Database: ${DB_HOST:-db}:${DB_PORT:-5432}/${DB_NAME:-task_tracker_db}"
echo "============================================================"

# Wait for PostgreSQL to become ready
echo "[1/4] Waiting for PostgreSQL database connection..."
until pg_isready -h "${DB_HOST:-db}" -p "${DB_PORT:-5432}" -U "${DB_USER:-postgres}" >/dev/null 2>&1; do
    echo "      Database is unavailable - sleeping 1 second..."
    sleep 1
done
echo "      PostgreSQL is online and accepting connections!"

# Run migrations
echo "[2/4] Applying database schema migrations..."
python manage.py migrate --noinput

# Verify initial seed data and Super Admin account
echo "[3/4] Verifying administrator account and sample data..."
python -c "
import os, sys, django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'task_tracker.settings')
django.setup()

from tasks.models import User, Department

force_seed = os.getenv('SEED_DATA', '0') == '1'

if not User.objects.exists() or force_seed:
    print('      -> Empty database detected or SEED_DATA=1 set.')
    print('      -> Seeding default departments, staff personas, and sample tasks...')
    try:
        from seed_data import run_seed
        run_seed()
    except Exception as e:
        print(f'      [!] Error during seed_data: {e}')
else:
    print(f'      -> Existing database detected ({User.objects.count()} users, {Department.objects.count()} departments).')
    # Always ensure primary Super Admin exists
    admin_user = User.objects.filter(username='admin').first()
    if not admin_user:
        User.objects.create_superuser(
            username='admin',
            email='admin@tasktracker.enterprise',
            password='admin',
            role=User.ROLE_SUPER_ADMIN,
            job_title='System Administrator'
        )
        print('      -> Created Master Super Admin (admin / admin).')
    else:
        if not admin_user.is_superuser or admin_user.role != User.ROLE_SUPER_ADMIN:
            admin_user.role = User.ROLE_SUPER_ADMIN
            admin_user.is_superuser = True
            admin_user.is_staff = True
            admin_user.is_active = True
            admin_user.set_password('admin')
            admin_user.save()
            print('      -> Re-asserted Master Super Admin credentials (admin / admin).')
"

echo "[4/4] Starting Django application server..."
echo "============================================================"
echo " Backend REST API ready at http://0.0.0.0:8000/api/"
echo " Django Administration at http://0.0.0.0:8000/admin/"
echo "============================================================"

exec "$@"
