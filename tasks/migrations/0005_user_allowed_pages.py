from django.db import migrations, models

def populate_default_allowed_pages(apps, schema_editor):
    User = apps.get_model('tasks', 'User')
    all_pages = [
        'board', 'table', 'list', 'calendar', 'self_desk',
        'today', 'approvals', 'departments', 'staff', 'report', 'settings'
    ]
    dept_manager_pages = [
        'board', 'table', 'list', 'calendar', 'self_desk',
        'departments', 'staff', 'report'
    ]
    staff_pages = [
        'board', 'table', 'list', 'calendar', 'self_desk'
    ]

    for user in User.objects.all():
        if user.role in ['SUPER_ADMIN', 'GENERAL_MANAGER']:
            user.allowed_pages = all_pages
        elif user.role == 'DEPT_MANAGER':
            user.allowed_pages = dept_manager_pages
        else:
            user.allowed_pages = staff_pages
        user.save(update_fields=['allowed_pages'])


class Migration(migrations.Migration):

    dependencies = [
        ('tasks', '0004_selfnote_selftask'),
    ]

    operations = [
        migrations.AddField(
            model_name='user',
            name='allowed_pages',
            field=models.JSONField(blank=True, default=list),
        ),
        migrations.RunPython(
            populate_default_allowed_pages,
            reverse_code=migrations.RunPython.noop
        ),
    ]
