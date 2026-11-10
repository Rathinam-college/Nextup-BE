# Generated for RoutineWorkItem count and RoutineWorkLog count tracking

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('tasks', '0008_routineworkitem_routineworklog'),
    ]

    operations = [
        migrations.AddField(
            model_name='routineworkitem',
            name='last_completed_count',
            field=models.IntegerField(blank=True, default=0, null=True),
        ),
        migrations.AddField(
            model_name='routineworkitem',
            name='target_count',
            field=models.IntegerField(blank=True, default=0, null=True),
        ),
        migrations.AddField(
            model_name='routineworkitem',
            name='unit',
            field=models.CharField(blank=True, default='', max_length=50),
        ),
        migrations.AddField(
            model_name='routineworklog',
            name='count',
            field=models.IntegerField(blank=True, default=1, null=True),
        ),
    ]

